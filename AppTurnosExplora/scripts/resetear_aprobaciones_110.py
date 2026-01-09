"""
Script para resetear completamente las aprobaciones de la solicitud 110.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio
from django.db import connection

def resetear_aprobaciones():
    """Resetear aprobaciones usando SQL directo para evitar constraints."""
    try:
        with connection.cursor() as cursor:
            # Actualizar usando SQL directo
            cursor.execute("""
                UPDATE solicitudes_solicitudcambio 
                SET aprobado_receptor = FALSE,
                    aprobado_supervisor = FALSE,
                    fecha_resolucion = NULL
                WHERE id = 110
            """)
        
        # Verificar cambio
        solicitud = SolicitudCambio.objects.get(id=110)
        
        print(f"\n✅ SOLICITUD 110 RESETEADA COMPLETAMENTE:")
        print(f"   Estado: {solicitud.estado}")
        print(f"   Aprobado receptor: {solicitud.aprobado_receptor}")
        print(f"   Aprobado supervisor: {solicitud.aprobado_supervisor}")
        print(f"   Fecha resolución: {solicitud.fecha_resolucion}")
        print(f"\n🔄 Ahora SÍ aparecerá en 'Solicitudes Pendientes' para Marco\n")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = resetear_aprobaciones()
    sys.exit(0 if success else 1)

