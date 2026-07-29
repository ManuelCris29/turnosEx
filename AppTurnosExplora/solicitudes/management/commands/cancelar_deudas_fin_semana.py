"""
Cancela las deudas corporativas (30 min) cuya doblada cayó en FIN DE SEMANA.

Regla de negocio: los 30 minutos de deuda por doblada solo aplican de lunes a viernes.
Cuando se trabaja un fin de semana se cumple una jornada completa de todos modos, así que
NO se debe deuda. La generación ya está bloqueada (DeudaCorporativaService.aplica_deuda_doblada),
pero pueden existir registros HISTÓRICOS creados antes de la regla. Este comando los limpia
marcándolos como 'cancelada' (no los borra: es reversible y queda traza en el comentario).

Uso:
    python manage.py cancelar_deudas_fin_semana --dry-run   # solo muestra, no cambia nada
    python manage.py cancelar_deudas_fin_semana             # aplica la cancelación
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from solicitudes.models import DeudaCorporativa

_MARCA = '[LIMPIEZA FDS]'
_DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']


class Command(BaseCommand):
    help = "Cancela deudas corporativas históricas cuya doblada cayó en fin de semana (ya no aplican 30 min)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Muestra las deudas que se cancelarían sin modificar nada.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        activas = DeudaCorporativa.objects.filter(estado='activa').select_related('explorador__user')
        fds = [d for d in activas if d.fecha_doblada and d.fecha_doblada.weekday() >= 5]

        if not fds:
            self.stdout.write(self.style.SUCCESS('No hay deudas activas de fin de semana. Nada que cancelar.'))
            return

        self.stdout.write(
            f"Deudas activas de FIN DE SEMANA encontradas: {len(fds)} "
            f"({sum(d.minutos for d in fds)} min en total)\n"
        )
        for d in sorted(fds, key=lambda x: x.fecha_doblada):
            dia = _DIAS[d.fecha_doblada.weekday()]
            exp = d.explorador.user.username if d.explorador and d.explorador.user else d.explorador_id
            self.stdout.write(f"  #{d.id}  {d.fecha_doblada} ({dia})  {d.minutos} min  {exp}")

        if dry_run:
            self.stdout.write(self.style.WARNING('\n[DRY-RUN] No se modificó nada. Ejecuta sin --dry-run para aplicar.'))
            return

        hoy = timezone.localdate()
        actualizadas = 0
        for d in fds:
            nota = f"{_MARCA} Cancelada el {hoy}: las dobladas de fin de semana no generan deuda de 30 min."
            d.comentario = f"{d.comentario}\n{nota}" if d.comentario else nota
            d.estado = 'cancelada'
            d.save(update_fields=['estado', 'comentario'])
            actualizadas += 1

        self.stdout.write(self.style.SUCCESS(f"\nListo. {actualizadas} deudas de fin de semana canceladas."))
