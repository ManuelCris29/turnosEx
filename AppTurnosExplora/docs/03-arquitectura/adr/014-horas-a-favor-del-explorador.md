# ADR 014 — Las horas a favor del explorador son una bolsa, y no tocan la sanción

- **Estado:** Implementado
- **Fecha:** 2026-09
- **Ámbito:** `permisos` (`CreditoHoras`, `ConsumoCreditoHoras`, `CreditoHorasService`, PDH),
  `empleados` (CRUD y formulario), `turnos` (consolidado de horas), `core` (sesión de menú)
- **Relación:** no enmienda ningún ADR. Añade la dirección contraria del ledger que describen
  el [ADR 011](./011-sancion-independiente-del-pago.md) y el
  [ADR 013](./013-condonacion-al-levantar-la-sancion.md), **sin alterar** ninguna de sus reglas.

## Contexto

Todo el sistema de horas se construyó en una sola dirección: lo que el explorador debe a la
corporación. No era un descuido, estaba escrito como invariante en el propio modelo —
`DeudaPermisoMes.minutos_pendientes` devuelve `max(0, generados - pagados)` con el comentario
*"Nunca negativo: un exceso no genera crédito"* (`permisos/models.py:303-305`)— y reforzado en
el servicio de pago, que **rechaza** un abono mayor que lo pendiente en lugar de dejar saldo
(`permisos/pago_horas_service.py:264-266`).

Pero el hecho contrario ocurre en la operación diaria. El caso típico: la jornada de un
explorador va de 08:00 a 14:00 y su supervisor le pide entrar a las 07:00. Esa hora se la
deben. Y como no había dónde anotarla, el desenlace era siempre el mismo: si esa persona tenía
media hora de deuda encima, se le compensaba de palabra al saldarla y **la media hora restante
desaparecía**. No quedaba registro, ni forma de reclamarla, ni manera de que el consolidado la
reflejara.

Tres cosas que el sistema no podía representar:

1. Un saldo a favor que **sobreviva** al pago que lo consumió parcialmente.
2. Quién reconoció esas horas y por qué —la trazabilidad que sí tiene cualquier deuda.
3. Un consolidado que admita que la cuenta puede cerrar en negativo para la corporación.

## Decisión

### 1. Es una bolsa, no un ajuste contra una deuda concreta

Se descartó modelarlo como una corrección sobre una deuda existente (restar minutos a un
`DeudaPermisoMes`, o una fila negativa en el ledger de deuda). El crédito se otorga por **el
hecho** —el día que trabajó de más— y vive por su cuenta: si le deben 1 h y solo tiene 0,5 h de
deuda, tras saldarla le quedan 30 min disponibles para la próxima.

Modelo nuevo `CreditoHoras` (`permisos/models.py:355`), en **minutos enteros** como el resto del
dominio (`DeudaPermisoMes`, `DeudaCorporativa`), con `minutos_otorgados`, `minutos_consumidos`,
`motivo`, quién lo otorga y estado `activo` / `consumido` / `anulado`.

**El consumo es FIFO, y esa regla vive en el `ordering` del modelo**
(`ordering = ['fecha_hecho', 'id']`, `:408`), no en el servicio. Es una decisión consciente y
frágil a partes iguales: quien cambie ese `ordering` creyendo que es cosmético cambiará qué
crédito se gasta primero. Sin orden fijo, un crédito antiguo puede quedarse indefinidamente al
fondo de la cola mientras se consumen los recientes.

### 2. No es un tipo de transacción nuevo: es un medio de pago dentro del PDH

La alternativa —una pantalla propia donde el crédito se "aplica" por su cuenta— habría exigido
duplicar la vista de pago, el servicio que salda deudas y toda la lógica de reversión, con dos
caminos distintos por los que una deuda puede quedar saldada. En su lugar, el crédito entra en
el PDH que ya existe: el supervisor registra el pago como siempre y decide cuántas horas a favor
lo cubren.

De ahí sale un invariante que hay que sostener explícitamente: **el crédito aplicado no puede
superar las horas que ese PDH salda** (`permisos/credito_horas_service.py:128-131`). Si pudiera,
el consolidado restaría dos veces las mismas horas — una por el pago y otra por el crédito.

Y de ahí sale también el orden raro de la vista: el crédito se consume **después** de crear el
PDH, porque se valida contra sus horas; si falla, se deshace el pago entero
(`empleados/views/pdh.py:169-189`). Borrar el PDH devuelve el crédito a la bolsa (`:246`).

### 3. La estructura es una copia deliberada de `DeudaPermisoMes` + `PagoDeudaPermisoMes`

`ConsumoCreditoHoras` (`permisos/models.py:435`) es una tabla intermedia con importe, calcada de
`PagoDeudaPermisoMes` y por el mismo motivo que aquella (ADR 011, punto 5): el consumo puede ser
**parcial** y repartirse entre varios créditos, así que sin el importe por fila, borrar el PDH no
sabría cuánto devolver a cada uno. `PROTECT` sobre el crédito impide que desaparezca uno que ya
cubrió un pago.

Copiar la estructura no es pereza: es que el problema es el mismo con el signo cambiado, y dos
soluciones distintas para el mismo problema obligan a mantener dos.

### 4. Las horas a favor NO intervienen en la sanción

**Es la decisión con más consecuencias, y la más fácil de revertir por accidente.**

Un mes vencido sigue sancionando aunque el explorador tenga crédito de sobra. Lo sancionable es
**haber dejado vencer el plazo**, no el importe adeudado; el crédito reduce lo que debe, no el
hecho de no haber pagado a tiempo.

En la práctica esto significa que `sancion_deuda_calculo.py` y `deuda_corporativa_service.py`
quedaron **sin tocar**: `gestionar_sancion_por_deuda` y `_periodos_con_deuda` no consultan
`CreditoHoras` en absoluto. Lo que blinda la política es un centinela,
`permisos/tests/test_credito_horas.py:222`, que fija que un mes vencido con 10 h de crédito
sigue produciendo sanción.

Sin esta regla, una bolsa de horas a favor volvería **inmune a la sanción** a quien nunca paga a
tiempo, y vaciaría de sentido todo el ADR 011.

### 5. El consolidado suma una clave nueva; no reinterpreta la vieja

`total_horas` sigue significando exactamente lo mismo —lo que el explorador debe— porque la
consultan la vista de morosos y las plantillas. El neto va aparte, en `saldo_neto`, que **puede
ser negativo** cuando la corporación le debe a él
(`turnos/services/consolidado_horas_service.py:287-303,330-333`).

Restar el crédito dentro de `total_horas` habría sido más corto y habría escondido una de las dos
cifras: quien mira el consolidado necesita ver por separado lo que debe y lo que le deben.

### 6. Reconocer horas es una potestad distinta de registrar un pago

Sesión de menú **propia**, `credito_horas`, separada de `pdh` (`core/sesiones.py`). Un PDH
constata lo que el explorador **ya debía**; reconocer horas a favor **compromete a la
corporación**. Separarlas permite dar lo primero sin dar lo segundo. Ambas quedan bajo
`AdminRequiredMixin`, que ya cubre administradores y supervisores.

Un crédito **no se borra: se anula** con su motivo (`empleados/views/credito.py`), y solo si no
se ha consumido nada — con consumos encima hay que deshacer primero el PDH. Es el mismo criterio
que con las sanciones, que se levantan en vez de eliminarse: es un reconocimiento de deuda hacia
una persona, y borrarlo haría desaparecer el rastro de quién lo concedió.

## Consecuencias

**A favor:**

- El hecho existe en el sistema: hay dónde anotarlo, quién lo reconoció y por qué.
- El remanente deja de perderse, que era el problema concreto que originó todo esto.
- No hay un segundo camino por el que una deuda pueda quedar saldada: sigue siendo el PDH.
- La disciplina de la sanción queda intacta.

**En contra, asumido:**

- **El crédito no caduca.** Horas reconocidas hace dos años siguen siendo gastables hoy. No se
  puso caducidad porque no hay decisión de negocio que la respalde; si algún día la hay, el sitio
  es un campo `vence_el` más un filtro en `creditos_disponibles`
  (`permisos/credito_horas_service.py:37`). Queda anotado en § 18 del manual técnico.
- **El crédito solo se aplica junto a un pago.** Un explorador con saldo a favor y sin ninguna
  deuda que saldar simplemente lo acumula. Es coherente con la decisión 2, pero significa que la
  bolsa puede crecer sin que nadie la vea salvo en el consolidado.
- **La regla FIFO es invisible desde el servicio.** Vive en el `Meta` del modelo. Está
  documentada en el propio `ordering` y en el manual técnico (§ 5), pero sigue siendo un sitio
  donde un cambio inocente rompe una regla de negocio.
- **Quien reconoce las horas no necesita aprobación de nadie.** Igual que un PDH. La contención
  es la trazabilidad —queda quién, cuándo y por qué—, no un segundo par de ojos.

## Alternativas descartadas

- **Un campo de signo en el ledger de deuda** (permitir `minutos_pendientes` negativo, o filas de
  `DeudaCorporativa` con minutos negativos). Habría contaminado todas las consultas de deuda, que
  hoy pueden asumir que un pendiente es positivo, y sobre todo habría metido el crédito en el
  cálculo de la sanción **por omisión**: cualquier suma de deuda pendiente lo habría restado sin
  que nadie lo decidiera. La decisión 4 dejaría de estar protegida por construcción.
- **Aplicar el crédito contra una deuda concreta al registrarlo.** Más simple, pero devuelve
  exactamente el problema original: si el crédito supera esa deuda, el excedente se pierde.
- **Una pantalla de aplicación independiente del PDH.** Dos caminos para saldar una deuda, dos
  lógicas de reversión y dos sitios donde el consolidado puede descuadrar.
- **Que el explorador reclame sus horas con un formulario de solicitud**, como los seis
  existentes. Se descartó por desproporcionado para el caso real: el supervisor que pidió entrar
  antes es quien lo sabe y quien lo reconoce en el acto. Si el reconocimiento se vuelve
  conflictivo, es el momento de reconsiderarlo.
