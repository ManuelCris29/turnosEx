from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, View
from django.http import JsonResponse
from empleados.views import AdminRequiredMixin
from .models import Turno, DiaEspecial
from .services.turno_service import TurnoService

# Create your views here.

class MisTurnosView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/mis_turnos.html'

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

# Vista solo visualización para Consultas Rápidas
class DiaEspecialVisualizarListView(LoginRequiredMixin, ListView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_visualizar_list.html'
    context_object_name = 'dias_especiales'
