from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from django.contrib import messages
from django.urls import reverse
from core.mixins import AdminRequiredMixin
from ..models import Turno, DiaEspecial, AsignarJornadaExplorador, DescansoSemanaManual
from ..forms import TemporadasAnualForm, DiasEspecialesAnualForm
from ..services.temporada_service import TemporadaService
from ..services.dia_especial_service import DiaEspecialService
from datetime import timedelta, date
from django.utils import timezone
import json

# Create your views here.

class TurnoListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Turno
    template_name = 'turnos/turnos_list.html'
    context_object_name = 'turnos'
    
    def get_queryset(self):
        # OPTIMIZACIÓN: Pre-cargar relaciones frecuentes
        return (
            Turno.objects
            .select_related('explorador', 'jornada', 'sala', 'explorador__user')
            .order_by('-fecha', 'explorador')
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        turnos = context['turnos']
        
        # OPTIMIZACIÓN: Pre-cargar todas las jornadas display en consultas batch
        from turnos.services.turno_service import TurnoService
        from collections import defaultdict
        
        if not turnos:
            context['turnos'] = turnos
            return context
        
        # Obtener todas las fechas y exploradores únicos
        fechas_unicas = set(t.fecha for t in turnos)
        explorador_ids = set(t.explorador_id for t in turnos)
        
        # OPTIMIZACIÓN: Pre-cargar todos los turnos de todas las fechas relevantes
        # Esto evita consultas individuales en obtener_jornada_display
        from turnos.models import Turno
        from empleados.models import Empleado
        
        # Pre-cargar turnos para todas las fechas y exploradores
        turnos_precargados = (
            Turno.objects
            .filter(
                explorador_id__in=explorador_ids,
                fecha__in=fechas_unicas
            )
            .select_related('jornada', 'explorador')
            .order_by('fecha', 'explorador', 'jornada__nombre')
        )
        
        # Agrupar turnos por (explorador_id, fecha)
        turnos_por_explorador_fecha = defaultdict(list)
        for t in turnos_precargados:
            key = (t.explorador_id, t.fecha)
            turnos_por_explorador_fecha[key].append(t)
        
        # Pre-cargar exploradores
        exploradores = {
            e.id: e
            for e in Empleado.objects.filter(id__in=explorador_ids).select_related('supervisor')
        }
        
        # Cache de jornada_display por (explorador_id, fecha)
        display_cache = {}
        
        # Calcular jornada_display usando datos pre-cargados
        for turno in turnos:
            key = (turno.explorador_id, turno.fecha)
            if key not in display_cache:
                explorador = exploradores.get(turno.explorador_id)
                if explorador:
                    # Usar método optimizado que puede usar datos pre-cargados
                    jornada_display = TurnoService.obtener_jornada_display(explorador, turno.fecha)
                    display_cache[key] = jornada_display
                else:
                    display_cache[key] = turno.jornada.nombre if turno.jornada else None
            
            # Agregar atributo temporal para el template
            turno.jornada_display = display_cache[key]
        
        context['turnos'] = turnos
        return context

class TurnoCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Turno
    template_name = 'turnos/turnos_create.html'
    fields = ['explorador', 'fecha', 'jornada', 'sala', 'tipo_cambio']
    success_url = '/turnos/lista/'

class TurnoUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Turno
    template_name = 'turnos/turnos_edit.html'
    fields = ['explorador', 'fecha', 'jornada', 'sala', 'tipo_cambio']
    success_url = '/turnos/lista/'

class TurnoDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Turno
    template_name = 'turnos/turnos_confirm_delete.html'
    success_url = '/turnos/lista/'

