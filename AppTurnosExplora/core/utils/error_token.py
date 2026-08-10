"""Página de error de los enlaces de aprobación por correo.

Existe para que las 15 llamadas repartidas entre `solicitudes` y `permisos`
rendericen SIEMPRE la misma plantilla con el mismo contexto. La plantilla dice al
usuario cuántos días duran los enlaces; si una vista se olvidara de pasar ese
dato, la frase saldría coja. Con un único punto de entrada no puede pasar.

QUÉ PUEDE IR EN `mensaje`
-------------------------
Solo texto **redactado por nosotros** y pensado para el usuario: «Token inválido
o expirado», o el mensaje de negocio que devuelve el servicio de aprobación.

Nunca `str(excepcion)`. El texto de una excepción de base de datos puede llevar
fragmentos de SQL, nombres de tabla y de columna o el nombre de la restricción
violada, y esta página la ve alguien que llega desde un correo, posiblemente sin
sesión iniciada (CWE-209). Para eso está `render_error_token_inesperado()`: deja
la traza en el log y al usuario le enseña el código de referencia con el que
reportarla.
"""

import logging

from django.conf import settings
from django.shortcuts import render

logger = logging.getLogger(__name__)

PLANTILLA = 'solicitudes/error_token.html'

# Texto único para cualquier fallo no previsto. No describe la causa: la causa
# va al log, identificada por el mismo código que se le muestra al usuario.
MENSAJE_INESPERADO = (
    'No pudimos completar la operación por un fallo interno. '
    'El equipo de desarrollo ya tiene el registro del error.'
)


def render_error_token(request, mensaje, status=200):
    """Renderiza la página de token inválido/caducado con su contexto completo.

    `status` por defecto es 200 por compatibilidad con las llamadas antiguas,
    pero conviene pasar el que corresponda: un 200 en un enlace rechazado miente
    al navegador y, sobre todo, hace invisible el fallo para las alarmas.
    """
    return render(
        request,
        PLANTILLA,
        {
            'mensaje': mensaje,
            'dias_validez': getattr(settings, 'APPROVAL_LINK_MAX_AGE_DAYS', 30),
            'request_id': getattr(request, 'request_id', None),
        },
        status=status,
    )


def render_error_token_inesperado(request, excepcion, contexto=''):
    """Cierra un `except Exception` sin filtrar nada al usuario.

    Registra la traza completa —el filtro de logging le adjunta el mismo
    identificador que se muestra en pantalla, así que buscar el código que
    reporte el usuario lleva directamente a este traceback— y devuelve la página
    con el mensaje genérico y un 500.
    """
    logger.exception(
        'Fallo inesperado en un enlace de aprobación por correo%s: %s',
        f' ({contexto})' if contexto else '',
        excepcion.__class__.__name__,
    )
    return render_error_token(request, MENSAJE_INESPERADO, status=500)
