"""
Comando para instalar y verificar la biblioteca calendario-colombiano
Ejecutar: python manage.py instalar_calendario_colombiano
"""
from django.core.management.base import BaseCommand
import subprocess  # nosec B404 - comando de instalación con args fijos, sin input externo
import sys


class Command(BaseCommand):
    help = 'Instala la biblioteca calendario-colombiano para cálculo preciso de festivos'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('Instalando calendario-colombiano...'))
        
        try:
            # nosec B603 - argumentos fijos (sys.executable + pip), sin datos de usuario
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'calendario-colombiano'])  # nosec B603
            self.stdout.write(self.style.SUCCESS('✓ Biblioteca instalada correctamente'))
            
            # Verificar instalación
            try:
                from calendario_colombiano import CalendarioColombiano
                from datetime import date
                
                calendario = CalendarioColombiano()
                
                # Probar con una fecha conocida
                fecha_prueba = date(2026, 1, 12)  # Lunes 12 de enero de 2026 (Reyes Magos trasladado)
                es_festivo = calendario.es_festivo(fecha_prueba)
                
                self.stdout.write(self.style.SUCCESS(f'✓ Verificación exitosa'))
                self.stdout.write(f'  Fecha de prueba: {fecha_prueba}')
                self.stdout.write(f'  ¿Es festivo? {es_festivo}')
                
            except ImportError as e:
                self.stdout.write(self.style.ERROR(f'✗ Error al importar: {e}'))
                
        except subprocess.CalledProcessError as e:
            self.stdout.write(self.style.ERROR(f'✗ Error al instalar: {e}'))
            self.stdout.write(self.style.WARNING('Intenta ejecutar manualmente: pip install calendario-colombiano'))


