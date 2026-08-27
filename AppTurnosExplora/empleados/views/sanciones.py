import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.generic import ListView, TemplateView, UpdateView
from django.views.generic.edit import CreateView, FormView

from core.mixins import AdminRequiredMixin, es_supervisor

from ..forms import SancionEmpleadoForm, SancionLevantarForm
from ..models import Empleado, SancionEmpleado

logger = logging.getLogger(__name__)


def _id_valido(valor):
    """Devuelve el id como int solo si el parámetro es un entero; si no, None."""
    return int(valor) if valor and str(valor).isdigit() else None


def _estados_sancion():
    """
    Los tres estados posibles, como filtros de BD. Están aquí y no repartidos por las
    vistas para que los totales y la lista filtrada no puedan discrepar: son el mismo
    criterio evaluado dos veces.

    - activa:     sigue contando (vigente hoy o programada para empezar más adelante).
                  Incluir las futuras es deliberado: una sanción que empieza mañana no
                  está ni terminada ni levantada, y dejarla fuera de los tres totales la
                  haría desaparecer del resumen.
    - levantada:  terminada a mano o por pago antes de su fecha de fin.
    - finalizada: llegó a su fecha de fin sin que nadie la levantara.

    Ojo: 'activa' aquí es para MOSTRAR. Quien decide si alguien está bloqueado es
    siempre `sancion_activa()`; no sustituyas una por la otra.
    """
    from django.db.models import Q
    return {
        'activa': lambda hoy: (
            Q(levantada_en__isnull=True) & (Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy))
        ),
        'levantada': lambda hoy: Q(levantada_en__isnull=False),
        'finalizada': lambda hoy: Q(levantada_en__isnull=True) & Q(fecha_fin__lt=hoy),
    }


_FILTROS_ESTADO = _estados_sancion()


# CRUD de Sanciones
class SancionListView(LoginRequiredMixin, ListView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_list.html'
    context_object_name = 'sanciones'
    paginate_by = 25

    def _base_queryset(self):
        """Sanciones visibles para el usuario, ya filtradas por explorador."""
        if hasattr(self, '_qs_cache'):
            return self._qs_cache
        qs = (
            SancionEmpleado.objects
            .select_related('explorador', 'supervisor')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if es_supervisor(user):
            eid = _id_valido(self.request.GET.get('explorador'))
            if eid:
                qs = qs.filter(explorador_id=eid)
        else:
            empleado = getattr(user, 'empleado', None)
            qs = qs.filter(explorador=empleado) if empleado else qs.none()
        self._qs_cache = qs
        return qs

    def _estado(self):
        estado = self.request.GET.get('estado')
        return estado if estado in ('activa', 'finalizada', 'levantada') else 'todos'

    def get_queryset(self):
        # El filtro por estado va en el servidor: si filtrara en el navegador
        # solo afectaría a la página visible y contradiría los totales.
        qs = self._base_queryset()
        estado = self._estado()
        if estado in _FILTROS_ESTADO:
            return qs.filter(_FILTROS_ESTADO[estado](timezone.localdate()))
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        queryset = self._base_queryset()
        user = self.request.user
        hoy = timezone.localdate()

        total_sanciones = queryset.count()
        total_activas = queryset.filter(_FILTROS_ESTADO['activa'](hoy)).count()
        total_finalizadas = queryset.filter(_FILTROS_ESTADO['finalizada'](hoy)).count()
        total_levantadas = queryset.filter(_FILTROS_ESTADO['levantada'](hoy)).count()

        supervisa = es_supervisor(user)
        context.update({
            'es_supervisor': supervisa,
            'empleado_actual': getattr(user, 'empleado', None) if not supervisa else None,
            'total_sanciones': total_sanciones,
            'total_activas': total_activas,
            'total_finalizadas': total_finalizadas,
            'total_levantadas': total_levantadas,
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
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver sanciones.')

        return context

def _invalidar_turnos_cache_sancion(sancion):
    """Refresca Mis Turnos del explorador para que la sanción se vea al instante."""
    try:
        from datetime import timedelta

        from core.services.cache_service import CacheService
        hoy = timezone.localdate()
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
        logger.warning("Error invalidando caché de turnos por sanción (explorador=%s)", sancion.explorador_id, exc_info=True)


class _SancionFormViewMixin:
    """Fija como supervisor a quien registra la sanción, sin dejarlo elegir."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not getattr(request.user, 'empleado', None):
            raise PermissionDenied(
                'Tu usuario no está asociado a un empleado, por lo que no puede '
                'registrar sanciones. Pide que se vincule tu ficha de empleado.'
            )
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['supervisor'] = getattr(self.request.user, 'empleado', None)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['supervisor_actual'] = context['form'].supervisor_actual
        return context

    def form_valid(self, form):
        resp = super().form_valid(form)
        _invalidar_turnos_cache_sancion(self.object)
        return resp


class SancionCreateView(LoginRequiredMixin, AdminRequiredMixin, _SancionFormViewMixin, CreateView):
    model = SancionEmpleado
    form_class = SancionEmpleadoForm
    template_name = 'empleados/sanciones_create.html'
    success_url = '/empleados/sanciones/'


class SancionUpdateView(LoginRequiredMixin, AdminRequiredMixin, _SancionFormViewMixin, UpdateView):
    model = SancionEmpleado
    form_class = SancionEmpleadoForm
    template_name = 'empleados/sanciones_edit.html'
    success_url = '/empleados/sanciones/'

class SancionLevantarView(LoginRequiredMixin, AdminRequiredMixin, FormView):
    """
    Levanta una sanción vigente dejando constancia de quién, cuándo y por qué.

    Sustituye al borrado, que ya no existe: una sanción es un hecho disciplinario y
    su registro tiene que sobrevivir, también cuando se puso por error (en ese caso
    se levanta indicándolo como motivo). Y sustituye al apaño de editar la fecha_fin
    a mano, que dejaba el levantamiento indistinguible de una sanción que siempre fue
    corta y podía producir rangos invertidos.
    """
    form_class = SancionLevantarForm
    template_name = 'empleados/sanciones_levantar.html'
    success_url = '/empleados/sanciones/'

    def get_sancion(self):
        if not hasattr(self, '_sancion'):
            self._sancion = get_object_or_404(
                SancionEmpleado.objects.select_related('explorador', 'supervisor'),
                pk=self.kwargs['pk'],
            )
        return self._sancion

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not getattr(request.user, 'empleado', None):
            raise PermissionDenied(
                'Tu usuario no está asociado a un empleado, por lo que no puede '
                'levantar sanciones. Pide que se vincule tu ficha de empleado.'
            )
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['sancion'] = self.get_sancion()
        context['hoy'] = timezone.localdate()
        return context

    def form_valid(self, form):
        sancion = self.get_sancion()
        # Comprobado aquí y no en dispatch: entre que se abre el formulario y se envía,
        # el pago de la deuda puede haberla levantado sola. Avisar es mejor que
        # sobrescribir en silencio quién la levantó.
        if sancion.esta_levantada:
            messages.info(
                self.request,
                f'La sanción de {sancion.explorador.nombre} ya estaba levantada '
                f'({sancion.levantada_en.strftime("%d/%m/%Y")}). No se hizo ningún cambio.'
            )
            return redirect(self.success_url)

        sancion.levantar(
            motivo=form.cleaned_data['motivo'],
            supervisor=getattr(self.request.user, 'empleado', None),
        )
        _invalidar_turnos_cache_sancion(sancion)
        logger.info('Sanción %s de %s levantada por %s', sancion.id,
                    sancion.explorador_id, getattr(self.request.user, 'username', '?'))
        messages.success(
            self.request,
            f'Sanción de {sancion.explorador.nombre} {sancion.explorador.apellido} levantada. '
            'Ya puede volver a realizar solicitudes.'
        )
        return redirect(self.success_url)


class SancionVisualizarListView(LoginRequiredMixin, ListView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_visualizar_list.html'
    context_object_name = 'sanciones'
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
            SancionEmpleado.objects
            .select_related('explorador', 'supervisor')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if es_supervisor(user):
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(explorador=empleado)

    def get_queryset(self):
        if hasattr(self, '_qs_cache'):
            return self._qs_cache
        qs = self._base_queryset()
        f = self._filtros()

        if f['empleado']:
            qs = qs.filter(explorador_id=f['empleado'])
        if f['fecha_desde']:
            qs = qs.filter(fecha_inicio__gte=f['fecha_desde'])
        if f['fecha_hasta']:
            qs = qs.filter(fecha_inicio__lte=f['fecha_hasta'])

        self._qs_cache = qs
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        hoy = timezone.localdate()
        supervisa = es_supervisor(user)

        # Totales sobre el queryset ya filtrado
        qs = self.get_queryset()
        total_activas = qs.filter(_FILTROS_ESTADO['activa'](hoy)).count()
        total_finalizadas = qs.filter(_FILTROS_ESTADO['finalizada'](hoy)).count()
        total_levantadas = qs.filter(_FILTROS_ESTADO['levantada'](hoy)).count()

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
            'total_activas': total_activas,
            'total_finalizadas': total_finalizadas,
            'total_levantadas': total_levantadas,
            'empleados': empleados,
            'filtro_empleado': str(f['empleado']) if f['empleado'] else '',
            'filtro_fecha_desde': f['fecha_desde'].isoformat() if f['fecha_desde'] else '',
            'filtro_fecha_hasta': f['fecha_hasta'].isoformat() if f['fecha_hasta'] else '',
            'query_params': params.urlencode(),
        })

        if not supervisa and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver sanciones.')

        return context


class MorososDeudaView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """
    Quién debe horas de doblada, visto desde fuera.

    La razón de existir: la auto-sanción por deuda es PEREZOSA — solo se calcula cuando el
    propio explorador abre una pantalla. Mientras no entre, su deuda vencida no está en
    ninguna parte y el supervisor no puede verla ni actuar. Esta pantalla la calcula sin
    depender de él.

    GET no escribe nada: es un diagnóstico que se puede mirar con tranquilidad. El POST
    ('Aplicar sanciones') es el que crea las que falten y levanta las de quien ya pagó,
    exactamente lo mismo que ocurriría si cada explorador entrara por su cuenta. Separarlos
    evita que recargar la página tenga efectos disciplinarios.

    Con `?corte=AAAA-MM-DD` la pantalla cambia de pregunta: en vez de "a quién toca sancionar"
    muestra "quién debe de lo que va de este mes, a día de hoy". Es puramente informativa —sin
    botón de sanciones—, porque el mes aún no ha vencido y no hay nada que aplicar todavía.
    """
    template_name = 'empleados/sanciones_morosos.html'

    def _corte(self):
        """La fecha de corte pedida, o None. Un valor con basura se ignora, no rompe."""
        return parse_date(self.request.GET.get('corte') or '')

    def get_context_data(self, **kwargs):
        from solicitudes.models import ConfiguracionSanciones
        from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService

        corte = self._corte()
        if corte:
            context = super().get_context_data(**kwargs)
            filas_corte = DeudaCorporativaService.deuda_a_corte(corte)
            minutos_corte = sum(f['minutos'] for f in filas_corte)
            context.update({
                'corte': corte,
                'filas_corte': filas_corte,
                'hoy': timezone.localdate(),
                'total_exploradores': len(filas_corte),
                'total_minutos_corte': minutos_corte,
                # En horas, que es como se paga: el PDH se registra en horas.
                'total_horas_corte': round(minutos_corte / 60, 2),
            })
            return context

        context = super().get_context_data(**kwargs)
        filas = DeudaCorporativaService.auditar_morosos(aplicar=False)
        context.update({
            'filas': filas,
            'config_sanciones': ConfiguracionSanciones.obtener(),
            'hoy': timezone.localdate(),
            'total_pendientes': sum(1 for f in filas if f['estado'] == 'pendiente'),
            'total_sancionados': sum(1 for f in filas if f['estado'] == 'sancionado'),
            'total_en_plazo': sum(1 for f in filas if f['estado'] == 'en_plazo'),
            'total_levantadas': sum(1 for f in filas if f['estado'] == 'levantada'),
            'total_minutos': sum(f['minutos'] for f in filas),
        })
        return context

    def post(self, request, *args, **kwargs):
        from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService

        if request.POST.get('accion') == 'config':
            return self._guardar_config(request)

        # La vista con corte es de consulta: no debe poder sancionar. La plantilla ya no
        # muestra el botón, pero el POST también lo rechaza — si llegara igual, sancionaría a
        # TODOS los vencidos y no a los del rango que el supervisor tiene delante.
        if self._corte():
            messages.info(request, 'La vista por fecha de corte es solo de consulta. '
                                   'Quita el filtro para aplicar sanciones.')
            return redirect('sanciones_morosos')

        antes = DeudaCorporativaService.auditar_morosos(aplicar=False)
        pendientes = [f for f in antes if f['estado'] == 'pendiente']
        DeudaCorporativaService.auditar_morosos(aplicar=True)

        if pendientes:
            nombres = ', '.join(f"{f['explorador'].nombre} {f['explorador'].apellido}"
                                for f in pendientes)
            messages.success(
                request,
                f'{len(pendientes)} sanción(es) por deuda vencida aplicadas: {nombres}. '
                'Quedan bloqueados hasta que la sanción termine; pagar la deuda no la levanta.'
            )
        else:
            messages.info(
                request,
                'No había ninguna sanción pendiente de aplicar. Todo al día.'
            )
        logger.info('Revisión de morosos ejecutada por %s: %s sanción(es) aplicadas',
                    getattr(request.user, 'username', '?'), len(pendientes))
        return redirect('sanciones_morosos')

    def _guardar_config(self, request):
        """
        Guarda la ventana de reincidencia.

        Es una decisión de política disciplinaria, así que queda registrado quién la tomó.
        No recalcula nada de lo ya grabado: lo que se comunicó a un explorador no puede
        reinterpretarse después con una regla distinta.
        """
        from django.core.exceptions import ValidationError

        from solicitudes.models import ConfiguracionSanciones

        crudo = (request.POST.get('dias_ventana_reincidencia') or '').strip()
        if not crudo.isdigit():
            messages.error(request, 'La ventana de reincidencia debe ser un número de días.')
            return redirect('sanciones_morosos')

        config = ConfiguracionSanciones.obtener()
        anterior = config.dias_ventana_reincidencia
        config.dias_ventana_reincidencia = int(crudo)
        config.actualizado_por = getattr(request.user, 'empleado', None)
        try:
            config.full_clean()
        except ValidationError as e:
            messages.error(request, ' '.join(m for ms in e.message_dict.values() for m in ms))
            return redirect('sanciones_morosos')
        config.save()

        messages.success(
            request,
            f'Ventana de reincidencia: {anterior} → {config.dias_ventana_reincidencia} días. '
            'Aplica a las sanciones que se generen a partir de ahora; las ya existentes no '
            'cambian.')
        logger.info('Ventana de reincidencia cambiada de %s a %s días por %s',
                    anterior, config.dias_ventana_reincidencia,
                    getattr(request.user, 'username', '?'))
        return redirect('sanciones_morosos')
