from django.shortcuts import render
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from empleados.views import AdminRequiredMixin
from .models import TipoSolicitudCambio, PermisoDetalle

# Create your views here.

class SolicitudesView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/list.html'

# CRUD de TipoSolicitudCambio
class TipoSolicitudCambioListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_list.html'
    context_object_name = 'tipos_solicitud'

class TipoSolicitudCambioCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_create.html'
    fields = ['nombre', 'activo']
    success_url = '/solicitudes/tipos-solicitud/'

class TipoSolicitudCambioUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_edit.html'
    fields = ['nombre', 'activo']
    success_url = '/solicitudes/tipos-solicitud/'

class TipoSolicitudCambioDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_confirm_delete.html'
    success_url = '/solicitudes/tipos-solicitud/'

# CRUD de PermisoDetalle
class PermisoDetalleListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = PermisoDetalle
    template_name = 'solicitudes/permisodetalle_list.html'
    context_object_name = 'permisos_detalle'

class PermisoDetalleCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = PermisoDetalle
    template_name = 'solicitudes/permisodetalle_create.html'
    fields = ['solicitud', 'horas_solicitadas']
    success_url = '/solicitudes/permisos-detalle/'

class PermisoDetalleUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = PermisoDetalle
    template_name = 'solicitudes/permisodetalle_edit.html'
    fields = ['solicitud', 'horas_solicitadas']
    success_url = '/solicitudes/permisos-detalle/'

class PermisoDetalleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = PermisoDetalle
    template_name = 'solicitudes/permisodetalle_confirm_delete.html'
    success_url = '/solicitudes/permisos-detalle/'
