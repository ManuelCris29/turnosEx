"""
Convierte una excepción en el texto que se le muestra a una persona.

Existe por un detalle de Django que se filtraba a la interfaz: `str()` sobre un
`ValidationError` NO devuelve el mensaje, devuelve su `repr` de lista. Así, un error
escrito con cuidado terminaba en pantalla como:

    Error aplicando D FDS: ['Explorador Jessika no tiene sala asignada para la fecha 2026-09-05']

Los corchetes y las comillas son ruido de Python, no información: quien aprueba una
solicitud no tiene por qué leer una estructura de datos. El caso real que lo destapó fue un
supervisor que no entendió por qué no podía aprobar.
"""
from django.core.exceptions import ValidationError


def texto_de_error(exc: Exception) -> str:
    """
    Devuelve el mensaje legible de una excepción, sin envoltorios de Python.

    Para `ValidationError` usa `messages` (la lista real de mensajes) y los une con espacio;
    para cualquier otra excepción, el `str()` de siempre.

    Args:
        exc: La excepción capturada.

    Returns:
        El texto a mostrar. Cadena vacía si la excepción no traía mensaje.
    """
    if isinstance(exc, ValidationError):
        # `messages` aplana tanto la forma de lista como la de diccionario (errores por
        # campo), que es justo lo que `str()` no hace.
        return ' '.join(str(m) for m in exc.messages)
    return str(exc)
