from django.shortcuts import render, get_object_or_404
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from empleados.views import AdminRequiredMixin
from empleados.models import Empleado
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
    fields = ['nombre', 'activo', 'genera_deuda']
    success_url = '/solicitudes/tipos-solicitud/'

class TipoSolicitudCambioUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = TipoSolicitudCambio
    template_name = 'solicitudes/tiposolicitudcambio_edit.html'
    fields = ['nombre', 'activo', 'genera_deuda']
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

class CambioTurnoInicioView(LoginRequiredMixin, TemplateView):
    template_name = 'solicitudes/cambio_turno_inicio.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tipos_solicitud'] = TipoSolicitudCambio.objects.filter(activo=True)
        return context
    
class SolicitarCambioTurnoView(LoginRequiredMixin, View):
    template_name = 'solicitudes/solicitar_cambio_turno.html'

    def get(self, request, tipo_id):
        tipo_solicitud = get_object_or_404(TipoSolicitudCambio, id=tipo_id)
        # ... lógica para armar el contexto ...
        context = {
            'tipo_solicitud': tipo_solicitud,
            # ... otros datos necesarios ...
        }
        return render(request, self.template_name, context)


class ObtenerEmpleadosDisponiblesView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        if not fecha:
            return JsonResponse({'empleados': []})
        
        # Obtener empleados disponibles para la fecha (excluyendo al usuario actual)
        empleados_disponibles = Empleado.objects.filter(
            activo=True
        ).exclude(
            id=request.user.empleado.id if hasattr(request.user, 'empleado') else None
        )
        
        # Convertir a formato JSON
        empleados_data = []
        for empleado in empleados_disponibles:
            empleados_data.append({
                'id': empleado.id,
                'nombre': empleado.nombre,
                'apellido': empleado.apellido,
                'jornada': empleado.get_jornada_display(),
            })
        
        return JsonResponse({'empleados': empleados_data})
