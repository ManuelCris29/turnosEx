"""
Script para agregar la columna jornada_pago_sabado a la tabla histórica de simple_history
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from solicitudes.models import DobladaDetalle

def agregar_columna_historica():
    """Agrega la columna jornada_pago_sabado a la tabla histórica si no existe."""
    with connection.cursor() as cursor:
        # Obtener el nombre de la tabla histórica
        # simple_history generalmente usa el patrón: {app}_{model}history
        tabla_historica = f"{DobladaDetalle._meta.app_label}_{DobladaDetalle._meta.model_name}history"
        
        print("=" * 60)
        print("AGREGAR COLUMNA A TABLA HISTÓRICA")
        print("=" * 60)
        print(f"\nTabla histórica: {tabla_historica}")
        
        # Verificar si la tabla histórica existe
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
        """, [tabla_historica])
        
        tabla_existe = cursor.fetchone()[0] > 0
        
        if not tabla_existe:
            print(f"\n⚠️  La tabla histórica '{tabla_historica}' no existe.")
            print("   Esto puede ser normal si no se ha usado simple_history aún.")
            return
        
        print(f"✅ Tabla histórica encontrada")
        
        # Verificar si la columna existe en la tabla histórica
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
            AND COLUMN_NAME = 'jornada_pago_sabado'
        """, [tabla_historica])
        
        existe = cursor.fetchone()[0] > 0
        
        if existe:
            print(f"✅ La columna 'jornada_pago_sabado' ya existe en la tabla histórica")
        else:
            print(f"⚠️  La columna 'jornada_pago_sabado' NO existe en la tabla histórica. Agregándola...")
            
            # Agregar la columna a la tabla histórica
            cursor.execute(f"""
                ALTER TABLE {tabla_historica}
                ADD COLUMN jornada_pago_sabado VARCHAR(2) NULL
                COMMENT 'Si la fecha de pago es sábado, jornada (AM/PM) que el solicitante elige trabajar ese sábado'
            """)
            
            print(f"✅ Columna 'jornada_pago_sabado' agregada a la tabla histórica exitosamente")
    
    print("\n" + "=" * 60)
    print("✅ Proceso completado")
    print("=" * 60)

if __name__ == '__main__':
    try:
        agregar_columna_historica()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


