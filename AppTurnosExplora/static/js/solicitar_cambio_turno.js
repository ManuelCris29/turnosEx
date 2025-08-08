document.addEventListener('DOMContentLoaded', function() {
    const fechaInput = document.getElementById('fecha_solicitud');
    const empleadoSelect = document.getElementById('empleado_receptor');
    const form = document.getElementById('cambioTurnoForm');
    const turnoInfo = document.getElementById('turno_info');
    const salasInfo = document.getElementById('salas_info');
    const turnoDetalles = document.getElementById('turno_detalles');
    const salasDetalles = document.getElementById('salas_detalles');
    const turnoSolicitanteInfo = document.getElementById('turno_solicitante_info');
    const turnoSolicitanteDetalles = document.getElementById('turno_solicitante_detalles');
    const salasSolicitanteDetalles = document.getElementById('salas_solicitante_detalles');

    // Función para actualizar la lista de empleados disponibles
    function actualizarEmpleadosDisponibles() {
        const fecha = fechaInput.value;
        if (!fecha) return;

        // Obtener el tipo de solicitud desde la URL o un elemento oculto
        const urlParams = new URLSearchParams(window.location.search);
        const tipoSolicitudId = urlParams.get('tipo_id') || 
                               document.getElementById('tipo_solicitud_id')?.value || 
                               window.tipoSolicitudId;

        console.log('DEBUG JS:', {
            fecha: fecha,
            tipoSolicitudId: tipoSolicitudId,
            urlParams: window.location.search,
            hiddenElement: document.getElementById('tipo_solicitud_id')?.value
        });

        // Mostrar indicador de carga
        empleadoSelect.innerHTML = '<option value="">Cargando compañeros...</option>';
        empleadoSelect.disabled = true;

        // Ocultar información de turno
        turnoInfo.style.display = 'none';
        // Eliminado: salasInfo.style.display = 'none';

        // Construir URL con parámetros
        let url = `/solicitudes/obtener-empleados-disponibles/?fecha=${fecha}`;
        if (tipoSolicitudId) {
            url += `&tipo_solicitud_id=${tipoSolicitudId}`;
        }

        console.log('DEBUG JS: URL final:', url);

        // Realizar petición AJAX
        fetch(url, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            console.log('DEBUG JS: Respuesta del servidor:', data);
            empleadoSelect.innerHTML = '<option value="">Selecciona un compañero...</option>';
            if (data.empleados && data.empleados.length > 0) {
                data.empleados.forEach(empleado => {
                    const option = document.createElement('option');
                    option.value = empleado.id;
                    option.textContent = `${empleado.nombre} ${empleado.apellido}`;
                    empleadoSelect.appendChild(option);
                });
            } else {
                // Mensaje dinámico según el tipo de solicitud
                const mensaje = tipoSolicitudId && window.location.pathname.includes('cambio') 
                    ? 'No hay compañeros de jornada contraria disponibles para esta fecha'
                    : 'No hay compañeros disponibles para esta fecha';
                empleadoSelect.innerHTML = `<option value="">${mensaje}</option>`;
            }
            empleadoSelect.disabled = false;
        })
        .catch(error => {
            console.error('Error al cargar empleados:', error);
            empleadoSelect.innerHTML = '<option value="">Error al cargar compañeros</option>';
            empleadoSelect.disabled = false;
        });
    }

    // Función reutilizable para renderizar turno y salas de manera ordenada
    function renderTurnoYSalas(turno, detallesElem, salasElem) {
        if (!turno) {
            detallesElem.innerHTML = `
                <div class="card mb-3">
                    <div class="card-body text-center">
                        <i class="fas fa-exclamation-triangle text-warning"></i>
                        <span class="text-muted">No tiene jornada asignada para esta fecha</span>
                    </div>
                </div>
            `;
            salasElem.innerHTML = `
                <div class="card mb-3">
                    <div class="card-body text-center">
                        <i class="fas fa-exclamation-triangle text-warning"></i>
                        <span class="text-muted">No tienes salas asignadas</span>
                    </div>
                </div>
            `;
            return;
        }
        const esJornadaFija = turno.es_turno_virtual;
        const badgeClass = esJornadaFija ? 'badge-info' : 'badge-success';
        const badgeText = esJornadaFija ? 'Jornada Fija' : 'Turno Asignado';
        detallesElem.innerHTML = `
            <div class="card mb-3">
                <div class="card-body">
                    <div class="row align-items-center mb-2">
                        <div class="col-12 col-md-6 mb-2 mb-md-0">
                            <strong>Jornada:</strong> ${turno.jornada || '-'}
                            <span class="badge ${badgeClass} ml-1">${badgeText}</span>
                        </div>
                        <div class="col-12 col-md-6">
                            <strong>Horario:</strong> ${turno.hora_inicio || '-'} - ${turno.hora_fin || '-'}
                        </div>
                    </div>
                </div>
            </div>
        `;
        let salasHtml = `<div class="card mb-3"><div class="card-body"><div class="row"><div class="col-12"><strong>Salas:</strong> `;
        let haySalas = false;
        if (turno.tipo_sala === 'competencia' && turno.salas_competencia && turno.salas_competencia.length > 0) {
            turno.salas_competencia.forEach(sala => {
                salasHtml += `<span class="badge badge-info ml-1">${sala.nombre}</span> `;
            });
            haySalas = true;
        } else if (turno.sala) {
            salasHtml += `<span class="badge badge-info ml-1">${turno.sala}</span>`;
            haySalas = true;
        }
        salasHtml += `</div></div></div></div>`;
        if (haySalas) {
            salasElem.innerHTML = salasHtml;
        } else {
            salasElem.innerHTML = `
                <div class="card mb-3">
                    <div class="card-body text-center">
                        <i class="fas fa-exclamation-triangle text-warning"></i>
                        <span class="text-muted">No tienes salas asignadas</span>
                    </div>
                </div>
            `;
        }
    }

    // Función para cargar información del turno y salas del explorador
    function cargarInformacionExplorador() {
        const fecha = fechaInput.value;
        const exploradorId = empleadoSelect.value;
        if (!fecha || !exploradorId) {
            turnoInfo.style.display = 'none';
            // Eliminado: salasInfo.style.display = 'none';
            return;
        }
        turnoDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        salasDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        turnoInfo.style.display = 'block';
        // Eliminado: salasInfo.style.display = 'block';
        fetch(`/solicitudes/obtener-turno-explorador/?fecha=${fecha}&explorador_id=${exploradorId}`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            renderTurnoYSalas(data.turno, turnoDetalles, salasDetalles);
        })
        .catch(error => {
            console.error('Error al cargar información del explorador:', error);
            turnoDetalles.innerHTML = `
                <div class="text-center text-danger">
                    <i class="fas fa-exclamation-triangle"></i>
                    Error al cargar información
                </div>
            `;
            salasDetalles.innerHTML = `
                <div class="text-center text-danger">
                    <i class="fas fa-exclamation-triangle"></i>
                    Error al cargar información
                </div>
            `;
        });
    }

    // Función para cargar información del turno y salas del solicitante (usuario logueado)
    function cargarInformacionSolicitante() {
        const fecha = fechaInput.value;
        const solicitanteId = window.solicitanteId || null;
        if (!fecha || !solicitanteId) {
            turnoSolicitanteInfo.style.display = 'none';
            return;
        }
        turnoSolicitanteDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        salasSolicitanteDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        turnoSolicitanteInfo.style.display = 'block';
        fetch(`/solicitudes/obtener-turno-explorador/?fecha=${fecha}&explorador_id=${solicitanteId}`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            renderTurnoYSalas(data.turno, turnoSolicitanteDetalles, salasSolicitanteDetalles);
        })
        .catch(error => {
            console.error('Error al cargar información del solicitante:', error);
            turnoSolicitanteDetalles.innerHTML = `
                <div class="text-center text-danger">
                    <i class="fas fa-exclamation-triangle"></i>
                    Error al cargar información
                </div>
            `;
            salasSolicitanteDetalles.innerHTML = `
                <div class="text-center text-danger">
                    <i class="fas fa-exclamation-triangle"></i>
                    Error al cargar información
                </div>
            `;
        });
    }

    // Event listener para cambio de fecha
    if (fechaInput) {
        fechaInput.addEventListener('change', function() {
            actualizarEmpleadosDisponibles();
            cargarInformacionSolicitante();
        });
    }

    // Event listener para cambio de explorador
    if (empleadoSelect) {
        empleadoSelect.addEventListener('change', function() {
            cargarInformacionExplorador();
        });
    }

    // Función para enviar la solicitud
    function enviarSolicitud() {
        const form = document.getElementById('cambioTurnoForm');
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
                    confirmButtonText: 'OK'
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
                    confirmButtonText: 'OK'
                });
            }
        })
        .catch(error => {
            console.error('Error:', error);
            Swal.fire({
                icon: 'error',
                title: 'Error de conexión',
                text: 'No se pudo enviar la solicitud. Inténtalo de nuevo.',
                confirmButtonText: 'OK'
            });
        })
        .finally(() => {
            // Restaurar botón
            submitButton.innerHTML = originalText;
            submitButton.disabled = false;
        });
    }

    // Event listener para el formulario
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            enviarSolicitud();
        });
    }

    // Al cargar la página, si hay fecha seleccionada, cargar info del solicitante
    if (fechaInput && fechaInput.value) {
        cargarInformacionSolicitante();
    }
}); 