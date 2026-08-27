# Triaje de issues SonarQube — código nuevo

Clasificación de los **82 issues** del período "New Code" (desde 23 jul 2026).
Snapshot: 4 ago 2026. Regenerar con los comandos de
[MANUAL_SONARQUBE.md](../04-guias/MANUAL_SONARQUBE.md) §10.

Criterio de clasificación:

- 🟢 **ARREGLAR** — defecto real, riesgo bajo, beneficio claro.
- 🟡 **EVALUAR** — legítimo pero con costo/riesgo; decisión de negocio.
- 🔵 **ACEPTAR** — falso positivo o decisión deliberada; marcar *Accepted*
  en Sonar con justificación.

Resumen inicial: **9 arreglar · 52 evaluar · 21 aceptar** (= 82)

> Conteos verificados contra la API con `resolved=false&inNewCodePeriod=true`.
> Cada ítem de la categoría 🟢 fue auditado leyendo el código y buscando
> llamadores; el detalle de la verificación está en cada entrada.

---

# 📊 ESTADO DE AVANCE

| | Issues | Fecha |
|---|---|---|
| Línea base | **82** | 4 ago 2026 |
| Tras arreglar los 9 de la categoría 🟢 | **73** | 4 ago 2026 |
| Tras suprimir los 12 falsos positivos / decisiones | **61** | 4 ago 2026 |
| **Pendiente real** | **61** | — |

Los 61 restantes son deuda técnica legítima: **ningún falso positivo queda
sin justificar**.

### Impacto en las métricas globales

| Métrica | Antes | Después |
|---|---|---|
| **Security rating** | **D** | **A** ✅ |
| Issues de seguridad (global) | 3 | 1 |
| Issues de seguridad (código nuevo) | 3 | **0** |
| Reliability issues | 151 | 146 |
| Maintainability issues | 1.540 | 1.511 |

El salto de seguridad **D → A** viene de los dos issues del `Dockerfile`:
`S6471` (corría como root) se arregló de verdad y `S6470` (`COPY . .`) se
suprimió con justificación. El único de seguridad que queda a nivel global
es `python:S1313` (IP hardcodeada `192.168.2.102` en `config/settings.py:506`),
que está fuera del período de código nuevo — **pendiente de revisar**.

> ✅ **Cobertura confirmada**: una corrida intermedia publicó 49,2% porque el
> `coverage.xml` se había generado con solo 3 apps. Regenerada con la suite
> completa (789 passed, 1 failed) volvió a **50,2%**, confirmando que la baja
> era artefacto de medición y no pérdida de tests. Es exactamente la trampa
> descrita en [MANUAL_SONARQUBE.md](../04-guias/MANUAL_SONARQUBE.md) §9.5.

### Snapshot verificado — 5 ago 2026

| Métrica | Global | Código nuevo |
|---|---|---|
| Issues | 1.601 | **61** |
| Coverage | 50,2% | — |
| Duplicación | 5,3% | — |
| Security | 1 — rating **A** | 0 |
| Reliability | 146 — rating D | — |
| Maintainability | 1.511 — rating A | — |

Los 61 de código nuevo: Python 46 · JS 15. Severidad: HIGH 34 · MEDIUM 22 ·
LOW 9. **Ningún BLOCKER.**

## ✅ Resueltos (9) — verificados contra Sonar tras el arreglo

| Regla | Cant. | Qué se hizo | Archivo |
|---|---|---|---|
| `python:S1854` | 1 | Eliminada la asignación muerta `fechas` **y su parámetro**; actualizado el único llamador | [doblada_snapshot_service.py](../../solicitudes/services/doblada_snapshot_service.py) |
| `python:S5603` | 1 | Eliminada la función anidada `_info`, nunca invocada | [api_alternancia.py](../../solicitudes/views/api_alternancia.py) |
| `python:S3457` | 3 | Quitado el prefijo `f` de f-strings sin interpolación | [reaplicar_doblada.py](../../solicitudes/management/commands/reaplicar_doblada.py) |
| `Web:S6853` | 3 | 2 `<label>`→`<span>` (texto de solo lectura); 1 `<label>`→`<fieldset>`+`<legend>` (grupo de controles) | sanciones_create/edit, asignacion_especial_anual |
| `docker:S6471` | 1 | Añadido usuario `appuser` sin privilegios + `USER` | [Dockerfile](../../Dockerfile) |

**Verificación**: `82 → 73` en el dashboard. Las 5 reglas quedaron en 0.

**Extras hechos de paso** (no los pedía Sonar en código nuevo):

- Se limpiaron **6 f-strings sin interpolación adicionales** en
  `reaplicar_doblada.py` que eran del código anterior a julio (no salían en
  "New Code" pero sí en "Overall").
- `.coverage`, `coverage.xml` y `htmlcov/` añadidos a
  [.dockerignore](../../.dockerignore): se estaban copiando a la imagen.

**Incidente durante el arreglo** — el `USER` del Dockerfile se añadió primero
como un `RUN` separado, lo que **introdujo un issue nuevo** (`docker:S7031`,
"merge consecutive RUN instructions"). Se corrigió fusionando el `useradd` +
`chown` dentro del `RUN` de `collectstatic`, en una sola capa. Lección: tras
arreglar, **volver a analizar** para confirmar que no se introdujo nada.

**Validación de no regresión**: `manage.py check` sin issues y suite de
`solicitudes`/`turnos`/`empleados` en **753 passed, 1 failed**. El fallo
(`test_ceder_hoy_rechazado_en_finde`) es **preexistente**, ya fallaba antes
de estos cambios — ver "Pendientes ajenos" al final.

## 🔇 Suprimidos con justificación (12)

Declarados en [sonar-project.properties](../../sonar-project.properties)
como `sonar.issue.ignore.multicriteria` (entradas `e2`-`e12`), cada uno con
su razón comentada en el propio archivo.

| Regla | Cant. | Motivo |
|---|---|---|
| `python:S1135` + `javascript:S1135` | 5 | Falso positivo por idioma: "Todo" español ≠ marcador `TODO` |
| `python:S8572` | 3 | `logger.error(…, exc_info=True)` ya es equivalente a `logger.exception()` |
| `docker:S6470` | 1 | `.dockerignore` ya excluye lo sensible; Sonar no lo lee |
| `javascript:S2486` | 1 | El `catch` sí maneja el error con un fallback seguro |
| `python:S1192` (solo `settings.py`) | 2 | `'unsafe-inline'` / `data:` del CSP se leen mejor literales |

**Verificado**: `73 → 61` tras re-analizar.

**Por qué en el archivo y no en la interfaz**: el token de análisis (`sqp_…`)
no tiene permiso para administrar issues (la API devuelve *403 Insufficient
privileges*). Marcarlos en la interfaz habría requerido un token de usuario
administrador. La supresión por configuración es además **mejor**: queda
versionada en git, se aplica sola en cada análisis y en cualquier máquina, y
la justificación vive junto a la regla.

## ⬜ Pendientes (61)

Todo lo que queda es **deuda técnica legítima**, sin falsos positivos.

| Categoría | Cant. | Estado |
|---|---|---|
| 🟡 Complejidad cognitiva (`S3776`) | 24 | Sin empezar — refactors de riesgo, ver criterio abajo |
| 🟡 Modernización Python/JS | 22 | Sin empezar — seguros, baja prioridad |
| 🟡 Literales duplicados (`S1192`) fuera de `settings.py` | 9 | Sin empezar — **incluye `'D FDS'`, ver abajo** |
| 🟡 Complejidad JS + varios | 5 | Sin empezar |
| 🟡 `null=True` en CharField (`S6553`) | 1 | Sin decidir — requiere migración |

### ⚠ Hallazgo sistémico: literales de dominio hardcodeados

Al revisar los `S1192` en detalle apareció algo que **Sonar apenas insinúa**.
La regla solo dispara cuando un literal se repite 3+ veces *dentro de un
mismo archivo*, así que reporta 2 casos de `'D FDS'`. El recuento real
(excluyendo tests y `venvturnos`):

| Literal | Usos | Archivos |
|---|---|---|
| `'DOBLADA'` | **165** | **47** |
| `'aprobada'` | **126** | **54** |
| `'pendiente'` | **112** | **43** |
| `'cancelada'` | 69 | 27 |
| `'D FDS'` | 33 | 21 |
| `'CAMBIO DESCANSO'` | 31 | 11 |
| `'CT PERMANENTE'` | 23 | 11 |
| `'rechazada'` | 20 | 9 |
| `'DOBLADA PERMANENTE'` | 13 | 7 |
| `'CAMBIO TURNO'` | 6 | 5 |

**Dato decisivo para el refactor**: estos literales **no son constantes de
código, son valores de datos**. `'DOBLADA'`, `'D FDS'`, etc. viven en el
campo `nombre` de la tabla `TipoSolicitudCambio`
([models.py:110](../../solicitudes/models.py#L110)) y se consultan así:

```python
tipo_cambio__nombre__in=['DOBLADA', 'D FDS']
```

Las estrategias se registran **dinámicamente desde la BD** leyendo
`codigo_estrategia`/`nombre` ([solicitud_factory.py](../../solicitudes/services/solicitud_factory.py)).

Consecuencias:

- Centralizar en constantes **no elimina el acoplamiento con la BD**: si
  alguien renombra una fila en `TipoSolicitudCambio`, el código sigue
  rompiéndose. Lo que sí logra es que haya **un solo punto que actualizar**
  en vez de 47 archivos.
- El patrón correcto ya existe en el propio proyecto: `EmailOutbox`
  ([models.py:68](../../solicitudes/models.py#L68)) define
  `ESTADO_PENDIENTE`, `ESTADO_ENVIANDO`… y arma `ESTADO_CHOICES` con esas
  constantes. Los demás modelos usan tuplas de strings crudos.
- No existe ningún módulo `constants.py`/`enums.py` en el proyecto.

**Riesgo del refactor**: tocar 54 archivos en una sola pasada es alto riesgo
sobre lógica de negocio delicada.

> 📋 **El levantamiento completo está en
> [inventario-literales-hardcodeados.md](inventario-literales-hardcodeados.md)**:
> los tres campos `tipo_cambio` distintos, los cuatro vocabularios que
> conviven en la misma columna, los 7 riesgos identificados y los candidatos
> ordenados por riesgo. **Nada se ha refactorizado todavía** — es material
> para decidir el plan.

## Pendientes ajenos a SonarQube

- ❌ **Test fallando**: `solicitudes/tests/test_cambio_descanso.py::CDDiaEnCursoTest::test_ceder_hoy_rechazado_en_finde`.
  Preexistente (falla desde antes de este trabajo). Parece depender de si
  "hoy" cae en fin de semana. **Sin diagnosticar.**

---

---

## 🟢 ARREGLAR — código muerto verificado (2)

Ambos confirmados leyendo el código, no solo por el mensaje de Sonar.

### `python:S1854` — [doblada_snapshot_service.py:303](../../solicitudes/services/doblada_snapshot_service.py#L303)

```python
if fechas is None:
    fechas = {f for (_e, f) in afectados}   # ← nunca se usa después
```

**Auditoría realizada:**

1. Se leyó el cuerpo completo de `refrescar_resultantes` (líneas 296-324):
   tras la asignación, la función solo usa `exploradores` y
   `claves_afectadas`. `fechas` no se vuelve a leer.
2. Los otros usos de `fechas` en el archivo pertenecen a
   `_reconciliar_cambios_de_turno`, que declara **su propio parámetro**
   homónimo (línea 326). No hay relación.
3. Búsqueda de llamadores en todo el proyecto: **uno solo**, en la línea
   292-293 del mismo archivo, que lo pasa posicionalmente.

**Conclusión**: la asignación es muerta y el parámetro `fechas` también.
Limpiarlo implica tocar 2 puntos (la firma y el único llamador). Riesgo
bajo y acotado.

### `python:S5603` — [api_alternancia.py:85](../../solicitudes/views/api_alternancia.py#L85)

```python
def _info(d, e_estados, e_emp):
    return bool(_estado(d, e_estados, e_emp)['trabaja'])
```

**Auditoría realizada:**

1. Es una función **anidada** dentro de una vista: su ámbito es únicamente
   la función que la contiene. Ningún otro módulo puede alcanzarla.
2. Menciones de `_info` en el archivo (313 líneas): solo la definición
   (línea 85). Las otras dos coincidencias son `exc_info=True`, palabra
   clave sin relación.
3. Se descartó acceso dinámico: en el archivo no hay `locals()`,
   `globals()`, `eval()` ni `exec()`. Los dos `getattr` presentes operan
   sobre `request.user`, no sobre el ámbito local.
4. Su función hermana `_estado` —definida igual, justo encima— sí se invoca
   6 veces, lo que confirma que el patrón funciona y que `_info` quedó
   descolgada.
5. `git log -S"def _info"` muestra que entró en el commit `f7891b9`
   ("Refactor: dividir api_turno_jornada.py en módulos por dominio"):
   residuo típico de un refactor.

**Conclusión**: inalcanzable por cualquier vía. Borrado seguro.

## 🟢 ARREGLAR — f-strings sin interpolación (3)

`python:S3457` en [reaplicar_doblada.py](../../solicitudes/management/commands/reaplicar_doblada.py)
líneas 218, 265, 267.

```python
self.stdout.write(f'  📝 Creando las deudas que falten...')   # sin {}
```

**No es un bug** (no falta ninguna interpolación, el texto es estático);
solo sobra el prefijo `f`. Quitarlo es seguro y trivial.

## 🟢 ARREGLAR — accesibilidad de formularios (3)

`Web:S6853` — `<label>` sin control asociado. **Auditados uno por uno: son
dos casos distintos, con arreglos distintos.**

### Caso A — rótulo sobre un dato de solo lectura (2)

[sanciones_create.html:33](../../templates/empleados/sanciones_create.html#L33)
y [sanciones_edit.html:30](../../templates/empleados/sanciones_edit.html#L30):

```html
<label><i class="fas fa-user-shield mr-1"></i> Supervisor que sanciona</label>
<p class="form-control-plaintext mb-0">{{ supervisor_actual.nombre }} …</p>
```

Verificado: **detrás no hay ningún control**, solo un `<p>` con el nombre
del supervisor. Un lector de pantalla anuncia un campo editable inexistente.
Arreglo: cambiar `<label>` por un elemento sin semántica de formulario
conservando las clases visuales. Riesgo nulo.

### Caso B — rótulo de un grupo de controles (1)

[asignacion_especial_anual.html:47](../../templates/turnos/asignacion_especial_anual.html#L47):

```html
<label class="mb-1 small font-weight-bold d-block">… Sembrar el año {{ anio }}</label>
<div style="display:flex; …">
  <span class="small">Primer sábado trabaja:</span>
  <select id="seed-finde" …>
```

Aquí **sí hay controles** (un `<select id="seed-finde">` y más elementos),
pero el `<label>` actúa como **título de la sección completa**, no de un
campo puntual, y no tiene `for`. Arreglo correcto: `<fieldset>` + `<legend>`
para el grupo. Poner `for="seed-finde"` sería incorrecto: ataría el título
del grupo a un solo control.

## 🟢 ARREGLAR — endurecimiento del contenedor (1)

`docker:S6471` — [Dockerfile:4](../../Dockerfile#L4): la imagen corre como
**root** por defecto. Buena práctica estándar: crear un usuario sin
privilegios y declararlo con `USER` antes del `CMD`. Relevante porque la
imagen va a ECS Fargate.

> **Nota**: los 5 issues `S1135` ("TODO") resultaron falsos positivos por
> idioma. Ver la sección 🔵 correspondiente.

---

## 🟡 EVALUAR — complejidad cognitiva (24)

`python:S3776` (23) + `javascript:S3776` (1). Es el grupo más grande y el de
**mayor riesgo**: son refactors sobre lógica de negocio delicada.

Concentración por archivo:

| Archivo | Líneas |
|---|---|
| `cambios_permanentes_helper.py` | 69, 182, 511 |
| `empleados/forms.py` | 36, 101, 197 |
| `ct_permanente_strategy.py` | 246, 338 |
| `asignacion_especial_service.py` | 84, 205 |
| resto (14 archivos) | 1 c/u |

Ejemplo del umbral: "complejidad 27, permitido 15".

**Recomendación**: no refactorizar en masa. Estos módulos concentran las
reglas de dobladas / CT permanente / cambio de descanso, donde un error es
caro y sutil. Atacarlos **de a uno, con tests que cubran la función antes de
tocarla**, y solo cuando ya haya que modificar ese código por otra razón.
Ver [PROTECTION_PATTERNS.md](../../PROTECTION_PATTERNS.md).

## 🟡 EVALUAR — modelado de datos (1)

`python:S6553` — [models.py:746](../../solicitudes/models.py#L746):

```python
jornada_pago_previa = models.CharField(
    max_length=2, choices=JORNADA_CHOICES, null=True, blank=True, …
)
```

Convención Django: en campos de texto se evita `null=True` (dos formas de
representar "vacío": `NULL` y `''`). Corregirlo exige **migración**. Como
producción arranca limpia, el costo de datos es nulo — pero hay que revisar
todo el código que compare contra `None` en ese campo.

## 🟡 EVALUAR — modernización de Python y JS (22)

Mejoras de legibilidad sin cambio funcional. Seguras pero numerosas:

| Regla | Cant. | Qué pide |
|---|---|---|
| `javascript:S6582` | 7 | Usar optional chaining (`?.`) |
| `python:S3358` | 5 | Sacar ternarios anidados a sentencias |
| `javascript:S7773` | 4 | `Number.parseInt` en vez de `parseInt` |
| `python:S7494` | 4 | Set comprehension en vez de `set(...)` |
| `python:S6546` | 3 | Union types (`X | None`) en type hints |
| `python:S7517` | 1 | Iterar con `.items()` |
| `javascript:S7761` | 1 | `.dataset` en vez de `getAttribute()` |
| `javascript:S7765` | 1 | `.includes()` en vez de `.indexOf()` |
| `javascript:S7776` | 1 | `Set` + `.has()` para búsqueda de existencia |

Buen material para limpiar de a poco al pasar por cada archivo. Ninguno
urgente.

---

## 🔵 ACEPTAR — copia recursiva en Docker (1)

`docker:S6470` — [Dockerfile:33](../../Dockerfile#L33): `COPY . .`

Sonar advierte que podría colar secretos en la imagen. **Pero Sonar no lee
el `.dockerignore`**, y [el nuestro](../../.dockerignore) ya excluye
exactamente lo que la regla teme:

```
.env, .env.*   ← secretos
.git/          ← historial
venvturnos/    ← entorno
db.sqlite3     ← base local
docs/, *.md    ← documentación
```

Reemplazar por ~20 `COPY` explícitos sería **más frágil** (cada archivo
nuevo habría que recordarlo). Marcar como *Accepted* citando el
`.dockerignore`.

> ⚠ **Pendiente detectado de paso**: `.coverage` y `coverage.xml` (generados
> por `pytest --cov`) **no** están en `.dockerignore`, así que hoy entrarían
> a la imagen. No son sensibles, pero conviene agregarlos.

## 🔵/🟡 literales duplicados (`python:S1192`) — 2 aceptar, 9 evaluar

> **Corrección de clasificación.** En una primera pasada se marcaron los 11
> como "aceptar" sin revisarlos uno por uno. Al hacerlo, resultó que **solo 2
> se sostienen**. Se deja constancia porque el error es instructivo: un
> "aceptar" en bloque puede esconder deuda real.

### 🔵 Aceptar — los 2 del CSP

[settings.py:370,381](../../config/settings.py#L370):

```python
'script-src': ["'self'", "'unsafe-inline'", …],
'style-src':  ["'self'", "'unsafe-inline'", …],
```

Extraer constantes para `'unsafe-inline'` y `data:` **empeora la
legibilidad**: la política CSP se lee mejor literal, igual que se emite en la
cabecera HTTP. Suprimido (`e12`).

### 🟡 Evaluar — los otros 9, deuda legítima

| Literal | Repeticiones | Archivo |
|---|---|---|
| `'D FDS'` | 3 | `descanso_solicitud_service.py:127` |
| `'D FDS'` | 3 | `reprogramacion_doblada_service.py:82` |
| `'solicitudes:reprog_list'` | 6 | `reprogramacion_views.py:236` |
| `'solicitudes:cierre_config'` | 4 | `cierre_config_views.py:92` |
| `'sábado'` | 4 | `d_fds_strategy.py:144` |
| `'Error al procesar la solicitud'` | 3 | `solicitud_orchestrator.py:279` |
| `'%d/%m/%Y'` | 3 | `cancelar_solicitud.py:142` |
| `'%d/%m'` | 3 | `api_alternancia.py:200` |
| `'Año inválido.'` | 3 | `descanso_semana.py:174` |

Los más valiosos de atacar:

- **`'D FDS'`** — no es "texto de dominio" inocuo: es el identificador con el
  que se despachan estrategias. Ver el hallazgo sistémico arriba (28
  archivos).
- **Nombres de ruta** (`'solicitudes:reprog_list'` ×6,
  `'solicitudes:cierre_config'` ×4) — extraerlos a una constante del módulo
  los vuelve a prueba de typos, que hoy solo fallarían en runtime.

Los formatos de fecha y los mensajes de error son de menor impacto.

## 🔵 ACEPTAR — `logging.exception()` (3)

`python:S8572` en [dia_especial_service.py:177](../../turnos/services/dia_especial_service.py#L177),
[temporada_service.py:156](../../turnos/services/temporada_service.py#L156),
[health.py:49](../../core/health.py#L49):

```python
logger.error(f"Error al guardar días especiales anual: {e}", exc_info=True)
```

Sonar pide `logger.exception(...)`. Es **exactamente equivalente**:
`logger.exception()` es azúcar sintáctico de `logger.error(..., exc_info=True)`,
y el código ya pasa `exc_info=True`, que es lo que importa. Cambio cosmético
de valor nulo.

> Nota aparte: sí valdría la pena pasar de f-string a *lazy logging*
> (`logger.error("… %s", e)`), que evita formatear el mensaje cuando el nivel
> está desactivado. Sonar no lo reporta aquí, pero es la mejora real.

## 🔵 ACEPTAR — `catch` con fallback (1)

`javascript:S2486` — [pdh_create.js:12](../../static/js/empleados/pdh_create.js#L12):

```js
try { preseleccion = JSON.parse(preNode.textContent) || []; }
catch(e) { preseleccion = []; }
```

Sonar lo lee como excepción ignorada, pero **sí está manejada**: si el JSON
viene corrupto se cae a un valor por defecto seguro. Es degradación
elegante deliberada, no un `catch` vacío.

## 🔵 ACEPTAR — falsos positivos por idioma: "Todo" ≠ "TODO" (5)

`python:S1135` (4) + `javascript:S1135` (1). **El hallazgo más importante de
la auditoría.**

La regla busca el marcador inglés `TODO` (tarea pendiente). Estos 5 casos
son la palabra **española "Todo"** al comienzo de un comentario:

| Archivo | Comentario real |
|---|---|
| [pdh.py:182](../../empleados/views/pdh.py#L182) | `# Todo en una transacción: si el DELETE falla…` |
| [admin.py:23](../../solicitudes/admin.py#L23) | `# Todo es de solo lectura: editar a mano…` |
| [cancelar_solicitud.py:165](../../solicitudes/use_cases/cancelar_solicitud.py#L165) | `# Todo ocurrió ya: se cierra el registro…` |
| [gestion_solicitudes.py:64](../../solicitudes/views/gestion_solicitudes.py#L64) | `# Todo el panel identifica las solicitudes por "#123"…` |
| [turnos_calendario.js:9](../../static/js/turnos/turnos_calendario.js#L9) | `// Todo el contenido dinámico se inserta con innerHTML…` |

**No hay ninguna tarea pendiente.** Son comentarios explicativos normales en
español; el analizador no distingue el idioma.

⚠ **Esto va a repetirse**: mientras se comente en español, cualquier
comentario que empiece con "Todo…" será marcado. Opciones:

1. Marcarlos *Accepted* en Sonar (hay que repetirlo con cada nuevo caso).
2. Añadir una supresión permanente de la regla en
   `sonar-project.properties`, igual que la de `Web:S5247`:

   ```
   sonar.issue.ignore.multicriteria.e2.ruleKey=python:S1135
   sonar.issue.ignore.multicriteria.e2.resourceKey=**/*.py
   ```

   Costo: se pierde la detección de `TODO` reales. Dado que el equipo
   comenta en español, el ruido probablemente supere al beneficio.
3. Redactar los comentarios evitando iniciar con "Todo" (p. ej. "Se hace
   todo en una transacción"). Es la opción que conserva la regla útil.

---

## Sobre el Quality Gate

Con 82 issues nuevos y un gate que exige **0**, el semáforo va a seguir en
rojo aunque se arreglen los 11 de la categoría 🟢. Dos caminos:

1. **Marcar los 🔵 como *Accepted*** en la interfaz de Sonar (Issues →
   seleccionar → *Accept*). Dejan de contar para el gate y queda registrada
   la justificación.
2. **Crear un Quality Gate propio** más realista para un proyecto en
   desarrollo activo: por ejemplo 0 issues nuevos **BLOCKER/HIGH**,
   cobertura ≥ 70%, duplicación ≤ 3%.

Un gate que nunca pasa deja de dar información. Conviene uno alcanzable que
el equipo respete.

Ver también: [semgrep-triage.md](semgrep-triage.md) (mismo criterio aplicado
a Semgrep).
