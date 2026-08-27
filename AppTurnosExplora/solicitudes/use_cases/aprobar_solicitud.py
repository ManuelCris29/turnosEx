"""
Use Cases: Aprobación y rechazo de solicitudes.

Separa la intención de negocio (quién aprueba y en qué rol) de la
implementación técnica (SolicitudAprobacionService).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from empleados.models import Empleado


class AprobarComoReceptorUseCase:
    def execute(self, solicitud_id: int, empleado: "Empleado", comentario: str) -> Tuple[bool, str]:
        from solicitudes.services.solicitud_aprobacion_service import SolicitudAprobacionService
        return SolicitudAprobacionService.aprobar_solicitud_receptor(solicitud_id, empleado, comentario)


class AprobarComoSupervisorUseCase:
    def execute(self, solicitud_id: int, empleado: "Empleado", comentario: str) -> Tuple[bool, str]:
        from solicitudes.services.solicitud_aprobacion_service import SolicitudAprobacionService
        return SolicitudAprobacionService.aprobar_solicitud_supervisor(solicitud_id, empleado, comentario)


class RechazarComoReceptorUseCase:
    def execute(self, solicitud_id: int, empleado: "Empleado", comentario: str) -> Tuple[bool, str]:
        from solicitudes.services.solicitud_aprobacion_service import SolicitudAprobacionService
        return SolicitudAprobacionService.rechazar_solicitud_receptor(solicitud_id, empleado, comentario)


class RechazarComoSupervisorUseCase:
    def execute(self, solicitud_id: int, empleado: "Empleado", comentario: str) -> Tuple[bool, str]:
        from solicitudes.services.solicitud_aprobacion_service import SolicitudAprobacionService
        return SolicitudAprobacionService.rechazar_solicitud_supervisor(solicitud_id, empleado, comentario)


class AprobarAmbosRolesUseCase:
    """Aprueba como receptor Y supervisor en una sola acción (cuando el usuario ocupa ambos roles)."""

    def execute(self, solicitud_id: int, empleado: "Empleado", comentario: str) -> Tuple[bool, str]:
        from solicitudes.repositories.solicitud_repository import SolicitudRepository
        from solicitudes.services.solicitud_aprobacion_service import SolicitudAprobacionService

        solicitud = SolicitudRepository.get_by_id(solicitud_id)
        if solicitud is None:
            return False, 'Solicitud no encontrada'

        es_receptor = solicitud.explorador_receptor == empleado
        es_supervisor = (getattr(solicitud.explorador_solicitante, 'supervisor', None) == empleado)

        if not (es_receptor and es_supervisor):
            return False, 'No tienes permisos para aprobar en ambos roles'

        if solicitud.estado != 'pendiente':
            return False, 'La solicitud no está pendiente'

        if not solicitud.aprobado_receptor:
            ok, msg = SolicitudAprobacionService.aprobar_solicitud_receptor(
                solicitud_id, empleado, f'{comentario} (rol receptor)'
            )
            if not ok:
                return False, msg

        ok, msg = SolicitudAprobacionService.aprobar_solicitud_supervisor(
            solicitud_id, empleado, f'{comentario} (rol supervisor)'
        )
        return ok, msg
