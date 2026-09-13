"""
DobladaDeudaService

Responsabilidad: generar las deudas (entre exploradores y corporativas) cuando
una doblada es aprobada. No toca turnos.
"""
import logging
from datetime import date

from django.core.exceptions import ValidationError

from core.constants import JornadaDisplay
from empleados.models import Empleado
from solicitudes.models import DobladaDetalle, SolicitudCambio

from .deuda_corporativa_repository import DeudaCorporativaRepository
from .deuda_corporativa_service import DeudaCorporativaService
from .deuda_service import DeudaService

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
            # Sin jornada base no se puede etiquetar la deuda: fallar explícito (dentro de la
            # transacción de aprobación) en vez de reventar con AttributeError sobre None.
            if not jornada_solicitante:
                raise ValidationError(
                    f"{solicitante.nombre} no tiene jornada asignada el "
                    f"{fecha_cesion.strftime('%d/%m/%Y')}: no se puede registrar la deuda de la doblada."
                )
            jornada_cedida_nombre = jornada_solicitante.nombre.upper()

        # Deuda entre exploradores
        DeudaService.crear_deuda_idempotente(
            deudor=solicitante,
            acreedor=receptor,
            solicitud=solicitud,
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
            DeudaService.crear_deuda_idempotente(
                deudor=receptor,
                acreedor=solicitante,
                solicitud=solicitud,
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
            if jornada_display == JornadaDisplay.DOBLADA:
                creada = DeudaCorporativaRepository.crear_deuda_corporativa_idempotente(
                    explorador=explorador,
                    minutos=30,
                    fecha_doblada=fecha_doblada,
                    solicitud=solicitud,
                    comentario=comentario,
                )
                if creada:
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

        # Contrapartida del bloque anterior: quien DEJA de doblar por esta solicitud tampoco debe
        # seguir con sus 30 min. Pasa al ceder una mitad de una doblada (el emisor se queda con una
        # sola jornada en la cesión) y al recibir cobertura en la fecha de pago. Sin esto la deuda
        # vieja quedaba activa sumando en el Consolidado de Horas mientras el nuevo receptor —el
        # que realmente dobla— recibía la suya.
        DeudaCorporativaRepository.sincronizar_deuda_corporativa(
            solicitante, fecha_cesion, motivo=f'cedió una jornada en la solicitud {solicitud.id}',
        )
        DeudaCorporativaRepository.sincronizar_deuda_corporativa(
            receptor, fecha_pago, motivo=f'recibe cobertura en la solicitud {solicitud.id}',
        )

        # NOTA: CEDER una doblada NO genera 30 min al emisor. Los 30 min corporativos son solo
        # para quien REALMENTE se dobla en día hábil: el receptor en la cesión (arriba) y, si aplica,
        # el emisor cuando PAGA doblándose en día hábil. Pagar en sábado no genera nada (día completo
        # por alternancia). Los 30 min previos del emisor (p. ej. de una doblada permanente) quedan
        # intactos; ceder no le añade otros.

        logger.info(
            "Deudas generadas: Solicitud %s - Deuda entre %s y %s, deudas corporativas para ambos",
            solicitud.id, solicitante.nombre, receptor.nombre,
        )
