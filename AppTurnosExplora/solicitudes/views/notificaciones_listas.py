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

PER_PAGE_OPCIONES = [10, 20, 50]
PER_PAGE_DEFAULT = 20


def _resolver_per_page(request):
    """Lee ?per_page y solo admite valores de la lista blanca (default 20)."""
    raw = request.GET.get('per_page')
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return PER_PAGE_DEFAULT
    return val if val in PER_PAGE_OPCIONES else PER_PAGE_DEFAULT


def _query_params_sin_page(request):
    """GET urlencoded sin 'page' (para conservar filtros en los enlaces de paginación)."""
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()


class NotificacionesListView(LoginRequiredMixin, ListView):
    model = Notificacion
    template_name = 'solicitudes/notificaciones_list.html'
    context_object_name = 'notificaciones'

    def get_paginate_by(self, queryset):
        return _resolver_per_page(self.request)

    def get_queryset(self):
        if not hasattr(self.request.user, 'empleado'):
            return Notificacion.objects.none()
        qs = NotificacionService.obtener_notificaciones(self.request.user.empleado)
        leidas = self.request.GET.get('leidas')
        if leidas == 'no':
            qs = qs.filter(leida=False)
        elif leidas == 'si':
            qs = qs.filter(leida=True)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        no_leidas = 0
        if hasattr(self.request.user, 'empleado'):
            no_leidas = Notificacion.objects.filter(
                destinatario=self.request.user.empleado, leida=False
            ).count()
        context.update({
            'filtro_leidas': self.request.GET.get('leidas', ''),
            'no_leidas_count': no_leidas,
            'per_page': _resolver_per_page(self.request),
            'per_page_opciones': PER_PAGE_OPCIONES,
            'query_params': _query_params_sin_page(self.request),
        })
        return context

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

    def get_paginate_by(self, queryset):
        return _resolver_per_page(self.request)

    def get_queryset(self):
        if not hasattr(self.request.user, 'empleado'):
            return SolicitudCambio.objects.none()
        from ..services.solicitud_consulta_service import SolicitudConsultaService
        qs = SolicitudConsultaService.get_solicitudes_usuario(self.request.user)
        tipo = self.request.GET.get('tipo')
        if tipo and str(tipo).isdigit():
            qs = qs.filter(tipo_cambio_id=int(tipo))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'tipos': TipoSolicitudCambio.objects.filter(activo=True).order_by('nombre'),
            'filtro_tipo': self.request.GET.get('tipo', ''),
            'per_page': _resolver_per_page(self.request),
            'per_page_opciones': PER_PAGE_OPCIONES,
            'query_params': _query_params_sin_page(self.request),
        })
        return context

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

    def get_context_data(self, **kwargs):
        """
        Añade las CANCELACIONES que esperan mi respuesta como receptor.

        No caben en el queryset principal: esas solicitudes están 'aprobada', no 'pendiente'
        —el cambio sigue vigente mientras decido—, así que se listan aparte. Sin esto la
        petición no tendría dónde verse y caducaría siempre por no haberla mostrado.
        """
        context = super().get_context_data(**kwargs)
        context['cancelaciones_pendientes'] = self._cancelaciones_pendientes()
        return context

    def _cancelaciones_pendientes(self):
        from datetime import timedelta

        from django.utils import timezone

        from core.constants import EstadoCancelacion, VENTANA_RESPONDER_CANCELACION_HORAS

        if not hasattr(self.request.user, 'empleado'):
            return SolicitudCambio.objects.none()

        # Las vencidas se excluyen aquí en vez de marcarlas: el estado CADUCADA lo escribe quien
        # intenta responder (`_caducar_si_vencida`). Listar una que ya no se puede responder solo
        # daría un botón que falla.
        limite = timezone.now() - timedelta(hours=VENTANA_RESPONDER_CANCELACION_HORAS)
        return (
            SolicitudCambio.objects
            .filter(
                estado='aprobada',
                cancelacion_estado=EstadoCancelacion.PENDIENTE,
                cancelacion_solicitada_en__gte=limite,
                explorador_receptor=self.request.user.empleado,
            )
            .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')
            .order_by('cancelacion_solicitada_en')
        )
