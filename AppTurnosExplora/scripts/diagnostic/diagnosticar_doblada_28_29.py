"""
Script de diagnóstico para la doblada entre Mariana y Jeison
Fecha de cesión: 28/01/2026
Fecha de pago: 29/01/2026
"""
import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio
from turnos.models import Turno
from empleados.models import Empleado
from datetime import date
from core.services.cache_service import CacheService

print(f"\n{'='*80}")
print("DIAGNÓSTICO: DOBLADA 28-29 ENERO")
print(f"{'='*80}\n")

# Buscar empleados
mariana = Empleado.objects.filter(nombre__icontains='mariana').first()
jeison = Empleado.objects.filter(nombre__icontains='jeison').first()

if not mariana or not jeison:
    print("❌ No se encontraron los empleados")
    sys.exit(1)

print(f"✅ Mariana: {mariana.nombre} (ID: {mariana.id})")
print(f"✅ Jeison: {jeison.nombre} (ID: {jeison.id})\n")

# Buscar solicitud
fecha_cesion = date(2026, 1, 28)
fecha_pago = date(2026, 1, 29)

solicitud = SolicitudCambio.objects.filter(
    explorador_solicitante=mariana,
    explorador_receptor=jeison,
    tipo_cambio__nombre='DOBLADA',
    fecha_cambio_turno=fecha_cesion
).select_related('doblada').first()

if not solicitud:
    print("❌ No se encontró la solicitud")
    print("\nBuscando todas las solicitudes recientes:")
    todas = SolicitudCambio.objects.filter(
        explorador_solicitante=mariana,
        tipo_cambio__nombre='DOBLADA'
    ).order_by('-id')[:5]
    for s in todas:
        print(f"  - ID: {s.id}, Estado: {s.estado}, Fecha: {s.fecha_cambio_turno}, Aprobado: {s.aprobado_receptor} y {s.aprobado_supervisor}")
    sys.exit(1)

print(f"✅ Solicitud ID: {solicitud.id}")
print(f"   Estado: {solicitud.estado}")
print(f"   Aprobado receptor: {solicitud.aprobado_receptor}")
print(f"   Aprobado supervisor: {solicitud.aprobado_supervisor}\n")

# Verificar turnos
print("TURNOS EN BD:")
print(f"  28/01 - Mariana: {Turno.objects.filter(explorador=mariana, fecha=fecha_cesion).count()} turnos")
print(f"  28/01 - Jeison: {Turno.objects.filter(explorador=jeison, fecha=fecha_cesion).count()} turnos")
print(f"  29/01 - Mariana: {Turno.objects.filter(explorador=mariana, fecha=fecha_pago).count()} turnos")
print(f"  29/01 - Jeison: {Turno.objects.filter(explorador=jeison, fecha=fecha_pago).count()} turnos\n")

# Verificar caché
print("CACHÉ:")
anio = 2026
mes = 1
cache_key_mariana = f'turnos_mes_{mariana.id}_{anio}_{mes:02d}'
cache_key_jeison = f'turnos_mes_{jeison.id}_{anio}_{mes:02d}'

cache_mariana = CacheService.get(cache_key_mariana)
cache_jeison = CacheService.get(cache_key_jeison)

print(f"  Mariana: {'✅ Existe' if cache_mariana else '❌ No existe'}")
print(f"  Jeison: {'✅ Existe' if cache_jeison else '❌ No existe'}")

if cache_mariana:
    fechas_en_cache = list(cache_mariana.keys()) if isinstance(cache_mariana, dict) else []
    tiene_28 = '2026-01-28' in fechas_en_cache
    tiene_29 = '2026-01-29' in fechas_en_cache
    print(f"  Fechas en caché Mariana: {len(fechas_en_cache)}")
    print(f"  Tiene 28/01: {'✅' if tiene_28 else '❌'}")
    print(f"  Tiene 29/01: {'✅' if tiene_29 else '❌'}")

print(f"\n{'='*80}\n")




