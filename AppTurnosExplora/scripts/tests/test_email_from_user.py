#!/usr/bin/env python
"""
Script para probar el envío de emails desde el correo del usuario logueado
"""
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from empleados.models import Empleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.email_service import EmailService
from datetime import date

def test_email_from_user():
    print("=== PRUEBA DE EMAIL DESDE USUARIO LOGUEADO ===")
    
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
        
        # 3. Crear una solicitud de prueba
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=luisa,
            explorador_receptor=manuel,
            tipo_cambio=tipo_solicitud,
            fecha_cambio_turno=date(2025, 1, 15),
            comentario="Prueba de email desde usuario logueado"
        )
        
        print(f"✅ Solicitud creada con ID: {solicitud.id}")
        print(f"   Solicitante: {solicitud.explorador_solicitante.email}")
        print(f"   Receptor: {solicitud.explorador_receptor.email}")
        
        # 4. Probar envío de emails
        print(f"\n📧 Probando envío de emails desde {luisa.email}...")
        
        # Email al receptor
        print("   - Enviando email al receptor...")
        EmailService._enviar_email_receptor(solicitud)
        
        # Email al supervisor (si existe)
        if luisa.supervisor:
            print("   - Enviando email al supervisor...")
            EmailService._enviar_email_supervisor(solicitud)
        else:
            print("   - No hay supervisor asignado")
        
        # Email de confirmación al solicitante
        print("   - Enviando email de confirmación al solicitante...")
        EmailService._enviar_email_solicitante(solicitud)
        
        print(f"\n✅ Prueba completada. Verifica los emails recibidos.")
        print(f"   Los emails deberían aparecer como enviados desde: {luisa.email}")
        
        # 5. Limpiar solicitud de prueba
        solicitud.delete()
        print(f"✅ Solicitud de prueba eliminada")
        
    except Empleado.DoesNotExist as e:
        print(f"❌ Error: {e}")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    test_email_from_user() 