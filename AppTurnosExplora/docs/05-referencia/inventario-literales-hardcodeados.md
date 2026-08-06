# Inventario: literales de dominio hardcodeados

**Estado: SOLO INVENTARIO. No se ha modificado ningún código.**

Levantamiento previo a decidir un plan de refactor. Fecha: 5 ago 2026.
Origen: los `python:S1192` de [sonarqube-triage.md](sonarqube-triage.md)
destaparon un problema mucho mayor que el que SonarQube reporta.

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

## 4. Estado actual de las constantes en el proyecto

- **No existe** ningún módulo `constants.py`, `constantes.py` ni `enums.py`.
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

## 5. Riesgos identificados para el refactor

| # | Riesgo | Por qué |
|---|---|---|
| 1 | **Confundir los tres `tipo_cambio`** | Uno es FK y dos son CharField. Un reemplazo global por texto los mezclaría. |
| 2 | **Asumir un vocabulario único** | `DOBLADA PERMANENTE` (maestra) vs `DOBLADA PERM` (turnos) son el mismo concepto con dos textos. |
| 3 | **`CharField` sin `choices`** | Nada valida lo que se escribe en `Turno.tipo_cambio`; un typo entra en silencio y solo se nota al leer. |
| 4 | **Valores fuera de la maestra** | `PAGO REPROGRAMADO` y `DOBLADA PERM` no existen en `TipoSolicitudCambio`: no se pueden derivar de ella. |
| 5 | **Registro dinámico de estrategias** | [`solicitud_factory.py`](../../solicitudes/services/solicitud_factory.py) resuelve estrategias leyendo `codigo_estrategia`/`nombre` **desde la BD** en tiempo de ejecución. Cambiar textos afecta el despacho. |
| 6 | **Sin red de seguridad completa** | La suite tiene **1 test fallando** (`test_ceder_hoy_rechazado_en_finde`), preexistente. Conviene resolverlo antes para poder confiar en el verde. |
| 7 | **Volumen** | 54 archivos si se aborda todo; muchos en lógica de dobladas/CT/descansos, la más delicada del sistema. |

---

## 6. Candidatos ordenados por riesgo (para decidir después)

Sin recomendación cerrada: material para que decidas.

### Riesgo MUY BAJO — contenidos en un solo archivo

| Qué | Dónde | Usos |
|---|---|---|
| `'solicitudes:reprog_list'` | `reprogramacion_views.py` | 6 |
| `'solicitudes:cierre_config'` | `cierre_config_views.py` | 4 |
| `'%d/%m/%Y'` | `cancelar_solicitud.py` | 3 |
| `'%d/%m'` | `api_alternancia.py` | 3 |
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

## 7. Preguntas abiertas antes de decidir

1. ¿`DOBLADA PERM` y `DOBLADA PERMANENTE` deben unificarse, o la abreviatura
   en `Turno` es intencional? *(Producción arranca limpia, así que migrar
   datos no sería el obstáculo; el obstáculo es el código que lee ambas.)*
2. ¿`Turno.tipo_cambio` debería tener `choices` para que la BD valide?
3. ¿`PAGO REPROGRAMADO` debería existir como fila en `TipoSolicitudCambio`,
   o es correcto que sea solo un marcador de turno?
4. ¿Se arregla primero `test_ceder_hoy_rechazado_en_finde` para tener la
   suite en verde como red de seguridad?

---

Ver también: [sonarqube-triage.md](sonarqube-triage.md) (triaje completo de
los 61 issues abiertos).
