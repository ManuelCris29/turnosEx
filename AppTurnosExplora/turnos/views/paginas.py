from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from core.mixins import AdminRequiredMixin

# Create your views here.

class MisTurnosView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/mis_turnos.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if hasattr(self.request.user, 'empleado'):
            from ..services.turno_context_service import TurnoContextService
            empleado = self.request.user.empleado
            context_data = TurnoContextService.get_context_data_for_mis_turnos_view(empleado)
            
            context.update({
                'empleado': empleado,
                'semana_actual': {
                    'inicio': context_data['inicio_semana'],
                    'fin': context_data['fin_semana']
                },
                'semana_turnos': context_data['turnos_semana'],
                'turnos_mes': list(context_data['turnos_mes'].values()),
                'turnos_mes_json_str': context_data['turnos_mes_json_str'],
                'asignaciones_activas': context_data['asignaciones_activas'],
                'fecha_actual': context_data['fecha_actual']
            })
        
        return context

class CambiosTurnoView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/placeholder.html'

class ConsolidadoHorasView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/consolidado_horas.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from empleados.models import Empleado

        from ..services.consolidado_horas_service import ConsolidadoHorasService

        user = self.request.user
        es_supervisor = ConsolidadoHorasService.es_supervisor(user)
        empleado_actual = getattr(user, 'empleado', None)

        objetivo = None
        if es_supervisor:
            # El supervisor elige a quién consultar (?explorador_id=...)
            context['exploradores'] = ConsolidadoHorasService.exploradores_disponibles()
            eid = self.request.GET.get('explorador_id')
            if eid:
                objetivo = Empleado.objects.filter(id=eid, activo=True).first()
            elif empleado_actual:
                # Por defecto, el propio supervisor (si también es explorador)
                objetivo = empleado_actual
        else:
            # Explorador: solo sus propios datos
            objetivo = empleado_actual

        context['es_supervisor'] = es_supervisor
        context['explorador_objetivo'] = objetivo
        context['explorador_id_sel'] = str(objetivo.id) if objetivo else ''
        if objetivo:
            context['consolidado'] = ConsolidadoHorasService.get_consolidado(objetivo)
        return context

# CRUD de Turnos
class DiasEspecialesView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/diasespeciales_list.html'

# CRUD de Días Especiales
class TurnosCalendarioView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = 'turnos/turnos_calendario.html'


# Vista solo visualización para Consultas Rápidas
