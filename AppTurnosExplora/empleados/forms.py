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
        if explorador and fi and not self.errors:
            otras = SancionEmpleado.objects.filter(explorador=explorador)
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
                    'que se solapa con el rango indicado. Edita o elimina la existente.'
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
        explorador_role = Role.objects.filter(nombre__icontains='explorador').first()
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

class RestriccionEmpleadoForm(forms.ModelForm):
    fecha_inicio = forms.DateField(
        label='Fecha de inicio',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    fecha_fin = forms.DateField(
        label='Fecha de fin',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=True
    )

    def clean(self):
        cleaned = super().clean()
        fi, ff = cleaned.get('fecha_inicio'), cleaned.get('fecha_fin')
        if fi and ff and ff < fi:
            self.add_error('fecha_fin', 'La fecha de fin debe ser igual o posterior a la de inicio.')
        return cleaned

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
    class Meta:
        model = Jornada
        fields = ['nombre', 'hora_inicio', 'hora_fin']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'hora_inicio': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'hora_fin': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        }

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
        queryset=Empleado.objects.filter(activo=True, empleadorole__role__nombre__icontains='supervisor').distinct(),
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
        return bool(roles) and any('supervisor' in (r.nombre or '').lower() for r in roles)

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