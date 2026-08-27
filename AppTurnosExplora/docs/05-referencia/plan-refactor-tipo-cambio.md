# Plan quirúrgico: constantes para `Turno.tipo_cambio`

> **Estado: EJECUTADO (Fases 1-3). Verificado el 26 ago 2026.**
> Redactado el 5 ago 2026 como propuesta; se ejecutó después sin actualizar esta
> cabecera, que hasta el 26 de agosto seguía diciendo «no ejecutada».
> Antecedente: [inventario-literales-hardcodeados.md](inventario-literales-hardcodeados.md)
>
> ### Qué se hizo, y en qué se apartó del plan
>
> | Fase | Estado | Desviación respecto a lo planeado |
> |---|---|---|
> | **1** — andamiaje + test | ✅ HECHA | **Vive en `core/constants.py`, no en `turnos/constants.py`**, y usa CLASES (`TipoCambioTurno`) en vez de constantes de módulo (`TIPO_DOBLADA`). Motivo: el mismo módulo acabó albergando los otros vocabularios (`EstadoSolicitud`, `TipoSolicitud`, `EstadoCancelacion`), y agruparlos por clase es lo que hace visible que NO son intercambiables. El test de caracterización es `core/tests/test_constants.py` |
> | **2** — piloto `PAGO REPROGRAMADO` | ✅ HECHA | Sin desviación. Los 3 sitios usan `TipoCambioTurno.PAGO_REPROGRAMADO` |
> | **3** — un literal por commit | ✅ HECHA | 57 usos de `TipoCambioTurno.*`. Los únicos literales crudos que quedan sobre ese campo son `exclude(tipo_cambio='')` (cadena vacía: ausencia de valor, no vocabulario) y menciones en docstrings |
> | **5a** — `choices` + constraint | ✅ **HECHA** (el plan la dejaba «FUERA, fase separada») | `Turno.tipo_cambio` tiene `choices=TipoCambioTurno.CHOICES` **y** un `CheckConstraint` en BD, `turno_tipo_cambio_valido`, que solo admite `NULL` o un valor de `TipoCambioTurno.TODOS` |
> | **5b** — normalizar los textos | ⬜ NO hecha | Sigue pendiente y sigue siendo opcional. `'DOBLADA PERM'` y `'CT'` conservan su texto abreviado |
>
> ### ⚠ El riesgo que justificaba este plan ya NO existe
>
> El §1 dice que alguien puede escribir `Doblada` en vez de `DOBLADA` y dejar un
> turno huérfano sin aviso. **Eso ya no puede pasar:** el `CheckConstraint`
> lo rechaza en la propia base de datos.
>
> Y las dos superficies de escritura que citaba el §1 se redujeron a una:
> `turnos/views/turno_crud.py` **ya no existe** (no hay `TurnoCreateView` ni
> `TurnoUpdateView` en el proyecto). Queda solo el admin de Django, y ahí el campo
> se pinta como desplegable cerrado, no como texto libre.
>
> ### Hallazgos del §10, revisados el 26 ago 2026
>
> | # | Hallazgo | Estado hoy |
> |---|---|---|
> | 1 | `'PERMISO'` fuera de la lista blanca | Ya estaba descartado: correcto por diseño |
> | 2 | `solicitudes/domain/solicitud.py` roto y muerto | ✅ **RESUELTO** — el archivo se borró |
> | 3 | `_get_default_strategy()` falla ABIERTO | ✅ **MITIGADO** — existe `get_strategy_registrada()`, que devuelve `None` en vez de caer al fallback, y la usan los 5 flujos que escriben |
> | 4 | Código muerto en `turno_repository.py` | ✅ **RESUELTO el 26 ago 2026** — `comprometidos_por_tipo_cambio` y `tiene_tipo_cambio` borrados, junto con el test que sostenía al segundo |
> | 5 | `nombre`/`codigo_estrategia` editables desde el admin | ⬜ **ABIERTO** — sigue siendo posible romper el despacho de estrategias sin tocar código |
>
> ### Lo que el plan no vio: un CUARTO vocabulario
>
> El §1 enumera tres campos `tipo_cambio`. Hay un cuarto vocabulario que no es
> un campo de ninguna tabla: la jornada EFECTIVA que devuelve
> `TurnoService.estado_dia()['jornada']` → `'AM' | 'PM' | 'DOBLADA' | None`.
> Comparte el texto `'DOBLADA'` con los otros tres sin significar lo mismo, y
> estaba escrito a mano en **39 sitios de 17 archivos**. Centralizado el
> 26 ago 2026 como `JornadaDisplay` en `core/constants.py`.

---

## 1. Contexto: por qué esto importa

`Turno.tipo_cambio` es un **enum de negocio no declarado**: un `CharField(50)` libre, sin
`choices` ([turnos/models.py:42](../../turnos/models.py#L42)), cuyo valor de texto decide
operaciones destructivas. Sus 8 valores están escritos a mano en ~40 sitios sin una sola
fuente de verdad.

**No es un problema cosmético.** El literal exacto decide:

| Qué decide | Dónde |
|---|---|
| Qué filas se **borran** al revertir (7 `.delete()`, uno por literal) | `doblada_aplicacion_service.py:493`, `d_fds_aplicacion_service.py:125`, `doblada_permanente_aplicacion_service.py:435`, `cambio_turno_strategy.py:292`, `ct_permanente_strategy.py:271`, `cambio_descanso_aplicacion_service.py:712` |
| Qué días se **anulan** por reprogramación (lista blanca) | `doblada_aplicacion_service.py:413` |
| Si se **bloquea** una nueva solicitud de cambio de descanso | `cambio_descanso_aplicacion_service.py:228-236` |
| Si se **genera la deuda** de 30 min | `cambio_descanso_aplicacion_service.py:517-524` |
| Si se **bloquea una cancelación** (huella de integridad) | `cancelar_solicitud.py:337,350,359` |
| Cómo se renderiza en el frontend | `static/js/mis_turnos.js:721` |

~~Y el campo es **texto libre editable desde el admin y el CRUD de turnos**
(`turnos/views/turno_crud.py:99,105`,
[turnos/admin.py:21-22](../../turnos/admin.py#L21)). Alguien puede escribir `Doblada` en vez
de `DOBLADA` y los siete filtros de borrado dejan de verlo: **el turno queda huérfano sin
ningún aviso**.~~

> **OBSOLETO (verificado el 26 ago 2026).** Dos cambios lo desactivaron:
> `turnos/views/turno_crud.py` **fue eliminado** (el enlace de arriba llevaba
> meses roto), y `Turno.tipo_cambio` tiene ahora `choices` más un
> `CheckConstraint` en base de datos (`turno_tipo_cambio_valido`) que rechaza
> cualquier valor fuera de `TipoCambioTurno.TODOS`. Escribir `Doblada` ya no
> es posible ni desde el admin ni por ORM.

**Objetivo del refactor**: una sola fuente de verdad, sin cambiar ni un byte de comportamiento.

### Alcance acordado

- **DENTRO**: solo `Turno.tipo_cambio` (8 valores).
- **FUERA**: los estados (`'aprobada'`, `'pendiente'`, `'cancelada'`…). Son **6 campos
  independientes en 6 modelos** donde `'pendiente'` significa cuatro cosas distintas
  (solicitud sin resolver / deuda sin saldar / día sin reprogramar / correo sin enviar).
  Son 385 ocurrencias en 104 archivos que **no se pueden sustituir automáticamente**:
  cada una exige mirar a qué modelo pertenece. Requiere su propio proyecto.

---

## 2. Principio rector: VALUE-PRESERVING byte a byte

> Las constantes contienen **exactamente** los strings que se escriben hoy, incluidos los
> feos (`'DOBLADA PERM'`, `'CT'`). **Cero cambio de dato persistido.**

### 2.1. Por qué, si producción arranca limpia

El contexto aportado —BD de desarrollo desechable; en producción solo se preservan/recrean
**roles y permisos, jornadas, tipos de solicitud, y el superusuario `manuel.moreno`**—
**debilita** el motivo original de preservar los valores (que romper los snapshots
bloquearía cancelaciones legítimas): esos datos son desechables.

Pero la recomendación se mantiene por **razones distintas y más fuertes**:

**1. Las constantes ABARATAN la normalización, no la retrasan.**
Hoy, unificar `'DOBLADA PERM'` → `'DOBLADA PERMANENTE'` obliga a tocar ~40 sitios. Después
de este refactor es **una sola línea**. Hacer las constantes primero es lo que *habilita*
la normalización, no lo que la posterga.

**2. La red de seguridad son los tests con literales crudos.**
Si producción y tests importaran la misma constante, cambiar su valor **dejaría la suite
verde** mientras rompe los datos. Los `assertEqual(t.tipo_cambio, 'CT PERMANENTE')` que ya
existen en ~15 archivos **son** los tests de caracterización de este refactor.

**3. Hay una 8ª superficie persistida que no estaba en el inventario.**
`turnos_historicalturno` (`simple_history`) tiene **2.086 filas** con `tipo_cambio` — más
que la propia tabla `Turno` (435 filas). Normalizar obliga a decidir qué hacer con ese
histórico.

**4. Separar los dos cambios es lo que hace verificable el refactor.**
Extraer constantes es riesgo cero; cambiar valores es un cambio de comportamiento real.
Mezclados, si algo falla no se puede saber cuál de los dos lo causó.

**Resultado: se obtienen las dos cosas.** Constantes ahora (riesgo cero), normalización
después como Fase 5, barata y deliberada.

### 2.2. Las 8 superficies donde el valor está persistido

Para dimensionar por qué cambiar un valor NO es un refactor:

1. `turnos_turno.tipo_cambio` — 435 filas
2. `turnos_historicalturno.tipo_cambio` — **2.086 filas**
3. `turnos_turnoarchivado.tipo_cambio`
4-10. **7 columnas `JSONField`** de snapshots que contienen `tipo_cambio` **anidado dentro
del JSON**: `solicitudes/models.py:177,185,434,441,511,516` y `permisos/models.py:100`

El serializador es [`doblada_snapshot_service.py:54-84`](../../solicitudes/services/doblada_snapshot_service.py#L54)
(`serializar_pares`), que guarda `{'jornada_nombre':…, 'sala_id':…, 'tipo_cambio': …}`.
Al cancelar, `cancelar_solicitud.py:337` compara `if esperado != actual` y **bloquea la
cancelación** si difieren.

---

## 3. Fase 0 — Precondiciones (bloqueantes)

### 3.1. Limpiar el árbol de trabajo

Hoy hay **11 archivos modificados sin commitear** (incluido `doblada_snapshot_service.py`,
justo el más sensible) + 3 sin seguimiento. Sin limpiarlo, el `git diff` de verificación
—que es el control principal de todo el plan— no sirve para distinguir qué cambió el
refactor y qué venía de antes.

### 3.2. Arreglar `test_ceder_hoy_rechazado_en_finde` en un commit APARTE, ANTES

**No es un test "flaky": está roto.** En
[test_cambio_descanso.py:393-403](../../solicitudes/tests/test_cambio_descanso.py#L393):

```python
def test_ceder_hoy_rechazado_en_finde(self):
    hoy = timezone.localdate()
    if hoy.weekday() not in (5, 6):          # "forzar un hoy de fin de semana"
        hoy = hoy + timedelta(days=(5 - hoy.weekday()) % 7)   # ← lo manda al FUTURO
    ...
    self.assertFalse(ok)
```

Verificado el 5-ago-2026 (miércoles): `hoy` se reasigna al **sábado 8-ago**, una fecha
futura. Entonces la regla que el test dice validar —"la cesión debe ser posterior a hoy"—
**nunca se dispara**, porque la fecha *sí* es posterior. El `assertFalse(ok)` solo pasaba
cuando, por accidente, alguna *otra* regla rechazaba esa fecha.

Sus dos tests hermanos ([:405](../../solicitudes/tests/test_cambio_descanso.py#L405),
[:419](../../solicitudes/tests/test_cambio_descanso.py#L419)) resuelven lo mismo con
`skipTest`. Además, este no asserta el mensaje, así que ni siquiera detecta que está
rechazando por el motivo equivocado.

**Arreglo**: usar `skipTest` como los hermanos + añadir `assertIn('posterior a hoy', msg)`.

### 3.3. Congelar la línea base

```bash
pytest -q --tb=no -n 4 > baseline.txt     # en el scratchpad, fuera del repo
```

Correrla **dos veces** para confirmar que es determinista. Si dos corridas sin cambios
difieren, **parar y resolver eso primero**: sin baseline reproducible, toda la verificación
posterior es humo.

> El criterio de éxito no es "todo verde". Es **"exactamente el mismo conjunto de fallos,
> con los mismos nombres"**.

---

## 4. Fase 1 — Andamiaje (sin call-sites)

Crear `AppTurnosExplora/turnos/constants.py`:

```python
"""Vocabulario de Turno.tipo_cambio. FUENTE ÚNICA.

Los tests asertan estos valores como literales crudos A PROPÓSITO. Si cambias
un valor aquí y la suite sigue verde, algo está mal.

Cambiar un valor de este archivo NO es un refactor: es una migración de datos
que afecta a turnos_turno, turnos_historicalturno (2086 filas) y al contenido
de los 7 JSONField de snapshots.
"""
TIPO_DOBLADA           = 'DOBLADA'
TIPO_DOBLADA_PERM      = 'DOBLADA PERM'       # ⚠ NO es 'DOBLADA PERMANENTE'
TIPO_D_FDS             = 'D FDS'
TIPO_CT                = 'CT'                 # ⚠ NO es 'CAMBIO TURNO'
TIPO_CT_PERMANENTE     = 'CT PERMANENTE'
TIPO_CAMBIO_DESCANSO   = 'CAMBIO DESCANSO'
TIPO_PAGO_REPROGRAMADO = 'PAGO REPROGRAMADO'
TIPO_PERMISO           = 'PERMISO'

TIPOS_ANULABLES_POR_REPROGRAMACION = (
    TIPO_DOBLADA, TIPO_D_FDS, TIPO_DOBLADA_PERM, TIPO_PAGO_REPROGRAMADO,
)
```

### 4.1. Dos decisiones de diseño, ambas deliberadas

**Módulo hoja, NO dentro de `turnos/models.py`** (aunque `EmailOutbox` use ese idiom).
Ya existe un **ciclo real turnos↔solicitudes**: `solicitudes/models.py` importa
`turnos.models` a nivel de módulo, y `turnos/services/*` importan `solicitudes.models`
también arriba. Meter las constantes en `models.py` obligaría a `solicitudes/services/*` y
`permisos/services.py` a importar el módulo de modelos completo solo para leer un string,
ampliando la superficie del ciclo y arriesgando `AppRegistryNotReady` en migraciones y
management commands. `turnos/constants.py` no importa nada: cero riesgo.

**Nombres feos a propósito.** `TIPO_DOBLADA_PERM`, no `TIPO_DOBLADA_PERMANENTE`. El nombre
debe delatar que el valor está abreviado, o el siguiente que lo lea asumirá lo contrario y
volverá a introducir la divergencia.

### 4.2. Test de caracterización

`turnos/tests/test_constantes_valores.py`: 8 `assertEqual` contra literales crudos.
20 líneas que hacen imposible cambiar un valor por accidente.

**Verificación de la fase**: `manage.py check` + suite == baseline.

---

## 5. Fase 2 — Piloto: `PAGO REPROGRAMADO`

El candidato natural. Ya tiene una constante **a medias** en
[reprogramacion_doblada_service.py:28](../../solicitudes/services/reprogramacion_doblada_service.py#L28),
usada en `:285` pero **ignorada en `:82`** — la deriva ya empezó dentro del mismo archivo.

Es el literal con menos usos y **el único que cruza los tres puntos de peligro** a la vez:
escritura del campo, lista blanca de anulación, y frontend. Ejercita el procedimiento
completo a escala mínima.

**Sitios**: `reprogramacion_doblada_service.py:28,82,285`, `doblada_aplicacion_service.py:413`,
`turnos_mes.py:267`.

**Verificación**: `pytest solicitudes/tests/test_reprogramacion_doblada.py -q`, luego suite.

---

## 6. Fase 3 — Un literal por commit

Orden **creciente en peligro de sustitución**, no en número de usos:

```
D FDS → CT PERMANENTE → CAMBIO DESCANSO → PERMISO → DOBLADA PERM → CT → DOBLADA
```

- **`'CT'` casi al final** pese a tener pocos usos: son **2 caracteres**, aparece dentro de
  `'CT PERMANENTE'` y de nombres de variables. Solo sustitución manual, **jamás `sed`**.
- **`'DOBLADA'` último**: 165 usos y es substring de `'DOBLADA PERM'`.

### 6.1. Procedimiento por literal (ciclo repetible)

**1. Inventariar y congelar el conteo** con `grep -rn`. Ese número es el contrato del commit.

**2. Clasificar cada hit en 4 cubos ANTES de editar nada:**

| Cubo | Qué es | Acción |
|---|---|---|
| (a) | `Turno.tipo_cambio` (CharField) | **se sustituye** |
| (b) | `TipoSolicitudCambio.nombre` / `codigo_estrategia` (FK) | **NO se toca en esta fase** |
| (c) | Tests | **NO se tocan** (§6.2) |
| (d) | Migraciones, `scripts/`, comandos forenses | **NO se tocan** (§7) |

> Confundir (a) con (b) es **el error #1 posible** en este refactor: son dos vocabularios
> distintos que casualmente comparten algunos textos.

**3. Sustituir a mano, un archivo a la vez.** Prohibido el reemplazo global: hay literales
en docstrings y en mensajes de usuario (`f"No puedes cancelar una solicitud aprobada"`) que
**no** son el valor del campo.

**4. Control de invariancia sintáctica** — el que más errores atrapa y corre en segundos:

```bash
git diff -U0
```

Comprobar que **cada par de líneas `-`/`+` difiere únicamente en `literal → constante`**,
más el bloque de imports. Cualquier otra diferencia (un `==` que se volvió `in`, un espacio
dentro del string, un `.upper()` que desapareció) es un bug introducido.

**5. Tests del área**, luego suite completa contra `baseline.txt`:

| Literal | Comando |
|---|---|
| `DOBLADA` | `pytest solicitudes/tests/test_doblada*.py solicitudes/tests/test_cancelacion_integridad.py -q` |
| `D FDS` | `pytest solicitudes/tests/ -q -k "fds or finde"` |
| `CT` / `CT PERMANENTE` | `pytest solicitudes/tests/test_ct_permanente_intercambio.py solicitudes/tests/test_cambio_turno_revert.py -q` |
| `CAMBIO DESCANSO` | `pytest solicitudes/tests/test_cambio_descanso.py -q` |
| `DOBLADA PERM` | `pytest solicitudes/tests/ -q -k "permanente"` |

**6. Commit atómico**, revertible por sí solo.

### 6.2. Los tests NO se migran a constantes

Decisión deliberada, no pereza.

Si producción y tests importan la misma constante, cambiar
`TIPO_DOBLADA_PERM = 'DOBLADA PERM'` a `'DOBLADA PERMANENTE'` **deja la suite verde** y
rompe en silencio 55 filas + 2.086 filas históricas + 9 snapshots. Migrar los tests
destruye exactamente la red de seguridad que este refactor necesita.

Los snapshots JSON hardcodeados en `test_cancelacion_integridad.py:81-82,201-202` son
**doblemente intocables**: son fixtures de un formato persistido, equivalentes a datos de
producción.

> **Regla operativa**, escrita en la cabecera de `turnos/constants.py`:
> *"Si cambias un valor aquí y la suite sigue verde, algo está mal."*

---

## 7. Qué NO tocar

| No tocar | Por qué |
|---|---|
| `*/migrations/**` | Una migración es un snapshot histórico. Importar una constante acopla el historial al presente y rompe `migrate` en cuanto el valor cambie |
| `scripts/`, comandos forenses (`diagnosticar_*`, `verificar_*`) | Artefactos ligados a incidentes pasados; cero ganancia, ruido en el diff |
| `doblada_snapshot_service.py:54-84` y `cancelar_solicitud.py:337,350,359` | **Objetivo: cero líneas modificadas.** Cualquier cambio en el orden de claves o el formato de la huella cambia el byte serializado. **Si el procedimiento obliga a tocarlos, parar y reevaluar** |
| `static/js/mis_turnos.js:721` | Python y JS no comparten módulo; una constante JS sería una segunda fuente de verdad que puede divergir en silencio. Dejar el literal + comentario de referencia cruzada. (El arreglo real es exponer el tipo desde el backend: otro proyecto) |
| `choices` en el modelo | No es value-preserving: cambia validación en `full_clean()` y los formularios del admin. Fase separada |
| `TurnoArchivado.tipo_cambio` | Solo se escribe, nunca decide nada. Bajísimo valor, riesgo no nulo |
| Estados (`'aprobada'`…), `PermisoEspecial`, `EmailOutbox` | Fuera del alcance acordado |

---

## 8. Verificación objetiva

Cuatro capas. Usar las cuatro.

**(A) Equivalencia de valores reales** — antes de la Fase 2 y después de la Fase 3:

```python
Turno.objects.values('tipo_cambio').annotate(n=Count('id')).order_by('tipo_cambio')
```

Los dos outputs deben ser **idénticos, incluida la fila `None`**. Repetirlo sobre
`turnos_historicalturno` y sobre el conjunto de `tipo_cambio` que viven **dentro** de los
7 JSONField. Un valor nuevo o un conteo desplazado = principio rector violado.

**(B) `test_constantes_valores.py`** (Fase 1) — cierra el agujero de "cambiar el valor sin
que nadie lo note".

**(C) Grep de residuo**, como métrica de avance (no de corrección). Los hits que quedan en
tests/migraciones/scripts son el resultado **esperado**, no deuda.

**(D) El diff-check de §6.1.4** — en la práctica es la verificación primaria: corre en
segundos y atrapa la gran mayoría de errores mecánicos, mucho antes que los tests.

---

## 9. Fase 5 (posterior, opcional) — Normalizar el vocabulario

Solo **después** de que las constantes estén estables, y como decisión explícita aparte.

Con la fuente única en su sitio, unificar `'DOBLADA PERM'` → `'DOBLADA PERMANENTE'` y
`'CT'` → `'CAMBIO TURNO'` es **cambiar una línea por concepto**, más:

- resetear los datos de desarrollo (son desechables), o un `RunPython` que cubra
  `turnos_turno`, `turnos_historicalturno` **y el contenido anidado de los 7 JSONField**;
- actualizar los ~15 archivos de test que asertan el valor viejo;
- opcionalmente, `choices` + constraint siguiendo el **precedente del propio proyecto**:
  [`turnos/migrations/0013_diaespecial_tipo_choices_y_unicidad.py`](../../turnos/migrations/0013_diaespecial_tipo_choices_y_unicidad.py)
  (`RunPython` + `AlterField(choices)` + `AddConstraint`).

---

## 10. Hallazgos a REPORTAR, no a arreglar aquí

Cambiarlos alteraría comportamiento y contaminaría la verificación del refactor.

1. ~~**`'PERMISO'` no está en la lista blanca de anulación**~~ — **DESCARTADO, no es un
   hallazgo.** Se planteó como posible asimetría y al verificarlo resultó **correcto por
   diseño**:
   - `anular_doblada_de_un_dia` (`doblada_aplicacion_service.py:396`) anula **dobladas**, y
     su lista blanca `['DOBLADA','D FDS','DOBLADA PERM','PAGO REPROGRAMADO']` son las
     cuatro formas que toma una doblada.
   - Solo se la llama desde `reprogramacion_doblada_service.py:250,330`, es decir al
     reprogramar una doblada.
   - `PERMISO` no es una doblada, igual que tampoco lo son `CT` ni `CAMBIO DESCANSO`, que
     tampoco están en la lista.
   - `PERMISO` tiene **su propia vía de reversión**: `PermisoService.revertir()`
     (`permisos/services.py:218`) restaura desde su propio snapshot, con la guarda
     `puede_revertir_limpio()` (`:229`) que bloquea la cancelación si otro flujo tocó esos
     días.

   > Lección: la asimetría se detectó por patrón (un valor ausente de una lista) sin leer
   > para qué servía la lista. **Al centralizar las constantes esta clase de "asimetría
   > aparente" se va a hacer más visible; la regla es leer el propósito de cada lista antes
   > de tocarla.**

2. **`solicitudes/domain/solicitud.py` está roto y muerto.** Su línea 13 importa
   `TRANSICIONES, ESTADOS_TERMINALES`, pero `estado_machine.py` solo define `_TRANSICIONES`
   y `_ESTADOS_VALIDOS` (privados). **Verificado**: lanza
   `ImportError: cannot import name 'TRANSICIONES'` y **ningún archivo lo importa**.
   Riesgo: si se toca `estado_machine.py` y "de paso" se exportan esos nombres, se activa
   un módulo muerto y sin tests.

3. **`_get_default_strategy()` falla ABIERTO** (`solicitud_factory.py:189-202`): un tipo de
   solicitud desconocido se procesa **silenciosamente como cambio de turno**, con solo un
   `logger.warning`. No hay excepción ni bloqueo.

4. ~~**Código muerto**: `turno_repository.py:39-48` (`comprometidos_por_tipo_cambio`) y
   `:59-62` (`tiene_tipo_cambio`) no tienen llamadores en producción, solo en tests. El
   docstring dice "Usado por CambioDescansoFindesView", pero esa vista ya no lo usa.~~
   **RESUELTO el 26 ago 2026.** Ambos métodos borrados. `tiene_tipo_cambio` tenía un test
   (`test_repositories.py`) y se borró con él: un test que solo prueba código que nadie
   llama mantiene vivo el código muerto y da una sensación falsa de cobertura.

5. **`TipoSolicitudCambio.nombre` y `codigo_estrategia` son editables desde el admin**
   (`admin.py:70,72`, `dashboard_admin.py:54,60`): un usuario administrador puede **romper
   el despacho de estrategias sin tocar código**.

---

## 11. Riesgo de coordinación

165 call-sites de `DOBLADA` repartidos en 47 archivos generan conflictos con cualquier rama
en vuelo. Conviene **ventana corta y rama efímera**: si el refactor se alarga, la
resolución manual de conflictos reintroduce literales y deshace el trabajo en silencio.

---

## 12. Preguntas abiertas

1. ¿Se acepta el principio value-preserving, o se prefiere normalizar de una vez
   aprovechando que producción arranca limpia? *(La propuesta razona que separar es mejor
   incluso en ese escenario — §2.1.)*
2. ¿`'DOBLADA PERM'` abreviado en `Turno` es intencional, o deriva histórica?
3. ¿Se quiere `choices` en el campo eventualmente, asumiendo que convierte el input libre
   del admin en un desplegable cerrado?

*(La pregunta sobre `'PERMISO'` se retiró: verificada y descartada — ver §10.1.)*

---

Ver también:
[inventario-literales-hardcodeados.md](inventario-literales-hardcodeados.md) ·
[sonarqube-triage.md](sonarqube-triage.md) ·
[PROTECTION_PATTERNS.md](../../../PROTECTION_PATTERNS.md)
