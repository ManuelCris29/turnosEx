"""
Utilidades de dominio para nombres de jornada.

Centraliza la normalización de 'AM'/'PM'/'AMBAS' que aparece dispersa
como .strip().upper() en servicios y estrategias.
"""
from typing import Literal

JornadaNombre = Literal['AM', 'PM']
JornadaPagoSabado = Literal['AM', 'PM', 'AMBAS']

_VALIDAS: frozenset[str] = frozenset({'AM', 'PM'})
_VALIDAS_PAGO_SABADO: frozenset[str] = frozenset({'AM', 'PM', 'AMBAS'})


def normalizar_jornada(valor: str | None) -> str:
    """Devuelve el nombre de jornada normalizado (strip + upper)."""
    return (valor or '').strip().upper()


def es_jornada_valida(valor: str | None) -> bool:
    """True si el valor normalizado es 'AM' o 'PM'."""
    return normalizar_jornada(valor) in _VALIDAS


def es_jornada_pago_sabado_valida(valor: str | None) -> bool:
    """True si el valor normalizado es 'AM', 'PM' o 'AMBAS'."""
    return normalizar_jornada(valor) in _VALIDAS_PAGO_SABADO
