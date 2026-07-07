"""
Use Case: CancelarSolicitud

Encapsula la regla de negocio de cancelación:
- Pendiente: puede cancelar sin restricción de tiempo.
- Aprobada: solo dentro de la ventana de 30 minutos (guardia LIFO).
- Cualquier otro estado: no se puede cancelar.

Extrae toda la lógica de negocio que estaba en CancelarSolicitudView
y la coloca en la capa de aplicación correcta.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from empleados.models import Empleado


VENTANA_CANCELACION_MINUTOS = 30


class CancelarSolicitudUseCase:

    def execute(self, solicitud_id: int, solicitante: "Empleado") -> Tuple[bool, str]:
        from django.db import transaction
        from django.utils import timezone
        from datetime import date as _date

        from solicitudes.models import SolicitudCambio
        from solicitudes.domain.estado_machine import transicionar
        from solicitudes.repositories.solicitud_repository import SolicitudRepository

        try:
            with transaction.atomic():
                solicitud = (
                    SolicitudCambio.objects
                    .select_for_update()
                    .select_related(
                        'explorador_solicitante',
                        'explorador_receptor',
                        'explorador_solicitante__supervisor',
                        'tipo_cambio',
                        'doblada',
                    )
                    .get(id=solicitud_id)
                )

                if solicitud.explorador_solicitante != solicitante:
                    return False, 'Solo puedes cancelar tus propias solicitudes'

                if solicitud.estado == 'pendiente':
                    transicionar(solicitud, 'cancelada', save=False)
                    solicitud.fecha_resolucion = timezone.now()
                    solicitud.comentario = f"{solicitud.comentario or ''}\n\nCancelada por el solicitante"
                    solicitud.save()
                    return True, 'Solicitud cancelada correctamente'

                if solicitud.estado == 'aprobada':
                    ok, msg = self._cancelar_aprobada(solicitud, solicitante, timezone)
                    if not ok:
                        return False, msg
                    return True, 'Solicitud cancelada correctamente'

                return False, f'No se puede cancelar una solicitud en estado "{solicitud.estado}".'

        except SolicitudCambio.DoesNotExist:
            return False, 'Solicitud no encontrada'

    def _cancelar_aprobada(self, solicitud, solicitante, timezone) -> Tuple[bool, str]:
        from django.db.models import Q
        from datetime import date as _date
        from solicitudes.models import SolicitudCambio
        from solicitudes.domain.estado_machine import transicionar

        if not solicitud.fecha_resolucion:
            return False, 'No se puede cancelar: la solicitud no tiene fecha de aprobación registrada.'

        minutos = (timezone.now() - solicitud.fecha_resolucion).total_seconds() / 60
        if minutos > VENTANA_CANCELACION_MINUTOS:
            return False, (
                f'Ya no es posible cancelar esta solicitud. Solo se puede cancelar dentro de los '
                f'{VENTANA_CANCELACION_MINUTOS} minutos posteriores a su aprobación '
                f'(han pasado {int(minutos)} minutos).'
            )

        # Guardia LIFO
        mios = self._pares_afectados(solicitud)
        if mios:
            personas = [solicitud.explorador_solicitante_id, solicitud.explorador_receptor_id]
            posteriores = (
                SolicitudCambio.objects
                .filter(estado='aprobada', fecha_resolucion__gt=solicitud.fecha_resolucion)
                .filter(Q(explorador_solicitante_id__in=personas) | Q(explorador_receptor_id__in=personas))
                .exclude(id=solicitud.id)
                .select_related('doblada', 'doblada_permanente')
            )
            for otra in posteriores:
                comunes = mios & self._pares_afectados(otra)
                if comunes:
                    fechas = sorted({k.split(':', 1)[1] for k in comunes})
                    fmt = ', '.join(_date.fromisoformat(f).strftime('%d/%m') for f in fechas)
                    return False, (
                        f'No puedes cancelar este cambio: hay otro más reciente sobre el mismo '
                        f'día ({fmt}). Cancela primero el cambio más reciente.'
                    )

        self._revertir_por_tipo(solicitud)

        # La reversión BORRA los turnos materializados (y los recrea con ids nuevos). Los FK
        # turno_origen/turno_destino apuntaban a esos turnos borrados; en BD ya quedaron NULL
        # (on_delete=SET_NULL), pero este objeto en memoria conserva el id viejo. Sincronizamos
        # para no reescribir un id inexistente al guardar (evita IntegrityError al cancelar CT).
        try:
            solicitud.refresh_from_db(fields=['turno_origen', 'turno_destino'])
        except Exception:
            solicitud.turno_origen = None
            solicitud.turno_destino = None

        transicionar(solicitud, 'cancelada', save=False)
        solicitud.comentario = (
            f"{solicitud.comentario or ''}\n\n"
            f"Cancelada por el solicitante dentro de la ventana de {VENTANA_CANCELACION_MINUTOS} minutos."
        )
        solicitud.save()
        return True, 'ok'

    @staticmethod
    def _pares_afectados(solicitud) -> set:
        snap = (
            getattr(solicitud, 'snapshot_turnos_previos', None)
            or getattr(getattr(solicitud, 'doblada', None), 'snapshot_turnos_previos', None)
            or getattr(getattr(solicitud, 'doblada_permanente', None), 'snapshot_turnos_previos', None)
            or {}
        )
        return set(snap.keys())

    @staticmethod
    def _revertir_por_tipo(solicitud) -> None:
        from core.services.cache_service import CacheService as CS
        from datetime import timedelta

        tipo = solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else ''

        if tipo == 'DOBLADA' and getattr(solicitud, 'doblada', None):
            from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
            DobladaAplicacionService.revertir_doblada_aplicada(solicitud)
            detalle = solicitud.doblada
            for fecha in [solicitud.fecha_cambio_turno, detalle.fecha_pago]:
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)

        elif tipo == 'D FDS' and getattr(solicitud, 'doblada', None):
            from solicitudes.services.d_fds_aplicacion_service import DFDSAplicacionService
            DFDSAplicacionService.revertir(solicitud)
            detalle = solicitud.doblada
            for fecha in [solicitud.fecha_cambio_turno, detalle.fecha_pago]:
                if fecha:
                    CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                    CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)

        elif tipo == 'CAMBIO TURNO':
            from solicitudes.services.strategies.cambio_turno_strategy import CambioTurnoStrategy
            CambioTurnoStrategy.revertir(solicitud)
            f = solicitud.fecha_cambio_turno
            if f:
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, f.month, f.year)
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, f.month, f.year)

        elif tipo == 'CT PERMANENTE' and getattr(solicitud, 'cambio_permanente', None):
            from solicitudes.services.strategies.ct_permanente_strategy import CTPermanenteStrategy
            CTPermanenteStrategy.revertir(solicitud)
            det = solicitud.cambio_permanente
            fin = det.fecha_fin or det.fecha_inicio
            meses = set()
            d = det.fecha_inicio
            while d <= fin:
                meses.add((d.month, d.year))
                d += timedelta(days=28)
            meses.add((fin.month, fin.year))
            for (m, y) in meses:
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, m, y)
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, m, y)

        elif tipo == 'CAMBIO DESCANSO' and getattr(solicitud, 'doblada', None):
            from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService
            CambioDescansoAplicacionService.revertir(solicitud)
            detalle = solicitud.doblada
            for fecha in [solicitud.fecha_cambio_turno, detalle.fecha_pago]:
                if fecha:
                    CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                    CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)

        elif tipo == 'DOBLADA PERMANENTE' and getattr(solicitud, 'doblada_permanente', None):
            from solicitudes.services.doblada_permanente_aplicacion_service import DobladaPermanenteAplicacionService
            DobladaPermanenteAplicacionService.revertir(solicitud)
            det = solicitud.doblada_permanente
            meses = set()
            d = det.fecha_inicio
            while d <= det.fecha_fin:
                meses.add((d.month, d.year))
                d += timedelta(days=28)
            meses.add((det.fecha_fin.month, det.fecha_fin.year))
            for (m, y) in meses:
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, m, y)
                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, m, y)
