from django.core.management.base import BaseCommand
from turnos.models import DiaEspecial
from core.utils.festivos_colombia import CalculadoraFestivos
from django.db import transaction

class Command(BaseCommand):
    help = 'Corrige y regenera los días festivos de Colombia según la Ley Emiliani para un rango de años.'

    def handle(self, *args, **options):
        START_YEAR = 2025
        END_YEAR = 2031

        self.stdout.write(self.style.WARNING(f'Iniciando corrección de festivos para el rango {START_YEAR}-{END_YEAR}...'))

        with transaction.atomic():
            # 1. Limpiar festivos existentes (borrado masivo de datos erróneos)
            deleted_count, _ = DiaEspecial.objects.filter(
                tipo='festivo',
                fecha__year__gte=START_YEAR,
                fecha__year__lte=END_YEAR
            ).delete()
            
            self.stdout.write(self.style.SUCCESS(f'Se eliminaron {deleted_count} registros de festivos existentes (posiblemente erróneos).'))

            # 2. Regenerar festivos correctos
            total_created = 0
            for year in range(START_YEAR, END_YEAR + 1):
                festivos = CalculadoraFestivos.calcular_festivos(year)
                
                for f in festivos:
                    # Asignar explícitamente mes y año de planificación para asegurar consistencia
                    fecha = f['fecha']
                    _, created = DiaEspecial.objects.get_or_create(
                        fecha=fecha,
                        tipo='festivo',
                        defaults={
                            'descripcion': f['descripcion'],
                            'activo': True,
                            'es_temporada': False,
                            'mes': fecha.month,
                            'año_planificacion': fecha.year
                        }
                    )
                    if created:
                        total_created += 1
                
                self.stdout.write(f' - Año {year}: Generados {len(festivos)} festivos.')

        self.stdout.write(self.style.SUCCESS(f'¡Proceso completado! Se crearon {total_created} festivos correctos.'))
