"""
Middlewares compartidos del proyecto.
"""
import logging

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
        return es_supervisor(user)
