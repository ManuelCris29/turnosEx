// Variables globales (se establecen desde el template)
// window.solicitanteId = {{ request.user.empleado.id }};
// window.tipoSolicitud = '{{ tipo_solicitud.nombre }}';

document.addEventListener('DOMContentLoaded', function() {
    // Función para cargar información cuando cambia la fecha de inicio
    document.getElementById('fecha_inicio').addEventListener('change', function() {
        const fechaInicio = this.value;
        if (fechaInicio) {
            cargarJornadaActual(fechaInicio);
            cargarEmpleadosDisponibles(fechaInicio);
        }
    });

    // Cargar datos automáticamente al cargar la página si hay fecha de inicio
    const fechaInicio = document.getElementById('fecha_inicio').value;
    if (fechaInicio) {
        console.log('Cargando datos automáticamente para fecha:', fechaInicio);
        cargarJornadaActual(fechaInicio);
        cargarEmpleadosDisponibles(fechaInicio);
    }

    // Función para cargar información del compañero seleccionado
    document.getElementById('empleado_receptor').addEventListener('change', function() {
        const empleadoId = this.value;
        const fechaInicio = document.getElementById('fecha_inicio').value;
        
        if (empleadoId && fechaInicio) {
            cargarJornadaCompanero(empleadoId, fechaInicio);
            mostrarResumenIntercambio();
        } else {
            document.getElementById('turno_companero_info').style.display = 'none';
            document.getElementById('resumen_intercambio').style.display = 'none';
        }
    });

    // Validación del formulario y envío por AJAX
    document.getElementById('ctPermanenteForm').addEventListener('submit', function(e) {
        e.preventDefault(); // Prevenir envío tradicional del formulario
        
        const fechaInicio = document.getElementById('fecha_inicio').value;
        const fechaFin = document.getElementById('fecha_fin').value;
        const empleadoReceptor = document.getElementById('empleado_receptor').value;
        
        // Validaciones
        if (!fechaInicio) {
            Swal.fire({
                icon: 'warning',
                title: 'Campo requerido',
                text: 'Por favor selecciona una fecha de inicio',
                confirmButtonText: 'Entendido'
            });
            return;
        }
        
        if (!empleadoReceptor) {
            Swal.fire({
                icon: 'warning',
                title: 'Campo requerido',
                text: 'Por favor selecciona un compañero para el intercambio',
                confirmButtonText: 'Entendido'
            });
            return;
        }
        
        if (fechaFin && fechaFin <= fechaInicio) {
            Swal.fire({
                icon: 'warning',
                title: 'Fecha inválida',
                text: 'La fecha de fin debe ser posterior a la fecha de inicio',
                confirmButtonText: 'Entendido'
            });
            return;
        }
        
        // Mostrar confirmación
        Swal.fire({
            title: '¿Confirmar solicitud?',
            text: '¿Estás seguro de que deseas enviar esta solicitud de cambio permanente?',
            icon: 'question',
            showCancelButton: true,
            confirmButtonColor: '#3085d6',
            cancelButtonColor: '#d33',
            confirmButtonText: 'Sí, enviar',
            cancelButtonText: 'Cancelar'
        }).then((result) => {
            if (result.isConfirmed) {
                enviarSolicitudCTPermanente();
            }
        });
    });
});

// Función para cargar empleados disponibles
function cargarEmpleadosDisponibles(fecha) {
    const tipoSolicitudId = document.getElementById('tipo_solicitud_id').value;
    
    console.log('Cargando empleados para fecha:', fecha, 'tipo:', tipoSolicitudId);
    
    fetch(`/solicitudes/obtener-empleados-disponibles/?fecha=${fecha}&tipo_solicitud_id=${tipoSolicitudId}`)
        .then(response => {
            console.log('Respuesta recibida:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('Datos recibidos:', data);
            const select = document.getElementById('empleado_receptor');
            select.innerHTML = '<option value="">Selecciona un compañero con jornada contraria...</option>';
            
            if (data.empleados && data.empleados.length > 0) {
                data.empleados.forEach(empleado => {
                    const option = document.createElement('option');
                    option.value = empleado.id;
                    option.textContent = `${empleado.nombre} ${empleado.apellido} (${empleado.jornada})`;
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

// Función para cargar jornada actual
function cargarJornadaActual(fecha) {
    console.log('Cargando jornada actual para fecha:', fecha, 'empleado:', window.solicitanteId);
    
    fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fecha}`)
        .then(response => {
            console.log('Respuesta jornada actual:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('Datos jornada actual:', data);
            const container = document.getElementById('jornada_actual_detalles');
            const infoDiv = document.getElementById('turno_actual_info');
            
            if (data.turno && data.tiene_turno) {
                const turno = data.turno;
                
                // Construir horario desde hora_inicio y hora_fin
                let horario = 'No definido';
                if (turno.hora_inicio && turno.hora_fin) {
                    horario = `${turno.hora_inicio} - ${turno.hora_fin}`;
                }
                
                // Construir salas desde salas_competencia
                let salasHtml = '';
                if (turno.salas_competencia && turno.salas_competencia.length > 0) {
                    const nombresSalas = turno.salas_competencia.map(sala => sala.nombre);
                    salasHtml = `
                        <div class="col-12 mt-2">
                            <div class="badge badge-success p-2">
                                <strong>Salas:</strong> ${nombresSalas.join(', ')}
                            </div>
                        </div>
                    `;
                }
                
                container.innerHTML = `
                    <div class="row">
                        <div class="col-md-6">
                            <div class="badge badge-info p-2">
                                <strong>Jornada:</strong> ${turno.jornada || 'No asignada'}
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="badge badge-secondary p-2">
                                <strong>Horario:</strong> ${horario}
                            </div>
                        </div>
                        ${salasHtml}
                    </div>
                `;
                infoDiv.style.display = 'block';
            } else {
                container.innerHTML = '<p class="text-muted">No tienes jornada asignada para esta fecha</p>';
                infoDiv.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error cargando jornada actual:', error);
            const container = document.getElementById('jornada_actual_detalles');
            const infoDiv = document.getElementById('turno_actual_info');
            container.innerHTML = '<p class="text-danger">Error cargando información de jornada</p>';
            infoDiv.style.display = 'block';
        });
}

function cargarJornadaCompanero(empleadoId, fecha) {
    console.log('Cargando jornada del compañero:', empleadoId, 'fecha:', fecha);
    
    fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${empleadoId}&fecha=${fecha}`)
        .then(response => {
            console.log('Respuesta jornada compañero:', response.status);
            return response.json();
        })
        .then(data => {
            console.log('Datos jornada compañero:', data);
            const container = document.getElementById('jornada_companero_detalles');
            const infoDiv = document.getElementById('turno_companero_info');
            
            if (data.turno && data.tiene_turno) {
                const turno = data.turno;
                
                // Construir horario desde hora_inicio y hora_fin
                let horario = 'No definido';
                if (turno.hora_inicio && turno.hora_fin) {
                    horario = `${turno.hora_inicio} - ${turno.hora_fin}`;
                }
                
                // Construir salas desde salas_competencia
                let salasHtml = '';
                if (turno.salas_competencia && turno.salas_competencia.length > 0) {
                    const nombresSalas = turno.salas_competencia.map(sala => sala.nombre);
                    salasHtml = `
                        <div class="col-12 mt-2">
                            <div class="badge badge-success p-2">
                                <strong>Salas:</strong> ${nombresSalas.join(', ')}
                            </div>
                        </div>
                    `;
                }
                
                container.innerHTML = `
                    <div class="row">
                        <div class="col-md-6">
                            <div class="badge badge-warning p-2">
                                <strong>Jornada:</strong> ${turno.jornada || 'No asignada'}
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="badge badge-secondary p-2">
                                <strong>Horario:</strong> ${horario}
                            </div>
                        </div>
                        ${salasHtml}
                    </div>
                `;
                infoDiv.style.display = 'block';
            } else {
                container.innerHTML = '<p class="text-muted">El compañero no tiene jornada asignada para esta fecha</p>';
                infoDiv.style.display = 'block';
            }
        })
        .catch(error => {
            console.error('Error cargando jornada del compañero:', error);
            const container = document.getElementById('jornada_companero_detalles');
            const infoDiv = document.getElementById('turno_companero_info');
            container.innerHTML = '<p class="text-danger">Error cargando información del compañero</p>';
            infoDiv.style.display = 'block';
        });
}

function mostrarResumenIntercambio() {
    const fechaInicio = document.getElementById('fecha_inicio').value;
    const fechaFin = document.getElementById('fecha_fin').value;
    const empleadoSelect = document.getElementById('empleado_receptor');
    const empleadoNombre = empleadoSelect.options[empleadoSelect.selectedIndex].text;
    
    if (fechaInicio && empleadoSelect.value) {
        const container = document.getElementById('resumen_detalles');
        const infoDiv = document.getElementById('resumen_intercambio');
        
        let fechaFinText = fechaFin ? ` hasta ${fechaFin}` : ' hasta fin de año';
        
        container.innerHTML = `
            <div class="alert alert-info">
                <h6><i class="fas fa-info-circle mr-2"></i>Resumen del Cambio Permanente:</h6>
                <ul class="mb-0">
                    <li><strong>Período:</strong> Desde ${fechaInicio}${fechaFinText}</li>
                    <li><strong>Compañero:</strong> ${empleadoNombre}</li>
                    <li><strong>Tipo:</strong> Intercambio permanente de jornadas</li>
                    <li><strong>Retorno automático:</strong> Al finalizar el período, ambos volverán a sus jornadas originales</li>
                </ul>
            </div>
        `;
        infoDiv.style.display = 'block';
    }
}

// Función para enviar la solicitud por AJAX
function enviarSolicitudCTPermanente() {
    const form = document.getElementById('ctPermanenteForm');
    const formData = new FormData(form);
    
    // Mostrar indicador de carga
    const submitButton = form.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
    submitButton.disabled = true;

    fetch('/solicitudes/procesar-solicitud/', {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Mostrar mensaje de éxito
            Swal.fire({
                icon: 'success',
                title: '¡Solicitud enviada!',
                text: data.message,
                confirmButtonText: 'OK',
                timer: 4000,
                timerProgressBar: true,
                showConfirmButton: false,
                position: 'top-end',
                toast: true,
                customClass: {
                    popup: 'swal2-toast'
                }
            }).then((result) => {
                // Redirigir a la lista de solicitudes o dashboard
                window.location.href = '/solicitudes/';
            });
        } else {
            // Mostrar error
            Swal.fire({
                icon: 'error',
                title: 'Error al enviar solicitud',
                text: data.error,
                confirmButtonText: 'Entendido',
                timer: 4000,
                timerProgressBar: true,
                showConfirmButton: false,
                position: 'center',
                customClass: {
                    popup: 'swal2-error-popup'
                }
            });
        }
    })
    .catch(error => {
        console.error('Error:', error);
        Swal.fire({
            icon: 'error',
            title: 'Error de conexión',
            text: 'No se pudo enviar la solicitud. Inténtalo de nuevo.',
            confirmButtonText: 'Reintentar',
            timer: 5000,
            timerProgressBar: true,
            showConfirmButton: true,
            position: 'center',
            customClass: {
                popup: 'swal2-error-popup'
            }
        });
    })
    .finally(() => {
        // Restaurar botón
        submitButton.innerHTML = originalText;
        submitButton.disabled = false;
    });
}
