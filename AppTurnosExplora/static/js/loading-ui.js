/**
 * LoadingUI - Indicador de carga reutilizable para todo el proyecto.
 *
 * Usa SweetAlert2 (ya cargado globalmente en base.html) para mostrar un modal
 * BLOQUEANTE: el usuario no puede volver a hacer clic en el botón ni interactuar
 * con la página mientras una solicitud está en proceso. Esto evita el doble envío
 * (doble clic) y le da feedback claro de que algo está pasando.
 *
 * Uso típico:
 *
 *   LoadingUI.mostrar('Enviando solicitud...');
 *   fetch(url, {...})
 *     .then(data => {
 *        // Un Swal.fire de éxito REEMPLAZA automáticamente el modal de carga.
 *        Swal.fire({ icon: 'success', title: '¡Listo!' });
 *     })
 *     .catch(() => {
 *        // En errores sin Swal propio, cerrar el loading explícitamente:
 *        LoadingUI.ocultar();
 *        Swal.fire({ icon: 'error', title: 'Error' });
 *     });
 *
 * Nota: si después de mostrar() se llama a cualquier otro Swal.fire(), SweetAlert
 * reutiliza el mismo modal y reemplaza el contenido (no hace falta ocultar primero).
 * Solo llama a ocultar() cuando NO vas a mostrar otro Swal.
 *
 * EL MODAL NUNCA DEBE QUEDARSE COLGADO
 * ------------------------------------
 * Este modal es deliberadamente inescapable (sin botón, sin Escape, sin clic fuera):
 * se cierra únicamente cuando el .then() o el .catch() del fetch muestran otro Swal.
 * Si la petición no termina NUNCA, tampoco lo hace el modal, y el usuario se queda con
 * la pantalla bloqueada sin más salida que recargar — justo lo que el propio texto le
 * pide que no haga. Y `fetch` no tiene timeout propio: una conexión colgada puede
 * esperar minutos. Por eso `fetchLimitado` le pone un límite duro y `avisoDeFallo`
 * traduce ese límite a un mensaje honesto.
 */
(function (global) {
    'use strict';

    // Techo de espera de un envío. Generoso a propósito: el objetivo NO es cortar
    // una petición lenta (crear una solicitud dispara varios correos y puede tardar
    // segundos), sino garantizar que una petición COLGADA acabe soltando la pantalla.
    var LIMITE_ENVIO_MS = 45000;

    // Aviso del corte por tiempo. Está redactado con mucho cuidado y no debe suavizarse:
    // abortar el fetch NO cancela nada en el servidor. Cuando saltamos, la solicitud
    // puede haberse creado perfectamente y ser solo la RESPUESTA la que no llegó. Decirle
    // al usuario "no se pudo enviar, intenta de nuevo" —lo que dicen los .catch() de red—
    // sería falso y le llevaría a crear el acuerdo por duplicado. Se le manda a comprobar.
    var TITULO_TIEMPO = 'La solicitud está tardando demasiado';
    var TEXTO_TIEMPO = 'Dejamos de esperar la respuesta del servidor. Es posible que la ' +
        'solicitud SÍ se haya enviado: revisa "Mis Solicitudes" antes de volver a intentarlo.';

    var LoadingUI = {

        LIMITE_ENVIO_MS: LIMITE_ENVIO_MS,
        /**
         * Muestra el modal de carga bloqueante.
         * @param {string} [mensaje] Título a mostrar (por defecto "Procesando...").
         * @param {string} [detalle] Texto secundario opcional.
         */
        mostrar: function (mensaje, detalle) {
            if (typeof Swal === 'undefined') return;
            Swal.fire({
                title: mensaje || 'Procesando...',
                html: detalle || 'Por favor espera, no cierres ni recargues la página.',
                allowOutsideClick: false,
                allowEscapeKey: false,
                showConfirmButton: false,
                didOpen: function () {
                    Swal.showLoading();
                }
            });
        },

        /**
         * Cierra el modal de carga si está visible.
         * Úsalo solo en rutas que NO muestran otro Swal (ej. catch silencioso).
         */
        ocultar: function () {
            if (typeof Swal === 'undefined') return;
            if (Swal.isVisible()) {
                Swal.close();
            }
        },

        /**
         * `fetch` con límite de espera. Idéntico a fetch salvo que, pasado `limiteMs`,
         * aborta la petición y rechaza la promesa con un error marcado.
         *
         * El rechazo llega al .catch() que el formulario ya tiene, así que el modal se
         * cierra por el camino de siempre; lo único que cambia es el texto, y de eso se
         * encarga `avisoDeFallo`. Si el navegador no tuviera AbortController, se delega
         * en el fetch normal: mejor sin límite que sin envío.
         *
         * @param {string} url
         * @param {Object} [opciones] Las mismas de fetch (se copian, no se mutan).
         * @param {number} [limiteMs] Por defecto LIMITE_ENVIO_MS.
         * @returns {Promise<Response>}
         */
        fetchLimitado: function (url, opciones, limiteMs) {
            if (typeof AbortController === 'undefined') {
                return fetch(url, opciones);
            }

            var control = new AbortController();
            var temporizador = setTimeout(function () { control.abort(); }, limiteMs || LIMITE_ENVIO_MS);

            var conSenal = {};
            for (var clave in (opciones || {})) {
                if (Object.prototype.hasOwnProperty.call(opciones, clave)) {
                    conSenal[clave] = opciones[clave];
                }
            }
            conSenal.signal = control.signal;

            return fetch(url, conSenal).then(function (respuesta) {
                clearTimeout(temporizador);
                return respuesta;
            }, function (error) {
                clearTimeout(temporizador);
                // AbortError es el corte por tiempo; cualquier otro fallo (red caída, DNS)
                // se propaga tal cual para que el formulario lo trate como siempre.
                if (error && error.name === 'AbortError') {
                    var porTiempo = new Error(TEXTO_TIEMPO);
                    porTiempo.esTiempoAgotado = true;
                    throw porTiempo;
                }
                throw error;
            });
        },

        /**
         * Traduce el error de un .catch() al aviso que toca mostrar.
         *
         * Existe para que cada formulario no tenga que distinguir a mano el corte por
         * tiempo del fallo de red: son casos OPUESTOS para el usuario. Ante un fallo de
         * red la solicitud no salió y reintentar es lo correcto; ante un corte por tiempo
         * puede haber salido y reintentar duplicaría.
         *
         * @param {*} error El valor recibido en el .catch().
         * @param {string} textoPorDefecto Aviso que el formulario mostraba antes.
         * @returns {{titulo: (string|null), texto: string, esTiempoAgotado: boolean}}
         *          `titulo` es null salvo en el corte por tiempo: el formulario conserva
         *          entonces el suyo (`aviso.titulo || 'Error de red'`).
         */
        avisoDeFallo: function (error, textoPorDefecto) {
            if (error && error.esTiempoAgotado) {
                return { titulo: TITULO_TIEMPO, texto: TEXTO_TIEMPO, esTiempoAgotado: true };
            }
            return { titulo: null, texto: textoPorDefecto, esTiempoAgotado: false };
        }
    };

    global.LoadingUI = LoadingUI;
})(window);
