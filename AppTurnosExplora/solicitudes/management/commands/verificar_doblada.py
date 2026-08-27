"""
Management command para verificar el estado de una doblada aplicada.

Uso:
    python manage.py verificar_doblada <solicitud_id>

Parámetros:
    solicitud_id: ID de la solicitud de doblada a verificar

Este comando verifica:
    1. Estado de la solicitud
    2. Turnos creados para receptor (fecha de cesión)
    3. Turnos creados para solicitante (fecha de pago)
    4. Deudas generadas (DeudaExplorador y DeudaCorporativa)
    5. Validación de integridad de datos
    6. Visualización en "Mis Turnos" (simulada)

Ejemplo:
    python manage.py verificar_doblada 123
"""
import logging

from django.core.management.base import BaseCommand, CommandError

from core.constants import JornadaDisplay
from solicitudes.models import DeudaCorporativa, DeudaExplorador, SolicitudCambio
from turnos.models import Turno
from turnos.services.turno_service import TurnoService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Verifica el estado de una doblada aplicada'

    def add_arguments(self, parser):
        parser.add_argument(
            'solicitud_id',
            type=int,
            help='ID de la solicitud de doblada a verificar'
        )

    def handle(self, *args, **options):
        solicitud_id = options['solicitud_id']

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

            detalle = solicitud.doblada
            solicitante = solicitud.explorador_solicitante
            receptor = solicitud.explorador_receptor
            fecha_cesion = solicitud.fecha_cambio_turno
            fecha_pago = detalle.fecha_pago

            # Banner principal
            self.stdout.write('')
            self.stdout.write('=' * 80)
            self.stdout.write(self.style.HTTP_INFO('  VERIFICACIÓN DE DOBLADA'))
            self.stdout.write('=' * 80)
            self.stdout.write('')

            # ============================================================
            # 1. INFORMACIÓN GENERAL
            # ============================================================
            self.stdout.write(self.style.HTTP_INFO('📋 INFORMACIÓN GENERAL'))
            self.stdout.write('-' * 80)
            self.stdout.write(f'  ID Solicitud:        {solicitud.id}')
            self.stdout.write(f'  Estado:              {solicitud.estado.upper()}')
            self.stdout.write(f'  Fecha Solicitud:     {solicitud.fecha_solicitud}')
            self.stdout.write(f'  Tipo de Cesión:      {detalle.tipo_cesion}')
            if detalle.jornada_cedida:
                self.stdout.write(f'  Jornada Cedida:      {detalle.jornada_cedida}')
            self.stdout.write('')
            self.stdout.write(f'  Solicitante (Deudor):  {solicitante.nombre} (ID: {solicitante.id})')
            self.stdout.write(f'  Receptor (Acreedor):   {receptor.nombre} (ID: {receptor.id})')
            self.stdout.write('')
            self.stdout.write(f'  Fecha de Cesión:     {fecha_cesion}')
            self.stdout.write(f'  Fecha de Pago:       {fecha_pago}')
            self.stdout.write('')

            # ============================================================
            # 2. TURNOS EN FECHA DE CESIÓN
            # ============================================================
            self.stdout.write(self.style.HTTP_INFO(f'📅 TURNOS EN FECHA DE CESIÓN ({fecha_cesion})'))
            self.stdout.write('-' * 80)

            # Receptor (debe tener AM+PM = DOBLADA)
            turnos_receptor_cesion = list(Turno.objects.filter(
                explorador=receptor,
                fecha=fecha_cesion
            ).select_related('jornada', 'sala').order_by('jornada__nombre'))

            jornadas_receptor = [t.jornada.nombre.upper() for t in turnos_receptor_cesion]
            tiene_doblada_receptor = 'AM' in jornadas_receptor and 'PM' in jornadas_receptor

            self.stdout.write(f'  🔹 Receptor ({receptor.nombre}):')
            if turnos_receptor_cesion:
                for turno in turnos_receptor_cesion:
                    self.stdout.write(
                        f'     • Jornada: {turno.jornada.nombre} | Sala: {turno.sala.nombre} | '
                        f'Tipo: {turno.tipo_cambio or "N/A"}'
                    )
                if tiene_doblada_receptor:
                    self.stdout.write(self.style.SUCCESS('     ✅ Tiene DOBLADA completa (AM + PM)'))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'     ⚠️  No tiene DOBLADA completa (tiene: {", ".join(jornadas_receptor)})'
                    ))
            else:
                self.stdout.write(self.style.ERROR('     ❌ Sin turnos (ERROR: debería tener DOBLADA)'))

            # Jornada display (lo que vería en "Mis Turnos")
            jornada_display_receptor = TurnoService.obtener_jornada_display(receptor, fecha_cesion)
            self.stdout.write(f'     👁️  Visualización en "Mis Turnos": {jornada_display_receptor or "DESCANSO"}')

            self.stdout.write('')

            # Solicitante (debe descansar = sin turnos)
            turnos_solicitante_cesion = list(Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_cesion
            ).select_related('jornada', 'sala').order_by('jornada__nombre'))

            self.stdout.write(f'  🔹 Solicitante ({solicitante.nombre}):')
            if turnos_solicitante_cesion:
                if detalle.tipo_cesion == 'cesion_completa':
                    self.stdout.write(self.style.WARNING(
                        '     ⚠️  Tiene turnos (debería descansar en cesión completa):'
                    ))
                else:
                    self.stdout.write('     • Tiene turnos (cesión parcial):')
                for turno in turnos_solicitante_cesion:
                    self.stdout.write(
                        f'       - Jornada: {turno.jornada.nombre} | Sala: {turno.sala.nombre} | '
                        f'Tipo: {turno.tipo_cambio or "N/A"}'
                    )
            else:
                self.stdout.write(self.style.SUCCESS('     ✅ Descansa (sin turnos)'))

            jornada_display_solicitante_cesion = TurnoService.obtener_jornada_display(solicitante, fecha_cesion)
            self.stdout.write(f'     👁️  Visualización en "Mis Turnos": {jornada_display_solicitante_cesion or "DESCANSO"}')

            self.stdout.write('')

            # ============================================================
            # 3. TURNOS EN FECHA DE PAGO
            # ============================================================
            self.stdout.write(self.style.HTTP_INFO(f'📅 TURNOS EN FECHA DE PAGO ({fecha_pago})'))
            self.stdout.write('-' * 80)

            # Solicitante (debe tener AM+PM = DOBLADA)
            turnos_solicitante_pago = list(Turno.objects.filter(
                explorador=solicitante,
                fecha=fecha_pago
            ).select_related('jornada', 'sala').order_by('jornada__nombre'))

            jornadas_solicitante = [t.jornada.nombre.upper() for t in turnos_solicitante_pago]
            tiene_doblada_solicitante = 'AM' in jornadas_solicitante and 'PM' in jornadas_solicitante

            self.stdout.write(f'  🔹 Solicitante ({solicitante.nombre}):')
            if turnos_solicitante_pago:
                for turno in turnos_solicitante_pago:
                    self.stdout.write(
                        f'     • Jornada: {turno.jornada.nombre} | Sala: {turno.sala.nombre} | '
                        f'Tipo: {turno.tipo_cambio or "N/A"}'
                    )
                if tiene_doblada_solicitante:
                    self.stdout.write(self.style.SUCCESS('     ✅ Tiene DOBLADA completa (AM + PM)'))
                else:
                    # Caso especial: pago en sábado con jornada única
                    if fecha_pago.weekday() == 5 and detalle.jornada_pago_sabado:
                        self.stdout.write(self.style.SUCCESS(
                            f'     ✅ Pago en sábado: trabaja jornada {detalle.jornada_pago_sabado} '
                            f'(tiene: {", ".join(jornadas_solicitante)})'
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f'     ⚠️  No tiene DOBLADA completa (tiene: {", ".join(jornadas_solicitante)})'
                        ))
            else:
                self.stdout.write(self.style.ERROR('     ❌ Sin turnos (ERROR: debería tener DOBLADA)'))

            jornada_display_solicitante_pago = TurnoService.obtener_jornada_display(solicitante, fecha_pago)
            self.stdout.write(f'     👁️  Visualización en "Mis Turnos": {jornada_display_solicitante_pago or "DESCANSO"}')

            self.stdout.write('')

            # Receptor (debe descansar = sin turnos)
            turnos_receptor_pago = list(Turno.objects.filter(
                explorador=receptor,
                fecha=fecha_pago
            ).select_related('jornada', 'sala').order_by('jornada__nombre'))

            self.stdout.write(f'  🔹 Receptor ({receptor.nombre}):')
            if turnos_receptor_pago:
                # Caso especial: pago en sábado (receptor trabaja jornada contraria)
                if fecha_pago.weekday() == 5 and detalle.jornada_pago_sabado:
                    jornada_contraria = 'PM' if detalle.jornada_pago_sabado == 'AM' else 'AM'
                    self.stdout.write(self.style.SUCCESS(
                        f'     ✅ Pago en sábado: trabaja jornada {jornada_contraria}:'
                    ))
                else:
                    self.stdout.write(self.style.WARNING('     ⚠️  Tiene turnos (debería descansar):'))
                for turno in turnos_receptor_pago:
                    self.stdout.write(
                        f'       - Jornada: {turno.jornada.nombre} | Sala: {turno.sala.nombre} | '
                        f'Tipo: {turno.tipo_cambio or "N/A"}'
                    )
            else:
                self.stdout.write(self.style.SUCCESS('     ✅ Descansa (sin turnos)'))

            jornada_display_receptor_pago = TurnoService.obtener_jornada_display(receptor, fecha_pago)
            self.stdout.write(f'     👁️  Visualización en "Mis Turnos": {jornada_display_receptor_pago or "DESCANSO"}')

            self.stdout.write('')

            # ============================================================
            # 4. DEUDAS ENTRE EXPLORADORES
            # ============================================================
            self.stdout.write(self.style.HTTP_INFO('💰 DEUDAS ENTRE EXPLORADORES'))
            self.stdout.write('-' * 80)

            deudas_explorador = DeudaExplorador.objects.filter(
                solicitud_origen=solicitud
            ).select_related('deudor', 'acreedor')

            if deudas_explorador.exists():
                for deuda in deudas_explorador:
                    self.stdout.write(f'  🔹 Deuda ID: {deuda.id}')
                    self.stdout.write(f'     Deudor:             {deuda.deudor.nombre}')
                    self.stdout.write(f'     Acreedor:           {deuda.acreedor.nombre}')
                    self.stdout.write(f'     Estado:             {deuda.estado.upper()}')
                    self.stdout.write(f'     Jornada Cedida:     {deuda.jornada_cedida}')
                    self.stdout.write(f'     Media Jornada:      {"Sí" if deuda.media_jornada else "No"}')
                    self.stdout.write(f'     Fecha Generación:   {deuda.fecha_generacion}')
                    self.stdout.write(f'     Fecha Pago Pactada: {deuda.fecha_pago_pactada}')
                    if deuda.fecha_pago_real:
                        self.stdout.write(f'     Fecha Pago Real:    {deuda.fecha_pago_real}')
                    
                    if deuda.estado == 'pagada':
                        self.stdout.write(self.style.SUCCESS('     ✅ Estado: PAGADA'))
                    elif deuda.estado == 'pendiente':
                        self.stdout.write(self.style.WARNING('     ⚠️  Estado: PENDIENTE'))
                    else:
                        self.stdout.write(f'     Estado: {deuda.estado.upper()}')
                    self.stdout.write('')
            else:
                self.stdout.write(self.style.ERROR('  ❌ No se encontraron deudas entre exploradores'))
                self.stdout.write('')

            # ============================================================
            # 5. DEUDAS CORPORATIVAS
            # ============================================================
            self.stdout.write(self.style.HTTP_INFO('🏢 DEUDAS CORPORATIVAS'))
            self.stdout.write('-' * 80)

            deudas_corporativas = DeudaCorporativa.objects.filter(
                solicitud_origen=solicitud
            ).select_related('explorador').order_by('fecha_doblada')

            if deudas_corporativas.exists():
                for deuda in deudas_corporativas:
                    self.stdout.write(f'  🔹 Deuda ID: {deuda.id}')
                    self.stdout.write(f'     Explorador:       {deuda.explorador.nombre}')
                    self.stdout.write(f'     Minutos:          {deuda.minutos} min')
                    self.stdout.write(f'     Fecha Doblada:    {deuda.fecha_doblada}')
                    self.stdout.write(f'     Estado:           {deuda.estado.upper()}')
                    self.stdout.write(f'     Comentario:       {deuda.comentario or "N/A"}')
                    
                    # Verificar que corresponda a doblada efectiva
                    jornada_display = TurnoService.obtener_jornada_display(
                        deuda.explorador, deuda.fecha_doblada
                    )
                    if jornada_display == JornadaDisplay.DOBLADA:
                        self.stdout.write(self.style.SUCCESS('     ✅ Corresponde a DOBLADA efectiva (AM+PM)'))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f'     ⚠️  NO corresponde a DOBLADA (jornada: {jornada_display})'
                        ))
                    self.stdout.write('')
            else:
                self.stdout.write(self.style.WARNING('  ⚠️  No se encontraron deudas corporativas'))
                self.stdout.write('      (Es normal si las fechas no son sábado/domingo o si no hay AM+PM completo)')
                self.stdout.write('')

            # ============================================================
            # 6. RESUMEN Y VALIDACIÓN
            # ============================================================
            self.stdout.write(self.style.HTTP_INFO('✅ RESUMEN Y VALIDACIÓN'))
            self.stdout.write('-' * 80)

            errores = []
            advertencias = []
            exitos = []

            # Validar fecha de cesión
            if tiene_doblada_receptor:
                exitos.append(f'Receptor ({receptor.nombre}) tiene DOBLADA en fecha de cesión')
            else:
                errores.append(f'Receptor ({receptor.nombre}) NO tiene DOBLADA en fecha de cesión')

            if not turnos_solicitante_cesion or detalle.tipo_cesion != 'cesion_completa':
                exitos.append(f'Solicitante ({solicitante.nombre}) descansa en fecha de cesión')
            else:
                if detalle.tipo_cesion == 'cesion_completa':
                    advertencias.append(f'Solicitante ({solicitante.nombre}) tiene turnos en cesión completa')

            # Validar fecha de pago
            if fecha_pago.weekday() == 5 and detalle.jornada_pago_sabado:
                # Caso especial: pago en sábado
                if jornadas_solicitante and detalle.jornada_pago_sabado in jornadas_solicitante:
                    exitos.append(
                        f'Solicitante ({solicitante.nombre}) trabaja jornada {detalle.jornada_pago_sabado} '
                        f'en sábado (fecha de pago)'
                    )
                else:
                    errores.append(
                        f'Solicitante ({solicitante.nombre}) NO trabaja jornada {detalle.jornada_pago_sabado} '
                        f'en sábado'
                    )
            else:
                # Caso normal: pago con doblada completa
                if tiene_doblada_solicitante:
                    exitos.append(f'Solicitante ({solicitante.nombre}) tiene DOBLADA en fecha de pago')
                else:
                    errores.append(f'Solicitante ({solicitante.nombre}) NO tiene DOBLADA en fecha de pago')

            # Validar descanso del receptor en fecha de pago
            if not turnos_receptor_pago or (fecha_pago.weekday() == 5 and detalle.jornada_pago_sabado):
                exitos.append(f'Receptor ({receptor.nombre}) descansa (o trabaja jornada contraria) en fecha de pago')
            else:
                advertencias.append(f'Receptor ({receptor.nombre}) tiene turnos en fecha de pago')

            # Validar deudas
            if deudas_explorador.exists():
                exitos.append('Deuda entre exploradores generada')
            else:
                errores.append('Falta deuda entre exploradores')

            # Mostrar resumen
            if exitos:
                self.stdout.write(self.style.SUCCESS('  ÉXITOS:'))
                for exito in exitos:
                    self.stdout.write(self.style.SUCCESS(f'    ✅ {exito}'))
                self.stdout.write('')

            if advertencias:
                self.stdout.write(self.style.WARNING('  ADVERTENCIAS:'))
                for adv in advertencias:
                    self.stdout.write(self.style.WARNING(f'    ⚠️  {adv}'))
                self.stdout.write('')

            if errores:
                self.stdout.write(self.style.ERROR('  ERRORES:'))
                for error in errores:
                    self.stdout.write(self.style.ERROR(f'    ❌ {error}'))
                self.stdout.write('')

            # Veredicto final
            self.stdout.write('=' * 80)
            if not errores:
                self.stdout.write(self.style.SUCCESS(
                    '  ✅ DOBLADA APLICADA CORRECTAMENTE'
                ))
            else:
                self.stdout.write(self.style.ERROR(
                    '  ❌ DOBLADA CON ERRORES - Se requiere reaplicación'
                ))
                self.stdout.write('')
                self.stdout.write('  💡 Sugerencia: Ejecuta el comando de reaplicación:')
                self.stdout.write(f'     python manage.py reaplicar_doblada {solicitud_id}')
            self.stdout.write('=' * 80)
            self.stdout.write('')

        except SolicitudCambio.DoesNotExist:
            raise CommandError(f'La solicitud con ID {solicitud_id} no existe')
        except Exception as e:
            self.stdout.write('')
            self.stdout.write(self.style.ERROR(f'❌ ERROR: {str(e)}'))
            logger.error(f'Error verificando doblada {solicitud_id}: {str(e)}', exc_info=True)
            raise

