"""
Utilidades para manejo de fechas.
Responsabilidad única: Conversión y formateo de fechas.
"""
from datetime import datetime, date
from typing import Union


class DateUtils:
    """
    Utilidades para manejo de fechas.
    """
    
    DATE_FORMAT = '%Y-%m-%d'
    DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'
    DISPLAY_DATE_FORMAT = '%d/%m/%Y'
    DISPLAY_DATETIME_FORMAT = '%d/%m/%Y %H:%M'
    
    @staticmethod
    def parse_date(fecha: Union[str, date]) -> date:
        """
        Convierte una fecha (string o date) a objeto date.
        
        Args:
            fecha: String en formato 'YYYY-MM-DD' o objeto date
            
        Returns:
            Objeto date
            
        Raises:
            ValueError: Si el formato es inválido
        """
        if isinstance(fecha, date):
            return fecha
        if hasattr(fecha, 'strftime'):
            # Ya es un objeto date-like
            return fecha
        return datetime.strptime(str(fecha), DateUtils.DATE_FORMAT).date()
    
    @staticmethod
    def format_date(fecha: Union[str, date], formato: str = None) -> str:
        """
        Formatea una fecha a string.
        
        Args:
            fecha: Objeto date o string en formato 'YYYY-MM-DD'
            formato: Formato a usar (default: '%Y-%m-%d')
            
        Returns:
            String formateado
        """
        if formato is None:
            formato = DateUtils.DATE_FORMAT
        
        fecha_obj = DateUtils.parse_date(fecha)
        return fecha_obj.strftime(formato)
    
    @staticmethod
    def format_date_display(fecha: Union[str, date]) -> str:
        """
        Formatea una fecha para mostrar al usuario (DD/MM/YYYY).
        
        Args:
            fecha: Objeto date o string en formato 'YYYY-MM-DD'
            
        Returns:
            String en formato 'DD/MM/YYYY'
        """
        return DateUtils.format_date(fecha, DateUtils.DISPLAY_DATE_FORMAT)
    
    @staticmethod
    def format_datetime_display(dt: datetime) -> str:
        """
        Formatea un datetime para mostrar al usuario (DD/MM/YYYY HH:MM).
        
        Args:
            dt: Objeto datetime
            
        Returns:
            String en formato 'DD/MM/YYYY HH:MM'
        """
        return dt.strftime(DateUtils.DISPLAY_DATETIME_FORMAT) if dt else None


