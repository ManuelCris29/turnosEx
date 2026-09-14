"""
Fuente ÚNICA de "¿este `Turno` MANDA sobre las capas de abajo?".

POR QUÉ EXISTE
--------------
La capa L1 (turno real) gana sobre la L2 (descanso por solicitud aprobada) porque un turno
presente solo puede venir de algo aprobado DESPUÉS: la última aprobada gana el día. Pero en
un FESTIVO entre semana esa premisa no se cumple. Ahí la regla del festivo (L5) manda sobre
el horario predeterminado o importado, y solo se respeta un cambio EXPLÍCITO — un turno con
`tipo_cambio`. Un turno plano (`tipo_cambio` NULL) en un festivo NO es "algo aprobado
después": es el horario de siempre, o lo que dejó restaurado la cancelación de otra
solicitud.

El criterio estaba escrito dos veces con dos formas distintas, y se contradecían:

  · L5 (`TurnoService.estado_dia`, `estado_rango_multiple`, `reporte_dia_empleado.clasifica`)
    filtraba por `tipo_cambio` — correcto.
  · La guarda de realidad de `DescansoPorSolicitudService` contaba CUALQUIER turno activo.

Resultado en un festivo entre semana con un turno plano: la guarda silenciaba la L2 y la L5
descartaba ese mismo turno, así que la solicitud aprobada desaparecía y mandaba la rotación.
El acreedor de una doblada salía DOBLANDO el día en que le pagaban y el deudor que debía
cubrirlo salía descansando — el trato al revés, tanto en el reporte del supervisor como en
Mis Turnos. Ver `turnos/tests/test_festivo_turno_plano.py`.

Con el criterio en un solo sitio, las dos capas no pueden volver a discrepar.
"""


def turno_manda_en(fecha, tipo_cambio, es_festivo: bool) -> bool:
    """¿Un turno de `fecha` con ese `tipo_cambio` cuenta como la REALIDAD de ese día?

    `es_festivo` lo aporta quien llama, que ya lo tiene resuelto (en batch para todo el
    rango, o vía `DiaEspecial.es_festivo`): este módulo no toca la base de datos a
    propósito, para poder usarse dentro de bucles por empleado sin coste.
    """
    if es_festivo and fecha.weekday() < 5:
        # Festivo entre semana: solo un cambio EXPLÍCITO gana a la rotación del festivo.
        return bool(tipo_cambio)
    return True


def turnos_que_mandan(fecha, turnos, es_festivo: bool) -> list:
    """Sublista de `turnos` (objetos `Turno`) que manda sobre las capas de abajo en `fecha`."""
    return [t for t in turnos if turno_manda_en(fecha, t.tipo_cambio, es_festivo)]
