"""
Servicio para consultas de solicitudes.

Responsabilidad única: Consultar y filtrar solicitudes según diferentes criterios.
"""
import logging

from django.db.models import Q

from core.utils.date_utils import DateUtils
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio

logger = logging.getLogger(__name__)


class SolicitudConsultaService:
    """
    Servicio para consultas de solicitudes.
    
    Responsabilidad única: Lectura y consulta de solicitudes.
    """
    
    @staticmethod
    def get_tipos_solicitud_activos():
        """
        Obtiene todos los tipos de solicitud activos.
        
        Returns:
            QuerySet de TipoSolicitudCambio activos
        """
        return TipoSolicitudCambio.objects.filter(activo=True)
    
    @staticmethod
    def get_solicitudes_usuario(usuario):
        """
        Obtiene las solicitudes de un usuario específico.
        
        Args:
            usuario: Objeto User con empleado asociado
        
        Returns:
            QuerySet de SolicitudCambio del usuario
        """
        if hasattr(usuario, 'empleado'):
            return (
                SolicitudCambio.objects
                .filter(explorador_solicitante=usuario.empleado)
                .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')
                .order_by('-fecha_solicitud')
            )
        return SolicitudCambio.objects.none()
    
    @staticmethod
    def get_solicitudes_pendientes():
        """
        Obtiene todas las solicitudes pendientes.
        
        Returns:
            QuerySet de SolicitudCambio pendientes
        """
        return (
            SolicitudCambio.objects
            .filter(estado='pendiente')
            .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')
            .order_by('-fecha_solicitud')
        )
    
    @staticmethod
    def get_solicitudes_por_receptor(receptor):
        """
        Obtiene las solicitudes pendientes que debe aprobar un receptor.
        
        Args:
            receptor: Objeto Empleado receptor
        
        Returns:
            QuerySet de SolicitudCambio pendientes para el receptor
        """
        return (
            SolicitudCambio.objects
            .filter(
                explorador_receptor=receptor,
                estado='pendiente',
                aprobado_receptor=False,  # Ocultar si el receptor ya aprobó
            )
            .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')
            .order_by('-fecha_solicitud')
        )
    
    @staticmethod
    def get_solicitudes_por_supervisor(supervisor):
        """
        Obtiene las solicitudes pendientes que debe aprobar un supervisor.
        
        Args:
            supervisor: Objeto Empleado supervisor
        
        Returns:
            QuerySet de SolicitudCambio pendientes para el supervisor
        """
        return (
            SolicitudCambio.objects
            .filter(
                explorador_solicitante__supervisor=supervisor,
                estado='pendiente',
                aprobado_supervisor=False,  # Ocultar si el supervisor ya aprobó
            )
            .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')
            .order_by('-fecha_solicitud')
        )
    
    @staticmethod
    def get_estado_aprobacion_solicitud(solicitud):
        """
        Obtiene el estado de aprobación de una solicitud en formato legible.
        
        Args:
            solicitud: Objeto SolicitudCambio
        
        Returns:
            String con el estado de aprobación
        """
        if solicitud.estado == 'aprobada':
            return 'Aprobada por ambos'
        elif solicitud.estado == 'rechazada':
            if solicitud.aprobado_supervisor == False:
                return 'Rechazada por supervisor'
            elif solicitud.aprobado_receptor == False:
                return 'Rechazada por compañero'
            else:
                return 'Rechazada'
        elif solicitud.estado == 'pendiente':
            if solicitud.aprobado_supervisor and solicitud.aprobado_receptor:
                return 'Pendiente de confirmación final'
            elif solicitud.aprobado_supervisor:
                return 'Aprobada por supervisor, pendiente compañero'
            elif solicitud.aprobado_receptor:
                return 'Aprobada por compañero, pendiente supervisor'
            else:
                return 'Pendiente de ambos'
        else:
            return solicitud.get_estado_display()
    
    @staticmethod
    def contar_cambios_explorador_fecha(explorador_id: int, fecha) -> int:
        """
        Cuenta el número de solicitudes aprobadas donde el explorador participa
        (como solicitante o receptor) para una fecha específica.
        
        Este método se usa para validar el límite de cambios por explorador/fecha.
        
        Args:
            explorador_id: ID del explorador
            fecha: Fecha del cambio (puede ser string 'YYYY-MM-DD' o date object)
            
        Returns:
            Número de solicitudes aprobadas donde el explorador participa en esa fecha
        """
        # Convertir fecha a objeto date si es string
        if isinstance(fecha, str):
            fecha_obj = DateUtils.parse_date(fecha)
        else:
            fecha_obj = fecha
        
        # Contar solicitudes aprobadas donde el explorador es solicitante o receptor
        count = SolicitudCambio.objects.filter(
            Q(explorador_solicitante_id=explorador_id) | Q(explorador_receptor_id=explorador_id),
            fecha_cambio_turno=fecha_obj,
            estado='aprobada'
        ).count()
        
        logger.debug(
            "contar_cambios_explorador_fecha - Explorador ID: %d, Fecha: %s, Cambios aprobados: %d",
            explorador_id,
            fecha_obj,
            count
        )
        
        return count
    
