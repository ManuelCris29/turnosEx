"""
Servicio para gestión de jornadas de exploradores.

Responsabilidad única: Obtener y calcular jornadas de exploradores para fechas específicas.
"""
from datetime import datetime
from empleados.models import Empleado
from turnos.models import Turno, AsignarJornadaExplorador
from core.services.cache_service import CacheService, CACHE_TTL_LONG
import logging

logger = logging.getLogger(__name__)


class JornadaService:
    """
    Servicio para gestión de jornadas de exploradores.
    
    Responsabilidad única: Obtener y calcular jornadas para fechas específicas.
    """
    
    @staticmethod
    def get_jornada_explorador_fecha(explorador_id, fecha):
        """
        Obtiene la jornada de un explorador para una fecha específica.
        Considera jornada fija vs cambios específicos.
        
        Prioridad:
        1. Turno específico para esa fecha (cambio aprobado)
        2. Jornada predeterminada (AsignarJornadaExplorador)
        
        Args:
            explorador_id: ID del explorador
            fecha: Fecha en formato string 'YYYY-MM-DD' o date object
        
        Returns:
            Jornada object o None si no tiene jornada asignada
        """
        try:
            # Convertir fecha a objeto date si es string
            if isinstance(fecha, str):
                fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            else:
                fecha_obj = fecha
            
            explorador = Empleado.objects.get(id=explorador_id)
            
            # 1. Buscar si hay un turno específico para esa fecha (cambio aprobado)
            turno_especifico = Turno.objects.filter(
                explorador=explorador, 
                fecha=fecha_obj
            ).select_related('jornada').first()
            
            if turno_especifico:
                logger.info("JornadaService.get_jornada_explorador_fecha - Jornada obtenida de Turno", extra={
                    'explorador_id': explorador_id,
                    'fecha': str(fecha_obj),
                    'jornada_nombre': turno_especifico.jornada.nombre,
                    'turno_id': turno_especifico.id,
                    'fuente': 'Turno (cambio aprobado)'
                })
                return turno_especifico.jornada  # Jornada del cambio
            
            # 2. Si no hay turno específico, usar la jornada fija del explorador
            #    (sin caché, para reflejar inmediatamente cambios en AsignarJornadaExplorador)
            asignacion_jornada = AsignarJornadaExplorador.objects.select_related('jornada').filter(
                explorador=explorador,
                fecha_inicio__lte=fecha_obj
            ).order_by('-fecha_inicio').first()
            
            if asignacion_jornada:
                logger.info("JornadaService.get_jornada_explorador_fecha - Jornada obtenida de Asignación", extra={
                    'explorador_id': explorador_id,
                    'fecha': str(fecha_obj),
                    'jornada_nombre': asignacion_jornada.jornada.nombre,
                    'asignacion_id': asignacion_jornada.id,
                    'fecha_inicio': str(asignacion_jornada.fecha_inicio),
                    'fuente': 'AsignarJornadaExplorador (jornada predeterminada)'
                })
                return asignacion_jornada.jornada
            else:
                logger.warning("JornadaService.get_jornada_explorador_fecha - No se encontró jornada", extra={
                    'explorador_id': explorador_id,
                    'fecha': str(fecha_obj),
                    'fuente': 'Ninguna'
                })
                return None
            
        except (ValueError, Empleado.DoesNotExist) as e:
            logger.warning(f"Error obteniendo jornada: {e}")
            return None
    
    @staticmethod
    def get_jornada_predeterminada(explorador):
        """
        Obtiene la jornada predeterminada más reciente de un explorador.
        
        Args:
            explorador: Objeto Empleado
        
        Returns:
            AsignarJornadaExplorador más reciente o None
        """
        return (
            AsignarJornadaExplorador.objects
            .filter(explorador=explorador)
            .select_related('jornada')
            .order_by('-fecha_inicio')
            .first()
        )

