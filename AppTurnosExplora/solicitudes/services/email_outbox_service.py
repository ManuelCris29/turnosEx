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

UNA CONEXIÓN SMTP POR LOTE, NO POR CORREO
-----------------------------------------
Casi nada en esta aplicación envía UN correo suelto: crear una solicitud dispara tres
(supervisor, receptor y solicitante), y los flujos que crean varias solicitudes a la vez
—cobertura con 2 compañeros, doblada permanente con N— multiplican esa cifra. Cada envío
abría su propia conexión, y el coste real de un correo no es el mensaje sino el saludo:
handshake TLS + AUTH, ~2 s medidos contra Gmail, frente a milisegundos de enviar por un
canal ya abierto.

Por eso el envío se hace SIEMPRE en lote (`enviar_lote`) sobre una conexión abierta a
mano: `send_messages` de Django solo cierra la conexión si fue él quien la abrió, así que
abrirla explícitamente antes del bucle es lo que evita un saludo por mensaje. Un correo
suelto es simplemente un lote de uno.

Efecto secundario deseable: si el SMTP no responde, el fallo ocurre al ABRIR, antes de
reclamar ninguna fila. Ninguna quema un intento por una caída que no es culpa suya.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from email.mime.image import MIMEImage
from functools import lru_cache
from pathlib import Path
from threading import local

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.utils import timezone

from solicitudes.models import EmailOutbox

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------- logo incrustado
# El <img> de templates/emails/base_email.html apunta a `cid:logo-swalp` en vez de a
# una URL: una imagen enlazada NO se ve. Con SITE_URL=http://127.0.0.1:8000 el cliente
# de correo resuelve 127.0.0.1 contra la máquina de quien lee, y aun con el dominio
# público Gmail y Outlook bloquean las remotas hasta que el destinatario da permiso.
# Incrustada se ve siempre, sin pedir nada.
_CID_LOGO = 'logo-swalp'
_RUTA_LOGO = Path(settings.BASE_DIR) / 'static' / 'img' / 'logo-explora-email.png'


@lru_cache(maxsize=1)
def _bytes_del_logo() -> bytes | None:
    """Lee el PNG una sola vez por proceso. `None` si no está: un logo que falta no
    puede impedir que salga el correo."""
    try:
        return _RUTA_LOGO.read_bytes()
    except OSError:
        logger.warning("Outbox: no se pudo leer el logo %s; los correos saldrán sin él.",
                       _RUTA_LOGO)
        return None


def _incrustar_logo(mensaje, cuerpo_html: str) -> None:
    """Engancha el logo como parte `related` si el HTML lo referencia por su cid."""
    if f'cid:{_CID_LOGO}' not in cuerpo_html:
        return
    datos = _bytes_del_logo()
    if datos is None:
        return
    # multipart/related envolviendo al multipart/alternative: es lo que hace que el
    # cliente resuelva el cid contra esta parte y no lo trate como adjunto suelto.
    mensaje.mixed_subtype = 'related'
    imagen = MIMEImage(datos)
    imagen.add_header('Content-ID', f'<{_CID_LOGO}>')
    imagen.add_header('Content-Disposition', 'inline', filename='logo-explora.png')
    mensaje.attach(imagen)


# Ventana de arriendo (*lease*) del primer intento y base del backoff exponencial.
# Un intento que se queda en 'enviando' más que su ventana se considera abandonado
# (proceso muerto a media entrega) y otro worker puede reclamarlo.
_BACKOFF_MINUTOS = [1, 5, 15, 60, 180]

# Resultado de un intento individual. 'omitido' NO es un fallo: significa que la fila no
# se pudo reclamar (otro worker la tiene, ya se envió, o aún no toca reintentarla), y por
# tanto no dice nada sobre el estado de la conexión.
_ENVIADO, _FALLIDO, _OMITIDO = 'enviado', 'fallido', 'omitido'

# Grupo de envío abierto en el hilo actual (ver `envio_agrupado`). Es thread-local porque
# cada petición se atiende en su propio hilo y los grupos de dos peticiones simultáneas no
# pueden mezclarse.
_grupos = local()


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
    def _intentar(fila_id: int, conexion=None) -> str:
        """
        Envía una fila concreta si logra reclamarla. Devuelve `_ENVIADO`, `_FALLIDO` o
        `_OMITIDO` (no se pudo reclamar).

        Distinguir 'fallido' de 'omitido' es lo que permite a `enviar_lote` saber si la
        conexión compartida quedó tocada: una fila omitida no la ha usado siquiera.

        Con `conexion` se reutiliza el canal ya abierto por el lote; sin ella se abre uno
        propio para este único mensaje. En ningún caso se cierra aquí: la cierra quien la
        abrió (`send_messages` de Django solo cierra la que él mismo abre).

        Nunca lanza: un fallo de SMTP deja la fila lista para el siguiente reintento, y
        que un envío falle no debe tumbar al proceso que lo intentaba.
        """
        fila = EmailOutboxService._reclamar(fila_id)
        if fila is None:
            return _OMITIDO  # otro worker la tiene, ya se envió, o aún no toca reintentar

        try:
            mensaje = EmailMultiAlternatives(
                subject=fila.asunto,
                body=fila.cuerpo_texto,
                from_email=fila.remitente,
                to=list(fila.destinatarios or []),
                reply_to=[fila.reply_to] if fila.reply_to else None,
                connection=conexion or get_connection(),
            )
            if fila.cuerpo_html:
                mensaje.attach_alternative(fila.cuerpo_html, "text/html")
                _incrustar_logo(mensaje, fila.cuerpo_html)
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
            return _FALLIDO

        EmailOutbox.objects.filter(pk=fila.id).update(
            estado=EmailOutbox.ESTADO_ENVIADO,
            enviado_en=timezone.now(),
            ultimo_error='',
        )
        logger.info("Outbox: fila %s enviada a %s.", fila.id, fila.destinatarios)
        return _ENVIADO

    @staticmethod
    def intentar_enviar(fila_id: int, conexion=None) -> bool:
        """Envía una fila. True solo si el correo salió. Ver `_intentar`."""
        return EmailOutboxService._intentar(fila_id, conexion) == _ENVIADO

    @staticmethod
    def _abrir_conexion():
        """
        Abre el canal SMTP del lote, o devuelve None si el servidor no responde.

        El `open()` explícito es el que hace que la conexión sobreviva a varios
        `send_messages`: sin él, Django abre y cierra en cada mensaje (solo cierra la
        conexión que él mismo abrió) y volveríamos a pagar un handshake por correo.
        """
        conexion = get_connection()
        try:
            conexion.open()
        except Exception as exc:
            # Ninguna fila se ha reclamado todavía: siguen pendientes, con sus intentos
            # intactos, y el worker las recogerá cuando el SMTP vuelva.
            logger.warning("Outbox: no se pudo abrir la conexión de correo: %s", exc)
            return None
        return conexion

    @staticmethod
    def _cerrar(conexion) -> None:
        """Cierra sin ruido: fallar al colgar no puede convertir un envío bueno en error."""
        try:
            conexion.close()
        except Exception:
            logger.debug("Outbox: fallo al cerrar la conexión de correo.", exc_info=True)

    @staticmethod
    def enviar_lote(ids) -> int:
        """
        Envía varias filas por UNA sola conexión. Devuelve cuántas salieron.

        Es el único camino de envío: `intentar_enviar` suelto queda para el que ya tiene
        una fila concreta entre manos (y para los tests). Un correo aislado es un lote de
        uno, y así el ahorro del canal compartido lo aprovecha todo el mundo sin que cada
        llamador tenga que acordarse.

        Si una fila falla, se renueva la conexión antes de seguir: el fallo pudo ser del
        canal (SMTP que corta por inactividad o por límite de mensajes), y con un canal
        muerto fallaría también todo el resto del lote. Si la renovación no prospera se
        corta ahí: el resto de filas se queda sin reclamar —intentos intactos— y las
        recoge el barrido, en vez de quemarles un intento a todas contra un servidor
        que ya sabemos que no está.
        """
        ids = list(ids or [])
        if not ids:
            return 0

        conexion = EmailOutboxService._abrir_conexion()
        if conexion is None:
            return 0

        enviados = 0
        try:
            for indice, fila_id in enumerate(ids):
                resultado = EmailOutboxService._intentar(fila_id, conexion)
                if resultado == _ENVIADO:
                    enviados += 1
                    continue
                if resultado == _FALLIDO and indice < len(ids) - 1:
                    EmailOutboxService._cerrar(conexion)
                    conexion = EmailOutboxService._abrir_conexion()
                    if conexion is None:
                        logger.warning(
                            "Outbox: lote interrumpido tras %s de %s filas; el resto "
                            "queda pendiente para el barrido.", indice + 1, len(ids))
                        return enviados
        finally:
            if conexion is not None:
                EmailOutboxService._cerrar(conexion)

        return enviados

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

        enviados = EmailOutboxService.enviar_lote(ids)
        return {'candidatos': len(ids), 'enviados': enviados, 'fallidos': len(ids) - enviados}

    # ------------------------------------------------------------------
    # Despacho: cuándo y con qué agrupación se intenta el envío
    # ------------------------------------------------------------------

    @staticmethod
    def enviar_tras_commit(ids) -> None:
        """
        Camino rápido: intenta el envío en cuanto la transacción commita, en un hilo,
        para no bloquear la respuesta con el handshake SMTP (~2 s por correo).

        Acepta un id o una lista: todo el lote viaja en UN hilo y UNA conexión.

        Si este intento no ocurre (proceso reiniciado) o falla, las filas siguen en la
        cola y `procesar_email_outbox` las recogerá. Por eso aquí se puede fallar sin
        drama: la garantía de entrega no depende de este hilo, solo la latencia.
        """
        import threading

        lote = [ids] if isinstance(ids, int) else list(ids)
        if not lote:
            return

        def _lanzar():
            hilo = threading.Thread(
                target=EmailOutboxService.enviar_lote, args=(lote,), daemon=True)
            hilo.start()

        transaction.on_commit(_lanzar)

    @staticmethod
    @contextmanager
    def envio_agrupado():
        """
        Agrupa en un solo lote todos los correos encolados dentro del bloque.

        Sin esto, `despachar` trata cada correo por separado y una notificación de tres
        correos vuelve a pagar tres saludos SMTP. Con esto se encolan los tres y al salir
        del bloque se despachan juntos, por un único canal.

        NO se apoya en `transaction.on_commit` para agrupar, y es deliberado: fuera de un
        `atomic()` —hay strategies que crean sin transacción a propósito— Django ejecuta
        el callback en el acto, así que cada correo formaría su propio grupo de uno. El
        bloque marca el límite del lote de forma explícita, haya transacción o no.

        Reentrante: si ya hay un grupo abierto manda el de fuera, de modo que anidar dos
        notificaciones produce un lote, no dos.
        """
        if getattr(_grupos, 'abierto', None) is not None:
            yield
            return

        _grupos.abierto = []
        try:
            yield
        finally:
            lote, _grupos.abierto = _grupos.abierto, None
            # El despacho va en el `finally` a propósito: si el bloque se rompió a medias,
            # los correos que SÍ llegaron a encolarse deben salir igual. Y si la excepción
            # tumba una transacción, el rollback se lleva por delante las filas del outbox
            # y el lote queda vacío por sí solo — la atomicidad la sigue dando la BD.
            if lote:
                EmailOutboxService._despachar_lote(lote)

    @staticmethod
    def _despachar_lote(ids) -> None:
        """Envía el lote según el modo configurado. Ver `despachar`."""
        if getattr(settings, 'EMAIL_SEND_ASYNC', False):
            EmailOutboxService.enviar_tras_commit(ids)
        else:
            EmailOutboxService.enviar_lote(ids)

    @staticmethod
    def despachar(fila_id: int) -> None:
        """
        Punto único de salida tras encolar: decide CUÁNDO se intenta entregar el correo.

        - Dentro de un `envio_agrupado`: se apunta al lote y no se envía todavía.
        - Con `EMAIL_SEND_ASYNC`: tras el commit y en un hilo (no bloquea la respuesta).
        - Sin él (desarrollo/tests): aquí mismo, para que `mail.outbox` quede poblado
          dentro del propio test.
        """
        if getattr(_grupos, 'abierto', None) is not None:
            _grupos.abierto.append(fila_id)
            return
        EmailOutboxService._despachar_lote([fila_id])
