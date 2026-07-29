"""
Management command para probar el proceso de aprobación de solicitudes
"""
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.solicitud_service import SolicitudService
from turnos.models import Turno
from datetime import date, timedelta
import logging
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Prueba el proceso de aprobación de solicitudes'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== INICIANDO PRUEBA DE APROBACIÓN ===\n'))
        
        try:
            # 1. Obtener usuarios
            self.stdout.write('1. Obteniendo usuarios...')
            try:
                user_mariana = User.objects.get(username='mariana.villa')
                user_jhon = User.objects.get(username='jhon.areiza')
                user_manuel = User.objects.get(username='manuel.moreno')
                
                empleado_mariana = user_mariana.empleado
                empleado_jhon = user_jhon.empleado
                empleado_manuel = user_manuel.empleado
                
                self.stdout.write(f'   [OK] Mariana: {empleado_mariana.id} - {empleado_mariana.nombre} {empleado_mariana.apellido}')
                self.stdout.write(f'   [OK] Jhon: {empleado_jhon.id} - {empleado_jhon.nombre} {empleado_jhon.apellido}')
                self.stdout.write(f'   [OK] Manuel: {empleado_manuel.id} - {empleado_manuel.nombre} {empleado_manuel.apellido}')
            except User.DoesNotExist as e:
                self.stdout.write(self.style.ERROR(f'   [ERROR] Error obteniendo usuarios: {e}'))
                return
            
            # 2. Verificar solicitudes pendientes
            self.stdout.write('\n2. Verificando solicitudes pendientes...')
            fecha_prueba = timezone.localdate() + timedelta(days=7)  # 7 días en el futuro
            
            solicitudes_pendientes = SolicitudCambio.objects.filter(
                explorador_receptor=empleado_jhon,
                fecha_cambio_turno=fecha_prueba,
                estado='pendiente'
            )
            
            self.stdout.write(f'   Solicitudes pendientes para Jhon en {fecha_prueba}: {solicitudes_pendientes.count()}')
            for sol in solicitudes_pendientes:
                self.stdout.write(f'   - ID: {sol.id}, Solicitante: {sol.explorador_solicitante.nombre}, Estado: {sol.estado}')
            
            # 3. Obtener tipo de solicitud
            self.stdout.write('\n3. Obteniendo tipo de solicitud...')
            try:
                tipo_cambio = TipoSolicitudCambio.objects.filter(activo=True).first()
                if not tipo_cambio:
                    self.stdout.write(self.style.ERROR('   [ERROR] No hay tipos de solicitud activos'))
                    return
                self.stdout.write(f'   [OK] Tipo: {tipo_cambio.nombre}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'   [ERROR] Error: {e}'))
                return
            
            # 4. Eliminar solicitudes existentes y crear una nueva
            self.stdout.write('\n4. Eliminando solicitudes existentes y creando nueva...')
            SolicitudCambio.objects.filter(
                explorador_solicitante=empleado_mariana,
                explorador_receptor=empleado_jhon,
                fecha_cambio_turno=fecha_prueba
            ).delete()
            
            # Eliminar turnos existentes para esta fecha
            Turno.objects.filter(
                fecha=fecha_prueba,
                explorador__in=[empleado_mariana, empleado_jhon]
            ).delete()
            
            # Crear nueva solicitud
            solicitud = SolicitudCambio.objects.create(
                explorador_solicitante=empleado_mariana,
                explorador_receptor=empleado_jhon,
                tipo_cambio=tipo_cambio,
                fecha_cambio_turno=fecha_prueba,
                estado='pendiente',
                comentario='Solicitud de prueba automática - NUEVA'
            )
            
            self.stdout.write(f'   [OK] Solicitud creada - ID: {solicitud.id}, Estado: {solicitud.estado}')
            
            # 5. Verificar turnos antes de aprobar
            self.stdout.write('\n5. Verificando turnos ANTES de aprobar...')
            turnos_antes = Turno.objects.filter(
                fecha=fecha_prueba,
                explorador__in=[empleado_mariana, empleado_jhon]
            )
            self.stdout.write(f'   Turnos existentes: {turnos_antes.count()}')
            for turno in turnos_antes:
                self.stdout.write(f'   - {turno.explorador.nombre}: {turno.jornada.nombre if turno.jornada else "N/A"}')
            
            # 6. Aprobar como receptor
            self.stdout.write('\n6. Aprobando como receptor (Jhon)...')
            success, message = SolicitudService.aprobar_solicitud_receptor(
                solicitud.id,
                empleado_jhon,
                'Aprobado por receptor (prueba automática)'
            )
            
            if success:
                self.stdout.write(self.style.SUCCESS(f'   [OK] {message}'))
            else:
                self.stdout.write(self.style.ERROR(f'   [ERROR] {message}'))
            
            # Recargar solicitud
            solicitud.refresh_from_db()
            self.stdout.write(f'   Estado actual: {solicitud.estado}')
            self.stdout.write(f'   Aprobado receptor: {solicitud.aprobado_receptor}')
            self.stdout.write(f'   Aprobado supervisor: {solicitud.aprobado_supervisor}')
            
            # 7. Aprobar como supervisor
            if solicitud.estado == 'pendiente':
                self.stdout.write('\n7. Aprobando como supervisor (Manuel)...')
                success, message = SolicitudService.aprobar_solicitud_supervisor(
                    solicitud.id,
                    empleado_manuel,
                    'Aprobado por supervisor (prueba automática)'
                )
                
                if success:
                    self.stdout.write(self.style.SUCCESS(f'   [OK] {message}'))
                else:
                    self.stdout.write(self.style.ERROR(f'   [ERROR] {message}'))
                
                # Recargar solicitud
                solicitud.refresh_from_db()
                self.stdout.write(f'   Estado actual: {solicitud.estado}')
            
            # 8. Verificar turnos DESPUÉS de aprobar
            self.stdout.write('\n8. Verificando turnos DESPUÉS de aprobar...')
            turnos_despues = Turno.objects.filter(
                fecha=fecha_prueba,
                explorador__in=[empleado_mariana, empleado_jhon]
            )
            self.stdout.write(f'   Turnos existentes: {turnos_despues.count()}')
            for turno in turnos_despues:
                self.stdout.write(f'   - {turno.explorador.nombre}: {turno.jornada.nombre if turno.jornada else "N/A"}, Tipo: {turno.tipo_cambio}')
            
            # 9. Verificar solicitud final
            self.stdout.write('\n9. Estado final de la solicitud...')
            solicitud.refresh_from_db()
            self.stdout.write(f'   ID: {solicitud.id}')
            self.stdout.write(f'   Estado: {solicitud.estado}')
            self.stdout.write(f'   Turno origen: {solicitud.turno_origen.id if solicitud.turno_origen else "None"}')
            self.stdout.write(f'   Turno destino: {solicitud.turno_destino.id if solicitud.turno_destino else "None"}')
            
            # 10. Verificar otras solicitudes rechazadas
            self.stdout.write('\n10. Verificando otras solicitudes rechazadas...')
            otras_solicitudes = SolicitudCambio.objects.filter(
                explorador_receptor=empleado_jhon,
                fecha_cambio_turno=fecha_prueba,
                estado='rechazada'
            ).exclude(id=solicitud.id)
            
            self.stdout.write(f'   Solicitudes rechazadas automáticamente: {otras_solicitudes.count()}')
            for sol in otras_solicitudes:
                self.stdout.write(f'   - ID: {sol.id}, Solicitante: {sol.explorador_solicitante.nombre}, Comentario: {sol.comentario[:50] if sol.comentario else "N/A"}')
            
            # Resumen
            self.stdout.write('\n=== RESUMEN ===')
            if solicitud.estado == 'aprobada' and turnos_despues.count() >= 2:
                self.stdout.write(self.style.SUCCESS('[OK] PRUEBA EXITOSA: Solicitud aprobada y turnos creados'))
            else:
                self.stdout.write(self.style.ERROR('[ERROR] PRUEBA FALLIDA: Verificar logs arriba'))
                self.stdout.write(f'   Estado: {solicitud.estado}')
                self.stdout.write(f'   Turnos creados: {turnos_despues.count()}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n[ERROR] ERROR: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())

