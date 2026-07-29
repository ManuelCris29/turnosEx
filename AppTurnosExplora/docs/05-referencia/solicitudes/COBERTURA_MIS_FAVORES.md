# Cobertura de "Mis Favores": qué formularios llegan a la pantalla

La pantalla `/solicitudes/mis-favores/` lista `DeudaExplorador`: el registro de "fulano trabajó
mi día y yo se lo devolví el día tal". La pregunta de este estudio es si los **6 formularios**
de solicitud dejan ahí el rastro que les corresponde, o si alguno genera un favor real que la
pantalla no puede ver.

## Criterio

Un formulario debe aparecer en Mis Favores cuando produce un **favor asimétrico con devolución
diferida**: alguien trabaja un día que no le tocaba, y la contrapartida ocurre *en otro momento*.
Ese desfase es justo lo que un explorador no puede reconstruir de memoria y necesita consultar.

No debe aparecer cuando la operación es una **permuta simétrica**: ambos ceden y ambos reciben
en el mismo acto de aprobación, sin que nadie quede a deber nada. Ahí no hay favor pendiente que
recordar, y meterlo en la lista solo la llenaría de ruido.

## Los 6 formularios

| Formulario | Qué hace | ¿Favor diferido? | ¿Registra `DeudaExplorador`? | Sale en Mis Favores |
|---|---|---|---|---|
| **CT** (cambio de turno) | Dos exploradores intercambian turno | No — permuta simétrica | No | No, y es correcto |
| **CT PERMANENTE** | Igual, repetido en un rango | No — permuta simétrica | No | No, y es correcto |
| **DOBLADA** | El receptor cubre media jornada; el solicitante la devuelve en la fecha pactada | **Sí** | Sí, `DobladaDeudaService` | ✅ Sí |
| **D FDS** | El receptor cubre un día de finde completo; se devuelve otro finde | **Sí** | Sí, `DFDSAplicacionService.generar_deudas` | ✅ Sí |
| **DOBLADA PERMANENTE** | N pares (cesión, devolución) a lo largo de un rango | **Sí** | Sí, `_deudas_entre_exploradores` (una por par) | ✅ Sí |
| **CAMBIO DESCANSO** | Se permutan los días de descanso de la semana | No — permuta simétrica | No | No, y es correcto |

## Por qué CT, CT PERMANENTE y CAMBIO DESCANSO se quedan fuera con razón

En `CambioDescansoAplicacionService.aplicar` el reparto es literalmente recíproco: en la fecha de
cesión el receptor trabaja y el solicitante descansa; en la de pago se invierte
([`cambio_descanso_aplicacion_service.py:360-377`](../../../solicitudes/services/cambio_descanso_aplicacion_service.py#L360-L377)).
Las dos mitades se aplican en la **misma transacción de aprobación**. No existe un instante en
que uno le deba algo al otro, y por eso el servicio solo registra la deuda corporativa de 30 min
cuando alguien acaba doblando. CT y CT PERMANENTE son el mismo patrón sobre turnos en vez de
descansos.

Es un hueco *aparente*, no real: la pantalla no debe listarlos.

## El hueco que había en DOBLADA PERMANENTE (ya cerrado)

`DobladaPermanenteAplicacionService.aplicar`
([`doblada_permanente_aplicacion_service.py:262-274`](../../../solicitudes/services/doblada_permanente_aplicacion_service.py#L262-L274))
aplica pares balanceados:

- **Cesión**: el receptor dobla, el solicitante descansa.
- **Devolución**: el solicitante dobla, el receptor descansa.

Eso es exactamente un favor con devolución diferida —la misma forma que la DOBLADA suelta— y
repetido N veces a lo largo de semanas o meses. Pero el servicio solo llamaba a `_deuda()`, que
crea `DeudaCorporativa` (los 30 min con la empresa): **nunca creaba `DeudaExplorador`**.

Consecuencia: un explorador con una doblada permanente de tres meses veía la pantalla vacía
aunque hubiera cubierto a alguien doce veces.

### Cómo quedó resuelto

`_deudas_entre_exploradores` crea **una `DeudaExplorador` por par (cesión, devolución)**. El
emparejamiento por índice es correcto porque `_calcular_ocurrencias(balancear=True)` ya recorta
ambos lados al mínimo común, así que `ocur_ces[i]` se salda siempre con `ocur_dev[i]`.

Decisiones que se tomaron, y por qué:

- **Una fila por par, no una por solicitud.** Es lo que el explorador quiere ver: "el lunes 3 me
  cubrió, se lo devolví el martes 4", doce veces. Una fila resumen perdería las fechas concretas,
  que son justo el dato que nadie recuerda de memoria.
- **Nace `pagada`**, con `fecha_pago_real` igual a la de devolución, porque la devolución se
  aplica en el mismo acto. Idéntico a la doblada suelta y coherente con "no existen dobladas
  abiertas".
- **La jornada cedida se lee ANTES de mutar los turnos.** Los bucles de aplicación le borran el
  turno al solicitante; leerla después daría siempre vacío.
- **Idempotencia**: la clave de `crear_deuda_idempotente` es
  `(solicitud, deudor, acreedor, fecha_pago_pactada)`. Cada par tiene una fecha de devolución
  distinta dentro del rango, así que re-aplicar la solicitud no duplica nada. Cubierto por
  `test_aplicar_dos_veces_no_duplica_los_favores`.
- **`reaplicar_fechas` no crea deudas** — solo re-materializa turnos pisados por la
  reconciliación. Las deudas de la solicitud ya existen y siguen siendo válidas.
- **Reversión**: `revertir()` marca `cancelada` las N deudas. Además, `signals.py` ya cancelaba
  cualquier `DeudaExplorador` por `solicitud_origen` al borrar o rechazar una solicitud, sin
  mirar el tipo, así que esos caminos quedaron cubiertos solos.

La vista de Mis Favores **no necesitó ni una línea**: ya leía cualquier `DeudaExplorador` y
muestra `tipo_cambio.nombre`, así que las filas salen etiquetadas "DOBLADA PERMANENTE".

Tests en `DobladaPermanenteFavoresTest`, incluido uno de extremo a extremo que aprueba la
solicitud y comprueba que el favor aparece en la pantalla de los dos exploradores: como recibido
en el del solicitante y como hecho en el del compañero.

## Caso límite ya cubierto: la deuda residual del sábado

Cuando una DOBLADA se paga en sábado cubriendo **AMBAS** jornadas, `DobladaDeudaService` crea una
**segunda** `DeudaExplorador` con deudor y acreedor invertidos sobre la *misma* `solicitud_origen`
([`doblada_deuda_service.py:79-87`](../../../solicitudes/services/doblada_deuda_service.py#L79-L87)).
El favor de esa fila no ocurrió el día de la cesión sino el sábado del pago. La vista lo detecta
comparando el deudor con `solicitud.explorador_solicitante` y toma `doblada.fecha_pago`; hay test
de regresión en `DeudaResidualSabadoTest`.
