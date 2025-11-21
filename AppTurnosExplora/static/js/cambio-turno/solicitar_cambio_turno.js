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
    const advertenciaCambioAprobado = document.getElementById('advertencia_cambio_aprobado');
    const mensajeAdvertencia = document.getElementById('mensaje_advertencia');
    const detallesCambioAprobado = document.getElementById('detalles_cambio_aprobado');
    const indicadorFestivo = document.getElementById('indicador_festivo');
    const descripcionFestivo = document.getElementById('descripcion_festivo');
    const indicadorMantenimiento = document.getElementById('indicador_mantenimiento');
    const descripcionMantenimiento = document.getElementById('descripcion_mantenimiento');
    
    // Instancia de Flatpickr (se inicializará con el módulo común)
    let flatpickrInstance = null;
    
    // Variable para rastrear si la fecha seleccionada es día de mantenimiento
    let esDiaMantenimiento = false;

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
        const fecha = fechaInput.value;
        
        // Validar que no sea día de mantenimiento antes de enviar
        if (fecha && window.DatepickerFestivos && window.DatepickerFestivos.cargarDiasMantenimiento) {
            const año = parseInt(fecha.split('-')[0]);
            window.DatepickerFestivos.cargarDiasMantenimiento(año).then(mantenimiento => {
                if (mantenimiento.has(fecha)) {
                    // Es día de mantenimiento, bloquear envío
                    Swal.fire({
                        icon: 'error',
                        title: 'Día de Mantenimiento',
                        text: 'No se pueden realizar cambios de turno en días de mantenimiento. Por favor, selecciona otra fecha.',
                        confirmButtonText: 'Entendido'
                    });
                    return;
                } else {
                    // No es día de mantenimiento, proceder con el envío
                    procederConEnvio(form);
                }
            }).catch(error => {
                console.error('Error verificando día de mantenimiento:', error);
                // En caso de error, proceder con el envío (la validación backend lo manejará)
                procederConEnvio(form);
            });
        } else {
            // Si no se puede verificar, proceder con el envío (la validación backend lo manejará)
            procederConEnvio(form);
        }
    }
    
    // Función auxiliar para proceder con el envío del formulario
    function procederConEnvio(form) {
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
                // Si el error es sobre día de mantenimiento, destacarlo
                const esErrorMantenimiento = data.error && data.error.toLowerCase().includes('mantenimiento');
                
                Swal.fire({
                    icon: 'error',
                    title: esErrorMantenimiento ? 'Día de Mantenimiento' : 'Error al enviar solicitud',
                    text: data.error || 'Ocurrió un error al procesar la solicitud',
                    confirmButtonText: 'Entendido',
                    timer: esErrorMantenimiento ? 6000 : 4000,
                    timerProgressBar: true,
                    showConfirmButton: true,
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

    // Event listener para el formulario
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            enviarSolicitud();
        });
    }

    // Función para verificar si una fecha es festivo (usa módulo común)
    function verificarDiaFestivo(fecha) {
        if (!fecha || !indicadorFestivo || !descripcionFestivo) {
            return;
        }
        // Usar función del módulo común
        if (window.DatepickerFestivos) {
            window.DatepickerFestivos.verificarDiaFestivo(fecha, indicadorFestivo, descripcionFestivo);
        }
    }
    
    // FASE 2.5: Función para verificar si ya existe un cambio aprobado
    function verificarCambioAprobado() {
        const fecha = fechaInput.value;
        if (!fecha) {
            // Ocultar advertencia si no hay fecha
            if (advertenciaCambioAprobado) {
                advertenciaCambioAprobado.style.display = 'none';
            }
            return;
        }

        fetch(`/solicitudes/obtener-cambio-aprobado/?fecha=${fecha}`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success && data.data && data.data.tiene_cambio_aprobado) {
                // Mostrar advertencia
                if (advertenciaCambioAprobado) {
                    advertenciaCambioAprobado.style.display = 'block';
                }
                
                // Mostrar mensaje
                if (mensajeAdvertencia) {
                    mensajeAdvertencia.textContent = data.data.mensaje;
                }
                
                // Mostrar detalles del cambio
                if (detallesCambioAprobado && data.data.informacion_cambio) {
                    const info = data.data.informacion_cambio;
                    let detallesHTML = '<hr class="my-2">';
                    detallesHTML += '<div class="small">';
                    detallesHTML += '<strong>Información del cambio actual:</strong><br>';
                    detallesHTML += `<i class="fas fa-clock mr-1"></i>Jornada actual: <strong>${info.jornada_actual}</strong><br>`;
                    if (info.companero_nombre) {
                        detallesHTML += `<i class="fas fa-user-friends mr-1"></i>Compañero: <strong>${info.companero_nombre}</strong><br>`;
                    }
                    if (info.fecha_aprobacion && info.fecha_aprobacion !== 'N/A') {
                        detallesHTML += `<i class="fas fa-calendar-check mr-1"></i>Aprobado el: <strong>${info.fecha_aprobacion}</strong>`;
                    }
                    if (info.solicitud_id) {
                        detallesHTML += `<br><i class="fas fa-hashtag mr-1"></i>Solicitud ID: <strong>#${info.solicitud_id}</strong>`;
                    }
                    detallesHTML += '</div>';
                    detallesCambioAprobado.innerHTML = detallesHTML;
                }
            } else {
                // Ocultar advertencia si no hay cambio aprobado
                if (advertenciaCambioAprobado) {
                    advertenciaCambioAprobado.style.display = 'none';
                }
            }
        })
        .catch(error => {
            console.error('Error al verificar cambio aprobado:', error);
            // En caso de error, ocultar advertencia
            if (advertenciaCambioAprobado) {
                advertenciaCambioAprobado.style.display = 'none';
            }
        });
    }

    // Inicializar Flatpickr con festivos marcados (usa módulo común)
    function inicializarDatepicker() {
        if (!fechaInput || !window.DatepickerFestivos) {
            console.error('DatepickerFestivos no está disponible');
            return;
        }
        
        // Usar módulo común para inicializar datepicker
        window.DatepickerFestivos.inicializar({
            input: fechaInput,
            indicadorFestivo: indicadorFestivo,
            descripcionFestivo: descripcionFestivo,
            onDateChange: function(fecha) {
                // Verificar si es día de mantenimiento
                if (fecha && window.DatepickerFestivos && window.DatepickerFestivos.verificarDiaMantenimiento) {
                    window.DatepickerFestivos.verificarDiaMantenimiento(
                        fecha, 
                        indicadorMantenimiento, 
                        descripcionMantenimiento
                    ).then(esMantenimiento => {
                        esDiaMantenimiento = esMantenimiento;
                    });
                }
                
                // Callbacks personalizados cuando cambia la fecha
                verificarCambioAprobado();
                actualizarEmpleadosDisponibles();
                cargarInformacionSolicitante();
            }
        }).then(instance => {
            flatpickrInstance = instance;
        }).catch(error => {
            console.error('Error inicializando datepicker:', error);
        });
    }
    
    // Al cargar la página, inicializar datepicker y cargar info
    if (fechaInput) {
        inicializarDatepicker();
        
        // Si hay fecha seleccionada inicialmente, cargar info
        if (fechaInput.value) {
            // Verificar si es día de mantenimiento
            if (window.DatepickerFestivos && window.DatepickerFestivos.verificarDiaMantenimiento) {
                window.DatepickerFestivos.verificarDiaMantenimiento(
                    fechaInput.value,
                    indicadorMantenimiento,
                    descripcionMantenimiento
                ).then(esMantenimiento => {
                    esDiaMantenimiento = esMantenimiento;
                });
            }
            cargarInformacionSolicitante();
            verificarCambioAprobado();
        }
    }
}); 