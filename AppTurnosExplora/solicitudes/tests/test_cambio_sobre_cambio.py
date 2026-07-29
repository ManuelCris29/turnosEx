"""
FASE 2.6: Management command para probar el escenario completo de cambio sobre cambio
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
    help = 'FASE 2.6: Prueba el escenario completo de cambio sobre cambio'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== FASE 2.6: PRUEBA CAMBIO SOBRE CAMBIO ===\n'))
        
        try:
            # Obtener usuarios de prueba
            self.stdout.write('1. Obteniendo usuarios de prueba...')
            try:
                user_mariana = User.objects.get(username='mariana.villa')
                user_jhon = User.objects.get(username='jhon.areiza')
                user_manuel = User.objects.get(username='manuel.moreno')
                
                empleado_mariana = user_mariana.empleado
                empleado_jhon = user_jhon.empleado
                empleado_manuel = user_manuel.empleado
                
                self.stdout.write(f'   [OK] Mariana (A): {empleado_mariana.id}')
                self.stdout.write(f'   [OK] Jhon (B): {empleado_jhon.id}')
                self.stdout.write(f'   [OK] Manuel (C): {empleado_manuel.id}')
            except User.DoesNotExist as e:
                self.stdout.write(self.style.ERROR(f'   [ERROR] Error obteniendo usuarios: {e}'))
                return
            
            # Fecha de prueba
            fecha_prueba = timezone.localdate() + timedelta(days=7)
            self.stdout.write(f'\n2. Fecha de prueba: {fecha_prueba}')
            
            # Limpiar datos de prueba anteriores
            self.stdout.write('\n3. Limpiando datos de prueba anteriores...')
            SolicitudCambio.objects.filter(
                fecha_cambio_turno=fecha_prueba,
                explorador_solicitante__in=[empleado_mariana, empleado_jhon, empleado_manuel]
            ).delete()
            Turno.objects.filter(
                fecha=fecha_prueba,
                explorador__in=[empleado_mariana, empleado_jhon, empleado_manuel]
            ).delete()
            self.stdout.write('   [OK] Datos limpiados')
            
            # Obtener tipo de cambio (buscar por nombre que contenga "Cambio" o "CT")
            tipo_cambio = TipoSolicitudCambio.objects.filter(
                activo=True
            ).filter(
                nombre__icontains='Cambio'
            ).first()
            
            if not tipo_cambio:
                # Intentar buscar por "CT"
                tipo_cambio = TipoSolicitudCambio.objects.filter(
                    activo=True,
                    nombre__icontains='CT'
                ).first()
            
            if not tipo_cambio:
                # Si no existe, crear uno
                self.stdout.write('   [INFO] Tipo de cambio no encontrado, creando uno...')
                tipo_cambio = TipoSolicitudCambio.objects.create(
                    nombre='Cambio Turno',
                    activo=True
                )
                self.stdout.write(f'   [OK] Tipo de cambio creado - ID: {tipo_cambio.id}')
            else:
                self.stdout.write(f'   [OK] Tipo de cambio encontrado - ID: {tipo_cambio.id}, Nombre: {tipo_cambio.nombre}')
            
            # ===== CASO 1: PRIMER CAMBIO (A->B) =====
            self.stdout.write(self.style.SUCCESS('\n=== CASO 1: PRIMER CAMBIO (Mariana->Jhon) ==='))
            
            # Crear solicitud A->B
            self.stdout.write('\n4. Creando solicitud Mariana->Jhon...')
            solicitud_ab = SolicitudCambio.objects.create(
                explorador_solicitante=empleado_mariana,
                explorador_receptor=empleado_jhon,
                tipo_cambio=tipo_cambio,
                fecha_cambio_turno=fecha_prueba,
                estado='pendiente',
                comentario='FASE 2.6: Primer cambio - A->B'
            )
            self.stdout.write(f'   [OK] Solicitud creada - ID: {solicitud_ab.id}')
            
            # Verificar que no hay turnos antes
            turnos_antes = Turno.objects.filter(
                fecha=fecha_prueba,
                explorador__in=[empleado_mariana, empleado_jhon]
            )
            self.stdout.write(f'   Turnos existentes antes: {turnos_antes.count()}')
            
            # Aprobar solicitud A->B
            self.stdout.write('\n5. Aprobando solicitud Mariana->Jhon...')
            success, message = SolicitudService.aprobar_solicitud_receptor(
                solicitud_ab.id,
                empleado_jhon,
                'Aprobado por receptor (FASE 2.6)'
            )
            if not success:
                self.stdout.write(self.style.ERROR(f'   [ERROR] {message}'))
                return
            
            success, message = SolicitudService.aprobar_solicitud_supervisor(
                solicitud_ab.id,
                empleado_manuel,  # Supervisor de Mariana
                'Aprobado por supervisor (FASE 2.6)'
            )
            if not success:
                self.stdout.write(self.style.ERROR(f'   [ERROR] {message}'))
                return
            
            solicitud_ab.refresh_from_db()
            self.stdout.write(f'   [OK] Solicitud aprobada - Estado: {solicitud_ab.estado}')
            
            # Verificar turnos creados
            self.stdout.write('\n6. Verificando turnos creados...')
            turno_mariana_1 = Turno.objects.filter(
                explorador=empleado_mariana,
                fecha=fecha_prueba
            ).first()
            turno_jhon_1 = Turno.objects.filter(
                explorador=empleado_jhon,
                fecha=fecha_prueba
            ).first()
            
            if turno_mariana_1:
                self.stdout.write(f'   [OK] Turno Mariana creado - ID: {turno_mariana_1.id}, Jornada: {turno_mariana_1.jornada.nombre}')
            else:
                self.stdout.write(self.style.ERROR('   [ERROR] Turno de Mariana no encontrado'))
                return
            
            if turno_jhon_1:
                self.stdout.write(f'   [OK] Turno Jhon creado - ID: {turno_jhon_1.id}, Jornada: {turno_jhon_1.jornada.nombre}')
            else:
                self.stdout.write(self.style.ERROR('   [ERROR] Turno de Jhon no encontrado'))
                return
            
            # Guardar ID del turno de Mariana para verificar que se actualiza
            turno_mariana_id_original = turno_mariana_1.id
            
            # ===== CASO 2: SEGUNDO CAMBIO (A->C) - CAMBIO SOBRE CAMBIO =====
            self.stdout.write(self.style.SUCCESS('\n=== CASO 2: SEGUNDO CAMBIO (Mariana->Manuel) - CAMBIO SOBRE CAMBIO ==='))
            
            # Verificar jornada actual de Mariana
            self.stdout.write('\n7. Verificando jornada actual de Mariana...')
            jornada_actual = SolicitudService.get_jornada_explorador_fecha(
                empleado_mariana.id,
                fecha_prueba.strftime('%Y-%m-%d')
            )
            if jornada_actual:
                self.stdout.write(f'   [OK] Jornada actual: {jornada_actual.nombre} (debe ser PM del turno)')
            else:
                self.stdout.write(self.style.ERROR('   [ERROR] No se pudo obtener jornada actual'))
                return
            
            # Crear solicitud A->C
            self.stdout.write('\n8. Creando solicitud Mariana->Manuel...')
            solicitud_ac = SolicitudCambio.objects.create(
                explorador_solicitante=empleado_mariana,
                explorador_receptor=empleado_manuel,
                tipo_cambio=tipo_cambio,
                fecha_cambio_turno=fecha_prueba,
                estado='pendiente',
                comentario='FASE 2.6: Segundo cambio - A->C (cambio sobre cambio)'
            )
            self.stdout.write(f'   [OK] Solicitud creada - ID: {solicitud_ac.id}')
            
            # Aprobar solicitud A->C
            self.stdout.write('\n9. Aprobando solicitud Mariana->Manuel...')
            success, message = SolicitudService.aprobar_solicitud_receptor(
                solicitud_ac.id,
                empleado_manuel,
                'Aprobado por receptor (FASE 2.6)'
            )
            if not success:
                self.stdout.write(self.style.ERROR(f'   [ERROR] {message}'))
                return
            
            success, message = SolicitudService.aprobar_solicitud_supervisor(
                solicitud_ac.id,
                empleado_manuel,  # Supervisor de Mariana
                'Aprobado por supervisor (FASE 2.6)'
            )
            if not success:
                self.stdout.write(self.style.ERROR(f'   [ERROR] {message}'))
                return
            
            solicitud_ac.refresh_from_db()
            self.stdout.write(f'   [OK] Solicitud aprobada - Estado: {solicitud_ac.estado}')
            
            # Verificar que el turno de Mariana se ACTUALIZÓ (no se creó nuevo)
            self.stdout.write('\n10. Verificando actualización del turno de Mariana...')
            turno_mariana_2 = Turno.objects.filter(
                explorador=empleado_mariana,
                fecha=fecha_prueba
            ).first()
            
            if turno_mariana_2:
                if turno_mariana_2.id == turno_mariana_id_original:
                    self.stdout.write(f'   [OK] Turno ACTUALIZADO (mismo ID: {turno_mariana_2.id})')
                    self.stdout.write(f'   [OK] Nueva jornada: {turno_mariana_2.jornada.nombre}')
                else:
                    self.stdout.write(self.style.ERROR(f'   [ERROR] Se creó nuevo turno (ID: {turno_mariana_2.id}) en lugar de actualizar'))
                    return
            else:
                self.stdout.write(self.style.ERROR('   [ERROR] Turno de Mariana no encontrado'))
                return
            
            # Verificar que el turno de Jhon NO cambió
            self.stdout.write('\n11. Verificando que turno de Jhon NO cambió...')
            turno_jhon_2 = Turno.objects.filter(
                explorador=empleado_jhon,
                fecha=fecha_prueba
            ).first()
            
            if turno_jhon_2:
                if turno_jhon_2.id == turno_jhon_1.id:
                    self.stdout.write(f'   [OK] Turno de Jhon NO cambió (mismo ID: {turno_jhon_2.id})')
                    self.stdout.write(f'   [OK] Jornada permanece: {turno_jhon_2.jornada.nombre}')
                else:
                    self.stdout.write(self.style.WARNING(f'   [ADVERTENCIA] Turno de Jhon cambió (nuevo ID: {turno_jhon_2.id})'))
            else:
                self.stdout.write(self.style.ERROR('   [ERROR] Turno de Jhon no encontrado'))
                return
            
            # Verificar turno de Manuel (C)
            self.stdout.write('\n12. Verificando turno de Manuel...')
            turno_manuel = Turno.objects.filter(
                explorador=empleado_manuel,
                fecha=fecha_prueba
            ).first()
            
            if turno_manuel:
                self.stdout.write(f'   [OK] Turno Manuel creado - ID: {turno_manuel.id}, Jornada: {turno_manuel.jornada.nombre}')
            else:
                self.stdout.write(self.style.ERROR('   [ERROR] Turno de Manuel no encontrado'))
                return
            
            # ===== VERIFICACIÓN DE TRAZABILIDAD =====
            self.stdout.write(self.style.SUCCESS('\n=== VERIFICACIÓN DE TRAZABILIDAD ==='))
            
            self.stdout.write('\n13. Verificando relación de solicitudes...')
            solicitud_ac.refresh_from_db()
            if solicitud_ac.solicitud_origen:
                self.stdout.write(f'   [OK] solicitud_origen establecida - ID: {solicitud_ac.solicitud_origen.id}')
                if solicitud_ac.solicitud_origen.id == solicitud_ab.id:
                    self.stdout.write('   [OK] Relación correcta: A->C apunta a A->B')
                else:
                    self.stdout.write(self.style.WARNING(f'   [ADVERTENCIA] Relación apunta a solicitud diferente'))
            else:
                self.stdout.write(self.style.WARNING('   [ADVERTENCIA] solicitud_origen no establecida'))
            
            self.stdout.write('\n14. Verificando comentario de trazabilidad...')
            if solicitud_ac.comentario and 'Actualización' in solicitud_ac.comentario:
                self.stdout.write('   [OK] Comentario de trazabilidad encontrado')
                self.stdout.write(f'   Comentario: {solicitud_ac.comentario[:100]}...')
            else:
                self.stdout.write(self.style.WARNING('   [ADVERTENCIA] Comentario de trazabilidad no encontrado'))
            
            # ===== VERIFICACIÓN DE LÍMITE DE CAMBIOS =====
            self.stdout.write(self.style.SUCCESS('\n=== VERIFICACIÓN DE LÍMITE DE CAMBIOS ==='))
            
            self.stdout.write('\n15. Contando cambios aprobados de Mariana...')
            count = SolicitudService.contar_cambios_explorador_fecha(
                empleado_mariana.id,
                fecha_prueba
            )
            self.stdout.write(f'   [OK] Cambios aprobados: {count} (esperado: 2)')
            
            if count == 2:
                self.stdout.write('   [OK] Conteo correcto')
            else:
                self.stdout.write(self.style.WARNING(f'   [ADVERTENCIA] Conteo inesperado: {count}'))
            
            # ===== RESUMEN FINAL =====
            self.stdout.write(self.style.SUCCESS('\n=== RESUMEN FINAL ==='))
            self.stdout.write(f'\nSolicitudes creadas:')
            self.stdout.write(f'  - A->B (ID: {solicitud_ab.id}): {solicitud_ab.estado}')
            self.stdout.write(f'  - A->C (ID: {solicitud_ac.id}): {solicitud_ac.estado}')
            
            self.stdout.write(f'\nTurnos para fecha {fecha_prueba}:')
            turnos_finales = Turno.objects.filter(
                fecha=fecha_prueba,
                explorador__in=[empleado_mariana, empleado_jhon, empleado_manuel]
            ).select_related('explorador', 'jornada')
            
            for turno in turnos_finales:
                self.stdout.write(f'  - {turno.explorador.nombre}: {turno.jornada.nombre} (ID: {turno.id})')
            
            self.stdout.write(self.style.SUCCESS('\n=== PRUEBA COMPLETADA EXITOSAMENTE ==='))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n[ERROR] Error durante la prueba: {e}'))
            import traceback
            self.stdout.write(traceback.format_exc())
            logger.exception('Error en test_cambio_sobre_cambio')

