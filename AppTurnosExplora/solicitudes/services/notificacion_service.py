from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from solicitudes.models import Notificacion, SolicitudCambio
from empleados.models import Empleado
from datetime import datetime
from django.utils import timezone
import hashlib
import hmac
from django.core.mail.backends.smtp import EmailBackend

class NotificacionService:
    @staticmethod
    def _convertir_fecha(fecha):
        """Convierte fecha a objeto date si es string"""
        if isinstance(fecha, str):
            from datetime import datetime
            return datetime.strptime(fecha, '%Y-%m-%d').date()
        return fecha
    
    @staticmethod
    def _configurar_email_backend(email_usuario):
        """Configura el backend de email para usar el correo del usuario"""
        try:
            # Intentar usar el correo del usuario como EMAIL_HOST_USER
            backend = EmailBackend(
                host=settings.EMAIL_HOST,
                port=settings.EMAIL_PORT,
                username=email_usuario,  # Usar el correo del usuario
                password=settings.EMAIL_HOST_PASSWORD,  # Usar la contraseña configurada
                use_tls=settings.EMAIL_USE_TLS,
                fail_silently=False
            )
            return backend
        except Exception as e:
            print(f"Error configurando email backend para {email_usuario}: {e}")
            # Si falla, usar la configuración por defecto
            return None
    
    @staticmethod
    def _enviar_email_desde_usuario(subject, message, from_email, recipient_list, html_message=None):
        """Envía email usando el correo del usuario logueado"""
        try:
            # Intentar usar el backend personalizado
            backend = NotificacionService._configurar_email_backend(from_email)
            
            if backend:
                # Usar el backend personalizado
                from django.core.mail import EmailMessage
                email = EmailMessage(
                    subject=subject,
                    body=message,
                    from_email=from_email,
                    to=recipient_list
                )
                if html_message:
                    email.content_subtype = "html"
                backend.send_messages([email])
                print(f"Email enviado desde {from_email} usando backend personalizado")
            else:
                # Usar la configuración por defecto pero con from_email personalizado
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=from_email,
                    recipient_list=recipient_list,
                    html_message=html_message,
                    fail_silently=False,
                )
                print(f"Email enviado desde {from_email} usando configuración por defecto")
                
        except Exception as e:
            print(f"Error enviando email desde {from_email}: {e}")
            # Fallback: usar configuración por defecto
            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipient_list,
                    html_message=html_message,
                    fail_silently=False,
                )
                print(f"Email enviado usando configuración por defecto como fallback")
            except Exception as fallback_error:
                print(f"Error en fallback: {fallback_error}")
    
    @staticmethod
    def _generar_token(solicitud_id, empleado_id, tipo):
        """Genera un token de seguridad para aprobación por email"""
        data = f"{solicitud_id}_{empleado_id}_{tipo}"
        return hmac.new(
            b'secret_key_change_this',  # Cambiar en producción
            data.encode(),
            hashlib.sha256
        ).hexdigest()
    
    @staticmethod
    def _generar_enlaces_aprobacion(solicitud):
        """Genera enlaces de aprobación para email"""
        enlaces = {}
        
        # Enlaces para supervisor
        if solicitud.explorador_solicitante.supervisor:
            supervisor = solicitud.explorador_solicitante.supervisor
            token_supervisor = NotificacionService._generar_token(solicitud.id, supervisor.id, 'supervisor')
            enlaces['supervisor'] = {
                'aprobar': f"{settings.SITE_URL}/solicitudes/aprobar-email/{solicitud.id}/{token_supervisor}/",
                'rechazar': f"{settings.SITE_URL}/solicitudes/rechazar-email/{solicitud.id}/{token_supervisor}/"
            }
        
        # Enlaces para receptor
        token_receptor = NotificacionService._generar_token(solicitud.id, solicitud.explorador_receptor.id, 'receptor')
        enlaces['receptor'] = {
            'aprobar': f"{settings.SITE_URL}/solicitudes/aprobar-receptor-email/{solicitud.id}/{token_receptor}/",
            'rechazar': f"{settings.SITE_URL}/solicitudes/rechazar-receptor-email/{solicitud.id}/{token_receptor}/"
        }
        
        return enlaces
    
    @staticmethod
    def crear_notificacion_solicitud(solicitud):
        """
        Crea notificaciones para el supervisor, el compañero receptor Y el solicitante
        Maneja el caso especial donde supervisor = receptor
        """
        print(f"DEBUG: Iniciando creación de notificaciones para solicitud {solicitud.id}")
        print(f"DEBUG: Solicitante: {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}")
        print(f"DEBUG: Receptor: {solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}")
        print(f"DEBUG: Fecha cambio turno: {solicitud.fecha_cambio_turno}")
        
        # Verificar si supervisor = receptor
        supervisor = solicitud.explorador_solicitante.supervisor
        receptor = solicitud.explorador_receptor
        es_mismo_usuario = supervisor and supervisor.id == receptor.id
        
        print(f"DEBUG: Supervisor: {supervisor.nombre if supervisor else 'No asignado'}")
        print(f"DEBUG: Receptor: {receptor.nombre}")
        print(f"DEBUG: ¿Es el mismo usuario? {es_mismo_usuario}")
        
        if es_mismo_usuario:
            # CASO ESPECIAL: Supervisor = Receptor
            print(f"DEBUG: Caso especial - Supervisor = Receptor")
            
            # Crear notificación combinada
            NotificacionService._crear_notificacion_supervisor_receptor(solicitud)
            
            # Enviar email combinado
            try:
                NotificacionService._enviar_email_supervisor_receptor(solicitud)
                print(f"DEBUG: Email combinado enviado")
            except Exception as e:
                print(f"ERROR enviando email combinado: {e}")
        else:
            # CASO NORMAL: Supervisor ≠ Receptor
            print(f"DEBUG: Caso normal - Supervisor ≠ Receptor")
            
            # Notificación para el supervisor
            if supervisor:
                print(f"DEBUG: Creando notificación para supervisor: {supervisor.nombre}")
                NotificacionService._crear_notificacion_supervisor(solicitud)
            else:
                print(f"DEBUG: No hay supervisor asignado para {solicitud.explorador_solicitante.nombre}")
            
            # Notificación para el compañero receptor
            print(f"DEBUG: Creando notificación para receptor: {receptor.nombre}")
            NotificacionService._crear_notificacion_receptor(solicitud)
            
            # Enviar emails separados
            print(f"DEBUG: Enviando emails separados...")
            try:
                NotificacionService._enviar_email_supervisor(solicitud)
                print(f"DEBUG: Email al supervisor enviado")
            except Exception as e:
                print(f"ERROR enviando email al supervisor: {e}")
            
            try:
                NotificacionService._enviar_email_receptor(solicitud)
                print(f"DEBUG: Email al receptor enviado")
            except Exception as e:
                print(f"ERROR enviando email al receptor: {e}")
        
        # Notificación para el solicitante (siempre se crea)
        print(f"DEBUG: Creando notificación para solicitante: {solicitud.explorador_solicitante.nombre}")
        NotificacionService._crear_notificacion_solicitante(solicitud)
        
        try:
            NotificacionService._enviar_email_solicitante(solicitud)
            print(f"DEBUG: Email al solicitante enviado")
        except Exception as e:
            print(f"ERROR enviando email al solicitante: {e}")
        
        print(f"DEBUG: Proceso de notificaciones completado")
    
    @staticmethod
    def _crear_notificacion_supervisor(solicitud):
        """Crea notificación para el supervisor"""
        supervisor = solicitud.explorador_solicitante.supervisor
        if not supervisor:
            return
        
        titulo = f"Nueva solicitud de cambio de turno"
        mensaje = f"""
        {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} 
        ha solicitado un cambio de turno con {solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}
        para el día {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Pendiente de aprobación
        """
        
        print(f"DEBUG: Creando notificación para supervisor {supervisor.nombre}")
        
        Notificacion.objects.create(
            destinatario=supervisor,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        print(f"DEBUG: Notificación creada para supervisor {supervisor.nombre}")
    
    @staticmethod
    def _crear_notificacion_receptor(solicitud):
        """Crea notificación para el compañero receptor"""
        titulo = f"Solicitud de cambio de turno recibida"
        mensaje = f"""
        {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} 
        te ha enviado una solicitud de cambio de turno para el día {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Pendiente de tu aprobación
        """
        
        print(f"DEBUG: Creando notificación para receptor {solicitud.explorador_receptor.nombre}")
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_receptor,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        print(f"DEBUG: Notificación creada para receptor {solicitud.explorador_receptor.nombre}")
    
    @staticmethod
    def _crear_notificacion_supervisor_receptor(solicitud):
        """Crea notificación combinada para cuando supervisor = receptor"""
        supervisor_receptor = solicitud.explorador_receptor
        
        titulo = f"Solicitud de cambio de turno - Rol Doble (Supervisor + Receptor)"
        mensaje = f"""
        {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} 
        te ha enviado una solicitud de cambio de turno para el día {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Pendiente de aprobación
        
        IMPORTANTE: Como eres tanto su supervisor como el receptor de la solicitud, 
        necesitas aprobar esta solicitud en ambos roles.
        """
        
        print(f"DEBUG: Creando notificación combinada para {supervisor_receptor.nombre}")
        
        Notificacion.objects.create(
            destinatario=supervisor_receptor,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        print(f"DEBUG: Notificación combinada creada para {supervisor_receptor.nombre}")
    
    @staticmethod
    def _enviar_email_supervisor_receptor(solicitud):
        """Envía email combinado cuando supervisor = receptor"""
        supervisor_receptor = solicitud.explorador_receptor
        
        subject = f"Solicitud de cambio de turno - Rol Doble - {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}"
        
        # Generar enlaces de aprobación
        enlaces = NotificacionService._generar_enlaces_aprobacion(solicitud)
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/solicitud_supervisor_receptor.html', {
            'solicitud': solicitud,
            'supervisor_receptor': supervisor_receptor,
            'enlaces': enlaces
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            NotificacionService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=solicitud.explorador_solicitante.email,
                recipient_list=[supervisor_receptor.email],
                html_message=html_message
            )
        except Exception as e:
            print(f"Error enviando email combinado: {e}")
    
    @staticmethod
    def _crear_notificacion_solicitante(solicitud):
        """Crea notificación para el solicitante (para que pueda ver el estado)"""
        titulo = f"Solicitud de cambio de turno enviada"
        mensaje = f"""
        Has enviado una solicitud de cambio de turno a {solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}
        para el día {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Pendiente de aprobación
        
        Podrás ver el estado de tu solicitud en la sección de notificaciones.
        """
        
        print(f"DEBUG: Creando notificación para solicitante {solicitud.explorador_solicitante.nombre}")
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        print(f"DEBUG: Notificación creada para solicitante {solicitud.explorador_solicitante.nombre}")
    
    @staticmethod
    def _enviar_email_supervisor(solicitud):
        """Envía email al supervisor"""
        supervisor = solicitud.explorador_solicitante.supervisor
        if not supervisor:
            return
        
        subject = f"Nueva solicitud de cambio de turno - {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}"
        
        # Generar enlaces de aprobación
        enlaces = NotificacionService._generar_enlaces_aprobacion(solicitud)
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/solicitud_supervisor.html', {
            'solicitud': solicitud,
            'supervisor': supervisor,
            'enlaces': enlaces
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            NotificacionService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=solicitud.explorador_solicitante.email,  # Email del usuario logueado
                recipient_list=[supervisor.email],
                html_message=html_message,
            )
        except Exception as e:
            print(f"Error enviando email al supervisor: {e}")
    
    @staticmethod
    def _enviar_email_receptor(solicitud):
        """Envía email al compañero receptor"""
        subject = f"Solicitud de cambio de turno recibida - {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}"
        
        # Generar enlaces de aprobación
        enlaces = NotificacionService._generar_enlaces_aprobacion(solicitud)
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/solicitud_receptor.html', {
            'solicitud': solicitud,
            'enlaces': enlaces
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            NotificacionService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=solicitud.explorador_solicitante.email,  # Email del usuario logueado
                recipient_list=[solicitud.explorador_receptor.email],
                html_message=html_message,
            )
        except Exception as e:
            print(f"Error enviando email al receptor: {e}")
    
    @staticmethod
    def _enviar_email_solicitante(solicitud):
        """Envía email de confirmación al solicitante"""
        try:
            subject = f"Confirmación de solicitud de cambio de turno"
            
            html_message = render_to_string('solicitudes/emails/confirmacion_solicitud.html', {
                'solicitud': solicitud,
                'empleado': solicitud.explorador_solicitante
            })
            
            plain_message = strip_tags(html_message)
            
            NotificacionService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=solicitud.explorador_solicitante.email,  # Email del usuario logueado
                recipient_list=[solicitud.explorador_solicitante.email],
                html_message=html_message,
            )
            
            print(f"DEBUG: Email de confirmación enviado a {solicitud.explorador_solicitante.email}")
            
        except Exception as e:
            print(f"ERROR enviando email de confirmación al solicitante: {e}")
            import traceback
            print(f"ERROR traceback: {traceback.format_exc()}")
    
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
    def obtener_notificaciones_no_leidas(empleado):
        """
        Obtiene las notificaciones no leídas de un empleado
        """
        return Notificacion.objects.filter(destinatario=empleado, leida=False).order_by('-fecha_creacion')

    @staticmethod
    def obtener_notificaciones(empleado):
        """
        Obtiene todas las notificaciones de un empleado
        """
        return Notificacion.objects.filter(destinatario=empleado).order_by('-fecha_creacion')

    @staticmethod
    def crear_notificacion_aprobacion(solicitud, aprobador, comentario_respuesta=None):
        """
        Crea notificación de aprobación para el empleado que solicitó
        """
        titulo = f"Solicitud Aprobada - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')} ha sido aprobada por {aprobador.nombre} {aprobador.apellido}."
        
        if comentario_respuesta:
            mensaje += f"\n\nComentario del supervisor: {comentario_respuesta}"
        
        # Notificación para el empleado que solicitó
        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='aprobacion',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        # Email al empleado que solicitó
        NotificacionService._enviar_email_aprobacion(solicitud, aprobador, comentario_respuesta)

    @staticmethod
    def crear_notificacion_rechazo(solicitud, rechazador, comentario_respuesta=None):
        """
        Crea notificación de rechazo para el empleado que solicitó
        """
        titulo = f"Solicitud Rechazada - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')} ha sido rechazada por {rechazador.nombre} {rechazador.apellido}."
        
        if comentario_respuesta:
            mensaje += f"\n\nComentario del supervisor: {comentario_respuesta}"
        
        # Notificación para el empleado que solicitó
        Notificacion.objects.create(
            destinatario=solicitud.explorador_solicitante,
            tipo='rechazo',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        # Email al empleado que solicitó
        NotificacionService._enviar_email_rechazo(solicitud, rechazador, comentario_respuesta)

    @staticmethod
    def _enviar_email_aprobacion(solicitud, aprobador, comentario_respuesta=None):
        """
        Envía email de aprobación al empleado que solicitó
        """
        subject = f"Solicitud Aprobada - {solicitud.tipo_cambio.nombre}"
        
        context = {
            'solicitud': solicitud,
            'aprobador': aprobador,
            'comentario_respuesta': comentario_respuesta,
        }
        
        html_message = render_to_string('solicitudes/emails/solicitud_aprobada.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=solicitud.explorador_solicitante.email,
            recipient_list=[solicitud.explorador_solicitante.email],
            html_message=html_message,
            fail_silently=False,
        )

    @staticmethod
    def _enviar_email_rechazo(solicitud, rechazador, comentario_respuesta=None):
        """
        Envía email de rechazo al empleado que solicitó
        """
        subject = f"Solicitud Rechazada - {solicitud.tipo_cambio.nombre}"
        
        context = {
            'solicitud': solicitud,
            'rechazador': rechazador,
            'comentario_respuesta': comentario_respuesta,
        }
        
        html_message = render_to_string('solicitudes/emails/solicitud_rechazada.html', context)
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=solicitud.explorador_solicitante.email,
            recipient_list=[solicitud.explorador_solicitante.email],
            html_message=html_message,
            fail_silently=False,
        ) 

    @staticmethod
    def crear_notificacion_aprobacion_supervisor(solicitud, supervisor, comentario_respuesta=None):
        """
        Crea notificación cuando el supervisor aprueba una solicitud
        """
        # Notificación para el solicitante
        titulo = f"Solicitud Aprobada por Supervisor - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')} ha sido aprobada por tu supervisor {supervisor.nombre} {supervisor.apellido}."
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
            mensaje_receptor = f"La solicitud de {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} para el {solicitud.fecha_cambio_turno.strftime('%d/%m/%Y')} ha sido aprobada por el supervisor. Tu aprobación está pendiente."
            
            Notificacion.objects.create(
                destinatario=solicitud.explorador_receptor,
                tipo='aprobacion',
                titulo=titulo_receptor,
                mensaje=mensaje_receptor,
                solicitud=solicitud
            )
        
        # Enviar email de aprobación
        NotificacionService._enviar_email_aprobacion_supervisor(solicitud, supervisor, comentario_respuesta)

    @staticmethod
    def crear_notificacion_aprobacion_receptor(solicitud, receptor, comentario_respuesta=None):
        """
        Crea notificación cuando el receptor aprueba una solicitud
        """
        # Notificación para el solicitante
        titulo = f"Solicitud Aprobada por Compañero - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')} ha sido aprobada por tu compañero {receptor.nombre} {receptor.apellido}."
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
            mensaje_supervisor = f"La solicitud de {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} para el {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')} ha sido aprobada por el compañero. Tu aprobación está pendiente."
            
            Notificacion.objects.create(
                destinatario=solicitud.explorador_solicitante.supervisor,
                tipo='aprobacion',
                titulo=titulo_supervisor,
                mensaje=mensaje_supervisor,
                solicitud=solicitud
            )
        
        # Enviar email de aprobación
        NotificacionService._enviar_email_aprobacion_receptor(solicitud, receptor, comentario_respuesta)

    @staticmethod
    def crear_notificacion_rechazo_supervisor(solicitud, supervisor, comentario_respuesta=None):
        """
        Crea notificación cuando el supervisor rechaza una solicitud
        """
        # Notificación para el solicitante
        titulo = f"Solicitud Rechazada por Supervisor - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')} ha sido rechazada por tu supervisor {supervisor.nombre} {supervisor.apellido}."
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
        mensaje_receptor = f"La solicitud de {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} para el {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')} ha sido rechazada por el supervisor."
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_receptor,
            tipo='rechazo',
            titulo=titulo_receptor,
            mensaje=mensaje_receptor,
            solicitud=solicitud
        )
        
        # Enviar email de rechazo
        NotificacionService._enviar_email_rechazo_supervisor(solicitud, supervisor, comentario_respuesta)

    @staticmethod
    def crear_notificacion_rechazo_receptor(solicitud, receptor, comentario_respuesta=None):
        """
        Crea notificación cuando el receptor rechaza una solicitud
        """
        # Notificación para el solicitante
        titulo = f"Solicitud Rechazada por Compañero - {solicitud.tipo_cambio.nombre}"
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')} ha sido rechazada por tu compañero {receptor.nombre} {receptor.apellido}."
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
            mensaje_supervisor = f"La solicitud de {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} para el {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')} ha sido rechazada por el compañero."
            
            Notificacion.objects.create(
                destinatario=solicitud.explorador_solicitante.supervisor,
                tipo='rechazo',
                titulo=titulo_supervisor,
                mensaje=mensaje_supervisor,
                solicitud=solicitud
            )
        
        # Enviar email de rechazo
        NotificacionService._enviar_email_rechazo_receptor(solicitud, receptor, comentario_respuesta) 

    @staticmethod
    def _enviar_email_aprobacion_supervisor(solicitud, supervisor, comentario_respuesta=None):
        """Envía email cuando el supervisor aprueba una solicitud"""
        subject = f"Solicitud Aprobada por Supervisor - {solicitud.tipo_cambio.nombre}"
        
        # Generar enlaces de aprobación
        enlaces = NotificacionService._generar_enlaces_aprobacion(solicitud)
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/aprobacion_supervisor.html', {
            'solicitud': solicitud,
            'supervisor': supervisor,
            'comentario_respuesta': comentario_respuesta,
            'enlaces': enlaces
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            NotificacionService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=supervisor.email,
                recipient_list=[solicitud.explorador_solicitante.email],
                html_message=html_message,
            )
        except Exception as e:
            print(f"Error enviando email de aprobación del supervisor: {e}")

    @staticmethod
    def _enviar_email_aprobacion_receptor(solicitud, receptor, comentario_respuesta=None):
        """Envía email cuando el receptor aprueba una solicitud"""
        subject = f"Solicitud Aprobada por Compañero - {solicitud.tipo_cambio.nombre}"
        
        # Generar enlaces de aprobación
        enlaces = NotificacionService._generar_enlaces_aprobacion(solicitud)
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/aprobacion_receptor.html', {
            'solicitud': solicitud,
            'receptor': receptor,
            'comentario_respuesta': comentario_respuesta,
            'enlaces': enlaces
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            NotificacionService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=receptor.email,
                recipient_list=[solicitud.explorador_solicitante.email],
                html_message=html_message,
            )
        except Exception as e:
            print(f"Error enviando email de aprobación del receptor: {e}")

    @staticmethod
    def _enviar_email_rechazo_supervisor(solicitud, supervisor, comentario_respuesta=None):
        """Envía email cuando el supervisor rechaza una solicitud"""
        subject = f"Solicitud Rechazada por Supervisor - {solicitud.tipo_cambio.nombre}"
        
        # Generar enlaces de aprobación
        enlaces = NotificacionService._generar_enlaces_aprobacion(solicitud)
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/rechazo_supervisor.html', {
            'solicitud': solicitud,
            'supervisor': supervisor,
            'comentario_respuesta': comentario_respuesta,
            'enlaces': enlaces
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            NotificacionService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=supervisor.email,
                recipient_list=[solicitud.explorador_solicitante.email],
                html_message=html_message,
            )
        except Exception as e:
            print(f"Error enviando email de rechazo del supervisor: {e}")

    @staticmethod
    def _enviar_email_rechazo_receptor(solicitud, receptor, comentario_respuesta=None):
        """Envía email cuando el receptor rechaza una solicitud"""
        subject = f"Solicitud Rechazada por Compañero - {solicitud.tipo_cambio.nombre}"
        
        # Generar enlaces de aprobación
        enlaces = NotificacionService._generar_enlaces_aprobacion(solicitud)
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/rechazo_receptor.html', {
            'solicitud': solicitud,
            'receptor': receptor,
            'comentario_respuesta': comentario_respuesta,
            'enlaces': enlaces
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            NotificacionService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=receptor.email,
                recipient_list=[solicitud.explorador_solicitante.email],
                html_message=html_message,
            )
        except Exception as e:
            print(f"Error enviando email de rechazo del receptor: {e}") 

    @staticmethod
    def _verificar_token(solicitud, token, tipo):
        """Verifica que el token sea válido"""
        # Crear token esperado
        if tipo == 'supervisor':
            supervisor = solicitud.explorador_solicitante.supervisor
            if not supervisor:
                return False
            data = f"{solicitud.id}_{supervisor.id}_{tipo}"
        else:  # receptor
            data = f"{solicitud.id}_{solicitud.explorador_receptor.id}_{tipo}"
        
        expected_token = hmac.new(
            b'secret_key_change_this',  # Cambiar en producción
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(token, expected_token)
    
    @staticmethod
    def crear_notificacion_cancelacion(solicitud):
        """Crea notificación de cancelación para el receptor"""
        titulo = f"Solicitud de cambio de turno cancelada"
        mensaje = f"""
        {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} 
        ha cancelado la solicitud de cambio de turno para el día {NotificacionService._convertir_fecha(solicitud.fecha_cambio_turno).strftime('%d/%m/%Y')}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Cancelada
        
        Ya no necesitas aprobar o rechazar esta solicitud.
        """
        
        print(f"DEBUG: Creando notificación de cancelación para receptor {solicitud.explorador_receptor.nombre}")
        
        Notificacion.objects.create(
            destinatario=solicitud.explorador_receptor,
            tipo='solicitud_cambio',
            titulo=titulo,
            mensaje=mensaje,
            solicitud=solicitud
        )
        
        print(f"DEBUG: Notificación de cancelación creada para receptor {solicitud.explorador_receptor.nombre}")
        
        # Enviar email de cancelación
        NotificacionService._enviar_email_cancelacion(solicitud)
    
    @staticmethod
    def _enviar_email_cancelacion(solicitud):
        """Envía email de cancelación al receptor"""
        subject = f"Solicitud de cambio de turno cancelada - {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}"
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/cancelacion_solicitud.html', {
            'solicitud': solicitud
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            NotificacionService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=solicitud.explorador_solicitante.email,
                recipient_list=[solicitud.explorador_receptor.email],
                html_message=html_message
            )
        except Exception as e:
            print(f"Error enviando email de cancelación: {e}") 