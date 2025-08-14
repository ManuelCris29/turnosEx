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
                              comentario=None, turno_origen=None, turno_destino=None, fecha_cambio_turno=None):
        """
        Crea una nueva solicitud de cambio de turno y envía notificaciones
        Incluye lógica para cancelar solicitudes anteriores de la misma fecha
        """
        from .notificacion_service import NotificacionService
        
        print(f"DEBUG SOLICITUD: Creando solicitud...")
        print(f"DEBUG SOLICITUD: Solicitante: {explorador_solicitante.nombre} {explorador_solicitante.apellido}")
        print(f"DEBUG SOLICITUD: Receptor: {explorador_receptor.nombre} {explorador_receptor.apellido}")
        print(f"DEBUG SOLICITUD: Tipo: {tipo_cambio.nombre}")
        print(f"DEBUG SOLICITUD: Fecha cambio: {fecha_cambio_turno}")
        
        # 1. Verificar si ya existe una solicitud pendiente para la misma fecha
        solicitud_anterior = SolicitudCambio.objects.filter(
            explorador_solicitante=explorador_solicitante,
            estado='pendiente',
            fecha_cambio_turno=fecha_cambio_turno
        ).first()
        
        if solicitud_anterior:
            print(f"DEBUG SOLICITUD: Encontrada solicitud anterior ID: {solicitud_anterior.id}")
            
            # 2. Verificar si la solicitud anterior ya fue aprobada por alguien
            if solicitud_anterior.aprobado_receptor or solicitud_anterior.aprobado_supervisor:
                print(f"DEBUG SOLICITUD: ❌ Solicitud anterior ya fue aprobada - No se puede cancelar")
                return None, "No puedes crear una nueva solicitud porque la anterior ya fue aprobada"
            
            # 3. Cancelar la solicitud anterior
            print(f"DEBUG SOLICITUD: Cancelando solicitud anterior ID: {solicitud_anterior.id}")
            solicitud_anterior.estado = 'cancelada'
            solicitud_anterior.comentario = f"{solicitud_anterior.comentario or ''}\n\nCancelada automáticamente al crear nueva solicitud"
            solicitud_anterior.fecha_resolucion = timezone.now()
            solicitud_anterior.save()
            
            # 4. Notificar al receptor anterior sobre la cancelación
            try:
                NotificacionService.crear_notificacion_cancelacion(solicitud_anterior)
                print(f"DEBUG SOLICITUD: Notificación de cancelación enviada para solicitud {solicitud_anterior.id}")
            except Exception as e:
                print(f"ERROR SOLICITUD enviando notificación de cancelación: {e}")
        
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
        
        print(f"DEBUG SOLICITUD: Nueva solicitud creada con ID: {solicitud.id}")
        print(f"DEBUG SOLICITUD: Fecha cambio turno guardada: {solicitud.fecha_cambio_turno}")
        
        # 6. Crear notificaciones y enviar emails para la nueva solicitud
        try:
            print(f"DEBUG SOLICITUD: Llamando a NotificacionService.crear_notificacion_solicitud")
            NotificacionService.crear_notificacion_solicitud(solicitud)
            print(f"DEBUG SOLICITUD: Notificaciones creadas para solicitud {solicitud.id}")
        except Exception as e:
            print(f"ERROR SOLICITUD creando notificaciones: {e}")
            import traceback
            print(f"ERROR SOLICITUD traceback: {traceback.format_exc()}")
        
        return solicitud, "Solicitud creada correctamente"

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
        print(f"DEBUG VALIDACION: Verificando solicitudes existentes...")
        print(f"DEBUG VALIDACION: Solicitante: {explorador_solicitante.nombre}")
        print(f"DEBUG VALIDACION: Receptor: {explorador_receptor.nombre}")
        print(f"DEBUG VALIDACION: Fecha: {fecha}")
        
        # SOLUCIÓN: Solo bloquear si existe solicitud pendiente en la MISMA fecha
        # PERO permitir si es la misma fecha pero diferente receptor (se cancelará la anterior)
        solicitud_existente = SolicitudCambio.objects.filter(
            explorador_solicitante=explorador_solicitante,
            explorador_receptor=explorador_receptor,
            estado='pendiente',
            fecha_cambio_turno=fecha  # ¡FILTRAR POR FECHA!
        ).first()
        
        print(f"DEBUG VALIDACION: Solicitud existente encontrada: {solicitud_existente}")
        
        if solicitud_existente:
            print(f"DEBUG VALIDACION: ❌ VALIDACIÓN FALLÓ - Ya existe solicitud pendiente con el mismo receptor")
            print(f"DEBUG VALIDACION: Solicitud existente ID: {solicitud_existente.id}, Fecha: {solicitud_existente.fecha_cambio_turno}")
            return False, "Ya existe una solicitud pendiente con este explorador para la misma fecha"
        
        print(f"DEBUG VALIDACION: ✅ VALIDACIÓN EXITOSA")
        
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
    def aprobar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        Aprueba una solicitud por parte del supervisor
        """
        try:
            solicitud = SolicitudCambio.objects.get(id=solicitud_id)
            
            # Verificar que el aprobador sea el supervisor del solicitante
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
            
            solicitud.save()
            
            # Crear notificación de aprobación del supervisor
            from .notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_aprobacion_supervisor(solicitud, supervisor, comentario_respuesta)
            
            return True, "Solicitud aprobada por supervisor correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            return False, f"Error al aprobar la solicitud: {str(e)}"

    @staticmethod
    def aprobar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        Aprueba una solicitud por parte del compañero receptor
        """
        try:
            solicitud = SolicitudCambio.objects.get(id=solicitud_id)
            
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
            
            solicitud.save()
            
            # Crear notificación de aprobación del receptor
            from .notificacion_service import NotificacionService
            NotificacionService.crear_notificacion_aprobacion_receptor(solicitud, receptor, comentario_respuesta)
            
            return True, "Solicitud aprobada por compañero correctamente"
            
        except SolicitudCambio.DoesNotExist:
            return False, "Solicitud no encontrada"
        except Exception as e:
            return False, f"Error al aprobar la solicitud: {str(e)}"

    @staticmethod
    def rechazar_solicitud_supervisor(solicitud_id, supervisor, comentario_respuesta=None):
        """
        Rechaza una solicitud por parte del supervisor
        """
        try:
            solicitud = SolicitudCambio.objects.get(id=solicitud_id)
            
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
            return False, f"Error al rechazar la solicitud: {str(e)}"

    @staticmethod
    def rechazar_solicitud_receptor(solicitud_id, receptor, comentario_respuesta=None):
        """
        Rechaza una solicitud por parte del compañero receptor
        """
        try:
            solicitud = SolicitudCambio.objects.get(id=solicitud_id)
            
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
            return False, f"Error al rechazar la solicitud: {str(e)}"

    @staticmethod
    def get_solicitudes_por_receptor(receptor):
        """
        Obtiene las solicitudes pendientes que debe aprobar un receptor
        """
        return SolicitudCambio.objects.filter(
            explorador_receptor=receptor,
            estado='pendiente'
        ).order_by('-fecha_solicitud')

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