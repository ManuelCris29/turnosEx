# Inventario: literales de dominio hardcodeados

**Estado: EJECUTADO.** Rama `refactor/constantes-dominio`. Fecha: 5 ago 2026.

Origen: los `python:S1192` de [sonarqube-triage.md](sonarqube-triage.md)
destaparon un problema mucho mayor que el que SonarQube reporta.

## Qué se hizo

| Fase | Qué | Commit |
|---|---|---|
| — | **Bug**: `tipo_cambio__nombre='CT'` no casaba con ninguna fila | `cdd8a2c` |
| 1 | Literales de riesgo muy bajo a constantes de módulo | `80b435e` |
| 2 | `core/constants.py`: `EstadoSolicitud`, `TipoSolicitud`, `TipoCambioTurno` | `6680164` |
| 3 | `choices` + `CheckConstraint` en `Turno.tipo_cambio` | `2442bc3` |
| 4 | `TipoCambioTurno` en los 9 servicios que escriben turnos | `52bec93` |

Suite: 792 → **802 passed** (10 tests nuevos, cero regresiones).

## Correcciones a este inventario

La auditoría previa encontró cinco datos equivocados aquí. Se dejan anotados
porque explican por qué el plan salió distinto de lo previsto:

1. **`SolicitudCambio.estado` tiene 6 valores, no 4**: faltaban `pagada` y
   `reemplazada`. Y el campo ya tenía `choices`, así que la BD ya lo validaba:
   la sección 6 lo clasificaba como riesgo ALTO sin serlo.
2. **Falta `'PERMISO'`** en la tabla de valores de `Turno.tipo_cambio` (§3). Lo
   escribe [permisos/services.py:212](../../permisos/services.py#L212). Aún sin
   filas, pero es un valor legítimo: son **cinco** vocabularios en la columna,
   no cuatro.
3. **La suite NO tenía 1 test fallando** (riesgo #6). Estaba entera en verde:
   792 passed, 0 skips. El dato estaba desactualizado.
4. **`'%d/%m'` en `api_alternancia.py` tiene 1 uso, no 3** (§6). Se omitió del
   refactor: una constante para un uso único no aporta.
5. **`TurnoArchivado` se llama `TurnoArchivo`**
   ([turnos/models.py:199](../../turnos/models.py#L199)).

Y dos cosas que el inventario no llegó a ver:

- **El JS es el foco real de duplicación**: 41 usos de `DOBLADA` en 9 archivos
  de `static/js/` y ~22 de `aprobada`. Las constantes Python no lo alcanzan.
  Sigue pendiente — ver "Lo que queda".
- **Hay un TERCER vocabulario que también dice `'DOBLADA'`**: el display de
  jornada que devuelve `estado_dia(...)['jornada']` (`AM` / `PM` / `DOBLADA` /
  `Descanso`). No tiene relación con `tipo_cambio` aunque comparta el texto.
  Sustituirlo por la constante habría atado dos conceptos distintos por
  coincidencia tipográfica.

---

## 1. Por qué SonarQube subestima el problema

La regla `S1192` solo dispara cuando un literal se repite **3+ veces dentro
de un mismo archivo**. Reporta 9 casos. El recuento real por el proyecto
(excluyendo `tests/` y `venvturnos/`):

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

Concentración de `'DOBLADA'` (top 8):

| Archivo | Usos |
|---|---|
| `turnos/services/turno_service.py` | 19 |
| `turnos/api/views/turnos_mes.py` | 14 |
| `solicitudes/views/api_turno_jornada.py` | 13 |
| `solicitudes/views/doblada_api.py` | 9 |
| `solicitudes/services/strategies/doblada_strategy.py` | 7 |
| `solicitudes/services/doblada_pago_service.py` | 7 |
| `solicitudes/services/doblada_aplicacion_service.py` | 7 |
| `solicitudes/services/ct_permanente_helper.py` | 7 |

---

## 2. ⚠ Lo más importante: hay TRES campos `tipo_cambio` distintos

Cualquier refactor tiene que respetar esta distinción o romperá cosas.

| Modelo | Campo | Tipo | Qué guarda |
|---|---|---|---|
| `SolicitudCambio` | `tipo_cambio` | **ForeignKey** → `TipoSolicitudCambio` | Relación a la tabla maestra |
| `Turno` | `tipo_cambio` | **CharField(50)**, libre, sin `choices` | Texto denormalizado |
| `TurnoArchivado` | `tipo_cambio` | **CharField(50)**, libre | Copia histórica |

Referencias:
[solicitudes/models.py:141](../../solicitudes/models.py#L141),
[turnos/models.py:42](../../turnos/models.py#L42),
[turnos/models.py:199](../../turnos/models.py#L199).

Esto hace que existan dos formas de consulta que **parecen** lo mismo y no lo
son:

```python
# FK: atraviesa la relación hacia la tabla maestra
SolicitudCambio.objects.filter(tipo_cambio__nombre__in=['DOBLADA', 'D FDS'])

# CharField: compara texto plano guardado en la fila del turno
Turno.objects.filter(tipo_cambio='DOBLADA PERM')
```

Frecuencia de cada patrón en el código:

| Patrón | Usos |
|---|---|
| `tipo_cambio=` (asignación/filtro CharField) | 73 |
| `tipo_cambio__nombre=` (FK) | 53 |
| `tipo_solicitud.nombre` | 27 |
| `tipo_cambio__nombre__in` (FK) | 18 |
| `tipo_cambio.nombre ==` | 1 |

---

## 3. ⚠⚠ Los vocabularios NO coinciden entre sí

Esto es lo que hace peligroso "centralizar en una constante por concepto".

### Tabla maestra `TipoSolicitudCambio` (6 filas, todas activas)

| `nombre` | `codigo_estrategia` |
|---|---|
| `CAMBIO DESCANSO` | `CAMBIO DESCANSO` |
| `CAMBIO TURNO` | **`CT`** |
| `CT PERMANENTE` | `CT PERMANENTE` |
| `D FDS` | `D FDS` |
| `DOBLADA` | `DOBLADA` |
| `DOBLADA PERMANENTE` | `DOBLADA PERMANENTE` |

### Valores REALES en `Turno.tipo_cambio` (consultado en la BD de desarrollo)

| Valor guardado | Filas | ¿Coincide con la maestra? |
|---|---|---|
| `DOBLADA` | 163 | ✅ = `nombre` |
| `CT` | 74 | ⚠ = `codigo_estrategia`, **no** el `nombre` (`CAMBIO TURNO`) |
| `CAMBIO DESCANSO` | 68 | ✅ = `nombre` |
| **`DOBLADA PERM`** | 55 | ❌ **no existe**: la maestra dice `DOBLADA PERMANENTE` |
| `CT PERMANENTE` | 34 | ✅ = `nombre` |
| `NULL` | 29 | ✅ legítimo (turno sin cambio) |
| **`PAGO REPROGRAMADO`** | 8 | ❌ **no existe en la tabla maestra** |
| `D FDS` | 4 | ✅ = `nombre` |
| **`PERMISO`** | 0 | ❌ **no existe en la maestra**; lo escribe `permisos/services.py` |

> Recuento repetido con `Turno.all_objects` (incluye anulados, que el manager
> por defecto oculta) y sobre `TurnoArchivo`: no aparece ningún valor más. La
> lista de 8 está completa y es la que valida la `CheckConstraint`.

> Verificado que los 29 son `NULL` reales, **no** el string `'None'`
> (`tipo_cambio__isnull=True` → 29; `tipo_cambio='None'` → 0).

**En una sola columna conviven cuatro vocabularios:**

1. Valores de `nombre` (`DOBLADA`, `CAMBIO DESCANSO`, `CT PERMANENTE`, `D FDS`)
2. Valores de `codigo_estrategia` (`CT`)
3. Abreviaturas propias (`DOBLADA PERM`)
4. Estados que no están en la maestra (`PAGO REPROGRAMADO`)

**Consecuencia para el refactor**: no se puede escribir
`TIPO_DOBLADA_PERMANENTE = 'DOBLADA PERMANENTE'` y usarlo en todos lados. Las
filas de `Turno` guardan `'DOBLADA PERM'`. Son **dos constantes distintas
para el mismo concepto**, según el campo que se consulte.

### Dónde vive cada valor divergente

`'DOBLADA PERM'` (11 apariciones):

- [ct_permanente_helper.py:373,374,563](../../solicitudes/services/ct_permanente_helper.py#L373)
- [doblada_aplicacion_service.py:413](../../solicitudes/services/doblada_aplicacion_service.py#L413)
- [doblada_permanente_aplicacion_service.py:289,300,393,397,435](../../solicitudes/services/doblada_permanente_aplicacion_service.py#L289)
- [reprogramacion_doblada_service.py:62,65](../../solicitudes/services/reprogramacion_doblada_service.py#L62)

`'PAGO REPROGRAMADO'`:

- [doblada_aplicacion_service.py:413](../../solicitudes/services/doblada_aplicacion_service.py#L413)
- [reprogramacion_doblada_service.py:28,82](../../solicitudes/services/reprogramacion_doblada_service.py#L28)
- [turnos_mes.py:267](../../turnos/api/views/turnos_mes.py#L267)

`'CT'` escrito en `Turno.tipo_cambio`:

- [cambio_turno_strategy.py:292,332,468,513](../../solicitudes/services/strategies/cambio_turno_strategy.py#L292)

---

## 4. Estado de las constantes ANTES del refactor

> Hoy existe [`core/constants.py`](../../core/constants.py) con
> `EstadoSolicitud`, `TipoSolicitud`, `TipoCambioTurno` y
> `MAPA_SOLICITUD_A_TURNO`. Lo de abajo es el punto de partida.

- **No existía** ningún módulo `constants.py`, `constantes.py` ni `enums.py`.
- **No se usa** `models.TextChoices` en ninguna parte.
- Solo **una** constante de dominio está definida en todo el proyecto:

  ```python
  # solicitudes/services/reprogramacion_doblada_service.py:28
  TIPO_PAGO_REPROGRAMADO = 'PAGO REPROGRAMADO'
  ```

  Y **ni siquiera se usa de forma consistente dentro de su propio archivo**:

  | Línea | Cómo se usa |
  |---|---|
  | 28 | Se define la constante |
  | 82 | Usa el **literal** `'PAGO REPROGRAMADO'` |
  | 285 | Usa la **constante** `TIPO_PAGO_REPROGRAMADO` |

  Es la prueba en miniatura del problema: definir la constante no basta si no
  hay disciplina o una regla que la imponga.

- El patrón correcto **sí existe** para otro modelo:
  [`EmailOutbox`](../../solicitudes/models.py#L68) define
  `ESTADO_PENDIENTE`, `ESTADO_ENVIANDO`, `ESTADO_ENVIADO`, `ESTADO_FALLIDO` y
  construye `ESTADO_CHOICES` con ellas. Los demás modelos
  ([models.py:559,634,722](../../solicitudes/models.py#L559)) usan tuplas de
  strings crudos.

---

## 5. Riesgos identificados, y cómo se resolvió cada uno

| # | Riesgo | Cómo quedó |
|---|---|---|
| 1 | **Confundir los tres `tipo_cambio`** | Resuelto por construcción: `TipoSolicitud` y `TipoCambioTurno` son namespaces separados y no se pueden mezclar sin que salte a la vista. **El riesgo ya se había materializado**: ver §8. |
| 2 | **Asumir un vocabulario único** | No se unificaron. `MAPA_SOLICITUD_A_TURNO` hace explícitas las dos correspondencias que no son la identidad, con un test que lo verifica. |
| 3 | **`CharField` sin `choices`** | **Resuelto.** `choices` + `CheckConstraint`. Los `choices` solos no bastaban: Django solo los comprueba en `full_clean()`, que ningún servicio llama. |
| 4 | **Valores fuera de la maestra** | Confirmado y asumido: `PAGO REPROGRAMADO` y `PERMISO` viven solo en `TipoCambioTurno`, con un test que fija que son exactamente esos dos. |
| 5 | **Registro dinámico de estrategias** | **No se tocó** `solicitud_factory.py`. Se añadió un test que verifica que cada `TipoSolicitud` resuelve una estrategia y no cae en el fallback silencioso a `CambioTurnoStrategy`. |
| 6 | ~~1 test fallando~~ | Dato equivocado: la suite estaba en verde (792 passed, 0 skips). |
| 7 | **Volumen** | Acotado: solo los 9 servicios que ESCRIBEN turnos, que es donde un literal errado corrompe datos. Las lecturas transversales quedan fuera. |

---

## 6. Candidatos ordenados por riesgo (para decidir después)

Sin recomendación cerrada: material para que decidas.

### Riesgo MUY BAJO — contenidos en un solo archivo

| Qué | Dónde | Usos |
|---|---|---|
| `'solicitudes:reprog_list'` | `reprogramacion_views.py` | 6 |
| `'solicitudes:cierre_config'` | `cierre_config_views.py` | 4 |
| `'%d/%m/%Y'` | `cancelar_solicitud.py` | 3 |
| ~~`'%d/%m'`~~ | ~~`api_alternancia.py`~~ | ~~3~~ → **1 real, omitido** |
| `'Año inválido.'` | `descanso_semana.py` | 3 |
| `'Error al procesar la solicitud'` | `solicitud_orchestrator.py` | 3 |

Son nombres de ruta, formatos y mensajes: no tocan lógica de negocio ni
valores persistidos. Coinciden casi 1:1 con los `S1192` que Sonar reporta.

### Riesgo MEDIO — un concepto, pocos archivos

| Qué | Archivos | Nota |
|---|---|---|
| `'PAGO REPROGRAMADO'` | 4 | Ya tiene constante definida; sería completarla |
| `'DOBLADA PERM'` | 4 | Requiere decidir si se unifica con `DOBLADA PERMANENTE` |
| `'D FDS'` | 21 | Valor consistente entre maestra y turnos |

### Riesgo ALTO — transversales

| Qué | Archivos | Nota |
|---|---|---|
| `'DOBLADA'` | 47 | Aparece como FK y como CharField |
| `'aprobada'` / `'pendiente'` / `'cancelada'` | 54 / 43 / 27 | Estados de solicitud; atraviesan todo el flujo |

---

## 7. Preguntas abiertas: cómo se respondieron

1. **¿Unificar `DOBLADA PERM` y `DOBLADA PERMANENTE`?** No. Son vocabularios de
   campos distintos y el despacho de estrategias depende del segundo. Se
   documenta la correspondencia en `MAPA_SOLICITUD_A_TURNO`; unificar sigue
   siendo posible después, y ese mapa sería el único sitio a cambiar.
2. **¿`choices` en `Turno.tipo_cambio`?** Sí, más `CheckConstraint`, que es lo
   que de verdad valida.
3. **¿`PAGO REPROGRAMADO` como fila de la maestra?** No. Es un marcador de
   turno, no un tipo de solicitud: nadie *pide* un pago reprogramado.
4. **¿Arreglar el test que fallaba?** No hacía falta: la suite estaba verde.

---

## 8. El bug que destapó la auditoría

Antes de tocar nada se clasificó cada filtro sobre `tipo_cambio` como FK o
CharField. De los 58 del lado FK, uno usaba el vocabulario equivocado:

```python
# solicitudes/views/doblada_api.py — dos veces
tipo_cambio__nombre='CT',  # 'CT' es el codigo_estrategia, el nombre es 'CAMBIO TURNO'
```

Filas de la maestra con `nombre='CT'`: **0**. Solicitudes que casaba el filtro:
**0**, siempre. Solicitudes `CAMBIO TURNO` aprobadas que debía encontrar: **52**.

Efecto: la regla *"ya tienes un cambio de turno aprobado para esta fecha, no
puedes pedir doblada"* nunca disparaba. Fallaba en silencio y en la dirección
permisiva.

El test que cubría el caso pasaba porque su fixture fabricaba un
`TipoSolicitudCambio(nombre='CT')` que no existe en producción: verificaba el
filtro incorrecto contra un dato igual de incorrecto.

Corregido en `cdd8a2c`. Es el argumento entero a favor de los dos namespaces
separados: con `TipoSolicitud.CAMBIO_TURNO` y `TipoCambioTurno.CT` el error deja
de ser expresable.

La `CheckConstraint` destapó tres casos más del mismo tipo, todos en tests:
`tipo_cambio='TEST'` (un marcador inventado, en ~100 turnos de
`test_matriz_dobladas.py`) y `tipo_cambio='CAMBIO TURNO'` escrito en el
CharField en otros dos archivos.

---

## 9. Lo que queda pendiente

- **El front (41 usos de `DOBLADA` en `static/js/`, ~22 de `aprobada`).** Es el
  foco real de duplicación y las constantes Python no lo alcanzan. Requiere
  exponerlas vía context processor o endpoint JSON: es un diseño aparte, no una
  sustitución mecánica.
- **Los estados en las 54/43 ubicaciones.** `EstadoSolicitud` ya existe; su
  adopción masiva es riesgo alto y beneficio bajo, porque el campo ya tiene
  `choices` y la BD ya restringe los valores.
- **`solicitud_factory.py`**, deliberadamente intacto.
- **La tabla maestra no la crea ninguna migración de datos.** Las 6 filas se
  crearon a mano en desarrollo. Si producción arranca limpia, habrá que crearlas
  antes de que el sistema funcione — conviene una migración de datos o un
  comando de seed.
- **`scripts/tests/test_architecture.py`** filtra `nombre="CT"` con el mismo
  error del §8. Solo imprime un diagnóstico, así que no se tocó.
- **Colación de MySQL.** Es case-insensitive por defecto, así que la constraint
  acepta `'doblada'` como `'DOBLADA'`. Los filtros del ORM comparan igual y
  tampoco lo notarían; solo un `==` en Python distinguiría.

---

Ver también: [sonarqube-triage.md](sonarqube-triage.md) (triaje completo de
los 61 issues abiertos).
