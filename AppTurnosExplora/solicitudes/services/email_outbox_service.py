"""
EmailOutboxService: entrega fiable de correos mediante el patrón *outbox*.

Separa ENCOLAR (transaccional, junto al cambio de negocio) de ENVIAR (fuera de la
transacción, reintentable). Ver la docstring de `EmailOutbox` para el problema que
resuelve.

GARANTÍA REAL: *al menos una vez* por fila encolada, y *como máximo una vez* por
`clave_idempotencia` a la hora de ENCOLAR. No es exactamente-una-vez: si el proceso
muere justo después de que el SMTP aceptó el mensaje pero antes de marcar la fila como
enviada, el reintento reenviará ese correo. Es el compromiso clásico e inevitable sin
transacciones distribuidas con el servidor de correo, y para este dominio es el lado
correcto: un supervisor prefiere un aviso repetido a no enterarse de una solicitud.
"""
from __future__ import annotations

import logging

from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.utils import timezone

from solicitudes.models import EmailOutbox

logger = logging.getLogger(__name__)

# Ventana de arriendo (*lease*) del primer intento y base del backoff exponencial.
# Un intento que se queda en 'enviando' más que su ventana se considera abandonado
# (proceso muerto a media entrega) y otro worker puede reclamarlo.
_BACKOFF_MINUTOS = [1, 5, 15, 60, 180]


def _proximo_intento(intentos: int):
    """Momento en que la fila vuelve a estar disponible tras el intento número `intentos`."""
    idx = min(max(intentos - 1, 0), len(_BACKOFF_MINUTOS) - 1)
    return timezone.now() + timezone.timedelta(minutes=_BACKOFF_MINUTOS[idx])


class EmailOutboxService:

    # ------------------------------------------------------------------
    # Encolar
    # ------------------------------------------------------------------

    @staticmethod
    def encolar(asunto, cuerpo_texto, remitente, destinatarios,
                cuerpo_html='', reply_to='', clave_idempotencia=None) -> EmailOutbox | None:
        """
        Escribe el correo en la cola. Debe llamarse DENTRO de la transacción del cambio
        de negocio: esa atomicidad es justamente la garantía del patrón.

        Con `clave_idempotencia`, un segundo intento de encolar el mismo correo lógico
        no crea otra fila (el `unique` del modelo lo impide incluso entre procesos
        concurrentes) y devuelve la existente.
        """
        if clave_idempotencia:
            fila, creada = EmailOutbox.objects.get_or_create(
                clave_idempotencia=clave_idempotencia,
                defaults={
                    'asunto': asunto,
                    'cuerpo_texto': cuerpo_texto,
                    'cuerpo_html': cuerpo_html or '',
                    'remitente': remitente,
                    'reply_to': reply_to or '',
                    'destinatarios': destinatarios,
                },
            )
            if not creada:
                logger.info("Outbox: correo ya encolado con clave %s (fila %s), no se duplica.",
                            clave_idempotencia, fila.id)
            return fila

        return EmailOutbox.objects.create(
            asunto=asunto,
            cuerpo_texto=cuerpo_texto,
            cuerpo_html=cuerpo_html or '',
            remitente=remitente,
            reply_to=reply_to or '',
            destinatarios=destinatarios,
        )

    # ------------------------------------------------------------------
    # Enviar
    # ------------------------------------------------------------------

    @staticmethod
    def _reclamar(fila_id: int) -> EmailOutbox | None:
        """
        Toma la fila en exclusiva mediante un UPDATE condicional.

        Un solo statement `UPDATE ... WHERE estado IN (...) AND disponible_en <= now`
        es atómico en cualquier motor: si dos workers lo lanzan a la vez, solo uno ve
        `rowcount == 1`. Se prefiere a `select_for_update(skip_locked=True)` porque no
        depende de la versión de MySQL ni mantiene un lock abierto durante el SMTP.

        Incluye 'enviando' en el filtro a propósito: una fila que quedó en ese estado con
        su ventana ya vencida es un intento abandonado (proceso muerto a media entrega),
        y debe poder reclamarse — si no, se quedaría atascada para siempre.
        """
        ahora = timezone.now()
        fila = EmailOutbox.objects.filter(pk=fila_id).first()
        if fila is None:
            return None

        reclamadas = EmailOutbox.objects.filter(
            pk=fila_id,
            estado__in=[EmailOutbox.ESTADO_PENDIENTE, EmailOutbox.ESTADO_ENVIANDO],
            disponible_en__lte=ahora,
            intentos__lt=EmailOutbox.MAX_INTENTOS,
        ).update(
            estado=EmailOutbox.ESTADO_ENVIANDO,
            intentos=fila.intentos + 1,
            disponible_en=_proximo_intento(fila.intentos + 1),
        )
        if reclamadas != 1:
            return None
        fila.refresh_from_db()
        return fila

    @staticmethod
    def intentar_enviar(fila_id: int) -> bool:
        """
        Envía una fila concreta si logra reclamarla. Devuelve True solo si el correo salió.

        Nunca lanza: un fallo de SMTP deja la fila lista para el siguiente reintento, y
        que un envío falle no debe tumbar al proceso que lo intentaba.
        """
        fila = EmailOutboxService._reclamar(fila_id)
        if fila is None:
            return False  # otro worker la tiene, ya se envió, o aún no toca reintentar

        try:
            mensaje = EmailMultiAlternatives(
                subject=fila.asunto,
                body=fila.cuerpo_texto,
                from_email=fila.remitente,
                to=list(fila.destinatarios or []),
                reply_to=[fila.reply_to] if fila.reply_to else None,
                connection=get_connection(),
            )
            if fila.cuerpo_html:
                mensaje.attach_alternative(fila.cuerpo_html, "text/html")
            mensaje.send()
        except Exception as exc:
            agotado = fila.intentos >= EmailOutbox.MAX_INTENTOS
            EmailOutbox.objects.filter(pk=fila.id).update(
                estado=EmailOutbox.ESTADO_FALLIDO if agotado else EmailOutbox.ESTADO_PENDIENTE,
                ultimo_error=str(exc)[:2000],
            )
            log = logger.error if agotado else logger.warning
            log("Outbox: fallo enviando la fila %s (intento %s/%s): %s",
                fila.id, fila.intentos, EmailOutbox.MAX_INTENTOS, exc)
            return False

        EmailOutbox.objects.filter(pk=fila.id).update(
            estado=EmailOutbox.ESTADO_ENVIADO,
            enviado_en=timezone.now(),
            ultimo_error='',
        )
        logger.info("Outbox: fila %s enviada a %s.", fila.id, fila.destinatarios)
        return True

    @staticmethod
    def procesar_pendientes(limite: int = 50) -> dict:
        """
        Barrido del worker: intenta todas las filas que ya tocan.

        Es la RED DE SEGURIDAD del patrón — lo que convierte "se perdió el correo" en
        "se envía con retraso". El camino normal sigue siendo el envío inmediato tras el
        commit; aquí solo caen los que ese camino no logró entregar.
        """
        ahora = timezone.now()
        ids = list(EmailOutbox.objects.filter(
            estado__in=[EmailOutbox.ESTADO_PENDIENTE, EmailOutbox.ESTADO_ENVIANDO],
            disponible_en__lte=ahora,
            intentos__lt=EmailOutbox.MAX_INTENTOS,
        ).order_by('creado_en').values_list('id', flat=True)[:limite])

        enviados = sum(1 for fila_id in ids if EmailOutboxService.intentar_enviar(fila_id))
        return {'candidatos': len(ids), 'enviados': enviados, 'fallidos': len(ids) - enviados}

    @staticmethod
    def enviar_tras_commit(fila_id: int) -> None:
        """
        Camino rápido: intenta el envío en cuanto la transacción commita, en un hilo,
        para no bloquear la respuesta con el handshake SMTP (~20 s).

        Si este intento no ocurre (proceso reiniciado) o falla, la fila sigue en la cola
        y `procesar_email_outbox` la recogerá. Por eso aquí se puede fallar sin drama:
        la garantía de entrega no depende de este hilo, solo la latencia.
        """
        import threading

        def _lanzar():
            hilo = threading.Thread(
                target=EmailOutboxService.intentar_enviar, args=(fila_id,), daemon=True)
            hilo.start()

        transaction.on_commit(_lanzar)
