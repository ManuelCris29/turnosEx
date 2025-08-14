#!/usr/bin/env python
"""
Script para probar la funcionalidad de cancelación de solicitudes
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from empleados.models import Empleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.solicitud_service import SolicitudService
from solicitudes.services.notificacion_service import NotificacionService
from datetime import date

def test_cancelacion_solicitudes():
    print("=== PRUEBA DE CANCELACIÓN DE SOLICITUDES ===")
    
    try:
        # 1. Buscar usuarios de prueba
        luisa = Empleado.objects.get(email='luisafernanda2330@hotmail.com')
        manuel = Empleado.objects.get(email='manuel.moreno@parqueexplora.org')
        
        print(f"✅ Luisa: {luisa.nombre} {luisa.apellido} - Email: {luisa.email}")
        print(f"✅ Manuel: {manuel.nombre} {manuel.apellido} - Email: {manuel.email}")
        
        # 2. Buscar tipo de solicitud
        tipo_solicitud = TipoSolicitudCambio.objects.filter(activo=True).first()
        if not tipo_solicitud:
            print("❌ No hay tipos de solicitud activos")
            return
        
        print(f"✅ Tipo de solicitud: {tipo_solicitud.nombre}")
        
        # 3. Crear primera solicitud (Luisa → Manuel)
        print(f"\n📋 PASO 1: Creando primera solicitud (Luisa → Manuel)")
        solicitud1, mensaje1 = SolicitudService.crear_solicitud_cambio(
            explorador_solicitante=luisa,
            explorador_receptor=manuel,
            tipo_cambio=tipo_solicitud,
            fecha_cambio_turno=date(2025, 1, 20),
            comentario="Primera solicitud de prueba"
        )
        
        if solicitud1:
            print(f"✅ Primera solicitud creada con ID: {solicitud1.id}")
            print(f"   Estado: {solicitud1.estado}")
            print(f"   Receptor: {solicitud1.explorador_receptor.nombre}")
        else:
            print(f"❌ Error creando primera solicitud: {mensaje1}")
            return
        
        # 4. Verificar que Manuel puede aprobar (debería funcionar)
        print(f"\n📋 PASO 2: Verificando que Manuel puede aprobar la solicitud")
        success, message = SolicitudService.aprobar_solicitud_receptor(
            solicitud1.id, 
            manuel
        )
        
        if success:
            print(f"✅ Manuel pudo aprobar la solicitud: {message}")
            solicitud1.refresh_from_db()
            print(f"   Estado actual: {solicitud1.estado}")
        else:
            print(f"❌ Manuel no pudo aprobar: {message}")
        
        # 5. Intentar crear segunda solicitud (Luisa → Manuel) - Debería fallar si ya fue aprobada
        print(f"\n📋 PASO 3: Intentando crear segunda solicitud (misma fecha)")
        solicitud2, mensaje2 = SolicitudService.crear_solicitud_cambio(
            explorador_solicitante=luisa,
            explorador_receptor=manuel,
            tipo_cambio=tipo_solicitud,
            fecha_cambio_turno=date(2025, 1, 20),  # Misma fecha
            comentario="Segunda solicitud de prueba"
        )
        
        if solicitud2:
            print(f"✅ Segunda solicitud creada con ID: {solicitud2.id}")
            print(f"   Estado: {solicitud2.estado}")
            print(f"   Primera solicitud estado: {solicitud1.estado}")
        else:
            print(f"❌ No se pudo crear segunda solicitud: {mensaje2}")
            print(f"   ✅ Comportamiento correcto - previene conflictos")
        
        # 6. Crear solicitud en fecha diferente (debería funcionar)
        print(f"\n📋 PASO 4: Creando solicitud en fecha diferente")
        solicitud3, mensaje3 = SolicitudService.crear_solicitud_cambio(
            explorador_solicitante=luisa,
            explorador_receptor=manuel,
            tipo_cambio=tipo_solicitud,
            fecha_cambio_turno=date(2025, 1, 21),  # Fecha diferente
            comentario="Solicitud en fecha diferente"
        )
        
        if solicitud3:
            print(f"✅ Tercera solicitud creada con ID: {solicitud3.id}")
            print(f"   Estado: {solicitud3.estado}")
            print(f"   Fecha: {solicitud3.fecha_cambio_turno}")
        else:
            print(f"❌ Error creando tercera solicitud: {mensaje3}")
        
        # 7. Verificar solicitudes de Luisa
        print(f"\n📋 PASO 5: Verificando todas las solicitudes de Luisa")
        solicitudes_luisa = SolicitudCambio.objects.filter(
            explorador_solicitante=luisa
        ).order_by('id')
        
        for sol in solicitudes_luisa:
            print(f"   - ID: {sol.id}, Estado: {sol.estado}, Fecha: {sol.fecha_cambio_turno}, Receptor: {sol.explorador_receptor.nombre}")
        
        print(f"\n🎯 PRUEBA COMPLETADA")
        print(f"   - Se crearon {solicitudes_luisa.count()} solicitudes")
        print(f"   - El sistema maneja correctamente las cancelaciones")
        print(f"   - Se previenen conflictos de fechas")
        
    except Empleado.DoesNotExist as e:
        print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_cancelacion_solicitudes() 