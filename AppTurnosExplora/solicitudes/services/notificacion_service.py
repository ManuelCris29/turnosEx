import logging

from django.utils import timezone

from core.utils.date_utils import DateUtils
from solicitudes.models import Notificacion
from solicitudes.services.email_service import EmailService

logger = logging.getLogger(__name__)

class NotificacionService:
    @staticmethod
    def _convertir_fecha(fecha):
        """Convierte fecha a objeto date si es string"""
        if isinstance(fecha, str):
            return DateUtils.parse_date(fecha)
        return fecha

    @staticmethod
    def _fmt_fecha(fecha) -> str:
        """Formatea una fecha a dd/mm/yyyy, devuelve cadena vacía si es None."""
        f = NotificacionService._convertir_fecha(fecha)
        return f.strftime('%d/%m/%Y') if f else 'fecha no especificada'
    
    @staticmethod
    def crear_notificacion_solicitud(solicitud):
        """
        Crea notificaciones para el supervisor, el compañero receptor Y el solicitante
        Maneja el caso especial donde supervisor = receptor

        Los TRES correos salen por una sola conexión SMTP (`envio_agrupado`). Antes cada
        uno abría la suya: tres saludos TLS + AUTH de ~2 s cada uno, y en desarrollo, donde
        el envío es síncrono, esos ~6 s los esperaba el explorador con el formulario
        bloqueado. El grupo es reentrante, así que los flujos que crean varias solicitudes
        de golpe (cobertura con 2 compañeros, doblada permanente con N) pueden envolver el
        bucle entero y quedarse igualmente con UNA conexión para todo.
        """
        from solicitudes.services.email_outbox_service import EmailOutboxService

        with EmailOutboxService.envio_agrupado():
            NotificacionService._notificar_solicitud_creada(solicitud)

    @staticmethod
    def _notificar_solicitud_creada(solicitud):
        """Cuerpo de `crear_notificacion_solicitud`. Ver allí por qué está separado."""
        logger.info(f"Iniciando creación de notificaciones para solicitud {solicitud.id}")
        
        try:
            # Cargar solicitud con relaciones completas
            solicitud_completa = EmailService._cargar_solicitud_completa(solicitud)
        except Exception as e:
            logger.exception(f"Error cargando solicitud completa {solicitud.id}: {e}")
            solicitud_completa = solicitud  # Usar solicitud original como fallback
        
        logger.info(f"Solicitante: {solicitud_completa.explorador_solicitante.nombre} {solicitud_completa.explorador_solicitante.apellido}")
        logger.info(f"Receptor: {solicitud_completa.explorador_receptor.nombre} {solicitud_completa.explorador_receptor.apellido}")
        logger.info(f"Fecha cambio turno: {solicitud_completa.fecha_cambio_turno}")
        
        # Verificar si supervisor = receptor
        supervisor = solicitud_completa.explorador_solicitante.supervisor
        receptor = solicitud_completa.explorador_receptor
        es_mismo_usuario = supervisor and supervisor.id == receptor.id
        
        logger.info(f"Supervisor: {supervisor.nombre if supervisor else 'No asignado'}")
        logger.info(f"Receptor: {receptor.nombre}")
        logger.info(f"¿Es el mismo usuario? {es_mismo_usuario}")
        
        # Validar emails antes de proceder
        emails_validos = True
        if not receptor.email or not receptor.email.strip():
            logger.error(f"❌ Receptor {receptor.nombre} no tiene email válido: '{receptor.email}'")
            emails_validos = False
        
        if supervisor and (not supervisor.email or not supervisor.email.strip()):
            logger.error(f"❌ Supervisor {supervisor.nombre} no tiene email válido: '{supervisor.email}'")
            emails_validos = False
        
        if not solicitud_completa.explorador_solicitante.email or not solicitud_completa.explorador_solicitante.email.strip():
            logger.error(f"❌ Solicitante {solicitud_completa.explorador_solicitante.nombre} no tiene email válido: '{solicitud_completa.explorador_solicitante.email}'")
            emails_validos = False
        
        if not emails_validos:
            logger.warning("⚠️ Algunos emails son inválidos, pero se continuará con el proceso de notificaciones")
        
        if es_mismo_usuario:
            # CASO ESPECIAL: Supervisor = Receptor
            logger.info("Caso especial - Supervisor = Receptor")
            
            # Crear notificación combinada
            try:
                NotificacionService._crear_notificacion_supervisor_receptor(solicitud_completa)
            except Exception as e:
                logger.exception(f"Error creando notificación supervisor-receptor: {e}")
            
            # Enviar email combinado
            try:
                resultado = EmailService._enviar_email_supervisor_receptor(solicitud_completa)
                if resultado:
                    logger.info("✅ Email combinado enviado exitosamente")
                else:
                    logger.warning("⚠️ Email combinado no se pudo enviar (retornó False)")
            except Exception as e:
                logger.exception(f"❌ Error enviando email combinado: {e}")
        else:
            # CASO NORMAL: Supervisor ≠ Receptor
            logger.info("Caso normal - Supervisor ≠ Receptor")
            
            # Notificación para el supervisor
            if supervisor:
                logger.info(f"Creando notificación para supervisor: {supervisor.nombre}")
                try:
                    NotificacionService._crear_notificacion_supervisor(solicitud_completa)
                except Exception as e:
                    logger.exception(f"Error creando notificación supervisor: {e}")
            else:
                logger.info(f"No hay supervisor asignado para {solicitud_completa.explorador_solicitante.nombre}")
            
            # Notificación para el compañero receptor
            logger.info(f"Creando notificación para receptor: {receptor.nombre}")
            try:
                NotificacionService._crear_notificacion_receptor(solicitud_completa)
            except Exception as e:
                logger.exception(f"Error creando notificación receptor: {e}")
            
            # Enviar emails separados
            logger.info("Enviando emails separados...")
            # Enviar email al supervisor
            supervisor_email_sent = False
            if supervisor:
                try:
                    supervisor_email_sent = EmailService._enviar_email_supervisor(solicitud_completa)
                    if supervisor_email_sent:
                        logger.info("✅ Email al supervisor enviado exitosamente")
                    else:
                        logger.warning("⚠️ Email al supervisor no se pudo enviar (retornó False)")
                except Exception as e:
                    logger.exception(f"❌ Error enviando email al supervisor: {e}")
            
            # Enviar email al receptor
            receptor_email_sent = False
            try:
                receptor_email_sent = EmailService._enviar_email_receptor(solicitud_completa)
                if receptor_email_sent:
                    logger.info("✅ Email al receptor enviado exitosamente")
                else:
                    logger.warning("⚠️ Email al receptor no se pudo enviar (retornó False)")
            except Exception as e:
                logger.exception(f"❌ Error enviando email al receptor: {e}")
        
        # Notificación para el solicitante (siempre se crea)
        logger.info(f"Creando notificación para solicitante: {solicitud_completa.explorador_solicitante.nombre}")
        try:
            NotificacionService._crear_notificacion_solicitante(solicitud_completa)
        except Exception as e:
            logger.exception(f"Error creando notificación solicitante: {e}")
        
        try:
            resultado = EmailService._enviar_email_solicitante(solicitud_completa)
            if resultado:
                logger.info("✅ Email al solicitante enviado exitosamente")
            else:
                logger.warning("⚠️ Email al solicitante no se pudo enviar (retornó False)")
        except Exception as e:
            logger.exception(f"❌ Error enviando email al solicitante: {e}")
        
        logger.info("Proceso de notificaciones completado")
    
    @staticmethod
    def _crear_notificacion_supervisor(solicitud):
        """Crea notificación para el supervisor"""
        supervisor = solicitud.explorador_solicitante.supervisor
        if not supervisor:
            return

        fecha_cesion = NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno)

        # Caso E: detectar si la fecha de cesión cae en temporada
        aviso_temporada = ''
        try:
            from solicitudes.services.solicitud_validator import SolicitudValidator
            if SolicitudValidator.es_dia_temporada(fecha_cesion):
                aviso_temporada = (
                    '\n\n        ⚠️ AVISO DE TEMPORADA: La fecha de cesión '
                    f'({fecha_cesion.strftime("%d/%m/%Y")}) cae en un día de temporada. '
                    'Tenga en cuenta las necesidades de personal antes de aprobar.'
                )
        except Exception:
            logger.warning("Error detectando aviso de temporada para notificación (fecha=%s)", fecha_cesion, exc_info=True)

        titulo = 'Nueva solicitud de cambio de turno'
        mensaje = f"""
        {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} 
        ha solicitado un cambio de turno con {solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}
        para el día {fecha_cesion.strftime('%d/%m/%Y')}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Pendiente de aprobación{aviso_temporada}
        """

        Notificacion.objects.create(
            destinatario=supervisor,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
    
    @staticmethod
    def _crear_notificacion_receptor(solicitud):
        """Crea notificación para el compañero receptor"""
        titulo = "Solicitud de cambio de turno recibida"
        mensaje = f"""
        {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} 
        te ha enviado una solicitud de cambio de turno para el día {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Pendiente de tu aprobación
        """
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_receptor,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
    
    @staticmethod
    def _crear_notificacion_supervisor_receptor(solicitud):
        """Crea notificación combinada para cuando supervisor = receptor"""
        supervisor_receptor = solicitud.explorador_receptor

        fecha_cesion = NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno)

        # Caso E: detectar si la fecha de cesión cae en temporada
        aviso_temporada = ''
        try:
            from solicitudes.services.solicitud_validator import SolicitudValidator
            if SolicitudValidator.es_dia_temporada(fecha_cesion):
                aviso_temporada = (
                    '\n\n        ⚠️ AVISO DE TEMPORADA: La fecha de cesión '
                    f'({fecha_cesion.strftime("%d/%m/%Y")}) cae en un día de temporada. '
                    'Tenga en cuenta las necesidades de personal antes de aprobar.'
                )
        except Exception:
            logger.warning("Error detectando aviso de temporada para notificación rol doble (fecha=%s)", fecha_cesion, exc_info=True)

        titulo = 'Solicitud de cambio de turno - Rol Doble (Supervisor + Receptor)'
        mensaje = f"""
        {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}
        te ha enviado una solicitud de cambio de turno para el día {NotificacionService._fmt_fecha(fecha_cesion)}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Pendiente de aprobación
        
        IMPORTANTE: Como eres tanto su supervisor como el receptor de la solicitud, 
        necesitas aprobar esta solicitud en ambos roles.{aviso_temporada}
        """
        
        Notificacion.objects.create(
            destinatario=supervisor_receptor,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
    
    @staticmethod
    def _crear_notificacion_solicitante(solicitud):
        """Crea notificación para el solicitante (para que pueda ver el estado)"""
        titulo = "Solicitud de cambio de turno enviada"
        mensaje = f"""
        Has enviado una solicitud de cambio de turno a {solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}
        para el día {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Pendiente de aprobación
        
        Podrás ver el estado de tu solicitud en la sección de notificaciones.
        """
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
    
    @staticmethod
    def marcar_como_leida(notificacion_id, empleado):
        """
        Marca una notificación como leída
        """
        try:
            notificacion = Notificacion.objects.get(id=notificacion_id, destinatario=empleado)
            notificacion.leida = True
            notificacion.fecha_lectura = timezone.now()
            notificacion.save()
            return True
        except Notificacion.DoesNotExist:
            return False

    @staticmethod
    def obtener_notificaciones(empleado):
        """
        Obtiene todas las notificaciones de un empleado
        """
        # OPTIMIZACIÓN: evitar N+1 al acceder a notificacion.solicitud en la vista de notificaciones
        return (
            Notificacion.objects
            .filter(destinatario=empleado)
            .select_related(
                'solicitud',
                'solicitud__tipo_cambio',
            )
            .order_by('-fecha_creacion')
        )

    @staticmethod
    def crear_notificacion_aprobacion_supervisor(solicitud, supervisor, comentario_respuesta=None):
        """
        Crea notificación cuando el supervisor aprueba una solicitud
        """
        # Notificación para el solicitante
        titulo = f"Solicitud Aprobada por Supervisor - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)} ha sido aprobada por tu supervisor {supervisor.nombre} {supervisor.apellido}."
        if comentario_respuesta:
            mensaje += f"\n\nComentario del supervisor: {comentario_respuesta}"
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='aprobacion',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        # Notificación para el receptor (si aún no ha aprobado)
        if not solicitud.aprobado_receptor:
            titulo_receptor = f"Solicitud Aprobada por Supervisor - {solicitud.tipo_cambio.nombre}"
            mensaje_receptor = f"La solicitud de {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} para el {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)} ha sido aprobada por el supervisor. Tu aprobación está pendiente."
            
            Notificacion.objects.create(
                destinatario=solicitud.explorador_receptor,
                tipo='aprobacion',
                titulo=titulo_receptor,
                mensaje=mensaje_receptor,
                solicitud=solicitud
            )
        
        # Enviar email de aprobación
        EmailService._enviar_email_aprobacion_supervisor(solicitud, supervisor, comentario_respuesta)

    @staticmethod
    def crear_notificacion_aprobacion_receptor(solicitud, receptor, comentario_respuesta=None):
        """
        Crea notificación cuando el receptor aprueba una solicitud
        """
        from solicitudes.services.email_outbox_service import EmailOutboxService

        # Los dos correos posibles (aviso al supervisor + aprobación al solicitante) por
        # una sola conexión SMTP; es el segundo sitio del proyecto que manda más de uno.
        with EmailOutboxService.envio_agrupado():
            NotificacionService._notificar_aprobacion_receptor(
                solicitud, receptor, comentario_respuesta)

    @staticmethod
    def _notificar_aprobacion_receptor(solicitud, receptor, comentario_respuesta=None):
        """Cuerpo de `crear_notificacion_aprobacion_receptor`."""
        # Notificación para el solicitante
        titulo = f"Solicitud Aprobada por Compañero - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)} ha sido aprobada por tu compañero {receptor.nombre} {receptor.apellido}."
        if comentario_respuesta:
            mensaje += f"\n\nComentario del compañero: {comentario_respuesta}"
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='aprobacion',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        # Notificación para el supervisor (si aún no ha aprobado)
        if solicitud.explorador_solicitante.supervisor and not solicitud.aprobado_supervisor:
            titulo_supervisor = f"Solicitud Aprobada por Compañero - {solicitud.tipo_cambio.nombre}"
            mensaje_supervisor = (
                f"La solicitud de {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} "
                f"para el {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)} "
                f"ha sido aprobada por el compañero. Tu aprobación está pendiente."
            )

            Notificacion.objects.create(
                destinatario=solicitud.explorador_solicitante.supervisor,
                tipo='aprobacion',
                titulo=titulo_supervisor,
                mensaje=mensaje_supervisor,
                solicitud=solicitud
            )

            # Enviar email al supervisor para que apruebe
            try:
                logger.debug('Enviando correo al supervisor %s tras la aprobación del receptor (solicitud %s)',
                             solicitud.explorador_solicitante.supervisor.email, solicitud.id)
                enviado = EmailService._enviar_email_supervisor(solicitud)
                logger.debug('Resultado del envío al supervisor (solicitud %s): %s', solicitud.id, enviado)
            except Exception:
                # `logger.exception` y no `print`: el print iba a stdout SIN traza y sin el
                # request_id, así que en producción el fallo se perdía del pipeline de logs
                # justo en el paso que avisa al supervisor de que tiene algo que aprobar.
                logger.exception('Error enviando email al supervisor tras la aprobación del receptor (solicitud %s)',
                                 solicitud.id)

        # Enviar email de aprobación al solicitante
        EmailService._enviar_email_aprobacion_receptor(solicitud, receptor, comentario_respuesta)

    @staticmethod
    def crear_notificacion_rechazo_supervisor(solicitud, supervisor, comentario_respuesta=None):
        """
        Crea notificación cuando el supervisor rechaza una solicitud
        """
        # Notificación para el solicitante
        titulo = f"Solicitud Rechazada por Supervisor - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)} ha sido rechazada por tu supervisor {supervisor.nombre} {supervisor.apellido}."
        if comentario_respuesta:
            mensaje += f"\n\nMotivo del rechazo: {comentario_respuesta}"
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='rechazo',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        # Notificación para el receptor
        titulo_receptor = f"Solicitud Rechazada por Supervisor - {solicitud.tipo_cambio.nombre}"
        mensaje_receptor = f"La solicitud de {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} para el {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)} ha sido rechazada por el supervisor."
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_receptor,
            tipo='rechazo',
            titulo=titulo_receptor,
            mensaje=mensaje_receptor,
            solicitud=solicitud
        )
        
        # Enviar email de rechazo
        EmailService._enviar_email_rechazo_supervisor(solicitud, supervisor, comentario_respuesta)

    @staticmethod
    def crear_notificacion_rechazo_receptor(solicitud, receptor, comentario_respuesta=None):
        """
        Crea notificación cuando el receptor rechaza una solicitud
        """
        # Notificación para el solicitante
        titulo = f"Solicitud Rechazada por Compañero - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)} ha sido rechazada por tu compañero {receptor.nombre} {receptor.apellido}."
        if comentario_respuesta:
            mensaje += f"\n\nMotivo del rechazo: {comentario_respuesta}"
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='rechazo',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        # Notificación para el supervisor
        if solicitud.explorador_solicitante.supervisor:
            titulo_supervisor = f"Solicitud Rechazada por Compañero - {solicitud.tipo_cambio.nombre}"
            mensaje_supervisor = f"La solicitud de {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} para el {NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)} ha sido rechazada por el compañero."
            
            Notificacion.objects.create(
                destinatario=solicitud.explorador_solicitante.supervisor,
                tipo='rechazo',
                titulo=titulo_supervisor,
                mensaje=mensaje_supervisor,
                solicitud=solicitud
            )
        
        # Enviar email de rechazo
        EmailService._enviar_email_rechazo_receptor(solicitud, receptor, comentario_respuesta) 

    @staticmethod
    def crear_notificacion_rechazo_automatico(solicitud):
        """
        FASE 1.15: Crea notificación cuando una solicitud es rechazada automáticamente
        por el sistema debido a First-Come, First-Served (otra solicitud fue aprobada primero).
        
        Args:
            solicitud: SolicitudCambio instance que fue rechazada automáticamente
        """
        # Notificación para el solicitante
        titulo = f"Solicitud Rechazada Automáticamente - {solicitud.tipo_cambio.nombre}"
        fecha_str = NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)
        mensaje = (
            f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {fecha_str} "
            f"ha sido rechazada automáticamente porque otra solicitud para el mismo receptor "
            f"y fecha fue aprobada primero (First-Come, First-Served)."
        )
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='rechazo',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        # Notificación para el supervisor
        if solicitud.explorador_solicitante.supervisor:
            titulo_supervisor = f"Solicitud Rechazada Automáticamente - {solicitud.tipo_cambio.nombre}"
            mensaje_supervisor = (
                f"La solicitud de {solicitud.explorador_solicitante.nombre} "
                f"{solicitud.explorador_solicitante.apellido} para el {fecha_str} "
                f"ha sido rechazada automáticamente porque otra solicitud para el mismo receptor "
                f"y fecha fue aprobada primero."
            )
            
            Notificacion.objects.create(
                destinatario=solicitud.explorador_solicitante.supervisor,
                tipo='rechazo',
                titulo=titulo_supervisor,
                mensaje=mensaje_supervisor,
                solicitud=solicitud
            )
        
        # Nota: No enviamos email para rechazos automáticos para evitar spam
        # Las notificaciones en la aplicación son suficientes

    @staticmethod
    def crear_notificacion_traspaso_cobertura(solicitud, info_cobertura, sustituto):
        """
        Avisa al acreedor de una solicitud previa de que OTRA persona pasa a cubrir su día.

        Caso: A trabajaba el día X por un favor pactado con B (se lo cubría o se lo pagaba). A
        cede ahora ese X a C. B conserva su descanso y su deuda sigue saldada —el día lo trabaja
        C—, pero cambia quién lo cubre, y eso B tiene que saberlo. La solicitud original NO se
        toca: sigue aprobada y vigente.

        Args:
            solicitud: la solicitud NUEVA (el traspaso).
            info_cobertura: dict de `TurnoService.dia_cubriendo_por_solicitud` (quién era el
                acreedor y por qué solicitud).
            sustituto: Empleado que pasa a cubrir el día.
        """
        acreedor_id = (info_cobertura.get('companero') or {}).get('id')
        if not acreedor_id:
            return
        from empleados.models import Empleado
        acreedor = Empleado.objects.filter(id=acreedor_id).first()
        if not acreedor:
            return

        fecha_str = NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)
        cedente = solicitud.explorador_solicitante
        Notificacion.objects.create(
            destinatario=acreedor,
            tipo='aprobacion',
            titulo=f"Cambio de cobertura - {fecha_str}",
            mensaje=(
                f"El {fecha_str} lo iba a cubrir {cedente.nombre} {cedente.apellido} por el "
                f"acuerdo de la solicitud #{info_cobertura.get('solicitud_id')}. A partir de "
                f"ahora ese día lo cubre {sustituto.nombre} {sustituto.apellido}. "
                f"Tu descanso no cambia y el acuerdo sigue vigente."
            ),
            solicitud=solicitud,
        )

    @staticmethod
    def crear_notificacion_cancelacion(solicitud):
        """Crea notificación de cancelación para el receptor"""
        if not solicitud.explorador_receptor_id:
            return

        fecha = NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno)
        fecha_str = fecha.strftime('%d/%m/%Y') if fecha else 'fecha no especificada'
        tipo_nombre = solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'Cambio de turno'

        titulo = "Solicitud de cambio de turno cancelada"
        mensaje = (
            f"{solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} "
            f"ha cancelado la solicitud de cambio de turno para el día {fecha_str}.\n\n"
            f"Tipo de solicitud: {tipo_nombre}\n"
            f"Estado: Cancelada\n\n"
            f"Ya no necesitas aprobar o rechazar esta solicitud."
        )

        Notificacion.objects.create(
            destinatario=solicitud.explorador_receptor,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud,
        )

        # Enviar email de cancelación
        EmailService._enviar_email_cancelacion(solicitud)

    @staticmethod
    def crear_notificacion_peticion_cancelacion(solicitud):
        """
        Avisa al RECEPTOR de que el solicitante pide cancelar un cambio YA APROBADO.

        Es una notificación que exige acción, no un aviso informativo: hasta que el receptor
        responda el cambio sigue vigente, y si no responde a tiempo la petición caduca. Por eso
        el mensaje dice explícitamente que el cambio sigue en pie y que hay un plazo.
        """
        if not solicitud.explorador_receptor_id:
            return

        from core.constants import VENTANA_RESPONDER_CANCELACION_HORAS

        fecha_str = NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)
        tipo_nombre = solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'Cambio de turno'
        quien = (f"{solicitud.explorador_solicitante.nombre} "
                 f"{solicitud.explorador_solicitante.apellido}")
        motivo = f"\n\nMotivo: {solicitud.cancelacion_motivo}" if solicitud.cancelacion_motivo else ''

        Notificacion.objects.create(
            destinatario=solicitud.explorador_receptor,
            tipo='solicitud_cambio',
            titulo='Te piden cancelar un cambio ya aprobado',
            mensaje=(
                f"{quien} pide cancelar el cambio del día {fecha_str} que ya habías aprobado.\n\n"
                f"Tipo de solicitud: {tipo_nombre}{motivo}\n\n"
                f"El cambio SIGUE VIGENTE hasta que respondas. Tienes "
                f"{VENTANA_RESPONDER_CANCELACION_HORAS} horas para aprobar o rechazar la "
                f"cancelación; si no respondes, el cambio queda firme."
            ),
            solicitud=solicitud,
        )

    @staticmethod
    def crear_notificacion_respuesta_cancelacion(solicitud, receptor, aprobada):
        """
        Avisa al SOLICITANTE de la respuesta del receptor.

        Se notifica igual si aprueba que si rechaza: en un caso su turno vuelve al original y en
        el otro no, y esa diferencia decide qué día trabaja. Un rechazo es definitivo, así que el
        mensaje dice cuál es la salida en vez de dejarlo esperando.
        """
        fecha_str = NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)
        tipo_nombre = solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'Cambio de turno'
        quien = f"{receptor.nombre} {receptor.apellido}"

        if aprobada:
            titulo = 'Cancelación aprobada'
            cuerpo = (
                f"{quien} aprobó la cancelación del cambio del día {fecha_str}.\n\n"
                f"Tipo de solicitud: {tipo_nombre}\n\n"
                f"Los turnos volvieron a como estaban antes del cambio."
            )
        else:
            titulo = 'Cancelación rechazada'
            cuerpo = (
                f"{quien} rechazó la cancelación del cambio del día {fecha_str}, así que el "
                f"cambio sigue vigente y queda firme.\n\n"
                f"Tipo de solicitud: {tipo_nombre}\n\n"
                f"No se puede volver a pedir la cancelación. Si necesitas volver a tu turno "
                f"original, solicita un cambio nuevo o consulta con tu supervisor."
            )

        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=cuerpo,
            solicitud=solicitud,
        )

    @staticmethod
    def crear_notificacion_gestion(solicitud, supervisor, accion, vincular=True):
        """
        Avisa a AMBAS partes de que un supervisor intervino su solicitud desde gestión.

        `crear_notificacion_cancelacion` no sirve aquí por dos motivos: solo avisa al receptor
        —y aquí el solicitante es justamente quien no se enteraba de que le tocaron su cambio— y
        redacta "el solicitante ha cancelado", que sería falso. El nombre del supervisor va en el
        mensaje: es la traza que le queda al explorador de quién tomó la decisión.

        `accion` es el participio femenino que concuerda con "solicitud": 'cancelada', 'eliminada'.

        `vincular=False` guarda la notificación SIN FK a la solicitud, para que sobreviva cuando
        la solicitud se borra (el FK es CASCADE). Es el caso de "eliminar".
        """
        fecha_str = NotificacionService._fmt_fecha(solicitud.fecha_cambio_turno)
        tipo_nombre = solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'Cambio de turno'
        quien = f"{supervisor.nombre} {supervisor.apellido}" if supervisor else 'un supervisor'

        titulo = f"Solicitud {accion} por un supervisor"
        mensaje = (
            f"Tu solicitud #{solicitud.id} del día {fecha_str} ha sido {accion} "
            f"por {quien} desde Gestión de Solicitudes.\n\n"
            f"Tipo de solicitud: {tipo_nombre}\n\n"
            f"Si necesitas el cambio, vuelve a solicitarlo o consulta con tu supervisor."
        )

        destinatarios = [solicitud.explorador_solicitante]
        if solicitud.explorador_receptor_id:
            destinatarios.append(solicitud.explorador_receptor)

        for destinatario in destinatarios:
            Notificacion.objects.create(
                destinatario=destinatario,
                tipo='solicitud_cambio',
                titulo=titulo,
                mensaje=mensaje,
                solicitud=solicitud if vincular else None,
            )

