"""
El aviso de que una tarea programada dejó de correr.

POR QUÉ EXISTE ESTE COMANDO SI YA ESTÁ `verificar_crons`
--------------------------------------------------------
`verificar_crons` DIAGNOSTICA: mira la cola del outbox y la tabla de revisiones, imprime
lo que encuentra y sale con código 1 si algo va mal. Eso bastaba en el plan de AWS porque
el `crontab` de Linux manda un correo automático cuando un trabajo sale con código
distinto de cero, y CloudWatch enganchaba los marcadores del log con un metric filter.

En Dokploy no hay ninguna de las dos cosas. Sus notificaciones se disparan con
despliegues, backups, limpieza de Docker y umbrales del servidor, pero **NO existe un
disparador para un Schedule que falla**. Un trabajo programado que revienta se queda en
rojo dentro de un log que nadie abre, que es exactamente el modo de fallo contra el que
se escribió `verificar_crons`.

Así que este comando hace lo que allí hacía la infraestructura: ejecuta el mismo
diagnóstico y, si algo va mal, MANDA EL CORREO ÉL MISMO.

POR QUÉ `smtplib` Y NO `django.core.mail`
-----------------------------------------
Dos razones que apuntan al mismo sitio, y ninguna es estética:

  1. **El vigilante no puede compartir maquinaria con lo que vigila.** Todo correo de la
     aplicación pasa por `EmailOutbox`. Si lo averiado es justamente el worker del outbox
     —el caso que este comando existe para detectar—, una alerta encolada ahí se quedaría
     esperando junto a los correos que denuncia. La alarma tiene que salir por un camino
     que no dependa del sistema averiado.
  2. **El ADR 016 fija una comprobación de acoplamiento**: fuera de los tests,
     `django.core.mail` solo puede aparecer en `email_outbox_service.py` (más la línea de
     `EMAIL_BACKEND` de settings). Un import aquí rompería ese invariante en silencio.

Se reutiliza la configuración `EMAIL_*` que ya está en settings: el transporte es el
mismo, lo que cambia es que no se pasa por la cola.

DESTINATARIOS
-------------
Con `--para`, o con la variable de entorno `ALERTAS_CRON_EMAIL` (direcciones separadas
por coma). No se añade un ajuste nuevo a `settings.py` a propósito: esto es configuración
de despliegue y en Dokploy vive junto al resto de variables de la aplicación.

USO
---
    python manage.py alertar_crons --para soporte@parqueexplora.org
    python manage.py alertar_crons --dry-run     # diagnostica e imprime, no envía nada

Termina con código 1 si hay algún problema —incluido el problema de que la propia alerta
no se pudiera enviar—, para que el Schedule quede en rojo además de haber avisado.

EL LATIDO SEMANAL
-----------------
Los lunes, si todo está bien, manda igualmente un correo de "sin novedad". Es la única
defensa contra que deje de correr ESTE comando: un vigilante mudo y un vigilante muerto
se ven igual desde fuera. Se eligió semanal y no diario porque un aviso diario de que no
pasa nada se deja de leer en dos semanas, y entonces el latido no vale nada.
"""
import os
import smtplib
import ssl
from email.message import EmailMessage

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from solicitudes.management.commands.verificar_crons import (
    MARCADOR_ALERTA,
    UMBRAL_FALLIDOS,
    UMBRAL_OUTBOX_MINUTOS,
)
from solicitudes.management.commands.verificar_crons import (
    Command as VerificarCrons,
)

ASUNTO_ALERTA = 'SWALP: una tarea programada no esta corriendo'
ASUNTO_LATIDO = 'SWALP: tareas programadas sin novedad'

# Lunes. `date.weekday()` cuenta desde 0 = lunes.
DIA_DEL_LATIDO = 0


class Command(BaseCommand):
    help = ('Ejecuta los chequeos de verificar_crons y envia un correo de alerta si algo '
            'va mal. Pensado para un Schedule diario.')

    def add_arguments(self, parser):
        parser.add_argument(
            '--para', default='', metavar='CORREOS',
            help='Destinatarios separados por coma. Por defecto, ALERTAS_CRON_EMAIL.')
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Diagnostica e imprime el correo que enviaria, sin enviarlo.')
        parser.add_argument(
            '--umbral-outbox', type=int, default=UMBRAL_OUTBOX_MINUTOS, metavar='MINUTOS',
            help=f'Igual que en verificar_crons (default: {UMBRAL_OUTBOX_MINUTOS}).')
        parser.add_argument(
            '--umbral-fallidos', type=int, default=UMBRAL_FALLIDOS, metavar='N',
            help=f'Igual que en verificar_crons (default: {UMBRAL_FALLIDOS}).')
        parser.add_argument(
            '--sin-latido', action='store_true',
            help='No enviar el correo semanal de "sin novedad" de los lunes.')

    def handle(self, *args, **options):
        checks = [
            VerificarCrons._revisar_outbox(options['umbral_outbox']),
            VerificarCrons._revisar_correos_fallidos(options['umbral_fallidos']),
            VerificarCrons._revisar_sanciones(),
        ]
        problemas = [c for c in checks if not c['ok']]

        for c in checks:
            linea = f"{c['cron']}: {c['detalle']}"
            if c['ok']:
                self.stdout.write(self.style.SUCCESS(f'[ok] {linea}'))
            else:
                self.stderr.write(self.style.ERROR(
                    f"{c.get('marcador', MARCADOR_ALERTA)} {linea}"))

        es_latido = (not problemas
                     and not options['sin_latido']
                     and timezone.localdate().weekday() == DIA_DEL_LATIDO)

        if not problemas and not es_latido:
            self.stdout.write('Nada que avisar.')
            return

        asunto = ASUNTO_ALERTA if problemas else ASUNTO_LATIDO
        cuerpo = self._redactar(checks, problemas)

        if options['dry_run']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                f'--dry-run: NO se envia. Asunto: {asunto}'))
            self.stdout.write(cuerpo)
            if problemas:
                raise SystemExit(1)
            return

        destinatarios = self._destinatarios(options['para'])
        try:
            self._enviar(destinatarios, asunto, cuerpo)
        except Exception as exc:
            # Que la alerta no salga es, en si mismo, un problema que hay que ver: se
            # informa por stderr y se sale en rojo. No se relanza la excepcion para que el
            # traceback no tape el diagnostico, que es lo que alguien va a leer.
            self.stderr.write(self.style.ERROR(
                f'{MARCADOR_ALERTA} alertar_crons: no se pudo enviar el aviso a '
                f'{", ".join(destinatarios)}: {exc.__class__.__name__}: {exc}'))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(
            f'Aviso enviado a {", ".join(destinatarios)}.'))

        if problemas:
            raise SystemExit(1)

    # ------------------------------------------------------------------

    @staticmethod
    def _destinatarios(desde_opcion):
        crudo = desde_opcion or os.environ.get('ALERTAS_CRON_EMAIL', '')
        destinatarios = [d.strip() for d in crudo.split(',') if d.strip()]
        if not destinatarios:
            # Sin destinatarios el comando no puede cumplir su unica funcion. Falla
            # ruidosamente: un vigilante mal configurado que calla es peor que ninguno.
            raise SystemExit(
                f'{MARCADOR_ALERTA} alertar_crons: no hay destinatarios. Pasa --para o '
                f'define ALERTAS_CRON_EMAIL.')
        return destinatarios

    @staticmethod
    def _redactar(checks, problemas):
        if problemas:
            cabecera = [
                'Hay tareas de fondo de SWALP que no estan funcionando como deberian.',
                '',
                'PROBLEMAS:',
            ]
            cuerpo = [
                f"  {c.get('marcador', MARCADOR_ALERTA)}  {c['cron']}: {c['detalle']}"
                for c in problemas
            ]
        else:
            cabecera = ['Latido semanal: las tareas de fondo de SWALP estan al dia.', '']
            cuerpo = []

        detalle = ['', 'ESTADO COMPLETO:'] + [
            f"  [{'ok' if c['ok'] else '!!'}] {c['cron']}: {c['detalle']}" for c in checks
        ]

        pie = [
            '',
            'Que hacer con cada aviso:',
            '  CRON_NO_EJECUTADO  -> nadie esta ejecutando la tarea. Revisar los Schedules',
            '                        de Dokploy (swalp-outbox, swalp-sanciones).',
            '  CORREOS_FALLIDOS   -> hay correos que agotaron los 5 reintentos. No se',
            '                        arreglan solos: /admin/solicitudes/emailoutbox/,',
            '                        filtrar por "fallido" y decidir.',
            '',
            f'Generado por manage.py alertar_crons el '
            f'{timezone.localtime():%Y-%m-%d %H:%M} ({settings.TIME_ZONE}).',
        ]
        return '\n'.join(cabecera + cuerpo + detalle + pie)

    @staticmethod
    def _enviar(destinatarios, asunto, cuerpo):
        """
        Envio directo por SMTP, deliberadamente al margen del outbox y de
        `django.core.mail`. Ver el docstring del modulo: si el outbox esta averiado, la
        alerta no puede viajar por el outbox.
        """
        mensaje = EmailMessage()
        mensaje['Subject'] = asunto
        mensaje['From'] = settings.DEFAULT_FROM_EMAIL
        mensaje['To'] = ', '.join(destinatarios)
        mensaje.set_content(cuerpo)

        timeout = getattr(settings, 'EMAIL_TIMEOUT', 10) or 10
        usa_ssl = getattr(settings, 'EMAIL_USE_SSL', False)

        if usa_ssl:
            servidor = smtplib.SMTP_SSL(settings.EMAIL_HOST, settings.EMAIL_PORT,
                                        timeout=timeout)
        else:
            servidor = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT,
                                    timeout=timeout)

        try:
            if not usa_ssl and settings.EMAIL_USE_TLS:
                servidor.starttls(context=ssl.create_default_context())
            # Con el relay SMTP de Workspace autenticado POR IP no hay credenciales: las
            # variables existen pero van vacias. Llamar a `login` sin ellas da error, asi
            # que se comprueba igual que hace el backend SMTP de Django.
            if settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD:
                servidor.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
            servidor.send_message(mensaje)
        finally:
            try:
                servidor.quit()
            except Exception:
                # Un fallo al cerrar no debe tapar ni inventar un fallo de envio.
                pass
