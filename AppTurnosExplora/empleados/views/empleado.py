import logging

from django import forms
from django.contrib import messages
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import DetailView, ListView, UpdateView

from core.mixins import AdminRequiredMixin, es_supervisor
from turnos.models import AsignarJornadaExplorador

from ..forms import EmpleadoUsuarioForm
from ..models import CompetenciaEmpleado, Empleado, EmpleadoRole, Jornada, Role, Sala
from ..services.empleado_service import EmpleadoService

logger = logging.getLogger(__name__)


class EmpleadoListView(LoginRequiredMixin, ListView):
    template_name = 'empleados/lista.html'
    context_object_name = 'empleados'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Misma definición que el resto del sistema: staff o rol Supervisor exacto.
        context['is_admin_user'] = es_supervisor(self.request.user)
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

        # Staff y rol Supervisor ven la plantilla completa. Antes había aquí una
        # rama `user.is_supervisor`, atributo que el User de Django no tiene: al
        # entrar un supervisor sin `is_staff` reventaba antes de llegar al
        # criterio correcto de más abajo.
        if es_supervisor(user):
            query = self.request.GET.get('q', '')
            if query:
                # El servicio ya retorna queryset optimizado
                return EmpleadoService.buscar_empleados(query)
            return base_queryset.all()

        try:
            empleado = self.request.user.empleado
        except Exception:
            return Empleado.objects.none()

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
    """Ficha de un explorador: datos, jornada vigente, salas y roles.

    La jornada no vive en ``Empleado`` sino en la última asignación de
    ``AsignarJornadaExplorador``, así que la resuelve la vista: la plantilla
    no puede ordenar por ``-fecha_inicio``.
    """
    model = Empleado
    template_name = 'empleados/detail.html'

    def get_queryset(self):
        return (
            Empleado.objects
            .select_related('user', 'supervisor')
            .prefetch_related('empleadorole_set__role', 'competenciaempleado_set__sala')
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        asignacion = (
            AsignarJornadaExplorador.objects
            .select_related('jornada')
            .filter(explorador=self.object)
            .order_by('-fecha_inicio')
            .first()
        )
        context['jornada_actual'] = asignacion.jornada if asignacion else None
        context['supervisados'] = self.object.empleados_supervisados.filter(activo=True)
        return context

class EmpleadoEditForm(forms.ModelForm):
    """
    Edita la ficha del empleado y, con ella, el `username` de su cuenta.

    El `username` no es un campo de `Empleado`: vive en el `User` con el que
    tiene un OneToOne. Por eso se declara aquí a mano y se guarda aparte en
    `save()`; sin esto el administrador podía crear un explorador con el usuario
    mal escrito y no tenia forma de corregirlo desde la aplicacion.

    Cambiarlo cambia la credencial con la que esa persona entra: no hay alias ni
    redireccion del antiguo. Es deliberado — el `username` es el identificador de
    login, no un apodo — y por eso el campo lo dice en su `help_text`.
    """
    username = forms.CharField(
        label='Usuario',
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        help_text='Con este nombre inicia sesion el empleado. Si lo cambias, deberá entrar con el nuevo.'
    )
    email = forms.EmailField(
        label='Email',
        max_length=254,
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'}),
        help_text='Recibe aqui los avisos de solicitudes y el restablecimiento de contrasena.'
    )
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
        fields = ['nombre', 'apellido', 'cedula', 'activo', 'supervisor']

    # Los campos declarados se anaden al final; sin esto 'Usuario' quedaria
    # suelto tras 'Jornada', lejos de los datos de identidad a los que pertenece.
    field_order = ['nombre', 'apellido', 'cedula', 'username', 'email', 'activo', 'supervisor', 'jornada']

    def __init__(self, *args, **kwargs):
        empleado = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        if empleado:
            from turnos.models import AsignarJornadaExplorador
            asignacion = AsignarJornadaExplorador.objects.filter(explorador=empleado).order_by('-fecha_inicio').first()
            self.fields['jornada'].initial = asignacion.jornada.id if asignacion else None
            if empleado.user_id:
                self.fields['username'].initial = empleado.user.username
                self.fields['email'].initial = empleado.user.email

    def clean_username(self):
        """
        La unicidad se comprueba aqui y no solo en la base: la restriccion UNIQUE
        de `auth_user` existe, pero llegar hasta ella devuelve un 500 en vez de
        marcar el campo en rojo. Se excluye el propio usuario para que guardar sin
        tocar el campo no se acuse a si mismo de duplicado.
        """
        username = (self.cleaned_data.get('username') or '').strip()
        otros = User.objects.filter(username=username)
        if self.instance and self.instance.user_id:
            otros = otros.exclude(pk=self.instance.user_id)
        if otros.exists():
            raise forms.ValidationError('Ese usuario ya existe. Elige otro.')
        return username

    def save(self, commit=True):
        """
        `username` y `email` no son campos de `Empleado`: los dos viven en el
        `User` con el que tiene un OneToOne (el email desde la migracion 0010,
        que elimino la copia duplicada; ver `Empleado.email`). Por eso se
        declaran a mano arriba y se persisten aqui.

        Solo se escribe lo que cambio: un save() del User en cada edicion
        generaria ruido en auditoria y tocaria la fila sin motivo.
        """
        empleado = super().save(commit=commit)
        if not (commit and empleado.user_id):
            return empleado

        user = empleado.user
        cambios = []

        username = self.cleaned_data.get('username')
        if username and user.username != username:
            user.username = username
            cambios.append('username')

        email = self.cleaned_data.get('email') or ''
        if user.email != email:
            user.email = email
            cambios.append('email')

        if cambios:
            user.save(update_fields=cambios)
        return empleado

class EmpleadoEditView(LoginRequiredMixin, AdminRequiredMixin, UpdateView):
    """
    Edita la ficha de un explorador. Solo administración y supervisores.

    `AdminRequiredMixin` NO estaba, y sus vistas hermanas (`EmpleadoBajaView`,
    `EmpleadoUsuarioCreateView`, `AsignarRolesSalasView`) sí lo tienen: fue un
    olvido, no una decisión. Sin él, cualquier explorador con sesión podía hacer
    POST a /empleados/edit/<id>/ y cambiar la ficha de CUALQUIER compañero —
    nombre, cédula, email, supervisor y el campo `activo`, con el que se puede
    dejar a otro fuera del sistema.

    Además abría una vía de XSS: el nombre se interpola sin escapar en varios
    `innerHTML` del formulario de cambio de descanso, así que un nombre con
    `<img src=x onerror=...>` se ejecutaba en el navegador de quien lo abriera,
    supervisor incluido. La CSP del proyecto no lo frena, porque `script-src`
    lleva 'unsafe-inline'.
    """
    model = Empleado
    template_name = 'empleados/edit.html'
    form_class = EmpleadoEditForm
    success_url = '/empleados/'

    def form_valid(self, form):
        # Ficha, cuenta y jornada se guardan como una sola unidad: si falla la
        # jornada no puede quedar el username ya cambiado.
        with transaction.atomic():
            empleado = form.save()

            jornada = form.cleaned_data['jornada']
            # Eliminar asignaciones anteriores
            AsignarJornadaExplorador.objects.filter(explorador=empleado).delete()
            # Crear nueva asignación
            AsignarJornadaExplorador.objects.create(
                explorador=empleado,
                jornada=jornada,
                fecha_inicio=timezone.localdate()
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
            logger.warning("Error invalidando caché de turnos (empleado=%s)", empleado.id, exc_info=True)

        messages.success(self.request, 'Empleado actualizado correctamente.')
        return super().form_valid(form)

class EmpleadoBajaView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Da de baja a un empleado: conserva la ficha y le CORTA el acceso.

    POR QUE YA NO SE BORRA
    ----------------------
    Antes esto era un `DeleteView` sobre `Empleado`. `Empleado.user` es un
    OneToOne con `on_delete=CASCADE`, y ese cascade va en un solo sentido:
    borrar el `User` arrastra su `Empleado`, pero borrar el `Empleado` deja el
    `User` intacto. Resultado: "eliminar empleado" borraba la ficha y dejaba la
    cuenta viva y activa.

    Se descubrio porque un usuario dado de baja siguio recibiendo correos de
    recuperacion de contraseña. El correo era el sintoma; el problema real es que
    esa cuenta TAMBIEN podia seguir entrando en la aplicacion — comprobado: login
    302 al dashboard, que respondia 200. En produccion eso significa que quien
    sale de la organizacion conserva su acceso.

    Dar de baja en vez de borrar resuelve las dos cosas y ademas conserva el
    historial (`simple_history`, solicitudes pasadas, auditoria), que un borrado
    fisico se llevaria por delante. El borrado real queda solo en /admin/, para
    superusuarios.

    La revocacion no se escribe aqui: basta con `activo=False`, porque
    `Empleado.save()` sincroniza `User.is_active`. Django invalida ademas las
    sesiones ya abiertas en cuanto la cuenta deja de estar activa, asi que no
    hace falta cerrarlas a mano.
    """

    template_name = 'empleados/confirm_baja.html'

    def get(self, request, pk):
        return render(request, self.template_name, {'object': get_object_or_404(Empleado, pk=pk)})

    def post(self, request, pk):
        empleado = get_object_or_404(Empleado, pk=pk)

        # Darse de baja a uno mismo deja la pantalla sin administrador y expulsa
        # a quien acaba de pulsar el boton.
        if empleado.user_id == request.user.id:
            messages.error(request, 'No puedes darte de baja a ti mismo.')
            return redirect('empleados')

        empleado.activo = False
        empleado.save()
        logger.info('EMPLEADO_BAJA empleado_id=%s por_user_id=%s', empleado.id, request.user.id)
        messages.success(
            request,
            f'{empleado.nombre} {empleado.apellido} quedo dado de baja y ya no puede entrar.',
        )
        return redirect('empleados')


class EmpleadoReingresoView(LoginRequiredMixin, AdminRequiredMixin, View):
    """Deshace una baja y devuelve el acceso.

    Sin esto, corregir una baja equivocada obligaria a entrar a /admin/, que es
    justo lo que la pantalla de empleados trata de evitar.
    """

    def post(self, request, pk):
        empleado = get_object_or_404(Empleado, pk=pk)
        empleado.activo = True
        empleado.save()
        logger.info('EMPLEADO_REINGRESO empleado_id=%s por_user_id=%s', empleado.id, request.user.id)
        messages.success(
            request,
            f'{empleado.nombre} {empleado.apellido} fue reingresado y ya puede entrar.',
        )
        return redirect('empleados')

# Formulario personalizado para crear usuario, empleado, roles y salas
class EmpleadoUsuarioCreateView(LoginRequiredMixin, AdminRequiredMixin, View):
    template_name = 'empleados/create_usuario_empleado.html'
    form_class = EmpleadoUsuarioForm

    def get(self, request):
        form = self.form_class()
        return render(request, self.template_name, {'form': form})

    def post(self, request):
        from turnos.models import AsignarJornadaExplorador
        form = self.form_class(request.POST)
        if form.is_valid():
            usuario_existente = form.cleaned_data.get('usuario_existente')
            email = form.cleaned_data.get('email') or ''
            if usuario_existente:
                user = usuario_existente
                # Reutilizar una cuenta no debe dejarla con el correo de su vida
                # anterior: el que se indica al dar de alta es el que vale, y
                # desde la migracion 0010 es el unico que existe.
                if email and user.email != email:
                    user.email = email
                    user.save(update_fields=['email'])
            else:
                user = User.objects.create_user(
                    username=form.cleaned_data['username'],
                    password=form.cleaned_data['password'],
                    email=email
                )
            es_supervisor = form.es_supervisor()
            empleado = Empleado.objects.create(
                user=user,
                nombre=form.cleaned_data['nombre'],
                apellido=form.cleaned_data['apellido'],
                cedula=form.cleaned_data['cedula'],
                # El email NO se pasa aqui: ya quedo guardado en `user`, que es
                # donde vive (`Empleado.email` solo lo lee de ahi).
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
                        fecha_inicio=timezone.localdate()
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
