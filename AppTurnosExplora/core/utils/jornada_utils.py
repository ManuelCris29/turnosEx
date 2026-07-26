"""
Utilidades para cálculo de jornadas.

Responsabilidad única:
- Lógica de cálculo de la jornada efectiva de un día (trabaja o descansa),
  delegando las reglas de fines de semana al servicio de alternancia.
- Cache de objetos Jornada AM/PM para evitar consultas repetidas.
"""
from datetime import date
from typing import Dict

from turnos.services.alternancia_fines_semana_service import (
    AlternanciaFinesSemanaService,
)


class JornadaUtils:
    """
    Utilidades para cálculo de jornadas.
    """

    @staticmethod
    def calcular_jornada_dia(jornada_base: str, fecha: date) -> str:
        """
        Calcula la jornada para un día específico, considerando:
        - Jornada base (AM o PM).
        - Alternancia real de fines de semana (sábados y domingos).

        Nueva lógica de fines de semana:
        - Los fines de semana se alternan por grupo:
          - En un fin de semana, un grupo (AM o PM) TRABAJA sábado (doblada completa)
            y DESCANSA domingo.
          - El grupo contrario DESCANSA sábado y TRABAJA domingo (doblada completa).
        - Esta alternancia se calcula a partir del sábado 10/01/2026 donde trabaja PM.

        Comportamiento:
        - Si la fecha es sábado o domingo:
          - Si jornada_base es la que TRABAJA ese día según alternancia → retorna jornada_base.
          - Si jornada_base es la que DESCANSA ese día → retorna "Descanso".
        - Si no es fin de semana → retorna siempre jornada_base.

        IMPORTANTE: jornada_base siempre debe ser "AM" o "PM", nunca None.
        Si un explorador no tiene jornada asignada, debe manejarse antes de llamar
        a esta función.

        Args:
            jornada_base: Nombre de la jornada base ("AM" o "PM")
            fecha: Fecha para calcular la jornada

        Returns:
            Nombre de la jornada ("AM", "PM", o "Descanso")

        Raises:
            ValueError: Si jornada_base no es "AM" o "PM"
        """
        if not jornada_base or jornada_base not in ["AM", "PM"]:
            raise ValueError(
                f"jornada_base debe ser 'AM' o 'PM', recibido: {jornada_base}. "
                "Todos los exploradores deben tener una jornada asignada."
            )

        # Lunes a viernes: siempre trabaja su jornada base
        if fecha.weekday() < 5:
            return jornada_base

        # Sábados y domingos: usar servicio de alternancia
        jornada_trabaja = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(
            fecha
        )
        jornada_descansa = AlternanciaFinesSemanaService.jornada_descansa_fin_semana(
            fecha
        )

        # Seguridad: si por alguna razón no se pudo determinar, usar comportamiento base
        if jornada_trabaja is None or jornada_descansa is None:
            return jornada_base

        jornada_base_upper = jornada_base.upper()

        if jornada_base_upper == jornada_trabaja:
            return jornada_base  # Trabaja ese día

        if jornada_base_upper == jornada_descansa:
            return "Descanso"

        # Si por alguna razón no coincide con ninguna (no debería ocurrir), devolver base
        return jornada_base


def obtener_jornada_base(empleado, fecha):
    """
    Jornada BASE (predeterminada) de un explorador en una fecha: la asignación vigente en
    `AsignarJornadaExplorador`. Devuelve el objeto Jornada o None.

    Es el estado "virtual" del día, independiente de lo que haya materializado en `Turno`.
    La usan las re-materializaciones de la reconciliación (patrón #22), que corren
    justamente cuando los turnos del día acaban de ser borrados y no se pueden consultar.
    """
    from turnos.models import AsignarJornadaExplorador

    asignacion = (
        AsignarJornadaExplorador.objects
        .filter(explorador=empleado, fecha_inicio__lte=fecha)
        .select_related('jornada')
        .order_by('-fecha_inicio')
        .first()
    )
    return asignacion.jornada if asignacion else None


def obtener_jornada_contraria(jornada):
    """La otra jornada del par AM/PM. Devuelve None si no se puede determinar."""
    if not jornada:
        return None
    jornadas = obtener_jornadas_am_pm()
    nombre = (jornada.nombre or '').upper()
    return jornadas.get('PM' if nombre == 'AM' else 'AM')


def obtener_jornadas_am_pm() -> Dict[str, object]:
    """
    Retorna {'AM': Jornada, 'PM': Jornada} con caché de proceso (1 hora).
    Uso centralizado para evitar múltiples consultas a la BD en servicios de doblada.
    """
    from django.core.cache import cache
    from turnos.models import Jornada

    cache_key = 'jornadas_am_pm'
    jornadas = cache.get(cache_key)
    if jornadas is None:
        jornadas = {
            'AM': Jornada.objects.get(nombre='AM'),
            'PM': Jornada.objects.get(nombre='PM'),
        }
        cache.set(cache_key, jornadas, 3600)
    return jornadas
