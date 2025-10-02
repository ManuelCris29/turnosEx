from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from empleados.views import AdminRequiredMixin
from .models import Turno, DiaEspecial, AsignarSalaExplorador, AsignarJornadaExplorador
from datetime import timedelta
from django.utils import timezone
import json

# Create your views here.

class MisTurnosView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/mis_turnos.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if hasattr(self.request.user, 'empleado'):
            empleado = self.request.user.empleado
            fecha_actual = timezone.now().date()
            
            # Obtener fecha actual y calcular solo el mes actual (optimizado)
            from datetime import timedelta
            fecha_actual = timezone.now().date()
            
            # Calcular solo el mes actual para optimizar rendimiento
            inicio_mes = fecha_actual.replace(day=1)
            if fecha_actual.month == 12:
                fin_mes = fecha_actual.replace(year=fecha_actual.year + 1, month=1, day=1) - timedelta(days=1)
            else:
                fin_mes = fecha_actual.replace(month=fecha_actual.month + 1, day=1) - timedelta(days=1)
            
            # Calcular inicio y fin de la semana actual para el resumen semanal
            inicio_semana = fecha_actual - timedelta(days=fecha_actual.weekday())
            fin_semana = inicio_semana + timedelta(days=6)
            
            # Obtener turnos asignados solo para el mes actual (optimizado, evitando N+1)
            turnos_mes = (
                Turno.objects
                .filter(
                    explorador=empleado,
                    fecha__gte=inicio_mes,
                    fecha__lte=fin_mes
                )
                .select_related('jornada', 'sala')
                .order_by('fecha')
            )
            turnos_por_fecha = {t.fecha: t for t in turnos_mes}
            
            # Obtener asignaciones de sala activas
            from .models import AsignarSalaExplorador
            asignaciones_activas = AsignarSalaExplorador.objects.filter(
                explorador=empleado,
                fecha_inicio__lte=fecha_actual,
                fecha_fin__gte=fecha_actual
            ).first()
            
            # Obtener jornada predeterminada vigente (una por explorador)
            try:
                jornada_predeterminada = AsignarJornadaExplorador.objects.select_related('jornada').get(
                    explorador=empleado
                )
            except AsignarJornadaExplorador.DoesNotExist:
                jornada_predeterminada = None
            jornada_base = (
                jornada_predeterminada.jornada.nombre if jornada_predeterminada else None
            )

            def calcular_jornada_dia(j_base, fecha):
                if not j_base:
                    return "PM"
                if j_base == "AM" and fecha.weekday() == 5:  # Sábado
                    return "Descanso"
                if j_base == "PM" and fecha.weekday() == 6:  # Domingo
                    return "Descanso"
                return j_base
            
            # Crear estructura de datos solo para el mes actual (optimizado)
            turnos_mes_dict = {}
            for i in range((fin_mes - inicio_mes).days + 1):
                fecha = inicio_mes + timedelta(days=i)
                turno = turnos_por_fecha.get(fecha)
                
                if turno:
                    # Hay turno asignado (puede ser cambio aprobado)
                    turnos_mes_dict[fecha] = {
                        'turno': turno,
                        'jornada': turno.jornada.nombre,
                        'sala': turno.sala.nombre,
                        'tipo': 'asignado',
                        'es_cambio': turno.tipo_cambio is not None
                    }
                else:
                    # No hay turno asignado, usar jornada predeterminada
                    jornada_nombre = calcular_jornada_dia(jornada_base, fecha)
                    
                    # Intentar obtener sala de asignación activa
                    sala_nombre = 'Por asignar'
                    if asignaciones_activas:
                        sala_nombre = asignaciones_activas.sala.nombre
                    
                    turnos_mes_dict[fecha] = {
                        'turno': None,
                        'jornada': jornada_nombre,
                        'sala': sala_nombre,
                        'tipo': 'predeterminado',
                        'es_cambio': False
                    }
            
            # Crear estructura de datos para la semana actual (resumen semanal)
            semana_turnos = {}
            for i in range(7):
                fecha = inicio_semana + timedelta(days=i)
                if fecha in turnos_mes_dict:
                    semana_turnos[fecha] = turnos_mes_dict[fecha]
                else:
                    # Si la fecha no está en el mes actual, usar regla predeterminada
                    jornada_nombre = calcular_jornada_dia(jornada_base, fecha)
                    
                    semana_turnos[fecha] = {
                        'turno': None,
                        'jornada': jornada_nombre,
                        'sala': 'Por asignar',
                        'tipo': 'predeterminado',
                        'es_cambio': False
                    }
            
            # Convertir fechas a strings para JSON (solo mes actual)
            turnos_mes_json = {}
            for fecha, info in turnos_mes_dict.items():
                turnos_mes_json[fecha.strftime('%Y-%m-%d')] = {
                    'jornada': info['jornada'],
                    'sala': info['sala'],
                    'tipo': info['tipo'],
                    'es_cambio': info['es_cambio']
                }
            
            # Convertir a string JSON válido
            turnos_mes_json_str = json.dumps(turnos_mes_json)
            
            context.update({
                'empleado': empleado,
                'semana_actual': {
                    'inicio': inicio_semana,
                    'fin': fin_semana
                },
                'semana_turnos': semana_turnos,
                'turnos_mes': turnos_mes,
                'turnos_mes_json_str': turnos_mes_json_str,
                'asignaciones_activas': asignaciones_activas,
                'fecha_actual': fecha_actual
            })
        
        return context

class CambiosTurnoView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/placeholder.html'

class ConsolidadoHorasView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/placeholder.html'

# CRUD de Turnos
class TurnoListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Turno
    template_name = 'turnos/turnos_list.html'
    context_object_name = 'turnos'

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

class DiasEspecialesView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/diasespeciales_list.html'

# CRUD de Días Especiales
class DiaEspecialListView(LoginRequiredMixin, ListView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_list.html'
    context_object_name = 'dias_especiales'

class DiaEspecialCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_create.html'
    fields = ['fecha', 'tipo', 'descripcion', 'recurrente', 'activo']
    success_url = '/turnos/dias-especiales-admin/'

class DiaEspecialUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_edit.html'
    fields = ['fecha', 'tipo', 'descripcion', 'recurrente', 'activo']
    success_url = '/turnos/dias-especiales-admin/'

class DiaEspecialDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_confirm_delete.html'
    success_url = '/turnos/dias-especiales-admin/'

class TurnosCalendarioView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/turnos_calendario.html'


# Vista solo visualización para Consultas Rápidas
class DiaEspecialVisualizarListView(LoginRequiredMixin, ListView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_visualizar_list.html'
    context_object_name = 'dias_especiales'
