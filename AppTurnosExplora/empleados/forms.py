from django import forms
from django.contrib.auth.models import User
from .models import SancionEmpleado, Empleado, Role, RestriccionEmpleado, Jornada, Sala

class SancionEmpleadoForm(forms.ModelForm):
    fecha_inicio = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    fecha_fin = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False
    )

    class Meta:
        model = SancionEmpleado
        fields = ['explorador', 'supervisor', 'fecha_inicio', 'fecha_fin', 'motivo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )
    fecha_fin = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        required=False
    )

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
        fields = ['explorador', 'fecha', 'horas', 'comentario']
        labels = {
            'horas': 'Horas a pagar (se descuentan del consolidado)',
            'comentario': 'Nota (p. ej. el día que se está pagando)',
        }
        widgets = {
            'explorador': forms.Select(attrs={'class': 'form-control'}),
            'horas': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0.5'}),
            'comentario': forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                                'placeholder': 'Ej: paga la doblada del 15/01/2026'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['explorador'].queryset = Empleado.objects.filter(activo=True).order_by('nombre', 'apellido')
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