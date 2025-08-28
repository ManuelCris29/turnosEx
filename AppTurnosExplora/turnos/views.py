from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, View
from django.http import JsonResponse
from empleados.views import AdminRequiredMixin
from .models import Turno, DiaEspecial, AsignarSalaExplorador, AsignarJornadaExplorador
from .services.turno_service import TurnoService
from datetime import datetime, timedelta
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
            
            # Obtener turnos asignados solo para el mes actual (optimizado)
            turnos_mes = Turno.objects.filter(
                explorador=empleado,
                fecha__gte=inicio_mes,
                fecha__lte=fin_mes
            ).order_by('fecha')
            
            # Obtener asignaciones de sala activas
            from .models import AsignarSalaExplorador
            asignaciones_activas = AsignarSalaExplorador.objects.filter(
                explorador=empleado,
                fecha_inicio__lte=fecha_actual,
                fecha_fin__gte=fecha_actual
            ).first()
            
            # Obtener jornada predeterminada del empleado
            jornada_predeterminada = AsignarJornadaExplorador.objects.filter(
                explorador=empleado
            ).order_by('-fecha_inicio').first()
            
            # Crear estructura de datos solo para el mes actual (optimizado)
            turnos_mes_dict = {}
            for i in range((fin_mes - inicio_mes).days + 1):
                fecha = inicio_mes + timedelta(days=i)
                turno = turnos_mes.filter(fecha=fecha).first()
                
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
                    if jornada_predeterminada:
                        jornada_base = jornada_predeterminada.jornada.nombre
                        
                        # Aplicar regla de descanso según la jornada
                        if jornada_base == "AM":
                            # AM: descansan los sábados
                            if fecha.weekday() == 5:  # Sábado
                                jornada_nombre = "Descanso"
                            else:
                                jornada_nombre = jornada_base
                        elif jornada_base == "PM":
                            # PM: descansan los domingos
                            if fecha.weekday() == 6:  # Domingo
                                jornada_nombre = "Descanso"
                            else:
                                jornada_nombre = jornada_base
                        else:
                            jornada_nombre = jornada_base
                    else:
                        # Si no hay jornada configurada, usar PM por defecto
                        jornada_nombre = "PM"
                    
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
                    # Si la fecha no está en el mes actual, usar jornada predeterminada
                    if jornada_predeterminada:
                        jornada_base = jornada_predeterminada.jornada.nombre
                        if jornada_base == "AM" and fecha.weekday() == 5:
                            jornada_nombre = "Descanso"
                        elif jornada_base == "PM" and fecha.weekday() == 6:
                            jornada_nombre = "Descanso"
                        else:
                            jornada_nombre = jornada_base
                    else:
                        jornada_nombre = "PM"
                    
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

class TurnosPorDiaView(LoginRequiredMixin, View):
    def get(self, request):
        fecha = request.GET.get('fecha')
        if not fecha:
            return JsonResponse({'error': 'Debe seleccionar una fecha'}, status=400)
        data = TurnoService.get_exploradores_por_jornada(fecha)
        # Serializar empleados (solo nombre y apellido)
        am = [{'id': e.id, 'nombre': e.nombre, 'apellido': e.apellido} for e in data['am']]
        pm = [{'id': e.id, 'nombre': e.nombre, 'apellido': e.apellido} for e in data['pm']]
        return JsonResponse({'am': am, 'pm': pm})

class TurnosPorMesView(LoginRequiredMixin, View):
    def get(self, request):
        fecha_inicio = request.GET.get('fecha_inicio')
        fecha_fin = request.GET.get('fecha_fin')
        if not fecha_inicio or not fecha_fin:
            return JsonResponse({'error': 'Debe enviar fecha_inicio y fecha_fin'}, status=400)
        data = TurnoService.get_exploradores_por_jornada_rango(fecha_inicio, fecha_fin)
        # Serializar empleados (ya son dicts)
        serializado = {}
        for dia, grupos in data.items():
            serializado[dia] = {
                'am': grupos['am'],
                'pm': grupos['pm'],
            }
        return JsonResponse(serializado)

class MisTurnosPorMesView(LoginRequiredMixin, View):
    """Vista para obtener jornadas de un mes específico (cálculo dinámico)"""
    
    def get(self, request):
        if not hasattr(request.user, 'empleado'):
            return JsonResponse({'error': 'Usuario no es empleado'}, status=400)
        
        empleado = request.user.empleado
        mes = request.GET.get('mes')  # formato: '2025-08'
        anio = request.GET.get('anio')  # formato: '2025'
        
        if not mes or not anio:
            return JsonResponse({'error': 'Debe enviar mes y anio'}, status=400)
        
        try:
            # Calcular inicio y fin del mes solicitado
            fecha_inicio = datetime.strptime(f"{anio}-{mes}-01", "%Y-%m-%d").date()
            if int(mes) == 12:
                fecha_fin = datetime.strptime(f"{int(anio)+1}-01-01", "%Y-%m-%d").date() - timedelta(days=1)
            else:
                fecha_fin = datetime.strptime(f"{anio}-{int(mes)+1:02d}-01", "%Y-%m-%d").date() - timedelta(days=1)
            
            # Obtener turnos del mes solicitado
            turnos_mes = Turno.objects.filter(
                explorador=empleado,
                fecha__gte=fecha_inicio,
                fecha__lte=fecha_fin
            ).order_by('fecha')
            
            # Obtener jornada predeterminada
            jornada_predeterminada = AsignarJornadaExplorador.objects.filter(
                explorador=empleado
            ).order_by('-fecha_inicio').first()
            
            # Crear estructura de datos para el mes
            turnos_mes_dict = {}
            for i in range((fecha_fin - fecha_inicio).days + 1):
                fecha = fecha_inicio + timedelta(days=i)
                turno = turnos_mes.filter(fecha=fecha).first()
                
                if turno:
                    turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                        'jornada': turno.jornada.nombre,
                        'sala': turno.sala.nombre,
                        'tipo': 'asignado',
                        'es_cambio': turno.tipo_cambio is not None
                    }
                else:
                    # Usar jornada predeterminada
                    if jornada_predeterminada:
                        jornada_base = jornada_predeterminada.jornada.nombre
                        if jornada_base == "AM" and fecha.weekday() == 5:
                            jornada_nombre = "Descanso"
                        elif jornada_base == "PM" and fecha.weekday() == 6:
                            jornada_nombre = "Descanso"
                        else:
                            jornada_nombre = jornada_base
                    else:
                        jornada_nombre = "PM"
                    
                    turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                        'jornada': jornada_nombre,
                        'sala': 'Por asignar',
                        'tipo': 'predeterminado',
                        'es_cambio': False
                    }
            
            return JsonResponse(turnos_mes_dict)
            
        except Exception as e:
            return JsonResponse({'error': f'Error al procesar fechas: {str(e)}'}, status=400)

# Vista solo visualización para Consultas Rápidas
class DiaEspecialVisualizarListView(LoginRequiredMixin, ListView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_visualizar_list.html'
    context_object_name = 'dias_especiales'
