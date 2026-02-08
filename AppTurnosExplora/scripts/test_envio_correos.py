"""
Script para probar el envío de correos cuando se crea una solicitud.
Este script ayuda a diagnosticar problemas con el sistema de notificaciones.
"""
import os
import sys
import django

# Configurar Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.conf import settings
from django.core.mail import send_mail
from solicitudes.models import SolicitudCambio
from empleados.models import Empleado
from solicitudes.services.notificacion_service import NotificacionService
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_configuracion_email():
    """Verifica la configuración de email"""
    print("\n" + "="*60)
    print("1. VERIFICANDO CONFIGURACIÓN DE EMAIL")
    print("="*60)
    
    print(f"EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
    print(f"EMAIL_HOST: {settings.EMAIL_HOST}")
    print(f"EMAIL_PORT: {settings.EMAIL_PORT}")
    print(f"EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
    print(f"EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
    print(f"EMAIL_HOST_PASSWORD: {'*' * len(settings.EMAIL_HOST_PASSWORD) if settings.EMAIL_HOST_PASSWORD else 'NO CONFIGURADO'}")
    print(f"DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")
    print(f"SITE_URL: {settings.SITE_URL}")
    
    if settings.EMAIL_BACKEND == 'django.core.mail.backends.console.EmailBackend':
        print("\n⚠️  MODO DESARROLLO: Los emails se mostrarán en la consola")
    else:
        print("\n✅ MODO PRODUCCIÓN: Los emails se enviarán por SMTP")

def test_envio_email_simple():
    """Prueba el envío de un email simple"""
    print("\n" + "="*60)
    print("2. PROBANDO ENVÍO DE EMAIL SIMPLE")
    print("="*60)
    
    try:
        resultado = send_mail(
            subject='Test de Email - Sistema de Turnos',
            message='Este es un email de prueba para verificar la configuración.',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.DEFAULT_FROM_EMAIL],  # Enviar a sí mismo para prueba
            fail_silently=False,
        )
        if resultado:
            print("✅ Email simple enviado exitosamente")
        else:
            print("❌ Email simple no se pudo enviar (retornó False)")
    except Exception as e:
        print(f"❌ Error enviando email simple: {e}")
        import traceback
        traceback.print_exc()

def test_emails_empleados():
    """Verifica que los empleados tengan emails válidos"""
    print("\n" + "="*60)
    print("3. VERIFICANDO EMAILS DE EMPLEADOS")
    print("="*60)
    
    empleados = Empleado.objects.all()[:10]  # Primeros 10 para no saturar
    
    sin_email = []
    con_email = []
    
    for empleado in empleados:
        if not empleado.email or not empleado.email.strip():
            sin_email.append(empleado)
            print(f"❌ {empleado.nombre} {empleado.apellido}: SIN EMAIL")
        else:
            con_email.append(empleado)
            print(f"✅ {empleado.nombre} {empleado.apellido}: {empleado.email}")
    
    print(f"\nResumen: {len(con_email)} con email, {len(sin_email)} sin email")
    
    if sin_email:
        print("\n⚠️  ADVERTENCIA: Hay empleados sin email configurado")
        print("   Estos empleados no recibirán notificaciones por correo")

def test_solicitud_reciente():
    """Prueba el envío de notificaciones para una solicitud reciente"""
    print("\n" + "="*60)
    print("4. PROBANDO NOTIFICACIONES PARA SOLICITUD RECIENTE")
    print("="*60)
    
    # Buscar la solicitud más reciente
    solicitud = SolicitudCambio.objects.select_related(
        'explorador_solicitante',
        'explorador_receptor',
        'tipo_cambio'
    ).order_by('-fecha_solicitud').first()
    
    if not solicitud:
        print("❌ No se encontraron solicitudes en la base de datos")
        return
    
    print(f"Solicitud encontrada: ID={solicitud.id}")
    print(f"Tipo: {solicitud.tipo_cambio.nombre}")
    print(f"Solicitante: {solicitud.explorador_solicitante.nombre} {solicitud.explorador_solicitante.apellido}")
    print(f"  Email: {solicitud.explorador_solicitante.email or 'NO CONFIGURADO'}")
    print(f"Receptor: {solicitud.explorador_receptor.nombre} {solicitud.explorador_receptor.apellido}")
    print(f"  Email: {solicitud.explorador_receptor.email or 'NO CONFIGURADO'}")
    
    supervisor = solicitud.explorador_solicitante.supervisor
    if supervisor:
        print(f"Supervisor: {supervisor.nombre} {supervisor.apellido}")
        print(f"  Email: {supervisor.email or 'NO CONFIGURADO'}")
    else:
        print("Supervisor: No asignado")
    
    print("\nIntentando enviar notificaciones...")
    try:
        NotificacionService.crear_notificacion_solicitud(solicitud)
        print("✅ Proceso de notificaciones completado (revisar logs para detalles)")
    except Exception as e:
        print(f"❌ Error en proceso de notificaciones: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Función principal"""
    print("\n" + "="*60)
    print("DIAGNÓSTICO DE ENVÍO DE CORREOS")
    print("="*60)
    
    test_configuracion_email()
    test_envio_email_simple()
    test_emails_empleados()
    test_solicitud_reciente()
    
    print("\n" + "="*60)
    print("DIAGNÓSTICO COMPLETADO")
    print("="*60)
    print("\nRevisa los logs anteriores para identificar problemas.")
    print("Si hay errores, verifica:")
    print("  1. Configuración SMTP en settings.py")
    print("  2. Credenciales de email (usuario/contraseña)")
    print("  3. Que los empleados tengan emails configurados")
    print("  4. Que los templates de email existan")
    print("  5. Logs del servidor Django para más detalles")

if __name__ == '__main__':
    main()


