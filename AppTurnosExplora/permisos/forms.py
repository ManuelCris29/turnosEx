from django import forms

from core.utils.anio_operativo import mensaje_fuera_del_anio_operativo
from empleados.models import Empleado

from .models import PermisoEspecial

DIAS_SEMANA = [
    (0, 'Lunes'), (1, 'Martes'), (2, 'Miércoles'), (3, 'Jueves'),
    (4, 'Viernes'), (5, 'Sábado'), (6, 'Domingo'),
]


def _empleados_qs():
    """Candidatos del campo `cubre`: quien puede cubrir el hueco del permiso.

    `operativos()` deja fuera a los supervisores (por rol o por staff): el
    supervisor aprueba el permiso, no cubre el turno de nadie.
    """
    return Empleado.objects.operativos().order_by('nombre', 'apellido')


class _BasePermisoForm(forms.ModelForm):
    """Campos comunes (tiempo, tipo, especificación, quién cubre, motivo)."""
    class Meta:
        model = PermisoEspecial
        fields = ['tiempo', 'tipo', 'especificacion', 'cubre', 'motivo']
        labels = {
            'tiempo': 'Tiempo solicitado (horas)',
            'tipo': 'Tipo de permiso',
            'especificacion': 'Especificación (ej. "Entrada 1:30 pm")',
            'cubre': '¿Quién cubre el hueco? (opcional)',
            'motivo': 'Motivo',
        }
        widgets = {
            'tiempo': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0.5'}),
            'tipo': forms.Select(attrs={'class': 'form-control'}),
            'especificacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Entrada 1:30 pm'}),
            'cubre': forms.Select(attrs={'class': 'form-control'}),
            'motivo': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Motivo del permiso'}),
        }

    def __init__(self, *args, **kwargs):
        self.empleado = kwargs.pop('empleado', None)
        super().__init__(*args, **kwargs)
        qs = _empleados_qs()
        if self.empleado:
            qs = qs.exclude(id=self.empleado.id)
        self.fields['cubre'].queryset = qs
        self.fields['cubre'].required = False

    def _validar_anio_operativo(self, *campos):
        """
        Ningún permiso cruza el 31 de diciembre: el año siguiente todavía no tiene calendario
        publicado (se prepara en la apertura de año). Ver `core/utils/anio_operativo.py`.

        Vive en la base porque las dos subclases tienen la misma regla con campos de fecha
        distintos —`fecha` la puntual, `fecha_inicio`/`fecha_fin` la permanente—. El error se
        cuelga del campo infractor, que puede ser más de uno, para que el formulario lo marque
        donde el usuario tiene que corregirlo.
        """
        for campo in campos:
            error = mensaje_fuera_del_anio_operativo([self.cleaned_data.get(campo)])
            if error:
                self.add_error(campo, error)


class PermisoEspecialForm(_BasePermisoForm):
    """Permiso especial puntual (un día)."""
    fecha = forms.DateField(
        label='Fecha del permiso',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )

    field_order = ['fecha', 'tiempo', 'tipo', 'especificacion', 'cubre', 'motivo']

    def clean(self):
        cleaned = super().clean()
        self._validar_anio_operativo('fecha')
        return cleaned


class PermisoEspecialPermanenteForm(_BasePermisoForm):
    """Permiso permanente: días fijos de la semana dentro de un rango."""
    fecha_inicio = forms.DateField(
        label='Desde',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    fecha_fin = forms.DateField(
        label='Hasta',
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
    )
    dias = forms.MultipleChoiceField(
        choices=DIAS_SEMANA,
        widget=forms.CheckboxSelectMultiple,
        label='Días de la semana',
    )

    field_order = ['fecha_inicio', 'fecha_fin', 'dias', 'tiempo', 'tipo', 'especificacion', 'cubre', 'motivo']

    def clean(self):
        cleaned = super().clean()
        fi, ff = cleaned.get('fecha_inicio'), cleaned.get('fecha_fin')
        self._validar_anio_operativo('fecha_inicio', 'fecha_fin')
        if fi and ff and ff < fi:
            self.add_error('fecha_fin', 'La fecha "Hasta" debe ser igual o posterior a "Desde".')
        return cleaned
