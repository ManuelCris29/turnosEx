"""
DobladaSnapshotService

Responsabilidad: capturar y restaurar el estado de turnos antes/después de aplicar
una doblada, y reconciliar las dobladas vigentes tras una cancelación.
"""
from datetime import date
import logging

from django.core.exceptions import ValidationError

from solicitudes.models import SolicitudCambio, DobladaDetalle
from empleados.models import Empleado
from turnos.models import Turno
from core.utils.jornada_utils import obtener_jornadas_am_pm as _obtener_jornadas_cache

logger = logging.getLogger(__name__)


class DobladaSnapshotService:

    @staticmethod
    def capturar_snapshot_turnos_previos(solicitud: SolicitudCambio, detalle: DobladaDetalle) -> dict:
        """
        Copia el estado real de Turno en BD para solicitante y receptor en fecha de cesión y de pago,
        antes de aplicar la doblada. Así la cancelación en 30 min puede restaurar cambios de turno
        sencillos u otras asignaciones que no son solo jornada predeterminada.

        IMPORTANTE: incluye también `fecha_pago_semana` (devolución en semana del pago en sábado
        AMBAS). Ese día lo MUTA `aplicar_pago_residual_semana`, así que si no entra en el snapshot
        la cancelación no lo revierte: el receptor quedaba doblado sin solicitud que lo respaldara
        y con su deuda ya cancelada (turnos y deudas desalineados). Las claves del snapshot son
        además la fuente de `_pares_afectados` en la cancelación, así que sin este día tampoco se
        reconciliaba ni se invalidaba su caché.
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago
        fechas = [fecha_cesion, fecha_pago]
        fecha_semana = getattr(detalle, 'fecha_pago_semana', None)
        if fecha_semana:
            fechas.append(fecha_semana)
        pairs = [
            (emp_id, fecha)
            for fecha in dict.fromkeys(f for f in fechas if f)
            for emp_id in (solicitante.id, receptor.id)
        ]
        return DobladaSnapshotService.serializar_pares(
            f"{emp_id}:{fecha.isoformat()}" for emp_id, fecha in pairs
        )

    @staticmethod
    def serializar_pares(claves) -> dict:
        """
        Estado actual de Turno para un iterable de claves 'explorador_id:YYYY-MM-DD'.

        Serializador ÚNICO del formato de snapshot: lo usan tanto la captura del estado previo
        como la del resultante. Si divergieran, la comparación de integridad al cancelar
        (`bloqueo_integridad`) daría falsos conflictos.
        """
        snapshot: dict = {}
        for key in claves:
            try:
                emp_str, fecha_str = key.split(':', 1)
                emp_id = int(emp_str)
                fecha = date.fromisoformat(fecha_str)
            except (ValueError, TypeError, AttributeError):
                logger.warning('Snapshot: clave inválida %r', key)
                continue
            turnos_qs = (
                Turno.objects.filter(explorador_id=emp_id, fecha=fecha)
                .select_related('jornada')
                .order_by('jornada_id')
            )
            snapshot[key] = [
                {
                    'jornada_nombre': t.jornada.nombre.upper(),
                    'sala_id': t.sala_id,
                    'tipo_cambio': t.tipo_cambio,
                }
                for t in turnos_qs
            ]
        return snapshot

    @staticmethod
    def capturar_snapshot_resultante(objeto, snapshot_previo: dict = None) -> dict:
        """
        Estado que este cambio DEJÓ en las mismas fechas del snapshot previo, y lo guarda en
        `objeto.snapshot_turnos_resultantes`.

        A diferencia del previo (snapshot-once, idempotente), este se REESCRIBE siempre después
        de aplicar: `reaplicar_fechas` y `reconciliar_dobladas_aprobadas` vuelven a tocar los
        turnos y el resultante debe reflejar el estado final, no el de la primera aplicación.

        Llamar SIEMPRE al final de la aplicación, con los turnos ya materializados.
        """
        if snapshot_previo is None:
            snapshot_previo = getattr(objeto, 'snapshot_turnos_previos', None) or {}
        if not snapshot_previo:
            return {}
        resultante = DobladaSnapshotService.serializar_pares(snapshot_previo.keys())
        objeto.snapshot_turnos_resultantes = resultante
        try:
            objeto.save(update_fields=['snapshot_turnos_resultantes'])
        except ValueError:
            # Objeto sin pk aún o campo no persistible: el llamador guardará.
            pass
        return resultante

    @staticmethod
    def restaurar_turnos_desde_snapshot(snapshot: dict) -> None:
        """Reemplaza turnos en las fechas del snapshot por el contenido guardado."""
        if not snapshot:
            return
        from turnos.models import Jornada as JornadaModel
        from turnos.services.doblada_turno_service import DobladaTurnoService
        jornadas_cache = _obtener_jornadas_cache()

        for key, rows in snapshot.items():
            try:
                emp_str, fecha_str = key.split(':', 1)
                emp_id = int(emp_str)
                fecha = date.fromisoformat(fecha_str)
            except (ValueError, TypeError):
                logger.warning('Snapshot doblada: clave inválida %r', key)
                continue

            Turno.objects.filter(explorador_id=emp_id, fecha=fecha).delete()

            for row in rows or []:
                jn = (row.get('jornada_nombre') or '').upper()
                jornada_obj = jornadas_cache.get(jn)
                if not jornada_obj:
                    jornada_obj = JornadaModel.objects.filter(nombre__iexact=jn).first()
                if not jornada_obj:
                    logger.warning(
                        'Snapshot doblada: jornada %r no encontrada para %s en %s',
                        jn, emp_id, fecha,
                    )
                    continue
                sala_id = row.get('sala_id')
                if not sala_id:
                    empleado = Empleado.objects.filter(pk=emp_id).first()
                    if not empleado:
                        continue
                    sala = DobladaTurnoService.obtener_sala_explorador_fecha(empleado, fecha)
                    sala_id = sala.id if sala else None
                if not sala_id:
                    logger.warning('Snapshot doblada: sin sala para %s en %s', emp_id, fecha)
                    continue
                Turno.objects.create(
                    explorador_id=emp_id,
                    fecha=fecha,
                    jornada=jornada_obj,
                    sala_id=sala_id,
                    tipo_cambio=row.get('tipo_cambio'),
                )
                logger.info('Turno restaurado desde snapshot: explorador %s, %s, %s', emp_id, fecha, jn)

    @staticmethod
    def fechas_explorador_afectados(snapshot: dict) -> set:
        """Extrae el conjunto de (explorador_id, fecha) que cubre un snapshot."""
        afectados = set()
        for key in (snapshot or {}).keys():
            try:
                emp_str, fecha_str = key.split(':', 1)
                afectados.add((int(emp_str), date.fromisoformat(fecha_str)))
            except (ValueError, TypeError):
                continue
        return afectados

    # Tope de vueltas del cierre. Cada vuelta solo puede AÑADIR pares, así que converge; el tope
    # es una red de seguridad ante una cadena patológica de solicitudes encadenadas.
    MAX_VUELTAS_CIERRE = 8

    @staticmethod
    def _cerrar_afectados(afectados: set, excluir_solicitud_id: int) -> set:
        """
        Amplía `afectados` con los pares (explorador, fecha) que la re-aplicación de las
        solicitudes vigentes va a reescribir, hasta que el conjunto deje de crecer.

        Se pregunta a cada candidata qué va a escribir REALMENTE (`_pares_que_reescribe`), no
        todas sus fechas: añadir un día que nadie va a tocar haría que la reconciliación lo
        re-aplicara y pisara cambios ajenos en ese día.
        """
        afectados = set(afectados)
        for _ in range(DobladaSnapshotService.MAX_VUELTAS_CIERRE):
            fechas = {f for (_e, f) in afectados}
            exploradores = {e for (e, _f) in afectados}
            nuevos = set()
            for s in DobladaSnapshotService._solicitudes_que_tocan(
                    fechas, exploradores, excluir_solicitud_id):
                nuevos |= DobladaSnapshotService._pares_que_reescribe(s, fechas)
            if nuevos <= afectados:
                return afectados
            afectados |= nuevos
        logger.warning(
            'Cierre de fechas afectadas sin converger en %d vueltas (cancelando solicitud %s): '
            'se reconcilia con el conjunto alcanzado.',
            DobladaSnapshotService.MAX_VUELTAS_CIERRE, excluir_solicitud_id,
        )
        return afectados

    @staticmethod
    def _solicitudes_que_tocan(fechas: set, exploradores: set, excluir_solicitud_id: int) -> list:
        """
        Solicitudes APROBADAS que la reconciliación re-aplicaría con estos `fechas`/`exploradores`.

        Solo se enumeran las que pueden aportar días COLATERALES: las del modelo `doblada`
        (DOBLADA, D FDS, CAMBIO DESCANSO, intercambio) y los CAMBIO TURNO sencillos. Las
        permanentes (`doblada_permanente`, `cambio_permanente`) y los CT PERMANENTE se
        re-materializan acotados a `fechas` (ver sus `reaplicar_fechas`), así que nunca escriben
        fuera del conjunto y no lo amplían: se dejan para la fase de aplicación.
        """
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio

        if not fechas or not exploradores:
            return []
        base = (
            SolicitudCambio.objects
            .filter(estado='aprobada')
            .exclude(id=excluir_solicitud_id)
            .filter(Q(explorador_solicitante_id__in=exploradores)
                    | Q(explorador_receptor_id__in=exploradores))
            .select_related('doblada', 'tipo_cambio')
        )
        con_detalle = base.filter(doblada__isnull=False).filter(
            Q(fecha_cambio_turno__in=fechas)
            | Q(doblada__fecha_pago__in=fechas)
            | Q(doblada__fecha_pago_semana__in=fechas))
        cambios_turno = base.filter(tipo_cambio__nombre='CAMBIO TURNO',
                                    fecha_cambio_turno__in=fechas)
        return list(con_detalle.distinct()) + list(cambios_turno.distinct())

    @staticmethod
    def _estrategia_de(solicitud):
        """
        Strategy que sabe re-materializar `solicitud`.

        El despacho de la reconciliacion NO era por tipo a secas: miraba primero si
        la solicitud tiene `DobladaDetalle` y solo despues el tipo, con un `else`
        que significaba "cualquier otro tipo CON detalle, tratalo como DOBLADA".
        Ese orden se conserva aqui, porque el detalle es lo que determina COMO se
        materializo la solicitud.

        La diferencia con antes es que ya no hay una lista de tipos en este
        servicio: se pregunta a la strategy si ella se materializa a traves de un
        detalle de doblada (`usa_detalle_doblada`). Un tipo nuevo se declara en su
        propia clase y este archivo no se toca.
        """
        from solicitudes.services.solicitud_factory import SolicitudFactory
        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy

        # SIN caida por defecto: un tipo desconocido no se re-materializa "como si
        # fuera un cambio de turno". La cadena anterior terminaba sin `else`, y al
        # pasar a despacho por strategy `get_strategy` habria roto ese silencio.
        estrategia = SolicitudFactory.get_strategy_registrada(solicitud.tipo_cambio)
        tiene_detalle = getattr(solicitud, 'doblada', None) is not None
        if tiene_detalle and not getattr(estrategia, 'usa_detalle_doblada', False):
            return DobladaStrategy()
        return estrategia

    @staticmethod
    def _pares_que_reescribe(solicitud, fechas: set) -> set:
        """
        Pares (explorador_id, fecha) que la re-aplicacion de `solicitud` va a
        escribir, dado que la reconciliacion corre sobre `fechas`.

        Lo contesta la STRATEGY. Antes habia aqui una cadena por tipo que era
        "espejo exacto" de la de `_reaplicar_una`, sostenida solo por un comentario
        que pedia mantener las dos sincronizadas a mano. Ahora las dos preguntas se
        le hacen al mismo objeto, asi que no pueden separarse por descuido.
        """
        estrategia = DobladaSnapshotService._estrategia_de(solicitud)
        if estrategia is None:
            return set()
        return estrategia.pares_que_reescribe(solicitud, fechas)

    @staticmethod
    def reconciliar_dobladas_aprobadas(afectados: set, excluir_solicitud_id: int) -> None:
        """
        Tras restaurar el snapshot de una doblada CANCELADA, re-aplica el efecto de las
        dobladas que SIGUEN APROBADAS cuyo cesión/pago cae en las fechas afectadas.

        Motivo: el snapshot de una cesión total (2 solicitudes enlazadas que comparten la
        fecha de cesión) refleja un estado INTERMEDIO. Restaurarlo tal cual deja el estado
        inconsistente según el orden de cancelación. Re-aplicar las dobladas vigentes en
        orden cronológico de aprobación reconstruye el estado correcto.

        Solo se re-aplica el lado (cesión o pago) que cae en una fecha afectada.
        No genera deudas (eso es responsabilidad de DobladaDeudaService).
        """

        if not afectados:
            return

        # CIERRE de las fechas afectadas antes de re-aplicar nada. `afectados` llega con los días
        # de la solicitud CANCELADA, pero varios re-aplicadores reescriben SU EFECTO COMPLETO, no
        # solo el día que coincidió: un CAMBIO DESCANSO de finde reescribe los DOS findes (sáb↔dom
        # de cesión y de devolución) y una D FDS reescribe cesión Y pago. Esos días colaterales no
        # estaban en el conjunto, así que las solicitudes que los tenían vigentes NO se
        # reconciliaban y su efecto se perdía en silencio.
        #
        # Caso real: al cancelar una D FDS (cesión 15/08, pago 08/08) se re-aplicaba un CAMBIO
        # DESCANSO cuya cesión caía el 15/08; ese re-aplicado reescribió también el 09/08 y el
        # 16/08 y borró la D FDS —posterior y aún aprobada— que vivía en esos dos días.
        #
        # Se cierra ANTES de aplicar (no en pasadas de aplicación sucesivas) para que todas las
        # solicitudes vigentes se re-apliquen UNA vez y en orden global de `fecha_resolucion`:
        # así la última aprobada sigue ganando el día, que es el principio del sistema.
        afectados = DobladaSnapshotService._cerrar_afectados(afectados, excluir_solicitud_id)

        fechas = {f for (_e, f) in afectados}
        exploradores = {e for (e, _f) in afectados}

        # UNA sola pasada, en UN solo orden de aprobación (ver `_candidatas_ordenadas`).
        reaplicadas = set()
        for s in DobladaSnapshotService._candidatas_ordenadas(
                fechas, exploradores, excluir_solicitud_id):
            # Una solicitud vigente que YA NO ENCAJA con el calendario actual no puede tumbar la
            # cancelación de OTRA. Los servicios de aplicación tienen guardias de negocio (patrón
            # 39: "no le inventes un turno a quien ese día descansa"), y desde aquí se re-aplican
            # SIN re-validar, así que una de ellas puede levantar ValidationError legítimamente.
            # Sin este `try`, ese error subía y abortaba la transacción entera: el usuario se
            # quedaba sin poder cancelar por culpa de una solicitud ajena que él no puede arreglar.
            #
            # La reconciliación es REPARACIÓN best-effort, no una validación: si una pieza no se
            # puede recolocar, se registra y se sigue con las demás. Se captura SOLO
            # ValidationError (precondición de negocio incumplida); cualquier otro fallo —de BD, de
            # programación— sigue propagándose, porque ahí sí conviene abortar.
            try:
                DobladaSnapshotService._reaplicar_una(s, fechas)
            except ValidationError as e:
                logger.error(
                    "Reconciliación: la solicitud aprobada %s (%s) NO se pudo re-aplicar sobre %s "
                    "y se OMITE para no bloquear la cancelación en curso. Su efecto queda sin "
                    "materializar y hay que revisarla a mano. Motivo: %s",
                    s.id, s.tipo_cambio.nombre if s.tipo_cambio else '?',
                    sorted(fechas), getattr(e, 'messages', [str(e)])[0],
                )
                continue
            reaplicadas.add(s.id)

        # La reconciliación acaba de reescribir turnos: los `snapshot_turnos_resultantes` de las
        # solicitudes que siguen vigentes ahí quedaron desactualizados. Si no se refrescan, la
        # guardia de integridad los vería "modificados por otro" y bloquearía su cancelación
        # legítima. Se hace al final, con el estado ya estabilizado.
        #
        # SOLO las que se acaban de re-aplicar. Refrescar a las demás era un agujero grave: si una
        # solicitud vigente NO se re-materializó (porque no entró como candidata) su efecto está
        # roto, y refrescar su resultante graba el estado ROTO como "lo que esta solicitud dejó".
        # A partir de ahí la discrepancia deja de existir para el sistema: `bloqueo_integridad` no
        # la ve y la auditoría dice que todo está bien. Pasó de verdad con la D FDS #554, cuyo
        # resultante acabó afirmando que había dejado un turno `CAMBIO DESCANSO` en el día que su
        # dueño cedió — algo que una D FDS no puede dejar nunca.
        DobladaSnapshotService.refrescar_resultantes(
            afectados, excluir_solicitud_id, exploradores, ids_reaplicadas=reaplicadas)

        # CACHÉ: Mis Turnos guarda el mes completo por empleado, así que hay que invalidarlo para
        # TODO el conjunto afectado, no solo para las dos partes de la solicitud que se canceló.
        #
        # La reconciliación reescribe turnos de TERCEROS en los días colaterales (el compañero de un
        # cambio de descanso, el receptor de otra doblada…). A ellos nadie les invalidaba el mes:
        # seguían viendo su horario anterior hasta que expirara el TTL. En desarrollo el caché es
        # LocMemCache y un reinicio del servidor lo borraba, lo que hacía parecer que el problema era
        # otro; con Redis en producción no se taparía solo.
        from core.services.cache_service import CacheService
        for (emp_id, fecha) in afectados:
            CacheService.invalidar_cache_turnos_empleado(emp_id, fecha.month, fecha.year)

    @staticmethod
    def _candidatas_ordenadas(fechas: set, exploradores: set, excluir_solicitud_id: int) -> list:
        """
        TODAS las solicitudes aprobadas a re-materializar, en UN ÚNICO orden global de
        `fecha_resolucion`.

        Antes se re-aplicaban en TRES bloques consecutivos: primero las del modelo `doblada`
        (DOBLADA, D FDS, CAMBIO DESCANSO, intercambio), luego las dobladas permanentes, y por
        último los CAMBIO TURNO y CT PERMANENTE. Dentro de cada bloque el orden era correcto, pero
        ENTRE bloques no existía: una doblada permanente aprobada en junio se re-aplicaba DESPUÉS
        de una D FDS aprobada en julio, y le ganaba el día.

        Eso invierte el principio del sistema —la última aprobada gana el día— y no es un caso
        teórico: un mismo (persona, día) puede estar reclamado por dos solicitudes vigentes, porque
        ceder un sábado que se trabaja por una doblada permanente es perfectamente legítimo. Al
        re-aplicar la permanente encima, la persona volvía a trabajar el día que había cedido
        mientras su sustituto también lo tenía asignado: dos personas en el mismo turno.

        Los tres grupos se consultan por separado porque viven en modelos distintos (`doblada`,
        `doblada_permanente`, y el snapshot en la propia solicitud), no porque deban aplicarse en
        ese orden. Aquí se juntan y se ordenan una sola vez.
        """
        from datetime import datetime, timezone as dt_timezone
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio

        base = (SolicitudCambio.objects
                .filter(estado='aprobada')
                .exclude(id=excluir_solicitud_id))

        # DOBLADA, D FDS, CAMBIO DESCANSO e intercambio: comparten el modelo DobladaDetalle, pero
        # cada una se re-aplica con la lógica de SU tipo (ver `_reaplicar_una`).
        con_detalle = (base
                       .filter(doblada__isnull=False)
                       .filter(Q(fecha_cambio_turno__in=fechas)
                               | Q(doblada__fecha_pago__in=fechas)
                               | Q(doblada__fecha_pago_semana__in=fechas))
                       .select_related('doblada', 'tipo_cambio'))

        # DOBLADA PERMANENTE: si no se re-materializa, restaurar un snapshot que pise un día
        # `DOBLADA PERM` borra la doblada y deja viva su deuda de 30 min (y no la detecta
        # `cancelar_deudas_huerfanas`, porque sí tiene solicitud de origen).
        permanentes = (base
                       .filter(doblada_permanente__isnull=False,
                               doblada_permanente__fecha_inicio__lte=max(fechas))
                       .filter(Q(doblada_permanente__fecha_fin__gte=min(fechas))
                               | Q(doblada_permanente__fecha_fin__isnull=True))
                       .select_related('doblada_permanente', 'tipo_cambio'))

        # CAMBIO TURNO y CT PERMANENTE: su snapshot vive en la propia solicitud, así que no entran
        # por las dos consultas anteriores. Sin ellos, restaurar cualquier snapshot que pisara su
        # día los borraba en silencio y la persona volvía a su jornada base sin que nada avisara.
        # No se filtran por fecha aquí: sus `reaplicar_fechas` ya se acotan a `fechas`.
        cambios_turno = (base
                         .filter(tipo_cambio__nombre__in=['CAMBIO TURNO', 'CT PERMANENTE'])
                         .select_related('tipo_cambio', 'explorador_solicitante',
                                         'explorador_receptor'))

        vistas, candidatas = set(), []
        for qs in (con_detalle, permanentes, cambios_turno):
            for s in qs.distinct():
                if s.id in vistas:
                    continue
                if (s.explorador_solicitante_id not in exploradores
                        and s.explorador_receptor_id not in exploradores):
                    continue
                vistas.add(s.id)
                candidatas.append(s)

        # `fecha_resolucion` no debería faltar en una aprobada, pero si falta se re-aplica primero
        # (lo más antiguo posible): así nunca gana un día por un dato ausente.
        sin_fecha = datetime.min.replace(tzinfo=dt_timezone.utc)
        candidatas.sort(key=lambda s: (s.fecha_resolucion or sin_fecha, s.id))
        return candidatas

    @staticmethod
    def _reaplicar_una(solicitud, fechas: set) -> None:
        """
        Re-materializa UNA solicitud aprobada sobre `fechas`, con la logica de su
        tipo. Lo hace la STRATEGY.

        `_pares_que_reescribe` es el espejo de esto: lo que aqui se re-aplique tiene
        que estar declarado alli, o el cierre de fechas afectadas se queda corto y
        se pierde en silencio lo que viva en los dias colaterales (patron #33).
        Ahora los dos metodos viven en la MISMA clase, que es lo que impide que se
        separen; antes eran dos cadenas gemelas en este archivo.
        """
        estrategia = DobladaSnapshotService._estrategia_de(solicitud)
        if estrategia is None:
            return
        estrategia.reaplicar(solicitud, fechas)
        if getattr(solicitud, 'doblada', None) is not None:
            logger.info(
                "Reconciliacion post-revert: re-aplicada solicitud aprobada %s (%s) sobre fechas afectadas.",
                solicitud.id,
                solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else '',
            )

    @staticmethod
    def refrescar_resultantes(afectados: set, excluir_solicitud_id: int,
                              exploradores: set = None, ids_reaplicadas: set = None) -> None:
        """
        Recalcula `snapshot_turnos_resultantes` de las solicitudes aprobadas que tocan `afectados`.

        `ids_reaplicadas`: restringe el refresco a esas solicitudes. Es lo correcto tras una
        reconciliación —solo el que se re-aplicó tiene un resultante legítimamente nuevo—; refrescar
        al resto adopta como propio un estado que puede estar roto y ciega la guardia de integridad.
        """
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio

        if exploradores is None:
            exploradores = {e for (e, _f) in afectados}
        claves_afectadas = {f"{e}:{f.isoformat()}" for (e, f) in afectados}

        vigentes = (
            SolicitudCambio.objects
            .filter(estado='aprobada')
            .filter(Q(explorador_solicitante_id__in=exploradores)
                    | Q(explorador_receptor_id__in=exploradores))
            .exclude(id=excluir_solicitud_id)
            .select_related('doblada', 'doblada_permanente')
            .distinct()
        )
        if ids_reaplicadas is not None:
            vigentes = vigentes.filter(id__in=ids_reaplicadas)
        for s in vigentes:
            for obj in (s, getattr(s, 'doblada', None), getattr(s, 'doblada_permanente', None)):
                if obj is None:
                    continue
                previo = getattr(obj, 'snapshot_turnos_previos', None) or {}
                comunes = claves_afectadas & set(previo.keys()) if previo else set()
                if not comunes:
                    continue
                # SOLO las claves que la reconciliación acaba de reconstruir. Una doblada toca
                # 2-3 días (cesión, pago y devolución en semana) y aquí puede entrar por UNO de
                # ellos. Recalcular el resultante COMPLETO reescribiría también los días que
                # nadie tocó: si alguien los había modificado por fuera (admin, permiso
                # especial), esa discrepancia —justo la que `bloqueo_integridad` debe detectar—
                # quedaría adoptada como "lo que esta solicitud dejó" y la cancelación pisaría
                # el cambio ajeno en silencio. Por eso se fusiona en vez de reemplazar.
                resultante = dict(getattr(obj, 'snapshot_turnos_resultantes', None) or {})
                resultante.update(DobladaSnapshotService.serializar_pares(comunes))
                obj.snapshot_turnos_resultantes = resultante
                try:
                    obj.save(update_fields=['snapshot_turnos_resultantes'])
                except ValueError:
                    # No se cambia el flujo, pero deja de ser invisible: este snapshot es
                    # lo que hace posible revertir (patrones #3, #13 y #24). Si el guardado
                    # falla y nadie se entera, una cancelación posterior restauraría un
                    # estado incompleto creyendo que es el bueno.
                    logger.exception(
                        'No se pudo guardar snapshot_turnos_resultantes de %s id=%s: una '
                        'cancelación posterior partiría de un snapshot incompleto',
                        type(obj).__name__, getattr(obj, 'pk', '?'))
