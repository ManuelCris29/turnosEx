"""
Script para forzar a Django a reconocer la columna en la tabla histórica
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from django.core.management import call_command
from solicitudes.models import DobladaDetalle

def forzar_reconocimiento():
    """Fuerza a Django a reconocer la columna"""
    print("=" * 70)
    print("FORZAR RECONOCIMIENTO DE COLUMNA EN TABLA HISTÓRICA")
    print("=" * 70)
    
    # 1. Verificar que la columna existe en BD
    tabla_historica = "solicitudes_dobladadetallehistory"
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
            AND COLUMN_NAME = 'jornada_pago_sabado'
        """, [tabla_historica])
        
        existe = cursor.fetchone()[0] > 0
        if not existe:
            print("❌ La columna no existe en la base de datos")
            return False
        
        print("✅ Columna confirmada en base de datos")
    
    # 2. Limpiar caché de Django
    print("\n📋 Limpiando caché de Django...")
    from django.core.cache import cache
    cache.clear()
    print("✅ Caché limpiado")
    
    # 3. Forzar recarga del esquema de la base de datos
    print("\n📋 Forzando recarga del esquema...")
    connection.close()
    connection.ensure_connection()
    print("✅ Conexión reiniciada")
    
    # 4. Verificar modelo histórico
    print("\n📋 Verificando modelo histórico...")
    try:
        # Obtener el modelo histórico
        from simple_history.utils import get_history_manager_for_model
        history_manager = get_history_manager_for_model(DobladaDetalle)
        historical_model = history_manager.model
        
        campos_historicos = [f.name for f in historical_model._meta.get_fields() if hasattr(f, 'name')]
        
        if 'jornada_pago_sabado' in campos_historicos:
            print("✅ Campo 'jornada_pago_sabado' encontrado en modelo histórico")
            print(f"   Campos históricos: {campos_historicos}")
            return True
        else:
            print("⚠️  Campo 'jornada_pago_sabado' NO encontrado en modelo histórico")
            print(f"   Campos históricos disponibles: {campos_historicos}")
            print("\n💡 Esto puede requerir regenerar el modelo histórico")
            return False
            
    except Exception as e:
        print(f"⚠️  Error verificando modelo histórico: {e}")
        return False

if __name__ == '__main__':
    try:
        exito = forzar_reconocimiento()
        print("\n" + "=" * 70)
        if exito:
            print("✅ RECONOCIMIENTO FORZADO - Prueba crear un DobladaDetalle ahora")
        else:
            print("⚠️  Puede ser necesario regenerar el modelo histórico")
            print("   O usar la solución temporal (excluded_fields) por ahora")
        print("=" * 70)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


