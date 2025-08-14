#!/usr/bin/env python
"""
Script para verificar todas las solicitudes de Luisa Perez
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio, Notificacion
from empleados.models import Empleado

def check_luisa_requests():
    print("=== VERIFICANDO SOLICITUDES DE LUISA PEREZ ===")
    
    try:
        # 1. Buscar a Luisa
        luisa = Empleado.objects.get(email='luisafernanda2330@hotmail.com')
        print(f"✅ Luisa Perez: {luisa.nombre} {luisa.apellido} (ID: {luisa.id})")
        
        # 2. Verificar solicitudes como solicitante
        solicitudes_solicitante = SolicitudCambio.objects.filter(
            explorador_solicitante=luisa
        ).order_by('-id')
        
        print(f"\n📋 Solicitudes como SOLICITANTE: {solicitudes_solicitante.count()}")
        
        for sol in solicitudes_solicitante:
            print(f"\n🔄 Solicitud ID: {sol.id}")
            print(f"  - Receptor: {sol.explorador_receptor.nombre} {sol.explorador_receptor.apellido}")
            print(f"  - Fecha cambio: {sol.fecha_cambio_turno}")
            print(f"  - Tipo: {sol.tipo_cambio.nombre}")
            print(f"  - Estado: {sol.estado}")
            print(f"  - Fecha solicitud: {sol.fecha_solicitud}")
            
            # Verificar notificaciones
            notif_solicitud = Notificacion.objects.filter(solicitud=sol)
            print(f"  - Notificaciones: {notif_solicitud.count()}")
            
            for notif in notif_solicitud:
                print(f"    * {notif.destinatario.nombre}: {notif.titulo[:40]}...")
        
        # 3. Verificar solicitudes como receptor
        solicitudes_receptor = SolicitudCambio.objects.filter(
            explorador_receptor=luisa
        ).order_by('-id')
        
        print(f"\n📋 Solicitudes como RECEPTOR: {solicitudes_receptor.count()}")
        
        for sol in solicitudes_receptor:
            print(f"\n🔄 Solicitud ID: {sol.id}")
            print(f"  - Solicitante: {sol.explorador_solicitante.nombre} {sol.explorador_solicitante.apellido}")
            print(f"  - Fecha cambio: {sol.fecha_cambio_turno}")
            print(f"  - Tipo: {sol.tipo_cambio.nombre}")
            print(f"  - Estado: {sol.estado}")
        
        # 4. Verificar notificaciones de Luisa
        notificaciones_luisa = Notificacion.objects.filter(destinatario=luisa)
        print(f"\n📋 Total de notificaciones de Luisa: {notificaciones_luisa.count()}")
        
        notificaciones_no_leidas = notificaciones_luisa.filter(leida=False)
        print(f"  - No leídas: {notificaciones_no_leidas.count()}")
        
        # 5. Contador del modelo
        contador_modelo = luisa.notificaciones_no_leidas_count()
        print(f"  - Contador del modelo: {contador_modelo}")
        
        print(f"\n🎯 RESUMEN:")
        print(f"  - Solicitudes como solicitante: {solicitudes_solicitante.count()}")
        print(f"  - Solicitudes como receptor: {solicitudes_receptor.count()}")
        print(f"  - Notificaciones totales: {notificaciones_luisa.count()}")
        print(f"  - Notificaciones no leídas: {notificaciones_no_leidas.count()}")
        print(f"  - Contador del modelo: {contador_modelo}")
        
    except Empleado.DoesNotExist:
        print("❌ Luisa Perez no encontrada")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    check_luisa_requests() 