"""
ReporteDiaService

Genera el reporte operacional de un día para supervisores: quién trabaja
(AM/PM/DOBLADA), quién descansa y por qué, quién tiene permiso especial.

Usa las mismas capas de prioridad que TurnoService.estado_mes pero en batch
para TODOS los empleados activos en una sola pasada (~10 queries totales).
"""
from datetime import date as _date
from django.db.models import Q
from empleados.models import Empleado
from turnos.models import Turno, AsignarJornadaExplorador, DiaEspecial, DescansoSemanaManual
from solicitudes.models import SolicitudCambio


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
             permiso}       # None | {horas, tipo, especificacion}
          ],
          'descansando': [
            {id, nombre, apellido, jornada_base,
             motivo,        # texto legible
             companero,     # None | {id, nombre}
             permiso}       # None | {horas, tipo, especificacion}
          ],
          'dia_info': {
            'es_festivo', 'es_finde', 'es_mantenimiento',
            'grupo_dobla_festivo'
          }
        }
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
        es_festivo = DiaEspecial.objects.filter(
            fecha=fecha, tipo='festivo', activo=True).exists()
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
                pass

        # ── Grupo que trabaja el fin de semana ───────────────────────────────
        grupo_trabaja_finde = None
        if es_finde:
            try:
                from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
                grupo_trabaja_finde = AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha)
                if grupo_trabaja_finde:
                    grupo_trabaja_finde = grupo_trabaja_finde.upper()
            except Exception:
                pass

        # ── Descanso de semana manual (temporada) por jornada ───────────────
        jornadas_descanso_temporada = set()
        for dsm in DescansoSemanaManual.objects.filter(
                fecha=fecha, activo=True).select_related('jornada'):
            jornadas_descanso_temporada.add(dsm.jornada.nombre.upper())

        # ── Solicitudes que afectan esta fecha ───────────────────────────────
        # Quién DESCANSA por haber cedido (DOBLADA / D FDS — solicitante)
        descansa_por_cesion = {}   # emp_id → {motivo, companero}
        for s in (SolicitudCambio.objects
                  .filter(tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                          estado='aprobada', fecha_cambio_turno=fecha,
                          explorador_solicitante_id__in=emp_ids)
                  .select_related('explorador_solicitante', 'explorador_receptor')):
            descansa_por_cesion[s.explorador_solicitante_id] = {
                'motivo': 'cedió su jornada',
                'companero': _nombre(s.explorador_receptor),
            }

        # Quién DESCANSA por pagar doblada (receptor, en fecha_pago)
        descansa_por_pago = {}   # emp_id → {motivo, companero}
        for s in (SolicitudCambio.objects
                  .filter(tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                          estado='aprobada', explorador_receptor_id__in=emp_ids,
                          doblada__fecha_pago=fecha)
                  .select_related('explorador_solicitante', 'explorador_receptor', 'doblada')):
            descansa_por_pago[s.explorador_receptor_id] = {
                'motivo': 'paga doblada',
                'companero': _nombre(s.explorador_solicitante),
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
            ini_mes = _date(anio, mes, 1)
            fin_mes = _date(anio, mes, 28 + 4)  # fin holgado
            from calendar import monthrange
            fin_mes = _date(anio, mes, monthrange(anio, mes)[1])
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
            pass

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
