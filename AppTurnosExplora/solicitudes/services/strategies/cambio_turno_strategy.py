"""
Cambio Turno Strategy - Implementation for "Cambio Turno" solicitud type

This strategy implements the specific logic for "Cambio Turno" solicitudes,
migrating the current SolicitudService functionality to the new architecture.
"""

from typing import Dict, Any, Tuple, Optional
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from empleados.models import Empleado
from .base_strategy import SolicitudStrategy


class CambioTurnoStrategy(SolicitudStrategy):
    """
    Strategy for "Cambio Turno" solicitudes.
    
    This implements the specific logic for turn change requests,
    including validation, creation, and application of changes.
    """
    
    def __init__(self):
        super().__init__("CT")
    
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate cambio turno specific data.
        
        Args:
            datos: Dictionary containing:
                - explorador_solicitante: Empleado instance
                - explorador_receptor: Empleado instance  
                - fecha_cambio_turno: Date string
                
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Import here to avoid circular imports
            from ..solicitud_validator import SolicitudValidator
            
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            fecha = datos.get('fecha_cambio_turno')
            
            if not all([explorador_solicitante, explorador_receptor, fecha]):
                return False, "Faltan datos requeridos para la validación"
            
            # Use centralized validator
            SolicitudValidator.validar_empleado_activo(explorador_solicitante)
            SolicitudValidator.validar_empleado_activo(explorador_receptor)
            SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)
            SolicitudValidator.validar_jornada_en_fecha(explorador_solicitante, fecha)
            SolicitudValidator.validar_jornada_en_fecha(explorador_receptor, fecha)
            SolicitudValidator.validar_duplicada_misma_fecha(explorador_solicitante, explorador_receptor, fecha)
            
            return True, "Solicitud válida"
            
        except Exception as e:
            return False, str(e)
    
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a cambio turno solicitud.
        
        Args:
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        try:
            # Import here to avoid circular imports
            from ..solicitud_service import SolicitudService
            
            explorador_solicitante = datos.get('explorador_solicitante')
            explorador_receptor = datos.get('explorador_receptor')
            tipo_cambio = datos.get('tipo_cambio')
            comentario = datos.get('comentario')
            fecha_cambio_turno = datos.get('fecha_cambio_turno')
            
            # Use existing service logic
            return SolicitudService.crear_solicitud_cambio(
                explorador_solicitante=explorador_solicitante,
                explorador_receptor=explorador_receptor,
                tipo_cambio=tipo_cambio,
                comentario=comentario,
                fecha_cambio_turno=fecha_cambio_turno
            )
            
        except Exception as e:
            return None, f"Error creando solicitud de cambio de turno: {str(e)}"
    
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Apply turn change when solicitud is approved.
        Creates records in Turno table for both employees.
        
        Args:
            solicitud: The approved solicitud instance
            
        Returns:
            Tuple of (success, message)
        """
        try:
            from turnos.models import Turno
            from datetime import datetime
            from ..solicitud_service import SolicitudService
            
            # Convertir fecha a objeto date
            fecha_cambio = solicitud.fecha_cambio_turno
            
            # 1. Obtener jornadas actuales de ambos empleados para esa fecha
            jornada_solicitante = SolicitudService.get_jornada_explorador_fecha(
                solicitud.explorador_solicitante.id, 
                fecha_cambio.strftime('%Y-%m-%d')
            )
            jornada_receptor = SolicitudService.get_jornada_explorador_fecha(
                solicitud.explorador_receptor.id, 
                fecha_cambio.strftime('%Y-%m-%d')
            )
            
            if not jornada_solicitante or not jornada_receptor:
                return False, "No se pudieron obtener las jornadas de los empleados"
            
            # 2. Obtener salas de ambos empleados
            salas_solicitante = SolicitudService.get_salas_explorador(solicitud.explorador_solicitante.id)
            salas_receptor = SolicitudService.get_salas_explorador(solicitud.explorador_receptor.id)
            
            if not salas_solicitante.exists() or not salas_receptor.exists():
                return False, "No se pudieron obtener las salas de los empleados"
            
            # 3. Crear registro de turno para el solicitante (con jornada del receptor)
            turno_solicitante = Turno.objects.create(
                explorador=solicitud.explorador_solicitante,
                fecha=fecha_cambio,
                jornada=jornada_receptor,  # Jornada del receptor
                sala=salas_receptor.first().sala,  # Sala del receptor
                tipo_cambio='CT'
            )
            
            # 4. Crear registro de turno para el receptor (con jornada del solicitante)
            turno_receptor = Turno.objects.create(
                explorador=solicitud.explorador_receptor,
                fecha=fecha_cambio,
                jornada=jornada_solicitante,  # Jornada del solicitante
                sala=salas_solicitante.first().sala,  # Sala del solicitante
                tipo_cambio='CT'
            )
            
            # 5. Actualizar la solicitud con las referencias a los turnos creados
            solicitud.turno_origen = turno_solicitante  # Turno original del solicitante
            solicitud.turno_destino = turno_receptor    # Turno resultante del receptor
            solicitud.save()
            
            return True, "Cambio de turno aplicado correctamente"
            
        except Exception as e:
            return False, f"Error aplicando cambio de turno: {str(e)}"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado) -> list:
        """
        Get available employees for cambio turno (jornada contraria).
        
        Args:
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            
        Returns:
            List of available empleados
        """
        try:
            # Import here to avoid circular imports
            from ..solicitud_service import SolicitudService
            
            # For cambio turno, filter by opposite jornada
            return SolicitudService.get_empleados_disponibles(
                fecha, 
                usuario_actual, 
                solo_jornada_contraria=True
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
