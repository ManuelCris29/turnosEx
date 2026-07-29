"""
Bloqueo de las PARTES (exploradores) de una solicitud.

Por qué existe
--------------
Aprobar o cancelar una solicitud lee el estado de unos días (¿descansa?, ¿ya tiene un cambio?,
¿jornadas contrarias?) y acto seguido ESCRIBE turnos sobre esos mismos días. Entre la lectura y
la escritura no puede colarse nadie.

El `select_for_update()` que ya hacían ambos flujos bloquea la fila de la SOLICITUD, y eso
resuelve el doble clic sobre la misma solicitud. Pero no cubre el caso real: dos solicitudes
DISTINTAS que comparten un explorador, aprobadas a la vez. Cada transacción bloquea su propia
fila, ninguna espera a la otra y —bajo REPEATABLE READ, que es el nivel por defecto de MySQL—
ninguna ve los turnos que la otra todavía no ha confirmado. Las dos re-validan contra una foto
del mundo anterior, las dos concluyen que el día está libre y las dos escriben: el día acaba con
dos cambios superpuestos que la validación existía precisamente para impedir.

Qué hace
--------
Bloquea las filas `Empleado` de todos los implicados. Como TODA aprobación y TODA cancelación
pasan por aquí, dos operaciones que compartan explorador quedan serializadas: la segunda espera
a que la primera confirme y entonces re-valida viendo ya sus turnos.

Orden determinista (por `id` ascendente) para no crear interbloqueos: si dos transacciones piden
los mismos dos exploradores en orden contrario, cada una retiene lo que la otra necesita y el
motor mata a una. Pidiéndolos siempre en el mismo orden, eso no puede ocurrir.
"""


def bloquear_partes(solicitud) -> None:
    """
    Toma un lock de escritura sobre los exploradores implicados en `solicitud`.

    Debe llamarse DENTRO de una transacción y ANTES de re-validar: un lock tomado después de
    leer no protege de nada. El bloqueo se mantiene hasta que la transacción más externa
    confirma, aunque esta función abra su propio `atomic()` (los `atomic()` anidados son
    savepoints; los locks no se liberan al cerrarlos).

    Incluye al solicitante, al receptor y al `empleado_receptor` de los detalles que lo llevan
    (doblada, doblada permanente), que puede diferir del receptor de la cabecera.
    """
    from django.db import transaction
    from empleados.models import Empleado

    ids = {
        getattr(solicitud, 'explorador_solicitante_id', None),
        getattr(solicitud, 'explorador_receptor_id', None),
    }
    for rel in ('doblada', 'doblada_permanente'):
        detalle = getattr(solicitud, rel, None)
        if detalle is not None:
            ids.add(getattr(detalle, 'empleado_receptor_id', None))

    ids = sorted(i for i in ids if i)
    if not ids:
        return

    with transaction.atomic():
        # `order_by('id')` es la parte que evita el interbloqueo, no un detalle cosmético.
        # Se fuerza la evaluación del queryset: sin consumirlo, la consulta —y por tanto el
        # lock— nunca llegaría a ejecutarse.
        list(Empleado.objects.select_for_update().filter(id__in=ids).order_by('id'))
