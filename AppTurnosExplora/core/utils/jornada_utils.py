"""
Utilidades para cálculo de jornadas.

Responsabilidad única:
- Lógica de cálculo de la jornada efectiva de un día (trabaja o descansa),
  delegando las reglas de fines de semana al servicio de alternancia.
"""
from datetime import date

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
