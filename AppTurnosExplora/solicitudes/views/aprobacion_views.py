from django.shortcuts import render, get_object_or_404
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from core.mixins import AdminRequiredMixin
from ..repositories.solicitud_repository import SolicitudRepository
from ..use_cases.aprobar_solicitud import (
    AprobarComoReceptorUseCase,
    AprobarComoSupervisorUseCase,
    RechazarComoReceptorUseCase,
    RechazarComoSupervisorUseCase,
    AprobarAmbosRolesUseCase,
)
from ..use_cases.cancelar_solicitud import CancelarSolicitudUseCase
import logging

logger = logging.getLogger(__name__)

from core.utils.json_responses import json_ok, json_error

# Create your views here.

class AprobarSolicitudView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        comentario = request.POST.get('comentario_respuesta', '')
        success, message = AprobarComoSupervisorUseCase().execute(solicitud_id, request.user.empleado, comentario)
        return json_ok({'success': success, 'message': message})

class AprobarSolicitudReceptorView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        comentario = request.POST.get('comentario_respuesta', '')
        success, message = AprobarComoReceptorUseCase().execute(solicitud_id, request.user.empleado, comentario)
        return json_ok({'success': success, 'message': message})

class RechazarSolicitudView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        if not hasattr(request.user, 'empleado'):
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
        comentario = request.POST.get('comentario_respuesta', '')
        success, message = RechazarComoSupervisorUseCase().execute(solicitud_id, request.user.empleado, comentario)
        return json_ok({'success': success, 'message': message})

class RechazarSolicitudReceptorView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        try:
            comentario = request.POST.get('comentario_respuesta', '')
            success, message = RechazarComoReceptorUseCase().execute(solicitud_id, request.user.empleado, comentario)
            return json_ok({'success': success, 'message': message})
        except Exception:
            logger.exception('Error en RechazarSolicitudReceptorView')
            return json_error('Error al rechazar la solicitud', status=500, code='internal_error')

class CancelarSolicitudView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        try:
            if not hasattr(request.user, 'empleado'):
                return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
            ok, msg = CancelarSolicitudUseCase().execute(solicitud_id, request.user.empleado)
            if not ok:
                if 'propias' in msg:
                    return json_error(msg, status=403, code='forbidden')
                if 'más reciente' in msg:
                    return json_error(msg, status=400, code='cambio_mas_reciente')
                if 'conflicto de jornadas' in msg:
                    return json_error(msg, status=400, code='conflicto_integridad')
                if 'minutos' in msg and 'ventana' not in msg.lower():
                    return json_error(msg, status=400, code='ventana_expirada')
                return json_error(msg, status=400, code='invalid_state')
            # Notificación e invalidación de caché post-cancelación
            from core.services.cache_service import CacheService
            from ..services.notificacion_service import NotificacionService
            solicitud = SolicitudRepository.get_by_id_con_relaciones(solicitud_id)
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
            ]
            if solicitud.explorador_receptor_id:
                cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_receptor_id}")
            if solicitud.explorador_solicitante.supervisor:
                cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_solicitante.supervisor.id}")
            CacheService.delete_many(cache_keys)
            NotificacionService.crear_notificacion_cancelacion(solicitud)
            return json_ok({'message': msg})
        except Exception:
            logger.exception('Error en CancelarSolicitudView')
            return json_error('Error al cancelar la solicitud', status=500, code='internal_error')


class AprobarSolicitudAmbosView(LoginRequiredMixin, View):
    def post(self, request, solicitud_id):
        try:
            if not hasattr(request.user, 'empleado'):
                return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')
            ok, msg = AprobarAmbosRolesUseCase().execute(
                solicitud_id, request.user.empleado, request.POST.get('comentario_respuesta', '')
            )
            if not ok:
                status = 403 if 'permisos' in msg else 400
                return json_error(msg, status=status, code='approval_error')
            return json_ok({'message': msg})
        except Exception:
            logger.exception('Error en AprobarSolicitudAmbosView')
            return json_error('Error al aprobar en ambos roles', status=500, code='internal_error')


# Vistas para aprobaciÃ³n por email (sin login requerido)
