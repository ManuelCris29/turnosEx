"""
Interfaz para servicios de disponibilidad de empleados.
Aplicación del principio Dependency Inversion (DIP).
"""
from abc import ABC, abstractmethod
from typing import Iterable

from empleados.models import Empleado


class IEmpleadoDisponibilidadService(ABC):
    """
    Interfaz para servicios que obtienen empleados disponibles.
    
    Esta interfaz permite que las estrategias dependan de una abstracción
    en lugar de una implementación concreta, siguiendo el principio DIP.
    """
    
    @abstractmethod
    def get_empleados_disponibles(self, fecha: str, usuario_actual: Empleado = None, solo_jornada_contraria: bool = False) -> Iterable[Empleado]:
        """
        Obtiene los empleados disponibles para una fecha específica.
        
        Args:
            fecha: Fecha en formato 'YYYY-MM-DD'
            usuario_actual: Empleado actual (opcional)
            solo_jornada_contraria: Si True, filtra por jornada contraria
            
        Returns:
            Iterable de empleados disponibles
        """
        pass

    @abstractmethod
    def get_empleados_jornada_contraria(self, fecha: str, empleado_actual: Empleado) -> Iterable[Empleado]:
        """
        Obtiene los empleados que se encuentran en la jornada contraria al empleado actual.

        Args:
            fecha: Fecha en formato 'YYYY-MM-DD'
            empleado_actual: Empleado de referencia

        Returns:
            Iterable de empleados que cumplen la condición
        """
        pass

