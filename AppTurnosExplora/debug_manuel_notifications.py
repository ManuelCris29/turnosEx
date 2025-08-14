#!/usr/bin/env python
"""
Script para verificar las notificaciones de Manuel Moreno y diagnosticar problemas
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from empleados.models import Empleado
from solicitudes.models import Notificacion, SolicitudCambio
from solicitudes.services.notificacion_service import NotificacionService

def debug_manuel_notifications():
    print("=== DEPURACIÓN DE NOTIFICACIONES DE MANUEL MORENO ===")
    
    try:
        # 1. Buscar a Manuel Moreno
        manuel = Empleado.objects.get(email='manuel.moreno@parqueexplora.org')
        print(f"✅ Manuel Moreno encontrado: {manuel.nombre} {manuel.apellido}")
        print(f"  - ID: {manuel.id}")
        print(f"  - Email: {manuel.email}")
        print(f"  - Supervisor: {manuel.supervisor.nombre if manuel.supervisor else 'Ninguno'}")
        
        # 2. Verificar contador actual
        contador_actual = manuel.notificaciones_no_leidas_count()
        print(f"📊 Contador actual: {contador_actual}")
        
        # 3. Verificar notificaciones existentes
        notificaciones_manuel = Notificacion.objects.filter(destinatario=manuel)
        print(f"📋 Total de notificaciones: {notificaciones_manuel.count()}")
        
        for notif in notificaciones_manuel:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}, Leída: {notif.leida}")
            print(f"    Título: {notif.titulo[:50]}...")
            if notif.solicitud:
                print(f"    Solicitud: {notif.solicitud.id}")
        
        # 4. Verificar solicitudes donde Manuel es receptor
        solicitudes_manuel_receptor = SolicitudCambio.objects.filter(explorador_receptor=manuel)
        print(f"\n🔄 Solicitudes donde Manuel es receptor: {solicitudes_manuel_receptor.count()}")
        
        for sol in solicitudes_manuel_receptor:
            print(f"  - ID: {sol.id}, Estado: {sol.estado}")
            print(f"    Solicitante: {sol.explorador_solicitante.nombre} {sol.explorador_solicitante.apellido}")
            print(f"    Fecha cambio: {sol.fecha_cambio_turno}")
            print(f"    Tipo: {sol.tipo_cambio.nombre}")
        
        # 5. Verificar solicitudes donde Manuel es supervisor
        solicitudes_manuel_supervisor = SolicitudCambio.objects.filter(
            explorador_solicitante__supervisor=manuel
        )
        print(f"\n👨‍💼 Solicitudes donde Manuel es supervisor: {solicitudes_manuel_supervisor.count()}")
        
        for sol in solicitudes_manuel_supervisor:
            print(f"  - ID: {sol.id}, Estado: {sol.estado}")
            print(f"    Solicitante: {sol.explorador_solicitante.nombre} {sol.explorador_solicitante.apellido}")
            print(f"    Receptor: {sol.explorador_receptor.nombre} {sol.explorador_receptor.apellido}")
            print(f"    Fecha cambio: {sol.fecha_cambio_turno}")
        
        # 6. Verificar notificaciones no leídas específicamente
        notificaciones_no_leidas = Notificacion.objects.filter(
            destinatario=manuel, 
            leida=False
        )
        print(f"\n🔴 Notificaciones NO leídas: {notificaciones_no_leidas.count()}")
        
        for notif in notificaciones_no_leidas:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}")
            print(f"    Título: {notif.titulo}")
            if notif.solicitud:
                print(f"    Solicitud: {notif.solicitud.id}")
        
        # 7. Verificar la solicitud más reciente (ID 8 según los logs)
        try:
            solicitud_reciente = SolicitudCambio.objects.get(id=8)
            print(f"\n🔍 SOLICITUD RECIENTE (ID 8):")
            print(f"  - Solicitante: {solicitud_reciente.explorador_solicitante.nombre}")
            print(f"  - Receptor: {solicitud_reciente.explorador_receptor.nombre}")
            print(f"  - Supervisor del solicitante: {solicitud_reciente.explorador_solicitante.supervisor.nombre if solicitud_reciente.explorador_solicitante.supervisor else 'Ninguno'}")
            print(f"  - Fecha: {solicitud_reciente.fecha_cambio_turno}")
            
            # Verificar notificaciones para esta solicitud
            notif_solicitud = Notificacion.objects.filter(solicitud=solicitud_reciente)
            print(f"  - Notificaciones creadas: {notif_solicitud.count()}")
            
            for notif in notif_solicitud:
                print(f"    - Destinatario: {notif.destinatario.nombre}, Tipo: {notif.tipo}")
                
        except SolicitudCambio.DoesNotExist:
            print(f"❌ Solicitud ID 8 no encontrada")
        
        print(f"\n🎯 RESUMEN:")
        print(f"  - Contador del modelo: {contador_actual}")
        print(f"  - Notificaciones totales: {notificaciones_manuel.count()}")
        print(f"  - Notificaciones no leídas: {notificaciones_no_leidas.count()}")
        
        if contador_actual == notificaciones_no_leidas.count():
            print(f"✅ El contador está funcionando correctamente")
        else:
            print(f"❌ HAY UNA DISCREPANCIA en el contador")
            
    except Empleado.DoesNotExist:
        print("❌ Manuel Moreno no encontrado")
    except Exception as e:
        print(f"❌ Error general: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    debug_manuel_notifications() 