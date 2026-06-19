"""
Servicio core para gestión de solicitudes.

Responsabilidad única: Creación y gestión core de solicitudes.
Los demás métodos han sido movidos a servicios específicos siguiendo SRP.
"""
from django.utils import timezone
from solicitudes.models import SolicitudCambio
from .notificacion_service import NotificacionService
from core.services.cache_service import CacheService
from core.services import (
    get_empleado_disponibilidad_service,
    get_turno_service,
)
import logging

logger = logging.getLogger(__name__)


class SolicitudService:
    """
    Servicio core para creación de solicitudes.
    
    Responsabilidad única: Crear nuevas solicitudes y manejar cancelaciones automáticas.
    
    NOTA: Otros métodos han sido movidos a servicios específicos:
    - get_empleados_disponibles/get_empleados_jornada_contraria → EmpleadoDisponibilidadService
    - get_jornada_explorador_fecha → JornadaService (turnos)
    - get_turno_explorador/get_salas_explorador → TurnoService (turnos)
    - get_tipos_solicitud_activos/get_solicitudes_* → SolicitudConsultaService
    - aprobar_*/rechazar_* → SolicitudAprobacionService
    """
    
    @staticmethod
    def crear_solicitud_cambio(explorador_solicitante, explorador_receptor, tipo_cambio, 
                              comentario=None, turno_origen=None, turno_destino=None, fecha_cambio_turno=None):
        """
        Crea una nueva solicitud de cambio de turno y envía notificaciones.
        Incluye lógica para cancelar solicitudes anteriores de la misma fecha.
        
        Args:
            explorador_solicitante: Objeto Empleado solicitante
            explorador_receptor: Objeto Empleado receptor
            tipo_cambio: Objeto TipoSolicitudCambio
            comentario: Comentario opcional
            turno_origen: Turno origen opcional
            turno_destino: Turno destino opcional
            fecha_cambio_turno: Fecha del cambio (date object)
        
        Returns:
            Tupla (solicitud: SolicitudCambio, message: str) o (None, error_message)
        """
        # Regla de negocio: el comentario es obligatorio para crear una solicitud.
        if not comentario or not str(comentario).strip():
            return None, "Debes ingresar un comentario para enviar la solicitud."

        logger.info("Creando solicitud de cambio", extra={
            'solicitante_id': explorador_solicitante.id,
            'receptor_id': explorador_receptor.id,
            'tipo_cambio': tipo_cambio.nombre,
            'fecha_cambio_turno': str(fecha_cambio_turno)
        })

        # 1. Verificar si ya existe una solicitud pendiente para la misma fecha
        solicitud_anterior = SolicitudCambio.objects.filter(
            explorador_solicitante=explorador_solicitante,
            estado='pendiente',
            fecha_cambio_turno=fecha_cambio_turno
        ).first()
        
        if solicitud_anterior:
            logger.info("Solicitud anterior encontrada", extra={'solicitud_id': solicitud_anterior.id})
            
            # 2. Verificar si la solicitud anterior ya fue aprobada por alguien
            if solicitud_anterior.aprobado_receptor or solicitud_anterior.aprobado_supervisor:
                logger.warning("Solicitud anterior ya fue aprobada - no cancelar", extra={'solicitud_id': solicitud_anterior.id})
                return None, "No puedes crear una nueva solicitud porque la anterior ya fue aprobada"
            
            # 3. Cancelar la solicitud anterior
            logger.info("Cancelando solicitud anterior", extra={'solicitud_id': solicitud_anterior.id})
            solicitud_anterior.estado = 'cancelada'
            solicitud_anterior.comentario = f"{solicitud_anterior.comentario or ''}\n\nCancelada automáticamente al crear nueva solicitud"
            solicitud_anterior.fecha_resolucion = timezone.now()
            solicitud_anterior.save()
            
            # 4. Notificar al receptor anterior sobre la cancelación
            try:
                NotificacionService.crear_notificacion_cancelacion(solicitud_anterior)
                logger.info("Notificación de cancelación enviada", extra={'solicitud_id': solicitud_anterior.id})
            except Exception as e:
                logger.exception("Error enviando notificación de cancelación")
        
        # 5. Crear la nueva solicitud
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=explorador_solicitante,
            explorador_receptor=explorador_receptor,
            tipo_cambio=tipo_cambio,
            comentario=comentario,
            turno_origen=turno_origen,
            turno_destino=turno_destino,
            fecha_cambio_turno=fecha_cambio_turno
        )
        
        logger.info("Nueva solicitud creada", extra={'solicitud_id': solicitud.id})
        
        # Invalidar cache de contadores usando CacheService
        CacheService.delete_many([
            f"solicitudes_count_mis_{explorador_solicitante.id}",
            f"solicitudes_count_pend_{explorador_solicitante.id}",
            f"solicitudes_count_pend_{explorador_receptor.id}",
        ])
        
        # 6. Crear notificaciones y enviar emails para la nueva solicitud
        try:
            logger.debug("Creando notificaciones para solicitud", extra={'solicitud_id': solicitud.id})
            NotificacionService.crear_notificacion_solicitud(solicitud)
        except Exception:
            logger.exception("Error creando notificaciones")
        
        return solicitud, "Solicitud creada correctamente"
    
    # MÉTODOS DEPRECADOS - Usar servicios específicos en su lugar
    
    @staticmethod
    def get_empleados_disponibles(fecha, usuario_actual=None, solo_jornada_contraria=False):
        """
        DEPRECADO: Usar EmpleadoDisponibilidadService.get_empleados_disponibles()
        """
        servicio = get_empleado_disponibilidad_service()
        return servicio.get_empleados_disponibles(
            fecha, usuario_actual, solo_jornada_contraria
        )
    
    @staticmethod
    def get_empleados_jornada_contraria(fecha, usuario_actual=None):
        """
        DEPRECADO: Usar EmpleadoDisponibilidadService.get_empleados_jornada_contraria()
        """
        servicio = get_empleado_disponibilidad_service()
        return servicio.get_empleados_jornada_contraria(fecha, usuario_actual)
    
    @staticmethod
    def get_jornada_explorador_fecha(explorador_id, fecha):
        """
        DEPRECADO: Usar JornadaService.get_jornada_explorador_fecha()
        """
        from turnos.services.jornada_service import JornadaService
        return JornadaService.get_jornada_explorador_fecha(explorador_id, fecha)
    
    @staticmethod
    def get_turno_explorador(explorador_id, fecha):
        """
        DEPRECADO: Usar TurnoService.get_turno_explorador()
        """
        turno_service = get_turno_service()
        return turno_service.get_turno_explorador(explorador_id, fecha)
    
    @staticmethod
    def get_salas_explorador(explorador_id):
        """
        DEPRECADO: Usar TurnoService.get_salas_explorador()
        """
        turno_service = get_turno_service()
        return turno_service.get_salas_explorador(explorador_id)
    
    @staticmethod
    def get_tipos_solicitud_activos():
        """
        DEPRECADO: Usar SolicitudConsultaService.get_tipos_solicitud_activos()
        """
        from .solicitud_consulta_service import SolicitudConsultaService
        return SolicitudConsultaService.get_tipos_solicitud_activos()
    
    @staticmethod
    def get_solicitudes_usuario(usuario):
        """
        DEPRECADO: Usar SolicitudConsultaService.get_solicitudes_usuario()
        """
        from .solicitud_consulta_service import SolicitudConsultaService
        return SolicitudConsultaService.get_solicitudes_usuario(usuario)
    
    @staticmethod
    def get_solicitudes_pendientes():
        """
        DEPRECADO: Usar SolicitudConsultaService.get_solicitudes_pendientes()
        """
        from .solicitud_consulta_service import SolicitudConsultaService
        return SolicitudConsultaService.get_solicitudes_pendientes()
    
    @staticmethod
    def aprobar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        DEPRECADO: Usar SolicitudAprobacionService.aprobar_solicitud_supervisor()
        """
        from .solicitud_aprobacion_service import SolicitudAprobacionService
        return SolicitudAprobacionService.aprobar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta)
    
    @staticmethod
    def aprobar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        DEPRECADO: Usar SolicitudAprobacionService.aprobar_solicitud_receptor()
        """
        from .solicitud_aprobacion_service import SolicitudAprobacionService
        return SolicitudAprobacionService.aprobar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta)
    
    @staticmethod
    def rechazar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        DEPRECADO: Usar SolicitudAprobacionService.rechazar_solicitud_supervisor()
        """
        from .solicitud_aprobacion_service import SolicitudAprobacionService
        return SolicitudAprobacionService.rechazar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta)
    
    @staticmethod
    def rechazar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        DEPRECADO: Usar SolicitudAprobacionService.rechazar_solicitud_receptor()
        """
        from .solicitud_aprobacion_service import SolicitudAprobacionService
        return SolicitudAprobacionService.rechazar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta)
    
    @staticmethod
    def get_solicitudes_por_receptor(receptor):
        """
        DEPRECADO: Usar SolicitudConsultaService.get_solicitudes_por_receptor()
        """
        from .solicitud_consulta_service import SolicitudConsultaService
        return SolicitudConsultaService.get_solicitudes_por_receptor(receptor)
    
    @staticmethod
    def get_solicitudes_por_supervisor(supervisor):
        """
        DEPRECADO: Usar SolicitudConsultaService.get_solicitudes_por_supervisor()
        """
        from .solicitud_consulta_service import SolicitudConsultaService
        return SolicitudConsultaService.get_solicitudes_por_supervisor(supervisor)
    
    @staticmethod
    def get_estado_aprobacion_solicitud(solicitud):
        """
        DEPRECADO: Usar SolicitudConsultaService.get_estado_aprobacion_solicitud()
        """
        from .solicitud_consulta_service import SolicitudConsultaService
        return SolicitudConsultaService.get_estado_aprobacion_solicitud(solicitud)
    
    @staticmethod
    def contar_cambios_explorador_fecha(explorador_id: int, fecha) -> int:
        """
        DEPRECADO: Usar SolicitudConsultaService.contar_cambios_explorador_fecha()
        """
        from .solicitud_consulta_service import SolicitudConsultaService
        return SolicitudConsultaService.contar_cambios_explorador_fecha(explorador_id, fecha)
