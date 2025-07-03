// Script para habilitar/deshabilitar campos de usuario nuevo según selección de usuario existente
function toggleCamposUsuarioNuevo() {
    const usuarioExistente = document.getElementById('id_usuario_existente');
    const username = document.getElementById('id_username');
    const password = document.getElementById('id_password');
    // El email siempre debe estar habilitado
    if (usuarioExistente && usuarioExistente.value) {
        username.value = '';
        password.value = '';
        username.setAttribute('disabled', 'disabled');
        password.setAttribute('disabled', 'disabled');
    } else {
        username.removeAttribute('disabled');
        password.removeAttribute('disabled');
    }
}

document.addEventListener('DOMContentLoaded', function() {
    const usuarioExistente = document.getElementById('id_usuario_existente');
    if (usuarioExistente) {
        usuarioExistente.addEventListener('change', toggleCamposUsuarioNuevo);
        toggleCamposUsuarioNuevo();
    }
}); 