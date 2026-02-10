"""
Comando de management para verificar la integridad de solicitudes de doblada.
Detecta solicitudes aprobadas sin turnos generados correctamente.

Uso:
    python manage.py verificar_integridad_dobladas
    python manage.py verificar_integridad_dobladas --reparar
    python manage.py verificar_integridad_dobladas --email admin@example.com
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from solicitudes.models import SolicitudCambio, DobladaDetalle
from turnos.models import Turno
from empleados.models import Empleado
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Verifica la integridad de solicitudes de doblada aprobadas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reparar',
            action='store_true',
            help='Intenta reparar automáticamente las inconsistencias detectadas',
        )
        parser.add_argument(
            '--email',
            type=str,
            help='Envía un reporte por email a la dirección especificada',
        )
        parser.add_argument(
            '--dias',
            type=int,
            default=90,
            help='Número de días hacia atrás para verificar (default: 90)',
        )

    def handle(self, *args, **options):
        reparar = options['reparar']
        email_destino = options['email']
        dias = options['dias']
        
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('VERIFICACIÓN DE INTEGRIDAD DE DOBLADAS'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        
        # Calcular fecha límite
        fecha_limite = timezone.now().date() - timedelta(days=dias)
        
        self.stdout.write(f"\n📅 Verificando solicitudes desde: {fecha_limite}")
        self.stdout.write(f"🔧 Modo reparación: {'SÍ' if reparar else 'NO'}")
        
        # Buscar solicitudes de doblada aprobadas
        solicitudes_aprobadas = SolicitudCambio.objects.filter(
            tipo_cambio__nombre='DOBLADA',
            estado='aprobada',
            fecha_cambio_turno__gte=fecha_limite
        ).select_related(
            'explorador_solicitante',
            'explorador_receptor',
            'tipo_cambio'
        ).prefetch_related('doblada')
        
        total = solicitudes_aprobadas.count()
        self.stdout.write(f"\n📊 Total de solicitudes aprobadas: {total}")
        
        # Verificar cada solicitud
        inconsistencias = []
        
        for solicitud in solicitudes_aprobadas:
            problema = self.verificar_solicitud(solicitud)
            if problema:
                inconsistencias.append((solicitud, problema))
        
        # Reporte
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("RESULTADOS")
        self.stdout.write("=" * 80)
        
        if not inconsistencias:
            self.stdout.write(self.style.SUCCESS("\n✅ No se encontraron inconsistencias"))
        else:
            self.stdout.write(self.style.ERROR(f"\n❌ Se encontraron {len(inconsistencias)} inconsistencia(s):\n"))
            
            for i, (solicitud, problema) in enumerate(inconsistencias, 1):
                self.stdout.write(f"\n{i}. Solicitud ID: {solicitud.id}")
                self.stdout.write(f"   Solicitante: {solicitud.explorador_solicitante.nombre}")
                self.stdout.write(f"   Receptor: {solicitud.explorador_receptor.nombre if solicitud.explorador_receptor else 'N/A'}")
                self.stdout.write(f"   Fecha cesión: {solicitud.fecha_cambio_turno}")
                self.stdout.write(self.style.ERROR(f"   Problema: {problema}"))
                
                # Intentar reparar si está habilitado
                if reparar:
                    self.stdout.write(f"   🔧 Intentando reparar...")
                    resultado = self.reparar_solicitud(solicitud)
                    if resultado['exito']:
                        self.stdout.write(self.style.SUCCESS(f"      ✅ {resultado['mensaje']}"))
                    else:
                        self.stdout.write(self.style.ERROR(f"      ❌ {resultado['mensaje']}"))
        
        # Enviar email si se especificó
        if email_destino and inconsistencias:
            self.enviar_reporte_email(email_destino, inconsistencias)
        
        self.stdout.write("\n" + "=" * 80)
    
    def verificar_solicitud(self, solicitud):
        """
        Verifica si una solicitud tiene los turnos correctamente generados.
        
        Returns:
            str con descripción del problema, o None si está OK
        """
        fecha_cesion = solicitud.fecha_cambio_turno
        receptor = solicitud.explorador_receptor
        
        if not receptor:
            return "No tiene receptor asignado"
        
        # Verificar turnos del receptor
        turnos_receptor = Turno.objects.filter(
            explorador=receptor,
            fecha=fecha_cesion
        ).count()
        
        if turnos_receptor == 0:
            return f"Receptor {receptor.nombre} no tiene turnos para {fecha_cesion} (debería tener doblada)"
        
        return None
    
    def reparar_solicitud(self, solicitud):
        """
        Intenta reparar una solicitud reseteándola a estado pendiente.
        
        Returns:
            dict con 'exito' (bool) y 'mensaje' (str)
        """
        try:
            from django.db import transaction
            
            with transaction.atomic():
                solicitud.estado = 'pendiente'
                solicitud.aprobado_receptor = False
                solicitud.aprobado_supervisor = False
                solicitud.fecha_resolucion = None
                solicitud.save()
            
            return {
                'exito': True,
                'mensaje': 'Solicitud reseteada a pendiente. Debe ser aprobada nuevamente.'
            }
        except Exception as e:
            logger.exception(f"Error reparando solicitud {solicitud.id}")
            return {
                'exito': False,
                'mensaje': f'Error: {str(e)}'
            }
    
    def enviar_reporte_email(self, email_destino, inconsistencias):
        """
        Envía un reporte por email con las inconsistencias detectadas.
        """
        from django.core.mail import send_mail
        from django.conf import settings
        
        asunto = f'⚠️ Reporte de Integridad de Dobladas - {len(inconsistencias)} problema(s)'
        
        mensaje = f"""
Reporte de Verificación de Integridad de Dobladas
=================================================

Se detectaron {len(inconsistencias)} inconsistencia(s) en el sistema:

"""
        
        for i, (solicitud, problema) in enumerate(inconsistencias, 1):
            mensaje += f"""
{i}. Solicitud ID: {solicitud.id}
   Solicitante: {solicitud.explorador_solicitante.nombre}
   Receptor: {solicitud.explorador_receptor.nombre if solicitud.explorador_receptor else 'N/A'}
   Fecha cesión: {solicitud.fecha_cambio_turno}
   Problema: {problema}
   
"""
        
        mensaje += """
Acción recomendada:
- Ejecutar: python manage.py verificar_integridad_dobladas --reparar
- O resetear manualmente las solicitudes afectadas

Este es un mensaje automático del sistema de monitoreo.
"""
        
        try:
            send_mail(
                asunto,
                mensaje,
                settings.DEFAULT_FROM_EMAIL,
                [email_destino],
                fail_silently=False,
            )
            self.stdout.write(self.style.SUCCESS(f"\n📧 Reporte enviado a {email_destino}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error enviando email: {e}"))





