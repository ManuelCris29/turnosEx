# Pruebas de JavaScript

Red de pruebas de JS del proyecto, estrenada el 2026-08-22 con 76 tests. **85 tests el
2026-08-26**, tras añadir `guardado-atomico.test.cjs`. Hasta que se estrenó, el CI solo
ejecutaba `pytest`, que no corre una sola línea de JavaScript: las **9 790 líneas**
de `static/js/cambio-turno/` no las miraba nadie.

> El número de tests de esta línea se queda viejo solo. La cifra que manda es la que
> imprime `node --test tests_js/*.test.cjs`.

## Cómo se ejecutan

```bash
node --test tests_js/*.test.cjs
```

Sin `npm install`, sin `package.json`, sin `node_modules`. Se usa el runner que trae
Node (estable desde Node 20). En el CI corre en su propio job, **bloqueante**.

Para un solo fichero:

```bash
node --test tests_js/date-utils.test.cjs
```

## Por qué no está bajo `static/`

Todo lo que cuelga de `static/` lo recoge `collectstatic` y acaba **servido
públicamente**. Un fichero de pruebas ahí sería contenido público. Comprobado:
`collectstatic --dry-run` no toca esta carpeta, y `pytest` tampoco (sus `testpaths`
son explícitos).

## Por qué sin dependencias

Para lo que hay que cubrir hoy no hace falta Jest ni Vitest, y evitarlos significa
cero dependencias nuevas y cero superficie de suministro. El día que haya que probar
el DOM de verdad —`dom-utils`, `api-client`, `datepicker-service`— sí hará falta
jsdom, y ese será el momento de traer una herramienta. Hoy sería adelantarse.

## Qué está cubierto y qué no

| Fichero | Estado | Motivo |
|---|---|---|
| `utils/date-utils.js` | **cubierto** | lógica pura, cero referencias al navegador |
| `utils/validators.js` | **cubierto** | lógica pura |
| `utils/api-client.js` | **cubierto** | solo usa `fetch`, `document.cookie` y `querySelector`: dobles fieles, sin jsdom |
| `utils/dom-utils.js` | **parcial** | `debounce` y `throttle` cubiertos (JS puro). El resto manipula el DOM |
| `loading-ui.js` | **parcial** | `fetchLimitado` y `avisoDeFallo` cubiertos: solo usan `fetch` y `AbortController`, nativos en Node. `mostrar`/`ocultar` no, son Swal puro |
| `utils/detalle-dia-mensajes.js` | **cubierto** | los textos de «Detalles del día» de Mis Turnos: lógica pura, se extrajo de `mis_turnos.js` justo para poder probarla |
| `utils/codigo-referencia.js` | sin cubrir | reemplaza `window.fetch` |
| `services/datepicker-service.js` | sin cubrir | 25 referencias al navegador y a flatpickr |
| `cambio-turno/*.js` | sin cubrir | los formularios; requieren DOM completo |

**Sobre los dobles y jsdom.** `api-client` se prueba sin jsdom porque no toca el DOM
de verdad: `document.cookie` es una cadena y `querySelector` solo sirve para leer un
`.value`. Un doble ahí es **fiel**. En cambio, fingir `classList` o `appendChild`
para probar `addClass` o `createElement` sería peor que no probarlos: el doble pasa
siempre y daría por bueno código que en el navegador falla. Esa mitad espera a jsdom.

## Cómo añadir un fichero de pruebas

1. Crear `tests_js/<modulo>.test.cjs`.
2. Cargar el módulo con el ayudante, que le pone el `window` que los `utils`
   necesitan para no explotar al importarse:

```js
const { cargarUtil } = require('./_setup.cjs');
const DateUtils = cargarUtil('utils/date-utils.js');
```

3. Si el módulo maneja fechas, probarlo en varias zonas horarias con
   `conZonaHoraria`. **No es un lujo**: el proyecto corre en dos husos —Colombia
   (UTC-5) en local y UTC en el CI—, y los dos fallos que esta red encontró el
   primer día eran exactamente de eso.

## Aviso importante: estos módulos casi no se usan

Medido el 2026-08-22. Las cuatro plantillas de solicitudes cargan `date-utils`,
`validators`, `api-client` y `dom-utils`, pero los usos reales son:

| Módulo | Usos en el proyecto |
|---|---|
| `date-utils.js` | **0** |
| `validators.js` | **0** |
| `api-client.js` | **0** (solo aparece en comentarios) |
| `dom-utils.js` | **1** — `DomUtils.ready()` en `core/app.js` |
| `codigo-referencia.js` | 8 — este sí se usa |
| `detalle-dia-mensajes.js` | 5 — `mis_turnos.js` lo llama en cada apertura del detalle del día (añadido el 2026-09-09) |

Dicho sin rodeos: **estos tests cubren código que hoy nadie llama.** Aun así valen —
encontraron dos bugs reales que habrían mordido al primero que los usara, y montan
la infraestructura— pero conviene no confundir cobertura con protección: hoy no
protegen ninguna pantalla.

Eso explica el punto 20 del informe de auditoría: la duplicación no está entre
formularios, sino **entre los formularios y estos utils**. Cada `solicitar_*.js`
reimplementó por su cuenta lo que ya existía al lado. Hacer que los formularios usen
los utils es el trabajo pendiente, y necesita jsdom antes.

## Lo que encontró el primer día

Los `utils` ya traían `module.exports` además del global, así que fueron probables
**sin tocar una línea de código de producción**. Y en cuanto se ejecutaron
aparecieron dos fallos de zona horaria:

- **`getMonthRange` retrocedía un día** en husos positivos: enero de 2026 salía como
  `2025-12-31 .. 2026-01-30` en Madrid o Tokio. Latente (la app corre en UTC-5),
  pero esperando a un despliegue en otro huso.
- **`futureDate` rechazaba HOY** y **`pastDate` daba HOY por pasado**, en Colombia.
  Su mensaje dice «hoy o una fecha futura». Ese sí habría afectado a usuarios, si
  alguien llegara a llamarlo — hoy `Validators` no lo usa nadie, ver el aviso en
  `validators.test.cjs`.

Ambos parseaban `new Date('2026-01-15')`, que es medianoche **UTC**. Los dos están
corregidos, y hay tests que fallan si vuelven.
