from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from datetime import date


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio
        from permisos.models import PermisoEspecial
        from empleados.models import Empleado

        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Dashboard'
        context['user'] = self.request.user

        anio = date.today().year
        es_admin = self.request.user.is_staff
        empleado = getattr(self.request.user, 'empleado', None)

        if es_admin:
            # Supervisor: métricas globales de toda la organización.
            aprobadas = SolicitudCambio.objects.filter(estado='aprobada', fecha_cambio_turno__year=anio).count()
            total_sol = SolicitudCambio.objects.filter(fecha_cambio_turno__year=anio).count()
            permisos_pend = PermisoEspecial.objects.filter(estado='PENDIENTE').count()
            kpi_empleados = Empleado.objects.filter(activo=True).count()
            kpi_permisos_usados = 0
        elif empleado:
            # Explorador: solo SUS propios datos. "Cambios" = solicitudes donde
            # participó (solicitante o receptor). El card de "Exploradores activos"
            # se reemplaza por "Mis permisos usados" (permisos APROBADO del año).
            mias = SolicitudCambio.objects.filter(
                Q(explorador_solicitante=empleado) | Q(explorador_receptor=empleado),
                fecha_cambio_turno__year=anio,
            )
            aprobadas = mias.filter(estado='aprobada').count()
            total_sol = mias.count()
            permisos_pend = PermisoEspecial.objects.filter(estado='PENDIENTE', empleado=empleado).count()
            kpi_empleados = 0
            kpi_permisos_usados = PermisoEspecial.objects.filter(
                estado='APROBADO', empleado=empleado, fecha_inicio__year=anio
            ).count()
        else:
            # Usuario autenticado sin empleado asociado: todo en 0, sin errores.
            aprobadas = total_sol = permisos_pend = kpi_empleados = kpi_permisos_usados = 0

        context.update({
            'es_admin': es_admin,
            'anio': anio,
            'kpi_cambios': aprobadas,
            'kpi_tasa': round(100 * aprobadas / total_sol) if total_sol else 0,
            'kpi_empleados': kpi_empleados,
            'kpi_permisos_usados': kpi_permisos_usados,
            'kpi_permisos_pend': permisos_pend,
        })
        return context
