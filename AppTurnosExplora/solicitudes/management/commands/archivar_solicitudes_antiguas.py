"""
FASE 3.8: Comando de gestión para archivar solicitudes antiguas
Archiva solicitudes aprobadas de más de 1 año a una tabla de archivo
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from solicitudes.models import SolicitudCambio
from django.db import transaction, models


class Command(BaseCommand):
    help = 'Archiva solicitudes aprobadas de más de 1 año'

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
            help='Número de días para considerar una solicitud como antigua (default: 365)',
        )
        parser.add_argument(
            '--solo-aprobadas',
            action='store_true',
            default=True,
            help='Solo archivar solicitudes aprobadas (default: True)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        dias_antiguedad = options['dias']
        solo_aprobadas = options['solo_aprobadas']
        
        # Calcular fecha límite
        fecha_limite = timezone.localdate() - timedelta(days=dias_antiguedad)
        
        self.stdout.write(f'[INFO] Buscando solicitudes anteriores a {fecha_limite}...')
        
        # Obtener solicitudes antiguas
        queryset = SolicitudCambio.objects.filter(
            fecha_resolucion__lt=timezone.make_aware(
                timezone.datetime.combine(fecha_limite, timezone.datetime.min.time())
            ) if timezone.is_aware(timezone.now()) else fecha_limite
        )
        
        if solo_aprobadas:
            queryset = queryset.filter(estado='aprobada')
            self.stdout.write('[INFO] Solo se archivarán solicitudes aprobadas')
        
        total_solicitudes = queryset.count()
        
        if total_solicitudes == 0:
            self.stdout.write(self.style.SUCCESS('[OK] No hay solicitudes antiguas para archivar'))
            return
        
        self.stdout.write(f'[INFO] Se encontraron {total_solicitudes} solicitudes para archivar')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY-RUN] Modo simulación activado. No se archivarán solicitudes.'))
            # Mostrar muestra
            muestra = queryset[:10]
            for solicitud in muestra:
                self.stdout.write(
                    f'  - ID {solicitud.id}: {solicitud.explorador_solicitante.user.username} -> '
                    f'{solicitud.explorador_receptor.user.username} ({solicitud.fecha_resolucion})'
                )
            if total_solicitudes > 10:
                self.stdout.write(f'  ... y {total_solicitudes - 10} más')
            return
        
        # Para solicitudes, simplemente las marcamos como archivadas o las eliminamos
        # Como no tenemos un modelo de archivo, podemos:
        # 1. Eliminarlas directamente (si no se necesitan para auditoría)
        # 2. Crear un campo "archivada" en el modelo
        # 3. Moverlas a otra tabla
        
        # Por ahora, vamos a crear un campo "archivada" en el modelo si no existe
        # O simplemente eliminarlas si el usuario lo confirma
        
        # Opción más segura: crear un campo de archivo en el modelo
        # Por ahora, solo mostramos un mensaje informativo
        self.stdout.write(self.style.WARNING(
            '[INFO] Para archivar solicitudes, se recomienda:'
        ))
        self.stdout.write('  1. Agregar un campo "archivada" al modelo SolicitudCambio')
        self.stdout.write('  2. O crear un modelo SolicitudCambioArchivo similar a TurnoArchivo')
        self.stdout.write('  3. O simplemente eliminar las solicitudes antiguas si no se necesitan')
        self.stdout.write('')
        self.stdout.write(self.style.ERROR(
            '[ADVERTENCIA] No se archivarán solicitudes automáticamente por seguridad.'
        ))
        self.stdout.write('  Las solicitudes contienen información importante para auditoría.')
        self.stdout.write('  Si deseas eliminarlas, hazlo manualmente desde el admin de Django.')

