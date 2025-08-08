from django.db.models import Q
from empleados.models import Empleado, CompetenciaEmpleado
from turnos.models import Turno, AsignarJornadaExplorador, AsignarSalaExplorador
from solicitudes.models import TipoSolicitudCambio, SolicitudCambio
from datetime import datetime
from django.utils import timezone


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
        empleados = Empleado.objects.filter(activo=True)
        
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
        print(f"DEBUG: get_empleados_jornada_contraria - fecha={fecha}, usuario={usuario_actual}")
        
        if not usuario_actual or not hasattr(usuario_actual, 'empleado'):
            print("DEBUG: No hay usuario actual o no tiene empleado asociado")
            return Empleado.objects.none()
        
        # Obtener la jornada del usuario actual para esa fecha
        jornada_usuario = SolicitudService.get_jornada_explorador_fecha(
            usuario_actual.empleado.id, fecha
        )
        
        print(f"DEBUG: jornada_usuario={jornada_usuario}")
        
        if not jornada_usuario:
            print("DEBUG: Usuario no tiene jornada asignada")
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
        
        print(f"DEBUG: jornada_contraria={jornada_contraria}")
        
        # Buscar empleados que tengan la jornada contraria asignada
        empleados_contrarios = []
        empleados_activos = Empleado.objects.filter(activo=True).exclude(id=usuario_actual.empleado.id)
        
        print(f"DEBUG: empleados_activos count={len(empleados_activos)}")
        
        for empleado in empleados_activos:
            jornada_empleado = SolicitudService.get_jornada_explorador_fecha(empleado.id, fecha)
            print(f"DEBUG: empleado={empleado.nombre}, jornada={jornada_empleado.nombre if jornada_empleado else 'None'}")
            if jornada_empleado and jornada_empleado.nombre == jornada_contraria:
                empleados_contrarios.append(empleado)
        
        print(f"DEBUG: empleados_contrarios count={len(empleados_contrarios)}")
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
                fecha_inicio__lte=fecha_obj,
                fecha_fin__isnull=True  # Sin fecha fin = vigente
            ).first()
            
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
            turno = Turno.objects.filter(
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
            asignacion_jornada = AsignarJornadaExplorador.objects.filter(
                explorador=explorador,
                fecha_inicio__lte=fecha_obj
            ).filter(
                Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=fecha_obj)
            ).order_by('-fecha_inicio').first()
            jornada = asignacion_jornada.jornada if asignacion_jornada else None
            # 3. Buscar sala asignada especial para ese día
            asignacion_sala = AsignarSalaExplorador.objects.filter(
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
                              fecha_cambio, comentario=None, turno_origen=None, turno_destino=None):
        """
        Crea una nueva solicitud de cambio de turno y envía notificaciones
        """
        from .notificacion_service import NotificacionService
        
        # Crear la solicitud
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=explorador_solicitante,
            explorador_receptor=explorador_receptor,
            tipo_cambio=tipo_cambio,
            comentario=comentario,
            turno_origen=turno_origen,
            turno_destino=turno_destino
        )
        
        # Crear notificaciones y enviar emails
        NotificacionService.crear_notificacion_solicitud(solicitud)
        
        return solicitud

    @staticmethod
    def validar_solicitud_cambio(explorador_solicitante, explorador_receptor, fecha):
        """
        Valida si una solicitud de cambio es válida
        """
        # Verificar que ambos exploradores estén activos
        if not explorador_solicitante.activo or not explorador_receptor.activo:
            return False, "Uno o ambos exploradores no están activos"
        
        # Verificar que no sea la misma persona
        if explorador_solicitante.id == explorador_receptor.id:
            return False, "No puedes solicitar cambio contigo mismo"
        
        # Verificar que ambos tengan jornadas asignadas en esa fecha
        jornada_solicitante = SolicitudService.get_jornada_explorador_fecha(explorador_solicitante.id, fecha)
        jornada_receptor = SolicitudService.get_jornada_explorador_fecha(explorador_receptor.id, fecha)
        
        if not jornada_solicitante:
            return False, "No tienes jornada asignada para esa fecha"
        
        if not jornada_receptor:
            return False, "El explorador seleccionado no tiene jornada asignada para esa fecha"
        
        # Verificar que no exista una solicitud pendiente entre estos exploradores para esa fecha
        solicitud_existente = SolicitudCambio.objects.filter(
            explorador_solicitante=explorador_solicitante,
            explorador_receptor=explorador_receptor,
            estado='pendiente'
        ).first()
        
        if solicitud_existente:
            return False, "Ya existe una solicitud pendiente con este explorador"
        
        return True, "Solicitud válida"

    @staticmethod
    def get_solicitudes_usuario(usuario):
        """
        Obtiene las solicitudes de un usuario específico
        """
        if hasattr(usuario, 'empleado'):
            return SolicitudCambio.objects.filter(
                explorador_solicitante=usuario.empleado
            ).order_by('-fecha_solicitud')
        return SolicitudCambio.objects.none()

    @staticmethod
    def get_solicitudes_pendientes():
        """
        Obtiene todas las solicitudes pendientes
        """
        return SolicitudCambio.objects.filter(estado='pendiente').order_by('-fecha_solicitud')

    @staticmethod
    def get_solicitudes_por_supervisor(supervisor):
        """
        Obtiene las solicitudes pendientes que debe aprobar un supervisor
        """
        return SolicitudCambio.objects.filter(
            explorador_solicitante__supervisor=supervisor,
            estado='pendiente'
        ).order_by('-fecha_solicitud')

    @staticmethod
    def aprobar_solicitud(solicitud_id, aprobador, comentario_respuesta=None):
        """
        Aprueba una solicitud de cambio
        """
        try:
            solicitud = SolicitudCambio.objects.get(id=solicitud_id)
            
            # Verificar que el aprobador sea el supervisor del solicitante
            if solicitud.explorador_solicitante.supervisor != aprobador:
                return False, "No tienes permisos para aprobar esta solicitud"
            
            # Actualizar estado
            solicitud.estado = 'aprobada'
            solicitud.aprobado_supervisor = True
            solicitud.fecha_aprobacion_supervisor = timezone.now()
            solicitud.fecha_resolucion = timezone.now()
            solicitud.save()
            
            # Crear notificación de aprobación
            from .notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_aprobacion(solicitud, aprobador, comentario_respuesta)
            
            return True, "Solicitud aprobada correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            return False, f"Error al aprobar la solicitud: {str(e)}"

    @staticmethod
    def rechazar_solicitud(solicitud_id, rechazador, comentario_respuesta=None):
        """
        Rechaza una solicitud de cambio
        """
        try:
            solicitud = SolicitudCambio.objects.get(id=solicitud_id)
            
            # Verificar que el rechazador sea el supervisor del solicitante
            if solicitud.explorador_solicitante.supervisor != rechazador:
                return False, "No tienes permisos para rechazar esta solicitud"
            
            # Actualizar estado
            solicitud.estado = 'rechazada'
            solicitud.aprobado_supervisor = False
            solicitud.fecha_aprobacion_supervisor = timezone.now()
            solicitud.fecha_resolucion = timezone.now()
            solicitud.save()
            
            # Crear notificación de rechazo
            from .notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_rechazo(solicitud, rechazador, comentario_respuesta)
            
            return True, "Solicitud rechazada correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            return False, f"Error al rechazar la solicitud: {str(e)}" 