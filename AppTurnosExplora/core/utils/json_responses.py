"""
Helpers para respuestas JSON estandarizadas
"""
import logging

from django.http import JsonResponse

logger = logging.getLogger(__name__)


def json_ok(payload=None, status=200):
    """
    Crea una respuesta JSON exitosa.
    
    Args:
        payload: Diccionario con datos adicionales a incluir en la respuesta
        status: Código de estado HTTP (default: 200)
    
    Returns:
        JsonResponse con formato estándar:
        {
            "success": true,
            ...payload (si se proporciona)
        }
    
    Ejemplo:
        return json_ok({'data': [1, 2, 3]})
        # Retorna: {"success": true, "data": [1, 2, 3]}
    """
    data = {'success': True}
    if isinstance(payload, dict):
        data.update(payload)
    return JsonResponse(data, status=status)


def json_error(message, *, status=400, code=None, extra=None):
    """
    Crea una respuesta JSON de error.
    
    Args:
        message: Mensaje de error
        status: Código de estado HTTP (default: 400)
        code: Código de error opcional para identificación
        extra: Diccionario con información adicional opcional
    
    Returns:
        JsonResponse con formato estándar:
        {
            "success": false,
            "error": "mensaje",
            "code": "codigo" (opcional),
            "extra": {...} (opcional)
        }
    
    Ejemplo:
        return json_error("Usuario no encontrado", code="USER_NOT_FOUND", status=404)
        # Retorna: {"success": false, "error": "Usuario no encontrado", "code": "USER_NOT_FOUND"}
    """
    data = {'success': False, 'error': str(message)}
    if code:
        data['code'] = code
    if isinstance(extra, dict):
        data['extra'] = extra
    return JsonResponse(data, status=status)


def json_error_inesperado(request, excepcion, mensaje, *, code='internal_error'):
    """Cierra un `except Exception` de una API sin filtrar nada al cliente.

    POR QUÉ EXISTE
    --------------
    El patrón que sustituye era este:

        except Exception as e:
            return JsonResponse({'error': f'Error al obtener festivos: {str(e)}'}, status=500)

    `str(e)` de una excepción de base de datos no es un mensaje para el usuario:
    es el error crudo del driver. Puede ser
    `(1054, "Unknown column 'turnos_diaespecial.descripcion' in 'field list'")`,
    que regala nombres reales de tabla y columna, o
    `(2003, "Can't connect to MySQL server on 'swalp-prod.xxxx.rds.amazonaws.com'")`,
    que expone el endpoint de RDS. Es CWE-209, la misma fuga que cierran las
    páginas de error propias (ADR 007), por una vía que no pasa por ningún
    handler de Django.

    Al usuario le llega `mensaje` —escrito por nosotros, específico del endpoint
    para no degradar la experiencia— y el código de referencia. La traza
    completa va al log con ese mismo código.

    Args:
        request: para recuperar el `request_id` de la petición.
        excepcion: la capturada; se registra con traza, no se muestra.
        mensaje: qué decirle al usuario. Concreto, sin jerga y sin causa técnica.
        code: código de error de la API.
    """
    request_id = getattr(request, 'request_id', None)
    logger.exception('Fallo inesperado en API: %s', mensaje)

    extra = {'request_id': request_id} if request_id else None
    return json_error(mensaje, status=500, code=code, extra=extra)


