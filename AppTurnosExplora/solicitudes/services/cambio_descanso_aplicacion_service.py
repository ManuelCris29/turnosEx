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
                # Entre semana: el descanso COMPLETO depende de la sub-modalidad.
                # (Las medias jornadas quedan con Turno real y no pasan por aquí.)
                sub = getattr(det, 'submodalidad_semana', None) or 'intercambio_dia'
                if sub == 'intercambio_dia':
                    dias = [fp] if es_sol else [fc]
                elif sub == 'cobertura_misma_semana':
                    if det.tipo_cesion == 'cesion_completa':
                        dias = [fc] if es_sol else [fp]
                    else:
                        dias = []  # cesión parcial: ambos conservan media jornada (L1)
                elif sub == 'cambio_doblada':
                    dias = [fc] if es_sol else [fp]  # cada uno descansa el día que cedió
                else:
                    dias = []  # jornadas_partidas: ambos trabajan media en ambos días (L1)
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
    def _trabaja_jornada(explorador, fecha, jornada_nombre=None, tipo_cambio='CAMBIO DESCANSO'):
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
        """
        if not Turno.objects.filter(
            explorador=explorador, fecha=fecha, tipo_cambio='CAMBIO DESCANSO'
        ).exists():
            return

        from django.db.models import Q
        from solicitudes.models import SolicitudCambio

        otro = _otro_dia(fecha)
        # El turno en (explorador, fecha) fue creado porque:
        # - Explorador es RECEPTOR en una solicitud con fecha_cambio_turno=fecha o doblada.fecha_pago=fecha
        # - Explorador es SOLICITANTE en una solicitud donde fecha=_otro_dia(fc) o fecha=_otro_dia(fp)
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
        CambioDescansoAplicacionService._marcar_reemplazadas(solicitud, solicitante, otro_w1)
        CambioDescansoAplicacionService._trabaja_dia(solicitante, otro_w1)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fecha_cesion)
        CambioDescansoAplicacionService._marcar_reemplazadas(solicitud, receptor, fecha_cesion)
        CambioDescansoAplicacionService._trabaja_dia(receptor, fecha_cesion)
        CambioDescansoAplicacionService._descansa_dia(receptor, otro_w1)

        # Semana de devolución (espejo)
        CambioDescansoAplicacionService._marcar_reemplazadas(solicitud, solicitante, otro_w2)
        CambioDescansoAplicacionService._trabaja_dia(solicitante, otro_w2)
        CambioDescansoAplicacionService._descansa_dia(solicitante, fecha_pago)
        CambioDescansoAplicacionService._marcar_reemplazadas(solicitud, receptor, fecha_pago)
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
        from turnos.services.descanso_semana_service import DescansoSemanaService
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        asg = (AsignarJornadaExplorador.objects.filter(explorador=explorador, fecha_inicio__lte=fecha)
               .select_related('jornada').order_by('-fecha_inicio').first())
        base = asg.jornada.nombre.upper() if asg else None
        if not base:
            return set()
        if fecha.weekday() >= 5:
            g = AsignacionEspecialService.grupo_trabaja_efectivo(fecha)
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
        from .deuda_corporativa_service import DeudaCorporativaService
        if len(pre_set) == 1 and post_set >= {'AM', 'PM'} \
                and DeudaCorporativaService.aplica_deuda_doblada(fecha):
            DeudaCorporativaService.crear_deuda_corporativa(
                explorador=explorador,
                minutos=30,
                fecha_generacion=date.today(),
                fecha_doblada=fecha,
                solicitud=solicitud,
                comentario=comentario,
            )
            logger.info("Deuda 30 min (temporada) para %s en %s", explorador.nombre, fecha)

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
        from solicitudes.models import DeudaCorporativa
        detalle = solicitud.doblada
        snap = getattr(detalle, 'snapshot_turnos_previos', None)
        if snap:
            DobladaAplicacionService.restaurar_turnos_desde_snapshot(snap)
        DeudaCorporativa.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')
        logger.info("Cambio de descanso revertido: solicitud %s", solicitud.id)
