"""
Aplicación de Doblada Permanente.

Recorre el rango y, por cada ocurrencia válida (día de semana seleccionado, NO
domingo ni festivo):
- Días de cesión: el receptor se dobla (AM+PM) y el solicitante descansa.
- Días de devolución: el solicitante se dobla (AM+PM) y el receptor descansa.

Cada doblada efectiva acumula 30 min de deuda corporativa para quien se dobla
(se ve en el Consolidado de Horas y se paga vía PDH).
"""
from datetime import date, timedelta
import logging

from django.db import transaction

from turnos.models import Turno
from .deuda_corporativa_service import DeudaCorporativaService
from .d_fds_aplicacion_service import DFDSAplicacionService

logger = logging.getLogger(__name__)


class DobladaPermanenteAplicacionService:

    @staticmethod
    def _parse_dias(dias_str):
        return {int(x) for x in (dias_str or '').split(',') if x.strip().isdigit()}

    @staticmethod
    def _ocurrencias(fecha_inicio, fecha_fin, dias_set):
        """
        Fechas del rango cuyo weekday está en dias_set, excluyendo domingos, festivos
        y días de mantenimiento (la temporada manda sobre el mantenimiento).
        """
        from .ct_permanente_helper import _es_festivo
        from turnos.models import DiaEspecial
        d = fecha_inicio
        while d <= fecha_fin:
            if (d.weekday() in dias_set and d.weekday() != 6
                    and not _es_festivo(d)
                    and not DiaEspecial.es_mantenimiento_efectivo(d)):
                yield d
            d += timedelta(days=1)

    @staticmethod
    def _deuda(explorador, fecha, solicitud, etiqueta):
        # Los 30 min solo aplican de lunes a viernes (no sábados ni festivos:
        # esos días se trabaja jornada completa). Los festivos/domingos ya se
        # excluyen de las ocurrencias; aquí cubrimos también el sábado.
        if not DeudaCorporativaService.aplica_deuda_doblada(fecha):
            return
        DeudaCorporativaService.crear_deuda_corporativa(
            explorador=explorador,
            minutos=30,
            fecha_generacion=date.today(),
            fecha_doblada=fecha,
            solicitud=solicitud,
            comentario=f'Doblada permanente ({etiqueta}) — {fecha}',
        )

    @staticmethod
    def _capturar_snapshot(solicitante, receptor, fechas):
        """Estado de Turno (solicitante y receptor) en las fechas afectadas, antes de aplicar."""
        snapshot = {}
        for emp in (solicitante, receptor):
            for fecha in fechas:
                key = f"{emp.id}:{fecha.isoformat()}"
                turnos = Turno.objects.filter(explorador=emp, fecha=fecha).select_related('jornada').order_by('jornada_id')
                snapshot[key] = [
                    {'jornada_nombre': t.jornada.nombre.upper(), 'sala_id': t.sala_id, 'tipo_cambio': t.tipo_cambio}
                    for t in turnos
                ]
        return snapshot

    @staticmethod
    @transaction.atomic
    def aplicar(solicitud, detalle):
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        cesion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_cesion)
        devolucion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_devolucion)

        # Snapshot de todas las fechas afectadas (cesión + devolución) ANTES de mutar,
        # para poder revertir si se cancela dentro de los 30 min.
        fechas_afectadas = sorted(set(
            list(DobladaPermanenteAplicacionService._ocurrencias(detalle.fecha_inicio, detalle.fecha_fin, cesion))
            + list(DobladaPermanenteAplicacionService._ocurrencias(detalle.fecha_inicio, detalle.fecha_fin, devolucion))
        ))
        snapshot = DobladaPermanenteAplicacionService._capturar_snapshot(solicitante, receptor, fechas_afectadas)
        from solicitudes.models import DobladaPermanenteDetalle as _DPD
        _DPD.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snapshot)
        detalle.snapshot_turnos_previos = snapshot

        n_ces = n_dev = 0

        # Cesión: receptor dobla, solicitante descansa
        for fecha in DobladaPermanenteAplicacionService._ocurrencias(detalle.fecha_inicio, detalle.fecha_fin, cesion):
            DFDSAplicacionService._crear_doblada_dia(receptor, fecha, tipo_cambio='DOBLADA PERM')
            Turno.objects.filter(explorador=solicitante, fecha=fecha).delete()
            DobladaPermanenteAplicacionService._deuda(receptor, fecha, solicitud, 'cesión')
            n_ces += 1

        # Devolución: solicitante dobla, receptor descansa
        for fecha in DobladaPermanenteAplicacionService._ocurrencias(detalle.fecha_inicio, detalle.fecha_fin, devolucion):
            DFDSAplicacionService._crear_doblada_dia(solicitante, fecha, tipo_cambio='DOBLADA PERM')
            Turno.objects.filter(explorador=receptor, fecha=fecha).delete()
            DobladaPermanenteAplicacionService._deuda(solicitante, fecha, solicitud, 'devolución')
            n_dev += 1

        logger.info(
            "Doblada permanente aplicada: solicitud %s — %s ocurrencias cesión (receptor dobla), "
            "%s ocurrencias devolución (solicitante dobla)",
            solicitud.id, n_ces, n_dev,
        )
        return n_ces, n_dev

    @staticmethod
    @transaction.atomic
    def revertir(solicitud):
        """
        Revierte una doblada permanente aplicada (cancelación dentro de los 30 min):
        - Restaura los turnos previos desde el snapshot (borra las dobladas creadas
          y recrea lo que había antes).
        - Cancela las deudas corporativas generadas por la solicitud.
        """
        from solicitudes.models import DeudaCorporativa
        from .doblada_aplicacion_service import DobladaAplicacionService

        detalle = solicitud.doblada_permanente
        snapshot = getattr(detalle, 'snapshot_turnos_previos', None)
        if snapshot:
            DobladaAplicacionService.restaurar_turnos_desde_snapshot(snapshot)
        else:
            # Sin snapshot: al menos eliminar las dobladas creadas en el rango
            cesion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_cesion)
            devolucion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_devolucion)
            for dias_set, quien in ((cesion, solicitud.explorador_receptor),
                                    (devolucion, solicitud.explorador_solicitante)):
                for fecha in DobladaPermanenteAplicacionService._ocurrencias(detalle.fecha_inicio, detalle.fecha_fin, dias_set):
                    Turno.objects.filter(explorador=quien, fecha=fecha, tipo_cambio='DOBLADA PERM').delete()

        DeudaCorporativa.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')
        logger.info("Doblada permanente revertida: solicitud %s", solicitud.id)
