"""
Script para diagnosticar la solicitud de doblada 111.
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

from solicitudes.models import SolicitudCambio, DobladaDetalle
from turnos.models import Turno

print("=" * 80)
print("DIAGNÓSTICO: Solicitud de Doblada ID 111")
print("=" * 80)

try:
    solicitud = SolicitudCambio.objects.get(id=111)
    print(f"\n✅ Solicitud encontrada:")
    print(f"   Tipo: {solicitud.tipo_cambio.nombre}")
    print(f"   Estado: {solicitud.estado}")
    print(f"   Solicitante: {solicitud.explorador_solicitante.nombre} (ID: {solicitud.explorador_solicitante.id})")
    print(f"   Receptor: {solicitud.explorador_receptor.nombre if solicitud.explorador_receptor else 'N/A'} (ID: {solicitud.explorador_receptor.id if solicitud.explorador_receptor else 'N/A'})")
    print(f"   Fecha cesión: {solicitud.fecha_cambio_turno}")
    print(f"   Fecha solicitud: {solicitud.fecha_solicitud}")
    print(f"   Fecha resolución: {solicitud.fecha_resolucion}")
    print(f"   Aprobado receptor: {solicitud.aprobado_receptor}")
    print(f"   Aprobado supervisor: {solicitud.aprobado_supervisor}")
    
    # Detalles de la doblada
    print("\n" + "-" * 80)
    print("DETALLES DE LA DOBLADA")
    print("-" * 80)
    
    try:
        detalle = solicitud.doblada
        print(f"   Fecha pago: {detalle.fecha_pago}")
        print(f"   Minutos deuda: {detalle.minutos_deuda}")
        print(f"   Tipo cesión: {detalle.tipo_cesion}")
        print(f"   Jornada cedida: {detalle.jornada_cedida}")
        print(f"   Empleado receptor: {detalle.empleado_receptor.nombre if detalle.empleado_receptor else 'N/A'}")
    except DobladaDetalle.DoesNotExist:
        print("   ❌ No se encontró detalle de doblada")
    
    # Verificar turnos creados para el SOLICITANTE (Jhon)
    print("\n" + "-" * 80)
    print(f"TURNOS PARA SOLICITANTE ({solicitud.explorador_solicitante.nombre})")
    print("-" * 80)
    
    turnos_solicitante = Turno.objects.filter(
        explorador=solicitud.explorador_solicitante,
        fecha=solicitud.fecha_cambio_turno
    ).select_related('jornada')
    
    if turnos_solicitante.exists():
        print(f"   ✅ Tiene {turnos_solicitante.count()} turno(s):")
        for turno in turnos_solicitante:
            print(f"      - {turno.jornada.nombre} | Tipo cambio: {turno.tipo_cambio or 'N/A'}")
    else:
        print(f"   ✅ CORRECTO: No tiene turnos (está descansando)")
    
    # Verificar turnos creados para el RECEPTOR (Marco)
    print("\n" + "-" * 80)
    print(f"TURNOS PARA RECEPTOR ({solicitud.explorador_receptor.nombre if solicitud.explorador_receptor else 'N/A'})")
    print("-" * 80)
    
    if solicitud.explorador_receptor:
        turnos_receptor = Turno.objects.filter(
            explorador=solicitud.explorador_receptor,
            fecha=solicitud.fecha_cambio_turno
        ).select_related('jornada')
        
        if turnos_receptor.exists():
            print(f"   ✅ Tiene {turnos_receptor.count()} turno(s):")
            for turno in turnos_receptor:
                print(f"      - {turno.jornada.nombre} | Tipo cambio: {turno.tipo_cambio or 'N/A'}")
        else:
            print(f"   ❌ ERROR: No tiene turnos (debería tener doblada)")
    
    print("\n" + "=" * 80)
    print("CONCLUSIÓN")
    print("=" * 80)
    
    if solicitud.explorador_receptor:
        turnos_count = Turno.objects.filter(
            explorador=solicitud.explorador_receptor,
            fecha=solicitud.fecha_cambio_turno
        ).count()
        
        if turnos_count == 0:
            print("   ❌ PROBLEMA DETECTADO:")
            print("      La solicitud está aprobada pero no se generaron los turnos.")
            print("      Posible causa: Error al aplicar la doblada o transacción fallida.")
            print("\n   💡 SOLUCIÓN:")
            print("      Resetear la solicitud y volverla a aprobar:")
            print(f"      python scripts/resetear_solicitud_111.py")
        elif turnos_count == 1:
            print("   ⚠️  PROBLEMA DETECTADO:")
            print("      Solo se generó 1 turno en lugar de 2 (doblada incompleta).")
        elif turnos_count == 2:
            print("   ✅ Todo correcto: Se generaron los 2 turnos de la doblada.")
    
    print("=" * 80)
    
except SolicitudCambio.DoesNotExist:
    print("\n❌ ERROR: No se encontró la solicitud 111")




