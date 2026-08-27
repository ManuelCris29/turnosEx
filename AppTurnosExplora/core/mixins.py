"""
Mixins compartidos para el proyecto
"""
import logging

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def es_supervisor(user) -> bool:
    """
    True si el usuario puede ver la operación completa: staff o rol Supervisor.

    Única definición del permiso: la usan tanto las vistas HTML
    (`AdminRequiredMixin`) como las de API (`SupervisorApiRequiredMixin`) y el
    middleware. Falla cerrado y deja rastro en el log para poder diagnosticar
    por qué un supervisor legítimo pudo quedar sin acceso.

    El rol se compara EXACTO contra `Role.SUPERVISOR`: con la coincidencia
    parcial anterior, cualquier rol creado desde /empleados/roles/ que
    contuviera "supervisor" concedía acceso total.
    """
    from empleados.models import Role

    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_staff:
        return True
    try:
        return user.empleado.empleadorole_set.filter(
            role__nombre__iexact=Role.SUPERVISOR
        ).exists()
    except Exception:
        logger.warning(
            "Error verificando rol de supervisor para user=%s",
            getattr(user, 'username', '?'),
            exc_info=True,
        )
        return False


class AdminRequiredMixin:
    """
    Mixin para verificar permisos de administrador en vistas HTML.

    Permite acceso si:
    - El usuario es staff, o
    - El usuario tiene rol de Supervisor

    Uso:
        class MiView(LoginRequiredMixin, AdminRequiredMixin, ListView):
            ...
    """

    def dispatch(self, request, *args, **kwargs):
        """
        Verifica permisos antes de procesar la solicitud.

        Raises:
            PermissionDenied: Si el usuario no tiene permisos
        """
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        if es_supervisor(request.user):
            return super().dispatch(request, *args, **kwargs)

        raise PermissionDenied("No tienes permisos de administrador.")


class SupervisorApiRequiredMixin:
    """
    Igual que `AdminRequiredMixin` pero para endpoints JSON: en vez de lanzar
    PermissionDenied (que devuelve una página HTML de error) responde
    403 con un cuerpo JSON que el front puede mostrar tal cual.
    """

    def dispatch(self, request, *args, **kwargs):
        if not es_supervisor(request.user):
            return JsonResponse({'error': 'Sin permisos'}, status=403)
        return super().dispatch(request, *args, **kwargs)


class StaffRequiredMixin:
    """
    Restringe una vista al ADMINISTRADOR de la aplicación (`is_staff`).

    Más estricto que `AdminRequiredMixin`, que también deja pasar al rol
    Supervisor. Lo usa la pantalla de permisos de sesión: si un supervisor
    pudiera editarla, podría devolverse a sí mismo cualquier sesión que el
    administrador le hubiera quitado, y la función entera no serviría de nada.
    """

    def dispatch(self, request, *args, **kwargs):
        if not getattr(request.user, 'is_authenticated', False):
            return self.handle_no_permission()
        if request.user.is_staff:
            return super().dispatch(request, *args, **kwargs)
        raise PermissionDenied('Solo un administrador puede gestionar los permisos de sesión.')
