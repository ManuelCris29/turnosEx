"""
Management command para reaplicar una solicitud de doblada que no se aplicó correctamente.

Uso:
    python manage.py reaplicar_doblada <solicitud_id> [--dry-run] [--skip-deudas]

Parámetros:
    solicitud_id: ID de la solicitud de doblada a reaplicar
    --dry-run: Simula la operación sin hacer cambios en la BD (útil para verificar)
    --skip-deudas: No regenera las deudas (solo recrea los turnos)

Ejemplos:
    # Ver qué haría sin hacer cambios
    python manage.py reaplicar_doblada 123 --dry-run
    
    # Reaplicar completamente la solicitud 123
    python manage.py reaplicar_doblada 123
    
    # Reaplicar solo los turnos (sin tocar deudas)
    python manage.py reaplicar_doblada 123 --skip-deudas
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from solicitudes.models import SolicitudCambio, DobladaDetalle
from turnos.models import Turno
from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
from core.services.cache_service import CacheService
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Reaplica una solicitud de doblada que no se aplicó correctamente'

    def add_arguments(self, parser):
        parser.add_argument(
            'solicitud_id',
            type=int,
            help='ID de la solicitud de doblada a reaplicar'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la operación sin hacer cambios en la BD'
        )
        parser.add_argument(
            '--skip-deudas',
            action='store_true',
            help='No regenera las deudas (solo recrea los turnos)'
        )

    def handle(self, *args, **options):
        solicitud_id = options['solicitud_id']
        dry_run = options['dry_run']
        skip_deudas = options['skip_deudas']

        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 MODO DRY-RUN: No se harán cambios en la BD'))
            self.stdout.write('')

        try:
            # Obtener la solicitud
            solicitud = SolicitudCambio.objects.select_related(
                'tipo_cambio',
                'explorador_solicitante',
                'explorador_receptor',
                'doblada'
            ).get(id=solicitud_id)

            # Verificar que sea una solicitud de doblada
            if solicitud.tipo_cambio.nombre != 'DOBLADA':
                raise CommandError(
                    f'La solicitud {solicitud_id} no es de tipo DOBLADA '
                    f'(tipo actual: {solicitud.tipo_cambio.nombre})'
                )

            # Verificar que esté aprobada
            if solicitud.estado != 'aprobada':
                raise CommandError(
                    f'La solicitud {solicitud_id} no está aprobada '
                    f'(estado actual: {solicitud.estado})'
                )

            detalle = solicitud.doblada
            solicitante = solicitud.explorador_solicitante
            receptor = solicitud.explorador_receptor
            fecha_cesion = solicitud.fecha_cambio_turno
            fecha_pago = detalle.fecha_pago

            # Mostrar información de la solicitud
            self.stdout.write(self.style.HTTP_INFO('📋 INFORMACIÓN DE LA SOLICITUD'))
            self.stdout.write(f'  ID: {solicitud.id}')
            self.stdout.write(f'  Solicitante (deudor): {solicitante.nombre} (ID: {solicitante.id})')
            self.stdout.write(f'  Receptor (acreedor): {receptor.nombre} (ID: {receptor.id})')
            self.stdout.write(f'  Fecha de cesión: {fecha_cesion}')
            self.stdout.write(f'  Fecha de pago: {fecha_pago}')
            self.stdout.write(f'  Tipo de cesión: {detalle.tipo_cesion}')
            self.stdout.write(f'  Estado: {solicitud.estado}')
            self.stdout.write('')

            # Verificar estado actual de turnos
            self.stdout.write(self.style.HTTP_INFO('🔍 ESTADO ACTUAL DE TURNOS'))
            
            # Turnos en fecha de cesión
            turnos_cesion_receptor = list(Turno.objects.filter(
                explorador=receptor, fecha=fecha_cesion
            ).select_related('jornada'))
            
            turnos_cesion_solicitante = list(Turno.objects.filter(
                explorador=solicitante, fecha=fecha_cesion
            ).select_related('jornada'))
            
            self.stdout.write(f'  📅 Fecha de cesión ({fecha_cesion}):')
            self.stdout.write(
                f'    - Receptor ({receptor.nombre}): '
                f'{", ".join([t.jornada.nombre for t in turnos_cesion_receptor]) if turnos_cesion_receptor else "Sin turnos"}'
            )
            self.stdout.write(
                f'    - Solicitante ({solicitante.nombre}): '
                f'{", ".join([t.jornada.nombre for t in turnos_cesion_solicitante]) if turnos_cesion_solicitante else "Sin turnos"}'
            )
            
            # Turnos en fecha de pago
            turnos_pago_solicitante = list(Turno.objects.filter(
                explorador=solicitante, fecha=fecha_pago
            ).select_related('jornada'))
            
            turnos_pago_receptor = list(Turno.objects.filter(
                explorador=receptor, fecha=fecha_pago
            ).select_related('jornada'))
            
            self.stdout.write(f'  📅 Fecha de pago ({fecha_pago}):')
            self.stdout.write(
                f'    - Solicitante ({solicitante.nombre}): '
                f'{", ".join([t.jornada.nombre for t in turnos_pago_solicitante]) if turnos_pago_solicitante else "Sin turnos"}'
            )
            self.stdout.write(
                f'    - Receptor ({receptor.nombre}): '
                f'{", ".join([t.jornada.nombre for t in turnos_pago_receptor]) if turnos_pago_receptor else "Sin turnos"}'
            )
            self.stdout.write('')

            # Detectar qué falta (cesión completa vs parcial)
            jornadas_cesion_receptor = [t.jornada.nombre.upper() for t in turnos_cesion_receptor]
            jornadas_cesion_solicitante = [t.jornada.nombre.upper() for t in turnos_cesion_solicitante]
            jornadas_pago_solicitante = [t.jornada.nombre.upper() for t in turnos_pago_solicitante]
            jornadas_pago_receptor = [t.jornada.nombre.upper() for t in turnos_pago_receptor]
            es_cesion_parcial = detalle.tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm')

            if es_cesion_parcial:
                jornada_cedida = (detalle.jornada_cedida or ('AM' if detalle.tipo_cesion == 'cesion_parcial_am' else 'PM')).upper()
                jornada_otra = 'PM' if jornada_cedida == 'AM' else 'AM'
                # Cesión: receptor solo jornada cedida; solicitante solo la otra
                falta_doblada_cesion = (
                    len(jornadas_cesion_receptor) != 1 or jornadas_cesion_receptor[0] != jornada_cedida
                    or len(jornadas_cesion_solicitante) != 1 or jornadas_cesion_solicitante[0] != jornada_otra
                )
                # Pago: solicitante jornada cedida (paga), receptor la otra (media jornada)
                falta_doblada_pago = (
                    len(jornadas_pago_solicitante) != 1 or jornadas_pago_solicitante[0] != jornada_cedida
                    or len(jornadas_pago_receptor) != 1 or jornadas_pago_receptor[0] != jornada_otra
                )
            else:
                falta_doblada_cesion = not ('AM' in jornadas_cesion_receptor and 'PM' in jornadas_cesion_receptor)
                falta_doblada_pago = not ('AM' in jornadas_pago_solicitante and 'PM' in jornadas_pago_solicitante)

            self.stdout.write(self.style.HTTP_INFO('📊 DIAGNÓSTICO'))
            if falta_doblada_cesion:
                self.stdout.write(self.style.WARNING(
                    '  ⚠️  Estado incorrecto en fecha de cesión'
                    + (f' (receptor {jornada_cedida}, solicitante {jornada_otra})' if es_cesion_parcial else ' (receptor sin doblada)')
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    '  ✅ Fecha de cesión correcta'
                ))
            
            if falta_doblada_pago:
                self.stdout.write(self.style.WARNING(
                    '  ⚠️  Estado incorrecto en fecha de pago'
                    + (f' (solicitante {jornada_cedida}, receptor {jornada_otra})' if es_cesion_parcial else ' (solicitante sin doblada)')
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    '  ✅ Fecha de pago correcta'
                ))
            
            if not falta_doblada_cesion and not falta_doblada_pago:
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS(
                    '✅ La doblada ya está aplicada correctamente. No es necesario reaplicar.'
                ))
                return
            
            self.stdout.write('')

            if dry_run:
                self.stdout.write(self.style.WARNING('🔍 DRY-RUN: Simulando operaciones...'))
                self.stdout.write('')
                self.stdout.write('  Se aplicarían los siguientes cambios:')
                self.stdout.write(f'    - Borrar turnos de {solicitante.nombre} y {receptor.nombre} en {fecha_cesion} y {fecha_pago}')
                if getattr(detalle, 'es_intercambio', False):
                    self.stdout.write(
                        f'    - Re-aplicar el INTERCAMBIO: {receptor.nombre} asume la doblada (AM+PM) del '
                        f'{fecha_cesion} y {solicitante.nombre} la del {fecha_pago}; cada uno descansa el día del otro')
                    self.stdout.write('    - Sin deudas (un intercambio de dobladas no genera ninguna)')
                    self.stdout.write('')
                    self.stdout.write(self.style.SUCCESS('✅ DRY-RUN completado. Ejecuta sin --dry-run para aplicar.'))
                    return
                self.stdout.write(f'    - Aplicar doblada de cesión: {receptor.nombre} dobla en {fecha_cesion}, {solicitante.nombre} según tipo de cesión')
                if es_cesion_parcial:
                    self.stdout.write(f'    - Aplicar doblada de pago: {solicitante.nombre} {jornada_cedida}, {receptor.nombre} {jornada_otra} en {fecha_pago}')
                else:
                    self.stdout.write(f'    - Aplicar doblada de pago: {solicitante.nombre} dobla en {fecha_pago}, {receptor.nombre} descansa')
                if not skip_deudas:
                    self.stdout.write(
                        '    - Crear las deudas que falten (DeudaExplorador y DeudaCorporativa). '
                        'Las que ya existan NO se duplican.'
                    )
                else:
                    self.stdout.write('    - ⏭️  Omitir regeneración de deudas (--skip-deudas)')
                self.stdout.write('')
                self.stdout.write(self.style.SUCCESS('✅ DRY-RUN completado. Ejecuta sin --dry-run para aplicar.'))
                return

            # Aplicar cambios
            self.stdout.write(self.style.HTTP_INFO('⚙️  APLICANDO CAMBIOS...'))
            self.stdout.write('')

            with transaction.atomic():
                # 0. Revertir: borrar turnos de cesión y pago para reaplicar desde cero
                # (evita estado incoherente cuando ya se aplicó mal antes)
                Turno.objects.filter(
                    explorador__in=[solicitante, receptor],
                    fecha__in=[fecha_cesion, fecha_pago]
                ).delete()
                self.stdout.write('  🧹 Turnos de cesión y pago borrados para reaplicar desde cero')
                self.stdout.write('')

                # Un INTERCAMBIO de dobladas tiene su propio aplicador (swap de día completo entre
                # dos dobladas) y NO genera deudas. Re-aplicarlo con la lógica de cesión/pago
                # reconstruye un estado inventado.
                es_intercambio = bool(getattr(detalle, 'es_intercambio', False))
                if es_intercambio:
                    self.stdout.write(f'  📝 Re-aplicando INTERCAMBIO de dobladas ({fecha_cesion} ↔ {fecha_pago})...')
                    DobladaAplicacionService.aplicar_intercambio(solicitud, detalle)
                    self.stdout.write(self.style.SUCCESS('     ✅ Intercambio aplicado (sin deudas)'))
                else:
                    # 1. Aplicar doblada de cesión (siempre, tras el borrado)
                    self.stdout.write(f'  📝 Aplicando doblada en fecha de cesión ({fecha_cesion})...')
                    DobladaAplicacionService.aplicar_doblada_cesion(solicitud, detalle)
                    self.stdout.write(self.style.SUCCESS('     ✅ Doblada de cesión aplicada'))

                    # 2. Aplicar doblada de pago (siempre, tras el borrado)
                    self.stdout.write(f'  📝 Aplicando doblada en fecha de pago ({fecha_pago})...')
                    DobladaAplicacionService.aplicar_doblada_pago(solicitud, detalle)
                    self.stdout.write(self.style.SUCCESS('     ✅ Doblada de pago aplicada'))

                # 3. Generar deudas (opcional; un intercambio nunca las genera)
                if not skip_deudas and not es_intercambio:
                    # Idempotente: crea solo las deudas que falten. Antes esto duplicaba la deuda
                    # (y los 30 min corporativos) de una solicitud ya aplicada. Ver
                    # PROTECTION_PATTERNS.md #21.
                    self.stdout.write('  📝 Creando las deudas que falten...')
                    DobladaAplicacionService.generar_deudas_doblada(solicitud, detalle)
                    self.stdout.write(self.style.SUCCESS('     ✅ Deudas al día (las existentes no se duplicaron)'))
                elif es_intercambio:
                    self.stdout.write('  ⏭️  Un intercambio de dobladas no genera deudas')
                else:
                    self.stdout.write('  ⏭️  Omitiendo regeneración de deudas (--skip-deudas)')

            self.stdout.write('')

            # Limpiar caché
            self.stdout.write('  🧹 Limpiando caché...')
            CacheService.invalidar_cache_turnos_empleado(solicitante.id, fecha_cesion.month, fecha_cesion.year)
            CacheService.invalidar_cache_turnos_empleado(receptor.id, fecha_cesion.month, fecha_cesion.year)
            if fecha_pago.month != fecha_cesion.month or fecha_pago.year != fecha_cesion.year:
                CacheService.invalidar_cache_turnos_empleado(solicitante.id, fecha_pago.month, fecha_pago.year)
                CacheService.invalidar_cache_turnos_empleado(receptor.id, fecha_pago.month, fecha_pago.year)
            self.stdout.write(self.style.SUCCESS('     ✅ Caché limpiado'))

            self.stdout.write('')

            # Verificar resultado final
            self.stdout.write(self.style.HTTP_INFO('🔍 VERIFICACIÓN POST-APLICACIÓN'))
            
            turnos_cesion_receptor_new = list(Turno.objects.filter(
                explorador=receptor, fecha=fecha_cesion
            ).select_related('jornada'))
            
            turnos_pago_solicitante_new = list(Turno.objects.filter(
                explorador=solicitante, fecha=fecha_pago
            ).select_related('jornada'))
            turnos_pago_receptor_new = list(Turno.objects.filter(
                explorador=receptor, fecha=fecha_pago
            ).select_related('jornada'))
            turnos_cesion_solicitante_new = list(Turno.objects.filter(
                explorador=solicitante, fecha=fecha_cesion
            ).select_related('jornada'))
            
            jornadas_cesion_receptor_new = [t.jornada.nombre.upper() for t in turnos_cesion_receptor_new]
            jornadas_cesion_solicitante_new = [t.jornada.nombre.upper() for t in turnos_cesion_solicitante_new]
            jornadas_pago_solicitante_new = [t.jornada.nombre.upper() for t in turnos_pago_solicitante_new]
            jornadas_pago_receptor_new = [t.jornada.nombre.upper() for t in turnos_pago_receptor_new]
            
            self.stdout.write(f'  📅 Fecha de cesión ({fecha_cesion}):')
            self.stdout.write(
                f'    - Receptor ({receptor.nombre}): '
                f'{", ".join(jornadas_cesion_receptor_new) if jornadas_cesion_receptor_new else "Sin turnos"}'
            )
            self.stdout.write(
                f'    - Solicitante ({solicitante.nombre}): '
                f'{", ".join(jornadas_cesion_solicitante_new) if jornadas_cesion_solicitante_new else "Sin turnos"}'
            )
            self.stdout.write(f'  📅 Fecha de pago ({fecha_pago}):')
            self.stdout.write(
                f'    - Solicitante ({solicitante.nombre}): '
                f'{", ".join(jornadas_pago_solicitante_new) if jornadas_pago_solicitante_new else "Sin turnos"}'
            )
            self.stdout.write(
                f'    - Receptor ({receptor.nombre}): '
                f'{", ".join(jornadas_pago_receptor_new) if jornadas_pago_receptor_new else "Sin turnos"}'
            )
            self.stdout.write('')

            # Validación final
            if es_intercambio:
                # El swap es correcto cuando cada uno tiene la DOBLADA (AM+PM) del día del OTRO y
                # descansa el propio. `es_cesion_parcial`/`jornada_cedida` no describen nada aquí.
                tiene_doblada_cesion = (
                    {'AM', 'PM'} <= set(jornadas_cesion_receptor_new)
                    and not jornadas_cesion_solicitante_new
                )
                tiene_doblada_pago = (
                    {'AM', 'PM'} <= set(jornadas_pago_solicitante_new)
                    and not jornadas_pago_receptor_new
                )
            elif es_cesion_parcial:
                tiene_doblada_cesion = (
                    len(jornadas_cesion_receptor_new) == 1 and jornadas_cesion_receptor_new[0] == jornada_cedida
                    and len(jornadas_cesion_solicitante_new) == 1 and jornadas_cesion_solicitante_new[0] == jornada_otra
                )
                tiene_doblada_pago = (
                    len(jornadas_pago_solicitante_new) == 1 and jornadas_pago_solicitante_new[0] == jornada_cedida
                    and len(jornadas_pago_receptor_new) == 1 and jornadas_pago_receptor_new[0] == jornada_otra
                )
            else:
                tiene_doblada_cesion = 'AM' in jornadas_cesion_receptor_new and 'PM' in jornadas_cesion_receptor_new
                tiene_doblada_pago = 'AM' in jornadas_pago_solicitante_new and 'PM' in jornadas_pago_solicitante_new

            if tiene_doblada_cesion and tiene_doblada_pago:
                self.stdout.write(self.style.SUCCESS(
                    '✅ ¡ÉXITO! La doblada se reaplicó correctamente.'
                ))
                self.stdout.write('')
                self.stdout.write('Ahora:')
                if es_intercambio:
                    self.stdout.write(f'  • {receptor.nombre} DOBLADA en {fecha_cesion} y {solicitante.nombre} descansa')
                    self.stdout.write(f'  • {solicitante.nombre} DOBLADA en {fecha_pago} y {receptor.nombre} descansa')
                elif es_cesion_parcial:
                    self.stdout.write(f'  • {fecha_cesion}: {receptor.nombre} {jornada_cedida}, {solicitante.nombre} {jornada_otra}')
                    self.stdout.write(f'  • {fecha_pago}: {solicitante.nombre} {jornada_cedida} (paga), {receptor.nombre} {jornada_otra}')
                else:
                    self.stdout.write(f'  • {receptor.nombre} DOBLADA en {fecha_cesion}, {solicitante.nombre} DOBLADA en {fecha_pago}')
                self.stdout.write('  • La doblada debería aparecer en "Mis Turnos"')
            else:
                self.stdout.write(self.style.ERROR(
                    '❌ ERROR: La doblada no se aplicó completamente.'
                ))
                if not tiene_doblada_cesion:
                    self.stdout.write('  • Estado incorrecto en fecha de cesión')
                if not tiene_doblada_pago:
                    self.stdout.write('  • Estado incorrecto en fecha de pago')

        except SolicitudCambio.DoesNotExist:
            raise CommandError(f'La solicitud con ID {solicitud_id} no existe')
        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ ERROR: {str(e)}'))
            logger.error(f'Error reaplicando doblada {solicitud_id}: {str(e)}', exc_info=True)
            raise

