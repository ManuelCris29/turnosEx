"""
Interfaces y abstracciones para aplicar Dependency Inversion Principle (DIP).
"""
from .empleado_disponibilidad_interface import IEmpleadoDisponibilidadService
from .turno_interface import ITurnoService

__all__ = ['IEmpleadoDisponibilidadService', 'ITurnoService']


