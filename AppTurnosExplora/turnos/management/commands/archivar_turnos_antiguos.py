"""
FASE 3.7: Comando de gestión para archivar turnos antiguos
Archiva turnos de más de 1 año a la tabla TurnoArchivo
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from turnos.models import Turno, TurnoArchivo
from django.db import transaction


class Command(BaseCommand):
    help = 'Archiva turnos de más de 1 año a la tabla TurnoArchivo'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simular el proceso sin archivar realmente',
        )
        parser.add_argument(
            '--dias',
            type=int,
            default=365,
            help='Número de días para considerar un turno como antiguo (default: 365)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        dias_antiguedad = options['dias']
        
        # Calcular fecha límite (turnos anteriores a esta fecha se archivan)
        fecha_limite = timezone.localdate() - timedelta(days=dias_antiguedad)
        
        self.stdout.write(f'[INFO] Buscando turnos anteriores a {fecha_limite}...')
        
        # Obtener turnos antiguos
        turnos_antiguos = Turno.objects.filter(fecha__lt=fecha_limite)
        total_turnos = turnos_antiguos.count()
        
        if total_turnos == 0:
            self.stdout.write(self.style.SUCCESS('[OK] No hay turnos antiguos para archivar'))
            return
        
        self.stdout.write(f'[INFO] Se encontraron {total_turnos} turnos para archivar')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Modo simulación activado. No se archivarán turnos.'))
            # Mostrar muestra de turnos que se archivarían
            muestra = turnos_antiguos[:10]
            for turno in muestra:
                self.stdout.write(f'  - {turno.explorador.user.username} - {turno.fecha}')
            if total_turnos > 10:
                self.stdout.write(f'  ... y {total_turnos - 10} más')
            return
        
        # Archivar turnos en lotes para mejor rendimiento
        lote_size = 100
        turnos_archivados = 0
        turnos_errores = 0
        
        self.stdout.write(f'[INFO] Iniciando archivado en lotes de {lote_size}...')
        
        for i in range(0, total_turnos, lote_size):
            lote = turnos_antiguos[i:i + lote_size]
            
            with transaction.atomic():
                for turno in lote:
                    try:
                        # Crear registro en TurnoArchivo
                        TurnoArchivo.objects.create(
                            explorador=turno.explorador,
                            fecha=turno.fecha,
                            jornada=turno.jornada,
                            sala=turno.sala,
                            tipo_cambio=turno.tipo_cambio,
                            turno_original_id=turno.id
                        )
                        
                        # Eliminar turno original
                        turno.delete()
                        turnos_archivados += 1
                        
                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(f'[ERROR] Error al archivar turno {turno.id}: {str(e)}')
                        )
                        turnos_errores += 1
            
            # Mostrar progreso
            if (i + lote_size) % 500 == 0 or (i + lote_size) >= total_turnos:
                self.stdout.write(f'[INFO] Progreso: {min(i + lote_size, total_turnos)}/{total_turnos} procesados')
        
        # Resumen final
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('[OK] Archivado completado:'))
        self.stdout.write(f'  - Turnos archivados: {turnos_archivados}')
        if turnos_errores > 0:
            self.stdout.write(self.style.ERROR(f'  - Errores: {turnos_errores}'))
        
        # Invalidar caché relacionado
        from django.core.cache import cache
        cache.clear()
        self.stdout.write('[INFO] Caché limpiado')

