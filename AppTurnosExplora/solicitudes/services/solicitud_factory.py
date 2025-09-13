"""
Solicitud Factory - Factory Pattern Implementation

This module implements the Factory Pattern to create solicitud strategies
based on the solicitud type. This centralizes the creation logic and
makes it easy to add new solicitud types.
"""

from typing import Optional, Dict, Any
from solicitudes.models import TipoSolicitudCambio
from .strategies.base_strategy import SolicitudStrategy


class SolicitudFactory:
    """
    Factory class for creating solicitud strategies.
    
    This implements the Factory Pattern to create the appropriate
    strategy based on the solicitud type. This centralizes creation
    logic and makes the system extensible.
    """
    
    # Registry of available strategies
    _strategies = {}
    
    @classmethod
    def register_strategy(cls, tipo_nombre: str, strategy_class):
        """
        Register a new strategy for a solicitud type.
        
        Args:
            tipo_nombre: Name of the solicitud type
            strategy_class: Strategy class to register
        """
        cls._strategies[tipo_nombre] = strategy_class
    
    @classmethod
    def get_strategy(cls, tipo_solicitud: TipoSolicitudCambio) -> Optional[SolicitudStrategy]:
        """
        Get the appropriate strategy for a solicitud type.
        
        Args:
            tipo_solicitud: TipoSolicitudCambio instance
            
        Returns:
            SolicitudStrategy instance or None if not found
        """
        if not tipo_solicitud or not tipo_solicitud.activo:
            return None
        
        strategy_class = cls._strategies.get(tipo_solicitud.nombre)
        if strategy_class:
            return strategy_class()
        
        # Fallback to default strategy if not found
        return cls._get_default_strategy(tipo_solicitud.nombre)
    
    @classmethod
    def _get_default_strategy(cls, tipo_nombre: str) -> Optional[SolicitudStrategy]:
        """
        Get default strategy for unknown solicitud types.
        
        Args:
            tipo_nombre: Name of the solicitud type
            
        Returns:
            Default strategy or None
        """
        # Import here to avoid circular imports
        from .strategies.cambio_turno_strategy import CambioTurnoStrategy
        return CambioTurnoStrategy()
    
    @classmethod
    def crear_solicitud(cls, tipo_solicitud: TipoSolicitudCambio, datos: Dict[str, Any]) -> tuple:
        """
        Create a solicitud using the appropriate strategy.
        
        Args:
            tipo_solicitud: TipoSolicitudCambio instance
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (solicitud_instance, message)
        """
        strategy = cls.get_strategy(tipo_solicitud)
        if not strategy:
            return None, f"No se encontró estrategia para el tipo: {tipo_solicitud.nombre}"
        
        try:
            return strategy.crear_solicitud(datos)
        except Exception as e:
            return None, f"Error creando solicitud: {str(e)}"
    
    @classmethod
    def validar_solicitud(cls, tipo_solicitud: TipoSolicitudCambio, datos: Dict[str, Any]) -> tuple:
        """
        Validate solicitud data using the appropriate strategy.
        
        Args:
            tipo_solicitud: TipoSolicitudCambio instance
            datos: Dictionary containing solicitud data
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        strategy = cls.get_strategy(tipo_solicitud)
        if not strategy:
            return False, f"No se encontró estrategia para el tipo: {tipo_solicitud.nombre}"
        
        try:
            return strategy.validar_solicitud(datos)
        except Exception as e:
            return False, f"Error validando solicitud: {str(e)}"
    
    @classmethod
    def aplicar_cambios(cls, solicitud: 'SolicitudCambio') -> tuple:
        """
        Apply changes for an approved solicitud using the appropriate strategy.
        
        Args:
            solicitud: SolicitudCambio instance
            
        Returns:
            Tuple of (success, message)
        """
        strategy = cls.get_strategy(solicitud.tipo_cambio)
        if not strategy:
            return False, f"No se encontró estrategia para el tipo: {solicitud.tipo_cambio.nombre}"
        
        try:
            return strategy.aplicar_cambios(solicitud)
        except Exception as e:
            return False, f"Error aplicando cambios: {str(e)}"
    
    @classmethod
    def get_empleados_disponibles(cls, tipo_solicitud: TipoSolicitudCambio, 
                                 fecha: str, usuario_actual) -> list:
        """
        Get available employees for a solicitud type.
        
        Args:
            tipo_solicitud: TipoSolicitudCambio instance
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            
        Returns:
            List of available empleados
        """
        strategy = cls.get_strategy(tipo_solicitud)
        if not strategy:
            return []
        
        try:
            return strategy.get_empleados_disponibles(fecha, usuario_actual)
        except Exception:
            return []
    
    @classmethod
    def get_turno_explorador(cls, tipo_solicitud: TipoSolicitudCambio, 
                           explorador_id: int, fecha: str) -> Dict[str, Any]:
        """
        Get turn information for an explorer using the appropriate strategy.
        
        Args:
            tipo_solicitud: TipoSolicitudCambio instance
            explorador_id: ID of the empleado
            fecha: Date string in YYYY-MM-DD format
            
        Returns:
            Dictionary with turn information
        """
        strategy = cls.get_strategy(tipo_solicitud)
        if not strategy:
            return {}
        
        try:
            return strategy.get_turno_explorador(explorador_id, fecha)
        except Exception:
            return {}
    
    @classmethod
    def get_available_types(cls) -> list:
        """
        Get list of available solicitud types.
        
        Returns:
            List of registered strategy names
        """
        return list(cls._strategies.keys())


# Auto-register strategies when module is imported
def _auto_register_strategies():
    """Auto-register all available strategies"""
    try:
        from .strategies import CambioTurnoStrategy, DobladaStrategy, CTPermanenteStrategy, DFDSStrategy
        
        SolicitudFactory.register_strategy("CT", CambioTurnoStrategy)
        SolicitudFactory.register_strategy("DOBLADA", DobladaStrategy)
        SolicitudFactory.register_strategy("CT PERMANENTE", CTPermanenteStrategy)
        SolicitudFactory.register_strategy("D FDS", DFDSStrategy)
        
        import logging
        logger = logging.getLogger(__name__)
        logger.debug("Estrategias auto-registradas correctamente")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error al auto-registrar estrategias: {e}")

# Execute auto-registration
_auto_register_strategies()
