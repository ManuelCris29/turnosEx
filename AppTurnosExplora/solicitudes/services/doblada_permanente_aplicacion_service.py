"""
Aplicación de Doblada Permanente.

Recorre el rango y, por cada ocurrencia válida (día de semana seleccionado, NO
domingo ni festivo):
- Días de cesión: el receptor se dobla (AM+PM) y el solicitante descansa.
- Días de devolución: el solicitante se dobla (AM+PM) y el receptor descansa.

Cada doblada efectiva acumula 30 min de deuda corporativa para quien se dobla
(se ve en el Consolidado de Horas y se paga vía PDH).
"""
from datetime import date, timedelta
import logging

from django.db import transaction

from turnos.models import Turno
from .deuda_corporativa_service import DeudaCorporativaService
from .d_fds_aplicacion_service import DFDSAplicacionService

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
        from .ct_permanente_helper import _jornada_doblada_perm
        d = fecha_inicio
        while d <= fecha_fin:
            if d.weekday() in dias_set and d.weekday() < 5:
                # `excluir_id` ignora ESTA solicitud (al re-validar/aplicar ya aprobada) para no
                # auto-excluirse por su propio descanso.
                js = _jornada_doblada_perm(solicitante, d, excluir_id) if solicitante else None
                jr = _jornada_doblada_perm(receptor, d, excluir_id) if receptor else None
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
        from .ct_permanente_helper import _jornada_doblada_perm
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
            js = _jornada_doblada_perm(solicitante, d, excluir_id) if solicitante else None
            jr = _jornada_doblada_perm(receptor, d, excluir_id) if receptor else None
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
        from .ct_permanente_helper import _jornada_doblada_perm, _motivo_no_doblada_perm

        fi = detalle.fecha_inicio
        ff = detalle.fecha_fin or date(fi.year, 12, 31)

        def _elegible(d):
            js = _jornada_doblada_perm(solicitante, d)
            jr = _jornada_doblada_perm(receptor, d)
            if js is not None and jr is not None and js != jr:
                return True, None
            razon = (
                _motivo_no_doblada_perm(solicitante, d)
                or _motivo_no_doblada_perm(receptor, d)
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
        DeudaCorporativaService.crear_deuda_corporativa(
            explorador=explorador,
            minutos=30,
            fecha_generacion=date.today(),
            fecha_doblada=fecha,
            solicitud=solicitud,
            comentario=f'Doblada permanente ({etiqueta}) — {fecha}',
        )

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
        # día comprometido). Si el detalle trae FECHAS específicas se usan esas (permite balancear
        # con distinto número de ocurrencias por weekday); si no, se expanden los weekdays.
        fces = getattr(detalle, 'fechas_cesion', '') or ''
        fdev = getattr(detalle, 'fechas_devolucion', '') or ''
        if fces or fdev:
            ocur_ces = DobladaPermanenteAplicacionService._fechas_validas(
                fces, detalle.fecha_inicio, detalle.fecha_fin, solicitante, receptor, _ex)
            ocur_dev = DobladaPermanenteAplicacionService._fechas_validas(
                fdev, detalle.fecha_inicio, detalle.fecha_fin, solicitante, receptor, _ex)
        else:
            _occ = DobladaPermanenteAplicacionService._ocurrencias
            cesion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_cesion)
            devolucion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_devolucion)
            ocur_ces = list(_occ(detalle.fecha_inicio, detalle.fecha_fin, cesion, solicitante, receptor, _ex))
            ocur_dev = list(_occ(detalle.fecha_inicio, detalle.fecha_fin, devolucion, solicitante, receptor, _ex))
        # BALANCE: solo se aplican PARES cubrir↔devolver → se recorta cada lado al MÍNIMO común
        # (nunca se paga un favor que no se recibió, ni al revés).
        n = min(len(ocur_ces), len(ocur_dev))
        ocur_ces, ocur_dev = ocur_ces[:n], ocur_dev[:n]

        # Snapshot de las fechas afectadas ANTES de mutar (para revertir en 30 min).
        fechas_afectadas = sorted(set(ocur_ces + ocur_dev))
        if not getattr(detalle, 'snapshot_turnos_previos', None):
            snapshot = DobladaPermanenteAplicacionService._capturar_snapshot(solicitante, receptor, fechas_afectadas)
            from solicitudes.models import DobladaPermanenteDetalle as _DPD
            _DPD.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snapshot)
            detalle.snapshot_turnos_previos = snapshot

        n_ces = n_dev = 0

        # Cesión: receptor dobla, solicitante descansa
        for fecha in ocur_ces:
            DFDSAplicacionService._crear_doblada_dia(receptor, fecha, tipo_cambio='DOBLADA PERM')
            Turno.objects.filter(explorador=solicitante, fecha=fecha).delete()
            DobladaPermanenteAplicacionService._deuda(receptor, fecha, solicitud, 'cesión')
            n_ces += 1

        # Devolución: solicitante dobla, receptor descansa
        for fecha in ocur_dev:
            DFDSAplicacionService._crear_doblada_dia(solicitante, fecha, tipo_cambio='DOBLADA PERM')
            Turno.objects.filter(explorador=receptor, fecha=fecha).delete()
            DobladaPermanenteAplicacionService._deuda(solicitante, fecha, solicitud, 'devolución')
            n_dev += 1

        logger.info(
            "Doblada permanente aplicada: solicitud %s — %s ocurrencias cesión (receptor dobla), "
            "%s ocurrencias devolución (solicitante dobla)",
            solicitud.id, n_ces, n_dev,
        )
        return n_ces, n_dev

    @staticmethod
    @transaction.atomic
    def revertir(solicitud):
        """
        Revierte una doblada permanente aplicada (cancelación dentro de los 30 min):
        - Restaura los turnos previos desde el snapshot (borra las dobladas creadas
          y recrea lo que había antes).
        - Cancela las deudas corporativas generadas por la solicitud.
        """
        from solicitudes.models import DeudaCorporativa
        from .doblada_aplicacion_service import DobladaAplicacionService

        detalle = solicitud.doblada_permanente
        snapshot = getattr(detalle, 'snapshot_turnos_previos', None)
        if snapshot:
            DobladaAplicacionService.restaurar_turnos_desde_snapshot(snapshot)
        else:
            # Sin snapshot: al menos eliminar las dobladas creadas en el rango.
            fces = getattr(detalle, 'fechas_cesion', '') or ''
            fdev = getattr(detalle, 'fechas_devolucion', '') or ''
            if fces or fdev:
                lados = (
                    (DobladaPermanenteAplicacionService._fechas_validas(fces, detalle.fecha_inicio, detalle.fecha_fin), solicitud.explorador_receptor),
                    (DobladaPermanenteAplicacionService._fechas_validas(fdev, detalle.fecha_inicio, detalle.fecha_fin), solicitud.explorador_solicitante),
                )
            else:
                cesion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_cesion)
                devolucion = DobladaPermanenteAplicacionService._parse_dias(detalle.dias_devolucion)
                lados = (
                    (DobladaPermanenteAplicacionService._ocurrencias(detalle.fecha_inicio, detalle.fecha_fin, cesion), solicitud.explorador_receptor),
                    (DobladaPermanenteAplicacionService._ocurrencias(detalle.fecha_inicio, detalle.fecha_fin, devolucion), solicitud.explorador_solicitante),
                )
            for fechas, quien in lados:
                for fecha in fechas:
                    Turno.objects.filter(explorador=quien, fecha=fecha, tipo_cambio='DOBLADA PERM').delete()

        DeudaCorporativa.objects.filter(solicitud_origen=solicitud).update(estado='cancelada')
        logger.info("Doblada permanente revertida: solicitud %s", solicitud.id)
