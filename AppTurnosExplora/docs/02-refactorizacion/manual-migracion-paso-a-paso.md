# Manual de migración CDN → local (paso a paso, copiar/pegar)

> Cómo ejecutar la migración de recursos CDN a archivos locales en las plantillas.
> **Contexto y decisión:** ver `docs/manual-cdn-a-estaticos-locales.md`.
> **Estado actual:** todas las librerías ya están descargadas localmente y con versión
> verificada (ver §1). Este manual solo cubre **editar las plantillas** y los pasos finales.
>
> ## ✅ EJECUTADO EL 2026-07-28
> Todas las ediciones de §2 están aplicadas, **salvo Font Awesome** (§2.1), que se
> mantuvo en CDN a propósito. Dos pasos salieron distintos a lo escrito aquí: §2.1 y
> §2.4 — se corrigieron abajo con el motivo. Este manual queda como registro.

---

## 1. Prerrequisitos — YA HECHO ✅

Archivos locales descargados y verificados por versión (2026-07-23):

| Librería | Versión local | Archivo(s) | Coincide con lo que usa el código |
|---|---|---|---|
| Flatpickr | **4.6.13** | `static/plugins/flatpickr/{flatpickr.min.css, themes/material_blue.css, flatpickr.min.js, l10n/es.js}` | ✅ (CDN era "latest" = 4.6.13) |
| Chart.js | **4.5.1** | `static/plugins/chart.js/chart.umd.min.js` | ✅ (CDN `@4` sirve 4.5.1) |
| FullCalendar | **6.1.11** | `static/plugins/fullcalendar/index.global.min.js` + `locales/es.global.min.js` | ✅ (CDN 6.1.11) |
| SweetAlert2 | **11.4.0** | `static/plugins/sweetalert2/sweetalert2.all.min.js` | ✅ (CDN `@11`) |
| Font Awesome | — | *(no aplica, ver §2.1)* | — |

> **Archivos viejos que quedaron intactos** (huérfanos, nadie los referencia): Chart.js
> **v2.9.4** (`Chart.min.js`) y FullCalendar **v5.10.1** (`main.min.js`) en esas mismas
> carpetas. **No los uses.** Apunta siempre a los nombres de la tabla de arriba.

Todas las plantillas afectadas ya tienen `{% load static static_version %}`, así que
`{% static_v %}` está disponible. No hay que añadir `{% load %}`.

---

## 2. Ediciones por plantilla (antes → después)

### 2.1 `templates/turnos/mis_turnos.html` — Font Awesome (ELIMINAR) y FullCalendar

**Font Awesome (línea ~9): ⛔ NO SE ELIMINÓ — el análisis de abajo era incorrecto.**
La copia local es Font Awesome **5.15.4** y el CDN sirve la **6.4.0**: son majors
distintos, así que la línea del CDN **no es redundante**, es una actualización
deliberada para esa página. Eliminarla degradaría los iconos a FA5 y algunos podrían
quedar en blanco. Para cerrarlo hay que **actualizar la copia local a 6.x** y entonces
sí quitar la línea. Texto original conservado abajo como referencia del razonamiento:

~~eliminar la línea completa.~~
`base.html` (línea 16) ya carga Font Awesome local en **todas** las páginas
(`/static/plugins/fontawesome-free/css/all.min.css`). Esta línea del CDN es **redundante**
(carga FA dos veces). Se elimina:

```html
<!-- ELIMINAR esta línea -->
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet" integrity="sha384-..." crossorigin="anonymous">
```
> Nota: el FA global es la **5.15.4** (de AdminLTE). Los iconos de esta página ya se
> renderizan con esa versión. Tras eliminar la línea, revisa que ningún icono quede en
> blanco; si alguno falla, es un icono exclusivo de FA6 y hay que usar su equivalente FA5.

**FullCalendar JS (línea ~92):**
```html
<!-- ANTES -->
<script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.js" integrity="sha384-5JIwZN3k..." crossorigin="anonymous"></script>
<!-- DESPUÉS -->
<script src="{% static_v 'plugins/fullcalendar/index.global.min.js' %}"></script>
```

### 2.2 `templates/turnos/turnos_calendario.html` — FullCalendar (JS + locale)

```html
<!-- ANTES -->
<script src="https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.js" integrity="sha384-5JIwZN3k..." crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/@fullcalendar/core@6.1.11/locales/es.global.min.js" integrity="sha384-cbWTKHcC..." crossorigin="anonymous"></script>
<!-- DESPUÉS -->
<script src="{% static_v 'plugins/fullcalendar/index.global.min.js' %}"></script>
<script src="{% static_v 'plugins/fullcalendar/locales/es.global.min.js' %}"></script>
```

### 2.3 Flatpickr — MISMO cambio en 4 plantillas

Aplica esto en:
`solicitar_cambio_turno.html`, `solicitar_ct_permanente.html`,
`solicitar_doblada.html`, `solicitar_doblada_permanente.html`.

```html
<!-- ANTES (CSS, en el bloque extra_css) -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/flatpickr.min.css">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/flatpickr/dist/themes/material_blue.css">
<!-- DESPUÉS -->
<link rel="stylesheet" href="{% static_v 'plugins/flatpickr/flatpickr.min.css' %}">
<link rel="stylesheet" href="{% static_v 'plugins/flatpickr/themes/material_blue.css' %}">
```
```html
<!-- ANTES (JS, en el bloque extra_js) -->
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
<script src="https://cdn.jsdelivr.net/npm/flatpickr/dist/l10n/es.js"></script>
<!-- DESPUÉS -->
<script src="{% static_v 'plugins/flatpickr/flatpickr.min.js' %}"></script>
<script src="{% static_v 'plugins/flatpickr/l10n/es.js' %}"></script>
```

### 2.4 `templates/solicitudes/mis_solicitudes_list.html` — SweetAlert2 (ELIMINAR)

⚠️ **Corregido respecto al plan original.** No hay que apuntar a un archivo local: hay
que **borrar la línea**. `base.html` (línea 292) ya carga la copia local de SweetAlert2
en **todas** las páginas, y `{% block extra_js %}` va después (línea 297) — así que esta
línea cargaba una **segunda** copia (v11.26.25) que pisaba a la local (v11.4.0). Era una
doble carga, no un tema de CDN.

```html
<!-- ELIMINAR esta línea; base.html ya provee Swal -->
<script src="https://cdn.jsdelivr.net/npm/sweetalert2@11"></script>
```

Comprobado antes de borrarla: los usos del proyecto son `Swal.fire` con `icon`,
`showCancelButton` y `toast`, todos disponibles desde v9 → la v11.4.0 los cubre.

### 2.5 `templates/empleados/indicadores.html` — Chart.js

```html
<!-- ANTES -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<!-- DESPUÉS (usar el UMD v4, NO el Chart.min.js v2 viejo) -->
<script src="{% static_v 'plugins/chart.js/chart.umd.min.js' %}"></script>
```

---

## 3. Pasos finales (después de editar todas las plantillas)

### 3.1 Recolectar estáticos (en el servidor)
```
python manage.py collectstatic --noinput
```

### 3.2 Limpiar la CSP (`config/settings.py`) — HECHO en modo report-only
`cdn.jsdelivr.net` ya no lo usa nadie, así que se eliminó de la política estricta, junto
con `code.ionicframework.com` (que no se usaba en ninguna plantilla).

`cdnjs.cloudflare.com` **también se quitó**: tras unificar Font Awesome en la copia local
5.15.4 (ver §2.1) ya no lo usa ninguna plantilla. Solo se conservan `fonts.googleapis.com`
y `fonts.gstatic.com`.

La política estricta se publicó como `CONTENT_SECURITY_POLICY_REPORT_ONLY`: **reporta sin
bloquear**. Una CSP demasiado estricta rompe en silencio (200 OK, logs limpios, la página
carga a medias y solo la consola lo delata), así que se observa primero y se promueve
después. Ver §5 de `docs/04-guias/manual-cdn-a-estaticos-locales.md`.

### 3.3 Probar cada página (consola F12, sin 404 ni bloqueos CSP)
- **mis_turnos.html** → el calendario carga; iconos FA visibles
- **turnos_calendario.html** → calendario en español
- **solicitar_*** (4) → el date picker (flatpickr) abre y está en español
- **mis_solicitudes_list.html** → las alertas (SweetAlert2) funcionan
- **indicadores.html** → los gráficos (Chart.js) se dibujan

### 3.4 Verificar con Semgrep
```
semgrep scan --config auto
```
No deben quedar hallazgos `missing-integrity` en `templates/` (los de `static/plugins/`
son de terceros; ver `docs/semgrep-triage.md`).

---

## 4. Rollback
Si algo falla, revierte la plantilla concreta a la línea de CDN anterior (git) mientras
investigas. Como los archivos locales ya existen, el cambio es solo de `src`/`href`, fácil
de revertir por archivo.

---

## 5. Resumen de una línea
Editar 8 plantillas cambiando `src/href` de CDN por `{% static_v 'plugins/...' %}`
(archivos ya descargados y verificados), eliminar la línea redundante de Font Awesome en
`mis_turnos.html`, correr `collectstatic`, limpiar la CSP y probar.
