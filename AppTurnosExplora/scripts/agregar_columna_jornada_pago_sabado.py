"""
Script para agregar la columna jornada_pago_sabado a la tabla solicitudes_dobladadetalle
si no existe.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

def agregar_columna():
    """Agrega la columna jornada_pago_sabado si no existe."""
    with connection.cursor() as cursor:
        # Verificar si la columna existe
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'solicitudes_dobladadetalle'
            AND COLUMN_NAME = 'jornada_pago_sabado'
        """)
        
        existe = cursor.fetchone()[0] > 0
        
        if existe:
            print("✅ La columna 'jornada_pago_sabado' ya existe en la tabla 'solicitudes_dobladadetalle'")
        else:
            print("⚠️  La columna 'jornada_pago_sabado' NO existe. Agregándola...")
            
            # Agregar la columna
            cursor.execute("""
                ALTER TABLE solicitudes_dobladadetalle
                ADD COLUMN jornada_pago_sabado VARCHAR(2) NULL
                COMMENT 'Si la fecha de pago es sábado, jornada (AM/PM) que el solicitante elige trabajar ese sábado'
            """)
            
            print("✅ Columna 'jornada_pago_sabado' agregada exitosamente")
    
    print("\n✅ Proceso completado. La columna debería estar disponible ahora.")

if __name__ == '__main__':
    try:
        agregar_columna()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


