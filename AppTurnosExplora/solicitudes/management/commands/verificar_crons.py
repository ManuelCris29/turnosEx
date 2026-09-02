"""
¿Están corriendo de verdad las tareas programadas?

EL HUECO QUE CIERRA
-------------------
Los dos procesos de fondo de SWALP fallan EN SILENCIO cuando nadie los programa:

  - `procesar_email_outbox` (cada 5 min) reintenta los correos que el envío inmediato
    no logró entregar. Si no corre, esos correos se quedan en la cola para siempre y
    nadie ve un error: el explorador simplemente nunca recibe el aviso.
  - `revisar_sanciones_por_deuda` (a diario) crea las sanciones de quien cerró el mes
    debiendo. Si no corre, los morosos siguen solicitando con normalidad.

`revisar_sanciones_por_deuda` ya se autodenuncia si lleva días sin correr… pero solo
PUEDE hacerlo cuando alguien lo ejecuta. Contra el fallo que de verdad importa —que
nadie programó la tarea— un proceso no puede avisar de su propia ausencia. Hasta ahora
la única defensa era que una persona leyera un checklist de despliegue.

Este comando mira el problema desde FUERA: no ejecuta ninguna de las dos tareas, solo
lee el rastro que dejan en la base de datos. Un cron muerto se delata por lo que se
acumula sin que nadie lo toque.

USO
---
    python manage.py verificar_crons            # legible, para una persona
    python manage.py verificar_crons --json     # para un script de despliegue

Termina con código de salida 1 si algo va mal, para que el paso de un despliegue o el
propio cron que lo envuelve falle de forma visible en vez de imprimir y seguir.

Cada problema se anuncia con el marcador `CRON_NO_EJECUTADO` al principio de la línea:
en mayúsculas, sin acentos y sin texto variable, porque es lo que engancha la alarma
(metric filter de CloudWatch, grep en un cron.daily). Misma convención y mismo motivo
que `REVISION_SANCIONES_NO_EJECUTADA`: si el enganche dependiera de la redacción en
español, cualquier retoque del mensaje apagaría la alerta sin que se note.
"""
import json as _json

from django.core.management.base import BaseCommand
from django.utils import timezone

from solicitudes.models import EmailOutbox, RevisionSancionesDeuda

# Ver el docstring: no se traduce, no se adorna y no cambia.
MARCADOR_ALERTA = 'CRON_NO_EJECUTADO'

# Cuánto puede llevar esperando el correo pendiente más antiguo antes de que la cola
# delate al worker. El cron va cada 5 minutos; una hora son doce pasadas perdidas, lo
# bastante como para descartar un pico de SMTP lento o un reintento con backoff.
UMBRAL_OUTBOX_MINUTOS = 60


class Command(BaseCommand):
    help = 'Comprueba que las tareas programadas (outbox y sanciones) están corriendo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--umbral-outbox', type=int, default=UMBRAL_OUTBOX_MINUTOS, metavar='MINUTOS',
            help=f'Minutos que puede llevar esperando el correo pendiente más antiguo '
                 f'antes de dar la alarma (default: {UMBRAL_OUTBOX_MINUTOS}).')
        parser.add_argument('--json', action='store_true',
                            help='Salida en JSON, para consumo automático.')

    def handle(self, *args, **options):
        checks = [
            self._revisar_outbox(options['umbral_outbox']),
            self._revisar_sanciones(),
        ]
        problemas = [c for c in checks if not c['ok']]

        if options['json']:
            self.stdout.write(_json.dumps(
                {'ok': not problemas, 'checks': checks}, ensure_ascii=False, indent=2))
        else:
            for c in checks:
                if c['ok']:
                    self.stdout.write(self.style.SUCCESS(f"[ok] {c['cron']}: {c['detalle']}"))
                else:
                    self.stderr.write(self.style.ERROR(
                        f"{MARCADOR_ALERTA} {c['cron']}: {c['detalle']}"))

        if problemas:
            # Código de salida != 0: lo que convierte esto en un check y no en un informe
            # que alguien tiene que acordarse de leer.
            raise SystemExit(1)

    # ------------------------------------------------------------------

    @staticmethod
    def _revisar_outbox(umbral_minutos: int) -> dict:
        """
        Se mide la ESPERA del correo pendiente más antiguo que ya tocaba enviar, no el
        tamaño de la cola.

        Es la única señal que distingue las dos situaciones: una cola larga con un worker
        vivo se vacía sola —lo normal tras un pico—, mientras que una sola fila que lleva
        horas esperando su turno solo se explica porque nadie está pasando a recogerla.

        El filtro repite el de `procesar_email_outbox` (`disponible_en` vencido e intentos
        sin agotar) a propósito: si contara filas que el worker NO va a tocar, daría la
        alarma con un worker perfectamente sano. Las que agotaron los reintentos quedan
        fuera —esas piden una persona, no un cron— y se informan aparte.
        """
        ahora = timezone.now()
        mas_antigua = (
            EmailOutbox.objects
            .filter(estado__in=[EmailOutbox.ESTADO_PENDIENTE, EmailOutbox.ESTADO_ENVIANDO],
                    disponible_en__lte=ahora,
                    intentos__lt=EmailOutbox.MAX_INTENTOS)
            .order_by('disponible_en')
            .values_list('disponible_en', flat=True)
            .first()
        )
        agotados = EmailOutbox.objects.filter(estado=EmailOutbox.ESTADO_FALLIDO).count()
        extra = (f' Además, {agotados} correo(s) agotaron los reintentos y necesitan '
                 f'revisión manual.') if agotados else ''

        if mas_antigua is None:
            return {'cron': 'procesar_email_outbox', 'ok': True,
                    'espera_minutos': 0, 'agotados': agotados,
                    'detalle': f'no hay correos esperando.{extra}'}

        espera = int((ahora - mas_antigua).total_seconds() // 60)
        ok = espera <= umbral_minutos
        detalle = (f'el correo pendiente más antiguo lleva {espera} min esperando '
                   f'(umbral {umbral_minutos} min).')
        if not ok:
            detalle += (' Nadie está vaciando la cola: comprueba que el cron '
                        '`procesar_email_outbox` esté programado y corriendo.')
        return {'cron': 'procesar_email_outbox', 'ok': ok,
                'espera_minutos': espera, 'agotados': agotados,
                'detalle': detalle + extra}

    @staticmethod
    def _revisar_sanciones() -> dict:
        """
        Aquí el rastro ya existía: `RevisionSancionesDeuda` graba una fila por día
        ejecutado. Se reutilizan `dias_sin_ejecutar` y `hay_hueco` en vez de escribir un
        segundo criterio, para que «lleva demasiado sin correr» signifique lo mismo visto
        desde dentro del comando y desde fuera.
        """
        dias = RevisionSancionesDeuda.dias_sin_ejecutar()
        nunca = not RevisionSancionesDeuda.objects.exists()
        ok = not RevisionSancionesDeuda.hay_hueco()

        if nunca:
            detalle = ('NUNCA se ha ejecutado. Si el sistema lleva más de un día '
                       'desplegado, la tarea programada no existe.')
        elif ok:
            detalle = ('se ejecutó hoy.' if dias == 0
                       else f'se ejecutó hace {dias} día(s), dentro de lo tolerado.')
        else:
            detalle = (f'lleva {dias} días sin ejecutarse (se toleran '
                       f'{RevisionSancionesDeuda.DIAS_TOLERADOS}). Los morosos no se '
                       f'están sancionando.')

        return {'cron': 'revisar_sanciones_por_deuda', 'ok': ok,
                'dias_sin_ejecutar': None if nunca else dias,
                'nunca_ejecutado': nunca, 'detalle': detalle}
