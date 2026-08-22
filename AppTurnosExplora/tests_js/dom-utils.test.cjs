/**
 * `static/js/utils/dom-utils.js` — solo la parte que NO toca el DOM.
 *
 * QUE SE CUBRE Y POR QUE SOLO ESO
 * El modulo tiene dos mitades muy distintas:
 *
 *   1. Manipulacion del DOM: `$`, `$$`, `ready`, `addClass`, `show`, `hide`,
 *      `createElement`, `clear`, `on`, `off`... Esas necesitan un DOM de verdad.
 *      Fingirlas con dobles seria peor que no probarlas: un doble de
 *      `classList` o de `appendChild` pasa siempre, y daria por bueno codigo que
 *      en el navegador falla. Quedan para cuando se traiga jsdom.
 *
 *   2. `debounce` y `throttle`: JavaScript puro, solo `setTimeout`. Ninguna
 *      referencia al DOM. Se prueban aqui, y merece la pena: son control de
 *      tiempo, que es facil de escribir mal de forma sutil y dificil de depurar
 *      cuando falla en produccion.
 *
 * Se usan los relojes simulados que trae Node (`t.mock.timers`, desde la v20), asi
 * que los tests son instantaneos y deterministas: nada de `setTimeout` real ni de
 * esperas que a veces fallan segun la carga de la maquina.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

const { cargarUtil } = require('./_setup.cjs');

const DomUtils = cargarUtil('utils/dom-utils.js');


test('debounce', async (t) => {
  await t.test('no ejecuta hasta que pasa la espera', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let veces = 0;
    const f = DomUtils.debounce(() => veces++, 300);

    f();
    assert.equal(veces, 0, 'no debe ejecutarse de inmediato');

    t.mock.timers.tick(299);
    assert.equal(veces, 0, 'todavia no');

    t.mock.timers.tick(1);
    assert.equal(veces, 1);
  });

  await t.test('varias llamadas seguidas producen UNA sola ejecucion', (t) => {
    // Es su razon de ser: el usuario teclea o mueve el calendario y solo se
    // lanza una peticion al final, no una por pulsacion.
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let veces = 0;
    const f = DomUtils.debounce(() => veces++, 300);

    f(); f(); f(); f();
    t.mock.timers.tick(300);

    assert.equal(veces, 1);
  });

  await t.test('cada llamada reinicia el contador', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let veces = 0;
    const f = DomUtils.debounce(() => veces++, 300);

    f();
    t.mock.timers.tick(200);
    f();                       // reinicia: faltan otros 300
    t.mock.timers.tick(200);
    assert.equal(veces, 0, 'el segundo aviso reinicio la espera');

    t.mock.timers.tick(100);
    assert.equal(veces, 1);
  });

  await t.test('respeta los argumentos de la ULTIMA llamada', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const recibidos = [];
    const f = DomUtils.debounce((...a) => recibidos.push(a), 100);

    f('primero');
    f('segundo');
    f('tercero');
    t.mock.timers.tick(100);

    assert.deepEqual(recibidos, [['tercero']]);
  });

  await t.test('pasadas dos rafagas separadas, ejecuta dos veces', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let veces = 0;
    const f = DomUtils.debounce(() => veces++, 100);

    f();
    t.mock.timers.tick(100);
    f();
    t.mock.timers.tick(100);

    assert.equal(veces, 2);
  });
});


test('throttle', async (t) => {
  await t.test('ejecuta INMEDIATAMENTE la primera vez', (t) => {
    // Aqui esta la diferencia con debounce: throttle actua ya y luego calla.
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let veces = 0;
    const f = DomUtils.throttle(() => veces++, 300);

    f();
    assert.equal(veces, 1);
  });

  await t.test('ignora las llamadas dentro de la ventana', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let veces = 0;
    const f = DomUtils.throttle(() => veces++, 300);

    f(); f(); f(); f();
    assert.equal(veces, 1);

    t.mock.timers.tick(299);
    f();
    assert.equal(veces, 1, 'la ventana no ha terminado');
  });

  await t.test('vuelve a permitir cuando expira la ventana', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    let veces = 0;
    const f = DomUtils.throttle(() => veces++, 300);

    f();
    t.mock.timers.tick(300);
    f();

    assert.equal(veces, 2);
  });

  await t.test('CARACTERIZADO: descarta las del medio, no las guarda para el final', (t) => {
    // Esta implementacion NO ejecuta al cerrar la ventana con la ultima llamada
    // pendiente (lo que se suele llamar "trailing"). Las intermedias se pierden.
    // No es un fallo —es una decision valida— pero conviene que este escrito:
    // quien lo use para algo donde la ULTIMA llamada importe (por ejemplo el
    // valor final de un deslizador) se llevaria una sorpresa.
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const recibidos = [];
    const f = DomUtils.throttle((v) => recibidos.push(v), 100);

    f('a');          // pasa
    f('b');          // descartada
    f('c');          // descartada
    t.mock.timers.tick(100);

    assert.deepEqual(recibidos, ['a'], 'ni "b" ni "c" se ejecutan al expirar');
  });

  await t.test('respeta los argumentos de la llamada que SI pasa', (t) => {
    t.mock.timers.enable({ apis: ['setTimeout'] });
    const recibidos = [];
    const f = DomUtils.throttle((...a) => recibidos.push(a), 100);

    f('x', 1);
    assert.deepEqual(recibidos, [['x', 1]]);
  });
});
