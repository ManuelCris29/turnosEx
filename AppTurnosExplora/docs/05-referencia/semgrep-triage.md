# Triaje de hallazgos Semgrep

`semgrep scan --config auto` · versión Semgrep 1.171.0

Resultado inicial: **141 hallazgos**. Tras las correcciones reales quedan **~139**
(el ruleset `auto` se descarga del registro y varía ligeramente entre corridas, sobre
todo en librerías de terceros).

Este documento explica el estado de cada categoría: qué se corrigió y por qué el resto
son **falsos positivos** o **código de terceros** que no se parchea.

---

## 1. Corregido (bugs reales)

### 1.1 URLs `http://127.0.0.1:8000` hardcodeadas en emails — `plaintext-http-link` (4)
Los botones "Ver Solicitudes / Ver en el Sistema" de los correos apuntaban al localhost
de desarrollo, lo que los dejaría rotos en producción.

- **Fix**: se pasa `settings.SITE_URL` al contexto de los 4 renders en
  `solicitudes/services/email_service.py` y las plantillas usan `{{ site_url }}/solicitudes/`.
- Plantillas: `cancelacion_solicitud.html`, `solicitud_receptor.html`,
  `solicitud_supervisor.html`, `solicitud_supervisor_receptor.html`.
- `SITE_URL` ya existía en `config/settings.py` (se configura por variable de entorno; en
  producción debe ser `https://…`).

### 1.2 SRI en CDN con versión exacta — `missing-integrity` (4)
Se añadió `integrity` + `crossorigin="anonymous"` a los recursos servidos por CDN que
están **fijados a una versión exacta** (hash verificable y estable):

| Recurso | Archivo |
|---|---|
| `fullcalendar@6.1.11/index.global.min.js` | `templates/turnos/mis_turnos.html`, `templates/turnos/turnos_calendario.html` |
| `@fullcalendar/core@6.1.11/locales/es.global.min.js` | `templates/turnos/turnos_calendario.html` |
| `font-awesome/6.4.0/css/all.min.css` | `templates/turnos/mis_turnos.html` |

---

## 2. Falsos positivos en nuestro código (sin cambios)

### 2.1 `sql-injection-db-cursor-execute` (8) — NO es SQL
`solicitudes/views/aprobacion_views.py` y `procesar_solicitud.py`. La regla matchea el
nombre de método `.execute(...)`, pero aquí son **casos de uso** de la capa de aplicación
(`AprobarComoSupervisorUseCase().execute(...)`, `CrearSolicitudUseCase().execute(...)`),
no cursores de base de datos. No hay SQL involucrado.

### 2.2 `django-no-csrf-token` (8) — el token SÍ está presente
La regla no detecta `{% csrf_token %}` en algunos layouts, pero los 8 formularios lo
incluyen inmediatamente después de `<form method="post">`:
`login.html`, `pdh_edit.html`, `roles_edit.html`, `salas_edit.html`,
`permisos_especiales_create.html`, `permisos_especiales_permanente_create.html`,
`cierre_config.html` (2 formularios). Verificado uno a uno.

### 2.3 `formatted-sql-query` / `sqlalchemy-execute-raw-query` (8 + 8) — no explotable
Scripts de mantenimiento/migración en `scripts/` ejecutados **manualmente por un admin**.
El único valor interpolado en el SQL es el nombre de tabla, que es una **constante
hardcodeada** en el propio script (p. ej. `tabla_historica = "solicitudes_dobladadetallehistory"`);
los datos sí van parametrizados con `%s`. No hay entrada de usuario.

### 2.4 `unsafe-formatstring` en nuestro JS (7) — template literals inofensivos
`static/js/utils/api-client.js`, `static/js/mis_turnos.js`,
`static/js/cambio-turno/datepicker_festivos.js`. Son plantillas de cadena de JS dentro de
`console.log`/`console.error`/`fetch` (p. ej. `` `Error ... ${año}` ``). No es un
format-string peligroso.

---

## 3. Hardening pendiente / aceptado (audit-level, sin cambios)

### 3.1 `missing-integrity` restantes (18) — CDN sin versión exacta
No se añade SRI porque el hash rompería la app cuando el CDN sirva otro contenido:

- **flatpickr** (`solicitar_cambio_turno`, `solicitar_ct_permanente`, `solicitar_doblada`,
  `solicitar_doblada_permanente`): URL **sin versión** (`npm/flatpickr` = latest).
- **chart.js@4** (`indicadores.html`) y **sweetalert2@11** (`mis_solicitudes_list.html`):
  versión por **rango mayor**, no exacta; el minor cambia sin aviso.

> **Corregido**: el `<link>` a `fullcalendar@6.1.11/index.global.min.css`
> (`mis_turnos.html`, `turnos_calendario.html`) devolvía **HTTP 404** — FullCalendar 6
> inyecta su CSS desde el JS. Ese `<link>` muerto se eliminó de ambas plantillas.

> El proyecto ya mitiga los CDN mediante una **allowlist CSP** en `config/settings.py`.
> Para cerrar estos hallazgos habría que fijar versiones exactas o autohospedar los recursos.

---

## 4. Código de terceros / vendored (80) — no se parchea
Hallazgos dentro de `static/plugins/` (codemirror, bootstrap, jquery-validation,
datatables, select2, jsgrid, flot, bootstrap-slider…). Es código de librerías incluido
tal cual; se actualiza reemplazando la librería, no editando su fuente.

- `detect-non-literal-regexp` (69)
- `incomplete-sanitization` (4)
- `prototype-pollution-loop` (4)
- `unsafe-formatstring` (3)

**Recomendación**: excluir `static/plugins/` del análisis (p. ej. `.semgrepignore`) para
reducir ruido, o mantener las librerías actualizadas desde su origen.
