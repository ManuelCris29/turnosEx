"""
Servicio para preparar el contexto de las vistas de solicitudes.
Responsabilidad única: Construir y preparar datos para las vistas.
"""
from django.db.models import Q
from solicitudes.models import SolicitudCambio
from empleados.models import Empleado
from core.services.cache_service import CacheService, CACHE_TTL_SHORT
import logging

logger = logging.getLogger(__name__)


class SolicitudContextService:
    """
    Servicio para preparar el contexto de las vistas de solicitudes.
    Responsabilidad única: Construir estructuras de datos para las vistas.
    """

    @staticmethod
    def get_context_data_for_solicitudes_view(empleado: Empleado) -> dict:
        """
        Prepara el contexto para SolicitudesView.
        
        Args:
            empleado: Empleado autenticado
            
        Returns:
            Diccionario con 'mis_solicitudes_count' y 'solicitudes_pendientes_count'
        """
        cache_key_mis = f"solicitudes_count_mis_{empleado.id}"
        cache_key_pend = f"solicitudes_count_pend_{empleado.id}"
        
        def calcular_mis_solicitudes():
            return SolicitudCambio.objects.filter(
                explorador_solicitante=empleado
            ).count()
        
        def calcular_pendientes():
            return SolicitudCambio.objects.filter(
                Q(estado='pendiente', explorador_receptor=empleado, aprobado_receptor=False) |
                Q(estado='pendiente', explorador_solicitante__supervisor=empleado, aprobado_supervisor=False)
            ).distinct().count()
        
        mis_solicitudes_count = CacheService.get_or_set(
            cache_key_mis,
            calcular_mis_solicitudes,
            ttl=CACHE_TTL_SHORT
        )
        
        solicitudes_pendientes_count = CacheService.get_or_set(
            cache_key_pend,
            calcular_pendientes,
            ttl=CACHE_TTL_SHORT
        )
        
        return {
            'mis_solicitudes_count': mis_solicitudes_count,
            'solicitudes_pendientes_count': solicitudes_pendientes_count
        }


