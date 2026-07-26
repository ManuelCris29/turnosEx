"""
DobladaSnapshotService

Responsabilidad: capturar y restaurar el estado de turnos antes/después de aplicar
una doblada, y reconciliar las dobladas vigentes tras una cancelación.
"""
from datetime import date
import logging

from django.db import transaction

from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from turnos.models import Turno
from core.utils.jornada_utils import obtener_jornadas_am_pm as _obtener_jornadas_cache

logger = logging.getLogger(__name__)


class DobladaSnapshotService:

    @staticmethod
    def capturar_snapshot_turnos_previos(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> dict:
        """
        Copia el estado real de Turno en BD para solicitante y receptor en fecha de cesión y de pago,
        antes de aplicar la doblada. Así la cancelación en 30 min puede restaurar cambios de turno
        sencillos u otras asignaciones que no son solo jornada predeterminada.
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago
        pairs = [
            (solicitante.id, fecha_cesion),
            (receptor.id, fecha_cesion),
            (solicitante.id, fecha_pago),
            (receptor.id, fecha_pago),
        ]
        snapshot: dict = {}
        for emp_id, fecha in pairs:
            key = f"{emp_id}:{fecha.isoformat()}"
            turnos_qs = (
                Turno.objects.filter(explorador_id=emp_id, fecha=fecha)
                .select_related('jornada')
                .order_by('jornada_id')
            )
            snapshot[key] = [
                {
                    'jornada_nombre': t.jornada.nombre.upper(),
                    'sala_id': t.sala_id,
                    'tipo_cambio': t.tipo_cambio,
                }
                for t in turnos_qs
            ]
        return snapshot

    @staticmethod
    def restaurar_turnos_desde_snapshot(snapshot: dict) -> None:
        """Reemplaza turnos en las fechas del snapshot por el contenido guardado."""
        if not snapshot:
            return
        from turnos.models import Jornada as JornadaModel
        from turnos.services.doblada_turno_service import DobladaTurnoService
        jornadas_cache = _obtener_jornadas_cache()

        for key, rows in snapshot.items():
            try:
                emp_str, fecha_str = key.split(':', 1)
                emp_id = int(emp_str)
                fecha = date.fromisoformat(fecha_str)
            except (ValueError, TypeError):
                logger.warning('Snapshot doblada: clave inválida %r', key)
                continue

            Turno.objects.filter(explorador_id=emp_id, fecha=fecha).delete()

            for row in rows or []:
                jn = (row.get('jornada_nombre') or '').upper()
                jornada_obj = jornadas_cache.get(jn)
                if not jornada_obj:
                    jornada_obj = JornadaModel.objects.filter(nombre__iexact=jn).first()
                if not jornada_obj:
                    logger.warning(
                        'Snapshot doblada: jornada %r no encontrada para %s en %s',
                        jn, emp_id, fecha,
                    )
                    continue
                sala_id = row.get('sala_id')
                if not sala_id:
                    empleado = Empleado.objects.filter(pk=emp_id).first()
                    if not empleado:
                        continue
                    sala = DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha)
                    sala_id = sala.id if sala else None
                if not sala_id:
                    logger.warning('Snapshot doblada: sin sala para %s en %s', emp_id, fecha)
                    continue
                Turno.objects.create(
                    explorador_id=emp_id,
                    fecha=fecha,
                    jornada=jornada_obj,
                    sala_id=sala_id,
                    tipo_cambio=row.get('tipo_cambio'),
                )
                logger.info('Turno restaurado desde snapshot: explorador %s, %s, %s', emp_id, fecha, jn)

    @staticmethod
    def fechas_explorador_afectados(snapshot: dict) -> set:
        """Extrae el conjunto de (explorador_id, fecha) que cubre un snapshot."""
        afectados = set()
        for key in (snapshot or {}).keys():
            try:
                emp_str, fecha_str = key.split(':', 1)
                afectados.add((int(emp_str), date.fromisoformat(fecha_str)))
            except (ValueError, TypeError):
                continue
        return afectados

    @staticmethod
    def reconciliar_dobladas_aprobadas(afectados: set, excluir_solicitud_id: int) -> None:
        """
        Tras restaurar el snapshot de una doblada CANCELADA, re-aplica el efecto de las
        dobladas que SIGUEN APROBADAS cuyo cesión/pago cae en las fechas afectadas.

        Motivo: el snapshot de una cesión total (2 solicitudes enlazadas que comparten la
        fecha de cesión) refleja un estado INTERMEDIO. Restaurarlo tal cual deja el estado
        inconsistente según el orden de cancelación. Re-aplicar las dobladas vigentes en
        orden cronológico de aprobación reconstruye el estado correcto.

        Solo se re-aplica el lado (cesión o pago) que cae en una fecha afectada.
        No genera deudas (eso es responsabilidad de DobladaDeudaService).
        """
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio

        if not afectados:
            return

        fechas = {f for (_e, f) in afectados}
        exploradores = {e for (e, _f) in afectados}
        # IMPORTANTE: DOBLADA, D FDS y CAMBIO DESCANSO comparten el modelo DobladaDetalle
        # (`doblada`). Reconstruimos TODAS las solicitudes aprobadas que tocan las fechas afectadas,
        # pero cada una con la lógica de SU tipo. Antes se aplicaba lógica de DOBLADA a todas, lo que
        # CORROMPÍA los turnos de un cambio de descanso (y no re-materializaba su estado real).
        candidatas = (
            SolicitudCambio.objects
            .filter(estado='aprobada', doblada__isnull=False)
            .exclude(id=excluir_solicitud_id)
            .filter(Q(fecha_cambio_turno__in=fechas) | Q(doblada__fecha_pago__in=fechas))
            .select_related('doblada', 'tipo_cambio')
            .order_by('fecha_resolucion', 'id')
            .distinct()
        )
        for s in candidatas:
            if (s.explorador_solicitante_id not in exploradores
                    and s.explorador_receptor_id not in exploradores):
                continue
            det = s.doblada
            tipo = s.tipo_cambio.nombre if s.tipo_cambio else ''
            if tipo == 'CAMBIO DESCANSO':
                # Re-aplicar con la lógica de CAMBIO DESCANSO (no la de doblada).
                DobladaSnapshotService._reaplicar_cambio_descanso(s, det)
            elif tipo == 'D FDS':
                # D FDS también comparte DobladaDetalle: re-aplicar con SU lógica (finde), no la
                # de doblada entre semana.
                from solicitudes.services.d_fds_aplicacion_service import DFDSAplicacionService
                DFDSAplicacionService.aplicar(s, det)
            else:
                # DOBLADA: re-aplicar solo el lado (cesión/pago) que cae en fecha afectada.
                from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
                if s.fecha_cambio_turno in fechas:
                    DobladaAplicacionService.aplicar_doblada_cesion(s, det)
                if det.fecha_pago in fechas:
                    DobladaAplicacionService.aplicar_doblada_pago(s, det)
            logger.info(
                "Reconciliación post-revert: re-aplicada solicitud aprobada %s (%s) sobre fechas afectadas.",
                s.id, tipo,
            )

        # DOBLADA PERMANENTE: vive en otro modelo (`doblada_permanente`, no `doblada`), así que no
        # entra en la consulta de arriba. Sin esto, restaurar un snapshot que pisa un día
        # `DOBLADA PERM` borraba la doblada y dejaba viva su deuda de 30 min (y no la detecta
        # `cancelar_deudas_huerfanas`, porque sí tiene solicitud de origen).
        permanentes = (
            SolicitudCambio.objects
            .filter(estado='aprobada', doblada_permanente__isnull=False,
                    doblada_permanente__fecha_inicio__lte=max(fechas))
            .filter(Q(doblada_permanente__fecha_fin__gte=min(fechas))
                    | Q(doblada_permanente__fecha_fin__isnull=True))
            .exclude(id=excluir_solicitud_id)
            .select_related('doblada_permanente')
            .order_by('fecha_resolucion', 'id')
            .distinct()
        )
        for s in permanentes:
            if (s.explorador_solicitante_id not in exploradores
                    and s.explorador_receptor_id not in exploradores):
                continue
            from solicitudes.services.doblada_permanente_aplicacion_service import (
                DobladaPermanenteAplicacionService,
            )
            n = DobladaPermanenteAplicacionService.reaplicar_fechas(s, s.doblada_permanente, fechas)
            if n:
                logger.info(
                    "Reconciliación post-revert: re-materializada doblada permanente %s en %d día(s).",
                    s.id, n,
                )

        # CAMBIO TURNO y CT PERMANENTE: no tienen `doblada` ni `doblada_permanente`, así que
        # tampoco entran en las dos consultas anteriores. Su snapshot vive en la propia
        # solicitud. Sin este bloque, restaurar cualquier snapshot que pisara su día los
        # borraba en silencio y la persona volvía a su jornada base sin que nada avisara.
        DobladaSnapshotService._reconciliar_cambios_de_turno(
            fechas, exploradores, excluir_solicitud_id)

    @staticmethod
    def _reconciliar_cambios_de_turno(fechas: set, exploradores: set, excluir_solicitud_id: int) -> None:
        """Re-materializa los CT sencillos y CT permanentes aprobados que tocan `fechas`."""
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio
        from solicitudes.services.strategies.cambio_turno_strategy import CambioTurnoStrategy
        from solicitudes.services.strategies.ct_permanente_strategy import CTPermanenteStrategy

        candidatas = (
            SolicitudCambio.objects
            .filter(estado='aprobada', tipo_cambio__nombre__in=['CAMBIO TURNO', 'CT PERMANENTE'])
            .filter(Q(explorador_solicitante_id__in=exploradores)
                    | Q(explorador_receptor_id__in=exploradores))
            .exclude(id=excluir_solicitud_id)
            .select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor')
            .order_by('fecha_resolucion', 'id')
            .distinct()
        )
        for s in candidatas:
            tipo = s.tipo_cambio.nombre if s.tipo_cambio else ''
            if tipo == 'CAMBIO TURNO':
                n = CambioTurnoStrategy.reaplicar_fechas(s, fechas)
            else:
                n = CTPermanenteStrategy.reaplicar_fechas(s, fechas)
            if n:
                logger.info(
                    "Reconciliación post-revert: re-materializado %s %s en %d día(s).",
                    tipo, s.id, n,
                )

    @staticmethod
    def _reaplicar_cambio_descanso(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> None:
        """Re-materializa los turnos de un CAMBIO DESCANSO aprobado (mismo dispatch que su
        estrategia). Solo turnos, sin deudas: el cambio de descanso no genera deudas."""
        from solicitudes.services.cambio_descanso_aplicacion_service import (
            CambioDescansoAplicacionService as _CDS,
        )
        fc = solicitud.fecha_cambio_turno
        if fc and fc.weekday() in (5, 6):
            _CDS.aplicar(solicitud, detalle)
            return
        sub = getattr(detalle, 'submodalidad_semana', None) or 'intercambio_dia'
        if sub == 'jornadas_partidas':
            _CDS.aplicar_semana_jornadas_partidas(solicitud, detalle)
        elif sub == 'cobertura_misma_semana':
            _CDS.aplicar_semana_cobertura(solicitud, detalle)
        elif sub == 'cambio_doblada':
            _CDS.aplicar_semana_cambio_doblada(solicitud, detalle)
        else:
            _CDS.aplicar_entre_semana(solicitud, detalle)
