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
        if _es_supervisor(self.request.user):
            return qs
        empleado = getattr(self.request.user, 'empleado', None)
        return qs.filter(empleado=empleado) if empleado else qs.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['es_supervisor'] = _es_supervisor(self.request.user)
        return context


class _PermisoCreateBase(LoginRequiredMixin, CreateView):
    model = PermisoEspecial
    success_url = reverse_lazy('permisos_especiales_list')
    es_permanente = False

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
