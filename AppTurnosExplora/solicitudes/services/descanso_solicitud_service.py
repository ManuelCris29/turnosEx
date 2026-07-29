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
        from django.db.models import Q
        from solicitudes.models import SolicitudCambio
        from turnos.models import DiaEspecial
        from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService

        if isinstance(ini, str):
            ini = date.fromisoformat(ini)
        if isinstance(fin, str):
            fin = date.fromisoformat(fin)

        out = {}

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

        # ---------- DOBLADA / D FDS: el SOLICITANTE descansa en la cesión ----------
        # Día libre COMPLETO solo si cedió todo el día: cesión completa / D FDS, o AMBAS
        # medias jornadas (parciales AM y PM). Una sola parcial deja la otra jornada (L1).
        ced = {}  # fecha -> {'parciales': set, 'rep': solicitud, 'full': bool}
        for s in _exc(SolicitudCambio.objects.filter(
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'], estado='aprobada',
                explorador_solicitante=empleado, fecha_cambio_turno__range=(qini, qfin))
                .select_related('explorador_receptor', 'doblada').order_by('-id')):
            det = getattr(s, 'doblada', None)
            tc = getattr(det, 'tipo_cesion', None) if det else None
            for d in _dias_descanso(s.fecha_cambio_turno):
                if not (ini <= d <= fin):
                    continue
                e = ced.setdefault(d, {'parciales': set(), 'rep': s, 'full': False})
                if tc == 'cesion_parcial_am':
                    e['parciales'].add('AM')
                elif tc == 'cesion_parcial_pm':
                    e['parciales'].add('PM')
                else:
                    e['full'] = True
        for d, e in ced.items():
            if e['full'] or {'AM', 'PM'} <= e['parciales']:
                s = e['rep']
                det = getattr(s, 'doblada', None)
                out.setdefault(d, {
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
        pago = {}
        for s in _exc(SolicitudCambio.objects.filter(
                tipo_cambio__nombre__in=['DOBLADA', 'D FDS'], estado='aprobada',
                explorador_receptor=empleado, doblada__fecha_pago__range=(qini, qfin))
                .select_related('explorador_solicitante', 'doblada').order_by('-id')):
            det = getattr(s, 'doblada', None)
            fp = det.fecha_pago if det else None
            if not fp:
                continue
            tc = det.tipo_cesion if det else None
            for d in _dias_descanso(fp):
                if not (ini <= d <= fin):
                    continue
                e = pago.setdefault(d, {'parciales': set(), 'rep': s, 'full': False})
                if tc == 'cesion_parcial_am':
                    e['parciales'].add('AM')
                elif tc == 'cesion_parcial_pm':
                    e['parciales'].add('PM')
                else:
                    e['full'] = True
        for d, e in pago.items():
            if e['full'] or {'AM', 'PM'} <= e['parciales']:
                s = e['rep']
                det = getattr(s, 'doblada', None)
                out.setdefault(d, {
                    'motivo': 'paga doblada', 'origen': None, 'tipo': 'pago',
                    'companero': _comp(s.explorador_solicitante), 'solicitud_id': s.id,
                    'fecha_cesion': _fmt(s.fecha_cambio_turno),
                    'fecha_pago': _fmt(det.fecha_pago) if det else None,
                    'tipo_cesion': det.get_tipo_cesion_display() if det else None,
                    'jornada_cedida': (det.jornada_cedida if det and det.jornada_cedida else None),
                    'fecha_solicitud': DateUtils.format_datetime_display(s.fecha_solicitud),
                    'fecha_aprobacion': DateUtils.format_datetime_display(s.fecha_resolucion),
                })

        # ---------- CAMBIO DESCANSO (intercambio de día): fuente de verdad ----------
        for dcd in CambioDescansoAplicacionService.dias_en_descanso(empleado, ini, fin, excluir_id=excluir_id):
            if not (ini <= dcd <= fin):
                continue
            comp = CambioDescansoAplicacionService.companero_descanso(empleado, dcd, excluir_id=excluir_id)
            out.setdefault(dcd, {
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
        from turnos.models import Turno as _Turno
        con_turno_real = set(_Turno.objects.filter(
            explorador=empleado, fecha__range=(ini, fin)).values_list('fecha', flat=True))
        festivos = set(DiaEspecial.objects.filter(
            fecha__range=(ini, fin), tipo='festivo', activo=True).values_list('fecha', flat=True))
        for sp in _exc(SolicitudCambio.objects
                       .filter(tipo_cambio__nombre='DOBLADA PERMANENTE', estado='aprobada')
                       .filter(Q(explorador_solicitante=empleado) | Q(explorador_receptor=empleado))
                       .select_related('doblada_permanente', 'explorador_solicitante', 'explorador_receptor')):
            det = getattr(sp, 'doblada_permanente', None)
            if not det:
                continue
            es_sol = sp.explorador_solicitante_id == empleado.id
            companero = sp.explorador_receptor if es_sol else sp.explorador_solicitante
            info = {
                'motivo': 'doblada permanente', 'origen': None,
                'tipo': 'cedio' if es_sol else 'pago',
                'companero': _comp(companero), 'solicitud_id': sp.id,
                'fecha_cesion': None, 'fecha_pago': None,
                'tipo_cesion': None, 'jornada_cedida': None,
            }

            def _marca(d):
                if (ini <= d <= fin and det.fecha_inicio <= d <= det.fecha_fin
                        and d.weekday() != 6 and d not in festivos and d not in con_turno_real):
                    out.setdefault(d, info)

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

        return out

    @staticmethod
    def en_fecha(empleado, fecha, excluir_id=None):
        """Atajo de conveniencia: la atribución de descanso de UN día (o None)."""
        if isinstance(fecha, str):
            fecha = date.fromisoformat(fecha)
        return DescansoPorSolicitudService.en_rango(empleado, fecha, fecha, excluir_id=excluir_id).get(fecha)
