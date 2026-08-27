"""
Servicio para preparar el contexto de las vistas de solicitudes.
Responsabilidad única: Construir y preparar datos para las vistas.
"""
import logging

from django.db.models import Q

from empleados.models import Empleado
from solicitudes.models import SolicitudCambio

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
        # Se calculan en vivo (sin caché): son consultas COUNT baratas con filtro indexado
        # y solo se ejecutan al abrir el dashboard, no en un bucle caliente. Cachearlas causaba
        # contadores obsoletos, porque la invalidación de caché no cubría todas las rutas de
        # creación (cada estrategia crea la solicitud por su cuenta) ni al supervisor del
        # solicitante. La lista de pendientes (SolicitudesPendientesListView) usa exactamente
        # este mismo filtro sin caché, así que ahora el contador siempre coincide con la lista.
        mis_solicitudes_count = SolicitudCambio.objects.filter(
            explorador_solicitante=empleado
        ).count()

        solicitudes_pendientes_count = SolicitudCambio.objects.filter(
            Q(estado='pendiente', explorador_receptor=empleado, aprobado_receptor=False) |
            Q(estado='pendiente', explorador_solicitante__supervisor=empleado, aprobado_supervisor=False)
        ).distinct().count()

        return {
            'mis_solicitudes_count': mis_solicitudes_count,
            'solicitudes_pendientes_count': solicitudes_pendientes_count
        }


