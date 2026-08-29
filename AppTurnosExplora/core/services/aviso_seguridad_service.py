"""Aviso por correo de que la contraseña de una cuenta acaba de cambiar.

POR QUÉ EXISTE
--------------
Es la única forma de que el titular se entere de que le han robado la cuenta.
Quien roba una contraseña lo primero que hace es cambiarla; si ese cambio no
avisa a nadie, el dueño legítimo solo lo descubre cuando ya no puede entrar, y
para entonces no sabe desde cuándo ni qué se hizo con su sesión.

Este correo SÍ pasa por `EmailService` -> `EmailOutbox`, al contrario que el
enlace de recuperación (ver `core.login.views.PasswordResetSWALPView`). La razón
es la inversa: aquí nadie está esperando delante de la pantalla, así que lo que
importa no es la inmediatez sino que el aviso **no se pierda** si el SMTP está
caído en ese momento. El outbox lo reintenta; `send_mail` no.
"""
import logging

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

logger = logging.getLogger('core.seguridad')

ORIGEN_CAMBIO = 'cambio'
ORIGEN_RESET = 'reset'


def notificar_cambio_password(user, origen, ip=None):
    """Encola el aviso. Nunca lanza: un fallo aquí no puede tumbar el cambio.

    El cambio de contraseña ya está guardado cuando se llama a esto. Si el
    correo fallara y la excepción subiera, el usuario vería un error 500 después
    de que su contraseña YA hubiera cambiado — el peor de los desenlaces, porque
    no sabría con cuál de las dos entrar.
    """
    email = (getattr(user, 'email', '') or '').strip()
    if not email:
        # Cuenta sin correo: no hay a dónde avisar. Se deja constancia porque es
        # justo el agujero que describe el manual de despliegue.
        logger.info('AVISO_PASSWORD_SIN_DESTINO origen=%s', origen)
        return False

    try:
        contexto = {
            'nombre': user.get_full_name() or user.username,
            'origen': origen,
            'fecha': timezone.localtime(),
            'ip': ip or 'desconocida',
            'site_url': settings.SITE_URL,
        }
        html = render_to_string('registration/aviso_password_cambiada.html', contexto)

        from solicitudes.services.email_service import EmailService

        EmailService._enviar_email_desde_usuario(
            subject='SWALP · Tu contraseña ha cambiado',
            message=strip_tags(html),
            from_email=None,
            recipient_list=[email],
            html_message=html,
        )
        logger.info('AVISO_PASSWORD_ENCOLADO origen=%s user_id=%s', origen, user.pk)
        return True
    except Exception:
        logger.exception('AVISO_PASSWORD_FALLIDO origen=%s user_id=%s', origen, user.pk)
        return False
