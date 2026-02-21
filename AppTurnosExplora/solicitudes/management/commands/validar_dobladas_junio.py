"""
Valida solicitudes y turnos de doblada para fechas concretas (ej. 8 y 15 junio 2026).

Uso:
  python manage.py validar_dobladas_junio
  python manage.py validar_dobladas_junio --fechas 2026-06-08 2026-06-15
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from datetime import datetime
from solicitudes.models import SolicitudCambio
from turnos.models import Turno


class Command(BaseCommand):
    help = 'Valida estado de dobladas en fechas dadas (por defecto 8 y 15 junio 2026)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fechas',
            nargs='+',
            default=['2026-06-08', '2026-06-15'],
            help='Fechas a validar (YYYY-MM-DD)'
        )

    def handle(self, *args, **options):
        fechas_str = options['fechas']
        fechas = []
        for s in fechas_str:
            try:
                fechas.append(datetime.strptime(s, '%Y-%m-%d').date())
            except ValueError:
                self.stdout.write(self.style.WARNING(f'Fecha ignorada (formato inválido): {s}'))
                continue

        if not fechas:
            self.stdout.write(self.style.ERROR('No hay fechas válidas.'))
            return

        self.stdout.write(self.style.HTTP_INFO('Validación de dobladas'))
        self.stdout.write('')

        for fecha in fechas:
            self._validar_fecha(fecha)

    def _validar_fecha(self, fecha):
        self.stdout.write(self.style.HTTP_INFO(f'--- Fecha {fecha} ---'))

        # Solicitudes de doblada con esta fecha de cesión o de pago
        solicitudes_cesion = SolicitudCambio.objects.filter(
            tipo_cambio__nombre='DOBLADA',
            fecha_cambio_turno=fecha,
            estado__in=['aprobada', 'pendiente']
        ).select_related('explorador_solicitante', 'explorador_receptor', 'doblada')

        solicitudes_pago = SolicitudCambio.objects.filter(
            tipo_cambio__nombre='DOBLADA',
            estado__in=['aprobada', 'pendiente'],
            doblada__fecha_pago=fecha
        ).select_related('explorador_solicitante', 'explorador_receptor', 'doblada')

        todas = list(solicitudes_cesion) + [s for s in solicitudes_pago if s not in solicitudes_cesion]

        if not todas:
            self.stdout.write('  Sin solicitudes de doblada con esta fecha (cesión o pago).')
            # Listar turnos doblada (AM+PM) en esta fecha para ver si "parecen dobladas"
            turnos = Turno.objects.filter(fecha=fecha).select_related('explorador', 'jornada')
            by_emp = {}
            for t in turnos:
                by_emp.setdefault(t.explorador, []).append(t.jornada.nombre)
            for emp, jorns in by_emp.items():
                if 'AM' in jorns and 'PM' in jorns:
                    self.stdout.write(self.style.WARNING(
                        f'  Turnos: {emp.nombre} tiene AM+PM (doblada) en BD.'
                    ))
                else:
                    self.stdout.write(f'  Turnos: {emp.nombre} -> {", ".join(jorns)}')
            self.stdout.write('')
            return

        for sol in todas:
            det = sol.doblada
            es_cesion = sol.fecha_cambio_turno == fecha
            self.stdout.write(
                f'  Solicitud ID={sol.id} estado={sol.estado} tipo_cesion={getattr(det, "tipo_cesion", "N/A")} '
                f'cesión={sol.fecha_cambio_turno} pago={getattr(det, "fecha_pago", None)}'
            )
            self.stdout.write(
                f'    Solicitante: {sol.explorador_solicitante.nombre}  Receptor: {sol.explorador_receptor.nombre}'
            )
            if es_cesion:
                # En fecha de cesión: receptor debería doblar, solicitante según tipo
                turnos_rec = list(Turno.objects.filter(explorador=sol.explorador_receptor, fecha=fecha).values_list('jornada__nombre', flat=True))
                turnos_sol = list(Turno.objects.filter(explorador=sol.explorador_solicitante, fecha=fecha).values_list('jornada__nombre', flat=True))
                self.stdout.write(f'    Turnos en {fecha}: Receptor {turnos_rec}  Solicitante {turnos_sol}')
                if det and det.tipo_cesion == 'cesion_completa':
                    if set(turnos_rec) != {'AM', 'PM'}:
                        self.stdout.write(self.style.WARNING(
                            f'    Esperado: receptor con AM+PM (cesión completa).'
                        ))
                    if turnos_sol:
                        self.stdout.write(self.style.WARNING(
                            f'    Esperado: solicitante sin turnos (descansa).'
                        ))
            else:
                # Fecha de pago
                turnos_sol = list(Turno.objects.filter(explorador=sol.explorador_solicitante, fecha=fecha).values_list('jornada__nombre', flat=True))
                turnos_rec = list(Turno.objects.filter(explorador=sol.explorador_receptor, fecha=fecha).values_list('jornada__nombre', flat=True))
                self.stdout.write(f'    Turnos en {fecha} (pago): Solicitante {turnos_sol}  Receptor {turnos_rec}')
                if det and det.tipo_cesion == 'cesion_completa':
                    if set(turnos_sol) != {'AM', 'PM'}:
                        self.stdout.write(self.style.WARNING(
                            f'    Esperado: solicitante con AM+PM (paga doblada).'
                        ))
                    if turnos_rec:
                        self.stdout.write(self.style.WARNING(
                            f'    Esperado: receptor sin turnos (descansa).'
                        ))

        self.stdout.write('')
