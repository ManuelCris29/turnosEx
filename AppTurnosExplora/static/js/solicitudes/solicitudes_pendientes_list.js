// Literales servidos por la plantilla (ver window.MSG_COMENTARIOS): el aviso del
// navegador debe ser palabra por palabra el que devuelve el servidor para el mismo fallo.
// Literales servidos por la plantilla. El respaldo sale del helper común (genérico a
// propósito): repetir aquí el texto exacto recrearía la copia que este cambio elimina.
const MSG = window.MSG_COMENTARIOS || (function () {
    const r = window.ComentarioObligatorio.RESPALDO;
    return { comentario: r, motivo: r };
})();


let solicitudActual = null;
let accionActual = null;
let rolActual = null;

/**
 * Muestra por qué falló una cancelación. (Gemela de la de `mis_solicitudes_list.js`: las dos
 * pantallas golpean el MISMO endpoint, así que el bloqueo debe leerse igual en ambas.)
 *
 * Dos cosas que no eran obvias:
 * - `json_error` responde el motivo en `error`, NO en `message`. Leer solo `message` dejaba
 *   `undefined` y el motivo real (guardia LIFO, ventana expirada, conflicto de jornadas)
 *   nunca llegaba al usuario.
 * - Los bloqueos por guardia explican qué pasó y qué hacer a continuación. No son un "Error"
 *   y no pueden autocerrarse por temporizador antes de que dé tiempo a leerlos.
 */
function mostrarErrorCancelacion(data, textoPorDefecto) {
    const esGuardia = data.code === 'conflicto_integridad'
                   || data.code === 'cambio_mas_reciente'
                   || data.code === 'ventana_expirada';
    Swal.fire({
        icon: esGuardia ? 'warning' : 'error',
        title: esGuardia ? 'No se puede cancelar' : 'Error',
        text: data.error || data.message || textoPorDefecto,
        // Ningún motivo de fallo se autocierra: explican qué pasó y qué hacer, y a los 4 s
        // desaparecían antes de que diera tiempo a leerlos. Lo cierra quien lo lee.
        showConfirmButton: true,
        confirmButtonText: 'Entendido'
    });
}

function aprobarSolicitudReceptor(solicitudId) {
    solicitudActual = solicitudId;
    accionActual = 'aprobar';
    rolActual = 'receptor';
    $('#accionModalTitle').text('Aprobar Solicitud como Receptor');
    $('#accionSolicitudModal').modal('show');
}

function rechazarSolicitudReceptor(solicitudId) {
    solicitudActual = solicitudId;
    accionActual = 'rechazar';
    rolActual = 'receptor';
    $('#accionModalTitle').text('Rechazar Solicitud como Receptor');
    $('#accionSolicitudModal').modal('show');
}

function aprobarSolicitudSupervisor(solicitudId) {
    solicitudActual = solicitudId;
    accionActual = 'aprobar';
    rolActual = 'supervisor';
    $('#accionModalTitle').text('Aprobar Solicitud como Supervisor');
    $('#accionSolicitudModal').modal('show');
}

function rechazarSolicitudSupervisor(solicitudId) {
    solicitudActual = solicitudId;
    accionActual = 'rechazar';
    rolActual = 'supervisor';
    $('#accionModalTitle').text('Rechazar Solicitud como Supervisor');
    $('#accionSolicitudModal').modal('show');
}

function aprobarSolicitudAmbos(solicitudId) {
    Swal.fire({
        title: '¿Aprobar como Receptor y Supervisor?',
        text: 'Se registrarán ambas aprobaciones y la solicitud quedará aprobada.',
        icon: 'question',
        showCancelButton: true,
        confirmButtonColor: '#28a745',
        cancelButtonColor: '#6c757d',
        confirmButtonText: 'Sí, aprobar ambos',
        cancelButtonText: 'Cancelar'
    }).then((result) => {
        if (result.isConfirmed) {
            const formData = new FormData();
            formData.append('csrfmiddlewaretoken', window.CSRF_TOKEN);
            // Loading bloqueante: evita doble envío. Cualquier Swal posterior lo reemplaza.
            LoadingUI.mostrar('Aprobando solicitud...');

            fetch(`/solicitudes/aprobar-solicitud-ambos/${solicitudId}/`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                }
            })
            .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        icon: 'success',
                        title: '¡Aprobado!',
                        text: data.message,
                        timer: 2500,
                        timerProgressBar: true,
                        showConfirmButton: false,
                        position: 'top-end',
                        toast: true
                    }).then(() => {
                        location.reload();
                    });
                } else {
                    Swal.fire({
                        icon: 'error',
                        title: 'Error',
                        text: data.message || 'No se pudo aprobar en ambos roles',
                        showConfirmButton: true,
                        confirmButtonText: 'Entendido'
                    });
                }
            })
            .catch(error => {
                console.error('Error:', error);
                Swal.fire({
                    icon: 'error',
                    title: 'Error de conexión',
                    text: 'No se pudo completar la acción. Inténtalo de nuevo.'
                });
            });
        }
    });
}

// Respuesta del receptor a una petición de cancelación. Aprobar revierte los turnos;
// rechazar deja el cambio firme y no se puede volver a pedir, así que se advierte.
function responderCancelacion(solicitudId, aprobar) {
    const config = aprobar
        ? {
            title: 'Aprobar la cancelación',
            html: `Los turnos de ambos volverán a como estaban antes del cambio.<br><br>
                   Esta operación no se puede deshacer.`,
            confirmButtonText: 'Sí, cancelar el cambio',
            confirmButtonColor: '#dc3545',
        }
        : {
            title: 'Rechazar la cancelación',
            html: `El cambio seguirá vigente y quedará <strong>firme</strong>:
                   tu compañero no podrá volver a pedir su cancelación.`,
            confirmButtonText: 'Sí, mantener el cambio',
            confirmButtonColor: '#198754',
        };

    ComentarioObligatorio.swal({
        ...config,
        icon: 'warning',
        etiqueta: 'Comentario',
        marcador: 'Explica tu decisión...',
        error: MSG.comentario,
        showCancelButton: true,
        cancelButtonColor: '#6c757d',
        cancelButtonText: 'Volver'
    }).then((result) => {
        if (!result.isConfirmed) return;

        const formData = new FormData();
        formData.append('csrfmiddlewaretoken', window.CSRF_TOKEN);
        formData.append('accion', aprobar ? 'aprobar' : 'rechazar');
        formData.append('comentario_respuesta', (result.value || '').trim());
        LoadingUI.mostrar(aprobar ? 'Cancelando y revirtiendo cambios...' : 'Registrando tu respuesta...');

        fetch(`/solicitudes/cancelar-solicitud/${solicitudId}/responder/`, {
            method: 'POST',
            body: formData,
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
        .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
        .then(data => {
            if (data.success) {
                Swal.fire({
                    icon: 'success',
                    title: aprobar ? 'Cancelacion aprobada' : 'Cancelación rechazada',
                    text: data.message,
                    confirmButtonText: 'Entendido'
                }).then(() => { location.reload(); });
            } else {
                mostrarErrorCancelacion(data, 'No se pudo registrar tu respuesta.');
            }
        })
        .catch(() => {
            Swal.fire({
                icon: 'error',
                title: 'Error de conexión',
                text: 'No se pudo registrar tu respuesta. Inténtalo de nuevo.',
            });
        });
    });
}

function cancelarSolicitud(solicitudId) {
    ComentarioObligatorio.swal({
        title: '¿Cancelar solicitud?',
        text: 'Esta acción cancelará la solicitud. ¿Estás seguro?',
        icon: 'warning',
        etiqueta: 'Motivo',
        marcador: '¿Por qué la cancelas?',
        error: MSG.motivo,
        showCancelButton: true,
        confirmButtonColor: '#ffc107',
        cancelButtonColor: '#6c757d',
        confirmButtonText: 'Sí, cancelar',
        cancelButtonText: 'No, mantener'
    }).then((result) => {
        if (result.isConfirmed) {
            const formData = new FormData();
            formData.append('csrfmiddlewaretoken', window.CSRF_TOKEN);
            formData.append('motivo', (result.value || '').trim());
            // Loading bloqueante: evita doble envío. Cualquier Swal posterior lo reemplaza.
            LoadingUI.mostrar('Cancelando solicitud...');

            fetch(`/solicitudes/cancelar-solicitud/${solicitudId}/`, {
                method: 'POST',
                body: formData,
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                }
            })
            .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
            .then(data => {
                if (data.success) {
                    Swal.fire({
                        icon: 'success',
                        title: '¡Solicitud cancelada!',
                        text: data.message,
                        timer: 3000,
                        timerProgressBar: true,
                        showConfirmButton: false,
                        position: 'top-end',
                        toast: true
                    }).then(() => {
                        location.reload();
                    });
                } else {
                    mostrarErrorCancelacion(data, 'Error al cancelar la solicitud');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                Swal.fire({
                    icon: 'error',
                    title: 'Error de conexión',
                    text: 'No se pudo cancelar la solicitud. Inténtalo de nuevo.',
                    showConfirmButton: true,
                    confirmButtonText: 'Reintentar'
                });
            });
        }
    });
}

function verDetalleSolicitud(solicitudId) {
    // Mostrar modal con loading
    const modalContent = document.getElementById('detalleSolicitudContent');
    modalContent.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"><span class="sr-only">Cargando...</span></div><p class="mt-3">Cargando detalles de la solicitud...</p></div>';
    $('#detalleSolicitudModal').modal('show');
    
    // Hacer llamada AJAX para obtener detalles
    fetch(`/solicitudes/obtener-detalle-solicitud/${solicitudId}/`, {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Los datos están directamente en el objeto data, no en data.data
            renderizarDetalleSolicitud(data);
        } else {
            modalContent.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-triangle"></i> ${data.error || data.message || 'Error al cargar los detalles'}</div>`;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        modalContent.innerHTML = `<div class="alert alert-danger"><i class="fas fa-exclamation-triangle"></i> Error de conexión. Inténtalo de nuevo.</div>`;
    });
}

function agruparFechasExcluidas(fechasExcluidas) {
    // Agrupar fechas por razón
    const agrupadas = {};
    fechasExcluidas.forEach(item => {
        const razon = item.razon || 'Sin razón';
        if (!agrupadas[razon]) {
            agrupadas[razon] = [];
        }
        agrupadas[razon].push(item.fecha);
    });
    
    // Generar HTML agrupado
    let html = '';
    const iconosRazon = {
        'Festivo': '<i class="fas fa-calendar-times text-danger mr-1"></i>',
        'Mantenimiento': '<i class="fas fa-tools text-warning mr-1"></i>',
        'Temporada': '<i class="fas fa-calendar-alt text-info mr-1"></i>',
        'Descanso Solicitante': '<i class="fas fa-user-slash text-secondary mr-1"></i>',
        'Descanso Receptor': '<i class="fas fa-user-slash text-secondary mr-1"></i>',
        'Domingo': '<i class="fas fa-calendar-day text-muted mr-1"></i>',
        'Sábado': '<i class="fas fa-calendar-day text-muted mr-1"></i>',
        'Fines de semana': '<i class="fas fa-calendar-day text-muted mr-1"></i>'
    };
    
    const coloresRazon = {
        'Festivo': 'danger',
        'Mantenimiento': 'warning',
        'Temporada': 'info',
        'Descanso Solicitante': 'secondary',
        'Descanso Receptor': 'secondary',
        'Domingo': 'muted',
        'Sábado': 'muted',
        'Fines de semana': 'muted'
    };
    
    Object.keys(agrupadas).forEach(razon => {
        const fechas = agrupadas[razon];
        const icono = iconosRazon[razon] || '<i class="fas fa-ban text-muted mr-1"></i>';
        const color = coloresRazon[razon] || 'muted';
        const blockId = `excluidas_${razon.replace(/\s+/g, '_').replace(/[^\w]/g, '')}`;
        const esFinde = razon === 'Fines de semana';

        if (esFinde) {
            html += `
                <div class="mb-2">
                    <strong>${icono}${razon}:</strong>
                    <span class="badge badge-${color} ml-1">${fechas.length} día${fechas.length > 1 ? 's' : ''}</span>
                    <div class="mt-1 ml-3">
                        <button type="button" class="btn btn-link p-0 small" onclick="(function(){const el=document.getElementById('${blockId}'); if(!el) return; el.style.display = (el.style.display === 'none' ? 'block' : 'none');})()">
                            Ver detalle
                        </button>
                        <div id="${blockId}" style="display:none;" class="mt-1">
                            <ul class="mb-0 pl-3 small text-${color}">
                                ${fechas.map(f => `<li>${f}</li>`).join('')}
                            </ul>
                        </div>
                    </div>
                </div>
            `;
            return;
        }

        html += `
            <div class="mb-2">
                <strong>${icono}${razon}:</strong>
                <span class="badge badge-${color} ml-1">${fechas.length} día${fechas.length > 1 ? 's' : ''}</span>
                <div class="mt-1 ml-3">
                    <small class="text-${color}">${fechas.join(', ')}</small>
                </div>
            </div>
        `;
    });
    
    return html;
}

function colorTipoBadge(tipoCodigo) {
    const t = (tipoCodigo || '').toUpperCase();
    const mapa = {
        'CAMBIO DESCANSO': 'warning',
        'CAMBIO_DESCANSO': 'warning',
        'CT': 'primary',
        'CAMBIO DE TURNO': 'primary',
        'CT PERMANENTE': 'info',
        'DOBLADA': 'success',
        'D FDS': 'success',
        'DOBLADA PERMANENTE': 'dark',
    };
    return mapa[t] || 'secondary';
}

function renderizarDetalleSolicitud(data) {
    const modalContent = document.getElementById('detalleSolicitudContent');
    
    // Los datos vienen directamente en el objeto, no en data.data
    // Extraer los campos necesarios (excluyendo 'success')
    const datos = {
        id: data.id,
        fecha_solicitud: data.fecha_solicitud,
        tipo: data.tipo,
        tipo_codigo: data.tipo_codigo,
        estado: data.estado,
        comentario: data.comentario,
        fecha_resolucion: data.fecha_resolucion,
        solicitante: data.solicitante,
        receptor: data.receptor,
        aprobaciones: data.aprobaciones,
        fechas: data.fechas || {},
        informacion_adicional: data.informacion_adicional || {}
    };
    
    // Mapear estados a colores y textos
    const estadosMap = {
        'pendiente': { class: 'warning', texto: 'Pendiente' },
        'aprobada': { class: 'success', texto: 'Aprobada' },
        'rechazada': { class: 'danger', texto: 'Rechazada' },
        'cancelada': { class: 'secondary', texto: 'Cancelada' },
        'pagada': { class: 'info', texto: 'Pagada' }
    };
    
    const estadoInfo = estadosMap[datos.estado] || { class: 'secondary', texto: datos.estado };
    
    let html = `
        <div class="row">
            <!-- Información Básica -->
            <div class="col-12 mb-4">
                <div class="card border-0 shadow-sm">
                    <div class="card-header bg-primary text-white">
                        <h5 class="mb-0"><i class="fas fa-info-circle mr-2"></i>Información Básica</h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <strong><i class="fas fa-calendar-alt mr-2"></i>Fecha de Solicitud:</strong>
                                <p class="mb-0">${datos.fecha_solicitud || 'No especificada'}</p>
                            </div>
                            <div class="col-md-6 mb-3">
                                <strong><i class="fas fa-tag mr-2"></i>Tipo de formulario:</strong>
                                <p class="mb-0"><span class="badge badge-${colorTipoBadge(datos.tipo_codigo || datos.tipo)}" style="font-size: 0.95em;">${datos.tipo}</span></p>
                            </div>
                            <div class="col-md-6 mb-3">
                                <strong><i class="fas fa-check-circle mr-2"></i>Estado:</strong>
                                <p class="mb-0"><span class="badge badge-${estadoInfo.class}">${estadoInfo.texto}</span></p>
                            </div>
                            ${datos.fecha_resolucion ? `
                            <div class="col-md-6 mb-3">
                                <strong><i class="fas fa-clock mr-2"></i>Fecha de Resolución:</strong>
                                <p class="mb-0">${datos.fecha_resolucion}</p>
                            </div>
                            ` : ''}
                            <div class="col-12 mb-3">
                                <strong><i class="fas fa-comment mr-2"></i>Comentario:</strong>
                                <p class="mb-0">${datos.comentario}</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Participantes -->
            <div class="col-md-6 mb-4">
                <div class="card border-0 shadow-sm">
                    <div class="card-header bg-info text-white">
                        <h5 class="mb-0"><i class="fas fa-user mr-2"></i>Solicitante</h5>
                    </div>
                    <div class="card-body">
                        <p class="mb-1"><strong>Nombre:</strong> ${datos.solicitante.nombre}</p>
                        <p class="mb-1"><strong>Email:</strong> ${datos.solicitante.email}</p>
                        ${datos.solicitante.supervisor ? `<p class="mb-0"><strong>Supervisor:</strong> ${datos.solicitante.supervisor}</p>` : ''}
                    </div>
                </div>
            </div>
            
            <div class="col-md-6 mb-4">
                <div class="card border-0 shadow-sm">
                    <div class="card-header bg-success text-white">
                        <h5 class="mb-0"><i class="fas fa-user-friends mr-2"></i>Receptor</h5>
                    </div>
                    <div class="card-body">
                        <p class="mb-1"><strong>Nombre:</strong> ${datos.receptor.nombre}</p>
                        <p class="mb-1"><strong>Email:</strong> ${datos.receptor.email}</p>
                        ${datos.receptor.supervisor ? `<p class="mb-0"><strong>Supervisor:</strong> ${datos.receptor.supervisor}</p>` : ''}
                    </div>
                </div>
            </div>
            
            <!-- Fechas e Información Específica -->
            ${Object.keys(datos.fechas).length > 0 || Object.keys(datos.informacion_adicional).length > 0 ? `
            <div class="col-12 mb-4">
                <div class="card border-0 shadow-sm">
                    <div class="card-header bg-warning text-dark">
                        <h5 class="mb-0"><i class="fas fa-calendar-week mr-2"></i>Fechas e Información Específica</h5>
                    </div>
                    <div class="card-body">
                        ${datos.fechas.fecha_cambio ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-calendar-day mr-2"></i>Fecha del Cambio de Turno:</strong>
                                <p class="mb-0">${datos.fechas.fecha_cambio}</p>
                            </div>
                        ` : ''}
                        ${datos.fechas.fecha_cesion ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-hand-paper mr-2 text-success"></i>Fecha de Cesión (día que cedes/descansas):</strong>
                                <p class="mb-0">${datos.fechas.fecha_cesion}</p>
                            </div>
                        ` : ''}
                        ${datos.fechas.fecha_doblada ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-calendar-day mr-2"></i>Fecha de Cesión (día de la doblada):</strong>
                                <p class="mb-0">${datos.fechas.fecha_doblada}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.modalidad ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-exchange-alt mr-2"></i>Modalidad:</strong>
                                <p class="mb-0">${datos.informacion_adicional.modalidad}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.intercambio_dia_a ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-calendar-day mr-2 text-success"></i>Día A:</strong>
                                <p class="mb-0">${datos.informacion_adicional.intercambio_dia_a}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.intercambio_dia_b ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-calendar-day mr-2 text-primary"></i>Día B:</strong>
                                <p class="mb-0">${datos.informacion_adicional.intercambio_dia_b}</p>
                            </div>
                        ` : ''}
                        ${datos.fechas.inicio ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-calendar-check mr-2"></i>Fecha de Inicio:</strong>
                                <p class="mb-0">${datos.fechas.inicio}</p>
                            </div>
                            <div class="mb-3">
                                <strong><i class="fas fa-calendar-times mr-2"></i>Fecha de Fin:</strong>
                                <p class="mb-0">${datos.fechas.fin}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.dias_semana_seleccionados ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-calendar-week mr-2"></i>Días de Semana Seleccionados:</strong>
                                <p class="mb-0">${datos.informacion_adicional.dias_semana_seleccionados}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.dias_cesion ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-hand-paper mr-2 text-success"></i>Días que cede (lo cubre el compañero):</strong>
                                <p class="mb-0">${datos.informacion_adicional.dias_cesion}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.dias_devolucion ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-exchange-alt mr-2 text-primary"></i>Días que devuelve (se dobla para pagar):</strong>
                                <p class="mb-0">${datos.informacion_adicional.dias_devolucion}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.tipo_cesion ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-layer-group mr-2"></i>Tipo de cesión:</strong>
                                <p class="mb-0">${datos.informacion_adicional.tipo_cesion}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.jornada_cedida ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-clock mr-2"></i>Jornada que cede:</strong>
                                <p class="mb-0">${datos.informacion_adicional.jornada_cedida}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.pago_sabado ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-calendar-day mr-2 text-warning"></i>Pago en sábado:</strong>
                                <p class="mb-0">${datos.informacion_adicional.pago_sabado}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.fecha_pago_semana ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-calendar-week mr-2"></i>Día de pago en semana:</strong>
                                <p class="mb-0">${datos.informacion_adicional.fecha_pago_semana}</p>
                            </div>
                        ` : ''}
                        ${datos.fechas.total_dias !== undefined ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-hashtag mr-2"></i>Total de Días Afectados:</strong>
                                <p class="mb-0"><span class="badge badge-primary">${datos.fechas.total_dias} día${datos.fechas.total_dias !== 1 ? 's' : ''}</span></p>
                            </div>
                        ` : ''}
                        ${datos.fechas.cesion_aplicables && datos.fechas.cesion_aplicables.length > 0 ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-check-circle mr-2 text-success"></i>Fechas de Cesión Aplicables (te cubre el compañero):</strong>
                                <div class="mt-2" style="max-height: 200px; overflow-y: auto;">
                                    <p class="mb-0 small">${datos.fechas.cesion_aplicables.join(', ')}</p>
                                </div>
                            </div>
                        ` : ''}
                        ${datos.fechas.cesion_excluidas && datos.fechas.cesion_excluidas.length > 0 ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-times-circle mr-2 text-danger"></i>Fechas de Cesión Excluidas:</strong>
                                <div class="mt-2" style="max-height: 200px; overflow-y: auto;">
                                    ${agruparFechasExcluidas(datos.fechas.cesion_excluidas)}
                                </div>
                            </div>
                        ` : ''}
                        ${datos.fechas.devolucion_aplicables && datos.fechas.devolucion_aplicables.length > 0 ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-check-circle mr-2 text-success"></i>Fechas de Devolución Aplicables (te doblas tú):</strong>
                                <div class="mt-2" style="max-height: 200px; overflow-y: auto;">
                                    <p class="mb-0 small">${datos.fechas.devolucion_aplicables.join(', ')}</p>
                                </div>
                            </div>
                        ` : ''}
                        ${datos.fechas.devolucion_excluidas && datos.fechas.devolucion_excluidas.length > 0 ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-times-circle mr-2 text-danger"></i>Fechas de Devolución Excluidas:</strong>
                                <div class="mt-2" style="max-height: 200px; overflow-y: auto;">
                                    ${agruparFechasExcluidas(datos.fechas.devolucion_excluidas)}
                                </div>
                            </div>
                        ` : ''}
                        ${datos.fechas.aplicables && datos.fechas.aplicables.length > 0 ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-check-circle mr-2 text-success"></i>Fechas Aplicables:</strong>
                                <div class="mt-2" style="max-height: 200px; overflow-y: auto;">
                                    <p class="mb-0 small">${datos.fechas.aplicables.join(', ')}</p>
                                </div>
                            </div>
                        ` : ''}
                        ${datos.fechas.excluidas && datos.fechas.excluidas.length > 0 ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-times-circle mr-2 text-danger"></i>Fechas Excluidas:</strong>
                                <div class="mt-2" style="max-height: 300px; overflow-y: auto;">
                                    ${datos.fechas.resumen ? `
                                        <div class="alert alert-light py-2 mb-2 small">
                                            <strong>Resumen del rango:</strong>
                                            ${datos.fechas.resumen.total_dias_rango} días ·
                                            ${datos.fechas.resumen.fines_de_semana_en_rango} fines de semana ·
                                            ${datos.fechas.total_dias} aplicables ·
                                            ${datos.fechas.excluidas.length} excluidas
                                            <div class="mt-1"><small><strong>Cómo leer esto:</strong> En CT Permanente solo aplican días hábiles (lun–vie).</small></div>
                                            <div class="mt-1"><small>Los fines de semana se cuentan aunque, por prioridad, puedan mostrarse como Festivo/Temporada/Mantenimiento/Descanso.</small></div>
                                            ${datos.fechas.resumen.prioridad ? ('<div class="mt-1"><small><strong>Prioridad de exclusión:</strong> ' + datos.fechas.resumen.prioridad + '</small></div>') : ''}
                                        </div>
                                    ` : ''}
                                    ${agruparFechasExcluidas(datos.fechas.excluidas)}
                                </div>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.nota ? `
                            <div class="alert alert-info mb-0">
                                <i class="fas fa-info-circle mr-2"></i><small>${datos.informacion_adicional.nota}</small>
                            </div>
                        ` : ''}
                        ${datos.fechas.fecha_pago ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-money-bill mr-2"></i>Fecha de Pago/Devolución:</strong>
                                <p class="mb-0">${datos.fechas.fecha_pago}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.jornada_cedida_partida ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-clock mr-2 text-success"></i>Jornada que cedes (jornada partida):</strong>
                                <p class="mb-0">${datos.informacion_adicional.jornada_cedida_partida}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.te_cubren ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-user-shield mr-2"></i>Cobertura (te cubren):</strong>
                                <p class="mb-0">${datos.informacion_adicional.te_cubren}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.cubre_en_pago ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-hands-helping mr-2"></i>Cobertura en la fecha de pago:</strong>
                                <p class="mb-0">${datos.informacion_adicional.cubre_en_pago}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.deuda_30min ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-clock mr-2"></i>Deuda de 30 minutos:</strong>
                                <p class="mb-0">${datos.informacion_adicional.deuda_30min}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.minutos_deuda !== undefined ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-clock mr-2"></i>Minutos de Deuda:</strong>
                                <p class="mb-0">${datos.informacion_adicional.minutos_deuda} minutos</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.jornada_solicitante ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-clock mr-2"></i>Jornada Solicitante:</strong>
                                <p class="mb-0">${datos.informacion_adicional.jornada_solicitante}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.jornada_receptor ? `
                            <div class="mb-3">
                                <strong><i class="fas fa-clock mr-2"></i>Jornada Receptor:</strong>
                                <p class="mb-0">${datos.informacion_adicional.jornada_receptor}</p>
                            </div>
                        ` : ''}
                        ${datos.informacion_adicional.nota_jornadas ? `
                            <div class="alert alert-info mb-0">
                                <i class="fas fa-info-circle mr-2"></i><small>${datos.informacion_adicional.nota_jornadas}</small>
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
            ` : ''}

            <!-- Aprobaciones -->
            <div class="col-12 mb-4">
                <div class="card border-0 shadow-sm">
                    <div class="card-header bg-secondary text-white">
                        <h5 class="mb-0"><i class="fas fa-check-double mr-2"></i>Aprobaciones</h5>
                    </div>
                    <div class="card-body">
                        <div class="row">
                            <div class="col-md-6 mb-3">
                                <strong>Receptor:</strong>
                                <p class="mb-0">
                                    ${datos.aprobaciones.receptor.aprobado ? 
                                        `<span class="badge badge-success"><i class="fas fa-check mr-1"></i>Aprobado</span>` : 
                                        `<span class="badge badge-secondary">Pendiente</span>`
                                    }
                                    ${datos.aprobaciones.receptor.fecha ? ` - ${datos.aprobaciones.receptor.fecha}` : ''}
                                </p>
                            </div>
                            <div class="col-md-6 mb-3">
                                <strong>Supervisor:</strong>
                                <p class="mb-0">
                                    ${datos.aprobaciones.supervisor.aprobado ? 
                                        `<span class="badge badge-success"><i class="fas fa-check mr-1"></i>Aprobado</span>` : 
                                        `<span class="badge badge-secondary">Pendiente</span>`
                                    }
                                    ${datos.aprobaciones.supervisor.fecha ? ` - ${datos.aprobaciones.supervisor.fecha}` : ''}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    modalContent.innerHTML = html;
}

// Confirmar acción del modal
$('#confirmarAccion').click(function() {
    if (!solicitudActual || !accionActual) return;

    // El comentario es obligatorio: es lo único que le llega al otro explicando la decisión.
    const $comentario = $('#comentario_respuesta');
    const comentario = ($comentario.val() || '').trim();
    if (!comentario) {
        $comentario.addClass('is-invalid').focus();
        $('#comentario_respuesta_error').text(MSG.comentario);
        return;
    }
    $comentario.removeClass('is-invalid');
    $('#comentario_respuesta_error').text('');

    // Evitar doble envío: si el botón ya está procesando, ignorar clics extra.
    const $btnConfirmar = $(this);
    if ($btnConfirmar.prop('disabled')) return;
    $btnConfirmar.prop('disabled', true).data('textoPrevio', $btnConfirmar.text()).text('Procesando...');

    const formData = new FormData();
    formData.append('csrfmiddlewaretoken', window.CSRF_TOKEN);
    // El nombre lo fija el backend: 'comentario_respuesta'. Antes se enviaba como
    // 'comentario' y el comentario del supervisor se perdía en el camino.
    formData.append('comentario_respuesta', comentario);

    let url = '';
    if (rolActual === 'receptor') {
        if (accionActual === 'aprobar') {
            url = `/solicitudes/aprobar-solicitud-receptor/${solicitudActual}/`;
        } else if (accionActual === 'rechazar') {
            url = `/solicitudes/rechazar-solicitud-receptor/${solicitudActual}/`;
        }
    } else if (rolActual === 'supervisor') {
        if (accionActual === 'aprobar') {
            url = `/solicitudes/aprobar-solicitud/${solicitudActual}/`;
        } else if (accionActual === 'rechazar') {
            url = `/solicitudes/rechazar-solicitud/${solicitudActual}/`;
        }
    }
    
    // Ocultar el modal y mostrar loading bloqueante mientras se procesa.
    $('#accionSolicitudModal').modal('hide');
    const textoAccion = accionActual === 'aprobar' ? 'Aprobando solicitud...' : 'Rechazando solicitud...';
    LoadingUI.mostrar(textoAccion);

    fetch(url, {
        method: 'POST',
        body: formData,
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        }
    })
    .then(response => { if (!response.ok) throw new Error('HTTP ' + response.status); return response.json(); })
    .then(data => {
        $('#accionSolicitudModal').modal('hide');
        $('#comentario_respuesta').val('').removeClass('is-invalid');
        $('#comentario_respuesta_error').text('');
        
        if (data.success) {
            Swal.fire({
                icon: 'success',
                title: '¡Acción completada!',
                text: data.message,
                timer: 3000,
                timerProgressBar: true,
                showConfirmButton: false,
                position: 'top-end',
                toast: true
            }).then(() => {
                location.reload();
            });
        } else {
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: data.message,
                showConfirmButton: true,
                confirmButtonText: 'Entendido'
            });
        }
    })
    .catch(error => {
        console.error('Error:', error);
        $('#accionSolicitudModal').modal('hide');
        Swal.fire({
            icon: 'error',
            title: 'Error de conexión',
            text: 'No se pudo completar la acción. Inténtalo de nuevo.',
            showConfirmButton: true,
            confirmButtonText: 'Reintentar'
        });
    })
    .finally(() => {
        // Rehabilitar el botón para permitir otra acción (en éxito la página recarga igualmente).
        $btnConfirmar.prop('disabled', false).text($btnConfirmar.data('textoPrevio') || 'Confirmar');
    });
});