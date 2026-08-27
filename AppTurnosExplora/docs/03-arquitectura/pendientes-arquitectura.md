# Pendientes de Arquitectura

> **Revisado y re-medido el 26 ago 2026.** La versión anterior de este documento
> daba por pendiente trabajo que ya estaba hecho, y por disponible un repositorio
> que se había borrado. Todas las cifras de aquí abajo están medidas ese día,
> no estimadas.
>
> Documento vivo: si vuelves a leerlo dentro de un mes, **re-mide antes de actuar**.
> El fallo que hizo falsa la versión anterior fue confiar en cifras de julio.

> Hacer cuando el proyecto esté **funcionalmente completo** y antes de subir a AWS.
> Refactorizar mientras hay flujos en desarrollo activo introduce riesgo de regresiones
> sin beneficio inmediato.

---

## Lo que ya NO está pendiente (cerrado entre ago-2025 y ago-2026)

Se conserva la lista porque el documento anterior seguía pidiendo estas cuatro
cosas, y alguien podría "arreglarlas" otra vez.

| Lo que se pedía | Estado real (26 ago 2026) |
|---|---|
| Partir `solicitud_validator.py` — «1.482 líneas, 35 métodos» | ✅ **HECHO.** Hoy son **20 líneas**. La lógica vive en `services/validators/` (`base_validator`, `ct_validator`, `ct_permanente_validator`, `doblada_validator`) |
| Partir `notificacion_service.py` — «1.125 líneas» | ✅ **HECHO.** Hoy son **739 líneas**, y `email_service.py` (552) ya está extraído |
| «`EmpleadoRepository` **ya creado** — actualizar las vistas para usarlo» | ❌ **FALSO, y era la afirmación más peligrosa del documento.** Se creó en el commit `48410ab`, **nunca se adoptó**, y se BORRÓ el 22 ago 2026 en `b69cb80` («eliminar tres módulos Python que nadie importa»). Hoy `EmpleadoRepository` **no existe en ningún archivo del repo** |
| Vaciar `api_turno_jornada.py` — «855 líneas, 34 queries» | 🟡 **A MEDIAS.** Hoy son **715 líneas y 14 queries**; su `get()` bajó de 310 a 167 líneas |

> **La lección del `EmpleadoRepository` manda sobre todo lo que sigue.**
> Construir un repositorio que nadie adopta no produce arquitectura: produce
> código muerto que alguien acaba borrando. **Adoptar > crear.** No crear un
> repositorio nuevo hasta haber migrado los llamadores del anterior.

---

## 1. Adoptar los repositorios que YA existen

El problema real no es que falten repositorios. Es que los que hay casi no se usan.

| Medida (26 ago 2026) | Valor |
|---|---|
| Métodos disponibles | **17** (`SolicitudRepository` 11 · `TurnoRepository` 6) |
| Archivos de PRODUCCIÓN que los consumen | **2** — `views/aprobacion_views.py`, `use_cases/aprobar_solicitud.py` |
| Llamadas a través del repositorio | **19** |
| Accesos ORM crudos en el resto del proyecto | **467** |

Reparto de esos 467 accesos, para elegir por dónde entrar:

| Capa | `.objects.` |
|---|---|
| `solicitudes/services` | 262 |
| `turnos/services` | 71 |
| `solicitudes/views` | 56 |
| `empleados/views` | 32 |
| `permisos` | 18 |
| `turnos/api` | 10 |
| `empleados/services` | 10 |
| `turnos/views` | 8 |

**Orden recomendado**, por riesgo creciente:

1. `empleados/views` (32) — el más mecánico. **Requiere crear `EmpleadoRepository` otra vez**; hacerlo solo si se migran los llamadores **en el mismo commit**, o repetiremos la historia.
2. `turnos/views` (8) y `turnos/api` (10) — pocos y acotados.
3. `solicitudes/views` (56) — ver §2, muchos están dentro de funciones gigantes.
4. Los servicios (333) — al final. Ahí el ORM está entretejido con la lógica y sacarlo sin partir antes las funciones da abstracciones que mienten.

> Precedente a respetar: `services/bloqueo_partes.py` demuestra que **no todo
> acceso a datos debe ir tras un repositorio**. Su `select_for_update` es SQL
> específico de MySQL, no un concepto de dominio, y envolverlo habría escondido
> que el orden importa. Antes de mover una query, preguntar qué esconde la
> abstracción.

---

## 2. Funciones que no se pueden leer

Medido con AST el 26 ago 2026 (excluye tests, migraciones y `venv`):

| Métrica | Valor |
|---|---|
| Funciones > 100 líneas | **62** |
| Funciones > 50 líneas | **178** |
| Funciones con > 5 parámetros | 33 |
| Funciones marcadas `C901` (complejidad > 10) | 78 |

Reparto de las 62: **36 en servicios**, 14 en vistas/API, 7 otros, 5 en comandos.

Las peores, con su complejidad ciclomática real:

| Función | Líneas | C901 |
|---|---|---|
| `turnos/api/views/turnos_mes.py::MisTurnosPorMesView.get` | **344** | **36** |
| `turnos/api/views/turnos_mes.py::_enriquecer_solicitud_info` | 239 | **38** |
| `turnos/services/reporte_dia_service.py::reporte` | 338 | — |
| `solicitudes/services/strategies/cambio_turno_strategy.py::aplicar_cambios` | 294 | — |
| `turnos/services/turno_context_service.py::get_context_data_for_mis_turnos_view` | 289 | — |
| `solicitudes/views/doblada_api.py::get` | 278 | — |

**Regla aprendida en `api_turno_jornada.py`, y que aquí es innegociable:
medir la cobertura del archivo ANTES de cortar.** Ese `get()` se troceó cuando
su cobertura funcional era CERO (el 5 % que reportaba el CI eran los `import` y
las líneas de `class`/`def`). Cortar sin red es exactamente lo que la Fase 0
quería evitar.

Candidato siguiente: `doblada_api.py` (542 líneas, `get()` de 278). Medir su
cobertura primero.

---

## 3. Endurecer ruff por familias

`ruff check .` sale **en cero** hoy, y el lint es bloqueante en CI y pre-commit.
Lo pendiente es ampliar el `select`. Coste medido de cada familia y advertencia
sobre `I`: ver el comentario de [`pyproject.toml`](../../pyproject.toml).

---

## 4. Abierto y sin dueño

- **`TipoSolicitudCambio.nombre` y `codigo_estrategia` son editables desde el admin**
  (`solicitudes/admin.py`, `dashboard_admin.py`). Un administrador puede romper el
  despacho de estrategias sin tocar una línea de código. Hallazgo §10.5 de
  [plan-refactor-tipo-cambio.md](../05-referencia/plan-refactor-tipo-cambio.md).
- **Los estados siguen sin centralizar**: 314 literales crudos (`'aprobada'` 124,
  `'pendiente'` 103, `'cancelada'` 64, `'rechazada'` 15, `'reemplazada'` 8) repartidos
  en 6 modelos donde `'pendiente'` significa cuatro cosas distintas. `EstadoSolicitud`
  existe en `core/constants.py` pero solo cubre `SolicitudCambio`. **Es un proyecto
  propio, no una sustitución mecánica**: cada ocurrencia exige mirar a qué modelo
  pertenece.
- **`coverage.xml` es un artefacto local que Sonar lee como verdad.** Está en
  `.gitignore`, se genera en local (donde Python 3.14 da fallos fantasma de cobertura)
  y marca 65,19 %, por debajo del gate del CI (`--cov-fail-under=68`).
  `sonar-project.properties` apunta a ese archivo: quien lance Sonar en local publica
  una cobertura que el proyecto no tiene. Usar el artefacto `coverage-xml` del CI.

---

## Sobre los "puntajes objetivo"

La versión anterior prometía «60 % → ~90 %» y «85 % → ~97 %» al completar la lista.
Se retiran esas cifras: eran estimaciones sin método detrás, y perseguir un
porcentaje es justo lo que produce repositorios vacíos e interfaces de un solo
implementador — que es como se llegó a tener un `EmpleadoRepository` que nadie usaba.

La línea base medida y su método están en
[AUDITORIA_CALIDAD_2026-08.md](./AUDITORIA_CALIDAD_2026-08.md).
