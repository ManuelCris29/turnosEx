import logging
from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from django.contrib import messages
from django.urls import reverse
from core.mixins import AdminRequiredMixin
from ..models import Turno, DiaEspecial, AsignarJornadaExplorador, DescansoSemanaManual
from ..forms import TemporadasAnualForm, DiasEspecialesAnualForm
from ..services.temporada_service import TemporadaService
from ..services.dia_especial_service import DiaEspecialService
from datetime import timedelta, date
from django.utils import timezone
import json

logger = logging.getLogger(__name__)

# Create your views here.

class DescansoSemanaListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = DescansoSemanaManual
    template_name = 'turnos/descanso_semana_list.html'
    context_object_name = 'descansos'

    def get_queryset(self):
        return DescansoSemanaManual.objects.select_related('jornada').order_by('-fecha', 'jornada__nombre')


class DescansoSemanaCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = DescansoSemanaManual
    template_name = 'turnos/descanso_semana_form.html'
    fields = ['fecha', 'jornada', 'motivo', 'descripcion', 'activo']
    success_url = '/turnos/descanso-semana/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = 'Nuevo descanso de semana'
        return ctx


class DescansoSemanaUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = DescansoSemanaManual
    template_name = 'turnos/descanso_semana_form.html'
    fields = ['fecha', 'jornada', 'motivo', 'descripcion', 'activo']
    success_url = '/turnos/descanso-semana/'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['titulo'] = 'Editar descanso de semana'
        return ctx


class DescansoSemanaDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = DescansoSemanaManual
    template_name = 'turnos/descanso_semana_confirm_delete.html'
    success_url = '/turnos/descanso-semana/'


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
            return date.today().year

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

        anio_actual = date.today().year
        context.update({
            'anio': anio,
            'anios_disponibles': list(range(anio_actual, anio_actual + 6)),
            'meses': meses,
            'preseleccion_json': DescansoSemanaService.descansos_anual(anio),
            'marcadores_json': dict(marcadores),
        })
        return context

    def post(self, request, *args, **kwargs):
        from turnos.services.descanso_semana_service import DescansoSemanaService
        try:
            anio = int(request.POST.get('anio'))
        except (TypeError, ValueError):
            messages.error(request, 'Año inválido.')
            return redirect('descanso_semana_anual')
        try:
            seleccion = json.loads(request.POST.get('seleccion', '{}'))
        except json.JSONDecodeError:
            seleccion = {}
        n = DescansoSemanaService.guardar_anual(anio, seleccion)
        # Invalidar caché de Mis Turnos para que todos los empleados vean el cambio inmediatamente
        from core.services.cache_service import CacheService
        from empleados.models import Empleado as _Emp
        empleados_ids = list(_Emp.objects.filter(activo=True).values_list('id', flat=True))
        for emp_id in empleados_ids:
            for mes in range(1, 13):
                CacheService.invalidar_cache_turnos_empleado(emp_id, mes, anio)
        messages.success(request, f'Programación de descansos guardada para {anio} ({n} día(s) asignados).')
        return redirect(f"{reverse('descanso_semana_anual')}?anio={anio}")


class AsignacionEspecialAnualView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Planeación ANUAL del OVERRIDE manual de días especiales (fines de semana y festivos):
    el supervisor hace clic en un sábado/domingo o un festivo entre semana y fija qué grupo
    (AM/PM) TRABAJA el día completo. Sin override, sigue la alternancia/rotación automática.
    Clic repetido cambia: automático → AM trabaja → PM trabaja → automático.
    """
    template_name = 'turnos/asignacion_especial_anual.html'

    def _anio(self):
        try:
            return int(self.request.GET.get('anio'))
        except (TypeError, ValueError):
            return date.today().year

    def get_context_data(self, **kwargs):
        import calendar as _cal
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        from turnos.services.alternancia_fines_semana_service import (
            AlternanciaFinesSemanaService, FECHA_REFERENCIA_SABADO, JORNADA_REFERENCIA_SABADO,
        )
        from turnos.services.festivos_rotacion_service import FestivosRotacionService
        context = super().get_context_data(**kwargs)
        anio = self._anio()
        meses_nombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
        cal = _cal.Calendar(firstweekday=0)
        meses = [{'numero': m, 'nombre': meses_nombres[m - 1], 'semanas': cal.monthdatescalendar(anio, m)}
                 for m in range(1, 13)]

        # Festivos entre semana del año (clickeables además de los fines de semana)
        festivos_semana = [
            de.fecha.isoformat()
            for de in DiaEspecial.objects.filter(fecha__year=anio, tipo='festivo', activo=True)
            if de.fecha.weekday() < 5
        ]

        # Default AUTOMÁTICO por fecha especial (pista visual de qué pasa sin override)
        auto = {}
        d = date(anio, 1, 1)
        fin = date(anio, 12, 31)
        while d <= fin:
            if d.weekday() >= 5:
                g = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(d)
                if g:
                    auto[d.isoformat()] = g
            d += timedelta(days=1)
        for iso in festivos_semana:
            try:
                g = FestivosRotacionService.get_grupo_que_dobla_en_festivo(date.fromisoformat(iso))
                auto[iso] = g
            except Exception:
                logger.warning("Error obteniendo grupo que dobla en festivo (fecha=%s)", iso, exc_info=True)

        bloqueadas = AsignacionEspecialService.fechas_bloqueadas_por_solicitud(anio)
        anio_actual = date.today().year
        ancla_sabado = JORNADA_REFERENCIA_SABADO.upper()
        context.update({
            'anio': anio,
            'anios_disponibles': list(range(anio_actual, anio_actual + 6)),
            'meses': meses,
            'preseleccion_json': AsignacionEspecialService.asignaciones_anual(anio),
            'festivos_json': festivos_semana,
            'auto_json': auto,
            'bloqueadas_json': sorted(bloqueadas),
            'anio_editable_completo': len(bloqueadas) == 0,
            # Ancla de la alternancia automática (para la nota informativa). Se lee de las
            # constantes del servicio para que la nota nunca quede desactualizada.
            'ancla_fecha': FECHA_REFERENCIA_SABADO,
            'ancla_jornada_sabado': ancla_sabado,
            'ancla_jornada_domingo': 'AM' if ancla_sabado == 'PM' else 'PM',
        })
        return context

    def post(self, request, *args, **kwargs):
        from turnos.services.asignacion_especial_service import (
            AsignacionEspecialService, AsignacionEspecialConflicto,
        )
        try:
            anio = int(request.POST.get('anio'))
        except (TypeError, ValueError):
            messages.error(request, 'Año inválido.')
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
        from core.services.cache_service import CacheService
        from empleados.models import Empleado as _Emp
        for emp_id in _Emp.objects.filter(activo=True).values_list('id', flat=True):
            for mes in range(1, 13):
                CacheService.invalidar_cache_turnos_empleado(emp_id, mes, anio)
        messages.success(request, f'Asignaciones especiales guardadas para {anio} ({n} día(s) fijados).')
        return redirect(f"{reverse('asignacion_especial_anual')}?anio={anio}")


