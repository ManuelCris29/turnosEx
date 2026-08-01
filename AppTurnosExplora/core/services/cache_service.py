"""
Servicio centralizado para gestión de cache
"""
from django.core.cache import cache
from typing import Callable, Any, Optional
import logging

logger = logging.getLogger(__name__)


# Constantes para TTLs comunes (en segundos)
# Estas constantes se exportan para uso en otros módulos
CACHE_TTL_SHORT = 300      # 5 minutos
CACHE_TTL_MEDIUM = 1800    # 30 minutos
CACHE_TTL_LONG = 3600      # 1 hora
CACHE_TTL_VERY_LONG = 86400  # 24 horas

__all__ = ['CacheService', 'CACHE_TTL_SHORT', 'CACHE_TTL_MEDIUM', 'CACHE_TTL_LONG', 'CACHE_TTL_VERY_LONG']


class CacheService:
    """
    Servicio para gestión centralizada de cache.
    
    Proporciona métodos helper para patrones comunes de cache,
    asegurando consistencia en TTLs y manejo de errores.
    """
    
    @staticmethod
    def get_or_set(key: str, callable_func: Callable[[], Any], ttl: int = CACHE_TTL_MEDIUM) -> Any:
        """
        Obtiene un valor del cache, o lo calcula y guarda si no existe.
        
        Este es el patrón más común: obtener del cache, o calcular y guardar.
        
        Args:
            key: Clave del cache
            callable_func: Función que calcula el valor si no está en cache
            ttl: Time to live en segundos (default: 30 minutos)
        
        Returns:
            Valor del cache o resultado de callable_func
        
        Ejemplo:
            def calcular_contador():
                return SolicitudCambio.objects.count()
            
            count = CacheService.get_or_set(
                'solicitudes_count',
                calcular_contador,
                ttl=CacheService.CACHE_TTL_SHORT
            )
        """
        cached_value = cache.get(key)
        if cached_value is None:
            try:
                cached_value = callable_func()
                cache.set(key, cached_value, ttl)
                logger.debug(f"Cache miss - key: {key}, calculated and stored")
            except Exception as e:
                logger.error(f"Error calculating cache value for key {key}: {e}")
                raise
        else:
            logger.debug(f"Cache hit - key: {key}")
        return cached_value
    
    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """
        Obtiene un valor del cache.
        
        Args:
            key: Clave del cache
            default: Valor por defecto si no existe
        
        Returns:
            Valor del cache o default
        """
        return cache.get(key, default)
    
    @staticmethod
    def set(key: str, value: Any, ttl: int = CACHE_TTL_MEDIUM) -> None:
        """
        Guarda un valor en el cache.
        
        Args:
            key: Clave del cache
            value: Valor a guardar
            ttl: Time to live en segundos (default: 30 minutos)
        """
        cache.set(key, value, ttl)
        logger.debug(f"Cache set - key: {key}, ttl: {ttl}")
    
    @staticmethod
    def delete(key: str) -> None:
        """
        Elimina un valor del cache.
        
        Args:
            key: Clave del cache
        """
        cache.delete(key)
        logger.debug(f"Cache delete - key: {key}")
    
    @staticmethod
    def acquire_lock(key: str, ttl: int = 10) -> bool:
        """
        Intenta tomar un lock corto y atómico (dedupe de doble-submit/doble-clic).

        Usa `cache.add`, que solo escribe si la clave NO existe — a diferencia de `set`,
        eso es atómico entre procesos/workers concurrentes. Devuelve True si se tomó el
        lock (nadie lo tenía), False si ya estaba tomado (hay una operación igual en curso).
        El lock se libera solo por expiración del TTL; no hace falta (ni conviene) liberarlo
        a mano, porque el objetivo es bloquear reintentos *inmediatos*, no serializar el uso normal.
        """
        return cache.add(key, True, ttl)

    @staticmethod
    def delete_many(keys: list[str]) -> None:
        """
        Elimina múltiples valores del cache.
        
        Args:
            keys: Lista de claves a eliminar
        """
        cache.delete_many(keys)
        logger.debug(f"Cache delete_many - keys: {len(keys)}")
    
    @staticmethod
    def invalidar_cache_turnos_empleado(empleado_id: int, mes: int | str, anio: int | str) -> None:
        """
        Invalida el caché de turnos por mes para un empleado específico.
        
        Clave utilizada por MisTurnosPorMesView:
            turnos_mes_{empleado_id}_{anio}_{mes}
        
        Donde:
            - anio: string del año (ej: '2026')
            - mes: string con dos dígitos (ej: '02')
        
        Este helper normaliza mes/año para mantener un formato consistente.
        """
        try:
            mes_int = int(mes)
            anio_int = int(anio)
        except (TypeError, ValueError):
            logger.error(f"No se pudo invalidar caché de turnos: mes/anio inválidos (mes={mes!r}, anio={anio!r})")
            return
        
        mes_str = f"{mes_int:02d}"
        anio_str = str(anio_int)
        
        cache_key = f"turnos_mes_{empleado_id}_{anio_str}_{mes_str}"
        CacheService.delete(cache_key)
        logger.info(f"Caché de turnos invalidado para empleado={empleado_id}, anio={anio_str}, mes={mes_str} (key={cache_key})")
    
    @staticmethod
    def invalidate_pattern(pattern: str) -> None:
        """
        Invalida todas las claves que coincidan con un patrón.
        
        Nota: Esto requiere que el backend de cache soporte búsqueda por patrón.
        Redis lo soporta, pero el cache local de Django no.
        
        Args:
            pattern: Patrón de búsqueda (ej: "solicitudes_count_*")
        
        Ejemplo:
            CacheService.invalidate_pattern("solicitudes_count_*")
        """
        # Implementación depende del backend de cache
        # Para Redis, se podría usar:
        # from django.core.cache import cache
        # if hasattr(cache, 'delete_pattern'):
        #     cache.delete_pattern(pattern)
        # else:
        #     logger.warning(f"Cache backend does not support pattern deletion: {pattern}")
        logger.warning(f"Pattern invalidation not fully implemented for: {pattern}")
        
