import logging
from django.shortcuts import redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.http import JsonResponse
from django.contrib import messages
from django.urls import reverse
from core.mixins import AdminRequiredMixin
from ..models import DiaEspecial, DescansoSemanaManual
from django.utils import timezone
import json

logger = logging.getLogger(__name__)

# Mismo texto en los tres puntos donde se valida el año (dos vistas HTML y un endpoint JSON).
_MSG_ANIO_INVALIDO = 'Año inválido.'


def _invalidar_cache_turnos(anio, meses=None):
    """
    Invalida el caché de Mis Turnos de todos los empleados activos para los meses indicados
    (por defecto, el año completo). Cambiar un descanso de semana cambia el estado del día
    para toda la plantilla, así que el caché debe caer o los empleados verían el dato viejo.
    """
    from core.services.cache_service import CacheService
    from empleados.models import Empleado as _Emp
    meses = meses or range(1, 13)
    for emp_id in _Emp.objects.filter(activo=True).values_list('id', flat=True):
        for mes in meses:
            CacheService.invalidar_cache_turnos_empleado(emp_id, mes, anio)


class _InvalidaCacheDescansoMixin:
    """Invalida el caché de turnos del mes afectado tras crear/editar/borrar un descanso."""

    def _invalidar_por_objeto(self, obj):
        if obj and obj.fecha:
            _invalidar_cache_turnos(obj.fecha.year, meses=[obj.fecha.month])


class DescansoSemanaListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = DescansoSemanaManual
    template_name = 'turnos/descanso_semana_list.html'
    context_object_name = 'descansos'

    def get_queryset(self):
        return DescansoSemanaManual.objects.select_related('jornada').order_by('-fecha', 'jornada__nombre')


class DescansoSemanaCreateView(LoginRequiredMixin, AdminRequiredMixin,
                               _InvalidaCacheDescansoMixin, CreateView):
    model = DescansoSemanaManual
    template_name = 'turnos/descanso_semana_form.html'
    fields = ['fecha', 'jornada', 'motivo', 'descripcion', 'activo']
    success_url = '/turnos/descanso-semana/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = 'Nuevo descanso de semana'
        return ctx

    def form_valid(self, form):
        resp = super().form_valid(form)
        self._invalidar_por_objeto(self.object)
        return resp


class DescansoSemanaUpdateView(LoginRequiredMixin, AdminRequiredMixin,
                               _InvalidaCacheDescansoMixin, UpdateView):
    model = DescansoSemanaManual
    template_name = 'turnos/descanso_semana_form.html'
    fields = ['fecha', 'jornada', 'motivo', 'descripcion', 'activo']
    success_url = '/turnos/descanso-semana/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = 'Editar descanso de semana'
        return ctx

    def form_valid(self, form):
        # La fecha puede cambiar de mes: hay que invalidar el mes viejo y el nuevo.
        anterior = self.get_object()
        fecha_anterior = anterior.fecha if anterior else None
        resp = super().form_valid(form)
        if fecha_anterior:
            _invalidar_cache_turnos(fecha_anterior.year, meses=[fecha_anterior.month])
        self._invalidar_por_objeto(self.object)
        return resp


class DescansoSemanaDeleteView(LoginRequiredMixin, AdminRequiredMixin,
                               _InvalidaCacheDescansoMixin, DeleteView):
    model = DescansoSemanaManual
    template_name = 'turnos/descanso_semana_confirm_delete.html'
    success_url = '/turnos/descanso-semana/'

    def form_valid(self, form):
        obj = self.get_object()
        resp = super().form_valid(form)
        self._invalidar_por_objeto(obj)
        return resp


class DescansoSemanaAnualView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Planeación ANUAL de los descansos de semana (estilo Días Especiales): 12 meses, el
    supervisor hace clic en cada día y asigna qué jornada descansa (AM/PM) en las semanas
    de temporada. Se guarda todo el año de una vez.
    """
    template_name = 'turnos/descanso_semana_anual.html'

    def _anio(self):
        anio = self.request.GET.get('anio')
        try:
            return int(anio)
        except (TypeError, ValueError):
            return timezone.localdate().year

    def get_context_data(self, **kwargs):
        import calendar as _cal
        from turnos.services.descanso_semana_service import DescansoSemanaService
        context = super().get_context_data(**kwargs)
        anio = self._anio()
        meses_nombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        cal = _cal.Calendar(firstweekday=0)  # lunes primero
        meses = []
        for m in range(1, 13):
            meses.append({
                'numero': m,
                'nombre': meses_nombres[m - 1],
                'semanas': cal.monthdatescalendar(anio, m),  # semanas de 7 fechas
            })
        # Marcadores de referencia: temporada / festivo / mantenimiento del año (solo informativo)
        from collections import defaultdict as _dd
        marcadores = _dd(list)
        for de in DiaEspecial.objects.filter(fecha__year=anio, activo=True):
            f = de.fecha.isoformat()
            if de.es_temporada:
                tag = 'temporada'
            elif de.tipo == 'festivo':
                tag = 'festivo'
            elif de.tipo == 'mantenimiento':
                tag = 'mantenimiento'
            else:
                continue
            if tag not in marcadores[f]:
                marcadores[f].append(tag)

        anio_actual = timezone.localdate().year
        bloqueadas = DescansoSemanaService.fechas_bloqueadas_por_solicitud(anio)
        context.update({
            'anio': anio,
            'anios_disponibles': list(range(anio_actual, anio_actual + 6)),
            'meses': meses,
            'preseleccion_json': DescansoSemanaService.descansos_anual(anio),
            'otros_motivos_json': DescansoSemanaService.descansos_anual_otros_motivos(anio),
            'marcadores_json': dict(marcadores),
            'bloqueadas_json': sorted(bloqueadas),
            'anio_editable_completo': len(bloqueadas) == 0,
        })
        return context

    def post(self, request, *args, **kwargs):
        from turnos.services.descanso_semana_service import (
            DescansoSemanaService, DescansoSemanaConflicto,
        )
        try:
            anio = int(request.POST.get('anio'))
        except (TypeError, ValueError):
            messages.error(request, _MSG_ANIO_INVALIDO)
            return redirect('descanso_semana_anual')
        anio_actual = timezone.localdate().year
        if not (anio_actual <= anio <= anio_actual + 5):
            messages.error(request, 'Año fuera del rango planificable.')
            return redirect('descanso_semana_anual')
        try:
            seleccion = json.loads(request.POST.get('seleccion', '{}'))
        except json.JSONDecodeError:
            seleccion = {}
        try:
            n = DescansoSemanaService.guardar_anual(anio, seleccion)
        except DescansoSemanaConflicto as e:
            messages.error(request, str(e))
            return redirect(f"{reverse('descanso_semana_anual')}?anio={anio}")
        # Invalidar caché de Mis Turnos para que todos los empleados vean el cambio inmediatamente
        _invalidar_cache_turnos(anio)
        messages.success(request, f'Programación de descansos guardada para {anio} ({n} día(s) asignados).')
        return redirect(f"{reverse('descanso_semana_anual')}?anio={anio}")


class AsignacionEspecialAnualView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Planeación ANUAL de la alternancia de días especiales (fines de semana y festivos).

    El supervisor SIEMBRA el año y ajusta a mano lo que quiera: qué grupo (AM/PM) TRABAJA
    el día completo cada sábado, domingo y festivo entre semana. Lo que aquí se guarda es
    la fuente de verdad — no hay cálculo automático detrás. Un día sin publicar sale como
    SIN PLANIFICAR, nunca como un turno inventado.
    """
    template_name = 'turnos/asignacion_especial_anual.html'

    def _anio(self):
        try:
            return int(self.request.GET.get('anio'))
        except (TypeError, ValueError):
            return timezone.localdate().year

    def get_context_data(self, **kwargs):
        import calendar as _cal
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        context = super().get_context_data(**kwargs)
        anio = self._anio()
        meses_nombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        cal = _cal.Calendar(firstweekday=0)
        meses = [{'numero': m, 'nombre': meses_nombres[m - 1], 'semanas': cal.monthdatescalendar(anio, m)}
                 for m in range(1, 13)]

        # Festivos del año, separados por dónde caen:
        # - entre semana → clickeables, tienen su propia alternancia.
        # - en fin de semana → solo se marcan; manda la alternancia del finde, no son un caso aparte.
        festivos_semana, festivos_finde = [], []
        for de in DiaEspecial.objects.filter(fecha__year=anio, tipo='festivo', activo=True):
            (festivos_semana if de.fecha.weekday() < 5 else festivos_finde).append(de.fecha.isoformat())

        bloqueadas = AsignacionEspecialService.fechas_bloqueadas_por_solicitud(anio)
        sin_planificar = AsignacionEspecialService.fechas_sin_planificar(anio)
        anio_actual = timezone.localdate().year
        context.update({
            'anio': anio,
            'anios_disponibles': list(range(anio_actual, anio_actual + 6)),
            'meses': meses,
            'preseleccion_json': AsignacionEspecialService.asignaciones_anual(anio),
            'festivos_json': festivos_semana,
            'festivos_finde_json': festivos_finde,
            'bloqueadas_json': sorted(bloqueadas),
            'anio_editable_completo': len(bloqueadas) == 0,
            # Días que aún no tienen alternancia publicada: el supervisor tiene que verlos.
            'sin_planificar_json': [f.isoformat() for f in sin_planificar],
            'total_sin_planificar': len(sin_planificar),
            # Grupos sugeridos, derivados del año anterior para no romper la continuidad.
            # None cuando el año previo no está sembrado: entonces se elige explícitamente.
            'sugerencia': AsignacionEspecialService.sugerencia_siembra(anio),
        })
        return context

    def post(self, request, *args, **kwargs):
        from turnos.services.asignacion_especial_service import (
            AsignacionEspecialService, AsignacionEspecialConflicto,
        )
        try:
            anio = int(request.POST.get('anio'))
        except (TypeError, ValueError):
            messages.error(request, _MSG_ANIO_INVALIDO)
            return redirect('asignacion_especial_anual')
        # Los años pasados no se reprograman: alterarían turnos ya trabajados.
        anio_actual = timezone.localdate().year
        if not (anio_actual <= anio <= anio_actual + 5):
            messages.error(request, 'Año fuera del rango planificable.')
            return redirect('asignacion_especial_anual')
        try:
            seleccion = json.loads(request.POST.get('seleccion', '{}'))
        except json.JSONDecodeError:
            seleccion = {}
        try:
            n = AsignacionEspecialService.guardar_anual(anio, seleccion)
        except AsignacionEspecialConflicto as e:
            messages.error(request, str(e))
            return redirect(f"{reverse('asignacion_especial_anual')}?anio={anio}")
        _invalidar_cache_turnos(anio)
        faltan = len(AsignacionEspecialService.fechas_sin_planificar(anio))
        if faltan:
            messages.warning(
                request,
                f'Guardado ({n} día(s)), pero quedan {faltan} día(s) sin alternancia publicada '
                f'en {anio}. Los exploradores los verán como "sin planificar" hasta completarlos.')
        else:
            messages.success(
                request, f'Alternancia de {anio} publicada completa ({n} día(s)).')
        return redirect(f"{reverse('asignacion_especial_anual')}?anio={anio}")


class AsignacionEspecialSiembraView(LoginRequiredMixin, AdminRequiredMixin, View):
    """
    Propuesta de siembra de un año: {fecha_iso: 'AM'|'PM'}.

    La regla vive en el servicio, no en el navegador. El JS solo pinta lo que llega y el
    supervisor sigue revisando y pulsando Guardar; nada se escribe desde aquí.
    """

    def get(self, request, *args, **kwargs):
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        try:
            anio = int(request.GET.get('anio'))
        except (TypeError, ValueError):
            return JsonResponse({'error': _MSG_ANIO_INVALIDO}, status=400)
        try:
            propuesta = AsignacionEspecialService.calcular_siembra(
                anio, request.GET.get('finde'), request.GET.get('festivo'))
        except ValueError as e:
            return JsonResponse({'error': str(e)}, status=400)
        return JsonResponse({'siembra': propuesta})


