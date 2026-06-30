from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import reverse_lazy
from django.db.models import Q
from core.mixins import AdminRequiredMixin
from core.services import get_turno_service
from empleados.models import Empleado
from ..models import TipoSolicitudCambio, Notificacion, SolicitudCambio, CambioPermanenteDetalle
from ..services.solicitud_service import SolicitudService
from ..services.solicitud_factory import SolicitudFactory
from ..services.permiso_service import PermisoService
from ..services.notificacion_service import NotificacionService
from django.utils import timezone
import hashlib
import hmac
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core
from core.utils.json_responses import json_ok, json_error

# Create your views here.

@method_decorator(csrf_exempt, name='dispatch')
class AprobarSolicitudView(LoginRequiredMixin, View):
    """
    Vista para aprobar una solicitud por parte del supervisor
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
        success, message = SolicitudAprobacionService.aprobar_solicitud_supervisor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return json_ok({'success': success, 'message': message})

@method_decorator(csrf_exempt, name='dispatch')
class AprobarSolicitudReceptorView(LoginRequiredMixin, View):
    """
    Vista para aprobar una solicitud por parte del compaÃ±ero receptor
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
        success, message = SolicitudAprobacionService.aprobar_solicitud_receptor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return json_ok({'success': success, 'message': message})

@method_decorator(csrf_exempt, name='dispatch')
class RechazarSolicitudView(LoginRequiredMixin, View):
    """
    Vista para rechazar una solicitud por parte del supervisor
    """
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        
        comentario_respuesta = request.POST.get('comentario_respuesta', '')
        
        from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
        success, message = SolicitudAprobacionService.rechazar_solicitud_supervisor(
            solicitud_id, 
            request.user.empleado, 
            comentario_respuesta
        )
        
        return json_ok({'success': success, 'message': message})

@method_decorator(csrf_exempt, name='dispatch')
class RechazarSolicitudReceptorView(LoginRequiredMixin, View):
    """
    Vista para rechazar una solicitud por parte del compaÃ±ero receptor
    """
    def post(self, request, solicitud_id):
        try:
            comentario_respuesta = request.POST.get('comentario_respuesta', '')
            from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
            success, message = SolicitudAprobacionService.rechazar_solicitud_receptor(
                solicitud_id, request.user.empleado, comentario_respuesta
            )
            return json_ok({'success': success, 'message': message})
        except Exception as e:
            logger.exception('Error en RechazarSolicitudReceptorView')
            return json_error('Error al rechazar la solicitud', status=500, code='internal_error')

@method_decorator(csrf_exempt, name='dispatch')
class CancelarSolicitudView(LoginRequiredMixin, View):
    VENTANA_CANCELACION_MINUTOS = 30

    @staticmethod
    def _pares_afectados(solicitud):
        """Conjunto de claves "empleado_id:YYYY-MM-DD" que tocó la solicitud, leídas de su
        snapshot (esté en la propia solicitud, en `doblada` o en `doblada_permanente`).
        Es la huella uniforme de (persona, día) afectados, para la guardia de orden (LIFO)."""
        snap = (getattr(solicitud, 'snapshot_turnos_previos', None)
                or getattr(getattr(solicitud, 'doblada', None), 'snapshot_turnos_previos', None)
                or getattr(getattr(solicitud, 'doblada_permanente', None), 'snapshot_turnos_previos', None)
                or {})
        return set(snap.keys())

    def post(self, request, solicitud_id):
        try:
            from django.db import transaction
            # Lock de fila + lógica de cancelación dentro de UNA transacción: serializa
            # cancelaciones concurrentes (doble clic / reintento). La segunda espera a la
            # primera y, al ver el estado ya cambiado, cae en el caso correspondiente sin
            # revertir dos veces.
            with transaction.atomic():
                # OPTIMIZACIÓN: Pre-cargar relaciones frecuentes
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

                # Solo el solicitante puede cancelar su propia solicitud
                if solicitud.explorador_solicitante != request.user.empleado:
                    return json_error('Solo puedes cancelar tus propias solicitudes', status=403, code='forbidden')

                if solicitud.estado == 'pendiente':
                    # Cancelación normal: sin restricción de tiempo
                    from solicitudes.domain.estado_machine import transicionar as _transicionar
                    _transicionar(solicitud, 'cancelada', save=False)
                    solicitud.fecha_resolucion = timezone.now()
                    solicitud.comentario = f"{solicitud.comentario or ''}\n\nCancelada por el solicitante"
                    solicitud.save()

                elif solicitud.estado == 'aprobada':
                    # Cancelación de solicitud aprobada: solo dentro de la ventana de 30 minutos
                    if not solicitud.fecha_resolucion:
                        return json_error(
                            'No se puede cancelar: la solicitud no tiene fecha de aprobación registrada.',
                            status=400, code='invalid_state'
                        )

                    tiempo_transcurrido = timezone.now() - solicitud.fecha_resolucion
                    minutos_transcurridos = tiempo_transcurrido.total_seconds() / 60

                    if minutos_transcurridos > self.VENTANA_CANCELACION_MINUTOS:
                        return json_error(
                            f'Ya no es posible cancelar esta solicitud. Solo se puede cancelar dentro de los '
                            f'{self.VENTANA_CANCELACION_MINUTOS} minutos posteriores a su aprobación '
                            f'(han pasado {int(minutos_transcurridos)} minutos).',
                            status=400, code='ventana_expirada'
                        )

                    # Guardia de orden (LIFO): no se puede cancelar este cambio si hay otro cambio
                    # APROBADO MÁS RECIENTE sobre los mismos (persona, día). Revertir el viejo
                    # restauraría su foto previa y PISARÍA el cambio nuevo. Hay que cancelar primero
                    # el más reciente. La huella de (persona, día) sale del snapshot de cada uno.
                    from django.db.models import Q as _Q
                    from datetime import date as _date
                    _mios = self._pares_afectados(solicitud)
                    if _mios:
                        _personas = [solicitud.explorador_solicitante_id, solicitud.explorador_receptor_id]
                        _posteriores = (SolicitudCambio.objects
                                        .filter(estado='aprobada', fecha_resolucion__gt=solicitud.fecha_resolucion)
                                        .filter(_Q(explorador_solicitante_id__in=_personas) |
                                                _Q(explorador_receptor_id__in=_personas))
                                        .exclude(id=solicitud.id)
                                        .select_related('doblada', 'doblada_permanente'))
                        for _otra in _posteriores:
                            _comunes = _mios & self._pares_afectados(_otra)
                            if _comunes:
                                _fechas = sorted({k.split(':', 1)[1] for k in _comunes})
                                _fmt = ', '.join(_date.fromisoformat(f).strftime('%d/%m') for f in _fechas)
                                return json_error(
                                    f'No puedes cancelar este cambio: hay otro más reciente sobre el mismo '
                                    f'día ({_fmt}). Cancela primero el cambio más reciente.',
                                    status=400, code='cambio_mas_reciente'
                                )

                    # Revertir cambios de la doblada si aplica
                    tipo_nombre = solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else ''
                    es_doblada = (
                        tipo_nombre == 'DOBLADA' and
                        hasattr(solicitud, 'doblada') and
                        solicitud.doblada is not None
                    )
                    if es_doblada:
                        from ..services.doblada_aplicacion_service import DobladaAplicacionService
                        DobladaAplicacionService.revertir_doblada_aplicada(solicitud)
                        # Limpiar caché de turnos
                        from core.services.cache_service import CacheService as CS
                        detalle = solicitud.doblada
                        for fecha in [solicitud.fecha_cambio_turno, detalle.fecha_pago]:
                            CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                            CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)

                    elif tipo_nombre == 'D FDS' and getattr(solicitud, 'doblada', None) is not None:
                        # Doblada de fin de semana: restaura turnos desde snapshot y cancela las
                        # deudas generadas (favor/pago). Sin esto, al cancelar quedaba aplicada.
                        from ..services.d_fds_aplicacion_service import DFDSAplicacionService
                        DFDSAplicacionService.revertir(solicitud)
                        from core.services.cache_service import CacheService as CS
                        detalle = solicitud.doblada
                        for fecha in [solicitud.fecha_cambio_turno, detalle.fecha_pago]:
                            if fecha:
                                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)

                    elif tipo_nombre == 'CAMBIO TURNO':
                        # CT sencillo: restaura los turnos previos (jornadas intercambiadas) desde
                        # el snapshot. No genera deudas.
                        from ..services.strategies.cambio_turno_strategy import CambioTurnoStrategy
                        CambioTurnoStrategy.revertir(solicitud)
                        from core.services.cache_service import CacheService as CS
                        f = solicitud.fecha_cambio_turno
                        if f:
                            CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, f.month, f.year)
                            CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, f.month, f.year)

                    elif tipo_nombre == 'CT PERMANENTE' and getattr(solicitud, 'cambio_permanente', None):
                        # CT permanente: borrado dirigido de los turnos CT PERMANENTE creados.
                        from ..services.strategies.ct_permanente_strategy import CTPermanenteStrategy
                        CTPermanenteStrategy.revertir(solicitud)
                        from core.services.cache_service import CacheService as CS
                        from datetime import timedelta as _td
                        det = solicitud.cambio_permanente
                        fin = det.fecha_fin or det.fecha_inicio
                        meses = set()
                        d = det.fecha_inicio
                        while d <= fin:
                            meses.add((d.month, d.year)); d += _td(days=28)
                        meses.add((fin.month, fin.year))
                        for (m, y) in meses:
                            CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, m, y)
                            CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, m, y)

                    elif tipo_nombre == 'CAMBIO DESCANSO' and getattr(solicitud, 'doblada', None) is not None:
                        # Cambio de día de descanso (finde o entre semana): restaura los turnos
                        # previos desde el snapshot (igual mecanismo que doblada). Sin esto, al
                        # cancelar quedaba el intercambio aplicado.
                        from ..services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService
                        CambioDescansoAplicacionService.revertir(solicitud)
                        from core.services.cache_service import CacheService as CS
                        detalle = solicitud.doblada
                        for fecha in [solicitud.fecha_cambio_turno, detalle.fecha_pago]:
                            if fecha:
                                CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, fecha.month, fecha.year)
                                CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, fecha.month, fecha.year)

                    elif tipo_nombre == 'DOBLADA PERMANENTE' and getattr(solicitud, 'doblada_permanente', None):
                        from ..services.doblada_permanente_aplicacion_service import DobladaPermanenteAplicacionService
                        DobladaPermanenteAplicacionService.revertir(solicitud)
                        # Limpiar caché de turnos en los meses del rango
                        from core.services.cache_service import CacheService as CS
                        from datetime import timedelta as _td
                        det = solicitud.doblada_permanente
                        meses = set()
                        d = det.fecha_inicio
                        while d <= det.fecha_fin:
                            meses.add((d.month, d.year)); d += _td(days=28)
                        meses.add((det.fecha_fin.month, det.fecha_fin.year))
                        for (m, y) in meses:
                            CS.invalidar_cache_turnos_empleado(solicitud.explorador_solicitante.id, m, y)
                            CS.invalidar_cache_turnos_empleado(solicitud.explorador_receptor.id, m, y)

                    from solicitudes.domain.estado_machine import transicionar as _transicionar
                    _transicionar(solicitud, 'cancelada', save=False)
                    solicitud.comentario = (
                        f"{solicitud.comentario or ''}\n\n"
                        f"Cancelada por el solicitante dentro de la ventana de "
                        f"{self.VENTANA_CANCELACION_MINUTOS} minutos."
                    )
                    solicitud.save()

                else:
                    return json_error(
                        f'No se puede cancelar una solicitud en estado "{solicitud.estado}".',
                        status=400, code='invalid_state'
                    )

            # Invalidar cache de contadores para todos los afectados
            from core.services.cache_service import CacheService
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_receptor.id}",
            ]
            if solicitud.explorador_solicitante.supervisor:
                cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_solicitante.supervisor.id}")
            CacheService.delete_many(cache_keys)

            # Crear notificación de cancelación
            from ..services.notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_cancelacion(solicitud)

            return json_ok({'message': 'Solicitud cancelada correctamente'})

        except SolicitudCambio.DoesNotExist:
            return json_error('Solicitud no encontrada', status=404, code='not_found')
        except Exception as e:
            logger.exception('Error en CancelarSolicitudView')
            return json_error('Error al cancelar la solicitud', status=500, code='internal_error')

@method_decorator(csrf_exempt, name='dispatch')
class AprobarSolicitudAmbosView(LoginRequiredMixin, View):
    """
    Aprueba como Receptor y como Supervisor en una sola acciÃ³n
    Solo disponible si el usuario es simultÃ¡neamente receptor y supervisor de la solicitud
    y la solicitud estÃ¡ en estado pendiente.
    """
    def post(self, request, solicitud_id):
        try:
            if not hasattr(request.user, 'empleado'):
                return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')

            # OPTIMIZACIÓN: Pre-cargar relaciones frecuentes
            solicitud = get_object_or_404(
                SolicitudCambio.objects.select_related(
                    'explorador_solicitante',
                    'explorador_receptor',
                    'explorador_solicitante__supervisor',
                    'tipo_cambio'
                ),
                id=solicitud_id
            )
            empleado = request.user.empleado

            # Validar roles simultÃ¡neos
            es_receptor = solicitud.explorador_receptor == empleado
            es_supervisor = (getattr(solicitud.explorador_solicitante, 'supervisor', None) == empleado)

            if not (es_receptor and es_supervisor):
                return json_error('No tienes permisos para aprobar en ambos roles', status=403, code='forbidden')

            if solicitud.estado != 'pendiente':
                return json_error('La solicitud no estÃ¡ pendiente', status=400, code='invalid_state')

            # Recargar la solicitud para obtener el estado actualizado
            solicitud.refresh_from_db()
            
            # Aprobar primero como receptor si falta
            if not solicitud.aprobado_receptor:
                from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
                success, message = SolicitudAprobacionService.aprobar_solicitud_receptor(solicitud_id, empleado, 'Aprobado como receptor (acciÃ³n combinada)')
                if not success:
                    return json_error(message, status=400, code='approval_error')
                # Recargar despuÃ©s de aprobar como receptor
                solicitud.refresh_from_db()

            # Aprobar como supervisor si falta
            if not solicitud.aprobado_supervisor:
                from ..services.solicitud_aprobacion_service import SolicitudAprobacionService
                success, message = SolicitudAprobacionService.aprobar_solicitud_supervisor(solicitud_id, empleado, 'Aprobado como supervisor (acciÃ³n combinada)')
                if not success:
                    return json_error(message, status=400, code='approval_error')
                # Recargar despuÃ©s de aprobar como supervisor
                solicitud.refresh_from_db()

            # NOTA: No necesitamos llamar a aplicar_cambios aquÃ­ porque
            # aprobar_solicitud_receptor y aprobar_solicitud_supervisor ya lo hacen
            # cuando detectan que ambos roles estÃ¡n aprobados

            return json_ok({'message': 'Solicitud aprobada en ambos roles correctamente'})
        except Exception:
            logger.exception('Error en AprobarSolicitudAmbosView')
            return json_error('Error al aprobar en ambos roles', status=500, code='internal_error')


# Vistas para aprobaciÃ³n por email (sin login requerido)
