// Helpers CSRF
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

function getCsrfToken() {
    return getCookie('csrftoken');
}

// Estado actual para acciones
let solicitudActual = null;
let accionActual = null;
let rolActual = null;

// Exponer funciones globales usadas por botones inline
window.aprobarSolicitudReceptor = function (solicitudId) {
    solicitudActual = solicitudId;
    accionActual = 'aprobar';
    rolActual = 'receptor';
    $('#accionModalTitle').text('Aprobar Solicitud como Receptor');
    $('#accionSolicitudModal').modal('show');
};

window.rechazarSolicitudReceptor = function (solicitudId) {
    solicitudActual = solicitudId;
    accionActual = 'rechazar';
    rolActual = 'receptor';
    $('#accionModalTitle').text('Rechazar Solicitud como Receptor');
    $('#accionSolicitudModal').modal('show');
};

window.aprobarSolicitudSupervisor = function (solicitudId) {
    solicitudActual = solicitudId;
    accionActual = 'aprobar';
    rolActual = 'supervisor';
    $('#accionModalTitle').text('Aprobar Solicitud como Supervisor');
    $('#accionSolicitudModal').modal('show');
};

window.rechazarSolicitudSupervisor = function (solicitudId) {
    solicitudActual = solicitudId;
    accionActual = 'rechazar';
    rolActual = 'supervisor';
    $('#accionModalTitle').text('Rechazar Solicitud como Supervisor');
    $('#accionSolicitudModal').modal('show');
};

window.cancelarSolicitud = function (solicitudId) {
    Swal.fire({
        title: '¿Cancelar solicitud?',
        text: 'Esta acción cancelará la solicitud. ¿Estás seguro?',
        icon: 'warning',
        showCancelButton: true,
        confirmButtonColor: '#ffc107',
        cancelButtonColor: '#6c757d',
        confirmButtonText: 'Sí, cancelar',
        cancelButtonText: 'No, mantener'
    }).then((result) => {
        if (result.isConfirmed) {
            const formData = new FormData();
            fetch(`/solicitudes/cancelar-solicitud/${solicitudId}/`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': getCsrfToken(),
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        icon: 'success',
                        title: '¡Solicitud cancelada!',
                        text: data.message,
                        timer: 3000,
                        timerProgressBar: true,
                        showConfirmButton: false,
                        position: 'top-end',
                        toast: true
                    }).then(() => {
                        location.reload();
                    });
                } else {
                    Swal.fire({
                        icon: 'error',
                        title: 'Error',
                        text: data.message,
                        timer: 4000,
                        timerProgressBar: true,
                        showConfirmButton: false
                    });
                }
            })
            .catch(() => {
                Swal.fire({
                    icon: 'error',
                    title: 'Error de conexión',
                    text: 'No se pudo cancelar la solicitud. Inténtalo de nuevo.',
                    timer: 5000,
                    timerProgressBar: true,
                    showConfirmButton: true,
                    confirmButtonText: 'Reintentar'
                });
            });
        }
    });
};

window.verDetalleSolicitud = function (_solicitudId) {
    $('#detalleSolicitudModal').modal('show');
};

// Confirmar acción del modal
document.addEventListener('DOMContentLoaded', function () {
    const confirmarBtn = document.getElementById('confirmarAccion');
    if (!confirmarBtn) return;

    confirmarBtn.addEventListener('click', function () {
        if (!solicitudActual || !accionActual) return;

        const comentario = document.getElementById('comentario_respuesta')?.value || '';
        const formData = new FormData();
        formData.append('comentario', comentario);

        let url = '';
        if (rolActual === 'receptor') {
            if (accionActual === 'aprobar') {
                url = `/solicitudes/aprobar-solicitud-receptor/${solicitudActual}/`;
            } else if (accionActual === 'rechazar') {
                url = `/solicitudes/rechazar-solicitud-receptor/${solicitudActual}/`;
            }
        } else if (rolActual === 'supervisor') {
            if (accionActual === 'aprobar') {
                url = `/solicitudes/aprobar-solicitud/${solicitudActual}/`;
            } else if (accionActual === 'rechazar') {
                url = `/solicitudes/rechazar-solicitud/${solicitudActual}/`;
            }
        }

        fetch(url, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRFToken': getCsrfToken(),
            }
        })
        .then(response => response.json())
        .then(data => {
            $('#accionSolicitudModal').modal('hide');
            const comentarioField = document.getElementById('comentario_respuesta');
            if (comentarioField) comentarioField.value = '';

            if (data.success) {
                Swal.fire({
                    icon: 'success',
                    title: '¡Acción completada!',
                    text: data.message,
                    timer: 3000,
                    timerProgressBar: true,
                    showConfirmButton: false,
                    position: 'top-end',
                    toast: true
                }).then(() => {
                    location.reload();
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: data.message,
                    timer: 4000,
                    timerProgressBar: true,
                    showConfirmButton: false
                });
            }
        })
        .catch(() => {
            $('#accionSolicitudModal').modal('hide');
            Swal.fire({
                icon: 'error',
                title: 'Error de conexión',
                text: 'No se pudo completar la acción. Inténtalo de nuevo.',
                timer: 5000,
                timerProgressBar: true,
                showConfirmButton: true,
                confirmButtonText: 'Reintentar'
            });
        });
    });
});


