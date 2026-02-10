"""
Script para verificar y corregir la tabla histórica de DobladaDetalle
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection

def verificar_y_corregir():
    """Verifica y corrige la tabla histórica"""
    tabla_historica = "solicitudes_dobladadetallehistory"
    
    with connection.cursor() as cursor:
        print("=" * 70)
        print("VERIFICACIÓN Y CORRECCIÓN DE TABLA HISTÓRICA")
        print("=" * 70)
        
        # 1. Verificar si la tabla existe
        cursor.execute("""
            SELECT COUNT(*) 
            FROM information_schema.TABLES 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
        """, [tabla_historica])
        
        existe = cursor.fetchone()[0] > 0
        
        if not existe:
            print(f"\n⚠️  La tabla '{tabla_historica}' no existe")
            print("   Se creará automáticamente cuando se guarde el primer registro")
            return
        
        print(f"\n✅ Tabla encontrada: {tabla_historica}")
        
        # 2. Ver todas las columnas actuales
        cursor.execute(f"DESCRIBE {tabla_historica}")
        columnas_actuales = {row[0]: row[1] for row in cursor.fetchall()}
        
        print(f"\n📋 Columnas actuales en la tabla histórica:")
        for col, tipo in columnas_actuales.items():
            print(f"   - {col}: {tipo}")
        
        # 3. Verificar si jornada_pago_sabado existe
        if 'jornada_pago_sabado' in columnas_actuales:
            print(f"\n✅ La columna 'jornada_pago_sabado' ya existe")
            print(f"   Tipo: {columnas_actuales['jornada_pago_sabado']}")
        else:
            print(f"\n⚠️  La columna 'jornada_pago_sabado' NO existe. Agregándola...")
            try:
                cursor.execute(f"""
                    ALTER TABLE {tabla_historica}
                    ADD COLUMN jornada_pago_sabado VARCHAR(2) NULL
                    COMMENT 'Si la fecha de pago es sábado, jornada (AM/PM) que el solicitante elige trabajar ese sábado'
                """)
                print(f"✅ Columna agregada exitosamente")
            except Exception as e:
                print(f"❌ Error al agregar columna: {e}")
                return False
        
        # 4. Verificar estructura completa esperada
        print(f"\n📋 Verificando estructura completa...")
        columnas_esperadas = [
            'id', 'history_id', 'history_date', 'history_change_reason', 
            'history_type', 'history_user_id', 'minutos_deuda', 'fecha_pago',
            'solicitud_id', 'jornada_cedida', 'tipo_cesion', 
            'empleado_receptor_id', 'jornada_pago_sabado'
        ]
        
        faltantes = [col for col in columnas_esperadas if col not in columnas_actuales]
        if faltantes:
            print(f"⚠️  Columnas faltantes: {faltantes}")
        else:
            print(f"✅ Todas las columnas esperadas están presentes")
        
        print("\n" + "=" * 70)
        print("✅ VERIFICACIÓN COMPLETA")
        print("=" * 70)
        return True

if __name__ == '__main__':
    try:
        verificar_y_corregir()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


