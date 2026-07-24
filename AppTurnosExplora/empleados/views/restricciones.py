import logging

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import CreateView, DeleteView
from django.db.models import Count
from django.contrib import messages
from django.utils import timezone

from core.mixins import AdminRequiredMixin

from ..models import Empleado, RestriccionEmpleado
from ..forms import RestriccionEmpleadoForm

logger = logging.getLogger(__name__)


# CRUD de Restricciones
class RestriccionListView(LoginRequiredMixin, ListView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_list.html'
    context_object_name = 'restricciones'

    def _base_queryset(self):
        qs = (
            RestriccionEmpleado.objects
            .select_related('empleado')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if user.is_staff:
            eid = self.request.GET.get('explorador')
            if eid and str(eid).isdigit():
                qs = qs.filter(empleado_id=eid)
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(empleado=empleado)

    def get_queryset(self):
        return self._base_queryset()

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        context = super().get_context_data(**kwargs)
        queryset = self._base_queryset()
        user = self.request.user
        hoy = timezone.now().date()

        # Calcular totales usando el queryset base
        # Activa: fecha_fin es NULL o fecha_fin >= hoy
        # Finalizada: fecha_fin < hoy
        total_restricciones = queryset.count()
        total_activos = queryset.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizados = queryset.filter(fecha_fin__lt=hoy).count()

        context.update({
            'es_supervisor': user.is_staff,
            'empleado_actual': getattr(user, 'empleado', None) if not user.is_staff else None,
            'total_restricciones': total_restricciones,
            'total_activos': total_activos,
            'total_finalizados': total_finalizados,
            'totales_por_tipo': queryset.values('tipo_restriccion').annotate(total=Count('id')).order_by('-total'),
            'hoy': hoy
        })
        if user.is_staff:
            context['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
            context['filtro_explorador'] = self.request.GET.get('explorador', '')

        if not user.is_staff and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver restricciones.')

        return context

def _invalidar_turnos_cache_restriccion(restriccion):
    """Refresca Mis Turnos del empleado para que la restricción se vea al instante."""
    try:
        from datetime import timedelta, date as _date
        from core.services.cache_service import CacheService
        fin = restriccion.fecha_fin or (restriccion.fecha_inicio + timedelta(days=365))
        meses = set()
        d = restriccion.fecha_inicio
        while d <= fin:
            meses.add((d.month, d.year))
            d += timedelta(days=28)
        meses.add((fin.month, fin.year))
        for m, y in meses:
            CacheService.invalidar_cache_turnos_empleado(restriccion.empleado.id, m, y)
    except Exception:
        logger.warning("Error invalidando caché de turnos por restricción (empleado=%s)", restriccion.empleado_id, exc_info=True)


class RestriccionCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = RestriccionEmpleado
    form_class = RestriccionEmpleadoForm
    template_name = 'empleados/restricciones_create.html'
    success_url = '/empleados/restricciones/'

    def form_valid(self, response):
        resp = super().form_valid(response)
        _invalidar_turnos_cache_restriccion(self.object)
        return resp

class RestriccionUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = RestriccionEmpleado
    form_class = RestriccionEmpleadoForm
    template_name = 'empleados/restricciones_edit.html'
    success_url = '/empleados/restricciones/'

    def form_valid(self, response):
        resp = super().form_valid(response)
        _invalidar_turnos_cache_restriccion(self.object)
        return resp

class RestriccionDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_confirm_delete.html'
    success_url = '/empleados/restricciones/'

    def form_valid(self, form):
        _invalidar_turnos_cache_restriccion(self.get_object())
        return super().form_valid(form)


class RestriccionVisualizarListView(LoginRequiredMixin, ListView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_visualizar_list.html'
    context_object_name = 'restricciones'
    paginate_by = 20

    def _base_queryset(self):
        qs = (
            RestriccionEmpleado.objects
            .select_related('empleado')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if user.is_staff:
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(empleado=empleado)

    def get_queryset(self):
        qs = self._base_queryset()
        p = self.request.GET

        # Filtro por empleado (solo supervisores)
        emp_id = p.get('empleado')
        if emp_id and self.request.user.is_staff:
            qs = qs.filter(empleado_id=emp_id)

        # Filtro por rango de fechas (ambos roles)
        fecha_desde = p.get('fecha_desde')
        fecha_hasta = p.get('fecha_hasta')
        if fecha_desde:
            qs = qs.filter(fecha_inicio__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(fecha_inicio__lte=fecha_hasta)

        return qs

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        from django.utils import timezone
        context = super().get_context_data(**kwargs)
        user = self.request.user
        hoy = timezone.now().date()

        qs = self.get_queryset()
        total_activos = qs.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizados = qs.filter(fecha_fin__lt=hoy).count()

        empleados = []
        if user.is_staff:
            empleados = list(
                Empleado.objects.filter(activo=True)
                .order_by('apellido', 'nombre')
                .values('id', 'nombre', 'apellido')
            )

        params = self.request.GET.copy()
        params.pop('page', None)

        context.update({
            'es_supervisor': user.is_staff,
            'empleado_actual': getattr(user, 'empleado', None) if not user.is_staff else None,
            'hoy': hoy,
            'total_activos': total_activos,
            'total_finalizados': total_finalizados,
            'empleados': empleados,
            'filtro_empleado': self.request.GET.get('empleado', ''),
            'filtro_fecha_desde': self.request.GET.get('fecha_desde', ''),
            'filtro_fecha_hasta': self.request.GET.get('fecha_hasta', ''),
            'query_params': params.urlencode(),
        })

        if not user.is_staff and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver restricciones.')

        return context
