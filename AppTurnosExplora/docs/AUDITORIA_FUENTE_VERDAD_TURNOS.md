# Auditoría: Fuente de Verdad del Estado del Día (Turnos)

**Fecha:** 2026-06-26
**Contexto:** Tras reorganizar el formulario de *Cambio de Día de Descanso*, se detectó que
el sistema tiene **varias fuentes de verdad desalineadas** para saber si un explorador
**trabaja o descansa** un día. Este documento audita los 6 formularios de solicitud y
propone unificar la lógica en una sola función canónica.

---

## La regla del negocio (confirmada con el usuario)

> Siempre se mira **primero el registro `Turno`** (ahí se hacen las modificaciones reales).
> Si ese día **no existe** un registro `Turno`, entonces se usa el **turno virtual /
> predeterminado** (jornada base + alternancia), teniendo en cuenta además los
> **días especiales**: temporada, mantenimiento, festivos y descansos por solicitudes
> aprobadas.

---

## Las 6 capas del estado de un día

| # | Capa | Significado |
|---|------|-------------|
| L1 | **Turno real** | Registro `Turno` del día (cambio aprobado, doblada, etc.). Máxima prioridad. |
| L2 | **Día comprometido por solicitud aprobada** | El día quedó en descanso por una DOBLADA / D FDS / CAMBIO DESCANSO / DOBLADA PERMANENTE aprobada (sin registro `Turno`). |
| L3 | **Mantenimiento** | Lunes de mantenimiento efectivo → descansan AM y PM. |
| L4 | **Temporada** | `DescansoSemanaManual` (descanso entre semana por jornada). |
| L5 | **Festivos / días especiales** | `DiaEspecial` tipo festivo. En festivo entre semana, el grupo que dobla por **rotación** (`FestivosRotacionService`) trabaja AM+PM (DOBLADA) y el grupo contrario DESCANSA. Esta regla MANDA sobre el horario predeterminado/importado; un cambio EXPLÍCITO (turno con `tipo_cambio`, p. ej. festivo-por-festivo) se respeta por encima. |
| L6 | **Alternancia de fin de semana** | Sáb/Dom: un grupo trabaja un día (AM+PM) y descansa el otro. |

### Dónde vive cada capa hoy

- **`JornadaService.get_jornada_explorador_fecha`** (lo que usan casi todos los forms):
  cubre **solo L1 + jornada base de grupo**. No aplica alternancia ni días especiales.
  Devuelve el *grupo* (AM/PM), no si trabaja/descansa.
- **`JornadaUtils.calcular_jornada_dia`** (virtual): cubre **L6**. Entre semana
  **siempre** devuelve la jornada base (no sabe de L3/L4/L5).
- **`TurnoService.get_turno_explorador`**: cubre **L1 + L6**. Le faltan **L2, L3, L4, L5**.
- **`MisTurnosPorMesView`** (lo que ve el usuario): **única que cubre las 6 capas**,
  pero la lógica está embebida en la vista (no reutilizable).

---

## Auditoría por formulario

| Formulario | L1 | L2 | L3 Mantenim. | L4 Temporada | L5 Festivos | L6 Alternancia | Riesgo |
|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **CT PERMANENTE** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟢 Bajo (migrado 2026-06-26) |
| **CAMBIO TURNO** | ✅ | ✅ | ✅ | ✅ | ✅ | n/a (solo entre semana) | 🟢 Bajo (migrado 2026-06-26) |
| **DOBLADA** | ✅ | ✅ | ✅ | ✅* | ✅ | ⚠️ parcial | 🟢 Bajo (migrado 2026-06-26) |
| **DOBLADA PERMANENTE** | ✅ | ✅ | ✅ | ✅ | ✅* | n/a | 🟢 Bajo (migrado 2026-06-26) |
| **D FDS** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 🟢 Bajo (migrado 2026-06-26) |
| **CAMBIO DESCANSO** | ✅ | ✅ | n/a | ✅ | ✅ | ✅ | 🟢 Bajo (corregido 2026-06-26) |

> Las marcas se basan en `grep` de cada `*_strategy.py` (uso de `Turno.objects`,
> `JornadaService`, `DiaEspecial`, `mantenimiento`, `DescansoSemanaManual`, `es_festivo`).
> ⚠️ = cobertura parcial o delegada; conviene verificar al migrar.

---

## Los 2 problemas sistémicos

### 1. L2 — "Día ya comprometido" falta en TODOS menos CAMBIO DESCANSO
Ningún otro formulario verifica si el día ya fue cedido/comprometido por **otra solicitud
aprobada**. Riesgo: encadenar dos operaciones sobre el mismo día (doble compromiso) →
estado corrupto (familia del bug #287).

### 2. Inconsistencia en días especiales
Cada formulario reimplementó los chequeos a mano, por eso:
- **DOBLADA** y **D FDS** no miran **temporada (L4)**.
- **D FDS** no mira **festivos (L5)**.
- **DOBLADA PERMANENTE** no cubre **festivos/mantenimiento** completo.

Ejemplo de impacto: **D FDS podría permitir operar sobre un día de temporada o festivo**
donde la jornada en realidad no aplica.

---

## Riesgo priorizado (orden de migración sugerido)

1. **D FDS** — mayor exposición: faltan festivos + temporada + L2.
2. **DOBLADA** — falta temporada + L2 (alto uso → más impacto).
3. **DOBLADA PERMANENTE** — cobertura parcial de especiales + L2.
4. **CAMBIO TURNO / CT PERMANENTE** — bien cubiertos; solo les falta L2.

---

## Solución propuesta: una sola función canónica

Crear **`TurnoService.estado_dia(empleado, fecha)`** que aplique las 6 capas en orden y
devuelva el estado real del día. Todos los formularios, endpoints y (gradualmente)
`MisTurnos` deben consumirla. Una fuente, un comportamiento.

```python
estado_dia(empleado, fecha) -> {
    'trabaja': bool,
    'jornada': 'AM' | 'PM' | 'DOBLADA' | None,
    'fuente': 'turno' | 'solicitud' | 'mantenimiento' | 'temporada' | 'alternancia' | 'base',
    'motivo': str | None,        # descripción del descanso
    'es_festivo': bool,          # bandera (regla de negocio la decide el caller)
    'companero': dict | None,    # si descansa por una solicitud, con quién
}
```

### Orden de evaluación (fiel a `MisTurnosPorMesView`)
1. **L1** Turno real → trabaja (AM/PM/DOBLADA).
2. **L2** Descanso por solicitud aprobada → descansa.
3. **L6** Fin de semana: si por alternancia le toca → trabaja (DOBLADA); si no → descansa.
4. **L3/L4** Entre semana: mantenimiento o temporada → descansa.
5. **Base**: jornada predeterminada → trabaja.
6. **L5** Festivo: se expone como bandera `es_festivo` (no fuerza descanso; cada
   formulario aplica su regla, p. ej. "no pago en festivo").

### Plan de adopción (incremental, con pruebas por formulario)
1. ✅ Crear `estado_dia()` + tests (sin tocar formularios). — *hecho 2026-06-26*
2. ✅ Migrar **D FDS**. — *hecho 2026-06-26*
3. ✅ Migrar **DOBLADA**. — *hecho 2026-06-26*
4. ✅ Migrar **DOBLADA PERMANENTE**. — *hecho 2026-06-26*
5. ✅ Migrar **CAMBIO TURNO** y **CT PERMANENTE** (cerrar L2). — *hecho 2026-06-26*
6. ✅ Refactorizar `MisTurnosPorMesView` para usar `estado_mes()` (versión batch de
   `estado_dia`) y eliminar la lógica de capas duplicada. — *hecho 2026-06-26*

> **Los 6 formularios quedaron migrados (L2 cerrado en todos)** y la vista de calendario
> (`MisTurnos`) consume la misma fuente de verdad. `TurnoService.estado_dia()` /
> `estado_mes()` / `dia_comprometido_por_solicitud()` son la base común.

### Registro de migración
- **2026-06-27 — Consistencia del display (ObtenerTurnoExploradorView) + duplicados:**
  - **Form Cambio de descanso (findes endpoint):** ahora usa `estado_mes` (6 capas) en vez de
    `get_turno_explorador` (2 capas). Antes ofrecía días que la persona ya había cedido por
    una doblada (el form decía "trabaja" y Mis Turnos "descansa"). Verificado.
  - **Display `ObtenerTurnoExploradorView`** (usado por Doblada, Cambio turno, CT permanente):
    ya cubría temporada/mantenimiento/festivo/finde y DOBLADA, pero su detección de descanso
    por solicitud era SOLO DOBLADA. Se añadió `dia_comprometido_por_solicitud()` para cubrir
    también **D FDS, CAMBIO DESCANSO y DOBLADA PERMANENTE**. Verificado (working days intactos).
  - **Duplicados pendientes:** se añadió `validar_solicitante_sin_solicitud_pendiente_en_fecha`
    (+ receptor en los de fecha única) a los 4 formularios que faltaban: `cambio_descanso`,
    `d_fds`, `ct_permanente`, `doblada_permanente`. Ya no se puede enviar dos veces la misma
    solicitud pendiente. (cambio_turno y doblada ya lo tenían.)

- **2026-06-26 — D FDS** (`d_fds_strategy.py`):
  - Se añadió verificación con `TurnoService.estado_dia()` para que el solicitante
    realmente TRABAJE el día de cesión y el receptor el día de pago (cierra **L2**:
    día ya comprometido por otra solicitud, + L4/L5).
  - **Bug latente corregido:** `_grupo_base` usaba `get_jornada_explorador_fecha` (que lee
    el Turno del día). Como en finde se trabaja AM+PM, y un cambio de descanso puede
    materializar un Turno ese día, el grupo se calculaba mal. Ahora usa la asignación base
    (`AsignarJornadaExplorador`). Mismo patrón ya aplicado en `cambio_descanso_strategy`.
  - ⚠️ Los demás formularios (`doblada`, `cambio_turno`, `ct_permanente`,
    `doblada_permanente`) tienen el MISMO `_grupo_base` basado en el Turno del día →
    revisar al migrar cada uno.

- **2026-06-26 — DOBLADA** (`doblada_strategy.py`):
  - Se añadió verificación **L2** con `TurnoService.dia_comprometido_por_solicitud()`:
    ni el solicitante (en cesión) ni el receptor (en pago) pueden usar un día que ya está
    comprometido por otra solicitud APROBADA (cambio descanso / d_fds / doblada / perm).
  - DOBLADA ya cubría bien los días especiales vía `SolicitudValidator._explorador_trabaja`
    (alternancia + temporada + mantenimiento) y **permite temporada/festivo a propósito**;
    por eso NO se usó `estado_dia` completo (bloquearía temporada), solo la capa L2.
  - Se añadió `TurnoService.dia_comprometido_por_solicitud()` como helper público de L2
    para formularios que permiten operar en temporada/festivo.
  - ⚠️ Pendiente (no crítico): varias llamadas a `get_jornada_explorador_fecha` dentro de
    los sub-casos (pago en sábado, etc.) leen el Turno del día; revisar si conviene basarlas
    en la asignación base como en `_grupo_base`.

- **2026-06-26 — DOBLADA PERMANENTE** (`doblada_permanente_strategy.py`):
  - `_grupo_base` ya usaba la asignación base (sin el bug de los otros forms). ✅
  - Se reemplazó la rama `n == 0` de `_estado_jornada` (que solo miraba temporada) por
    `TurnoService.estado_dia()`: ahora marca 'libre' si el día descansa por CUALQUIER motivo
    (temporada, **mantenimiento (L3)**, fin de semana, o **día ya comprometido por otra
    solicitud aprobada (L2)**).
  - Verificado con datos reales: bloqueó correctamente un miércoles donde el receptor ya
    descansaba por "pagar una doblada" aprobada (conflicto L2 que antes pasaba inadvertido).

- **2026-06-26 — CAMBIO TURNO** (`cambio_turno_strategy.py`):
  - Ya cubría días especiales vía `_explorador_trabaja` y bloquea sábado/domingo (es solo
    entre semana → sin el bug de `_grupo_base`). Se añadió verificación **L2** con
    `dia_comprometido_por_solicitud()` para solicitante y receptor en la fecha.
  - Verificado con datos reales: bloqueó un día donde el solicitante ya descansaba por
    "pagar una doblada" aprobada.

- **2026-06-26 — Auditoría de FESTIVO por formulario** (regla: festivo-por-festivo SOLO en DOBLADA):
  | Formulario | Comportamiento en festivo | Estado |
  |---|---|---|
  | **DOBLADA** | Permite festivo-por-festivo (rotación, mismo mes) | ✅ correcto (el único que lo permite) |
  | **CAMBIO TURNO** | Antes solo registraba el festivo; ahora **BLOQUEA** con mensaje claro | ✅ corregido |
  | **D FDS** | Solo fin de semana; un festivo entre semana se rechaza por "debe ser finde" | ✅ ok |
  | **DOBLADA PERMANENTE** | `_ocurrencias` excluye festivos (no opera en ellos) | ✅ ok |
  | **CT PERMANENTE** | Omite festivos en la aplicación (día inválido) | ✅ ok |
  | **CAMBIO DESCANSO** | Entre semana exige descanso de temporada (excluye festivo); finde usa sáb/dom | ✅ ok |
  - Único cambio de código: bloqueo de festivo en `cambio_turno_strategy.py`.

- **2026-06-26 — Bloqueos adicionales por petición:**
  - **CAMBIO TURNO**: ahora bloquea también **doblada** (AM+PM) con mensaje claro
    (vía `estado_dia().jornada == 'DOBLADA'`), además del descanso (ya existente) y festivo.
    El cambio de turno solo intercambia AM↔PM en un día donde ambos trabajan UNA jornada.
  - **DOBLADA PERMANENTE (frontend)**: el datepicker ahora bloquea **temporada y festivos**
    (`permitirTemporada:false, permitirFestivos:false`), igual que CT Permanente. El backend
    ya rechazaba esas ocurrencias dentro del rango (`_estado_jornada` → 'libre').

- **2026-06-26 — Regla de FESTIVO (L5) implementada** (`turno_service.py`, `turnos/api/views.py`):
  - Antes, los festivos entre semana se mostraban como jornada single (la rotación de
    festivos solo se usaba para validar, no para pintar el calendario). Bug pre-existente.
  - Ahora `estado_dia` / `estado_mes` aplican la regla: en festivo entre semana, el grupo que
    dobla por rotación → **DOBLADA (AM+PM)**; el grupo contrario → **descanso**. Manda sobre
    el horario predeterminado/importado (incluidos turnos single sueltos con `tipo_cambio=None`);
    un cambio EXPLÍCITO (turno con `tipo_cambio`) se respeta por encima.
  - `MisTurnosPorMesView` aplica el override de festivo ANTES de la rama de turno.
  - Verificado: solo cambian los días festivos (0 cambios en días normales). Ej. 17-ago
    (rotación PM): Mariana(PM)→DOBLADA, Jhon(AM)→descanso.

- **2026-06-26 — `estado_mes()` + refactor de MisTurnos** (`turno_service.py`, `turnos/api/views.py`):
  - Se añadió `TurnoService.estado_mes(empleado, anio, mes)`: versión BATCH de `estado_dia`
    (~8 consultas para todo el mes, sin N+1), mismo orden de capas.
  - `MisTurnosPorMesView` ahora consume `estado_mes()` para la decisión predeterminada por día
    (alternancia de finde / temporada / mantenimiento / base), eliminando esa lógica duplicada
    del bucle. El enriquecimiento (descanso_info, solicitud_info, permisos…) se conserva igual.
  - **Verificado byte-a-byte:** se capturó un golden master de la salida previa (6 meses de
    2 empleados) y la salida tras el refactor es IDÉNTICA (0 diferencias en 184 días).
  - Test de regresión `MisTurnosFuenteVerdadTest` que bloquea futuras divergencias entre la
    vista y `estado_mes`.

- **2026-06-26 — CT PERMANENTE** (`ct_permanente_strategy.py`):
  - Ya saltaba sábado/domingo/festivo/mantenimiento/descanso y cambios materializados
    (`_tipo_cambio_previo`). Se añadió **L2** dentro de `_es_dia_descanso`
    (`dia_comprometido_por_solicitud()`): ahora también OMITE los días que el explorador ya
    cedió/comprometió en otra solicitud aprobada (lado de descanso sin turno). Cubre
    validación y aplicación a la vez (mismo helper).

---

## Referencias en el código

- `turnos/services/turno_service.py` — `get_turno_explorador` (L1+L6), nueva `estado_dia`.
- `turnos/services/jornada_service.py` — `get_jornada_explorador_fecha` (L1+grupo base).
- `core/utils/jornada_utils.py` — `calcular_jornada_dia` (L6).
- `turnos/api/views.py` — `MisTurnosPorMesView` (las 6 capas, embebidas).
- `solicitudes/services/cambio_descanso_aplicacion_service.py` — `dias_en_descanso` (L2 para cambio descanso).
- `solicitudes/services/strategies/*_strategy.py` — los 6 formularios.
