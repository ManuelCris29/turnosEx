/**
 * `static/js/utils/api-client.js`
 *
 * Por aqui pasan TODAS las llamadas AJAX de la aplicacion, incluido el token CSRF
 * que las protege.
 *
 * POR QUE SE PUEDE PROBAR SIN jsdom
 * El modulo parece necesitar navegador, pero mirado de cerca solo usa tres cosas y
 * ninguna es DOM de verdad:
 *
 *   - `fetch`                  -> Node lo trae nativo desde la v18; aqui se
 *                                 sustituye por un doble para no salir a la red.
 *   - `document.cookie`        -> es una CADENA.
 *   - `document.querySelector` -> solo para leer `.value` de un input.
 *
 * No recorre el arbol, no mide, no escucha eventos. Un doble de tres lineas es
 * FIEL a lo que el codigo hace, asi que jsdom no aportaria nada y si traeria una
 * dependencia. Cuando toque probar `dom-utils` completo sera otra historia.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

const { cargarUtil } = require('./_setup.cjs');

const ApiClient = cargarUtil('utils/api-client.js');


/** Doble de `fetch` que devuelve lo que se le diga y apunta como fue llamado. */
function fetchFalso({ ok = true, status = 200, json = {} } = {}) {
  const llamadas = [];
  const doble = async (url, opciones) => {
    llamadas.push({ url, opciones });
    return {
      ok,
      status,
      json: async () => json,
    };
  };
  doble.llamadas = llamadas;
  return doble;
}

/** Ejecuta `fn` con un `fetch` y un `document` de mentira, y los retira despues. */
async function conEntornoFalso({ fetch: f, cookie = '', input = null }, fn) {
  const fetchAnterior = global.fetch;
  const documentAnterior = global.document;
  const errorAnterior = console.error;

  global.fetch = f;
  global.document = {
    cookie,
    querySelector: () => input,
  };
  // El modulo registra los fallos con console.error. Silenciarlo evita que la
  // salida de los tests parezca rota cuando se estan probando A PROPOSITO los
  // caminos de error.
  console.error = () => {};

  try {
    return await fn();
  } finally {
    global.fetch = fetchAnterior;
    global.document = documentAnterior;
    console.error = errorAnterior;
  }
}


test('getCsrfToken', async (t) => {
  await t.test('lo saca de la cookie csrftoken', async () => {
    await conEntornoFalso({ cookie: 'otra=1; csrftoken=ABC123; mas=2' }, () => {
      assert.equal(ApiClient.getCsrfToken(), 'ABC123');
    });
  });

  await t.test('no confunde una cookie que solo CONTENGA el nombre', async () => {
    // Usa `startsWith`, asi que `xcsrftoken` no debe colar. Si algun dia se
    // cambiara por un `includes`, este test lo caza.
    await conEntornoFalso({ cookie: 'xcsrftoken=FALSO; csrftoken=BUENO' }, () => {
      assert.equal(ApiClient.getCsrfToken(), 'BUENO');
    });
  });

  await t.test('sin cookie, cae al input del formulario', async () => {
    await conEntornoFalso({ cookie: '', input: { value: 'DESDE-INPUT' } }, () => {
      assert.equal(ApiClient.getCsrfToken(), 'DESDE-INPUT');
    });
  });

  await t.test('sin cookie y sin input devuelve cadena vacia, no revienta', async () => {
    // Importa que no lance: si lanzara, cualquier POST se caeria antes de salir,
    // y el usuario veria un fallo sin explicacion en vez de un 403 del servidor.
    await conEntornoFalso({ cookie: '', input: null }, () => {
      assert.equal(ApiClient.getCsrfToken(), '');
    });
  });
});


test('get', async (t) => {
  await t.test('devuelve el JSON de la respuesta', async () => {
    const f = fetchFalso({ json: { total: 3 } });
    await conEntornoFalso({ fetch: f }, async () => {
      assert.deepEqual(await ApiClient.get('/api/x'), { total: 3 });
    });
  });

  await t.test('monta el query string a partir de los parametros', async () => {
    const f = fetchFalso();
    await conEntornoFalso({ fetch: f }, async () => {
      await ApiClient.get('/api/turnos', { mes: 8, anio: 2026 });
    });
    assert.equal(f.llamadas[0].url, '/api/turnos?mes=8&anio=2026');
  });

  await t.test('sin parametros no anade el interrogante', async () => {
    const f = fetchFalso();
    await conEntornoFalso({ fetch: f }, async () => {
      await ApiClient.get('/api/turnos');
    });
    assert.equal(f.llamadas[0].url, '/api/turnos');
  });

  await t.test('escapa los parametros con caracteres especiales', async () => {
    const f = fetchFalso();
    await conEntornoFalso({ fetch: f }, async () => {
      await ApiClient.get('/api/x', { nombre: 'Ana Pérez & Cía' });
    });
    assert.match(f.llamadas[0].url, /nombre=Ana\+P/);
    assert.doesNotMatch(f.llamadas[0].url, / & /);
  });

  await t.test('manda la cabecera que Django usa para distinguir AJAX', async () => {
    // `X-Requested-With` es lo que mira `_quiere_json` en el backend para decidir
    // si responde JSON o redirige. Sin ella, una API devolveria HTML.
    const f = fetchFalso();
    await conEntornoFalso({ fetch: f }, async () => {
      await ApiClient.get('/api/x');
    });
    assert.equal(f.llamadas[0].opciones.headers['X-Requested-With'], 'XMLHttpRequest');
    assert.equal(f.llamadas[0].opciones.credentials, 'same-origin');
  });

  await t.test('una respuesta con error HTTP lanza, no devuelve datos a medias', async () => {
    const f = fetchFalso({ ok: false, status: 500 });
    await conEntornoFalso({ fetch: f }, async () => {
      await assert.rejects(() => ApiClient.get('/api/x'), /500/);
    });
  });

  await t.test('un 404 tambien lanza', async () => {
    const f = fetchFalso({ ok: false, status: 404 });
    await conEntornoFalso({ fetch: f }, async () => {
      await assert.rejects(() => ApiClient.get('/api/x'), /404/);
    });
  });
});


test('post', async (t) => {
  await t.test('envia el cuerpo como JSON y adjunta el token CSRF', async () => {
    const f = fetchFalso({ json: { ok: true } });
    await conEntornoFalso({ fetch: f, cookie: 'csrftoken=TOK' }, async () => {
      await ApiClient.post('/api/crear', { fecha: '2026-01-15' });
    });

    const { opciones } = f.llamadas[0];
    assert.equal(opciones.method, 'POST');
    assert.equal(opciones.headers['X-CSRFToken'], 'TOK');
    assert.deepEqual(JSON.parse(opciones.body), { fecha: '2026-01-15' });
  });

  await t.test('sin token disponible manda la cabecera vacia, no la omite', async () => {
    // Django rechazara la peticion con 403, que es la respuesta correcta y
    // diagnosticable. Lo importante es que la llamada SALGA en vez de reventar
    // en el navegador.
    const f = fetchFalso();
    await conEntornoFalso({ fetch: f, cookie: '', input: null }, async () => {
      await ApiClient.post('/api/crear', {});
    });
    assert.equal(f.llamadas[0].opciones.headers['X-CSRFToken'], '');
  });

  await t.test('propaga el error HTTP', async () => {
    const f = fetchFalso({ ok: false, status: 400 });
    await conEntornoFalso({ fetch: f, cookie: 'csrftoken=T' }, async () => {
      await assert.rejects(() => ApiClient.post('/api/x', {}), /400/);
    });
  });
});


test('handleError da una forma estable', async (t) => {
  await t.test('recoge el mensaje y el contexto', async () => {
    await conEntornoFalso({}, () => {
      const r = ApiClient.handleError(new Error('se cayo la red'), 'cargarMes');
      assert.deepEqual(r, { success: false, error: 'se cayo la red', context: 'cargarMes' });
    });
  });

  await t.test('un error sin mensaje no deja el campo vacio', async () => {
    await conEntornoFalso({}, () => {
      const r = ApiClient.handleError(new Error(''), 'x');
      assert.equal(r.error, 'Error desconocido');
    });
  });
});
