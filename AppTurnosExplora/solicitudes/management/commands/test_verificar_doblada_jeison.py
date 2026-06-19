"""
Management command para probar la verificación de doblada existente para Jeison el 14/02/2026

Uso:
    python manage.py test_verificar_doblada_jeison
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from solicitudes.models import SolicitudCambio
from turnos.models import Turno
from datetime import date
import json

User = get_user_model()


class Command(BaseCommand):
    help = 'Prueba la verificación de doblada existente para Jeison el 14/02/2026'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== TEST: Verificar Doblada Existente para Jeison 14/02/2026 ===\n'))
        
        # Buscar usuario Jeison
        try:
            jeison = User.objects.get(username='jeison.mora').empleado
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('Usuario jeison.mora no encontrado'))
            return
        except AttributeError:
            self.stdout.write(self.style.ERROR('Usuario jeison.mora no tiene empleado asociado'))
            return
        
        fecha_test = date(2026, 2, 14)
        
        self.stdout.write(f'Empleado: {jeison.nombre} {getattr(jeison, "apellido", "")} (ID: {jeison.id})')
        self.stdout.write(f'Fecha: {fecha_test}\n')
        
        # 1. Verificar turnos en BD
        self.stdout.write('1. VERIFICANDO TURNOS EN BD:')
        turnos = Turno.objects.filter(
            explorador=jeison,
            fecha=fecha_test
        ).select_related('jornada')
        
        if turnos.exists():
            self.stdout.write(f'   ✓ Encontrados {turnos.count()} turno(s):')
            for turno in turnos:
                self.stdout.write(f'     - Jornada: {turno.jornada.nombre if turno.jornada else "N/A"}')
                self.stdout.write(f'     - Tipo cambio: {turno.tipo_cambio}')
        else:
            self.stdout.write(self.style.WARNING('   ⚠ NO hay turnos en BD (esperado: descanso)'))
        
        self.stdout.write('')
        
        # 2. Verificar solicitudes de DOBLADA donde Jeison es solicitante
        self.stdout.write('2. VERIFICANDO DOBLADAS APROBADAS (Jeison como solicitante):')
        dobladas_solicitante = SolicitudCambio.objects.filter(
            explorador_solicitante=jeison,
            tipo_cambio__nombre='DOBLADA',
            fecha_cambio_turno=fecha_test,
            estado='aprobada'
        ).select_related('explorador_receptor', 'doblada')
        
        if dobladas_solicitante.exists():
            self.stdout.write(self.style.SUCCESS(f'   ✓ Encontrada(s) {dobladas_solicitante.count()} doblada(s) aprobada(s):'))
            for doblada in dobladas_solicitante:
                receptor = doblada.explorador_receptor
                fecha_pago = doblada.doblada.fecha_pago if doblada.doblada else None
                self.stdout.write(f'     - ID: {doblada.id}')
                self.stdout.write(f'     - Receptor: {receptor.nombre} {getattr(receptor, "apellido", "")}')
                self.stdout.write(f'     - Fecha pago: {fecha_pago}')
                self.stdout.write(f'     - Estado: {doblada.estado}')
        else:
            self.stdout.write(self.style.ERROR('   ✗ NO se encontró doblada aprobada (esto explicaría el problema)'))
        
        self.stdout.write('')
        
        # 3. Verificar solicitudes de DOBLADA donde Jeison es receptor
        self.stdout.write('3. VERIFICANDO DOBLADAS APROBADAS (Jeison como receptor):')
        dobladas_receptor = SolicitudCambio.objects.filter(
            explorador_receptor=jeison,
            tipo_cambio__nombre='DOBLADA',
            estado='aprobada',
            doblada__fecha_pago=fecha_test
        ).select_related('explorador_solicitante', 'doblada')
        
        if dobladas_receptor.exists():
            self.stdout.write(self.style.SUCCESS(f'   ✓ Encontrada(s) {dobladas_receptor.count()} doblada(s) aprobada(s):'))
            for doblada in dobladas_receptor:
                solicitante = doblada.explorador_solicitante
                self.stdout.write(f'     - ID: {doblada.id}')
                self.stdout.write(f'     - Solicitante: {solicitante.nombre} {getattr(solicitante, "apellido", "")}')
                self.stdout.write(f'     - Fecha cesión: {doblada.fecha_cambio_turno}')
        else:
            self.stdout.write('   - No hay dobladas donde Jeison es receptor')
        
        self.stdout.write('')
        
        # 4. Verificar solicitudes de CT donde Jeison es solicitante
        self.stdout.write('4. VERIFICANDO CAMBIOS DE TURNO (CT) APROBADOS (Jeison como solicitante):')
        cts_solicitante = SolicitudCambio.objects.filter(
            explorador_solicitante=jeison,
            tipo_cambio__nombre='CT',
            fecha_cambio_turno=fecha_test,
            estado='aprobada'
        ).select_related('explorador_receptor', 'turno_origen', 'turno_destino')
        
        if cts_solicitante.exists():
            self.stdout.write(self.style.SUCCESS(f'   ✓ Encontrado(s) {cts_solicitante.count()} CT(s) aprobado(s):'))
            for ct in cts_solicitante:
                receptor = ct.explorador_receptor
                self.stdout.write(f'     - ID: {ct.id}')
                self.stdout.write(f'     - Receptor: {receptor.nombre} {getattr(receptor, "apellido", "")}')
                self.stdout.write(f'     - Turno origen: {ct.turno_origen.id if ct.turno_origen else "N/A"}')
                self.stdout.write(f'     - Turno destino: {ct.turno_destino.id if ct.turno_destino else "N/A"}')
        else:
            self.stdout.write('   - No hay CTs donde Jeison es solicitante')
        
        self.stdout.write('')
        
        # 5. Simular la lógica de VerificarDobladaExistenteView
        self.stdout.write('5. SIMULANDO LÓGICA DE VerificarDobladaExistenteView:')
        self.stdout.write('   (Orden de verificación esperado)')
        self.stdout.write('')
        
        jornadas = [t.jornada.nombre.upper() for t in turnos if t.jornada]
        es_doblada_turnos = 'AM' in jornadas and 'PM' in jornadas
        
        self.stdout.write(f'   a) ¿Tiene turnos AM+PM? {es_doblada_turnos}')
        if es_doblada_turnos:
            self.stdout.write(self.style.SUCCESS('      → CASO 1: Tiene doblada asignada'))
            return
        
        self.stdout.write(f'   b) ¿Tiene turnos? {bool(jornadas)}')
        if jornadas:
            # Verificar si es CT
            ct_como_solicitante = cts_solicitante.filter(
                turno_origen__in=[t.id for t in turnos]
            ).first()
            if ct_como_solicitante:
                self.stdout.write(self.style.SUCCESS('      → CASO 2: Tiene CT aprobado (no puede ceder)'))
                return
            else:
                self.stdout.write('      → CASO 2: Tiene turno normal (puede ceder)')
                return
        
        self.stdout.write('   c) ¿NO tiene turnos? Verificando descanso...')
        
        # Verificar DOBLADA como solicitante
        if dobladas_solicitante.exists():
            self.stdout.write(self.style.SUCCESS('      → CASO 3: Está descansando por DOBLADA aprobada (PRIORIDAD)'))
            self.stdout.write(self.style.SUCCESS('      ✓ RESULTADO ESPERADO: esta_descansando=True, puede_ceder=False'))
            return
        
        # Verificar DOBLADA como receptor
        if dobladas_receptor.exists():
            self.stdout.write(self.style.SUCCESS('      → CASO 3: Está descansando por DOBLADA aprobada (receptor)'))
            self.stdout.write(self.style.SUCCESS('      ✓ RESULTADO ESPERADO: esta_descansando=True, puede_ceder=False'))
            return
        
        # Verificar CT
        if cts_solicitante.exists():
            self.stdout.write(self.style.WARNING('      → CASO 2.6: Tiene CT aprobado (no puede ceder)'))
            return
        
        # Verificar regla de sábado
        if fecha_test.weekday() == 5:  # Sábado
            from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
            from turnos.services.jornada_service import JornadaService
            
            jornada_trabaja_sabado = AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha_test)
            if jornada_trabaja_sabado:
                jornada_predeterminada = JornadaService.get_jornada_explorador_fecha(
                    jeison.id, fecha_test.strftime('%Y-%m-%d')
                )
                if jornada_predeterminada and jornada_predeterminada.nombre.upper() == jornada_trabaja_sabado.upper():
                    self.stdout.write(self.style.WARNING('      → CASO 2.5: Doblada por regla de negocio (sábado)'))
                    self.stdout.write(self.style.ERROR('      ✗ PROBLEMA: Esto NO debería ejecutarse si hay DOBLADA aprobada'))
                    return
        
        self.stdout.write('      → CASO 4: No hay turnos ni solicitudes (puede solicitar doblada)')
        
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=== FIN DEL TEST ==='))


