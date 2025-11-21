"""
Servicios compartidos para el proyecto.

Este módulo actúa como un punto centralizado para obtener instancias
de servicios que implementan interfaces definidas en `core.interfaces`.
"""

from typing import Optional, TYPE_CHECKING

from core.interfaces import IEmpleadoDisponibilidadService, ITurnoService
from core.services.cache_service import CacheService as CacheService  # noqa: F401 - Re-export

if TYPE_CHECKING:  # Solo para chequeo estático, evita importaciones en tiempo de ejecución
    from solicitudes.services.empleado_disponibilidad_service import EmpleadoDisponibilidadService
    from turnos.services.turno_service import TurnoService

_empleado_disponibilidad_service: Optional[IEmpleadoDisponibilidadService] = None
_turno_service: Optional[ITurnoService] = None


def get_empleado_disponibilidad_service() -> IEmpleadoDisponibilidadService:
    """
    Devuelve la instancia compartida de IEmpleadoDisponibilidadService.
    """
    global _empleado_disponibilidad_service
    if _empleado_disponibilidad_service is None:
        from solicitudes.services.empleado_disponibilidad_service import (
            EmpleadoDisponibilidadService,
        )
        _empleado_disponibilidad_service = EmpleadoDisponibilidadService()
    return _empleado_disponibilidad_service


def get_turno_service() -> ITurnoService:
    """
    Devuelve la instancia compartida de ITurnoService.
    """
    global _turno_service
    if _turno_service is None:
        from turnos.services.turno_service import TurnoService
        _turno_service = TurnoService()
    return _turno_service


__all__ = [
    "CacheService",
    "get_empleado_disponibilidad_service",
    "get_turno_service",
]
