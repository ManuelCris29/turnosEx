#!/usr/bin/env python
"""
Script para eliminar la solicitud corrupta ID 10 y verificar que se pueda crear una nueva
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio, Notificacion
from empleados.models import Empleado

def fix_solicitud_10():
    print("=== ARREGLANDO SOLICITUD CORRUPTA ID 10 ===")
    
    try:
        # 1. Buscar la solicitud ID 10
        solicitud_10 = SolicitudCambio.objects.get(id=10)
        print(f"🔍 Solicitud ID 10 encontrada:")
        print(f"  - Solicitante: {solicitud_10.explorador_solicitante.nombre}")
        print(f"  - Receptor: {solicitud_10.explorador_receptor.nombre}")
        print(f"  - Fecha: {solicitud_10.fecha_cambio_turno}")
        print(f"  - Estado: {solicitud_10.estado}")
        print(f"  - Notificaciones: {Notificacion.objects.filter(solicitud=solicitud_10).count()}")
        
        # 2. Eliminar la solicitud corrupta
        print(f"\n❌ ELIMINANDO solicitud corrupta ID 10...")
        solicitud_10.delete()
        print(f"✅ Solicitud eliminada")
        
        # 3. Verificar que se eliminó
        try:
            SolicitudCambio.objects.get(id=10)
            print(f"❌ ERROR: La solicitud ID 10 aún existe")
        except SolicitudCambio.DoesNotExist:
            print(f"✅ Solicitud ID 10 eliminada correctamente")
        
        # 4. Verificar solicitudes restantes de Luisa
        luisa = Empleado.objects.get(email='luisafernanda2330@hotmail.com')
        solicitudes_luisa = SolicitudCambio.objects.filter(explorador_solicitante=luisa)
        print(f"\n📋 Solicitudes restantes de Luisa: {solicitudes_luisa.count()}")
        
        for sol in solicitudes_luisa:
            print(f"  - ID: {sol.id}, Receptor: {sol.explorador_receptor.nombre}, Fecha: {sol.fecha_cambio_turno}")
        
        print(f"\n🎯 AHORA PUEDES CREAR UNA NUEVA SOLICITUD para 2025-08-27")
        
    except SolicitudCambio.DoesNotExist:
        print(f"✅ La solicitud ID 10 ya no existe")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    fix_solicitud_10() 