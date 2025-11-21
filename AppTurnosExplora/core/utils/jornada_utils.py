"""
Utilidades para cálculo de jornadas.
Responsabilidad única: Lógica de cálculo de jornadas según reglas de negocio.
"""
from datetime import date


class JornadaUtils:
    """
    Utilidades para cálculo de jornadas.
    """
    
    @staticmethod
    def calcular_jornada_dia(jornada_base: str, fecha: date) -> str:
        """
        Calcula la jornada para un día específico, considerando la jornada base
        y las reglas de descanso para sábados (AM) y domingos (PM).
        
        Reglas:
        - Si jornada_base es "AM" y el día es sábado (weekday=5) → "Descanso"
        - Si jornada_base es "PM" y el día es domingo (weekday=6) → "Descanso"
        - En caso contrario, retorna la jornada_base
        
        IMPORTANTE: jornada_base siempre debe ser "AM" o "PM", nunca None.
        Si un explorador no tiene jornada asignada, debe manejarse antes de llamar
        a esta función.
        
        Args:
            jornada_base: Nombre de la jornada base ("AM" o "PM")
            fecha: Fecha para calcular la jornada
            
        Returns:
            Nombre de la jornada ("AM", "PM", o "Descanso")
            
        Raises:
            ValueError: Si jornada_base no es "AM" o "PM"
        """
        if not jornada_base or jornada_base not in ["AM", "PM"]:
            raise ValueError(
                f"jornada_base debe ser 'AM' o 'PM', recibido: {jornada_base}. "
                "Todos los exploradores deben tener una jornada asignada."
            )
        
        if jornada_base == "AM" and fecha.weekday() == 5:  # Sábado
            return "Descanso"
        if jornada_base == "PM" and fecha.weekday() == 6:  # Domingo
            return "Descanso"
        
        return jornada_base

