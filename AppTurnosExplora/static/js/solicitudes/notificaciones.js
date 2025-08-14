function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return null;
}

function getCsrfToken() {
    return getCookie('csrftoken');
}

window.marcarComoLeida = function (notificacionId) {
    const formData = new FormData();
    fetch(`/solicitudes/notificaciones/${notificacionId}/marcar-leida/`, {
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
            const notificacionItem = document.getElementById(`notificacion-${notificacionId}`);
            if (notificacionItem) {
                notificacionItem.classList.remove('no-leida');
                const boton = notificacionItem.querySelector('.btn-marcar-leida');
                if (boton) boton.outerHTML = '<span class="text-muted"><i class="fas fa-check-circle"></i> Leída</span>';
            }

            Swal.fire({
                icon: 'success',
                title: '¡Marcada como leída!',
                text: 'La notificación ha sido marcada como leída',
                timer: 2000,
                timerProgressBar: true,
                showConfirmButton: false,
                position: 'top-end',
                toast: true
            });

            const badge = document.querySelector('.badge-warning.right');
            if (badge) {
                const current = parseInt(badge.textContent);
                if (!Number.isNaN(current)) {
                    if (current > 1) badge.textContent = current - 1;
                    else badge.style.display = 'none';
                }
            }
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: data.message || 'Error al marcar como leída',
                timer: 3000,
                timerProgressBar: true,
                showConfirmButton: false
            });
        }
    })
    .catch(() => {
        Swal.fire({
            icon: 'error',
            title: 'Error',
            text: 'Error al marcar como leída',
            timer: 3000,
            timerProgressBar: true,
            showConfirmButton: false
        });
    });
}


