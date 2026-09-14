/**
 * `static/js/utils/permiso-chip.js`
 *
 * El chip de permiso del reporte operacional. Lo que se prueba aqui no es cosmetico:
 * el reporte trae a proposito los permisos APROBADOS y los PENDIENTES, y la tarjeta los
 * pintaba identicos. Un supervisor planeando el dia leia como concedida una ausencia que
 * nadie habia autorizado.
 *
 * Logica pura (cero `document`), asi que se prueba sin jsdom y sin instalar nada.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

const { cargarUtil } = require('./_setup.cjs');

const P = cargarUtil('utils/permiso-chip.js');

const APROBADO = { horas: 3, tipo: 'Cita medica', especificacion: 'EPS', estado: 'APROBADO' };
const PENDIENTE = { horas: 3, tipo: 'Cita medica', especificacion: 'EPS', estado: 'PENDIENTE' };


test('estaAprobado', async (t) => {
  await t.test('solo APROBADO cuenta como concedido', () => {
    assert.equal(P.estaAprobado(APROBADO), true);
    assert.equal(P.estaAprobado(PENDIENTE), false);
  });

  await t.test('tolera espacios y minusculas del dato guardado', () => {
    assert.equal(P.estaAprobado({ estado: ' aprobado ' }), true);
  });

  await t.test('sin estado NO se da por aprobado', () => {
    // Lo seguro es lo contrario: si no consta la aprobacion, se avisa.
    assert.equal(P.estaAprobado({ horas: 2 }), false);
    assert.equal(P.estaAprobado(null), false);
  });
});


test('describir', async (t) => {
  await t.test('sin permiso no hay chip', () => {
    assert.equal(P.describir(null), null);
    assert.equal(P.describir(undefined), null);
  });

  await t.test('un permiso aprobado se anuncia con sus horas y sin ruido', () => {
    const chip = P.describir(APROBADO);
    assert.equal(chip.clase, 'tag-permiso');
    assert.equal(chip.etiqueta, '3h permiso');
    assert.match(chip.detalle, /Permiso aprobado/);
  });

  await t.test('EL CASO: uno pendiente NO puede parecerse a uno aprobado', () => {
    const chip = P.describir(PENDIENTE);
    assert.notEqual(chip.clase, P.describir(APROBADO).clase,
      'tiene que distinguirse por color, no solo por texto');
    assert.equal(chip.clase, 'tag-permiso-pend');
    assert.match(chip.etiqueta, /Pendiente/);
    assert.match(chip.detalle, /sin aprobar/i);
    assert.doesNotMatch(chip.detalle, /Permiso aprobado/);
  });

  await t.test('el detalle lleva el tipo y la especificacion cuando los hay', () => {
    assert.match(P.describir(APROBADO).detalle, /Cita medica/);
    assert.match(P.describir(APROBADO).detalle, /EPS/);
    // Y no deja separadores colgando cuando faltan.
    const minimo = P.describir({ horas: 1, estado: 'APROBADO' });
    assert.equal(minimo.detalle, 'Permiso aprobado');
  });

  await t.test('sin horas no se inventa un 0', () => {
    assert.equal(P.describir({ estado: 'APROBADO' }).etiqueta, 'Permiso');
    assert.equal(P.describir({ horas: 0, estado: 'APROBADO' }).etiqueta, '0h permiso');
  });

  await t.test('un estado desconocido se avisa igual, no se calla', () => {
    const chip = P.describir({ horas: 2, estado: 'RECHAZADO' });
    assert.equal(chip.clase, 'tag-permiso-pend');
    assert.match(chip.etiqueta, /Rechazado/);
  });

  await t.test('un estado vacio tampoco deja el chip a medias', () => {
    const chip = P.describir({ horas: 2, estado: '' });
    assert.equal(chip.clase, 'tag-permiso-pend');
    assert.match(chip.etiqueta, /Sin aprobar/);
  });
});
