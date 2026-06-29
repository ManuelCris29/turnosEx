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
    def _ocurrencias(fecha_inicio, fecha_fin, dias_set, solicitante=None, receptor=None, excluir_id=None):
        """
        Fechas del rango cuyo weekday está en dias_set y que son VÁLIDAS para doblada.
        EXCLUYE (misma política que CT Permanente — se OMITEN, no se rechaza todo):
        - fines de semana (sábado y domingo) y festivos,
        - mantenimiento y temporada,
        - días en que el solicitante o el receptor descansan o YA tienen un cambio
          (doblada / CT / D FDS) — solo si se pasan ambos exploradores.
        """
        from .ct_permanente_helper import (_es_festivo, _es_mantenimiento, _es_temporada,
                                            _es_dia_descanso, _tipo_cambio_previo, _dia_libre_por_solicitud)
        d = fecha_inicio
        while d <= fecha_fin:
            if (d.weekday() in dias_set and d.weekday() < 5
                    and not _es_festivo(d) and not _es_mantenimiento(d) and not _es_temporada(d)):
                # Excluye si el solicitante o el receptor ese día: descansan (rotación/temporada),
                # ya tienen un cambio (doblada/CT/D FDS) o están LIBRES por otra solicitud aprobada
                # (L2 — vía estado de Mis Turnos). `excluir_id` ignora ESTA solicitud al aplicarla
                # ya aprobada (si no, se auto-excluiría su propio efecto de descanso).
                _ok = True
                for emp in (solicitante, receptor):
                    if emp and (_es_dia_descanso(emp, d) or _tipo_cambio_previo(emp, d)
                                or _dia_libre_por_solicitud(emp, d, excluir_id)):
                        _ok = False
                        break
                if _ok:
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

        # Ocurrencias VÁLIDAS de cada lado (ya omiten festivo/temporada/mantenimiento/descanso/
        # día comprometido). BALANCE: solo se aplican PARES cubrir↔devolver, así que se recorta
        # cada lado al MÍNIMO común → nunca se paga un favor que no se recibió, ni al revés.
        _occ = DobladaPermanenteAplicacionService._ocurrencias
        _ex = solicitud.id  # excluir ESTA solicitud (ya aprobada) de la detección L2
        ocur_ces = list(_occ(detalle.fecha_inicio, detalle.fecha_fin, cesion, solicitante, receptor, _ex))
        ocur_dev = list(_occ(detalle.fecha_inicio, detalle.fecha_fin, devolucion, solicitante, receptor, _ex))
        n = min(len(ocur_ces), len(ocur_dev))
        ocur_ces, ocur_dev = ocur_ces[:n], ocur_dev[:n]

        # Snapshot de las fechas afectadas ANTES de mutar (para revertir en 30 min).
        fechas_afectadas = sorted(set(ocur_ces + ocur_dev))
        if not getattr(detalle, 'snapshot_turnos_previos', None):
            snapshot = DobladaPermanenteAplicacionService._capturar_snapshot(solicitante, receptor, fechas_afectadas)
            from solicitudes.models import DobladaPermanenteDetalle as _DPD
            _DPD.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snapshot)
            detalle.snapshot_turnos_previos = snapshot

        n_ces = n_dev = 0

        # Cesión: receptor dobla, solicitante descansa
        for fecha in ocur_ces:
            DFDSAplicacionService._crear_doblada_dia(receptor, fecha, tipo_cambio='DOBLADA PERM')
            Turno.objects.filter(explorador=solicitante, fecha=fecha).delete()
            DobladaPermanenteAplicacionService._deuda(receptor, fecha, solicitud, 'cesión')
            n_ces += 1

        # Devolución: solicitante dobla, receptor descansa
        for fecha in ocur_dev:
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
