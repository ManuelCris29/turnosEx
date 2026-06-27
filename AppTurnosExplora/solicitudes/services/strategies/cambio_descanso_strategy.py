"""
Cambio de Día de Descanso (fin de semana y entre semana).

MODALIDAD FIN DE SEMANA:
- Intercambio IDA Y VUELTA de días trabajados en el fin de semana.
- Ej: Mariana trabaja SAB 4, Jhon trabaja DOM 5 → después: Mariana trabaja DOM 5, Jhon trabaja SAB 4.
- En otra semana del mismo mes se revierte.
- No hay dobladas ni deudas: cada explorador sigue trabajando UN solo día por finde, solo cambia CUÁL.
- Validación de balance: si el mes tiene 5 domingos (impar), se muestra advertencia.

MODALIDAD ENTRE SEMANA (Temporada):
- Intercambio DIRECTO de descansos asignados por el supervisor.
- Ej: Mariana descansa martes, Jhon descansa viernes → después: Mariana descansa viernes, Jhon descansa martes.
- SIN devolución, es un intercambio simple.
- Ambos deben estar en el mismo rango de temporada.
"""
from typing import Dict, Any, Tuple, Optional
from datetime import datetime

from django.core.exceptions import ValidationError
from django.db import transaction

from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
from turnos.services.jornada_service import JornadaService


class CambioDescansoStrategy(SolicitudStrategy):

    def __init__(self):
        super().__init__("CAMBIO DESCANSO")

    @staticmethod
    def _parse(fecha):
        if not fecha:
            return None
        if isinstance(fecha, str):
            try:
                return datetime.strptime(fecha, '%Y-%m-%d').date()
            except ValueError:
                return None
        return fecha

    @staticmethod
    def _grupo_base(explorador: Empleado, fecha) -> Optional[str]:
        """
        Jornada BASE (grupo AM/PM) del explorador según su asignación, NO según los turnos
        del día. En fin de semana quien trabaja lo hace AM+PM, así que los turnos no sirven
        para distinguir el grupo: hay que mirar la asignación base.
        """
        from turnos.models import AsignarJornadaExplorador
        asg = (AsignarJornadaExplorador.objects
               .filter(explorador=explorador, fecha_inicio__lte=fecha)
               .select_related('jornada').order_by('-fecha_inicio').first())
        return asg.jornada.nombre.upper() if asg else None

    @staticmethod
    def _es_festivo(fecha) -> bool:
        from turnos.models import DiaEspecial
        return DiaEspecial.objects.filter(fecha=fecha, tipo='festivo', activo=True).exists()

    @staticmethod
    def _otro_dia_finde(fecha):
        """Retorna el otro día del fin de semana (sábado <-> domingo)."""
        from datetime import timedelta
        if fecha.weekday() == 5:  # sábado
            return fecha + timedelta(days=1)  # domingo
        elif fecha.weekday() == 6:  # domingo
            return fecha - timedelta(days=1)  # sábado
        return None

    @staticmethod
    def _contar_domingos_mes(fecha):
        """Cuenta cuántos domingos hay en el mes de fecha."""
        from datetime import timedelta
        from calendar import monthrange
        year, month = fecha.year, fecha.month
        _, ultimo_dia = monthrange(year, month)
        inicio = fecha.replace(day=1)
        fin = fecha.replace(day=ultimo_dia)
        contador = 0
        actual = inicio
        while actual <= fin:
            if actual.weekday() == 6:  # domingo
                contador += 1
            actual += timedelta(days=1)
        return contador

    @staticmethod
    def _trabaja_dia(explorador, fecha):
        """
        Verifica que el explorador TRABAJE ese día y que ese día esté DISPONIBLE para un
        cambio de descanso, con la regla del sistema:
        1) ¿El día tiene un turno COMPROMETIDO en otra solicitud (tipo_cambio: doblada, d_fds,
           CT, doblada permanente, otro cambio de descanso)? → NO disponible (no se puede tocar
           un día que ya es parte de otra solicitud, aunque ese día se trabaje).
        2) Turno REAL del día (horario importado, sin tipo_cambio) → trabaja.
        3) ¿Una solicitud de CAMBIO DESCANSO aprobada ya lo dejó descansando? → NO trabaja.
        4) En otro caso, turno VIRTUAL (jornada base + alternancia).

        Devuelve (True, jornada) o (False, motivo).
        En fin de semana, quien trabaja lo hace el día completo (AM+PM): eso es NORMAL.
        """
        from turnos.models import Turno
        from turnos.services.turno_service import TurnoService
        from ..cambio_descanso_aplicacion_service import CambioDescansoAplicacionService

        turnos = list(Turno.objects.filter(explorador=explorador, fecha=fecha))

        # 1) Día COMPROMETIDO en otra solicitud (turno con tipo_cambio). No se puede usar para
        #    un cambio de descanso, aunque la persona trabaje ese día (p. ej. media jornada de
        #    una doblada en sábado). Cubre el caso donde el día se TRABAJA comprometido.
        comprometidos = sorted({t.tipo_cambio for t in turnos if t.tipo_cambio})
        if comprometidos:
            return False, (
                f"Ese día ya está comprometido en otra solicitud ({', '.join(comprometidos)}). "
                f"No se puede intercambiar un día que ya es parte de otra gestión."
            )

        # 2) Turno real sin tipo_cambio (horario base materializado) → trabaja.
        if turnos:
            t = TurnoService.get_turno_explorador(explorador.id, fecha.strftime('%Y-%m-%d'))
            return True, (t.get('jornada') if t else 'TRABAJA')

        # 3) ¿Ya cedió este día en otra solicitud de cambio de descanso aprobada (lado descanso)?
        if fecha in CambioDescansoAplicacionService.dias_en_descanso(explorador, fecha, fecha):
            return False, "Día ya comprometido en otro cambio de descanso"

        # 4) Turno virtual (predeterminado)
        t = TurnoService.get_turno_explorador(explorador.id, fecha.strftime('%Y-%m-%d'))
        if not t:
            return False, "Descanso"
        return True, t.get('jornada') or 'TRABAJA'

    # --------------------------------------------------------------- validación
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            from ..solicitud_validator import SolicitudValidator

            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            fecha_cesion = self._parse(datos.get('fecha_cambio_turno'))
            fecha_pago = self._parse(datos.get('fecha_pago'))
            comentario = datos.get('comentario') or ''

            if not solicitante:
                return False, "Explorador solicitante es requerido"
            if not receptor:
                return False, "Debe seleccionar el compañero con quien intercambia el descanso"
            if not fecha_cesion:
                return False, "El día que cambias es requerido"
            if not fecha_pago:
                return False, "El día de devolución es obligatorio (otro día del mismo mes)"

            SolicitudValidator.validar_empleado_activo(solicitante)
            SolicitudValidator.validar_empleado_activo(receptor)
            SolicitudValidator.validar_no_mismo_empleado(solicitante, receptor)
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'el cambio de día de descanso')

            # No DUPLICADOS pendientes: si ya hay una solicitud pendiente para esa fecha (de
            # cualquier tipo, como solicitante o receptor) no se puede enviar otra igual.
            SolicitudValidator.validar_solicitante_sin_solicitud_pendiente_en_fecha(solicitante, fecha_cesion)
            SolicitudValidator.validar_receptor_sin_solicitud_pendiente_en_fecha(receptor, fecha_cesion)

            # Detectar modalidad: fin de semana (sáb/dom) o ENTRE SEMANA (lun-vie).
            es_finde = fecha_cesion.weekday() in (5, 6)
            if not es_finde:
                return self._validar_entre_semana(solicitante, receptor, fecha_cesion, fecha_pago)

            # --- Fin de semana ---
            if fecha_cesion.weekday() not in (5, 6):
                return False, "El día que cambias debe ser un fin de semana (sábado o domingo)"
            if fecha_pago.weekday() not in (5, 6):
                return False, "El día de devolución debe ser un fin de semana (sábado o domingo)"

            from django.utils import timezone
            hoy = timezone.now().date()
            if fecha_cesion < hoy:
                return False, "No se puede cambiar el descanso de un fin de semana pasado"
            if fecha_pago <= hoy:
                return False, "La fecha de devolución debe ser posterior a hoy"
            if fecha_pago == fecha_cesion:
                return False, "La devolución debe ser un fin de semana distinto al que cambias"

            # DÍA OPUESTO (sáb↔dom): el balance de domingos se conserva porque en la cesión
            # trabajas un día y en la devolución trabajas el día contrario por alternancia.
            # Ej: cesión sábado (trabajas) → devolución domingo (trabajas el otro finde).
            if fecha_cesion.weekday() == fecha_pago.weekday():
                dia = 'domingo' if fecha_cesion.weekday() == 6 else 'sábado'
                otro = 'sábado' if fecha_cesion.weekday() == 6 else 'domingo'
                return False, (
                    f"Cambiaste un {dia}: la devolución debe ser un {otro} "
                    f"(el día contrario), para mantener tu balance de domingos en el mes."
                )

            # Mismo mes que la cesión
            SolicitudValidator.validar_fecha_pago_mismo_mes_cesion(fecha_pago, fecha_cesion)

            # Grupos contrarios
            grupo_sol = self._grupo_base(solicitante, fecha_cesion)
            grupo_rec = self._grupo_base(receptor, fecha_cesion)
            if not grupo_sol or not grupo_rec:
                return False, "No se pudo determinar la jornada base de los exploradores"
            if grupo_sol == grupo_rec:
                return False, (
                    "El compañero debe ser del grupo contrario (el que descansa el otro día del "
                    "fin de semana). No puedes intercambiar con alguien de tu mismo grupo."
                )

            # VALIDACIÓN CRÍTICA: Verificar que AMBOS tengan turnos REALES en las fechas.
            # El solicitante debe tener UN turno (su jornada base) en fecha_cesion
            tiene_turno_sol_ces, jor_sol_ces = self._trabaja_dia(solicitante, fecha_cesion)
            if not tiene_turno_sol_ces:
                return False, (
                    f"No tienes un turno válido el {fecha_cesion.strftime('%d/%m/%Y')}. "
                    f"No puedes cambiar descanso sin tu turno normal."
                )

            otro_dia_cesion = self._otro_dia_finde(fecha_cesion)
            tiene_turno_rec_otro, jor_rec_otro = self._trabaja_dia(receptor, otro_dia_cesion)
            if not tiene_turno_rec_otro:
                return False, (
                    f"Tu compañero no tiene un turno válido el {otro_dia_cesion.strftime('%d/%m/%Y')}. "
                    f"No puede hacer el intercambio."
                )

            # El solicitante debe tener UN turno (su jornada base) en fecha_pago
            tiene_turno_sol_pago, jor_sol_pago = self._trabaja_dia(solicitante, fecha_pago)
            if not tiene_turno_sol_pago:
                return False, (
                    f"No tienes un turno válido el {fecha_pago.strftime('%d/%m/%Y')} (devolución). "
                    f"No puedes completar el intercambio."
                )

            otro_dia_pago = self._otro_dia_finde(fecha_pago)
            tiene_turno_rec_otro_pago, jor_rec_otro_pago = self._trabaja_dia(receptor, otro_dia_pago)
            if not tiene_turno_rec_otro_pago:
                return False, (
                    f"Tu compañero no tiene un turno válido el {otro_dia_pago.strftime('%d/%m/%Y')} (devolución). "
                    f"No puede completar el intercambio."
                )

            # ADVERTENCIA (no bloqueo): si el mes tiene 5 domingos, el balance es impar
            if fecha_cesion.weekday() == 6:  # Si estamos intercambiando domingos
                domingos_mes = self._contar_domingos_mes(fecha_cesion)
                if domingos_mes == 5:
                    # Es una advertencia informativa, pero no bloqueamos
                    # El frontend debería mostrar esto, pero no es un error de validación
                    pass  # No es error, solo información

            return True, "Solicitud de cambio de descanso válida"

        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Error validando cambio de descanso: {str(e)}"

    def _validar_entre_semana(self, solicitante, receptor, fecha_cesion, fecha_pago):
        """
        Validación del cambio de descanso ENTRE SEMANA (lun-vie) en temporada.

        Es un intercambio DIRECTO de descansos (SIN devolución):
        Solicitante descansa fecha_cesion, Receptor descansa fecha_pago.
        Después del intercambio: Solicitante descansa fecha_pago, Receptor descansa fecha_cesion.

        NOTA: fecha_pago en este contexto es el "otro descanso" que intercambian,
        no una devolución posterior (no hay ida y vuelta como en fin de semana).
        """
        from django.utils import timezone
        from turnos.services.descanso_semana_service import DescansoSemanaService
        hoy = timezone.now().date()

        if fecha_cesion.weekday() >= 5:
            return False, "El día que cambias debe ser de lunes a viernes."
        if fecha_pago.weekday() >= 5:
            return False, "El compañero solo puede descansar de lunes a viernes."
        if fecha_cesion < hoy:
            return False, "No se puede cambiar el descanso de un día pasado."
        if fecha_pago <= hoy:
            return False, "El descanso del compañero debe ser posterior a hoy."
        if fecha_pago == fecha_cesion:
            return False, "Los descansos deben ser días distintos."

        # Deben estar en el mismo rango (temporada): máximo 30-45 días
        dias_diff = abs((fecha_pago - fecha_cesion).days)
        if dias_diff > 45:
            return False, "Los descansos deben estar en el mismo rango de temporada (máximo 45 días)."

        # Grupos contrarios
        grupo_sol = self._grupo_base(solicitante, fecha_cesion)
        grupo_rec = self._grupo_base(receptor, fecha_cesion)
        if not grupo_sol or not grupo_rec:
            return False, "No se pudo determinar la jornada base de los exploradores."
        if grupo_sol == grupo_rec:
            return False, "El compañero debe ser del grupo contrario para intercambiar."

        # VALIDACIÓN CRÍTICA: Ambos deben tener DescansoSemanaManual en sus fechas
        # El solicitante debe tener descanso en fecha_cesion
        if not DescansoSemanaService.es_descanso_semana_manual(grupo_sol, fecha_cesion):
            return False, (
                f"No tienes un descanso asignado el {fecha_cesion.strftime('%d/%m/%Y')}. "
                f"No puedes cambiar un descanso que no existe."
            )

        # El receptor debe tener descanso en fecha_pago
        if not DescansoSemanaService.es_descanso_semana_manual(grupo_rec, fecha_pago):
            return False, (
                f"Tu compañero no tiene descanso asignado el {fecha_pago.strftime('%d/%m/%Y')}. "
                f"No pueden intercambiar descansos que no están asignados."
            )

        # FUENTE DE VERDAD (L2): además de estar configurado como descanso de temporada, el
        # día debe seguir SIENDO descanso HOY (no ya intercambiado ni comprometido por otra
        # solicitud aprobada). es_descanso_semana_manual mira la CONFIGURACIÓN; estado_dia mira
        # el ESTADO real (igual que "Mis Turnos").
        from turnos.services.turno_service import TurnoService
        if TurnoService.estado_dia(solicitante, fecha_cesion)['trabaja']:
            return False, (
                f"Ese día ({fecha_cesion.strftime('%d/%m/%Y')}) ya no es tu descanso disponible "
                f"(ya lo intercambiaste o está comprometido en otra solicitud). Elige otro."
            )
        if TurnoService.estado_dia(receptor, fecha_pago)['trabaja']:
            return False, (
                f"Tu compañero ya no descansa el {fecha_pago.strftime('%d/%m/%Y')} "
                f"(ya lo intercambió o está comprometido). Elige otro día o compañero."
            )

        return True, "Solicitud de cambio de descanso (entre semana) válida"

    # ------------------------------------------------------------------- crear
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        try:
            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fecha_cesion = datos.get('fecha_cambio_turno')
            fecha_pago = datos.get('fecha_pago')

            with transaction.atomic():
                solicitud = SolicitudCambio.objects.create(
                    explorador_solicitante=solicitante,
                    explorador_receptor=receptor,
                    tipo_cambio=tipo_cambio,
                    comentario=comentario,
                    fecha_cambio_turno=fecha_cesion,
                    estado='pendiente',
                )
                DobladaDetalle.objects.create(
                    solicitud=solicitud,
                    fecha_pago=fecha_pago,
                    minutos_deuda=0,  # intercambio puro, sin deuda
                    tipo_cesion='cesion_completa',
                    empleado_receptor=receptor,
                )
            try:
                from ..notificacion_service import NotificacionService
                NotificacionService.crear_notificacion_solicitud(solicitud)
            except Exception:
                pass
            return solicitud, "Solicitud de cambio de descanso creada correctamente"
        except Exception as e:
            return None, f"Error creando solicitud de cambio de descanso: {str(e)}"

    # ----------------------------------------------------------------- aplicar
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        try:
            from ..cambio_descanso_aplicacion_service import CambioDescansoAplicacionService
            from core.services.cache_service import CacheService

            with transaction.atomic():
                detalle = solicitud.doblada
                if solicitud.fecha_cambio_turno and solicitud.fecha_cambio_turno.weekday() in (5, 6):
                    CambioDescansoAplicacionService.aplicar(solicitud, detalle)
                else:
                    CambioDescansoAplicacionService.aplicar_entre_semana(solicitud, detalle)

            for fecha in (solicitud.fecha_cambio_turno, solicitud.doblada.fecha_pago):
                if fecha:
                    CacheService.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                    CacheService.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)
            return True, "Cambio de día de descanso aplicado correctamente."
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Error aplicando cambio de descanso")
            return False, f"Error aplicando cambio de descanso: {str(e)}"

    # --------------------------------------------------- empleados disponibles
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """Compañeros del grupo CONTRARIO al solicitante en ese fin de semana."""
        try:
            fecha_obj = self._parse(fecha)
            if not fecha_obj:
                return []
            grupo_sol = self._grupo_base(usuario_actual, fecha_obj)
            if not grupo_sol:
                return []
            grupo_contrario = 'PM' if grupo_sol == 'AM' else 'AM'

            from turnos.models import AsignarJornadaExplorador
            empleados = (Empleado.objects.filter(activo=True)
                         .exclude(id=usuario_actual.id).select_related('supervisor'))
            bases = {}
            for asg in (AsignarJornadaExplorador.objects
                        .filter(explorador__in=empleados, fecha_inicio__lte=fecha_obj)
                        .select_related('jornada', 'explorador').order_by('explorador_id', '-fecha_inicio')):
                bases.setdefault(asg.explorador_id, asg.jornada.nombre.upper())
            return [e for e in empleados if bases.get(e.id) == grupo_contrario]
        except Exception:
            return []
