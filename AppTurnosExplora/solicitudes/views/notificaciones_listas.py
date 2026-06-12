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

class NotificacionesListView(LoginRequiredMixin, ListView):
    model = Notificacion
    template_name = 'solicitudes/notificaciones_list.html'
    context_object_name = 'notificaciones'
    
    def get_queryset(self):
        if hasattr(self.request.user, 'empleado'):
            return NotificacionService.obtener_notificaciones(self.request.user.empleado)
        return Notificacion.objects.none()

class MarcarNotificacionLeidaView(LoginRequiredMixin, View):
    def post(self, request, notificacion_id):
        if hasattr(request.user, 'empleado'):
            success = NotificacionService.marcar_como_leida(notificacion_id, request.user.empleado)
            return json_ok({'success': success})
        return json_error('No autorizado', status=403, code='forbidden')

class MisSolicitudesListView(LoginRequiredMixin, ListView):
    """
    Vista para que los empleados vean sus propias solicitudes
    """
    model = SolicitudCambio
    template_name = 'solicitudes/mis_solicitudes_list.html'
    context_object_name = 'solicitudes'
    
    def get_queryset(self):
        if hasattr(self.request.user, 'empleado'):
            from ..services.solicitud_consulta_service import SolicitudConsultaService
            return SolicitudConsultaService.get_solicitudes_usuario(self.request.user)
        return SolicitudCambio.objects.none()

class SolicitudesPendientesListView(LoginRequiredMixin, ListView):
    """
    Vista para que los supervisores vean las solicitudes pendientes de sus empleados
    """
    model = SolicitudCambio
    template_name = 'solicitudes/solicitudes_pendientes_list.html'
    context_object_name = 'solicitudes'
    
    def get_queryset(self):
        if hasattr(self.request.user, 'empleado'):
            # OPTIMIZACIÓN: Una sola query combinada con select_related para evitar N+1
            from django.db.models import Q
            solicitudes_combined = (
                SolicitudCambio.objects
                .filter(
                    (
                        Q(estado='pendiente', explorador_receptor=self.request.user.empleado, aprobado_receptor=False)
                    ) |
                    (
                        Q(estado='pendiente', explorador_solicitante__supervisor=self.request.user.empleado, aprobado_supervisor=False)
                    )
                )
                .select_related(
                    'explorador_solicitante',
                    'explorador_receptor',
                    'tipo_cambio',
                    'explorador_solicitante__supervisor',
                    'turno_origen',
                    'turno_destino'
                )
                .distinct()
                .order_by('-fecha_solicitud')
            )
            
            # Agregar información del rol a cada solicitud (sin queries extra gracias a select_related)
            for solicitud in solicitudes_combined:
                es_receptor = solicitud.explorador_receptor == self.request.user.empleado and not solicitud.aprobado_receptor
                es_supervisor = solicitud.explorador_solicitante.supervisor == self.request.user.empleado and not solicitud.aprobado_supervisor
                
                if es_receptor and es_supervisor:
                    solicitud.mi_rol = 'ambos'
                elif es_receptor:
                    solicitud.mi_rol = 'receptor'
                elif es_supervisor:
                    solicitud.mi_rol = 'supervisor'
            
            return solicitudes_combined
        return SolicitudCambio.objects.none()
