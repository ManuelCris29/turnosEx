from django import forms
from django.contrib.auth.models import User
from .models import SancionEmpleado, Empleado, Role, RestriccionEmpleado, Jornada, Sala

class SancionEmpleadoForm(forms.ModelForm):
    """
    El supervisor que sanciona no se elige: es siempre quien registra la sanción
    (lo fija la vista). Al editar se conserva el supervisor original para no
    perder la trazabilidad de quién impuso la sanción.
    """
    INDEFINIDA = 'indefinida'
    OTRO = 'otro'
    DURACION_CHOICES = [
        ('15', '15 días'), ('30', '30 días'), ('45', '45 días'),
        ('60', '60 días'), ('90', '90 días'),
        (OTRO, 'Otro (personalizado)'),
        (INDEFINIDA, 'Indefinida (sin fecha de fin)'),
    ]
    fecha_inicio = forms.DateField(
        label='Fecha de inicio',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    duracion = forms.ChoiceField(
        label='Duración de la sanción', choices=DURACION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    dias_personalizado = forms.IntegerField(
        label='Días (personalizado)', required=False, min_value=1,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 20'})
    )

    class Meta:
        model = SancionEmpleado
        fields = ['explorador', 'fecha_inicio', 'motivo']

    def clean(self):
        from datetime import timedelta
        from django.db.models import Q

        cleaned = super().clean()
        fi = cleaned.get('fecha_inicio')
        dur = cleaned.get('duracion')

        # Una sanción indefinida no tiene fecha de fin; el resto se calcula
        # de forma inclusiva: 15 días desde el 1 → termina el 15.
        ff = None
        if dur == self.INDEFINIDA:
            cleaned['_fecha_fin'] = None
        else:
            dias = None
            if dur == self.OTRO:
                dias = cleaned.get('dias_personalizado')
                if not dias or dias <= 0:
                    self.add_error('dias_personalizado', 'Indica cuántos días dura la sanción.')
            elif dur:
                dias = int(dur)
            if fi and dias:
                ff = fi + timedelta(days=dias - 1)
                cleaned['_fecha_fin'] = ff

        if fi and ff and ff < fi:
            self.add_error('fecha_inicio', 'La fecha de fin debe ser posterior a la fecha de inicio.')

        explorador = cleaned.get('explorador')
        if explorador and self.supervisor_actual and explorador == self.supervisor_actual:
            self.add_error('explorador', 'Un empleado no puede sancionarse a sí mismo.')

        # Sin solapamientos: dos sanciones activas a la vez sobre el mismo
        # explorador harían que los totales y la vigencia mostrada mintieran.
        # Las LEVANTADAS no estorban: ya no bloquean a nadie, y exigir que no se
        # solapen impediría volver a sancionar por un hecho nuevo dentro de un rango
        # que en la práctica terminó.
        if explorador and fi and not self.errors:
            otras = SancionEmpleado.objects.filter(explorador=explorador, levantada_en__isnull=True)
            if self.instance.pk:
                otras = otras.exclude(pk=self.instance.pk)
            # Solapan si empiezan antes de que esta acabe y acaban después de que esta empiece.
            if ff is not None:
                otras = otras.filter(fecha_inicio__lte=ff)
            otras = otras.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fi))
            existente = otras.order_by('-fecha_inicio').first()
            if existente:
                fin_txt = existente.fecha_fin.strftime('%d/%m/%Y') if existente.fecha_fin else 'indefinida'
                self.add_error(None, (
                    f'Este explorador ya tiene una sanción del '
                    f'{existente.fecha_inicio.strftime("%d/%m/%Y")} al {fin_txt}, '
                    'que se solapa con el rango indicado. Edita la existente o levántala.'
                ))

        return cleaned

    def save(self, commit=True):
        instancia = super().save(commit=False)
        instancia.fecha_fin = self.cleaned_data.get('_fecha_fin')
        if not instancia.supervisor_id and self.supervisor_actual:
            instancia.supervisor = self.supervisor_actual
        if commit:
            instancia.save()
        return instancia

    def __init__(self, *args, supervisor=None, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        # El supervisor de una sanción ya registrada no cambia al editarla.
        self.supervisor_actual = inst.supervisor if inst.pk and inst.supervisor_id else supervisor

        # Al editar, precargar la duración a partir del rango existente
        if inst.pk and inst.fecha_inicio:
            if inst.fecha_fin is None:
                self.fields['duracion'].initial = self.INDEFINIDA
            else:
                dias = (inst.fecha_fin - inst.fecha_inicio).days + 1
                if str(dias) in dict(self.DURACION_CHOICES):
                    self.fields['duracion'].initial = str(dias)
                else:
                    self.fields['duracion'].initial = self.OTRO
                    self.fields['dias_personalizado'].initial = dias

        # Solo exploradores activos; al editar se conserva el ya sancionado
        # aunque haya sido dado de baja, para que el formulario siga siendo válido.
        explorador_role = Role.objects.filter(nombre__iexact=Role.EXPLORADOR).first()
        if explorador_role is not None:
            from django.db.models import Q
            qs = Empleado.objects.filter(empleadorole__role=explorador_role)
            filtro_activos = Q(activo=True)
            if inst.pk and inst.explorador_id:
                filtro_activos |= Q(pk=inst.explorador_id)
            self.fields['explorador'].queryset = (
                qs.filter(filtro_activos).distinct().order_by('apellido', 'nombre')
            )
        else:
            self.fields['explorador'].queryset = Empleado.objects.none()

class SancionLevantarForm(forms.Form):
    """
    Levantar una sanción antes de su fecha de fin.

    El motivo es OBLIGATORIO y con un mínimo real de contenido: es el único dato que
    convierte el historial en algo útil. Sin él solo queda constancia de que alguien
    la levantó, que es justo lo que no sirve cuando hay que revisar el caso meses
    después. Es también la vía para corregir una sanción mal puesta (motivo: "creada
    por error"), ya que las sanciones no se borran.
    """
    MIN_MOTIVO = 10

    motivo = forms.CharField(
        label='Motivo del levantamiento',
        widget=forms.Textarea(attrs={
            'class': 'form-control', 'rows': 3,
            'placeholder': 'Ej: pagó la deuda de horas / creada por error, no era este explorador',
        }),
    )

    def clean_motivo(self):
        motivo = (self.cleaned_data.get('motivo') or '').strip()
        if len(motivo) < self.MIN_MOTIVO:
            raise forms.ValidationError(
                f'Explica por qué levantas la sanción (mínimo {self.MIN_MOTIVO} caracteres). '
                'Queda registrado en el historial.'
            )
        return motivo


class RestriccionEmpleadoForm(forms.ModelForm):
    fecha_inicio = forms.DateField(
        label='Fecha de inicio',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    # El modelo y Mis Turnos ya tratan fecha_fin nula como "indefinida"; el
    # formulario lo hace explícito en vez de exigir siempre una fecha de fin.
    fecha_fin = forms.DateField(
        label='Fecha de fin',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False
    )
    indefinida = forms.BooleanField(
        label='Indefinida (sin fecha de fin)', required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        if inst.pk and inst.fecha_inicio and inst.fecha_fin is None:
            self.fields['indefinida'].initial = True

        # Solo empleados activos; al editar se conserva el ya restringido aunque
        # haya sido dado de baja, para que el formulario siga siendo válido.
        from django.db.models import Q
        filtro = Q(activo=True)
        if inst.pk and inst.empleado_id:
            filtro |= Q(pk=inst.empleado_id)
        self.fields['empleado'].queryset = (
            Empleado.objects.filter(filtro).order_by('apellido', 'nombre')
        )

    def clean(self):
        from django.db.models import Q

        cleaned = super().clean()
        fi = cleaned.get('fecha_inicio')
        indefinida = cleaned.get('indefinida')

        if indefinida:
            ff = None
            cleaned['fecha_fin'] = None
        else:
            ff = cleaned.get('fecha_fin')
            if not ff:
                self.add_error('fecha_fin', 'Indica la fecha de fin o marca la restricción como indefinida.')
            elif fi and ff < fi:
                self.add_error('fecha_fin', 'La fecha de fin debe ser igual o posterior a la de inicio.')

        # Sin solapamientos: dos restricciones a la vez sobre el mismo empleado
        # se pisarían en Mis Turnos y ganaría una de forma arbitraria.
        empleado = cleaned.get('empleado')
        if empleado and fi and not self.errors:
            otras = RestriccionEmpleado.objects.filter(empleado=empleado)
            if self.instance.pk:
                otras = otras.exclude(pk=self.instance.pk)
            # Solapan si empiezan antes de que esta acabe y acaban después de que esta empiece.
            if ff is not None:
                otras = otras.filter(fecha_inicio__lte=ff)
            otras = otras.filter(Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fi))
            existente = otras.order_by('-fecha_inicio').first()
            if existente:
                fin_txt = existente.fecha_fin.strftime('%d/%m/%Y') if existente.fecha_fin else 'indefinida'
                self.add_error(None, (
                    f'Este explorador ya tiene una restricción del '
                    f'{existente.fecha_inicio.strftime("%d/%m/%Y")} al {fin_txt}, '
                    'que se solapa con el rango indicado. Edita o elimina la existente.'
                ))

        return cleaned

    def save(self, commit=True):
        instancia = super().save(commit=False)
        if self.cleaned_data.get('indefinida'):
            instancia.fecha_fin = None
        if commit:
            instancia.save()
        return instancia

    class Meta:
        model = RestriccionEmpleado
        fields = ['empleado', 'fecha_inicio', 'fecha_fin', 'recomendacion', 'tipo_restriccion']
        widgets = {
            'empleado': forms.Select(attrs={'class': 'form-control'}),
            'recomendacion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Describe la recomendación médica o administrativa'
            }),
            'tipo_restriccion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Restricción de peso, postura, turnos, etc.'
            }),
        } 

class JornadaForm(forms.ModelForm):
    """Formulario del catálogo estructural de jornadas.

    El nombre se limita a AM/PM (ver Jornada): renombrar una jornada rompería
    los servicios que la buscan por nombre literal. Además se valida que el
    horario sea coherente y que no solape con la otra jornada.
    """
    class Meta:
        model = Jornada
        fields = ['nombre', 'hora_inicio', 'hora_fin']
        widgets = {
            'nombre': forms.Select(attrs={'class': 'form-control'}),
            'hora_inicio': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'hora_fin': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        }
        error_messages = {
            'nombre': {'unique': 'Ya existe una jornada con ese nombre.'},
        }

    def clean(self):
        cleaned = super().clean()
        inicio = cleaned.get('hora_inicio')
        fin = cleaned.get('hora_fin')

        if inicio and fin:
            if inicio == fin:
                self.add_error('hora_fin', 'La hora de fin no puede ser igual a la de inicio.')
            elif fin < inicio:
                # El motor de turnos trata la jornada como un rango del mismo día;
                # un cruce de medianoche haría que la duración salga negativa.
                self.add_error('hora_fin', 'La hora de fin debe ser posterior a la de inicio.')
            else:
                otras = Jornada.objects.exclude(pk=self.instance.pk) if self.instance.pk else Jornada.objects.all()
                solapada = otras.filter(hora_inicio__lt=fin, hora_fin__gt=inicio).first()
                if solapada:
                    self.add_error(
                        'hora_inicio',
                        f'El horario se solapa con la jornada {solapada.nombre} '
                        f'({solapada.hora_inicio:%H:%M} - {solapada.hora_fin:%H:%M}).'
                    )

        return cleaned

class RoleForm(forms.ModelForm):
    """Formulario del catálogo estructural de roles.

    Tres reglas, todas por seguridad y no por estética (ver Role):

    - Los roles protegidos no se renombran: el permiso de administración se
      resuelve buscando "Supervisor" por nombre.
    - Nadie puede crear un rol cuyo nombre se confunda con uno protegido
      ("Supervisor de sala", "Ex-supervisor"): antes esos nombres concedían
      acceso total porque la búsqueda del permiso era por coincidencia parcial.
    - El nombre se normaliza y es único sin distinguir mayúsculas, para que no
      convivan "Supervisor" y "supervisor" con significados distintos.
    """
    class Meta:
        model = Role
        fields = ['nombre']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control',
                                             'placeholder': 'Ej: Coordinador'}),
        }
        error_messages = {
            'nombre': {'unique': 'Ya existe un rol con ese nombre.'},
        }

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        if not nombre:
            raise forms.ValidationError('El nombre del rol es obligatorio.')

        original = self.instance.nombre if self.instance.pk else None
        if self.instance.pk and self.instance.es_protegido and nombre != original:
            raise forms.ValidationError(
                f'El rol "{original}" es parte de la configuración base del sistema '
                f'y no se puede renombrar.'
            )

        otros = Role.objects.exclude(pk=self.instance.pk) if self.instance.pk else Role.objects.all()
        if otros.filter(nombre__iexact=nombre).exists():
            raise forms.ValidationError('Ya existe un rol con ese nombre.')

        if nombre.lower() not in {n.lower() for n in Role.NOMBRES_PROTEGIDOS}:
            for protegido in Role.NOMBRES_PROTEGIDOS:
                if protegido.lower() in nombre.lower():
                    raise forms.ValidationError(
                        f'El nombre no puede contener "{protegido}": se confundiría con el '
                        f'rol base "{protegido}" y podría conceder permisos por error. '
                        f'Elige un nombre distinto.'
                    )

        return nombre

class PDHForm(forms.ModelForm):
    """Formulario para que un supervisor registre un Pago de Horas de un explorador."""
    fecha = forms.DateField(
        label='Fecha de pago',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    class Meta:
        from permisos.models import PDH
        model = PDH
        # El registro de un pago se hace por SELECCIÓN de deudas (ver PDHCreateView).
        # Este form se usa solo para EDITAR un pago ya creado: fecha y nota.
        fields = ['fecha', 'comentario']
        labels = {
            'comentario': 'Nota',
        }
        widgets = {
            'comentario': forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                                'placeholder': 'Nota opcional'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['comentario'].required = False


class EmpleadoUsuarioForm(forms.Form):
    usuario_existente = forms.ModelChoiceField(
        queryset=User.objects.all(),
        required=False,
        label='Usuario existente',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    username = forms.CharField(label='Usuario', max_length=150, required=False, widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(label='Contraseña', required=False, widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    email = forms.EmailField(label='Email', required=False, widget=forms.EmailInput(attrs={'class': 'form-control'}))
    nombre = forms.CharField(label='Nombre', max_length=50, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    apellido = forms.CharField(label='Apellido', max_length=50, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    cedula = forms.CharField(label='Cédula', max_length=10, required=True, widget=forms.TextInput(attrs={'class': 'form-control'}))
    activo = forms.BooleanField(label='Activo', required=False, initial=True, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    supervisor = forms.ModelChoiceField(
        queryset=Empleado.objects.filter(activo=True, empleadorole__role__nombre__iexact=Role.SUPERVISOR).distinct(),
        required=False,
        label='Supervisor',
        widget=forms.Select(attrs={'class': 'form-control'}),
        help_text='Opcional: Asignar un supervisor a este empleado (solo empleados con rol Supervisor)'
    )
    roles = forms.ModelMultipleChoiceField(queryset=Role.objects.all(), required=True, widget=forms.SelectMultiple(attrs={'class': 'form-control'}))
    # salas/jornada NO son obligatorias a nivel de campo: se exigen solo si el empleado NO
    # es supervisor (ver clean()). Un supervisor no tiene sala, jornada ni supervisor asignado.
    salas = forms.ModelMultipleChoiceField(queryset=Sala.objects.all(), required=False, widget=forms.SelectMultiple(attrs={'class': 'form-control'}))
    jornada = forms.ModelChoiceField(queryset=Jornada.objects.all(), required=False, label="Jornada (AM/PM)", widget=forms.Select(attrs={'class': 'form-control'}))

    @staticmethod
    def _roles_incluyen_supervisor(roles):
        # Exacto, igual que core.mixins.es_supervisor: si aquí bastara una
        # coincidencia parcial, un rol cualquiera podría eximir de sala/jornada.
        return bool(roles) and any(
            (r.nombre or '').strip().lower() == Role.SUPERVISOR.lower() for r in roles
        )

    def es_supervisor(self):
        return self._roles_incluyen_supervisor(self.cleaned_data.get('roles'))

    def clean(self):
        cleaned = super().clean()
        if not self._roles_incluyen_supervisor(cleaned.get('roles')):
            # Empleado normal (no supervisor): sala y jornada son obligatorias.
            if not cleaned.get('salas'):
                self.add_error('salas', 'Selecciona al menos una sala (obligatorio para no supervisores).')
            if not cleaned.get('jornada'):
                self.add_error('jornada', 'Selecciona una jornada (obligatorio para no supervisores).')
        return cleaned