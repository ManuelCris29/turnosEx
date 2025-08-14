#!/usr/bin/env python
"""
Script para probar la nueva funcionalidad de notificaciones para el solicitante
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

def test_new_notification():
    print("=== PROBANDO NUEVA FUNCIONALIDAD DE NOTIFICACIONES ===")
    
    try:
        # 1. Buscar a Luisa Perez
        luisa = Empleado.objects.get(email='luisafernanda2330@hotmail.com')
        print(f"✅ Luisa Perez: {luisa.nombre} {luisa.apellido}")
        
        # 2. Verificar contador ANTES
        contador_antes = luisa.notificaciones_no_leidas_count()
        print(f"📊 Contador ANTES: {contador_antes}")
        
        # 3. Verificar notificaciones existentes
        notificaciones_existentes = Notificacion.objects.filter(destinatario=luisa).count()
        print(f"📋 Notificaciones existentes: {notificaciones_existentes}")
        
        # 4. Crear nueva solicitud para probar
        receptor = Empleado.objects.exclude(id=luisa.id).first()
        tipo_solicitud = TipoSolicitudCambio.objects.first()
        
        print(f"\n🔄 Creando nueva solicitud de prueba...")
        solicitud = SolicitudService.crear_solicitud_cambio(
            explorador_solicitante=luisa,
            explorador_receptor=receptor,
            tipo_cambio=tipo_solicitud,
            comentario="Prueba de nueva funcionalidad de notificaciones",
            fecha_cambio_turno=date(2025, 8, 30)
        )
        
        print(f"✅ Solicitud creada con ID: {solicitud.id}")
        
        # 5. Verificar notificaciones creadas
        notificaciones_creadas = Notificacion.objects.filter(solicitud=solicitud)
        print(f"📋 Total de notificaciones creadas: {notificaciones_creadas.count()}")
        
        for notif in notificaciones_creadas:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}")
            print(f"    Destinatario: {notif.destinatario.nombre} {notif.destinatario.apellido}")
            print(f"    Título: {notif.titulo[:50]}...")
            print(f"    Leída: {notif.leida}")
        
        # 6. Verificar notificaciones específicas para Luisa
        notificaciones_luisa = Notificacion.objects.filter(
            destinatario=luisa,
            solicitud=solicitud
        )
        print(f"\n🔍 Notificaciones para Luisa: {notificaciones_luisa.count()}")
        
        for notif in notificaciones_luisa:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}")
            print(f"    Título: {notif.titulo}")
            print(f"    Leída: {notif.leida}")
        
        # 7. Verificar contador DESPUÉS
        contador_despues = luisa.notificaciones_no_leidas_count()
        print(f"\n📊 Contador DESPUÉS: {contador_despues}")
        print(f"📊 Diferencia: {contador_despues - contador_antes}")
        
        # 8. Verificar todas las notificaciones de Luisa
        todas_notificaciones = Notificacion.objects.filter(destinatario=luisa)
        print(f"\n📋 Total de notificaciones de Luisa: {todas_notificaciones.count()}")
        
        if contador_despues > contador_antes:
            print(f"✅ ¡ÉXITO! El contador se actualizó correctamente")
            print(f"✅ Luisa ahora tiene notificaciones y el contador funciona")
        else:
            print(f"❌ El contador no se actualizó")
        
        print(f"\n🎯 SOLICITUD DE PRUEBA MANTENIDA (ID: {solicitud.id})")
        
    except Empleado.DoesNotExist:
        print("❌ Luisa Perez no encontrada")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_new_notification() 