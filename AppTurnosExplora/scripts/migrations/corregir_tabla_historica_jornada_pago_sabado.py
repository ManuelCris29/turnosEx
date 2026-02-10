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

def corregir_tabla_historica():
    """Busca y corrige la tabla histórica de DobladaDetalle"""
    with connection.cursor() as cursor:
        print("=" * 60)
        print("CORRECCIÓN DE TABLA HISTÓRICA")
        print("=" * 60)
        
        # Buscar todas las tablas que contengan "dobladadetalle" y "history"
        cursor.execute("""
            SELECT TABLE_NAME 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME LIKE '%dobladadetalle%history%'
        """)
        
        tablas = [row[0] for row in cursor.fetchall()]
        
        if not tablas:
            print("\n⚠️  No se encontraron tablas históricas para DobladaDetalle")
            print("   Esto es normal si aún no se ha creado ningún registro histórico")
            print("   La tabla se creará automáticamente cuando se guarde el primer registro")
            print("\n💡 Solución: La columna se agregará automáticamente cuando simple_history")
            print("   cree la tabla, ya que el modelo ya tiene el campo definido.")
            return
        
        print(f"\n✅ Encontradas {len(tablas)} tabla(s) histórica(s):")
        for tabla in tablas:
            print(f"   - {tabla}")
        
        # Verificar y agregar la columna en cada tabla
        for tabla in tablas:
            print(f"\n📋 Procesando tabla: {tabla}")
            
            # Verificar si la columna existe
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = %s
                AND COLUMN_NAME = 'jornada_pago_sabado'
            """, [tabla])
            
            existe = cursor.fetchone()[0] > 0
            
            if existe:
                print(f"   ✅ La columna 'jornada_pago_sabado' ya existe")
            else:
                print(f"   ⚠️  La columna 'jornada_pago_sabado' NO existe. Agregándola...")
                
                try:
                    cursor.execute(f"""
                        ALTER TABLE {tabla}
                        ADD COLUMN jornada_pago_sabado VARCHAR(2) NULL
                        COMMENT 'Si la fecha de pago es sábado, jornada (AM/PM) que el solicitante elige trabajar ese sábado'
                    """)
                    print(f"   ✅ Columna agregada exitosamente")
                except Exception as e:
                    print(f"   ❌ Error al agregar columna: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Proceso completado")
    print("=" * 60)

if __name__ == '__main__':
    try:
        corregir_tabla_historica()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


