/**
 * `static/js/utils/guardado_atomico.js`
 *
 * Guarda la regla de "sin cambios no se guarda" de las cuatro pantallas anuales
 * (descansos de semana, fines de semana/festivos, temporadas y festivos/
 * mantenimiento). Todas reescriben el año COMPLETO al guardar, asi que un guardado
 * sin cambios borra y recrea lo publicado sin motivo.
 *
 * POR QUE SE PUEDE PROBAR SIN jsdom
 * Del boton solo se tocan tres cosas: `disabled` (booleano), `title` (cadena) y
 * `classList.toggle`. Un objeto de tres lineas es FIEL a eso, y el resto del modulo
 * —la huella normalizada— es logica pura.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

const { cargarUtil } = require('./_setup.cjs');

const guardadoAtomico = cargarUtil('utils/guardado_atomico.js');

/** Doble de boton: solo lo que el modulo usa de verdad. */
function botonFalso() {
  const clases = new Set();
  return {
    disabled: undefined,
    title: '',
    clases,
    classList: { toggle: (c, on) => (on ? clases.add(c) : clases.delete(c)) },
  };
}


test('la huella no depende del orden de claves ni del de los arrays', () => {
  const h = guardadoAtomico.huella;
  // Las jornadas de un dia son un CONJUNTO: ['PM','AM'] es el mismo descanso que
  // ['AM','PM'], y los dias de un mes tampoco tienen orden significativo.
  assert.equal(h({ '2026-01-05': ['PM', 'AM'] }), h({ '2026-01-05': ['AM', 'PM'] }));
  assert.equal(h({ 3: [9, 2], 1: [4] }), h({ 1: [4], 3: [2, 9] }));
});

test('la huella si distingue contenidos distintos', () => {
  const h = guardadoAtomico.huella;
  assert.notEqual(h({ a: ['AM'] }), h({ a: ['PM'] }));
  assert.notEqual(h({ a: ['AM'] }), h({ a: ['AM'], b: ['AM'] }));
  assert.notEqual(h({ a: [1] }), h({ a: [] }));
});

test('arranca deshabilitado: al cargar la pagina no hay nada que guardar', () => {
  const boton = botonFalso();
  guardadoAtomico({ boton, instantanea: () => ({ '2026-01-05': ['AM'] }) });
  assert.equal(boton.disabled, true);
  assert.ok(boton.clases.has('pg-btn-disabled'));
  assert.match(boton.title, /no hay nada que guardar/i);
});

test('se habilita en cuanto cambia un dia y `sucio()` lo confirma', () => {
  const boton = botonFalso();
  const estado = { '2026-01-05': ['AM'] };
  const guardia = guardadoAtomico({ boton, instantanea: () => estado });

  estado['2026-02-10'] = ['PM'];
  assert.equal(guardia.revisar(), true);
  assert.equal(boton.disabled, false);
  assert.equal(guardia.sucio(), true);
  assert.ok(!boton.clases.has('pg-btn-disabled'));
});

test('deshacer el cambio vuelve a apagar el boton', () => {
  // Esto es lo que un simple flag booleano NO daria: tres clics que recorren el
  // ciclo AM -> PM -> ambas -> ninguna dejan el dia como estaba, y eso no es un cambio.
  const boton = botonFalso();
  const estado = { '2026-01-05': ['AM'] };
  const guardia = guardadoAtomico({ boton, instantanea: () => estado });

  estado['2026-01-05'] = ['PM'];
  guardia.revisar();
  assert.equal(boton.disabled, false);

  estado['2026-01-05'] = ['AM'];
  guardia.revisar();
  assert.equal(boton.disabled, true);
  assert.equal(guardia.sucio(), false);
});

test('`reiniciar()` toma el estado actual como el publicado', () => {
  // Lo usa la carga por fetch: lo que llega del servidor ES lo guardado, no una
  // edicion del usuario, asi que no debe encender el boton.
  const boton = botonFalso();
  const estado = {};
  const guardia = guardadoAtomico({ boton, instantanea: () => estado });

  estado['2026-03-01'] = [15];
  guardia.reiniciar();
  assert.equal(boton.disabled, true);

  estado['2026-03-02'] = [16];
  guardia.revisar();
  assert.equal(boton.disabled, false);
});

test('sin boton no explota: devuelve un guardia inerte que nunca bloquea', () => {
  // Una pantalla donde el boton este oculto por permisos no debe romper el JS ni,
  // sobre todo, impedir el envio.
  const guardia = guardadoAtomico({ boton: null, instantanea: () => ({}) });
  guardia.revisar();
  assert.equal(guardia.sucio(), true);
});


/**
 * `paraFormulario`: la variante para formularios Django normales (asignar roles y
 * salas, editar empleado). No hay estado en JS; la instantanea son los campos.
 */
function formFalso(entradas) {
  const handlers = {};
  return {
    entradas,
    querySelector: () => null,
    addEventListener: (ev, fn) => { (handlers[ev] = handlers[ev] || []).push(fn); },
    disparar: ev => (handlers[ev] || []).forEach(fn => fn({})),
  };
}

test('paraFormulario ignora el token CSRF y agrupa los multi-select', () => {
  // FormData en Node necesita un form real del DOM; aqui se sustituye por un doble
  // que recorre las entradas, que es lo unico que el modulo usa de `FormData`.
  const anterior = global.FormData;
  global.FormData = function (form) {
    return { forEach: fn => form.entradas.forEach(([k, v]) => fn(v, k)) };
  };
  try {
    const boton = botonFalso();
    let entradas = [
      ['csrfmiddlewaretoken', 'abc'],
      ['roles', '1'], ['roles', '2'], ['salas', '7'],
    ];
    const form = formFalso(entradas);
    const guardia = guardadoAtomico.paraFormulario(form, boton);
    assert.equal(boton.disabled, true);

    // El token cambia en cada carga y no es un dato editado: no debe contar.
    form.entradas = [['csrfmiddlewaretoken', 'XYZ-distinto'], ['roles', '1'], ['roles', '2'], ['salas', '7']];
    form.disparar('change');
    assert.equal(boton.disabled, true);

    form.entradas = [['csrfmiddlewaretoken', 'abc'], ['roles', '1'], ['salas', '7']];
    form.disparar('change');
    assert.equal(boton.disabled, false, 'quitar un rol si es un cambio');
  } finally {
    global.FormData = anterior;
  }
});

test('paraFormulario sin form ni boton devuelve el guardia inerte', () => {
  assert.equal(guardadoAtomico.paraFormulario(null, null).sucio(), true);
});


// ---------------------------------------------------------------------------
// `referencia`: lo mostrado no siempre es lo guardado
// ---------------------------------------------------------------------------
// La pantalla de festivos/mantenimiento pinta una PROPUESTA calculada cuando el ano
// no tiene nada guardado, y la anuncia como "Sugerencia automatica (aun NO
// guardada)". Sin declarar la referencia, esa propuesta se tomaba como el estado ya
// publicado: el boton nacia apagado y el `submit` se cancelaba, asi que la unica
// forma de guardar la sugerencia era marcar un dia a mano y desmarcarlo. El ano se
// quedaba sin mantenimientos y nadie se enteraba hasta que "Mis Turnos" mostraba
// descansos que no eran.

test('sin nada guardado, la propuesta que se muestra cuenta como cambio', () => {
  const boton = botonFalso();
  // Lo que la vista pinto: 36 dias de mantenimiento propuestos. En la base, NADA.
  let estado = { 1: [5, 12, 19, 26], 2: [2, 9, 16, 23] };

  const guardia = guardadoAtomico({
    boton,
    instantanea: () => estado,
    referencia: {},          // el ano esta vacio en la base
  });

  assert.equal(boton.disabled, false, 'hay algo que guardar: la propuesta');
  assert.equal(guardia.sucio(), true);
});

test('con el ano ya guardado, la referencia sigue siendo lo mostrado', () => {
  const boton = botonFalso();
  let estado = { 1: [5, 12] };

  // Sin `referencia`: lo mostrado ES lo guardado (comportamiento de siempre).
  const guardia = guardadoAtomico({ boton, instantanea: () => estado });

  assert.equal(boton.disabled, true, 'nada tocado, nada que guardar');

  estado = { 1: [5, 12, 19] };
  guardia.revisar();
  assert.equal(boton.disabled, false, 'anadir un dia si es un cambio');
});

test('con referencia declarada, volver al estado guardado vuelve a apagar el boton', () => {
  const boton = botonFalso();
  let estado = {};
  const guardia = guardadoAtomico({ boton, instantanea: () => estado, referencia: {} });

  assert.equal(boton.disabled, true, 'vacio y vacio: nada que guardar');

  estado = { 3: [7] };
  guardia.revisar();
  assert.equal(boton.disabled, false);

  // Se deshace la seleccion: vuelve a coincidir con lo guardado (nada).
  estado = {};
  guardia.revisar();
  assert.equal(boton.disabled, true, 'deshacer devuelve el boton a apagado');
});

test('referencia: undefined es una referencia declarada, no una ausente', () => {
  // `Object.assign({...}, {referencia: undefined})` es un error facil de cometer al
  // construir las opciones de forma condicional. Si el modulo mirara `!= null` en vez
  // de `hasOwnProperty`, caeria silenciosamente al comportamiento viejo y el bug
  // volveria sin que ningun test lo notara.
  const boton = botonFalso();
  const estado = { 1: [1] };
  guardadoAtomico({ boton, instantanea: () => estado, referencia: undefined });
  assert.equal(boton.disabled, false, 'undefined significa "no hay nada guardado"');
});
