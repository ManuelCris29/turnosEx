/**
 * Comentario obligatorio: una sola forma de pedirlo en toda la aplicación.
 *
 * La aplicación marca los campos obligatorios con un asterisco rojo detrás de la etiqueta
 * (unas cuarenta veces entre los formularios de solicitud, sanciones y pagos). Las ventanas
 * de SweetAlert no podían seguir esa convención porque `inputLabel` se inserta como texto
 * plano, así que decían "(obligatorio)" y al usuario le llegaban dos convenciones para el
 * mismo requisito. Aquí se pinta el asterisco a mano sobre el label ya renderizado.
 *
 * `window.ComentarioObligatorio.swal({...})` devuelve la misma promesa que `Swal.fire`.
 */
(function (global) {
    'use strict';

    // Respaldo único para cuando quien llama no pasa `error`. Vive aquí y no repetido en cada
    // fichero: el texto bueno lo sirve el servidor, este solo evita un aviso vacío.
    const RESPALDO = 'Este campo es obligatorio.';

    /** Etiqueta + asterisco rojo, igual que en las plantillas. */
    function marcarObligatorio(etiqueta) {
        // Acotado al diálogo activo: con `document.querySelector` se marcaba el primer label
        // del documento, que no tiene por qué ser el de esta ventana.
        const popup = (typeof Swal !== 'undefined' && Swal.getPopup && Swal.getPopup()) || document;
        const label = popup.querySelector('.swal2-input-label');
        if (!label) return;
        label.textContent = etiqueta;
        const asterisco = document.createElement('span');
        asterisco.className = 'text-danger';
        asterisco.textContent = ' *';
        label.appendChild(asterisco);
    }

    /**
     * Abre un Swal con un textarea obligatorio.
     *
     * Opciones propias: `etiqueta` (sin el asterisco, se añade solo), `error` (el aviso, que
     * debe ser el mismo literal que devuelve el servidor) y `marcador` para el placeholder.
     * El resto se pasa tal cual a SweetAlert.
     */
    function swal(opciones) {
        const etiqueta = opciones.etiqueta || 'Comentario';
        const error = opciones.error || RESPALDO;
        const marcador = opciones.marcador || '';

        const config = Object.assign({}, opciones);
        delete config.etiqueta;
        delete config.error;
        delete config.marcador;

        return Swal.fire(Object.assign(config, {
            input: 'textarea',
            inputLabel: etiqueta,
            inputPlaceholder: marcador,
            inputAttributes: { 'aria-required': 'true', maxlength: 1000 },
            inputValidator: function (valor) {
                return (valor || '').trim() ? undefined : error;
            },
            didOpen: function () {
                marcarObligatorio(etiqueta);
                if (typeof opciones.didOpen === 'function') opciones.didOpen();
            }
        }));
    }

    global.ComentarioObligatorio = {
        swal: swal,
        marcarObligatorio: marcarObligatorio,
        RESPALDO: RESPALDO
    };
})(window);
