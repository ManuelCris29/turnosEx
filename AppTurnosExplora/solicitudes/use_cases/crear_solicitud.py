"""
Use Case: CrearSolicitud

Encapsula la intención de negocio "un explorador crea una solicitud de cambio de turno".
Delega la orquestación técnica al SolicitudOrchestrator y la validación al SolicitudRequestParser.

Punto de entrada único para las vistas — las vistas no necesitan saber qué servicios
existen, solo invocan este caso de uso con los datos del request.

Devuelve un `ResultadoSolicitud`, no una respuesta HTTP: quien traduce a JSON es la
vista (`views/resultado_http.py`). Así este caso de uso se puede invocar igual desde
un test de integración o un comando de gestión.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from solicitudes.services.resultado import ResultadoSolicitud

if TYPE_CHECKING:
    from empleados.models import Empleado
    from solicitudes.models import TipoSolicitudCambio


class CrearSolicitudUseCase:
    """
    Entrada: datos crudos del POST + tipo de solicitud + empleado solicitante.
    Salida:  ResultadoSolicitud producido por el orquestador.
    """

    def execute(
        self,
        post_data: dict,
        tipo_solicitud: "TipoSolicitudCambio",
        solicitante: "Empleado",
    ) -> ResultadoSolicitud:
        from solicitudes.services.solicitud_orchestrator import SolicitudOrchestrator
        from solicitudes.services.solicitud_request_parser import SolicitudRequestParser

        ok, error_msg = SolicitudRequestParser.validate_required(tipo_solicitud.nombre, post_data)
        if not ok:
            return ResultadoSolicitud.error(error_msg, status=400, code='missing_fields')

        return SolicitudOrchestrator.procesar(post_data, tipo_solicitud, solicitante)
