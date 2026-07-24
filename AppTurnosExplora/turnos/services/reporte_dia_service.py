"""
ReporteDiaService

Genera el reporte operacional de un día para supervisores: quién trabaja
(AM/PM/DOBLADA), quién descansa y por qué, quién tiene permiso especial.

Usa las mismas capas de prioridad que TurnoService.estado_mes pero en batch
para TODOS los empleados activos en una sola pasada (~10 queries totales).
"""
import logging
from datetime import date as _date
from django.db.models import Q
from empleados.models import Empleado
from turnos.models import Turno, AsignarJornadaExplorador, DiaEspecial, DescansoSemanaManual
from solicitudes.models import SolicitudCambio

logger = logging.getLogger(__name__)


def _nombre(emp):
    return {'id': emp.id, 'nombre': f'{emp.nombre} {emp.apellido}'}


class ReporteDiaService:

    @staticmethod
    def reporte(fecha: _date) -> dict:
        """
        Devuelve el estado de todos los empleados activos para `fecha`.

        Estructura de retorno:
        {
          'trabajando': [
            {id, nombre, apellido, jornada_base, jornada_dia,
             tipo,          # 'oficial' | 'cambio' | 'doblada'
             cubre_a,       # None | {id, nombre}  (cuando dobló por alguien)
             permiso,       # None | {horas, tipo, especificacion, estado}
             restriccion,   # None | {tipo, recomendacion, fecha_fin}
             sancion,       # None | {motivo, fecha_inicio, fecha_fin}
             deuda_reprogramacion}  # None | {fecha_original, jornada_debida,
                            #   fecha_reprogramada, motivo, estado, paga_hoy}
          ],
          'descansando': [
            {id, nombre, apellido, jornada_base,
             motivo,        # texto legible
             companero,     # None | {id, nombre}
             permiso, restriccion, sancion, deuda_reprogramacion}  # (idem)
          ],
          'dia_info': {
            'es_festivo', 'es_finde', 'es_mantenimiento',
            'grupo_dobla_festivo'
          }
        }

        Las fechas dentro de restriccion/sancion/deuda_reprogramacion son
        strings ISO (YYYY-MM-DD) o None.
        """
        anio, mes = fecha.year, fecha.month

        # ── Empleados activos ────────────────────────────────────────────────
        empleados = list(
            Empleado.objects.filter(activo=True)
            .select_related('supervisor')
            .order_by('apellido', 'nombre')
        )
        emp_ids = [e.id for e in empleados]

        # ── Jornada base más reciente por empleado ───────────────────────────
        jornada_base_por_emp = {}
        for asg in (AsignarJornadaExplorador.objects
                    .filter(explorador_id__in=emp_ids, fecha_inicio__lte=fecha)
                    .select_related('jornada', 'explorador')
                    .order_by('explorador_id', '-fecha_inicio')):
            if asg.explorador_id not in jornada_base_por_emp:
                jornada_base_por_emp[asg.explorador_id] = asg.jornada.nombre.upper()

        # ── Turnos del día ───────────────────────────────────────────────────
        turnos_por_emp = {}
        for t in (Turno.objects
                  .filter(explorador_id__in=emp_ids, fecha=fecha)
                  .select_related('jornada', 'explorador')):
            turnos_por_emp.setdefault(t.explorador_id, []).append(t)

        # ── Festivo ──────────────────────────────────────────────────────────
        es_festivo = DiaEspecial.es_festivo(fecha)
        es_finde = fecha.weekday() in (5, 6)
        es_mantenimiento = (not es_festivo and not es_finde
                            and DiaEspecial.es_mantenimiento_efectivo(fecha))

        grupo_dobla_festivo = None
        if es_festivo and fecha.weekday() < 5:
            try:
                from turnos.services.festivos_rotacion_service import FestivosRotacionService
                grupo_dobla_festivo = FestivosRotacionService.get_grupo_que_dobla_en_festivo(fecha)
                if grupo_dobla_festivo:
                    grupo_dobla_festivo = grupo_dobla_festivo.upper()
            except Exception:
                logger.warning("Error obteniendo grupo que dobla en festivo (fecha=%s)", fecha, exc_info=True)

        # ── Grupo que trabaja el fin de semana ───────────────────────────────
        grupo_trabaja_finde = None
        if es_finde:
            try:
                from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
                grupo_trabaja_finde = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha)
                if grupo_trabaja_finde:
                    grupo_trabaja_finde = grupo_trabaja_finde.upper()
            except Exception:
                logger.warning("Error obteniendo grupo que trabaja el fin de semana (fecha=%s)", fecha, exc_info=True)

        # ── Descanso de semana manual (temporada) por jornada ───────────────
        jornadas_descanso_temporada = set()
        for dsm in DescansoSemanaManual.objects.filter(
                fecha=fecha, activo=True).select_related('jornada'):
            jornadas_descanso_temporada.add(dsm.jornada.nombre.upper())

        # ── Solicitudes que afectan esta fecha ───────────────────────────────
        # Quién DESCANSA por haber cedido (DOBLADA / D FDS — solicitante).
        # Solo descansa el día COMPLETO si cedió todo: cesión completa / D FDS, o AMBAS
        # medias jornadas por parciales. Una sola cesión parcial deja la otra jornada
        # (se muestra por su Turno real). Se acumula por empleado para distinguirlo.
        _ced_acc = {}   # emp_id → {'parciales': set(), 'rep': solicitud, 'full': bool}
        for s in (SolicitudCambio.objects
                  .filter(tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                          estado='aprobada', fecha_cambio_turno=fecha,
                          explorador_solicitante_id__in=emp_ids)
                  .select_related('explorador_solicitante', 'explorador_receptor', 'doblada')):
            _det = getattr(s, 'doblada', None)
            _tc = getattr(_det, 'tipo_cesion', None) if _det else None
            e = _ced_acc.setdefault(s.explorador_solicitante_id,
                                    {'parciales': set(), 'rep': s, 'full': False})
            if _tc == 'cesion_parcial_am':
                e['parciales'].add('AM')
            elif _tc == 'cesion_parcial_pm':
                e['parciales'].add('PM')
            else:
                e['full'] = True
        descansa_por_cesion = {}   # emp_id → {motivo, companero}
        for emp_id, e in _ced_acc.items():
            if e['full'] or {'AM', 'PM'} <= e['parciales']:
                descansa_por_cesion[emp_id] = {
                    'motivo': 'cedió su jornada',
                    'companero': _nombre(e['rep'].explorador_receptor),
                }

        # Quién DESCANSA por pagar doblada (receptor, en fecha_pago). Solo descansa el día
        # COMPLETO si el pago cubre todo: cesión completa / D FDS, o ambas medias jornadas.
        # Un solo pago parcial deja media jornada (se ve por su Turno real).
        _pago_acc = {}   # emp_id → {'parciales': set(), 'rep': solicitud, 'full': bool}
        for s in (SolicitudCambio.objects
                  .filter(tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                          estado='aprobada', explorador_receptor_id__in=emp_ids,
                          doblada__fecha_pago=fecha)
                  .select_related('explorador_solicitante', 'explorador_receptor', 'doblada')):
            _det = getattr(s, 'doblada', None)
            _tc = getattr(_det, 'tipo_cesion', None) if _det else None
            e = _pago_acc.setdefault(s.explorador_receptor_id,
                                     {'parciales': set(), 'rep': s, 'full': False})
            if _tc == 'cesion_parcial_am':
                e['parciales'].add('AM')
            elif _tc == 'cesion_parcial_pm':
                e['parciales'].add('PM')
            else:
                e['full'] = True
        descansa_por_pago = {}   # emp_id → {motivo, companero}
        for emp_id, e in _pago_acc.items():
            if e['full'] or {'AM', 'PM'} <= e['parciales']:
                descansa_por_pago[emp_id] = {
                    'motivo': 'paga doblada',
                    'companero': _nombre(e['rep'].explorador_solicitante),
                }

        # Quién DOBLÓ (receptor en fecha_cambio_turno) → para mostrar "cubre a X"
        dobla_cubre = {}   # emp_id (receptor) → {id, nombre} del cedente
        for s in (SolicitudCambio.objects
                  .filter(tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                          estado='aprobada', fecha_cambio_turno=fecha,
                          explorador_receptor_id__in=emp_ids)
                  .select_related('explorador_solicitante', 'explorador_receptor')):
            dobla_cubre[s.explorador_receptor_id] = _nombre(s.explorador_solicitante)

        # Quién DESCANSA por CAMBIO DESCANSO
        descansa_por_cd = {}   # emp_id → {motivo, companero}
        try:
            from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService
            from datetime import timedelta
            for s in (SolicitudCambio.objects
                      .filter(tipo_cambio__nombre='CAMBIO DESCANSO', estado='aprobada')
                      .filter(Q(explorador_solicitante_id__in=emp_ids) |
                              Q(explorador_receptor_id__in=emp_ids))
                      .select_related('explorador_solicitante', 'explorador_receptor', 'doblada')):
                det = getattr(s, 'doblada', None)
                fc = s.fecha_cambio_turno
                fp = det.fecha_pago if det else None
                es_finde_cd = fc and fc.weekday() in (5, 6)
                if es_finde_cd:
                    # Solicitante descansa fc y fp; receptor descansa los contrarios
                    def _otro(f):
                        if not f:
                            return None
                        return f + timedelta(days=1) if f.weekday() == 5 else f - timedelta(days=1)
                    days_sol = [fc, fp]
                    days_rec = [_otro(fc), _otro(fp)]
                else:
                    days_sol = [fp]
                    days_rec = [fc]
                comp_sol = _nombre(s.explorador_receptor)
                comp_rec = _nombre(s.explorador_solicitante)
                if fecha in [d for d in days_sol if d]:
                    descansa_por_cd[s.explorador_solicitante_id] = {
                        'motivo': 'cambio de día de descanso', 'companero': comp_sol}
                if fecha in [d for d in days_rec if d]:
                    descansa_por_cd[s.explorador_receptor_id] = {
                        'motivo': 'cambio de día de descanso', 'companero': comp_rec}
        except Exception:
            logger.warning("Error resolviendo descansos por cambio de descanso (fecha=%s)", fecha, exc_info=True)

        # Quién DESCANSA por DOBLADA PERMANENTE
        descansa_por_perm = {}   # emp_id → {motivo, companero}
        for s in (SolicitudCambio.objects
                  .filter(tipo_cambio__nombre='DOBLADA PERMANENTE', estado='aprobada')
                  .filter(Q(explorador_solicitante_id__in=emp_ids) |
                          Q(explorador_receptor_id__in=emp_ids))
                  .select_related('doblada_permanente',
                                  'explorador_solicitante', 'explorador_receptor')):
            det = getattr(s, 'doblada_permanente', None)
            if not det or not (det.fecha_inicio <= fecha <= det.fecha_fin):
                continue
            for es_sol in (True, False):
                emp_id = s.explorador_solicitante_id if es_sol else s.explorador_receptor_id
                if emp_id not in emp_ids:
                    continue
                dias_txt = det.dias_cesion if es_sol else det.dias_devolucion
                dias_set = {int(x) for x in (dias_txt or '').split(',') if x.strip().isdigit()}
                if fecha.weekday() in dias_set and fecha.weekday() != 6 and not es_festivo:
                    comp = s.explorador_receptor if es_sol else s.explorador_solicitante
                    descansa_por_perm[emp_id] = {
                        'motivo': 'doblada permanente',
                        'companero': _nombre(comp),
                    }

        # ── Permisos especiales ──────────────────────────────────────────────
        from permisos.models import PermisoEspecial
        permisos_por_emp = {}
        for p in (PermisoEspecial.objects
                  .filter(empleado_id__in=emp_ids,
                          estado__in=['APROBADO', 'PENDIENTE'],
                          fecha_inicio__lte=fecha, fecha_fin__gte=fecha)
                  .select_related('empleado')):
            if p.es_permanente:
                dias_set = {int(x) for x in (p.dias_semana or '').split(',')
                            if x.strip().isdigit()}
                if fecha.weekday() not in dias_set:
                    continue
            permisos_por_emp[p.empleado_id] = {
                'horas': float(p.tiempo or 0),
                'tipo': p.get_tipo_display(),
                'especificacion': p.especificacion or '',
                'estado': p.estado,
            }

        # ── Restricciones activas en la fecha (batch) ────────────────────────
        from django.db.models import Q as _Q
        from empleados.models import RestriccionEmpleado, SancionEmpleado
        restricciones_por_emp = {}
        for r in (RestriccionEmpleado.objects
                  .filter(empleado_id__in=emp_ids, fecha_inicio__lte=fecha)
                  .filter(_Q(fecha_fin__isnull=True) | _Q(fecha_fin__gte=fecha))
                  .order_by('empleado_id', '-fecha_inicio')):
            restricciones_por_emp.setdefault(r.empleado_id, {
                'tipo': r.tipo_restriccion or '',
                'recomendacion': r.recomendacion or '',
                'fecha_fin': r.fecha_fin.isoformat() if r.fecha_fin else None,
            })

        # ── Sanciones activas en la fecha (batch) ────────────────────────────
        sanciones_por_emp = {}
        for s in (SancionEmpleado.objects
                  .filter(explorador_id__in=emp_ids, fecha_inicio__lte=fecha)
                  .filter(_Q(fecha_fin__isnull=True) | _Q(fecha_fin__gte=fecha))
                  .order_by('explorador_id', '-fecha_inicio')):
            sanciones_por_emp.setdefault(s.explorador_id, {
                'motivo': s.motivo or '',
                'fecha_inicio': s.fecha_inicio.isoformat(),
                'fecha_fin': s.fecha_fin.isoformat() if s.fecha_fin else None,
            })

        # ── Deuda de doblada por reprogramación (batch) ──────────────────────
        # 'pendiente'  → deuda abierta sin fecha (no cumplió su día de doblada).
        # 'pagada' + fecha_reprogramada>=hoy → ya tiene fecha para pagarla.
        # paga_hoy = ese día le toca cumplir la doblada reprogramada.
        from solicitudes.models import ReprogramacionDiaDoblada
        deudas_por_emp = {}
        for rep in (ReprogramacionDiaDoblada.objects
                    .filter(explorador_id__in=emp_ids)
                    .filter(_Q(estado='pendiente')
                            | _Q(estado='pagada', fecha_reprogramada__gte=fecha))
                    .order_by('explorador_id', 'fecha_original')):
            paga_hoy = (rep.fecha_reprogramada == fecha)
            d = {
                'fecha_original': rep.fecha_original.isoformat(),
                'jornada_debida': rep.jornada_debida,
                'fecha_reprogramada': rep.fecha_reprogramada.isoformat() if rep.fecha_reprogramada else None,
                'motivo': rep.motivo or '',
                'estado': rep.estado,
                'paga_hoy': paga_hoy,
            }
            prev = deudas_por_emp.get(rep.explorador_id)
            # Prioriza la que se paga HOY; si no, la más antigua (primera vista).
            if prev is None or (paga_hoy and not prev['paga_hoy']):
                deudas_por_emp[rep.explorador_id] = d

        # ── Clasificar cada empleado ─────────────────────────────────────────
        trabajando = []
        descansando = []

        for emp in empleados:
            jb = jornada_base_por_emp.get(emp.id)
            turnos = turnos_por_emp.get(emp.id, [])
            permiso = permisos_por_emp.get(emp.id)

            # Determinar jornada del día y si trabaja
            jornada_dia = None
            trabaja = False
            tipo = 'oficial'
            cubre_a = None
            motivo_descanso = None
            companero_descanso = None

            # — Descanso por solicitud aprobada (prioridad máxima) ————————————
            # Se evalúa ANTES que los turnos porque una cesión aprobada es la
            # fuente de verdad del negocio: el empleado cedió su jornada aunque
            # existan registros residuales en la tabla Turno (p.ej. de un cambio
            # turno previo sobre ese mismo día).
            if emp.id in descansa_por_cesion:
                info = descansa_por_cesion[emp.id]
                trabaja = False
                motivo_descanso = info['motivo']
                companero_descanso = info['companero']
            elif emp.id in descansa_por_pago:
                info = descansa_por_pago[emp.id]
                trabaja = False
                motivo_descanso = info['motivo']
                companero_descanso = info['companero']
            elif emp.id in descansa_por_cd:
                info = descansa_por_cd[emp.id]
                trabaja = False
                motivo_descanso = info['motivo']
                companero_descanso = info['companero']
            elif emp.id in descansa_por_perm:
                info = descansa_por_perm[emp.id]
                trabaja = False
                motivo_descanso = info['motivo']
                companero_descanso = info['companero']

            # — FESTIVO entre semana con turno explícito —
            elif es_festivo and fecha.weekday() < 5 and turnos:
                explicitos = [t for t in turnos if t.tipo_cambio]
                if explicitos:
                    js = {t.jornada.nombre.upper() for t in explicitos if t.jornada}
                    jornada_dia = ('DOBLADA' if {'AM', 'PM'} <= js
                                   else ('AM' if 'AM' in js else 'PM' if 'PM' in js else None))
                    trabaja = True
                    tipo = 'cambio'
                    cubre_a = dobla_cubre.get(emp.id)
                    if cubre_a:
                        tipo = 'doblada'
                else:
                    # Sin turno explícito en festivo → rotación
                    if grupo_dobla_festivo and jb == grupo_dobla_festivo:
                        jornada_dia = 'DOBLADA'
                        trabaja = True
                        tipo = 'oficial'
                    else:
                        trabaja = False
                        motivo_descanso = 'festivo'

            # — Turno registrado (cualquier día no festivo) —
            elif turnos and not (es_festivo and fecha.weekday() < 5):
                js = {t.jornada.nombre.upper() for t in turnos if t.jornada}
                jornada_dia = ('DOBLADA' if {'AM', 'PM'} <= js
                               else ('AM' if 'AM' in js else 'PM' if 'PM' in js else None))
                trabaja = True
                tiene_tipo_cambio = any(t.tipo_cambio for t in turnos)
                tipo = 'cambio' if tiene_tipo_cambio else 'oficial'
                cubre_a = dobla_cubre.get(emp.id)
                if cubre_a:
                    tipo = 'doblada'

            # — Sin jornada base —
            elif not jb:
                trabaja = False
                motivo_descanso = 'sin jornada asignada'

            # — Fin de semana —
            elif es_finde:
                if grupo_trabaja_finde and jb == grupo_trabaja_finde:
                    jornada_dia = 'DOBLADA'
                    trabaja = True
                    tipo = 'oficial'
                else:
                    trabaja = False
                    motivo_descanso = 'descanso de fin de semana'

            # — Temporada (descanso semana manual) —
            elif jb in jornadas_descanso_temporada:
                trabaja = False
                motivo_descanso = 'descanso de temporada'

            # — Mantenimiento —
            elif es_mantenimiento:
                trabaja = False
                motivo_descanso = 'lunes de mantenimiento'

            # — Día laboral normal —
            else:
                jornada_dia = jb
                trabaja = True
                tipo = 'oficial'

            base_info = {
                'id': emp.id,
                'nombre': emp.nombre,
                'apellido': emp.apellido,
                'jornada_base': jb,
                'permiso': permiso,
                'restriccion': restricciones_por_emp.get(emp.id),
                'sancion': sanciones_por_emp.get(emp.id),
                'deuda_reprogramacion': deudas_por_emp.get(emp.id),
            }

            if trabaja:
                trabajando.append({
                    **base_info,
                    'jornada_dia': jornada_dia,
                    'tipo': tipo,
                    'cubre_a': cubre_a,
                })
            else:
                descansando.append({
                    **base_info,
                    'motivo': motivo_descanso,
                    'companero': companero_descanso,
                })

        return {
            'trabajando': trabajando,
            'descansando': descansando,
            'dia_info': {
                'es_festivo': es_festivo,
                'es_finde': es_finde,
                'es_mantenimiento': es_mantenimiento,
                'grupo_dobla_festivo': grupo_dobla_festivo,
            },
        }
