"""
Frontera HTTP del alta de solicitudes: `ResultadoSolicitud` → `JsonResponse`.

Es el ÚNICO sitio donde el resultado de crear una solicitud se convierte en una
respuesta. El orquestador decide qué pasó; aquí se decide cómo se cuenta por HTTP.
"""
from django.http import JsonResponse

from ..services.resultado import ResultadoSolicitud


def json_desde_resultado(resultado: ResultadoSolicitud) -> JsonResponse:
    """Convierte el resultado de dominio en la respuesta JSON que leen los formularios."""
    return JsonResponse(resultado.como_payload(), status=resultado.status)
