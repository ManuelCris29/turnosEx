"""
Manejo de errores HTTP: identificador de petición, handlers y filtro de logging.

EL PROBLEMA QUE RESUELVE
------------------------
Con DEBUG=True, Django responde a un 404 con su pantalla técnica, que imprime
el URLconf completo (todos los endpoints de la aplicación, incluidos los de
aprobación y rechazo de solicitudes), y a un 500 con el traceback, el código
fuente y las variables locales. Eso es divulgación de información: le entrega a
un atacante el mapa de la aplicación sin tener que buscarlo (CWE-215).

Con DEBUG=False Django deja de filtrar, pero entonces el usuario ve una página
muda y el equipo se queda sin forma de relacionar "me falló a las 3" con una
línea concreta del log.

LA SOLUCIÓN
-----------
A cada petición se le asigna un identificador corto y opaco. Ese identificador:

  * se muestra en la página de error como "código de referencia";
  * se adjunta a TODAS las líneas de log de esa petición (vía RequestIDFilter);
  * se devuelve en la cabecera X-Request-ID.

Así el usuario puede reportar `A3F91C2B` y el equipo hace un único filtro en
CloudWatch Logs para ver el traceback entero. El usuario no recibe ni un dato
interno; el equipo no pierde ninguno.

El identificador es aleatorio, no correlativo: no revela cuántas peticiones ha
atendido el sistema ni permite adivinar el de otro usuario.
"""
import logging
import uuid
from contextvars import ContextVar

from django.http import HttpResponseForbidden, HttpResponseNotFound
from django.http import HttpResponseBadRequest, HttpResponseServerError
from django.template import loader

logger = logging.getLogger(__name__)

# contextvar y no un atributo de request: el filtro de logging no recibe el
# request, pero sí se ejecuta dentro del mismo contexto asíncrono/hilo.
_request_id: ContextVar[str] = ContextVar('request_id', default='-')


def get_request_id() -> str:
    """Identificador de la petición en curso, o '-' fuera de una petición."""
    return _request_id.get()


class RequestIDMiddleware:
    """
    Asigna un identificador a cada petición y lo publica en la respuesta.

    Debe ir MUY ARRIBA en MIDDLEWARE: cualquier middleware que registre algo o
    que falle por debajo de él quedará etiquetado; lo que quede por encima, no.

    No se acepta un X-Request-ID entrante del cliente: sería un valor
    controlado por el atacante que acabaría escrito en los logs (inyección de
    log / envenenamiento de trazas). El identificador siempre lo genera el
    servidor.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = uuid.uuid4().hex[:12].upper()
        token = _request_id.set(rid)
        request.request_id = rid
        try:
            response = self.get_response(request)
            response['X-Request-ID'] = rid
            return response
        finally:
            _request_id.reset(token)


class RequestIDFilter(logging.Filter):
    """Inyecta `request_id` en cada registro para poder usarlo en el formato."""

    def filter(self, record):
        record.request_id = get_request_id()
        return True


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
# Se renderiza con loader.get_template().render(context) y NO con render(request):
# render() activa los context processors, y `core.context_processors.permisos`
# consulta la base de datos. En un handler500 provocado justamente por una BD
# caída eso lanzaría una segunda excepción y Django acabaría devolviendo su 500
# de emergencia en texto plano. Sin request, el contexto es plano y no falla.

def _render(template_name: str, request, response_class):
    rid = getattr(request, 'request_id', None) or get_request_id()
    context = {'request_id': None if rid == '-' else rid}
    try:
        html = loader.get_template(template_name).render(context)
    except Exception:
        # Última red: si hasta la plantilla falla, se responde algo mínimo
        # antes que dejar salir la pantalla técnica de Django.
        logger.exception('Fallo al renderizar la plantilla de error %s', template_name)
        html = (
            '<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">'
            '<title>Error</title></head><body>'
            '<h1>Se produjo un error</h1>'
            '<p>Inténtalo de nuevo más tarde.</p></body></html>'
        )
    return response_class(html)


def bad_request(request, exception=None):
    """400. También se dispara con un Host fuera de ALLOWED_HOSTS."""
    return _render('400.html', request, HttpResponseBadRequest)


def permission_denied(request, exception=None):
    """403."""
    return _render('403.html', request, HttpResponseForbidden)


def page_not_found(request, exception=None):
    """404. No se refleja la ruta pedida: no se devuelve entrada del usuario."""
    return _render('404.html', request, HttpResponseNotFound)


def server_error(request):
    """500."""
    return _render('500.html', request, HttpResponseServerError)


def previsualizar_error(request, codigo: int):
    """
    Renderiza una página de error a demanda para poder revisarla en desarrollo.

    Solo se enruta con DEBUG=True (ver config/urls.py). No existe en producción.
    """
    from django.http import Http404, HttpResponse

    plantillas = {
        400: '400.html',
        403: '403.html',
        404: '404.html',
        500: '500.html',
        419: '403_csrf.html',   # código libre para distinguir el CSRF del 403
    }
    if codigo not in plantillas:
        raise Http404
    return _render(plantillas[codigo], request, HttpResponse)


def csrf_failure(request, reason=''):
    """
    403 por fallo de CSRF.

    El motivo exacto ("CSRF token missing", "Referer checking failed"...) se
    registra pero NO se muestra: decirle a un atacante qué comprobación falló
    le ahorra trabajo en el siguiente intento. El usuario solo ve el mensaje
    genérico de sesión expirada.
    """
    logger.warning('Fallo de verificación CSRF: %s', reason)
    return _render('403_csrf.html', request, HttpResponseForbidden)
