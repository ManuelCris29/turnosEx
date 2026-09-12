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

from core.services.cache_service import CACHE_TTL_SHORT, CacheService
from core.utils.date_utils import DateUtils
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio
from turnos.models import AsignarJornadaExplorador, DescansoSemanaManual, DiaEspecial, Turno
from turnos.services.reporte_dia_empleado import (  # noqa: F401  (reexportado)  # noqa: F401  (reexportado)
    MOTIVO_SIN_PLANIFICAR,
    ContextoDia,
    clasifica,
)


def _nombre(emp):
    return {'id': emp.id, 'nombre': f'{emp.nombre} {emp.apellido}'}


class ReporteDiaService:

    @staticmethod
    def dias_del_mes(anio: int, mes: int) -> dict:
        """
        Qué TIPO de día es cada fecha del mes: festivo, fin de semana, mantenimiento o
        sin planificar. Hermano de `reporte()`, pero sin tocar empleados: es solo el
        calendario, para poder pintar la cuadrícula del mes de una sola petición en vez
        de una por día.

        Las cuatro claves significan exactamente lo mismo que en `reporte()['dia_info']`
        y salen de las mismas fuentes (`DiaEspecial`, `AsignacionEspecialManual`), en
        batch: si alguna vez divergieran, la celda pintada y el reporte al hacer clic
        dirían cosas distintas del mismo día.

        Devuelve {'YYYY-MM-DD': {es_festivo, es_finde, es_mantenimiento, sin_planificar}}
        solo para los días que tienen algo que contar; un día laboral normal no aparece.
        """
        import calendar

        from turnos.models import AsignacionEspecialManual

        primero = _date(anio, mes, 1)
        ultimo = _date(anio, mes, calendar.monthrange(anio, mes)[1])

        especiales = {'festivo': set(), 'mantenimiento': set(), 'temporada': set()}
        for fecha, tipo, es_temporada in (DiaEspecial.objects
                                          .filter(fecha__range=(primero, ultimo), activo=True)
                                          .values_list('fecha', 'tipo', 'es_temporada')):
            if es_temporada:
                especiales['temporada'].add(fecha)
            if tipo in especiales:
                especiales[tipo].add(fecha)

        planificados = set(AsignacionEspecialManual.objects
                           .filter(fecha__range=(primero, ultimo), activo=True)
                           .values_list('fecha', flat=True))

        dias = {}
        for n in range(1, ultimo.day + 1):
            fecha = _date(anio, mes, n)
            es_festivo = fecha in especiales['festivo']
            es_finde = fecha.weekday() in (5, 6)
            # La temporada manda sobre el mantenimiento, igual que en
            # `DiaEspecial.es_mantenimiento_efectivo`.
            es_mant = (not es_festivo and not es_finde
                       and fecha in especiales['mantenimiento']
                       and fecha not in especiales['temporada'])
            # Sin fila de alternancia el día NO es "todos descansan": es que nadie lo
            # ha planificado. Ver `AsignacionEspecialManual`.
            sin_plan = ((es_finde or (es_festivo and fecha.weekday() < 5))
                        and fecha not in planificados)
            if es_festivo or es_finde or es_mant or sin_plan:
                dias[fecha.isoformat()] = {
                    'es_festivo': es_festivo,
                    'es_finde': es_finde,
                    'es_mantenimiento': es_mant,
                    'sin_planificar': sin_plan,
                }
        return dias

    @staticmethod
    def reporte(fecha: _date) -> dict:
        """Cachea `_reporte_bd` 5 minutos. Ver su docstring para la forma del resultado.

        Sin invalidación explícita a propósito: este reporte agrega datos que
        cambian por ~15 puntos distintos (aprobación, cancelación, sanciones,
        permisos, día especial...); perseguir cada uno aquí sería acoplar un
        reporte de solo lectura a toda esa lógica. Un TTL corto cubre el caso
        real (ver el reporte y bajar el Excel de la misma fecha, `ReporteDiaView`
        y `ReporteDiaExcelView` en `turnos/api/views/reportes.py`) sin arriesgar
        más de 5 minutos de desfase en una pantalla que ya se refresca a mano.
        """
        return CacheService.get_or_set(
            f"reporte_dia_v1_{fecha}",
            lambda: ReporteDiaService._reporte_bd(fecha),
            ttl=CACHE_TTL_SHORT,
        )

    @staticmethod
    def _reporte_bd(fecha: _date) -> dict:
        """
        Devuelve el estado de todos los empleados activos para `fecha`.

        Estructura de retorno:
        {
          'trabajando': [
            {id, nombre, apellido, jornada_base, jornada_dia,
             tipo,          # 'oficial' | 'cambio' | 'doblada'
             cubre_a,       # None | {id, nombre}  (cuando dobló por alguien)
             acuerdo,       # None | la solicitud que le puso este turno (ver abajo)
             permiso,       # None | {horas, tipo, especificacion, estado, id,
                            #   cubre, aprobado_por, fecha_aprobacion, es_permanente}
             restriccion,   # None | {tipo, recomendacion, fecha_fin}
             sancion,       # None | {motivo, fecha_inicio, fecha_fin}
             deuda_reprogramacion}  # None | {fecha_original, jornada_debida,
                            #   fecha_reprogramada, motivo, estado, paga_hoy}
          ],
          'descansando': [
            {id, nombre, apellido, jornada_base,
             motivo,        # texto legible
             companero,     # None | {id, nombre}
             acuerdo,       # None | la solicitud por la que descansa (ver abajo)
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

        `acuerdo` tiene la MISMA forma en los dos lados —quien trabaja por un cambio y quien
        descansa por él son las dos caras del mismo trato— y es lo que permite al reporte
        decir CON QUIÉN se hizo, no solo que hubo un cambio:

            {'solicitud_id', 'tipo',            # 'DOBLADA', 'CAMBIO TURNO', 'CT PERMANENTE'…
             'tipo_cambio',                     # lo que quedó escrito en Turno.tipo_cambio
             'companero_id', 'companero_nombre',
             'rol',                             # 'solicitante' | 'receptor'
             'fecha_solicitud', 'fecha_resolucion',   # 'DD/MM/AAAA HH:MM' | None
             'fecha_relacionada'}               # el OTRO día del trato ('DD/MM/AAAA') | None

        Sale de `AcuerdoPorDiaService` para quien trabaja y de `DescansoPorSolicitudService`
        para quien descansa (normalizado en `reporte_dia_empleado._acuerdo_de_descanso`).

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

        # ── L1: acuerdo que pone a TRABAJAR (FUENTE ÚNICA, en batch) ─────────
        # El hermano del bloque de arriba: `dobla_cubre` (más abajo) solo sabe de
        # DOBLADA/D FDS y solo del lado del receptor, así que un CAMBIO TURNO, un CT
        # PERMANENTE, una DOBLADA PERMANENTE o un PAGO REPROGRAMADO salían sin decir con
        # quién era el acuerdo. `AcuerdoPorDiaService` lo resuelve para los seis tipos por
        # snapshot, con la misma guarda de realidad y el mismo "la última aprobada gana".
        from solicitudes.services.acuerdo_por_dia_service import AcuerdoPorDiaService
        acuerdo_l1 = {
            eid: por_fecha.get(fecha)
            for eid, por_fecha in AcuerdoPorDiaService.en_rango_multiple(
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
                  .select_related('empleado', 'cubre', 'supervisor')):
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
                # Un permiso también deja un hueco que alguien tapa: para el supervisor es
                # tan parte de la planeación del día como una doblada. `cubre` es opcional.
                'id': p.id,
                'cubre': _nombre(p.cubre) if p.cubre else None,
                'aprobado_por': _nombre(p.supervisor) if p.supervisor else None,
                'fecha_solicitud': DateUtils.format_datetime_display(p.creado_en),
                'fecha_aprobacion': DateUtils.format_datetime_display(p.fecha_aprobacion),
                'es_permanente': p.es_permanente,
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

        # ── Sanciones vigentes en la fecha (batch) ───────────────────────────
        # Vía `vigentes_en`, el mismo criterio que decide si alguien está bloqueado:
        # rearmarlo aquí a mano ya dejó fuera los levantamientos una vez.
        from empleados.sancion_utils import vigentes_en
        sanciones_por_emp = {}
        for s in (SancionEmpleado.objects
                  .filter(vigentes_en(fecha), explorador_id__in=emp_ids)
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

        _ctx = ContextoDia(
            fecha=fecha,
            es_festivo=es_festivo,
            es_finde=es_finde,
            es_mantenimiento=es_mantenimiento,
            grupo_dobla_festivo=grupo_dobla_festivo,
            grupo_trabaja_finde=grupo_trabaja_finde,
            jornadas_descanso_temporada=jornadas_descanso_temporada,
            jornada_base_por_emp=jornada_base_por_emp,
            turnos_por_emp=turnos_por_emp,
            descanso_l2=descanso_l2,
            acuerdo_l1=acuerdo_l1,
            dobla_cubre=dobla_cubre,
            permisos_por_emp=permisos_por_emp,
            restricciones_por_emp=restricciones_por_emp,
            sanciones_por_emp=sanciones_por_emp,
            deudas_por_emp=deudas_por_emp,
        )

        for emp in empleados:
            clasifica(emp, _ctx, trabajando, descansando)

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
