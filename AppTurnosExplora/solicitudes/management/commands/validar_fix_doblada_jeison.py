"""
Script de validación para verificar que el fix de doblada para Jeison está funcionando correctamente

Este script valida que:
1. Cuando Jeison tiene una DOBLADA aprobada el 14/02/2026, el sistema detecta que está descansando
2. NO muestra "Doblada Existente Detectada" cuando está descansando por DOBLADA aprobada
3. La prioridad está correcta: DOBLADA aprobada > CT > Regla de sábado
"""

import json
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import RequestFactory

from solicitudes.models import SolicitudCambio, TipoCambioCambio
from solicitudes.views import VerificarDobladaExistenteView
from turnos.models import Turno

User = get_user_model()


class Command(BaseCommand):
    help = 'Valida que el fix de doblada para Jeison está funcionando correctamente'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('=== VALIDACIÓN DEL FIX DE DOBLADA PARA JEISON ===\n'))
        
        # Buscar usuario Jeison
        try:
            jeison_user = User.objects.get(username='jeison.mora')
            jeison = jeison_user.empleado
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR('✗ Usuario jeison.mora no encontrado'))
            self.stdout.write('   Por favor, asegúrate de que el usuario existe en la base de datos')
            return
        except AttributeError:
            self.stdout.write(self.style.ERROR('✗ Usuario jeison.mora no tiene empleado asociado'))
            return
        
        fecha_test = date(2026, 2, 14)
        
        self.stdout.write(f'Empleado: {jeison.nombre} {getattr(jeison, "apellido", "")} (ID: {jeison.id})')
        self.stdout.write(f'Fecha: {fecha_test} (Sábado)\n')
        
        # 1. Verificar si existe DOBLADA aprobada
        tipo_doblada = TipoCambioCambio.objects.filter(nombre='DOBLADA').first()
        if not tipo_doblada:
            self.stdout.write(self.style.ERROR('✗ Tipo de cambio DOBLADA no encontrado'))
            return
        
        doblada_aprobada = SolicitudCambio.objects.filter(
            explorador_solicitante=jeison,
            tipo_cambio=tipo_doblada,
            fecha_cambio_turno=fecha_test,
            estado='aprobada'
        ).first()
        
        if not doblada_aprobada:
            self.stdout.write(self.style.WARNING('⚠ No se encontró DOBLADA aprobada para Jeison el 14/02/2026'))
            self.stdout.write('   Esto significa que el problema puede no estar presente en este momento')
            self.stdout.write('   O que la solicitud aún no ha sido aprobada\n')
        else:
            self.stdout.write(self.style.SUCCESS(f'✓ DOBLADA aprobada encontrada (ID: {doblada_aprobada.id})'))
            receptor = doblada_aprobada.explorador_receptor
            self.stdout.write(f'  - Receptor: {receptor.nombre} {getattr(receptor, "apellido", "")}')
            self.stdout.write(f'  - Estado: {doblada_aprobada.estado}\n')
        
        # 2. Verificar turnos en BD
        turnos = Turno.objects.filter(
            explorador=jeison,
            fecha=fecha_test
        )
        
        if turnos.exists():
            self.stdout.write(self.style.WARNING(f'⚠ Encontrados {turnos.count()} turno(s) en BD'))
            self.stdout.write('   Esto es inesperado si Jeison está descansando por DOBLADA')
            for turno in turnos:
                self.stdout.write(f'     - Jornada: {turno.jornada.nombre if turno.jornada else "N/A"}')
        else:
            self.stdout.write(self.style.SUCCESS('✓ NO hay turnos en BD (esperado: descanso)'))
        
        self.stdout.write('')
        
        # 3. Simular la llamada al endpoint
        self.stdout.write('3. SIMULANDO LLAMADA AL ENDPOINT:')
        self.stdout.write('   (VerificarDobladaExistenteView)\n')
        
        factory = RequestFactory()
        request = factory.get('/solicitudes/verificar-doblada-existente/', {'fecha': '2026-02-14'})
        request.user = jeison_user
        
        view = VerificarDobladaExistenteView()
        try:
            response = view.get(request)
            response_data = json.loads(response.content)
            
            self.stdout.write('   Respuesta del endpoint:')
            self.stdout.write(f'   - success: {response_data.get("success")}')
            self.stdout.write(f'   - tiene_doblada: {response_data.get("tiene_doblada")}')
            self.stdout.write(f'   - esta_descansando: {response_data.get("esta_descansando")}')
            self.stdout.write(f'   - puede_ceder: {response_data.get("puede_ceder")}')
            self.stdout.write(f'   - jornadas: {response_data.get("jornadas")}')
            self.stdout.write(f'   - mensaje: {response_data.get("mensaje", "")[:80]}...')
            self.stdout.write('')
            
            # VALIDACIONES CRÍTICAS
            self.stdout.write('4. VALIDACIONES:')
            todas_pasan = True
            
            if doblada_aprobada:
                # Si hay DOBLADA aprobada, debe estar descansando
                if response_data.get('esta_descansando'):
                    self.stdout.write(self.style.SUCCESS('   ✓ esta_descansando = True (CORRECTO)'))
                else:
                    self.stdout.write(self.style.ERROR('   ✗ esta_descansando = False (INCORRECTO - debería ser True)'))
                    todas_pasan = False
                
                if not response_data.get('tiene_doblada'):
                    self.stdout.write(self.style.SUCCESS('   ✓ tiene_doblada = False (CORRECTO)'))
                else:
                    self.stdout.write(self.style.ERROR('   ✗ tiene_doblada = True (INCORRECTO - debería ser False)'))
                    todas_pasan = False
                
                if not response_data.get('puede_ceder'):
                    self.stdout.write(self.style.SUCCESS('   ✓ puede_ceder = False (CORRECTO)'))
                else:
                    self.stdout.write(self.style.ERROR('   ✗ puede_ceder = True (INCORRECTO - debería ser False)'))
                    todas_pasan = False
                
                mensaje = response_data.get('mensaje', '').lower()
                if 'descansando' in mensaje or 'cediste' in mensaje:
                    self.stdout.write(self.style.SUCCESS('   ✓ Mensaje indica descanso (CORRECTO)'))
                else:
                    self.stdout.write(self.style.ERROR('   ✗ Mensaje NO indica descanso (INCORRECTO)'))
                    self.stdout.write(f'      Mensaje actual: {response_data.get("mensaje", "")}')
                    todas_pasan = False
                
                if 'sábado' in response_data.get('mensaje', '').lower() and 'regla de negocio' in response_data.get('mensaje', '').lower():
                    self.stdout.write(self.style.ERROR('   ✗ Mensaje menciona "regla de negocio (sábado)" (INCORRECTO)'))
                    self.stdout.write('      Esto indica que está aplicando la regla de sábado en lugar de detectar descanso')
                    todas_pasan = False
            else:
                self.stdout.write(self.style.WARNING('   ⚠ No hay DOBLADA aprobada para validar'))
            
            self.stdout.write('')
            
            if todas_pasan and doblada_aprobada:
                self.stdout.write(self.style.SUCCESS('=== ✓ TODAS LAS VALIDACIONES PASARON ==='))
                self.stdout.write(self.style.SUCCESS('El fix está funcionando correctamente!'))
            elif doblada_aprobada:
                self.stdout.write(self.style.ERROR('=== ✗ ALGUNAS VALIDACIONES FALLARON ==='))
                self.stdout.write(self.style.ERROR('El problema NO está completamente resuelto'))
            else:
                self.stdout.write(self.style.WARNING('=== ⚠ NO SE PUDO VALIDAR COMPLETAMENTE ==='))
                self.stdout.write('No hay DOBLADA aprobada para Jeison el 14/02/2026')
                self.stdout.write('Por favor, crea una solicitud de DOBLADA y apruebala para validar el fix')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'✗ Error al simular la llamada: {str(e)}'))
            import traceback
            self.stdout.write(traceback.format_exc())


