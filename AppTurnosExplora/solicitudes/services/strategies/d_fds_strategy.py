"""
D FDS Strategy - Doblada de Fin de Semana

Implementa la lógica de "D FDS": un explorador cede SU día de fin de semana
(sábado o domingo, según alternancia) a un compañero del grupo contrario, que se
dobla ese finde (trabaja su día + el día cedido). El solicitante devuelve el favor
doblándose un finde futuro del mismo mes (fecha de pago).

Reutiliza:
- AlternanciaFinesSemanaService: qué grupo trabaja cada día del finde.
- SolicitudValidator.validar_fecha_pago_mismo_mes_cesion: pago en el mismo mes.
- DobladaDetalle: modelo de detalle (fecha_pago, minutos_deuda).
- DFDSAplicacionService: aplicación de turnos y deudas al aprobar.
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


class DFDSStrategy(SolicitudStrategy):
    """Strategy para "D FDS" (Doblada de Fin de Semana)."""

    def __init__(self):
        super().__init__("D FDS")

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _parse(fecha) -> Optional[Any]:
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
        Jornada BASE (grupo AM/PM) del explorador según su ASIGNACIÓN, no según el Turno del
        día. En fin de semana quien trabaja lo hace AM+PM, así que mirar el Turno del día da
        un grupo equivocado: hay que usar la asignación base (AsignarJornadaExplorador).
        """
        from turnos.models import AsignarJornadaExplorador
        asg = (AsignarJornadaExplorador.objects
               .filter(explorador=explorador, fecha_inicio__lte=fecha)
               .select_related('jornada').order_by('-fecha_inicio').first())
        return asg.jornada.nombre.upper() if asg else None

    def _datos_desde_solicitud(self, solicitud):
        """Reconstruye los datos para re-validar al aprobar (ver base)."""
        det = getattr(solicitud, 'doblada', None)
        return {
            'explorador_solicitante': solicitud.explorador_solicitante,
            'explorador_receptor': solicitud.explorador_receptor,
            'tipo_cambio': solicitud.tipo_cambio,
            'comentario': solicitud.comentario or '',
            'fecha_cambio_turno': solicitud.fecha_cambio_turno,
            'fecha_pago': det.fecha_pago if det else None,
        }

    # --------------------------------------------------------------- validación
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        try:
            from ..solicitud_validator import SolicitudValidator

            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            fecha_cesion_raw = datos.get('fecha_cambio_turno')
            fecha_pago_raw = datos.get('fecha_pago')
            comentario = datos.get('comentario') or ''

            # 1. Requeridos
            if not solicitante:
                return False, "Explorador solicitante es requerido"
            if not receptor:
                return False, "Debe seleccionar el compañero que se doblará el fin de semana"
            if not fecha_cesion_raw:
                return False, "La fecha de fin de semana es requerida"
            if not fecha_pago_raw:
                return False, "La fecha de pago es obligatoria (otro fin de semana del mismo mes)"

            fecha_cesion = self._parse(fecha_cesion_raw)
            fecha_pago = self._parse(fecha_pago_raw)
            if not fecha_cesion or not fecha_pago:
                return False, "Formato de fecha inválido"

            # 2. Empleados
            SolicitudValidator.validar_empleado_activo(solicitante)
            SolicitudValidator.validar_empleado_activo(receptor)
            SolicitudValidator.validar_no_mismo_empleado(solicitante, receptor)
            SolicitudValidator.validar_comentario_obligatorio(comentario, 'la solicitud de D FDS')

            # No DUPLICADOS pendientes (regla de CREACIÓN; se OMITE al re-validar para aprobar).
            if not datos.get('es_revalidacion'):
                SolicitudValidator.validar_solicitante_sin_solicitud_pendiente_en_fecha(solicitante, fecha_cesion)
                SolicitudValidator.validar_receptor_sin_solicitud_pendiente_en_fecha(receptor, fecha_cesion)

            # 3. Ambas fechas deben ser fin de semana (sáb/dom)
            if fecha_cesion.weekday() not in (5, 6):
                return False, "La fecha de cesión debe ser un fin de semana (sábado o domingo)"
            if fecha_pago.weekday() not in (5, 6):
                return False, "La fecha de pago debe ser un fin de semana (sábado o domingo)"

            # 4. Fechas no pasadas / coherencia
            from django.utils import timezone
            hoy = timezone.now().date()
            if fecha_cesion < hoy:
                return False, "No se puede solicitar D FDS para un fin de semana pasado"
            if fecha_pago <= hoy:
                return False, "La fecha de pago debe ser posterior a hoy"
            if fecha_pago == fecha_cesion:
                return False, "La fecha de pago no puede ser la misma que la fecha de cesión"

            # 4b. El pago debe ser el MISMO día del fin de semana que la cesión:
            #     si cedes un domingo, devuelves un domingo; si cedes un sábado, un sábado.
            #     Así cada quien conserva la misma cantidad de sábados/domingos del mes.
            if fecha_cesion.weekday() != fecha_pago.weekday():
                dia_ces = 'domingo' if fecha_cesion.weekday() == 6 else 'sábado'
                return False, (
                    f"Cediste un {dia_ces}: la devolución (pago) también debe ser un {dia_ces}, "
                    f"para que ambos conserven la misma cantidad de {dia_ces}s en el mes."
                )

            # 5. Pago en el mismo mes que la cesión (regla reutilizada de doblada)
            SolicitudValidator.validar_fecha_pago_mismo_mes_cesion(fecha_pago, fecha_cesion)

            # 6. No mantenimiento en ninguna fecha
            SolicitudValidator.validar_no_dia_mantenimiento(fecha_cesion.strftime('%Y-%m-%d'))
            SolicitudValidator.validar_no_dia_mantenimiento(fecha_pago.strftime('%Y-%m-%d'))

            # 7. Grupos: solicitante y receptor deben ser de grupos contrarios
            grupo_sol = self._grupo_base(solicitante, fecha_cesion)
            grupo_rec = self._grupo_base(receptor, fecha_cesion)
            if not grupo_sol or not grupo_rec:
                return False, "No se pudo determinar la jornada base de los exploradores"
            if grupo_sol == grupo_rec:
                return False, (
                    "El compañero debe ser del grupo contrario (el que trabaja el otro día del "
                    "fin de semana). No puedes doblarte con alguien de tu mismo grupo."
                )

            # 8. Al solicitante le corresponde trabajar SU día en la fecha de cesión
            trabaja_cesion = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha_cesion)
            if not trabaja_cesion:
                return False, "No se pudo determinar la alternancia del fin de semana de cesión"
            if grupo_sol != trabaja_cesion:
                return False, (
                    f"Ese día ({fecha_cesion.strftime('%d/%m/%Y')}) no te corresponde trabajar por "
                    f"alternancia (trabaja el grupo {trabaja_cesion}); no tienes un día que ceder. "
                    "Elige el fin de semana en el que sí trabajas."
                )

            # 9. En la fecha de pago, el día a cubrir debe ser el del RECEPTOR
            trabaja_pago = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha_pago)
            if not trabaja_pago:
                return False, "No se pudo determinar la alternancia del fin de semana de pago"
            if grupo_rec != trabaja_pago:
                return False, (
                    f"En la fecha de pago ({fecha_pago.strftime('%d/%m/%Y')}) debes cubrir el día "
                    f"que trabaja tu compañero (grupo {grupo_rec}). Ese día por alternancia trabaja "
                    f"el grupo {trabaja_pago}; elige el día del fin de semana que le corresponde a tu compañero."
                )

            # 9b. FUENTE DE VERDAD ÚNICA (estado_dia): valida con TODAS las capas
            #     (Turno real → día ya comprometido por otra solicitud → especiales → virtual).
            #     Cierra el hueco L2: un día ya cedido/comprometido no se puede volver a usar.
            from turnos.services.turno_service import TurnoService

            est_sol_ces = TurnoService.estado_dia(solicitante, fecha_cesion)
            if not est_sol_ces['trabaja']:
                motivo = est_sol_ces.get('motivo') or 'descansas ese día'
                return False, (
                    f"No tienes un turno que ceder el {fecha_cesion.strftime('%d/%m/%Y')} ({motivo})."
                )

            est_rec_pago = TurnoService.estado_dia(receptor, fecha_pago)
            if not est_rec_pago['trabaja']:
                motivo = est_rec_pago.get('motivo') or 'descansa ese día'
                return False, (
                    f"Tu compañero no trabaja el {fecha_pago.strftime('%d/%m/%Y')} ({motivo}); "
                    f"no hay día que cubrir."
                )

            # 10. Evitar triple turno: receptor sin doblada ya en cesión; solicitante sin doblada ya en pago
            from turnos.models import Turno

            def _ya_doblada(emp, fecha):
                js = {t.jornada.nombre.upper() for t in Turno.objects.filter(explorador=emp, fecha=fecha).select_related('jornada')}
                return 'AM' in js and 'PM' in js

            if _ya_doblada(receptor, fecha_cesion):
                return False, "El compañero ya tiene una doblada (AM+PM) en la fecha de cesión y no puede cubrirte."
            if _ya_doblada(solicitante, fecha_pago):
                return False, "Ya tienes una doblada (AM+PM) en la fecha de pago; no puedes doblarte de nuevo ese día."

            return True, "Solicitud de D FDS válida"

        except ValidationError as e:
            return False, str(e)
        except Exception as e:
            return False, f"Error validando D FDS: {str(e)}"

    # ------------------------------------------------------------------- crear
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        try:
            solicitante = datos.get('explorador_solicitante')
            receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fecha_cesion = datos.get('fecha_cambio_turno')
            fecha_pago = datos.get('fecha_pago')
            minutos_deuda = datos.get('minutos_deuda', 30)

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
                    minutos_deuda=minutos_deuda,
                    tipo_cesion='cesion_completa',
                    empleado_receptor=receptor,
                )

            return solicitud, "Solicitud de D FDS creada correctamente"

        except Exception as e:
            return None, f"Error creando solicitud de D FDS: {str(e)}"

    # ----------------------------------------------------------------- aplicar
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        try:
            from ..d_fds_aplicacion_service import DFDSAplicacionService
            from ..doblada_aplicacion_service import DobladaAplicacionService
            from core.services.cache_service import CacheService

            with transaction.atomic():
                detalle = solicitud.doblada

                # Snapshot para poder revertir (cancelación de 30 min, igual que doblada).
                # Solo la PRIMERA vez: si ya existe, no sobrescribir (una doble aplicación
                # grabaría el estado ya aplicado como "previo" y rompería la reversión).
                if not getattr(detalle, 'snapshot_turnos_previos', None):
                    snapshot = DobladaAplicacionService.capturar_snapshot_turnos_previos(solicitud, detalle)
                    DobladaDetalle.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snapshot)
                    detalle.snapshot_turnos_previos = snapshot

                DFDSAplicacionService.aplicar(solicitud, detalle)
                DFDSAplicacionService.generar_deudas(solicitud, detalle)

            # Invalidar caché de ambos en ambos meses (cesión y pago)
            solicitante = solicitud.explorador_solicitante
            receptor = solicitud.explorador_receptor
            for fecha in (solicitud.fecha_cambio_turno, detalle.fecha_pago):
                if fecha:
                    CacheService.invalidar_cache_turnos_empleado(solicitante.id, fecha.month, fecha.year)
                    CacheService.invalidar_cache_turnos_empleado(receptor.id, fecha.month, fecha.year)

            return True, "D FDS aplicada correctamente (favor y pago agendados)."

        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Error aplicando D FDS")
            return False, f"Error aplicando D FDS: {str(e)}"

    # --------------------------------------------------- empleados disponibles
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado, **kwargs) -> list:
        """
        Compañeros válidos para D FDS: del grupo CONTRARIO al del solicitante en el
        fin de semana de cesión (el grupo que trabaja el otro día del finde).
        """
        try:
            fecha_obj = self._parse(fecha)
            if not fecha_obj or fecha_obj.weekday() not in (5, 6):
                return []

            grupo_sol = self._grupo_base(usuario_actual, fecha_obj)
            if not grupo_sol:
                return []
            grupo_contrario = 'PM' if grupo_sol == 'AM' else 'AM'

            from turnos.models import AsignarJornadaExplorador

            empleados = (
                Empleado.objects.filter(activo=True)
                .exclude(id=usuario_actual.id)
                .select_related('supervisor')
            )
            # Jornada base de cada empleado (1 query)
            bases = {}
            for asg in (
                AsignarJornadaExplorador.objects
                .filter(explorador__in=empleados, fecha_inicio__lte=fecha_obj)
                .select_related('jornada', 'explorador')
                .order_by('explorador_id', '-fecha_inicio')
            ):
                bases.setdefault(asg.explorador_id, asg.jornada.nombre.upper())

            return [e for e in empleados if bases.get(e.id) == grupo_contrario]
        except Exception:
            return []

    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        try:
            from core.services import get_turno_service
            return get_turno_service().get_turno_explorador(explorador_id, fecha)
        except Exception:
            return {}
