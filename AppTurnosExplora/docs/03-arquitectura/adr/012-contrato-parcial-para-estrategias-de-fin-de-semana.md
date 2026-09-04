# ADR 012: Contrato parcial para las estrategias de fin de semana

**Estado:** Implementado
**Fecha:** 2026-09

## Contexto

`SolicitudStrategy` es la base de las seis estrategias de solicitud. Entre sus métodos
había dos que solo tienen sentido en los formularios de fin de semana:

- `disponibilidad_companero(candidato, fecha_cesion)` — ¿puede este compañero participar
  en un cambio sobre este sábado o domingo, y por qué no?
- `etiqueta_companero(candidato, fecha_cesion)` — el texto que explica por qué sí sirve.

Los llama un único sitio, `solicitudes/views/api_fin_semana.py`, y solo los necesitan
CAMBIO DESCANSO y D FDS. Las otras cuatro —CAMBIO TURNO, DOBLADA, CT PERMANENTE, DOBLADA
PERMANENTE— no tienen selector de compañeros de finde.

Estaban en la base **con la regla del INTERCAMBIO como comportamiento por defecto**, que
es la de CAMBIO DESCANSO. Eso producía dos problemas:

1. D FDS, cuya regla es la de la CESIÓN, tenía que sobrescribir a su propia base. Quien
   leía `base_strategy.py` no podía saber que ese "por defecto" era en realidad la regla
   de otro formulario.
2. Las otras cuatro heredaban una respuesta a una pregunta que no les corresponde. Y el
   endpoint acepta `?tipo_solicitud_id=` de **cualquier** tipo: pidiéndole los compañeros
   de un sábado con el id de DOBLADA, contestaba **200 con una lista verosímil** calculada
   con la regla del intercambio. No fallaba: acertaba a medias, en silencio.

La auditoría de arquitectura de 2026-09 señaló el síntoma —«el contrato de las strategies
mezcla dos oficios»— y recomendó partir `SolicitudStrategy` en dos interfaces,
`ISolicitudCicloVida` e `ISolicitudPantalla`.

## Decisión

**No se parte el contrato en dos interfaces.** Se saca de la base únicamente esos dos
métodos, a un contrato aparte que solo implementan las estrategias que lo necesitan:

`solicitudes/services/strategies/estrategia_fin_de_semana.py` define
`EstrategiaFinDeSemana` con los dos métodos **abstractos y sin implementación por
defecto** —no existe una regla común que sirva a ambos formularios—. Lo implementan
`CambioDescansoStrategy` (regla del intercambio, mudada desde la base, que es su dueña) y
`DFDSStrategy` (regla de la cesión, que ya tenía).

`api_fin_semana.py` comprueba el contrato con `isinstance` antes de preguntar, y responde
`400 tipo_sin_selector_finde` a un tipo que no lo implementa, en vez de una lista
inventada.

La división en dos interfaces se descartó **por medición, no por criterio**: las seis
estrategias implementan métodos de ambos lados —las seis tienen `validar_solicitud`,
`crear_solicitud` y `aplicar_cambios`, y las seis tienen `get_empleados_disponibles` y
`detalle`—. Dos interfaces que siempre se implementan juntas son una sola con más
ceremonia.

## Consecuencias

- **Una estrategia de finde nueva debe declarar `EstrategiaFinDeSemana` y escribir sus dos
  métodos.** No hereda una regla por descuido, que era el problema.
- **Las otras cuatro ya no pueden contestar** a una pregunta que no les corresponde. Lo
  que antes era una respuesta plausible ahora es un error explícito.
- **La base deja de tomar partido por un subtipo.** `SolicitudStrategy` ya no contiene la
  regla de CAMBIO DESCANSO.
- Es el primer contrato del proyecto que se reparte entre un **subconjunto** de las
  estrategias. Si aparecen más grupos así (por ejemplo, algo propio de los permanentes),
  este es el patrón a seguir antes que engordar la base.
- `test_contrato_fin_de_semana.py` fija las tres propiedades: que solo las dos lo
  implementan, que la base ya no responde por nadie, y que **cada formulario conserva una
  regla distinta** —si alguien las unifica "para no repetir código", el intercambio y la
  cesión volverían a compartir criterio, que es de lo que se venía.

## Alternativas descartadas

- **`ISolicitudCicloVida` + `ISolicitudPantalla`**, como pedía la auditoría. Medido, no
  separa nada: las seis estrategias implementan ambos lados. Habría añadido dos nombres y
  ninguna frontera, y habría dejado intacto el problema real —que la base contenía la
  regla de un subtipo—.
- **Dejar los dos métodos en la base y que las cuatro que no los usan lancen
  `NotImplementedError`.** Convierte un error de diseño en un error de ejecución: el
  endpoint seguiría pudiendo llamarlos, solo que reventando en vez de mintiendo. Con
  `isinstance` la comprobación ocurre antes, y la respuesta es un mensaje que el usuario
  entiende.
- **Unificar las dos reglas en una sola implementación compartida.** Es justo el estado
  del que se venía: la regla del intercambio aplicada también a la cesión, que dejaba
  fuera del selector a quien descansa los dos días del finde —precisamente a quien sí se
  le puede ceder—.
