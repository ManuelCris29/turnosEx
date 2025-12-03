"""
Servicio para aprobación y rechazo de solicitudes.

Responsabilidad única: Procesar aprobaciones y rechazos de solicitudes.
"""
from django.utils import timezone
from solicitudes.models import SolicitudCambio
from .solicitud_factory import SolicitudFactory
from .notificacion_service import NotificacionService
import logging

logger = logging.getLogger(__name__)


class SolicitudAprobacionService:
    """
    Servicio para procesar aprobaciones y rechazos de solicitudes.
    
    Responsabilidad única: Gestionar el flujo de aprobación/rechazo.
    """
    
    @staticmethod
    def aprobar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        Aprueba una solicitud por parte del supervisor.
        
        Args:
            solicitud_id: ID de la solicitud
            supervisor: Objeto Empleado supervisor
            comentario_respuesta: Comentario opcional
        
        Returns:
            Tupla (success: bool, message: str)
        """
        try:
            solicitud = (
                SolicitudCambio.objects
                .select_related('explorador_solicitante__supervisor', 'explorador_receptor', 'tipo_cambio')
                .get(id=solicitud_id)
            )
            
            # Verificar que el aprobador sea el supervisor del solicitante
            # Permitir auto-supervisión para desarrollo
            if solicitud.explorador_solicitante.supervisor != supervisor:
                return False, "No tienes permisos para aprobar esta solicitud"
            
            # Verificar que la solicitud esté pendiente
            if solicitud.estado != 'pendiente':
                if solicitud.estado == 'cancelada':
                    return False, "Esta solicitud fue cancelada y ya no puede ser aprobada"
                elif solicitud.estado == 'aprobada':
                    return False, "Esta solicitud ya fue aprobada"
                elif solicitud.estado == 'rechazada':
                    return False, "Esta solicitud ya fue rechazada"
                else:
                    return False, "La solicitud no está pendiente de aprobación"
            
            # Marcar como aprobada por supervisor
            solicitud.aprobado_supervisor = True
            solicitud.fecha_aprobacion_supervisor = timezone.now()
            
            # Si ya fue aprobada por el receptor, cambiar estado a aprobada
            if solicitud.aprobado_receptor:
                logger.info(
                    "Aprobando solicitud completamente - ID: %d, Tipo: %s, Receptor: %d, Solicitante: %d",
                    solicitud.id,
                    solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'N/A',
                    solicitud.explorador_receptor.id,
                    solicitud.explorador_solicitante.id
                )
                
                solicitud.estado = 'aprobada'
                solicitud.fecha_resolucion = timezone.now()
                
                # IMPORTANTE: Guardar primero para que aplicar_cambios pueda recargar el estado correcto
                solicitud.save()
                logger.info("Solicitud guardada con estado 'aprobada' - ID: %d", solicitud.id)
                
                # Aplicar los cambios usando el Factory
                logger.info("Llamando a aplicar_cambios para solicitud ID: %d", solicitud.id)
                success, message = SolicitudFactory.aplicar_cambios(solicitud)
                if not success:
                    logger.error("ERROR aplicando cambios para solicitud ID: %d - Mensaje: %s", solicitud.id, message)
                    return False, f"Error aplicando cambios: {message}"
                else:
                    logger.info("Cambios aplicados exitosamente para solicitud ID: %d - Mensaje: %s", solicitud.id, message)
            else:
                # Si no está completamente aprobada, solo guardar
                solicitud.save()
            
            # Crear notificación de aprobación del supervisor
            NotificacionService.crear_notificacion_aprobacion_supervisor(solicitud, supervisor, comentario_respuesta)
            
            # Invalidar cache de contadores para todos los afectados
            from core.services.cache_service import CacheService
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_receptor.id}",
                f"solicitudes_count_pend_{supervisor.id}",
            ]
            CacheService.delete_many(cache_keys)
            
            return True, "Solicitud aprobada por supervisor correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al aprobar solicitud supervisor")
            return False, f"Error al aprobar la solicitud: {str(e)}"

    @staticmethod
    def aprobar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        Aprueba una solicitud por parte del compañero receptor.
        
        Args:
            solicitud_id: ID de la solicitud
            receptor: Objeto Empleado receptor
            comentario_respuesta: Comentario opcional
        
        Returns:
            Tupla (success: bool, message: str)
        """
        try:
            solicitud = (
                SolicitudCambio.objects
                .select_related('explorador_solicitante__supervisor', 'explorador_receptor', 'tipo_cambio')
                .get(id=solicitud_id)
            )
            
            # Verificar que el aprobador sea el receptor de la solicitud
            if solicitud.explorador_receptor != receptor:
                return False, "No tienes permisos para aprobar esta solicitud"
            
            # Verificar que la solicitud esté pendiente
            if solicitud.estado != 'pendiente':
                if solicitud.estado == 'cancelada':
                    return False, "Esta solicitud fue cancelada y ya no puede ser aprobada"
                elif solicitud.estado == 'aprobada':
                    return False, "Esta solicitud ya fue aprobada"
                elif solicitud.estado == 'rechazada':
                    return False, "Esta solicitud ya fue rechazada"
                else:
                    return False, "La solicitud no está pendiente de aprobación"
            
            # Marcar como aprobada por receptor
            solicitud.aprobado_receptor = True
            solicitud.fecha_aprobacion_receptor = timezone.now()
            
            # Si ya fue aprobada por el supervisor, cambiar estado a aprobada
            if solicitud.aprobado_supervisor:
                logger.info(
                    "Aprobando solicitud completamente - ID: %d, Tipo: %s, Receptor: %d, Solicitante: %d",
                    solicitud.id,
                    solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'N/A',
                    solicitud.explorador_receptor.id,
                    solicitud.explorador_solicitante.id
                )
                
                solicitud.estado = 'aprobada'
                solicitud.fecha_resolucion = timezone.now()
                
                # IMPORTANTE: Guardar primero para que aplicar_cambios pueda recargar el estado correcto
                solicitud.save()
                logger.info("Solicitud guardada con estado 'aprobada' - ID: %d", solicitud.id)
                
                # Aplicar los cambios usando el Factory
                logger.info("Llamando a aplicar_cambios para solicitud ID: %d", solicitud.id)
                success, message = SolicitudFactory.aplicar_cambios(solicitud)
                if not success:
                    logger.error("ERROR aplicando cambios para solicitud ID: %d - Mensaje: %s", solicitud.id, message)
                    return False, f"Error aplicando cambios: {message}"
                else:
                    logger.info("Cambios aplicados exitosamente para solicitud ID: %d - Mensaje: %s", solicitud.id, message)
            else:
                # Si no está completamente aprobada, solo guardar
                solicitud.save()
            
            # Crear notificación de aprobación del receptor
            NotificacionService.crear_notificacion_aprobacion_receptor(solicitud, receptor, comentario_respuesta)
            
            # Invalidar cache de contadores para todos los afectados
            from core.services.cache_service import CacheService
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{receptor.id}",
            ]
            # Si el solicitante tiene supervisor, también invalidar su caché
            if solicitud.explorador_solicitante.supervisor:
                cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_solicitante.supervisor.id}")
            CacheService.delete_many(cache_keys)
            
            return True, "Solicitud aprobada por compañero correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al aprobar solicitud receptor")
            return False, f"Error al aprobar la solicitud: {str(e)}"

    @staticmethod
    def rechazar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        Rechaza una solicitud por parte del supervisor.
        
        Args:
            solicitud_id: ID de la solicitud
            supervisor: Objeto Empleado supervisor
            comentario_respuesta: Comentario opcional
        
        Returns:
            Tupla (success: bool, message: str)
        """
        try:
            solicitud = (
                SolicitudCambio.objects
                .select_related('explorador_solicitante__supervisor', 'explorador_receptor', 'tipo_cambio')
                .get(id=solicitud_id)
            )
            
            # Verificar que el rechazador sea el supervisor del solicitante
            if solicitud.explorador_solicitante.supervisor != supervisor:
                return False, "No tienes permisos para rechazar esta solicitud"
            
            # Verificar que la solicitud esté pendiente
            if solicitud.estado != 'pendiente':
                if solicitud.estado == 'cancelada':
                    return False, "Esta solicitud fue cancelada y ya no puede ser rechazada"
                elif solicitud.estado == 'aprobada':
                    return False, "Esta solicitud ya fue aprobada"
                elif solicitud.estado == 'rechazada':
                    return False, "Esta solicitud ya fue rechazada"
                else:
                    return False, "La solicitud no está pendiente de aprobación"
            
            # Rechazar la solicitud
            solicitud.estado = 'rechazada'
            solicitud.aprobado_supervisor = False
            solicitud.fecha_aprobacion_supervisor = timezone.now()
            solicitud.fecha_resolucion = timezone.now()
            solicitud.save()
            
            # Crear notificación de rechazo
            NotificacionService.crear_notificacion_rechazo_supervisor(solicitud, supervisor, comentario_respuesta)
            
            # Invalidar cache de contadores para todos los afectados
            from core.services.cache_service import CacheService
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_receptor.id}",
                f"solicitudes_count_pend_{supervisor.id}",
            ]
            CacheService.delete_many(cache_keys)
            
            return True, "Solicitud rechazada por supervisor correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al rechazar solicitud supervisor")
            return False, f"Error al rechazar la solicitud: {str(e)}"

    @staticmethod
    def rechazar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        Rechaza una solicitud por parte del compañero receptor.
        
        Args:
            solicitud_id: ID de la solicitud
            receptor: Objeto Empleado receptor
            comentario_respuesta: Comentario opcional
        
        Returns:
            Tupla (success: bool, message: str)
        """
        try:
            solicitud = (
                SolicitudCambio.objects
                .select_related('explorador_solicitante__supervisor', 'explorador_receptor', 'tipo_cambio')
                .get(id=solicitud_id)
            )
            
            # Verificar que el rechazador sea el receptor de la solicitud
            if solicitud.explorador_receptor != receptor:
                return False, "No tienes permisos para rechazar esta solicitud"
            
            # Verificar que la solicitud esté pendiente
            if solicitud.estado != 'pendiente':
                if solicitud.estado == 'cancelada':
                    return False, "Esta solicitud fue cancelada y ya no puede ser rechazada"
                elif solicitud.estado == 'aprobada':
                    return False, "Esta solicitud ya fue aprobada"
                elif solicitud.estado == 'rechazada':
                    return False, "Esta solicitud ya fue rechazada"
                else:
                    return False, "La solicitud no está pendiente de aprobación"
            
            # Rechazar la solicitud
            solicitud.estado = 'rechazada'
            solicitud.aprobado_receptor = False
            solicitud.fecha_aprobacion_receptor = timezone.now()
            solicitud.fecha_resolucion = timezone.now()
            solicitud.save()
            
            # Crear notificación de rechazo
            NotificacionService.crear_notificacion_rechazo_receptor(solicitud, receptor, comentario_respuesta)
            
            # Invalidar cache de contadores para todos los afectados
            from core.services.cache_service import CacheService
            cache_keys = [
                f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{solicitud.explorador_solicitante.id}",
                f"solicitudes_count_pend_{receptor.id}",
            ]
            # Si el solicitante tiene supervisor, también invalidar su caché
            if solicitud.explorador_solicitante.supervisor:
                cache_keys.append(f"solicitudes_count_pend_{solicitud.explorador_solicitante.supervisor.id}")
            CacheService.delete_many(cache_keys)
            
            return True, "Solicitud rechazada por compañero correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al rechazar solicitud receptor")
            return False, f"Error al rechazar la solicitud: {str(e)}"


