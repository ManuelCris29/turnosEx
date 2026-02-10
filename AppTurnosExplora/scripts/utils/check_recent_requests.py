#!/usr/bin/env python
"""
Script para verificar las solicitudes más recientes y encontrar la que coincide con los logs
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio, Notificacion
from empleados.models import Empleado
from datetime import date

def check_recent_requests():
    print("=== VERIFICANDO SOLICITUDES RECIENTES ===")
    
    try:
        # 1. Buscar todas las solicitudes ordenadas por ID descendente
        solicitudes = SolicitudCambio.objects.all().order_by('-id')[:10]
        print(f"📋 Últimas 10 solicitudes:")
        
        for sol in solicitudes:
            print(f"\n🔄 Solicitud ID: {sol.id}")
            print(f"  - Solicitante: {sol.explorador_solicitante.nombre} {sol.explorador_solicitante.apellido}")
            print(f"  - Receptor: {sol.explorador_receptor.nombre} {sol.explorador_receptor.apellido}")
            print(f"  - Fecha cambio: {sol.fecha_cambio_turno}")
            print(f"  - Tipo: {sol.tipo_cambio.nombre}")
            print(f"  - Estado: {sol.estado}")
            print(f"  - Fecha creación: {sol.fecha_resolucion if sol.fecha_resolucion else 'No resuelta'}")
            
            # Verificar notificaciones para esta solicitud
            notif_solicitud = Notificacion.objects.filter(solicitud=sol)
            print(f"  - Notificaciones: {notif_solicitud.count()}")
            
            for notif in notif_solicitud:
                print(f"    * {notif.destinatario.nombre}: {notif.titulo[:40]}...")
        
        # 2. Buscar específicamente solicitudes con fecha 2025-08-22
        print(f"\n🔍 Buscando solicitudes con fecha 2025-08-22:")
        solicitudes_fecha = SolicitudCambio.objects.filter(fecha_cambio_turno=date(2025, 8, 22))
        print(f"  - Encontradas: {solicitudes_fecha.count()}")
        
        for sol in solicitudes_fecha:
            print(f"  - ID: {sol.id}, Receptor: {sol.explorador_receptor.nombre}")
        
        # 3. Buscar solicitudes donde Manuel Moreno sea receptor
        print(f"\n🔍 Buscando solicitudes donde Manuel Moreno sea receptor:")
        manuel = Empleado.objects.get(email='manuel.moreno@parqueexplora.org')
        solicitudes_manuel = SolicitudCambio.objects.filter(explorador_receptor=manuel)
        print(f"  - Encontradas: {solicitudes_manuel.count()}")
        
        for sol in solicitudes_manuel:
            print(f"  - ID: {sol.id}, Fecha: {sol.fecha_cambio_turno}, Solicitante: {sol.explorador_solicitante.nombre}")
        
        # 4. Verificar si hay solicitudes sin fecha_cambio_turno
        print(f"\n🔍 Verificando solicitudes sin fecha_cambio_turno:")
        solicitudes_sin_fecha = SolicitudCambio.objects.filter(fecha_cambio_turno__isnull=True)
        print(f"  - Encontradas: {solicitudes_sin_fecha.count()}")
        
        for sol in solicitudes_sin_fecha:
            print(f"  - ID: {sol.id}, Receptor: {sol.explorador_receptor.nombre}")
        
        print(f"\n🎯 ANÁLISIS:")
        print(f"  - Los logs muestran: empleado_receptor_id=2, fecha=2025-08-22")
        print(f"  - Manuel Moreno tiene ID: {manuel.id}")
        print(f"  - Si ID=2, entonces Manuel Moreno debería ser el receptor")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    check_recent_requests() 