from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, UpdateView
from django.views.generic.edit import CreateView, DeleteView
from django.contrib import messages
from django.utils import timezone

from core.mixins import AdminRequiredMixin

from ..models import Empleado, SancionEmpleado
from ..forms import SancionEmpleadoForm


# CRUD de Sanciones
class SancionListView(LoginRequiredMixin, ListView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_list.html'
    context_object_name = 'sanciones'

    def _base_queryset(self):
        qs = (
            SancionEmpleado.objects
            .select_related('explorador', 'supervisor')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if user.is_staff:
            eid = self.request.GET.get('explorador')
            if eid and str(eid).isdigit():
                qs = qs.filter(explorador_id=eid)
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(explorador=empleado)

    def get_queryset(self):
        return self._base_queryset()

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        context = super().get_context_data(**kwargs)
        queryset = self._base_queryset()
        user = self.request.user
        hoy = timezone.now().date()

        total_sanciones = queryset.count()
        total_activas = queryset.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizadas = queryset.filter(fecha_fin__lt=hoy).count()

        context.update({
            'es_supervisor': user.is_staff,
            'empleado_actual': getattr(user, 'empleado', None) if not user.is_staff else None,
            'total_sanciones': total_sanciones,
            'total_activas': total_activas,
            'total_finalizadas': total_finalizadas,
            'hoy': hoy
        })
        if user.is_staff:
            context['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
            context['filtro_explorador'] = self.request.GET.get('explorador', '')

        if not user.is_staff and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver sanciones.')

        return context

def _invalidar_turnos_cache_sancion(sancion):
    """Refresca Mis Turnos del explorador para que la sanción se vea al instante."""
    try:
        from datetime import date, timedelta
        from core.services.cache_service import CacheService
        hoy = date.today()
        # Para indefinidas, cubrir hasta el mes actual (no solo +365 días desde inicio)
        fin = sancion.fecha_fin or max(sancion.fecha_inicio + timedelta(days=365), hoy)
        meses = set()
        d = sancion.fecha_inicio
        while d <= fin:
            meses.add((d.month, d.year))
            d += timedelta(days=28)
        meses.add((fin.month, fin.year))
        for m, y in meses:
            CacheService.invalidar_cache_turnos_empleado(sancion.explorador.id, m, y)
    except Exception:
        pass


class SancionCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = SancionEmpleado
    form_class = SancionEmpleadoForm
    template_name = 'empleados/sanciones_create.html'
    success_url = '/empleados/sanciones/'

    def form_valid(self, response):
        resp = super().form_valid(response)
        _invalidar_turnos_cache_sancion(self.object)
        return resp

class SancionUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = SancionEmpleado
    form_class = SancionEmpleadoForm
    template_name = 'empleados/sanciones_edit.html'
    success_url = '/empleados/sanciones/'

    def form_valid(self, response):
        resp = super().form_valid(response)
        _invalidar_turnos_cache_sancion(self.object)
        return resp

class SancionDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_confirm_delete.html'
    success_url = '/empleados/sanciones/'

    def form_valid(self, form):
        _invalidar_turnos_cache_sancion(self.get_object())
        return super().form_valid(form)


class SancionVisualizarListView(LoginRequiredMixin, ListView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_visualizar_list.html'
    context_object_name = 'sanciones'
    paginate_by = 20

    def _base_queryset(self):
        qs = (
            SancionEmpleado.objects
            .select_related('explorador', 'supervisor')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if user.is_staff:
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(explorador=empleado)

    def get_queryset(self):
        from django.db.models import Q
        qs = self._base_queryset()
        p = self.request.GET

        # Filtro por empleado (solo supervisores)
        emp_id = p.get('empleado')
        if emp_id and self.request.user.is_staff:
            qs = qs.filter(explorador_id=emp_id)

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

        # Totales sobre el queryset ya filtrado
        qs = self.get_queryset()
        total_activas = qs.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizadas = qs.filter(fecha_fin__lt=hoy).count()

        # Lista de empleados para el selector del supervisor
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
            'total_activas': total_activas,
            'total_finalizadas': total_finalizadas,
            'empleados': empleados,
            'filtro_empleado': self.request.GET.get('empleado', ''),
            'filtro_fecha_desde': self.request.GET.get('fecha_desde', ''),
            'filtro_fecha_hasta': self.request.GET.get('fecha_hasta', ''),
            'query_params': params.urlencode(),
        })

        if not user.is_staff and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver sanciones.')

        return context
