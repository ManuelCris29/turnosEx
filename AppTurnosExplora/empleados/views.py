from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, TemplateView
from .services.empleado_service import EmpleadoService
from .models import Empleado

# Create your views here.

class EmpleadoListView(LoginRequiredMixin, ListView):
    template_name = 'empleados/lista.html'
    context_object_name = 'empleados'
    
    def get_queryset(self):
        query = self.request.GET.get('q', '')
        if query:
            return EmpleadoService.buscar_empleados(query)
        
        sala_id = self.request.GET.get('sala')
        if sala_id:
            return EmpleadoService.get_empleados_by_sala(sala_id)
            
        # Si el usuario tiene una CompetenciaEmpleado, mostrar empleados de su sala
        competencia = self.request.user.empleado.competenciaempleado_set.first()
        if competencia:
            return EmpleadoService.get_empleados_by_sala(competencia.sala_id)
        return Empleado.objects.none()  # Si no tiene sala asignada, retornar lista vacía

class EmpleadoDetailView(LoginRequiredMixin, DetailView):
    model = Empleado
    template_name = 'empleados/detail.html'

class EmpleadoEditView(LoginRequiredMixin, UpdateView):
    model = Empleado
    template_name = 'empleados/edit.html'
    fields = ['nombre', 'apellido', 'cedula', 'email', 'activo'] # Campos de ejemplo
    success_url = '/empleados/' # Redirigir a la lista después de editar

class RestriccionesView(LoginRequiredMixin, TemplateView):
    template_name = 'empleados/placeholder.html'

class SeccionesView(LoginRequiredMixin, TemplateView):
    template_name = 'empleados/placeholder.html'

class JornadasView(LoginRequiredMixin, TemplateView):
    template_name = 'empleados/placeholder.html'

class RolesView(LoginRequiredMixin, TemplateView):
    template_name = 'empleados/placeholder.html'
