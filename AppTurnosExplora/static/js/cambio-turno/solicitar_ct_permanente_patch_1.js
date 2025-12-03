// Función para cargar empleados disponibles
function cargarEmpleadosDisponibles(fecha) {
    const tipoSolicitudId = document.getElementById('tipo_solicitud_id').value;
    const fechaFin = document.getElementById('fecha_fin').value;
    const diasSeleccionados = obtenerDiasSeleccionados();
    const diasJSON = JSON.stringify(diasSeleccionados);
    
    console.log('Cargando empleados para fecha:', fecha, 'tipo:', tipoSolicitudId, 'fin:', fechaFin);
    
    // Construir URL con parámetros
    let url = `/solicitudes/obtener-empleados-disponibles/?fecha=${fecha}&tipo_solicitud_id=${tipoSolicitudId}`;
    if (fechaFin) {
        url += `&fecha_fin=${fechaFin}&dias_seleccionados=${encodeURIComponent(diasJSON)}`;
    }
    
    fetch(url)
        .then(response => {
            console.log('Respuesta recibida:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('Datos recibidos:', data);
            const select = document.getElementById('empleado_receptor');
            select.innerHTML = '<option value="">Selecciona un compañero...</option>';
            
            if (data.empleados && data.empleados.length > 0) {
                data.empleados.forEach(empleado => {
                    const option = document.createElement('option');
                    option.value = empleado.id;
                    
                    // Texto base
                    let texto = `${empleado.nombre} ${empleado.apellido}`;
                    
                    // Añadir compatibilidad si existe
                    if (empleado.compatibilidad_percent !== undefined) {
                        texto += ` - Compatibilidad: ${empleado.compatibilidad_percent}%`;
                        
                        // Guardar datos en atributos data para uso posterior
                        option.setAttribute('data-compatibilidad', empleado.compatibilidad_percent);
                        option.setAttribute('data-dias-compatibles', JSON.stringify(empleado.dias_compatibles || []));
                        option.setAttribute('data-dias-incompatibles', JSON.stringify(empleado.dias_incompatibles || []));
                        option.setAttribute('data-total-dias', empleado.total_dias_rango || 0);
                        
                        // Estilo visual simple en el texto (algunos navegadores no soportan estilo en option)
                        if (empleado.compatibilidad_percent === 100) {
                            texto += ' ✅';
                        } else if (empleado.compatibilidad_percent >= 50) {
                            texto += ' ⚠️';
                        } else {
                            texto += ' ❌';
                        }
                    } else if (empleado.jornada) {
                        texto += ` (${empleado.jornada})`;
                    }
                    
                    option.textContent = texto;
                    select.appendChild(option);
                });
                console.log('Empleados cargados:', data.empleados.length);
            } else {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No hay compañeros disponibles con jornada contraria';
                select.appendChild(option);
                console.log('No hay empleados disponibles');
            }
        })
        .catch(error => {
            console.error('Error cargando empleados:', error);
            const select = document.getElementById('empleado_receptor');
            select.innerHTML = '<option value="">Error cargando empleados</option>';
        });
}

