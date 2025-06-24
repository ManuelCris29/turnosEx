from django.shortcuts import render
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from .models import PDH, PermisoEspecial

# Mixin personalizado para verificar permisos de administrador
class AdminRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        # Verificar si el usuario es staff o tiene rol de Supervisor
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        # Si es staff, permitir acceso
        if request.user.is_staff:
            return super().dispatch(request, *args, **kwargs)
        
        # Verificar si tiene rol de Supervisor
        try:
            empleado = request.user.empleado
            tiene_rol_supervisor = empleado.empleadorole_set.filter(role__nombre__icontains='supervisor').exists()
            if tiene_rol_supervisor:
                return super().dispatch(request, *args, **kwargs)
        except:
            pass
        
        # Si no cumple ninguna condición, denegar acceso
        raise PermissionDenied("No tienes permisos de administrador.")

# Create your views here.

class PermisosEspecialesView(LoginRequiredMixin, TemplateView):
    template_name = 'permisos/list.html'

class BeneficiosView(LoginRequiredMixin, TemplateView):
    template_name = 'permisos/beneficios.html'

# CRUD de Permisos Especiales
class PermisoEspecialListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = PermisoEspecial
    template_name = 'permisos/permisos_especiales_list.html'
    context_object_name = 'permisos_especiales'

class PermisoEspecialCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = PermisoEspecial
    template_name = 'permisos/permisos_especiales_create.html'
    fields = ['empleado', 'tipo', 'fecha_inicio', 'fecha_fin', 'motivo', 'estado', 'supervisor', 'comentario_supervisor']
    success_url = '/permisos/permisos-especiales/'

class PermisoEspecialUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = PermisoEspecial
    template_name = 'permisos/permisos_especiales_edit.html'
    fields = ['empleado', 'tipo', 'fecha_inicio', 'fecha_fin', 'motivo', 'estado', 'supervisor', 'comentario_supervisor']
    success_url = '/permisos/permisos-especiales/'

class PermisoEspecialDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = PermisoEspecial
    template_name = 'permisos/permisos_especiales_confirm_delete.html'
    success_url = '/permisos/permisos-especiales/'
