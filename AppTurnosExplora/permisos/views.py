from django.shortcuts import render
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from .models import PDH, PermisoEspecial

# Importar mixin común desde core
from core.mixins import AdminRequiredMixin

# Create your views here.

class PermisosEspecialesView(LoginRequiredMixin, TemplateView):
    template_name = 'permisos/list.html'

class BeneficiosView(LoginRequiredMixin, TemplateView):
    template_name = 'permisos/beneficios.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Obtener información del empleado
        try:
            empleado = self.request.user.empleado
            context['empleado'] = empleado
            context['documento'] = empleado.cedula
            context['nombre_completo'] = f"{empleado.nombre} {empleado.apellido}"
            context['email'] = empleado.email or self.request.user.email
            context['tipo_usuario'] = 'Operativo'  # Puedes ajustar según tu lógica
            context['jefe_directo'] = f"{empleado.supervisor.nombre} {empleado.supervisor.apellido}" if empleado.supervisor else ""
        except Exception:
            # Si no hay empleado asociado, usar información básica del usuario
            context['empleado'] = None
            context['documento'] = ""
            context['nombre_completo'] = self.request.user.get_full_name() or self.request.user.username
            context['email'] = self.request.user.email
            context['tipo_usuario'] = 'Operativo'
            context['jefe_directo'] = ""
        
        # URL del Google Apps Script (sin parámetros, el script manejará la autenticación)
        context['google_script_url'] = 'https://script.google.com/a/macros/parqueexplora.org/s/AKfycbzEclLu4hB0BkDQ8d2wDgU3W4oFUFE_JbzTVl6k97o/exec'
        
        return context

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
