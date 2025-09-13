"""
Base Strategy for Solicitud types - Domain-Driven Design (DDD) + Clean Architecture

This module implements the Strategy Pattern for different types of solicitudes.
Each solicitud type (Cambio Turno, Doblada, CT Permanente, D FDS) will have
its own strategy that inherits from this base class.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
from django.core.exceptions import ValidationError
from solicitudes.models import SolicitudCambio
from empleados.models import Empleado


class SolicitudStrategy(ABC):
    """
    Abstract base class for solicitud strategies.
    
    This implements the Strategy Pattern where each type of solicitud
    (Cambio Turno, Doblada, etc.) has its own strategy with specific
    validation, creation, and application logic.
    """
    
    def __init__(self, tipo_solicitud: str):
        """
        Initialize the strategy with the solicitud type.
        
        Args:
            tipo_solicitud: Name of the solicitud type (e.g., "Cambio Turno", "DOBLADA")
        """
        self.tipo_solicitud = tipo_solicitud
    
    @abstractmethod
    def validar_solicitud(self, datos: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate solicitud-specific data.
        
        Args:
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        pass
    
    @abstractmethod
    def crear_solicitud(self, datos: Dict[str, Any]) -> Tuple[Optional[SolicitudCambio], str]:
        """
        Create a new solicitud with type-specific logic.
        
        Args:
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        pass
    
    @abstractmethod
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> Tuple[bool, str]:
        """
        Apply changes when solicitud is approved.
        
        Args:
            solicitud: The approved solicitud instance
            
        Returns:
            Tuple of (success, message)
        """
        pass
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado) -> list:
        """
        Get available employees for this solicitud type.
        Can be overridden by specific strategies.
        
        Args:
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            
        Returns:
            List of available empleados
        """
        # Default implementation - can be overridden
        from ..solicitud_service import SolicitudService
        return SolicitudService.get_empleados_disponibles(fecha, usuario_actual)
    
    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        """
        Get turn information for an explorer.
        Can be overridden by specific strategies.
        
        Args:
            explorador_id: ID of the empleado
            fecha: Date string in YYYY-MM-DD format
            
        Returns:
            Dictionary with turn information
        """
        # Default implementation - can be overridden
        from ..solicitud_service import SolicitudService
        return SolicitudService.get_turno_explorador(explorador_id, fecha)
    
    def __str__(self):
        return f"{self.__class__.__name__}({self.tipo_solicitud})"
    
    def __repr__(self):
        return f"{self.__class__.__name__}(tipo_solicitud='{self.tipo_solicitud}')"

