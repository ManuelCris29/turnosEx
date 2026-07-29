"""
Informa si el año siguiente está listo para arrancar.

Pensado para cron/monitoreo: sale con código != 0 cuando falta algo, de modo que un fallo
sea visible sin depender de que alguien entre a la aplicación.

Uso:
    python manage.py verificar_apertura_anio
    python manage.py verificar_apertura_anio --anio 2028
"""
from django.core.management.base import BaseCommand

from turnos.services.apertura_anio_service import AperturaAnioService


class Command(BaseCommand):
    help = 'Verifica el checklist de apertura del año siguiente. Código != 0 si falta algo.'

    def add_arguments(self, parser):
        parser.add_argument('--anio', type=int, default=None,
                            help='Año a verificar. Por defecto, el siguiente al actual.')

    def handle(self, *args, **options):
        anio = options['anio'] or AperturaAnioService.anio_objetivo()
        items = AperturaAnioService.estado(anio)

        self.stdout.write(f'Apertura del año {anio}:')
        for item in items:
            marca = self.style.SUCCESS('OK  ') if item.completo else self.style.ERROR('FALTA')
            self.stdout.write(f'  [{marca}] {item.titulo} — {item.detalle}')

        pendientes = [i for i in items if not i.completo]
        if pendientes:
            self.stderr.write(self.style.ERROR(
                f'\n{len(pendientes)} de {len(items)} procesos sin completar para {anio}.'))
            raise SystemExit(1)

        self.stdout.write(self.style.SUCCESS(f'\n{anio} está listo: los {len(items)} procesos completos.'))
