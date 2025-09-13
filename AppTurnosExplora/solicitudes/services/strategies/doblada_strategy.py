"""
Doblada Strategy - Implementation for "DOBLADA" solicitud type

This strategy implements the specific logic for "DOBLADA" solicitudes,
which are requests to work extra hours (double shift).
"""

from typing import Dict, Any, Tuple, Optional
from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy


class DobladaStrategy(SolicitudStrategy):
    """
    Strategy for "DOBLADA" solicitudes.
    
    This implements the specific logic for double shift requests,
    including validation, creation, and application of changes.
    """
    
    def __init__(self):
        super().__init__("DOBLADA")
    
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate doblada specific data.
        
        Args:
            datos: Dictionary containing:
                - explorador_solicitante: Empleado instance
                - fecha_cambio_turno: Date string
                - minutos_deuda: Integer (optional, defaults to 30)
                
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            explorador_solicitante = datos.get('explorador_solicitante')
            fecha = datos.get('fecha_cambio_turno')
            minutos_deuda = datos.get('minutos_deuda', 30)
            
            if not explorador_solicitante:
                return False, "Explorador solicitante es requerido"
            
            if not fecha:
                return False, "Fecha es requerida"
            
            if not isinstance(minutos_deuda, int) or minutos_deuda <= 0:
                return False, "Minutos de deuda debe ser un número positivo"
            
            # Validate empleado is active
            if not explorador_solicitante.activo:
                return False, "El explorador no está activo"
            
            # TODO: Add more specific validations for doblada
            # - Check if empleado already has a doblada for that date
            # - Check if empleado has permission for dobladas
            # - Check if fecha is not in the past
            
            return True, "Solicitud de doblada válida"
            
        except Exception as e:
            return False, f"Error validando doblada: {str(e)}"
    
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a doblada solicitud.
        
        Args:
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        try:
            from django.utils import timezone
            
            explorador_solicitante = datos.get('explorador_solicitante')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario', '')
            fecha_cambio_turno = datos.get('fecha_cambio_turno')
            minutos_deuda = datos.get('minutos_deuda', 30)
            
            # Create the main solicitud
            solicitud = SolicitudCambio.objects.create(
                explorador_solicitante=explorador_solicitante,
                explorador_receptor=explorador_solicitante,  # Self-request for doblada
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fecha_cambio_turno,
                estado='pendiente'
            )
            
            # Create the doblada detail
            DobladaDetalle.objects.create(
                solicitud=solicitud,
                minutos_deuda=minutos_deuda
            )
            
            # TODO: Send notifications
            # This will be handled by the WorkflowEngine
            
            return solicitud, "Solicitud de doblada creada correctamente"
            
        except Exception as e:
            return None, f"Error creando solicitud de doblada: {str(e)}"
    
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Apply doblada when solicitud is approved.
        
        Args:
            solicitud: The approved solicitud instance
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # TODO: Implement doblada application logic
            # - Add extra hours to empleado's record
            # - Update deuda tracking
            # - Send confirmation notifications
            
            return True, "Doblada aplicada correctamente"
            
        except Exception as e:
            return False, f"Error aplicando doblada: {str(e)}"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado) -> list:
        """
        Get available employees for doblada (all active employees).
        
        Args:
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            
        Returns:
            List of available empleados
        """
        try:
            # For doblada, show all active employees (including self)
            from ..solicitud_service import SolicitudService
            
            return SolicitudService.get_empleados_disponibles(
                fecha, 
                usuario_actual, 
                solo_jornada_contraria=False
            )
            
        except Exception:
            return []
    
    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        """
        Get turn information for an explorer.
        
        Args:
            explorador_id: ID of the empleado
            fecha: Date string in YYYY-MM-DD format
            
        Returns:
            Dictionary with turn information
        """
        try:
            # Import here to avoid circular imports
            from ..solicitud_service import SolicitudService
            
            return SolicitudService.get_turno_explorador(explorador_id, fecha)
            
        except Exception:
            return {}
