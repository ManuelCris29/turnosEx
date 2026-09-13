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
import logging
from datetime import date, timedelta

from django.db import transaction

from core.constants import TipoCambioTurno
from core.utils.date_utils import DateUtils
from turnos.models import Turno
from turnos.services.doblada_turno_service import DobladaTurnoService

logger = logging.getLogger(__name__)


def _as_date(fecha):
    """Normaliza a date: acepta date o str 'YYYY-MM-DD'."""
    if isinstance(fecha, str):
        return DateUtils.parse_date(fecha)
    return fecha


def otro_dia(fecha: date) -> date:
    """El otro día del mismo fin de semana (sábado<->domingo)."""
    fecha = _as_date(fecha)
    return fecha + timedelta(days=1) if fecha.weekday() == 5 else fecha - timedelta(days=1)


class CambioDescansoAplicacionService:

    @staticmethod
    def fechas_afectadas(solicitud):
        """
        Todas las fechas que esta solicitud modifica — la base para invalidar caché.

        En finde no basta con cesión y pago: el intercambio también reescribe el día OPUESTO de
        cada finde (sáb↔dom). Ese día puede caer en OTRO MES (cesión el sábado 31 de enero →
        opuesto el 1 de febrero), y la caché de ese mes quedaba sin invalidar.
        """
        detalle = getattr(solicitud, 'doblada', None)
        fechas = [f for f in (_as_date(solicitud.fecha_cambio_turno),
                              _as_date(detalle.fecha_pago) if detalle else None) if f]
        opuestas = [otro_dia(f) for f in fechas if f.weekday() in (5, 6)]
        out = []
        for f in fechas + opuestas:
            if f not in out:
                out.append(f)
        return out

    @staticmethod
    def _jornadas():
        from turnos.models import Jornada
        return {'AM': Jornada.objects.get(nombre='AM'), 'PM': Jornada.objects.get(nombre='PM')}

    @staticmethod
    def _mapa_descanso(empleado, fecha_inicio, fecha_fin, excluir_id=None):
        """
        Base común: { fecha: {'id','nombre'} del compañero } para los días en que el empleado
        DESCANSA por una solicitud de CAMBIO DESCANSO aprobada. `dias_en_descanso` expone solo las
        fechas (claves) y `companero_descanso` el compañero. Mantener ambos consistentes de aquí.

        Atajo de un empleado sobre `_mapa_descanso_multi`: hay UNA sola implementación de la regla,
        así la versión batch (reporte del día) no puede divergir de la individual (Mis Turnos).
        """
        return CambioDescansoAplicacionService._mapa_descanso_multi(
            [empleado], fecha_inicio, fecha_fin, excluir_id
        ).get(getattr(empleado, 'id', empleado), {})

    @staticmethod
    def _mapa_descanso_multi(empleados, fecha_inicio, fecha_fin, excluir_id=None):
        """
        Versión BATCH de `_mapa_descanso`: { emp_id: { fecha: compañero } } para VARIOS empleados
        en una sola tanda de consultas, en vez de N×empleado.

        Existe para el reporte operativo del día, que clasifica a toda la plantilla a la vez: con
        ~400 exploradores, llamar la versión individual costaba miles de consultas. La regla es la
        misma línea por línea — esta función ES la implementación y la individual la envuelve.
        """
        from django.db.models import F, Q

        from solicitudes.models import SolicitudCambio

        fecha_inicio = _as_date(fecha_inicio)
        fecha_fin = _as_date(fecha_fin)
        emp_ids = {getattr(e, 'id', e) for e in empleados}
        rest = {eid: {} for eid in emp_ids}
        # Cobertura del solicitante: jornadas cedidas ACUMULADAS por fecha. Una sola parcial
        # deja media jornada real (L1) y NO es descanso; pero dos parciales (AM y PM, a distintos
        # compañeros) o una completa suman el día entero → descansa completo. Sin esta suma, ceder
        # AM y PM por separado dejaba el día "sin turnos" y la temporada lo re-pintaba como DOBLADA.
        # (Por empleado: en batch dos personas distintas pueden estar acumulando el mismo día.)
        cob_sol_ced = {}    # emp_id → {fecha: set(jornadas)}
        cob_sol_comp = {}   # emp_id → {fecha: compañero}
        # ORDEN EXPLÍCITO + `setdefault` más abajo: "última aprobada gana por día". Sin `order_by`
        # el queryset llegaba en el orden que quisiera la BD y, como el resultado se escribía con
        # asignación directa, con dos intercambios aprobados sobre el mismo día el compañero
        # mostrado era arbitrario y podía cambiar entre peticiones. Se ordena de más reciente a más
        # antigua para que el primero en reclamar la fecha sea el vigente (mismo criterio que las
        # ramas DOBLADA de `DescansoPorSolicitudService`). `fecha_resolucion` puede ser NULL en
        # datos antiguos: `-id` desempata.
        qs = (SolicitudCambio.objects
              .filter(tipo_cambio__nombre='CAMBIO DESCANSO', estado='aprobada')
              .filter(Q(explorador_solicitante_id__in=emp_ids) | Q(explorador_receptor_id__in=emp_ids))
              .select_related('doblada', 'explorador_solicitante', 'explorador_receptor')
              .order_by(F('fecha_resolucion').desc(nulls_last=True), '-id'))
        if excluir_id:
            qs = qs.exclude(id=excluir_id)
        for s in qs:
            det = getattr(s, 'doblada', None)
            if not det:
                continue
            fc = _as_date(s.fecha_cambio_turno)
            fp = _as_date(det.fecha_pago)
            # Una misma solicitud puede tener a AMBAS partes dentro del lote: se procesan los dos
            # lados por separado, igual que dos llamadas individuales.
            for es_sol in (True, False):
                emp_id = s.explorador_solicitante_id if es_sol else s.explorador_receptor_id
                if emp_id not in emp_ids:
                    continue
                otro = s.explorador_receptor if es_sol else s.explorador_solicitante
                # `acuerdo` viaja junto al compañero para que quien pinta el día pueda decir
                # de QUÉ intercambio viene y cuándo se aprobó, sin volver a deducir la
                # geometría (que es justo lo que esta función ya sabe). Los consumidores que
                # solo leen 'id'/'nombre' no se enteran de que está.
                comp = {
                    'id': otro.id,
                    'nombre': f'{otro.nombre} {getattr(otro, "apellido", "")}'.strip(),
                    'acuerdo': {
                        'solicitud_id': s.id,
                        'tipo_solicitud': 'CAMBIO DESCANSO',
                        # Qué papel juega el EMPLEADO (no el compañero) en el intercambio.
                        # Aquí se sabe de primera mano; deducirlo después obligaría a volver
                        # a mirar la solicitud para saber de qué lado cae cada uno.
                        'rol': 'solicitante' if es_sol else 'receptor',
                        'fecha_cesion': fc.strftime('%d/%m/%Y') if fc else None,
                        'fecha_pago': fp.strftime('%d/%m/%Y') if fp else None,
                        'fecha_solicitud': DateUtils.format_datetime_display(s.fecha_solicitud),
                        'fecha_aprobacion': DateUtils.format_datetime_display(s.fecha_resolucion),
                    },
                }
                es_finde = bool(fc) and fc.weekday() in (5, 6)
                if es_finde:
                    dias = [fc, fp] if es_sol else [otro_dia(fc), otro_dia(fp)]
                else:
                    # Entre semana: el descanso COMPLETO depende de la sub-modalidad.
                    # (Las medias jornadas quedan con Turno real y no pasan por aquí.)
                    sub = getattr(det, 'submodalidad_semana', None) or 'intercambio_dia'
                    if sub == 'intercambio_dia':
                        dias = [fp] if es_sol else [fc]
                    elif sub == 'cobertura_misma_semana':
                        dias = []
                        if es_sol and fc:
                            ced = ({'AM', 'PM'} if det.tipo_cesion == 'cesion_completa'
                                   else ({(det.jornada_cedida or '').upper()} & {'AM', 'PM'}))
                            cob_sol_ced.setdefault(emp_id, {}).setdefault(fc, set()).update(ced)
                            cob_sol_comp.setdefault(emp_id, {})[fc] = comp
                        elif not es_sol and det.tipo_cesion == 'cesion_completa':
                            dias = [fp]  # receptor: solo descansa el pago si le cedieron el día entero
                    elif sub == 'cambio_doblada':
                        dias = [fc] if es_sol else [fp]  # cada uno descansa el día que cedió
                    else:
                        dias = []  # jornadas_partidas: ambos trabajan media en ambos días (L1)
                for d in dias:
                    if d and fecha_inicio <= d <= fecha_fin:
                        # `setdefault`, no asignación: con el orden de arriba la PRIMERA que
                        # reclama la fecha es la más reciente, y es la que debe ganar.
                        rest[emp_id].setdefault(d, comp)
        # Días donde el solicitante cedió el día COMPLETO por cobertura (parciales que suman AM+PM).
        for emp_id, por_fecha in cob_sol_ced.items():
            for f_ced, js in por_fecha.items():
                if js >= {'AM', 'PM'} and fecha_inicio <= f_ced <= fecha_fin:
                    # `setdefault` por el mismo motivo: si una solicitud más reciente ya reclamó
                    # esa fecha, no se la pisa con la suma de parciales de una anterior.
                    rest[emp_id].setdefault(f_ced, cob_sol_comp.get(emp_id, {}).get(f_ced))
        return rest

    @staticmethod
    def dias_en_descanso(empleado, fecha_inicio, fecha_fin, excluir_id=None):
        """
        Conjunto de fechas en [fecha_inicio, fecha_fin] donde el empleado DESCANSA por una
        solicitud de CAMBIO DESCANSO aprobada (su día cedido, que queda sin registro Turno).

        Misma lógica que usa "Mis Turnos" para pintar el descanso (informativo/histórico: no importa
        cuánto tiempo pasó). Para saber si un día está BLOQUEADO para un nuevo cambio de descanso
        (fin de semana), usar `dia_bloqueado_para_nuevo_cambio`.

        `excluir_id`: ignora esa solicitud (la PROPIA, al aplicarla ya aprobada).
        """
        return set(CambioDescansoAplicacionService._mapa_descanso(
            empleado, fecha_inicio, fecha_fin, excluir_id).keys())

    @staticmethod
    def companero_descanso(empleado, fecha, excluir_id=None):
        """Compañero (otro explorador) de la solicitud de CAMBIO DESCANSO que hace que `empleado`
        descanse `fecha`. Devuelve {'id','nombre'} o None. Mismo criterio que dias_en_descanso."""
        fecha = _as_date(fecha)
        return CambioDescansoAplicacionService._mapa_descanso(
            empleado, fecha, fecha, excluir_id).get(fecha)

    @staticmethod
    def dia_bloqueado_para_nuevo_cambio(empleado, fecha, excluir_id=None):
        """
        FUENTE ÚNICA: ¿`fecha` está bloqueada para un NUEVO cambio de descanso (fin de semana) de
        `empleado`? Usada tanto por el selector de findes (`CambioDescansoFindesView`) como por la
        validación (`CambioDescansoStrategy._trabaja_dia`) — así ambos responden siempre lo mismo.

        Regla ÚNICA: turno ese día con `tipo_cambio` DISTINTO de 'CAMBIO DESCANSO' (DOBLADA,
        D FDS, CT…) → bloqueado, siempre. Cualquier otra cosa → libre.

        Un CAMBIO DESCANSO previo ya NO bloquea. Antes lo hacía durante 30 minutos, para que
        reutilizar el día no rompiera el revert de una cancelación aún posible. Esa regla nació
        atada a una cancelación que era inmediata y duraba 30 min; desde que cancelar se PIDE y lo
        decide el receptor con 24 h de plazo (ver `use_cases/cancelar_solicitud.py`), mantenerlas
        alineadas habría significado congelar el día un día entero para todo el mundo. Se prefirió
        dejar el día libre para elegir: "última aprobada gana por día".

        Contrapartida deliberada: si alguien reutiliza el día mientras la cancelación anterior
        sigue viva, la guardia LIFO impedirá revertirla. Es un intercambio consciente —se protege
        la elección de día de descanso, no la reversibilidad—, así que NO se reintroduzca el
        bloqueo sin revisar esa decisión.

        `excluir_id`: se mantiene por compatibilidad con las llamadas existentes (re-validación de
        la PROPIA solicitud al aprobar). Con la regla actual no hay nada que excluir: el criterio
        mira los turnos del día, no las solicitudes.
        """
        fecha = _as_date(fecha)

        return (Turno.objects.filter(explorador=empleado, fecha=fecha)
                .exclude(tipo_cambio__isnull=True)
                .exclude(tipo_cambio='')
                .exclude(tipo_cambio=TipoCambioTurno.CAMBIO_DESCANSO)
                .exists())

    @staticmethod
    def _trabaja_dia(explorador, fecha, tipo_cambio=TipoCambioTurno.CAMBIO_DESCANSO):
        """Deja al explorador trabajando el día completo (AM+PM) en `fecha`."""
        jc = CambioDescansoAplicacionService._jornadas()
        Turno.objects.filter(explorador=explorador, fecha=fecha).delete()
        sala = DobladaTurnoService.obtener_sala_explorador_fecha(explorador, fecha)
        for nombre in ('AM', 'PM'):
            Turno.objects.create(explorador=explorador, fecha=fecha, jornada=jc[nombre],
                                 sala=sala, tipo_cambio=tipo_cambio)

    @staticmethod
    def _trabaja_jornada(explorador, fecha, jornada_nombre=None, tipo_cambio=TipoCambioTurno.CAMBIO_DESCANSO):
        """
        Deja al explorador trabajando UNA sola jornada en `fecha` (entre semana).
        Si `jornada_nombre` es None usa su jornada base (AsignarJornadaExplorador).
        """
        from turnos.models import AsignarJornadaExplorador, Jornada
        if not jornada_nombre:
            asg = (AsignarJornadaExplorador.objects.filter(explorador=explorador, fecha_inicio__lte=fecha)
                   .select_related('jornada').order_by('-fecha_inicio').first())
            jornada_nombre = asg.jornada.nombre.upper() if asg else 'AM'
        jornada = Jornada.objects.get(nombre=jornada_nombre.upper())
        Turno.objects.filter(explorador=explorador, fecha=fecha).delete()
        sala = DobladaTurnoService.obtener_sala_explorador_fecha(explorador, fecha)
        Turno.objects.create(explorador=explorador, fecha=fecha, jornada=jornada, sala=sala, tipo_cambio=tipo_cambio)

    @staticmethod
    def _descansa_dia(explorador, fecha):
        """Deja al explorador descansando `fecha` (borra cualquier turno de ese día)."""
        Turno.objects.filter(explorador=explorador, fecha=fecha).delete()

    @staticmethod
    def _marcar_reemplazadas(solicitud_nueva, explorador, fecha):
        """
        Si hay un turno con tipo_cambio='CAMBIO DESCANSO' en (explorador, fecha) perteneciente
        a otra solicitud aprobada, esa solicitud pasa a estado 'reemplazada'.

        Se llama antes de _trabaja_dia() para registrar el reemplazo en el historial antes
        de que el turno sea borrado.

        SOLO FIN DE SEMANA, a propósito: la búsqueda de la solicitud dueña del turno se apoya en
        `otro_dia()` (sáb↔dom), que no tiene equivalente entre semana. Las rutas de temporada
        resuelven el mismo principio ("última aprobada gana por día") por el otro lado: en vez de
        reemplazar la solicitud previa, la VALIDACIÓN impide crear la nueva mientras el día siga
        comprometido (`dia_comprometido_por_solicitud` / `estado_dia(...)['trabaja']`). Por eso
        aplicar_entre_semana y las sub-modalidades no llaman aquí: no es un olvido.
        """
        if not Turno.objects.filter(
            explorador=explorador, fecha=fecha, tipo_cambio=TipoCambioTurno.CAMBIO_DESCANSO
        ).exists():
            return

        from django.db.models import Q

        from solicitudes.models import SolicitudCambio

        otro = otro_dia(fecha)
        # El turno en (explorador, fecha) fue creado porque:
        # - Explorador es RECEPTOR en una solicitud con fecha_cambio_turno=fecha o doblada.fecha_pago=fecha
        # - Explorador es SOLICITANTE en una solicitud donde fecha=otro_dia(fc) o fecha=otro_dia(fp)
        candidatas = SolicitudCambio.objects.filter(
            tipo_cambio__nombre='CAMBIO DESCANSO',
            estado='aprobada',
        ).exclude(pk=solicitud_nueva.pk).filter(
            Q(explorador_receptor=explorador, fecha_cambio_turno=fecha) |
            Q(explorador_receptor=explorador, doblada__fecha_pago=fecha) |
            Q(explorador_solicitante=explorador, fecha_cambio_turno=otro) |
            Q(explorador_solicitante=explorador, doblada__fecha_pago=otro),
        )
        from solicitudes.domain.estado_machine import transicionar
        for candidata in candidatas:
            candidata.reemplazada_por = solicitud_nueva
            transicionar(candidata, 'reemplazada', update_fields=['reemplazada_por'])

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
    def aplicar(solicitud, detalle, marcar_reemplazos: bool = True):
        """
        Aplica el intercambio de descansos en los dos findes (cesión y devolución).

        `marcar_reemplazos=False` re-materializa SOLO los turnos, sin tocar el estado de otras
        solicitudes. Lo usa la reconciliación posterior a una cancelación: allí esta solicitud ya
        estaba aplicada y solo se están reconstruyendo sus turnos, así que volver a marcar
        reemplazos convertiría en 'reemplazada' a una solicitud que sigue vigente.

        Semana 1 (cesión):
        - Solicitante: trabaja otro_w1 (lo que el receptor trabajaba)
        - Receptor: trabaja fecha_cesion (lo que el solicitante trabajaba)

        Semana 2 (devolución): espejo (para mantener balance de domingos)
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = _as_date(solicitud.fecha_cambio_turno)
        fecha_pago = _as_date(detalle.fecha_pago)

        otro_w1 = otro_dia(fecha_cesion)
        otro_w2 = otro_dia(fecha_pago)

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

        def _reemplazos(explorador, fecha):
            if marcar_reemplazos:
                CambioDescansoAplicacionService._marcar_reemplazadas(solicitud, explorador, fecha)

        # Semana de cesión
        _reemplazos(solicitante, otro_w1)
        CambioDescansoAplicacionService._trabaja_dia(solicitante, otro_w1)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fecha_cesion)
        _reemplazos(receptor, fecha_cesion)
        CambioDescansoAplicacionService._trabaja_dia(receptor, fecha_cesion)
        CambioDescansoAplicacionService._descansa_dia(receptor, otro_w1)

        # Semana de devolución (espejo)
        _reemplazos(solicitante, otro_w2)
        CambioDescansoAplicacionService._trabaja_dia(solicitante, otro_w2)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fecha_pago)
        _reemplazos(receptor, fecha_pago)
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
        # El día especial de temporada se trabaja COMPLETO (AM+PM), igual que lo hacía quien lo cede.
        CambioDescansoAplicacionService._trabaja_dia(solicitante, fecha_cesion)
        CambioDescansoAplicacionService._descansa_dia(receptor, fecha_cesion)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fecha_pago)
        CambioDescansoAplicacionService._trabaja_dia(receptor, fecha_pago)

        # Los dos pasan a DESCANSAR un día que antes trabajaban: si en él venían doblando por otra
        # solicitud, dejan de doblar y sus 30 min de esa fecha ya no corresponden. Este intercambio
        # no genera deuda nueva (trabajar un día que tenías libre no la genera), así que aquí solo
        # hay que apagar.
        CambioDescansoAplicacionService._sincronizar_deuda_corp(
            solicitante, fecha_pago, solicitud, 'pasa a descansar')
        CambioDescansoAplicacionService._sincronizar_deuda_corp(
            receptor, fecha_cesion, solicitud, 'pasa a descansar')

        logger.info("Cambio de descanso (entre semana) aplicado: solicitud %s — %s <-> %s",
                    solicitud.id, fecha_cesion, fecha_pago)

    # ------------------------------------------------------------------
    # Sub-modalidades nuevas de ENTRE SEMANA (temporada)
    # ------------------------------------------------------------------

    @staticmethod
    def _jornadas_virtuales(explorador, fecha):
        """
        Estado VIRTUAL del día (sin L1 turnos ni L2 solicitudes): alternancia de finde,
        temporada (descanso propio o día completo si descansa el grupo contrario),
        mantenimiento o jornada base.
        """
        from turnos.models import AsignarJornadaExplorador, DiaEspecial
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        from turnos.services.descanso_semana_service import DescansoSemanaService
        asg = (AsignarJornadaExplorador.objects.filter(explorador=explorador, fecha_inicio__lte=fecha)
               .select_related('jornada').order_by('-fecha_inicio').first())
        base = asg.jornada.nombre.upper() if asg else None
        if not base:
            return set()
        if fecha.weekday() >= 5:
            g = AsignacionEspecialService.grupo_trabaja(fecha)
            return {'AM', 'PM'} if (g and base == g.upper()) else set()
        if DescansoSemanaService.es_descanso_semana_manual(base, fecha):
            return set()
        if DiaEspecial.es_mantenimiento_efectivo(fecha):
            return set()
        contraria = 'PM' if base == 'AM' else 'AM'
        if DescansoSemanaService.es_descanso_semana_manual(contraria, fecha):
            return {'AM', 'PM'}  # día especial de temporada: trabaja día completo
        return {base}

    @staticmethod
    def _jornadas_actuales(explorador, fecha, excluir_solicitud_id=None):
        """
        Set de jornadas que el explorador tiene HOY en `fecha`: L1 turnos reales →
        L2 descanso por solicitud aprobada (con `excluir_solicitud_id` para que la
        PROPIA solicitud, ya aprobada, no se cuente al aplicarla) → estado virtual.
        """
        from turnos.services.turno_service import TurnoService
        turnos = list(Turno.objects.filter(explorador=explorador, fecha=fecha).select_related('jornada'))
        if turnos:
            return {t.jornada.nombre.upper() for t in turnos}
        if TurnoService._descanso_por_solicitud(explorador, fecha, excluir_id=excluir_solicitud_id):
            return set()
        return CambioDescansoAplicacionService._jornadas_virtuales(explorador, fecha)

    @staticmethod
    def _materializar(explorador, fecha, jornadas_set):
        """Deja al explorador con exactamente `jornadas_set` en `fecha` (delete + create)."""
        if jornadas_set >= {'AM', 'PM'}:
            CambioDescansoAplicacionService._trabaja_dia(explorador, fecha)
        elif jornadas_set:
            CambioDescansoAplicacionService._trabaja_jornada(explorador, fecha, next(iter(jornadas_set)))
        else:
            CambioDescansoAplicacionService._descansa_dia(explorador, fecha)

    @staticmethod
    def _jornadas_propias_para_deuda(explorador, fecha, excluir_solicitud_id=None):
        """
        Jornadas 'propias' del día para la regla de deuda: si hay turnos reales, cuentan
        solo los que NO vienen de un pago de cobertura (tipo_cambio='CAMBIO DESCANSO');
        así, quien reparte el pago de su día cedido en dos medias jornadas el mismo día
        libre no paga deuda por la segunda media. Sin turnos, aplica el estado virtual.
        """
        turnos = list(Turno.objects.filter(explorador=explorador, fecha=fecha).select_related('jornada'))
        if turnos:
            return {t.jornada.nombre.upper() for t in turnos
                    if (t.tipo_cambio or '') != 'CAMBIO DESCANSO'}
        return CambioDescansoAplicacionService._jornadas_actuales(
            explorador, fecha, excluir_solicitud_id=excluir_solicitud_id)

    @staticmethod
    def _deuda_30_si_doblo(explorador, fecha, pre_set, post_set, solicitud, comentario):
        """
        REGLA DE NEGOCIO (temporada): debes 30 min solo si YA tenías una jornada propia
        ese día y quedaste con AM+PM (doblaste). Venir en el día libre (media o completa)
        no genera deuda. Solo lun-vie no festivo (aplica_deuda_doblada).
        """
        from .deuda_corporativa_repository import DeudaCorporativaRepository
        from .deuda_corporativa_service import DeudaCorporativaService
        if len(pre_set) == 1 and post_set >= {'AM', 'PM'} \
                and DeudaCorporativaService.aplica_deuda_doblada(fecha):
            DeudaCorporativaRepository.crear_deuda_corporativa_idempotente(
                explorador=explorador,
                minutos=30,
                fecha_doblada=fecha,
                solicitud=solicitud,
                comentario=comentario,
            )
            logger.info("Deuda 30 min (temporada) para %s en %s", explorador.nombre, fecha)

    @staticmethod
    def _sincronizar_deuda_corp(explorador, fecha, solicitud, que_hizo):
        """
        Espejo de `_deuda_30_si_doblo`: cancela los 30 min de `fecha` si el explorador DEJÓ de
        doblar por esta solicitud. Los 30 min los debe quien realmente dobla, así que perder una
        de las dos mitades del día los extingue. Sin esto la deuda vieja seguía activa sumando en
        el Consolidado de Horas aunque el día ya no fuera DOBLADA.
        """
        from .deuda_corporativa_repository import DeudaCorporativaRepository

        DeudaCorporativaRepository.sincronizar_deuda_corporativa(
            explorador, fecha, motivo=f'{que_hizo} en el cambio de descanso {solicitud.id}')

    @staticmethod
    def _snapshot_idempotente(detalle, solicitante, receptor, fechas):
        if not getattr(detalle, 'snapshot_turnos_previos', None):
            snap = CambioDescansoAplicacionService._capturar_snapshot(solicitante, receptor, fechas)
            from solicitudes.models import DobladaDetalle as _DD
            _DD.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snap)
            detalle.snapshot_turnos_previos = snap

    @staticmethod
    @transaction.atomic
    def aplicar_semana_jornadas_partidas(solicitud, detalle):
        """
        Jornadas partidas: en los DOS días especiales de la semana, el solicitante
        trabaja `jornada_cedida` ambos días y el receptor la contraria ambos días.
        Nadie dobla → sin deuda.
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fc = _as_date(solicitud.fecha_cambio_turno)   # día de trabajo del solicitante
        fp = _as_date(detalle.fecha_pago)             # día de trabajo del receptor
        j_sol = (detalle.jornada_cedida or 'AM').upper()
        j_rec = 'PM' if j_sol == 'AM' else 'AM'

        CambioDescansoAplicacionService._snapshot_idempotente(detalle, solicitante, receptor, [fc, fp])

        for f in (fc, fp):
            CambioDescansoAplicacionService._trabaja_jornada(solicitante, f, j_sol)
            CambioDescansoAplicacionService._trabaja_jornada(receptor, f, j_rec)

        logger.info("Jornadas partidas aplicadas: solicitud %s — sol=%s rec=%s en %s y %s",
                    solicitud.id, j_sol, j_rec, fc, fp)

    @staticmethod
    @transaction.atomic
    def aplicar_semana_cobertura(solicitud, detalle):
        """
        Cobertura con pago en la MISMA semana:
        - fc (mi día completo de temporada): el receptor cubre `jornada_cedida`
          (una jornada) o el día entero (cesion_completa); yo conservo el resto.
        - fp (día de pago, misma semana): yo cubro al receptor lo equivalente
          (media o completa) y él descansa esa parte.
        Deuda 30 min SOLO para quien ya tenía una jornada ese día y quedó AM+PM.
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fc = _as_date(solicitud.fecha_cambio_turno)
        fp = _as_date(detalle.fecha_pago)
        completa = detalle.tipo_cesion == 'cesion_completa'
        cedidas = {'AM', 'PM'} if completa else {(detalle.jornada_cedida or 'AM').upper()}

        # Estados PRE (fuente de verdad) antes de mutar. Se excluye la PROPIA solicitud
        # (ya está aprobada al aplicar y su L2 haría ver descansos que aún no existen).
        _sid = solicitud.id
        pre_sol_fc = CambioDescansoAplicacionService._jornadas_actuales(solicitante, fc, excluir_solicitud_id=_sid)
        pre_rec_fc = CambioDescansoAplicacionService._jornadas_actuales(receptor, fc, excluir_solicitud_id=_sid)
        pre_sol_fp = CambioDescansoAplicacionService._jornadas_actuales(solicitante, fp, excluir_solicitud_id=_sid)
        pre_rec_fp = CambioDescansoAplicacionService._jornadas_actuales(receptor, fp, excluir_solicitud_id=_sid)
        # Para la DEUDA cuenta solo la jornada PROPIA (no la asumida por otro pago de cobertura)
        deuda_pre_rec_fc = CambioDescansoAplicacionService._jornadas_propias_para_deuda(receptor, fc, _sid)
        deuda_pre_sol_fp = CambioDescansoAplicacionService._jornadas_propias_para_deuda(solicitante, fp, _sid)

        CambioDescansoAplicacionService._snapshot_idempotente(detalle, solicitante, receptor, [fc, fp])

        # fc: receptor suma las jornadas cedidas; solicitante se las quita.
        post_rec_fc = pre_rec_fc | cedidas
        post_sol_fc = pre_sol_fc - cedidas
        # fp: el solicitante toma del receptor lo equivalente (media o todo su día). En cesión
        # parcial cubre UNA jornada: la elegida `jornada_cubre_en_pago` (si estaba libre y el
        # receptor trabajaba ambas), o en su defecto la cedida.
        if completa:
            tomadas = set(pre_rec_fp)
        else:
            j_pago = (getattr(detalle, 'jornada_cubre_en_pago', None) or detalle.jornada_cedida or 'AM').upper()
            tomadas = {j_pago} if j_pago in pre_rec_fp else (set(list(pre_rec_fp)[:1]) if pre_rec_fp else set())
        post_sol_fp = pre_sol_fp | tomadas
        post_rec_fp = pre_rec_fp - tomadas

        CambioDescansoAplicacionService._materializar(receptor, fc, post_rec_fc)
        CambioDescansoAplicacionService._materializar(solicitante, fc, post_sol_fc)
        CambioDescansoAplicacionService._materializar(solicitante, fp, post_sol_fp)
        CambioDescansoAplicacionService._materializar(receptor, fp, post_rec_fp)

        # Deudas por la regla de negocio (solo quien DOBLÓ sobre su propia jornada)
        CambioDescansoAplicacionService._deuda_30_si_doblo(
            receptor, fc, deuda_pre_rec_fc, post_rec_fc, solicitud,
            f'Cobertura temporada: cubrió jornada(s) el {fc} teniendo jornada propia')
        CambioDescansoAplicacionService._deuda_30_si_doblo(
            solicitante, fp, deuda_pre_sol_fp, post_sol_fp, solicitud,
            f'Cobertura temporada: pagó jornada(s) el {fp} teniendo jornada propia')

        # Contrapartida: los dos que PIERDEN jornadas (el solicitante en `fc`, el receptor en `fp`)
        # pueden dejar de doblar. Si venían con 30 min de esa fecha, ya no corresponden.
        CambioDescansoAplicacionService._sincronizar_deuda_corp(
            solicitante, fc, solicitud, 'cede jornada(s)')
        CambioDescansoAplicacionService._sincronizar_deuda_corp(
            receptor, fp, solicitud, 'recibe cobertura')

        logger.info("Cobertura misma semana aplicada: solicitud %s — cede %s en %s, paga en %s",
                    solicitud.id, sorted(cedidas), fc, fp)

    @staticmethod
    @transaction.atomic
    def aplicar_semana_cambio_doblada(solicitud, detalle):
        """
        Cambio de doblada (misma semana de temporada): el solicitante toma la doblada
        (AM+PM) que el receptor tenía en `fecha_pago` y el receptor toma el día completo
        de temporada del solicitante (`fecha_cambio_turno`).
        SIN deuda: ambos ya doblaban un día, solo cambia CUÁL. Las deudas existentes
        quedan intactas con su dueño original.
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fc = _as_date(solicitud.fecha_cambio_turno)   # mi día completo que cedo
        fp = _as_date(detalle.fecha_pago)             # día de la doblada del receptor que tomo

        CambioDescansoAplicacionService._snapshot_idempotente(detalle, solicitante, receptor, [fc, fp])

        # fp: yo tomo la doblada COMPLETA (incluida la jornada propia del receptor);
        #     el receptor descansa ese día (cedió todo su día doblado).
        CambioDescansoAplicacionService._trabaja_dia(solicitante, fp)
        CambioDescansoAplicacionService._descansa_dia(receptor, fp)
        # fc: el receptor toma mi día completo; yo descanso.
        CambioDescansoAplicacionService._trabaja_dia(receptor, fc)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fc)

        # A PROPÓSITO no se sincroniza la deuda corporativa aquí. Es un swap: cada uno sigue
        # doblando UN día de la semana, solo cambia cuál. Cancelar los 30 min del día que sueltan
        # los borraría sin crear los del día nuevo (esta modalidad no genera deuda), y acabarían
        # doblando gratis. La deuda se queda con su dueño, que es lo correcto en importe.
        logger.info("Cambio de doblada aplicado: solicitud %s — %s toma %s, %s toma %s",
                    solicitud.id, solicitante.nombre, fp, receptor.nombre, fc)

    @staticmethod
    @transaction.atomic
    def revertir(solicitud):
        """
        Restaura los turnos previos desde el snapshot y cancela las deudas
        corporativas generadas por esta solicitud (cobertura misma semana).
        """
        from .doblada_aplicacion_service import DobladaAplicacionService
        detalle = solicitud.doblada
        snap = getattr(detalle, 'snapshot_turnos_previos', None)
        if snap:
            DobladaAplicacionService.restaurar_turnos_desde_snapshot(snap)
        else:
            # Solicitudes antiguas (sin snapshot): al menos borrar los turnos que ESTA gestión
            # creó. Sin este else se cancelaban las deudas pero los turnos quedaban aplicados:
            # la persona seguía con la doblada puesta y sin deber los 30 min correspondientes.
            fechas = [f for f in (solicitud.fecha_cambio_turno, detalle.fecha_pago) if f]
            if fechas:
                Turno.objects.filter(
                    explorador__in=[solicitud.explorador_solicitante, solicitud.explorador_receptor],
                    fecha__in=fechas,
                    tipo_cambio=TipoCambioTurno.CAMBIO_DESCANSO,
                ).delete()
                logger.info(
                    "Cambio de descanso %s sin snapshot: turnos 'CAMBIO DESCANSO' borrados en %s.",
                    solicitud.id, fechas,
                )
        # Solo las ACTIVAS: una deuda corporativa ya pagada sigue pagada aunque se revierta.
        from .deuda_corporativa_repository import DeudaCorporativaRepository as _DCR
        _DCR.cancelar_deudas_de_solicitud(solicitud, motivo='cambio de descanso revertido')
        # Patrón #22: restaurar el snapshot arrasa el día entero. Reconstruir lo que SIGUE
        # vigente en esas fechas (otra doblada, un CT, un CT permanente…) o se borra en silencio.
        if snap:
            DobladaAplicacionService.reconciliar_dobladas_aprobadas(
                DobladaAplicacionService._fechas_explorador_afectados(snap), solicitud.id)
        logger.info("Cambio de descanso revertido: solicitud %s", solicitud.id)
