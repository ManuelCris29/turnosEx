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

Cada problema se anuncia con un marcador al principio de la línea: en mayúsculas, sin
acentos y sin texto variable, porque es lo que engancha la alarma (metric filter de
CloudWatch, grep en un cron.daily). Misma convención y mismo motivo que
`REVISION_SANCIONES_NO_EJECUTADA`: si el enganche dependiera de la redacción en español,
cualquier retoque del mensaje apagaría la alerta sin que se note.

DOS MARCADORES, PORQUE SON DOS PROBLEMAS DISTINTOS
--------------------------------------------------
  - `CRON_NO_EJECUTADO`  → nadie está pasando a recoger. Se arregla programando la tarea.
  - `CORREOS_FALLIDOS`   → hay correos que agotaron los cinco reintentos. El cron puede
                           estar perfectamente sano; esto lo arregla UNA PERSONA, desde
                           el admin, y ninguna cantidad de cron lo va a resolver.

Mezclarlos sería el error fácil: un `fallido` NO significa que el worker esté muerto, y
si ensuciara `CRON_NO_EJECUTADO` la alarma de "nadie ejecuta la tarea" empezaría a sonar
por un motivo que no es el suyo — y una alarma que suena por dos causas distintas deja de
decirte qué hacer. Por eso `_revisar_outbox` sigue ignorando los agotados para su `ok`.

VENTANA DE LOS AGOTADOS
-----------------------
`CORREOS_FALLIDOS` solo mira los que agotaron los reintentos en las últimas
`VENTANA_FALLIDOS_HORAS`. Es deliberado: una alarma que no se puede apagar arreglando la
causa se acaba ignorando, y un buzón muerto de verdad (empleado que se fue) volvería a
fallar en cada reintento manual, dejando el check en rojo para siempre. Con la ventana, la
alarma se apaga sola cuando dejan de producirse fallos nuevos, y de inmediato si alguien
los reintenta desde el admin. El recuento TOTAL de agotados no se pierde: sigue saliendo
en el detalle del check del outbox, que es donde se consulta sin prisa.

El aviso, entonces, es «está pasando algo ahora», no «hay pendientes históricos».
"""
import json as _json

from django.core.management.base import BaseCommand
from django.utils import timezone

from solicitudes.models import EmailOutbox, RevisionSancionesDeuda

# Ver el docstring: no se traducen, no se adornan y no cambian.
MARCADOR_ALERTA = 'CRON_NO_EJECUTADO'
MARCADOR_CORREOS_FALLIDOS = 'CORREOS_FALLIDOS'

# Cuánto puede llevar esperando el correo pendiente más antiguo antes de que la cola
# delate al worker. El cron va cada 5 minutos; una hora son doce pasadas perdidas, lo
# bastante como para descartar un pico de SMTP lento o un reintento con backoff.
UMBRAL_OUTBOX_MINUTOS = 60

# Cuántos correos pueden agotar los reintentos dentro de la ventana antes de dar la alarma.
# Por defecto 1: un correo perdido ya es una solicitud que alguien nunca vio, y el volumen
# normal de este sistema (~180 al día) no produce fallos definitivos de forma rutinaria.
UMBRAL_FALLIDOS = 1

# Ver el docstring: la alarma mira lo que se rompió HACE POCO, para que se pueda apagar.
VENTANA_FALLIDOS_HORAS = 24


class Command(BaseCommand):
    help = 'Comprueba que las tareas programadas (outbox y sanciones) están corriendo.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--umbral-outbox', type=int, default=UMBRAL_OUTBOX_MINUTOS, metavar='MINUTOS',
            help=f'Minutos que puede llevar esperando el correo pendiente más antiguo '
                 f'antes de dar la alarma (default: {UMBRAL_OUTBOX_MINUTOS}).')
        parser.add_argument(
            '--umbral-fallidos', type=int, default=UMBRAL_FALLIDOS, metavar='N',
            help=f'Correos que pueden agotar los reintentos en las últimas '
                 f'{VENTANA_FALLIDOS_HORAS} h antes de dar la alarma '
                 f'(default: {UMBRAL_FALLIDOS}).')
        parser.add_argument('--json', action='store_true',
                            help='Salida en JSON, para consumo automático.')

    def handle(self, *args, **options):
        checks = [
            self._revisar_outbox(options['umbral_outbox']),
            self._revisar_correos_fallidos(options['umbral_fallidos']),
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
                    # El marcador lo elige cada check: son alarmas distintas con respuestas
                    # distintas (ver el docstring). `MARCADOR_ALERTA` es solo el default.
                    marcador = c.get('marcador', MARCADOR_ALERTA)
                    self.stderr.write(self.style.ERROR(
                        f"{marcador} {c['cron']}: {c['detalle']}"))

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
    def _revisar_correos_fallidos(umbral: int) -> dict:
        """
        Correos que agotaron los cinco reintentos: nadie los va a volver a tocar.

        Es la otra mitad del hueco que dejaba `_revisar_outbox`. Aquel mide si ALGUIEN está
        vaciando la cola; este mide si algo se perdió del todo. Un worker impecable puede
        producir correos definitivamente perdidos —un destinatario que ya no existe, unas
        credenciales SMTP mal puestas— y hasta ahora eso solo se veía entrando al admin.

        Entrada distinta y marcador distinto a propósito: el arreglo no es programar un
        cron, es que una persona entre a `/admin/solicitudes/emailoutbox/`, filtre por
        `fallido` y decida (reintentar, o corregir la dirección en la ficha del empleado).

        No es un cron, pero viaja en la misma lista que los que sí lo son: una sola
        ejecución y un solo código de salida cubren "las tareas de fondo están sanas".
        """
        desde = timezone.now() - timezone.timedelta(hours=VENTANA_FALLIDOS_HORAS)

        recientes = EmailOutbox.objects.filter(
            estado=EmailOutbox.ESTADO_FALLIDO, creado_en__gte=desde).count()
        total = EmailOutbox.objects.filter(estado=EmailOutbox.ESTADO_FALLIDO).count()

        ok = recientes < umbral
        if not ok:
            detalle = (f'{recientes} correo(s) agotaron los reintentos en las últimas '
                       f'{VENTANA_FALLIDOS_HORAS} h (umbral {umbral}). No se reintentan '
                       f'solos: revisa /admin/solicitudes/emailoutbox/ filtrando por '
                       f'«fallido».')
            if total > recientes:
                detalle += f' En total hay {total} sin resolver.'
        elif total:
            detalle = (f'ninguno agotó los reintentos en las últimas '
                       f'{VENTANA_FALLIDOS_HORAS} h; quedan {total} antiguo(s) sin '
                       f'resolver, para revisar sin prisa.')
        else:
            detalle = 'ningún correo ha agotado los reintentos.'

        return {'cron': 'correos_fallidos', 'ok': ok,
                'marcador': MARCADOR_CORREOS_FALLIDOS,
                'recientes': recientes, 'total': total, 'detalle': detalle}

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
