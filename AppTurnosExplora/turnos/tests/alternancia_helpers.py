"""
Ayudas de test para la alternancia de findes y festivos.

Desde el rediseño a semilla anual, qué grupo trabaja un finde o un festivo es un DATO en
`AsignacionEspecialManual`, no una fórmula: un año sin publicar no tiene turnos de finde y
todo sale como `sin_planificar`. Los tests que ejercitan solicitudes sobre findes o festivos
necesitan, por tanto, publicar la alternancia del año que usan.

`publicar_alternancia(anio)` la publica reproduciendo EXACTAMENTE lo que daba la fórmula
histórica. Así los tests que eligen sus fechas consultando `AlternanciaFinesSemanaService`
siguen siendo válidos sin reescribirlos.

Ojo al orden: los festivos (`DiaEspecial`) deben existir ANTES de llamar, o sus filas no
se crean.
"""
from io import StringIO

from django.core.management import call_command

from empleados.models import Jornada


def publicar_alternancia(*anios):
    """Publica la alternancia de los años dados, igual a la que calculaba la fórmula."""
    for nombre in ('AM', 'PM'):
        Jornada.objects.get_or_create(
            nombre=nombre,
            defaults={'hora_inicio': '06:00:00' if nombre == 'AM' else '14:00:00',
                      'hora_fin': '14:00:00' if nombre == 'AM' else '22:00:00'})
    for anio in anios:
        call_command('materializar_alternancia', anio=anio, stdout=StringIO())
