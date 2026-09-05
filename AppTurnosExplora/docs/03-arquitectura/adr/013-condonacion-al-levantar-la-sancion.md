# ADR 013 — Levantar una auto-sanción por deuda condona la deuda del mes que la originó

- **Estado:** Implementado
- **Fecha:** 2026-09
- **Ámbito:** `empleados` (`SancionEmpleado.levantar`), `solicitudes` (`DeudaCorporativa`,
  `DeudaCorporativaService`), `permisos` (`DeudaPermisoMes`, PDH)
- **Enmienda:** corrige el punto 3 del [ADR 011](./011-sancion-independiente-del-pago.md)
  ("una sanción levantada a mano no salda nada"), que dejaba un estado sin salida.

## Contexto

El ADR 011 dejó la deuda del mes en manos de dos mecanismos: se paga (PDH) o la extingue la
sanción **cumplida** (`consumida_por_sancion`). El tercer final —el supervisor **levanta** la
sanción— no tenía dueño, y la deuda de ese mes quedaba en un limbo permanente. Las tres
puertas cerradas a la vez:

1. **No se puede pagar.** El mes que originó la sanción ya venció, y `Periodo.esta_vencido`
   cierra el PDH sobre él (`solicitudes/services/sancion_deuda_calculo.py:99`).
2. **Esa sanción no la consumirá nunca.** El consumo solo mira sanciones cumplidas y sin
   levantar: filtra por `levantada_en__isnull=True`
   (`solicitudes/services/deuda_corporativa_service.py:101`, filtro en `:126`).
3. **No nacerá otra sanción que la consuma.** `_periodos_ya_evaluados` cuenta las levantadas
   como mes ya juzgado —a propósito: recrear la sanción anularía el botón del supervisor—
   (`solicitudes/services/deuda_corporativa_service.py:273-294`).

Resultado: horas `activa` para siempre, ni cobrables ni saldables, engordando el saldo del
explorador sin ninguna forma de bajarlo.

## Decisión

**Levantar perdona el hecho entero, no solo el castigo.** Si el motivo del levantamiento era
una excusa certificable, no hay falta que cobrar. La deuda del mes pasa a un estado nuevo,
`'condonada'`, con la sanción responsable y la fecha.

### 1. Estado propio, ni `cancelada` ni `consumida_por_sancion`

`'condonada'` se añade a `solicitudes.DeudaCorporativa.ESTADO_CHOICES`
(`solicitudes/models.py:715`, motivo comentado en `:709-714`) y a
`permisos.DeudaPermisoMes.ESTADO_CHOICES` (`permisos/models.py:249`, motivo en `:246-248`).

- No es `'cancelada'`: cancelar es una **corrección técnica** (deuda huérfana, fin de semana
  deshecho). Esto es una decisión disciplinaria con un responsable detrás. Fundirlas haría
  ilegible cualquier informe de condonaciones.
- No es `'consumida_por_sancion'`: aquella la paga el **castigo cumplido**; esta no la paga
  nadie.
- No es `'pagada'`: no hubo PDH.

La trazabilidad reutiliza los campos que ya existían, `sancion_consumidora` y `fecha_consumo`
(`solicitudes/models.py:764,767`; `permisos/models.py:274,277`). La sanción responsable es una
sola en ambos casos, y es el `estado` el que dice cuál de las dos cosas ocurrió.

### 2. El disparador vive en `levantar()`, no en la vista

`SancionEmpleado.levantar()` llama a
`DeudaCorporativaService.condonar_deudas_por_levantamiento` dentro de su propia
`transaction.atomic` (`empleados/models.py:409`, llamada en `:438`). Es el **único** punto de
entrada al levantamiento. Si viviera en el llamador, cada nueva forma de levantar —un proceso
automático, un comando de gestión, el admin— tendría que acordarse de repetirla, y la que se
olvidara reabriría exactamente este limbo.

Todo o nada: si la condonación falla, el levantamiento tampoco se guarda. Media operación aquí
es el estado incoherente que se quiere evitar.

### 3. Alcance: solo auto-sanciones, solo su mes

`condonar_deudas_por_levantamiento` (`solicitudes/services/deuda_corporativa_service.py:181`)
actúa solo si la sanción está levantada y tiene `periodo_anio`/`periodo_mes` (guardas en
`:212-215`). Una sanción **manual** no tiene periodo —no nació de un mes impagado— y no
condona nada. Y se condona el mes que originó la sanción, no el expediente: las deudas de
otros meses siguen `activa`.

Es **idempotente**: toca solo lo que sigue `'activa'` (`:218-236`), así que un doble clic o un
reintento no condonan nada nuevo ni reescriben quién lo hizo. Después recalcula el roll-up de
los permisos afectados (`:241-249`), porque `PermisoEspecial.pagado` es un agregado que vive
aparte de sus meses.

### 4. Una auto-sanción se reconoce por su periodo, y eso vale para TODAS las consultas

El `motivo` es texto libre y **editable** desde la pantalla de edición de sanciones; el
periodo es un dato del ledger que nadie retoca. La detección por el prefijo del motivo era
frágil, y no solo aquí: la misma consulta se repetía en las siete decisiones del subsistema.
Retocar la redacción de una sanción automática la volvía invisible para todas a la vez, con
**dos** daños encadenados —su deuda no se consumía al cumplirse el castigo, y su mes dejaba
de contar como juzgado, así que el sistema podía sancionar **por segunda vez** un mes ya
castigado—.

El criterio queda en dos `Q` de clase, declaradas una sola vez y con el porqué junto a ellas
(`solicitudes/services/deuda_corporativa_service.py:58-69`):

```python
ES_AUTOMATICA = Q(periodo_anio__isnull=False)
ES_MANUAL = Q(periodo_anio__isnull=True)
```

Las usan `_consumir_deudas_de_sanciones_cumplidas` (`:137`), `_periodos_ya_evaluados`
(`:386`), `contar_pendientes_de_sancion` (`:574`), las tres de `auditar_morosos` (`:731`,
`:740`, `:777`) y la de `revisar_todos` (`:828`). `_antecedente` (`:340`) queda fuera a
propósito: cuenta **cualquier** sanción, también las manuales, como ya decidió el ADR 011. El prefijo
`AUTO_SANCION_PREFIJO` (`:56`) se sigue **escribiendo** en el motivo (`:497`), pero solo como
etiqueta para quien lo lee: ninguna decisión depende ya de él. La comprobación previa de la
pantalla usa el mismo criterio a propósito (`empleados/views/sanciones.py:168-169`): si
divergieran, el aviso prometería unas horas y se perdonarían otras.

Lo fijan `test_condona_aunque_se_haya_editado_el_motivo` (`:318`) y
`test_editar_el_motivo_no_reabre_el_ciclo_de_sanciones` (`:339`), ambos en
`solicitudes/tests/test_consumo_deuda_por_sancion.py`.

### 5. Lo que se cuenta después del hecho se lee de lo escrito, no se recalcula

`horas_condonadas_por(sancion)` (`solicitudes/services/deuda_corporativa_service.py:258`) suma
las deudas ya marcadas (`sancion_consumidora=sancion, estado='condonada'`) en las dos tablas.
Es la fuente de verdad del mensaje al supervisor (`empleados/views/sanciones.py:316`) y del
aviso al explorador. La estimación previa que pinta el recuadro ámbar sigue existiendo, pero
queda acotada a eso: `_horas_que_se_condonan` (`empleados/views/sanciones.py:149`). Antes
ambos números salían del mismo cálculo repetido y podían discrepar si entraba un pago entre
que se pinta el formulario y se envía: se anunciaba una cifra y se perdonaba otra.

### 6. El explorador se entera por la campana

`notificar_condonacion(sancion, horas)` (`:282`) crea una `Notificacion` (`:328-334`) por la
campana, la misma vía por la que se enteró de la sanción, para que las dos mitades de la
historia lleguen por el mismo sitio. **Tipo propio, `'sancion_levantada'`** (`:330`), añadido a
`Notificacion.TIPOS_CHOICES` (`solicitudes/models.py:22`): la campana pinta el icono según el
tipo, y compartiendo `'sancion'` el aviso de que te **levantan** el castigo salía con el mismo
triángulo rojo de peligro que el de que te sancionan (`:18-21`; icono en
`templates/solicitudes/notificaciones_list.html:65-68`). Se dispara desde `levantar()` **dentro
de la misma transacción** (`empleados/models.py:442-443`, motivo comentado en `:439-441`): si el levantamiento no llega a guardarse,
tampoco puede quedar un aviso diciendo que sí. Nunca lanza, igual que `_notificar_sancion`: un
fallo avisando no puede tumbar un levantamiento ya decidido. Avisa también cuando **no** hubo
horas que condonar, con otro texto. Tests:
`test_al_levantar_se_avisa_al_explorador_por_la_campana` (`:362`) y
`test_se_avisa_al_explorador_aunque_no_hubiera_horas_que_condonar` (`:385`).

### 7. Se perdona la deuda, no el expediente

El antecedente de reincidencia **no se toca**. `_periodos_ya_evaluados` (`:369`) y `_antecedente`
(`:340`) siguen viendo la sanción levantada, así que la escalada del ADR 011 se
mide igual. Lo que desaparece es el saldo, no el historial.

## Consecuencias

**A favor:**

- Desaparece el estado sin salida: tras levantar no queda deuda vencida que arrastrar ni mes
  que vuelva a sancionar.
- Un informe puede separar tres finales distintos con solo leer el `estado`: pagado, cumplido,
  perdonado.
- El consolidado de horas puede explicar la extinción en vez de hacerla desaparecer:
  `_extinguidas_por_sancion` (`turnos/services/consolidado_horas_service.py:75`) agrupa las
  deudas por la sanción responsable y separa las dos vías con la marca `condonada` (`:137`).
  Expone `extinguidas_sancion` y `total_extinguido_sancion` (`:302-303`) — nombres alineados
  con lo que ya decía la pantalla: **extinguido**, no *saldado*, porque nadie pagó.
- El explorador se entera del perdón por la campana en vez de tener que entrar al Consolidado
  de Horas a descubrirlo.

**En contra, asumido:**

- **Levantar cuesta dinero.** El supervisor perdona horas reales, no solo días de bloqueo. Se
  mitiga avisándolo **antes** de confirmar: la pantalla de levantamiento calcula las horas que
  se van a perdonar con `_horas_que_se_condonan` (`empleados/views/sanciones.py:149`, contexto
  en `:289`) —una lectura que replica el alcance del servicio sin ejecutar nada y nunca lanza:
  un fallo contando no puede impedir levantar una sanción—. El mensaje **posterior** ya no
  repite esa estimación: lee lo realmente escrito con `horas_condonadas_por` (`:316`, motivo
  comentado en `:312-314`) y avisa además de que se notificó al explorador (`:319-321`).
- **No se deshace.** No hay operación inversa que devuelva la deuda a `'activa'`. Coherente con
  el resto del dominio: un hecho registrado no se borra.
- **Efecto colateral sobre el recálculo.** `'condonada'` obliga a tratarse como hecho ocurrido
  en dos sitios más, o el perdón se revierte por la puerta de atrás:
  `_tiene_historia` en `permisos/deuda_permiso_service.py:44` (no se recalcula, `:54-55`) y el
  revert de PDH en `permisos/pago_horas_service.py:387` (no resucita al borrar un pago).

## Alternativas descartadas

- **Arreglar solo la condonación y dejar el prefijo en las demás consultas.** Fue el
  estado intermedio, y duró poco: dejaba dos criterios de "esto es automático" conviviendo,
  y el peor de los dos seguía decidiendo si un mes ya estaba juzgado.

- **Marcar la deuda como `'cancelada'`.** Un solo estado menos, pero mezcla la corrección
  técnica con la decisión disciplinaria; a los tres meses nadie sabe cuál fue cuál.
- **Reutilizar `'consumida_por_sancion'`.** Diría que el castigo se pagó cumpliéndolo, que es
  justo lo que no pasó. Haría creer que basta con que te levanten una sanción para no cumplir
  ninguna.
- **Condonar desde la vista de levantamiento.** Más simple de leer, pero deja la regla fuera
  del único punto de entrada: cualquier vía futura de levantar la olvidaría.
- **Permitir pagar un mes ya vencido tras levantar la sanción.** Reabre el PDH sobre periodos
  cerrados y contradice el vencimiento del ADR 011.
- **Dejar de contar las levantadas en `_periodos_ya_evaluados`** para que naciera otra sanción
  que consumiera la deuda: la sanción levantada volvería a nacer en el acto y el botón del
  supervisor se anularía solo.

## Migraciones

`permisos/migrations/0011_alter_deudapermisomes_estado_and_more.py` y
`solicitudes/migrations/0039_alter_deudacorporativa_estado_and_more.py`, más
`solicitudes/migrations/0040_alter_notificacion_tipo.py` para el tipo de notificación nuevo.
Solo `AlterField` sobre `estado`, su tabla histórica y `Notificacion.tipo`: Django trata `choices` como un atributo que **no** vive en
la base (`non_db_attrs`), así que no generan `ALTER TABLE` ni pueden fallar sobre datos
existentes. No hay backfill: ninguna fila anterior es `'condonada'`.

## Tests

- `ConsumoDeudaPorSancionTest` (`solicitudes/tests/test_consumo_deuda_por_sancion.py:28`):
  `test_una_sancion_levantada_no_consume_la_deuda_la_condona` (`:145`),
  `test_levantar_no_deja_deuda_pendiente_ni_reabre_sancion` (`:174`),
  `test_condonar_es_idempotente` (`:192`),
  `test_levantar_no_toca_la_deuda_de_otros_meses` (`:208`),
  `test_una_sancion_manual_levantada_no_condona_nada` (`:226`),
  `test_condona_aunque_se_haya_editado_el_motivo` (`:318`),
  `test_editar_el_motivo_no_reabre_el_ciclo_de_sanciones` (`:339`),
  `test_al_levantar_se_avisa_al_explorador_por_la_campana` (`:362`),
  `test_se_avisa_al_explorador_aunque_no_hubiera_horas_que_condonar` (`:385`),
  `test_levantar_condona_tambien_la_deuda_mensual_de_un_permiso` (`:297`).
- `SancionAutomaticaPorDeudaTest`
  (`solicitudes/tests/test_sancion_automatica_deuda.py:29`):
  `test_una_sancion_levantada_condona_la_deuda_y_no_renace` (`:257`).
- `turnos/tests/test_consolidado_extinguido_sancion.py`: el consolidado separa lo cumplido de
  lo condonado y cuadra el total.
