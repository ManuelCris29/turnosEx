// Validación visual: no permitir enviar ambos bloques llenos en crear usuario+empleado
document.addEventListener('DOMContentLoaded', function() {
    const form = document.getElementById('usuario-empleado-form');
    if (!form) return;

    form.addEventListener('submit', function(e) {
        const usuarioExistenteEl = document.getElementById('id_usuario_existente');
        const usernameEl = document.getElementById('id_username');
        const passwordEl = document.getElementById('id_password');
        const emailEl = document.getElementById('id_email');

        const usuarioExistente = usuarioExistenteEl ? usuarioExistenteEl.value : '';
        const username = usernameEl ? usernameEl.value : '';
        const password = passwordEl ? passwordEl.value : '';
        const email = emailEl ? emailEl.value : '';

        // Caso 1: se selecciona usuario existente y además se diligencian campos de usuario nuevo
        if (usuarioExistente && (username || password || email)) {
            alert('Por favor, selecciona un usuario existente O llena los campos de usuario nuevo, pero no ambos.');
            e.preventDefault();
            return;
        }

        // Caso 2: no hay usuario existente y faltan campos de usuario nuevo
        if (!usuarioExistente && (!username || !password || !email)) {
            alert('Si no seleccionas un usuario existente, debes llenar todos los campos de usuario nuevo.');
            e.preventDefault();
            return;
        }
    });
});


