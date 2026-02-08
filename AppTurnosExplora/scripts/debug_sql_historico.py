"""
Script para debuggear el SQL que Django genera para el historial
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from django.db import reset_queries
from solicitudes.models import DobladaDetalle, SolicitudCambio
from empleados.models import Empleado
from solicitudes.models import TipoSolicitudCambio
from datetime import date

def debug_sql():
    """Debug del SQL generado"""
    print("=" * 70)
    print("DEBUG: SQL GENERADO PARA HISTORIAL")
    print("=" * 70)
    
    # Habilitar logging de queries
    from django.db import connection
    from django.conf import settings
    settings.DEBUG = True
    
    try:
        # Obtener datos de prueba
        tipo_doblada = TipoSolicitudCambio.objects.filter(nombre="DOBLADA").first()
        empleado = Empleado.objects.first()
        
        if not tipo_doblada or not empleado:
            print("❌ No se encontraron datos de prueba")
            return
        
        # Crear solicitud
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=empleado,
            explorador_receptor=empleado,
            tipo_cambio=tipo_doblada,
            comentario="Debug test",
            fecha_cambio_turno=date.today(),
            estado='pendiente'
        )
        
        print(f"\n✅ Solicitud creada: ID={solicitud.id}")
        
        # Limpiar queries
        reset_queries()
        
        # Intentar crear DobladaDetalle con logging
        print("\n🔍 Intentando crear DobladaDetalle...")
        print("   Habilitando logging de SQL...")
        
        try:
            doblada_detalle = DobladaDetalle.objects.create(
                solicitud=solicitud,
                minutos_deuda=30,
                fecha_pago=date.today(),
                tipo_cesion='cesion_completa',
                jornada_pago_sabado='AM'
            )
            print("✅ DobladaDetalle creado exitosamente")
            solicitud.delete()
        except Exception as e:
            print(f"\n❌ Error: {e}")
            
            # Mostrar queries ejecutadas
            queries = connection.queries
            if queries:
                print(f"\n📋 Últimas {min(5, len(queries))} queries ejecutadas:")
                for i, query in enumerate(queries[-5:], 1):
                    print(f"\n{i}. {query['sql'][:200]}...")
                    if 'jornada_pago_sabado' in query['sql']:
                        print("   ⚠️  Esta query incluye 'jornada_pago_sabado'")
            
            solicitud.delete()
            raise
    
    except Exception as e:
        print(f"❌ Error en debug: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    debug_sql()


