"""
Script para crear la tabla histórica de DobladaDetalle con todas las columnas correctas
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

def crear_tabla_historica():
    """Crea la tabla histórica con todas las columnas correctas"""
    with connection.cursor() as cursor:
        print("=" * 60)
        print("CREAR TABLA HISTÓRICA COMPLETA")
        print("=" * 60)
        
        tabla_historica = "solicitudes_dobladadetallehistory"
        
        # Verificar si la tabla ya existe
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
        """, [tabla_historica])
        
        existe = cursor.fetchone()[0] > 0
        
        if existe:
            print(f"\n⚠️  La tabla histórica '{tabla_historica}' ya existe")
            print("   Eliminándola para recrearla con la estructura correcta...")
            cursor.execute(f"DROP TABLE IF EXISTS {tabla_historica}")
            print("   ✅ Tabla eliminada")
        
        print(f"\n📋 Creando tabla histórica: {tabla_historica}")
        
        # Crear la tabla histórica con todas las columnas necesarias
        # Basado en la estructura de simple_history para DobladaDetalle
        cursor.execute(f"""
            CREATE TABLE {tabla_historica} (
                id BIGINT NOT NULL,
                history_id INT AUTO_INCREMENT PRIMARY KEY,
                history_date DATETIME(6) NOT NULL,
                history_change_reason VARCHAR(100) NULL,
                history_type VARCHAR(1) NOT NULL,
                history_user_id INT NULL,
                minutos_deuda INT NOT NULL,
                fecha_pago DATE NOT NULL,
                solicitud_id BIGINT NOT NULL,
                jornada_cedida VARCHAR(2) NULL,
                tipo_cesion VARCHAR(50) NOT NULL,
                empleado_receptor_id INT NULL,
                jornada_pago_sabado VARCHAR(2) NULL,
                INDEX solicitudes_dobladadetallehistory_id_index (id),
                INDEX solicitudes_dobladadetallehistory_history_date_index (history_date),
                INDEX solicitudes_dobladadetallehistory_history_user_id_index (history_user_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        
        print("   ✅ Tabla histórica creada exitosamente")
        
        # Verificar que la columna jornada_pago_sabado existe
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
            AND COLUMN_NAME = 'jornada_pago_sabado'
        """, [tabla_historica])
        
        columna_existe = cursor.fetchone()[0] > 0
        
        if columna_existe:
            print("   ✅ Columna 'jornada_pago_sabado' verificada en la tabla histórica")
        else:
            print("   ❌ ERROR: La columna 'jornada_pago_sabado' no se creó")
    
    print("\n" + "=" * 60)
    print("✅ Proceso completado")
    print("=" * 60)
    print("\n💡 Ahora puedes probar crear un DobladaDetalle nuevamente")

if __name__ == '__main__':
    try:
        crear_tabla_historica()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


