"""
Limpieza de festivos pre-cargados de años futuros.

Contexto: durante un tiempo los festivos se auto-creaban al previsualizar años
futuros (hasta 50 años vista), dejando festivos sembrados en años que no se usan.
Ahora los festivos se generan por año al guardarlos (como temporada/mantenimiento),
así que estos festivos futuros sobran. Este comando los elimina.

Borra SOLO festivos (tipo='festivo', es_temporada=False) cuyo año sea posterior al
corte. NO toca temporada ni mantenimiento.

Uso:
    python manage.py limpiar_festivos_futuros --dry-run        # ver qué borraría
    python manage.py limpiar_festivos_futuros                  # borra > 2028 (default)
    python manage.py limpiar_festivos_futuros --hasta 2027     # conserva hasta 2027
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from turnos.models import DiaEspecial


class Command(BaseCommand):
    help = "Elimina festivos pre-cargados de años posteriores al corte (default 2028)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--hasta', type=int, default=2028,
            help='Último año a CONSERVAR. Se borran los festivos de años posteriores. Default: 2028.',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Solo informa cuántos borraría, sin eliminar nada.',
        )

    def handle(self, *args, **options):
        corte = options['hasta']
        dry_run = options['dry_run']

        # Solo festivos (no temporada, no mantenimiento), de años posteriores al corte.
        # Filtro robusto: por año de planificación O por año de la fecha.
        qs = DiaEspecial.objects.filter(
            tipo='festivo',
            es_temporada=False,
        ).filter(Q(año_planificacion__gt=corte) | Q(fecha__year__gt=corte))

        total = qs.count()
        por_anio = {}
        for anio in qs.values_list('año_planificacion', flat=True):
            por_anio[anio] = por_anio.get(anio, 0) + 1

        self.stdout.write(f'Corte: se conservan festivos hasta {corte} (inclusive).')
        self.stdout.write(f'Festivos candidatos a borrar (años > {corte}): {total}')
        for anio in sorted(k for k in por_anio if k is not None):
            self.stdout.write(f'  - {anio}: {por_anio[anio]}')

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY-RUN: no se eliminó nada.'))
            return

        if total == 0:
            self.stdout.write(self.style.SUCCESS('Nada que borrar.'))
            return

        with transaction.atomic():
            eliminados, _ = qs.delete()

        self.stdout.write(self.style.SUCCESS(
            f'Eliminados {eliminados} festivos de años posteriores a {corte}. '
            f'Temporada y mantenimiento intactos.'
        ))
