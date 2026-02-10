"""
Script para verificar y mostrar información sobre la columna jornada_pago_sabado
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

def verificar_columna():
    """Verifica si la columna existe y muestra información."""
    print("=" * 60)
    print("VERIFICACIÓN DE COLUMNA jornada_pago_sabado")
    print("=" * 60)
    
    # 1. Verificar nombre de tabla
    tabla = DobladaDetalle._meta.db_table
    print(f"\n1. Nombre de tabla Django: {tabla}")
    
    # 2. Verificar en base de datos
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM information_schema.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = %s
            AND COLUMN_NAME = 'jornada_pago_sabado'
        """, [tabla])
        
        resultado = cursor.fetchone()
        
        if resultado:
            print(f"\n2. ✅ Columna encontrada en BD:")
            print(f"   - Nombre: {resultado[0]}")
            print(f"   - Tipo: {resultado[1]}")
            print(f"   - Nullable: {resultado[2]}")
            print(f"   - Default: {resultado[3]}")
        else:
            print(f"\n2. ❌ Columna NO encontrada en BD")
            print(f"   Intentando agregarla...")
            
            try:
                cursor.execute(f"""
                    ALTER TABLE {tabla}
                    ADD COLUMN jornada_pago_sabado VARCHAR(2) NULL
                    COMMENT 'Si la fecha de pago es sábado, jornada (AM/PM) que el solicitante elige trabajar ese sábado'
                """)
                print(f"   ✅ Columna agregada exitosamente")
            except Exception as e:
                print(f"   ❌ Error al agregar columna: {e}")
    
    # 3. Verificar en modelo Django
    print(f"\n3. Verificando modelo Django...")
    campos = [f.name for f in DobladaDetalle._meta.get_fields()]
    if 'jornada_pago_sabado' in campos:
        print(f"   ✅ Campo 'jornada_pago_sabado' existe en el modelo")
        campo = DobladaDetalle._meta.get_field('jornada_pago_sabado')
        print(f"   - Tipo: {type(campo).__name__}")
        print(f"   - Nullable: {campo.null}")
        print(f"   - Blank: {campo.blank}")
    else:
        print(f"   ❌ Campo 'jornada_pago_sabado' NO existe en el modelo")
    
    print("\n" + "=" * 60)
    print("RECOMENDACIÓN: Si la columna existe en BD pero Django no la reconoce,")
    print("reinicia el servidor Django (detén y vuelve a ejecutar runserver)")
    print("=" * 60)

if __name__ == '__main__':
    try:
        verificar_columna()
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


