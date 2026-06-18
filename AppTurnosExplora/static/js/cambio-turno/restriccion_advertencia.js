/**
 * Advertencia (no bloqueo) por restricción médica.
 *
 * El backend, al procesar una solicitud, puede devolver:
 *   { success: false, code: 'advertencia_restriccion', restricciones: [{explorador, tipo, nota}] }
 *
 * Esto NO es un error: significa que hay una restricción médica vigente y se debe avisar
 * al usuario con la nota, dejándolo continuar. Al confirmar, se reenvía la solicitud con
 * el flag 'confirmar_restriccion=1'.
 *
 * Uso en el manejador de respuesta de cada formulario:
 *   if (window.RestriccionAdvertencia &&
 *       RestriccionAdvertencia.manejar(data, function () { reenviar(true); }, onCancelar)) {
 *       return;  // ya se mostró el aviso
 *   }
 */
window.RestriccionAdvertencia = (function () {
    function mostrar(restricciones, onContinuar, onCancelar) {
        var items = (restricciones || []).map(function (r) {
            return '<li class="mb-1"><strong>' + r.explorador + '</strong> — <em>' + r.tipo + '</em>: ' + r.nota + '</li>';
        }).join('');
        var html = '<p>Ten cuidado: hay una <strong>restricción médica</strong> vigente en las fechas:</p>' +
                   '<ul class="text-left">' + items + '</ul>' +
                   '<p class="mt-2">¿Deseas continuar de todos modos?</p>';
        if (window.Swal) {
            Swal.fire({
                icon: 'warning', title: 'Restricción médica', html: html,
                showCancelButton: true, confirmButtonText: 'Continuar de todos modos',
                cancelButtonText: 'Cancelar', confirmButtonColor: '#d97706',
            }).then(function (res) {
                if (res.isConfirmed) { if (onContinuar) onContinuar(); }
                else if (onCancelar) onCancelar();
            });
        } else {
            if (confirm('Hay una restricción médica vigente. ¿Continuar de todos modos?')) {
                if (onContinuar) onContinuar();
            } else if (onCancelar) onCancelar();
        }
    }

    // Devuelve true si manejó la advertencia (mostró el aviso). reenviar() se llama al confirmar.
    function manejar(data, reenviar, onCancelar) {
        if (data && data.code === 'advertencia_restriccion') {
            mostrar(data.restricciones, reenviar, onCancelar);
            return true;
        }
        return false;
    }

    return { mostrar: mostrar, manejar: manejar };
})();
