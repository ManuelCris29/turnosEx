from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from solicitudes.models import Notificacion, SolicitudCambio
from empleados.models import Empleado
from datetime import datetime
from django.utils import timezone

class NotificacionService:
    @staticmethod
    def crear_notificacion_solicitud(solicitud):
        """
        Crea notificaciones para el supervisor y el compañero receptor
        """
        # Notificación para el supervisor
        if solicitud.explorador_solicitante.supervisor:
            NotificacionService._crear_notificacion_supervisor(solicitud)
        
        # Notificación para el compañero receptor
        NotificacionService._crear_notificacion_receptor(solicitud)
        
        # Enviar emails
        NotificacionService._enviar_email_supervisor(solicitud)
        NotificacionService._enviar_email_receptor(solicitud)
    
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
        para el día {solicitud.fecha_solicitud.date()}.
        
        Tipo de solicitud: {solicitud.tipo_cambio.nombre}
        Estado: Pendiente de aprobación
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
        titulo = f"Solicitud de cambio de turno recibida"
        mensaje = f"""
        {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido} 
        te ha enviado una solicitud de cambio de turno para el día {solicitud.fecha_solicitud.date()}.
        
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
    def _enviar_email_supervisor(solicitud):
        """Envía email al supervisor"""
        supervisor = solicitud.explorador_solicitante.supervisor
        if not supervisor:
            return
        
        subject = f"Nueva solicitud de cambio de turno - {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}"
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/solicitud_supervisor.html', {
            'solicitud': solicitud,
            'supervisor': supervisor
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=solicitud.explorador_solicitante.email,  # Email del usuario logueado
                recipient_list=[supervisor.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            print(f"Error enviando email al supervisor: {e}")
    
    @staticmethod
    def _enviar_email_receptor(solicitud):
        """Envía email al compañero receptor"""
        subject = f"Solicitud de cambio de turno recibida - {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}"
        
        # Renderizar template HTML
        html_message = render_to_string('solicitudes/emails/solicitud_receptor.html', {
            'solicitud': solicitud
        })
        
        # Versión texto plano
        plain_message = strip_tags(html_message)
        
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=solicitud.explorador_solicitante.email,  # Email del usuario logueado
                recipient_list=[solicitud.explorador_receptor.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Exception as e:
            print(f"Error enviando email al receptor: {e}")
    
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
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {solicitud.fecha_solicitud.strftime('%d/%m/%Y')} ha sido aprobada por {aprobador.nombre} {aprobador.apellido}."
        
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
        mensaje = f"Tu solicitud de {solicitud.tipo_cambio.nombre} para el {solicitud.fecha_solicitud.strftime('%d/%m/%Y')} ha sido rechazada por {rechazador.nombre} {rechazador.apellido}."
        
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