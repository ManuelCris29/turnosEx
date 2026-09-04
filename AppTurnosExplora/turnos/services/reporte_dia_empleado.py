"""
Decide, para UN empleado, si trabaja hoy y por qué.

POR QUÉ ESTE MÓDULO
-------------------
`ReporteDiaService.reporte` eran 340 líneas, y 134 de ellas el cuerpo de un bucle: el
que clasifica a cada explorador del día. Es el cuarto punto caliente de la auditoría y
el peor cubierto de los tres que quedaban (72%).

El servicio se queda con lo que sí es suyo: reunir en LOTE todo lo del día —turnos,
jornadas base, permisos, restricciones, sanciones, deudas, descansos por solicitud— en
diccionarios indexados por empleado. Esa parte es de rendimiento: evita las N+1 de un
reporte con toda la plantilla. La decisión por persona vive aquí.

EL ORDEN DE LAS CAPAS ES EL CONTRATO
------------------------------------
Las ramas replican EXACTAMENTE el orden de `TurnoService.estado_dia`:

    L5 festivo → L1 turno real → L2 solicitud → base → L6 finde → L4 temporada →
    L3 mantenimiento → L4 lado que dobla → base

Cualquier reordenamiento hace que el reporte del supervisor y Mis Turnos digan cosas
distintas del mismo día. `test_reporte_dia_paridad.py` lo detecta, y
`test_reporte_dia_capas.py` cubre cada capa por separado.

`clasifica` escribe en las listas que recibe en vez de devolver la ficha: el original
mete al empleado en `trabajando` o en `descansando` con claves distintas en cada caso
—la de quien descansa lleva `motivo`—, y unificarlas habría sido reescribir la salida,
no moverla.
"""
from dataclasses import dataclass
from datetime import date
from typing import Any

#: Lo que se le dice al supervisor de un dia cuyo grupo de finde/festivo aun no se ha
#: publicado. Vive aqui, con la rama que lo usa; `reporte_dia_service` lo reexporta
#: para que los tests fijen el CASO y no la redaccion.
MOTIVO_SIN_PLANIFICAR = 'sin alternancia publicada'


@dataclass(frozen=True)
class ContextoDia:
    """Todo lo del día, ya reunido en lote e indexado por empleado.

    Se calcula una vez por reporte y se consulta para cada persona: por eso clasificar a
    un empleado no dispara ni una consulta.
    """

    fecha: date
    es_festivo: bool
    es_finde: bool
    es_mantenimiento: bool
    grupo_dobla_festivo: Any
    grupo_trabaja_finde: Any
    jornadas_descanso_temporada: set
    jornada_base_por_emp: dict
    turnos_por_emp: dict
    descanso_l2: dict
    dobla_cubre: dict
    permisos_por_emp: dict
    restricciones_por_emp: dict
    sanciones_por_emp: dict
    deudas_por_emp: dict


def clasifica(emp, ctx: ContextoDia, trabajando: list, descansando: list) -> None:
    """Mete a `emp` en la lista que le corresponda, con el porqué."""
    jb = ctx.jornada_base_por_emp.get(emp.id)
    turnos = ctx.turnos_por_emp.get(emp.id, [])
    permiso = ctx.permisos_por_emp.get(emp.id)

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
    l2 = ctx.descanso_l2.get(emp.id)

    def _jornada_de(ts):
        js = {t.jornada.nombre.upper() for t in ts if t.jornada}
        return ('DOBLADA' if {'AM', 'PM'} <= js
                else ('AM' if 'AM' in js else 'PM' if 'PM' in js else None))

    # — L5 FESTIVO entre semana: la regla del festivo manda sobre el horario base;
    #   solo un cambio EXPLÍCITO (turno con tipo_cambio) se respeta por encima. —
    if ctx.es_festivo and ctx.fecha.weekday() < 5:
        explicitos = [t for t in turnos if t.tipo_cambio]
        if explicitos:
            jornada_dia = _jornada_de(explicitos)
            trabaja = True
            tipo = 'cambio'
            cubre_a = ctx.dobla_cubre.get(emp.id)
            if cubre_a:
                tipo = 'doblada'
        elif l2:
            # Cedió el festivo por una solicitud aprobada: la rotación no puede
            # ponerlo a trabajar igualmente.
            trabaja = False
            motivo_descanso = l2['motivo']
            companero_descanso = l2.get('companero')
        elif ctx.grupo_dobla_festivo is None:
            trabaja = False
            motivo_descanso = MOTIVO_SIN_PLANIFICAR
        elif jb and jb == ctx.grupo_dobla_festivo:
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
        cubre_a = ctx.dobla_cubre.get(emp.id)
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
    elif ctx.es_finde:
        if ctx.grupo_trabaja_finde is None:
            trabaja = False
            motivo_descanso = MOTIVO_SIN_PLANIFICAR
        elif jb == ctx.grupo_trabaja_finde:
            jornada_dia = 'DOBLADA'
            trabaja = True
            tipo = 'oficial'
        else:
            trabaja = False
            motivo_descanso = 'descanso de fin de semana'

    # — L4: temporada (descanso semana manual) —
    elif jb in ctx.jornadas_descanso_temporada:
        trabaja = False
        motivo_descanso = 'descanso de temporada'

    # — L3: mantenimiento —
    elif ctx.es_mantenimiento:
        trabaja = False
        motivo_descanso = 'lunes de mantenimiento'

    # — L4 (lado que TRABAJA): si el grupo contrario descansa hoy por temporada,
    #   este grupo cubre el DÍA COMPLETO (AM+PM). Faltaba, y por eso el reporte
    #   mostraba media jornada a gente que en Mis Turnos figura doblada. —
    elif ('PM' if jb == 'AM' else 'AM') in ctx.jornadas_descanso_temporada:
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
        'restriccion': ctx.restricciones_por_emp.get(emp.id),
        'sancion': ctx.sanciones_por_emp.get(emp.id),
        'deuda_reprogramacion': ctx.deudas_por_emp.get(emp.id),
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