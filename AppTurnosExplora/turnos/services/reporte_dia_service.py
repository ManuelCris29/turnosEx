"""
ReporteDiaService

Genera el reporte operacional de un día para supervisores: quién trabaja
(AM/PM/DOBLADA), quién descansa y por qué, quién tiene permiso especial.

Aplica las MISMAS capas de prioridad que `TurnoService.estado_dia`, en el mismo
orden, pero en batch para TODOS los empleados activos en una sola pasada (número de
consultas constante: la plantilla real ronda los 400 exploradores y este reporte
alimenta también la exportación a Excel).

La capa L2 (descanso por solicitud aprobada) NO se reimplementa aquí: se delega en
`DescansoPorSolicitudService.en_rango_multiple`, la misma fuente única que usa
`estado_dia`. Reimplementarla fue la causa de que este reporte mostrara datos falsos
(gente "descansando" que en realidad estaba doblando).

`test_reporte_dia_paridad.py` compara este reporte contra `estado_dia` empleado por
empleado y día por día: si alguien vuelve a tocar una capa aquí sin tocarla allá, falla.
"""
from datetime import date as _date
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
            'grupo_dobla_festivo',
            'sin_planificar'   # True si el día es finde/festivo SIN alternancia
                               # publicada: las columnas vacías no significan
                               # "descansan todos", sino "nadie lo ha planificado".
          }
        }

        Las fechas dentro de restriccion/sancion/deuda_reprogramacion son
        strings ISO (YYYY-MM-DD) o None.
        """
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

        # Festivos y findes salen de la MISMA fuente que `estado_dia` y las validaciones de
        # solicitudes: la alternancia publicada. None = el año no está sembrado.
        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        grupo_dobla_festivo = None
        if es_festivo and fecha.weekday() < 5:
            grupo_dobla_festivo = AsignacionEspecialService.grupo_trabaja(fecha)

        # ── Grupo que trabaja el fin de semana ───────────────────────────────
        grupo_trabaja_finde = AsignacionEspecialService.grupo_trabaja(fecha) if es_finde else None

        # `grupo_trabaja` devuelve None cuando el día NO tiene alternancia publicada, y eso
        # NO es lo mismo que "descansa todo el mundo". Si no se distingue, un año sin sembrar
        # se ve exactamente igual que un día real con las tres columnas vacías. Se marca aquí
        # y se propaga como motivo propio para que la UI pueda avisar.
        sin_planificar = bool(
            (es_finde and grupo_trabaja_finde is None)
            or (es_festivo and fecha.weekday() < 5 and grupo_dobla_festivo is None)
        )
        MOTIVO_SIN_PLANIFICAR = 'sin alternancia publicada'

        # ── Descanso de semana manual (temporada) por jornada ───────────────
        jornadas_descanso_temporada = set()
        for dsm in DescansoSemanaManual.objects.filter(
                fecha=fecha, activo=True).select_related('jornada'):
            jornadas_descanso_temporada.add(dsm.jornada.nombre.upper())

        # ── L2: descanso por solicitud aprobada (FUENTE ÚNICA, en batch) ─────
        # Antes este servicio reimplementaba la atribución de descanso (cesión, pago, cambio de
        # descanso y doblada permanente) con sus propias consultas. Se desincronizó de la regla
        # real y mostraba datos falsos: la doblada permanente se resolvía por PATRÓN de día de la
        # semana en vez de por las FECHAS específicas elegidas, así que marcaba descansando a
        # gente que ese día estaba doblando; y ninguna rama aplicaba la guarda "L1 manda sobre L2"
        # (un turno real gana sobre una solicitud vieja: la última aprobada gana por día).
        #
        # Ahora delega en el mismo servicio que usan `estado_dia` y Mis Turnos, en su variante
        # batch: una sola tanda de consultas para toda la plantilla (importa: ~400 exploradores).
        from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService
        descanso_l2 = {
            eid: por_fecha.get(fecha)
            for eid, por_fecha in DescansoPorSolicitudService.en_rango_multiple(
                empleados, fecha, fecha).items()
        }

        # Quién DOBLÓ (receptor en fecha_cambio_turno) → para mostrar "cubre a X"
        dobla_cubre = {}   # emp_id (receptor) → {id, nombre} del cedente
        for s in (SolicitudCambio.objects
                  .filter(tipo_cambio__nombre__in=['DOBLADA', 'D FDS'],
                          estado='aprobada', fecha_cambio_turno=fecha,
                          explorador_receptor_id__in=emp_ids)
                  .select_related('explorador_solicitante', 'explorador_receptor')):
            dobla_cubre[s.explorador_receptor_id] = _nombre(s.explorador_solicitante)

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

            # El ORDEN de estas ramas replica exactamente el de `TurnoService.estado_dia`
            # (L5 festivo → L1 turno real → L2 solicitud → base → L6 finde → L4 temporada →
            # L3 mantenimiento → L4 lado que dobla → base). Cualquier reordenamiento aquí hace
            # que el reporte del supervisor y Mis Turnos digan cosas distintas del mismo día;
            # el test de paridad (`test_reporte_dia_paridad.py`) lo detecta.
            l2 = descanso_l2.get(emp.id)

            def _jornada_de(ts):
                js = {t.jornada.nombre.upper() for t in ts if t.jornada}
                return ('DOBLADA' if {'AM', 'PM'} <= js
                        else ('AM' if 'AM' in js else 'PM' if 'PM' in js else None))

            # — L5 FESTIVO entre semana: la regla del festivo manda sobre el horario base;
            #   solo un cambio EXPLÍCITO (turno con tipo_cambio) se respeta por encima. —
            if es_festivo and fecha.weekday() < 5:
                explicitos = [t for t in turnos if t.tipo_cambio]
                if explicitos:
                    jornada_dia = _jornada_de(explicitos)
                    trabaja = True
                    tipo = 'cambio'
                    cubre_a = dobla_cubre.get(emp.id)
                    if cubre_a:
                        tipo = 'doblada'
                elif l2:
                    # Cedió el festivo por una solicitud aprobada: la rotación no puede
                    # ponerlo a trabajar igualmente.
                    trabaja = False
                    motivo_descanso = l2['motivo']
                    companero_descanso = l2.get('companero')
                elif grupo_dobla_festivo is None:
                    trabaja = False
                    motivo_descanso = MOTIVO_SIN_PLANIFICAR
                elif jb and jb == grupo_dobla_festivo:
                    jornada_dia = 'DOBLADA'
                    trabaja = True
                    tipo = 'oficial'
                else:
                    trabaja = False
                    motivo_descanso = 'festivo: descansa el grupo contrario'

            # — L1: turno real (máxima prioridad el resto de días) —
            elif turnos:
                jornada_dia = _jornada_de(turnos)
                trabaja = True
                tipo = 'cambio' if any(t.tipo_cambio for t in turnos) else 'oficial'
                cubre_a = dobla_cubre.get(emp.id)
                if cubre_a:
                    tipo = 'doblada'

            # — L2: descanso por solicitud aprobada —
            elif l2:
                trabaja = False
                motivo_descanso = l2['motivo']
                companero_descanso = l2.get('companero')

            # — Sin jornada base —
            elif not jb:
                trabaja = False
                motivo_descanso = 'sin jornada asignada'

            # — L6: fin de semana —
            elif es_finde:
                if grupo_trabaja_finde is None:
                    trabaja = False
                    motivo_descanso = MOTIVO_SIN_PLANIFICAR
                elif jb == grupo_trabaja_finde:
                    jornada_dia = 'DOBLADA'
                    trabaja = True
                    tipo = 'oficial'
                else:
                    trabaja = False
                    motivo_descanso = 'descanso de fin de semana'

            # — L4: temporada (descanso semana manual) —
            elif jb in jornadas_descanso_temporada:
                trabaja = False
                motivo_descanso = 'descanso de temporada'

            # — L3: mantenimiento —
            elif es_mantenimiento:
                trabaja = False
                motivo_descanso = 'lunes de mantenimiento'

            # — L4 (lado que TRABAJA): si el grupo contrario descansa hoy por temporada,
            #   este grupo cubre el DÍA COMPLETO (AM+PM). Faltaba, y por eso el reporte
            #   mostraba media jornada a gente que en Mis Turnos figura doblada. —
            elif ('PM' if jb == 'AM' else 'AM') in jornadas_descanso_temporada:
                jornada_dia = 'DOBLADA'
                trabaja = True
                tipo = 'oficial'

            # — Base: trabaja su jornada —
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
                'sin_planificar': sin_planificar,
            },
        }
