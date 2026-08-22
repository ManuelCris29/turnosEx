# Pruebas de JavaScript

Primera red de pruebas de JS del proyecto (2026-08-22). Hasta esta fecha el CI solo
ejecutaba `pytest`, que no corre una sola línea de JavaScript: las **9 790 líneas**
de `static/js/cambio-turno/` no las miraba nadie.

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
| `utils/dom-utils.js` | sin cubrir | necesita `document` → jsdom |
| `utils/api-client.js` | sin cubrir | necesita `fetch` → jsdom o un doble |
| `utils/codigo-referencia.js` | sin cubrir | toca `window.fetch` |
| `services/datepicker-service.js` | sin cubrir | 25 referencias al navegador y a flatpickr |
| `cambio-turno/*.js` | sin cubrir | los formularios; requieren DOM completo |

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
