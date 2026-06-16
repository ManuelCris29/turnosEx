from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from datetime import date


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        from solicitudes.models import SolicitudCambio
        from permisos.models import PermisoEspecial
        from empleados.models import Empleado

        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Dashboard'
        context['user'] = self.request.user

        anio = date.today().year
        es_admin = self.request.user.is_staff
        empleado = getattr(self.request.user, 'empleado', None)

        aprobadas = SolicitudCambio.objects.filter(estado='aprobada', fecha_cambio_turno__year=anio).count()
        total_sol = SolicitudCambio.objects.filter(fecha_cambio_turno__year=anio).count()

        if es_admin:
            permisos_pend = PermisoEspecial.objects.filter(estado='PENDIENTE').count()
        else:
            permisos_pend = (PermisoEspecial.objects.filter(estado='PENDIENTE', empleado=empleado).count()
                             if empleado else 0)

        context.update({
            'es_admin': es_admin,
            'anio': anio,
            'kpi_cambios': aprobadas,
            'kpi_tasa': round(100 * aprobadas / total_sol) if total_sol else 0,
            'kpi_empleados': Empleado.objects.filter(activo=True).count(),
            'kpi_permisos_pend': permisos_pend,
        })
        return context
