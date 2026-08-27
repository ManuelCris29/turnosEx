from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils import timezone
from django.views.generic import TemplateView


class DashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/dashboard.html'

    def get_context_data(self, **kwargs):
        from empleados.models import Empleado
        from empleados.services.indicadores_service import IndicadoresService
        from permisos.models import PermisoEspecial

        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Dashboard'
        context['user'] = self.request.user

        anio = timezone.localdate().year
        from core.mixins import es_supervisor

        # Mismo criterio que el menú y las vistas de administración: el rol
        # Supervisor debe ver las métricas globales aunque no sea `is_staff`.
        es_admin = es_supervisor(self.request.user)
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

        # Morosos con deuda vencida que todavía nadie ha sancionado. Solo para el
        # supervisor, y solo si hay alguno: la sanción por deuda se calcula cuando el
        # explorador entra a la app, así que quien no entra no aparece bloqueado en ningún
        # sitio. Este aviso es lo que hace que el supervisor se entere sin ir a buscarlo.
        morosos_pendientes = 0
        revision_dias_sin_correr = 0
        if es_admin:
            try:
                from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
                morosos_pendientes = DeudaCorporativaService.contar_pendientes_de_sancion()
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    'No se pudo contar los morosos para el dashboard', exc_info=True)
            # Un cron caído no avisa: deja de ocurrir y ya. El síntoma —morosos que siguen
            # solicitando— tarda semanas en notarse y no se atribuye a esto. Aquí lo ve
            # alguien al día siguiente, sin tener que mirar logs de servidor.
            try:
                from solicitudes.models import RevisionSancionesDeuda
                if RevisionSancionesDeuda.hay_hueco():
                    revision_dias_sin_correr = RevisionSancionesDeuda.dias_sin_ejecutar()
            except Exception:
                import logging
                logging.getLogger(__name__).warning(
                    'No se pudo comprobar la última revisión de sanciones', exc_info=True)

        context.update({
            'es_admin': es_admin,
            'morosos_pendientes': morosos_pendientes,
            'revision_dias_sin_correr': revision_dias_sin_correr,
            'anio': anio,
            'apertura_aviso': apertura_aviso,
            'kpi_cambios': kpi_cambios,
            'kpi_tasa': kpi_tasa,
            'kpi_empleados': kpi_empleados,
            'kpi_permisos_usados': kpi_permisos_usados,
            'kpi_permisos_pend': permisos_pend,
        })
        return context
