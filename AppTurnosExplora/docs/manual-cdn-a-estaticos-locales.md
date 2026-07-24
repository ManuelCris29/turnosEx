# Manual: de CDN a estáticos locales (SRI / `missing-integrity`)

> Guía para entender el hallazgo `missing-integrity` de Semgrep y migrar los recursos
> servidos por CDN a archivos locales servidos por Django, **antes de pasar a producción**.

---

## 1. ¿Por qué Semgrep muestra `missing-integrity`?

Cuando cargas un archivo externo (CSS/JS) desde un CDN:

```html
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>
```

el navegador descarga y ejecuta **lo que el CDN le entregue en ese momento**, confiando
a ciegas. Si ese servidor externo fuera comprometido o modificado, tu app ejecutaría
código ajeno (ataque de cadena de suministro / XSS).

**SRI (Subresource Integrity)** es la defensa: añades el hash criptográfico del archivo
que esperas, y el navegador **rechaza** el recurso si no coincide.

```html
<script src="https://cdn.../flatpickr.min.js"
        integrity="sha384-xxxxx"
        crossorigin="anonymous"></script>
```

Semgrep marca `missing-integrity` en cada `<script>`/`<link>` externo **sin** ese atributo.

---

## 2. El problema del "latest" / versión no fija

SRI exige que el archivo sea **byte por byte idéntico** al del hash. Por eso solo funciona
con **versiones exactas**. Si la URL no fija versión:

```html
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>   <!-- = latest -->
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>  <!-- = último 4.x -->
```

el día que el CDN publique una versión nueva, el hash **dejará de coincidir** y el
navegador **bloqueará el recurso** → la app deja de cargar ese script y se rompe.

Conclusión: **CDN sin versión fija + SRI = frágil**. Por eso en este proyecto no se
añadió SRI a flatpickr, chart.js@4 ni sweetalert2@11 (ver `docs/semgrep-triage.md`).

---

## 3. Las dos salidas

| Opción | Qué implica | Cuándo |
|---|---|---|
| **A. CDN + SRI** | Fijar versión exacta + `integrity` + `crossorigin` en cada tag | Si quieres seguir con CDN |
| **B. Autohospedar** ✅ | Guardar los archivos en `static/` y servirlos con Django | **Recomendada para esta app** |

### Por qué la Opción B es la correcta aquí
- **Sin dependencia de Internet** — funciona en intranet / red corporativa sin salida.
- **Más rápido** — sin DNS/TLS extra hacia dominios de terceros.
- **Más seguro** — no ejecutas código externo; ya no necesitas SRI.
- **Simplifica la CSP** — puedes quitar `cdn.jsdelivr.net`, `cdnjs.cloudflare.com`, etc.
  de la allowlist en `config/settings.py` (ver nota de CSP del proyecto).
- **Sin fuga de datos** — los usuarios no exponen su IP a servidores de terceros.
- **Reproducible** — la versión queda congelada en el repo, no cambia sin que lo decidas.

---

## 4. Estado actual del proyecto (inventario)

Configuración de estáticos (`config/settings.py`):
```python
STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')   # destino de collectstatic
```
Tag de plantilla para cache-busting: `{% static_v 'ruta' %}`
(en `solicitudes/templatetags/static_version.py`).

**Buena noticia: 4 de las 5 librerías CDN ya están descargadas en `static/plugins/`.**
La migración es, en su mayoría, apuntar las plantillas a lo que ya existe.

| Librería | Versión que usa el código | CDN actual | ¿Local? | Acción |
|---|---|---|---|---|
| FullCalendar | `6.1.11` | `cdn.jsdelivr.net` | ✅ `static/plugins/fullcalendar` | Verificar versión local y apuntar `{% static %}` |
| SweetAlert2 | `@11` | `cdn.jsdelivr.net` | ✅ `static/plugins/sweetalert2/sweetalert2.all.min.js` | Apuntar `{% static %}` |
| Chart.js | `@4` (=4.5.1) | `cdn.jsdelivr.net` | ✅ **v4.5.1** en `static/plugins/chart.js/chart.umd.min.js` | Apuntar `{% static %}` |
| Font Awesome | `6.4.0` | `cdnjs.cloudflare.com` | ✅ `static/plugins/fontawesome-free` (5.15.4, ya lo carga `base.html`) | **Eliminar** la línea CDN (redundante) |
| Flatpickr | `latest` (=4.6.13) | `cdn.jsdelivr.net` | ✅ **4.6.13** en `static/plugins/flatpickr/` | Apuntar `{% static %}` |

> **Prerrequisitos ya resueltos (2026-07-23):** se descargaron **flatpickr 4.6.13** (css, tema
> material_blue, js, locale es) y **Chart.js 4.5.1** (`chart.umd.min.js`, versión exacta que
> sirve hoy `chart.js@4`, para no romper `indicadores.js`). El Chart.js **v2.9.4** que ya
> existía en esa carpeta quedó intacto (está huérfano, nadie lo referencia). Ya solo falta
> el paso de **cambiar las URLs en las plantillas** (Paso 3) cuando se decida el lanzamiento.

### Archivos de plantilla afectados
- `templates/turnos/mis_turnos.html` — FullCalendar, Font Awesome
- `templates/turnos/turnos_calendario.html` — FullCalendar (core + locale es)
- `templates/solicitudes/solicitar_cambio_turno.html` — Flatpickr (css, tema, js, locale)
- `templates/solicitudes/solicitar_ct_permanente.html` — Flatpickr
- `templates/solicitudes/solicitar_doblada.html` — Flatpickr
- `templates/solicitudes/solicitar_doblada_permanente.html` — Flatpickr
- `templates/solicitudes/mis_solicitudes_list.html` — SweetAlert2
- `templates/empleados/indicadores.html` — Chart.js
- `templates/base.html` — Google Fonts (opcional, ver §6)

---

## 5. Plan de migración paso a paso

### Paso 1 — Descargar lo que falta ✅ HECHO (2026-07-23)
Ya descargado en versiones exactas:
```
static/plugins/flatpickr/            (4.6.13)
    flatpickr.min.css
    themes/material_blue.css
    flatpickr.min.js
    l10n/es.js
static/plugins/chart.js/
    chart.umd.min.js                 (4.5.1  ← usar este, NO el Chart.min.js v2.9.4)
```

### Paso 2 — Verificar versiones ✅ HECHO
- **Chart.js**: la carpeta local tenía **v2.9.4** (incompatible con la API v4 de
  `indicadores.js`). Resuelto descargando **v4.5.1** (`chart.umd.min.js`), la misma versión
  que hoy sirve `chart.js@4`. Al migrar, apunta a `chart.umd.min.js`, no al `Chart.min.js` v2.
- **FullCalendar**: verificar que la carpeta local sea compatible con `6.1.11` antes de migrar.
- **SweetAlert2 / Font Awesome**: usar los archivos que ya existen.

### Paso 3 — Reemplazar las URLs de CDN por `{% static %}`
Al inicio de cada plantilla afectada asegúrate de tener `{% load static %}` y cambia:

```html
<!-- ANTES (CDN) -->
<script src="https://cdn.jsdelivr.net/npm/flatpickr"></script>

<!-- DESPUÉS (local, con cache-busting del proyecto) -->
<script src="{% static_v 'plugins/flatpickr/flatpickr.min.js' %}"></script>
```

Haz lo mismo con cada CSS/JS de la tabla del §4. Al ser local, **ya no necesitas
`integrity` ni `crossorigin`** (esos atributos son solo para recursos externos).

### Paso 4 — Recolectar estáticos
En el servidor de producción:
```
python manage.py collectstatic --noinput
```
Esto copia todo `static/` a `STATIC_ROOT` (`staticfiles/`) para que lo sirva el servidor
web (Nginx/Apache) o WhiteNoise. *(Nota: WhiteNoise no está instalado hoy; si no usas un
servidor web que sirva `staticfiles/`, considera agregarlo.)*

### Paso 5 — Limpiar la CSP
Una vez que **ninguna** plantilla cargue desde CDN, quita esos hosts de la allowlist CSP
en `config/settings.py` (`cdn.jsdelivr.net`, `cdnjs.cloudflare.com`, y `fonts.googleapis.com`
/ `fonts.gstatic.com` si también autohospedas las fuentes). Menos superficie, CSP más estricta.

### Paso 6 — Probar
Abre cada página afectada y verifica en la consola del navegador (F12) que **no haya
errores 404** de estáticos ni recursos bloqueados, y que funcionen: calendario, date
pickers, alertas y gráficos.

---

## 6. Nota sobre Google Fonts (`base.html`)
`base.html` carga `fonts.googleapis.com`. Es opcional migrarlo, pero por las mismas razones
(privacidad/offline) puedes descargar la fuente **Source Sans Pro** a `static/fonts/` y
declararla con `@font-face` en tu CSS. Si lo haces, recuerda quitar el host de la CSP.

---

## 7. Checklist pre-producción

- [x] Flatpickr descargado (4.6.13) en `static/plugins/flatpickr/`
- [x] Chart.js v4.5.1 descargado (`chart.umd.min.js`) — resuelto el conflicto con la v2.9.4
- [ ] Verificada la versión local de FullCalendar vs. `6.1.11`
- [ ] Todas las plantillas del §4 apuntan a `{% static %}` / `{% static_v %}`
- [ ] Eliminados los `integrity`/`crossorigin` de los tags que pasaron a locales
- [ ] `collectstatic` ejecutado en el servidor
- [ ] Servidor web (o WhiteNoise) sirviendo `staticfiles/`
- [ ] Hosts de CDN quitados de la allowlist CSP en `config/settings.py`
- [ ] Probadas todas las páginas sin 404 ni recursos bloqueados (F12)
- [ ] `semgrep scan` sin hallazgos `missing-integrity` en nuestras plantillas

---

## Referencias
- Triaje completo de Semgrep: `docs/semgrep-triage.md`
- Config de estáticos: `config/settings.py` (§ STATIC)
- Tag de versionado: `solicitudes/templatetags/static_version.py`
