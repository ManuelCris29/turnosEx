"""
Script para resetear la solicitud de doblada 108 (Jhon → Mariana).
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

from solicitudes.models import SolicitudCambio
from django.db import transaction

print("=" * 80)
print("RESETEAR SOLICITUD 108 (Jhon → Mariana)")
print("=" * 80)

try:
    with transaction.atomic():
        solicitud = SolicitudCambio.objects.select_for_update().get(id=108)
        
        print(f"\n📋 Solicitud actual:")
        print(f"   ID: {solicitud.id}")
        print(f"   Solicitante: {solicitud.explorador_solicitante.nombre}")
        print(f"   Receptor: {solicitud.explorador_receptor.nombre if solicitud.explorador_receptor else 'N/A'}")
        print(f"   Estado: {solicitud.estado}")
        print(f"   Aprobado receptor: {solicitud.aprobado_receptor}")
        print(f"   Aprobado supervisor: {solicitud.aprobado_supervisor}")
        print(f"   Fecha resolución: {solicitud.fecha_resolucion}")
        
        # Resetear a pendiente
        solicitud.estado = 'pendiente'
        solicitud.aprobado_receptor = False
        solicitud.aprobado_supervisor = False
        solicitud.fecha_resolucion = None
        solicitud.save()
        
        print(f"\n✅ Solicitud reseteada exitosamente:")
        print(f"   Estado: {solicitud.estado}")
        print(f"   Aprobado receptor: {solicitud.aprobado_receptor}")
        print(f"   Aprobado supervisor: {solicitud.aprobado_supervisor}")
        print(f"   Fecha resolución: {solicitud.fecha_resolucion}")
        
        print("\n" + "=" * 80)
        print("SIGUIENTE PASO:")
        print("=" * 80)
        print("1. Mariana debe aprobar la solicitud nuevamente")
        print("2. El supervisor debe aprobar la solicitud nuevamente")
        print("3. Los turnos se generarán automáticamente tras ambas aprobaciones")
        print("=" * 80)
        
except SolicitudCambio.DoesNotExist:
    print("\n❌ ERROR: No se encontró la solicitud 108")
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

