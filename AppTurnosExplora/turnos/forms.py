"""
Formularios para la gestión de días especiales y temporadas.
"""
from django import forms
from datetime import date

from turnos.models import DiaEspecial


class TemporadasAnualForm(forms.Form):
    """
    Formulario para gestionar temporadas anuales.
    Permite seleccionar días de temporada por mes para un año específico.
    """
    anio = forms.IntegerField(
        label='Año',
        min_value=DiaEspecial.ANIO_MIN,
        max_value=DiaEspecial.ANIO_MAX,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'id': 'id_anio',
            'required': True
        }),
        help_text='Seleccione el año para el cual desea configurar las temporadas'
    )
    
    dias_seleccionados = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    
    def clean_anio(self):
        """Valida que el año sea válido"""
        anio = self.cleaned_data.get('anio')
        if anio and (anio < DiaEspecial.ANIO_MIN or anio > DiaEspecial.ANIO_MAX):
            raise forms.ValidationError(f'El año debe estar entre {DiaEspecial.ANIO_MIN} y {DiaEspecial.ANIO_MAX}.')
        return anio
    
    def clean_dias_seleccionados(self):
        """Valida el formato de días seleccionados"""
        import json
        dias_str = self.cleaned_data.get('dias_seleccionados')
        if not dias_str:
            return {}
        
        try:
            dias = json.loads(dias_str)
            if not isinstance(dias, dict):
                raise forms.ValidationError('Formato inválido de días seleccionados.')
            
            # Validar estructura: {mes: [dias]}
            for mes, dias_lista in dias.items():
                try:
                    mes_int = int(mes)
                    if mes_int < 1 or mes_int > 12:
                        raise forms.ValidationError(f'Mes inválido: {mes_int}')
                    
                    if not isinstance(dias_lista, list):
                        raise forms.ValidationError(f'Los días del mes {mes_int} deben ser una lista.')
                    
                    for dia in dias_lista:
                        if not isinstance(dia, int) or dia < 1 or dia > 31:
                            raise forms.ValidationError(f'Día inválido: {dia} en el mes {mes_int}')
                            
                except ValueError:
                    raise forms.ValidationError(f'Mes inválido: {mes}')
            
            return dias
            
        except json.JSONDecodeError:
            raise forms.ValidationError('Formato JSON inválido en días seleccionados.')


class DiasEspecialesAnualForm(forms.Form):
    """
    Formulario para gestionar días especiales anuales (festivos y mantenimiento).
    Permite seleccionar días por mes para un año específico.
    """
    tipo = forms.ChoiceField(
        label='Tipo',
        choices=[('festivo', 'Festivo'), ('mantenimiento', 'Mantenimiento')],
        widget=forms.Select(attrs={
            'class': 'form-control',
            'id': 'id_tipo',
            'required': True
        }),
        help_text='Seleccione el tipo de día especial'
    )
    
    anio = forms.IntegerField(
        label='Año',
        min_value=DiaEspecial.ANIO_MIN,
        max_value=DiaEspecial.ANIO_MAX,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'id': 'id_anio',
            'required': True
        }),
        help_text='Seleccione el año para el cual desea configurar los días especiales'
    )
    
    dias_seleccionados = forms.CharField(
        widget=forms.HiddenInput(),
        required=False
    )
    
    def clean_tipo(self):
        """Valida que el tipo sea válido"""
        tipo = self.cleaned_data.get('tipo')
        if tipo and tipo not in ['festivo', 'mantenimiento']:
            raise forms.ValidationError('El tipo debe ser "festivo" o "mantenimiento".')
        return tipo
    
    def clean_anio(self):
        """Valida que el año sea válido"""
        anio = self.cleaned_data.get('anio')
        if anio and (anio < DiaEspecial.ANIO_MIN or anio > DiaEspecial.ANIO_MAX):
            raise forms.ValidationError(f'El año debe estar entre {DiaEspecial.ANIO_MIN} y {DiaEspecial.ANIO_MAX}.')
        return anio
    
    def clean_dias_seleccionados(self):
        """Valida el formato de días seleccionados"""
        import json
        dias_str = self.cleaned_data.get('dias_seleccionados')
        if not dias_str:
            return {}
        
        try:
            dias = json.loads(dias_str)
            if not isinstance(dias, dict):
                raise forms.ValidationError('Formato inválido de días seleccionados.')
            
            # Validar estructura: {mes: [dias]}
            for mes, dias_lista in dias.items():
                try:
                    mes_int = int(mes)
                    if mes_int < 1 or mes_int > 12:
                        raise forms.ValidationError(f'Mes inválido: {mes_int}')
                    
                    if not isinstance(dias_lista, list):
                        raise forms.ValidationError(f'Los días del mes {mes_int} deben ser una lista.')
                    
                    for dia in dias_lista:
                        if not isinstance(dia, int) or dia < 1 or dia > 31:
                            raise forms.ValidationError(f'Día inválido: {dia} en el mes {mes_int}')
                            
                except ValueError:
                    raise forms.ValidationError(f'Mes inválido: {mes}')
            
            return dias
            
        except json.JSONDecodeError:
            raise forms.ValidationError('Formato JSON inválido en días seleccionados.')


