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
 */
(function (global) {
    'use strict';

    var LoadingUI = {
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
        }
    };

    global.LoadingUI = LoadingUI;
})(window);
