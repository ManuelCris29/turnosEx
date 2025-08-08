from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, TemplateView
from django.views.generic.edit import CreateView, DeleteView
from django.core.exceptions import PermissionDenied
from .services.empleado_service import EmpleadoService
from .models import Empleado, Role, Sala, EmpleadoRole, CompetenciaEmpleado, Jornada, RestriccionEmpleado, SancionEmpleado
from permisos.models import PDH
from django import forms
from django.contrib.auth.models import User
from django.views import View
from django.shortcuts import redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.forms import SetPasswordForm
from django.urls import reverse_lazy
from turnos.models import AsignarJornadaExplorador
from django.utils import timezone
from .forms import SancionEmpleadoForm, RestriccionEmpleadoForm, JornadaForm, EmpleadoUsuarioForm

# Mixin personalizado para verificar permisos de administrador
class AdminRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        # Verificar si el usuario es staff o tiene rol de Supervisor
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        # Si es staff, permitir acceso
        if request.user.is_staff:
            return super().dispatch(request, *args, **kwargs)
        
        # Verificar si tiene rol de Supervisor
        try:
            empleado = request.user.empleado
            tiene_rol_supervisor = empleado.empleadorole_set.filter(role__nombre__icontains='supervisor').exists()
            if tiene_rol_supervisor:
                return super().dispatch(request, *args, **kwargs)
        except:
            pass
        
        # Si no cumple ninguna condición, denegar acceso
        raise PermissionDenied("No tienes permisos de administrador.")

# Create your views here.

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
        # Agregar jornadas actuales de cada empleado
        empleados = context.get('empleados', [])
        empleados_jornadas = []
        for empleado in empleados:
            asignacion = AsignarJornadaExplorador.objects.filter(explorador=empleado).order_by('-fecha_inicio').first()
            jornada = asignacion.jornada.nombre if asignacion else "-"
            empleados_jornadas.append((empleado, jornada))
        context['empleados_jornadas'] = empleados_jornadas
        return context
    
    def get_queryset(self):
        user = self.request.user

        if user.is_superuser or user.is_staff:
            return Empleado.objects.all()
        
        if user.is_supervisor:
            return Empleado.objects.filter(empleadorole_set__role__nombre__icontains='supervisor')
        
        
        try:
            empleado = self.request.user.empleado
        except Exception:
            return Empleado.objects.none()

        # Mostrar todos los empleados si es admin o supervisor
        if self.request.user.is_staff or empleado.empleadorole_set.filter(role__nombre__icontains='supervisor').exists():
            query = self.request.GET.get('q', '')
            if query:
                return EmpleadoService.buscar_empleados(query)
            return Empleado.objects.all()

        # Si no es admin/supervisor, filtrar por sala o mostrar ninguno
        sala_id = self.request.GET.get('sala')
        if sala_id:
            return EmpleadoService.get_empleados_by_sala(sala_id)
        competencia = empleado.competenciaempleado_set.first()
        if competencia:
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

#class RolesView(LoginRequiredMixin, TemplateView):
   # template_name = 'empleados/placeholder.html'

# CRUD de Roles
class RoleListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Role
    template_name = 'empleados/roles_list.html'
    context_object_name = 'roles'

class RoleCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Role
    template_name = 'empleados/roles_create.html'
    fields = ['nombre']
    success_url = reverse_lazy('roles_list')

class RoleUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Role
    template_name = 'empleados/roles_edit.html'
    fields = ['nombre']
    success_url = reverse_lazy('roles_list')

class RoleDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Role
    template_name = 'empleados/roles_confirm_delete.html'
    success_url = reverse_lazy('roles_list')

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
            empleado = Empleado.objects.create(
                user=user,
                nombre=form.cleaned_data['nombre'],
                apellido=form.cleaned_data['apellido'],
                cedula=form.cleaned_data['cedula'],
                email=form.cleaned_data['email'],
                activo=form.cleaned_data['activo'],
                supervisor=form.cleaned_data.get('supervisor')  # Agregar supervisor
            )
            for rol in form.cleaned_data['roles']:
                EmpleadoRole.objects.create(empleado=empleado, role=rol)
            for sala in form.cleaned_data['salas']:
                CompetenciaEmpleado.objects.create(empleado=empleado, sala=sala)
            jornada = form.cleaned_data['jornada']
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

# CRUD de Salas
class SalaListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Sala
    template_name = 'empleados/salas_list.html'
    context_object_name = 'salas'

class SalaCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Sala
    template_name = 'empleados/salas_create.html'
    fields = ['nombre', 'activo']
    success_url = '/empleados/salas/'

class SalaUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Sala
    template_name = 'empleados/salas_edit.html'
    fields = ['nombre', 'activo']
    success_url = '/empleados/salas/'

class SalaDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Sala
    template_name = 'empleados/salas_confirm_delete.html'
    success_url = '/empleados/salas/'

# CRUD de Jornadas
class JornadaListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    model = Jornada
    template_name = 'empleados/jornadas_list.html'
    context_object_name = 'jornadas'

class JornadaCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = Jornada
    form_class = JornadaForm
    template_name = 'empleados/jornadas_create.html'
    success_url = '/empleados/jornadas/'

class JornadaUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = Jornada
    form_class = JornadaForm
    template_name = 'empleados/jornadas_edit.html'
    success_url = '/empleados/jornadas/'

class JornadaDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = Jornada
    template_name = 'empleados/jornadas_confirm_delete.html'
    success_url = '/empleados/jornadas/'

# CRUD de Restricciones
class RestriccionListView(LoginRequiredMixin, ListView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_list.html'
    context_object_name = 'restricciones'

class RestriccionCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = RestriccionEmpleado
    form_class = RestriccionEmpleadoForm
    template_name = 'empleados/restricciones_create.html'
    success_url = '/empleados/restricciones/'

class RestriccionUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = RestriccionEmpleado
    form_class = RestriccionEmpleadoForm
    template_name = 'empleados/restricciones_edit.html'
    success_url = '/empleados/restricciones/'

class RestriccionDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_confirm_delete.html'
    success_url = '/empleados/restricciones/'

# CRUD de Sanciones
class SancionListView(LoginRequiredMixin, ListView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_list.html'
    context_object_name = 'sanciones'

class SancionCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = SancionEmpleado
    form_class = SancionEmpleadoForm
    template_name = 'empleados/sanciones_create.html'
    success_url = '/empleados/sanciones/'

class SancionUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = SancionEmpleado
    form_class = SancionEmpleadoForm
    template_name = 'empleados/sanciones_edit.html'
    success_url = '/empleados/sanciones/'

class SancionDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_confirm_delete.html'
    success_url = '/empleados/sanciones/'

# CRUD de PDH (Pago de Horas)
class PDHListView(LoginRequiredMixin, ListView):
    model = PDH
    template_name = 'empleados/pdh_list.html'
    context_object_name = 'pdhs'

class PDHCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = PDH
    template_name = 'empleados/pdh_create.html'
    fields = ['empleado', 'fecha', 'horas', 'monto', 'estado']
    success_url = '/empleados/pdh/'

class PDHUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = PDH
    template_name = 'empleados/pdh_edit.html'
    fields = ['empleado', 'fecha', 'horas', 'monto', 'estado']
    success_url = '/empleados/pdh/'

class PDHDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = PDH
    template_name = 'empleados/pdh_confirm_delete.html'
    success_url = '/empleados/pdh/'

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

# Vistas solo visualización para Consultas Rápidas
class PDHVisualizarListView(LoginRequiredMixin, ListView):
    model = PDH
    template_name = 'empleados/pdh_visualizar_list.html'
    context_object_name = 'pdhs'

class SancionVisualizarListView(LoginRequiredMixin, ListView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_visualizar_list.html'
    context_object_name = 'sanciones'

class RestriccionVisualizarListView(LoginRequiredMixin, ListView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_visualizar_list.html'
    context_object_name = 'restricciones'
