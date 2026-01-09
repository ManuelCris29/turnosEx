"""
Script de diagnóstico para verificar el estado de Marco Castillo para el 14 de enero de 2026.
"""
import os
import sys
import django

# Configurar el path correctamente
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from datetime import date
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio
from turnos.models import Turno

# Datos
fecha_objetivo = date(2026, 1, 14)
usuario = "marco.castillo"

print("=" * 80)
print(f"DIAGNÓSTICO: {usuario} - {fecha_objetivo}")
print("=" * 80)

try:
    # Buscar empleado
    empleado = Empleado.objects.get(user__username=usuario)
    print(f"\n✅ Empleado encontrado: {empleado.nombre} (ID: {empleado.id})")
    
    # Obtener jornada predeterminada
    from turnos.models import AsignarJornadaExplorador
    jornada_asignada = AsignarJornadaExplorador.objects.filter(
        explorador=empleado
    ).select_related('jornada').order_by('-fecha_inicio').first()
    
    if jornada_asignada:
        print(f"   Jornada predeterminada: {jornada_asignada.jornada.nombre}")
    else:
        print(f"   Jornada predeterminada: N/A (Sin asignación)")
    
except Empleado.DoesNotExist:
    print(f"\n❌ ERROR: No se encontró empleado con username '{usuario}'")
    exit(1)

# 1. Verificar turnos en esa fecha
print("\n" + "-" * 80)
print("1. TURNOS EN LA TABLA turnos_turno")
print("-" * 80)

turnos = Turno.objects.filter(
    explorador=empleado,
    fecha=fecha_objetivo
).select_related('jornada')

if turnos.exists():
    print(f"   ✅ Tiene {turnos.count()} turno(s) para {fecha_objetivo}:")
    for turno in turnos:
        print(f"      - {turno.jornada.nombre} | Tipo cambio: {turno.tipo_cambio or 'N/A'}")
else:
    print(f"   ℹ️  No tiene turnos registrados en la tabla para {fecha_objetivo}")
    if jornada_asignada:
        print(f"   → Usará su jornada predeterminada: {jornada_asignada.jornada.nombre}")
    else:
        print(f"   → Usará su jornada predeterminada: N/A")

# 2. Verificar solicitudes de doblada como SOLICITANTE
print("\n" + "-" * 80)
print("2. SOLICITUDES DE DOBLADA COMO SOLICITANTE")
print("-" * 80)

dobladas_solicitante = SolicitudCambio.objects.filter(
    explorador_solicitante=empleado,
    tipo_cambio__nombre='DOBLADA',
    fecha_cambio_turno=fecha_objetivo
).select_related('explorador_receptor', 'tipo_cambio')

if dobladas_solicitante.exists():
    print(f"   ✅ Tiene {dobladas_solicitante.count()} solicitud(es) como SOLICITANTE:")
    for sol in dobladas_solicitante:
        print(f"      - ID: {sol.id}")
        print(f"        Estado: {sol.estado}")
        print(f"        Receptor: {sol.explorador_receptor.nombre if sol.explorador_receptor else 'N/A'}")
        print(f"        Fecha cesión: {sol.fecha_cambio_turno}")
        if hasattr(sol, 'doblada'):
            print(f"        Fecha pago: {sol.doblada.fecha_pago}")
else:
    print(f"   ℹ️  No tiene solicitudes de doblada como SOLICITANTE para {fecha_objetivo}")

# 3. Verificar solicitudes de doblada como RECEPTOR
print("\n" + "-" * 80)
print("3. SOLICITUDES DE DOBLADA COMO RECEPTOR")
print("-" * 80)

dobladas_receptor = SolicitudCambio.objects.filter(
    explorador_receptor=empleado,
    tipo_cambio__nombre='DOBLADA',
    fecha_cambio_turno=fecha_objetivo
).select_related('explorador_solicitante', 'tipo_cambio')

if dobladas_receptor.exists():
    print(f"   ✅ Tiene {dobladas_receptor.count()} solicitud(es) como RECEPTOR:")
    for sol in dobladas_receptor:
        print(f"      - ID: {sol.id}")
        print(f"        Estado: {sol.estado}")
        print(f"        Solicitante: {sol.explorador_solicitante.nombre if sol.explorador_solicitante else 'N/A'}")
        print(f"        Fecha cesión: {sol.fecha_cambio_turno}")
        if hasattr(sol, 'doblada'):
            print(f"        Fecha pago: {sol.doblada.fecha_pago}")
else:
    print(f"   ℹ️  No tiene solicitudes de doblada como RECEPTOR para {fecha_objetivo}")

# 4. CONCLUSIÓN
print("\n" + "=" * 80)
print("CONCLUSIÓN")
print("=" * 80)

tiene_doblada_aprobada_receptor = dobladas_receptor.filter(estado='aprobada').exists()
esta_descansando = dobladas_solicitante.filter(estado='aprobada').exists()

if esta_descansando:
    print("   ❌ El sistema DEBE mostrar: 'Estás Descansando'")
    print("      (Marco cedió su jornada como solicitante)")
elif tiene_doblada_aprobada_receptor:
    print("   ❌ El sistema DEBE mostrar: 'Doblada Existente Detectada'")
    print("      (Marco cubre a otro como receptor)")
    jornadas_text = [t.jornada.nombre for t in turnos]
    print(f"      Jornadas: {', '.join(jornadas_text) if jornadas_text else 'N/A'}")
else:
    print("   ✅ El sistema DEBE mostrar: Jornada normal (sin mensaje de doblada)")
    if jornada_asignada:
        print(f"      Marco trabaja su jornada predeterminada: {jornada_asignada.jornada.nombre}")
    else:
        print(f"      Marco trabaja su jornada predeterminada: N/A")

print("\n" + "=" * 80)

