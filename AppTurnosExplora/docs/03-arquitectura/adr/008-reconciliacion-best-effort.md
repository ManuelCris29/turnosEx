# ADR 008: la reconciliación tras cancelar es una reparación best-effort, no una validación

**Estado:** Implementado
**Fecha:** 2026-08

## Contexto

Cancelar una solicitud aprobada no es solo deshacer sus turnos. Varias solicitudes pueden haber
tocado los mismos días encimadas unas sobre otras, y en este sistema rige el principio de que **la
última aprobada gana el día**. Al retirar una pieza del medio, el estado de esos días queda mal.

Por eso la cancelación tiene dos tiempos: restaurar `snapshot_turnos_previos`, y después
**reconciliar** — re-aplicar, en orden cronológico de aprobación, el efecto de las solicitudes que
siguen aprobadas sobre las fechas afectadas
(`solicitudes/services/doblada_snapshot_service.py:279`).

Tres hechos, ninguno negociable por separado, se combinan en un problema:

1. **La reconciliación re-aplica SIN re-validar.** Se asume que lo aprobado ya fue válido en su día.
2. **Los servicios de aplicación validan sus propias precondiciones** antes de escribir turnos
   (patrón #39 de `PROTECTION_PATTERNS.md`: *"no le inventes un turno a quien ese día descansa"*).
   Esa guardia existe justamente porque su ausencia no reventaba: escribía un dato incorrecto.
3. **El conjunto de días se AMPLÍA más allá de los de la solicitud cancelada.** Varios
   re-aplicadores reescriben su efecto completo —un CAMBIO DESCANSO de fin de semana reescribe los
   dos findes; una D FDS, cesión *y* pago—, así que `_cerrar_afectados`
   (`doblada_snapshot_service.py:179`) añade esos días colaterales. Sin ese cierre, el efecto de
   solicitudes vigentes se perdía en silencio.

De ahí la colisión: al recolocar una solicitud vieja sobre un calendario que ha cambiado (temporada,
mantenimiento, otras cancelaciones), su guardia de negocio puede levantar `ValidationError` **con
toda la razón**. Y esa solicitud vive en días colaterales que **ninguna guardia de entrada
examinó**: ni la LIFO (solo mira otras solicitudes aprobadas después, sobre los días propios) ni la
de integridad por snapshot (`use_cases/cancelar_solicitud.py:290-353`, compara el estado real contra
lo que *esta* solicitud dejó).

Antes de esta decisión, ese `ValidationError` subía y **abortaba la transacción entera**. El usuario
no podía cancelar por culpa de una solicitud ajena: de otra persona, aprobada semanas atrás, en días
que ni siquiera aparecen en su pantalla. Y a diferencia del bloqueo LIFO —que dice *"cancela primero
la última"*—, este **no ofrecía ninguna salida**: no había nada que el usuario pudiera cancelar,
arreglar ni ver.

## Decisión

La reconciliación se trata como **reparación**, no como validación: recoloca lo que puede, registra
lo que no, y termina.

En el bucle de `reconciliar_dobladas_aprobadas` (`doblada_snapshot_service.py:332-343`):

1. Cada candidata se re-aplica dentro de un `try`.
2. Se captura **solo `ValidationError`** — precondición de negocio incumplida. Cualquier otro fallo
   (BD, programación) sigue propagándose y aborta, porque ahí sí conviene parar y que se note.
3. El `except` registra a nivel **ERROR** el id, el tipo, las fechas y el motivo, diciendo
   explícitamente que el efecto queda sin materializar y hay que revisarlo a mano.
4. Se continúa con las demás candidatas.

### El detalle que sostiene la auditoría: `reaplicadas.add` va FUERA del `try`

La solicitud omitida **no** entra en el conjunto de reaplicadas
(`doblada_snapshot_service.py:343`). Importa más de lo que parece: al final, `refrescar_resultantes`
(`:525`) recalcula `snapshot_turnos_resultantes` de lo que se re-aplicó. Si la omitida se marcara
como procesada, se le grabaría **el estado roto como propio** y a partir de ahí ni la guardia de
integridad de su futura cancelación ni el auditor verían discrepancia alguna: la inconsistencia se
volvería invisible. Es exactamente el modo de fallo que ya se sufrió con la D FDS #554
(`management/commands/verificar_efecto_aplicado.py:96-102`).

### Qué NO relaja esta decisión

Las guardias de **entrada** siguen intactas y siguen bloqueando:

| Guardia | Cuándo | Qué hace |
|---|---|---|
| LIFO | Antes de cancelar | Si hay una aprobada después sobre tus días, exige cancelar esa primero |
| Integridad por snapshot | Antes de cancelar | Si alguien tocó tus días por otra vía, bloquea **sin opción de forzar** (`cancelar_solicitud.py:305-307`) |
| Best-effort (este ADR) | Después, ya autorizada | Recoloca lo vigente; omite y registra lo que no encaja |

Las dos primeras bloquean **con una salida clara**. La tercera actúa donde un bloqueo no tendría
ninguna.

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Dejarlo como estaba (todo o nada) | Deja al usuario en un callejón sin salida por una solicitud ajena que no puede ver ni arreglar. La consistencia se preservaba a costa de hacer la cancelación inoperante |
| Capturar `Exception` en vez de `ValidationError` | Se tragaría bugs de programación y fallos de BD en silencio, justo en el código que reescribe turnos. La lista de excepciones capturadas *es* la frontera entre "esta pieza no encaja" y "el código está roto" |
| Re-validar cada solicitud antes de re-aplicarla, y descartar las inválidas de forma limpia | Es la opción teóricamente correcta y sigue siendo el destino deseable. Hoy no es viable: la validación de varios tipos consulta `estado_dia`, que **ya atribuye el descanso a la propia solicitud en curso**, de modo que una solicitud legítima se declararía inválida a sí misma (mismo obstáculo documentado en el patrón #39 para las ramas sin guardia). Exige poder excluir la solicitud en curso de `estado_dia`, que hoy no admite ese parámetro |
| Cancelar en cascada las solicitudes que ya no encajan | Convierte una cancelación en una demolición: el usuario que cancela lo suyo tumbaría solicitudes ajenas ya aprobadas, sin que nadie lo pida ni lo apruebe |
| Bloquear y decirle al usuario qué cancelar primero, como hace la LIFO | No hay respuesta que dar: la solicitud conflictiva es de otra persona y está en días que no salen en su pantalla. Un mensaje sin acción posible es ruido |
| Marcar automáticamente la solicitud omitida como `cancelada` o `invalida` | Cambia el estado de una solicitud aprobada de otro usuario sin intervención humana, y en la ruta menos observada del sistema. La corrección exige criterio: se deja a una persona |
| Reintentar la pieza omitida al final, por si el estado cambió | El orden de re-aplicación **es** la semántica (última aprobada gana el día). Reintentar fuera de orden produce un estado distinto del que reconstruye la pasada única |

## Consecuencias

- **La cancelación deja de ser rehén de solicitudes ajenas.** Cubierto por
  `solicitudes/tests/test_matriz_dobladas.py:3072`
  (`test_una_doblada_que_ya_no_encaja_no_impide_cancelar_otra`).
- **Contrapartida aceptada: consistencia diferida.** La solicitud omitida queda **aprobada pero con
  su efecto sin materializar** en los turnos. Es una inconsistencia real, elegida a conciencia
  frente a un bloqueo sin salida.
- **Esa contrapartida es auditable y reparable**, y no depende de que alguien lea los logs:
  `python manage.py verificar_efecto_aplicado` lista las solicitudes aprobadas cuyo efecto ya no
  está en los turnos, y `--reparar` las re-materializa. Funciona precisamente porque el resultante
  de la omitida no se refrescó (ver arriba).
- **La reparación no puede pisar una decisión deliberada del supervisor.** Un día ANULADO por
  inasistencia también tiene los turnos distintos de lo que dejó su solicitud, pero eso no es un
  descuadre: es que la persona no cumplió, el turno quedó en soft-delete y la deuda vive en la
  `ReprogramacionDiaDoblada`. Reconciliar RE-CREA turnos, así que repararlo deshacía la anulación y
  dejaba la reprogramación pendiente sin día que compensar. El comando descarta esos días vía
  `ReprogramacionDobladaService.dias_anulados_por_inasistencia`, que decide por la reprogramación
  vigente y no por el texto libre de `motivo_anulacion`. Cubierto por
  `solicitudes/tests/test_reprogramacion_doblada.py::DiaAnuladoNoEsDescuadreTest`. Medido sobre la
  base de desarrollo: 3 de las 11 solicitudes marcadas eran anulaciones deliberadas.
- **El log de ERROR es la señal en caliente**, con id, tipo, fechas y motivo: suficiente para
  reparar a mano sin reconstruir el caso.
- El invariante queda registrado como patrón #40 en `PROTECTION_PATTERNS.md`, con los dos avisos que
  lo protegen: no ampliar el `except` a `Exception`, y no aplicar best-effort en fase de validación.

## Pendiente

- **Alertar sin que nadie mire.** Hoy el descuadre se descubre ejecutando el comando o leyendo el
  log. Conviene una alarma de CloudWatch sobre el patrón `Reconciliación:` del log de ERROR
  (el grupo y el filtrado por `request_id` ya existen, [ADR 007](./007-paginas-de-error-propias-y-request-id.md)),
  o `verificar_efecto_aplicado` en una tarea programada.
- **El camino limpio sigue abierto:** permitir a `estado_dia` excluir una solicitud concreta
  desbloquearía la re-validación previa y haría innecesario el best-effort. Es la misma pieza que
  falta para cerrar las ramas sin guardia del patrón #39: conviene abordarlas juntas.
