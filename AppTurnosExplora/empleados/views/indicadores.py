from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from django.shortcuts import redirect

from core.mixins import AdminRequiredMixin

from ..models import Empleado


class IndicadoresView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Panel de indicadores/KPIs para supervisores."""
    template_name = 'empleados/indicadores.html'

    def get_context_data(self, **kwargs):
        import json
        from ..services.indicadores_service import IndicadoresService
        ctx = super().get_context_data(**kwargs)
        explorador = self.request.GET.get('explorador') or None
        jornada = self.request.GET.get('jornada') or None
        anio_raw = self.request.GET.get('anio')
        anio = int(anio_raw) if anio_raw and str(anio_raw).isdigit() else None

        # Al mirar a UN explorador se cuenta su participación completa (solicitante
        # O receptor), igual que su vista personal, para que el número coincida.
        # Sin explorador (organización), se cuenta 1 por cambio (solo solicitante)
        # para no duplicar cada cambio entre sus dos participantes.
        data = IndicadoresService.get(
            explorador_id=explorador, jornada=jornada, anio=anio,
            incluir_receptor=bool(explorador),
        )
        ctx.update(data)
        ctx['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
        ctx['anios'] = IndicadoresService.anios_disponibles()
        ctx['filtro_explorador'] = explorador or ''
        ctx['filtro_jornada'] = jornada or ''
        ctx['chart_series_json'] = data['chart_series']
        ctx['meses_json'] = data['meses_nombres']
        return ctx


class MisIndicadoresView(LoginRequiredMixin, TemplateView):
    """Indicadores personales del explorador: mismas gráficas que el supervisor
    pero filtradas SOLO a sus propios datos (participación como solicitante o
    receptor). No admite elegir otro explorador ni jornada (privacidad)."""
    template_name = 'empleados/indicadores.html'

    def get_context_data(self, **kwargs):
        from ..services.indicadores_service import IndicadoresService
        ctx = super().get_context_data(**kwargs)
        empleado = getattr(self.request.user, 'empleado', None)
        if not empleado:
            return ctx  # se maneja el redirect en get()

        anio_raw = self.request.GET.get('anio')
        anio = int(anio_raw) if anio_raw and str(anio_raw).isdigit() else None

        data = IndicadoresService.get(explorador_id=empleado.id, anio=anio, incluir_receptor=True)
        ctx.update(data)
        ctx['page_title'] = 'Mis Indicadores'
        ctx['mi_vista'] = True
        ctx['anios'] = IndicadoresService.anios_disponibles()
        ctx['filtro_explorador'] = ''
        ctx['filtro_jornada'] = ''
        ctx['chart_series_json'] = data['chart_series']
        ctx['meses_json'] = data['meses_nombres']
        return ctx

    def get(self, request, *args, **kwargs):
        if not getattr(request.user, 'empleado', None):
            return redirect('dashboard')
        return super().get(request, *args, **kwargs)
