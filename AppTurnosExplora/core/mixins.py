"""
Mixins compartidos para el proyecto
"""
import logging

from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)


class AdminRequiredMixin:
    """
    Mixin para verificar permisos de administrador.
    
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
        # Verificar si el usuario es staff o tiene rol de Supervisor
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        # Si es staff, permitir acceso
        if request.user.is_staff:
            return super().dispatch(request, *args, **kwargs)
        
        # Verificar si tiene rol de Supervisor
        try:
            empleado = request.user.empleado
            tiene_rol_supervisor = empleado.empleadorole_set.filter(
                role__nombre__icontains='supervisor'
            ).exists()
            if tiene_rol_supervisor:
                return super().dispatch(request, *args, **kwargs)
        except Exception:
            # Falla cerrado (deniega abajo); se registra para poder diagnosticar
            # por qué un supervisor legítimo pudo quedar sin acceso.
            logger.warning(
                "Error verificando rol de supervisor para user=%s",
                getattr(request.user, 'username', '?'),
                exc_info=True,
            )

        # Si no cumple ninguna condición, denegar acceso
        raise PermissionDenied("No tienes permisos de administrador.")


