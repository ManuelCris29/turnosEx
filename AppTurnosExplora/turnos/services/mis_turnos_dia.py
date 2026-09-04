"""
Construye la ficha de UN día para «Mis Turnos por mes».

POR QUÉ ESTE MÓDULO
-------------------
`MisTurnosPorMesView.get` eran 345 líneas con 52 ramas, y 184 de ellas eran el cuerpo de
un solo bucle: el que decide, día a día, qué ve el explorador. Es uno de los cuatro
puntos calientes que señalaba la auditoría —el sitio donde «cada corrección futura
tendrá que entrar a ciegas»—, y alimenta la pantalla que más gente mira.

La vista se queda con lo que es de una vista: validar los parámetros, mirar la caché,
reunir los datos del mes en lote y responder. La decisión por día vive aquí, donde se
puede leer entera sin desplazarse por una petición HTTP.

QUÉ NO CAMBIA
-------------
Nada del comportamiento. El cuerpo se movió tal cual: lo único que se transformó fue el
`continue` del bucle, que aquí es un `return` —mismo efecto, saltar ese día— y las
variables del entorno, que ahora llegan en `ContextoMes` en vez de estar sueltas
alrededor.

POR QUÉ UN CONTEXTO Y NO NUEVE PARÁMETROS
------------------------------------------
El cuerpo dependía de nueve nombres del ámbito de la vista. Una firma de nueve
parámetros es más difícil de leer que el bucle que sustituye, y cada dato nuevo obligaría
a tocar la firma y todas las llamadas. `ContextoMes` es exactamente lo que ya había
suelto alrededor del bucle, con un nombre. Es la misma decisión que `EntradaDoblada` en
la doblada, y por el mismo motivo.

`escribe_en` recibe el diccionario del mes y se escribe dentro, en vez de devolver la
ficha: el original tiene SIETE puntos donde asigna el día —según sea festivo, cesión,
turno real, permiso…— y convertirlos en `return` habría sido reescribir la lógica, no
moverla. Un traslado que reescribe es un traslado que no se puede verificar.
"""
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from core.constants import JornadaDisplay


@dataclass(frozen=True)
class ContextoMes:
    """Los datos del mes, ya reunidos en lote por la vista.

    Todo lo de aquí se calcula UNA vez por petición y se consulta para cada día: son
    diccionarios indexados por fecha, no consultas. Por eso el bucle de días no toca la
    base de datos.
    """

    turnos_por_fecha: dict
    estados_mes: dict
    descansos_sol: dict
    jornada_base: str
    asignaciones_activas: Any
    calcular_jornada_dia: Callable
    calcular_predeterminado: Callable


def escribe_en(turnos_mes_dict: dict, fecha: date, ctx: ContextoMes) -> None:
    """Decide qué ve el explorador ese día y lo escribe en `turnos_mes_dict`.

    No escribe nada cuando el día no debe aparecer (un festivo que resuelve la fuente de
    verdad), que es lo que antes hacía el `continue` del bucle.
    """
    turnos_dia = ctx.turnos_por_fecha.get(fecha, [])

    # FESTIVO entre semana: la fuente de verdad manda sobre el horario
    # predeterminado (la jornada que dobla por rotación trabaja AM+PM, la otra
    # descansa). Solo un cambio EXPLÍCITO se respeta: en ese caso estado_mes
    # devuelve fuente='turno' y caemos al flujo normal de abajo.
    _est_fv = ctx.estados_mes.get(fecha)
    if _est_fv and _est_fv.get('fuente') == 'festivo':
        if _est_fv['trabaja']:
            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                'jornada': 'DOBLADA',
                'sala': 'Por asignar',
                'tipo': 'predeterminado',
                'es_cambio': False,
                'es_doblada': True,
                'jornada_predeterminada': 'DOBLADA',
                'coincide_con_predeterminada': True,
                'turno_id': None,
                'es_festivo': True,
            }
        else:
            turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                'jornada': None,
                'sala': None,
                'tipo': 'descanso',
                'es_cambio': False,
                'es_descanso': True,
                'jornada_predeterminada': None,
                'coincide_con_predeterminada': False,
                'turno_id': None,
                'es_festivo': True,
                'descanso_info': {'tipo': 'festivo'},
            }
        return

    # Una cesión COMPLETA aprobada tiene prioridad sobre cualquier Turno residual
    # (el empleado cedió TODO el día aunque queden registros huérfanos). Una cesión
    # PARCIAL, en cambio, deja la otra jornada como Turno real válido: NO se borra,
    # para que Mis Turnos muestre la jornada restante (no "día libre"). La fuente única
    # solo incluye la fecha cuando el día quedó libre COMPLETO (cesión completa o ambas
    # medias jornadas), así que su presencia como 'cedió su jornada' equivale a completa.
    _desc_ced = ctx.descansos_sol.get(fecha)
    if _desc_ced and _desc_ced.get('motivo') == 'cedió su jornada' and turnos_dia:
        turnos_dia = []

    if turnos_dia:
        # Hay turno(s) asignado(s) (puede ser cambio aprobado o doblada)
        # OPTIMIZACIÓN: Calcular jornada_display desde turnos_dia sin consultas extra
        jornadas_turnos = [t.jornada.nombre.upper() for t in turnos_dia if t.jornada]
        if 'AM' in jornadas_turnos and 'PM' in jornadas_turnos:
            jornada_display = JornadaDisplay.DOBLADA
        elif 'AM' in jornadas_turnos:
            jornada_display = 'AM'
        elif 'PM' in jornadas_turnos:
            jornada_display = 'PM'
        else:
            jornada_display = ctx.calcular_jornada_dia(ctx.jornada_base, fecha) or ''

        jornada_predeterminada = ctx.calcular_predeterminado(fecha)

        # Detectar si es doblada
        es_doblada = jornada_display == JornadaDisplay.DOBLADA

        # Determinar tipo de cambio (si todos los turnos tienen el mismo tipo_cambio)
        tipos_cambio = [t.tipo_cambio for t in turnos_dia if t.tipo_cambio]
        es_cambio = len(tipos_cambio) > 0
        tipo_cambio_principal = tipos_cambio[0] if tipos_cambio else None

        # Determinar sala(s)
        salas = [t.sala.nombre for t in turnos_dia if t.sala]
        if len(set(salas)) == 1:
            # Todas las salas son iguales
            sala_display = salas[0]
        else:
            # Salas diferentes (raro, pero posible)
            sala_display = ', '.join(set(salas)) if salas else 'Por asignar'

        coincide_con_predeterminada = jornada_display == jornada_predeterminada if jornada_display else False

        # Usar el primer turno como referencia (para compatibilidad con código existente)
        turno_principal = turnos_dia[0]

        turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
            'jornada': jornada_display,  # Usar jornada_display (puede ser JornadaDisplay.DOBLADA)
            'sala': sala_display,
            # 'asignado' solo cuando fue creado por CT/DOBLADA (tipo_cambio != null).
            # 'predeterminado' cuando el turno existe en BD pero sin tipo_cambio (horario importado).
            'tipo': 'asignado' if es_cambio else 'predeterminado',
            'es_cambio': es_cambio,
            'es_doblada': es_doblada,  # Flag para frontend
            'tipo_cambio': tipo_cambio_principal,  # p. ej. 'PAGO REPROGRAMADO' (detalle en Mis Turnos)
            'jornada_predeterminada': jornada_predeterminada,
            'coincide_con_predeterminada': coincide_con_predeterminada,
            'turno_id': turno_principal.id
        }
    else:
        # No hay turno asignado: descansa por una solicitud aprobada?
        # FUENTE UNICA (ctx.descansos_sol): DOBLADA, D FDS, CAMBIO DESCANSO y DOBLADA PERM.
        desc = ctx.descansos_sol.get(fecha)
        esta_descansando = desc is not None

        if esta_descansando:
            _cmp = desc.get("companero") or {}
            _tipo = desc.get("tipo")
            turnos_mes_dict[fecha.strftime("%Y-%m-%d")] = {
                "jornada": None,
                "sala": None,
                "tipo": "descanso",
                "es_cambio": False,
                "es_descanso": True,
                "jornada_predeterminada": ctx.calcular_jornada_dia(ctx.jornada_base, fecha),
                "coincide_con_predeterminada": False,
                "turno_id": None,
                "descanso_info": {
                    "tipo": _tipo,
                    "origen": desc.get("origen"),
                    "companero_nombre": _cmp.get("nombre"),
                    "companero_id": _cmp.get("id"),
                    "solicitud_id": desc.get("solicitud_id"),
                    "fecha_relacionada": (desc.get("fecha_pago") if _tipo == "cedio" else desc.get("fecha_cesion")),
                    "fecha_cesion": desc.get("fecha_cesion"),
                    "fecha_pago": desc.get("fecha_pago"),
                    "fecha_solicitud": desc.get("fecha_solicitud"),
                    "fecha_aprobacion": desc.get("fecha_aprobacion"),
                    "tipo_cesion": desc.get("tipo_cesion"),
                    "jornada_cedida": desc.get("jornada_cedida"),
                }
            }
        else:
            # No hay turno asignado: el estado lo resuelve la FUENTE DE VERDAD
            # única (estado_mes), que ya aplica alternancia de finde, temporada y
            # mantenimiento en el orden correcto. Antes esta lógica estaba duplicada
            # aquí; ahora solo se mapea su resultado al formato de la respuesta.
            est = ctx.estados_mes.get(fecha) or {}

            if est.get('trabaja') and est.get('jornada') == JornadaDisplay.DOBLADA:
                # Fin de semana que le corresponde trabajar → jornada predeterminada DOBLADA
                turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                    'jornada': 'DOBLADA',
                    'sala': 'Por asignar',
                    'tipo': 'predeterminado',
                    'es_cambio': False,
                    'es_doblada': True,  # Flag para frontend
                    'jornada_predeterminada': 'DOBLADA',
                    'coincide_con_predeterminada': True,
                    'turno_id': None
                }
            elif (not est.get('trabaja')) and est.get('fuente') in ('temporada', 'mantenimiento'):
                # Descanso de ENTRE SEMANA (temporada/mantenimiento)
                motivo_descanso_semana = 'temporada' if est.get('fuente') == 'temporada' else 'mantenimiento'
                turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                    'jornada': None,
                    'sala': None,
                    'tipo': 'descanso',
                    'es_cambio': False,
                    'es_descanso': True,
                    'jornada_predeterminada': ctx.calcular_jornada_dia(ctx.jornada_base, fecha),
                    'coincide_con_predeterminada': False,
                    'turno_id': None,
                    'descanso_info': {
                        'tipo': 'descanso_semana',
                        'motivo': motivo_descanso_semana,  # 'manual' o 'mantenimiento'
                    },
                }
            else:
                # Día normal (jornada base entre semana) o descanso de fin de semana
                # (que conserva el comportamiento histórico: jornada = "Descanso").
                jornada_nombre = ctx.calcular_jornada_dia(ctx.jornada_base, fecha)

                sala_nombre = 'Por asignar'
                if ctx.asignaciones_activas:
                    sala_nombre = ctx.asignaciones_activas.sala.nombre

                turnos_mes_dict[fecha.strftime('%Y-%m-%d')] = {
                    'jornada': jornada_nombre,
                    'sala': sala_nombre,
                    'tipo': 'predeterminado',
                    'es_cambio': False,
                    'es_descanso': False,
                    'jornada_predeterminada': jornada_nombre,
                    'coincide_con_predeterminada': True,
                    'turno_id': None
                }