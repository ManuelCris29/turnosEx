from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from datetime import date
from django.utils import timezone


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        from permisos.models import PermisoEspecial
        from empleados.models import Empleado
        from empleados.services.indicadores_service import IndicadoresService

        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Dashboard'
        context['user'] = self.request.user

        anio = timezone.localdate().year
        es_admin = self.request.user.is_staff
        empleado = getattr(self.request.user, 'empleado', None)

        # FUENTE ÚNICA DE VERDAD: las tarjetas "Cambios realizados" y "Tasa de
        # aprobación" usan EXACTAMENTE el mismo cálculo que la página de
        # Indicadores (ocurrencias reales de permanentes + permisos), para que
        # Dashboard, Mis Indicadores e Indicadores del supervisor coincidan.
        if es_admin:
            # Supervisor: métricas globales de toda la organización (1 por cambio).
            data = IndicadoresService.get(anio=anio)
            permisos_pend = PermisoEspecial.objects.filter(estado='PENDIENTE').count()
            kpi_empleados = Empleado.objects.filter(activo=True).count()
            kpi_permisos_usados = 0
        elif empleado:
            # Explorador: SUS datos, participación como solicitante O receptor
            # (igual que "Mis Indicadores").
            data = IndicadoresService.get(explorador_id=empleado.id, anio=anio, incluir_receptor=True)
            permisos_pend = PermisoEspecial.objects.filter(estado='PENDIENTE', empleado=empleado).count()
            kpi_empleados = 0
            kpi_permisos_usados = PermisoEspecial.objects.filter(
                estado='APROBADO', empleado=empleado, fecha_inicio__year=anio
            ).count()
        else:
            # Usuario autenticado sin empleado asociado: todo en 0, sin errores.
            data = None
            permisos_pend = kpi_empleados = kpi_permisos_usados = 0

        kpi_cambios = data['total_general'] if data else 0
        kpi_tasa = data['kpis']['pct_aprobacion'] if data else 0

        # Aviso de apertura de año: entre la fecha de recordatorio y la de bloqueo, el
        # supervisor ve un banner. Después de la de bloqueo ya no llega aquí (el middleware
        # lo redirige al checklist), así que este aviso es solo la fase amable.
        apertura_aviso = None
        if es_admin:
            try:
                from turnos.services.apertura_anio_service import AperturaAnioService
                situacion, anio_apertura = AperturaAnioService.situacion()
                if situacion in ('aviso', 'bloqueo'):
                    apertura_aviso = {
                        'anio': anio_apertura,
                        'pendientes': AperturaAnioService.pendientes(anio_apertura),
                    }
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    'No se pudo evaluar la apertura de año para el dashboard', exc_info=True)

        context.update({
            'es_admin': es_admin,
            'anio': anio,
            'apertura_aviso': apertura_aviso,
            'kpi_cambios': kpi_cambios,
            'kpi_tasa': kpi_tasa,
            'kpi_empleados': kpi_empleados,
            'kpi_permisos_usados': kpi_permisos_usados,
            'kpi_permisos_pend': permisos_pend,
        })
        return context
