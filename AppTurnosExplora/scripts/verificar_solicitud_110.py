"""
Script para verificar el estado actual de la solicitud 110.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio

def verificar_solicitud():
    """Verificar estado de la solicitud 110."""
    try:
        solicitud = SolicitudCambio.objects.get(id=110)
        
        print(f"\n📋 ESTADO ACTUAL DE SOLICITUD 110:")
        print(f"   ID: {solicitud.id}")
        print(f"   Estado: {solicitud.estado}")
        print(f"   Tipo: {solicitud.tipo_cambio.nombre}")
        print(f"   Fecha cesión: {solicitud.fecha_cambio_turno}")
        print(f"   Fecha solicitud: {solicitud.fecha_solicitud}")
        print(f"   Fecha resolución: {solicitud.fecha_resolucion}")
        print(f"   Solicitante ID: {solicitud.explorador_solicitante.id} - {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}")
        print(f"   Receptor ID: {solicitud.explorador_receptor.id} - {solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}")
        print(f"   Aprobado receptor: {solicitud.aprobado_receptor}")
        print(f"   Aprobado supervisor: {solicitud.aprobado_supervisor}")
        
        # Verificar supervisor
        supervisor_solicitante = solicitud.explorador_solicitante.supervisor if hasattr(solicitud.explorador_solicitante, 'supervisor') else None
        print(f"   Supervisor del solicitante: {supervisor_solicitante}")
        
        print(f"\n✅ La solicitud existe y está en estado '{solicitud.estado}'")
        print(f"\n📌 Marco (ID {solicitud.explorador_receptor.id}) debería ver esta solicitud en 'Solicitudes Pendientes'")
        
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
    success = verificar_solicitud()
    sys.exit(0 if success else 1)

