"""
Cambio de Día de Descanso (fin de semana).

Intercambio de descansos (descanso por descanso) entre dos exploradores de grupos
contrarios, con mutuo acuerdo. Es IDA Y VUELTA dentro del mismo mes para conservar el
balance de domingos: el finde de cesión y el de devolución son del MISMO tipo de día
(sáb↔sáb o dom↔dom), lo que garantiza que cada quien quede con los mismos domingos.

No hay doblada ni deudas: cada explorador sigue trabajando un solo día por finde, solo
cambia cuál.
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
        j = JornadaService.get_jornada_explorador_fecha(explorador.id, fecha.strftime('%Y-%m-%d'))
        return j.nombre.upper() if j else None

    @staticmethod
    def _es_festivo(fecha) -> bool:
        from turnos.models import DiaEspecial
        return DiaEspecial.objects.filter(fecha=fecha, tipo='festivo', activo=True).exists()

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

            # MISMO tipo de día (sáb↔sáb o dom↔dom): conserva el balance de domingos.
            if fecha_cesion.weekday() != fecha_pago.weekday():
                dia = 'domingo' if fecha_cesion.weekday() == 6 else 'sábado'
                return False, (
                    f"Cambiaste un {dia}: la devolución también debe ser un {dia}, "
                    f"para que ambos queden con la misma cantidad de domingos/sábados en el mes."
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

            # En la cesión, el día que cambias es el TUYO (tú lo trabajas por alternancia)
            trabaja_cesion = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha_cesion)
            if grupo_sol != trabaja_cesion:
                return False, (
                    f"Ese día ({fecha_cesion.strftime('%d/%m/%Y')}) no te corresponde trabajar por "
                    f"alternancia; no es tu día para cambiarlo. Elige el día del finde que trabajas."
                )

            # En la devolución, el día debe ser el del RECEPTOR (él lo trabaja por alternancia)
            trabaja_pago = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha_pago)
            if grupo_rec != trabaja_pago:
                return False, (
                    f"En la devolución ({fecha_pago.strftime('%d/%m/%Y')}) debes tomar el día que "
                    f"trabaja tu compañero. Ese día por alternancia trabaja el grupo {trabaja_pago}; "
                    f"elige el día del finde que le corresponde a tu compañero."
                )

            # Evitar conflictos: ninguno debe tener ya una doblada (AM+PM por otro cambio)
            # en los días afectados.
            from turnos.models import Turno
            from datetime import timedelta

            def _ya_doblada(emp, fecha):
                js = {t.jornada.nombre.upper() for t in Turno.objects.filter(explorador=emp, fecha=fecha)
                      .select_related('jornada') if t.tipo_cambio}
                return 'AM' in js and 'PM' in js

            for f in (fecha_cesion, fecha_pago, fecha_cesion + timedelta(days=1) if fecha_cesion.weekday() == 5 else fecha_cesion - timedelta(days=1)):
                if _ya_doblada(solicitante, f) or _ya_doblada(receptor, f):
                    return False, ("Hay una doblada existente en uno de esos días que impide el "
                                   "intercambio. Resuélvela primero o elige otro fin de semana.")

            return True, "Solicitud de cambio de descanso válida"

        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Error validando cambio de descanso: {str(e)}"

    def _validar_entre_semana(self, solicitante, receptor, fecha_cesion, fecha_pago):
        """
        Validación del cambio de descanso ENTRE SEMANA (lun-vie), con la regla
        FESTIVO POR FESTIVO: si el día que cambias es festivo, la devolución también debe
        ser un festivo del mismo mes (dentro de 30 días).
        """
        from django.utils import timezone
        hoy = timezone.now().date()

        if fecha_pago.weekday() >= 5:
            return False, "Para un cambio entre semana, la devolución también debe ser de lunes a viernes."
        if fecha_cesion < hoy:
            return False, "No se puede cambiar el descanso de un día pasado."
        if fecha_pago <= hoy:
            return False, "La fecha de devolución debe ser posterior a hoy."
        if fecha_pago == fecha_cesion:
            return False, "La devolución debe ser un día distinto al que cambias."

        # Mismo mes
        if (fecha_cesion.year, fecha_cesion.month) != (fecha_pago.year, fecha_pago.month):
            return False, "El cambio de descanso debe ser dentro del mismo mes."

        # Grupos contrarios
        grupo_sol = self._grupo_base(solicitante, fecha_cesion)
        grupo_rec = self._grupo_base(receptor, fecha_cesion)
        if not grupo_sol or not grupo_rec:
            return False, "No se pudo determinar la jornada base de los exploradores."
        if grupo_sol == grupo_rec:
            return False, "El compañero debe ser del grupo contrario para intercambiar el descanso."

        # Regla FESTIVO POR FESTIVO
        ces_fest = self._es_festivo(fecha_cesion)
        pago_fest = self._es_festivo(fecha_pago)
        if ces_fest != pago_fest:
            cual = 'El día que cambias' if ces_fest else 'La devolución'
            return False, (
                f"{cual} es festivo: el cambio debe ser FESTIVO POR FESTIVO. "
                f"Elige otro festivo del mismo mes (dentro de 30 días) para intercambiar."
            )
        if ces_fest and pago_fest and abs((fecha_pago - fecha_cesion).days) > 30:
            return False, "Festivo por festivo: ambos festivos deben estar dentro de un lapso de 30 días."

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
