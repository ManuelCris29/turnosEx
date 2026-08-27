"""
Interfaz para servicios de turnos.
Aplicación del principio Dependency Inversion (DIP).
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class ITurnoService(ABC):
    """
    Interfaz para servicios que gestionan turnos.
    
    Esta interfaz permite que las estrategias dependan de una abstracción
    en lugar de una implementación concreta, siguiendo el principio DIP.
    """
    
    @abstractmethod
    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene el turno de un explorador para una fecha específica.
        
        Args:
            explorador_id: ID del explorador
            fecha: Fecha en formato 'YYYY-MM-DD'
            
        Returns:
            Diccionario con información del turno o None
        """
        pass

    @abstractmethod
    def get_salas_explorador(self, explorador_id: int) -> Any:
        """
        Obtiene las salas asociadas a un explorador.
        """
        pass

    @abstractmethod
    def get_turnos_por_fecha(self, explorador: Any, fecha_inicio, fecha_fin) -> Dict[Any, Any]:
        """
        Obtiene turnos de un explorador en un rango de fechas.
        """
        pass

