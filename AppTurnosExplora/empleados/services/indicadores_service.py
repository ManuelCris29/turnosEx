"""
Servicio de Indicadores (KPIs) para supervisores.

Agrega solicitudes de cambio de turno y permisos por mes/año, por categoría,
con filtros por explorador y jornada predeterminada (AM/PM).

Categorías (alineadas con el tablero del área):
- Cambios de turno  : CAMBIO TURNO + CT PERMANENTE
- Dobladas          : DOBLADA + DOBLADA PERMANENTE
- Cambio descanso   : CAMBIO DESCANSO (fin de semana y entre semana)
- Doblada finde     : D FDS
- Permisos especiales: PermisoEspecial
"""
import calendar
from datetime import date, timedelta

from django.utils import timezone

CATEGORIAS = ['cambios_turno', 'dobladas', 'cambio_descanso', 'doblada_finde', 'permisos']
LABELS = {
    'cambios_turno': 'Cambios de turno',
    'dobladas': 'Dobladas',
    'cambio_descanso': 'Cambio descanso',
    'doblada_finde': 'Doblada finde',
    'permisos': 'Permisos especiales',
}
COLORES = {
    'cambios_turno': '#3b82f6',
    'dobladas': '#ef4444',
    'cambio_descanso': '#22c55e',
    'doblada_finde': '#a855f7',
    'permisos': '#06b6d4',
}
TIPO_A_CATEGORIA = {
    'CAMBIO TURNO': 'cambios_turno', 'CT': 'cambios_turno', 'CT PERMANENTE': 'cambios_turno',
    'DOBLADA': 'dobladas', 'DOBLADA PERMANENTE': 'dobladas',
    'D FDS': 'doblada_finde',
    'CAMBIO DESCANSO': 'cambio_descanso',
}
MESES_NOMBRES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']


class IndicadoresService:

    @staticmethod
    def _jornadas_base():
        """Mapa empleado_id -> jornada base (AM/PM)."""
        from turnos.models import AsignarJornadaExplorador
        m = {}
        for a in (AsignarJornadaExplorador.objects
                  .select_related('jornada').order_by('explorador_id', '-fecha_inicio')):
            m.setdefault(a.explorador_id, a.jornada.nombre.upper())
        return m

    @staticmethod
    def anios_disponibles():
        from permisos.models import PermisoEspecial
        from solicitudes.models import SolicitudCambio
        anios = set()
        for y in SolicitudCambio.objects.filter(fecha_cambio_turno__isnull=False) \
                .dates('fecha_cambio_turno', 'year'):
            anios.add(y.year)
        for y in PermisoEspecial.objects.dates('fecha_inicio', 'year'):
            anios.add(y.year)
        anios.add(timezone.localdate().year)
        return sorted(anios, reverse=True)

    @staticmethod
    def _dias_transcurridos(anio):
        hoy = timezone.localdate()
        if anio == hoy.year:
            return hoy.timetuple().tm_yday  # día del año actual
        dias = 366 if calendar.isleap(anio) else 365
        return dias

    @staticmethod
    def _ocurrencias_doblada_perm(solicitud, anio, hasta):
        """Fechas reales de doblada de una doblada permanente dentro del año (cesión + devolución)."""
        from solicitudes.services.ct_permanente_helper import es_festivo
        from turnos.models import DiaEspecial
        det = getattr(solicitud, 'doblada_permanente', None)
        if not det:
            return []
        dias = set()
        for campo in (det.dias_cesion, det.dias_devolucion):
            dias |= {int(x) for x in (campo or '').split(',') if x.strip().isdigit()}
        if not dias:
            return []
        res = []
        d = max(det.fecha_inicio, date(anio, 1, 1))
        fin = min(det.fecha_fin, date(anio, 12, 31), hasta)
        while d <= fin:
            if (d.weekday() in dias and d.weekday() != 6
                    and not es_festivo(d)
                    and not DiaEspecial.es_mantenimiento_efectivo(d)):
                res.append(d)
            d += timedelta(days=1)
        return res

    @staticmethod
    def _ocurrencias_ct_perm(solicitud, anio, hasta):
        """Fechas reales de cambio de un CT permanente dentro del año (lun-vie, sin festivos)."""
        from solicitudes.services.ct_permanente_helper import es_festivo
        det = getattr(solicitud, 'cambio_permanente', None)
        if not det:
            return []
        dias_obj = list(det.dias.all())
        fechas_esp = [x.fecha_especifica for x in dias_obj
                      if x.tipo == 'fecha_especifica' and x.fecha_especifica]
        dias_sem = {x.dia_semana for x in dias_obj
                    if x.tipo == 'dia_semana' and x.dia_semana is not None}
        res = []
        if fechas_esp:
            for f in fechas_esp:
                if f.year == anio and f <= hasta and f.weekday() < 5 and not es_festivo(f):
                    res.append(f)
        else:
            d = max(det.fecha_inicio, date(anio, 1, 1))
            fin = min(det.fecha_fin or date(anio, 12, 31), date(anio, 12, 31), hasta)
            while d <= fin:
                if d.weekday() < 5 and (not dias_sem or d.weekday() in dias_sem) and not es_festivo(d):
                    res.append(d)
                d += timedelta(days=1)
        return res

    @staticmethod
    def get(explorador_id=None, jornada=None, anio=None, incluir_receptor=False):
        from permisos.models import PermisoEspecial
        from solicitudes.models import SolicitudCambio

        anio = anio or timezone.localdate().year
        jbase = IndicadoresService._jornadas_base()
        jornada = (jornada or '').upper() or None

        def pasa_jornada(emp_id):
            return (not jornada) or (jbase.get(emp_id) == jornada)

        meses = {m: {c: 0 for c in CATEGORIAS} for m in range(1, 13)}

        from django.db.models import Q as _Q

        # Filtro por explorador. Para la vista personal (incluir_receptor=True) se
        # cuenta toda su participación: solicitante O receptor (permisos: empleado O
        # quien cubre). Para el supervisor (default) se mantiene solo solicitante.
        def filtro_sol(eid):
            return (_Q(explorador_solicitante_id=eid) | _Q(explorador_receptor_id=eid)) if incluir_receptor \
                else _Q(explorador_solicitante_id=eid)

        def filtro_perm(eid):
            return (_Q(empleado_id=eid) | _Q(cubre_id=eid)) if incluir_receptor \
                else _Q(empleado_id=eid)

        hoy = timezone.localdate()
        hasta = hoy if anio == hoy.year else date(anio, 12, 31)
        ene1, dic31 = date(anio, 1, 1), date(anio, 12, 31)

        # --- Cambios NO permanentes (1 por solicitud, en el mes de fecha_cambio_turno) ---
        sol_np = (SolicitudCambio.objects
                  .filter(estado='aprobada', fecha_cambio_turno__year=anio)
                  .exclude(tipo_cambio__nombre__in=['DOBLADA PERMANENTE', 'CT PERMANENTE'])
                  .select_related('tipo_cambio'))
        if explorador_id:
            sol_np = sol_np.filter(filtro_sol(explorador_id))
        for s in sol_np.values('tipo_cambio__nombre', 'fecha_cambio_turno', 'explorador_solicitante_id'):
            if not pasa_jornada(s['explorador_solicitante_id']):
                continue
            cat = TIPO_A_CATEGORIA.get((s['tipo_cambio__nombre'] or '').upper())
            if cat and s['fecha_cambio_turno']:
                meses[s['fecha_cambio_turno'].month][cat] += 1

        # --- Permanentes: querysets base (rango que toca el año) ---
        dp_all = (SolicitudCambio.objects
                  .filter(estado='aprobada', tipo_cambio__nombre='DOBLADA PERMANENTE',
                          doblada_permanente__fecha_inicio__lte=dic31,
                          doblada_permanente__fecha_fin__gte=ene1)
                  .select_related('doblada_permanente'))
        cp_all = (SolicitudCambio.objects
                  .filter(estado='aprobada', tipo_cambio__nombre='CT PERMANENTE',
                          cambio_permanente__fecha_inicio__lte=dic31)
                  .filter(_Q(cambio_permanente__fecha_fin__gte=ene1) | _Q(cambio_permanente__fecha_fin__isnull=True))
                  .select_related('cambio_permanente').prefetch_related('cambio_permanente__dias'))

        # --- Doblada permanente: ocurrencias reales (cesión + devolución) en el mes que toque ---
        dp = dp_all.filter(filtro_sol(explorador_id)) if explorador_id else dp_all
        for s in dp:
            if not pasa_jornada(s.explorador_solicitante_id):
                continue
            for occ in IndicadoresService._ocurrencias_doblada_perm(s, anio, hasta):
                meses[occ.month]['dobladas'] += 1

        # --- CT permanente: ocurrencias reales ---
        cp = cp_all.filter(filtro_sol(explorador_id)) if explorador_id else cp_all
        for s in cp:
            if not pasa_jornada(s.explorador_solicitante_id):
                continue
            for occ in IndicadoresService._ocurrencias_ct_perm(s, anio, hasta):
                meses[occ.month]['cambios_turno'] += 1

        # --- Permisos APROBADOS ---
        pe_aprob = PermisoEspecial.objects.filter(estado='APROBADO', fecha_inicio__year=anio)
        if explorador_id:
            pe_aprob = pe_aprob.filter(filtro_perm(explorador_id))
        for p in pe_aprob.values('fecha_inicio', 'empleado_id'):
            if not pasa_jornada(p['empleado_id']):
                continue
            meses[p['fecha_inicio'].month]['permisos'] += 1

        # --- Totales por categoría / mes / general (ocurrencias reales) ---
        totales_categoria = {c: sum(meses[m][c] for m in range(1, 13)) for c in CATEGORIAS}
        total_general = sum(totales_categoria.values())
        filas_mes = []
        for m in range(1, 13):
            fila = {'mes': MESES_NOMBRES[m - 1], **meses[m], 'total': sum(meses[m].values())}
            filas_mes.append(fila)

        porcentajes = {
            c: round(100 * totales_categoria[c] / total_general, 1) if total_general else 0
            for c in CATEGORIAS
        }

        # --- Conteo a nivel SOLICITUD (para % aprobación y solicitudes/día) ---
        sol_todas = SolicitudCambio.objects.filter(fecha_cambio_turno__year=anio)
        pe_todas = PermisoEspecial.objects.filter(fecha_inicio__year=anio)
        if explorador_id:
            sol_todas = sol_todas.filter(filtro_sol(explorador_id))
            pe_todas = pe_todas.filter(filtro_perm(explorador_id))
        if jornada:
            ids_j = [eid for eid, j in jbase.items() if j == jornada]
            sol_todas = sol_todas.filter(explorador_solicitante_id__in=ids_j)
            pe_todas = pe_todas.filter(empleado_id__in=ids_j)
        total_solicitudes = sol_todas.count() + pe_todas.count()
        total_aprobadas_sol = (sol_todas.filter(estado='aprobada').count()
                               + pe_todas.filter(estado='APROBADO').count())

        # --- Por explorador: Solicita (solicitante) vs Reemplaza (receptor), por ocurrencias ---
        from empleados.models import Empleado
        counters = {}

        def bump(eid, cat, rol, n=1):
            if eid is None or n == 0:
                return
            d = counters.setdefault(eid, {f'{c}_{r}': 0 for c in CATEGORIAS for r in ('sol', 'reemp')})
            d[f'{cat}_{rol}'] += n

        for s in (SolicitudCambio.objects
                  .filter(estado='aprobada', fecha_cambio_turno__year=anio)
                  .exclude(tipo_cambio__nombre__in=['DOBLADA PERMANENTE', 'CT PERMANENTE'])
                  .values('tipo_cambio__nombre', 'explorador_solicitante_id', 'explorador_receptor_id')):
            cat = TIPO_A_CATEGORIA.get((s['tipo_cambio__nombre'] or '').upper())
            if not cat:
                continue
            bump(s['explorador_solicitante_id'], cat, 'sol')
            bump(s['explorador_receptor_id'], cat, 'reemp')
        for s in dp_all:
            n = len(IndicadoresService._ocurrencias_doblada_perm(s, anio, hasta))
            bump(s.explorador_solicitante_id, 'dobladas', 'sol', n)
            bump(s.explorador_receptor_id, 'dobladas', 'reemp', n)
        for s in cp_all:
            n = len(IndicadoresService._ocurrencias_ct_perm(s, anio, hasta))
            bump(s.explorador_solicitante_id, 'cambios_turno', 'sol', n)
            bump(s.explorador_receptor_id, 'cambios_turno', 'reemp', n)
        for p in (PermisoEspecial.objects.filter(estado='APROBADO', fecha_inicio__year=anio)
                  .values('empleado_id', 'cubre_id')):
            bump(p['empleado_id'], 'permisos', 'sol')
            bump(p['cubre_id'], 'permisos', 'reemp')

        emp_map = Empleado.objects.in_bulk(list(counters.keys()))
        por_explorador = []
        for eid, d in counters.items():
            emp = emp_map.get(eid)
            if not emp:
                continue
            jb = jbase.get(eid, '')
            if jornada and jb != jornada:
                continue
            if explorador_id and str(eid) != str(explorador_id):
                continue
            total = sum(d.values())
            if total == 0:
                continue
            celdas = [{'sol': d[f'{c}_sol'], 'reemp': d[f'{c}_reemp']} for c in CATEGORIAS]
            por_explorador.append({
                'nombre': f'{emp.nombre} {emp.apellido}',
                'jornada': jb, 'total': total, 'celdas': celdas,
            })
        por_explorador.sort(key=lambda x: x['total'], reverse=True)

        dias = IndicadoresService._dias_transcurridos(anio) or 1
        kpis = {
            'total_aprobados': total_general,
            'total_solicitudes': total_solicitudes,
            'pct_aprobacion': round(100 * total_aprobadas_sol / total_solicitudes, 1) if total_solicitudes else 0,
            'cambios_por_dia': round(total_general / dias, 1),
            'solicitudes_por_dia': round(total_solicitudes / dias, 1),
            'dias': dias,
        }

        return {
            'anio': anio,
            'categorias': CATEGORIAS,
            'labels': LABELS,
            'colores': COLORES,
            'meses_nombres': MESES_NOMBRES,
            'filas_mes': filas_mes,
            'totales_categoria': totales_categoria,
            'total_general': total_general,
            'porcentajes': porcentajes,
            'categorias_resumen': [
                {'key': c, 'label': LABELS[c], 'color': COLORES[c],
                 'total': totales_categoria[c], 'pct': porcentajes[c]}
                for c in CATEGORIAS
            ],
            'por_explorador': por_explorador,
            'kpis': kpis,
            # Series para Chart.js (una por categoría)
            'chart_series': [
                {'label': LABELS[c], 'color': COLORES[c], 'data': [meses[m][c] for m in range(1, 13)]}
                for c in CATEGORIAS
            ],
        }
