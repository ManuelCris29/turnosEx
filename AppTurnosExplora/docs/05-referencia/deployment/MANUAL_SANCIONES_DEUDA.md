# Manual — Sanciones automáticas por deuda de horas

**Qué resuelve:** que un explorador que dejó vencer su deuda de horas quede bloqueado
—y su supervisor se entere— sin depender de que esa persona abra la aplicación.

**A quién le sirve este documento:** a quien despliega (secciones 4 y 5) y a quien tiene
que entender por qué el sistema bloqueó a alguien (secciones 1 a 3).

---

## 1. La regla de negocio

Hay dos fuentes de deuda de horas y se tratan igual:

- **Dobladas:** cada una genera 30 minutos.
- **Permisos especiales:** las horas del permiso. Un permiso PERMANENTE de varios meses no
  es una deuda global: se reparte **por mes**, y cada mes vence y se reclama por separado.

La deuda de un mes **vence al terminar ese mes** — no a los 30 días. Quien cierra un mes
debiendo queda sancionado, y mientras la sanción dure **no puede realizar solicitudes de
cambio de turno ni permisos**.

La escalada sube un escalón por cada sanción encadenada:

| Nivel | Duración | Se muestra como  |
|-------|----------|------------------|
| 1     | 15 días  | Sanción automática |
| 2     | 30 días  | reincidencia #1  |
| 3     | 45 días  | reincidencia #2  |
| n     | 15 × n días | reincidencia #(n-1) |

No hay tope de duración: cuatro meses seguidos sin pagar encadenan 15+30+45+60 días. Las
sanciones se encadenan una tras otra y nunca se solapan.

### La reincidencia prescribe

El nivel **no** se acumula para siempre. Cuando una sanción termina arranca una **ventana
de reincidencia** configurable (45 días por defecto):

- Si dentro de la ventana cae otra sanción → es reincidencia y sube un nivel.
- Si la ventana se agota sin sanciones nuevas → el contador vuelve a **cero**, y la
  siguiente es otra vez de 15 días.

Sin esa caducidad, un descuido aislado de hace dos años seguía encareciendo la sanción de
hoy. El antecedente tiene que poder prescribir.

La ventana se mide desde la finalización **efectiva** de la anterior (su `fecha_fin`, o el
día en que se levantó si el supervisor la levantó antes): lo que abre el periodo de prueba
es haber terminado de cumplirla.

Cuenta como antecedente **cualquier** sanción, también las manuales del supervisor: quien
acaba de cumplir un castigo por otro motivo no está estrenando expediente.

**Dónde se cambia:** `/empleados/sanciones/morosos/`, en el recuadro de configuración; o en
el admin, *Sanciones (configuración)*. Queda registrado quién lo cambió. Afecta solo a las
sanciones que se generen a partir de ese momento: las ya grabadas conservan el nivel y las
fechas que se comunicaron al explorador.

#### Cómo elegir el valor

Entre el fin de una sanción y el vencimiento del mes siguiente hay **días muertos**: la
sanción por enero acaba el 16/02, pero la deuda de febrero no vence hasta el 01/03. Ese
hueco es el que la ventana tiene que cubrir, y crece si el explorador tiene meses limpios
por medio:

| Hueco entre una sanción y la siguiente | nivel 1 | nivel 2 | nivel 3 | nivel 4 |
|---|---|---|---|---|
| meses consecutivos | 13 | — | — | — |
| saltándose 1 mes   | 44 | 29 | 14 | — |
| saltándose 2 meses | 74 | 59 | 44 | 29 |

(«—» = la anterior aún no ha terminado; se encadenan y siempre es reincidencia.)

De ahí salen los umbrales:

| Si quieres que cuente como reincidencia… | ventana mínima |
|---|---|
| solo meses consecutivos | 13 días |
| **saltándose un mes** (valor por defecto) | **45 días** |
| saltándose dos meses | 74 días |

**Por qué 45 y no 30.** Con 30, un solo mes limpio borraba el antecedente — y de forma
desigual: quien venía de una sanción larga seguía escalando (14 < 30) y quien venía de una
corta no (44 > 30). Con 45 el hueco queda cubierto en todos los niveles, y hacen falta dos
meses limpios para prescribir.

> **Cuidado al bajarla mucho.** Por debajo de 13 días la reincidencia no se encadena ni
> entre meses consecutivos, y todas las sanciones salen de 15 días.

**Pagar la deuda NO levanta la sanción.** Se cumple completa. Esto cambió a propósito:
mientras el pago la levantaba, la sanción funcionaba como una fianza reembolsable —el
moroso decidía cuándo dejar de estar bloqueado— en vez de como una consecuencia.

**Al cumplirse la sanción, la deuda de ese mes queda saldada por el propio castigo**
(estado `consumida_por_sancion`). Sin eso, el explorador terminaría sus 15 días con el
mismo saldo vencido que lo metió en ellos y volvería a ser sancionado por lo mismo, en un
bucle sin salida. El mes sigue contando como incumplido para la escalada.

Un **supervisor sí puede levantar** una sanción a mano. Eso perdona el castigo pero **no
la deuda**: el explorador sigue debiendo esas horas y el mes sigue contando.

### Ejemplo completo

Una doblada del **16/07/2026**:

```
16/07  se dobla, nace la deuda de 30 min
31/07  fin de plazo — hasta aquí se puede pagar sin consecuencias
01/08  ─┐
        │  ventana 1 · 15 días
16/08  ─┘
17/08  ─┐
        │  ventana 2 · 30 días · reincidencia #1
16/09  ─┘
17/09  ─┐
        │  ventana 3 · 45 días · reincidencia #2
01/11  ─┘
```

---

## 2. Las tres capas

El diseño separa **qué se graba** de **cuándo se entera el sistema**. Es la propiedad que
hace que todo lo demás sea seguro.

### Capa 1 — Cálculo (`solicitudes/services/sancion_deuda_calculo.py`)

Función pura, sin base de datos y sin reloj. Se le da la fecha de la doblada impagada y un
día, y responde qué ventana corresponde.

**Lo importante:** las fechas se derivan del **vencimiento de la deuda**, nunca de "hoy".
Calcular el 1 de agosto o el 23 de agosto produce **el mismo registro**.

> Antes no era así: la sanción nacía con `fecha_inicio = hoy`, siendo "hoy" el día en que
> el explorador casualmente abría la aplicación. Como la escalada contaba las ventanas
> anteriores ya grabadas, y esas no existían si el moroso no había entrado, **quien evitaba
> la aplicación se sancionaba más tarde y más barato**. La escalada 15/30/45 casi nunca
> llegaba a activarse.

### Capa 2 — Revisión diaria (`revisar_sanciones_por_deuda`)

Recorre a todos los implicados y materializa lo que la capa 1 dice. Es **el generador
principal**: es lo que hace que la sanción sea puntual y que llegue la notificación.

Recorre **dos** grupos, y hacen falta los dos:

- quien tiene deuda activa → puede haber que sancionarlo;
- quien tiene una sanción automática ya cumplida cuya deuda sigue viva → hay que saldarla.

El segundo grupo es el que cierra el ciclo: sin él, una deuda ya pagada con el castigo
seguiría pendiente y volvería a sancionar por lo mismo.

### Capa 3 — Red de seguridad (en la aplicación)

Si la capa 2 no corrió (cron caído, despliegue a medias), el bloqueo **no se cae**. El
mismo cálculo se dispara desde:

| Punto | Archivo |
|---|---|
| Envío de una solicitud (POST) | `SolicitudOrchestrator.procesar`, paso 1 |
| Pantalla de tipos de cambio de turno | `solicitudes/views/cambio_turno_pages.py` |
| Formulario de solicitud | `SolicitarCambioTurnoView.get` |
| Lista y formulario de permisos | `permisos/views.py` |
| Vistas de PDH | `empleados/views/pdh.py` |

Todos pasan por `empleados/sancion_utils.py::refrescar_y_sancion()`, que refresca y luego
consulta — **en ese orden**.

El POST es la puerta que de verdad cierra; las pantallas solo evitan que alguien llene un
formulario entero para chocar con el error al enviarlo.

---

## 3. Sanciones manuales del supervisor

**Siguen funcionando exactamente igual y el proceso automático no las toca.**

Se distinguen por el prefijo `[AUTO-DEUDA]` en el motivo. Las automáticas lo llevan; las
manuales, no.

| | Automática | Manual |
|---|---|---|
| La crea | La revisión diaria (o la capa 3) | El supervisor, en *Nueva sanción* |
| Fechas | Derivadas del vencimiento | Las que elija el supervisor |
| La levanta el sistema al pagar | **No** (se cumple entera) | **No** |
| La puede levantar el supervisor | Sí | Sí |
| Al cumplirse, salda la deuda | Sí | No (no viene de una deuda) |

Reglas de convivencia, todas cubiertas por tests:

- Una sanción manual vigente **no impide** crear la automática. Son hechos distintos: si la
  manual la bloqueara, al terminar la manual el moroso quedaría libre pese a seguir debiendo.
- Pagar la deuda **no levanta** ninguna sanción, ni automática ni manual.
- Si un supervisor levanta a mano una sanción automática, **la revisión no la recrea**. Sería
  el fallo más fácil de introducir: que el cron deshaga cada noche su decisión.
- Una sanción levantada a mano **no salda la deuda**: solo la cumplida lo hace. Confundirlas
  convertiría cada levantamiento en una condonación silenciosa de horas.
- Una deuda ya saldada por una sanción **no vuelve a sancionar** por ese mismo mes, pero el
  mes **sigue contando** para la escalada.

---

## 4. Puesta en producción

> Es el mismo patrón que ya usa `procesar_email_outbox`. Si eso ya está programado, esto es
> una entrada más al lado.

### Paso 1 — Migración

```bash
python manage.py migrate solicitudes
```

Crea `RevisionSancionesDeuda`, la tabla que coordina las ejecuciones.

### Paso 2 — Prueba en seco

Antes de programar nada, mira a quién afectaría. **No escribe nada:**

```bash
python manage.py revisar_sanciones_por_deuda --dry-run
```

Salida esperada:

```
Revisión 23/08/2026 — exploradores con deuda activa: 8 (sin sancionar: 1, ya sancionados: 1, en plazo: 6)
  - Vanesa Arteaga: 120 min, más antigua 04/07/2026 (venció el 31/07/2026)
DRY-RUN: no se ha modificado nada ni se ha marcado el día.
```

- [ ] Revisado el listado y confirmado que los nombres tienen sentido.

> **Atención en el primer arranque.** Si hay deudas vencidas de hace meses, la primera
> ejecución las sancionará con fechas **retroactivas** (la ventana en la que cae hoy). Es
> el comportamiento correcto, pero conviene saberlo antes, no descubrirlo. Ver sección 6.

### Paso 3 — Programar la ejecución diaria

Se recomienda **de madrugada**, para que la sanción esté puesta antes de que nadie
empiece a trabajar.

#### Si el despliegue es EC2

```bash
sudo mkdir -p /var/log/appturnos
sudo touch /var/log/appturnos/sanciones_deuda.log
sudo chown -R ubuntu:ubuntu /var/log/appturnos

crontab -e
```

Agregar:

```cron
15 5 * * * cd /home/ubuntu/appTurnos/AppTurnosExplora && /home/ubuntu/venvturnos/bin/python manage.py revisar_sanciones_por_deuda >> /var/log/appturnos/sanciones_deuda.log 2>&1
```

- [ ] Cron agregado y guardado.
- [ ] Verificado: `crontab -l | grep sanciones`

#### Si el despliegue es Fargate

En Fargate no hay crontab. Se necesita una **EventBridge Scheduled Rule**:

- [ ] Crear regla EventBridge con schedule `cron(15 10 * * ? *)` — **EventBridge usa UTC**,
      así que 10:15 UTC son las 05:15 en Colombia (UTC-5). Ajustar si cambia la zona.
- [ ] Target: ECS Task, **la misma Task Definition** que la app.
- [ ] Container override → command:
      `["python","manage.py","revisar_sanciones_por_deuda"]`
- [ ] Misma subnet y Security Group, con salida a RDS.
- [ ] Retry attempts: **2**. Un fallo transitorio (RDS que aún no acepta conexiones, una
      tarea que no arranca) se resuelve solo con reintentar; sin reintentos, ese día se
      pierde entero. La ejecución es idempotente —el candado de `RevisionSancionesDeuda`
      garantiza que solo una haga el trabajo—, así que reintentar es seguro.
- [ ] **Alarma de CloudWatch** sobre el log del contenedor, con el *metric filter*
      **`REVISION_SANCIONES_NO_EJECUTADA`** (no filtres por `CRITICAL` a secas: se mezclaría
      con otras alertas del sistema). El comando emite esa cadena cuando detecta que lleva
      días sin ejecutarse, y es la única forma de enterarse sin mirar: un cron caído no da
      error, deja de ocurrir.
- [ ] **Probar la alarma** antes de darla por buena. Un aviso sin probar no es un aviso.

### Paso 4 — Verificación post-despliegue

- [ ] Al día siguiente: `tail /var/log/appturnos/sanciones_deuda.log`. Si aparece una línea
      `ALERTA:` significa que el proceso no está corriendo a diario.
- [ ] En el admin, `/admin/solicitudes/revisionsancionesdeuda/` debe tener **una fila por
      día**, con lo que hizo cada una.
- [ ] Entrar como supervisor a `/empleados/sanciones/morosos/` y comprobar que nadie queda
      en estado **Sin sancionar** de forma permanente.

---

## 4 bis. Qué pasa si el proceso deja de correr

Un cron caído **no da ningún error que alguien vea**: simplemente deja de ocurrir. El
síntoma —morosos que siguen pudiendo solicitar— tarda semanas en notarse y casi nunca se
atribuye a esto. Por eso hay tres redes, en este orden:

1. **Alerta al ejecutarse.** El comando comprueba al arrancar cuántos días lleva sin correr
   (`RevisionSancionesDeuda.dias_sin_ejecutar()`). Si pasa de dos, escribe en nivel
   **CRITICAL** —y por stderr— una línea que empieza por el marcador:

   ```
   REVISION_SANCIONES_NO_EJECUTADA lleva 12 días sin ejecutarse. Se recupera ahora, pero...
   ```

   Ese marcador es un **contrato con la infraestructura**: las alarmas filtran por esa
   cadena exacta. Está fijado en `MARCADOR_ALERTA` y protegido por un test, porque si
   alguien lo cambia las alertas dejan de dispararse sin que falle nada visible.

   Dos días de tolerancia y no uno: un retraso aislado se autocura y una alerta que salta
   cada día deja de leerse.

2. **Aviso en el dashboard del supervisor.** Si el proceso lleva días sin correr, el
   supervisor ve un banner rojo al entrar, con el número de días. Cubre el caso en que la
   alerta técnica no llegue a nadie —incluido el más probable en un despliegue nuevo: que
   la tarea programada no se llegara a configurar—.

3. **Recuperación bajo demanda.** Aunque nadie mire nada, la sanción se materializa en
   cuanto el explorador abre cualquier pantalla (`refrescar_y_sancion`, capa 3). El cron no
   es lo que hace que el bloqueo exista: es lo que hace que exista **a tiempo** y sin
   depender de que el moroso entre por su cuenta.

**Comprobarlo a mano:** `/admin/solicitudes/revisionsancionesdeuda/` debe tener una fila
por día. Un hueco en las fechas es exactamente el fallo que se está buscando.

---

## 5. Por qué diaria y no mensual

La regla es mensual, pero el trabajo corre **todos los días**. Es deliberado.

> Un trabajo que solo corre el día 1 y falla ese día **pierde el mes entero**, y nadie se
> entera hasta que un moroso intenta solicitar algo.

Como el contenido de la sanción no depende del reloj (capa 1), correr el día 2 graba
exactamente el mismo registro que habría grabado el día 1. **Un fallo cuesta un día de
retraso en el aviso, no un mes de impunidad.** El proceso se autocura sin intervención.

### Coordinación entre workers

La aplicación corre con `--workers 3` y la caché puede ser `LocMemCache`, que es **por
proceso**: un lock de caché haría que los tres workers creyeran haber ganado.

El candado es una fila en `RevisionSancionesDeuda` con `fecha` **única**. Se toma con
`get_or_create`, que sobre un campo único es atómico: exactamente un proceso recibe
`created=True`. Lo impone el motor de la base de datos, que es lo único que los tres
comparten.

Aun así, **la seguridad real está en las guardas del servicio**, no en el candado: aunque
se fuerce la re-ejecución con `--force`, no se duplica ninguna sanción. El candado solo
evita trabajo repetido.

---

## 6. Decisión tomada: las solicitudes ya aprobadas se quedan

Al derivar las fechas del vencimiento, una sanción puede empezar **en el pasado**. Cabe
entonces que alguien haya hecho solicitudes en días en los que, retroactivamente, estaba
sancionado.

**Esas solicitudes se mantienen aprobadas.** Se aprobaron bajo las reglas vigentes en su
momento; anularlas rompería turnos ya publicados y acuerdos entre compañeros por un cambio
en cómo el sistema calcula fechas. El bloqueo aplica **de aquí en adelante**.

Si en algún caso concreto se quiere revertir una de esas solicitudes, se hace a mano por
la vía normal de cancelación, con su registro.

---

## 7. Operación diaria

### Ver quién debe

`/empleados/sanciones/` → botón **Deudas de horas**, o directo a
`/empleados/sanciones/morosos/`. Estados:

| Estado | Significa |
|---|---|
| **Sin sancionar** | Tiene un mes cerrado con deuda que el sistema todavía no ha juzgado. Con la revisión diaria activa esto debería ser transitorio. |
| **Sancionado** | Ya bloqueado, con la fecha de fin. |
| **Sanción levantada** | El sistema lo juzgó y el supervisor levantó el castigo. Sigue debiendo, pero la sanción no vuelve sola. |
| **En plazo** | Debe, pero aún está dentro del mes. Todavía no es moroso. |

El **dashboard** muestra un aviso con el número de *Sin sancionar*, solo cuando hay alguno.

### Cuándo aparece el aviso — y cuándo se apaga

El aviso mide **la distancia entre "un mes cerró debiendo" y "alguien lo juzgó"**. Se
enciende cuando se dan las tres cosas a la vez, para un mismo explorador y un mismo mes:

1. El mes ya **cerró** (es anterior al mes en curso).
2. Queda deuda **activa** de ese mes — doblada o permiso, da igual.
3. **No existe** sanción automática para ese mes: ni vigente, ni cumplida, ni levantada.

La unidad es el **mes**, no la persona. De ahí salen las dos consecuencias que más
confunden si se piensa en términos de "estar sancionado o no":

- Quien está **cumpliendo** la sanción de un mes y cierra otro debiendo **vuelve a
  aparecer**. Son juicios independientes y le falta uno. Contarlo por persona lo escondía
  justo durante la sanción anterior, que es cuando más fácil es acumular otro mes impago
  —y el agujero duraba tanto como el castigo en curso: 30, 45, 60 días—.
- Quien tiene una sanción **levantada** deja de aparecer para ese mes, **para siempre**.
  Ese mes ya se juzgó; que el supervisor perdonara el castigo es una decisión, no una
  tarea pendiente. Pero si cierra un mes NUEVO debiendo, ese sí vuelve a contar.

El aviso solo se enciende, entonces, cuando el botón **Aplicar sanciones** de verdad va a
crear algo. Si apareciera sobre un caso ya juzgado, el botón no podría apagarlo y quedaría
un aviso permanente invitando a pulsar algo que no cambia nada.

**Cuánto dura encendido.** Con el cron programado, casi nada: la revisión de la madrugada
del día 1 juzga los meses que acaban de cerrar, y cuando el supervisor entra ya ve
*Sancionado*, no *Sin sancionar*. Un aviso que persiste día tras día en producción
significa que **la revisión no está corriendo** — y eso lo dice por separado el banner rojo
del dashboard (§ 4 bis). En un entorno sin cron (desarrollo), se queda encendido hasta que
alguien pulse el botón o ejecute el comando.

> El contador del dashboard y la tabla de morosos calculan lo mismo por caminos distintos
> —uno agregado y barato, el otro explicando caso por caso—. **Deben coincidir siempre**;
> hay un test que lo comprueba. Si alguna vez divergen, manda la tabla de morosos.

### Adelantar la revisión a mano

El botón **Aplicar sanciones (N)** de esa pantalla hace lo mismo que la revisión diaria.
Útil si el cron aún no está programado, o para no esperar a mañana.

### Comandos útiles

```bash
# Ver el estado sin tocar nada
python manage.py revisar_sanciones_por_deuda --dry-run

# Ejecutar (lo que hace el cron)
python manage.py revisar_sanciones_por_deuda

# Repetir aunque hoy ya se haya ejecutado
python manage.py revisar_sanciones_por_deuda --force
```

### Levantar una sanción

- **Por cumplirla:** es la vía normal. Al llegar su fecha de fin deja de bloquear sola, y
  la deuda de ese mes queda saldada.
- **Por decisión del supervisor:** `/empleados/sanciones/` → icono de levantar. Queda
  constancia de quién, cuándo y por qué, y **la revisión diaria no la recrea**. Perdona el
  castigo, no la deuda.
- **Por pago: ya no.** Registrar el PDH salda la deuda pero no toca la sanción.

Una sanción **nunca se borra**: es un hecho disciplinario y su registro sobrevive. Los
errores también se corrigen levantándola con ese motivo.

---

## 8. Diagnóstico

| Síntoma | Qué mirar |
|---|---|
| Alguien con deuda vencida no está bloqueado | ¿Corrió la revisión? `/admin/solicitudes/revisionsancionesdeuda/`. Si falta el día, revisar el cron. |
| El aviso dice "debería estar sancionado" y aplicar no lo apaga | No debería ocurrir. Si ocurre, es que el mes está sin juzgar pero la sanción no llega a crearse: mirar el log de `gestionar_sancion_por_deuda`. Antes pasaba con las sanciones levantadas, que ahora tienen estado propio. |
| Levanté una sanción y quiero volver a bloquearlo | Crearla **a mano** en `/empleados/sanciones/`. La automática de ese mes no se recrea: sería anular la decisión de levantarla en el acto. |
| La revisión dice "ya se ejecutó" y quiero repetirla | `--force`. |
| Una sanción reaparece tras levantarla | No debería: se comprueba en `test_lo_que_levanta_el_supervisor_no_lo_recrea_la_revision_al_dia_siguiente`. Verificar que se levantó con `levantada_por` (supervisor) y no vaciándolo a mano. |
| Un explorador aparece dos veces sancionado | Es correcto si una es manual y otra automática. Se distinguen por el prefijo `[AUTO-DEUDA]`. |
| Las fechas no cuadran con lo esperado | La verdad está en `sancion_deuda_calculo.py` y en `test_sancion_deuda_calculo.py`, que fija la aritmética con fechas concretas. |

### Archivos

| Capa | Archivo |
|---|---|
| 1 · Cálculo | `solicitudes/services/sancion_deuda_calculo.py` |
| 2 · Revisión | `solicitudes/management/commands/revisar_sanciones_por_deuda.py` |
| 2 · Motor | `DeudaCorporativaService.revisar_todos()` / `gestionar_sancion_por_deuda()` |
| 2 · Candado | `solicitudes.models.RevisionSancionesDeuda` |
| 3 · Red | `empleados/sancion_utils.py::refrescar_y_sancion()` |
| Supervisión | `empleados/views/sanciones.py::MorososDeudaView` |

### Tests

| Archivo | Cubre |
|---|---|
| `solicitudes/tests/test_cadena_sanciones.py` | La aritmética de la escalada por meses (capa 1) |
| `solicitudes/tests/test_sancion_automatica_deuda.py` | Materialización y reincidencia |
| `solicitudes/tests/test_pago_no_desbloquea.py` | Que pagar NO levante la sanción |
| `solicitudes/tests/test_consumo_deuda_por_sancion.py` | Que cumplir la sanción salde la deuda |
| `permisos/tests/test_deuda_permiso_mes.py` | El reparto de un permiso por meses |
| `permisos/tests/test_pago_parcial_pdh.py` | Pago parcial y pantalla de PDH por mes |
| `solicitudes/tests/test_ventana_reincidencia.py` | La ventana configurable y su prescripción |
| `solicitudes/tests/test_alerta_cron_sanciones.py` | Que se note si la revisión deja de correr |
| `solicitudes/tests/test_revision_diaria_sanciones.py` | Idempotencia, candado y sanciones manuales |
| `solicitudes/tests/test_bloqueo_pantallas_sancion.py` | Que las pantallas bloqueen (capa 3) |
| `empleados/tests/test_morosos_deuda.py` | Pantalla de morosos, aviso del dashboard, y que ambos coincidan |
