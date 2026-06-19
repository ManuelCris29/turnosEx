from django import forms
from django.contrib.auth.models import User
from .models import SancionEmpleado, Empleado, Role, RestriccionEmpleado, Jornada, Sala

class SancionEmpleadoForm(forms.ModelForm):
    DURACION_CHOICES = [
        ('15', '15 días'), ('30', '30 días'), ('45', '45 días'),
        ('60', '60 días'), ('90', '90 días'), ('otro', 'Otro (personalizado)'),
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
        fields = ['explorador', 'supervisor', 'fecha_inicio', 'motivo']

    def clean(self):
        from datetime import timedelta
        cleaned = super().clean()
        fi = cleaned.get('fecha_inicio')
        dur = cleaned.get('duracion')
        dias = None
        if dur == 'otro':
            dias = cleaned.get('dias_personalizado')
            if not dias or dias <= 0:
                self.add_error('dias_personalizado', 'Indica cuántos días dura la sanción.')
        elif dur:
            dias = int(dur)
        if fi and dias:
            # Inclusivo: 15 días desde el 1 → termina el 15
            cleaned['_fecha_fin'] = fi + timedelta(days=dias - 1)
        return cleaned

    def save(self, commit=True):
        instancia = super().save(commit=False)
        instancia.fecha_fin = self.cleaned_data.get('_fecha_fin')
        if commit:
            instancia.save()
        return instancia

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Al editar, precargar la duración a partir del rango existente
        inst = kwargs.get('instance') or getattr(self, 'instance', None)
        if inst and inst.pk and inst.fecha_inicio and inst.fecha_fin:
            dias = (inst.fecha_fin - inst.fecha_inicio).days + 1
            if str(dias) in dict(self.DURACION_CHOICES):
                self.fields['duracion'].initial = str(dias)
            else:
                self.fields['duracion'].initial = 'otro'
                self.fields['dias_personalizado'].initial = dias
        # Filtrar solo empleados con rol de supervisor
        supervisor_role = Role.objects.filter(nombre__icontains='supervisor').first()
        if supervisor_role is not None:
            self.fields['supervisor'].queryset = Empleado.objects.filter(
                empleadorole__role=supervisor_role
            ).distinct()
        else:
            self.fields['supervisor'].queryset = Empleado.objects.none()
        # Filtrar solo empleados con rol de explorador
        explorador_role = Role.objects.filter(nombre__icontains='explorador').first()
        if explorador_role is not None:
            self.fields['explorador'].queryset = Empleado.objects.filter(
                empleadorole__role=explorador_role
            ).distinct()
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
    salas = forms.ModelMultipleChoiceField(queryset=Sala.objects.all(), required=True, widget=forms.SelectMultiple(attrs={'class': 'form-control'}))
    jornada = forms.ModelChoiceField(queryset=Jornada.objects.all(), required=True, label="Jornada (AM/PM)", widget=forms.Select(attrs={'class': 'form-control'}))