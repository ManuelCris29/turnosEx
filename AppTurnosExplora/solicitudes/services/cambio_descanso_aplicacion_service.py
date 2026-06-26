"""
Aplicación del Cambio de Día de Descanso (fin de semana).

Es un INTERCAMBIO puro de descansos entre dos exploradores de grupos contrarios
(nadie dobla, no hay deudas):

- Finde de cesión (W1): el solicitante cede SU día (descansa ese día) y trabaja el otro
  día del finde; el receptor toma el día del solicitante (lo trabaja) y descansa el suyo.
- Finde de devolución (W2, mismo mes y MISMO tipo de día): el espejo, para que los
  domingos/sábados de cada quien queden iguales que antes.

Cada explorador sigue trabajando UN solo día por finde (AM+PM completo), solo cambia CUÁL.
"""
from datetime import date, timedelta
import logging

from django.db import transaction

from turnos.models import Turno
from turnos.services.doblada_turno_service import DobladaTurnoService

logger = logging.getLogger(__name__)


def _otro_dia(fecha: date) -> date:
    """El otro día del mismo fin de semana (sábado<->domingo)."""
    return fecha + timedelta(days=1) if fecha.weekday() == 5 else fecha - timedelta(days=1)


class CambioDescansoAplicacionService:

    @staticmethod
    def _jornadas():
        from turnos.models import Jornada
        return {'AM': Jornada.objects.get(nombre='AM'), 'PM': Jornada.objects.get(nombre='PM')}

    @staticmethod
    def _trabaja_dia(explorador, fecha, tipo_cambio='CAMBIO DESCANSO'):
        """Deja al explorador trabajando el día completo (AM+PM) en `fecha`."""
        jc = CambioDescansoAplicacionService._jornadas()
        Turno.objects.filter(explorador=explorador, fecha=fecha).delete()
        sala = DobladaTurnoService.obtener_sala_explorador_fecha(explorador, fecha)
        for nombre in ('AM', 'PM'):
            Turno.objects.create(explorador=explorador, fecha=fecha, jornada=jc[nombre],
                                 sala=sala, tipo_cambio=tipo_cambio)

    @staticmethod
    def _trabaja_jornada_simple(explorador, fecha, tipo_cambio='CAMBIO DESCANSO'):
        """Deja al explorador trabajando UNA jornada (su grupo base AM/PM) en `fecha` (entre semana)."""
        from turnos.models import AsignarJornadaExplorador, Jornada
        asg = (AsignarJornadaExplorador.objects.filter(explorador=explorador, fecha_inicio__lte=fecha)
               .select_related('jornada').order_by('-fecha_inicio').first())
        nombre = asg.jornada.nombre.upper() if asg else 'AM'
        jornada = Jornada.objects.get(nombre=nombre)
        Turno.objects.filter(explorador=explorador, fecha=fecha).delete()
        sala = DobladaTurnoService.obtener_sala_explorador_fecha(explorador, fecha)
        Turno.objects.create(explorador=explorador, fecha=fecha, jornada=jornada, sala=sala, tipo_cambio=tipo_cambio)

    @staticmethod
    def _descansa_dia(explorador, fecha):
        """Deja al explorador descansando `fecha` (borra cualquier turno de ese día)."""
        Turno.objects.filter(explorador=explorador, fecha=fecha).delete()

    @staticmethod
    def _capturar_snapshot(solicitante, receptor, fechas):
        snap = {}
        for emp in (solicitante, receptor):
            for f in fechas:
                key = f"{emp.id}:{f.isoformat()}"
                turnos = Turno.objects.filter(explorador=emp, fecha=f).select_related('jornada').order_by('jornada_id')
                snap[key] = [
                    {'jornada_nombre': t.jornada.nombre.upper(), 'sala_id': t.sala_id, 'tipo_cambio': t.tipo_cambio}
                    for t in turnos
                ]
        return snap

    @staticmethod
    @transaction.atomic
    def aplicar(solicitud, detalle):
        """Aplica el intercambio de descansos en los dos findes (cesión y devolución)."""
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno     # día del solicitante (W1)
        fecha_pago = detalle.fecha_pago                 # día del receptor (W2)

        otro_w1 = _otro_dia(fecha_cesion)
        otro_w2 = _otro_dia(fecha_pago)

        # Snapshot para revertir. Solo la PRIMERA vez: si ya existe, no sobrescribir
        # (una doble aplicación grabaría el estado ya aplicado como "previo").
        if not getattr(detalle, 'snapshot_turnos_previos', None):
            snap = CambioDescansoAplicacionService._capturar_snapshot(
                solicitante, receptor, [fecha_cesion, otro_w1, fecha_pago, otro_w2]
            )
            from solicitudes.models import DobladaDetalle as _DD
            _DD.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snap)
            detalle.snapshot_turnos_previos = snap

        # --- W1 (cesión): se intercambian el finde ---
        # receptor toma el día del solicitante; solicitante toma el otro día.
        CambioDescansoAplicacionService._trabaja_dia(receptor, fecha_cesion)
        CambioDescansoAplicacionService._descansa_dia(receptor, otro_w1)
        CambioDescansoAplicacionService._trabaja_dia(solicitante, otro_w1)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fecha_cesion)

        # --- W2 (devolución): espejo ---
        CambioDescansoAplicacionService._trabaja_dia(solicitante, fecha_pago)
        CambioDescansoAplicacionService._descansa_dia(solicitante, otro_w2)
        CambioDescansoAplicacionService._trabaja_dia(receptor, otro_w2)
        CambioDescansoAplicacionService._descansa_dia(receptor, fecha_pago)

        logger.info(
            "Cambio de descanso aplicado: solicitud %s — cesión %s, devolución %s",
            solicitud.id, fecha_cesion, fecha_pago,
        )

    @staticmethod
    @transaction.atomic
    def aplicar_entre_semana(solicitud, detalle):
        """
        Intercambio de descanso ENTRE SEMANA (jornada simple):
        - fecha_cesion: el solicitante pasa a TRABAJAR su jornada; el receptor DESCANSA.
        - fecha_pago: el solicitante DESCANSA; el receptor TRABAJA su jornada.
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago

        # Solo capturar la PRIMERA vez (idempotente ante doble aplicación accidental).
        if not getattr(detalle, 'snapshot_turnos_previos', None):
            snap = CambioDescansoAplicacionService._capturar_snapshot(
                solicitante, receptor, [fecha_cesion, fecha_pago]
            )
            from solicitudes.models import DobladaDetalle as _DD
            _DD.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snap)
            detalle.snapshot_turnos_previos = snap

        CambioDescansoAplicacionService._trabaja_jornada_simple(solicitante, fecha_cesion)
        CambioDescansoAplicacionService._descansa_dia(receptor, fecha_cesion)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fecha_pago)
        CambioDescansoAplicacionService._trabaja_jornada_simple(receptor, fecha_pago)

        logger.info("Cambio de descanso (entre semana) aplicado: solicitud %s — %s <-> %s",
                    solicitud.id, fecha_cesion, fecha_pago)

    @staticmethod
    @transaction.atomic
    def revertir(solicitud):
        """Restaura los turnos previos desde el snapshot."""
        from .doblada_aplicacion_service import DobladaAplicacionService
        detalle = solicitud.doblada
        snap = getattr(detalle, 'snapshot_turnos_previos', None)
        if snap:
            DobladaAplicacionService.restaurar_turnos_desde_snapshot(snap)
        logger.info("Cambio de descanso revertido: solicitud %s", solicitud.id)
