"""
Servicio de alternancia de fines de semana (sábados y domingos).

Responsabilidad única:
- Determinar qué jornada (AM o PM) TRABAJA o DESCANSA un sábado o domingo,
  aplicando la regla de alternancia que definiste.

Regla de negocio (resumen):
- Los fines de semana se alternan por grupo:
  - En un fin de semana, el grupo AM trabaja el sábado (doblada completa AM+PM)
    y descansa el domingo; el grupo PM trabaja el domingo (doblada completa)
    y descansa el sábado.
  - Al siguiente fin de semana se invierte:
    - Sábado trabaja PM, domingo descansa PM.
    - Domingo trabaja AM, sábado descansa AM.

Punto de referencia:
- Tomamos como referencia el sábado 10/01/2026, donde trabaja el grupo PM.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


FECHA_REFERENCIA_SABADO = date(2026, 1, 10)  # Sábado donde trabaja PM (según regla de negocio)
JORNADA_REFERENCIA_SABADO = "PM"  # En la fecha de referencia, el sábado es del grupo PM


@dataclass(frozen=True)
class AlternanciaFinesSemanaService:
    """
    Servicio puro (sin acceso a BD) para calcular alternancia AM/PM
    en sábados y domingos.
    """

    @staticmethod
    def _es_sabado(fecha: date) -> bool:
        return fecha.weekday() == 5

    @staticmethod
    def _es_domingo(fecha: date) -> bool:
        return fecha.weekday() == 6

    # ==========================
    #  Cálculo de semana/paridad
    # ==========================

    @staticmethod
    def _delta_semanas_desde_referencia(fecha: date) -> int:
        """
        Calcula cuántas semanas (enteras) han pasado desde la fecha de referencia
        hasta el sábado del mismo fin de semana de `fecha`.

        Si `fecha` es domingo, se toma el sábado inmediatamente anterior.
        """
        if AlternanciaFinesSemanaService._es_domingo(fecha):
            sabado = fecha - timedelta(days=1)
        elif AlternanciaFinesSemanaService._es_sabado(fecha):
            sabado = fecha
        else:
            # No es fin de semana; por seguridad devolvemos 0
            sabado = fecha

        dias = (sabado - FECHA_REFERENCIA_SABADO).days
        # División entera: diferencia de semanas completa (puede ser negativa)
        return dias // 7

    @staticmethod
    def _es_fin_de_semana_par(fecha: date) -> bool:
        """
        Determina si el fin de semana de `fecha` tiene la misma configuración
        que el fin de semana de referencia.

        - Semana par (delta_semanas par): mismo patrón que referencia.
        - Semana impar: patrón invertido.
        """
        delta = AlternanciaFinesSemanaService._delta_semanas_desde_referencia(fecha)
        return (delta % 2) == 0

    # ==========================
    #  Jornadas que TRABAJAN
    # ==========================

    @staticmethod
    def jornada_trabaja_sabado(fecha: date) -> Optional[str]:
        """
        Retorna la jornada ('AM' o 'PM') que TRABAJA el sábado de ese fin
        de semana, según alternancia.

        Si la fecha no es sábado ni domingo, retorna None.
        """
        if not (AlternanciaFinesSemanaService._es_sabado(fecha) or AlternanciaFinesSemanaService._es_domingo(fecha)):
            return None

        es_par = AlternanciaFinesSemanaService._es_fin_de_semana_par(fecha)

        if es_par:
            # Mismo patrón que referencia:
            # - Sábado trabaja el grupo de referencia (PM)
            return JORNADA_REFERENCIA_SABADO
        else:
            # Patrón invertido:
            # - Sábado trabaja el grupo contrario
            return "AM" if JORNADA_REFERENCIA_SABADO == "PM" else "PM"

    @staticmethod
    def jornada_trabaja_domingo(fecha: date) -> Optional[str]:
        """
        Retorna la jornada ('AM' o 'PM') que TRABAJA el domingo de ese fin
        de semana, según alternancia.

        Regla de negocio:
        - Si el sábado trabaja AM, el domingo trabaja PM.
        - Si el sábado trabaja PM, el domingo trabaja AM.

        Si la fecha no es sábado ni domingo, retorna None.
        """
        if not (AlternanciaFinesSemanaService._es_sabado(fecha) or AlternanciaFinesSemanaService._es_domingo(fecha)):
            return None

        jornada_sabado = AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha)
        if jornada_sabado is None:
            return None

        # Domingo siempre es el grupo contrario al sábado
        return "PM" if jornada_sabado == "AM" else "AM"

    @staticmethod
    def jornada_trabaja_fin_semana(fecha: date) -> Optional[str]:
        """
        Retorna la jornada que TRABAJA en la fecha si es sábado o domingo.
        Si no es fin de semana, retorna None.
        """
        if AlternanciaFinesSemanaService._es_sabado(fecha):
            return AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha)
        if AlternanciaFinesSemanaService._es_domingo(fecha):
            return AlternanciaFinesSemanaService.jornada_trabaja_domingo(fecha)
        return None

    # ==========================
    #  Jornadas que DESCANSAN
    # ==========================

    @staticmethod
    def jornada_descansa_sabado(fecha: date) -> Optional[str]:
        """
        Retorna la jornada ('AM' o 'PM') que DESCANSA el sábado de ese fin
        de semana, según alternancia.
        """
        trabaja = AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha)
        if trabaja is None:
            return None
        return "PM" if trabaja == "AM" else "AM"

    @staticmethod
    def jornada_descansa_domingo(fecha: date) -> Optional[str]:
        """
        Retorna la jornada ('AM' o 'PM') que DESCANSA el domingo de ese fin
        de semana, según alternancia.
        """
        trabaja = AlternanciaFinesSemanaService.jornada_trabaja_domingo(fecha)
        if trabaja is None:
            return None
        return "PM" if trabaja == "AM" else "AM"

    @staticmethod
    def jornada_descansa_fin_semana(fecha: date) -> Optional[str]:
        """
        Retorna la jornada que DESCANSA en la fecha si es sábado o domingo.
        Si no es fin de semana, retorna None.
        """
        if AlternanciaFinesSemanaService._es_sabado(fecha):
            return AlternanciaFinesSemanaService.jornada_descansa_sabado(fecha)
        if AlternanciaFinesSemanaService._es_domingo(fecha):
            return AlternanciaFinesSemanaService.jornada_descansa_domingo(fecha)
        return None



