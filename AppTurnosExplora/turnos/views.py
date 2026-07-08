from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from django.contrib import messages
from django.urls import reverse
from core.mixins import AdminRequiredMixin
from .models import Turno, DiaEspecial, AsignarJornadaExplorador, DescansoSemanaManual
from .forms import TemporadasAnualForm, DiasEspecialesAnualForm
from .services.temporada_service import TemporadaService
from .services.dia_especial_service import DiaEspecialService
from datetime import timedelta, date
from django.utils import timezone
import json

# Create your views here.

class MisTurnosView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/mis_turnos.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        if hasattr(self.request.user, 'empleado'):
            from .services.turno_context_service import TurnoContextService
            empleado = self.request.user.empleado
            context_data = TurnoContextService.get_context_data_for_mis_turnos_view(empleado)
            
            context.update({
                'empleado': empleado,
                'semana_actual': {
                    'inicio': context_data['inicio_semana'],
                    'fin': context_data['fin_semana']
                },
                'semana_turnos': context_data['turnos_semana'],
                'turnos_mes': list(context_data['turnos_mes'].values()),
                'turnos_mes_json_str': context_data['turnos_mes_json_str'],
                'asignaciones_activas': context_data['asignaciones_activas'],
                'fecha_actual': context_data['fecha_actual']
            })
        
        return context

class CambiosTurnoView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/placeholder.html'

class ConsolidadoHorasView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/consolidado_horas.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .services.consolidado_horas_service import ConsolidadoHorasService
        from empleados.models import Empleado

        user = self.request.user
        es_supervisor = ConsolidadoHorasService.es_supervisor(user)
        empleado_actual = getattr(user, 'empleado', None)

        objetivo = None
        if es_supervisor:
            # El supervisor elige a quién consultar (?explorador_id=...)
            context['exploradores'] = ConsolidadoHorasService.exploradores_disponibles()
            eid = self.request.GET.get('explorador_id')
            if eid:
                objetivo = Empleado.objects.filter(id=eid, activo=True).first()
            elif empleado_actual:
                # Por defecto, el propio supervisor (si también es explorador)
                objetivo = empleado_actual
        else:
            # Explorador: solo sus propios datos
            objetivo = empleado_actual

        context['es_supervisor'] = es_supervisor
        context['explorador_objetivo'] = objetivo
        context['explorador_id_sel'] = str(objetivo.id) if objetivo else ''
        if objetivo:
            context['consolidado'] = ConsolidadoHorasService.get_consolidado(objetivo)
        return context

# CRUD de Turnos
class TurnoListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Turno
    template_name = 'turnos/turnos_list.html'
    context_object_name = 'turnos'
    
    def get_queryset(self):
        # OPTIMIZACIÓN: Pre-cargar relaciones frecuentes
        return (
            Turno.objects
            .select_related('explorador', 'jornada', 'sala', 'explorador__user')
            .order_by('-fecha', 'explorador')
        )
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        turnos = context['turnos']
        
        # OPTIMIZACIÓN: Pre-cargar todas las jornadas display en consultas batch
        from turnos.services.turno_service import TurnoService
        from collections import defaultdict
        
        if not turnos:
            context['turnos'] = turnos
            return context
        
        # Obtener todas las fechas y exploradores únicos
        fechas_unicas = set(t.fecha for t in turnos)
        explorador_ids = set(t.explorador_id for t in turnos)
        
        # OPTIMIZACIÓN: Pre-cargar todos los turnos de todas las fechas relevantes
        # Esto evita consultas individuales en obtener_jornada_display
        from turnos.models import Turno
        from empleados.models import Empleado
        
        # Pre-cargar turnos para todas las fechas y exploradores
        turnos_precargados = (
            Turno.objects
            .filter(
                explorador_id__in=explorador_ids,
                fecha__in=fechas_unicas
            )
            .select_related('jornada', 'explorador')
            .order_by('fecha', 'explorador', 'jornada__nombre')
        )
        
        # Agrupar turnos por (explorador_id, fecha)
        turnos_por_explorador_fecha = defaultdict(list)
        for t in turnos_precargados:
            key = (t.explorador_id, t.fecha)
            turnos_por_explorador_fecha[key].append(t)
        
        # Pre-cargar exploradores
        exploradores = {
            e.id: e
            for e in Empleado.objects.filter(id__in=explorador_ids).select_related('supervisor')
        }
        
        # Cache de jornada_display por (explorador_id, fecha)
        display_cache = {}
        
        # Calcular jornada_display usando datos pre-cargados
        for turno in turnos:
            key = (turno.explorador_id, turno.fecha)
            if key not in display_cache:
                explorador = exploradores.get(turno.explorador_id)
                if explorador:
                    # Usar método optimizado que puede usar datos pre-cargados
                    jornada_display = TurnoService.obtener_jornada_display(explorador, turno.fecha)
                    display_cache[key] = jornada_display
                else:
                    display_cache[key] = turno.jornada.nombre if turno.jornada else None
            
            # Agregar atributo temporal para el template
            turno.jornada_display = display_cache[key]
        
        context['turnos'] = turnos
        return context

class TurnoCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Turno
    template_name = 'turnos/turnos_create.html'
    fields = ['explorador', 'fecha', 'jornada', 'sala', 'tipo_cambio']
    success_url = '/turnos/lista/'

class TurnoUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Turno
    template_name = 'turnos/turnos_edit.html'
    fields = ['explorador', 'fecha', 'jornada', 'sala', 'tipo_cambio']
    success_url = '/turnos/lista/'

class TurnoDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Turno
    template_name = 'turnos/turnos_confirm_delete.html'
    success_url = '/turnos/lista/'

class DiasEspecialesView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/diasespeciales_list.html'

# CRUD de Días Especiales
class DiaEspecialListView(LoginRequiredMixin, ListView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_list.html'
    context_object_name = 'dias_especiales'
    paginate_by = 40

    def _anio_efectivo(self):
        from django.utils import timezone
        raw = self.request.GET.get('anio', '')
        if raw == 'todos':
            return None
        try:
            return int(raw)
        except (ValueError, TypeError):
            return timezone.now().year

    def get_queryset(self):
        qs = DiaEspecial.objects.all()
        tipo = self.request.GET.get('tipo', '')
        if tipo == 'temporada':
            qs = qs.filter(es_temporada=True)
        elif tipo == 'festivo':
            qs = qs.filter(tipo='festivo', es_temporada=False)
        elif tipo == 'mantenimiento':
            qs = qs.filter(tipo='mantenimiento', es_temporada=False)
        anio = self._anio_efectivo()
        if anio:
            qs = qs.filter(año_planificacion=anio)
        return qs.order_by('fecha')

    def get_context_data(self, **kwargs):
        from django.utils import timezone
        context = super().get_context_data(**kwargs)
        anio_efectivo = self._anio_efectivo()
        context['tipo_filtro'] = self.request.GET.get('tipo', '')
        context['anio_filtro'] = str(anio_efectivo) if anio_efectivo else 'todos'
        context['anio_actual'] = timezone.now().year
        context['anios_disponibles'] = TemporadaService.obtener_anios_con_temporadas()
        params = self.request.GET.copy()
        params.pop('page', None)
        context['query_params'] = params.urlencode()
        return context

class DiaEspecialCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_create.html'
    fields = ['fecha', 'tipo', 'descripcion', 'recurrente', 'activo']
    success_url = '/turnos/dias-especiales-admin/'

class DiaEspecialUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_edit.html'
    fields = ['fecha', 'tipo', 'descripcion', 'recurrente', 'activo']
    success_url = '/turnos/dias-especiales-admin/'

class DiaEspecialDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_confirm_delete.html'
    success_url = '/turnos/dias-especiales-admin/'

# ---------------------------------------------------------------------------
# Descanso de semana (manual) — para semanas con temporada/festivo
# ---------------------------------------------------------------------------
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
                pass

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


class TurnosCalendarioView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    template_name = 'turnos/turnos_calendario.html'


# Vista solo visualización para Consultas Rápidas
class DiaEspecialVisualizarListView(LoginRequiredMixin, ListView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_visualizar_list.html'
    context_object_name = 'dias_especiales'
    paginate_by = 40

    def _anio_efectivo(self):
        """Año del filtro; si no viene en GET usa el año actual."""
        from django.utils import timezone
        raw = self.request.GET.get('anio', '')
        if raw == 'todos':
            return None
        try:
            return int(raw)
        except (ValueError, TypeError):
            return timezone.now().year

    def get_queryset(self):
        queryset = DiaEspecial.objects.all()
        tipo = self.request.GET.get('tipo', '')
        es_supervisor = self.request.user.is_staff

        if tipo == 'temporada':
            queryset = queryset.filter(es_temporada=True)
        elif tipo == 'festivo':
            queryset = queryset.filter(tipo='festivo', es_temporada=False)
        elif tipo == 'mantenimiento':
            queryset = queryset.filter(tipo='mantenimiento', es_temporada=False)

        anio = self._anio_efectivo()
        if anio:
            queryset = queryset.filter(año_planificacion=anio)

        # Filtro activo: supervisores pueden ver inactivos; exploradores solo ven activos
        if es_supervisor:
            activo = self.request.GET.get('activo', '')
            if activo == '1':
                queryset = queryset.filter(activo=True)
            elif activo == '0':
                queryset = queryset.filter(activo=False)
        else:
            queryset = queryset.filter(activo=True)

        return queryset.order_by('fecha')

    def get_context_data(self, **kwargs):
        from django.utils import timezone
        context = super().get_context_data(**kwargs)
        anio_efectivo = self._anio_efectivo()
        context['tipo_filtro'] = self.request.GET.get('tipo', '')
        context['anio_filtro'] = str(anio_efectivo) if anio_efectivo else 'todos'
        context['anio_efectivo'] = anio_efectivo
        context['anio_actual'] = timezone.now().year
        context['anios_disponibles'] = TemporadaService.obtener_anios_con_temporadas()
        context['es_supervisor'] = self.request.user.is_staff
        context['activo_filtro'] = self.request.GET.get('activo', '')
        params = self.request.GET.copy()
        params.pop('page', None)
        context['query_params'] = params.urlencode()
        return context


class DiaEspecialTemporadasAnualView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Vista para gestionar temporadas anuales.
    Permite seleccionar días de temporada por mes para un año específico.
    """
    template_name = 'turnos/diasespeciales_temporadas_anual.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Obtener año del request o usar año siguiente por defecto
        anio_seleccionado = self.request.GET.get('anio')
        if anio_seleccionado:
            try:
                anio_seleccionado = int(anio_seleccionado)
            except ValueError:
                anio_seleccionado = None
        
        if not anio_seleccionado:
            anio_seleccionado = date.today().year + 1
        
        # Obtener días de temporada existentes para el año seleccionado
        dias_por_mes = TemporadaService.obtener_dias_temporada_por_mes(anio_seleccionado)
        tiene_temporadas = TemporadaService.tiene_temporadas_anio(anio_seleccionado)
        
        # Obtener años con temporadas configuradas
        anios_con_temporadas = TemporadaService.obtener_anios_con_temporadas()
        
        # Generar lista de años disponibles para el selector
        # Incluir desde el año actual hasta 10 años en el futuro (rango amplio para planificación)
        anio_actual = date.today().year
        anios_disponibles = list(range(anio_actual, anio_actual + 11))  # Año actual + 10 años más
        
        # Agregar años que ya tienen temporadas pero que no están en el rango
        for anio_temp in anios_con_temporadas:
            if anio_temp not in anios_disponibles and anio_temp >= 2000:
                anios_disponibles.append(anio_temp)
        
        # Ordenar años disponibles
        anios_disponibles = sorted(set(anios_disponibles))
        
        # Preparar datos para el template
        meses_nombres = [
            'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ]
        
        meses_data = []
        for mes in range(1, 13):
            dias_mes = dias_por_mes.get(mes, [])
            meses_data.append({
                'numero': mes,
                'nombre': meses_nombres[mes - 1],
                'dias_seleccionados': dias_mes,
                'total_dias': len(dias_mes)
            })
        
        context.update({
            'anio_seleccionado': anio_seleccionado,
            'anio_actual': anio_actual,
            'tiene_temporadas': tiene_temporadas,
            'dias_por_mes': json.dumps(dias_por_mes),  # Serializar a JSON para JavaScript
            'meses_data': meses_data,
            'anios_con_temporadas': anios_con_temporadas,  # Para referencia
            'anios_disponibles': anios_disponibles,  # Lista completa de años para el selector
            'form': TemporadasAnualForm(initial={'anio': anio_seleccionado})
        })
        
        return context
    
    def post(self, request, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)
        
        # Debug: Log de lo que viene en el POST
        logger.info(f"POST data recibido: {request.POST}")
        logger.info(f"dias_seleccionados recibido: {request.POST.get('dias_seleccionados', 'NO HAY')}")
        logger.info(f"anio recibido: {request.POST.get('anio', 'NO HAY')}")
        
        form = TemporadasAnualForm(request.POST)
        
        if form.is_valid():
            anio = form.cleaned_data['anio']
            dias_seleccionados = form.cleaned_data.get('dias_seleccionados', {})
            
            logger.info(f"Formulario válido. Año: {anio}, Días seleccionados: {dias_seleccionados}")
            
            # Guardar temporadas
            exito, mensaje = TemporadaService.guardar_temporadas_anual(
                anio=anio,
                dias_seleccionados=dias_seleccionados,
                usuario=request.user
            )
            
            logger.info(f"Resultado guardar temporadas: éxito={exito}, mensaje={mensaje}")
            
            if exito:
                messages.success(request, mensaje)
                return redirect(f"{reverse('dias_especiales_temporadas_anual')}?anio={anio}")
            else:
                messages.error(request, mensaje)
        else:
            logger.error(f"Formulario inválido. Errores: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
        
        # Si hay errores, volver a mostrar el formulario
        context = self.get_context_data()
        context['form'] = form
        return render(request, self.template_name, context)


class DiaEspecialFestivosMantenimientoAnualView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Vista para gestionar días especiales anuales (festivos y mantenimiento).
    Permite seleccionar días por mes para un año específico.
    """
    template_name = 'turnos/diasespeciales_festivos_mantenimiento_anual.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Obtener tipo del request o usar 'festivo' por defecto
        tipo_seleccionado = self.request.GET.get('tipo', 'festivo')
        if tipo_seleccionado not in ['festivo', 'mantenimiento']:
            tipo_seleccionado = 'festivo'
        
        # Obtener año del request o usar año siguiente por defecto
        anio_seleccionado = self.request.GET.get('anio')
        if anio_seleccionado:
            try:
                anio_seleccionado = int(anio_seleccionado)
            except ValueError:
                anio_seleccionado = None
        
        if not anio_seleccionado:
            anio_seleccionado = date.today().year + 1
        
        # Obtener días existentes para el tipo y año seleccionados
        dias_por_mes = DiaEspecialService.obtener_dias_por_tipo_por_mes(tipo_seleccionado, anio_seleccionado)
        tiene_dias = DiaEspecialService.tiene_dias_tipo_anio(tipo_seleccionado, anio_seleccionado)
        
        # Si es mantenimiento y no hay días guardados, calcular automáticamente
        if tipo_seleccionado == 'mantenimiento' and not tiene_dias:
            dias_por_mes = DiaEspecialService.calcular_dias_mantenimiento_automatico(anio_seleccionado)

        # Si es festivo y no hay días guardados, generar festivos automáticos
        if tipo_seleccionado == 'festivo' and not tiene_dias:
            dias_por_mes = DiaEspecialService.generar_festivos_automaticos(anio_seleccionado)
        
        # Obtener festivos y temporadas para mostrar en el calendario (para todos los tipos)
        festivos_por_mes = DiaEspecialService.obtener_dias_por_tipo_por_mes('festivo', anio_seleccionado)
        temporadas_por_mes = TemporadaService.obtener_dias_temporada_por_mes(anio_seleccionado)
        
        # Obtener años con días del tipo configurados
        anios_con_tipo = DiaEspecialService.obtener_anios_con_tipo(tipo_seleccionado)
        
        # Generar lista de años disponibles para el selector
        # Incluir desde el año actual hasta 50 años en el futuro (rango amplio para planificación a largo plazo)
        anio_actual = date.today().year
        anios_disponibles = list(range(anio_actual, anio_actual + 51))  # Año actual + 50 años más
        
        # Agregar años que ya tienen días del tipo pero que no están en el rango
        # Solo agregar años válidos (>= 2000)
        for anio_temp in anios_con_tipo:
            if anio_temp is not None and anio_temp not in anios_disponibles and anio_temp >= 2000:
                anios_disponibles.append(anio_temp)
        
        # Filtrar y ordenar años disponibles (solo mínimo 2000)
        anios_disponibles = sorted(set([a for a in anios_disponibles if a >= 2000]))
        
        # Preparar datos para el template
        meses_nombres = [
            'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
            'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
        ]
        
        meses_data = []
        for mes in range(1, 13):
            dias_mes = dias_por_mes.get(mes, [])
            meses_data.append({
                'numero': mes,
                'nombre': meses_nombres[mes - 1],
                'dias_seleccionados': dias_mes,
                'total_dias': len(dias_mes)
            })
        
        context.update({
            'tipo_seleccionado': tipo_seleccionado,
            'anio_seleccionado': anio_seleccionado,
            'anio_actual': anio_actual,
            'tiene_dias': tiene_dias,
            'dias_por_mes': dias_por_mes,
            'festivos_por_mes': festivos_por_mes,
            'temporadas_por_mes': temporadas_por_mes,
            'meses_data': meses_data,
            'anios_con_tipo': anios_con_tipo,  # Para referencia
            'anios_disponibles': anios_disponibles,  # Lista completa de años para el selector
            'form': DiasEspecialesAnualForm(initial={
                'tipo': tipo_seleccionado,
                'anio': anio_seleccionado
            })
        })
        
        return context
    
    def post(self, request, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)
        
        # Debug: Log de lo que viene en el POST
        logger.info(f"POST data recibido: {request.POST}")
        logger.info(f"dias_seleccionados recibido: {request.POST.get('dias_seleccionados', 'NO HAY')}")
        logger.info(f"tipo recibido: {request.POST.get('tipo', 'NO HAY')}")
        logger.info(f"anio recibido: {request.POST.get('anio', 'NO HAY')}")
        
        form = DiasEspecialesAnualForm(request.POST)
        
        if form.is_valid():
            tipo = form.cleaned_data['tipo']
            anio = form.cleaned_data['anio']
            dias_seleccionados = form.cleaned_data.get('dias_seleccionados', {})
            
            logger.info(f"Formulario válido. Tipo: {tipo}, Año: {anio}, Días seleccionados: {dias_seleccionados}")
            
            # Guardar días especiales
            exito, mensaje = DiaEspecialService.guardar_dias_especiales_anual(
                tipo=tipo,
                anio=anio,
                dias_seleccionados=dias_seleccionados,
                usuario=request.user
            )
            
            logger.info(f"Resultado guardar días especiales: éxito={exito}, mensaje={mensaje}")
            
            if exito:
                messages.success(request, mensaje)
                return redirect(f"{reverse('dias_especiales_festivos_mantenimiento_anual')}?tipo={tipo}&anio={anio}")
            else:
                messages.error(request, mensaje)
        else:
            logger.error(f"Formulario inválido. Errores: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
        
        # Si hay errores, volver a mostrar el formulario
        context = self.get_context_data()
        context['form'] = form
        return render(request, self.template_name, context)
