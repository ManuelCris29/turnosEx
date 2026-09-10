"""
CAPA 2 — Revisión diaria de sanciones por deuda de horas.

Crea las sanciones de quien cerró un mes debiendo y salda la deuda de quien ya cumplió su
castigo, sin esperar a que ninguna de esas personas abra la aplicación.

Pagar NO levanta una sanción: se cumple entera. Lo que este proceso cierra al final del
ciclo es la deuda, que queda saldada por el propio castigo.

Se ejecuta A DIARIO aunque la regla sea mensual, y esto es deliberado. Un trabajo que
solo corre el día 1 y falla ese día pierde el mes entero, y nadie se entera hasta que un
moroso intenta solicitar algo. Como el contenido de la sanción se deriva del vencimiento
de la deuda (ver `sancion_deuda_calculo`) y no del reloj, correr el día 2 produce
exactamente el mismo registro que habría producido el día 1: un fallo cuesta un día de
retraso en el aviso, no un mes de impunidad. El proceso se autocura.

Coordinación
------------
La aplicación corre con varios workers de gunicorn y la caché puede ser `LocMemCache`
(por proceso), así que un lock de caché no coordina nada. El candado es una fila en
`RevisionSancionesDeuda` con `fecha` única: quien logra insertarla es el único que trabaja
ese día. Lo impone el motor de la base de datos, que es lo único que los workers comparten.

Uso
---
    python manage.py revisar_sanciones_por_deuda --dry-run   # diagnóstico, no escribe
    python manage.py revisar_sanciones_por_deuda             # ejecución normal (cron)
    python manage.py revisar_sanciones_por_deuda --force     # repetir aunque ya corriera hoy

Programación en producción: ver `docs/05-referencia/deployment/03-operacion/MANUAL_SANCIONES_DEUDA.md`.
"""
import logging

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from solicitudes.models import RevisionSancionesDeuda
from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService

logger = logging.getLogger(__name__)

# Texto fijo que identifica la alerta en los logs. Las alarmas de producción filtran por
# ESTA cadena, así que no se traduce, no se adorna y no cambia: ver el checklist de
# despliegue y `MANUAL_SANCIONES_DEUDA.md`.
MARCADOR_ALERTA = 'REVISION_SANCIONES_NO_EJECUTADA'


class Command(BaseCommand):
    help = ("Revisa las deudas de horas vencidas y aplica o levanta las sanciones "
            "automáticas que correspondan. Pensado para correr una vez al día.")

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra a quién se sancionaría, sin escribir nada ni marcar el día.',
        )
        parser.add_argument(
            '--force', action='store_true',
            help='Ejecuta aunque la revisión de hoy ya esté marcada como hecha.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        hoy = timezone.localdate()

        # Lo primero: ¿ha estado corriendo? Un cron caído no da ningún error que alguien
        # vea —simplemente deja de ocurrir—, y el síntoma (morosos que siguen solicitando)
        # tarda semanas en notarse y nadie lo atribuye a esto. Se denuncia por log en el
        # nivel que dispara las alertas, y se enseña en pantalla.
        dias = RevisionSancionesDeuda.dias_sin_ejecutar(hoy)
        if RevisionSancionesDeuda.hay_hueco(hoy):
            nunca = not RevisionSancionesDeuda.objects.exists()
            aviso = ('NUNCA se ha ejecutado: comprueba que la tarea programada exista.'
                     if nunca else
                     f'lleva {dias} días sin ejecutarse. Se recupera ahora, pero no está '
                     f'corriendo a diario.')
            # El marcador va PRIMERO y en mayúsculas, sin acentos ni texto variable: es lo
            # que engancha la alarma (metric filter de CloudWatch, grep en un cron.daily…).
            # Si el enganche dependiera de la redacción en español, cualquier retoque del
            # mensaje apagaría la alerta en silencio — y una alerta apagada no se nota hasta
            # que hace falta.
            logger.critical('%s %s', MARCADOR_ALERTA, aviso)
            self.stderr.write(self.style.ERROR(f'{MARCADOR_ALERTA} {aviso}'))

        filas = DeudaCorporativaService.auditar_morosos(aplicar=False)
        pendientes = [f for f in filas if f['estado'] == 'pendiente']

        self.stdout.write(
            f"Revisión {hoy:%d/%m/%Y} — exploradores con deuda activa: {len(filas)} "
            f"(sin sancionar: {len(pendientes)}, "
            f"ya sancionados: {sum(1 for f in filas if f['estado'] == 'sancionado')}, "
            f"en plazo: {sum(1 for f in filas if f['estado'] == 'en_plazo')})"
        )
        for f in pendientes:
            e = f['explorador']
            self.stdout.write(
                f"  - {e.nombre} {e.apellido}: {f['minutos']} min, "
                f"más antigua {f['deuda_mas_antigua']:%d/%m/%Y} "
                f"(venció el {f['plazo_hasta']:%d/%m/%Y})"
            )

        if dry_run:
            self.stdout.write(self.style.WARNING(
                'DRY-RUN: no se ha modificado nada ni se ha marcado el día.'))
            return

        # El candado. `get_or_create` sobre un campo único es atómico: entre varios
        # procesos simultáneos, exactamente uno recibe created=True.
        with transaction.atomic():
            marca, creada = RevisionSancionesDeuda.objects.get_or_create(fecha=hoy)

        if not creada and not force:
            self.stdout.write(self.style.WARNING(
                f'La revisión de {hoy:%d/%m/%Y} ya se ejecutó '
                f'({marca.ejecutado_en:%H:%M}): {marca.sanciones_creadas} creada(s), '
                f'{marca.sanciones_levantadas} deuda(s) saldada(s). '
                f'Usa --force para repetirla.'))
            return

        resumen = DeudaCorporativaService.revisar_todos()

        marca.sanciones_creadas = resumen['creadas']
        # El campo se llama `sanciones_levantadas` por su uso anterior: contaba las que se
        # levantaban al pagar. Ese levantamiento automático ya no existe —la sanción se
        # cumple entera— y ahora cuenta las deudas SALDADAS al cumplirse el castigo, que es
        # la operación que ocupa su lugar en el ciclo. Se reutiliza para no migrar la tabla.
        marca.sanciones_levantadas = resumen['consumidas']
        marca.detalle = resumen['detalle']
        marca.save(update_fields=['sanciones_creadas', 'sanciones_levantadas', 'detalle'])

        self.stdout.write(self.style.SUCCESS(
            f"Hecho: {resumen['creadas']} sanción(es) creada(s), "
            f"{resumen['consumidas']} deuda(s) saldada(s) al cumplirse la sanción."))
        if resumen['detalle']:
            self.stdout.write(resumen['detalle'])
