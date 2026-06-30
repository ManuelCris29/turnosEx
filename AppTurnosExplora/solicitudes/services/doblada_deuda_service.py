"""
DobladaDeudaService

Responsabilidad: generar las deudas (entre exploradores y corporativas) cuando
una doblada es aprobada. No toca turnos.
"""
from datetime import date
import logging

from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from .deuda_service import DeudaService
from .deuda_corporativa_service import DeudaCorporativaService

logger = logging.getLogger(__name__)


class DobladaDeudaService:

    @staticmethod
    def generar_deudas_doblada(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Genera las deudas entre exploradores y corporativas asociadas a una doblada.

        Reglas:
        - Se crea una deuda entre exploradores (estado 'pagada' porque ambas dobladas ya están aplicadas)
        - La deuda corporativa (30 minutos) solo se genera si la doblada es efectiva en esa fecha,
          es decir, si la jornada real del día es DOBLADA (AM+PM) según los turnos aplicados.
        """
        from turnos.services.jornada_service import JornadaService
        from turnos.services.turno_service import TurnoService

        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor

        # Determinar jornada cedida
        if detalle.jornada_cedida:
            jornada_cedida_nombre = detalle.jornada_cedida.upper()
        else:
            jornada_solicitante = JornadaService.get_jornada_explorador_fecha(
                solicitante.id, fecha_cesion.strftime('%Y-%m-%d')
            )
            jornada_cedida_nombre = jornada_solicitante.nombre.upper()

        # Deuda entre exploradores
        DeudaService.crear_deuda(
            deudor=solicitante,
            acreedor=receptor,
            solicitud=solicitud,
            fecha_generacion=fecha_cesion,
            fecha_pago_pactada=fecha_pago,
            fecha_pago_real=fecha_pago,
            jornada_cedida=jornada_cedida_nombre,
            media_jornada=True,
        )

        # Deuda residual: pago en sábado cubriendo AMBAS jornadas
        if (fecha_pago.weekday() == 5
                and (getattr(detalle, 'jornada_pago_sabado', '') or '').upper() == 'AMBAS'
                and getattr(detalle, 'fecha_pago_semana', None)):
            fecha_semana = detalle.fecha_pago_semana
            jornada_sol_semana = JornadaService.get_jornada_explorador_fecha(
                solicitante.id, fecha_semana.strftime('%Y-%m-%d')
            )
            jornada_residual = (
                jornada_sol_semana.nombre.upper()
                if jornada_sol_semana else jornada_cedida_nombre
            )
            DeudaService.crear_deuda(
                deudor=receptor,
                acreedor=solicitante,
                solicitud=solicitud,
                fecha_generacion=fecha_pago,
                fecha_pago_pactada=fecha_semana,
                fecha_pago_real=fecha_semana,
                jornada_cedida=jornada_residual,
                media_jornada=True,
            )
            logger.info(
                "Deuda residual (pago sábado AMBAS): %s devuelve la jornada %s a %s el %s (en semana).",
                receptor.nombre, jornada_residual, solicitante.nombre, fecha_semana,
            )

        # Deuda corporativa (30 min) — solo por doblada efectiva
        def _registrar_deuda_corporativa_si_doblada(explorador: Empleado, fecha_doblada: date, comentario: str) -> None:
            if not DeudaCorporativaService.aplica_deuda_doblada(fecha_doblada):
                logger.info(
                    "No se genera deuda corporativa para %s en %s: fin de semana o festivo.",
                    explorador.nombre, fecha_doblada,
                )
                return
            jornada_display = TurnoService.obtener_jornada_display(explorador, fecha_doblada)
            if jornada_display == 'DOBLADA':
                DeudaCorporativaService.crear_deuda_corporativa(
                    explorador=explorador,
                    minutos=30,
                    fecha_generacion=date.today(),
                    fecha_doblada=fecha_doblada,
                    solicitud=solicitud,
                    comentario=comentario,
                )
                logger.info(
                    "Deuda corporativa generada (30 min) para %s en %s por jornada DOBLADA.",
                    explorador.nombre, fecha_doblada,
                )
            else:
                logger.info(
                    "No se genera deuda corporativa para %s en %s: jornada_display=%r",
                    explorador.nombre, fecha_doblada, jornada_display,
                )

        _registrar_deuda_corporativa_si_doblada(
            explorador=receptor,
            fecha_doblada=fecha_cesion,
            comentario=f'Doblada efectiva en fecha de cesión ({fecha_cesion})',
        )
        _registrar_deuda_corporativa_si_doblada(
            explorador=solicitante,
            fecha_doblada=fecha_pago,
            comentario=f'Doblada efectiva en fecha de pago ({fecha_pago})',
        )

        if (fecha_pago.weekday() == 5
                and (getattr(detalle, 'jornada_pago_sabado', '') or '').upper() == 'AMBAS'
                and getattr(detalle, 'fecha_pago_semana', None)):
            _registrar_deuda_corporativa_si_doblada(
                explorador=receptor,
                fecha_doblada=detalle.fecha_pago_semana,
                comentario=f'Doblada efectiva (pago en semana del sábado AMBAS) ({detalle.fecha_pago_semana})',
            )

        # Doblada de semana cedida y pagada en sábado: el emisor debe sus 30 min de la cesión de semana
        if (fecha_cesion.weekday() < 5
                and fecha_pago.weekday() == 5
                and DeudaCorporativaService.aplica_deuda_doblada(fecha_cesion)):
            _key_emisor = f"{solicitante.id}:{fecha_cesion.isoformat()}"
            _prev = (getattr(detalle, 'snapshot_turnos_previos', None) or {}).get(_key_emisor, [])
            _jornadas_prev = {(t.get('jornada_nombre') or '').upper() for t in _prev}
            if 'AM' in _jornadas_prev and 'PM' in _jornadas_prev:
                from solicitudes.models import DeudaCorporativa
                _ya = DeudaCorporativa.objects.filter(
                    explorador=solicitante, fecha_doblada=fecha_cesion
                ).exclude(estado='cancelada').exists()
                if not _ya:
                    DeudaCorporativaService.crear_deuda_corporativa(
                        explorador=solicitante,
                        minutos=30,
                        fecha_generacion=date.today(),
                        fecha_doblada=fecha_cesion,
                        solicitud=solicitud,
                        comentario=(
                            f'Doblada de semana cedida y pagada en sábado ({fecha_pago}): '
                            f'30 min del emisor por la jornada que cedió'
                        ),
                    )
                    logger.info(
                        "Deuda corporativa (30 min) generada para el EMISOR %s en %s "
                        "(doblada de semana cedida, pagada en sábado %s).",
                        solicitante.nombre, fecha_cesion, fecha_pago,
                    )

        logger.info(
            "Deudas generadas: Solicitud %s - Deuda entre %s y %s, deudas corporativas para ambos",
            solicitud.id, solicitante.nombre, receptor.nombre,
        )
