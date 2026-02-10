"""
Script de prueba para verificar que se puede crear un DobladaDetalle con jornada_pago_sabado
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import DobladaDetalle, SolicitudCambio
from empleados.models import Empleado
from solicitudes.models import TipoSolicitudCambio
from datetime import date

def test_crear_doblada_detalle():
    """Prueba crear un DobladaDetalle con jornada_pago_sabado"""
    print("=" * 60)
    print("PRUEBA: Crear DobladaDetalle con jornada_pago_sabado")
    print("=" * 60)
    
    try:
        # Obtener datos de prueba
        tipo_doblada = TipoSolicitudCambio.objects.filter(nombre="DOBLADA").first()
        if not tipo_doblada:
            print("❌ No se encontró tipo de solicitud DOBLADA")
            return
        
        empleado = Empleado.objects.first()
        if not empleado:
            print("❌ No se encontró ningún empleado")
            return
        
        print(f"\n✅ Usando empleado: {empleado.nombre}")
        print(f"✅ Usando tipo: {tipo_doblada.nombre}")
        
        # Crear solicitud de prueba
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=empleado,
            explorador_receptor=empleado,  # Auto-solicitud para prueba
            tipo_cambio=tipo_doblada,
            comentario="Prueba de jornada_pago_sabado",
            fecha_cambio_turno=date.today(),
            estado='pendiente'
        )
        print(f"✅ Solicitud creada: ID={solicitud.id}")
        
        # Intentar crear DobladaDetalle con jornada_pago_sabado
        print("\n🔍 Intentando crear DobladaDetalle con jornada_pago_sabado='AM'...")
        
        doblada_detalle = DobladaDetalle.objects.create(
            solicitud=solicitud,
            minutos_deuda=30,
            fecha_pago=date.today(),
            tipo_cesion='cesion_completa',
            jornada_pago_sabado='AM'
        )
        
        print(f"✅ DobladaDetalle creado exitosamente: ID={doblada_detalle.id}")
        print(f"   - jornada_pago_sabado: {doblada_detalle.jornada_pago_sabado}")
        
        # Limpiar: eliminar la solicitud de prueba
        solicitud.delete()
        print("\n✅ Solicitud de prueba eliminada")
        
        print("\n" + "=" * 60)
        print("✅ PRUEBA EXITOSA: La columna jornada_pago_sabado funciona correctamente")
        print("=" * 60)
        print("\n💡 Si el error persiste, reinicia el servidor Django completamente")
        print("   (detén el proceso y vuelve a ejecutar: python manage.py runserver)")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        print("\n" + "=" * 60)
        print("❌ PRUEBA FALLIDA")
        print("=" * 60)

if __name__ == '__main__':
    test_crear_doblada_detalle()


