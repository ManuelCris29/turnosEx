from django.shortcuts import render, redirect
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.db.models import Q
from django.contrib import messages
from django.urls import reverse
from core.mixins import AdminRequiredMixin
from .models import Turno, DiaEspecial, AsignarSalaExplorador, AsignarJornadaExplorador
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
    
    def get_queryset(self):
        # OPTIMIZACIÓN: Ordenar por fecha
        return DiaEspecial.objects.order_by('fecha')

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

class TurnosCalendarioView(LoginRequiredMixin, TemplateView):
    template_name = 'turnos/turnos_calendario.html'


# Vista solo visualización para Consultas Rápidas
class DiaEspecialVisualizarListView(LoginRequiredMixin, ListView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_visualizar_list.html'
    context_object_name = 'dias_especiales'
    
    def get_queryset(self):
        # OPTIMIZACIÓN: Aplicar filtros directamente en la consulta
        queryset = DiaEspecial.objects.all()
        tipo = self.request.GET.get('tipo')
        anio = self.request.GET.get('anio')
        
        if tipo:
            if tipo == 'temporada':
                queryset = queryset.filter(es_temporada=True)
            elif tipo == 'festivo':
                queryset = queryset.filter(tipo='festivo', es_temporada=False)
            elif tipo == 'mantenimiento':
                queryset = queryset.filter(tipo='mantenimiento', es_temporada=False)
        
        if anio:
            try:
                anio_int = int(anio)
                queryset = queryset.filter(año_planificacion=anio_int)
            except ValueError:
                pass
        
        return queryset.order_by('fecha')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tipo_filtro'] = self.request.GET.get('tipo', '')
        context['anio_filtro'] = self.request.GET.get('anio', '')
        context['anios_disponibles'] = TemporadaService.obtener_anios_con_temporadas()
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
            'dias_por_mes': json.dumps(dias_por_mes),  # Serializar a JSON para JavaScript
            'festivos_por_mes': json.dumps(festivos_por_mes),  # Festivos para mostrar en el calendario
            'temporadas_por_mes': json.dumps(temporadas_por_mes),  # Temporadas para mostrar en el calendario
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
