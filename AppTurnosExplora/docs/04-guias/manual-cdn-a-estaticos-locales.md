# Manual: de CDN a estáticos locales (SRI / `missing-integrity`)

> Guía para entender el hallazgo `missing-integrity` de Semgrep y migrar los recursos
> servidos por CDN a archivos locales servidos por Django, **antes de pasar a producción**.

> ## ✅ MIGRACIÓN COMPLETADA (2026-07-28)
>
> Las plantillas ya no cargan **ningún** script ni hoja de estilo desde `cdn.jsdelivr.net`.
> Flatpickr, Chart.js, SweetAlert2 y FullCalendar se sirven desde `static/plugins/`.
> Este documento se conserva como registro de la decisión y del método de verificación.
>
> **Lo único que sigue en CDN: Google Fonts** (`base.html` y login) — inofensivo
> (`display=fallback`).
>
> **Font Awesome — resuelto SIN actualizar (2026-07-28).** Se evaluó subir la copia local a
> 6.x y se DESCARTÓ: no aportaba nada que no diera la vía simple, y obligaba a revisar 84
> plantillas y 8 iconos de estilo `regular` (conjunto limitado en la versión gratuita).
> En su lugar se eliminó la línea de FA6 de `mis_turnos.html`. Auditoría que lo respalda:
> los **130 iconos distintos** del proyecto existen en la 5.15.4 local, incluidos los 10 de
> esa página y su JS. Antes convivían dos vocabularios de iconos y eso ya causaba un fallo
> real (ver abajo). Ahora hay **una sola versión en todo el sitio**.
>
> **CSP:** la política estricta (sin jsDelivr ni ionicons) está desplegada en modo
> **report-only** en `config/settings.py`. Ver §5, Paso 5.

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

| Librería | Versión que usa el código | Origen anterior | Estado final (2026-07-28) |
|---|---|---|---|
| FullCalendar | `6.1.11` | `cdn.jsdelivr.net` | ✅ **Migrado.** Local verificado **idéntico** al CDN (mismo sha256 en `index.global.min.js` y en `locales/es.global.min.js`) |
| SweetAlert2 | `@11` | `cdn.jsdelivr.net` | ✅ **Línea eliminada.** `base.html` ya servía la copia local (v11.4.0); el CDN cargaba una **segunda** copia encima |
| Chart.js | `@4` (=4.5.1) | `cdn.jsdelivr.net` | ✅ **Migrado** a `chart.umd.min.js`, byte por byte idéntico al CDN |
| Font Awesome | 5.15.4 (unificado) | `cdnjs.cloudflare.com` en 1 página | ✅ **Línea eliminada.** Se descartó actualizar a 6.x; los 130 iconos del proyecto existen en la 5.15.4 local |
| Flatpickr | `latest` (=4.6.13) | `cdn.jsdelivr.net` | ✅ **Migrado** en las 4 plantillas de formularios |

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
- **FullCalendar**: verificado idéntico. Método (reutilizable para cualquier librería):

  ```bash
  curl -sSL "https://cdn.jsdelivr.net/npm/fullcalendar@6.1.11/index.global.min.js" -o /tmp/cdn.js
  sha256sum /tmp/cdn.js static/plugins/fullcalendar/index.global.min.js   # deben coincidir
  # Prueba adicional: el sha384 del archivo LOCAL debe ser igual al integrity= del template
  openssl dgst -sha384 -binary static/plugins/fullcalendar/index.global.min.js | openssl base64 -A
  ```

  Los dos archivos (librería y locale `es`) resultaron idénticos, y su sha384 coincidió con
  el `integrity` que ya estaba escrito en las plantillas — prueba de que el navegador estaba
  cargando exactamente ese binario.
- **SweetAlert2**: local v11.4.0, mismo major que el `@11` del CDN. Los usos del proyecto son
  `Swal.fire` con `icon` / `showCancelButton` / `toast`, disponibles desde v9. Sin riesgo.
- **Font Awesome**: local 5.15.4 vs CDN 6.4.0 → **no migrable sin actualizar el local**.

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

### Paso 5 — Limpiar la CSP ✅ EN OBSERVACIÓN (report-only)
La CSP la impone el **navegador**: si bloquea un recurso, el servidor devuelve 200, los logs
quedan limpios y la página carga a medias. El fallo solo se ve en la consola (F12). Por eso
la política estricta **no se activó de golpe**: se publicó como
`CONTENT_SECURITY_POLICY_REPORT_ONLY` en `config/settings.py`, que **reporta sin bloquear**.

Se envían dos cabeceras a la vez:

| Cabecera | Contenido | Efecto |
|---|---|---|
| `Content-Security-Policy` | la permisiva de siempre | la que manda: nada se rompe |
| `Content-Security-Policy-Report-Only` | sin jsDelivr ni ionicons | solo avisa en consola |

**Para cerrar el paso:** usar la app unos días y revisar la consola. Si no aparece ninguna
violación, mover el diccionario de `CONTENT_SECURITY_POLICY_REPORT_ONLY` a
`CONTENT_SECURITY_POLICY` y borrar el permisivo.

Solo Google Fonts sigue siendo necesario. `cdn.jsdelivr.net`, `cdnjs.cloudflare.com` y
`code.ionicframework.com` se eliminaron de la política estricta: ninguna plantilla los usa.

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
- [x] Verificada la versión local de FullCalendar vs. `6.1.11` — **idéntica** (sha256 y sha384)
- [x] Todas las plantillas apuntan a `{% static_v %}` (salvo Font Awesome, ver nota de cabecera)
- [x] Eliminados los `integrity`/`crossorigin` de los tags que pasaron a locales
- [x] Verificado que **nada** en el proyecto referencia ya `cdn.jsdelivr.net`
      (templates, `static/`, `staticfiles/`, login; `django.contrib.gis` no está instalado)
- [x] CSP estricta desplegada en **report-only** en `config/settings.py`
- [ ] **Pendiente:** confirmar en consola que report-only no reporta violaciones, y entonces
      promoverla a política activa
- [ ] `collectstatic` ejecutado en el servidor
- [ ] Servidor web (o WhiteNoise) sirviendo `staticfiles/`
- [ ] Probadas todas las páginas sin 404 ni recursos bloqueados (F12)
- [ ] `semgrep scan` sin hallazgos `missing-integrity` en nuestras plantillas
- [x] Font Awesome unificado en 5.15.4 local; eliminada la última línea de `cdnjs`
- [x] Corregidos 2 iconos que se renderizaban en blanco (nombres FA6 en páginas con FA5)

---

## Referencias
- Triaje completo de Semgrep: `docs/semgrep-triage.md`
- Config de estáticos: `config/settings.py` (§ STATIC)
- Tag de versionado: `solicitudes/templatetags/static_version.py`
