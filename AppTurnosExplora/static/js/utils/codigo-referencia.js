/**
 * Código de referencia — recupera el identificador de la petición fallida.
 *
 * EL HUECO QUE CIERRA
 * -------------------
 * Las páginas de error a pantalla completa muestran un "código de referencia"
 * que el usuario reporta y el equipo busca en CloudWatch (ver core/errors.py).
 * Pero los formularios de solicitud NO recargan la página: envían por fetch y,
 * ante un 500, muestran su propio aviso. El servidor sí manda el identificador
 * en la cabecera X-Request-ID de esa respuesta, pero nadie lo leía y se perdía.
 *
 * Resultado: justo en el caso más grave —una solicitud que pudo quedar a medias
 * en la base— el usuario se quedaba sin lo único que le pedimos que reporte.
 *
 * POR QUÉ SE ENVUELVE window.fetch
 * --------------------------------
 * Hay ~50 llamadas a fetch repartidas por los formularios, casi ninguna usa
 * ApiClient y varias descartan la respuesta en el propio .catch(). Envolver
 * fetch una vez captura todas sin tocar ese código ni arriesgar una regresión
 * en la lógica de envío. Es un shim de observabilidad: no altera argumentos,
 * no altera la respuesta y no traga errores — solo mira una cabecera al pasar.
 *
 * Este fichero debe cargarse ANTES que cualquier script que haga peticiones.
 */
(function () {
  'use strict';

  // Solo interesa el identificador de una respuesta CON ERROR. Si se guardara
  // el de cualquier respuesta, un sondeo de fondo correcto pisaría el código
  // del fallo que el usuario acaba de ver.
  var ultimo = null;
  var registradoEn = 0;

  // Pasado este tiempo el código se considera de otro incidente y no se
  // muestra: es peor dar un código equivocado que no dar ninguno.
  var VIGENCIA_MS = 60000;

  var CodigoReferencia = {
    /** Último código de una respuesta con error, o null si no hay vigente. */
    ultimo: function () {
      if (!ultimo) return null;
      if (Date.now() - registradoEn > VIGENCIA_MS) return null;
      return ultimo;
    },

    /**
     * Añade el código al final de un mensaje de error, si lo hay.
     * Sin código el mensaje queda exactamente como estaba.
     *
     * @param {string} mensaje Texto que ya se le iba a mostrar al usuario.
     * @returns {string}
     */
    mensaje: function (mensaje) {
      var codigo = this.ultimo();
      if (!codigo) return mensaje;
      return mensaje + '\n\nCódigo de referencia: ' + codigo +
             '\nIndícaselo al equipo de desarrollo si reportas la incidencia.';
    },

    /**
     * Igual que mensaje(), pero para los avisos que se inyectan como HTML
     * (`notificar()` pasa su tercer argumento a Swal en `html:`, donde un \n
     * no se vería). El código es un identificador propio del servidor con
     * formato [A-F0-9]{12}; aun así se filtra antes de interpolarlo, para no
     * dejar abierta una vía de inyección si algún día cambia su origen.
     *
     * @param {string} html Aviso que ya se le iba a mostrar al usuario.
     * @returns {string}
     */
    htmlMensaje: function (html) {
      var codigo = this.ultimo();
      if (!codigo) return html;
      var limpio = String(codigo).replace(/[^A-Za-z0-9]/g, '');
      if (!limpio) return html;
      return html +
        '<p class="mt-3 mb-0" style="font-size:.9em">Código de referencia: ' +
        '<code>' + limpio + '</code><br>' +
        '<small>Indícaselo al equipo de desarrollo si reportas la incidencia.</small></p>';
    },

    /** Registra manualmente un código (por si algún día se usa XHR). */
    registrar: function (codigo) {
      if (!codigo) return;
      ultimo = codigo;
      registradoEn = Date.now();
    }
  };

  var fetchOriginal = window.fetch;
  if (typeof fetchOriginal === 'function') {
    window.fetch = function () {
      return fetchOriginal.apply(this, arguments).then(function (respuesta) {
        try {
          if (respuesta && !respuesta.ok) {
            CodigoReferencia.registrar(respuesta.headers.get('X-Request-ID'));
          }
        } catch (e) {
          // El shim JAMÁS puede romper una petición: si leer la cabecera
          // falla (respuesta opaca de otro origen, por ejemplo), se ignora.
        }
        return respuesta;   // La respuesta se devuelve intacta.
      });
      // No se encadena .catch: un fallo de red debe seguir rechazando la
      // promesa igual que antes. Además, sin respuesta no hay cabecera que
      // leer, así que no habría código que mostrar.
    };
  }

  window.CodigoReferencia = CodigoReferencia;
})();
