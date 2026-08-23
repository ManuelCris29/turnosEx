# JavaScript del proyecto

Sin build: los ficheros se sirven tal cual con `{% static %}` y cada módulo se publica en
`window.*`. No hay bundler, ni `package.json`, ni `node_modules` en producción.

> **Auditado contra el código el 2026-08-23.** Incluye el estado de uso real de cada
> módulo, medido con grep sobre plantillas y JS.

## Estructura real

```
js/
├── core/
│   ├── app.js                       # App: showError/showSuccess/confirm sobre SweetAlert2
│   └── comentario_obligatorio.js    # ComentarioObligatorio: el asterisco rojo en los Swal
├── utils/
│   ├── api-client.js                # ApiClient  (GET/POST/PUT/DELETE + CSRF)
│   ├── date-utils.js                # DateUtils
│   ├── dom-utils.js                 # DomUtils
│   ├── validators.js                # Validators
│   └── codigo-referencia.js         # CodigoReferencia: lee X-Request-ID de los fetch
├── services/
│   └── datepicker-service.js        # DatepickerService (flatpickr)
├── loading-ui.js                    # LoadingUI: modal bloqueante anti doble envío
├── festivos_colombia.js
├── mis_turnos.js
├── adminlte.min.js                  # vendor
├── cambio-turno/                    # los 6 formularios de solicitud + apoyo
├── solicitudes/                     # listados (mis solicitudes, pendientes)
├── notificaciones-solicitudes/
├── empleados/
├── permisos/
└── turnos/                          # calendarios, temporadas, descansos, anuales
```

Los plugins de terceros (jQuery, Bootstrap, SweetAlert2, **flatpickr**) están
autohospedados en `static/plugins/`, no en CDN.

## Cache-busting: `static_v`

Para JS propio que cambia a menudo, usa `{% static_v %}` en vez de `{% static %}`: añade
`?v=<mtime>` y evita que el navegador sirva una versión vieja tras un despliegue.

```django
{% load static_version %}
<script src="{% static_v 'js/cambio-turno/solicitar_doblada.js' %}"></script>
```

Definido en `solicitudes/templatetags/static_version.py`.

## Qué se carga y dónde

| Módulo | Cargado en |
|---|---|
| `utils/codigo-referencia.js`, `loading-ui.js` | `templates/base.html` → **todas** las páginas |
| `services/datepicker-service.js`, `core/app.js` | `solicitar_cambio_turno.html`, `solicitar_ct_permanente.html`, `solicitar_doblada.html`, `turnos/mis_turnos.html` |
| `cambio-turno/*`, `turnos/*`, `empleados/*`… | su plantilla concreta |

## Aviso: la mitad de estos utils no la llama nadie

Medido el 2026-08-23 sobre todo el proyecto (plantillas y JS), excluyendo el propio
módulo y sus tests:

| Módulo | Usos reales |
|---|---|
| `LoadingUI` | **14** |
| `CodigoReferencia` | **8** |
| `ComentarioObligatorio` | **6** |
| `DateUtils` | **0** |
| `Validators` | **0** |
| `ApiClient` | **0** |
| `DomUtils` | **0** fuera de `DomUtils.ready()` dentro de `core/app.js` |
| `DatepickerService` | **0** — las plantillas lo cargan, pero los formularios llaman a `flatpickr` directo |
| `App` | **0** fuera de su propio fichero |

Es decir: **cada `solicitar_*.js` reimplementó por su cuenta lo que ya existía al lado.**
La duplicación del proyecto no está entre formularios, está entre los formularios y estos
utils. Hacer que los formularios los usen es el trabajo pendiente; la red de pruebas de
JS ya existe para respaldarlo (ver [`tests_js/`](../../tests_js/README.md)).

No borres los utils por estar sin uso: están probados y son el destino de esa
unificación. Pero **no asumas que documentarlos aquí significa que estén en producción**.

## Referencia de los módulos

### ApiClient — `utils/api-client.js`

```javascript
await ApiClient.get('/api/endpoint', { param: 'value' });
await ApiClient.post('/api/endpoint', { name: 'John' });
await ApiClient.put('/api/endpoint/1', { name: 'Jane' });
await ApiClient.delete('/api/endpoint/1');
ApiClient.getCsrfToken();          // usado internamente en POST/PUT/DELETE
```

Envía `credentials: 'same-origin'` y adjunta el token CSRF. Los errores se normalizan a
`{ success: false, error }` vía `ApiClient.handleError`.

### DateUtils — `utils/date-utils.js`

```javascript
DateUtils.isSunday(d); DateUtils.isSaturday(d); DateUtils.isWeekend(d);
DateUtils.getDayName(d, 'es-ES');
DateUtils.formatDate(new Date());          // "19/01/2025"
DateUtils.getToday();                      // "2025-01-19" (local, no UTC)
DateUtils.compareDates(a, b);              // -1 | 0 | 1
DateUtils.isPastDate(d); DateUtils.isFutureDate(d);
DateUtils.addDays(d, 7);
DateUtils.getMonthRange(2026, 1);          // { fechaInicio, fechaFin }
DateUtils.aFechaLocal(dateObj);            // "YYYY-MM-DD" en huso local
```

> **Trampa conocida:** `new Date('2026-01-15')` es medianoche **UTC**, no local. Dos bugs
> reales salieron de ahí (`getMonthRange` y `futureDate`). Por eso existe `aFechaLocal` y
> por eso los tests corren en varias zonas horarias.

### DomUtils — `utils/dom-utils.js`

```javascript
DomUtils.$('#id'); DomUtils.$$('.class'); DomUtils.ready(cb);
DomUtils.addClass/removeClass/toggleClass/hasClass(el, 'x');
DomUtils.show/hide/toggle(el);
DomUtils.createElement('option', { value: 1 }, 'texto');
DomUtils.clear(el);
DomUtils.on/off(el, 'change', handler);
DomUtils.debounce(fn, 300); DomUtils.throttle(fn, 300);
```

### Validators — `utils/validators.js`

```javascript
Validators.required(v, 'Campo');       // { valid, message }
Validators.email(v);
Validators.futureDate(v);              // HOY es válido
Validators.pastDate(v);                // HOY no es pasado
Validators.dateAfter(inicio, fin, 'Fecha fin');
Validators.minLength(v, 5, 'Campo'); Validators.maxLength(v, 200, 'Campo');
Validators.number(v); Validators.positiveNumber(v); Validators.range(v, 1, 10);
Validators.validate(v, [ (x) => Validators.required(x, 'Campo') ]);
```

### CodigoReferencia — `utils/codigo-referencia.js`

Envuelve `window.fetch` para guardar el `X-Request-ID` de la última respuesta. Los
formularios no recargan la página, así que ante un 500 el identificador que el equipo
busca en CloudWatch se perdía. Se carga en `base.html`.

```javascript
CodigoReferencia.ultimo();               // el último id visto
CodigoReferencia.mensaje('Falló el envío.');   // texto + código
CodigoReferencia.htmlMensaje('<b>…</b>');
```

### LoadingUI — `loading-ui.js`

Modal **bloqueante** de SweetAlert2: impide el doble clic mientras vuela una petición.

```javascript
LoadingUI.mostrar('Enviando solicitud...');
try { await fetch(url, {...}); } finally { LoadingUI.ocultar(); }
```

### ComentarioObligatorio — `core/comentario_obligatorio.js`

`Swal.fire` con el asterisco rojo del resto de la app (el `inputLabel` de SweetAlert2 se
inserta como texto plano y no admite HTML).

```javascript
const { value } = await ComentarioObligatorio.swal({ title: 'Motivo' });
```

### DatepickerService — `services/datepicker-service.js`

```javascript
const fp = await DatepickerService.initialize({
  input: document.getElementById('fecha'),
  config: { minDate: 'today', dateFormat: 'Y-m-d' },
  onDateChange: (dateStr, dateObj) => {},
  indicadorFestivo: document.getElementById('indicador'),
  indicadorMantenimiento: document.getElementById('mantenimiento')
});
DatepickerService.loadAndMarkSpecialDays(fp, opciones);
DatepickerService.disableDates(fp, ['2026-01-20']);
DatepickerService.enableOnlyDates(fp, ['2026-01-20']);
DatepickerService.destroy(fp);
```

Requiere `plugins/flatpickr/flatpickr.min.js` y su locale `es` cargados antes.

### App — `core/app.js`

```javascript
App.showError('Ocurrió un error', 'Error');
App.showSuccess('Operación exitosa', 'Éxito');
if (await App.confirm('¿Está seguro?')) { /* … */ }
```

Sin SweetAlert2 cargado hace *fallback* a `alert()`. La instancia se crea en `window.app`.

## Convenciones

1. `const` por defecto; `let` solo si se reasigna.
2. `async/await` en vez de cadenas de `.then()`.
3. `?.` y `??` para acceso y valores por defecto.
4. Template literals en vez de concatenación.
5. Toda promesa de red va en `try/catch` con `LoadingUI.ocultar()` en `finally`.
6. Los mensajes al usuario salen por `App`/`Swal`, nunca por `alert()` directo.
7. Un recurso externo nuevo hay que añadirlo a la **allowlist de CSP** en `config/settings.py`
   — o el navegador lo bloqueará en silencio.

## Pruebas

`node --test tests_js/*.test.cjs` — sin dependencias. Cubre `date-utils`, `validators`,
`api-client` y la parte pura de `dom-utils`. Detalles y qué falta:
[`tests_js/README.md`](../../tests_js/README.md).
