from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import ListView, TemplateView, UpdateView

from core.mixins import AdminRequiredMixin, es_supervisor

from ..forms import DiasEspecialesAnualForm, TemporadasAnualForm
from ..models import DiaEspecial
from ..services.dia_especial_service import DiaEspecialService
from ..services.temporada_service import TemporadaService

# Create your views here.


def _anios_con_dias_especiales():
    """
    Años que tienen algún día especial registrado, de cualquier tipo.

    Se deriva de `fecha`, no de `año_planificacion`, y cubre los tres tipos: un año
    con solo festivos también debe poder elegirse en el filtro.
    """
    anios = DiaEspecial.objects.dates('fecha', 'year')
    return sorted({d.year for d in anios}, reverse=True)


def _anio_valido(anio):
    """True si el año está dentro del rango que la app acepta gestionar."""
    return anio is not None and DiaEspecial.ANIO_MIN <= anio <= DiaEspecial.ANIO_MAX


class DiaEspecialListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
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
        context['anios_disponibles'] = _anios_con_dias_especiales()
        context['es_supervisor'] = es_supervisor(self.request.user)
        params = self.request.GET.copy()
        params.pop('page', None)
        context['query_params'] = params.urlencode()
        return context

class DiaEspecialUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = DiaEspecial
    template_name = 'turnos/diasespeciales_edit.html'
    fields = ['fecha', 'tipo', 'descripcion', 'recurrente', 'activo']
    success_url = '/turnos/dias-especiales-admin/'

# El listado admin NO da de alta ni de baja días especiales. Eso se hace desde las
# páginas anuales, donde se ve el año completo y el guardado está protegido contra
# ediciones concurrentes. Aquí solo se edita un día existente (incluido su `activo`,
# con la advertencia correspondiente en el formulario).

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
        # Mismo criterio que `AdminRequiredMixin`: los supervisores sin `is_staff`
        # también tienen visibilidad ampliada.
        puede_ver_inactivos = es_supervisor(self.request.user)

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
        if puede_ver_inactivos:
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
        context['anios_disponibles'] = _anios_con_dias_especiales()
        context['es_supervisor'] = es_supervisor(self.request.user)
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
        
        # Obtener año del request o usar año siguiente por defecto.
        # Un año fuera de rango se descarta en lugar de propagarse: los servicios de
        # cálculo lanzan ValueError y la vista respondería 500.
        anio_seleccionado = self.request.GET.get('anio')
        if anio_seleccionado:
            try:
                anio_seleccionado = int(anio_seleccionado)
            except ValueError:
                anio_seleccionado = None
            if not _anio_valido(anio_seleccionado):
                messages.warning(
                    self.request,
                    f"Año fuera del rango permitido ({DiaEspecial.ANIO_MIN}-{DiaEspecial.ANIO_MAX}); se muestra el año por defecto."
                )
                anio_seleccionado = None

        if not anio_seleccionado:
            anio_seleccionado = timezone.localdate().year + 1

        # Obtener días de temporada existentes para el año seleccionado
        dias_por_mes = TemporadaService.obtener_dias_temporada_por_mes(anio_seleccionado)
        tiene_temporadas = TemporadaService.tiene_temporadas_anio(anio_seleccionado)
        
        # Obtener años con temporadas configuradas
        anios_con_temporadas = TemporadaService.obtener_anios_con_temporadas()
        
        # Generar lista de años disponibles para el selector
        # Incluir desde el año actual hasta 10 años en el futuro (rango amplio para planificación)
        anio_actual = timezone.localdate().year
        anios_disponibles = list(range(anio_actual, anio_actual + 11))  # Año actual + 10 años más

        # Agregar años que ya tienen temporadas pero que no están en el rango
        for anio_temp in anios_con_temporadas:
            if anio_temp not in anios_disponibles:
                anios_disponibles.append(anio_temp)

        # Ordenar y descartar los que la app no acepta gestionar
        anios_disponibles = sorted({a for a in anios_disponibles if _anio_valido(a)})
        
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
            'anio_min': DiaEspecial.ANIO_MIN,
            'anio_max': DiaEspecial.ANIO_MAX,
            'token_estado': TemporadaService.token_estado(anio_seleccionado),
            'form': TemporadasAnualForm(initial={'anio': anio_seleccionado})
        })
        
        return context
    
    def post(self, request, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)

        form = TemporadasAnualForm(request.POST)

        if form.is_valid():
            anio = form.cleaned_data['anio']
            dias_seleccionados = form.cleaned_data.get('dias_seleccionados', {})
            # Sin este flag explícito, una selección vacía se rechaza. Con él, el admin
            # puede dejar un año deliberadamente sin temporadas (el front lo confirma).
            limpiar = request.POST.get('limpiar_anio') == '1'

            logger.info(f"Guardando temporadas. Año: {anio}, meses con días: {sorted(dias_seleccionados)}, limpiar={limpiar}")

            # Guardar temporadas
            exito, mensaje = TemporadaService.guardar_temporadas_anual(
                anio=anio,
                dias_seleccionados=dias_seleccionados,
                usuario=request.user,
                permitir_vacio=limpiar,
                token_esperado=form.cleaned_data.get('token_estado') or None
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
        
        # Obtener año del request o usar año siguiente por defecto.
        # Un año fuera de rango se descarta en lugar de propagarse: `calcular_festivos_automaticos`
        # lanza ValueError y la vista respondería 500.
        anio_seleccionado = self.request.GET.get('anio')
        if anio_seleccionado:
            try:
                anio_seleccionado = int(anio_seleccionado)
            except ValueError:
                anio_seleccionado = None
            if not _anio_valido(anio_seleccionado):
                messages.warning(
                    self.request,
                    f"Año fuera del rango permitido ({DiaEspecial.ANIO_MIN}-{DiaEspecial.ANIO_MAX}); se muestra el año por defecto."
                )
                anio_seleccionado = None

        if not anio_seleccionado:
            anio_seleccionado = timezone.localdate().year + 1

        # Obtener días existentes para el tipo y año seleccionados
        dias_por_mes = DiaEspecialService.obtener_dias_por_tipo_por_mes(tipo_seleccionado, anio_seleccionado)
        tiene_dias = DiaEspecialService.tiene_dias_tipo_anio(tipo_seleccionado, anio_seleccionado)
        
        # Si es mantenimiento y no hay días guardados, calcular automáticamente
        if tipo_seleccionado == 'mantenimiento' and not tiene_dias:
            dias_por_mes = DiaEspecialService.calcular_dias_mantenimiento_automatico(anio_seleccionado)

        # Si es festivo y no hay días guardados, calcular festivos para previsualizar
        # (NO se persisten hasta que el admin guarde, igual que temporada/mantenimiento).
        if tipo_seleccionado == 'festivo' and not tiene_dias:
            dias_por_mes = DiaEspecialService.calcular_festivos_automaticos(anio_seleccionado)
        
        # Obtener festivos y temporadas para mostrar en el calendario (para todos los tipos)
        festivos_por_mes = DiaEspecialService.obtener_dias_por_tipo_por_mes('festivo', anio_seleccionado)
        temporadas_por_mes = TemporadaService.obtener_dias_temporada_por_mes(anio_seleccionado)

        # Si el año aún no tiene festivos guardados, el calendario muestra los calculados.
        # Es la misma base que usa el cálculo de mantenimiento, así que lo que se pinta
        # coincide con la propuesta; se avisa en la plantilla que son estimados.
        festivos_son_estimados = not festivos_por_mes
        if festivos_son_estimados:
            festivos_por_mes = DiaEspecialService.calcular_festivos_automaticos(anio_seleccionado)

        # Obtener años con días del tipo configurados
        anios_con_tipo = DiaEspecialService.obtener_anios_con_tipo(tipo_seleccionado)
        
        # Generar lista de años disponibles para el selector.
        # Ventana corta (año actual + 3): los festivos/mantenimiento se generan por año
        # cuando se necesitan, no con décadas de anticipación.
        anio_actual = timezone.localdate().year
        anios_disponibles = list(range(anio_actual, anio_actual + 4))  # Año actual + 3 años más

        # Agregar años que ya tienen días del tipo pero que no están en el rango
        for anio_temp in anios_con_tipo:
            if anio_temp is not None and anio_temp not in anios_disponibles:
                anios_disponibles.append(anio_temp)

        # Ordenar y descartar los que la app no acepta gestionar
        anios_disponibles = sorted({a for a in anios_disponibles if _anio_valido(a)})
        
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
            'festivos_son_estimados': festivos_son_estimados,
            'temporadas_por_mes': temporadas_por_mes,
            'meses_data': meses_data,
            'anios_con_tipo': anios_con_tipo,  # Para referencia
            'anios_disponibles': anios_disponibles,  # Lista completa de años para el selector
            'anio_min': DiaEspecial.ANIO_MIN,
            'anio_max': DiaEspecial.ANIO_MAX,
            'token_estado': DiaEspecialService.token_estado(tipo_seleccionado, anio_seleccionado),
            'form': DiasEspecialesAnualForm(initial={
                'tipo': tipo_seleccionado,
                'anio': anio_seleccionado
            })
        })
        
        return context
    
    def post(self, request, *args, **kwargs):
        import logging
        logger = logging.getLogger(__name__)

        form = DiasEspecialesAnualForm(request.POST)

        if form.is_valid():
            tipo = form.cleaned_data['tipo']
            anio = form.cleaned_data['anio']
            dias_seleccionados = form.cleaned_data.get('dias_seleccionados', {})
            # Sin este flag explícito, una selección vacía se rechaza. Con él, el admin
            # puede dejar un año deliberadamente sin días de ese tipo (el front lo confirma).
            limpiar = request.POST.get('limpiar_anio') == '1'

            logger.info(f"Guardando días especiales. Tipo: {tipo}, Año: {anio}, meses con días: {sorted(dias_seleccionados)}, limpiar={limpiar}")

            # Guardar días especiales
            exito, mensaje = DiaEspecialService.guardar_dias_especiales_anual(
                tipo=tipo,
                anio=anio,
                dias_seleccionados=dias_seleccionados,
                usuario=request.user,
                permitir_vacio=limpiar,
                token_esperado=form.cleaned_data.get('token_estado') or None
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
