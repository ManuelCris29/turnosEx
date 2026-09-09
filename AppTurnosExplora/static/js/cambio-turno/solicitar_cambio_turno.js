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

        // Realizar petición AJAX
        fetch(url, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            empleadoSelect.innerHTML = '<option value="">Selecciona un compañero...</option>';

            if (data.success === false) {
                // Error del servidor
                const mensajeError = data.error || 'Error al cargar compañeros disponibles';
                empleadoSelect.innerHTML = `<option value="">${mensajeError}</option>`;
                console.error('Error al cargar compañeros disponibles:', mensajeError);
            } else if (data.empleados && Array.isArray(data.empleados) && data.empleados.length > 0) {
                data.empleados.forEach(empleado => {
                    const option = document.createElement('option');
                    option.value = empleado.id;
                    option.textContent = `${empleado.nombre} ${empleado.apellido}`;
                    empleadoSelect.appendChild(option);
                });
            } else {
                // No hay empleados disponibles
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
        // Un turno es "predeterminado" si es virtual (sin registro en BD) o si el registro
        // no fue creado por ningún tipo de cambio (tipo_cambio=null → turno del horario importado).
        const esJornadaPredeterminada = turno.es_turno_virtual || (!turno.tipo_cambio && turno.id !== null);
        let badgeClass = esJornadaPredeterminada ? 'badge-info' : 'badge-success';
        let badgeText = esJornadaPredeterminada ? 'Jornada Predeterminada' : 'Turno Asignado';
        // Si el día es virtual, `fuente` (estado_dia) dice QUÉ capa lo resolvió. Sin esto
        // un día completo por temporada o por alternancia de finde se etiquetaba
        // "Jornada Predeterminada", que es engañoso: no es la jornada base del empleado.
        if (esJornadaPredeterminada && turno.fuente) {
            const etiquetasPorFuente = {
                temporada: ['badge-warning', 'Día completo por temporada'],
                festivo: ['badge-warning', 'Día completo por festivo'],
                alternancia: ['badge-warning', 'Fin de semana (alternancia)'],
                manual: ['badge-warning', 'Fin de semana (asignación del supervisor)'],
                mantenimiento: ['badge-warning', 'Lunes de mantenimiento'],
                solicitud: ['badge-success', 'Por solicitud aprobada'],
            };
            const etiqueta = etiquetasPorFuente[turno.fuente];
            if (etiqueta) {
                [badgeClass, badgeText] = etiqueta;
            } else if (turno.fuente === 'base' && turno.jornada === 'DOBLADA') {
                // El endpoint puede forzar DOBLADA por festivo/rotación sin tocar `fuente`.
                [badgeClass, badgeText] = ['badge-warning', 'Día completo'];
            }
        }
        detallesElem.innerHTML = `
            <div class="card mb-3">
                <div class="card-body">
                    <div class="row align-items-center mb-2">
                        <div class="col-12 col-md-6 mb-2 mb-md-0">
                            <strong>Jornada:</strong> <span translate="no">${turno.jornada || '-'}</span>
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
        // Incluir tipo_solicitud_id para que el backend pueda aplicar reglas específicas (ej: descanso por doblada)
        const tipoSolicitudInput = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudId = tipoSolicitudInput ? tipoSolicitudInput.value : '';
        const urlExplorador = `/solicitudes/obtener-turno-explorador/?fecha=${fecha}&explorador_id=${exploradorId}${tipoSolicitudId ? `&tipo_solicitud_id=${tipoSolicitudId}` : ''}`;
        fetch(urlExplorador, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
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
        // Incluir tipo_solicitud_id para que el backend pueda aplicar reglas específicas (ej: descanso por doblada)
        const tipoSolicitudInput = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudId = tipoSolicitudInput ? tipoSolicitudInput.value : '';
        const urlSolicitante = `/solicitudes/obtener-turno-explorador/?fecha=${fecha}&explorador_id=${solicitanteId}${tipoSolicitudId ? `&tipo_solicitud_id=${tipoSolicitudId}` : ''}`;
        fetch(urlSolicitante, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
        .then(data => {
            if (data.esta_descansando && data.descanso_info) {
                const info = data.descanso_info;
                let razon;
                if (info.tipo === 'descanso_semana') {
                    razon = info.motivo === 'mantenimiento'
                        ? 'Es tu día de descanso por mantenimiento.'
                        : 'Es tu día de descanso de la semana (temporada).';
                } else if (info.tipo === 'cedio') {
                    razon = `Cediste tu jornada del ${info.fecha_cesion || ''} a ${info.companero_nombre}.`;
                } else {
                    razon = `Estás en descanso como pago de la doblada realizada por ${info.companero_nombre}.`;
                }
                turnoSolicitanteDetalles.innerHTML = `
                    <div class="alert alert-info mb-0">
                        <i class="fas fa-bed mr-2"></i>
                        <strong>Estás Descansando</strong>
                        <p class="mb-1 mt-1">${razon}</p>
                        <small class="text-muted">
                            <i class="fas fa-info-circle"></i>
                            No puedes solicitar un cambio de turno para esta fecha mientras estés en descanso.
                        </small>
                    </div>`;
                salasSolicitanteDetalles.innerHTML = '';
                empleadoSelect.innerHTML = '<option value=\"\">No disponible — estás en descanso</option>';
                empleadoSelect.disabled = true;
            } else {
                renderTurnoYSalas(data.turno, turnoSolicitanteDetalles, salasSolicitanteDetalles);
            }
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
        
        // Validación genérica de campos requeridos
        if (window.ValidadoresSolicitudes) {
            const tipoNombre = window.ValidadoresSolicitudes.obtenerTipoSolicitud(form) || 
                              document.querySelector('[data-tipo-nombre]')?.getAttribute('data-tipo-nombre');
            
        if (tipoNombre) {
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
                text: 'Debes ingresar un comentario para enviar la solicitud.',
                confirmButtonText: 'Entendido'
            }).then(() => {
                if (comentariosInput) {
                    comentariosInput.focus();
                }
            });
            return;
        }
        }
        
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
                    procederConEnvio(form, false);
                }
            }).catch(error => {
                console.error('Error verificando día de mantenimiento:', error);
                // En caso de error, proceder con el envío (la validación backend lo manejará)
                procederConEnvio(form, false);
            });
        } else {
            // Si no se puede verificar, proceder con el envío (la validación backend lo manejará)
            procederConEnvio(form, false);
        }
    }
    
    // Función auxiliar para proceder con el envío del formulario
    function procederConEnvio(form, confirmarRestriccion) {
        const formData = new FormData(form);
        if (confirmarRestriccion) formData.set('confirmar_restriccion', '1');

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
            } else if (window.RestriccionAdvertencia &&
                       RestriccionAdvertencia.manejar(data, function () { procederConEnvio(form, true); })) {
                // Advertencia (no bloqueo) por restricción médica: ya se mostró el aviso.
                return;
            } else {
                // Mostrar error
                const mensajeError = CodigoReferencia.mensaje(data.error || 'Ocurrió un error al procesar la solicitud');

                // Detectar errores relacionados con jornada doblada / uso incorrecto de CT
                const errorDoblada = mensajeError.toLowerCase().includes('doblada') &&
                                     mensajeError.toLowerCase().includes('solicitud de dobladas');

                // Si el error es sobre día de mantenimiento, destacarlo
                const esErrorMantenimiento = !errorDoblada &&
                    mensajeError.toLowerCase().includes('mantenimiento');

                if (errorDoblada) {
                    Swal.fire({
                        icon: 'info',
                        title: 'Solicitud de Doblada requerida',
                        text: mensajeError,
                        confirmButtonText: 'Entendido',
                        timer: 8000,
                        timerProgressBar: true,
                        showConfirmButton: true,
                        position: 'center',
                        customClass: {
                            popup: 'swal2-error-popup'
                        }
                    });
                } else {
                    Swal.fire({
                        icon: 'error',
                        title: esErrorMantenimiento ? 'Día de Mantenimiento' : 'Error al enviar solicitud',
                        text: mensajeError,
                        confirmButtonText: 'Entendido',
                        showConfirmButton: true,
                        position: 'center',
                        customClass: {
                            popup: 'swal2-error-popup'
                        }
                    });
                }
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
        // Permitir festivos y temporada; bloquear domingos, sábados y mantenimiento
        window.DatepickerFestivos.inicializar({
            input: fechaInput,
            indicadorFestivo: indicadorFestivo,
            descripcionFestivo: descripcionFestivo,
            bloquearDiasEspeciales: true,
            bloquearSabados: true, // Para CT Sencillo, también bloquear sábados
            permitirFestivos: true,
            permitirTemporada: true, // En temporada sí se pueden hacer cambios de turno sencillos
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
            // Cargar compañeros disponibles para la fecha precargada (la actual). Sin esto,
            // la lista solo se llenaba al CAMBIAR la fecha (onDateChange).
            actualizarEmpleadosDisponibles();
            cargarInformacionSolicitante();
            verificarCambioAprobado();
        }
    }
}); 