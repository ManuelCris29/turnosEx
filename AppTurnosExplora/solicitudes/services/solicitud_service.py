from django.db.models import Q
# type: ignore
from empleados.models import Empleado, CompetenciaEmpleado
from turnos.models import Turno, AsignarJornadaExplorador, AsignarSalaExplorador
from solicitudes.models import TipoSolicitudCambio, SolicitudCambio
from datetime import datetime
from django.utils import timezone
import logging

# Logger estructurado para este módulo
logger = logging.getLogger(__name__)


class SolicitudService:
    @staticmethod
    def get_empleados_disponibles(fecha, usuario_actual=None, solo_jornada_contraria=False):
        """
        Obtiene los empleados disponibles para una fecha específica
        Args:
            fecha: Fecha para la cual buscar empleados
            usuario_actual: Usuario actual (para excluirlo de la lista)
            solo_jornada_contraria: Si True, solo devuelve empleados de jornada contraria
        """
        if solo_jornada_contraria:
            return SolicitudService.get_empleados_jornada_contraria(fecha, usuario_actual)
        
        # Lógica original: todos los empleados activos
        # Optimización: solo los campos necesarios y relaciones frecuentes
        empleados = (
            Empleado.objects
            .filter(activo=True)
            .select_related('supervisor')
        )
        
        # Excluir al usuario actual si se proporciona
        if usuario_actual and hasattr(usuario_actual, 'empleado'):
            empleados = empleados.exclude(id=usuario_actual.empleado.id)
        
        return empleados

    @staticmethod
    def get_empleados_jornada_contraria(fecha, usuario_actual=None):
        """
        Obtiene los empleados que están en la jornada contraria al usuario actual
        para una fecha específica
        """
        logger.debug("get_empleados_jornada_contraria", extra={
            'fecha': fecha,
            'usuario_id': getattr(getattr(usuario_actual, 'empleado', None), 'id', None)
        })
        
        # Verificar si es un objeto Empleado o User
        if isinstance(usuario_actual, Empleado):
            empleado_actual = usuario_actual
        elif hasattr(usuario_actual, 'empleado'):
            empleado_actual = usuario_actual.empleado
        else:
            logger.debug("No hay usuario actual o no tiene empleado asociado")
            return Empleado.objects.none()
        
        # Obtener la jornada del usuario actual para esa fecha
        jornada_usuario = SolicitudService.get_jornada_explorador_fecha(
            empleado_actual.id, fecha
        )
        
        logger.debug("jornada_usuario", extra={'jornada': getattr(jornada_usuario, 'nombre', None)})
        
        if not jornada_usuario:
            logger.debug("Usuario no tiene jornada asignada")
            return Empleado.objects.none()
        
        # Determinar la jornada contraria
        jornada_contraria = None
        if jornada_usuario.nombre == 'AM':
            jornada_contraria = 'PM'
        elif jornada_usuario.nombre == 'PM':
            jornada_contraria = 'AM'
        else:
            # Si no es AM ni PM, no hay jornada contraria definida
            print(f"DEBUG: Jornada no reconocida: {jornada_usuario.nombre}")
            return Empleado.objects.none()
        
        logger.debug("jornada_contraria", extra={'jornada_contraria': jornada_contraria})
        
        # Buscar empleados que tengan la jornada contraria asignada
        empleados_contrarios = []
        empleados_activos = (
            Empleado.objects
            .filter(activo=True)
            .exclude(id=empleado_actual.id)
            .select_related('supervisor')
        )
        
        logger.debug("empleados_activos_count", extra={'count': empleados_activos.count()})
        
        for empleado in empleados_activos:
            jornada_empleado = SolicitudService.get_jornada_explorador_fecha(empleado.id, fecha)
            if jornada_empleado and jornada_empleado.nombre == jornada_contraria:
                empleados_contrarios.append(empleado)
        
        logger.debug("empleados_contrarios_count", extra={'count': len(empleados_contrarios)})
        return empleados_contrarios

    @staticmethod
    def get_jornada_explorador_fecha(explorador_id, fecha):
        """
        Obtiene la jornada de un explorador para una fecha específica
        Considera jornada fija vs cambios específicos
        """
        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            explorador = Empleado.objects.get(id=explorador_id)
            
            # 1. Buscar si hay un turno específico para esa fecha (cambio aprobado)
            turno_especifico = Turno.objects.filter(
                explorador=explorador, 
                fecha=fecha_obj
            ).first()
            
            if turno_especifico:
                return turno_especifico.jornada  # Jornada del cambio
            
            # 2. Si no hay turno específico, usar la jornada fija del explorador
            jornada_fija = AsignarJornadaExplorador.objects.filter(
                explorador=explorador,
                fecha_inicio__lte=fecha_obj
            ).filter(
                Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_obj)
            ).order_by('-fecha_inicio').first()
            
            
            return jornada_fija.jornada if jornada_fija else None
            
        except (ValueError, Empleado.DoesNotExist):
            return None

    @staticmethod
    def get_turno_explorador(explorador_id, fecha):
        """
        Obtiene el turno de un explorador para una fecha específica
        """
        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            explorador = Empleado.objects.get(id=explorador_id)
            # 1. Buscar turno específico para esa fecha
            turno = Turno.objects.select_related('jornada', 'sala').filter(
                explorador_id=explorador_id,
                fecha=fecha_obj
            ).first()
            if turno:
                return {
                    'id': turno.id,
                    'jornada': turno.jornada.nombre,
                    'sala': turno.sala.nombre,
                    'sala_id': turno.sala.id,
                    'hora_inicio': turno.jornada.hora_inicio.strftime('%H:%M'),
                    'hora_fin': turno.jornada.hora_fin.strftime('%H:%M'),
                    'es_turno_virtual': False,
                    'tipo_sala': 'turno'
                }
            # 2. Si no hay turno, buscar jornada predeterminada
            asignacion_jornada = AsignarJornadaExplorador.objects.select_related('jornada').filter(
                explorador=explorador,
                fecha_inicio__lte=fecha_obj
            ).filter(
                Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_obj)
            ).order_by('-fecha_inicio').first()
            jornada = asignacion_jornada.jornada if asignacion_jornada else None
            # 3. Buscar sala asignada especial para ese día
            asignacion_sala = AsignarSalaExplorador.objects.select_related('sala').filter(
                explorador=explorador,
                fecha_inicio__lte=fecha_obj
            ).filter(
                Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_obj)
            ).order_by('-fecha_inicio').first()
            if asignacion_sala:
                return {
                    'id': None,
                    'jornada': jornada.nombre if jornada else None,
                    'sala': asignacion_sala.sala.nombre,
                    'sala_id': asignacion_sala.sala.id,
                    'hora_inicio': jornada.hora_inicio.strftime('%H:%M') if jornada else None,
                    'hora_fin': jornada.hora_fin.strftime('%H:%M') if jornada else None,
                    'es_turno_virtual': True,
                    'tipo_sala': 'asignacion_especial'
                }
            # 4. Si no hay asignación especial, usar todas las salas de competencia
            competencias = CompetenciaEmpleado.objects.filter(empleado=explorador).select_related('sala')
            salas_competencia = [
                {'id': c.sala.id, 'nombre': c.sala.nombre} for c in competencias
            ]
            return {
                'id': None,
                'jornada': jornada.nombre if jornada else None,
                'sala': None,
                'sala_id': None,
                'hora_inicio': jornada.hora_inicio.strftime('%H:%M') if jornada else None,
                'hora_fin': jornada.hora_fin.strftime('%H:%M') if jornada else None,
                'es_turno_virtual': True,
                'tipo_sala': 'competencia',
                'salas_competencia': salas_competencia
            }
        except ValueError:
            return None

    @staticmethod
    def get_salas_explorador(explorador_id):
        """
        Obtiene las salas asignadas a un explorador
        """
        return CompetenciaEmpleado.objects.filter(
            empleado_id=explorador_id
        ).select_related('sala')

    @staticmethod
    def get_tipos_solicitud_activos():
        """
        Obtiene todos los tipos de solicitud activos
        """
        return TipoSolicitudCambio.objects.filter(activo=True)

    @staticmethod
    def crear_solicitud_cambio(explorador_solicitante, explorador_receptor, tipo_cambio, 
                              comentario=None, turno_origen=None, turno_destino=None, fecha_cambio_turno=None):
        """
        Crea una nueva solicitud de cambio de turno y envía notificaciones
        Incluye lógica para cancelar solicitudes anteriores de la misma fecha
        """
        from .notificacion_service import NotificacionService

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
        
        # 6. Crear notificaciones y enviar emails para la nueva solicitud
        try:
            logger.debug("Creando notificaciones para solicitud", extra={'solicitud_id': solicitud.id})
            NotificacionService.crear_notificacion_solicitud(solicitud)
        except Exception:
            logger.exception("Error creando notificaciones")
        
        return solicitud, "Solicitud creada correctamente"

    @staticmethod
    def validar_solicitud_cambio(explorador_solicitante, explorador_receptor, fecha):
        """
        Valida si una solicitud de cambio es válida
        """
        try:
            # Importar aquí para evitar circular import
            from .solicitud_validator import SolicitudValidator
            
            # Validaciones centralizadas (lanzan ValidationError si no cumplen)
            SolicitudValidator.validar_empleado_activo(explorador_solicitante)
            SolicitudValidator.validar_empleado_activo(explorador_receptor)
            SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)
            SolicitudValidator.validar_jornada_en_fecha(explorador_solicitante, fecha)
            SolicitudValidator.validar_jornada_en_fecha(explorador_receptor, fecha)
            logger.debug("Validando solicitud existente", extra={
                'solicitante_id': explorador_solicitante.id,
                'receptor_id': explorador_receptor.id,
                'fecha': fecha
            })
            SolicitudValidator.validar_duplicada_misma_fecha(explorador_solicitante, explorador_receptor, fecha)
            logger.debug("Validación exitosa")
            return True, "Solicitud válida"
        except Exception as e:
            # Devolver mensaje amigable de validación
            return False, str(e)

    @staticmethod
    def get_solicitudes_usuario(usuario):
        """
        Obtiene las solicitudes de un usuario específico
        """
        if hasattr(usuario, 'empleado'):
            return (
                SolicitudCambio.objects
                .filter(explorador_solicitante=usuario.empleado)
                .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')
                .order_by('-fecha_solicitud')
            )
        return SolicitudCambio.objects.none()

    @staticmethod
    def get_solicitudes_pendientes():
        """
        Obtiene todas las solicitudes pendientes
        """
        return (
            SolicitudCambio.objects
            .filter(estado='pendiente')
            .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')
            .order_by('-fecha_solicitud')
        )

    @staticmethod
    def aprobar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        Aprueba una solicitud por parte del supervisor
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
                solicitud.estado = 'aprobada'
                solicitud.fecha_resolucion = timezone.now()
                
                # Aplicar los cambios usando el Factory
                from .solicitud_factory import SolicitudFactory
                success, message = SolicitudFactory.aplicar_cambios(solicitud)
                if not success:
                    logger.error(f"Error aplicando cambios: {message}")
            
            solicitud.save()
            
            # Crear notificación de aprobación del supervisor
            from .notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_aprobacion_supervisor(solicitud, supervisor, comentario_respuesta)
            
            return True, "Solicitud aprobada por supervisor correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al aprobar solicitud supervisor")
            return False, f"Error al aprobar la solicitud: {str(e)}"

    @staticmethod
    def aprobar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        Aprueba una solicitud por parte del compañero receptor
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
                solicitud.estado = 'aprobada'
                solicitud.fecha_resolucion = timezone.now()
                
                # Aplicar los cambios usando el Factory
                from .solicitud_factory import SolicitudFactory
                success, message = SolicitudFactory.aplicar_cambios(solicitud)
                if not success:
                    logger.error(f"Error aplicando cambios: {message}")
            
            solicitud.save()
            
            # Crear notificación de aprobación del receptor
            from .notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_aprobacion_receptor(solicitud, receptor, comentario_respuesta)
            
            return True, "Solicitud aprobada por compañero correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al aprobar solicitud receptor")
            return False, f"Error al aprobar la solicitud: {str(e)}"

    @staticmethod
    def rechazar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        Rechaza una solicitud por parte del supervisor
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
            from .notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_rechazo_supervisor(solicitud, supervisor, comentario_respuesta)
            
            return True, "Solicitud rechazada por supervisor correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al rechazar solicitud supervisor")
            return False, f"Error al rechazar la solicitud: {str(e)}"

    @staticmethod
    def rechazar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        Rechaza una solicitud por parte del compañero receptor
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
            from .notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_rechazo_receptor(solicitud, receptor, comentario_respuesta)
            
            return True, "Solicitud rechazada por compañero correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            logger.exception("Error al rechazar solicitud receptor")
            return False, f"Error al rechazar la solicitud: {str(e)}"

    @staticmethod
    def get_solicitudes_por_receptor(receptor):
        """
        Obtiene las solicitudes pendientes que debe aprobar un receptor
        """
        return (
            SolicitudCambio.objects
            .filter(
                explorador_receptor=receptor,
                estado='pendiente',
                aprobado_receptor=False,  # Ocultar si el receptor ya aprobó
            )
            .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')
            .order_by('-fecha_solicitud')
        )

    @staticmethod
    def get_solicitudes_por_supervisor(supervisor):
        """
        Obtiene las solicitudes pendientes que debe aprobar un supervisor
        """
        return (
            SolicitudCambio.objects
            .filter(
                explorador_solicitante__supervisor=supervisor,
                estado='pendiente',
                aprobado_supervisor=False,  # Ocultar si el supervisor ya aprobó
            )
            .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')
            .order_by('-fecha_solicitud')
        )

    @staticmethod
    def get_estado_aprobacion_solicitud(solicitud):
        """
        Obtiene el estado de aprobación de una solicitud
        """
        if solicitud.estado == 'aprobada':
            return 'Aprobada por ambos'
        elif solicitud.estado == 'rechazada':
            if solicitud.aprobado_supervisor == False:
                return 'Rechazada por supervisor'
            elif solicitud.aprobado_receptor == False:
                return 'Rechazada por compañero'
            else:
                return 'Rechazada'
        elif solicitud.estado == 'pendiente':
            if solicitud.aprobado_supervisor and solicitud.aprobado_receptor:
                return 'Pendiente de confirmación final'
            elif solicitud.aprobado_supervisor:
                return 'Aprobada por supervisor, pendiente compañero'
            elif solicitud.aprobado_receptor:
                return 'Aprobada por compañero, pendiente supervisor'
            else:
                return 'Pendiente de ambos'
        else:
            return solicitud.get_estado_display() 