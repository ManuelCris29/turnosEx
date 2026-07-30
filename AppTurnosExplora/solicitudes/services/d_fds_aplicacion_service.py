"""
Servicio para aplicar cambios de Doblada de Fin de Semana (D FDS).

Responsabilidad única: aplicar los turnos y generar las deudas cuando una
solicitud D FDS es aprobada.

Modelo de negocio (acordado):
- En un fin de semana, según la alternancia, UN grupo trabaja un día completo
  (AM+PM) y el otro grupo trabaja el otro día. Cada explorador trabaja un solo
  día del finde.
- Favor (fecha de cesión): el solicitante NO puede asistir a SU día del finde y
  lo cede. El receptor (grupo contrario, trabaja el otro día) se dobla: trabaja
  su día propio + el día cedido. El solicitante descansa todo ese finde.
- Pago (fecha de pago, mismo mes): espejo del favor. El solicitante cubre el día
  del receptor en un finde futuro: trabaja su día propio + el día del receptor.
  El receptor descansa su día.

Unidad transferida = un día de finde completo (AM+PM), no medias jornadas.

Deudas:
- Corporativa (30 min): NO aplica para D FDS. Los 30 min solo se generan por
  dobladas de lunes a viernes, y las fechas de D FDS son siempre fin de semana
  (el guard de `aplica_deuda_doblada` lo garantiza de forma defensiva).
- Entre exploradores (DeudaExplorador): el solicitante (deudor) le debe el finde
  al receptor (acreedor); nace saldada porque la fecha de pago queda pactada en
  la misma solicitud.
"""
from datetime import date
import logging

from django.db import transaction

from solicitudes.models import SolicitudCambio, DobladaDetalle
from turnos.models import Turno
from turnos.services.jornada_service import JornadaService
from turnos.services.doblada_turno_service import DobladaTurnoService
from .deuda_service import DeudaService
from .deuda_corporativa_service import DeudaCorporativaService

logger = logging.getLogger(__name__)


class DFDSAplicacionService:
    """Aplica turnos y deudas de una Doblada de Fin de Semana aprobada."""

    @staticmethod
    def _jornadas_cache():
        from turnos.models import Jornada
        return {
            'AM': Jornada.objects.get(nombre='AM'),
            'PM': Jornada.objects.get(nombre='PM'),
        }

    @staticmethod
    def _crear_doblada_dia(explorador, fecha: date, tipo_cambio: str = 'D FDS') -> None:
        """
        Deja al explorador con doblada completa AM+PM en `fecha` (un día de finde).
        Borra cualquier turno previo de ese día y crea AM y PM.
        """
        jc = DFDSAplicacionService._jornadas_cache()
        Turno.objects.filter(explorador=explorador, fecha=fecha).delete()
        sala = DobladaTurnoService.obtener_sala_explorador_fecha(explorador, fecha)
        for nombre in ('AM', 'PM'):
            Turno.objects.create(
                explorador=explorador,
                fecha=fecha,
                jornada=jc[nombre],
                sala=sala,
                tipo_cambio=tipo_cambio,
            )
        logger.info("D FDS: %s dobla (AM+PM) en %s", explorador.nombre, fecha)

    @staticmethod
    @transaction.atomic
    def aplicar(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Aplica el favor (fecha de cesión) y el pago (fecha de pago) de la D FDS.

        - Cesión: receptor dobla su día cedido; solicitante descansa el finde.
        - Pago: solicitante dobla el día del receptor; receptor descansa su día.
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago

        # --- Favor (fecha de cesión) ---
        # El receptor cubre el día del solicitante (se dobla ese día).
        DFDSAplicacionService._crear_doblada_dia(receptor, fecha_cesion)
        # El solicitante descansa: sin turnos ese día (el mensaje de descanso lo
        # provee la vista de Mis Turnos al detectar la solicitud como solicitante).
        Turno.objects.filter(explorador=solicitante, fecha=fecha_cesion).delete()

        # --- Pago (fecha de pago) ---
        # El solicitante cubre el día del receptor (se dobla ese día).
        DFDSAplicacionService._crear_doblada_dia(solicitante, fecha_pago)
        # El receptor descansa su día.
        Turno.objects.filter(explorador=receptor, fecha=fecha_pago).delete()

        logger.info(
            "D FDS aplicada: Solicitud %s - %s cede %s, %s paga %s",
            solicitud.id, solicitante.nombre, fecha_cesion, solicitante.nombre, fecha_pago,
        )

    @staticmethod
    @transaction.atomic
    def revertir(solicitud: SolicitudCambio) -> None:
        """
        Revierte una D FDS aprobada (ventana de cancelación de 30 min):
        restaura los turnos previos desde el snapshot y cancela las deudas generadas.
        Sin esto, al cancelar quedaban las dobladas aplicadas y las deudas vigentes.
        """
        from solicitudes.models import DeudaExplorador
        from .doblada_aplicacion_service import DobladaAplicacionService

        detalle = solicitud.doblada
        snapshot = getattr(detalle, 'snapshot_turnos_previos', None)
        if snapshot:
            DobladaAplicacionService.restaurar_turnos_desde_snapshot(snapshot)
        else:
            # D FDS antiguas (sin snapshot): elimina los turnos D FDS de cesión y pago.
            Turno.objects.filter(
                explorador__in=[solicitud.explorador_solicitante, solicitud.explorador_receptor],
                fecha__in=[solicitud.fecha_cambio_turno, detalle.fecha_pago],
                tipo_cambio='D FDS',
            ).delete()
        DeudaExplorador.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')
        # Solo las ACTIVAS: una deuda corporativa ya pagada sigue pagada aunque se revierta.
        DeudaCorporativaService.cancelar_deudas_de_solicitud(solicitud, motivo='D FDS revertida')
        # Patrón #22: restaurar el snapshot arrasa el día entero. Hay que reconstruir lo que
        # SIGUE vigente en esas fechas (otra doblada, un CT, un CT permanente…), o se borra en
        # silencio. Se cancelan las deudas ANTES para que la reconciliación no cuente las propias.
        if snapshot:
            DobladaAplicacionService.reconciliar_dobladas_aprobadas(
                DobladaAplicacionService._fechas_explorador_afectados(snapshot), solicitud.id)
        logger.info("D FDS revertida: Solicitud %s", solicitud.id)

    @staticmethod
    @transaction.atomic
    def generar_deudas(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """
        Genera la deuda entre exploradores y las deudas corporativas (30 min por
        cada día con doblada efectiva AM+PM).
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago

        # Jornada base del solicitante (el día cedido era de su grupo)
        jornada_base = JornadaService.get_jornada_explorador_fecha(
            solicitante.id, fecha_cesion.strftime('%Y-%m-%d')
        )
        jornada_cedida_nombre = jornada_base.nombre.upper() if jornada_base else 'AM'

        # Deuda entre exploradores: el solicitante le debe el finde al receptor,
        # saldada con la fecha de pago (finde de devolución).
        DeudaService.crear_deuda_idempotente(
            deudor=solicitante,
            acreedor=receptor,
            solicitud=solicitud,
            fecha_pago_pactada=fecha_pago,
            fecha_pago_real=fecha_pago,
            jornada_cedida=jornada_cedida_nombre,
            media_jornada=False,  # se cede un día de finde completo
        )

        # Deudas corporativas: 30 min por cada doblada efectiva AM+PM.
        from turnos.services.turno_service import TurnoService

        def _deuda_corp_si_doblada(explorador, fecha_doblada, comentario):
            # Los 30 min solo aplican de lunes a viernes (no sábados, domingos ni festivos).
            if not DeudaCorporativaService.aplica_deuda_doblada(fecha_doblada):
                logger.info(
                    "D FDS: sin deuda corporativa para %s en %s (fin de semana o festivo)",
                    explorador.nombre, fecha_doblada
                )
                return
            display = TurnoService.obtener_jornada_display(explorador, fecha_doblada)
            if display == 'DOBLADA':
                creada = DeudaCorporativaService.crear_deuda_corporativa_idempotente(
                    explorador=explorador,
                    minutos=30,
                    fecha_doblada=fecha_doblada,
                    solicitud=solicitud,
                    comentario=comentario,
                )
                if creada:
                    logger.info(
                        "D FDS: deuda corporativa 30 min para %s en %s", explorador.nombre, fecha_doblada
                    )

        # Receptor dobla el día cedido; solicitante dobla el día de pago.
        _deuda_corp_si_doblada(
            receptor, fecha_cesion, f'D FDS: doblada en día cedido ({fecha_cesion})'
        )
        _deuda_corp_si_doblada(
            solicitante, fecha_pago, f'D FDS: doblada en día de pago ({fecha_pago})'
        )

        # Contrapartida: quien DEJA de doblar por esta solicitud tampoco sigue debiendo sus 30 min.
        # El solicitante cede su día y el receptor recibe cobertura en el pago; si alguno venía
        # doblando esa fecha, deja de hacerlo. Sin esto la deuda vieja quedaba activa sumando en el
        # Consolidado de Horas aunque el día ya no fuera doblada.
        DeudaCorporativaService.sincronizar_deuda_corporativa(
            solicitante, fecha_cesion, motivo=f'cede el día en la D FDS {solicitud.id}')
        DeudaCorporativaService.sincronizar_deuda_corporativa(
            receptor, fecha_pago, motivo=f'recibe cobertura en la D FDS {solicitud.id}')

        logger.info("D FDS deudas generadas: Solicitud %s", solicitud.id)
