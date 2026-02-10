"""
Script para corregir la solicitud 110 que quedó aprobada sin crear turnos.
Cambia el estado de 'aprobada' a 'pendiente' para que se pueda aprobar de nuevo.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio

def corregir_solicitud_110():
    """Cambiar estado de solicitud 110 a pendiente."""
    try:
        solicitud = SolicitudCambio.objects.get(id=110)
        
        print(f"\n📋 SOLICITUD ANTES DE CORRECCIÓN:")
        print(f"   ID: {solicitud.id}")
        print(f"   Estado: {solicitud.estado}")
        print(f"   Fecha cesión: {solicitud.fecha_cambio_turno}")
        print(f"   Solicitante: {solicitud.explorador_solicitante.nombre}")
        print(f"   Receptor: {solicitud.explorador_receptor.nombre}")
        
        # Cambiar estado a pendiente (mantener aprobaciones para no violar constraint)
        solicitud.estado = 'pendiente'
        solicitud.fecha_resolucion = None
        solicitud.save(update_fields=['estado', 'fecha_resolucion'])
        
        print(f"\n✅ SOLICITUD CORREGIDA:")
        print(f"   Estado actualizado: {solicitud.estado}")
        print(f"   Fecha resolución: {solicitud.fecha_resolucion}")
        print(f"   Ahora aparecerá en 'Solicitudes Pendientes'")
        print(f"\n🔄 Próximos pasos:")
        print(f"   1. Recarga la página de 'Solicitudes Pendientes'")
        print(f"   2. Aprueba la solicitud como receptor")
        print(f"   3. Aprueba la solicitud como supervisor")
        print(f"   4. Los turnos se crearán correctamente\n")
        
        return True
        
    except SolicitudCambio.DoesNotExist:
        print(f"❌ ERROR: No se encontró la solicitud con ID 110")
        return False
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = corregir_solicitud_110()
    sys.exit(0 if success else 1)

