import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import CreateView, DeleteView

from core.mixins import AdminRequiredMixin, es_supervisor

from ..forms import RestriccionEmpleadoForm
from ..models import Empleado, RestriccionEmpleado

logger = logging.getLogger(__name__)


def _id_valido(valor):
    """Devuelve el id como int solo si el parámetro es un entero; si no, None."""
    return int(valor) if valor and str(valor).isdigit() else None


# CRUD de Restricciones
class RestriccionListView(LoginRequiredMixin, ListView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_list.html'
    context_object_name = 'restricciones'
    paginate_by = 25

    def _base_queryset(self):
        """Restricciones visibles para el usuario, ya filtradas por explorador."""
        if hasattr(self, '_qs_cache'):
            return self._qs_cache
        qs = (
            RestriccionEmpleado.objects
            .select_related('empleado')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if es_supervisor(user):
            eid = _id_valido(self.request.GET.get('explorador'))
            if eid:
                qs = qs.filter(empleado_id=eid)
        else:
            empleado = getattr(user, 'empleado', None)
            qs = qs.filter(empleado=empleado) if empleado else qs.none()
        self._qs_cache = qs
        return qs

    def _estado(self):
        estado = self.request.GET.get('estado')
        return estado if estado in ('activa', 'finalizada') else 'todos'

    def get_queryset(self):
        from django.db.models import Q
        # El filtro por estado va en el servidor: si filtrara en el navegador
        # solo afectaría a la página visible y contradiría los totales.
        qs = self._base_queryset()
        hoy = timezone.localdate()
        estado = self._estado()
        if estado == 'activa':
            return qs.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy))
        if estado == 'finalizada':
            return qs.filter(fecha_fin__lt=hoy)
        return qs

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        context = super().get_context_data(**kwargs)
        queryset = self._base_queryset()
        user = self.request.user
        hoy = timezone.localdate()

        # Calcular totales usando el queryset base
        # Activa: fecha_fin es NULL o fecha_fin >= hoy
        # Finalizada: fecha_fin < hoy
        total_restricciones = queryset.count()
        total_activos = queryset.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizados = queryset.filter(fecha_fin__lt=hoy).count()

        supervisa = es_supervisor(user)
        context.update({
            'es_supervisor': supervisa,
            'empleado_actual': getattr(user, 'empleado', None) if not supervisa else None,
            'total_restricciones': total_restricciones,
            'total_activos': total_activos,
            'total_finalizados': total_finalizados,
            'totales_por_tipo': queryset.values('tipo_restriccion').annotate(total=Count('id')).order_by('-total'),
            'filtro_estado': self._estado(),
            'hoy': hoy
        })
        params = self.request.GET.copy()
        params.pop('page', None)
        context['query_params'] = params.urlencode()
        # Para los enlaces de estado: mismos filtros, sin página ni estado
        base = self.request.GET.copy()
        base.pop('page', None)
        base.pop('estado', None)
        context['query_sin_estado'] = base.urlencode()

        if supervisa:
            context['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
            eid = _id_valido(self.request.GET.get('explorador'))
            context['filtro_explorador'] = str(eid) if eid else ''

        if not supervisa and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver restricciones.')

        return context

def _invalidar_turnos_cache_restriccion(restriccion):
    """Refresca Mis Turnos del empleado para que la restricción se vea al instante."""
    try:
        from datetime import timedelta

        from core.services.cache_service import CacheService
        hoy = timezone.localdate()
        # Para indefinidas, cubrir hasta el mes actual (no solo +365 días desde inicio)
        fin = restriccion.fecha_fin or max(restriccion.fecha_inicio + timedelta(days=365), hoy)
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


class _RestriccionFormViewMixin:
    """Tras crear o editar, refresca Mis Turnos del empleado afectado."""

    def form_valid(self, form):
        resp = super().form_valid(form)
        _invalidar_turnos_cache_restriccion(self.object)
        return resp


class RestriccionCreateView(LoginRequiredMixin, AdminRequiredMixin, _RestriccionFormViewMixin, CreateView):
    model = RestriccionEmpleado
    form_class = RestriccionEmpleadoForm
    template_name = 'empleados/restricciones_create.html'
    success_url = '/empleados/restricciones/'

class RestriccionUpdateView(LoginRequiredMixin, AdminRequiredMixin, _RestriccionFormViewMixin, UpdateView):
    model = RestriccionEmpleado
    form_class = RestriccionEmpleadoForm
    template_name = 'empleados/restricciones_edit.html'
    success_url = '/empleados/restricciones/'

class RestriccionDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_confirm_delete.html'
    success_url = '/empleados/restricciones/'

    def form_valid(self, form):
        _invalidar_turnos_cache_restriccion(self.object)
        return super().form_valid(form)


class RestriccionVisualizarListView(LoginRequiredMixin, ListView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_visualizar_list.html'
    context_object_name = 'restricciones'
    paginate_by = 20

    def _filtros(self):
        """Filtros ya validados: un parámetro con basura se ignora, no rompe la página."""
        if hasattr(self, '_filtros_cache'):
            return self._filtros_cache
        p = self.request.GET
        self._filtros_cache = {
            # El filtro por explorador solo tiene sentido para quien ve a todos
            'empleado': _id_valido(p.get('empleado')) if es_supervisor(self.request.user) else None,
            'fecha_desde': parse_date(p.get('fecha_desde') or ''),
            'fecha_hasta': parse_date(p.get('fecha_hasta') or ''),
        }
        return self._filtros_cache

    def _base_queryset(self):
        qs = (
            RestriccionEmpleado.objects
            .select_related('empleado')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if es_supervisor(user):
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(empleado=empleado)

    def get_queryset(self):
        if hasattr(self, '_qs_cache'):
            return self._qs_cache
        qs = self._base_queryset()
        f = self._filtros()

        if f['empleado']:
            qs = qs.filter(empleado_id=f['empleado'])
        if f['fecha_desde']:
            qs = qs.filter(fecha_inicio__gte=f['fecha_desde'])
        if f['fecha_hasta']:
            qs = qs.filter(fecha_inicio__lte=f['fecha_hasta'])

        self._qs_cache = qs
        return qs

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        context = super().get_context_data(**kwargs)
        user = self.request.user
        hoy = timezone.localdate()
        supervisa = es_supervisor(user)

        # Totales sobre el queryset ya filtrado
        qs = self.get_queryset()
        total_activos = qs.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizados = qs.filter(fecha_fin__lt=hoy).count()

        # Lista de empleados para el selector del supervisor
        empleados = []
        if supervisa:
            empleados = list(
                Empleado.objects.filter(activo=True)
                .order_by('apellido', 'nombre')
                .values('id', 'nombre', 'apellido')
            )

        f = self._filtros()
        params = self.request.GET.copy()
        params.pop('page', None)

        context.update({
            'es_supervisor': supervisa,
            'empleado_actual': getattr(user, 'empleado', None) if not supervisa else None,
            'hoy': hoy,
            'total_activos': total_activos,
            'total_finalizados': total_finalizados,
            'empleados': empleados,
            'filtro_empleado': str(f['empleado']) if f['empleado'] else '',
            'filtro_fecha_desde': f['fecha_desde'].isoformat() if f['fecha_desde'] else '',
            'filtro_fecha_hasta': f['fecha_hasta'].isoformat() if f['fecha_hasta'] else '',
            'query_params': params.urlencode(),
        })

        if not supervisa and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver restricciones.')

        return context
