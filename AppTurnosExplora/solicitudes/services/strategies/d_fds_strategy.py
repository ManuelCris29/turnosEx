"""
D FDS Strategy - Implementation for "D FDS" solicitud type

This strategy implements the specific logic for "D FDS" solicitudes,
which are requests for weekend double shifts.
"""

from typing import Dict, Any, Tuple, Optional
from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy


class DFDSStrategy(SolicitudStrategy):
    """
    Strategy for "D FDS" (Doblada Fin de Semana) solicitudes.
    
    This implements the specific logic for weekend double shift requests,
    including validation, creation, and application of changes.
    """
    
    def __init__(self):
        super().__init__("D FDS")
    
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate D FDS specific data.
        
        Args:
            datos: Dictionary containing:
                - explorador_solicitante: Empleado instance
                - fecha_cambio_turno: Date string (must be weekend)
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
            
            # Validate that fecha is a weekend
            from datetime import datetime
            try:
                fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
                # weekday() returns 0=Monday, 6=Sunday
                if fecha_obj.weekday() not in [5, 6]:  # Saturday or Sunday
                    return False, "D FDS solo se puede solicitar para fines de semana (sábado o domingo)"
            except ValueError:
                return False, "Formato de fecha inválido"
            
            # TODO: Add more specific validations
            # - Check if empleado already has a D FDS for that weekend
            # - Check if empleado has permission for weekend shifts
            # - Check if fecha is not in the past
            
            return True, "Solicitud de D FDS válida"
            
        except Exception as e:
            return False, f"Error validando D FDS: {str(e)}"
    
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a D FDS solicitud.
        
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
                explorador_receptor=explorador_solicitante,  # Self-request for D FDS
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fecha_cambio_turno,
                estado='pendiente'
            )
            
            # Create the D FDS detail (using DobladaDetalle model)
            DobladaDetalle.objects.create(
                solicitud=solicitud,
                minutos_deuda=minutos_deuda
            )
            
            # TODO: Send notifications
            # This will be handled by the WorkflowEngine
            
            return solicitud, "Solicitud de D FDS creada correctamente"
            
        except Exception as e:
            return None, f"Error creando solicitud de D FDS: {str(e)}"
    
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Apply D FDS when solicitud is approved.
        
        Args:
            solicitud: The approved solicitud instance
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # TODO: Implement D FDS application logic
            # - Add weekend extra hours to empleado's record
            # - Update deuda tracking with weekend bonus
            # - Send confirmation notifications
            
            return True, "D FDS aplicada correctamente"
            
        except Exception as e:
            return False, f"Error aplicando D FDS: {str(e)}"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado) -> list:
        """
        Get available employees for D FDS (all active employees).
        
        Args:
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            
        Returns:
            List of available empleados
        """
        try:
            # For D FDS, show all active employees (including self)
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
