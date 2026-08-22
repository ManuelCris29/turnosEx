/**
 * `static/js/utils/date-utils.js`
 *
 * Primer fichero de la red de pruebas de JavaScript del proyecto. Se empieza por
 * aqui porque es logica PURA: cero referencias a `document`, `window` o `fetch`,
 * asi que se prueba sin jsdom y sin instalar nada.
 *
 * Las fechas de este modulo alimentan los seis formularios de solicitudes, y un
 * dia de desfase ahi no da error: agenda el turno equivocado.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

const { cargarUtil, conZonaHoraria } = require('./_setup.cjs');

const DateUtils = cargarUtil('utils/date-utils.js');

// 2026-01-03 es sabado y 2026-01-04 domingo (comprobado con `date`).
const SABADO = '2026-01-03';
const DOMINGO = '2026-01-04';
const LUNES = '2026-01-05';


test('isSunday / isSaturday / isWeekend', async (t) => {
  await t.test('reconoce el sabado y el domingo', () => {
    assert.equal(DateUtils.isSaturday(SABADO), true);
    assert.equal(DateUtils.isSunday(DOMINGO), true);
    assert.equal(DateUtils.isWeekend(SABADO), true);
    assert.equal(DateUtils.isWeekend(DOMINGO), true);
  });

  await t.test('un lunes no es fin de semana', () => {
    assert.equal(DateUtils.isSaturday(LUNES), false);
    assert.equal(DateUtils.isSunday(LUNES), false);
    assert.equal(DateUtils.isWeekend(LUNES), false);
  });

  await t.test('acepta tanto cadena como objeto Date', () => {
    assert.equal(DateUtils.isSaturday(new Date(2026, 0, 3)), true);
    assert.equal(DateUtils.isSunday(new Date(2026, 0, 4)), true);
  });

  await t.test('el dia NO cambia con la zona horaria', () => {
    // Estas funciones parsean `${fecha}T00:00:00`, o sea medianoche LOCAL. Si
    // parsearan `new Date('2026-01-04')` seria medianoche UTC, y en Colombia
    // (UTC-5) eso es el dia 3 a las 19:00: un domingo se leeria como sabado.
    for (const tz of ['America/Bogota', 'UTC', 'Europe/Madrid', 'Asia/Tokyo']) {
      conZonaHoraria(tz, () => {
        assert.equal(DateUtils.isSunday(DOMINGO), true, `fallo en ${tz}`);
        assert.equal(DateUtils.isSaturday(SABADO), true, `fallo en ${tz}`);
      });
    }
  });
});


test('getToday devuelve la fecha LOCAL, no la UTC', () => {
  // El propio codigo lo documenta: en Colombia, a partir de las 19:00 `toISOString()`
  // ya devuelve el dia siguiente, y un "hoy" adelantado descuadra cualquier
  // comparacion contra lo que el usuario elige en el calendario.
  const hoy = DateUtils.getToday();
  const d = new Date();
  const esperado = d.getFullYear() + '-' +
    String(d.getMonth() + 1).padStart(2, '0') + '-' +
    String(d.getDate()).padStart(2, '0');

  assert.equal(hoy, esperado);
  assert.match(hoy, /^\d{4}-\d{2}-\d{2}$/);
});


test('compareDates', async (t) => {
  await t.test('ordena correctamente', () => {
    assert.equal(DateUtils.compareDates('2026-01-01', '2026-01-02'), -1);
    assert.equal(DateUtils.compareDates('2026-01-02', '2026-01-01'), 1);
    assert.equal(DateUtils.compareDates('2026-01-01', '2026-01-01'), 0);
  });

  await t.test('ignora la hora: el mismo dia a distinta hora es igual', () => {
    const manana = new Date(2026, 0, 15, 8, 30);
    const tarde = new Date(2026, 0, 15, 18, 45);
    assert.equal(DateUtils.compareDates(manana, tarde), 0);
  });

  await t.test('CARACTERIZADO: modifica los Date que recibe', () => {
    // No es lo deseable, pero es lo que hace: pone la hora a 00:00 sobre el
    // objeto original en vez de sobre una copia. Se fija para que se note si
    // alguien lo cambia, porque quien pase un Date y lo siga usando despues
    // se encontrara la hora perdida.
    const fecha = new Date(2026, 0, 15, 13, 45);
    DateUtils.compareDates(fecha, new Date(2026, 0, 16));
    assert.equal(fecha.getHours(), 0, 'ya no muta: se puede quitar esta advertencia');
  });
});


test('addDays', async (t) => {
  await t.test('suma dias y cruza el fin de mes', () => {
    assert.equal(DateUtils.addDays(new Date(2026, 0, 30), 5).getDate(), 4);
    assert.equal(DateUtils.addDays(new Date(2026, 0, 30), 5).getMonth(), 1); // febrero
  });

  await t.test('acepta dias negativos', () => {
    assert.equal(DateUtils.addDays(new Date(2026, 0, 5), -10).getDate(), 26);
  });

  await t.test('CARACTERIZADO: modifica el Date original', () => {
    // Devuelve el MISMO objeto que recibe, ya modificado. Quien haga
    // `const otro = DateUtils.addDays(fecha, 7)` y luego use `fecha` la
    // encontrara movida siete dias. Se fija para que el dia que se corrija
    // sea una decision y no un accidente.
    const original = new Date(2026, 0, 15);
    const resultado = DateUtils.addDays(original, 5);

    assert.equal(original.getDate(), 20, 'ya no muta: se puede quitar esta advertencia');
    assert.equal(resultado, original, 'devuelve el mismo objeto, no una copia');
  });
});


test('isPastDate / isFutureDate', async (t) => {
  await t.test('ayer es pasado y manana es futuro', () => {
    const ayer = new Date();
    ayer.setDate(ayer.getDate() - 1);
    const manana = new Date();
    manana.setDate(manana.getDate() + 1);

    assert.equal(DateUtils.isPastDate(ayer), true);
    assert.equal(DateUtils.isFutureDate(manana), true);
  });

  await t.test('hoy no es ni pasado ni futuro', () => {
    const hoy = new Date();
    assert.equal(DateUtils.isPastDate(hoy), false);
    assert.equal(DateUtils.isFutureDate(new Date()), false);
  });
});


test('getMonthRange', async (t) => {
  await t.test('devuelve el primer y el ultimo dia del mes', () => {
    assert.deepEqual(DateUtils.getMonthRange(2026, 1),
                     { fechaInicio: '2026-01-01', fechaFin: '2026-01-31' });
    assert.deepEqual(DateUtils.getMonthRange(2026, 2),
                     { fechaInicio: '2026-02-01', fechaFin: '2026-02-28' });
  });

  await t.test('acierta con febrero de un ano bisiesto', () => {
    assert.deepEqual(DateUtils.getMonthRange(2028, 2),
                     { fechaInicio: '2028-02-01', fechaFin: '2028-02-29' });
  });

  await t.test('el rango NO depende de la zona horaria', () => {
    // Esta era la unica funcion del modulo que usaba `toISOString()`, o sea que
    // convertia a UTC antes de recortar la fecha. En husos NEGATIVOS no se nota
    // (la medianoche local cae mas tarde en UTC y el dia se conserva), pero en
    // husos POSITIVOS retrocedia un dia: en Europe/Madrid, enero de 2026 salia
    // como 2025-12-31 .. 2026-01-30.
    //
    // No afectaba a nadie —la app corre en Colombia y el CI en UTC—, pero era un
    // fallo esperando a un despliegue en otro huso. Este test lo cierra.
    const esperado = { fechaInicio: '2026-01-01', fechaFin: '2026-01-31' };
    for (const tz of ['America/Bogota', 'UTC', 'Europe/Madrid', 'Asia/Tokyo']) {
      conZonaHoraria(tz, () => {
        assert.deepEqual(DateUtils.getMonthRange(2026, 1), esperado, `fallo en ${tz}`);
      });
    }
  });
});
