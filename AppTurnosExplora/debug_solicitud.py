#!/usr/bin/env python
"""
Script de depuración para verificar el flujo completo de solicitudes
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
from solicitudes.services.notificacion_service import NotificacionService

def debug_solicitud():
    print("=== DEPURACIÓN DE SOLICITUDES ===")
    
    # 1. Verificar empleados
    print("\n1. EMPLEADOS:")
    empleados = Empleado.objects.all()
    for emp in empleados:
        print(f"  - {emp.nombre} {emp.apellido} (ID: {emp.id}, Email: {emp.email}, Supervisor: {emp.supervisor.nombre if emp.supervisor else 'Ninguno'})")
    
    # 2. Verificar tipos de solicitud
    print("\n2. TIPOS DE SOLICITUD:")
    tipos = TipoSolicitudCambio.objects.all()
    for tipo in tipos:
        print(f"  - {tipo.nombre} (ID: {tipo.id}, Activo: {tipo.activo})")
    
    # 3. Verificar solicitudes existentes
    print("\n3. SOLICITUDES EXISTENTES:")
    solicitudes = SolicitudCambio.objects.all()
    for sol in solicitudes:
        print(f"  - ID: {sol.id}, Estado: {sol.estado}, Fecha solicitud: {sol.fecha_solicitud}, Fecha cambio: {sol.fecha_cambio_turno}")
        print(f"    Solicitante: {sol.explorador_solicitante.nombre} {sol.explorador_solicitante.apellido}")
        print(f"    Receptor: {sol.explorador_receptor.nombre} {sol.explorador_receptor.apellido}")
    
    # 4. Verificar notificaciones existentes
    print("\n4. NOTIFICACIONES EXISTENTES:")
    notificaciones = Notificacion.objects.all()
    for notif in notificaciones:
        print(f"  - ID: {notif.id}, Tipo: {notif.tipo}, Leída: {notif.leida}")
        print(f"    Destinatario: {notif.destinatario.nombre} {notif.destinatario.apellido}")
        print(f"    Título: {notif.titulo[:50]}...")
    
    # 5. Probar creación de solicitud
    print("\n5. PRUEBA DE CREACIÓN DE SOLICITUD:")
    try:
        empleado1 = Empleado.objects.first()
        empleado2 = Empleado.objects.exclude(id=empleado1.id).first()
        tipo_solicitud = TipoSolicitudCambio.objects.first()
        
        if empleado1 and empleado2 and tipo_solicitud:
            print(f"  - Empleado 1: {empleado1.nombre} {empleado1.apellido}")
            print(f"  - Empleado 2: {empleado2.nombre} {empleado2.apellido}")
            print(f"  - Tipo: {tipo_solicitud.nombre}")
            
            # Crear solicitud
            solicitud = SolicitudService.crear_solicitud_cambio(
                explorador_solicitante=empleado1,
                explorador_receptor=empleado2,
                tipo_cambio=tipo_solicitud,
                comentario="Prueba de depuración",
                fecha_cambio_turno=date(2025, 8, 15)
            )
            
            print(f"  ✅ Solicitud creada con ID: {solicitud.id}")
            print(f"  ✅ Fecha cambio turno: {solicitud.fecha_cambio_turno}")
            
            # Verificar notificaciones creadas
            notif_count = Notificacion.objects.filter(solicitud=solicitud).count()
            print(f"  ✅ Notificaciones creadas: {notif_count}")
            
            # Limpiar datos de prueba
            solicitud.delete()
            print("  🧹 Datos de prueba eliminados")
            
        else:
            print("  ❌ No hay suficientes datos para la prueba")
            
    except Exception as e:
        print(f"  ❌ Error en prueba: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    debug_solicitud() 