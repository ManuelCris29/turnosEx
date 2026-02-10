#!/usr/bin/env python
"""
Script para probar la creación manual de una solicitud con los mismos datos de la interfaz web
"""
import os
import django
from datetime import date

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio, Notificacion, TipoSolicitudCambio
from empleados.models import Empleado
from solicitudes.services.solicitud_service import SolicitudService

def test_manual_request():
    print("=== PROBANDO CREACIÓN MANUAL DE SOLICITUD ===")
    
    try:
        # 1. Buscar empleados
        luisa = Empleado.objects.get(email='luisafernanda2330@hotmail.com')
        manuel = Empleado.objects.get(email='manuel.moreno@parqueexplora.org')
        tipo_solicitud = TipoSolicitudCambio.objects.get(id=3)  # Doblada
        
        print(f"✅ Luisa Perez: {luisa.nombre} {luisa.apellido} (ID: {luisa.id})")
        print(f"✅ Manuel Moreno: {manuel.nombre} {manuel.apellido} (ID: {manuel.id})")
        print(f"✅ Tipo solicitud: {tipo_solicitud.nombre} (ID: {tipo_solicitud.id})")
        
        # 2. Verificar contadores ANTES
        contador_luisa_antes = luisa.notificaciones_no_leidas_count()
        contador_manuel_antes = manuel.notificaciones_no_leidas_count()
        print(f"\n📊 Contadores ANTES:")
        print(f"  - Luisa: {contador_luisa_antes}")
        print(f"  - Manuel: {contador_manuel_antes}")
        
        # 3. Crear solicitud con los mismos datos de la interfaz web
        fecha_solicitud = date(2025, 8, 22)
        print(f"\n🔄 Creando solicitud manual...")
        print(f"  - Solicitante: {luisa.nombre}")
        print(f"  - Receptor: {manuel.nombre}")
        print(f"  - Fecha: {fecha_solicitud}")
        print(f"  - Tipo: {tipo_solicitud.nombre}")
        
        solicitud = SolicitudService.crear_solicitud_cambio(
            explorador_solicitante=luisa,
            explorador_receptor=manuel,
            tipo_cambio=tipo_solicitud,
            comentario="Prueba manual desde script",
            fecha_cambio_turno=fecha_solicitud
        )
        
        print(f"✅ Solicitud creada con ID: {solicitud.id}")
        
        # 4. Verificar notificaciones creadas
        notificaciones_creadas = Notificacion.objects.filter(solicitud=solicitud)
        print(f"📋 Total de notificaciones creadas: {notificaciones_creadas.count()}")
        
        for notif in notificaciones_creadas:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}")
            print(f"    Destinatario: {notif.destinatario.nombre} {notif.destinatario.apellido}")
            print(f"    Título: {notif.titulo[:50]}...")
            print(f"    Leída: {notif.leida}")
        
        # 5. Verificar contadores DESPUÉS
        contador_luisa_despues = luisa.notificaciones_no_leidas_count()
        contador_manuel_despues = manuel.notificaciones_no_leidas_count()
        print(f"\n📊 Contadores DESPUÉS:")
        print(f"  - Luisa: {contador_luisa_despues} (diferencia: {contador_luisa_despues - contador_luisa_antes})")
        print(f"  - Manuel: {contador_manuel_despues} (diferencia: {contador_manuel_despues - contador_manuel_antes})")
        
        # 6. Verificar que la solicitud se guardó correctamente
        solicitud_verificada = SolicitudCambio.objects.get(id=solicitud.id)
        print(f"\n🔍 Verificación de la solicitud guardada:")
        print(f"  - ID: {solicitud_verificada.id}")
        print(f"  - Solicitante: {solicitud_verificada.explorador_solicitante.nombre}")
        print(f"  - Receptor: {solicitud_verificada.explorador_receptor.nombre}")
        print(f"  - Fecha: {solicitud_verificada.fecha_cambio_turno}")
        print(f"  - Tipo: {solicitud_verificada.tipo_cambio.nombre}")
        
        if (solicitud_verificada.explorador_receptor == manuel and 
            solicitud_verificada.fecha_cambio_turno == fecha_solicitud):
            print(f"✅ ¡ÉXITO! La solicitud se guardó correctamente")
        else:
            print(f"❌ ERROR: La solicitud no se guardó con los datos correctos")
        
        print(f"\n🎯 SOLICITUD DE PRUEBA MANTENIDA (ID: {solicitud.id})")
        
    except Empleado.DoesNotExist as e:
        print(f"❌ Empleado no encontrado: {e}")
    except Exception as e:
        print(f"❌ Error general: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_manual_request() 