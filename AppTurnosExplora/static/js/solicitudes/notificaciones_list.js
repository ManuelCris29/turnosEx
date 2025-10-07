function marcarComoLeida(notificacionId) {
    const formData = new FormData();
    formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
    
    fetch(`/solicitudes/notificaciones/${notificacionId}/marcar-leida/`, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Marcar visualmente como leída
            const notificacionItem = document.getElementById(`notificacion-${notificacionId}`);
            notificacionItem.classList.remove('no-leida');
            
            // Cambiar el botón por "Leída"
            const boton = notificacionItem.querySelector('.btn-marcar-leida');
            boton.outerHTML = '<span class="text-muted"><i class="fas fa-check-circle"></i> Leída</span>';
            
            // Mostrar notificación de éxito
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
            
            // Actualizar contador en el menú si existe
            const badge = document.querySelector('.badge-warning.right');
            if (badge) {
                const currentCount = parseInt(badge.textContent);
                if (currentCount > 1) {
                    badge.textContent = currentCount - 1;
                } else {
                    badge.style.display = 'none';
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
    .catch(error => {
        console.error('Error:', error);
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