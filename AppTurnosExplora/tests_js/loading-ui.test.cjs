/**
 * `static/js/loading-ui.js`
 *
 * QUE SE PRUEBA AQUI Y POR QUE IMPORTA
 * El modal de carga es DELIBERADAMENTE inescapable: sin boton, sin Escape y sin clic
 * fuera. Se cierra solo cuando el .then() o el .catch() del envio muestran otro Swal.
 * Eso convierte a `fetchLimitado` en la unica garantia de que la promesa TERMINA: si
 * fallara, el usuario se quedaria con la pantalla bloqueada y sin mas salida que
 * recargar — justo lo que el texto del modal le pide que no haga.
 *
 * `avisoDeFallo` se prueba porque distingue dos casos OPUESTOS para el usuario: ante un
 * fallo de red la solicitud no salio y reintentar es correcto; ante un corte por tiempo
 * puede haber salido —abortar el fetch no cancela nada en el servidor— y reintentar
 * duplicaria el acuerdo.
 *
 * POR QUE SE PUEDE PROBAR SIN jsdom
 * De navegador solo usa `fetch` (nativo en Node desde la v18, aqui doblado para no
 * salir a la red), `AbortController` (tambien nativo) y `Swal`, que solo se consulta
 * con `typeof` y por tanto no estorba. `mostrar`/`ocultar` no se prueban: son Swal puro.
 *
 * NOTA SOBRE LA CARGA
 * `loading-ui.js` no tiene `module.exports` —es un IIFE que hace `window.LoadingUI = ...`—
 * asi que se lee de `window` en vez de del valor que devuelve `require`. Se prueba tal
 * cual esta, sin tocar codigo de produccion.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

const { cargarUtil } = require('./_setup.cjs');

cargarUtil('loading-ui.js');
const LoadingUI = global.window.LoadingUI;


/**
 * Doble de `fetch` que tarda `demoraMs` y respeta la senal de aborto.
 * Guarda la ultima senal recibida para poder comprobar si se aborto o no.
 */
function fetchLento(demoraMs, respuesta = { ok: true }) {
  const doble = (url, opciones) => {
    doble.senal = opciones && opciones.signal;
    doble.opciones = opciones;
    return new Promise((resolver, rechazar) => {
      const t = setTimeout(() => resolver(respuesta), demoraMs);
      if (doble.senal) {
        doble.senal.addEventListener('abort', () => {
          clearTimeout(t);
          // Es lo que hace el fetch real al abortarse.
          const err = new Error('The operation was aborted.');
          err.name = 'AbortError';
          rechazar(err);
        });
      }
    });
  };
  return doble;
}

/** Ejecuta `fn` con un `fetch` de mentira y lo retira despues. */
async function conFetch(doble, fn) {
  const anterior = global.fetch;
  global.fetch = doble;
  try {
    return await fn();
  } finally {
    global.fetch = anterior;
  }
}

/** Espera `ms` sin bloquear. */
const esperar = (ms) => new Promise((r) => setTimeout(r, ms));


test('fetchLimitado', async (t) => {

  await t.test('devuelve la respuesta intacta cuando llega a tiempo', async () => {
    const respuesta = { ok: true, status: 201 };
    const doble = fetchLento(5, respuesta);
    await conFetch(doble, async () => {
      const r = await LoadingUI.fetchLimitado('/x', { method: 'POST' }, 200);
      assert.equal(r, respuesta);
    });
  });

  await t.test('aborta y rechaza con esTiempoAgotado al pasarse del limite', async () => {
    const doble = fetchLento(500);
    await conFetch(doble, async () => {
      await assert.rejects(
        () => LoadingUI.fetchLimitado('/x', { method: 'POST' }, 20),
        (e) => {
          assert.equal(e.esTiempoAgotado, true);
          // El mensaje NO puede decir que no se envio: puede haberse creado.
          assert.match(e.message, /Mis Solicitudes/);
          return true;
        }
      );
      assert.equal(doble.senal.aborted, true, 'la peticion debe quedar abortada');
    });
  });

  await t.test('no aborta despues de haber respondido (el temporizador se limpia)', async () => {
    // Sin el clearTimeout del camino de exito, el abort saltaria igual pasado el
    // limite. No romperia la promesa —ya resuelta— pero si dejaria la peticion
    // cancelada por detras y un temporizador vivo por cada envio de la sesion.
    const doble = fetchLento(5);
    await conFetch(doble, async () => {
      await LoadingUI.fetchLimitado('/x', {}, 30);
      await esperar(60);
      assert.equal(doble.senal.aborted, false, 'no debe abortarse tras responder');
    });
  });

  await t.test('un fallo de red se propaga tal cual, sin marcarlo como tiempo agotado', async () => {
    // Distinguirlos es el punto: aqui SI es correcto decirle al usuario que reintente.
    const doble = () => Promise.reject(new TypeError('Failed to fetch'));
    await conFetch(doble, async () => {
      await assert.rejects(
        () => LoadingUI.fetchLimitado('/x', {}, 200),
        (e) => {
          assert.equal(e.esTiempoAgotado, undefined);
          assert.equal(e.message, 'Failed to fetch');
          return true;
        }
      );
    });
  });

  await t.test('no muta el objeto de opciones que recibe', async () => {
    // Varios formularios reutilizan el mismo FormData/objeto para reenviar tras
    // confirmar una restriccion medica. Colarle la senal del intento anterior
    // haria que el reenvio naciera ya abortado.
    const opciones = { method: 'POST', body: 'x' };
    const doble = fetchLento(5);
    await conFetch(doble, async () => {
      await LoadingUI.fetchLimitado('/x', opciones, 200);
      assert.equal(opciones.signal, undefined);
      assert.ok(doble.opciones.signal, 'la copia si lleva la senal');
      assert.equal(doble.opciones.method, 'POST');
      assert.equal(doble.opciones.body, 'x');
    });
  });

  await t.test('sin AbortController delega en fetch: mejor sin limite que sin envio', async () => {
    const original = global.AbortController;
    delete global.AbortController;
    try {
      const respuesta = { ok: true };
      const doble = fetchLento(1, respuesta);
      await conFetch(doble, async () => {
        const r = await LoadingUI.fetchLimitado('/x', { method: 'POST' }, 10);
        assert.equal(r, respuesta);
        assert.equal(doble.opciones.signal, undefined);
      });
    } finally {
      global.AbortController = original;
    }
  });
});


test('avisoDeFallo', async (t) => {

  await t.test('el corte por tiempo trae titulo propio y manda a comprobar', () => {
    const error = Object.assign(new Error('lo que sea'), { esTiempoAgotado: true });
    const aviso = LoadingUI.avisoDeFallo(error, 'No se pudo enviar. Intenta de nuevo.');

    assert.equal(aviso.esTiempoAgotado, true);
    assert.ok(aviso.titulo, 'debe traer titulo para que el formulario no use el suyo');
    assert.match(aviso.texto, /Mis Solicitudes/);
    // Lo que NO debe hacer: afirmar que no se envio.
    assert.doesNotMatch(aviso.texto, /No se pudo enviar/);
  });

  await t.test('cualquier otro fallo conserva el mensaje que ya mostraba el formulario', () => {
    const aviso = LoadingUI.avisoDeFallo(new TypeError('Failed to fetch'), 'Intenta de nuevo.');

    assert.equal(aviso.esTiempoAgotado, false);
    assert.equal(aviso.titulo, null, 'null = el formulario conserva su propio titulo');
    assert.equal(aviso.texto, 'Intenta de nuevo.');
  });

  await t.test('aguanta un error nulo o indefinido', () => {
    // Varios .catch() del proyecto se invocan sin argumento: `.catch(() => ...)`.
    for (const valor of [null, undefined, 'texto suelto']) {
      const aviso = LoadingUI.avisoDeFallo(valor, 'por defecto');
      assert.equal(aviso.esTiempoAgotado, false);
      assert.equal(aviso.texto, 'por defecto');
    }
  });
});
