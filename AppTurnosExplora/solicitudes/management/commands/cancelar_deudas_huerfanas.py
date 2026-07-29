"""
Cancela las deudas corporativas ACTIVAS que quedaron HUÉRFANAS (sin solicitud de origen).

Cuando una SolicitudCambio se borraba, su FK en la deuda (on_delete=SET_NULL) quedaba en
NULL y la deuda seguía 'activa', sumando en el Consolidado de Horas dentro del bucket
"Otras". A partir de ahora un signal cancela las deudas al borrar la solicitud, pero pueden
existir huérfanas históricas. Este comando las limpia (marca 'cancelada', no borra).

Uso:
    python manage.py cancelar_deudas_huerfanas --dry-run
    python manage.py cancelar_deudas_huerfanas
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from solicitudes.models import DeudaCorporativa

_MARCA = '[LIMPIEZA HUERFANA]'


class Command(BaseCommand):
    help = "Cancela deudas corporativas activas sin solicitud de origen (huérfanas)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra las deudas que se cancelarían sin modificar nada.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        huerfanas = list(
            DeudaCorporativa.objects
            .filter(estado='activa', solicitud_origen__isnull=True)
            .select_related('explorador__user')
            .order_by('fecha_doblada')
        )

        if not huerfanas:
            self.stdout.write(self.style.SUCCESS('No hay deudas activas huérfanas. Nada que cancelar.'))
            return

        self.stdout.write(
            f"Deudas activas HUÉRFANAS (sin solicitud) encontradas: {len(huerfanas)} "
            f"({sum(d.minutos for d in huerfanas)} min)\n"
        )
        for d in huerfanas:
            exp = d.explorador.user.username if d.explorador and d.explorador.user else d.explorador_id
            self.stdout.write(f"  #{d.id}  {d.fecha_doblada}  {d.minutos} min  {exp}  | {(d.comentario or '')[:50]}")

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY-RUN] No se modificó nada. Ejecuta sin --dry-run para aplicar.'))
            return

        hoy = timezone.localdate()
        actualizadas = 0
        for d in huerfanas:
            nota = f"{_MARCA} Cancelada el {hoy}: deuda huérfana (su solicitud de origen fue borrada)."
            d.comentario = f"{d.comentario}\n{nota}" if d.comentario else nota
            d.estado = 'cancelada'
            d.save(update_fields=['estado', 'comentario'])
            actualizadas += 1

        self.stdout.write(self.style.SUCCESS(f"\nListo. {actualizadas} deudas huérfanas canceladas."))
