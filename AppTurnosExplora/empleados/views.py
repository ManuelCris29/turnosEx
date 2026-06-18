from django.shortcuts import render
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, DetailView, UpdateView, TemplateView
from django.views.generic.edit import CreateView, DeleteView
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
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
from .forms import SancionEmpleadoForm, RestriccionEmpleadoForm, JornadaForm, EmpleadoUsuarioForm, PDHForm

# Importar mixin común desde core
from core.mixins import AdminRequiredMixin

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

    def _base_queryset(self):
        qs = (
            RestriccionEmpleado.objects
            .select_related('empleado')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if user.is_staff:
            eid = self.request.GET.get('explorador')
            if eid and str(eid).isdigit():
                qs = qs.filter(empleado_id=eid)
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(empleado=empleado)

    def get_queryset(self):
        return self._base_queryset()

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        context = super().get_context_data(**kwargs)
        queryset = self._base_queryset()
        user = self.request.user
        hoy = timezone.now().date()
        
        # Calcular totales usando el queryset base
        # Activa: fecha_fin es NULL o fecha_fin >= hoy
        # Finalizada: fecha_fin < hoy
        total_restricciones = queryset.count()
        total_activos = queryset.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizados = queryset.filter(fecha_fin__lt=hoy).count()
        
        context.update({
            'es_supervisor': user.is_staff,
            'empleado_actual': getattr(user, 'empleado', None) if not user.is_staff else None,
            'total_restricciones': total_restricciones,
            'total_activos': total_activos,
            'total_finalizados': total_finalizados,
            'totales_por_tipo': queryset.values('tipo_restriccion').annotate(total=Count('id')).order_by('-total'),
            'hoy': hoy
        })
        if user.is_staff:
            context['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
            context['filtro_explorador'] = self.request.GET.get('explorador', '')
        
        if not user.is_staff and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver restricciones.')
        
        return context

def _invalidar_turnos_cache_restriccion(restriccion):
    """Refresca Mis Turnos del empleado para que la restricción se vea al instante."""
    try:
        from datetime import timedelta, date as _date
        from core.services.cache_service import CacheService
        fin = restriccion.fecha_fin or (restriccion.fecha_inicio + timedelta(days=365))
        meses = set()
        d = restriccion.fecha_inicio
        while d <= fin:
            meses.add((d.month, d.year))
            d += timedelta(days=28)
        meses.add((fin.month, fin.year))
        for m, y in meses:
            CacheService.invalidar_cache_turnos_empleado(restriccion.empleado.id, m, y)
    except Exception:
        pass


class RestriccionCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = RestriccionEmpleado
    form_class = RestriccionEmpleadoForm
    template_name = 'empleados/restricciones_create.html'
    success_url = '/empleados/restricciones/'

    def form_valid(self, response):
        resp = super().form_valid(response)
        _invalidar_turnos_cache_restriccion(self.object)
        return resp

class RestriccionUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = RestriccionEmpleado
    form_class = RestriccionEmpleadoForm
    template_name = 'empleados/restricciones_edit.html'
    success_url = '/empleados/restricciones/'

    def form_valid(self, response):
        resp = super().form_valid(response)
        _invalidar_turnos_cache_restriccion(self.object)
        return resp

class RestriccionDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_confirm_delete.html'
    success_url = '/empleados/restricciones/'

    def form_valid(self, form):
        _invalidar_turnos_cache_restriccion(self.get_object())
        return super().form_valid(form)

# CRUD de Sanciones
class SancionListView(LoginRequiredMixin, ListView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_list.html'
    context_object_name = 'sanciones'

    def _base_queryset(self):
        qs = (
            SancionEmpleado.objects
            .select_related('explorador', 'supervisor')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if user.is_staff:
            eid = self.request.GET.get('explorador')
            if eid and str(eid).isdigit():
                qs = qs.filter(explorador_id=eid)
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(explorador=empleado)

    def get_queryset(self):
        return self._base_queryset()

    def get_context_data(self, **kwargs):
        from django.db.models import Q
        context = super().get_context_data(**kwargs)
        queryset = self._base_queryset()
        user = self.request.user
        hoy = timezone.now().date()

        total_sanciones = queryset.count()
        total_activas = queryset.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizadas = queryset.filter(fecha_fin__lt=hoy).count()

        context.update({
            'es_supervisor': user.is_staff,
            'empleado_actual': getattr(user, 'empleado', None) if not user.is_staff else None,
            'total_sanciones': total_sanciones,
            'total_activas': total_activas,
            'total_finalizadas': total_finalizadas,
            'hoy': hoy
        })
        if user.is_staff:
            context['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
            context['filtro_explorador'] = self.request.GET.get('explorador', '')
        
        if not user.is_staff and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver sanciones.')
        
        return context

def _invalidar_turnos_cache_sancion(sancion):
    """Refresca Mis Turnos del explorador para que la sanción se vea al instante."""
    try:
        from datetime import timedelta
        from core.services.cache_service import CacheService
        fin = sancion.fecha_fin or (sancion.fecha_inicio + timedelta(days=365))
        meses = set()
        d = sancion.fecha_inicio
        while d <= fin:
            meses.add((d.month, d.year))
            d += timedelta(days=28)
        meses.add((fin.month, fin.year))
        for m, y in meses:
            CacheService.invalidar_cache_turnos_empleado(sancion.explorador.id, m, y)
    except Exception:
        pass


class SancionCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = SancionEmpleado
    form_class = SancionEmpleadoForm
    template_name = 'empleados/sanciones_create.html'
    success_url = '/empleados/sanciones/'

    def form_valid(self, response):
        resp = super().form_valid(response)
        _invalidar_turnos_cache_sancion(self.object)
        return resp

class SancionUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = SancionEmpleado
    form_class = SancionEmpleadoForm
    template_name = 'empleados/sanciones_edit.html'
    success_url = '/empleados/sanciones/'

    def form_valid(self, response):
        resp = super().form_valid(response)
        _invalidar_turnos_cache_sancion(self.object)
        return resp

class SancionDeleteView(LoginRequiredMixin, AdminRequiredMixin, DeleteView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_confirm_delete.html'
    success_url = '/empleados/sanciones/'

    def form_valid(self, form):
        _invalidar_turnos_cache_sancion(self.get_object())
        return super().form_valid(form)

class IndicadoresView(LoginRequiredMixin, AdminRequiredMixin, TemplateView):
    """Panel de indicadores/KPIs para supervisores."""
    template_name = 'empleados/indicadores.html'

    def get_context_data(self, **kwargs):
        import json
        from .services.indicadores_service import IndicadoresService
        ctx = super().get_context_data(**kwargs)
        explorador = self.request.GET.get('explorador') or None
        jornada = self.request.GET.get('jornada') or None
        anio_raw = self.request.GET.get('anio')
        anio = int(anio_raw) if anio_raw and str(anio_raw).isdigit() else None

        data = IndicadoresService.get(explorador_id=explorador, jornada=jornada, anio=anio)
        ctx.update(data)
        ctx['exploradores'] = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
        ctx['anios'] = IndicadoresService.anios_disponibles()
        ctx['filtro_explorador'] = explorador or ''
        ctx['filtro_jornada'] = jornada or ''
        ctx['chart_series_json'] = json.dumps(data['chart_series'])
        ctx['meses_json'] = json.dumps(data['meses_nombres'])
        return ctx


# CRUD de PDH (Pago de Horas)
class PDHListView(LoginRequiredMixin, AdminRequiredMixin, ListView):
    """Administración: el supervisor/admin ve y gestiona todos los pagos de horas."""
    model = PDH
    template_name = 'empleados/pdh_list.html'
    context_object_name = 'pdhs'

    def get_queryset(self):
        return (
            PDH.objects.filter(tipo_registro='pago_horas')
            .select_related('explorador', 'supervisor')
            .order_by('-fecha', '-id')
        )

class PDHCreateView(LoginRequiredMixin, AdminRequiredMixin, CreateView):
    model = PDH
    form_class = PDHForm
    template_name = 'empleados/pdh_create.html'
    success_url = '/empleados/pdh/'

    def form_valid(self, form):
        # El supervisor que registra es quien autoriza el pago.
        form.instance.supervisor = self.request.user.empleado
        form.instance.tipo_registro = 'pago_horas'
        messages.success(
            self.request,
            f'Pago de {form.instance.horas} h registrado para '
            f'{form.instance.explorador.nombre} {form.instance.explorador.apellido}. '
            'Se descuenta de su consolidado de horas.'
        )
        return super().form_valid(form)

class PDHUpdateView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    model = PDH
    form_class = PDHForm
    template_name = 'empleados/pdh_edit.html'
    success_url = '/empleados/pdh/'

    def form_valid(self, form):
        form.instance.tipo_registro = 'pago_horas'
        return super().form_valid(form)

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
    """Consulta: admin/supervisor ve todos los pagos; el explorador solo los suyos."""
    model = PDH
    template_name = 'empleados/pdh_visualizar_list.html'
    context_object_name = 'pdhs'

    def get_queryset(self):
        from turnos.services.consolidado_horas_service import ConsolidadoHorasService
        qs = (
            PDH.objects.filter(tipo_registro='pago_horas')
            .select_related('explorador', 'supervisor')
            .order_by('-fecha', '-id')
        )
        user = self.request.user
        if ConsolidadoHorasService.es_supervisor(user):
            return qs
        empleado = getattr(user, 'empleado', None)
        return qs.filter(explorador=empleado) if empleado else qs.none()

    def get_context_data(self, **kwargs):
        from turnos.services.consolidado_horas_service import ConsolidadoHorasService
        context = super().get_context_data(**kwargs)
        context['es_supervisor'] = ConsolidadoHorasService.es_supervisor(self.request.user)
        return context

class SancionVisualizarListView(LoginRequiredMixin, ListView):
    model = SancionEmpleado
    template_name = 'empleados/sanciones_visualizar_list.html'
    context_object_name = 'sanciones'

    def _base_queryset(self):
        qs = (
            SancionEmpleado.objects
            .select_related('explorador', 'supervisor')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if user.is_staff:
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(explorador=empleado)

    def get_queryset(self):
        return self._base_queryset()
    
    def get_context_data(self, **kwargs):
        from django.db.models import Q
        from django.utils import timezone
        context = super().get_context_data(**kwargs)
        user = self.request.user
        hoy = timezone.now().date()
        
        # Obtener queryset base (ya filtrado por explorador si es necesario)
        queryset = self._base_queryset()
        
        # Calcular totales usando el queryset filtrado
        # Activa: fecha_fin es NULL o fecha_fin >= hoy
        # Finalizada: fecha_fin < hoy
        total_activas = queryset.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizadas = queryset.filter(fecha_fin__lt=hoy).count()
        
        context.update({
            'es_supervisor': user.is_staff,
            'empleado_actual': getattr(user, 'empleado', None) if not user.is_staff else None,
            'hoy': hoy,
            'total_activas': total_activas,
            'total_finalizadas': total_finalizadas
        })
        
        if not user.is_staff and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver sanciones.')
        
        return context

class RestriccionVisualizarListView(LoginRequiredMixin, ListView):
    model = RestriccionEmpleado
    template_name = 'empleados/restricciones_visualizar_list.html'
    context_object_name = 'restricciones'

    def _base_queryset(self):
        qs = (
            RestriccionEmpleado.objects
            .select_related('empleado')
            .order_by('-fecha_inicio', '-id')
        )
        user = self.request.user
        if user.is_staff:
            eid = self.request.GET.get('explorador')
            if eid and str(eid).isdigit():
                qs = qs.filter(empleado_id=eid)
            return qs
        empleado = getattr(user, 'empleado', None)
        if not empleado:
            return qs.none()
        return qs.filter(empleado=empleado)

    def get_queryset(self):
        return self._base_queryset()
    
    def get_context_data(self, **kwargs):
        from django.db.models import Q
        from django.utils import timezone
        context = super().get_context_data(**kwargs)
        user = self.request.user
        hoy = timezone.now().date()
        
        # Obtener queryset base (ya filtrado por empleado si es necesario)
        queryset = self._base_queryset()
        
        # Calcular totales usando el queryset filtrado
        # Activa: fecha_fin es NULL o fecha_fin >= hoy
        # Finalizada: fecha_fin < hoy
        total_activos = queryset.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=hoy)).count()
        total_finalizados = queryset.filter(fecha_fin__lt=hoy).count()
        
        context.update({
            'es_supervisor': user.is_staff,
            'empleado_actual': getattr(user, 'empleado', None) if not user.is_staff else None,
            'hoy': hoy,
            'total_activos': total_activos,
            'total_finalizados': total_finalizados
        })
        
        if not user.is_staff and not getattr(user, 'empleado', None):
            messages.warning(self.request, 'Tu usuario no está asociado a un empleado, por lo que no puedes ver restricciones.')
        
        return context

