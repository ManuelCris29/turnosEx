"""
Aplicación de Doblada Permanente.

Recorre el rango y, por cada ocurrencia válida (día de semana seleccionado, NO
domingo ni festivo):
- Días de cesión: el receptor se dobla (AM+PM) y el solicitante descansa.
- Días de devolución: el solicitante se dobla (AM+PM) y el receptor descansa.

Cada doblada efectiva acumula 30 min de deuda corporativa para quien se dobla
(se ve en el Consolidado de Horas y se paga vía PDH).

Además se registra el favor ENTRE LOS DOS EXPLORADORES: una `DeudaExplorador` por cada par
(cesión, devolución), que es lo que alimenta la pantalla "Mis Favores". Una doblada permanente
es la misma operación que una doblada suelta repetida N veces, así que deja el mismo rastro;
antes solo se guardaba la deuda corporativa y la pantalla salía vacía aunque el compañero te
hubiera cubierto doce días. Ver `docs/05-referencia/solicitudes/COBERTURA_MIS_FAVORES.md`.
"""
import logging
from datetime import date, timedelta

from django.db import transaction

from core.constants import JornadaDisplay, TipoCambioTurno
from turnos.models import Turno

from .d_fds_aplicacion_service import DFDSAplicacionService
from .deuda_corporativa_service import DeudaCorporativaService
from .deuda_service import DeudaService

logger = logging.getLogger(__name__)


class DobladaPermanenteAplicacionService:

    @staticmethod
    def _parse_dias(dias_str):
        return {int(x) for x in (dias_str or '').split(',') if x.strip().isdigit()}

    @staticmethod
    def _ocurrencias(fecha_inicio, fecha_fin, dias_set, solicitante=None, receptor=None, excluir_id=None):
        """
        Fechas del rango cuyo weekday está en dias_set y que son VÁLIDAS para doblada.
        La elegibilidad se decide con la jornada REAL de "Mis Turnos" (`estado_dia`), no con la
        base/config, así que se OMITEN (no se rechaza todo) los días en que el solicitante o el
        receptor NO tienen una jornada única AM/PM ese día: ya están en DOBLADA (incluidas las
        virtuales por temporada/festivo), descansan (rotación, temporada, mantenimiento, fin de
        semana, o por otra solicitud) o no tienen turno. Los días cambiados por CT sencillo/permanente
        o por un cambio de descanso SÍ se incluyen con su jornada real. Cuando se pasan AMBOS
        exploradores, además exige que ese día tengan jornada CONTRARIA (uno AM y el otro PM).
        """
        from .ct_permanente_helper import jornada_doblada_perm
        d = fecha_inicio
        while d <= fecha_fin:
            if d.weekday() in dias_set and d.weekday() < 5:
                # `excluir_id` ignora ESTA solicitud (al re-validar/aplicar ya aprobada) para no
                # auto-excluirse por su propio descanso.
                js = jornada_doblada_perm(solicitante, d, excluir_id) if solicitante else None
                jr = jornada_doblada_perm(receptor, d, excluir_id) if receptor else None
                _ok = True
                if solicitante and js is None:
                    _ok = False
                if receptor and jr is None:
                    _ok = False
                if _ok and solicitante and receptor and js == jr:
                    _ok = False  # deben ser contrarias
                if _ok:
                    yield d
            d += timedelta(days=1)

    @staticmethod
    def _fechas_validas(fechas_csv, fecha_inicio, fecha_fin, solicitante=None, receptor=None, excluir_id=None):
        """
        Igual que `_ocurrencias` pero sobre FECHAS ESPECÍFICAS (CSV de YYYY-MM-DD): filtra las que
        estén en el rango, sean lun-vie y válidas según la jornada REAL de "Mis Turnos" (`estado_dia`):
        ambos con jornada única AM/PM y CONTRARIA ese día; se omiten dobladas (incl. virtuales),
        descansos y días sin turno. Devuelve ordenadas.
        """
        from .ct_permanente_helper import jornada_doblada_perm
        out = []
        for s in (fechas_csv or '').split(','):
            s = s.strip()
            if not s:
                continue
            try:
                d = date.fromisoformat(s)
            except ValueError:
                continue
            if not (fecha_inicio <= d <= fecha_fin and d.weekday() < 5):
                continue
            js = jornada_doblada_perm(solicitante, d, excluir_id) if solicitante else None
            jr = jornada_doblada_perm(receptor, d, excluir_id) if receptor else None
            if solicitante and js is None:
                continue
            if receptor and jr is None:
                continue
            if solicitante and receptor and js == jr:
                continue
            out.append(d)
        return sorted(out)

    @staticmethod
    def calcular_fechas_aplicables_y_excluidas(detalle, solicitante, receptor):
        """
        Fechas CONCRETAS de cesión y devolución dentro del rango vigente, con las mismas reglas
        de elegibilidad y de balance (recorte al mínimo común) que `aplicar()`, para mostrarlas
        en el detalle de la solicitud (igual que hace CT Permanente).

        Returns:
            {'cesion': {'aplicables': [date], 'excluidas': [{'fecha': date, 'razon': str}]},
             'devolucion': {'aplicables': [date], 'excluidas': [{'fecha': date, 'razon': str}]}}
        """
        from .ct_permanente_helper import jornada_doblada_perm, motivo_no_doblada_perm

        fi = detalle.fecha_inicio
        ff = detalle.fecha_fin or date(fi.year, 12, 31)

        def _elegible(d):
            js = jornada_doblada_perm(solicitante, d)
            jr = jornada_doblada_perm(receptor, d)
            if js is not None and jr is not None and js != jr:
                return True, None
            razon = (
                motivo_no_doblada_perm(solicitante, d)
                or motivo_no_doblada_perm(receptor, d)
                or 'Sin jornada única disponible'
            )
            return False, razon

        def _explorar_dias_semana(dias_set):
            aplicables = []
            excluidas = []
            d = fi
            while d <= ff:
                if d.weekday() in dias_set and d.weekday() < 5:
                    ok, razon = _elegible(d)
                    if ok:
                        aplicables.append(d)
                    else:
                        excluidas.append({'fecha': d, 'razon': razon})
                d += timedelta(days=1)
            return aplicables, excluidas

        def _explorar_fechas_especificas(fechas_csv):
            aplicables = []
            excluidas = []
            for s in (fechas_csv or '').split(','):
                s = s.strip()
                if not s:
                    continue
                try:
                    d = date.fromisoformat(s)
                except ValueError:
                    continue
                if not (fi <= d <= ff and d.weekday() < 5):
                    continue
                ok, razon = _elegible(d)
                if ok:
                    aplicables.append(d)
                else:
                    excluidas.append({'fecha': d, 'razon': razon})
            return sorted(aplicables), sorted(excluidas, key=lambda x: x['fecha'])

        fces = getattr(detalle, 'fechas_cesion', '') or ''
        fdev = getattr(detalle, 'fechas_devolucion', '') or ''
        if fces or fdev:
            ces_ap, ces_ex = _explorar_fechas_especificas(fces)
            dev_ap, dev_ex = _explorar_fechas_especificas(fdev)
        else:
            dias_cesion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_cesion)
            dias_devolucion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_devolucion)
            ces_ap, ces_ex = _explorar_dias_semana(dias_cesion)
            dev_ap, dev_ex = _explorar_dias_semana(dias_devolucion)

        # Balance: igual que aplicar(), solo se aplican PARES completos (recorte al mínimo común).
        n = min(len(ces_ap), len(dev_ap))
        for fecha in ces_ap[n:]:
            ces_ex.append({'fecha': fecha, 'razon': 'Sin par de devolución disponible (balance)'})
        for fecha in dev_ap[n:]:
            dev_ex.append({'fecha': fecha, 'razon': 'Sin par de cesión disponible (balance)'})
        ces_ap, dev_ap = ces_ap[:n], dev_ap[:n]

        ces_ex.sort(key=lambda x: x['fecha'])
        dev_ex.sort(key=lambda x: x['fecha'])

        return {
            'cesion': {'aplicables': ces_ap, 'excluidas': ces_ex},
            'devolucion': {'aplicables': dev_ap, 'excluidas': dev_ex},
        }

    @staticmethod
    def _deuda(explorador, fecha, solicitud, etiqueta):
        # Los 30 min solo aplican de lunes a viernes (no sábados ni festivos:
        # esos días se trabaja jornada completa). Los festivos/domingos ya se
        # excluyen de las ocurrencias; aquí cubrimos también el sábado.
        if not DeudaCorporativaService.aplica_deuda_doblada(fecha):
            return
        # Los 30 min se deben por el HECHO de doblar, no por el tipo de solicitud: hay que
        # confirmar contra el estado REAL del día, igual que hacen DOBLADA, D FDS y cambio de
        # descanso. Antes se creaba a ciegas sobre las ocurrencias calculadas, así que una
        # ocurrencia que no acabara en AM+PM (el explorador ya descansaba ese día por otra
        # solicitud, o `_crear_doblada_dia` no pudo doblarlo) cobraba 30 min igualmente.
        from turnos.services.turno_service import TurnoService
        if TurnoService.obtener_jornada_display(explorador, fecha) != JornadaDisplay.DOBLADA:
            logger.info(
                "Doblada permanente: sin deuda corporativa para %s en %s (%s): el día no quedó "
                "DOBLADA.", explorador.nombre, fecha, etiqueta,
            )
            return
        # IDEMPOTENTE: un día doblado = UNA deuda de 30 min, venga de la solicitud que venga.
        DeudaCorporativaService.crear_deuda_corporativa_idempotente(
            explorador=explorador,
            minutos=30,
            fecha_doblada=fecha,
            solicitud=solicitud,
            comentario=f'Doblada permanente ({etiqueta}) — {fecha}',
        )

    @staticmethod
    def _calcular_ocurrencias(detalle, solicitante=None, receptor=None, excluir_id=None, balancear=True):
        """
        Fechas concretas de (cesión, devolución) de esta doblada permanente.

        Punto ÚNICO de cálculo: si el detalle trae FECHAS específicas se usan esas (permite
        balancear con distinto número de ocurrencias por weekday); si no, se expanden los
        weekdays. Con `balancear` se recorta cada lado al MÍNIMO común (solo pares completos).
        """
        fi = detalle.fecha_inicio
        ff = detalle.fecha_fin or date(fi.year, 12, 31)  # mismo fallback que el detalle de la solicitud
        fces = getattr(detalle, 'fechas_cesion', '') or ''
        fdev = getattr(detalle, 'fechas_devolucion', '') or ''
        if fces or fdev:
            _f = DobladaPermanenteAplicacionService._fechas_validas
            ces = _f(fces, fi, ff, solicitante, receptor, excluir_id)
            dev = _f(fdev, fi, ff, solicitante, receptor, excluir_id)
        else:
            _occ = DobladaPermanenteAplicacionService._ocurrencias
            _parse = DobladaPermanenteAplicacionService._parse_dias
            ces = list(_occ(fi, ff, _parse(detalle.dias_cesion), solicitante, receptor, excluir_id))
            dev = list(_occ(fi, ff, _parse(detalle.dias_devolucion), solicitante, receptor, excluir_id))
        if balancear:
            n = min(len(ces), len(dev))
            ces, dev = ces[:n], dev[:n]
        return ces, dev

    @staticmethod
    def _capturar_snapshot(solicitante, receptor, fechas):
        """Estado de Turno (solicitante y receptor) en las fechas afectadas, antes de aplicar."""
        snapshot = {}
        for emp in (solicitante, receptor):
            for fecha in fechas:
                key = f"{emp.id}:{fecha.isoformat()}"
                turnos = Turno.objects.filter(explorador=emp, fecha=fecha).select_related('jornada').order_by('jornada_id')
                snapshot[key] = [
                    {'jornada_nombre': t.jornada.nombre.upper(), 'sala_id': t.sala_id, 'tipo_cambio': t.tipo_cambio}
                    for t in turnos
                ]
        return snapshot

    @staticmethod
    @transaction.atomic
    def aplicar(solicitud, detalle):
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        _ex = solicitud.id  # excluir ESTA solicitud (ya aprobada) de la detección L2

        # Ocurrencias VÁLIDAS de cada lado (ya omiten festivo/temporada/mantenimiento/descanso/
        # día comprometido). BALANCE: solo se aplican PARES cubrir↔devolver → cada lado se recorta
        # al MÍNIMO común (nunca se paga un favor que no se recibió, ni al revés).
        ocur_ces, ocur_dev = DobladaPermanenteAplicacionService._calcular_ocurrencias(
            detalle, solicitante, receptor, _ex)

        # Snapshot de las fechas afectadas ANTES de mutar (para revertir en 30 min).
        fechas_afectadas = sorted(set(ocur_ces + ocur_dev))
        if not getattr(detalle, 'snapshot_turnos_previos', None):
            snapshot = DobladaPermanenteAplicacionService._capturar_snapshot(solicitante, receptor, fechas_afectadas)
            from solicitudes.models import DobladaPermanenteDetalle as _DPD
            _DPD.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snapshot)
            detalle.snapshot_turnos_previos = snapshot

        n_ces = n_dev = 0

        # La jornada que el solicitante CEDE cada día hay que leerla ANTES de mutar nada: los
        # bucles de abajo le borran el turno, y después el día ya no dice qué jornada tenía.
        from .ct_permanente_helper import jornada_doblada_perm
        jornadas_cedidas = {
            fecha: jornada_doblada_perm(solicitante, fecha, _ex) for fecha in ocur_ces
        }

        # Cesión: receptor dobla, solicitante descansa
        for fecha in ocur_ces:
            DFDSAplicacionService._crear_doblada_dia(receptor, fecha, tipo_cambio=TipoCambioTurno.DOBLADA_PERM)
            Turno.objects.filter(explorador=solicitante, fecha=fecha).delete()
            DobladaPermanenteAplicacionService._deuda(receptor, fecha, solicitud, 'cesión')
            # El solicitante pierde sus turnos ese día: si venía doblando, deja de doblar y sus
            # 30 min de esa fecha ya no corresponden.
            DeudaCorporativaService.sincronizar_deuda_corporativa(
                solicitante, fecha, motivo=f'cede el día en la doblada permanente {solicitud.id}')
            n_ces += 1

        # Devolución: solicitante dobla, receptor descansa
        for fecha in ocur_dev:
            DFDSAplicacionService._crear_doblada_dia(solicitante, fecha, tipo_cambio=TipoCambioTurno.DOBLADA_PERM)
            Turno.objects.filter(explorador=receptor, fecha=fecha).delete()
            DobladaPermanenteAplicacionService._deuda(solicitante, fecha, solicitud, 'devolución')
            DeudaCorporativaService.sincronizar_deuda_corporativa(
                receptor, fecha, motivo=f'descansa en la doblada permanente {solicitud.id}')
            n_dev += 1

        DobladaPermanenteAplicacionService._deudas_entre_exploradores(
            solicitud, solicitante, receptor, ocur_ces, ocur_dev, jornadas_cedidas)

        # Estado RESULTANTE: lo que esta doblada permanente deja en esas fechas. Al cancelar se
        # compara contra los turnos actuales para no pisar un cambio ajeno posterior.
        from .doblada_snapshot_service import DobladaSnapshotService
        DobladaSnapshotService.capturar_snapshot_resultante(detalle)

        logger.info(
            "Doblada permanente aplicada: solicitud %s — %s ocurrencias cesión (receptor dobla), "
            "%s ocurrencias devolución (solicitante dobla)",
            solicitud.id, n_ces, n_dev,
        )
        return n_ces, n_dev

    @staticmethod
    def _deudas_entre_exploradores(solicitud, solicitante, receptor, ocur_ces, ocur_dev,
                                   jornadas_cedidas):
        """
        Una `DeudaExplorador` por cada par (cesión, devolución): el favor entre las dos personas,
        que es lo que lee "Mis Favores".

        El emparejamiento por índice es válido porque `_calcular_ocurrencias(balancear=True)` ya
        recortó ambos lados al mínimo común: `ocur_ces[i]` se salda con `ocur_dev[i]`. Nace
        'pagada' (con `fecha_pago_real`) igual que la doblada suelta, porque la devolución se
        aplica en el mismo acto, no queda abierta.

        Idempotente por (solicitud, deudor, acreedor, fecha_pago_pactada): como cada par tiene
        una fecha de devolución distinta, re-aplicar la solicitud no duplica ninguna fila.
        """
        for fecha_ces, fecha_dev in zip(ocur_ces, ocur_dev):
            DeudaService.crear_deuda_idempotente(
                deudor=solicitante,          # cedió su jornada ese día
                acreedor=receptor,           # dobló para cubrirla
                solicitud=solicitud,
                fecha_pago_pactada=fecha_dev,
                fecha_pago_real=fecha_dev,
                # Sin jornada legible (día raro o solicitud antigua) no se inventa: 'AM' es el
                # mismo valor por defecto que usa D FDS, y el campo no admite vacío.
                jornada_cedida=jornadas_cedidas.get(fecha_ces) or 'AM',
                media_jornada=True,          # se cede UNA jornada, no el día entero
            )
        if ocur_ces:
            logger.info(
                "Doblada permanente %s: %d favor(es) entre %s y %s registrados en Mis Favores.",
                solicitud.id, len(ocur_ces), solicitante.nombre, receptor.nombre,
            )

    @staticmethod
    @transaction.atomic
    def reaplicar_fechas(solicitud, detalle, fechas):
        """
        Re-materializa SOLO los días de esta doblada permanente que caen en `fechas`.

        La usa la reconciliación posterior a cancelar OTRA solicitud: al restaurar su snapshot
        se pisan los turnos DOBLADA PERM que seguían vigentes, y hay que reconstruirlos. No toca
        deudas (las de esta solicitud ya existen y siguen siendo válidas) ni el snapshot.
        """
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fechas = set(fechas or ())
        if not fechas:
            return 0

        # Qué días se aplicaron realmente: NO se puede re-derivar de la jornada real (el día que
        # se acaba de pisar ya no parece "elegible"), así que se usan las claves del snapshot,
        # que son exactamente las fechas afectadas al aplicar. Los candidatos van sin filtro de
        # estado (solicitante/receptor a None) y se intersectan con lo aplicado.
        from .doblada_snapshot_service import DobladaSnapshotService
        aplicadas = {
            f for (_e, f) in DobladaSnapshotService.fechas_explorador_afectados(
                getattr(detalle, 'snapshot_turnos_previos', None))
        }
        ocur_ces, ocur_dev = DobladaPermanenteAplicacionService._calcular_ocurrencias(
            detalle, balancear=False)
        if aplicadas:
            ocur_ces = [f for f in ocur_ces if f in aplicadas]
            ocur_dev = [f for f in ocur_dev if f in aplicadas]
        else:
            # Sin snapshot (solicitudes antiguas): caer a la eligibilidad en vivo, que como
            # mínimo no inventa días que nunca se aplicaron.
            ocur_ces, ocur_dev = DobladaPermanenteAplicacionService._calcular_ocurrencias(
                detalle, solicitante, receptor, solicitud.id)

        n = 0
        for fecha in (f for f in ocur_ces if f in fechas):
            DFDSAplicacionService._crear_doblada_dia(receptor, fecha, tipo_cambio=TipoCambioTurno.DOBLADA_PERM)
            Turno.objects.filter(explorador=solicitante, fecha=fecha).delete()
            n += 1
        for fecha in (f for f in ocur_dev if f in fechas):
            DFDSAplicacionService._crear_doblada_dia(solicitante, fecha, tipo_cambio=TipoCambioTurno.DOBLADA_PERM)
            Turno.objects.filter(explorador=receptor, fecha=fecha).delete()
            n += 1

        if n:
            logger.info(
                "Doblada permanente %s re-materializada en %d día(s) por reconciliación.",
                solicitud.id, n,
            )
        return n

    @staticmethod
    @transaction.atomic
    def revertir(solicitud):
        """
        Revierte una doblada permanente aplicada (cancelación dentro de los 30 min):
        - Restaura los turnos previos desde el snapshot (borra las dobladas creadas
          y recrea lo que había antes).
        - Cancela las deudas corporativas y los favores entre exploradores generados
          por la solicitud.
        """
        from solicitudes.models import DeudaExplorador

        from .doblada_aplicacion_service import DobladaAplicacionService

        detalle = solicitud.doblada_permanente
        snapshot = getattr(detalle, 'snapshot_turnos_previos', None)
        if snapshot:
            DobladaAplicacionService.restaurar_turnos_desde_snapshot(snapshot)
        else:
            # Sin snapshot: al menos eliminar las dobladas creadas en el rango. Sin balancear:
            # aquí se BORRA, así que conviene cubrir el superconjunto.
            ces, dev = DobladaPermanenteAplicacionService._calcular_ocurrencias(detalle, balancear=False)
            lados = (
                (ces, solicitud.explorador_receptor),
                (dev, solicitud.explorador_solicitante),
            )
            for fechas, quien in lados:
                for fecha in fechas:
                    Turno.objects.filter(explorador=quien, fecha=fecha, tipo_cambio=TipoCambioTurno.DOBLADA_PERM).delete()

        # Solo las ACTIVAS: una deuda corporativa ya pagada sigue pagada aunque se revierta.
        DeudaCorporativaService.cancelar_deudas_de_solicitud(
            solicitud, motivo='doblada permanente revertida')
        # Un acuerdo deshecho no es un favor: se cancelan igual que en D FDS y en la doblada
        # suelta, o quedarían para siempre en "Mis Favores" de ambos exploradores.
        DeudaExplorador.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')
        # Patrón #22: restaurar el snapshot arrasa cada día del rango. Reconstruir lo que SIGUE
        # vigente en esas fechas (otra doblada, un CT, un CT permanente…) o se borra en silencio.
        if snapshot:
            DobladaAplicacionService.reconciliar_dobladas_aprobadas(
                DobladaAplicacionService._fechas_explorador_afectados(snapshot), solicitud.id)
        logger.info("Doblada permanente revertida: solicitud %s", solicitud.id)
