import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import CreateView, DeleteView, ListView, TemplateView, UpdateView

from core.mixins import AdminRequiredMixin
from core.services.cache_service import CACHE_TTL_LONG, CacheService

from ..models import TipoSolicitudCambio

logger = logging.getLogger(__name__)

# Importar helpers JSON comunes desde core

# Create your views here.


class SolicitudesView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/list.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.request.user.is_authenticated and hasattr(self.request.user, 'empleado'):
            from ..services.solicitud_context_service import SolicitudContextService
            context_data = SolicitudContextService.get_context_data_for_solicitudes_view(
                self.request.user.empleado
            )
            context.update(context_data)
        return context

# CRUD de TipoSolicitudCambio
class TipoSolicitudCambioListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_list.html'
    context_object_name = 'tipos_solicitud'

    def get_queryset(self):
        # Cambia algo más que Salas/Jornadas (activar/desactivar tipos): TTL de
        # 1h, no 24h. Invalida por señal (solicitudes/signals.py).
        qs = super().get_queryset()
        return CacheService.get_or_set('catalogo_tipos_solicitud_v1', lambda: list(qs), ttl=CACHE_TTL_LONG)

class TipoSolicitudCambioCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_create.html'
    fields = ['nombre', 'codigo_estrategia', 'activo', 'genera_deuda']
    success_url = '/solicitudes/tipos-solicitud/'

class TipoSolicitudCambioUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_edit.html'
    fields = ['nombre', 'codigo_estrategia', 'activo', 'genera_deuda']
    success_url = '/solicitudes/tipos-solicitud/'

class TipoSolicitudCambioDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_confirm_delete.html'
    success_url = '/solicitudes/tipos-solicitud/'
