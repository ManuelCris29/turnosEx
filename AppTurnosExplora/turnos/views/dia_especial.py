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

# Create your views here.

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
            'dias_por_mes': dias_por_mes,  # dict crudo; el template lo serializa con json_script (XSS-safe)
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
