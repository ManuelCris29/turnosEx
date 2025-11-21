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
                return turno_especifico.jornada  # Jornada del cambio
            
            # 2. Si no hay turno específico, usar la jornada fija del explorador
            # Las jornadas son indefinidas por defecto (sin fecha_fin)
            # Cache para jornada predeterminada
            cache_key = f"jornada_pred_{explorador.id}_{fecha_obj}"
            
            def obtener_asignacion():
                return AsignarJornadaExplorador.objects.select_related('jornada').filter(
                    explorador=explorador,
                    fecha_inicio__lte=fecha_obj
                ).order_by('-fecha_inicio').first()
            
            asignacion_jornada = CacheService.get_or_set(
                cache_key,
                obtener_asignacion,
                ttl=CACHE_TTL_LONG
            )
            
            return asignacion_jornada.jornada if asignacion_jornada else None
            
        except (ValueError, Empleado.DoesNotExist) as e:
            logger.warning(f"Error obteniendo jornada: {e}")
            return None
    
    @staticmethod
    def calcular_jornada_dia(j_base, fecha):
        """
        Calcula la jornada para un día específico basado en la jornada base.
        
        DEPRECATED: Usar core.utils.jornada_utils.JornadaUtils.calcular_jornada_dia()
        
        IMPORTANTE: j_base siempre debe ser 'AM' o 'PM', nunca None.
        Todos los exploradores deben tener una jornada asignada.
        
        Args:
            j_base: Nombre de la jornada base ('AM' o 'PM')
            fecha: Objeto date
        
        Returns:
            String con el nombre de la jornada ('AM', 'PM', 'Descanso')
            
        Raises:
            ValueError: Si j_base no es 'AM' o 'PM'
        """
        from core.utils.jornada_utils import JornadaUtils
        return JornadaUtils.calcular_jornada_dia(j_base, fecha)
    
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

