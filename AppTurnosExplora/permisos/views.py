import logging

from django.shortcuts import render
from core.utils.error_token import render_error_token
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from core.constants import (
    EstadoCancelacion,
    VENTANA_PEDIR_CANCELACION_HORAS,
    VENTANA_RESPONDER_CANCELACION_HORAS,
)
from .models import PDH, PermisoEspecial

# Importar mixin común desde core
from core.mixins import AdminRequiredMixin
from core.utils.date_utils import DateUtils
from core.utils.json_responses import json_error
# Regla transversal: el comentario es obligatorio en toda acción que resuelve algo.
# Los textos viven en core para que permisos, solicitudes y las plantillas digan lo mismo.
from core.utils.comentarios import MSG_COMENTARIO, MSG_MOTIVO, leer_texto

logger = logging.getLogger(__name__)

# Create your views here.

class PermisosEspecialesView(LoginRequiredMixin, TemplateView):
    template_name = 'permisos/list.html'

class BeneficiosView(LoginRequiredMixin, TemplateView):
    template_name = 'permisos/beneficios.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Obtener información del empleado
        try:
            empleado = self.request.user.empleado
            context['empleado'] = empleado
            context['documento'] = empleado.cedula
            context['nombre_completo'] = f"{empleado.nombre} {empleado.apellido}"
            context['email'] = empleado.email or self.request.user.email
            context['tipo_usuario'] = 'Operativo'  # Puedes ajustar según tu lógica
            context['jefe_directo'] = f"{empleado.supervisor.nombre} {empleado.supervisor.apellido}" if empleado.supervisor else ""
        except Exception:
            # Si no hay empleado asociado, usar información básica del usuario
            context['empleado'] = None
            context['documento'] = ""
            context['nombre_completo'] = self.request.user.get_full_name() or self.request.user.username
            context['email'] = self.request.user.email
            context['tipo_usuario'] = 'Operativo'
            context['jefe_directo'] = ""
        
        # URL del Google Apps Script (sin parámetros, el script manejará la autenticación)
        context['google_script_url'] = 'https://script.google.com/a/macros/parqueexplora.org/s/AKfycbzEclLu4hB0BkDQ8d2wDgU3W4oFUFE_JbzTVl6k97o/exec'
        
        return context

# Permisos Especiales: el explorador solicita, el supervisor aprueba.
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.urls import reverse_lazy
from .forms import PermisoEspecialForm, PermisoEspecialPermanenteForm


def _es_supervisor(user):
    from turnos.services.consolidado_horas_service import ConsolidadoHorasService
    return ConsolidadoHorasService.es_supervisor(user)


def _dia_no_laborable(empleado, fecha):
    """True si el explorador NO trabaja ese día (descanso) y por tanto no puede pedir permiso.

    Usa la FUENTE DE VERDAD `estado_dia` (todas las capas: turno real, descanso por solicitud,
    alternancia de fin de semana, mantenimiento, temporada, base). Antes usaba `_es_dia_descanso`
    (solo calendario/rotación + temporada de config), que se le escapaban mantenimiento, festivo y
    los descansos por solicitud (día cedido por doblada, cambio de descanso…), permitiendo pedir
    permiso en días en que en realidad se descansa (o bloqueándolo cuando sí se trabaja)."""
    from turnos.services.turno_service import TurnoService
    try:
        return not TurnoService.estado_dia(empleado, fecha).get('trabaja')
    except Exception:
        return False


def _invalidar_turnos_cache(permiso):
    """Invalida la caché de Mis Turnos del explorador para que el permiso se vea al instante."""
    try:
        from datetime import timedelta
        from core.services.cache_service import CacheService
        meses = set()
        d = permiso.fecha_inicio
        while d <= permiso.fecha_fin:
            meses.add((d.month, d.year))
            d += timedelta(days=28)
        meses.add((permiso.fecha_fin.month, permiso.fecha_fin.year))
        for m, y in meses:
            CacheService.invalidar_cache_turnos_empleado(permiso.empleado.id, m, y)
    except Exception:
        logger.warning("Error invalidando caché de turnos por permiso (empleado=%s)", permiso.empleado_id, exc_info=True)


class PermisoEspecialListView(LoginRequiredMixin, ListView):
    """Explorador ve los suyos; supervisor ve todos (con acciones de aprobación)."""
    model = PermisoEspecial
    template_name = 'permisos/permisos_especiales_list.html'
    context_object_name = 'permisos_especiales'

    def get_queryset(self):
        qs = (
            PermisoEspecial.objects
            .select_related('empleado', 'supervisor', 'cubre')
            .order_by('-creado_en')
        )
        es_super = _es_supervisor(self.request.user)
        if es_super:
            # Supervisor: filtro opcional por explorador
            eid = self.request.GET.get('explorador')
            if eid and str(eid).isdigit():
                qs = qs.filter(empleado_id=eid)
        else:
            # Explorador: solo los suyos
            empleado = getattr(self.request.user, 'empleado', None)
            qs = qs.filter(empleado=empleado) if empleado else qs.none()

        # Filtro por fecha (día) — permisos que cubren ese día
        fecha = self.request.GET.get('fecha')
        if fecha:
            from datetime import datetime
            try:
                f = DateUtils.parse_date(fecha)
                qs = qs.filter(fecha_inicio__lte=f, fecha_fin__gte=f)
            except ValueError:
                pass

        # Filtro por mes (formato 'YYYY-MM') — permisos cuyo rango toca ese mes
        mes = self.request.GET.get('mes')
        if mes:
            from datetime import date as _date, timedelta
            try:
                y, m = (int(x) for x in mes.split('-')[:2])
                primero = _date(y, m, 1)
                ultimo = _date(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1) - timedelta(days=1)
                qs = qs.filter(fecha_inicio__lte=ultimo, fecha_fin__gte=primero)
            except (ValueError, TypeError):
                pass
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        es_super = _es_supervisor(self.request.user)
        context['es_supervisor'] = es_super
        # Sobre el permiso PROPIO se pide la cancelación aunque uno sea supervisor, así que la
        # plantilla necesita distinguir "mi permiso" de "el de otro", no solo el rol.
        mi_empleado = getattr(self.request.user, 'empleado', None)
        context['mi_empleado_id'] = mi_empleado.id if mi_empleado else None
        context['filtro_fecha'] = self.request.GET.get('fecha', '')
        context['filtro_mes'] = self.request.GET.get('mes', '')
        if es_super:
            from empleados.models import Empleado
            context['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
            context['filtro_explorador'] = self.request.GET.get('explorador', '')
        else:
            # Si el explorador está sancionado, avisamos y bloqueamos los botones (popup)
            from empleados.sancion_utils import sancion_activa, mensaje_sancion
            emp = getattr(self.request.user, 'empleado', None)
            s = sancion_activa(emp) if emp else None
            if s:
                context['sancion_msg'] = mensaje_sancion(s)
        return context


class _PermisoCreateBase(LoginRequiredMixin, CreateView):
    model = PermisoEspecial
    success_url = reverse_lazy('permisos_especiales_list')
    es_permanente = False

    def dispatch(self, request, *args, **kwargs):
        # Bloqueo por sanción antes de mostrar/procesar el formulario (un solo aviso)
        empleado = getattr(request.user, 'empleado', None)
        if empleado:
            # Generar/levantar automáticamente la sanción por deuda de doblada vencida
            try:
                from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
                DeudaCorporativaService.gestionar_sancion_por_deuda(empleado)
            except Exception:
                logger.warning("Error gestionando sanción por deuda (empleado=%s)", empleado.id, exc_info=True)
            from empleados.sancion_utils import sancion_activa, mensaje_sancion
            sancion = sancion_activa(empleado)
            if sancion:
                messages.warning(request, mensaje_sancion(sancion))
                return redirect('permisos_especiales_list')
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['empleado'] = getattr(self.request.user, 'empleado', None)
        return kwargs

    def form_valid(self, form):
        empleado = getattr(self.request.user, 'empleado', None)
        if not empleado:
            messages.error(self.request, 'Tu usuario no tiene un explorador asociado.')
            return self.form_invalid(form)

        permiso = form.save(commit=False)
        permiso.empleado = empleado
        permiso.supervisor = empleado.supervisor
        permiso.estado = 'PENDIENTE'
        permiso.es_permanente = self.es_permanente

        if self.es_permanente:
            permiso.fecha_inicio = form.cleaned_data['fecha_inicio']
            permiso.fecha_fin = form.cleaned_data['fecha_fin']
            permiso.dias_semana = ','.join(form.cleaned_data['dias'])
        else:
            fecha = form.cleaned_data['fecha']
            permiso.fecha_inicio = fecha
            permiso.fecha_fin = fecha
            # Validación: solo se puede pedir permiso en un día con jornada programada
            if _dia_no_laborable(empleado, fecha):
                form.add_error('fecha', 'Ese día estás en descanso (no tienes jornada programada). '
                                        'Solo puedes pedir permiso en días que trabajas.')
                return self.form_invalid(form)

        # Cierre semanal: no se pueden pedir permisos para fechas del fin de semana ya cerrado.
        from datetime import timedelta as _td
        from solicitudes.services.cierre_solicitudes_service import CierreSolicitudesService
        if self.es_permanente:
            _dias_wd = {int(x) for x in form.cleaned_data.get('dias', [])}
            _fechas_obj, _d = [], permiso.fecha_inicio
            while _d <= permiso.fecha_fin:
                if not _dias_wd or _d.weekday() in _dias_wd:
                    _fechas_obj.append(_d)
                _d += _td(days=1)
        else:
            _fechas_obj = [permiso.fecha_inicio]
        try:
            _fbloq, _msg = CierreSolicitudesService.validar_fechas(_fechas_obj)
        except Exception:
            # Fail-open igual que el orquestador, pero visible en alertas.
            logger.critical('CIERRE SEMANAL INOPERATIVO en permisos para las fechas %s; '
                            'la solicitud se permite sin validar el cierre.', _fechas_obj, exc_info=True)
            _msg = None
        if _msg:
            form.add_error('fecha_inicio' if self.es_permanente else 'fecha', _msg)
            return self.form_invalid(form)

        permiso.save()
        _invalidar_turnos_cache(permiso)

        # Notificar al supervisor del explorador (in-app + email con enlaces)
        from .services import PermisoNotificacionService
        try:
            PermisoNotificacionService.notificar_solicitud(permiso)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Error notificando permiso %s", permiso.id)

        sup = permiso.empleado.supervisor
        if sup:
            messages.success(
                self.request,
                f'Permiso solicitado ({permiso.horas_totales()} h). Se notificó a tu supervisor '
                f'{sup.nombre} {sup.apellido} para su aprobación.'
            )
        else:
            messages.warning(
                self.request,
                'Permiso solicitado, pero no tienes un supervisor asignado para aprobarlo. '
                'Avisa a administración.'
            )
        return redirect(self.success_url)


class PermisoEspecialCreateView(_PermisoCreateBase):
    template_name = 'permisos/permisos_especiales_create.html'
    form_class = PermisoEspecialForm
    es_permanente = False


class PermisoEspecialPermanenteCreateView(_PermisoCreateBase):
    template_name = 'permisos/permisos_especiales_permanente_create.html'
    form_class = PermisoEspecialPermanenteForm
    es_permanente = True


def _quiere_json(request):
    """¿Es un cliente automatizado (fetch/API) o un navegador siguiendo un formulario?"""
    return (
        request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in request.headers.get('Accept', '')
    )


def _fallo(request, mensaje, code, status=400):
    """
    Salida de error de las acciones de permisos, con un código que se pueda leer.

    Estas vistas nacieron como formularios normales: cualquier desenlace —comentario vacío,
    permiso ya resuelto, acción aplicada— terminaba en el mismo 302 a la lista, así que un
    cliente automatizado no podía distinguir un fallo de un éxito. Ahora quien pide JSON
    recibe el estado HTTP real y un `code`; el navegador sigue viendo su mensaje y su
    redirect, que es lo que espera al enviar un formulario.
    """
    if _quiere_json(request):
        return json_error(mensaje, status=status, code=code)
    messages.error(request, mensaje)
    return redirect('permisos_especiales_list')


class PermisoEspecialAprobarView(LoginRequiredMixin, View):
    """El supervisor aprueba o rechaza un permiso pendiente."""
    def post(self, request, pk):
        from django.utils import timezone

        if not _es_supervisor(request.user):
            return _fallo(request, 'No tienes permisos para aprobar.', 'forbidden', status=403)
        permiso = get_object_or_404(PermisoEspecial, pk=pk)
        accion = request.POST.get('accion')
        comentario = leer_texto(request, 'comentario')
        if comentario is None:
            return _fallo(request, MSG_COMENTARIO, 'comentario_requerido')
        if permiso.estado != 'PENDIENTE':
            return _fallo(request, 'Este permiso ya fue resuelto.', 'invalid_state', status=409)
        permiso.supervisor = getattr(request.user, 'empleado', None)
        permiso.comentario_supervisor = comentario
        if accion == 'aprobar':
            permiso.estado = 'APROBADO'
            permiso.fecha_aprobacion = timezone.now()
            messages.success(request, f'Permiso aprobado. Se acumulan {permiso.horas_totales()} h a {permiso.empleado.nombre}.')
        else:
            permiso.estado = 'RECHAZADO'
            messages.info(request, 'Permiso rechazado.')
        permiso.save()
        if permiso.estado == 'APROBADO' and permiso.tipo == 'MEDIA_JORNADA_TEMPORADA':
            from .services import PermisoMediaJornadaService
            PermisoMediaJornadaService.aplicar(permiso)
        _invalidar_turnos_cache(permiso)
        from .services import PermisoNotificacionService
        try:
            PermisoNotificacionService.notificar_resolucion(permiso)
        except Exception:
            logger.warning("Error notificando resolución de permiso %s", permiso.id, exc_info=True)
        return redirect('permisos_especiales_list')


class PermisoEspecialResolverEmailView(View):
    """Aprobar/rechazar un permiso desde el enlace del email (token firmado)."""
    accion = 'aprobar'

    def get(self, request, pk, token):
        from django.utils import timezone

        from .services import PermisoNotificacionService
        permiso = get_object_or_404(
            PermisoEspecial.objects.select_related('empleado', 'empleado__supervisor'), pk=pk
        )
        if not PermisoNotificacionService.verificar_token(permiso, token):
            return render_error_token(request, 'Token inválido o expirado.', status=403)

        ya_resuelto = permiso.estado != 'PENDIENTE'
        if not ya_resuelto:
            permiso.supervisor = permiso.empleado.supervisor
            permiso.estado = 'APROBADO' if self.accion == 'aprobar' else 'RECHAZADO'
            if permiso.estado == 'APROBADO':
                permiso.fecha_aprobacion = timezone.now()
            permiso.save()
            if permiso.estado == 'APROBADO' and permiso.tipo == 'MEDIA_JORNADA_TEMPORADA':
                from .services import PermisoMediaJornadaService
                PermisoMediaJornadaService.aplicar(permiso)
            _invalidar_turnos_cache(permiso)
            try:
                PermisoNotificacionService.notificar_resolucion(permiso)
            except Exception:
                logger.warning("Error notificando resolución de permiso %s (email)", permiso.id, exc_info=True)

        return render(request, 'permisos/permiso_email_resultado.html', {
            'permiso': permiso,
            'accion': permiso.get_estado_display(),
            'ya_resuelto': ya_resuelto,
        })


class PermisoEspecialDeleteView(LoginRequiredMixin, DeleteView):
    model = PermisoEspecial
    template_name = 'permisos/permisos_especiales_confirm_delete.html'
    success_url = reverse_lazy('permisos_especiales_list')

    def get_queryset(self):
        qs = super().get_queryset()
        if _es_supervisor(self.request.user):
            return qs
        empleado = getattr(self.request.user, 'empleado', None)
        return qs.filter(empleado=empleado, estado='PENDIENTE') if empleado else qs.none()

    def form_valid(self, form):
        permiso = self.get_object()
        # Un permiso de media jornada APROBADO ya modificó turnos: restaurarlos antes de borrar.
        if permiso.estado == 'APROBADO' and permiso.tipo == 'MEDIA_JORNADA_TEMPORADA':
            from .services import PermisoMediaJornadaService
            PermisoMediaJornadaService.revertir(permiso)
        _invalidar_turnos_cache(permiso)
        return super().form_valid(form)


class PermisoMediaJornadaCancelView(LoginRequiredMixin, View):
    """
    Cancela un permiso de MEDIA JORNADA TEMPORADA conservando el registro (estado CANCELADO)
    y restaurando los turnos.

    Quién puede cancelar depende de si el permiso llegó a aplicarse:

    - PENDIENTE: nadie lo aprobó y no hay turnos movidos. El dueño lo retira solo.
    - APROBADO: los turnos ya se movieron con el visto bueno del supervisor. El dueño NO lo
      cancela por su cuenta: lo PIDE y el supervisor lo confirma en `PermisoMediaJornadaCancelResponderView`.
      Aquí la contraparte es el supervisor porque el permiso no tiene receptor: es quien aprobó
      el permiso y quien responde por la cobertura del día.
    - El SUPERVISOR sigue cancelando directo: su decisión es la que se estaba pidiendo.

    En todos los casos, si otro cambio ya tocó esos días se bloquea para no pisarlo.
    """
    VENTANA_HORAS = VENTANA_PEDIR_CANCELACION_HORAS

    def post(self, request, pk):
        from django.utils import timezone

        permiso = get_object_or_404(PermisoEspecial, pk=pk, tipo='MEDIA_JORNADA_TEMPORADA')
        emp = getattr(request.user, 'empleado', None)
        es_sup = _es_supervisor(request.user)
        es_dueno = bool(emp) and permiso.empleado_id == emp.id
        if not (es_sup or es_dueno):
            return _fallo(request, 'No tienes permiso para cancelar este permiso.',
                          'forbidden', status=403)

        motivo = leer_texto(request, 'motivo')
        if motivo is None:
            return _fallo(request, MSG_MOTIVO, 'comentario_requerido')

        if permiso.estado in ('CANCELADO', 'RECHAZADO'):
            return _fallo(request, 'Este permiso ya no está activo.', 'invalid_state', status=409)

        # Pendiente: no hay turnos aplicados, solo se marca cancelado.
        if permiso.estado == 'PENDIENTE':
            permiso.estado = 'CANCELADO'
            permiso.save()
            messages.success(request, 'Permiso cancelado.')
            return redirect('permisos_especiales_list')

        # Aprobado y lo pide el DUEÑO: es una PETICIÓN, la decide su supervisor. La condición
        # mira de quién es el permiso, no qué rol tiene quien pulsa: antes era
        # `es_dueno and not es_sup`, así que un explorador que además fuera supervisor caía en
        # la rama de abajo y se autoaprobaba la cancelación de su propio permiso.
        if es_dueno:
            return self._pedir_cancelacion(request, permiso, emp, timezone, motivo)

        return self._cancelar(
            request, permiso,
            nota=(f'Cancelado por {emp.nombre} {emp.apellido}.' if emp else 'Cancelado desde supervisión.')
                 + f' Motivo: {motivo}',
        )

    def _pedir_cancelacion(self, request, permiso, emp, timezone, motivo):
        from .services import PermisoMediaJornadaService

        if permiso.cancelacion_estado == EstadoCancelacion.PENDIENTE:
            messages.info(request, 'Ya pediste cancelar este permiso. Está esperando la '
                                   'respuesta de tu supervisor.')
            return redirect('permisos_especiales_list')
        if permiso.cancelacion_estado in EstadoCancelacion.TERMINALES:
            messages.error(request, _mensaje_cancelacion_permiso_cerrada(permiso))
            return redirect('permisos_especiales_list')

        # `fecha_aprobacion or actualizado_en`: los permisos aprobados antes de que existiera el
        # campo no la tienen, y sin el respaldo quedarían incancelables para siempre.
        aprobado_en = permiso.fecha_aprobacion or permiso.actualizado_en
        horas = (timezone.now() - aprobado_en).total_seconds() / 3600
        if horas > self.VENTANA_HORAS:
            messages.error(
                request,
                f'Ya no puedes cancelar este permiso (pasaron más de {self.VENTANA_HORAS} horas '
                f'desde su aprobación). Pídele a tu supervisor que lo cancele.'
            )
            return redirect('permisos_especiales_list')

        # Se comprueba ANTES de molestar al supervisor: si la reversión ya no es limpia, la
        # petición no llega a existir y el dueño se entera al instante.
        if not PermisoMediaJornadaService.puede_revertir_limpio(permiso):
            messages.error(
                request,
                'No se puede cancelar: los turnos de esos días ya fueron modificados por otro '
                'cambio. Cancela primero ese cambio y vuelve a intentarlo.'
            )
            return redirect('permisos_especiales_list')

        permiso.cancelacion_estado = EstadoCancelacion.PENDIENTE
        permiso.cancelacion_solicitada_por = emp
        permiso.cancelacion_solicitada_en = timezone.now()
        permiso.cancelacion_motivo = motivo
        permiso.save(update_fields=[
            'cancelacion_estado', 'cancelacion_solicitada_por',
            'cancelacion_solicitada_en', 'cancelacion_motivo', 'actualizado_en',
        ])
        _notificar_peticion_cancelacion_permiso(permiso)
        messages.success(
            request,
            f'Se envió tu solicitud de cancelación a tu supervisor. El permiso sigue vigente '
            f'hasta que la apruebe. Tiene {VENTANA_RESPONDER_CANCELACION_HORAS} horas para responder.'
        )
        return redirect('permisos_especiales_list')

    def _cancelar(self, request, permiso, nota=''):
        """Reversión efectiva. La comparten la cancelación directa del supervisor y su
        aprobación de una petición del dueño: en ambos casos decide el supervisor."""
        from .services import PermisoMediaJornadaService

        if not PermisoMediaJornadaService.puede_revertir_limpio(permiso):
            messages.error(
                request,
                'No se puede cancelar: los turnos de esos días ya fueron modificados por otro '
                'cambio. Cancela primero ese cambio y vuelve a intentarlo.'
            )
            return redirect('permisos_especiales_list')

        PermisoMediaJornadaService.revertir(permiso)
        permiso.estado = 'CANCELADO'
        if nota:
            permiso.comentario_supervisor = f"{permiso.comentario_supervisor or ''}\n\n{nota}".strip()
        permiso.save()
        _invalidar_turnos_cache(permiso)
        messages.success(request, 'Permiso cancelado y turnos restaurados.')
        return redirect('permisos_especiales_list')


class PermisoMediaJornadaCancelResponderView(LoginRequiredMixin, View):
    """
    Respuesta del SUPERVISOR a la petición de cancelación de un permiso ya aprobado
    (`accion=aprobar` o `accion=rechazar`).

    Aprobar es lo único que revierte los turnos. Rechazar —o dejar pasar el plazo— deja el
    permiso firme y cierra el asunto: no se vuelve a pedir.
    """

    def post(self, request, pk):
        from django.utils import timezone

        permiso = get_object_or_404(
            PermisoEspecial.objects.select_related('empleado', 'empleado__supervisor', 'supervisor'),
            pk=pk, tipo='MEDIA_JORNADA_TEMPORADA',
        )
        emp = getattr(request.user, 'empleado', None)
        puede, motivo = _puede_responder_cancelacion(request.user, emp, permiso)
        if not puede:
            return _fallo(request, motivo, 'forbidden', status=403)

        if permiso.cancelacion_estado != EstadoCancelacion.PENDIENTE:
            return _fallo(request, 'Este permiso no tiene ninguna cancelación pendiente.',
                          'invalid_state', status=409)

        # Caducidad: se reconoce al mirarla, no con un proceso de fondo — una petición vencida
        # no tiene efecto pendiente que aplicar, el permiso simplemente sigue vigente.
        horas = (timezone.now() - permiso.cancelacion_solicitada_en).total_seconds() / 3600
        if horas > VENTANA_RESPONDER_CANCELACION_HORAS:
            permiso.cancelacion_estado = EstadoCancelacion.CADUCADA
            permiso.save(update_fields=['cancelacion_estado', 'actualizado_en'])
            return _fallo(request, f'El plazo de {VENTANA_RESPONDER_CANCELACION_HORAS} horas '
                                   f'para responder ya venció: el permiso quedó firme.',
                          'plazo_vencido', status=409)

        comentario = leer_texto(request, 'comentario')
        if comentario is None:
            return _fallo(request, MSG_COMENTARIO, 'comentario_requerido')

        aprueba = (request.POST.get('accion') or '').strip().lower() == 'aprobar'
        quien = f"{emp.nombre} {emp.apellido}" if emp else 'un supervisor'
        permiso.cancelacion_respondida_por = emp
        permiso.cancelacion_respondida_en = timezone.now()

        if not aprueba:
            permiso.cancelacion_estado = EstadoCancelacion.RECHAZADA
            permiso.comentario_supervisor = (
                f"{permiso.comentario_supervisor or ''}"
                f"\n\nCancelación rechazada por {quien}. "
                f"Motivo: {comentario}"
            ).strip()
            permiso.save(update_fields=[
                'cancelacion_estado', 'cancelacion_respondida_por',
                'cancelacion_respondida_en', 'comentario_supervisor', 'actualizado_en',
            ])
            _notificar_respuesta_cancelacion_permiso(permiso, quien, aprobada=False)
            messages.success(request, 'Rechazaste la cancelación. El permiso sigue vigente.')
            return redirect('permisos_especiales_list')

        permiso.cancelacion_estado = EstadoCancelacion.APROBADA
        respuesta = PermisoMediaJornadaCancelView()._cancelar(
            request, permiso,
            nota=f'Cancelación pedida por el explorador y aprobada por {quien}. Motivo: {comentario}',
        )
        _notificar_respuesta_cancelacion_permiso(permiso, quien, aprobada=True)
        return respuesta


def _supervisor_del_permiso(permiso):
    """
    Quién responde por este permiso: el supervisor que lo aprobó y, si no consta, el del
    explorador. Es la misma pareja que usa el aviso, así que decide y notifica lo mismo.
    """
    return permiso.supervisor or permiso.empleado.supervisor


def _puede_responder_cancelacion(user, emp, permiso) -> tuple[bool, str]:
    """
    ¿Puede este usuario aprobar o rechazar la cancelación de este permiso?

    Antes bastaba con tener el rol: cualquier supervisor decidía sobre el permiso de cualquier
    explorador, aunque el aviso se le mandara solo al suyo. En solicitudes el control es
    estricto contra el receptor concreto, y aquí debe serlo contra el supervisor concreto.

    Dos matices deliberados:
    - El dueño no puede responderse a sí mismo, aunque sea supervisor. Es la otra mitad de que
      sobre lo propio siempre se PIDA (ver `PermisoMediaJornadaCancelView.post`).
    - Si el permiso no tiene supervisor resoluble, vale cualquiera: si no, la petición no la
      podría responder nadie y caducaría siempre.
    """
    if not _es_supervisor(user):
        return False, 'Solo un supervisor puede responder esta cancelación.'
    if emp and permiso.empleado_id == emp.id:
        return False, ('No puedes responder la cancelación de tu propio permiso: la decide tu '
                       'supervisor.')
    responsable = _supervisor_del_permiso(permiso)
    if responsable and emp and responsable.id != emp.id:
        # No se afirma "quien aprobó el permiso": el responsable puede venir del supervisor del
        # explorador cuando el permiso no guarda el suyo, y entonces sería falso.
        return False, (f'Esta cancelación la decide {responsable.nombre} {responsable.apellido}, '
                       f'el supervisor responsable de este permiso.')
    return True, ''


def _mensaje_cancelacion_permiso_cerrada(permiso) -> str:
    """Por qué ya no se puede volver a pedir la cancelación de este permiso."""
    if permiso.cancelacion_estado == EstadoCancelacion.RECHAZADA:
        return ('Tu supervisor ya rechazó la cancelación de este permiso, así que quedó firme. '
                'Si lo necesitas, consúltalo directamente con él.')
    if permiso.cancelacion_estado == EstadoCancelacion.CADUCADA:
        return (f'La cancelación caducó: tu supervisor no respondió dentro de las '
                f'{VENTANA_RESPONDER_CANCELACION_HORAS} horas y el permiso quedó firme. '
                f'Si lo necesitas, consúltalo directamente con él.')
    return 'Este permiso ya fue cancelado.'


def _notificar_peticion_cancelacion_permiso(permiso):
    """Avisa al supervisor de que hay una cancelación esperando su respuesta."""
    from solicitudes.models import Notificacion

    destinatario = _supervisor_del_permiso(permiso)
    if not destinatario:
        return
    motivo = f"\n\nMotivo: {permiso.cancelacion_motivo}" if permiso.cancelacion_motivo else ''
    Notificacion.objects.create(
        destinatario=destinatario,
        tipo='solicitud_permiso',
        titulo='Te piden cancelar un permiso ya aprobado',
        mensaje=(
            f"{permiso.empleado.nombre} {permiso.empleado.apellido} pide cancelar su permiso de "
            f"media jornada del {permiso.fecha_inicio.strftime('%d/%m/%Y')}, que ya habías "
            f"aprobado.{motivo}\n\n"
            f"El permiso SIGUE VIGENTE hasta que respondas. Tienes "
            f"{VENTANA_RESPONDER_CANCELACION_HORAS} horas para aprobar o rechazar la "
            f"cancelación; si no respondes, el permiso queda firme."
        ),
    )


def _notificar_respuesta_cancelacion_permiso(permiso, quien, aprobada):
    """Avisa al dueño del permiso de la decisión del supervisor."""
    from solicitudes.models import Notificacion

    fecha = permiso.fecha_inicio.strftime('%d/%m/%Y')
    if aprobada:
        titulo = 'Cancelación de permiso aprobada'
        cuerpo = (f"{quien} aprobó la cancelación de tu permiso de media jornada del {fecha}. "
                  f"Los turnos volvieron a como estaban antes.")
    else:
        titulo = 'Cancelación de permiso rechazada'
        cuerpo = (f"{quien} rechazó la cancelación de tu permiso de media jornada del {fecha}, "
                  f"así que el permiso sigue vigente y queda firme. No se puede volver a pedir "
                  f"la cancelación; consúltalo directamente con tu supervisor.")
    Notificacion.objects.create(
        destinatario=permiso.empleado,
        tipo='solicitud_permiso',
        titulo=titulo,
        mensaje=cuerpo,
    )


class MediaJornadaTemporadaCreateView(LoginRequiredMixin, View):
    """
    Crea un PermisoEspecial de MEDIA JORNADA TEMPORADA desde el formulario de
    Cambio de Día de Descanso (modalidad entre semana). Es un PERMISO: lo aprueba
    el supervisor (no pasa por el flujo de solicitudes de cambio de turno).
    Sin deuda (tiempo=0): el día completo se compensa trabajando la otra media
    jornada en el día de descanso de la MISMA semana.
    """
    def post(self, request):
        from datetime import datetime as _dt, timedelta as _td
        from core.utils.json_responses import json_ok, json_error
        from turnos.services.turno_service import TurnoService

        emp = getattr(request.user, 'empleado', None)
        if not emp:
            return json_error('Usuario no tiene empleado asociado', status=403, code='forbidden')

        # Bloqueo por sanción de deuda: igual que los permisos normales, un empleado
        # sancionado NO puede realizar solicitudes ni permisos mientras dure la sanción.
        try:
            from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
            DeudaCorporativaService.gestionar_sancion_por_deuda(emp)
        except Exception:
            logger.warning("Error gestionando sanción por deuda (empleado=%s)", emp.id, exc_info=True)
        from empleados.sancion_utils import sancion_activa, mensaje_sancion
        _sancion = sancion_activa(emp)
        if _sancion:
            return json_error(mensaje_sancion(_sancion), status=403, code='sancionado')

        try:
            f_trabajo = _dt.strptime(request.POST.get('fecha_trabajo', ''), '%Y-%m-%d').date()
            f_comp = _dt.strptime(request.POST.get('fecha_compensacion', ''), '%Y-%m-%d').date()
        except (TypeError, ValueError):
            return json_error('Fechas inválidas (YYYY-MM-DD)', status=400, code='bad_request')
        jornada = (request.POST.get('jornada_trabaja') or '').upper()
        motivo = (request.POST.get('motivo') or '').strip()

        if jornada not in ('AM', 'PM'):
            return json_error('Debes indicar qué media jornada trabajarás ese día (AM o PM).',
                              status=400, code='invalid')
        if not motivo:
            return json_error('El motivo es obligatorio.', status=400, code='invalid')
        if f_trabajo.weekday() >= 5 or f_comp.weekday() >= 5:
            return json_error('Ambos días deben ser de lunes a viernes.', status=400, code='invalid')
        if (f_trabajo - _td(days=f_trabajo.weekday())) != (f_comp - _td(days=f_comp.weekday())):
            return json_error('La compensación debe ser en la MISMA semana de temporada.',
                              status=400, code='invalid')

        # No se pueden pedir días pasados (el resto del formulario de Cambio de Descanso ya lo
        # valida; esta vista es otro endpoint y hay que repetirlo aquí).
        from django.utils import timezone as _tz
        _hoy = _tz.localdate()
        if f_trabajo < _hoy or f_comp < _hoy:
            return json_error('No se pueden usar días pasados.', status=400, code='invalid')

        # Cierre semanal: este sub-tipo del formulario de Cambio de Descanso llega por su propio
        # endpoint, así que el gate del orquestador no lo cubre. Sin esto sería un bypass del cierre.
        from solicitudes.services.cierre_solicitudes_service import CierreSolicitudesService
        try:
            _fbloq, _msg_cierre = CierreSolicitudesService.validar_fechas([f_trabajo, f_comp])
        except Exception:
            # Fail-open igual que el orquestador, pero visible en alertas.
            logger.critical('CIERRE SEMANAL INOPERATIVO en media jornada temporada (%s, %s)',
                            f_trabajo, f_comp, exc_info=True)
            _msg_cierre = None
        if _msg_cierre:
            return json_error(_msg_cierre, status=400, code='cierre_semanal')
        # Fuente de verdad: fecha_trabajo debe ser mi día completo de temporada;
        # fecha_compensacion debe ser mi día libre.
        e_trab = TurnoService.estado_dia(emp, f_trabajo)
        if not (e_trab['trabaja'] and e_trab['jornada'] == 'DOBLADA'):
            return json_error('Ese día no es tu día completo de temporada (o ya fue modificado).',
                              status=400, code='invalid')
        e_comp = TurnoService.estado_dia(emp, f_comp)
        if e_comp['trabaja']:
            return json_error('El día de compensación debe ser tu día de descanso de esa semana.',
                              status=400, code='invalid')
        if PermisoEspecial.objects.filter(
                empleado=emp, tipo='MEDIA_JORNADA_TEMPORADA', estado='PENDIENTE',
                fecha_inicio=f_trabajo).exists():
            return json_error('Ya tienes un permiso de media jornada pendiente para ese día.',
                              status=400, code='duplicado')

        permiso = PermisoEspecial.objects.create(
            empleado=emp,
            tipo='MEDIA_JORNADA_TEMPORADA',
            fecha_inicio=f_trabajo,
            fecha_fin=f_trabajo,
            jornada_trabaja=jornada,
            fecha_compensacion=f_comp,
            tiempo=0,  # compensado: sin horas adeudadas
            especificacion=f'Trabaja {jornada} el {f_trabajo:%d/%m} y '
                           f'{"PM" if jornada == "AM" else "AM"} el {f_comp:%d/%m}',
            motivo=motivo,
            estado='PENDIENTE',
            supervisor=emp.supervisor,
        )
        from .services import PermisoNotificacionService
        try:
            PermisoNotificacionService.notificar_solicitud(permiso)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Error notificando permiso %s", permiso.id)
        return json_ok({'message': 'Permiso de media jornada enviado a tu supervisor.',
                        'permiso_id': permiso.id})
