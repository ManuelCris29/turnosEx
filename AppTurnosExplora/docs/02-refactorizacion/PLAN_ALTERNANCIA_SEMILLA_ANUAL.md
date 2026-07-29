# Alternancia de findes y festivos: arreglos de auditoría + rediseño a semilla anual

> **Estado:** commits 1 y 2 IMPLEMENTADOS. Pendiente el commit 3 (apertura de año).
> **Actualizado:** 2026-07-29.
> **Alcance:** `turnos` (asignación especial anual) + consumidores en `solicitudes`.
>
> **Corte de 2026 ejecutado el 29-jul-2026:** 121 días congelados (104 findes + 17 festivos).
> Verificado con un volcado de `estado_dia` de los 11 exploradores activos × 365 días:
> **0 cambios reales** en 4015 estados; las 732 diferencias fueron solo el campo `fuente`
> (`alternancia` → `manual`), es decir el mismo resultado leído ahora de la tabla.

## Contexto

La pantalla `/turnos/asignacion-especial/anual/` deja al supervisor fijar qué grupo (AM/PM) trabaja
el día completo en findes y festivos. Hoy funciona como **override sobre un cálculo automático**
hardcodeado: el ancla `FECHA_REFERENCIA_SABADO = date(2026, 1, 10)` / `"PM"` en
[alternancia_fines_semana_service.py:28-29](../../turnos/services/alternancia_fines_semana_service.py#L28-L29)
y un conteo global histórico de festivos en
[festivos_rotacion_service.py:63-76](../../turnos/services/festivos_rotacion_service.py#L63-L76).

Una auditoría encontró 9 hallazgos; los peores nacen de esa fórmula:

1. **Alto** — La rotación de festivos no está congelada. Insertar, desactivar o borrar un solo
   festivo pasado invierte AM/PM de *todos* los festivos posteriores, incluidos días con
   solicitudes aprobadas que la UI muestra como bloqueados (🔒) mientras el valor real ya cambió.
2. **Alto** — `fechas_bloqueadas_por_solicitud` solo mira `fecha_cambio_turno` y
   `doblada__fecha_pago`; ignora `fecha_pago_semana`, `CambioPermanenteDia`,
   `DobladaPermanenteDetalle`, `ReprogramacionDiaDoblada` y `DeudaExplorador`.
3. **Medio** — `guardar_anual` no valida que la fecha sea finde o festivo real.
4. **Medio** — El POST acepta cualquier año; se puede reescribir un año pasado.
5. **Medio** — La siembra está **duplicada en JavaScript** con una regla distinta a la del servidor.
6. **Bajo** — Los festivos que caen en finde no se marcan en el calendario.
7. **Bajo** — `grupo_trabaja_efectivo` devuelve `None` en festivos entre semana.
8. **Bajo** — Cobertura de tests casi nula del servicio.
9. **Medio (nuevo)** — La documentación y la nota informativa de la pantalla mienten: ver abajo.

### Estado real de 2026, verificado contra la BD (28-jul-2026)

| Dato | Valor |
|---|---|
| Festivos lun-vie en BD | 2025: **17**, 2026: 17, 2027: 15, 2028: 17 |
| Primer festivo lun-vie registrado | **2025-01-01** |
| Filas en `AsignacionEspecialManual` | **0** (ningún override, en ningún año) |
| `Turno` reales en 2026 | 372 |

Tres consecuencias que obligan a cambiar el plan original:

- **El docstring de `festivos_rotacion_service.py` es falso.** Afirma que 2026-01-01 es el primer
  festivo registrado y por tanto PM. Con 17 festivos de 2025 delante, su índice real es 17 →
  impar → **AM**. La nota informativa del template repite esa regla equivocada al supervisor.
- **La fórmula da resultados distintos en desarrollo y en producción.** Producción arranca limpia,
  sin los festivos de 2025, así que allí 2026-01-01 sí sería PM. Mismo código, mismo año, dos
  calendarios opuestos según el contenido de `DiaEspecial`. Es el hallazgo 1 demostrado en vivo y
  el argumento decisivo para el rediseño.
- **2026 no está materializado.** Con 0 overrides y solo 372 turnos reales, casi todo enero-julio
  2026 que hoy ve un explorador se calcula al vuelo. Apagar la fórmula sin más dejaría siete meses
  ya vividos en estado `sin_planificar`.

### Qué pasa con los días que hoy manda una solicitud aprobada

**Nada: se siguen respetando, y el corte no los toca.** La alternancia es la capa **más baja** del
orden de `estado_dia` / `estado_mes`:

| | Finde | Festivo lun-vie |
|---|---|---|
| 1º | `Turno` real (L1) | `Turno` con `tipo_cambio` (cambio explícito) |
| 2º | descanso por solicitud aprobada (L2) | — |
| 3º | **alternancia (L6)** ← lo que se congela | **rotación** ← lo que se congela |

Aplicar una solicitud **materializa filas `Turno` reales con `tipo_cambio`**
(`doblada_aplicacion_service.py:227,258,282,363`, `cambio_descanso_aplicacion_service.py:247,264`,
`doblada_pago_service.py:112,153`, `reprogramacion_doblada_service.py:331`). Esos días ganan antes
de llegar a la alternancia. La alternancia solo resuelve los días que nadie tocó, y congelarla
escribe el mismo valor que la fórmula ya devuelve.

**Congelar además los protege.** Hoy la alternancia es la base contra la que esas solicitudes se
validaron (quién dobla, quién es el contrapeso). Si alguien borra los 17 festivos de 2025, esa base
se invierte retroactivamente mientras las filas `Turno` quedan intactas: la solicitud dice una cosa
y la base la contraria. Congelada, no puede pasar.

**A verificar (posible hallazgo 10, preexistente e independiente de este trabajo):** en festivos
lun-vie, [turno_service.py:398-419](../../turnos/services/turno_service.py#L398-L419) y su gemelo
batch [:557-571](../../turnos/services/turno_service.py#L557-L571) **no consultan la capa L2** —
solo miran turnos con `tipo_cambio`. El diseño se sostiene porque la aplicación crea esas filas,
pero es un invariante no verificado: si alguna ruta concede descanso en un festivo sin materializar
`Turno`, ese explorador aparecería trabajando. Confirmar antes del commit 2; si se confirma, se
arregla en el commit 1.

### Decisiones tomadas

- La alternancia deja de ser una fórmula y pasa a ser un **dato sembrado por año**. Una fórmula
  recalcula el pasado; un dato no. La app **ya usa** ese patrón para festivos, mantenimiento y
  temporadas (`DiaEspecial.año_planificacion`); este módulo es el único que se salió de él.
- **2026 se congela, no se recalcula.** Un comando escribe en la tabla exactamente lo que la
  fórmula devuelve hoy, verificado día a día por un test de equivalencia antes de borrar nada.
  Ningún día cambia para el explorador. Se descartó la alternativa "fórmula para 2026, semilla
  desde 2027" porque exige un `if anio <= 2026` permanente en el código — una fecha quemada, justo
  lo que este trabajo elimina — y deja 2026 expuesto al hallazgo 1 y divergente entre entornos.
- **Continuidad entre años:** al sembrar X+1, el grupo sugerido del primer sábado y del primer
  festivo se **deriva de lo guardado en X**, no de una constante. El ancla del código desaparece
  como regla; si el año anterior no está sembrado, no hay sugerencia y el supervisor elige.
- **Los años pasados no se editan** (`anio_actual <= anio <= anio_actual + 5`).
- Sembrar el año es una responsabilidad anual explícita del supervisor, respaldada por una pantalla
  de **Apertura de Año** que bloquea al admin hasta completar todos los procesos.

Resultado esperado: una sola fuente de verdad (`AsignacionEspecialManual`), el pasado inmutable y
auditable vía `simple_history`, ninguna fecha de negocio quemada en el código, y ningún día que se
resuelva en silencio.

---

## Commit 1 — `fix(turnos): auditoría de findes y festivos`

Arreglos que sobreviven al rediseño. Todo en
[asignacion_especial_service.py](../../turnos/services/asignacion_especial_service.py)
salvo lo indicado.

**1.1 Completar `fechas_bloqueadas_por_solicitud` (hallazgo 2).**
Usar como referencia el gemelo
[descanso_semana_service.py::fechas_bloqueadas_por_solicitud](../../turnos/services/descanso_semana_service.py),
que ya cubre `doblada__fecha_pago_semana`. Añadir al `Q(...)` y al bucle de recolección:
`doblada__fecha_pago_semana`, `CambioPermanenteDia.fecha_especifica`,
`ReprogramacionDiaDoblada.fecha_reprogramada`, `DeudaExplorador.fecha_pago_pactada` y el rango
`fecha_inicio..fecha_fin` de `DobladaPermanenteDetalle` (solo sus findes/festivos). Mantener la
regla existente: si cae en finde, bloquear sábado **y** domingo vía `_fechas_finde`.

**1.2 Validar el tipo de día al guardar (hallazgo 3).**
En `guardar_anual`, descartar la fecha si `fecha.weekday() < 5` y `not DiaEspecial.es_festivo(fecha)`,
con `logger.warning` como hace `DescansoSemanaService`. Alinea `tipo` (`'finde'`/`'festivo'`) con la
realidad y respeta el `clean()` del modelo.

**1.3 Validar el rango de años en el POST (hallazgo 4).**
En `AsignacionEspecialAnualView.post`
([descanso_semana.py:267-291](../../turnos/views/descanso_semana.py#L267-L291)), replicar la
validación que ya existe en la vista gemela
([descanso_semana.py:174-177](../../turnos/views/descanso_semana.py#L174-L177)).

**1.4 Marcar festivos en finde (hallazgo 6).**
Pasar `festivos_finde_json` (festivos activos con `weekday() >= 5`) al template. El JS los pinta con
`mk-festivo` pero **no** cambia su comportamiento: sigue mandando la alternancia de finde.

**1.5 `grupo_trabaja_efectivo` completo (hallazgo 7).**
Si la fecha es festivo lun-vie, caer a `FestivosRotacionService`, no a `AlternanciaFinesSemanaService`.

**1.6 Corregir la regla documentada de festivos (hallazgo 9).**
Reescribir el docstring de [festivos_rotacion_service.py:1-14](../../turnos/services/festivos_rotacion_service.py#L1-L14):
la rotación **no** empieza en 2026, cuenta todos los festivos lun-vie de la tabla desde el primero
que exista (hoy 2025-01-01). En la nota informativa del template, sustituir el texto fijo
"empezando por PM en el primero" por el grupo **real** calculado para el primer festivo del año que
se está viendo. Este arreglo desaparece en el commit 2, pero mientras tanto la pantalla deja de
mentir.

**1.7 Unificar invalidación de caché.**
Reemplazar el doble bucle inline de
[descanso_semana.py:285-289](../../turnos/views/descanso_semana.py#L285-L289) por el helper
`_invalidar_cache_turnos(anio)` que ya existe en el mismo módulo (línea 20).

**1.8 Tests** — nuevo `turnos/tests/test_asignacion_especial_service.py`: `guardar_anual` feliz,
rechazo por `AsignacionEspecialConflicto`, descarte de fecha no especial, cada tipo de solicitud que
debe bloquear, y `grupo_trabaja_efectivo` en festivo lun-vie.

---

## Commit 2 — `refactor(turnos): alternancia por semilla anual`

**El orden de los pasos es obligatorio: 2.0 y 2.1 van antes de tocar ningún consumidor.**

**2.0 Congelar el año en curso (paso de corte).**
Comando nuevo `turnos/management/commands/materializar_alternancia.py`:
`--anio 2026 [--dry-run]`. Recorre todos los findes y festivos lun-vie del año, obtiene el grupo con
la **fórmula actual tal cual** — `AlternanciaFinesSemanaService` para findes y
`FestivosRotacionService` para festivos, con su **índice global**, *no* con reinicio anual — y crea
las filas en `AsignacionEspecialManual`. Idempotente: no pisa filas existentes.

**2.1 Test de equivalencia (la red de seguridad).**
`turnos/tests/test_equivalencia_alternancia_2026.py`: para cada finde y festivo lun-vie de 2026,
`AsignacionEspecialService.grupo_trabaja(f)` debe ser igual al valor de la fórmula antigua.
**Debe pasar en verde antes de eliminar cualquier fallback.** Después queda como test de regresión
de la semilla.

**2.2 La siembra se muda a Python.**
En `AsignacionEspecialService`:
- `calcular_siembra(anio, primer_sabado, primer_festivo) -> {fecha_iso: 'AM'|'PM'}` — cubre los
  ~104 findes y todos los festivos lun-vie del año. Findes por **paridad de fecha** (no por
  posición, que es el bug 5); festivos por orden cronológico dentro del año.
- `sugerencia_siembra(anio) -> {'primer_sabado': ..., 'primer_festivo': ...}` — **continuidad**:
  lee el último sábado y el último festivo sembrados en `anio-1` y devuelve el grupo contrario.
  Si `anio-1` no está sembrado, devuelve `None` y la pantalla obliga a elegir. Sustituye al ancla
  como origen del valor por defecto de los selectores.
- `sembrar_anio(anio, primer_sabado, primer_festivo) -> int` — `calcular_siembra` + `guardar_anual`.
  Es también el helper que usarán los tests.

Eliminar `sembrarFindes` / `sembrarFestivos` / `grupoSabado` de
[asignacion_especial_anual.js:106-139](../../static/js/turnos/asignacion_especial_anual.js#L106-L139).
Los botones llaman un endpoint `GET turnos/asignacion-especial/anual/siembra/?anio&finde&festivo`
que devuelve el mapa; el JS solo pinta. El supervisor revisa y pulsa Guardar.

**2.3 La BD es la única fuente de verdad.**
- `AsignacionEspecialService.grupo_trabaja(fecha)` (renombrado desde `get_grupo_trabaja`, sin
  fallback) y `mapa_grupo_trabaja(ini, fin)` son los únicos accesos.
- Eliminar el patrón `override or FestivosRotacionService...` de **todos** los consumidores:
  [turno_service.py:351-357, 410-416, 452-455, 536-541, 585-588](../../turnos/services/turno_service.py#L410-L416),
  [reporte_dia_service.py:91-92](../../turnos/services/reporte_dia_service.py#L91-L92),
  [api_turno_jornada.py:256-263](../../solicitudes/views/api_turno_jornada.py#L256-L263),
  [doblada_api.py:250-252](../../solicitudes/views/doblada_api.py#L250-L252),
  [doblada_strategy.py:317-319, 1036-1038](../../solicitudes/services/strategies/doblada_strategy.py#L317-L319).
- `AlternanciaFinesSemanaService` y `FestivosRotacionService` dejan de ser regla de negocio: se
  conservan **solo** como calculadoras de propuesta para `calcular_siembra`, con los docstrings
  reescritos. `FECHA_REFERENCIA_SABADO` / `JORNADA_REFERENCIA_SABADO` se eliminan; la continuidad
  la da `sugerencia_siembra`.

**2.4 Nada se inventa en silencio.**
En `estado_dia` y `estado_mes`, un finde o festivo lun-vie **sin fila** devuelve
`trabaja=False, jornada=None, fuente='sin_planificar'`, motivo
`'El año X aún no tiene la alternancia publicada'`. Las estrategias de solicitud rechazan ese día
con ese mensaje en vez de calcular. El front de Mis Turnos y las tarjetas de horario deben
representarlo de forma visible (gris + tooltip), no como un descanso normal.

**2.5 Migrar los tests que hoy dependen del ancla.**
`test_matriz_dobladas.py` (4 usos, ojo al `while` de la línea 919), `test_d_fds.py` (5),
`test_reflejo_mis_turnos.py` (3), `test_cambio_descanso.py`, `test_reporte_dia_service.py`.
Patrón: `AsignacionEspecialService.sembrar_anio(anio, 'PM', 'PM')` en `setUp` y consultar
`grupo_trabaja`. Revisar también `scripts/maintenance/test_alternancia_31_enero.py` y
`solicitudes/management/commands/test_verificar_doblada_jeison.py`.

**2.6 Docs** — actualizar
[AUDITORIA_FUENTE_VERDAD_TURNOS.md:29](../05-referencia/turnos/AUDITORIA_FUENTE_VERDAD_TURNOS.md#L29),
[REGLAS_NEGOCIO_SOLICITUDES.md:347](../05-referencia/solicitudes/REGLAS_NEGOCIO_SOLICITUDES.md#L347),
`manual_tecnico.md` y `manual_usuario.md`: la capa L6 ya no es "alternancia calculada" sino
"alternancia publicada por el supervisor". Documentar el procedimiento anual en el manual de usuario.

---

## Commit 3 — `feat(turnos): apertura de año con checklist obligatorio`

**3.1 `AperturaAnioConfig`** en `turnos/models.py`, patrón singleton de
[`CierreSolicitudesConfig`](../../solicitudes/models.py#L694) (`@classmethod obtener()` con
`get_or_create(pk=1)`, `HistoricalRecords`, sin caché). Campos: `inicio_recordatorio` (default
1-nov), `inicio_bloqueo` (default 1-dic), `bloqueo_duro` (default True).

**3.2 `AperturaAnioService.estado(anio)`** — checklist de 5 ítems, completitud derivada de los datos
existentes (sin modelo de estado nuevo, sin poder desincronizarse):

| Ítem | Completo si | Pantalla |
|---|---|---|
| Festivos | `DiaEspecial` `tipo='festivo'`, `año_planificacion=anio` | `DiaEspecialFestivosMantenimientoAnualView` |
| Mantenimiento | `DiaEspecial` `tipo='mantenimiento'` del año | misma |
| Temporadas | `DiaEspecial` `es_temporada=True` del año | `DiaEspecialTemporadasAnualView` |
| Descansos de semana | `DescansoSemanaManual` `motivo='temporada'` del año | `DescansoSemanaAnualView` |
| **Alternancia findes/festivos** | cobertura **completa**: toda fecha finde o festivo lun-vie del año tiene fila | `AsignacionEspecialAnualView` |

La alternancia es el único ítem que exige cobertura total, no "≥1 registro" — es lo que garantiza
que 2.4 nunca se dispare. Su prerrequisito es Festivos: el checklist va en orden y la alternancia
queda deshabilitada hasta que los festivos del año existan.

**3.3 Pantalla y bloqueo.** `AperturaAnioView` (`LoginRequired` + `AdminRequired`) en `turnos/views/`,
ruta `turnos/apertura-anio/<int:anio>/`, con el checklist y enlaces a cada pantalla. Middleware nuevo
en `core/middleware/` que redirige ahí a los admin cuando `hoy >= inicio_bloqueo` y el checklist del
año siguiente está incompleto. **Exenciones obligatorias** (si no, se autobloquea): logout,
static/media, admin de Django, la propia `apertura-anio` y las 5 pantallas del checklist. Entre
`inicio_recordatorio` e `inicio_bloqueo`, solo banner naranja en el dashboard.

**3.4 Comando `verificar_apertura_anio`** — reporta el checklist del año siguiente y sale con código
≠ 0 si falta algo (para cron/monitoreo).

**3.5 Tests** — `turnos/tests/test_apertura_anio.py`: cada ítem incompleto/completo, el middleware
redirige al admin y **no** al explorador, las rutas exentas no se bloquean, y antes de
`inicio_bloqueo` no hay redirección.

---

## Verificación

**Automática**
```
pytest AppTurnosExplora/turnos/tests -n 4
pytest AppTurnosExplora/solicitudes/tests -n 4        # los migrados en 2.5
pytest AppTurnosExplora -n 4                          # suite completa, ~3 min
python manage.py materializar_alternancia --anio 2026 --dry-run
python manage.py verificar_apertura_anio
python manage.py verificar_integridad_dobladas        # ya existe; no debe regresar
```

**El corte de 2026, paso a paso (commit 2)**
1. `materializar_alternancia --anio 2026 --dry-run` → revisar el listado: 104 findes + 17 festivos.
2. Anotar el estado de 3 fechas testigo en Mis Turnos **antes** (p. ej. sáb 07-feb, sáb 14-feb,
   festivo 06-ene) para un explorador AM y uno PM.
3. **Snapshot de los días mandados por solicitud**: volcar `estado_dia` de todo 2026 para los
   exploradores con solicitudes aprobadas en el año, a un JSON en el scratchpad.
4. Ejecutar sin `--dry-run` → deben quedar ~121 filas en `AsignacionEspecialManual`.
5. `pytest turnos/tests/test_equivalencia_alternancia_2026.py` en verde.
6. Repetir el volcado del paso 3 y **diff contra el anterior: debe salir vacío.** Es la prueba dura
   de que ningún día con solicitud aprobada cambió.
7. Recargar Mis Turnos: las 3 fechas testigo **idénticas**. Si alguna cambió, revertir y parar.
8. Solo entonces aplicar 2.3 (eliminar los fallbacks).

**Manual, en `runserver`**
1. `/turnos/asignacion-especial/anual/` en 2027 — el selector sugiere el grupo que **continúa** a
   2026; sembrar, Guardar, recargar: los 12 meses pintados coinciden.
2. Aprobar una solicitud sobre un sábado → ese sábado **y** su domingo salen 🔒; forzar el POST con
   ese día cambiado (DevTools) → mensaje de conflicto, nada se guarda.
3. Repetir con una **doblada permanente** y con una **reprogramación** — con commit 1 deben
   bloquear; hoy no lo hacen (prueba clave del hallazgo 2).
4. Forzar el POST con un año pasado → "Año fuera del rango planificable".
5. Año **no** sembrado (2029) → Mis Turnos muestra "sin planificar" y una solicitud sobre ese día se
   rechaza con el mensaje (prueba de 2.4).
6. Poner `inicio_bloqueo` a hoy → login como admin redirige al checklist; login como explorador
   entra normal; completar los 5 ítems libera la navegación.
