#!/usr/bin/env python
"""
Script para crear una solicitud REAL donde Luisa Perez sea la solicitante
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

def create_luisa_request():
    print("=== CREANDO SOLICITUD REAL PARA LUISA PEREZ ===")
    
    try:
        # 1. Buscar a Luisa Perez
        luisa = Empleado.objects.get(user__email='luisafernanda2330@hotmail.com')
        print(f"✅ Luisa Perez encontrada: {luisa.nombre} {luisa.apellido}")
        
        # 2. Buscar un receptor (que no sea Luisa)
        receptor = Empleado.objects.exclude(id=luisa.id).first()
        print(f"✅ Receptor: {receptor.nombre} {receptor.apellido}")
        
        # 3. Buscar tipo de solicitud
        tipo_solicitud = TipoSolicitudCambio.objects.first()
        print(f"✅ Tipo: {tipo_solicitud.nombre}")
        
        # 4. Verificar contador ANTES
        contador_antes = luisa.notificaciones_no_leidas_count()
        print(f"📊 Contador ANTES: {contador_antes}")
        
        # 5. Crear solicitud REAL
        print(f"\n🔄 Creando solicitud...")
        solicitud = SolicitudService.crear_solicitud_cambio(
            explorador_solicitante=luisa,
            explorador_receptor=receptor,
            tipo_cambio=tipo_solicitud,
            comentario="Solicitud de prueba para verificar notificaciones",
            fecha_cambio_turno=date(2025, 8, 25)
        )
        
        print(f"✅ Solicitud creada con ID: {solicitud.id}")
        
        # 6. Verificar notificaciones creadas
        notificaciones_creadas = Notificacion.objects.filter(solicitud=solicitud)
        print(f"📋 Notificaciones creadas: {notificaciones_creadas.count()}")
        
        for notif in notificaciones_creadas:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}")
            print(f"    Destinatario: {notif.destinatario.nombre} {notif.destinatario.apellido}")
            print(f"    Título: {notif.titulo}")
            print(f"    Leída: {notif.leida}")
        
        # 7. Verificar contador DESPUÉS
        contador_despues = luisa.notificaciones_no_leidas_count()
        print(f"\n📊 Contador DESPUÉS: {contador_despues}")
        print(f"📊 Diferencia: {contador_despues - contador_antes}")
        
        # 8. Verificar notificaciones específicas para Luisa
        notificaciones_luisa = Notificacion.objects.filter(
            destinatario=luisa,
            solicitud=solicitud
        )
        print(f"\n🔍 Notificaciones para Luisa: {notificaciones_luisa.count()}")
        
        for notif in notificaciones_luisa:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}")
            print(f"    Título: {notif.titulo}")
            print(f"    Leída: {notif.leida}")
        
        print(f"\n🎯 SOLICITUD MANTENIDA PARA TESTING (ID: {solicitud.id})")
        print(f"🎯 Ahora deberías ver el contador actualizado en la interfaz web")
        
    except Empleado.DoesNotExist:
        print("❌ Luisa Perez no encontrada")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    create_luisa_request() 