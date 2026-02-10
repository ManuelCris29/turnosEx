#!/usr/bin/env python
"""
Script simple para probar el contador de notificaciones
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from empleados.models import Empleado
from solicitudes.models import Notificacion

def test_counter():
    print("=== PRUEBA DEL CONTADOR DE NOTIFICACIONES ===")
    
    # Buscar a Luisa Perez
    try:
        luisa = Empleado.objects.get(email='luisafernanda2330@hotmail.com')
        print(f"✅ Luisa Perez encontrada: {luisa.nombre} {luisa.apellido}")
        
        # Verificar notificaciones directamente
        notificaciones = Notificacion.objects.filter(destinatario=luisa)
        print(f"📊 Total de notificaciones: {notificaciones.count()}")
        
        notificaciones_no_leidas = Notificacion.objects.filter(destinatario=luisa, leida=False)
        print(f"📊 Notificaciones no leídas: {notificaciones_no_leidas.count()}")
        
        # Probar el método del modelo
        print(f"\n🔍 Probando método del modelo:")
        try:
            contador = luisa.notificaciones_no_leidas_count()
            print(f"✅ Contador retornado: {contador}")
        except Exception as e:
            print(f"❌ Error en método: {e}")
            import traceback
            print(f"Traceback: {traceback.format_exc()}")
        
        # Verificar notificaciones específicas
        print(f"\n📋 Detalle de notificaciones:")
        for notif in notificaciones:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}, Leída: {notif.leida}")
            print(f"    Título: {notif.titulo[:50]}...")
            if notif.solicitud:
                print(f"    Solicitud: {notif.solicitud.id}")
        
    except Empleado.DoesNotExist:
        print("❌ Luisa Perez no encontrada")
    except Exception as e:
        print(f"❌ Error general: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_counter() 