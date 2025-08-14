#!/usr/bin/env python
"""
Script para verificar el estado actual de las notificaciones de Luisa Perez
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from empleados.models import Empleado
from solicitudes.models import Notificacion, SolicitudCambio

def check_luisa_status():
    print("=== VERIFICANDO ESTADO ACTUAL DE LUISA PEREZ ===")
    
    try:
        # 1. Buscar a Luisa Perez
        luisa = Empleado.objects.get(email='luisafernanda2330@hotmail.com')
        print(f"✅ Luisa Perez: {luisa.nombre} {luisa.apellido}")
        
        # 2. Verificar contador actual
        contador_actual = luisa.notificaciones_no_leidas_count()
        print(f"📊 Contador actual: {contador_actual}")
        
        # 3. Verificar todas las notificaciones para Luisa
        notificaciones_luisa = Notificacion.objects.filter(destinatario=luisa)
        print(f"📋 Total de notificaciones: {notificaciones_luisa.count()}")
        
        for notif in notificaciones_luisa:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}, Leída: {notif.leida}")
            print(f"    Título: {notif.titulo}")
            if notif.solicitud:
                print(f"    Solicitud: {notif.solicitud.id}")
        
        # 4. Verificar solicitudes donde Luisa es solicitante
        solicitudes_luisa = SolicitudCambio.objects.filter(explorador_solicitante=luisa)
        print(f"\n🔄 Solicitudes donde Luisa es solicitante: {solicitudes_luisa.count()}")
        
        for sol in solicitudes_luisa:
            print(f"  - ID: {sol.id}, Estado: {sol.estado}")
            print(f"    Receptor: {sol.explorador_receptor.nombre} {sol.explorador_receptor.apellido}")
            print(f"    Fecha cambio: {sol.fecha_cambio_turno}")
        
        # 5. Verificar notificaciones no leídas específicamente
        notificaciones_no_leidas = Notificacion.objects.filter(
            destinatario=luisa, 
            leida=False
        )
        print(f"\n🔴 Notificaciones NO leídas: {notificaciones_no_leidas.count()}")
        
        for notif in notificaciones_no_leidas:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}")
            print(f"    Título: {notif.titulo}")
            if notif.solicitud:
                print(f"    Solicitud: {notif.solicitud.id}")
        
        print(f"\n🎯 RESUMEN:")
        print(f"  - Contador del modelo: {contador_actual}")
        print(f"  - Notificaciones totales: {notificaciones_luisa.count()}")
        print(f"  - Notificaciones no leídas: {notificaciones_no_leidas.count()}")
        
        if contador_actual == notificaciones_no_leidas.count():
            print(f"✅ El contador está funcionando correctamente")
        else:
            print(f"❌ HAY UNA DISCREPANCIA en el contador")
            
    except Empleado.DoesNotExist:
        print("❌ Luisa Perez no encontrada")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    check_luisa_status() 