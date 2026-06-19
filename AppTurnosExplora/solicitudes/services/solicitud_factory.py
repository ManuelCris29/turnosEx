"""
Solicitud Factory - Factory Pattern Implementation

This module implements the Factory Pattern to create solicitud strategies
based on the solicitud type. This centralizes the creation logic and
makes it easy to add new solicitud types.

The factory uses a multi-level lookup strategy:
1. codigo_estrategia field (manual override)
2. Name normalization (convention-based)
3. Dynamic registration from database
4. Fallback to default strategy
"""

from typing import Optional, Dict, Any
import re
import logging
from solicitudes.models import TipoSolicitudCambio
from .strategies.base_strategy import SolicitudStrategy

logger = logging.getLogger(__name__)


class SolicitudFactory:
    """
    Factory class for creating solicitud strategies.
    
    This implements the Factory Pattern to create the appropriate
    strategy based on the solicitud type. This centralizes creation
    logic and makes the system extensible.
    
    The factory supports:
    - Manual registration (for backward compatibility)
    - Dynamic registration from database
    - Name normalization for flexible matching
    - Fallback to default strategy
    """
    
    # Registry of available strategies (key: normalized name/code, value: strategy class)
    _strategies = {}
    
    # Mapping of strategy classes to their normalized codes
    _strategy_codes = {}
    
    @classmethod
    def normalize_name(cls, name: str) -> str:
        """
        Normalize a name to match strategy conventions.
        
        Examples:
        - "Cambio de Turno" -> "CT"
        - "Cambio Turno" -> "CT"
        - "Doblada" -> "DOBLADA"
        - "CT PERMANENTE" -> "CT PERMANENTE"
        
        Args:
            name: Name to normalize
            
        Returns:
            Normalized name
        """
        if not name:
            return ""
        
        # Convert to uppercase and strip whitespace
        normalized = name.upper().strip()

        # Tratar guiones bajos/medios como espacios para que códigos como 'CT_PERMANENTE'
        # se normalicen igual que 'CT PERMANENTE' (y no caigan por subcadena en 'CT').
        normalized = normalized.replace('_', ' ').replace('-', ' ')
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        # Remove common words
        normalized = re.sub(r'\b(DE|DEL|LA|EL|LOS|LAS|Y|E)\b', '', normalized)
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Common mappings (order matters - more specific first)
        mappings = {
            'CT PERMANENTE': 'CT PERMANENTE',
            'CAMBIO PERMANENTE': 'CT PERMANENTE',
            'CAMBIO TURNO': 'CT',
            'CAMBIO': 'CT',
            'CT': 'CT',  # Exact match for CT
            'DOBLADA PERMANENTE': 'DOBLADA PERMANENTE',  # antes que 'DOBLADA' (match exacto primero)
            'DOBLADA': 'DOBLADA',
            'D FDS': 'D FDS',
            'DIA FIN DE SEMANA': 'D FDS',
        }
        
        # Check exact mappings first (most important)
        if normalized in mappings:
            return mappings[normalized]
        
        # Check if normalized is a substring of any mapping key (but not the other way around)
        # This handles cases like "CAMBIO DE TURNO" -> "CAMBIO TURNO" -> "CT"
        for key, value in mappings.items():
            # Only match if the mapping key is contained in normalized (not vice versa)
            # This prevents "CT" from matching "CT PERMANENTE"
            if key in normalized and len(key) <= len(normalized):
                return value
        
        # If no mapping found, return normalized version
        return normalized
    
    @classmethod
    def register_strategy(cls, tipo_nombre: str, strategy_class):
        """
        Register a new strategy for a solicitud type.
        
        Args:
            tipo_nombre: Name or code of the solicitud type (will be normalized)
            strategy_class: Strategy class to register
        """
        normalized = cls.normalize_name(tipo_nombre)
        cls._strategies[normalized] = strategy_class
        cls._strategy_codes[strategy_class] = normalized
        logger.debug(f"Estrategia registrada: '{tipo_nombre}' -> '{normalized}' -> {strategy_class.__name__}")
    
    @classmethod
    def get_strategy(cls, tipo_solicitud: TipoSolicitudCambio) -> Optional[SolicitudStrategy]:
        """
        Get the appropriate strategy for a solicitud type.
        
        Uses multi-level lookup:
        1. codigo_estrategia field (manual override)
        2. Name normalization (convention-based)
        3. Direct name match (backward compatibility)
        4. Fallback to default strategy
        
        Args:
            tipo_solicitud: TipoSolicitudCambio instance
            
        Returns:
            SolicitudStrategy instance or None if not found
        """
        if not tipo_solicitud or not tipo_solicitud.activo:
            return None
        
        # Level 1: Try codigo_estrategia field (manual override) - EXACT MATCH FIRST
        if tipo_solicitud.codigo_estrategia:
            codigo_normalizado = cls.normalize_name(tipo_solicitud.codigo_estrategia)
            # Try exact match first
            strategy_class = cls._strategies.get(codigo_normalizado)
            if strategy_class:
                logger.debug(
                    f"Estrategia encontrada por codigo_estrategia (exacto): '{tipo_solicitud.codigo_estrategia}' "
                    f"-> '{codigo_normalizado}' -> {strategy_class.__name__}"
                )
                return strategy_class()
            # Try direct match (without normalization)
            strategy_class = cls._strategies.get(tipo_solicitud.codigo_estrategia.upper().strip())
            if strategy_class:
                logger.debug(
                    f"Estrategia encontrada por codigo_estrategia (directo): '{tipo_solicitud.codigo_estrategia}' "
                    f"-> {strategy_class.__name__}"
                )
                return strategy_class()
        
        # Level 2: Try name normalization (convention-based) - EXACT MATCH FIRST
        nombre_normalizado = cls.normalize_name(tipo_solicitud.nombre)
        strategy_class = cls._strategies.get(nombre_normalizado)
        if strategy_class:
            logger.debug(
                f"Estrategia encontrada por normalización (exacto): '{tipo_solicitud.nombre}' "
                f"-> '{nombre_normalizado}' -> {strategy_class.__name__}"
            )
            return strategy_class()
        
        # Level 3: Try direct name match (backward compatibility)
        strategy_class = cls._strategies.get(tipo_solicitud.nombre.upper().strip())
        if strategy_class:
            logger.debug(
                f"Estrategia encontrada por nombre directo: '{tipo_solicitud.nombre}' "
                f"-> {strategy_class.__name__}"
            )
            return strategy_class()
        
        # Level 4: Fallback to default strategy
        logger.warning(
            f"No se encontró estrategia para tipo '{tipo_solicitud.nombre}' "
            f"(codigo_estrategia: '{tipo_solicitud.codigo_estrategia}'). "
            f"Usando estrategia por defecto."
        )
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
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(
            "SolicitudFactory.aplicar_cambios - Solicitud ID: %d, Tipo: %s",
            solicitud.id,
            solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'N/A'
        )
        
        strategy = cls.get_strategy(solicitud.tipo_cambio)
        if not strategy:
            error_msg = f"No se encontró estrategia para el tipo: {solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'N/A'}"
            logger.error("SolicitudFactory.aplicar_cambios - %s", error_msg)
            return False, error_msg
        
        logger.info(
            "SolicitudFactory.aplicar_cambios - Estrategia encontrada: %s",
            strategy.__class__.__name__
        )
        
        try:
            result = strategy.aplicar_cambios(solicitud)
            logger.info(
                "SolicitudFactory.aplicar_cambios - Resultado: success=%s, message=%s",
                result[0],
                result[1]
            )
            return result
        except Exception as e:
            error_msg = f"Error aplicando cambios: {str(e)}"
            logger.exception("SolicitudFactory.aplicar_cambios - Excepción: %s", error_msg)
            return False, error_msg
    
    @classmethod
    def get_empleados_disponibles(cls, tipo_solicitud: TipoSolicitudCambio, 
                                 fecha: str, usuario_actual, **kwargs) -> list:
        """
        Get available employees for a solicitud type.
        
        Args:
            tipo_solicitud: TipoSolicitudCambio instance
            fecha: Date string in YYYY-MM-DD format
            usuario_actual: Current user's empleado instance
            **kwargs: Additional arguments for specific strategies (e.g. fecha_fin for CT PERMANENTE)
            
        Returns:
            List of available empleados
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info("SolicitudFactory.get_empleados_disponibles - Iniciando", extra={
            'tipo_solicitud': tipo_solicitud.nombre if tipo_solicitud else 'None',
            'tipo_solicitud_id': tipo_solicitud.id if tipo_solicitud else None,
            'codigo_estrategia': tipo_solicitud.codigo_estrategia if tipo_solicitud else None,
            'fecha': fecha,
            'usuario_id': usuario_actual.id if usuario_actual else None
        })
        
        if not tipo_solicitud:
            logger.warning("SolicitudFactory.get_empleados_disponibles - tipo_solicitud es None, usando estrategia por defecto")
            # Si no hay tipo_solicitud, usar estrategia por defecto (CambioTurnoStrategy)
            from .strategies.cambio_turno_strategy import CambioTurnoStrategy
            strategy = CambioTurnoStrategy()
        else:
            strategy = cls.get_strategy(tipo_solicitud)
            if not strategy:
                logger.warning("SolicitudFactory.get_empleados_disponibles - No se encontró estrategia, usando por defecto", extra={
                    'tipo_solicitud': tipo_solicitud.nombre,
                    'codigo_estrategia': tipo_solicitud.codigo_estrategia
                })
                from .strategies.cambio_turno_strategy import CambioTurnoStrategy
                strategy = CambioTurnoStrategy()
            else:
                logger.info("SolicitudFactory.get_empleados_disponibles - Estrategia encontrada", extra={
                    'estrategia': strategy.__class__.__name__,
                    'tipo_solicitud': tipo_solicitud.nombre
                })
        
        try:
            empleados = strategy.get_empleados_disponibles(fecha, usuario_actual, **kwargs)
            logger.info("SolicitudFactory.get_empleados_disponibles - Empleados obtenidos", extra={
                'count': len(empleados) if empleados else 0,
                'estrategia': strategy.__class__.__name__
            })
            return empleados if empleados else []
        except Exception as e:
            logger.error("SolicitudFactory.get_empleados_disponibles - Error", extra={
                'error': str(e),
                'estrategia': strategy.__class__.__name__ if strategy else 'None'
            }, exc_info=True)
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
    
    @classmethod
    def get_registered_codes(cls) -> set:
        """
        Get set of registered strategy codes.
        
        Returns:
            Set of registered codes
        """
        return set(cls._strategies.keys())


# Auto-register strategies when module is imported
def _auto_register_strategies():
    """
    Auto-register all available strategies.
    
    This function:
    1. Registers strategies manually (for backward compatibility)
    2. Dynamically registers strategies from database
    """
    try:
        # Step 1: Manual registration (backward compatibility)
        from .strategies import (
            CambioTurnoStrategy, DobladaStrategy, CTPermanenteStrategy, DFDSStrategy,
            DobladaPermanenteStrategy,
        )

        SolicitudFactory.register_strategy("CT", CambioTurnoStrategy)
        SolicitudFactory.register_strategy("DOBLADA", DobladaStrategy)
        SolicitudFactory.register_strategy("CT PERMANENTE", CTPermanenteStrategy)
        SolicitudFactory.register_strategy("D FDS", DFDSStrategy)
        SolicitudFactory.register_strategy("DOBLADA PERMANENTE", DobladaPermanenteStrategy)

        logger.info("Estrategias manuales registradas: CT, DOBLADA, CT PERMANENTE, D FDS, DOBLADA PERMANENTE")
        
        # Step 2: Dynamic registration from database
        try:
            # Import here to avoid circular imports at module level
            from django.apps import apps
            if apps.is_installed('solicitudes'):
                tipos_activos = TipoSolicitudCambio.objects.filter(activo=True)
                registrados_dinamicamente = 0
                
                for tipo in tipos_activos:
                    # Try to find strategy by codigo_estrategia or nombre
                    codigo_a_buscar = tipo.codigo_estrategia or tipo.nombre
                    codigo_normalizado = SolicitudFactory.normalize_name(codigo_a_buscar)
                    
                    # Check if already registered
                    if codigo_normalizado not in SolicitudFactory.get_registered_codes():
                        # Try to find matching strategy class
                        strategy_class = _find_strategy_by_code(codigo_normalizado)
                        if strategy_class:
                            SolicitudFactory.register_strategy(codigo_normalizado, strategy_class)
                            registrados_dinamicamente += 1
                            logger.info(
                                f"Estrategia registrada dinámicamente desde BD: "
                                f"'{tipo.nombre}' (codigo: '{tipo.codigo_estrategia}') "
                                f"-> '{codigo_normalizado}' -> {strategy_class.__name__}"
                            )
                        else:
                            logger.warning(
                                f"No se encontró estrategia para tipo '{tipo.nombre}' "
                                f"(codigo_estrategia: '{tipo.codigo_estrategia}'). "
                                f"Se usará estrategia por defecto."
                            )
                
                if registrados_dinamicamente > 0:
                    logger.info(f"Total estrategias registradas dinámicamente: {registrados_dinamicamente}")
        except Exception as db_error:
            # Database might not be ready yet (e.g., during migrations)
            logger.debug(f"No se pudieron registrar estrategias desde BD (probablemente durante migraciones): {db_error}")
        
        logger.debug("Auto-registro de estrategias completado")
    except Exception as e:
        logger.error(f"Error al auto-registrar estrategias: {e}", exc_info=True)


def _find_strategy_by_code(codigo: str):
    """
    Find strategy class by normalized code.
    
    Args:
        codigo: Normalized code to search for
        
    Returns:
        Strategy class or None if not found
    """
    try:
        from .strategies import (
            CambioTurnoStrategy, DobladaStrategy,
            CTPermanenteStrategy, DFDSStrategy, DobladaPermanenteStrategy
        )

        # Mapping of codes to strategy classes
        code_mapping = {
            'CT': CambioTurnoStrategy,
            'DOBLADA': DobladaStrategy,
            'DOBLADA PERMANENTE': DobladaPermanenteStrategy,
            'CT PERMANENTE': CTPermanenteStrategy,
            'CAMBIO PERMANENTE': CTPermanenteStrategy,
            'D FDS': DFDSStrategy,
            'DIA FIN DE SEMANA': DFDSStrategy,
        }
        
        return code_mapping.get(codigo)
    except ImportError:
        return None


# Execute auto-registration
_auto_register_strategies()
