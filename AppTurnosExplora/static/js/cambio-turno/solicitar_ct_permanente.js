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
let diasSeleccionadosHidden = null;
let vistaPreviaFechas = null;
let totalDiasSeleccionados = null;
let listaFechasPrevia = null;

// Almacenar días seleccionados
let diasSemanaSeleccionados = [];

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
    diasSeleccionadosHidden = document.getElementById('dias_seleccionados');
    vistaPreviaFechas = document.getElementById('vista_previa_fechas');
    totalDiasSeleccionados = document.getElementById('total_dias_seleccionados');
    listaFechasPrevia = document.getElementById('lista_fechas_previa');
    
    // Inicializar datepickers con festivos (usa módulo común)
    function inicializarDatepickers() {
        if (!fechaInicioInput || !window.DatepickerFestivos) {
            console.error('DatepickerFestivos no está disponible');
            return Promise.resolve();
        }
        
        const fechaMinima = fechaInicioInput.getAttribute('data-min-date')
            || window.DatepickerFestivos.fechaMinimaPorDefecto();
        
        // Función callback para cuando cambia la fecha de inicio
        const onDateChangeInicio = function(fecha) {
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
            // Limpiar override si cambia fecha_inicio (debe recalcularse con nuevo rango)
            if (window.overrideDiasSeleccionados) {
                window.overrideDiasSeleccionados = null;
            }
            // Disparar evento change para mantener compatibilidad
            fechaInicioInput.dispatchEvent(new Event('change'));
        };
        
        // Inicializar Flatpickr para fecha de inicio (bloquea domingos, festivos, mantenimiento y temporada)
        const promesaInicio = window.DatepickerFestivos.inicializar({
            input: fechaInicioInput,
            minDate: fechaMinima,
            indicadorFestivo: indicadorFestivoInicio,
            descripcionFestivo: descripcionFestivoInicio,
            bloquearDiasEspeciales: true,
            onDateChange: onDateChangeInicio
        }).then(instance => {
            flatpickrInicio = instance;
            return instance;
        }).catch(error => {
            console.error('Error inicializando datepicker de inicio:', error);
            return null;
        });
        
        // Inicializar Flatpickr para fecha de fin
        let promesaFin = Promise.resolve(null);
        if (fechaFinInput) {
            promesaFin = window.DatepickerFestivos.inicializar({
                input: fechaFinInput,
                minDate: fechaMinima,
                indicadorFestivo: indicadorFestivoFin,
                descripcionFestivo: descripcionFestivoFin,
                bloquearDiasEspeciales: true,
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
                    // Limpiar override si cambia fecha_fin (debe recalcularse con nuevo rango)
                    if (window.overrideDiasSeleccionados) {
                        window.overrideDiasSeleccionados = null;
                    }
                    
                    // Recargar jornada del solicitante cuando cambia la fecha
                    cargarJornadaSolicitante().then(() => {
                        actualizarVistaPrevia();
                    });
                    // Recargar jornada actual (incluye desglose si hay rango)
                    if (fechaInicioInput && fechaInicioInput.value) {
                        cargarJornadaActual(fechaInicioInput.value);
                    }
                    // Recargar empleados disponibles cuando cambia fecha_fin (importante para rango)
                    if (fechaInicioInput && fechaInicioInput.value) {
                        cargarEmpleadosDisponibles(fechaInicioInput.value);
                    } else {
                        // Si se quita fecha_inicio, limpiar override
                        window.overrideDiasSeleccionados = null;
                        actualizarDiasSeleccionados();
                    }
                }
            }).then(instance => {
                flatpickrFin = instance;
                return instance;
            }).catch(error => {
                console.error('Error inicializando datepicker de fin:', error);
                return null;
            });
        }
        
        // Retornar Promise que espera ambas inicializaciones
        return Promise.all([promesaInicio, promesaFin]);
    }
    
    // Función para cargar información cuando cambia la fecha de inicio
    function configurarEventListeners() {
        if (fechaInicioInput) {
            fechaInicioInput.addEventListener('change', function() {
                const fechaInicio = this.value;
                if (fechaInicio) {
                    // Actualizar fecha mínima de fin
                    if (flatpickrFin) {
                        flatpickrFin.set('minDate', fechaInicio);
                    }
                    // Cargar jornada actual (se ocultará automáticamente si hay fecha_fin)
                    cargarJornadaActual(fechaInicio);
                    // Solo cargar empleados si hay rango completo (fecha_inicio Y fecha_fin)
                    const fechaFin = fechaFinInput ? fechaFinInput.value : null;
                    if (fechaFin) {
                        cargarEmpleadosDisponibles(fechaInicio);
                    } else {
                        // Limpiar lista de empleados si no hay rango completo
                        const select = document.getElementById('empleado_receptor');
                        if (select) {
                            select.innerHTML = '<option value="">Selecciona fecha de fin para ver compañeros disponibles...</option>';
                        }
                    }
                    // Recargar jornada del solicitante para validaciones
                    cargarJornadaSolicitante().then(() => {
                        actualizarVistaPrevia();
                    });
                }
            });
        }
    }
    
    // Función para cargar datos iniciales si existen
    function cargarDatosIniciales() {
        if (fechaInicioInput && fechaInicioInput.value) {
            const fechaInicio = fechaInicioInput.value;
            const fechaFin = fechaFinInput ? fechaFinInput.value : null;
            
            // Cargar jornada actual (se ocultará si hay fecha_fin)
            cargarJornadaActual(fechaInicio);
            
            // Limpiar override si cambian las fechas (debe recalcularse con nuevo rango)
            if (window.overrideDiasSeleccionados) {
                window.overrideDiasSeleccionados = null;
            }
            
            // Solo cargar empleados si hay rango completo (fecha_inicio Y fecha_fin)
            if (fechaFin) {
                cargarEmpleadosDisponibles(fechaInicio);
            } else {
                // Limpiar lista de empleados si no hay rango completo
                const select = document.getElementById('empleado_receptor');
                if (select) {
                    select.innerHTML = '<option value="">Selecciona fecha de fin para ver compañeros disponibles...</option>';
                }
                // Limpiar override si se quita fecha_fin
                window.overrideDiasSeleccionados = null;
                actualizarDiasSeleccionados();
            }
            
            // Cargar jornada del solicitante para validaciones
            cargarJornadaSolicitante().then(() => {
                actualizarVistaPrevia();
            });
        }
    }
    
    // Inicializar datepickers y luego cargar datos
    inicializarDatepickers()
        .then(() => {
            // Configurar event listeners después de inicializar
            configurarEventListeners();
            // Cargar datos iniciales después de que los datepickers estén listos
            cargarDatosIniciales();
        })
        .catch(error => {
            console.error('Error inicializando datepickers:', error);
            // Aún así, intentar configurar listeners y cargar datos
            configurarEventListeners();
            cargarDatosIniciales();
        });
    
    // Inicializar selección de días
    inicializarSeleccionDias();
    
    // Limpiar override cuando cambian las fechas o días seleccionados manualmente
    const limpiarOverrideSiNecesario = () => {
        // Si el usuario cambia fechas o días manualmente, limpiar override
        // (el override solo debe persistir si el mismo compañero sigue seleccionado)
        if (window.overrideDiasSeleccionados) {
            const empleadoActual = document.getElementById('empleado_receptor').value;
            if (!empleadoActual) {
                // Si no hay compañero seleccionado, limpiar override
                window.overrideDiasSeleccionados = null;
            }
        }
    };

    // Función para cargar información del compañero seleccionado
    document.getElementById('empleado_receptor').addEventListener('change', function() {
        const empleadoId = this.value;
        const fechaInicio = document.getElementById('fecha_inicio').value;
        
        // Limpiar override de compañero anterior
        window.overrideDiasSeleccionados = null;
        
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
            // Restaurar días seleccionados originales cuando se deselecciona compañero
            actualizarDiasSeleccionados();
            actualizarVistaPrevia();
        }
    });

    // Validación del formulario y envío por AJAX
    document.getElementById('ctPermanenteForm').addEventListener('submit', function(e) {
        e.preventDefault(); // Prevenir envío tradicional del formulario
        
        const form = document.getElementById('ctPermanenteForm');
        
        // Validación genérica de campos requeridos
        if (window.ValidadoresSolicitudes) {
            const tipoNombre = window.ValidadoresSolicitudes.obtenerTipoSolicitud(form) || 
                              document.querySelector('[data-tipo-nombre]')?.getAttribute('data-tipo-nombre') ||
                              'CT PERMANENTE';
            
            const validacion = window.ValidadoresSolicitudes.validarFormularioSolicitud(form, tipoNombre);
            if (!validacion.valido) {
                window.ValidadoresSolicitudes.mostrarErroresValidacion(validacion.errores);
                return;
            }
        }

        // Validar comentario obligatorio
        const comentariosInput = document.getElementById('comentarios');
        const comentarioValor = comentariosInput ? comentariosInput.value.trim() : '';
        if (!comentarioValor) {
            Swal.fire({
                icon: 'error',
                title: 'Comentario requerido',
                text: 'Debes ingresar un comentario para enviar la solicitud de cambio permanente.',
                confirmButtonText: 'Entendido'
            }).then(() => {
                if (comentariosInput) {
                    comentariosInput.focus();
                }
            });
            return;
        }
        
        // Validar que haya al menos un día seleccionado (validación específica de CT PERMANENTE)
        // Primero verificar si hay override activo (compatibilidad parcial)
        let tieneDiasValidos = false;
        let mensajeError = 'Debe seleccionar al menos un día de la semana (lunes a viernes) para el cambio permanente.';
        
        if (window.overrideDiasSeleccionados && window.overrideDiasSeleccionados.fechas_especificas) {
            // Si hay override con fechas específicas, validar que tenga al menos una fecha
            tieneDiasValidos = window.overrideDiasSeleccionados.fechas_especificas.length > 0;
            if (!tieneDiasValidos) {
                mensajeError = 'No hay días compatibles con el compañero seleccionado. Por favor, selecciona otro compañero o ajusta el rango de fechas.';
            }
        } else {
            // Validar checkboxes normales
            const diasSeleccionados = obtenerDiasSeleccionados();
            tieneDiasValidos = diasSeleccionados.dias_semana.length > 0;
        }
        
        if (!tieneDiasValidos) {
            Swal.fire({
                icon: 'warning',
                title: 'Días requeridos',
                text: mensajeError,
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
    const fechaFin = document.getElementById('fecha_fin').value;

    // Al recargar compañeros (cambió fecha/rango/días) la selección anterior se invalida:
    // ocultar los paneles dependientes del receptor para que no queden datos viejos visibles.
    const _tci = document.getElementById('turno_companero_info');
    if (_tci) _tci.style.display = 'none';
    const _ri = document.getElementById('resumen_intercambio');
    if (_ri) _ri.style.display = 'none';


    // Para CT PERMANENTE, solo cargar empleados si hay rango completo (fecha_inicio Y fecha_fin)
    if (!fechaFin) {
        const select = document.getElementById('empleado_receptor');
        if (select) {
            select.innerHTML = '<option value="">Selecciona fecha de fin para ver compañeros disponibles...</option>';
        }
        return;
    }
    
    const diasSeleccionados = obtenerDiasSeleccionados();
    const diasJSON = JSON.stringify(diasSeleccionados);
    
    
    // Construir URL con parámetros (siempre incluir fecha_fin ya que verificamos que existe)
    let url = `/solicitudes/obtener-empleados-disponibles/?fecha=${fecha}&tipo_solicitud_id=${tipoSolicitudId}&fecha_fin=${fechaFin}&dias_seleccionados=${encodeURIComponent(diasJSON)}`;
    
    fetch(url)
        .then(response => {
            return response.json();
        })
        .then(data => {
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
                        
                        // Estilo visual simple en el texto
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
            } else {
                const option = document.createElement('option');
                option.value = '';
                option.textContent = 'No hay compañeros disponibles con jornada contraria';
                select.appendChild(option);
            }
        })
        .catch(error => {
            console.error('Error cargando empleados:', error);
            const select = document.getElementById('empleado_receptor');
            select.innerHTML = '<option value="">Error cargando empleados</option>';
        });
}

// Función auxiliar para mostrar jornada simple (sin rango)
function mostrarJornadaSimple(container, turno, horario, salasHtml, infoDiv) {
    container.innerHTML = `
        <div class="row">
            <div class="col-md-6">
                <div class="badge badge-info p-2 w-100">
                    <strong>Jornada:</strong> ${turno.jornada || 'No asignada'}
                </div>
            </div>
            <div class="col-md-6">
                <div class="badge badge-secondary p-2 w-100">
                    <strong>Horario:</strong> ${horario}
                </div>
            </div>
            ${salasHtml}
        </div>
    `;
    if (infoDiv) {
        infoDiv.style.display = 'block';
    }
}

// Función para cargar desglose de jornadas día a día del rango
async function cargarDesgloseJornadasRango(exploradorId, fechaInicio, fechaFin) {
    const diasSeleccionados = obtenerDiasSeleccionados();
    const diasJSON = JSON.stringify(diasSeleccionados);
    
    const url = `/solicitudes/obtener-jornadas-rango/?explorador_id=${exploradorId}&fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}&dias_seleccionados=${encodeURIComponent(diasJSON)}`;
    
    const response = await fetch(url);
    const data = await response.json();
    
    if (!data.success) {
        throw new Error('Error obteniendo jornadas del rango');
    }
    
    // json_ok devuelve {success: true, jornadas: [...], resumen: {...}}
    const jornadas = data.jornadas || [];
    const resumen = data.resumen || { total_dias: 0, dias_am: 0, dias_pm: 0, dias_doblada: 0 };

    // Badges de días que NO aplican (se muestran solo si existen). Reflejan lo que el CT
    // permanente excluirá realmente, coherente con la lista de abajo.
    const badgeExcluido = (n, cls, icono, txt) => (n || 0) > 0
        ? `<span class="badge badge-${cls} p-2"><i class="fas ${icono} mr-1"></i>${txt}: ${n} días</span>`
        : '';

    // Construir resumen agrupado
    const resumenHtml = `
        <div class="d-flex flex-wrap gap-2 mb-3">
            <span class="badge badge-primary p-2">
                <i class="fas fa-sun mr-1"></i>AM: ${resumen.dias_am} días
            </span>
            <span class="badge badge-warning p-2">
                <i class="fas fa-moon mr-1"></i>PM: ${resumen.dias_pm} días
            </span>
            ${badgeExcluido(resumen.dias_doblada, 'info', 'fa-clone', 'Doblada')}
            ${badgeExcluido(resumen.dias_mantenimiento, 'dark', 'fa-tools', 'Mantenim.')}
            ${badgeExcluido(resumen.dias_festivo, 'danger', 'fa-calendar-check', 'Festivo')}
            ${badgeExcluido(resumen.dias_temporada, 'success', 'fa-calendar-alt', 'Temporada')}
            <span class="badge badge-secondary p-2">
                <i class="fas fa-calendar-alt mr-1"></i>Total: ${resumen.total_dias} días
            </span>
        </div>
    `;
    
    // Agrupar días consecutivos con misma jornada
    const grupos = agruparDiasConsecutivos(jornadas);
    
    // Construir lista de días (mostrar primeros 15, resto colapsable)
    const LIMITE_VISIBLE = 15;
    const diasVisibles = grupos.slice(0, LIMITE_VISIBLE);
    const diasOcultos = grupos.slice(LIMITE_VISIBLE);
    
    let listaDiasHtml = '<div class="list-group list-group-flush">';
    
    diasVisibles.forEach(grupo => {
        listaDiasHtml += renderizarGrupoDias(grupo);
    });
    
    if (diasOcultos.length > 0) {
        listaDiasHtml += `
            <div class="list-group-item p-0">
                <button type="button" class="btn btn-link btn-sm w-100 text-left" id="btn_ver_mas_jornadas" onclick="toggleDiasOcultos()">
                    <i class="fas fa-chevron-down mr-2"></i>
                    Ver ${diasOcultos.length} día${diasOcultos.length > 1 ? 's' : ''} más
                </button>
                <div id="dias_ocultos_jornadas" style="display: none;">
        `;
        diasOcultos.forEach(grupo => {
            listaDiasHtml += renderizarGrupoDias(grupo);
        });
        listaDiasHtml += `
                </div>
            </div>
        `;
    }
    
    listaDiasHtml += '</div>';
    
    return `
        <div class="card border-info">
            <div class="card-header bg-info text-white py-2">
                <h6 class="mb-0">
                    <i class="fas fa-calendar-week mr-2"></i>Desglose de Jornadas en el Rango
                </h6>
            </div>
            <div class="card-body p-3">
                ${resumenHtml}
                ${listaDiasHtml}
            </div>
        </div>
    `;
}

// Función para agrupar días consecutivos con misma jornada
function agruparDiasConsecutivos(jornadas) {
    if (jornadas.length === 0) return [];
    
    const grupos = [];
    let grupoActual = {
        jornada: jornadas[0].jornada,
        fechas: [jornadas[0]]
    };
    
    for (let i = 1; i < jornadas.length; i++) {
        const jornadaActual = jornadas[i];
        const fechaActual = new Date(jornadaActual.fecha + 'T00:00:00');
        const fechaAnterior = new Date(jornadas[i-1].fecha + 'T00:00:00');
        const diasDiferencia = (fechaActual - fechaAnterior) / (1000 * 60 * 60 * 24);
        
        // Si es consecutivo (diferencia de 1 día) y misma jornada, agregar al grupo
        if (diasDiferencia === 1 && jornadaActual.jornada === grupoActual.jornada) {
            grupoActual.fechas.push(jornadaActual);
        } else {
            // Nuevo grupo
            grupos.push(grupoActual);
            grupoActual = {
                jornada: jornadaActual.jornada,
                fechas: [jornadaActual]
            };
        }
    }
    grupos.push(grupoActual);
    
    return grupos;
}

// Función para renderizar un grupo de días
function renderizarGrupoDias(grupo) {
    const estilos = {
        'AM':            { color: 'primary', icono: 'fa-sun' },
        'PM':            { color: 'warning', icono: 'fa-moon' },
        'DOBLADA':       { color: 'info',    icono: 'fa-clone' },
        'MANTENIMIENTO': { color: 'dark',    icono: 'fa-tools' },
        'FESTIVO':       { color: 'danger',  icono: 'fa-calendar-check' },
        'TEMPORADA':     { color: 'success', icono: 'fa-calendar-alt' },
    };
    const est = estilos[grupo.jornada] || { color: 'secondary', icono: 'fa-question' };
    const colorBadge = est.color;
    const icono = est.icono;
    
    if (grupo.fechas.length === 1) {
        const fecha = grupo.fechas[0];
        return `
            <div class="list-group-item py-2">
                <div class="d-flex justify-content-between align-items-center">
                    <span>
                        <i class="fas ${icono} text-${colorBadge} mr-2"></i>
                        <strong>${fecha.fecha_formateada}</strong> (${fecha.dia_semana})
                    </span>
                    <span class="badge badge-${colorBadge}">${grupo.jornada || 'Sin jornada'}</span>
                </div>
            </div>
        `;
    } else {
        const primeraFecha = grupo.fechas[0];
        const ultimaFecha = grupo.fechas[grupo.fechas.length - 1];
        return `
            <div class="list-group-item py-2">
                <div class="d-flex justify-content-between align-items-center">
                    <span>
                        <i class="fas ${icono} text-${colorBadge} mr-2"></i>
                        <strong>${primeraFecha.fecha_formateada}</strong> - <strong>${ultimaFecha.fecha_formateada}</strong>
                        <small class="text-muted ml-2">(${grupo.fechas.length} días consecutivos)</small>
                    </span>
                    <span class="badge badge-${colorBadge}">${grupo.jornada || 'Sin jornada'}</span>
                </div>
            </div>
        `;
    }
}

// Función para toggle de días ocultos
function toggleDiasOcultos() {
    const divOcultos = document.getElementById('dias_ocultos_jornadas');
    const btn = document.getElementById('btn_ver_mas_jornadas');
    const icono = btn.querySelector('i');
    
    if (divOcultos.style.display === 'none') {
        divOcultos.style.display = 'block';
        icono.classList.remove('fa-chevron-down');
        icono.classList.add('fa-chevron-up');
        btn.innerHTML = '<i class="fas fa-chevron-up mr-2"></i>Ocultar días';
    } else {
        divOcultos.style.display = 'none';
        icono.classList.remove('fa-chevron-up');
        icono.classList.add('fa-chevron-down');
        const count = divOcultos.querySelectorAll('.list-group-item').length;
        btn.innerHTML = `<i class="fas fa-chevron-down mr-2"></i>Ver ${count} día${count > 1 ? 's' : ''} más`;
    }
}

// Función para cargar jornada actual
function cargarJornadaActual(fecha) {
    
    const fechaFin = document.getElementById('fecha_fin').value;
    const esRango = fechaFin && fechaFin > fecha;
    const infoDiv = document.getElementById('turno_actual_info');
    
    // Si hay rango, usar jornada_base=true para obtener la jornada base (no la del día específico)
    const tipoSolicitudInput = document.getElementById('tipo_solicitud_id');
    const tipoSolicitudId = tipoSolicitudInput ? tipoSolicitudInput.value : '';
    const url = esRango 
        ? `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fecha}&jornada_base=true${tipoSolicitudId ? `&tipo_solicitud_id=${tipoSolicitudId}` : ''}`
        : `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fecha}${tipoSolicitudId ? `&tipo_solicitud_id=${tipoSolicitudId}` : ''}`;
    
    fetch(url)
        .then(response => {
            return response.json();
        })
        .then(data => {
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
                            <div class="badge badge-success p-2 w-100" style="white-space: normal; text-align: left;">
                                <strong>Salas:</strong> ${nombresSalas.join(', ')}
                            </div>
                        </div>
                    `;
                }
                
                // Si hay rango, cargar desglose de jornadas día a día
                if (esRango && turno.es_jornada_base) {
                    const fechaFinValue = document.getElementById('fecha_fin').value;
                    cargarDesgloseJornadasRango(window.solicitanteId, fecha, fechaFinValue).then(desgloseHtml => {
                        container.innerHTML = `
                            <div class="row">
                                <div class="col-12 mb-2">
                                    <div class="alert alert-info py-2 px-3 small mb-2" style="border-left: 4px solid #17a2b8;">
                                        <i class="fas fa-info-circle mr-1"></i>
                                        <strong>Jornada Base:</strong> ${turno.jornada || 'No asignada'} | <strong>Horario:</strong> ${horario}
                                    </div>
                                </div>
                                ${salasHtml}
                                <div class="col-12 mt-3">
                                    ${desgloseHtml}
                                </div>
                            </div>
                        `;
                        if (infoDiv) {
                            infoDiv.style.display = 'block';
                        }
                    }).catch(error => {
                        console.error('Error cargando desglose de jornadas:', error);
                        // Fallback a visualización simple
                        mostrarJornadaSimple(container, turno, horario, salasHtml, infoDiv);
                    });
                } else {
                    // Sin rango: mostrar jornada simple
                    mostrarJornadaSimple(container, turno, horario, salasHtml, infoDiv);
                }
            } else {
                container.innerHTML = '<p class="text-muted">No tienes jornada asignada para esta fecha</p>';
                if (infoDiv) {
                    infoDiv.style.display = 'block';
                }
            }
        })
        .catch(error => {
            console.error('Error cargando jornada actual:', error);
            const container = document.getElementById('jornada_actual_detalles');
            const infoDiv = document.getElementById('turno_actual_info');
            if (container) {
                container.innerHTML = '<p class="text-danger">Error cargando información de jornada</p>';
            }
            if (infoDiv) {
                infoDiv.style.display = 'block';
            }
        });
}

function cargarJornadaCompanero(empleadoId, fecha) {
    
    // Si hay rango seleccionado, usar jornada_base para mostrar la jornada base del compañero
    const fechaFin = document.getElementById('fecha_fin').value;
    const esRango = fechaFin && fechaFin > fecha;
    const url = esRango
        ? `/solicitudes/obtener-turno-explorador/?explorador_id=${empleadoId}&fecha=${fecha}&jornada_base=true`
        : `/solicitudes/obtener-turno-explorador/?explorador_id=${empleadoId}&fecha=${fecha}`;
    
    fetch(url)
        .then(response => {
            return response.json();
        })
        .then(data => {
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
    const selectedOption = empleadoSelect.options[empleadoSelect.selectedIndex];
    const empleadoNombre = selectedOption.text.split(' - ')[0].replace(/ ✅| ⚠️| ❌/g, '');
    
    if (fechaInicio && empleadoSelect.value) {
        const container = document.getElementById('resumen_detalles');
        const infoDiv = document.getElementById('resumen_intercambio');
        
        let fechaFinText = fechaFin ? ` hasta ${fechaFin}` : ' hasta fin de año';
        let compatibilidadHtml = '';
        let advertenciaHtml = '';
        
        // Verificar compatibilidad
        const compatibilidad = selectedOption.getAttribute('data-compatibilidad');
        if (compatibilidad !== null) {
            const percent = parseInt(compatibilidad);
            const diasIncompatiblesStr = selectedOption.getAttribute('data-dias-incompatibles');
            const diasIncompatibles = diasIncompatiblesStr ? JSON.parse(diasIncompatiblesStr) : [];
            const totalDias = parseInt(selectedOption.getAttribute('data-total-dias') || 0);
            const diasCompatiblesCount = totalDias - diasIncompatibles.length;
            
            let colorBadge = 'success';
            if (percent < 100) colorBadge = percent >= 50 ? 'warning' : 'danger';
            
            compatibilidadHtml = `<li><strong>Compatibilidad:</strong> <span class="badge badge-${colorBadge}">${percent}%</span> (${diasCompatiblesCount} de ${totalDias} días)</li>`;
            
            if (percent < 100 && diasIncompatibles.length > 0) {
                advertenciaHtml = `
                    <div class="alert alert-warning mt-2">
                        <h6><i class="fas fa-exclamation-triangle mr-2"></i>Días excluidos automáticamente:</h6>
                        <small>Este compañero no está disponible o no tiene jornada contraria en las siguientes fechas, por lo que <strong>no se incluirán</strong> en la solicitud:</small>
                        <ul class="mb-0 mt-1 pl-3" style="max-height: 100px; overflow-y: auto;">
                            ${diasIncompatibles.map(d => `<li>${d}</li>`).join('')}
                        </ul>
                    </div>
                `;
                
                // Sobrescribir el campo hidden para enviar solo las fechas específicas compatibles
                const diasCompatiblesStr = selectedOption.getAttribute('data-dias-compatibles');
                const diasCompatibles = diasCompatiblesStr ? JSON.parse(diasCompatiblesStr) : [];
                
                // Usamos una propiedad especial en el objeto window para persistir esta decisión
                // sin alterar la selección visual de checkboxes (para no confundir al usuario)
                window.overrideDiasSeleccionados = {
                    fechas_especificas: diasCompatibles,
                    dias_semana: [] // Anular días semana para forzar uso de fechas específicas
                };
                
                document.getElementById('dias_seleccionados').value = JSON.stringify(window.overrideDiasSeleccionados);
                
            } else {
                // Restaurar selección original si es 100% compatible
                window.overrideDiasSeleccionados = null;
                actualizarDiasSeleccionados();
            }
        }
        
        container.innerHTML = `
            <div class="alert alert-info">
                <h6><i class="fas fa-info-circle mr-2"></i>Resumen del Cambio Permanente:</h6>
                <ul class="mb-0">
                    <li><strong>Período:</strong> Desde ${fechaInicio}${fechaFinText}</li>
                    <li><strong>Compañero:</strong> ${empleadoNombre}</li>
                    <li><strong>Tipo:</strong> Intercambio permanente de jornadas</li>
                    ${compatibilidadHtml}
                    <li><strong>Retorno automático:</strong> Al finalizar el período, ambos volverán a sus jornadas originales</li>
                </ul>
                ${advertenciaHtml}
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
            // Si el usuario cambia días manualmente, limpiar override (debe recalcularse)
            if (window.overrideDiasSeleccionados) {
                window.overrideDiasSeleccionados = null;
            }
            actualizarDiasSeleccionados();
            actualizarVistaPrevia();
            // Recargar empleados disponibles si hay fecha_inicio y fecha_fin seleccionadas
            const fechaInicio = fechaInicioInput ? fechaInicioInput.value : null;
            const fechaFin = fechaFinInput ? fechaFinInput.value : null;
            if (fechaInicio && fechaFin) {
                cargarEmpleadosDisponibles(fechaInicio);
                // Recargar desglose de jornadas si hay rango
                cargarJornadaActual(fechaInicio);
                // Recalcular resumen de intercambio si hay compañero seleccionado
                const empleadoId = document.getElementById('empleado_receptor').value;
                if (empleadoId) {
                    mostrarResumenIntercambio();
                }
            }
        });
    });
}

// Función para obtener días seleccionados
function obtenerDiasSeleccionados() {
    const checkboxesDiasSemana = document.querySelectorAll('input[name="dias_semana"]:checked');
    const diasSemana = Array.from(checkboxesDiasSemana).map(cb => parseInt(cb.value));
    
    return {
        dias_semana: diasSemana
    };
}

// Función para actualizar campo hidden
function actualizarDiasSeleccionados() {
    // Si hay un override activo (compatibilidad parcial), respetarlo
    if (window.overrideDiasSeleccionados && window.overrideDiasSeleccionados.fechas_especificas) {
        // Mantener el override si tiene fechas específicas válidas
        if (window.overrideDiasSeleccionados.fechas_especificas.length > 0) {
            if (diasSeleccionadosHidden) {
                diasSeleccionadosHidden.value = JSON.stringify(window.overrideDiasSeleccionados);
            }
            return; // No sobrescribir el override
        } else {
            // Si el override está vacío, limpiarlo
            window.overrideDiasSeleccionados = null;
        }
    }
    
    // Actualizar normalmente desde los checkboxes
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
    
    // Determinar el conjunto de días a enviar al backend:
    // - Si hay override por compatibilidad parcial, usarlo (incluye fechas_especificas)
    // - Si no, usar los días de semana seleccionados normalmente
    let diasParaBackend = dias;
    if (window.overrideDiasSeleccionados && window.overrideDiasSeleccionados.fechas_especificas) {
        diasParaBackend = window.overrideDiasSeleccionados;
    }
    
    if (!diasParaBackend.dias_semana.length && !(diasParaBackend.fechas_especificas && diasParaBackend.fechas_especificas.length)) {
        if (vistaPreviaFechas) {
            vistaPreviaFechas.style.display = 'none';
        }
        return;
    }
    
    // Mostrar indicador de carga
    if (listaFechasPrevia) {
        listaFechasPrevia.innerHTML = '<li class="list-group-item py-1 text-muted"><i class="fas fa-spinner fa-spin"></i> Validando fechas...</li>';
    }
    
    // Llamar al backend para previsualizar usando la misma lógica que el servidor
    let fechasGeneradas = [];
    let fechasInvalidas = [];
    
    try {
        const diasJSON = encodeURIComponent(JSON.stringify(diasParaBackend));
        const empleadoReceptor = document.getElementById('empleado_receptor');
        const empleadoReceptorId = empleadoReceptor ? empleadoReceptor.value : '';
        
        const url = `/solicitudes/previsualizar-ct-permanente/?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}&dias_seleccionados=${diasJSON}&empleado_receptor_id=${empleadoReceptorId}`;
        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        });
        
        const data = await response.json();
        
        if (!data.success) {
            // Si el backend indica que no hay días válidos u otro problema, ocultar vista previa y mostrar alerta
            if (vistaPreviaFechas) {
                vistaPreviaFechas.style.display = 'none';
            }
            if (data.message) {
                Swal.fire({
                    icon: 'warning',
                    title: 'Rango sin días válidos',
                    text: data.message,
                    confirmButtonText: 'Entendido'
                });
            }
            return;
        }
        
        fechasGeneradas = data.fechas.aplicables || [];
        const excluidas = data.fechas.excluidas || [];
        fechasInvalidas = excluidas.map(item => ({
            fecha: item.fecha,
            razon: item.razon
        }));
        // Guardar resumen informativo del rango si viene del backend
        window.__ctPermResumen = data.fechas.resumen || null;
    } catch (error) {
        console.error('Error previsualizando CT permanente:', error);
        if (vistaPreviaFechas) {
            vistaPreviaFechas.style.display = 'none';
        }
        return;
    }
    
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
        const resumen = window.__ctPermResumen;

        // Resumen UX (siempre visible arriba): ayuda a entender rangos con muchas exclusiones
        if (resumen && resumen.total_dias_rango !== undefined) {
            fechasHtml += `
                <li class="list-group-item py-2">
                    <div class="small text-muted">
                        <strong>Resumen del rango:</strong>
                        ${resumen.total_dias_rango} días en el rango ·
                        ${resumen.fines_de_semana_en_rango || 0} fines de semana ·
                        ${fechasGeneradas.length} aplicables ·
                        ${fechasInvalidas.length} excluidas
                        <div class="mt-1">
                            <small><strong>Cómo leer esto:</strong> En CT Permanente solo aplican días hábiles (lun–vie).</small>
                        </div>
                        <div class="mt-1">
                            <small>Los fines de semana se cuentan en el rango aunque, por prioridad, puedan mostrarse como Festivo/Temporada/Mantenimiento/Descanso.</small>
                        </div>
                        ${resumen.prioridad ? `<div class="mt-1"><small><strong>Prioridad de exclusión:</strong> ${resumen.prioridad}</small></div>` : ''}
                    </div>
                </li>
            `;
        }
        
        // Agrupar fechas inválidas por razón (siempre, incluso cuando hay 0 válidos)
        const fechasPorRazon = agruparFechasInvalidasPorRazon(fechasInvalidas);
        
        // Estado B: Solo válidos (sin excluidos) - Mensaje de éxito
        if (fechasGeneradas.length > 0 && fechasInvalidas.length === 0) {
            fechasHtml = `
                <li class="list-group-item py-3 bg-success text-white">
                    <div class="d-flex align-items-center">
                        <i class="fas fa-check-circle mr-2 fa-2x"></i>
                        <div>
                            <h6 class="mb-1"><strong>Todo OK</strong></h6>
                            <p class="mb-0">Todas las fechas seleccionadas son válidas para el cambio permanente.</p>
                        </div>
                    </div>
                </li>
            `;
            
            // Agregar lista de fechas válidas
            fechasHtml += fechasGeneradas.slice(0, 20).map(fecha => {
                const fechaObj = new Date(fecha + 'T00:00:00');
                const fechaFormateada = fechaObj.toLocaleDateString('es-ES', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
                return `<li class="list-group-item py-1"><i class="fas fa-check-circle text-success mr-2"></i>${fechaFormateada}</li>`;
            }).join('');
            
            if (fechasGeneradas.length > 20) {
                fechasHtml += `<li class="list-group-item py-1 text-muted">... y ${fechasGeneradas.length - 20} días más</li>`;
            }
        }
        
        // Estado A: Hay válidos + excluidos
        if (fechasGeneradas.length > 0 && fechasInvalidas.length > 0) {
            // Lista de fechas válidas
            fechasHtml = fechasGeneradas.slice(0, 20).map(fecha => {
                const fechaObj = new Date(fecha + 'T00:00:00');
                const fechaFormateada = fechaObj.toLocaleDateString('es-ES', { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' });
                return `<li class="list-group-item py-1"><i class="fas fa-check-circle text-success mr-2"></i>${fechaFormateada}</li>`;
            }).join('');
            
            if (fechasGeneradas.length > 20) {
                fechasHtml += `<li class="list-group-item py-1 text-muted">... y ${fechasGeneradas.length - 20} días más</li>`;
            }
            
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
                <li class="list-group-item py-3">
                    <div class="alert alert-success mb-2">
                        <h6 class="mb-1">
                            <i class="fas fa-check-circle mr-2"></i>
                            <strong>Fechas válidas:</strong> ${fechasGeneradas.length} día${fechasGeneradas.length > 1 ? 's' : ''} se aplicarán al cambio permanente.
                        </h6>
                    </div>
                    <div class="mt-3">
                        <h6 class="mb-2">
                            <i class="fas fa-exclamation-triangle text-warning mr-2"></i>
                            <strong>Fechas excluidas:</strong>
                        </h6>
                        <small class="text-muted d-block mb-2">Estas fechas no se aplicarán porque son inválidas según las reglas de negocio.</small>
                        ${seccionesExcluidas}
                    </div>
                </li>
            `;
        }
        
        // Mostrar mensaje mejorado cuando no hay fechas válidas
        if (fechasGeneradas.length === 0 && fechasInvalidas.length > 0) {
            // Detectar motivo principal
            const motivoPrincipal = detectarMotivoPrincipal(fechasPorRazon);
            
            // Obtener nombres de días seleccionados
            const nombresDias = obtenerNombresDiasSeleccionados(dias);
            
            // Formatear rango de fechas
            const fechaInicioObj = new Date(fechaInicio + 'T00:00:00');
            const fechaFinObj = new Date(fechaFin + 'T00:00:00');
            const rangoFormateado = fechaInicioObj.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' }) + 
                                   ' – ' + 
                                   fechaFinObj.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
            
            // Construir mensaje principal
            let mensajePrincipal = `
                <div class="alert alert-danger mb-3">
                    <h6 class="mb-2">
                        <i class="fas fa-exclamation-triangle mr-2"></i>
                        <strong>No hay fechas válidas para este cambio permanente</strong>
                    </h6>
                    <p class="mb-2">
                        En el rango <strong>${rangoFormateado}</strong>, todos los <strong>${nombresDias}</strong> se descartaron por las reglas de negocio.
                    </p>
            `;
            
            // Agregar motivo principal si es significativo (más del 50%)
            if (motivoPrincipal && motivoPrincipal.porcentaje >= 50) {
                let mensajeMotivo = '';
                if (motivoPrincipal.razon === 'Temporada') {
                    mensajeMotivo = `
                        <div class="alert alert-warning mb-0 mt-2">
                            <strong><i class="fas fa-calendar-alt mr-2"></i>Motivo principal:</strong> 
                            <strong>Días de TEMPORADA</strong> (${motivoPrincipal.dias} de ${motivoPrincipal.total} días, ${motivoPrincipal.porcentaje}%).
                            <br>
                            <small class="mt-1 d-block">
                                Por política del parque, <strong>no se permiten cambios permanentes en días de temporada</strong>.
                            </small>
                        </div>
                    `;
                } else if (motivoPrincipal.razon === 'Festivo') {
                    mensajeMotivo = `
                        <div class="alert alert-warning mb-0 mt-2">
                            <strong><i class="fas fa-calendar-check mr-2"></i>Motivo principal:</strong> 
                            <strong>Días FESTIVOS</strong> (${motivoPrincipal.dias} de ${motivoPrincipal.total} días, ${motivoPrincipal.porcentaje}%).
                            <br>
                            <small class="mt-1 d-block">
                                No se permiten cambios permanentes en días festivos.
                            </small>
                        </div>
                    `;
                } else {
                    mensajeMotivo = `
                        <div class="alert alert-info mb-0 mt-2">
                            <strong>Motivo principal:</strong> 
                            <strong>${motivoPrincipal.razon}</strong> (${motivoPrincipal.dias} de ${motivoPrincipal.total} días, ${motivoPrincipal.porcentaje}%).
                        </div>
                    `;
                }
                mensajePrincipal += mensajeMotivo;
            } else if (motivoPrincipal) {
                // Si no hay un motivo dominante, mostrar resumen de todos
                const motivos = Object.entries(fechasPorRazon)
                    .map(([razon, fechas]) => `${razon}: ${fechas.length} día${fechas.length > 1 ? 's' : ''}`)
                    .join(', ');
                mensajePrincipal += `
                    <div class="alert alert-info mb-0 mt-2">
                        <strong>Motivos detectados:</strong> ${motivos}
                    </div>
                `;
            }
            
            mensajePrincipal += `</div>`;
            
            // Generar secciones de fechas excluidas (igual que cuando hay válidos)
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
            
            fechasHtml = `
                <li class="list-group-item py-3">
                    ${mensajePrincipal}
                    <div class="mt-3">
                        <h6 class="mb-2">
                            <i class="fas fa-list-ul mr-2"></i>
                            <strong>Fechas excluidas (detalle por motivo):</strong>
                        </h6>
                        <small class="text-muted d-block mb-3">
                            Estas fechas no se aplicarán porque son inválidas según las reglas de negocio.
                        </small>
                        ${seccionesExcluidas}
                    </div>
                </li>
            `;
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
        // Las claves deben coincidir con _PRIORIDAD_RAZONES_CT_PERMANENTE (cambios_permanentes_helper.py).
        'Fines de semana': '<i class="fas fa-calendar-times text-muted mr-2"></i>',
        'Fecha pasada': '<i class="fas fa-history text-muted mr-2"></i>',
        'Festivo': '<i class="fas fa-calendar-check text-danger mr-2"></i>',
        'Mantenimiento': '<i class="fas fa-tools text-warning mr-2"></i>',
        'Temporada': '<i class="fas fa-calendar-alt text-warning mr-2"></i>',
        'Descanso Solicitante': '<i class="fas fa-moon text-secondary mr-2"></i>',
        'Descanso Receptor': '<i class="fas fa-user-slash text-secondary mr-2"></i>',
        'Día libre Solicitante': '<i class="fas fa-moon text-secondary mr-2"></i>',
        'Día libre Receptor': '<i class="fas fa-user-slash text-secondary mr-2"></i>',
        'Doblada Solicitante': '<i class="fas fa-clone text-info mr-2"></i>',
        'Doblada Receptor': '<i class="fas fa-clone text-info mr-2"></i>',
        'Cambio Previo Solicitante': '<i class="fas fa-exchange-alt text-info mr-2"></i>',
        'Cambio Previo Receptor': '<i class="fas fa-exchange-alt text-info mr-2"></i>',
        'Sin jornada contraria': '<i class="fas fa-not-equal text-warning mr-2"></i>'
    };
    return iconos[razon] || '<i class="fas fa-ban text-danger mr-2"></i>';
}

// Función helper para obtener color según razón de exclusión
function obtenerColorRazon(razon) {
    const colores = {
        // Las claves deben coincidir con _PRIORIDAD_RAZONES_CT_PERMANENTE (cambios_permanentes_helper.py).
        'Fines de semana': 'muted',
        'Fecha pasada': 'muted',
        'Festivo': 'danger',
        'Mantenimiento': 'warning',
        'Temporada': 'warning',
        'Descanso Solicitante': 'secondary',
        'Descanso Receptor': 'secondary',
        'Día libre Solicitante': 'secondary',
        'Día libre Receptor': 'secondary',
        'Doblada Solicitante': 'info',
        'Doblada Receptor': 'info',
        'Cambio Previo Solicitante': 'info',
        'Cambio Previo Receptor': 'info',
        'Sin jornada contraria': 'warning'
    };
    return colores[razon] || 'danger';
}

// Función para agrupar fechas inválidas por razón
function agruparFechasInvalidasPorRazon(fechasInvalidas) {
    const agrupadas = {};
    fechasInvalidas.forEach(item => {
        if (!agrupadas[item.razon]) {
            agrupadas[item.razon] = [];
        }
        agrupadas[item.razon].push(item.fecha);
    });
    
    // Ordenar fechas dentro de cada razón
    Object.keys(agrupadas).forEach(razon => {
        agrupadas[razon].sort();
    });
    
    return agrupadas;
}

// Función para detectar motivo principal cuando hay 0 válidos
function detectarMotivoPrincipal(fechasInvalidasAgrupadas) {
    if (Object.keys(fechasInvalidasAgrupadas).length === 0) {
        return null;
    }
    
    // Calcular total de días inválidos
    const totalInvalidos = Object.values(fechasInvalidasAgrupadas).reduce((sum, arr) => sum + arr.length, 0);
    
    // Encontrar la razón con más días
    let motivoPrincipal = null;
    let maxDias = 0;
    let porcentaje = 0;
    
    Object.entries(fechasInvalidasAgrupadas).forEach(([razon, fechas]) => {
        if (fechas.length > maxDias) {
            maxDias = fechas.length;
            motivoPrincipal = razon;
            porcentaje = Math.round((fechas.length / totalInvalidos) * 100);
        }
    });
    
    return {
        razon: motivoPrincipal,
        dias: maxDias,
        porcentaje: porcentaje,
        total: totalInvalidos
    };
}

// Función para obtener nombres de días de semana en español
function obtenerNombresDiasSeleccionados(diasSeleccionados) {
    const nombresDias = {
        0: 'lunes',
        1: 'martes',
        2: 'miércoles',
        3: 'jueves',
        4: 'viernes'
    };
    
    const dias = diasSeleccionados.dias_semana || [];
    const nombres = dias.map(d => nombresDias[d]).filter(n => n);
    
    if (nombres.length === 0) return '';
    if (nombres.length === 1) return nombres[0];
    if (nombres.length === 2) return nombres.join(' y ');
    return nombres.slice(0, -1).join(', ') + ' y ' + nombres[nombres.length - 1];
}

// Cache para festivos, mantenimiento y temporadas (se carga una vez)
let cacheFestivos = null;
let cacheMantenimiento = null;
let cacheTemporadas = null;
let cacheJornadaSolicitante = null;
let cacheJornadaReceptor = null;

// Función para cargar jornada del solicitante
function cargarJornadaSolicitante() {
    if (!window.solicitanteId || !fechaInicioInput || !fechaInicioInput.value) {
        return Promise.resolve();
    }
    
    return fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fechaInicioInput.value}`)
        .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
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
        .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
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

// Función para cargar festivos, mantenimiento y temporadas
function cargarFestivosMantenimientoYTemporadas() {
    if (cacheFestivos !== null && cacheMantenimiento !== null && cacheTemporadas !== null) {
        return Promise.resolve();
    }
    
    // Obtener año del rango de fechas para cargar temporadas
    const fechaInicio = fechaInicioInput ? fechaInicioInput.value : null;
    const fechaFin = fechaFinInput ? fechaFinInput.value : null;
    let anio = new Date().getFullYear();
    
    if (fechaInicio) {
        anio = new Date(fechaInicio + 'T00:00:00').getFullYear();
    } else if (fechaFin) {
        anio = new Date(fechaFin + 'T00:00:00').getFullYear();
    }
    
    return Promise.all([
        window.DatepickerFestivos ? window.DatepickerFestivos.cargarDiasFestivos() : Promise.resolve(new Map()),
        window.DatepickerFestivos ? window.DatepickerFestivos.cargarDiasMantenimiento() : Promise.resolve(new Map()),
        cargarTemporadas(anio)
    ]).then(([festivos, mantenimiento, temporadas]) => {
        cacheFestivos = festivos;
        cacheMantenimiento = mantenimiento;
        cacheTemporadas = temporadas;
    });
}

// Función para cargar temporadas de un año específico
function cargarTemporadas(anio) {
    return fetch(`/turnos/api/dias-temporada/?anio=${anio}`)
        .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
        .then(data => {
            // El endpoint devuelve {por_mes: {mes: [dias]}, ...} o {temporadas: [...], por_mes: {...}}
            if (data.por_mes) {
                // Convertir estructura {mes: [dias]} a Set de fechas YYYY-MM-DD
                const temporadasSet = new Set();
                for (const mes in data.por_mes) {
                    const dias = data.por_mes[mes];
                    if (Array.isArray(dias)) {
                        dias.forEach(dia => {
                            const fechaStr = `${anio}-${String(mes).padStart(2, '0')}-${String(dia).padStart(2, '0')}`;
                            temporadasSet.add(fechaStr);
                        });
                    }
                }
                return temporadasSet;
            }
            // Si no hay por_mes, intentar con temporadas (array de objetos con fecha)
            if (data.temporadas && Array.isArray(data.temporadas)) {
                const temporadasSet = new Set();
                data.temporadas.forEach(temp => {
                    if (temp.fecha) {
                        temporadasSet.add(temp.fecha);
                    }
                });
                return temporadasSet;
            }
            return new Set();
        })
        .catch(error => {
            console.error('Error cargando temporadas:', error);
            return new Set();
        });
}

// Función para enviar la solicitud por AJAX
function enviarSolicitudCTPermanente() {
    const form = document.getElementById('ctPermanenteForm');
    const formData = new FormData(form);
    
    // Asegurar que días seleccionados estén actualizados
    // Si hay override activo, asegurar que esté en el campo hidden
    if (window.overrideDiasSeleccionados && window.overrideDiasSeleccionados.fechas_especificas) {
        if (window.overrideDiasSeleccionados.fechas_especificas.length > 0) {
            // Mantener el override si tiene fechas válidas
            const diasHidden = document.getElementById('dias_seleccionados');
            if (diasHidden) {
                diasHidden.value = JSON.stringify(window.overrideDiasSeleccionados);
                // Actualizar FormData con el valor correcto
                formData.set('dias_seleccionados', diasHidden.value);
            }
        } else {
            // Si el override está vacío, usar días normales
            actualizarDiasSeleccionados();
        }
    } else {
        // Actualizar normalmente desde checkboxes
        actualizarDiasSeleccionados();
        // Asegurar que el FormData tenga el valor actualizado
        const diasHidden = document.getElementById('dias_seleccionados');
        if (diasHidden) {
            formData.set('dias_seleccionados', diasHidden.value);
        }
    }
    
    // Mostrar indicador de carga
    const submitButton = form.querySelector('button[type="submit"]');
    const originalText = submitButton.innerHTML;
    submitButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Enviando...';
    submitButton.disabled = true;
    // Loading bloqueante: evita doble envío. Cualquier Swal posterior lo reemplaza.
    LoadingUI.mostrar('Enviando solicitud...');

    LoadingUI.fetchLimitado('/solicitudes/procesar-solicitud/', {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        }
    })
    .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
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
        } else if (window.RestriccionAdvertencia && data.code === 'advertencia_restriccion') {
            // Advertencia (no bloqueo) por restricción médica: avisar y reenviar al confirmar
            RestriccionAdvertencia.mostrar(data.restricciones, function () {
                LoadingUI.mostrar('Enviando solicitud...');
                formData.set('confirmar_restriccion', '1');
                LoadingUI.fetchLimitado('/solicitudes/procesar-solicitud/', {
                    method: 'POST', body: formData, headers: { 'X-Requested-With': 'XMLHttpRequest' }
                })
                .then(r => r.json().catch(() => ({})))
                .then(d2 => {
                    if (d2 && d2.success) {
                        Swal.fire({ icon: 'success', title: '¡Solicitud enviada!', text: d2.message || 'Solicitud enviada correctamente.' })
                            .then(() => { window.location.href = '/solicitudes/'; });
                    } else {
                        Swal.fire({ icon: 'error', title: 'No se pudo enviar', text: (d2 && (d2.error || d2.message)) || 'Error al procesar la solicitud.' });
                    }
                })
                .catch((e) => {
                    const av = LoadingUI.avisoDeFallo(e, 'Ocurrió un error de red.');
                    Swal.fire({
                        icon: av.esTiempoAgotado ? 'warning' : 'error',
                        title: av.titulo || 'Error',
                        html: av.esTiempoAgotado ? av.texto : CodigoReferencia.htmlMensaje(av.texto)
                    });
                });
            });
        } else {
            // Mostrar error
            Swal.fire({
                icon: 'error',
                title: 'Error al enviar solicitud',
                text: data.error,
                confirmButtonText: 'Entendido',
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
        const aviso = LoadingUI.avisoDeFallo(
            error, 'No se pudo enviar la solicitud. Inténtalo de nuevo.');
        Swal.fire({
            icon: aviso.esTiempoAgotado ? 'warning' : 'error',
            title: aviso.titulo || 'Error de conexión',
            text: aviso.texto,
            // Tras un corte por tiempo la solicitud puede haberse creado: invitar a
            // "Reintentar" sería empujar al duplicado.
            confirmButtonText: aviso.esTiempoAgotado ? 'Entendido' : 'Reintentar',
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
