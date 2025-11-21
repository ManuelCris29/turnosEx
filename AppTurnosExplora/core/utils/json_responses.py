"""
Helpers para respuestas JSON estandarizadas
"""
from django.http import JsonResponse


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


