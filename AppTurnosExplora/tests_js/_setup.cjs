/**
 * Andamiaje minimo para probar los utils de `static/js/` desde Node.
 *
 * POR QUE ESTA CARPETA NO ESTA BAJO static/
 * Todo lo que cuelga de `static/` lo recoge `collectstatic` y acaba SERVIDO
 * publicamente. Un fichero de pruebas ahi seria contenido publico, asi que viven
 * aparte.
 *
 * POR QUE NO HAY package.json NI DEPENDENCIAS
 * Se usa el runner que trae Node (`node --test`, estable desde Node 20). No hace
 * falta Jest ni Vitest para lo que hay que cubrir ahora, y evitarlo significa cero
 * dependencias nuevas, cero `node_modules` y cero superficie de suministro. Si
 * algun dia hay que probar el DOM de verdad (`dom-utils`, `api-client`,
 * `datepicker-service`), entonces si hara falta jsdom y sera el momento de traer
 * una herramienta; hoy seria adelantarse.
 *
 * POR QUE HACE FALTA `global.window`
 * Los utils terminan con `window.X = X` para exponerse al navegador. En Node no
 * existe `window` y eso explota al importar. Se le da un objeto vacio antes de
 * cargarlos. El `module.exports` que ya tenian es lo que hace posible probarlos
 * sin tocar una sola linea de codigo de produccion.
 */
const path = require('path');

/** Carga un util de `static/js/` con el entorno de navegador minimo que necesita. */
function cargarUtil(rutaRelativa) {
  if (typeof global.window === 'undefined') {
    global.window = {};
  }
  return require(path.join(__dirname, '..', 'static', 'js', rutaRelativa));
}

/**
 * Ejecuta `fn` como si el reloj del sistema estuviera en otra zona horaria.
 *
 * Necesario porque varias funciones de fecha dan resultados distintos segun el
 * huso, y el proyecto corre en dos: Colombia (UTC-5) en local y UTC en el CI.
 * Un test que dependa del huso ambiente pasaria en un sitio y fallaria en el otro.
 *
 * Node relee `process.env.TZ` en cada operacion de fecha, asi que basta con
 * cambiarlo. Restaurarlo tiene una trampa, comprobada ejecutandola:
 *
 *   process.env.TZ = 'Asia/Tokyo';
 *   delete process.env.TZ;          // NO vuelve a la zona del sistema:
 *                                   // Tokyo sigue en efecto
 *
 * Por eso se captura la zona efectiva AL ARRANCAR —con `Intl`, que si la sabe— y
 * se restaura siempre a ese valor explicito. Sin esto, un test que cambiara de
 * zona contaminaba a todos los siguientes y la suite pasaba a depender del orden.
 */
const ZONA_DEL_SISTEMA =
  process.env.TZ || Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

function conZonaHoraria(tz, fn) {
  const anterior = process.env.TZ || ZONA_DEL_SISTEMA;
  process.env.TZ = tz;
  try {
    return fn();
  } finally {
    process.env.TZ = anterior;
  }
}

module.exports = { cargarUtil, conZonaHoraria };
