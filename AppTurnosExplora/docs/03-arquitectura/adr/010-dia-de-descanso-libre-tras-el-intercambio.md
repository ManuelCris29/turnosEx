# ADR 010 — El día de un cambio de descanso queda libre en cuanto se aplica

- **Estado:** Implementado
- **Fecha:** 2026-08
- **Ámbito:** `solicitudes` — CAMBIO DESCANSO (fin de semana) y el selector de findes

## Contexto

`CambioDescansoAplicacionService.dia_bloqueado_para_nuevo_cambio` decide si una fecha está
disponible para un **nuevo** cambio de descanso. Es la fuente única que comparten el selector de
findes (`solicitudes/views/api_fin_semana.py:358`) y la validación del backend
(`CambioDescansoStrategy._trabaja_dia`, `solicitudes/services/strategies/cambio_descanso_strategy.py:111`),
para que el formulario y el envío no se contradigan.

Hasta esta decisión, la función tenía tres ramas: la del bloqueo permanente por **otro tipo** de
cambio, y dos que miraban una **ventana temporal** tras un CAMBIO DESCANSO previo —una recorriendo
las solicitudes en ventana por el lado que pasa a trabajar, otra vía `_mapa_descanso(dentro_ventana=True)`
por el lado que pasa a descansar—. Su premisa: *mientras el cambio previo siga siendo revertible,
reutilizar el día puede romper ese revert; pasada la ventana, el día es reutilizable sin riesgo*.

Esa premisa dependía de que la cancelación fuera **inmediata y de 30 minutos**. El
[ADR 009](./009-cancelacion-consensuada.md) la convirtió en un acuerdo de dos pasos con **dos
plazos de 24 horas**. Mantener las dos reglas alineadas habría significado congelar cada día
intercambiado **24 horas** para toda la plantilla.

## Decisión

**Se protege la elección de día de descanso, no la reversibilidad.**

`dia_bloqueado_para_nuevo_cambio` se reduce a **una sola regla**: hay un `Turno` ese día con
`tipo_cambio` **distinto** de `'CAMBIO DESCANSO'` (DOBLADA, D FDS, CT…) → bloqueado, siempre y sin
ventana. Cualquier otra cosa → libre. Un CAMBIO DESCANSO previo **no bloquea nada**: el día vuelve
a estar disponible desde el primer minuto, coherente con el principio "la última aprobada gana por
día" (manual técnico § 8.2, P1).

La implementación es un único `Turno.objects...exists()`
(`solicitudes/services/cambio_descanso_aplicacion_service.py:228-232`); la función pasó de ~50
líneas a esa consulta.

## Consecuencias

- Un finde ya intercambiado se puede volver a intercambiar en cualquier momento. Ningún día queda
  congelado 24 horas para el resto de la plantilla.
- **Contrapartida asumida:** si alguien reutiliza el día mientras la cancelación anterior sigue
  viva, la **guardia LIFO** impedirá revertirla — la petición de cancelación se rechazará porque
  hay un cambio más reciente sobre esas fechas. Es un intercambio consciente, no un descuido: está
  escrito en el docstring de la función
  (`solicitudes/services/cambio_descanso_aplicacion_service.py:201-224`).
- **No se reintroduzca el bloqueo sin revisar esta decisión.** Es una zona frágil: manual técnico
  § 16.2. El centinela es
  `CDReintercambioDiaTest.test_dia_bloqueado_para_nuevo_cambio_directo`
  (`solicitudes/tests/test_cambio_descanso.py:312`), que comprueba **los dos lados** del
  intercambio justo después de aplicar.
- `dia_bloqueado_para_nuevo_cambio` conserva el parámetro `excluir_id` por compatibilidad con las
  llamadas existentes (re-validación de la propia solicitud al aprobar), pero **hoy no hace nada**:
  el criterio mira turnos, no solicitudes.

## Eliminaciones asociadas

| Qué se borró | Dónde estaba | Por qué |
|---|---|---|
| `VENTANA_CANCELACION_MINUTOS = 30` | `solicitudes/services/cambio_descanso_aplicacion_service.py` | Sostenía el bloqueo retirado |
| `VENTANA_CANCELACION_MINUTOS = 30` | `solicitudes/use_cases/cancelar_solicitud.py` | Código muerto desde el ADR 009: sin ningún uso |
| Parámetro `dentro_ventana` | `_mapa_descanso` y `_mapa_descanso_multi` (firmas y filtro) | Solo existía para ese cálculo |
| Segundo mensaje de bloqueo ("cambio de descanso reciente") | `cambio_descanso_strategy.py` | Inalcanzable con la regla única |

La constante **ya no existe en el proyecto**: con eso se cierra el bug **B13** del manual técnico
(§ 16.4) por **eliminación**, no por el renombrado que se anticipaba.

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Alinear el bloqueo con las 24 h de la cancelación | Congela el día un día entero para toda la plantilla por proteger un caso minoritario |
| Bloquear solo si hay una petición de cancelación viva sobre ese día | Añade a la validación una consulta sobre el estado de cancelación de terceros; el día seguiría bloqueándose de forma impredecible para quien elige |
| Renombrar la constante y conservar la regla | La regla misma era la que había dejado de tener sentido |

## Referencias

- [ADR 009](./009-cancelacion-consensuada.md) — la cancelación consensuada que invalidó la premisa.
- Manual técnico § 8.3 (regla), § 16.2 (zona frágil), § 16.4 (B13 cerrado).
- Tests: `solicitudes/tests/test_cambio_descanso.py:254` (`CDReintercambioDiaTest`).
