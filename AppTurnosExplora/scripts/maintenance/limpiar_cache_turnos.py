"""
Script para limpiar caché de turnos para usuarios y fechas específicas
Útil cuando se aprueban solicitudes y el caché no se ha limpiado automáticamente
"""
import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from core.services.cache_service import CacheService
from empleados.models import Empleado
from datetime import date

print(f"\n{'='*80}")
print("LIMPIEZA DE CACHÉ DE TURNOS")
print(f"{'='*80}\n")

# Limpiar caché para Mariana y Jeison en enero 2026
mariana = Empleado.objects.filter(nombre__icontains='mariana').first()
jeison = Empleado.objects.filter(nombre__icontains='jeison').first()

if not mariana or not jeison:
    print("❌ No se encontraron los empleados")
    sys.exit(1)

# Enero 2026
anio = 2026
mes = 1

empleados = [mariana, jeison]
cache_keys_limpiadas = []

for empleado in empleados:
    cache_key = f'turnos_mes_{empleado.id}_{anio}_{mes:02d}'
    CacheService.delete(cache_key)
    cache_keys_limpiadas.append(cache_key)
    print(f"✅ Caché limpiado: {cache_key} ({empleado.nombre})")

print(f"\n{'='*80}")
print(f"Total de cachés limpiados: {len(cache_keys_limpiadas)}")
print(f"{'='*80}\n")




