/**
 * `static/js/utils/validators.js`
 *
 * Segundo fichero de la red. Como `date-utils`, es logica pura: se prueba sin
 * jsdom y sin dependencias.
 *
 * AVISO SOBRE ESTE MODULO, medido el 2026-08-22: hoy no lo llama NADIE. Se carga
 * con `<script>` en cuatro plantillas (`solicitar_cambio_turno`,
 * `solicitar_ct_permanente`, `solicitar_doblada` y `mis_turnos`) pero no hay una
 * sola referencia a `Validators.` en todo el proyecto. Son 191 lineas que se
 * descargan para nada.
 *
 * Eso no lo hace inutil de probar —al contrario: los dos fallos de fecha que
 * estos tests fijan estaban ahi esperando al primero que lo usara— pero conviene
 * saberlo antes de invertir mas en el.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

const { cargarUtil, conZonaHoraria } = require('./_setup.cjs');

const Validators = cargarUtil('utils/validators.js');
const DateUtils = cargarUtil('utils/date-utils.js');

const ZONAS = ['America/Bogota', 'UTC', 'Europe/Madrid', 'Asia/Tokyo'];


test('required', async (t) => {
  await t.test('rechaza vacio, espacios, null e indefinido', () => {
    assert.equal(Validators.required('').valid, false);
    assert.equal(Validators.required('   ').valid, false);
    assert.equal(Validators.required(null).valid, false);
    assert.equal(Validators.required(undefined).valid, false);
  });

  await t.test('acepta texto con contenido', () => {
    assert.equal(Validators.required('algo').valid, true);
    assert.equal(Validators.required('  algo  ').valid, true);
  });

  await t.test('el mensaje incorpora el nombre del campo', () => {
    assert.equal(Validators.required('', 'La fecha').message, 'La fecha es requerido');
  });
});


test('email', async (t) => {
  await t.test('acepta direcciones validas', () => {
    for (const e of ['a@b.co', 'manuel.moreno@parqueexplora.org', 'x+tag@dominio.com.co']) {
      assert.equal(Validators.email(e).valid, true, e);
    }
  });

  await t.test('rechaza las invalidas', () => {
    for (const e of ['', 'sin-arroba.com', 'a@b', 'a@ b.co', 'a b@c.co', 'a@@b.co']) {
      assert.equal(Validators.email(e).valid, false, e);
    }
  });
});


test('futureDate / pastDate', async (t) => {
  await t.test('HOY es fecha valida para futureDate, en cualquier zona', () => {
    // El fallo que estos tests cerraron: `new Date('2026-01-15')` es medianoche
    // UTC, que en Colombia (UTC-5) es el dia 14 a las 19:00. Con el
    // `setHours(0,0,0,0)` posterior la fecha se quedaba en el dia ANTERIOR, asi
    // que `futureDate(hoy)` devolvia false pese a que su mensaje dice
    // "hoy o una fecha futura". Un explorador que eligiera el dia de hoy en el
    // calendario habria visto su fecha rechazada.
    for (const tz of ZONAS) {
      conZonaHoraria(tz, () => {
        const hoy = DateUtils.getToday();
        assert.equal(Validators.futureDate(hoy).valid, true, `futureDate fallo en ${tz}`);
        assert.equal(Validators.pastDate(hoy).valid, false, `pastDate fallo en ${tz}`);
      });
    }
  });

  await t.test('manana es futura y ayer es pasada', () => {
    const manana = new Date();
    manana.setDate(manana.getDate() + 1);
    const ayer = new Date();
    ayer.setDate(ayer.getDate() - 1);

    assert.equal(Validators.futureDate(manana).valid, true);
    assert.equal(Validators.pastDate(manana).valid, false);
    assert.equal(Validators.pastDate(ayer).valid, true);
    assert.equal(Validators.futureDate(ayer).valid, false);
  });
});


test('dateAfter', async (t) => {
  await t.test('exige que la segunda sea POSTERIOR, no igual', () => {
    assert.equal(Validators.dateAfter('2026-01-01', '2026-01-02').valid, true);
    assert.equal(Validators.dateAfter('2026-01-02', '2026-01-01').valid, false);
    assert.equal(Validators.dateAfter('2026-01-01', '2026-01-01').valid, false);
  });

  await t.test('no le afecta la zona horaria', () => {
    // A diferencia de futureDate, aqui las dos fechas se desplazaban IGUAL, asi
    // que la comparacion siempre fue correcta. Se fija para que siga siendolo.
    for (const tz of ZONAS) {
      conZonaHoraria(tz, () => {
        assert.equal(Validators.dateAfter('2026-01-01', '2026-01-02').valid, true, tz);
        assert.equal(Validators.dateAfter('2026-01-02', '2026-01-01').valid, false, tz);
      });
    }
  });
});


test('minLength / maxLength', async (t) => {
  await t.test('respetan los limites, que son inclusivos', () => {
    assert.equal(Validators.minLength('abc', 3).valid, true);
    assert.equal(Validators.minLength('ab', 3).valid, false);
    assert.equal(Validators.maxLength('abc', 3).valid, true);
    assert.equal(Validators.maxLength('abcd', 3).valid, false);
  });
});


test('number / positiveNumber / range', async (t) => {
  await t.test('number acepta enteros, decimales y negativos', () => {
    assert.equal(Validators.number('42').valid, true);
    assert.equal(Validators.number('4.5').valid, true);
    assert.equal(Validators.number('-3').valid, true);
    assert.equal(Validators.number('abc').valid, false);
  });

  await t.test('positiveNumber rechaza el cero y los negativos', () => {
    assert.equal(Validators.positiveNumber('1').valid, true);
    assert.equal(Validators.positiveNumber('0').valid, false);
    assert.equal(Validators.positiveNumber('-1').valid, false);
  });

  await t.test('range es inclusivo en los dos extremos', () => {
    assert.equal(Validators.range('5', 1, 10).valid, true);
    assert.equal(Validators.range('1', 1, 10).valid, true);
    assert.equal(Validators.range('10', 1, 10).valid, true);
    assert.equal(Validators.range('11', 1, 10).valid, false);
    assert.equal(Validators.range('abc', 1, 10).valid, false);
  });
});


test('validate encadena reglas', async (t) => {
  await t.test('devuelve el PRIMER error, no el ultimo', () => {
    const reglas = [
      (v) => Validators.required(v, 'El motivo'),
      (v) => Validators.minLength(v, 10, 'El motivo'),
    ];

    const vacio = Validators.validate('', reglas);
    assert.equal(vacio.valid, false);
    assert.match(vacio.message, /requerido/, 'debe cortar en la primera regla que falla');

    const corto = Validators.validate('hola', reglas);
    assert.equal(corto.valid, false);
    assert.match(corto.message, /10/);
  });

  await t.test('sin errores devuelve mensaje vacio', () => {
    const r = Validators.validate('un motivo suficientemente largo', [
      (v) => Validators.required(v),
      (v) => Validators.minLength(v, 10),
    ]);
    assert.equal(r.valid, true);
    assert.equal(r.message, '');
  });
});


test('todos los validadores devuelven la misma forma', () => {
  // El contrato que hace posible encadenarlos en `validate`: siempre
  // { valid: boolean, message: string }. Si uno devolviera solo un booleano,
  // `validate` leeria `undefined.valid` y reventaria.
  const resultados = [
    Validators.required('x'),
    Validators.email('a@b.co'),
    Validators.futureDate(DateUtils.getToday()),
    Validators.pastDate('2020-01-01'),
    Validators.dateAfter('2026-01-01', '2026-01-02'),
    Validators.minLength('abc', 2),
    Validators.maxLength('abc', 5),
    Validators.number('1'),
    Validators.positiveNumber('1'),
    Validators.range('5', 1, 10),
  ];

  for (const r of resultados) {
    assert.equal(typeof r.valid, 'boolean');
    assert.equal(typeof r.message, 'string');
  }
});
