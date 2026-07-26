"""EmailService: composicion y envio de correos de solicitudes.

Extraido de NotificacionService para separar la responsabilidad de ENVIAR correos
(plantillas, tokens, backend SMTP) de la de crear registros de Notificacion.
Dependencia en un solo sentido: NotificacionService -> EmailService.

Nota: _configurar_email_backend y _verificar_token se conservan tal cual (sin callers
actuales) para no cambiar comportamiento; candidatos a limpieza posterior.
"""
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail.backends.smtp import EmailBackend
from solicitudes.models import SolicitudCambio
import hashlib
import hmac
import logging
import threading

logger = logging.getLogger(__name__)


class EmailService:
    @staticmethod
    def _cargar_solicitud_completa(solicitud):
        """
        Carga la solicitud con todas las relaciones necesarias para los emails
        Maneja casos donde algunas relaciones pueden no existir (ej: doblada)
        """
        try:
            # Intentar cargar con todas las relaciones
            solicitud_completa = SolicitudCambio.objects.select_related(
                'explorador_solicitante',
                'explorador_receptor', 
                'explorador_solicitante__user',
                'explorador_receptor__user',
                'tipo_cambio',
                'cambio_permanente',
                'doblada'  # Puede ser None si aún no se ha creado
            ).prefetch_related(
                'cambio_permanente'
            ).get(id=solicitud.id)
            
            return solicitud_completa
        except SolicitudCambio.DoesNotExist:
            logger.error(f"Solicitud {solicitud.id} no encontrada al cargar relaciones")
            raise
        except Exception as e:
            logger.error(f"Error cargando solicitud completa {solicitud.id}: {e}")
            # Fallback: retornar la solicitud original con relaciones básicas
            return solicitud
    
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
    def _enviar_seguro(func):
        """Ejecuta el envío capturando cualquier error (para el hilo en segundo plano)."""
        try:
            func()
        except Exception:
            logger.exception("❌ Error enviando email en segundo plano")

    @staticmethod
    def _enviar_email_desde_usuario(subject, message, from_email, recipient_list, html_message=None):
        """Envía un correo desde el remitente fijo (DEFAULT_FROM_EMAIL), con la
        persona en Reply-To.

        En producción (EMAIL_SEND_ASYNC) el envío se hace fuera del request:
        tras el commit y en un hilo, para no bloquear la respuesta ~20 s con los
        handshakes SMTP. En desarrollo/tests el envío es síncrono.
        """
        try:
            # Validaciones antes de enviar
            if not subject or not subject.strip():
                logger.error("No se puede enviar email: subject vacío")
                return False

            if not recipient_list or not isinstance(recipient_list, list) or len(recipient_list) == 0:
                logger.error(f"No se puede enviar email: recipient_list inválido: {recipient_list}")
                return False

            # Filtrar emails None o vacíos
            recipient_list_validos = [email for email in recipient_list if email and email.strip()]
            if not recipient_list_validos:
                logger.error(f"No se puede enviar email: todos los destinatarios son inválidos: {recipient_list}")
                return False

            # Enviar SIEMPRE desde el remitente fijo; la persona (from_email
            # recibido) va en Reply-To para que las respuestas le lleguen.
            remitente = settings.DEFAULT_FROM_EMAIL
            if not remitente:
                logger.error("No se puede enviar email: DEFAULT_FROM_EMAIL está vacío")
                return False
            reply_to = [from_email] if from_email and from_email.strip() else None

            logger.info(f"Encolando email: subject='{subject}', from='{remitente}', reply_to={reply_to}, to={recipient_list_validos}")

            def _construir_y_enviar():
                # get_connection() respeta EMAIL_BACKEND y EMAIL_TIMEOUT.
                email = EmailMultiAlternatives(
                    subject=subject,
                    body=message,
                    from_email=remitente,
                    to=recipient_list_validos,
                    reply_to=reply_to,
                    connection=get_connection(),
                )
                if html_message:
                    email.attach_alternative(html_message, "text/html")
                email.send()
                logger.info(f"✅ Email enviado desde {remitente} a {recipient_list_validos}")

            if getattr(settings, 'EMAIL_SEND_ASYNC', False):
                # Fuera del request: tras el commit, en un hilo (no bloquea la respuesta).
                # Las notificaciones in-app siguen siendo síncronas (instantáneas).
                transaction.on_commit(
                    lambda: threading.Thread(
                        target=EmailService._enviar_seguro,
                        args=(_construir_y_enviar,),
                        daemon=True,
                    ).start()
                )
            else:
                _construir_y_enviar()
            return True

        except Exception as e:
            logger.exception(f"❌ Error enviando email: {e}")
            logger.error(f"Detalles: subject='{subject}', from='{from_email}', to={recipient_list}")
            return False
    
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
            token_supervisor = EmailService._generar_token(solicitud.id, supervisor.id, 'supervisor')
            enlaces['supervisor'] = {
                'aprobar': f"{settings.SITE_URL}/solicitudes/aprobar-email/{solicitud.id}/{token_supervisor}/",
                'rechazar': f"{settings.SITE_URL}/solicitudes/rechazar-email/{solicitud.id}/{token_supervisor}/"
            }
        
        # Enlaces para receptor
        token_receptor = EmailService._generar_token(solicitud.id, solicitud.explorador_receptor.id, 'receptor')
        enlaces['receptor'] = {
            'aprobar': f"{settings.SITE_URL}/solicitudes/aprobar-receptor-email/{solicitud.id}/{token_receptor}/",
            'rechazar': f"{settings.SITE_URL}/solicitudes/rechazar-receptor-email/{solicitud.id}/{token_receptor}/"
        }
        
        return enlaces
    
    @staticmethod
    def _enviar_email_supervisor_receptor(solicitud):
        """Envía email combinado cuando supervisor = receptor"""
        try:
            # Cargar solicitud con relaciones completas
            solicitud_completa = EmailService._cargar_solicitud_completa(solicitud)
            supervisor_receptor = solicitud_completa.explorador_receptor
            
            # Validar email del receptor
            if not supervisor_receptor.email or not supervisor_receptor.email.strip():
                logger.error(f"No se puede enviar email: receptor {supervisor_receptor.nombre} no tiene email válido")
                return False
            
            subject = f"Solicitud de cambio de turno - Rol Doble - {solicitud_completa.explorador_solicitante.nombre} {solicitud_completa.explorador_solicitante.apellido}"
            
            # Generar enlaces de aprobación
            enlaces = EmailService._generar_enlaces_aprobacion(solicitud_completa)
            
            # Renderizar template HTML
            try:
                html_message = render_to_string('solicitudes/emails/solicitud_supervisor_receptor.html', {
                    'solicitud': solicitud_completa,
                    'supervisor_receptor': supervisor_receptor,
                    'enlaces': enlaces,
                    'site_url': settings.SITE_URL
                })
            except Exception as e:
                logger.exception(f"Error renderizando template de email supervisor-receptor: {e}")
                return False
            
            # Versión texto plano
            plain_message = strip_tags(html_message)
            
            from_email = solicitud_completa.explorador_solicitante.email if solicitud_completa.explorador_solicitante.email else settings.DEFAULT_FROM_EMAIL
            
            return EmailService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=from_email,
                recipient_list=[supervisor_receptor.email],
                html_message=html_message
            )
        except Exception as e:
            logger.exception(f"Error en _enviar_email_supervisor_receptor: {e}")
            return False
    
    @staticmethod
    def _enviar_email_supervisor(solicitud):
        """Envía email al supervisor"""
        try:
            # Cargar solicitud con relaciones completas
            solicitud_completa = EmailService._cargar_solicitud_completa(solicitud)
            supervisor = solicitud_completa.explorador_solicitante.supervisor
            if not supervisor:
                logger.warning("No hay supervisor asignado, no se enviará email")
                return False
            
            # Validar email del supervisor
            if not supervisor.email or not supervisor.email.strip():
                logger.error(f"No se puede enviar email: supervisor {supervisor.nombre} no tiene email válido")
                return False
            
            subject = f"Nueva solicitud de cambio de turno - {solicitud_completa.explorador_solicitante.nombre} {solicitud_completa.explorador_solicitante.apellido}"
            
            # Generar enlaces de aprobación
            enlaces = EmailService._generar_enlaces_aprobacion(solicitud_completa)
            
            # Renderizar template HTML
            try:
                html_message = render_to_string('solicitudes/emails/solicitud_supervisor.html', {
                    'solicitud': solicitud_completa,
                    'supervisor': supervisor,
                    'enlaces': enlaces,
                    'site_url': settings.SITE_URL
                })
            except Exception as e:
                logger.exception(f"Error renderizando template de email supervisor: {e}")
                return False
            
            # Versión texto plano
            plain_message = strip_tags(html_message)
            
            from_email = solicitud_completa.explorador_solicitante.email if solicitud_completa.explorador_solicitante.email else settings.DEFAULT_FROM_EMAIL
            
            return EmailService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=from_email,
                recipient_list=[supervisor.email],
                html_message=html_message,
            )
        except Exception as e:
            logger.exception(f"Error en _enviar_email_supervisor: {e}")
            return False
    
    @staticmethod
    def _enviar_email_receptor(solicitud):
        """Envía email al compañero receptor"""
        try:
            # Cargar solicitud con relaciones completas
            solicitud_completa = EmailService._cargar_solicitud_completa(solicitud)
            
            # Validar email del receptor
            if not solicitud_completa.explorador_receptor.email or not solicitud_completa.explorador_receptor.email.strip():
                logger.error(f"No se puede enviar email: receptor {solicitud_completa.explorador_receptor.nombre} no tiene email válido")
                return False
            
            subject = f"Solicitud de cambio de turno recibida - {solicitud_completa.explorador_solicitante.nombre} {solicitud_completa.explorador_solicitante.apellido}"
            
            # Generar enlaces de aprobación
            enlaces = EmailService._generar_enlaces_aprobacion(solicitud_completa)
            
            # Renderizar template HTML
            try:
                html_message = render_to_string('solicitudes/emails/solicitud_receptor.html', {
                    'solicitud': solicitud_completa,
                    'enlaces': enlaces,
                    'site_url': settings.SITE_URL
                })
            except Exception as e:
                logger.exception(f"Error renderizando template de email receptor: {e}")
                return False
            
            # Versión texto plano
            plain_message = strip_tags(html_message)
            
            from_email = solicitud_completa.explorador_solicitante.email if solicitud_completa.explorador_solicitante.email else settings.DEFAULT_FROM_EMAIL
            
            return EmailService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=from_email,
                recipient_list=[solicitud_completa.explorador_receptor.email],
                html_message=html_message,
            )
        except Exception as e:
            logger.exception(f"Error en _enviar_email_receptor: {e}")
            return False
    
    @staticmethod
    def _enviar_email_solicitante(solicitud):
        """Envía email de confirmación al solicitante"""
        try:
            # Cargar solicitud con relaciones completas
            solicitud_completa = EmailService._cargar_solicitud_completa(solicitud)
            
            # Validar email del solicitante
            if not solicitud_completa.explorador_solicitante.email or not solicitud_completa.explorador_solicitante.email.strip():
                logger.error(f"No se puede enviar email: solicitante {solicitud_completa.explorador_solicitante.nombre} no tiene email válido")
                return False
            
            subject = f"Confirmación de solicitud de cambio de turno"
            
            try:
                html_message = render_to_string('solicitudes/emails/confirmacion_solicitud.html', {
                    'solicitud': solicitud_completa,
                    'empleado': solicitud_completa.explorador_solicitante
                })
            except Exception as e:
                logger.exception(f"Error renderizando template de email confirmación: {e}")
                return False
            
            plain_message = strip_tags(html_message)
            
            from_email = solicitud_completa.explorador_solicitante.email if solicitud_completa.explorador_solicitante.email else settings.DEFAULT_FROM_EMAIL
            
            return EmailService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=from_email,
                recipient_list=[solicitud_completa.explorador_solicitante.email],
                html_message=html_message,
            )
            
        except Exception as e:
            logger.exception(f"Error en _enviar_email_solicitante: {e}")
            return False
    
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

        EmailService._enviar_email_desde_usuario(
            subject=subject,
            message=plain_message,
            from_email=solicitud.explorador_solicitante.email,
            recipient_list=[solicitud.explorador_solicitante.email],
            html_message=html_message,
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

        EmailService._enviar_email_desde_usuario(
            subject=subject,
            message=plain_message,
            from_email=solicitud.explorador_solicitante.email,
            recipient_list=[solicitud.explorador_solicitante.email],
            html_message=html_message,
        )

    @staticmethod
    def _enviar_email_aprobacion_supervisor(solicitud, supervisor, comentario_respuesta=None):
        """Envía email cuando el supervisor aprueba una solicitud"""
        subject = f"Solicitud Aprobada por Supervisor - {solicitud.tipo_cambio.nombre}"
        
        # Generar enlaces de aprobación
        enlaces = EmailService._generar_enlaces_aprobacion(solicitud)
        
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
            EmailService._enviar_email_desde_usuario(
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
        enlaces = EmailService._generar_enlaces_aprobacion(solicitud)
        
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
            EmailService._enviar_email_desde_usuario(
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
        enlaces = EmailService._generar_enlaces_aprobacion(solicitud)
        
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
            EmailService._enviar_email_desde_usuario(
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
        enlaces = EmailService._generar_enlaces_aprobacion(solicitud)
        
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
            EmailService._enviar_email_desde_usuario(
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
    def _enviar_email_cancelacion(solicitud):
        """Envía email de cancelación al receptor"""
        subject = f"Solicitud de cambio de turno cancelada - {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}"
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/cancelacion_solicitud.html', {
            'solicitud': solicitud,
            'site_url': settings.SITE_URL
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            EmailService._enviar_email_desde_usuario(
                subject=subject,
                message=plain_message,
                from_email=solicitud.explorador_solicitante.email,
                recipient_list=[solicitud.explorador_receptor.email],
                html_message=html_message
            )
        except Exception as e:
            print(f"Error enviando email de cancelación: {e}") 