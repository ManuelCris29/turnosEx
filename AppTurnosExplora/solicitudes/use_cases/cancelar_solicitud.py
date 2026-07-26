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
        personas = [solicitud.explorador_solicitante_id, solicitud.explorador_receptor_id]
        posteriores = (
            SolicitudCambio.objects
            .filter(estado='aprobada', fecha_resolucion__gt=solicitud.fecha_resolucion)
            .filter(Q(explorador_solicitante_id__in=personas) | Q(explorador_receptor_id__in=personas))
            .exclude(id=solicitud.id)
            .select_related('doblada', 'doblada_permanente', 'cambio_permanente')
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
        """
        Claves 'empleado_id:YYYY-MM-DD' que esta solicitud toca. Es la base de la guardia LIFO.

        La fuente preferida es el snapshot (dice exactamente qué se pisó). Pero NO puede ser la
        única: una solicitud sin snapshot —las anteriores al patrón #13, o cualquiera cuyo detalle
        quedara sin capturar— devolvía conjunto vacío, la guardia se saltaba entera y se podía
        cancelar por debajo de un cambio más reciente, pisándolo.

        Por eso, sin snapshot se DERIVAN los pares de las fechas propias de la solicitud. La
        guardia falla cerrado: puede sobre-estimar el solape (bloquea de más, el usuario cancela
        primero el reciente), nunca sub-estimarlo.
        """
        snap = (
            getattr(solicitud, 'snapshot_turnos_previos', None)
            or getattr(getattr(solicitud, 'doblada', None), 'snapshot_turnos_previos', None)
            or getattr(getattr(solicitud, 'doblada_permanente', None), 'snapshot_turnos_previos', None)
            or {}
        )
        if snap:
            return set(snap.keys())
        return CancelarSolicitudUseCase._pares_derivados_de_fechas(solicitud)

    @staticmethod
    def _pares_derivados_de_fechas(solicitud) -> set:
        """Fallback sin snapshot: pares (persona, fecha) a partir de los campos de la solicitud."""
        from datetime import timedelta

        personas = [pid for pid in (solicitud.explorador_solicitante_id,
                                    solicitud.explorador_receptor_id) if pid]
        fechas = set()
        if solicitud.fecha_cambio_turno:
            fechas.add(solicitud.fecha_cambio_turno)

        detalle = (getattr(solicitud, 'doblada', None)
                   or getattr(solicitud, 'doblada_permanente', None)
                   or getattr(solicitud, 'cambio_permanente', None))
        if detalle is not None:
            if getattr(detalle, 'fecha_pago', None):
                fechas.add(detalle.fecha_pago)
            if getattr(detalle, 'fecha_pago_semana', None):
                fechas.add(detalle.fecha_pago_semana)
            # Rangos (CT permanente, doblada permanente): todo el intervalo cuenta como tocado.
            inicio = getattr(detalle, 'fecha_inicio', None)
            fin = getattr(detalle, 'fecha_fin', None) or inicio
            if inicio and fin:
                d = inicio
                while d <= fin:
                    fechas.add(d)
                    d += timedelta(days=1)

        return {f"{pid}:{f.isoformat()}" for pid in personas for f in fechas}

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
