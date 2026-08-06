"""
Verifica que el EFECTO de cada solicitud aprobada siga materializado en los turnos.

Complementa `verificar_integridad_dobladas` (que solo mira DOBLADA y espera un patrón concreto
de turnos): aquí la comprobación es genérica y se apoya en `snapshot_turnos_resultantes`, o sea
"lo que esta solicitud dejó en estos días". Si el estado real ya no coincide, alguien pisó esos
turnos y la solicitud sigue aprobada sin efecto — el horario muestra una cosa y las capas de
Mis Turnos otra.

Origen: una reconciliación posterior a una cancelación re-aplicaba un CAMBIO DESCANSO de finde,
que reescribe los DOS findes completos, y borraba una D FDS posterior que vivía en dos de esos
días colaterales. Nada avisaba. La causa está corregida (`DobladaSnapshotService._cerrar_afectados`),
pero conviene poder AUDITAR y REPARAR lo que quedó descuadrado.

Uso:
    python manage.py verificar_efecto_aplicado
    python manage.py verificar_efecto_aplicado --desde 2026-08-01
    python manage.py verificar_efecto_aplicado --reparar
    python manage.py verificar_efecto_aplicado --reparar --solicitud 554
"""
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from solicitudes.models import SolicitudCambio
from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService
from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase
from turnos.models import Turno


def _snapshots(solicitud):
    """(previos, resultantes) de la solicitud, vengan del propio objeto o de su detalle."""
    previos, resultantes = {}, {}
    for obj in (solicitud, getattr(solicitud, 'doblada', None),
                getattr(solicitud, 'doblada_permanente', None),
                getattr(solicitud, 'cambio_permanente', None)):
        if obj is None:
            continue
        previos = previos or (getattr(obj, 'snapshot_turnos_previos', None) or {})
        resultantes = resultantes or (getattr(obj, 'snapshot_turnos_resultantes', None) or {})
    return previos, resultantes


class Command(BaseCommand):
    help = 'Verifica (y opcionalmente repara) que el efecto de las solicitudes aprobadas siga aplicado'

    def add_arguments(self, parser):
        parser.add_argument('--desde', type=str, help='Solo solicitudes que tocan fechas >= AAAA-MM-DD '
                                                      '(por defecto: hace 30 días)')
        parser.add_argument('--solicitud', type=int, help='Verificar/reparar solo esta solicitud')
        parser.add_argument('--reparar', action='store_true',
                            help='Re-materializa los días descuadrados con la reconciliación')
        parser.add_argument('--incluir-sin-snapshot', action='store_true',
                            help='En modo reparación, reconcilia también las que no tienen '
                                 'snapshot resultante (no verificables, pero sí reparables)')

    def handle(self, *args, **opts):
        desde = (date.fromisoformat(opts['desde']) if opts.get('desde')
                 else timezone.localdate() - timedelta(days=30))
        reparar = opts['reparar']

        qs = (SolicitudCambio.objects.filter(estado='aprobada')
              .select_related('doblada', 'doblada_permanente', 'cambio_permanente',
                              'tipo_cambio', 'explorador_solicitante', 'explorador_receptor')
              .order_by('fecha_resolucion', 'id'))
        if opts.get('solicitud'):
            qs = qs.filter(id=opts['solicitud'])

        desajustadas, sin_snapshot = [], []
        for s in qs:
            previos, resultantes = _snapshots(s)
            pares = DobladaSnapshotService.fechas_explorador_afectados(previos or resultantes)
            if not pares or max(f for (_e, f) in pares) < desde:
                continue
            if not resultantes:
                sin_snapshot.append((s, pares))
                continue
            conflictos = self._conflictos(resultantes)
            if conflictos:
                desajustadas.append((s, pares, conflictos))

        self._reportar(desajustadas, sin_snapshot, desde)

        if not reparar:
            if desajustadas:
                self.stdout.write(self.style.WARNING(
                    '\nVuelve a ejecutar con --reparar para re-materializar los días descuadrados.'))
            return

        a_reparar = [(s, pares) for (s, pares, _c) in desajustadas]
        if opts['incluir_sin_snapshot']:
            a_reparar += sin_snapshot

        # `--solicitud N --reparar` reconcilia SIEMPRE esa solicitud, la detecte o no.
        #
        # Hace falta porque la detección puede estar ciega: si el resultante de una solicitud fue
        # refrescado mientras su efecto estaba roto, quedó grabado el estado roto como propio y la
        # comparación no encuentra nada (le pasó a la D FDS #554). El origen de esa corrupción está
        # cerrado —`refrescar_resultantes` solo toca lo que se re-aplicó—, pero lo ya grabado no se
        # cura solo, y reconciliar sobre sus fechas es inocuo: re-aplica lo vigente en orden.
        if opts.get('solicitud') and not a_reparar:
            for s in qs:
                previos, resultantes = _snapshots(s)
                pares = DobladaSnapshotService.fechas_explorador_afectados(previos or resultantes)
                if pares:
                    self.stdout.write(self.style.WARNING(
                        f'  #{s.id} sin desajuste detectable: se reconcilia igualmente por '
                        f'petición explícita (--solicitud).'))
                    a_reparar.append((s, pares))
        if not a_reparar:
            return

        # La reconciliación re-aplica TODAS las solicitudes vigentes sobre las fechas afectadas
        # (con su cierre de días colaterales) en orden de aprobación, así que reconstruye el
        # estado correcto sin que este comando tenga que saber de tipos de solicitud.
        with transaction.atomic():
            for s, pares in a_reparar:
                DobladaSnapshotService.reconciliar_dobladas_aprobadas(pares, excluir_solicitud_id=0)
                self.stdout.write(self.style.SUCCESS(
                    f'  reconciliada solicitud {s.id} ({len(pares)} par(es) persona-día)'))

        self.stdout.write(self.style.SUCCESS('\nReparación terminada. Vuelve a ejecutar sin '
                                             '--reparar para confirmar que ya no hay desajustes.'))

    @staticmethod
    def _conflictos(resultantes: dict) -> dict:
        """{explorador_id: {fechas}} donde el estado real no coincide con lo que la solicitud dejó."""
        uc = CancelarSolicitudUseCase
        conflictos = {}
        for clave, filas in resultantes.items():
            try:
                emp_id, fecha_str = clave.split(':', 1)
                emp_id = int(emp_id)
                fecha = date.fromisoformat(fecha_str)
            except (ValueError, TypeError, AttributeError):
                continue
            esperado = {uc._huella_fila(f) for f in (filas or [])}
            actual = {uc._huella_turno(t) for t in
                      Turno.objects.filter(explorador_id=emp_id, fecha=fecha).select_related('jornada')}
            if esperado != actual:
                conflictos.setdefault(emp_id, set()).add(fecha)
        return conflictos

    def _reportar(self, desajustadas, sin_snapshot, desde):
        self.stdout.write(self.style.SUCCESS(f'Efecto de solicitudes aprobadas desde {desde}'))
        if not desajustadas:
            self.stdout.write(self.style.SUCCESS('  Sin desajustes: todo lo aprobado sigue aplicado.'))
        for s, _pares, conflictos in desajustadas:
            tipo = s.tipo_cambio.nombre if s.tipo_cambio else '?'
            self.stdout.write(self.style.ERROR(
                f'  #{s.id} {tipo} ({s.explorador_solicitante} → {s.explorador_receptor}): '
                f'su efecto ya no está en los turnos'))
            for emp_id, fechas in sorted(conflictos.items()):
                dias = ', '.join(f.strftime('%d/%m/%Y') for f in sorted(fechas))
                self.stdout.write(f'      explorador {emp_id}: {dias}')
        if sin_snapshot:
            self.stdout.write(self.style.WARNING(
                f'\n  {len(sin_snapshot)} solicitud(es) sin snapshot resultante — no verificables '
                f'(y con la guardia de integridad de su cancelación desactivada): '
                f'{", ".join(str(s.id) for s, _p in sin_snapshot)}'))
