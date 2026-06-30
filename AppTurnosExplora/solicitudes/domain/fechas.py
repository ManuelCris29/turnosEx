"""
Value Objects y reglas de dominio para fechas de solicitudes.

Sin dependencias de Django ORM — lógica de negocio pura testeable en aislamiento.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterator


DIAS_SEMANA_LABORAL = frozenset({0, 1, 2, 3, 4})  # lunes=0 … viernes=4
DIAS_FINDE = frozenset({5, 6})                      # sábado=5, domingo=6


def es_dia_laboral(d: date) -> bool:
    return d.weekday() in DIAS_SEMANA_LABORAL


def es_finde(d: date) -> bool:
    return d.weekday() in DIAS_FINDE


def es_sabado(d: date) -> bool:
    return d.weekday() == 5


def dias_laborales_en_rango(inicio: date, fin: date) -> list[date]:
    return [d for d in _iter_rango(inicio, fin) if es_dia_laboral(d)]


def _iter_rango(inicio: date, fin: date) -> Iterator[date]:
    d = inicio
    while d <= fin:
        yield d
        d += timedelta(days=1)


def meses_en_rango(inicio: date, fin: date) -> set[tuple[int, int]]:
    """Devuelve el conjunto de (mes, año) que abarca el rango."""
    meses = set()
    d = inicio
    while d <= fin:
        meses.add((d.month, d.year))
        d += timedelta(days=28)
    meses.add((fin.month, fin.year))
    return meses


def validar_fecha_futura(d: date, hoy: date | None = None) -> tuple[bool, str]:
    if hoy is None:
        hoy = date.today()
    if d <= hoy:
        return False, 'La fecha debe ser futura'
    return True, ''


def validar_rango(inicio: date, fin: date) -> tuple[bool, str]:
    if fin < inicio:
        return False, 'La fecha de fin no puede ser anterior a la fecha de inicio'
    return True, ''
