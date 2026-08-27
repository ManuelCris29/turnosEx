"""
Corrige una solicitud de doblada que se creó como parcial (o dos parciales) a cesión total.

Uso cuando hiciste "cesión total" (mismo receptor AM y PM, misma fecha de pago) pero el sistema
creó 2 solicitudes parciales o guardó tipo_cesion como parcial:

  python manage.py corregir_doblada_cesion_total SOLICITUD_ID [SOLICITUD_ID2] [--reaplicar]

- Si pasas un solo ID: se pone tipo_cesion=cesion_completa en esa solicitud.
- Si pasas dos IDs (las dos parciales AM y PM): se pone cesion_completa en la primera,
  se cancela la segunda y se reaplican los turnos usando la primera.
- Con --reaplicar se reaplican los turnos después de corregir.
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.services.cache_service import CacheService
from solicitudes.models import SolicitudCambio
from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
from turnos.models import Turno


class Command(BaseCommand):
    help = 'Corrige doblada a cesión total (cesion_completa) y opcionalmente reaplica'

    def add_arguments(self, parser):
        parser.add_argument('ids', nargs='+', type=int, help='ID(s) de solicitud(es) (1 o 2)')
        parser.add_argument('--reaplicar', action='store_true', help='Reaplicar turnos después de corregir')

    def handle(self, *args, **options):
        ids = options['ids']
        reaplicar = options['reaplicar']

        if len(ids) not in (1, 2):
            raise CommandError('Indica 1 o 2 IDs de solicitud.')

        with transaction.atomic():
            s1 = SolicitudCambio.objects.select_related(
                'tipo_cambio', 'explorador_solicitante', 'explorador_receptor', 'doblada'
            ).get(id=ids[0])
            if s1.tipo_cambio.nombre != 'DOBLADA':
                raise CommandError(f'La solicitud {ids[0]} no es de tipo DOBLADA.')
            if not s1.doblada:
                raise CommandError(f'La solicitud {ids[0]} no tiene detalle doblada.')

            detalle1 = s1.doblada
            detalle1.tipo_cesion = 'cesion_completa'
            detalle1.jornada_cedida = None
            detalle1.save(update_fields=['tipo_cesion', 'jornada_cedida'])
            self.stdout.write(self.style.SUCCESS(f'Solicitud {ids[0]}: tipo_cesion=cesion_completa, jornada_cedida=null'))

            if len(ids) == 2:
                s2 = SolicitudCambio.objects.select_related('tipo_cambio', 'doblada').get(id=ids[1])
                if s2.tipo_cambio.nombre != 'DOBLADA' or not s2.doblada:
                    raise CommandError(f'La solicitud {ids[1]} no es doblada válida.')
                # Cancelar la segunda para que no cuente como activa
                s2.estado = 'cancelada'
                s2.fecha_resolucion = timezone.now()
                s2.save(update_fields=['estado', 'fecha_resolucion'])
                self.stdout.write(self.style.WARNING(f'Solicitud {ids[1]} cancelada (cesión total unificada en {ids[0]}).'))

        if reaplicar or len(ids) == 2:
            self.stdout.write('Reaplicando turnos...')
            solicitante = s1.explorador_solicitante
            receptor = s1.explorador_receptor
            fecha_cesion = s1.fecha_cambio_turno
            fecha_pago = detalle1.fecha_pago
            Turno.objects.filter(
                explorador__in=[solicitante, receptor],
                fecha__in=[fecha_cesion, fecha_pago]
            ).delete()
            DobladaAplicacionService.aplicar_doblada_cesion(s1, detalle1)
            DobladaAplicacionService.aplicar_doblada_pago(s1, detalle1)
            if s1.estado == 'aprobada':
                DobladaAplicacionService.generar_deudas_doblada(s1, detalle1)
            for fecha in [fecha_cesion, fecha_pago]:
                CacheService.invalidar_cache_turnos_empleado(solicitante.id, fecha.month, fecha.year)
                CacheService.invalidar_cache_turnos_empleado(receptor.id, fecha.month, fecha.year)
            self.stdout.write(self.style.SUCCESS(
                f'Listo: {fecha_cesion} {receptor.nombre} dobla, {solicitante.nombre} descansa; '
                f'{fecha_pago} {solicitante.nombre} dobla, {receptor.nombre} descansa.'
            ))
        else:
            self.stdout.write('Ejecuta: python manage.py reaplicar_doblada {} para aplicar turnos.'.format(ids[0]))
