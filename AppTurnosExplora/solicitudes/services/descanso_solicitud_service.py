"""
Fuente ÚNICA de la atribución de DESCANSO por solicitud aprobada.

Antes esta regla ("¿qué día descansa este empleado por una solicitud, y con qué
compañero?") estaba reimplementada en 3-4 lugares (estado_dia, estado_mes y los
endpoints de Mis Turnos), que divergían entre sí y causaban bugs (p. ej. atribuir el
descanso de una doblada permanente al compañero equivocado cuando el mismo día de la
semana se reparte entre varios compañeros por fechas distintas).

`DescansoPorSolicitudService.en_rango(empleado, ini, fin)` centraliza esa regla para un
rango de fechas y devuelve, por fecha, un dict con toda la info que consumen las vistas:

    {
        fecha: {
            'motivo': str,                 # 'cedió su jornada' | 'paga doblada' |
                                           # 'cambio de día de descanso' | 'doblada permanente'
            'origen': str|None,            # 'cambio_descanso' → es un INTERCAMBIO, no un día libre
            'tipo': str,                   # 'cedio' | 'pago'
            'companero': {'id','nombre'}|None,
            'solicitud_id': int|None,
            'fecha_cesion': 'dd/mm/aaaa'|None,
            'fecha_pago': 'dd/mm/aaaa'|None,
            'tipo_cesion': str|None,
            'jornada_cedida': str|None,
        }
    }

Cubre los 4 tipos que generan descanso: DOBLADA, D FDS, CAMBIO DESCANSO y DOBLADA
PERMANENTE. SIEMPRE por FECHA específica (nunca por patrón de día de la semana), igual
que se aplica realmente.

`estado_dia`/`estado_mes` (TurnoService) y el endpoint `mis-turnos-por-mes` delegan aquí.
"""
from datetime import date, timedelta
from core.utils.date_utils import DateUtils


class DescansoPorSolicitudService:

    # Prioridad de tipos (el primero que reclame una fecha gana): igual que el orden
    # histórico de `_descanso_por_solicitud` y `estado_mes`.
    @staticmethod
    def en_rango(empleado, ini, fin, excluir_id=None):
        """Atribución de descanso de UN empleado en un rango: { fecha: info }.

        Atajo sobre `en_rango_multiple`, que es la implementación real. Así el reporte del día
        (que necesita la plantilla entera en pocas consultas) y Mis Turnos comparten literalmente
        el mismo código, no dos copias que se desincronizan.
        """
        return DescansoPorSolicitudService.en_rango_multiple(
            [empleado], ini, fin, excluir_id=excluir_id
        ).get(getattr(empleado, 'id', empleado), {})

    @staticmethod
    def en_rango_multiple(empleados, ini, fin, excluir_id=None):
        """
        Versión BATCH: { emp_id: { fecha: info } } para VARIOS empleados con un número de consultas
        constante (no N×empleado). La usa el reporte operativo del día, que clasifica a toda la
        plantilla a la vez — con ~400 exploradores la versión individual costaba miles de consultas.

        Mismas reglas, mismo orden de prioridad y misma guarda L1-sobre-L2 que la individual.
        """
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio
        from turnos.models import DiaEspecial
        from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService

        if isinstance(ini, str):
            ini = date.fromisoformat(ini)
        if isinstance(fin, str):
            fin = date.fromisoformat(fin)

        emp_by_id = {getattr(e, 'id', e): e for e in empleados}
        emp_ids = set(emp_by_id)
        salida = {eid: {} for eid in emp_ids}

        def _comp(emp):
            return {'id': emp.id, 'nombre': f'{emp.nombre} {emp.apellido}'}

        def _exc(qs):
            return qs.exclude(id=excluir_id) if excluir_id else qs

        def _fmt(d):
            return d.strftime('%d/%m/%Y') if d else None

        # El descanso se atribuye SOLO a la fecha realmente cedida/pagada. Antes se expandía a
        # los dos días del finde, pero la solicitud únicamente mueve el día que se cede: el otro
        # día del finde ya se descansaba por ALTERNANCIA (L6 lo resuelve con su propio motivo), y
        # si por un cambio previo se trabajaba, marcarlo como descanso era directamente falso.
        # La ventana de consulta se mantiene ±2 días (inofensivo) por si el rango corta un finde.
        def _dias_descanso(f):
            return [f]

        qini, qfin = ini - timedelta(days=2), fin + timedelta(days=2)

        # GUARDA DE REALIDAD (L1 manda sobre L2): si ese día hay un Turno REAL, el empleado
        # TRABAJA y no se reporta descanso, aunque una solicitud aprobada antigua diga que
        # cedió/le pagan ese día. Al aplicar una doblada se BORRAN los turnos de quien queda
        # libre (cedente en la cesión, acreedor en el pago), así que un turno presente solo
        # puede venir de algo aprobado DESPUÉS: la última solicitud aprobada del día es la
        # vigente. Sin esta guarda, un día ya "descansado" quedaba bloqueado para siempre —
        # p. ej. te pagan una doblada el día X (descansas) y luego tomas la jornada de otro
        # ese mismo día X como pago de otra doblada: trabajas de verdad y sí puedes cederla.
        from turnos.models import Turno as _TurnoReal
        con_turno_real = {eid: set() for eid in emp_ids}
        for _eid, _f in _TurnoReal.objects.filter(
                explorador_id__in=emp_ids, fecha__range=(ini, fin)
        ).values_list('explorador_id', 'fecha'):
            con_turno_real[_eid].add(_f)

        # Un INTERCAMBIO de dobladas es SIEMPRE día completo por los dos lados: ambos tenían
        # DOBLADA (AM+PM) y se cambian el día entero (`aplicar_intercambio` borra todos los turnos
        # del día a cada uno). Su `tipo_cesion` es ruido heredado del formulario —puede llegar como
        # parcial AM/PM— y si se lee, el día se toma por MEDIO y no se atribuye descanso: el día
        # quedaba sin fila `Turno` y sin motivo, así que `estado_dia` caía al fallback de la jornada
        # BASE y mostraba trabajando a quien tiene el día libre (arley 06/08/2026, mildrey 12/08).
        def _full(det):
            if det is None:
                return False
            return bool(getattr(det, 'es_intercambio', False))

        # ---------- DOBLADA / D FDS: el SOLICITANTE descansa en la cesión ----------
        # Día libre COMPLETO solo si cedió todo el día: cesión completa / D FDS, o AMBAS
        # medias jornadas (parciales AM y PM). Una sola parcial deja la otra jornada (L1).
        ced = {}  # (emp_id, fecha) -> {'parciales': set, 'rep': solicitud, 'full': bool}
        for s in _exc(SolicitudCambio.objects.filter(
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'], estado='aprobada',
                explorador_solicitante_id__in=emp_ids, fecha_cambio_turno__range=(qini, qfin))
                .select_related('explorador_receptor', 'doblada').order_by('-id')):
            det = getattr(s, 'doblada', None)
            tc = getattr(det, 'tipo_cesion', None) if det else None
            for d in _dias_descanso(s.fecha_cambio_turno):
                if not (ini <= d <= fin):
                    continue
                e = ced.setdefault((s.explorador_solicitante_id, d),
                                   {'parciales': set(), 'rep': s, 'full': False})
                if _full(det):
                    e['full'] = True
                elif tc == 'cesion_parcial_am':
                    e['parciales'].add('AM')
                elif tc == 'cesion_parcial_pm':
                    e['parciales'].add('PM')
                else:
                    e['full'] = True
        for (emp_id, d), e in ced.items():
            if d in con_turno_real[emp_id]:
                continue
            if e['full'] or {'AM', 'PM'} <= e['parciales']:
                s = e['rep']
                det = getattr(s, 'doblada', None)
                salida[emp_id].setdefault(d, {
                    'motivo': 'cedió su jornada', 'origen': None, 'tipo': 'cedio',
                    'companero': _comp(s.explorador_receptor), 'solicitud_id': s.id,
                    'fecha_cesion': _fmt(s.fecha_cambio_turno),
                    'fecha_pago': _fmt(det.fecha_pago) if det else None,
                    'tipo_cesion': det.get_tipo_cesion_display() if det else None,
                    'jornada_cedida': (det.jornada_cedida if det and det.jornada_cedida else None),
                    'fecha_solicitud': DateUtils.format_datetime_display(s.fecha_solicitud),
                    'fecha_aprobacion': DateUtils.format_datetime_display(s.fecha_resolucion),
                })

        # ---------- DOBLADA / D FDS: el RECEPTOR descansa en el pago ----------
        # Cuánto pierde el ACREEDOR en la fecha de pago: 'FULL' o la mitad 'AM'/'PM'.
        #
        # OJO: NO lo dice `tipo_cesion`. Ese campo describe el día de la CESIÓN (cuánto cedió el
        # deudor), no el de pago; leerlo aquí era un error de categoría. En una cesión parcial el
        # acreedor igualmente queda LIBRE EL DÍA COMPLETO en el pago —`_aplicar_pago_cesion_parcial`
        # le borra todos los turnos, porque el deudor cubre la única jornada que él trabajaba—, y
        # al marcarlo como medio día no se atribuía descanso: sin fila `Turno` y sin motivo,
        # `estado_dia` caía a la jornada BASE y lo mostraba trabajando (arley el 26/08/2026).
        #
        # El orden replica el de `DobladaPagoService.aplicar_doblada_pago`, que es quien decide:
        #   1. sábado + jornada_pago_sabado: AMBAS → día completo; AM/PM → esa mitad (conserva la otra)
        #   2. jornada_cubre_en_pago: AMBAS → día completo; AM/PM → esa mitad
        #   3. resto (cesión parcial sin jcp, cesión completa, fallback) → día completo
        # D FDS y los INTERCAMBIOS no usan esos campos: siempre liberan el día completo.
        def _mitad_pago(det, tipo):
            if det is None or tipo != 'DOBLADA' or getattr(det, 'es_intercambio', False):
                return 'FULL'
            fp = det.fecha_pago
            jps = (getattr(det, 'jornada_pago_sabado', '') or '').strip().upper()
            if fp and fp.weekday() == 5 and jps in ('AM', 'PM'):
                return jps
            jcp = (getattr(det, 'jornada_cubre_en_pago', '') or '').strip().upper()
            if jcp in ('AM', 'PM'):
                return jcp
            return 'FULL'

        pago = {}
        for s in _exc(SolicitudCambio.objects.filter(
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'], estado='aprobada',
                explorador_receptor_id__in=emp_ids, doblada__fecha_pago__range=(qini, qfin))
                .select_related('explorador_solicitante', 'doblada', 'tipo_cambio').order_by('-id')):
            det = getattr(s, 'doblada', None)
            fp = det.fecha_pago if det else None
            if not fp:
                continue
            mitad = _mitad_pago(det, s.tipo_cambio.nombre if s.tipo_cambio else '')
            for d in _dias_descanso(fp):
                if not (ini <= d <= fin):
                    continue
                e = pago.setdefault((s.explorador_receptor_id, d),
                                    {'parciales': set(), 'rep': s, 'full': False})
                if mitad == 'FULL':
                    e['full'] = True
                else:
                    e['parciales'].add(mitad)
        for (emp_id, d), e in pago.items():
            if d in con_turno_real[emp_id]:
                continue
            if e['full'] or {'AM', 'PM'} <= e['parciales']:
                s = e['rep']
                det = getattr(s, 'doblada', None)
                salida[emp_id].setdefault(d, {
                    'motivo': 'paga doblada', 'origen': None, 'tipo': 'pago',
                    'companero': _comp(s.explorador_solicitante), 'solicitud_id': s.id,
                    'fecha_cesion': _fmt(s.fecha_cambio_turno),
                    'fecha_pago': _fmt(det.fecha_pago) if det else None,
                    'tipo_cesion': det.get_tipo_cesion_display() if det else None,
                    'jornada_cedida': (det.jornada_cedida if det and det.jornada_cedida else None),
                    'fecha_solicitud': DateUtils.format_datetime_display(s.fecha_solicitud),
                    'fecha_aprobacion': DateUtils.format_datetime_display(s.fecha_resolucion),
                })

        # ---------- Pago en sábado AMBAS: el SOLICITANTE descansa el día de la devolución ----------
        # `fecha_pago_semana` es un TERCER día que muta la doblada: el receptor dobla y el
        # solicitante descansa la jornada que le devuelven (`aplicar_pago_residual_semana`). Entre
        # semana esa es su única jornada, así que queda libre el día completo. No lo cubría ninguna
        # de las dos ramas de arriba (que solo miran fecha de cesión y fecha de pago), así que era
        # otro día sin fila `Turno` y sin motivo → `estado_dia` volvía a caer a la jornada base.
        for s in _exc(SolicitudCambio.objects.filter(
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'], estado='aprobada',
                explorador_solicitante_id__in=emp_ids,
                doblada__fecha_pago_semana__range=(qini, qfin))
                .select_related('explorador_receptor', 'doblada').order_by('-id')):
            det = getattr(s, 'doblada', None)
            fps = getattr(det, 'fecha_pago_semana', None) if det else None
            emp_id = s.explorador_solicitante_id
            if not fps or not (ini <= fps <= fin) or fps in con_turno_real[emp_id]:
                continue
            salida[emp_id].setdefault(fps, {
                # Misma forma que un pago normal: a esta persona le devuelven la jornada.
                'motivo': 'paga doblada', 'origen': None, 'tipo': 'pago',
                'companero': _comp(s.explorador_receptor), 'solicitud_id': s.id,
                'fecha_cesion': _fmt(s.fecha_cambio_turno),
                'fecha_pago': _fmt(fps),
                'tipo_cesion': det.get_tipo_cesion_display() if det else None,
                'jornada_cedida': (det.jornada_cedida if det and det.jornada_cedida else None),
                'fecha_solicitud': DateUtils.format_datetime_display(s.fecha_solicitud),
                'fecha_aprobacion': DateUtils.format_datetime_display(s.fecha_resolucion),
            })

        # ---------- CAMBIO DESCANSO (intercambio de día): fuente de verdad ----------
        # Una sola pasada para todo el lote: el mapa ya trae fecha → compañero por empleado.
        mapa_cd = CambioDescansoAplicacionService._mapa_descanso_multi(
            list(emp_by_id.values()), ini, fin, excluir_id=excluir_id)
        for emp_id, por_fecha in mapa_cd.items():
            for dcd, comp in por_fecha.items():
                if not (ini <= dcd <= fin):
                    continue
                # MISMA guarda L1 que las demás ramas (Patrón #28). Antes CAMBIO DESCANSO estaba
                # exento "porque tiene su propia fuente de verdad", pero esa fuente
                # (`_mapa_descanso_multi`) tampoco mira los turnos reales, así que nadie cubría el
                # caso: un intercambio viejo seguía diciendo "descansa" un día en el que la persona
                # había recuperado jornada real por algo aprobado DESPUÉS. Las pantallas no lo
                # notaban (todas resuelven L1 primero), pero `dia_comprometido_por_solicitud` sí:
                # alimenta 8 validaciones y producía falsos bloqueos ("ya tienes ese día
                # comprometido") sobre días que la persona trabaja de verdad.
                if dcd in con_turno_real[emp_id]:
                    continue
                salida[emp_id].setdefault(dcd, {
                    'motivo': 'cambio de día de descanso', 'origen': 'cambio_descanso', 'tipo': 'cedio',
                    'companero': comp, 'solicitud_id': None,
                    'fecha_cesion': None, 'fecha_pago': None,
                    'tipo_cesion': None, 'jornada_cedida': None,
                })

        # ---------- DOBLADA PERMANENTE (recurrente; nunca domingo ni festivo) ----------
        # El compromiso se decide EXACTAMENTE como se aplicó: si el detalle trae FECHAS
        # específicas, solo en ESAS fechas; si no (legacy), por patrón de día de la semana.
        # Guarda: si ese día hay un Turno REAL (el empleado trabaja de verdad, p. ej. una
        # doblada), la realidad manda sobre el patrón recurrente y NO se reporta descanso.
        festivos = set(DiaEspecial.objects.filter(
            fecha__range=(ini, fin), tipo='festivo', activo=True).values_list('fecha', flat=True))
        for sp in _exc(SolicitudCambio.objects
                       .filter(tipo_cambio__nombre='DOBLADA PERMANENTE', estado='aprobada')
                       .filter(Q(explorador_solicitante_id__in=emp_ids) | Q(explorador_receptor_id__in=emp_ids))
                       .select_related('doblada_permanente', 'explorador_solicitante', 'explorador_receptor')):
            det = getattr(sp, 'doblada_permanente', None)
            if not det:
                continue
            # Los dos lados por separado: el solicitante descansa en sus fechas de cesión y el
            # receptor en las de devolución. En batch ambos pueden estar en el lote.
            for es_sol in (True, False):
                emp_id = sp.explorador_solicitante_id if es_sol else sp.explorador_receptor_id
                if emp_id not in emp_ids:
                    continue
                companero = sp.explorador_receptor if es_sol else sp.explorador_solicitante
                info = {
                    'motivo': 'doblada permanente', 'origen': None,
                    'tipo': 'cedio' if es_sol else 'pago',
                    'companero': _comp(companero), 'solicitud_id': sp.id,
                    'fecha_cesion': None, 'fecha_pago': None,
                    'tipo_cesion': None, 'jornada_cedida': None,
                }

                def _marca(d, _emp_id=emp_id, _info=info):
                    if (ini <= d <= fin and det.fecha_inicio <= d <= det.fecha_fin
                            and d.weekday() != 6 and d not in festivos
                            and d not in con_turno_real[_emp_id]):
                        salida[_emp_id].setdefault(d, _info)

                usa_fechas = bool(det.fechas_cesion or det.fechas_devolucion)
                if usa_fechas:
                    fechas_txt = det.fechas_cesion if es_sol else det.fechas_devolucion
                    for x in (fechas_txt or '').split(','):
                        x = x.strip()
                        if not x:
                            continue
                        try:
                            _marca(date.fromisoformat(x))
                        except ValueError:
                            continue
                else:
                    dias_set = {int(x) for x in ((det.dias_cesion if es_sol else det.dias_devolucion) or '').split(',')
                                if x.strip().isdigit()}
                    if not dias_set:
                        continue
                    d = max(det.fecha_inicio, ini)
                    dlast = min(det.fecha_fin, fin)
                    while d <= dlast:
                        if d.weekday() in dias_set:
                            _marca(d)
                        d += timedelta(days=1)

        return salida

    @staticmethod
    def en_fecha(empleado, fecha, excluir_id=None):
        """Atajo de conveniencia: la atribución de descanso de UN día (o None)."""
        if isinstance(fecha, str):
            fecha = date.fromisoformat(fecha)
        return DescansoPorSolicitudService.en_rango(empleado, fecha, fecha, excluir_id=excluir_id).get(fecha)
