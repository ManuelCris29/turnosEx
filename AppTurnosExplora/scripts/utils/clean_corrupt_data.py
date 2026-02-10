#!/usr/bin/env python
"""
Script para limpiar datos corruptos en la base de datos
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio, Notificacion

def clean_corrupt_data():
    print("=== LIMPIEZA DE DATOS CORRUPTOS ===")
    
    try:
        # 1. Buscar solicitudes sin fecha_cambio_turno
        solicitudes_sin_fecha = SolicitudCambio.objects.filter(fecha_cambio_turno__isnull=True)
        print(f"🔍 Solicitudes sin fecha encontradas: {solicitudes_sin_fecha.count()}")
        
        for sol in solicitudes_sin_fecha:
            print(f"  - ID: {sol.id}")
            print(f"    Solicitante: {sol.explorador_solicitante.nombre}")
            print(f"    Receptor: {sol.explorador_receptor.nombre}")
            print(f"    Estado: {sol.estado}")
            print(f"    Fecha cambio: {sol.fecha_cambio_turno}")
            print(f"    Fecha solicitud: {sol.fecha_solicitud}")
            
            # 2. Eliminar notificaciones asociadas
            notif_solicitud = Notificacion.objects.filter(solicitud=sol)
            print(f"    Notificaciones asociadas: {notif_solicitud.count()}")
            
            # 3. Eliminar la solicitud corrupta
            print(f"    ❌ ELIMINANDO solicitud corrupta...")
            sol.delete()
            print(f"    ✅ Solicitud eliminada")
        
        # 4. Verificar que se limpió
        solicitudes_restantes = SolicitudCambio.objects.filter(fecha_cambio_turno__isnull=True)
        print(f"\n🎯 Solicitudes sin fecha restantes: {solicitudes_restantes.count()}")
        
        if solicitudes_restantes.count() == 0:
            print("✅ ¡Base de datos limpiada exitosamente!")
        else:
            print("⚠️  Aún quedan solicitudes corruptas")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    clean_corrupt_data() 