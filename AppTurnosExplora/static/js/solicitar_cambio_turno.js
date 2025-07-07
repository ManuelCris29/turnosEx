document.addEventListener('DOMContentLoaded', function() {
    const fechaInput = document.getElementById('fecha_solicitud');
    const empleadoSelect = document.getElementById('empleado_receptor');
    const form = document.getElementById('cambioTurnoForm');

    // Función para actualizar la lista de empleados disponibles
    function actualizarEmpleadosDisponibles() {
        const fecha = fechaInput.value;
        if (!fecha) return;

        // Mostrar indicador de carga
        empleadoSelect.innerHTML = '<option value="">Cargando compañeros...</option>';
        empleadoSelect.disabled = true;

        // Realizar petición AJAX
        fetch(`/solicitudes/obtener-empleados-disponibles/?fecha=${fecha}`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            empleadoSelect.innerHTML = '<option value="">Selecciona un compañero...</option>';
            
            if (data.empleados && data.empleados.length > 0) {
                data.empleados.forEach(empleado => {
                    const option = document.createElement('option');
                    option.value = empleado.id;
                    option.textContent = `${empleado.nombre} ${empleado.apellido} (${empleado.jornada})`;
                    empleadoSelect.appendChild(option);
                });
            } else {
                empleadoSelect.innerHTML = '<option value="">No hay compañeros disponibles para esta fecha</option>';
            }
            
            empleadoSelect.disabled = false;
        })
        .catch(error => {
            console.error('Error al cargar empleados:', error);
            empleadoSelect.innerHTML = '<option value="">Error al cargar compañeros</option>';
            empleadoSelect.disabled = false;
        });
    }

    // Event listener para cambio de fecha
    if (fechaInput) {
        fechaInput.addEventListener('change', actualizarEmpleadosDisponibles);
    }

    // Validación del formulario
    if (form) {
        form.addEventListener('submit', function(e) {
            const fecha = fechaInput.value;
            const empleado = empleadoSelect.value;

            if (!fecha) {
                e.preventDefault();
                alert('Por favor selecciona una fecha');
                return;
            }

            if (!empleado) {
                e.preventDefault();
                alert('Por favor selecciona un compañero');
                return;
            }
        });
    }
}); 