# Datos que se generan cada año (temporada, festivos, mantenimiento)

> **Para qué existe este documento**
> Además del upkeep técnico (ver [README](./README.md)), cada año hay que **cargar los
> días especiales del año entrante**. Se hace **una vez al año** (recomendado: diciembre)
> desde el **admin**, no por consola. Los años futuros están **vacíos a propósito**
> hasta que se generan: no se pre-cargan décadas de datos que no se van a usar.

---

## 1. Qué se genera cada año, y en qué ORDEN

El orden importa porque unos dependen de otros:

| # | Tipo | Cómo se obtiene | Depende de |
|---|------|-----------------|------------|
| 1 | **Temporada** | **Manual**: el admin selecciona los días de temporada del año. | — |
| 2 | **Festivos** | **Automático (preview)**: se calculan con la Ley Emiliani; el admin revisa y **guarda**. | Temporada (no pisa días de temporada) |
| 3 | **Mantenimiento** | **Automático (preview)**: primer día hábil de cada semana, saltando semanas de temporada y días festivos; el admin revisa y **guarda**. | Festivos y Temporada |

> **Clave:** festivos y mantenimiento se **calculan** para previsualizar, pero **NO se
> guardan hasta que el admin pulsa guardar** (igual que temporada). Antes los festivos se
> auto-creaban al abrir la vista; eso se corrigió.

---

## 2. Cómo hacerlo (en el admin, para el año entrante)

Las vistas ya abren por defecto en el **año siguiente** al actual.

### Paso 1 — Temporada
- Ir a **`/turnos/dias-especiales/temporadas-anual/`** (`dias_especiales_temporadas_anual`).
- Seleccionar el año entrante y marcar los días de temporada mes a mes.
- **Guardar.**

### Paso 2 — Festivos
- Ir a **`/turnos/dias-especiales/festivos-mantenimiento-anual/?tipo=festivo`**
  (`dias_especiales_festivos_mantenimiento_anual`).
- El calendario aparece **pre-rellenado** con los festivos calculados (Ley Emiliani).
- Revisar y **guardar** (esto es lo que los persiste para ese año).

### Paso 3 — Mantenimiento
- En la misma vista, cambiar a **`?tipo=mantenimiento`**.
- Aparece pre-rellenado con los días calculados (respeta festivos y temporada).
- Revisar y **guardar.**

### Verificación
- Abrir el listado **`/admin/turnos/diaespecial/`** y filtrar por el año entrante:
  deben aparecer temporada, festivos y mantenimiento de ese año.

---

## 3. Reglas / cosas a tener presente

- **Un año a la vez.** Genera solo el año que se va a operar (el entrante). No hay que
  sembrar 2035, 2040, etc.: se generan cuando toque.
- **Los años futuros vacíos NO son un bug** — es el diseño (los datos se cargan manual
  cada diciembre). Ver memoria del proyecto sobre el mantenimiento anual.
- **Festivos = deterministas** (`core/utils/festivos_colombia.py`, `CalculadoraFestivos`):
  el preview siempre se puede recalcular; por eso no hace falta guardarlos con años de
  anticipación.

---

## 4. Utilidad de limpieza (si vuelven a sobrar festivos futuros)

Si por cualquier motivo quedan festivos sembrados en años que no se usan:

```bash
cd AppTurnosExplora
PY manage.py limpiar_festivos_futuros --dry-run     # ver qué borraría
PY manage.py limpiar_festivos_futuros --hasta 2028  # conserva hasta 2028, borra posteriores
```
Borra **solo festivos** (no toca temporada ni mantenimiento).
