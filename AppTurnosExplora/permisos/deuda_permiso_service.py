"""
Deuda de permisos, repartida por mes.

Un permiso especial genera tiempo que el explorador debe. Cuando el permiso es PERMANENTE
y abarca varios meses, ese tiempo no es una sola obligación: es una por mes, porque cada
una vence al cerrar su mes y se reclama (y se sanciona) por separado. Antes se trataba
como un bloque único, lo que obligaba a esperar al final del rango para exigir lo del
primer mes.

Este servicio traduce un permiso en sus obligaciones mensuales (`DeudaPermisoMes`) y las
mantiene al día. Las obligaciones se MATERIALIZAN en la base de datos —no se derivan al
vuelo cada vez— porque tienen estado propio que no está en el permiso: cuánto se ha pagado
a cuenta y qué sanción las consumió. Una función derivada olvidaría ambas cosas.
"""
import logging

from django.db import transaction

from .models import DeudaPermisoMes, PermisoEspecial

logger = logging.getLogger(__name__)

# Estados en los que un permiso debe tener sus obligaciones vivas. Un permiso pendiente
# todavía no debe nada: nadie lo ha aprobado.
ESTADOS_CON_DEUDA = ('APROBADO',)


def desglose_mensual(permiso: PermisoEspecial) -> list[dict]:
    """
    Qué debe este permiso en cada mes: [{anio, mes, ocurrencias, minutos}].

    Función pura. La suma de `minutos` equivale siempre a `permiso.horas_totales()` en
    minutos —ambos salen del mismo recorrido—, invariante que se comprueba en los tests:
    si divergieran, la pantalla mostraría un total y se cobraría otro.
    """
    minutos_por_ocurrencia = round(float(permiso.tiempo or 0) * 60)
    return [
        {'anio': anio, 'mes': mes, 'ocurrencias': n,
         'minutos': minutos_por_ocurrencia * n}
        for anio, mes, n in permiso.ocurrencias_por_mes()
    ]


def _tiene_historia(deuda: DeudaPermisoMes) -> bool:
    """
    Si ya se pagó algo a cuenta o una sanción la consumió, la fila es un hecho ocurrido.

    Se usa para decidir si una obligación puede recalcularse o hay que respetarla: cambiar
    los minutos de un mes que alguien ya pagó descuadraría el pago registrado.
    """
    return deuda.minutos_pagados > 0 or deuda.estado in ('pagada', 'consumida_por_sancion')


@transaction.atomic
def sincronizar(permiso: PermisoEspecial) -> dict:
    """
    Deja las obligaciones mensuales de `permiso` acordes con su rango y su estado.

    Es idempotente: llamarla dos veces seguidas no cambia nada la segunda vez. Eso permite
    invocarla desde varios sitios (al aprobar, al cancelar, y como red de seguridad al
    consultar) sin que compitan entre sí — el mismo enfoque que ya usa la sanción por deuda.

    Reglas:
    - Un permiso que no está aprobado no debe nada: sus obligaciones limpias se borran y
      las que tienen historia se marcan 'cancelada' (nunca se destruye lo ya ocurrido).
    - Una obligación con pagos o consumida por sanción NO se recalcula aunque el permiso
      haya cambiado: se avisa por log y se deja como está.

    Devuelve {'creadas', 'actualizadas', 'canceladas', 'borradas'}.
    """
    resumen = {'creadas': 0, 'actualizadas': 0, 'canceladas': 0, 'borradas': 0}

    esperado = {}
    if permiso.estado in ESTADOS_CON_DEUDA:
        esperado = {(d['anio'], d['mes']): d for d in desglose_mensual(permiso)}

    existentes = {(d.anio, d.mes): d
                  for d in DeudaPermisoMes.objects.select_for_update()
                                                  .filter(permiso=permiso)}

    for clave, datos in esperado.items():
        deuda = existentes.get(clave)
        if deuda is None:
            DeudaPermisoMes.objects.create(
                permiso=permiso, explorador=permiso.empleado,
                anio=datos['anio'], mes=datos['mes'],
                minutos_generados=datos['minutos'], ocurrencias=datos['ocurrencias'],
            )
            resumen['creadas'] += 1
            continue

        if _tiene_historia(deuda):
            if deuda.minutos_generados != datos['minutos']:
                logger.warning(
                    'La deuda %s (permiso %s, %s-%s) ya tiene pagos o fue consumida: se '
                    'conserva en %s min aunque el permiso ahora calcule %s min.',
                    deuda.id, permiso.id, deuda.anio, deuda.mes,
                    deuda.minutos_generados, datos['minutos'])
            continue

        cambios = []
        if deuda.minutos_generados != datos['minutos']:
            deuda.minutos_generados = datos['minutos']
            cambios.append('minutos_generados')
        if deuda.ocurrencias != datos['ocurrencias']:
            deuda.ocurrencias = datos['ocurrencias']
            cambios.append('ocurrencias')
        if deuda.estado != 'activa':
            # Reactivar: el permiso volvió a cubrir este mes (p. ej. tras editar el rango).
            deuda.estado = 'activa'
            cambios.append('estado')
        if cambios:
            deuda.save(update_fields=cambios + ['actualizado_en'])
            resumen['actualizadas'] += 1

    for clave, deuda in existentes.items():
        if clave in esperado:
            continue
        if _tiene_historia(deuda):
            if deuda.estado == 'activa':
                deuda.estado = 'cancelada'
                deuda.save(update_fields=['estado', 'actualizado_en'])
                resumen['canceladas'] += 1
        else:
            deuda.delete()
            resumen['borradas'] += 1

    recalcular_roll_up(permiso)
    return resumen


def recalcular_roll_up(permiso: PermisoEspecial) -> None:
    """
    Mantiene `permiso.pagado` / `fecha_pago` coherentes con sus obligaciones mensuales.

    El booleano del permiso deja de ser la fuente de verdad —lo es cada mes—, pero se
    conserva porque varias pantallas y consultas filtran por él. Aquí se deriva: un permiso
    está pagado cuando no le queda ningún mes con saldo.
    """
    deudas = [d for d in permiso.deudas_mes.all() if d.estado != 'cancelada']
    if not deudas:
        return

    pendiente = any(d.minutos_pendientes > 0 and d.estado == 'activa' for d in deudas)
    pagado = not pendiente
    fechas = [d.fecha_pago for d in deudas if d.fecha_pago]
    fecha_pago = max(fechas) if (pagado and fechas) else None

    if permiso.pagado != pagado or permiso.fecha_pago != fecha_pago:
        permiso.pagado = pagado
        permiso.fecha_pago = fecha_pago
        permiso.save(update_fields=['pagado', 'fecha_pago', 'actualizado_en'])


def asegurar_deudas(explorador) -> None:
    """
    Red de seguridad: crea las obligaciones que falten de los permisos aprobados de alguien.

    El sistema se autocura igual que la sanción por deuda. Sin esto, un permiso aprobado
    por una vía que no llamara a `sincronizar` quedaría invisible para el cobro y para la
    sanción, y nadie se enteraría hasta que el explorador reclamara.
    """
    if not explorador:
        return
    permisos = (
        PermisoEspecial.objects
        .filter(empleado=explorador, estado__in=ESTADOS_CON_DEUDA, deudas_mes__isnull=True)
        .distinct()
    )
    for permiso in permisos:
        try:
            sincronizar(permiso)
        except Exception:
            logger.exception('No se pudieron crear las deudas mensuales del permiso %s',
                             permiso.id)
