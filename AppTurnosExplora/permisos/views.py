from django.shortcuts import render
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from .models import PDH, PermisoEspecial

# Importar mixin común desde core
from core.mixins import AdminRequiredMixin

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
    """True si el explorador NO trabaja ese día (descanso) y por tanto no puede pedir permiso."""
    from solicitudes.services.ct_permanente_helper import _es_dia_descanso
    try:
        return _es_dia_descanso(empleado, fecha)
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
        pass


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
                f = datetime.strptime(fecha, '%Y-%m-%d').date()
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
                pass
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


class PermisoEspecialAprobarView(LoginRequiredMixin, View):
    """El supervisor aprueba o rechaza un permiso pendiente."""
    def post(self, request, pk):
        if not _es_supervisor(request.user):
            messages.error(request, 'No tienes permisos para aprobar.')
            return redirect('permisos_especiales_list')
        permiso = get_object_or_404(PermisoEspecial, pk=pk)
        accion = request.POST.get('accion')
        comentario = request.POST.get('comentario', '')
        if permiso.estado != 'PENDIENTE':
            messages.warning(request, 'Este permiso ya fue resuelto.')
            return redirect('permisos_especiales_list')
        permiso.supervisor = getattr(request.user, 'empleado', None)
        permiso.comentario_supervisor = comentario
        if accion == 'aprobar':
            permiso.estado = 'APROBADO'
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
            pass
        return redirect('permisos_especiales_list')


class PermisoEspecialResolverEmailView(View):
    """Aprobar/rechazar un permiso desde el enlace del email (token firmado)."""
    accion = 'aprobar'

    def get(self, request, pk, token):
        from .services import PermisoNotificacionService
        permiso = get_object_or_404(
            PermisoEspecial.objects.select_related('empleado', 'empleado__supervisor'), pk=pk
        )
        if not PermisoNotificacionService.verificar_token(permiso, token):
            return render(request, 'solicitudes/error_token.html', {'mensaje': 'Token inválido o expirado.'})

        ya_resuelto = permiso.estado != 'PENDIENTE'
        if not ya_resuelto:
            permiso.supervisor = permiso.empleado.supervisor
            permiso.estado = 'APROBADO' if self.accion == 'aprobar' else 'RECHAZADO'
            permiso.save()
            if permiso.estado == 'APROBADO' and permiso.tipo == 'MEDIA_JORNADA_TEMPORADA':
                from .services import PermisoMediaJornadaService
                PermisoMediaJornadaService.aplicar(permiso)
            _invalidar_turnos_cache(permiso)
            try:
                PermisoNotificacionService.notificar_resolucion(permiso)
            except Exception:
                pass

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
    - Supervisor: sin límite de tiempo.
    - Dueño (explorador): solo dentro de la ventana (30 min desde la aprobación).
    En ambos casos, si otro cambio ya tocó esos días, se bloquea para no pisarlo.
    """
    VENTANA_MIN = 30

    def post(self, request, pk):
        from django.utils import timezone
        from .services import PermisoMediaJornadaService

        permiso = get_object_or_404(PermisoEspecial, pk=pk, tipo='MEDIA_JORNADA_TEMPORADA')
        emp = getattr(request.user, 'empleado', None)
        es_sup = _es_supervisor(request.user)
        es_dueno = bool(emp) and permiso.empleado_id == emp.id
        if not (es_sup or es_dueno):
            messages.error(request, 'No tienes permiso para cancelar este permiso.')
            return redirect('permisos_especiales_list')

        if permiso.estado in ('CANCELADO', 'RECHAZADO'):
            messages.info(request, 'Este permiso ya no está activo.')
            return redirect('permisos_especiales_list')

        # Pendiente: no hay turnos aplicados, solo se marca cancelado.
        if permiso.estado == 'PENDIENTE':
            permiso.estado = 'CANCELADO'
            permiso.save()
            messages.success(request, 'Permiso cancelado.')
            return redirect('permisos_especiales_list')

        # Aprobado: hay turnos aplicados que hay que revertir.
        if es_dueno and not es_sup:
            minutos = (timezone.now() - permiso.actualizado_en).total_seconds() / 60
            if minutos > self.VENTANA_MIN:
                messages.error(
                    request,
                    f'Ya no puedes cancelar este permiso (pasaron más de {self.VENTANA_MIN} min '
                    f'desde su aprobación). Pídele a tu supervisor que lo cancele.'
                )
                return redirect('permisos_especiales_list')

        if not PermisoMediaJornadaService.puede_revertir_limpio(permiso):
            messages.error(
                request,
                'No se puede cancelar: los turnos de esos días ya fueron modificados por otro '
                'cambio. Cancela primero ese cambio y vuelve a intentarlo.'
            )
            return redirect('permisos_especiales_list')

        PermisoMediaJornadaService.revertir(permiso)
        permiso.estado = 'CANCELADO'
        permiso.save()
        _invalidar_turnos_cache(permiso)
        messages.success(request, 'Permiso cancelado y turnos restaurados.')
        return redirect('permisos_especiales_list')


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
            pass
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
