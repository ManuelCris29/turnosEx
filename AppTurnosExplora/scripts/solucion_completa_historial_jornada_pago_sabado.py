"""
Script para implementar la solución completa: agregar jornada_pago_sabado al historial
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

def implementar_solucion_completa():
    """Implementa la solución completa agregando la columna al historial"""
    print("=" * 70)
    print("SOLUCIÓN COMPLETA: Agregar jornada_pago_sabado al Historial")
    print("=" * 70)
    
    tabla_historica = "solicitudes_dobladadetallehistory"
    
    with connection.cursor() as cursor:
        # 1. Verificar si la tabla histórica existe
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
        """, [tabla_historica])
        
        tabla_existe = cursor.fetchone()[0] > 0
        
        if not tabla_existe:
            print(f"\n⚠️  La tabla histórica '{tabla_historica}' no existe aún.")
            print("   Se creará automáticamente cuando se guarde el primer registro.")
            print("   La columna se agregará automáticamente porque el modelo ya la tiene definida.")
            print("\n✅ Solución: Solo necesitas quitar la exclusión del modelo.")
            return True
        
        print(f"\n✅ Tabla histórica encontrada: {tabla_historica}")
        
        # 2. Verificar si la columna ya existe
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
            AND COLUMN_NAME = 'jornada_pago_sabado'
        """, [tabla_historica])
        
        columna_existe = cursor.fetchone()[0] > 0
        
        if columna_existe:
            print(f"✅ La columna 'jornada_pago_sabado' ya existe en la tabla histórica")
            print("\n✅ Solución: Solo necesitas quitar la exclusión del modelo.")
            return True
        
        # 3. Agregar la columna
        print(f"\n📋 Agregando columna 'jornada_pago_sabado' a la tabla histórica...")
        
        try:
            cursor.execute(f"""
                ALTER TABLE {tabla_historica}
                ADD COLUMN jornada_pago_sabado VARCHAR(2) NULL
                COMMENT 'Si la fecha de pago es sábado, jornada (AM/PM) que el solicitante elige trabajar ese sábado'
            """)
            print(f"✅ Columna agregada exitosamente")
            
            # 4. Verificar
            cursor.execute("""
                SELECT COUNT(*) 
                FROM information_schema.COLUMNS 
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = %s
                AND COLUMN_NAME = 'jornada_pago_sabado'
            """, [tabla_historica])
            
            verificacion = cursor.fetchone()[0] > 0
            if verificacion:
                print(f"✅ Verificación: Columna confirmada en la tabla histórica")
                return True
            else:
                print(f"❌ Error: La columna no se creó correctamente")
                return False
                
        except Exception as e:
            print(f"❌ Error al agregar columna: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    return False

if __name__ == '__main__':
    try:
        exito = implementar_solucion_completa()
        
        print("\n" + "=" * 70)
        if exito:
            print("✅ SOLUCIÓN COMPLETA IMPLEMENTADA")
            print("=" * 70)
            print("\n📝 PRÓXIMOS PASOS:")
            print("1. Quitar 'excluded_fields' del modelo DobladaDetalle")
            print("2. Reiniciar el servidor Django")
            print("3. Probar crear un DobladaDetalle con jornada_pago_sabado")
            print("\n💡 El historial ahora capturará todos los cambios en jornada_pago_sabado")
        else:
            print("⚠️  Hubo problemas. Revisa los errores arriba.")
            print("=" * 70)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


