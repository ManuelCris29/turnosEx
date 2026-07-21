from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.forms import SetPasswordForm
from django.views import View
from django.views.generic import ListView, DetailView, UpdateView, TemplateView
from django.views.generic.edit import DeleteView
from django import forms
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils import timezone

from turnos.models import AsignarJornadaExplorador
from core.mixins import AdminRequiredMixin

from ..services.empleado_service import EmpleadoService
from ..models import Empleado, Role, Sala, EmpleadoRole, CompetenciaEmpleado, Jornada
from ..forms import EmpleadoUsuarioForm


class EmpleadoListView(LoginRequiredMixin, ListView):
    template_name = 'empleados/lista.html'
    context_object_name = 'empleados'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Función para verificar si el usuario es administrador
        def is_admin_user(user):
            if user.is_staff:
                return True
            try:
                empleado = user.empleado
                return empleado.empleadorole_set.filter(role__nombre__icontains='supervisor').exists()
            except:
                return False
        context['is_admin_user'] = is_admin_user(self.request.user)
        # Si el usuario no tiene empleado, mostrar advertencia
        try:
            _ = self.request.user.empleado
            context['has_empleado'] = True
        except Exception:
            context['has_empleado'] = False

        # OPTIMIZACIÓN: Pre-cargar todas las jornadas en una sola consulta (evita N+1)
        empleados = context.get('empleados', [])
        empleados_jornadas = []

        if empleados:
            # Obtener IDs de empleados
            empleado_ids = [e.id for e in empleados]

            # Pre-cargar todas las asignaciones de jornada más recientes en una consulta
            # Usar subquery para obtener la asignación más reciente por empleado
            from django.db.models import OuterRef, Subquery
            asignaciones_recientes = AsignarJornadaExplorador.objects.filter(
                explorador_id=OuterRef('explorador_id')
            ).order_by('-fecha_inicio')[:1]

            # Obtener todas las asignaciones con select_related
            asignaciones = (
                AsignarJornadaExplorador.objects
                .filter(explorador_id__in=empleado_ids)
                .select_related('jornada', 'explorador')
                .order_by('explorador', '-fecha_inicio')
            )

            # Agrupar por explorador y tomar la más reciente
            jornadas_por_empleado = {}
            for asignacion in asignaciones:
                if asignacion.explorador_id not in jornadas_por_empleado:
                    jornadas_por_empleado[asignacion.explorador_id] = asignacion.jornada.nombre

            # Crear lista de tuplas (empleado, jornada)
            for empleado in empleados:
                jornada = jornadas_por_empleado.get(empleado.id, "-")
                empleados_jornadas.append((empleado, jornada))

        context['empleados_jornadas'] = empleados_jornadas
        return context

    def get_queryset(self):
        user = self.request.user

        # OPTIMIZACIÓN: Pre-cargar relaciones ManyToMany para evitar N+1 en el template
        # El template accede a: empleado.competenciaempleado_set.all y empleado.empleadorole_set.all
        base_queryset = (
            Empleado.objects
            .select_related('supervisor', 'user')
            .prefetch_related(
                'competenciaempleado_set__sala',  # Para acceder a competencia.sala.nombre
                'empleadorole_set__role',         # Para acceder a empleado_rol.role.nombre
            )
        )

        if user.is_superuser or user.is_staff:
            return base_queryset.all()

        if user.is_supervisor:
            return base_queryset.filter(
                empleadorole_set__role__nombre__icontains='supervisor'
            ).distinct()


        try:
            empleado = self.request.user.empleado
        except Exception:
            return Empleado.objects.none()

        # Mostrar todos los empleados si es admin o supervisor
        if self.request.user.is_staff or empleado.empleadorole_set.filter(role__nombre__icontains='supervisor').exists():
            query = self.request.GET.get('q', '')
            if query:
                # El servicio ya retorna queryset optimizado
                return EmpleadoService.buscar_empleados(query)
            return base_queryset.all()

        # Si no es admin/supervisor, filtrar por sala o mostrar ninguno
        sala_id = self.request.GET.get('sala')
        if sala_id:
            # El servicio ya retorna queryset optimizado
            return EmpleadoService.get_empleados_by_sala(sala_id)
        competencia = empleado.competenciaempleado_set.select_related('sala').first()
        if competencia:
            # El servicio ya retorna queryset optimizado
            return EmpleadoService.get_empleados_by_sala(competencia.sala_id)
        return Empleado.objects.none()

class EmpleadoDetailView(LoginRequiredMixin, DetailView):
    model = Empleado
    template_name = 'empleados/detail.html'

class EmpleadoEditForm(forms.ModelForm):
    jornada = forms.ModelChoiceField(queryset=Jornada.objects.all(), required=True, label="Jornada (AM/PM)", widget=forms.Select(attrs={'class': 'form-control'}))
    supervisor = forms.ModelChoiceField(
        queryset=Empleado.objects.filter(activo=True, empleadorole__role__nombre__icontains='supervisor').distinct(),
        required=False,
        label='Supervisor',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Opcional: Asignar un supervisor a este empleado (solo empleados con rol Supervisor)'
    )

    class Meta:
        model = Empleado
        fields = ['nombre', 'apellido', 'cedula', 'email', 'activo', 'supervisor']

    def __init__(self, *args, **kwargs):
        empleado = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        if empleado:
            from turnos.models import AsignarJornadaExplorador
            asignacion = AsignarJornadaExplorador.objects.filter(explorador=empleado).order_by('-fecha_inicio').first()
            self.fields['jornada'].initial = asignacion.jornada.id if asignacion else None

class EmpleadoEditView(LoginRequiredMixin, UpdateView):
    model = Empleado
    template_name = 'empleados/edit.html'
    form_class = EmpleadoEditForm
    success_url = '/empleados/'

    def form_valid(self, form):
        # Guardar el empleado
        empleado = form.save()

        # Actualizar la jornada
        jornada = form.cleaned_data['jornada']
        # Eliminar asignaciones anteriores
        AsignarJornadaExplorador.objects.filter(explorador=empleado).delete()
        # Crear nueva asignación
        AsignarJornadaExplorador.objects.create(
            explorador=empleado,
            jornada=jornada,
            fecha_inicio=timezone.now().date()
        )

        # Invalidar caché de MisTurnosPorMesView para este empleado
        try:
            from core.services.cache_service import CacheService
            anio_actual = timezone.now().year
            for anio in (anio_actual, anio_actual + 1):
                for mes in range(1, 13):
                    CacheService.invalidar_cache_turnos_empleado(empleado.id, mes, anio)
        except Exception:
            # Si algo falla al invalidar caché, no bloquear la actualización del empleado
            pass

        messages.success(self.request, 'Empleado actualizado correctamente.')
        return super().form_valid(form)

class EmpleadoDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Empleado
    template_name = 'empleados/confirm_delete.html'
    success_url = '/empleados/'  # Redirigir a la lista después de eliminar

class RestriccionesView(LoginRequiredMixin, TemplateView):
    template_name = 'empleados/placeholder.html'

class SeccionesView(LoginRequiredMixin, TemplateView):
    template_name = 'empleados/placeholder.html'

class JornadasView(LoginRequiredMixin, TemplateView):
    template_name = 'empleados/placeholder.html'

# Formulario personalizado para crear usuario, empleado, roles y salas
class EmpleadoUsuarioCreateView(LoginRequiredMixin, AdminRequiredMixin, View):
    template_name = 'empleados/create_usuario_empleado.html'
    form_class = EmpleadoUsuarioForm

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        from turnos.models import AsignarJornadaExplorador
        from datetime import date
        form = self.form_class(request.POST)
        if form.is_valid():
            usuario_existente = form.cleaned_data.get('usuario_existente')
            if usuario_existente:
                user = usuario_existente
            else:
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    password=form.cleaned_data['password'],
                    email=form.cleaned_data['email']
                )
            es_supervisor = form.es_supervisor()
            empleado = Empleado.objects.create(
                user=user,
                nombre=form.cleaned_data['nombre'],
                apellido=form.cleaned_data['apellido'],
                cedula=form.cleaned_data['cedula'],
                email=form.cleaned_data['email'],
                activo=form.cleaned_data['activo'],
                # Un supervisor no tiene supervisor asignado.
                supervisor=None if es_supervisor else form.cleaned_data.get('supervisor')
            )
            for rol in form.cleaned_data['roles']:
                EmpleadoRole.objects.create(empleado=empleado, role=rol)
            # Sala y jornada solo aplican a empleados normales (no supervisores).
            if not es_supervisor:
                for sala in form.cleaned_data.get('salas') or []:
                    CompetenciaEmpleado.objects.create(empleado=empleado, sala=sala)
                jornada = form.cleaned_data.get('jornada')
                if jornada:
                    AsignarJornadaExplorador.objects.create(
                        explorador=empleado,
                        jornada=jornada,
                        fecha_inicio=date.today()
                    )
            messages.success(request, 'Usuario y empleado creados correctamente.')
            return redirect('empleados')
        return render(request, self.template_name, {'form': form})

class AsignarRolesSalasForm(forms.Form):
    roles = forms.ModelMultipleChoiceField(queryset=Role.objects.all(), required=False)
    salas = forms.ModelMultipleChoiceField(queryset=Sala.objects.all(), required=False)

class AsignarRolesSalasView(LoginRequiredMixin, AdminRequiredMixin, View):
    template_name = 'empleados/asignar_roles_salas.html'
    form_class = AsignarRolesSalasForm

    def get(self, request, empleado_id):
        empleado = Empleado.objects.get(pk=empleado_id)
        roles_actuales = empleado.empleadorole_set.values_list('role_id', flat=True)
        salas_actuales = empleado.competenciaempleado_set.values_list('sala_id', flat=True)
        form = self.form_class(initial={
            'roles': roles_actuales,
            'salas': salas_actuales
        })
        return render(request, self.template_name, {'form': form, 'empleado': empleado})

    def post(self, request, empleado_id):
        empleado = Empleado.objects.get(pk=empleado_id)
        form = self.form_class(request.POST)
        if form.is_valid():
            # Actualizar roles
            EmpleadoRole.objects.filter(empleado=empleado).delete()
            for rol in form.cleaned_data['roles']:
                EmpleadoRole.objects.create(empleado=empleado, role=rol)
            # Actualizar salas
            CompetenciaEmpleado.objects.filter(empleado=empleado).delete()
            for sala in form.cleaned_data['salas']:
                CompetenciaEmpleado.objects.create(empleado=empleado, sala=sala)
            messages.success(request, 'Roles y salas actualizados correctamente.')
            return redirect('empleados')
        return render(request, self.template_name, {'form': form, 'empleado': empleado})


class ChangePasswordView(LoginRequiredMixin, AdminRequiredMixin, View):
    template_name = 'empleados/change_password.html'
    form_class = SetPasswordForm

    def get(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        form = self.form_class(user)
        return render(request, self.template_name, {
            'form': form,
            'target_user': user,
            'empleado': getattr(user, 'empleado', None)
        })

    def post(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        form = self.form_class(user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Contraseña actualizada correctamente para {user.username}.')
            return redirect(reverse_lazy('empleados'))
        return render(request, self.template_name, {
            'form': form,
            'target_user': user,
            'empleado': getattr(user, 'empleado', None)
        })
