"""
Comentario obligatorio en toda acción que resuelve algo.

Aprobar, rechazar, cancelar o responder a una petición de cancelación mueven turnos reales
y le cambian la semana a alguien. El texto que se escribe al hacerlo es lo único que le
llega a la otra persona explicando el porqué, y lo único que queda para auditar después,
así que se exige SIEMPRE y se comprueba en el servidor: el `required` del formulario es
comodidad para quien lo rellena, no la defensa.

Este módulo es la única fuente de esos textos. Antes vivían repartidos entre las constantes
de solicitudes, literales sueltos en las vistas de permisos y atributos de las plantillas —
tres copias del mismo mensaje que se desincronizaban al primer retoque.

Hay dos funciones porque hay dos contratos, y llevan nombres distintos a propósito: la app
de solicitudes responde JSON a peticiones AJAX y la de permisos responde con `messages` y
un redirect. Un solo nombre para las dos semánticas invitaba a copiar la llamada de un lado
al otro y a que el error se perdiera en silencio.
"""
from core.utils.json_responses import json_error

# --- Textos, en un único sitio -------------------------------------------------------
# También los consume el front: las vistas los pasan al contexto de la plantilla en vez de
# repetirlos en el HTML, para que servidor y navegador digan exactamente lo mismo.
MSG_COMENTARIO = 'Escribe un comentario explicando tu decisión.'
MSG_MOTIVO = 'Escribe el motivo de la cancelación.'
MSG_MOTIVO_INASISTENCIA = 'Escribe el motivo de la inasistencia.'
MSG_NOTA_PAGO = 'Escribe una nota explicando el pago.'

# Código de error de la API para este fallo concreto. Los demás errores de cancelación aún
# se distinguen por subcadena del mensaje; este no.
CODE_COMENTARIO_REQUERIDO = 'comentario_requerido'


def leer_texto(request, campo):
    """
    Devuelve el texto del POST ya limpio, o None si venía vacío o solo con espacios.

    No decide nada sobre la respuesta: eso es de quien llama, que sabe si habla JSON o
    HTML. Úsala directamente cuando la vista ya tiene su propia forma de reportar el error.
    """
    return (request.POST.get(campo) or '').strip() or None


def exigir_texto_json(request, campo, mensaje):
    """
    Variante para vistas que responden JSON.

    Devuelve `(texto, None)` si vino con contenido, o `(None, respuesta_400)` si no. El
    segundo elemento es una respuesta lista para devolver, con `code` a
    `CODE_COMENTARIO_REQUERIDO` para que el cliente distinga este fallo de los demás.
    """
    texto = leer_texto(request, campo)
    if texto is None:
        return None, json_error(mensaje, status=400, code=CODE_COMENTARIO_REQUERIDO)
    return texto, None
