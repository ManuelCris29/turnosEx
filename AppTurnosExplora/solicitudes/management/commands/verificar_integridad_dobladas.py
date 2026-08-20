"""
Comando de management para verificar la integridad de solicitudes de doblada.
Detecta solicitudes aprobadas sin turnos generados correctamente.

Uso:
    python manage.py verificar_integridad_dobladas
    python manage.py verificar_integridad_dobladas --reparar
    python manage.py verificar_integridad_dobladas --email admin@example.com
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from solicitudes.models import SolicitudCambio
from turnos.models import Turno
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
        fecha_limite = timezone.localdate() - timedelta(days=dias)
        
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
        explicadas = []

        for solicitud in solicitudes_aprobadas:
            clase, texto = self.verificar_solicitud(solicitud)
            if clase == 'problema':
                inconsistencias.append((solicitud, texto))
            elif clase == 'explicado':
                explicadas.append((solicitud, texto))

        # Reporte
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("RESULTADOS")
        self.stdout.write("=" * 80)

        # Casos SIN turnos pero con explicación legítima: no son errores, se informan aparte
        # para que no se confundan con problemas reales (antes se reportaban como fallos).
        if explicadas:
            self.stdout.write(self.style.WARNING(
                f"\nℹ️  {len(explicadas)} doblada(s) sin turnos por razones esperadas (NO son errores):\n"
            ))
            for solicitud, texto in explicadas:
                self.stdout.write(f"   • Solicitud {solicitud.id} ({solicitud.fecha_cambio_turno}): {texto}")

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
                    self.stdout.write("   🔧 Intentando reparar...")
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
            (None, None) si está OK,
            ('problema', texto) si es una inconsistencia real,
            ('explicado', texto) si el receptor no tiene turnos por una razón LEGÍTIMA.
        """
        fecha_cesion = solicitud.fecha_cambio_turno
        receptor = solicitud.explorador_receptor

        if not receptor:
            return 'problema', "No tiene receptor asignado"

        # Verificar turnos del receptor
        turnos_receptor = Turno.objects.filter(
            explorador=receptor,
            fecha=fecha_cesion
        ).count()

        if turnos_receptor > 0:
            return None, None

        # Sin turnos NO siempre es un error. Hay dos razones legítimas por las que la doblada
        # de ese día deja de estar reflejada, y antes ambas se reportaban como inconsistencia.
        explicacion = (
            self._explicado_por_reprogramacion(solicitud, receptor, fecha_cesion)
            or self._explicado_por_solicitud_posterior(solicitud, receptor, fecha_cesion)
        )
        if explicacion:
            return 'explicado', explicacion

        return 'problema', (
            f"Receptor {receptor.nombre} no tiene turnos para {fecha_cesion} (debería tener doblada)"
        )

    @staticmethod
    def _explicado_por_reprogramacion(solicitud, receptor, fecha):
        """
        El receptor NO CUMPLIÓ ese día: se registró una reprogramación por inasistencia, que
        anula su doblada y cancela sus 30 min (los reactiva en la fecha de pago acordada).
        Que no tenga turnos ese día es justamente el resultado esperado.
        """
        from solicitudes.models import ReprogramacionDiaDoblada
        reprog = (
            ReprogramacionDiaDoblada.objects
            .filter(doblada_origen=solicitud, explorador=receptor, fecha_original=fecha)
            .exclude(estado='cancelada')
            .order_by('-id')
            .first()
        )
        if not reprog:
            return None
        if reprog.estado == 'pagada' and reprog.fecha_reprogramada:
            return (
                f"{receptor.nombre} no cumplió el {fecha}; reprogramado y ya pagado "
                f"doblando el {reprog.fecha_reprogramada}."
            )
        return (
            f"{receptor.nombre} no cumplió el {fecha}; reprogramación PENDIENTE de "
            f"programar por el supervisor."
        )

    @staticmethod
    def _explicado_por_solicitud_posterior(solicitud, receptor, fecha):
        """
        Otra solicitud aprobada MÁS RECIENTE modificó ese mismo día. Por la regla "la última
        aprobada gana por día", el estado vigente es el de esa otra, no el de esta.
        """
        from django.db.models import Q
        if not solicitud.fecha_resolucion:
            return None
        posterior = (
            SolicitudCambio.objects
            .filter(estado='aprobada', fecha_resolucion__gt=solicitud.fecha_resolucion)
            .filter(Q(explorador_solicitante=receptor) | Q(explorador_receptor=receptor))
            .filter(Q(fecha_cambio_turno=fecha) | Q(doblada__fecha_pago=fecha))
            .exclude(id=solicitud.id)
            .select_related('tipo_cambio')
            .order_by('-fecha_resolucion')
            .first()
        )
        if not posterior:
            return None
        tipo = posterior.tipo_cambio.nombre if posterior.tipo_cambio else 'otra solicitud'
        return (
            f"Sustituida en el {fecha} por la solicitud {posterior.id} ({tipo}), aprobada después. "
            f"La última aprobada del día es la que manda."
        )
    
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
        from django.conf import settings
        from solicitudes.services.email_service import EmailService

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
        
        # Un reporte por día y destinatario: este comando lo lanza un cron diario (3:00 AM),
        # así que la identidad lógica del correo es la FECHA, no su contenido. Si el cron se
        # dispara dos veces (solapamiento, reintento), el admin recibe un solo reporte.
        from solicitudes.models import EmailOutbox

        clave = f'reporte_integridad_{timezone.localdate().isoformat()}_{email_destino}'
        ya_encolado = EmailOutbox.objects.filter(clave_idempotencia=clave).exists()

        try:
            EmailService._enviar_email_desde_usuario(
                subject=asunto,
                message=mensaje,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email_destino],
                clave_idempotencia=clave,
            )
            if ya_encolado:
                # No se puede callar esto: quien re-ejecuta a mano el mismo día debe saber
                # que NO se envió un segundo reporte, o creerá que recibió datos frescos.
                self.stdout.write(self.style.WARNING(
                    f"\n📧 Hoy ya se encoló un reporte para {email_destino}; NO se envía otro. "
                    f"El reporte de arriba solo se muestra en pantalla."))
            else:
                self.stdout.write(self.style.SUCCESS(f"\n📧 Reporte encolado para {email_destino}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"\n❌ Error encolando email: {e}"))







