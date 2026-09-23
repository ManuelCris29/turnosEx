"""
Middlewares compartidos del proyecto.
"""
import logging

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger(__name__)


class AperturaAnioMiddleware:
    """
    Obliga al supervisor a dejar planificado el año siguiente antes de que empiece.

    A partir de la fecha configurada (1-dic por defecto), si el checklist de apertura no
    está completo, cualquier navegación de un usuario ADMIN se redirige a la pantalla de
    apertura. Los exploradores no se ven afectados: la planificación no es su trabajo y
    dejarlos fuera del sistema por una tarea administrativa sería peor que el problema.

    RUTAS EXENTAS: sin ellas el middleware se muerde la cola — el supervisor no podría ni
    abrir las pantallas donde se completa el checklist, ni cerrar sesión. Cualquier cambio
    aquí debe conservar esa lista.
    """

    # Prefijos que nunca se bloquean.
    EXENTOS = (
        '/static/', '/media/', '/admin/',
        '/logout', '/login', '/accounts/',
        # Sin esto, un administrador con el año sin abrir no podría ni cambiar su
        # propia contraseña: el middleware lo devolvería a la apertura de año una
        # y otra vez.
        '/password/',
        '/turnos/apertura-anio/',
        # Las cinco pantallas del checklist y sus endpoints de apoyo.
        '/turnos/dias-especiales/',
        '/turnos/descanso-semana/',
        '/turnos/asignacion-especial/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._debe_bloquear(request):
            from turnos.services.apertura_anio_service import AperturaAnioService
            anio = AperturaAnioService.anio_objetivo()
            return redirect(reverse('apertura_anio', kwargs={'anio': anio}))
        return self.get_response(request)

    def _debe_bloquear(self, request) -> bool:
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return False
        path = request.path
        if any(path.startswith(p) for p in self.EXENTOS):
            return False
        # Peticiones AJAX: redirigir rompería el JSON esperado por el front.
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return False
        if not self._es_admin(user):
            return False
        try:
            from turnos.services.apertura_anio_service import AperturaAnioService
            situacion, _ = AperturaAnioService.situacion()
            return situacion == 'bloqueo'
        except Exception:
            # Falla ABIERTO a propósito: un error calculando el checklist no puede dejar al
            # supervisor sin poder usar la aplicación.
            logger.warning('No se pudo evaluar la apertura de año', exc_info=True)
            return False

    @staticmethod
    def _es_admin(user) -> bool:
        # Delega en la única definición del permiso para no duplicar la regla.
        from core.mixins import es_supervisor
        from core.permisos_sesion import puede_ver

        # Y además exige tener HABILITADA la sesión de apertura: a un supervisor
        # al que se le ha quitado esa pantalla, redirigirle allí lo dejaría
        # atrapado entre este middleware, que lo manda a la apertura, y
        # PermisoSesionMiddleware, que se la niega.
        return es_supervisor(user) and puede_ver(user, 'apertura_anio')


class PermisoSesionMiddleware:
    """Bloquea la URL de una sesión que el usuario tiene deshabilitada.

    Ocultar el enlace del menú no es un permiso: quien conozca la URL entra
    igual. Este middleware es la mitad seria de la función; el menú solo evita
    enseñar puertas cerradas.

    Se resuelve en `process_view` y no en `__call__` porque necesita el
    `resolver_match` (el nombre de URL), que Django solo deja disponible una vez
    ha enrutado la petición.

    ⚠ Es un guardia ADICIONAL, nunca sustituye a `AdminRequiredMixin`: una URL
    que no esté en `core.sesiones` pasa de largo y conserva el permiso que ya
    tenía. Ver la nota del catálogo sobre por qué no se mapean los endpoints
    AJAX.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        from core.permisos_sesion import puede_ver
        from core.sesiones import POR_URL_NAME

        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return None

        match = getattr(request, 'resolver_match', None)
        codigo = POR_URL_NAME.get(getattr(match, 'view_name', '') or '')
        if codigo is None or puede_ver(user, codigo):
            return None

        logger.info(
            "Sesión '%s' deshabilitada para user=%s: acceso a %s bloqueado",
            codigo, getattr(user, 'username', '?'), request.path,
        )
        # JSON para las peticiones AJAX: una redirección o una página HTML de
        # error rompería el front, que espera un cuerpo que pueda leer.
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            from django.http import JsonResponse
            return JsonResponse(
                {'error': 'No tienes habilitada esta sección.'}, status=403,
            )
        raise PermissionDenied('No tienes habilitada esta sección.')


class SinCacheEnDatosMiddleware:
    """`Cache-Control: no-store` en las respuestas de DATOS.

    EL PROBLEMA QUE CIERRA
    Las 81 respuestas `JsonResponse` del proyecto salían sin ninguna cabecera de
    caché: ni `Cache-Control`, ni `Last-Modified`, ni `ETag` (medido el
    2026-09-20 sobre `/turnos/api/mis-turnos-por-mes/`). En la práctica el
    navegador las vuelve a pedir igual, porque sin nada con qué validar no puede
    reutilizarlas. Pero eso funciona por OMISIÓN, no porque se lo hayamos dicho:
    depende de que el navegador sea prudente, y el día que uno aplique una
    heurística distinta, un explorador ve sus turnos de ayer sin saberlo.

    Son datos de una sesión autenticada que cambian solos —una solicitud que
    aprueban, un turno que le cambian—. Decirlo explícitamente cuesta esto.

    POR QUÉ NO SE LE APLICA AL HTML
    `no-store` en un documento HTML desactiva el bfcache (la caché de ida y
    vuelta): al pulsar «atrás», en vez de restaurar la página al instante, el
    navegador la vuelve a pedir entera. En móvil eso es exactamente el viaje de
    ida y vuelta que este trabajo venía a quitar, así que sería pegarse un tiro
    en el pie. El HTML no necesita la cabecera: ya sale sin validadores y con
    `Vary: Cookie`, y su contenido se regenera en cada petición.

    Si algún día se quisiera `no-store` también en el HTML, el motivo sería de
    SEGURIDAD y no de frescura (que tras cerrar sesión el botón «atrás» no
    muestre la última pantalla en un móvil compartido). Es una decisión distinta,
    con un coste distinto, y hay que tomarla a propósito.

    NO PISA LO QUE YA ESTÉ PUESTO
    Si una vista ya fijó su `Cache-Control` —`@never_cache` en core/health.py,
    por ejemplo—, se respeta. Este middleware solo rellena el hueco.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.has_header('Cache-Control'):
            return response

        # `Content-Type` puede traer el charset detrás: 'application/json; ...'.
        tipo = response.headers.get('Content-Type', '').split(';')[0].strip()
        if tipo != 'text/html':
            response.headers['Cache-Control'] = 'no-store'

        return response
