"""
Use Case: CrearSolicitud

Encapsula la intención de negocio "un explorador crea una solicitud de cambio de turno".
Delega la orquestación técnica al SolicitudOrchestrator y la validación al SolicitudRequestParser.

Punto de entrada único para las vistas — las vistas no necesitan saber qué servicios
existen, solo invocan este caso de uso con los datos del request.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from django.http import HttpResponse

if TYPE_CHECKING:
    from empleados.models import Empleado
    from solicitudes.models import TipoSolicitudCambio


class CrearSolicitudUseCase:
    """
    Entrada: datos crudos del POST + tipo de solicitud + empleado solicitante.
    Salida:  HttpResponse (JSON) producida por el orquestador.
    """

    def execute(
        self,
        post_data: dict,
        tipo_solicitud: "TipoSolicitudCambio",
        solicitante: "Empleado",
    ) -> HttpResponse:
        from solicitudes.services.solicitud_request_parser import SolicitudRequestParser
        from solicitudes.services.solicitud_orchestrator import SolicitudOrchestrator
        from core.utils.json_responses import json_error

        ok, error_msg = SolicitudRequestParser.validate_required(tipo_solicitud.nombre, post_data)
        if not ok:
            return json_error(error_msg, status=400, code='missing_fields')

        return SolicitudOrchestrator.procesar(post_data, tipo_solicitud, solicitante)
