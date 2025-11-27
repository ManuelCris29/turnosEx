// Variables globales (se establecen desde el template)
// window.solicitanteId = {{ request.user.empleado.id }};
// window.tipoSolicitud = '{{ tipo_solicitud.nombre }}';

// Variables globales para acceso desde todas las funciones
let fechaInicioInput = null;
let fechaFinInput = null;
let indicadorFestivoInicio = null;
let descripcionFestivoInicio = null;
let indicadorFestivoFin = null;
let descripcionFestivoFin = null;
let fechasEspecificasInput = null;
let fechasEspecificasLista = null;
let diasSeleccionadosHidden = null;
let vistaPreviaFechas = null;
let totalDiasSeleccionados = null;
let listaFechasPrevia = null;

// Almacenar días seleccionados
let fechasEspecificasSeleccionadas = [];
let diasSemanaSeleccionados = [];
let flatpickrFechasEspecificas = null;

// Instancias de Flatpickr (se inicializarán con el módulo común)
let flatpickrInicio = null;
let flatpickrFin = null;

document.addEventListener('DOMContentLoaded', function() {
    // Asignar referencias a variables globales
    fechaInicioInput = document.getElementById('fecha_inicio');
    fechaFinInput = document.getElementById('fecha_fin');
    indicadorFestivoInicio = document.getElementById('indicador_festivo_inicio');
    descripcionFestivoInicio = document.getElementById('descripcion_festivo_inicio');
    indicadorFestivoFin = document.getElementById('indicador_festivo_fin');
    descripcionFestivoFin = document.getElementById('descripcion_festivo_fin');
    
    // Variables para selección de días
    fechasEspecificasInput = document.getElementById('fechas_especificas_input');
    fechasEspecificasLista = document.getElementById('fechas_especificas_lista');
    diasSeleccionadosHidden = document.getElementById('dias_seleccionados');
    vistaPreviaFechas = document.getElementById('vista_previa_fechas');
    totalDiasSeleccionados = document.getElementById('total_dias_seleccionados');
    listaFechasPrevia = document.getElementById('lista_fechas_previa');
    
    // Inicializar datepickers con festivos (usa módulo común)
    function inicializarDatepickers() {
        if (!fechaInicioInput || !window.DatepickerFestivos) {
            console.error('DatepickerFestivos no está disponible');
            return;
        }
        
        const fechaMinima = fechaInicioInput.getAttribute('data-min-date') || new Date().toISOString().split('T')[0];
        
        // Inicializar Flatpickr para fecha de inicio
        window.DatepickerFestivos.inicializar({
            input: fechaInicioInput,
            minDate: fechaMinima,
            indicadorFestivo: indicadorFestivoInicio,
            descripcionFestivo: descripcionFestivoInicio,
            onDateChange: function(fecha) {
                // Verificar si es día de mantenimiento
                if (fecha && window.DatepickerFestivos && window.DatepickerFestivos.verificarDiaMantenimiento) {
                    // Crear elementos temporales para el indicador de mantenimiento si no existen
                    let indicadorMant = document.getElementById('indicador_mantenimiento_inicio');
                    let descripcionMant = document.getElementById('descripcion_mantenimiento_inicio');
                    if (!indicadorMant) {
                        // Crear elementos si no existen
                        const divIndicador = document.createElement('div');
                        divIndicador.id = 'indicador_mantenimiento_inicio';
                        divIndicador.className = 'mt-2';
                        divIndicador.style.display = 'none';
                        divIndicador.innerHTML = `
                            <div class="alert alert-warning mb-0 py-2">
                                <i class="fas fa-tools mr-2"></i>
                                <strong>Día de Mantenimiento:</strong> <span id="descripcion_mantenimiento_inicio"></span>
                                <br>
                                <small class="text-danger mt-1 d-block">
                                    <i class="fas fa-exclamation-triangle mr-1"></i>
                                    <strong>No se pueden realizar cambios permanentes en días de mantenimiento.</strong>
                                </small>
                            </div>
                        `;
                        fechaInicioInput.parentElement.appendChild(divIndicador);
                        indicadorMant = divIndicador;
                        descripcionMant = document.getElementById('descripcion_mantenimiento_inicio');
                    }
                    window.DatepickerFestivos.verificarDiaMantenimiento(fecha, indicadorMant, descripcionMant);
                }
                // Disparar evento change para mantener compatibilidad
                fechaInicioInput.dispatchEvent(new Event('change'));
            }
        }).then(instance => {
            flatpickrInicio = instance;
        }).catch(error => {
            console.error('Error inicializando datepicker de inicio:', error);
        });
        
        // Inicializar Flatpickr para fecha de fin
        if (fechaFinInput) {
            window.DatepickerFestivos.inicializar({
                input: fechaFinInput,
                minDate: fechaMinima,
                indicadorFestivo: indicadorFestivoFin,
                descripcionFestivo: descripcionFestivoFin,
                onDateChange: function(fecha) {
                    // Verificar si es día de mantenimiento
                    if (fecha && window.DatepickerFestivos && window.DatepickerFestivos.verificarDiaMantenimiento) {
                        let indicadorMant = document.getElementById('indicador_mantenimiento_fin');
                        let descripcionMant = document.getElementById('descripcion_mantenimiento_fin');
                        if (!indicadorMant) {
                            const divIndicador = document.createElement('div');
                            divIndicador.id = 'indicador_mantenimiento_fin';
                            divIndicador.className = 'mt-2';
                            divIndicador.style.display = 'none';
                            divIndicador.innerHTML = `
                                <div class="alert alert-warning mb-0 py-2">
                                    <i class="fas fa-tools mr-2"></i>
                                    <strong>Día de Mantenimiento:</strong> <span id="descripcion_mantenimiento_fin"></span>
                                    <br>
                                    <small class="text-danger mt-1 d-block">
                                        <i class="fas fa-exclamation-triangle mr-1"></i>
                                        <strong>No se pueden realizar cambios permanentes en días de mantenimiento.</strong>
                                    </small>
                                </div>
                            `;
                            fechaFinInput.parentElement.appendChild(divIndicador);
                            indicadorMant = divIndicador;
                            descripcionMant = document.getElementById('descripcion_mantenimiento_fin');
                        }
                        window.DatepickerFestivos.verificarDiaMantenimiento(fecha, indicadorMant, descripcionMant);
                    }
                    // Actualizar fecha mínima de fin basada en fecha de inicio
                    if (fechaInicioInput.value && flatpickrFin) {
                        flatpickrFin.set('minDate', fechaInicioInput.value);
                    }
                    // Recargar jornada del solicitante cuando cambia la fecha
                    cargarJornadaSolicitante().then(() => {
                        actualizarVistaPrevia();
                    });
                }
            }).then(instance => {
                flatpickrFin = instance;
            }).catch(error => {
                console.error('Error inicializando datepicker de fin:', error);
            });
        }
    }
    
    // Inicializar datepickers
    inicializarDatepickers();
    
    // Inicializar selección de días
    inicializarSeleccionDias();
    
    // Función para cargar información cuando cambia la fecha de inicio
    if (fechaInicioInput) {
        fechaInicioInput.addEventListener('change', function() {
            const fechaInicio = this.value;
            if (fechaInicio) {
                // Actualizar fecha mínima de fin
                if (flatpickrFin) {
                    flatpickrFin.set('minDate', fechaInicio);
                }
                cargarJornadaActual(fechaInicio);
                cargarEmpleadosDisponibles(fechaInicio);
                // Recargar jornada del solicitante para validaciones
                cargarJornadaSolicitante().then(() => {
                    actualizarVistaPrevia();
                });
            }
        });
        
        // También actualizar cuando cambia desde el datepicker (usando el callback del módulo común)
        // Esto se maneja en inicializarDatepickers() con onDateChange
    }

    // Cargar datos automáticamente al cargar la página si hay fecha de inicio
    if (fechaInicioInput && fechaInicioInput.value) {
        console.log('Cargando datos automáticamente para fecha:', fechaInicioInput.value);
        cargarJornadaActual(fechaInicioInput.value);
        cargarEmpleadosDisponibles(fechaInicioInput.value);
        // Cargar jornada del solicitante para validaciones
        cargarJornadaSolicitante();
    }

    // Función para cargar información del compañero seleccionado
    document.getElementById('empleado_receptor').addEventListener('change', function() {
        const empleadoId = this.value;
        const fechaInicio = document.getElementById('fecha_inicio').value;
        
        if (empleadoId && fechaInicio) {
            cargarJornadaCompanero(empleadoId, fechaInicio);
            mostrarResumenIntercambio();
            // Recargar jornada del receptor y actualizar vista previa
            cargarJornadaReceptor().then(() => {
                actualizarVistaPrevia();
            });
        } else {
            document.getElementById('turno_companero_info').style.display = 'none';
            document.getElementById('resumen_intercambio').style.display = 'none';
            cacheJornadaReceptor = null;
            actualizarVistaPrevia();
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
        
        if (!fechaFin) {
            Swal.fire({
                icon: 'warning',
                title: 'Campo requerido',
                text: 'La fecha de fin es obligatoria para cambios permanentes',
                confirmButtonText: 'Entendido'
            });
            return;
        }
        
        if (fechaFin <= fechaInicio) {
            Swal.fire({
                icon: 'warning',
                title: 'Fecha inválida',
                text: 'La fecha de fin debe ser posterior a la fecha de inicio',
                confirmButtonText: 'Entendido'
            });
            return;
        }
        
        // Validar que haya al menos un día seleccionado
        const diasSeleccionados = obtenerDiasSeleccionados();
        if (!diasSeleccionados.fechas_especificas.length && !diasSeleccionados.dias_semana.length) {
            Swal.fire({
                icon: 'warning',
                title: 'Días requeridos',
                text: 'Debe seleccionar al menos un día específico o un día de la semana',
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

// Función para inicializar selección de días
function inicializarSeleccionDias() {
    // Event listeners para días de semana
    const checkboxesDiasSemana = document.querySelectorAll('input[name="dias_semana"]');
    checkboxesDiasSemana.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            actualizarDiasSeleccionados();
            actualizarVistaPrevia();
        });
    });
    
    // Inicializar Flatpickr para fechas específicas (modo múltiple)
    // Usar el módulo común para mostrar festivos y mantenimiento
    if (fechasEspecificasInput && window.DatepickerFestivos && typeof flatpickr !== 'undefined') {
        const fechaMinima = fechaInicioInput ? fechaInicioInput.getAttribute('data-min-date') : new Date().toISOString().split('T')[0];
        
        // Cargar festivos y mantenimiento primero
        Promise.all([
            window.DatepickerFestivos.cargarDiasFestivos(),
            window.DatepickerFestivos.cargarDiasMantenimiento()
        ]).then(([festivosMap, mantenimientoMap]) => {
            // Limpiar instancia anterior si existe
            if (flatpickrFechasEspecificas) {
                flatpickrFechasEspecificas.destroy();
            }
            
            flatpickrFechasEspecificas = flatpickr(fechasEspecificasInput, {
                mode: 'multiple',
                dateFormat: 'Y-m-d',
                locale: 'es',
                minDate: fechaMinima,
                enableTime: false,
                allowInput: false,
                clickOpens: true,
                onReady: function(selectedDates, dateStr, instance) {
                    setTimeout(() => {
                        if (window.DatepickerFestivos && window.DatepickerFestivos.marcarFestivosEnCalendario) {
                            window.DatepickerFestivos.marcarFestivosEnCalendario(instance, festivosMap);
                        }
                        if (window.DatepickerFestivos && window.DatepickerFestivos.marcarMantenimientoEnCalendario) {
                            window.DatepickerFestivos.marcarMantenimientoEnCalendario(instance, mantenimientoMap);
                        }
                    }, 100);
                },
                onMonthChange: function(selectedDates, dateStr, instance) {
                    setTimeout(() => {
                        if (window.DatepickerFestivos && window.DatepickerFestivos.marcarFestivosEnCalendario) {
                            window.DatepickerFestivos.marcarFestivosEnCalendario(instance, festivosMap);
                        }
                        if (window.DatepickerFestivos && window.DatepickerFestivos.marcarMantenimientoEnCalendario) {
                            window.DatepickerFestivos.marcarMantenimientoEnCalendario(instance, mantenimientoMap);
                        }
                    }, 100);
                },
                onYearChange: function(selectedDates, dateStr, instance) {
                    const nuevoAño = instance.currentYear;
                    Promise.all([
                        window.DatepickerFestivos.cargarDiasFestivos(nuevoAño),
                        window.DatepickerFestivos.cargarDiasMantenimiento(nuevoAño)
                    ]).then(([nuevosFestivos, nuevoMantenimiento]) => {
                        festivosMap = nuevosFestivos;
                        mantenimientoMap = nuevoMantenimiento;
                        setTimeout(() => {
                            if (window.DatepickerFestivos && window.DatepickerFestivos.marcarFestivosEnCalendario) {
                                window.DatepickerFestivos.marcarFestivosEnCalendario(instance, festivosMap);
                            }
                            if (window.DatepickerFestivos && window.DatepickerFestivos.marcarMantenimientoEnCalendario) {
                                window.DatepickerFestivos.marcarMantenimientoEnCalendario(instance, mantenimientoMap);
                            }
                        }, 100);
                    });
                },
                onOpen: function(selectedDates, dateStr, instance) {
                    setTimeout(() => {
                        if (window.DatepickerFestivos && window.DatepickerFestivos.marcarFestivosEnCalendario) {
                            window.DatepickerFestivos.marcarFestivosEnCalendario(instance, festivosMap);
                        }
                        if (window.DatepickerFestivos && window.DatepickerFestivos.marcarMantenimientoEnCalendario) {
                            window.DatepickerFestivos.marcarMantenimientoEnCalendario(instance, mantenimientoMap);
                        }
                    }, 100);
                },
                onChange: function(selectedDates, dateStr, instance) {
                    // Convertir fechas seleccionadas a formato YYYY-MM-DD
                    fechasEspecificasSeleccionadas = selectedDates.map(d => {
                        const year = d.getFullYear();
                        const month = String(d.getMonth() + 1).padStart(2, '0');
                        const day = String(d.getDate()).padStart(2, '0');
                        return `${year}-${month}-${day}`;
                    });
                    actualizarListaFechasEspecificas();
                    actualizarDiasSeleccionados();
                    actualizarVistaPrevia();
                }
            });
        }).catch(error => {
            console.error('Error cargando festivos/mantenimiento para fechas específicas:', error);
        });
    } else {
        if (!fechasEspecificasInput) {
            console.warn('fechasEspecificasInput no encontrado');
        }
        if (!window.DatepickerFestivos) {
            console.warn('DatepickerFestivos no está disponible');
        }
        if (typeof flatpickr === 'undefined') {
            console.warn('flatpickr no está disponible');
        }
    }
    
    // Actualizar fecha mínima cuando cambia fecha_inicio
    if (fechaInicioInput) {
        fechaInicioInput.addEventListener('change', function() {
            if (flatpickrFechasEspecificas && this.value) {
                flatpickrFechasEspecificas.set('minDate', this.value);
            }
            cargarJornadaSolicitante().then(() => {
                actualizarVistaPrevia();
            });
        });
    }
    
    // Actualizar fecha máxima cuando cambia fecha_fin
    if (fechaFinInput) {
        fechaFinInput.addEventListener('change', function() {
            if (flatpickrFechasEspecificas && this.value) {
                flatpickrFechasEspecificas.set('maxDate', this.value);
            }
            actualizarVistaPrevia();
        });
    }
}

// Función para actualizar lista de fechas específicas
function actualizarListaFechasEspecificas() {
    if (!fechasEspecificasLista) return;
    
    if (fechasEspecificasSeleccionadas.length === 0) {
        fechasEspecificasLista.innerHTML = '<p class="text-muted small">No hay fechas específicas seleccionadas</p>';
        return;
    }
    
    const fechasOrdenadas = fechasEspecificasSeleccionadas.sort();
    const fechasHtml = fechasOrdenadas.map(fecha => {
        const fechaObj = new Date(fecha + 'T00:00:00');
        const fechaFormateada = fechaObj.toLocaleDateString('es-ES', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
        return `
            <span class="badge badge-primary mr-2 mb-2" style="font-size: 0.9rem;">
                ${fechaFormateada}
                <button type="button" class="btn btn-sm btn-link text-white p-0 ml-2" onclick="eliminarFechaEspecifica('${fecha}')" style="text-decoration: none;">
                    <i class="fas fa-times"></i>
                </button>
            </span>
        `;
    }).join('');
    
    fechasEspecificasLista.innerHTML = fechasHtml;
}

// Función para eliminar fecha específica
function eliminarFechaEspecifica(fecha) {
    fechasEspecificasSeleccionadas = fechasEspecificasSeleccionadas.filter(f => f !== fecha);
    
    // Actualizar Flatpickr
    if (flatpickrFechasEspecificas) {
        const nuevasFechas = fechasEspecificasSeleccionadas.map(f => new Date(f + 'T00:00:00'));
        flatpickrFechasEspecificas.setDate(nuevasFechas, false);
    }
    
    actualizarListaFechasEspecificas();
    actualizarDiasSeleccionados();
    actualizarVistaPrevia();
}

// Función para obtener días seleccionados
function obtenerDiasSeleccionados() {
    const checkboxesDiasSemana = document.querySelectorAll('input[name="dias_semana"]:checked');
    const diasSemana = Array.from(checkboxesDiasSemana).map(cb => parseInt(cb.value));
    
    return {
        fechas_especificas: fechasEspecificasSeleccionadas,
        dias_semana: diasSemana
    };
}

// Función para actualizar campo hidden
function actualizarDiasSeleccionados() {
    const dias = obtenerDiasSeleccionados();
    if (diasSeleccionadosHidden) {
        diasSeleccionadosHidden.value = JSON.stringify(dias);
    }
}

// Función para generar vista previa de fechas
async function actualizarVistaPrevia() {
    const fechaInicio = fechaInicioInput ? fechaInicioInput.value : null;
    const fechaFin = fechaFinInput ? fechaFinInput.value : null;
    
    if (!fechaInicio || !fechaFin) {
        if (vistaPreviaFechas) {
            vistaPreviaFechas.style.display = 'none';
        }
        return;
    }
    
    const dias = obtenerDiasSeleccionados();
    
    if (!dias.fechas_especificas.length && !dias.dias_semana.length) {
        if (vistaPreviaFechas) {
            vistaPreviaFechas.style.display = 'none';
        }
        return;
    }
    
    // Mostrar indicador de carga
    if (listaFechasPrevia) {
        listaFechasPrevia.innerHTML = '<li class="list-group-item py-1 text-muted"><i class="fas fa-spinner fa-spin"></i> Validando fechas...</li>';
    }
    
    // Generar lista de fechas válidas
    const resultado = await generarFechasValidas(fechaInicio, fechaFin, dias);
    const fechasGeneradas = resultado.fechas;
    const fechasInvalidas = resultado.invalidas;
    
    if (fechasGeneradas.length === 0 && fechasInvalidas.length === 0) {
        if (vistaPreviaFechas) {
            vistaPreviaFechas.style.display = 'none';
        }
        return;
    }
    
    // Mostrar vista previa
    if (vistaPreviaFechas) {
        vistaPreviaFechas.style.display = 'block';
    }
    
    // Actualizar contador total
    if (totalDiasSeleccionados) {
        totalDiasSeleccionados.textContent = fechasGeneradas.length;
    }
    
    // Mostrar lista de fechas válidas
    if (listaFechasPrevia) {
        let fechasHtml = '';
        
        if (fechasGeneradas.length > 0) {
            fechasHtml = fechasGeneradas.slice(0, 20).map(fecha => {
                const fechaObj = new Date(fecha + 'T00:00:00');
                const fechaFormateada = fechaObj.toLocaleDateString('es-ES', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
                return `<li class="list-group-item py-1"><i class="fas fa-check-circle text-success mr-2"></i>${fechaFormateada}</li>`;
            }).join('');
            
            if (fechasGeneradas.length > 20) {
                fechasHtml += `<li class="list-group-item py-1 text-muted">... y ${fechasGeneradas.length - 20} días más</li>`;
            }
        }
        
        // Mostrar advertencia si hay fechas inválidas con fechas específicas
        if (fechasInvalidas.length > 0) {
            // Agrupar fechas por razón
            const fechasPorRazon = {};
            fechasInvalidas.forEach(item => {
                if (!fechasPorRazon[item.razon]) {
                    fechasPorRazon[item.razon] = [];
                }
                fechasPorRazon[item.razon].push(item.fecha);
            });
            
            // Ordenar fechas dentro de cada razón
            Object.keys(fechasPorRazon).forEach(razon => {
                fechasPorRazon[razon].sort();
            });
            
            // Generar HTML para cada razón con sus fechas
            const seccionesExcluidas = Object.entries(fechasPorRazon).map(([razon, fechas]) => {
                const count = fechas.length;
                const icono = obtenerIconoRazon(razon);
                const color = obtenerColorRazon(razon);
                
                // Formatear fechas
                const fechasFormateadas = fechas.map(fechaStr => {
                    const fechaObj = new Date(fechaStr + 'T00:00:00');
                    return fechaObj.toLocaleDateString('es-ES', { 
                        weekday: 'short', 
                        year: 'numeric', 
                        month: 'short', 
                        day: 'numeric' 
                    });
                });
                
                // Mostrar máximo 5 fechas inicialmente
                const mostrarTodas = fechas.length <= 5;
                const fechasVisibles = mostrarTodas ? fechasFormateadas : fechasFormateadas.slice(0, 5);
                const fechasOcultas = mostrarTodas ? [] : fechasFormateadas.slice(5);
                
                let fechasHtml = fechasVisibles.map(fecha => {
                    return `<div class="fecha-excluida-item">
                        <i class="fas fa-times-circle text-${color} mr-2"></i>
                        <span>${fecha}</span>
                    </div>`;
                }).join('');
                
                // Botón para mostrar todas si hay más de 5
                let botonVerTodas = '';
                if (!mostrarTodas) {
                    const razonId = razon.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
                    botonVerTodas = `
                        <button type="button" 
                                class="btn btn-sm btn-link p-0 mt-2 ver-todas-fechas" 
                                data-razon="${razonId}"
                                data-mostrando="false">
                            <i class="fas fa-chevron-down mr-1"></i>
                            Ver ${fechasOcultas.length} fecha${fechasOcultas.length > 1 ? 's' : ''} más
                        </button>
                        <div class="fechas-ocultas-${razonId}" style="display: none;">
                            ${fechasOcultas.map(fecha => {
                                return `<div class="fecha-excluida-item">
                                    <i class="fas fa-times-circle text-${color} mr-2"></i>
                                    <span>${fecha}</span>
                                </div>`;
                            }).join('')}
                        </div>
                    `;
                }
                
                return `
                    <div class="exclusion-razon mb-3">
                        <div class="d-flex align-items-center mb-2">
                            ${icono}
                            <strong class="mr-2">${razon}:</strong>
                            <span class="badge badge-${color}">${count} día${count > 1 ? 's' : ''}</span>
                        </div>
                        <div class="fechas-excluidas-list pl-4">
                            ${fechasHtml}
                            ${botonVerTodas}
                        </div>
                    </div>
                `;
            }).join('');
            
            fechasHtml += `
                <li class="list-group-item py-3 bg-warning text-dark">
                    <div class="d-flex align-items-start mb-2">
                        <i class="fas fa-exclamation-triangle mr-2 mt-1"></i>
                        <div class="flex-grow-1">
                            <strong>Fechas excluidas:</strong>
                            <small class="d-block mt-1 mb-2">Estas fechas no se aplicarán porque son inválidas según las reglas de negocio.</small>
                            ${seccionesExcluidas}
                        </div>
                    </div>
                </li>
            `;
        }
        
        // Mostrar advertencia si no hay fechas válidas
        if (fechasGeneradas.length === 0 && fechasInvalidas.length > 0) {
            fechasHtml = `<li class="list-group-item py-2 bg-danger text-white">
                <i class="fas fa-times-circle mr-2"></i>
                <strong>No hay fechas válidas:</strong> Todas las fechas seleccionadas son inválidas.
                <br><small>Por favor, selecciona otros días o ajusta el rango de fechas.</small>
            </li>`;
        }
        
        listaFechasPrevia.innerHTML = `<ul class="list-group list-group-flush">${fechasHtml}</ul>`;
        
        // Agregar event listeners para botones "Ver todas"
        document.querySelectorAll('.ver-todas-fechas').forEach(boton => {
            boton.addEventListener('click', function() {
                const razonId = this.getAttribute('data-razon');
                const mostrando = this.getAttribute('data-mostrando') === 'true';
                const fechasOcultas = document.querySelector(`.fechas-ocultas-${razonId}`);
                const icono = this.querySelector('i');
                
                if (mostrando) {
                    fechasOcultas.style.display = 'none';
                    icono.classList.remove('fa-chevron-up');
                    icono.classList.add('fa-chevron-down');
                    const count = fechasOcultas.querySelectorAll('.fecha-excluida-item').length;
                    this.innerHTML = `<i class="fas fa-chevron-down mr-1"></i>Ver ${count} fecha${count > 1 ? 's' : ''} más`;
                    this.setAttribute('data-mostrando', 'false');
                } else {
                    fechasOcultas.style.display = 'block';
                    icono.classList.remove('fa-chevron-down');
                    icono.classList.add('fa-chevron-up');
                    this.innerHTML = `<i class="fas fa-chevron-up mr-1"></i>Ocultar fechas`;
                    this.setAttribute('data-mostrando', 'true');
                }
            });
        });
    }
}

// Función helper para obtener icono según razón de exclusión
function obtenerIconoRazon(razon) {
    const iconos = {
        'Domingo': '<i class="fas fa-calendar-times text-danger mr-2"></i>',
        'Festivo': '<i class="fas fa-calendar-check text-danger mr-2"></i>',
        'Mantenimiento': '<i class="fas fa-tools text-warning mr-2"></i>',
        'Descanso (AM)': '<i class="fas fa-moon text-secondary mr-2"></i>',
        'Descanso (PM)': '<i class="fas fa-moon text-secondary mr-2"></i>',
        'Descanso receptor (AM)': '<i class="fas fa-user-slash text-secondary mr-2"></i>',
        'Descanso receptor (PM)': '<i class="fas fa-user-slash text-secondary mr-2"></i>'
    };
    return iconos[razon] || '<i class="fas fa-ban text-danger mr-2"></i>';
}

// Función helper para obtener color según razón de exclusión
function obtenerColorRazon(razon) {
    const colores = {
        'Domingo': 'danger',
        'Festivo': 'danger',
        'Mantenimiento': 'warning',
        'Descanso (AM)': 'secondary',
        'Descanso (PM)': 'secondary',
        'Descanso receptor (AM)': 'secondary',
        'Descanso receptor (PM)': 'secondary'
    };
    return colores[razon] || 'danger';
}

// Cache para festivos y mantenimiento (se carga una vez)
let cacheFestivos = null;
let cacheMantenimiento = null;
let cacheJornadaSolicitante = null;
let cacheJornadaReceptor = null;

// Función para cargar jornada del solicitante
function cargarJornadaSolicitante() {
    if (!window.solicitanteId || !fechaInicioInput || !fechaInicioInput.value) {
        return Promise.resolve();
    }
    
    return fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fechaInicioInput.value}`)
        .then(response => response.json())
        .then(data => {
            if (data.turno && data.turno.jornada) {
                cacheJornadaSolicitante = data.turno.jornada;
            }
        })
        .catch(error => {
            console.error('Error cargando jornada del solicitante:', error);
        });
}

// Función para cargar jornada del receptor
function cargarJornadaReceptor() {
    const receptorSelect = document.getElementById('empleado_receptor');
    if (!receptorSelect || !receptorSelect.value || !fechaInicioInput || !fechaInicioInput.value) {
        cacheJornadaReceptor = null;
        return Promise.resolve();
    }
    
    return fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${receptorSelect.value}&fecha=${fechaInicioInput.value}`)
        .then(response => response.json())
        .then(data => {
            if (data.turno && data.turno.jornada) {
                cacheJornadaReceptor = data.turno.jornada;
            } else {
                cacheJornadaReceptor = null;
            }
        })
        .catch(error => {
            console.error('Error cargando jornada del receptor:', error);
            cacheJornadaReceptor = null;
        });
}

// Función para cargar festivos y mantenimiento
function cargarFestivosYMantenimiento() {
    if (cacheFestivos !== null && cacheMantenimiento !== null) {
        return Promise.resolve();
    }
    
    return Promise.all([
        window.DatepickerFestivos ? window.DatepickerFestivos.cargarDiasFestivos() : Promise.resolve(new Map()),
        window.DatepickerFestivos ? window.DatepickerFestivos.cargarDiasMantenimiento() : Promise.resolve(new Map())
    ]).then(([festivos, mantenimiento]) => {
        cacheFestivos = festivos;
        cacheMantenimiento = mantenimiento;
    });
}

// Función para verificar si un día es válido
async function esDiaValido(fechaStr) {
    const fecha = new Date(fechaStr + 'T00:00:00');
    const fechaDate = new Date(fecha.getFullYear(), fecha.getMonth(), fecha.getDate());
    const diaSemana = fechaDate.getDay(); // 0=domingo, 1=lunes, ..., 6=sábado
    
    // 1. Validar domingo (getDay() === 0)
    if (diaSemana === 0) {
        return { valido: false, razon: 'Domingo' };
    }
    
    // 2. Validar sábado (getDay() === 6) - CT PERMANENTE solo lunes-viernes
    if (diaSemana === 6) {
        return { valido: false, razon: 'Sábado' };
    }
    
    // 2. Cargar festivos y mantenimiento si no están en cache
    await cargarFestivosYMantenimiento();
    
    // 3. Validar festivo
    if (cacheFestivos && cacheFestivos.has(fechaStr)) {
        return { valido: false, razon: 'Festivo' };
    }
    
    // 4. Validar mantenimiento
    if (cacheMantenimiento && cacheMantenimiento.has(fechaStr)) {
        return { valido: false, razon: 'Mantenimiento' };
    }
    
    // 5. Validar día de descanso del solicitante
    if (cacheJornadaSolicitante) {
        if (cacheJornadaSolicitante === 'AM' && diaSemana === 6) { // Sábado
            return { valido: false, razon: 'Descanso (AM)' };
        }
        if (cacheJornadaSolicitante === 'PM' && diaSemana === 0) { // Domingo
            return { valido: false, razon: 'Descanso (PM)' };
        }
    }
    
    // 6. Validar día de descanso del receptor (si está seleccionado)
    if (cacheJornadaReceptor) {
        if (cacheJornadaReceptor === 'AM' && diaSemana === 6) { // Sábado
            return { valido: false, razon: 'Descanso receptor (AM)' };
        }
        if (cacheJornadaReceptor === 'PM' && diaSemana === 0) { // Domingo
            return { valido: false, razon: 'Descanso receptor (PM)' };
        }
    }
    
    return { valido: true, razon: null };
}

// Función para generar fechas válidas (similar a la lógica del backend)
async function generarFechasValidas(fechaInicioStr, fechaFinStr, diasSeleccionados) {
    // Cargar jornadas si no están en cache
    await Promise.all([
        cargarJornadaSolicitante(),
        cargarJornadaReceptor(),
        cargarFestivosYMantenimiento()
    ]);
    
    const fechaInicio = new Date(fechaInicioStr + 'T00:00:00');
    const fechaFin = new Date(fechaFinStr + 'T00:00:00');
    const fechas = new Set();
    const fechasInvalidas = [];
    
    // Agregar fechas específicas dentro del rango
    for (const fechaStr of diasSeleccionados.fechas_especificas) {
        const fecha = new Date(fechaStr + 'T00:00:00');
        if (fecha >= fechaInicio && fecha <= fechaFin) {
            const validacion = await esDiaValido(fechaStr);
            if (validacion.valido) {
                fechas.add(fechaStr);
            } else {
                fechasInvalidas.push({ fecha: fechaStr, razon: validacion.razon });
            }
        }
    }
    
    // Generar fechas para días de semana
    if (diasSeleccionados.dias_semana.length > 0) {
        let fechaActual = new Date(fechaInicio);
        while (fechaActual <= fechaFin) {
            const diaSemana = fechaActual.getDay(); // 0=domingo, 1=lunes, ..., 6=sábado
            // Convertir a formato del backend (0=lunes, 6=domingo)
            // IMPORTANTE: CT PERMANENTE solo permite lunes-viernes (0-4 en backend)
            const diaSemanaBackend = diaSemana === 0 ? 6 : diaSemana - 1;
            
            // Filtrar sábados (5) y domingos (6) - no se permiten en CT PERMANENTE
            if (diaSemanaBackend >= 0 && diaSemanaBackend <= 4 && diasSeleccionados.dias_semana.includes(diaSemanaBackend)) {
                const fechaStr = fechaActual.toISOString().split('T')[0];
                const validacion = await esDiaValido(fechaStr);
                if (validacion.valido) {
                    fechas.add(fechaStr);
                } else {
                    fechasInvalidas.push({ fecha: fechaStr, razon: validacion.razon });
                }
            } else if (diaSemanaBackend === 5 || diaSemanaBackend === 6) {
                // Si se seleccionó sábado o domingo, agregarlo a inválidas
                const fechaStr = fechaActual.toISOString().split('T')[0];
                const razon = diaSemanaBackend === 5 ? 'Sábado' : 'Domingo';
                fechasInvalidas.push({ fecha: fechaStr, razon: razon });
            }
            
            // Crear nueva fecha para evitar problemas con setDate
            const nuevaFecha = new Date(fechaActual);
            nuevaFecha.setDate(nuevaFecha.getDate() + 1);
            fechaActual = nuevaFecha;
        }
    }
    
    // Si no hay días seleccionados, usar rango completo (retrocompatibilidad)
    // IMPORTANTE: Solo lunes-viernes (excluir sábados y domingos)
    if (diasSeleccionados.fechas_especificas.length === 0 && diasSeleccionados.dias_semana.length === 0) {
        let fechaActual = new Date(fechaInicio);
        while (fechaActual <= fechaFin) {
            const diaSemana = fechaActual.getDay(); // 0=domingo, 1=lunes, ..., 6=sábado
            // Solo procesar lunes-viernes (1-5)
            if (diaSemana >= 1 && diaSemana <= 5) {
                const fechaStr = fechaActual.toISOString().split('T')[0];
                const validacion = await esDiaValido(fechaStr);
                if (validacion.valido) {
                    fechas.add(fechaStr);
                } else {
                    fechasInvalidas.push({ fecha: fechaStr, razon: validacion.razon });
                }
            } else {
                // Sábado o domingo - agregar a inválidas
                const fechaStr = fechaActual.toISOString().split('T')[0];
                const razon = diaSemana === 0 ? 'Domingo' : 'Sábado';
                fechasInvalidas.push({ fecha: fechaStr, razon: razon });
            }
            fechaActual.setDate(fechaActual.getDate() + 1);
        }
    }
    
    return {
        fechas: Array.from(fechas).sort(),
        invalidas: fechasInvalidas
    };
}

// Función para enviar la solicitud por AJAX
function enviarSolicitudCTPermanente() {
    const form = document.getElementById('ctPermanenteForm');
    const formData = new FormData(form);
    
    // Asegurar que días seleccionados estén actualizados
    actualizarDiasSeleccionados();
    
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
