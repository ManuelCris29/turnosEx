#!/usr/bin/env python
"""
Script de depuración específico para verificar notificaciones de Luisa Perez
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

def debug_luisa_notifications():
    print("=== DEPURACIÓN ESPECÍFICA PARA LUISA PEREZ ===")
    
    # 1. Buscar específicamente a Luisa Perez
    try:
        luisa = Empleado.objects.get(email='luisafernanda2330@hotmail.com')
        print(f"✅ Luisa Perez encontrada:")
        print(f"  - ID: {luisa.id}")
        print(f"  - Nombre: {luisa.nombre} {luisa.apellido}")
        print(f"  - Email: {luisa.email}")
        print(f"  - Supervisor: {luisa.supervisor.nombre if luisa.supervisor else 'Ninguno'}")
        
        # 2. Verificar contador actual de notificaciones
        print(f"\n2. CONTADOR ACTUAL DE NOTIFICACIONES:")
        contador_actual = luisa.notificaciones_no_leidas_count
        print(f"  - Contador actual: {contador_actual}")
        
        # 3. Verificar notificaciones existentes para Luisa
        print(f"\n3. NOTIFICACIONES EXISTENTES PARA LUISA:")
        notificaciones_luisa = Notificacion.objects.filter(destinatario=luisa)
        print(f"  - Total de notificaciones: {notificaciones_luisa.count()}")
        
        for notif in notificaciones_luisa:
            print(f"  - ID: {notif.id}, Tipo: {notif.tipo}, Leída: {notif.leida}")
            print(f"    Título: {notif.titulo[:50]}...")
            print(f"    Solicitud: {notif.solicitud.id if notif.solicitud else 'N/A'}")
        
        # 4. Verificar solicitudes donde Luisa es solicitante
        print(f"\n4. SOLICITUDES DONDE LUISA ES SOLICITANTE:")
        solicitudes_luisa = SolicitudCambio.objects.filter(explorador_solicitante=luisa)
        print(f"  - Total de solicitudes: {solicitudes_luisa.count()}")
        
        for sol in solicitudes_luisa:
            print(f"  - ID: {sol.id}, Estado: {sol.estado}")
            print(f"    Receptor: {sol.explorador_receptor.nombre} {sol.explorador_receptor.apellido}")
            print(f"    Fecha cambio: {sol.fecha_cambio_turno}")
        
        # 5. Crear una solicitud REAL donde Luisa sea la solicitante
        print(f"\n5. CREANDO SOLICITUD REAL PARA LUISA:")
        try:
            # Buscar otro empleado como receptor
            receptor = Empleado.objects.exclude(id=luisa.id).first()
            tipo_solicitud = TipoSolicitudCambio.objects.first()
            
            if receptor and tipo_solicitud:
                print(f"  - Receptor: {receptor.nombre} {receptor.apellido}")
                print(f"  - Tipo: {tipo_solicitud.nombre}")
                
                # Crear solicitud REAL
                solicitud = SolicitudService.crear_solicitud_cambio(
                    explorador_solicitante=luisa,
                    explorador_receptor=receptor,
                    tipo_cambio=tipo_solicitud,
                    comentario="Solicitud de prueba para Luisa Perez",
                    fecha_cambio_turno=date(2025, 8, 20)
                )
                
                print(f"  ✅ Solicitud creada con ID: {solicitud.id}")
                
                # Verificar notificaciones creadas
                notif_count = Notificacion.objects.filter(solicitud=solicitud).count()
                print(f"  ✅ Notificaciones creadas: {notif_count}")
                
                # Verificar contador DESPUÉS de crear la solicitud
                print(f"\n6. CONTADOR DESPUÉS DE CREAR SOLICITUD:")
                contador_despues = luisa.notificaciones_no_leidas_count
                print(f"  - Contador antes: {contador_actual}")
                print(f"  - Contador después: {contador_despues}")
                print(f"  - Diferencia: {contador_despues - contador_actual}")
                
                # Verificar notificaciones específicas para Luisa
                notificaciones_nuevas = Notificacion.objects.filter(
                    destinatario=luisa,
                    solicitud=solicitud
                )
                print(f"  - Notificaciones nuevas para Luisa: {notificaciones_nuevas.count()}")
                
                for notif in notificaciones_nuevas:
                    print(f"    - ID: {notif.id}, Tipo: {notif.tipo}, Leída: {notif.leida}")
                    print(f"      Título: {notif.titulo}")
                
                # NO eliminar esta solicitud - es una solicitud REAL para testing
                print(f"\n  📝 SOLICITUD MANTENIDA PARA TESTING (ID: {solicitud.id})")
                
            else:
                print("  ❌ No hay suficientes datos para crear solicitud")
                
        except Exception as e:
            print(f"  ❌ Error creando solicitud: {e}")
            import traceback
            print(f"  Traceback: {traceback.format_exc()}")
        
    except Empleado.DoesNotExist:
        print("❌ Luisa Perez no encontrada en la base de datos")
    except Exception as e:
        print(f"❌ Error general: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    debug_luisa_notifications() 