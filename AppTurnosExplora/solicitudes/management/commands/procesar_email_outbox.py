"""
Reintenta los correos que quedaron sin entregar en la cola (`EmailOutbox`).

Es la RED DE SEGURIDAD del patrón outbox: el camino normal envía cada correo justo
después del commit, y este comando solo recoge lo que ese camino no logró entregar
(proceso reiniciado a media entrega, SMTP caído, red intermitente).

Pensado para un cron cada pocos minutos:
    */5 * * * * python manage.py procesar_email_outbox

Es seguro ejecutarlo en paralelo consigo mismo: cada fila se reclama con un UPDATE
condicional, así que dos ejecuciones simultáneas nunca envían el mismo correo dos veces.
"""
from django.core.management.base import BaseCommand

from solicitudes.models import EmailOutbox
from solicitudes.services.email_outbox_service import EmailOutboxService


class Command(BaseCommand):
    help = 'Reintenta el envío de los correos pendientes en la cola (outbox).'

    def add_arguments(self, parser):
        parser.add_argument('--limite', type=int, default=50,
                            help='Máximo de correos a intentar en esta pasada (default: 50).')
        parser.add_argument('--resumen', action='store_true',
                            help='Solo muestra el estado de la cola, sin enviar nada.')

    def handle(self, *args, **options):
        if options['resumen']:
            self._mostrar_resumen()
            return

        resultado = EmailOutboxService.procesar_pendientes(limite=options['limite'])

        if not resultado['candidatos']:
            self.stdout.write(self.style.SUCCESS('Cola vacía: no hay correos por reintentar.'))
            return

        self.stdout.write(self.style.SUCCESS(
            f"{resultado['enviados']} de {resultado['candidatos']} correo(s) enviados."))
        if resultado['fallidos']:
            self.stdout.write(self.style.WARNING(
                f"{resultado['fallidos']} siguen pendientes; se reintentarán con backoff."))
            self._mostrar_resumen()

    def _mostrar_resumen(self):
        conteos = {estado: EmailOutbox.objects.filter(estado=estado).count()
                   for estado, _ in EmailOutbox.ESTADO_CHOICES}
        self.stdout.write('Estado de la cola: ' +
                          ', '.join(f'{k}={v}' for k, v in conteos.items()))

        # Los 'fallido' agotaron los reintentos: nadie los va a recoger ya, así que son
        # los únicos que exigen intervención humana. Se listan para que se vean.
        agotados = EmailOutbox.objects.filter(estado=EmailOutbox.ESTADO_FALLIDO)[:10]
        if agotados:
            self.stdout.write(self.style.ERROR(
                'Correos que agotaron los reintentos (requieren revisión manual):'))
            for fila in agotados:
                self.stdout.write(self.style.ERROR(
                    f'  #{fila.id} → {fila.destinatarios}: {fila.ultimo_error[:120]}'))
