"""Vistas de la app turnos (divididas por dominio)."""

from .paginas import *  # noqa: F401,F403
from .turno_crud import *  # noqa: F401,F403
from .dia_especial import *  # noqa: F401,F403
from .descanso_semana import *  # noqa: F401,F403

__all__ = [
    "MisTurnosView",
    "CambiosTurnoView",
    "ConsolidadoHorasView",
    "DiasEspecialesView",
    "TurnosCalendarioView",
    "TurnoListView",
    "TurnoCreateView",
    "TurnoUpdateView",
    "TurnoDeleteView",
    "DiaEspecialListView",
    "DiaEspecialCreateView",
    "DiaEspecialUpdateView",
    "DiaEspecialDeleteView",
    "DiaEspecialVisualizarListView",
    "DiaEspecialTemporadasAnualView",
    "DiaEspecialFestivosMantenimientoAnualView",
    "DescansoSemanaListView",
    "DescansoSemanaCreateView",
    "DescansoSemanaUpdateView",
    "DescansoSemanaDeleteView",
    "DescansoSemanaAnualView",
    "AsignacionEspecialAnualView",
    "AsignacionEspecialSiembraView",
]
