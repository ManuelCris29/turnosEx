"""
Aplicación del Cambio de Día de Descanso (fin de semana y entre semana).

MODALIDAD FIN DE SEMANA:
Es un INTERCAMBIO puro de días trabajados entre dos exploradores de grupos contrarios
(sin dobladas ni deudas):

- Semana 1 (cesión):
  - Solicitante trabaja otro_w1 en lugar de fecha_cesion
  - Receptor trabaja fecha_cesion en lugar de otro_w1
- Semana 2 (devolución): espejo de la semana 1

Cada explorador sigue trabajando UN solo día por finde (su jornada base), solo cambia CUÁL.

MODALIDAD ENTRE SEMANA:
Intercambio DIRECTO de descansos (sin devolución posterior):
- Solicitante: trabaja fecha_cesion en lugar de descansar
- Receptor: descansa fecha_cesion en lugar de trabajar
- Solicitante: descansa fecha_pago en lugar de trabajar
- Receptor: trabaja fecha_pago en lugar de descansar
"""
from datetime import date, timedelta
import logging

from django.db import transaction

from turnos.models import Turno
from turnos.services.doblada_turno_service import DobladaTurnoService

logger = logging.getLogger(__name__)


def _as_date(fecha):
    """Normaliza a date: acepta date o str 'YYYY-MM-DD'."""
    if isinstance(fecha, str):
        from datetime import datetime
        return datetime.strptime(fecha, '%Y-%m-%d').date()
    return fecha


def _otro_dia(fecha: date) -> date:
    """El otro día del mismo fin de semana (sábado<->domingo)."""
    fecha = _as_date(fecha)
    return fecha + timedelta(days=1) if fecha.weekday() == 5 else fecha - timedelta(days=1)


class CambioDescansoAplicacionService:

    @staticmethod
    def _jornadas():
        from turnos.models import Jornada
        return {'AM': Jornada.objects.get(nombre='AM'), 'PM': Jornada.objects.get(nombre='PM')}

    @staticmethod
    def dias_en_descanso(empleado, fecha_inicio, fecha_fin, excluir_id=None):
        """
        Conjunto de fechas en [fecha_inicio, fecha_fin] donde el empleado DESCANSA por una
        solicitud de CAMBIO DESCANSO aprobada (su día cedido, que queda sin registro Turno).

        Misma lógica que usa "Mis Turnos" para pintar el descanso. Sirve para que el
        formulario/validación NO vuelvan a ofrecer un día ya comprometido.

        `excluir_id`: ignora esa solicitud (la PROPIA, al aplicarla ya aprobada).
        """
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio

        fecha_inicio = _as_date(fecha_inicio)
        fecha_fin = _as_date(fecha_fin)
        rest = set()
        qs = (SolicitudCambio.objects
              .filter(tipo_cambio__nombre='CAMBIO DESCANSO', estado='aprobada')
              .filter(Q(explorador_solicitante=empleado) | Q(explorador_receptor=empleado))
              .select_related('doblada'))
        if excluir_id:
            qs = qs.exclude(id=excluir_id)
        for s in qs:
            det = getattr(s, 'doblada', None)
            if not det:
                continue
            fc = _as_date(s.fecha_cambio_turno)
            fp = _as_date(det.fecha_pago)
            es_sol = s.explorador_solicitante_id == empleado.id
            es_finde = bool(fc) and fc.weekday() in (5, 6)
            if es_finde:
                dias = [fc, fp] if es_sol else [_otro_dia(fc), _otro_dia(fp)]
            else:
                dias = [fp] if es_sol else [fc]
            for d in dias:
                if d and fecha_inicio <= d <= fecha_fin:
                    rest.add(d)
        return rest

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
        """
        Aplica el intercambio de descansos en los dos findes (cesión y devolución).

        Semana 1 (cesión):
        - Solicitante: trabaja otro_w1 (lo que el receptor trabajaba)
        - Receptor: trabaja fecha_cesion (lo que el solicitante trabajaba)

        Semana 2 (devolución): espejo (para mantener balance de domingos)
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = _as_date(solicitud.fecha_cambio_turno)
        fecha_pago = _as_date(detalle.fecha_pago)

        otro_w1 = _otro_dia(fecha_cesion)
        otro_w2 = _otro_dia(fecha_pago)

        # Snapshot idempotente: solo capturar la PRIMERA vez
        if not getattr(detalle, 'snapshot_turnos_previos', None):
            snap = CambioDescansoAplicacionService._capturar_snapshot(
                solicitante, receptor, [fecha_cesion, otro_w1, fecha_pago, otro_w2]
            )
            from solicitudes.models import DobladaDetalle as _DD
            _DD.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snap)
            detalle.snapshot_turnos_previos = snap

        # Materializamos el TRABAJO (crea Turno AM+PM, que el sistema prioriza sobre el
        # turno virtual). El DESCANSO se borra de Turno y se refleja en "Mis Turnos" al
        # detectar esta solicitud (igual que DOBLADA / D FDS).
        #
        # Resultado deseado (ej. Mariana cede sábado, Jhon cede domingo):
        #   Solicitante TRABAJA otro_w1 y otro_w2 ; DESCANSA fecha_cesion y fecha_pago
        #   Receptor    TRABAJA fecha_cesion y fecha_pago ; DESCANSA otro_w1 y otro_w2

        # Semana de cesión
        CambioDescansoAplicacionService._trabaja_dia(solicitante, otro_w1)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fecha_cesion)
        CambioDescansoAplicacionService._trabaja_dia(receptor, fecha_cesion)
        CambioDescansoAplicacionService._descansa_dia(receptor, otro_w1)

        # Semana de devolución (espejo)
        CambioDescansoAplicacionService._trabaja_dia(solicitante, otro_w2)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fecha_pago)
        CambioDescansoAplicacionService._trabaja_dia(receptor, fecha_pago)
        CambioDescansoAplicacionService._descansa_dia(receptor, otro_w2)

        logger.info(
            "Cambio de descanso aplicado: solicitud %s — cesión %s, devolución %s",
            solicitud.id, fecha_cesion, fecha_pago,
        )

    @staticmethod
    @transaction.atomic
    def aplicar_entre_semana(solicitud, detalle):
        """
        Intercambio DIRECTO de descansos ENTRE SEMANA (sin devolución).

        fecha_cesion: el descanso del solicitante
        fecha_pago: el descanso del receptor

        Después del intercambio:
        - Solicitante: trabaja fecha_cesion, descansa fecha_pago
        - Receptor: descansa fecha_cesion, trabaja fecha_pago
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = _as_date(solicitud.fecha_cambio_turno)
        fecha_pago = _as_date(detalle.fecha_pago)

        # Snapshot idempotente
        if not getattr(detalle, 'snapshot_turnos_previos', None):
            snap = CambioDescansoAplicacionService._capturar_snapshot(
                solicitante, receptor, [fecha_cesion, fecha_pago]
            )
            from solicitudes.models import DobladaDetalle as _DD
            _DD.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snap)
            detalle.snapshot_turnos_previos = snap

        # Intercambio directo de DESCANSOS (días separados, no es "un día u otro"):
        # fecha_cesion: el solicitante DESCANSA → ahora TRABAJA; el receptor TRABAJA → ahora DESCANSA.
        # fecha_pago:   el receptor DESCANSA → ahora TRABAJA; el solicitante TRABAJA → ahora DESCANSA.
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
