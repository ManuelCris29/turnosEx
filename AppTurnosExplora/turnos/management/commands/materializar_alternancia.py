"""
Congela en la base la alternancia de findes y festivos de un año.

PASO DE CORTE del rediseño a semilla anual (ver
docs/02-refactorizacion/PLAN_ALTERNANCIA_SEMILLA_ANUAL.md).

Hasta ahora la alternancia de findes y la rotación de festivos se calculaban al vuelo con
una fórmula: el ancla de `AlternanciaFinesSemanaService` y el índice GLOBAL de
`FestivosRotacionService`. Eso hace que el pasado se recalcule (agregar o borrar un festivo
antiguo invierte todos los posteriores) y que dos entornos con distintos festivos cargados
produzcan calendarios opuestos para el mismo año.

Este comando toma una FOTO: pregunta a la fórmula actual qué grupo trabaja cada finde y cada
festivo entre semana del año, y lo escribe como filas en `AsignacionEspecialManual`. No
recalcula ni reinterpreta nada — el objetivo es que NINGÚN día cambie para el explorador.

IMPORTANTE: usa la rotación de festivos con su índice GLOBAL, no la siembra por año (que
reinicia en enero). Si se usara la siembra, los festivos del año saldrían invertidos respecto
a lo que los exploradores vienen viendo, sin ningún error visible.

Es idempotente: nunca pisa una fila existente (un override manual del supervisor manda).

Uso:
    python manage.py materializar_alternancia --anio 2026 --dry-run   # muestra, no escribe
    python manage.py materializar_alternancia --anio 2026
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from turnos.models import AsignacionEspecialManual, DiaEspecial, Jornada
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
from turnos.services.festivos_rotacion_service import FestivosRotacionService


class Command(BaseCommand):
    help = 'Congela la alternancia calculada de findes y festivos de un año en la base.'

    def add_arguments(self, parser):
        parser.add_argument('--anio', type=int, required=True, help='Año a congelar.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Muestra lo que haría sin escribir nada.')

    def handle(self, *args, **options):
        anio = options['anio']
        dry_run = options['dry_run']

        jornadas = {j.nombre.upper(): j for j in Jornada.objects.all()}
        if not {'AM', 'PM'} <= set(jornadas):
            raise CommandError('Faltan las jornadas AM/PM en la base.')

        festivos_semana = set(
            f for f in DiaEspecial.objects.filter(
                fecha__year=anio, tipo='festivo', activo=True).values_list('fecha', flat=True)
            if f.weekday() < 5
        )
        ya_existen = set(AsignacionEspecialManual.objects.filter(
            fecha__year=anio).values_list('fecha', flat=True))

        # Recorrido del año: findes por alternancia, festivos lun-vie por rotación GLOBAL.
        plan, sin_grupo = [], []
        d, fin = date(anio, 1, 1), date(anio, 12, 31)
        while d <= fin:
            grupo, tipo = None, None
            if d.weekday() >= 5:
                grupo, tipo = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(d), 'finde'
            elif d in festivos_semana:
                tipo = 'festivo'
                try:
                    grupo = FestivosRotacionService.get_grupo_que_dobla_en_festivo(d)
                except Exception as exc:
                    sin_grupo.append((d, str(exc)))
            if tipo:
                if grupo:
                    plan.append((d, tipo, grupo.upper()))
                elif not sin_grupo or sin_grupo[-1][0] != d:
                    sin_grupo.append((d, 'la fórmula no devolvió grupo'))
            d += timedelta(days=1)

        nuevos = [p for p in plan if p[0] not in ya_existen]
        conservados = [p for p in plan if p[0] in ya_existen]

        self.stdout.write(f'Año {anio}: {len(plan)} día(s) especiales '
                          f'({sum(1 for p in plan if p[1] == "finde")} findes, '
                          f'{sum(1 for p in plan if p[1] == "festivo")} festivos lun-vie).')
        for fecha, tipo, grupo in nuevos:
            self.stdout.write(f'  {fecha}  {tipo:8s}  {grupo}')
        if conservados:
            self.stdout.write(self.style.WARNING(
                f'{len(conservados)} día(s) ya tenían asignación manual: se conservan intactos.'))
        if sin_grupo:
            self.stdout.write(self.style.ERROR(
                f'{len(sin_grupo)} día(s) sin grupo calculable (quedan sin fila):'))
            for fecha, motivo in sin_grupo:
                self.stdout.write(self.style.ERROR(f'  {fecha}: {motivo}'))

        if dry_run:
            self.stdout.write(self.style.WARNING(
                f'DRY-RUN: no se escribió nada. Se crearían {len(nuevos)} fila(s).'))
            return

        if not nuevos:
            self.stdout.write(self.style.SUCCESS('Nada que crear: el año ya está congelado.'))
            return

        # Fila a fila y no bulk_create: `bulk_create` se salta las señales y dejaría el
        # congelado SIN historial, que es justo lo que da trazabilidad a este paso.
        #
        # Cada fila en su propio savepoint: si dos ejecuciones de este comando corren en
        # paralelo (dos operadores, o un cron mal configurado), la carrera la resuelve el
        # `UniqueConstraint(fecha)` del modelo — la segunda escritura choca con IntegrityError.
        # Sin savepoint por fila, ese choque tumbaría TODA la transacción y perdería incluso
        # los días que no colisionaron; con savepoint, se omite solo la fecha en conflicto.
        congeladas, en_conflicto = 0, []
        for fecha, tipo, grupo in nuevos:
            try:
                with transaction.atomic():
                    AsignacionEspecialManual.objects.create(
                        fecha=fecha, jornada_trabaja=jornadas[grupo], tipo=tipo, activo=True,
                        descripcion='Congelado desde la alternancia calculada.',
                    )
                congeladas += 1
            except IntegrityError:
                en_conflicto.append(fecha)

        if en_conflicto:
            self.stdout.write(self.style.WARNING(
                f'{len(en_conflicto)} día(s) ya fueron creados por otra ejecución concurrente, '
                f'se omitieron: {en_conflicto}'))

        self.stdout.write(self.style.SUCCESS(
            f'{congeladas} día(s) congelados para {anio}. '
            f'Verifica la equivalencia antes de eliminar la fórmula: '
            f'pytest turnos/tests/test_equivalencia_alternancia.py'))
