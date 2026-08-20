/**
 * Comentario obligatorio en las acciones de permisos especiales.
 *
 * Aprobar, rechazar y cancelar un permiso mueven turnos reales, y hasta ahora se
 * hacían con un simple confirm(): quien lo recibía no sabía por qué. El backend ya
 * guardaba `comentario_supervisor` / `cancelacion_motivo`, pero el formulario nunca
 * los enviaba. Aquí se pide el texto, se valida y se inyecta como campo oculto.
 */
(function () {
    document.querySelectorAll('form[data-comentario-label]').forEach(function (form) {
        form.addEventListener('submit', function (ev) {
            if (form.dataset.comentarioListo === '1') return;   // ya lo pidió: deja pasar
            ev.preventDefault();

            const label = form.dataset.comentarioLabel;
            const campo = form.dataset.comentarioCampo || 'comentario';
            const titulo = form.dataset.comentarioTitulo || '¿Confirmas la acción?';
            const texto = form.dataset.comentarioTexto || '';
            // Mismo literal que devuelve el servidor: dos textos distintos para la misma
            // falta hacen dudar al usuario de si el problema es otro.
            const error = form.dataset.comentarioError || ComentarioObligatorio.RESPALDO;

            const enviar = function (valor) {
                const oculto = document.createElement('input');
                oculto.type = 'hidden';
                oculto.name = campo;
                oculto.value = valor;
                form.appendChild(oculto);
                form.dataset.comentarioListo = '1';
                form.submit();
            };

            if (window.Swal && window.ComentarioObligatorio) {
                // El helper común pone la etiqueta con el asterisco rojo, igual que los
                // formularios de la aplicación, y valida con el literal del servidor.
                ComentarioObligatorio.swal({
                    title: titulo,
                    html: texto,
                    icon: 'question',
                    etiqueta: label,
                    error: error,
                    showCancelButton: true,
                    confirmButtonText: 'Confirmar',
                    cancelButtonText: 'Volver'
                }).then(function (r) {
                    if (r.isConfirmed) enviar((r.value || '').trim());
                });
            } else {
                // Sin Swal: prompt hasta que escriba algo o cancele.
                const v = (window.prompt(label + ' *', '') || '').trim();
                if (v) enviar(v);
                else window.alert(error);
            }
        });
    });
})();
