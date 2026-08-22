// JavaScript para Mis Turnos - Responsive y FullCalendar
var turnosMes = {};
var fechaSeleccionada = null;

// Variable para rastrear qué meses ya están cargados o están cargando
var mesesCargando = new Set();
var mesesCargados = new Set();
// Timestamps de cuándo se cargó cada mes (para invalidar después de 5 minutos)
var mesesCargadosTimestamps = {};

// Variable para prevenir múltiples ejecuciones de datesSet
var ultimoMesProcesado = null;
var fechaUltimoProcesamiento = null;

function cargarDatos(anio, mes) {
    // Crear clave única para el mes
    const claveMes = `${anio}-${mes}`;
    
    
    // Si ya está cargando este mes, no hacer nada
    if (mesesCargando.has(claveMes)) {
        return Promise.resolve();
    }
    
    // Si ya está cargado este mes, no hacer nada
    if (mesesCargados.has(claveMes)) {
        // Verificar si han pasado más de 1 minuto desde la última carga
        // Esto asegura que los datos se actualicen después de aprobar solicitudes
        const timestampAnterior = mesesCargadosTimestamps[claveMes];
        const ahora = Date.now();
        const tiempoTranscurrido = timestampAnterior ? (ahora - timestampAnterior) : Infinity;
        const UN_MINUTO = 60 * 1000; // 1 minuto en milisegundos
        
        if (timestampAnterior && tiempoTranscurrido < UN_MINUTO) {
            return Promise.resolve();
        } else {
            // Han pasado más de 1 minuto, forzar recarga
            mesesCargados.delete(claveMes);
            delete mesesCargadosTimestamps[claveMes];
        }
    }
    
    mesesCargando.add(claveMes);

    return fetch(`/turnos/api/mis-turnos-por-mes/?mes=${mes}&anio=${anio}`)
        .then(response => {
            return response.json();
        })
        .then(data => {
            turnosMes = Object.assign({}, turnosMes, data); // Merge en lugar de reemplazar
            
            // Marcar como cargado con timestamp
            mesesCargando.delete(claveMes);
            mesesCargados.add(claveMes);
            mesesCargadosTimestamps[claveMes] = Date.now();

            // Refrescar detalles si ya hay una fecha seleccionada
            // NO llamar a mostrarDetallesDia aquí porque puede causar bucles
            // Solo actualizar si realmente hay datos para esa fecha
            if (fechaSeleccionada && turnosMes[fechaSeleccionada]) {
                mostrarDetallesDia(fechaSeleccionada);
            }

            // Aplicar estilos después de que el calendario se haya actualizado
            // IMPORTANTE: Esperar a que viewDidMount haya terminado de renderizar las celdas
            // Prevenir múltiples ejecuciones con debounce
            if (window.aplicarEstilosTimeout) {
                clearTimeout(window.aplicarEstilosTimeout);
            }
            window.aplicarEstilosTimeout = setTimeout(function() {
                // Verificar que las celdas estén en el DOM antes de aplicar estilos
                const celdas = document.querySelectorAll('.fc-daygrid-day');
                if (celdas.length > 0) {
                    aplicarEstilosCambios();
                } else {
                    // Reintentar después de más tiempo
                    setTimeout(function() {
                        aplicarEstilosCambios();
                    }, 500);
                }
            }, 1500); // Delay mayor para asegurar que viewDidMount haya renderizado las celdas
        })
        .catch(error => {
            console.error('Error al cargar datos:', error);
            mesesCargando.delete(claveMes);
        });
}

// Aplica estilos distintivos a días con cambios de turno
var aplicandoEstilos = false; // Prevenir múltiples ejecuciones simultáneas

function aplicarEstilosCambios() {
    
    // Prevenir múltiples ejecuciones simultáneas
    if (aplicandoEstilos) {
        return;
    }
    aplicandoEstilos = true;
    
    
    // Limpiar estilos anteriores (cambios y descansos)
    document.querySelectorAll('.dia-con-cambio').forEach(el => {
        el.classList.remove('dia-con-cambio');
        const icon = el.querySelector('.cambio-turno-icon');
        if (icon) icon.remove();
    });
    
    document.querySelectorAll('.dia-con-descanso').forEach(el => {
        el.classList.remove('dia-con-descanso');
        const icon = el.querySelector('.descanso-icon');
        if (icon) icon.remove();
    });

    document.querySelectorAll('.dia-con-permiso').forEach(el => {
        el.classList.remove('dia-con-permiso');
        const icon = el.querySelector('.permiso-icon');
        if (icon) icon.remove();
    });

    document.querySelectorAll('.dia-con-restriccion').forEach(el => {
        el.classList.remove('dia-con-restriccion');
        const icon = el.querySelector('.restriccion-icon');
        if (icon) icon.remove();
    });

    document.querySelectorAll('.dia-con-sancion').forEach(el => {
        el.classList.remove('dia-con-sancion');
        const icon = el.querySelector('.sancion-icon');
        if (icon) icon.remove();
    });

    // Esperar a que FullCalendar haya renderizado las celdas
    // Intentar múltiples veces si los elementos no están disponibles
    let intentos = 0;
    const maxIntentos = 15; // Aumentar intentos
    
    function intentarAplicarEstilos() {
        intentos++;
        let elementosEncontrados = 0;
        let elementosNoEncontrados = [];
        
        // Obtener el mes actual del calendario para filtrar solo fechas visibles
        // NO usar getDate() aquí porque puede causar re-renderizados
        // En su lugar, usar el mes más común en los datos cargados
        let mesVisible = null;
        let anioVisible = null;
        
        // Intentar obtener el mes visible sin causar re-renderizados
        try {
            if (window.calendar && window.calendar.view) {
                const currentDate = window.calendar.view.currentStart;
                if (currentDate) {
                    mesVisible = currentDate.getMonth() + 1;
                    anioVisible = currentDate.getFullYear();
                }
            }
        } catch (e) {
        }
        
        // Si no se pudo obtener el mes visible, intentar desde las celdas del DOM
        if (!mesVisible || !anioVisible) {
            const primeraCelda = document.querySelector('.fc-daygrid-day:not(.fc-day-other)');
            if (primeraCelda) {
                const dataDate = primeraCelda.getAttribute('data-date');
                if (dataDate) {
                    const fechaObj = new Date(dataDate + 'T00:00:00');
                    mesVisible = fechaObj.getMonth() + 1;
                    anioVisible = fechaObj.getFullYear();
                }
            }
        }
        
        // Si aún no se tiene, usar el mes más común en los datos
        if (!mesVisible || !anioVisible) {
            const mesesEnDatos = {};
            for (const fechaStr of Object.keys(turnosMes)) {
                const fechaObj = new Date(fechaStr + 'T00:00:00');
                const mes = fechaObj.getMonth() + 1;
                const anio = fechaObj.getFullYear();
                const clave = `${anio}-${mes}`;
                mesesEnDatos[clave] = (mesesEnDatos[clave] || 0) + 1;
            }
            // Obtener el mes con más datos
            const mesMasComun = Object.keys(mesesEnDatos).sort((a, b) => mesesEnDatos[b] - mesesEnDatos[a])[0];
            if (mesMasComun) {
                const [anio, mes] = mesMasComun.split('-');
                mesVisible = parseInt(mes);
                anioVisible = parseInt(anio);
            }
        }
        
        
        // Verificar primero si hay celdas renderizadas en el DOM
        const celdasExistentes = document.querySelectorAll('.fc-daygrid-day');

        // LIMPIEZA: quitar marcadores de descanso "viejos" de celdas que, según los datos
        // actuales, ya NO son descanso. Sin esto, un ícono agregado en un render previo
        // (o por datos en caché desactualizados) puede quedar pegado en un día que ahora
        // es un fin de semana de descanso normal o una jornada predeterminada.
        celdasExistentes.forEach(celda => {
            const dataDate = celda.getAttribute('data-date');
            if (!dataDate) return;
            const info = turnosMes[dataDate];
            const esDescanso = info && (info.es_descanso || info.tipo === 'descanso');
            if (!esDescanso) {
                const iconoViejo = celda.querySelector('.descanso-icon');
                if (iconoViejo) iconoViejo.remove();
                celda.classList.remove('dia-con-descanso');
            }
        });
        
        if (celdasExistentes.length === 0) {
            if (intentos < maxIntentos) {
                setTimeout(intentarAplicarEstilos, 200);
                return;
            }
        }
        
        // Aplicar estilos a días con cambios
        let totalFechasConCambios = 0;
        let fechasFiltradas = 0;
        
        // Primero, contar todas las fechas con cambios, descansos y permisos
        let totalFechasConDescanso = 0;
        let totalFechasConPermiso = 0;
        let totalFechasConRestriccion = 0;
        let totalFechasConSancion = 0;
        for (const [fechaStr, turnoInfo] of Object.entries(turnosMes)) {
            if (turnoInfo && turnoInfo.es_cambio) {
                totalFechasConCambios++;
            }
            if (turnoInfo && (turnoInfo.es_descanso || turnoInfo.tipo === 'descanso')) {
                totalFechasConDescanso++;
            }
            if (turnoInfo && turnoInfo.permiso) {
                totalFechasConPermiso++;
            }
            if (turnoInfo && turnoInfo.restriccion) {
                totalFechasConRestriccion++;
            }
            if (turnoInfo && turnoInfo.sancion) {
                totalFechasConSancion++;
            }
        }

        // Si no hay nada que marcar, salir
        if (totalFechasConCambios === 0 && totalFechasConDescanso === 0
            && totalFechasConPermiso === 0 && totalFechasConRestriccion === 0
            && totalFechasConSancion === 0) {
            aplicandoEstilos = false;
            return;
        }
        
        for (const [fechaStr, turnoInfo] of Object.entries(turnosMes)) {
            // Procesar días con cambios
            if (turnoInfo && turnoInfo.es_cambio) {
                // Filtrar solo fechas del mes visible
                const fechaObj = new Date(fechaStr + 'T00:00:00');
                const mesFecha = fechaObj.getMonth() + 1;
                const anioFecha = fechaObj.getFullYear();
                
                
                // Si hay un mes visible, solo procesar fechas de ese mes
                if (mesVisible && anioVisible && (mesFecha !== mesVisible || anioFecha !== anioVisible)) {
                    fechasFiltradas++;
                    continue; // Saltar fechas que no están en el mes visible
                }
                
                // FullCalendar usa diferentes selectores según la versión
                // Intentar múltiples selectores posibles
                let cellElement = null;
                
                // Opción 1: data-date attribute (FullCalendar 5+)
                cellElement = document.querySelector(`.fc-daygrid-day[data-date="${fechaStr}"]`);
                
                // Opción 2: Buscar por todas las celdas y comparar data-date
                if (!cellElement) {
                    celdasExistentes.forEach(celda => {
                        const dataDate = celda.getAttribute('data-date');
                        if (dataDate === fechaStr) {
                            cellElement = celda;
                        }
                    });
                }
                
                // Opción 3: Buscar por aria-label
                if (!cellElement) {
                    const dia = fechaObj.getDate();
                    const todasLasCeldas = document.querySelectorAll('.fc-daygrid-day');
                    todasLasCeldas.forEach(celda => {
                        const ariaLabel = celda.getAttribute('aria-label');
                        if (ariaLabel && ariaLabel.includes(`${dia}`) && ariaLabel.includes(`${mesFecha}`) && ariaLabel.includes(`${anioFecha}`)) {
                            // Verificar que no sea de otro mes
                            if (!celda.classList.contains('fc-day-other')) {
                                cellElement = celda;
                            }
                        }
                    });
                }
                
                // Opción 4: Buscar por número de día (último recurso)
                if (!cellElement && mesVisible && anioVisible && mesFecha === mesVisible && anioFecha === anioVisible) {
                    const dia = fechaObj.getDate();
                    const todasLasCeldas = document.querySelectorAll('.fc-daygrid-day:not(.fc-day-other)');
                    todasLasCeldas.forEach(celda => {
                        const numeroDia = celda.querySelector('.fc-daygrid-day-number');
                        if (numeroDia && parseInt(numeroDia.textContent.trim()) === dia) {
                            cellElement = celda;
                        }
                    });
                }
                
                if (cellElement) {
                    elementosEncontrados++;
                    // Usar requestAnimationFrame para evitar causar re-renderizados
                    // y agrupar todas las modificaciones del DOM
                    requestAnimationFrame(function() {
                        if (cellElement && cellElement.parentNode) { // Verificar que aún existe
                            cellElement.classList.add('dia-con-cambio');
                            
                            // Agregar ícono si no existe
                            if (!cellElement.querySelector('.cambio-turno-icon')) {
                                const iconElement = document.createElement('span');
                                iconElement.className = 'cambio-turno-icon';
                                iconElement.innerHTML = '🔄';
                                iconElement.style.cssText = 'position: absolute; top: 2px; right: 2px; font-size: 10px; color: #e74c3c; z-index: 10;';
                                cellElement.appendChild(iconElement);
                            }
                        }
                    });
                } else {
                    elementosNoEncontrados.push(fechaStr);
                }
            }
            
            // Procesar días con descanso
            if (turnoInfo && (turnoInfo.es_descanso || turnoInfo.tipo === 'descanso')) {
                // Filtrar solo fechas del mes visible
                const fechaObj = new Date(fechaStr + 'T00:00:00');
                const mesFecha = fechaObj.getMonth() + 1;
                const anioFecha = fechaObj.getFullYear();
                
                // Si hay un mes visible, solo procesar fechas de ese mes
                if (mesVisible && anioVisible && (mesFecha !== mesVisible || anioFecha !== anioVisible)) {
                    continue; // Saltar fechas que no están en el mes visible
                }
                
                // FullCalendar usa diferentes selectores según la versión
                let cellElement = null;
                
                // Opción 1: data-date attribute (FullCalendar 5+)
                cellElement = document.querySelector(`.fc-daygrid-day[data-date="${fechaStr}"]`);
                
                // Opción 2: Buscar por todas las celdas y comparar data-date
                if (!cellElement) {
                    celdasExistentes.forEach(celda => {
                        const dataDate = celda.getAttribute('data-date');
                        if (dataDate === fechaStr) {
                            cellElement = celda;
                        }
                    });
                }
                
                // Opción 3: Buscar por aria-label
                if (!cellElement) {
                    const dia = fechaObj.getDate();
                    const todasLasCeldas = document.querySelectorAll('.fc-daygrid-day');
                    todasLasCeldas.forEach(celda => {
                        const ariaLabel = celda.getAttribute('aria-label');
                        if (ariaLabel && ariaLabel.includes(`${dia}`) && ariaLabel.includes(`${mesFecha}`) && ariaLabel.includes(`${anioFecha}`)) {
                            if (!celda.classList.contains('fc-day-other')) {
                                cellElement = celda;
                            }
                        }
                    });
                }
                
                // Opción 4: Buscar por número de día (último recurso)
                if (!cellElement && mesVisible && anioVisible && mesFecha === mesVisible && anioFecha === anioVisible) {
                    const dia = fechaObj.getDate();
                    const todasLasCeldas = document.querySelectorAll('.fc-daygrid-day:not(.fc-day-other)');
                    todasLasCeldas.forEach(celda => {
                        const numeroDia = celda.querySelector('.fc-daygrid-day-number');
                        if (numeroDia && parseInt(numeroDia.textContent.trim()) === dia) {
                            cellElement = celda;
                        }
                    });
                }
                
                if (cellElement) {
                    elementosEncontrados++;
                    // Usar requestAnimationFrame para evitar causar re-renderizados
                    requestAnimationFrame(function() {
                        if (!cellElement || !cellElement.parentNode) return; // ya no existe

                        // ANTI-RACE: este callback se programó con los datos de un momento
                        // anterior. Antes de pintar, RE-LEER los datos actuales de ESTA fecha.
                        // Si entre tanto el día dejó de ser descanso (p. ej. se refrescó la
                        // caché y ahora es jornada predeterminada), hay que QUITAR el ícono,
                        // no volver a agregarlo. Esto evita el café "superpuesto" intermitente.
                        const actual = turnosMes[fechaStr];
                        const sigueDescanso = actual && (actual.es_descanso || actual.tipo === 'descanso');
                        if (!sigueDescanso) {
                            const viejo = cellElement.querySelector('.descanso-icon');
                            if (viejo) viejo.remove();
                            cellElement.classList.remove('dia-con-descanso');
                            return;
                        }

                        cellElement.classList.add('dia-con-descanso');

                        // Ícono distinto según el tipo:
                        //  - DÍA LIBRE (queda libre por una doblada: cesión/pago) → ☕
                        //  - Descanso REAL (asignado: semana/mantenimiento/fin de semana) → 😴
                        // IMPORTANTE: el café (☕) SOLO aplica a días libres por doblada.
                        // Cualquier otro descanso (incluido un fin de semana de alternancia
                        // o datos en caché sin 'descanso_info') debe mostrar 😴, nunca ☕.
                        const di = (actual && actual.descanso_info) || {};
                        // Cambio de descanso = intercambio de día → es DESCANSO (😴), no día libre.
                        const esDiaLibre = di.origen !== 'cambio_descanso' && (di.tipo === 'cedio' || di.tipo === 'pago');
                        const emoji = esDiaLibre ? '☕' : '😴';
                        const titulo = esDiaLibre ? 'Día libre (doblada)' : 'Día de descanso';

                        if (!cellElement.querySelector('.descanso-icon')) {
                            const iconElement = document.createElement('span');
                            iconElement.className = 'descanso-icon';
                            iconElement.innerHTML = emoji;
                            iconElement.title = titulo;
                            iconElement.style.cssText = 'position: absolute; top: 2px; right: 2px; font-size: 10px; z-index: 10;';
                            cellElement.appendChild(iconElement);
                        } else {
                            // Si ya existe, asegurar que muestre el emoji correcto.
                            const ic = cellElement.querySelector('.descanso-icon');
                            ic.innerHTML = emoji;
                            ic.title = titulo;
                        }
                    });
                }
            }

            // Procesar días con PERMISO especial (marcador en la esquina)
            if (turnoInfo && turnoInfo.permiso) {
                const fechaObj = new Date(fechaStr + 'T00:00:00');
                const mesFecha = fechaObj.getMonth() + 1;
                const anioFecha = fechaObj.getFullYear();
                if (!(mesVisible && anioVisible && (mesFecha !== mesVisible || anioFecha !== anioVisible))) {
                    let cellPermiso = document.querySelector(`.fc-daygrid-day[data-date="${fechaStr}"]`);
                    if (!cellPermiso) {
                        celdasExistentes.forEach(celda => {
                            if (celda.getAttribute('data-date') === fechaStr) cellPermiso = celda;
                        });
                    }
                    if (cellPermiso) {
                        const aprobado = turnoInfo.permiso.estado === 'APROBADO';
                        requestAnimationFrame(function () {
                            if (cellPermiso && cellPermiso.parentNode && !cellPermiso.querySelector('.permiso-icon')) {
                                cellPermiso.classList.add('dia-con-permiso');
                                const ic = document.createElement('span');
                                ic.className = 'permiso-icon';
                                ic.title = aprobado ? 'Permiso aprobado' : 'Permiso pendiente';
                                ic.innerHTML = aprobado ? '📋' : '⏳';
                                ic.style.cssText = 'position: absolute; top: 2px; left: 2px; font-size: 10px; z-index: 10;';
                                cellPermiso.appendChild(ic);
                            }
                        });
                    }
                }
            }

            // Procesar días con RESTRICCIÓN (marcador en la esquina inferior izquierda)
            if (turnoInfo && turnoInfo.restriccion) {
                const fechaObj = new Date(fechaStr + 'T00:00:00');
                const mesFecha = fechaObj.getMonth() + 1;
                const anioFecha = fechaObj.getFullYear();
                if (!(mesVisible && anioVisible && (mesFecha !== mesVisible || anioFecha !== anioVisible))) {
                    let cellRest = document.querySelector(`.fc-daygrid-day[data-date="${fechaStr}"]`);
                    if (!cellRest) {
                        celdasExistentes.forEach(celda => {
                            if (celda.getAttribute('data-date') === fechaStr) cellRest = celda;
                        });
                    }
                    if (cellRest) {
                        const tituloRest = 'Restricción: ' + (turnoInfo.restriccion.tipo || '');
                        requestAnimationFrame(function () {
                            if (cellRest && cellRest.parentNode && !cellRest.querySelector('.restriccion-icon')) {
                                cellRest.classList.add('dia-con-restriccion');
                                const ic = document.createElement('span');
                                ic.className = 'restriccion-icon';
                                ic.title = tituloRest;
                                ic.innerHTML = '🚫';
                                ic.style.cssText = 'position: absolute; bottom: 2px; left: 2px; font-size: 10px; z-index: 10;';
                                cellRest.appendChild(ic);
                            }
                        });
                    }
                }
            }

            // Procesar días con SANCIÓN (marcador en la esquina inferior derecha)
            if (turnoInfo && turnoInfo.sancion) {
                const fechaObj = new Date(fechaStr + 'T00:00:00');
                const mesFecha = fechaObj.getMonth() + 1;
                const anioFecha = fechaObj.getFullYear();
                if (!(mesVisible && anioVisible && (mesFecha !== mesVisible || anioFecha !== anioVisible))) {
                    let cellSanc = document.querySelector(`.fc-daygrid-day[data-date="${fechaStr}"]`);
                    if (!cellSanc) {
                        celdasExistentes.forEach(celda => {
                            if (celda.getAttribute('data-date') === fechaStr) cellSanc = celda;
                        });
                    }
                    if (cellSanc) {
                        requestAnimationFrame(function () {
                            if (cellSanc && cellSanc.parentNode && !cellSanc.querySelector('.sancion-icon')) {
                                cellSanc.classList.add('dia-con-sancion');
                                const ic = document.createElement('span');
                                ic.className = 'sancion-icon';
                                ic.title = 'Sancionado: sin solicitudes';
                                ic.innerHTML = '⚖️';
                                ic.style.cssText = 'position: absolute; bottom: 2px; right: 2px; font-size: 10px; z-index: 10;';
                                cellSanc.appendChild(ic);
                            }
                        });
                    }
                }
            }
        }

        
        // Si hay elementos no encontrados y aún tenemos intentos, reintentar
        if (elementosNoEncontrados.length > 0 && intentos < maxIntentos) {
            setTimeout(intentarAplicarEstilos, 200); // Aumentar delay entre intentos
        } else {
            aplicandoEstilos = false; // Permitir nuevas ejecuciones
            if (elementosEncontrados > 0) {
            }
            if (elementosNoEncontrados.length > 0 && intentos >= maxIntentos) {
                // Solo mostrar warning si ya agotamos los intentos
                console.warn(`[DEBUG aplicarEstilosCambios] No se pudieron aplicar estilos a ${elementosNoEncontrados.length} día(s) después de ${maxIntentos} intentos. Puede que no estén visibles en el calendario actual.`);
            }
        }
    }
    
    // Iniciar el proceso
    intentarAplicarEstilos();
}

// Muestra los detalles del día seleccionado en los contenedores del template
// Nombre legible del acuerdo que modificó un día, a partir de `Turno.tipo_cambio`
// (vocabulario `core.constants.TipoCambioTurno`, que NO es el de los tipos de solicitud).
// El detalle del día decía "Cambio de turno" para TODOS los tipos, así que un intercambio de
// descanso o una doblada de finde se anunciaban con el nombre de otro trámite.
const NOMBRE_ACUERDO = {
    'CAMBIO DESCANSO': 'Cambio de día de descanso',
    'D FDS': 'Doblada de fin de semana',
    'DOBLADA': 'Doblada',
    'DOBLADA PERM': 'Doblada permanente',
    'CT': 'Cambio de turno',
    'CT PERMANENTE': 'Cambio de turno permanente',
};

// `YYYY-MM-DD` → ¿sábado o domingo? Se parte la cadena a mano: `new Date('YYYY-MM-DD')` se
// interpreta en UTC y en zonas al oeste devuelve el día anterior.
function esFinDeSemana(fechaStr) {
    const [a, m, d] = (fechaStr || '').split('-').map(Number);
    if (!a || !m || !d) return false;
    const wd = new Date(a, m - 1, d).getDay();
    return wd === 0 || wd === 6;
}

function mostrarDetallesDia(fechaStr) {
    
    const info = turnosMes[fechaStr];

    const fechaSpan = document.getElementById('fecha-seleccionada');
    const jornadaDiv = document.getElementById('mi-jornada');

    if (fechaSpan) {
        const [y, m, d] = fechaStr.split('-');
        const meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
        fechaSpan.textContent = `${parseInt(d)} de ${meses[parseInt(m)-1]} de ${y}`;
    }

    if (jornadaDiv) {
        // Verificar si hay información disponible (incluyendo descanso)
        if (info && (info.jornada || info.es_descanso || info.tipo === 'descanso')) {
            // Indicador de Permiso Especial (no cambia la jornada; se muestra encima)
            let permisoHTML = '';
            if (info.permiso) {
                const pp = info.permiso;
                const aprobado = pp.estado === 'APROBADO';
                const estadoBadge = aprobado
                    ? '<span style="background:#dcfce7;color:#166534;border-radius:999px;padding:1px 8px;font-size:.72rem;font-weight:600;">Aprobado</span>'
                    : '<span style="background:#fde68a;color:#854d0e;border-radius:999px;padding:1px 8px;font-size:.72rem;font-weight:600;">Pendiente</span>';
                const detallePermiso = pp.especificacion || pp.tipo || 'Permiso';
                permisoHTML = `<div class="info-permiso" style="margin-top: 8px; padding: 10px; background-color: #fef9c3; border-left: 3px solid #f59e0b; border-radius: 4px; font-size: 0.9rem; color: #854d0e; line-height: 1.5;">
                        <i class="fas fa-calendar-check" style="margin-right: 6px;"></i>
                        <strong>Permiso${pp.es_permanente ? ' permanente' : ''}:</strong> ${detallePermiso} · ${pp.horas} h ${estadoBadge}
                        ${pp.cubre ? `<br><small style="color:#92400e;">Cubre: ${pp.cubre}</small>` : ''}
                    </div>`;
            }

            // Indicador de Restricción (médica/administrativa) vigente ese día
            let restriccionHTML = '';
            if (info.restriccion) {
                const rr = info.restriccion;
                restriccionHTML = `<div class="info-restriccion" style="margin-top: 8px; padding: 10px; background-color: #fee2e2; border-left: 3px solid #ef4444; border-radius: 4px; font-size: 0.9rem; color: #991b1b; line-height: 1.5;">
                        <i class="fas fa-ban" style="margin-right: 6px;"></i>
                        <strong>Restricción:</strong> ${rr.tipo}${rr.indefinida ? ' <small>(vigente)</small>' : ''}
                        ${rr.recomendacion ? `<br><small style="color:#b91c1c;">${rr.recomendacion}</small>` : ''}
                    </div>`;
            }

            // Indicador de Sanción (bloquea solicitudes ese día)
            let sancionHTML = '';
            if (info.sancion) {
                const ss = info.sancion;
                const vig = ss.hasta ? `${ss.desde} – ${ss.hasta}` : `desde ${ss.desde} (indefinida)`;
                sancionHTML = `<div class="info-sancion" style="margin-top: 8px; padding: 10px; background-color: #1f2937; border-left: 3px solid #dc2626; border-radius: 4px; font-size: 0.9rem; color: #f9fafb; line-height: 1.5;">
                        <i class="fas fa-gavel" style="margin-right: 6px;"></i>
                        <strong>Sanción:</strong> no puedes solicitar cambios ni permisos. <small>(${vig})</small>
                        ${ss.motivo ? `<br><small style="color:#fca5a5;">Motivo: ${ss.motivo}</small>` : ''}
                    </div>`;
            }

            // Manejar caso de descanso
            if (info.es_descanso || info.tipo === 'descanso' || (!info.jornada && info.tipo === 'descanso')) {
                // ✅ MEJORADO: Mensajes sencillos y profesionales
                const descansoInfo = info.descanso_info || {};
                const tipoDescanso = descansoInfo.tipo; // 'cedio' | 'pago' | 'descanso_semana'
                const companeroNombre = descansoInfo.companero_nombre || 'un compañero';
                const fechaCesion = descansoInfo.fecha_cesion;
                const fechaPago = descansoInfo.fecha_pago;

                // CAMBIO DE DESCANSO: es un INTERCAMBIO de día de descanso, NO una doblada.
                // Aunque internamente venga con tipo 'cedio'/'pago', debe verse como DESCANSO
                // (tu descanso simplemente se movió de día), no como "día libre".
                const esCambioDescanso = descansoInfo.origen === 'cambio_descanso';

                // Diferenciar DÍA LIBRE (queda libre por una doblada: cesión/pago)
                // del DESCANSO real (asignado: temporada / mantenimiento / fin de semana / intercambio).
                // El café/DÍA LIBRE SOLO aplica a doblada (cedio/pago); todo lo demás es DESCANSO.
                const esDiaLibre = !esCambioDescanso && (tipoDescanso === 'cedio' || tipoDescanso === 'pago');
                const esDescansoReal = !esDiaLibre;
                const etiqueta = esDescansoReal ? 'DESCANSO' : 'DÍA LIBRE';
                const encabezado = esDescansoReal ? 'Día de descanso' : 'Día libre';
                const icono = esDescansoReal ? 'fa-bed' : 'fa-mug-hot';

                // Construir mensaje principal según el tipo (sencillo y profesional)
                let mensajeDescanso = '';
                if (esCambioDescanso) {
                    mensajeDescanso = `Descanso intercambiado con <strong>${companeroNombre}</strong>.`;
                } else if (esDescansoReal) {
                    if (descansoInfo.motivo === 'mantenimiento') {
                        mensajeDescanso = 'Descanso por día de mantenimiento.';
                    } else if (descansoInfo.motivo === 'temporada') {
                        mensajeDescanso = 'Descanso de temporada.';
                    } else {
                        mensajeDescanso = 'Día de descanso asignado.';
                    }
                } else if (tipoDescanso === 'cedio') {
                    mensajeDescanso = `El compañero <strong>${companeroNombre}</strong> está trabajando por ti este día.`;
                    if (fechaPago) {
                        mensajeDescanso += ` Pagarás el ${fechaPago}.`;
                    }
                } else if (tipoDescanso === 'pago') {
                    mensajeDescanso = `El compañero <strong>${companeroNombre}</strong> está trabajando por ti hoy.`;
                    if (fechaCesion) {
                        mensajeDescanso += ` Tú lo cubriste el ${fechaCesion}.`;
                    }
                } else {
                    mensajeDescanso = 'Quedaste libre por una doblada. El compañero que te cubrió está trabajando por ti.';
                }

                const jornadaHTML = `<span class="jornada-value descanso">${etiqueta}</span>
                    <div class="info-descanso" style="margin-top: 8px; padding: 10px; background-color: #e3f2fd; border-left: 3px solid #2196f3; border-radius: 4px; font-size: 0.9rem; color: #1565c0; line-height: 1.5;">
                        <i class="fas ${icono}" style="margin-right: 6px;"></i>
                        <strong>${encabezado}:</strong> ${mensajeDescanso}
                    </div>`;
                jornadaDiv.innerHTML = jornadaHTML + permisoHTML + restriccionHTML + sancionHTML;
                return;
            }
            
            const jornadaLower = info.jornada.toLowerCase();
            // Asegurar que el nombre de la clase coincida (am, pm, descanso, doblada)
            let claseJornada = jornadaLower;
            if (jornadaLower === 'descanso' || jornadaLower.includes('descanso')) {
                claseJornada = 'descanso';
            } else if (jornadaLower === 'doblada') {
                claseJornada = 'doblada';
            }
            
            // Construir HTML para la jornada
            let jornadaTexto = info.jornada;
            if (info.jornada === 'DOBLADA') {
                // En FIN DE SEMANA un día trabajado es AM+PM POR DEFINICIÓN: la unidad del finde es
                // el día completo, no media jornada. Llamarlo "DOBLADA" afirma un esfuerzo extra que
                // no existe —y en este dominio "doblada" significa algo preciso: cubrir un día de
                // más por un favor, con contraparte y con 30 min de deuda (solo de lunes a viernes)—.
                // Quien trabaja su sábado por un cambio de descanso leía "DOBLADA" y parecía que le
                // debían algo. Mismo vocabulario que el formulario de D FDS: DÍA COMPLETO.
                jornadaTexto = esFinDeSemana(fechaStr) ? 'DÍA COMPLETO (AM + PM)' : 'DOBLADA (AM + PM)';
            }
            let jornadaHTML = `<span class="jornada-value ${claseJornada}">${jornadaTexto}</span>`;
            
            // Si hay un cambio, mostrar información detallada (sencilla y profesional).
            // Si el día tiene un PERMISO (p. ej. media jornada de temporada), esa nota ya explica
            // por qué cambió la jornada; evitamos la nota genérica de "cambio de turno" duplicada.
            if (info.tipo_cambio === 'PAGO REPROGRAMADO') {
                // Doblada por pago reprogramado: la persona no pudo cumplir su día de doblada y
                // el supervisor le programó este día para pagar (dobla AM+PM).
                jornadaHTML += `<div class="info-cambio" style="margin-top: 8px; padding: 10px; background-color: #fef3c7; border-left: 3px solid #d97706; border-radius: 4px; font-size: 0.9rem; color: #92400e; line-height: 1.5;">
                    <i class="fas fa-calendar-check" style="margin-right: 6px;"></i>
                    <strong>Pago reprogramado:</strong> hoy te doblas (AM + PM) para pagar un día de doblada que no pudiste cumplir. Programado por el supervisor.
                </div>`;
                jornadaDiv.innerHTML = jornadaHTML + permisoHTML + restriccionHTML + sancionHTML;
                return;
            }
            if (info.es_cambio && !info.permiso) {
                const jornadaPredeterminada = info.jornada_predeterminada || 'N/A';
                const coincidePredeterminada = info.coincide_con_predeterminada ?? false;
                const solicitudInfo = info.solicitud_info;
                
                // Construir mensaje profesional y claro
                let mensajeCambio = '';
                const companero = solicitudInfo?.companero_nombre;
                const fechaAprobacion = solicitudInfo?.fecha_resolucion;
                const rol = solicitudInfo?.rol;   // 'solicitante' | 'receptor'
                
                // Lo que se trabaja ese día, dicho como lo entiende quien lo lee: en finde es un
                // DÍA COMPLETO, entre semana una DOBLADA (ver el badge, mismo criterio).
                const finde = esFinDeSemana(fechaStr);
                const loQueTrabaja = (info.jornada === 'DOBLADA'
                    ? (finde ? 'el día completo (AM + PM)' : 'DOBLADA (AM + PM)')
                    : info.jornada);
                // La comparación era `=== 'DESCANSO'`, pero en FINDE el backend devuelve 'Descanso'
                // (title case, ver `JornadaUtils.calcular_jornada_dia`). Resultado: la explicación
                // buena era inalcanzable justo en los findes, y siempre salía la genérica.
                const descansabaEseDia = String(jornadaPredeterminada).toUpperCase() === 'DESCANSO';

                if (coincidePredeterminada) {
                    // Cambio que coincide con la predeterminada
                    mensajeCambio = `Este turno fue modificado por un cambio aprobado. Tu jornada actual (${loQueTrabaja}) coincide con tu jornada predeterminada.`;
                } else if (descansabaEseDia) {
                    // Ese día en realidad DESCANSABA (temporada o alternancia del finde) y ahora
                    // trabaja por un acuerdo: no tenía jornada "predeterminada" que mostrar.
                    mensajeCambio = `Normalmente <strong>descansabas</strong> este día; por este acuerdo trabajas <strong>${loQueTrabaja}</strong>.`;
                } else {
                    mensajeCambio = `Tu jornada predeterminada era <strong>${jornadaPredeterminada}</strong>; ahora trabajas <strong>${loQueTrabaja}</strong>.`;
                }

                // Con QUIÉN, y qué papel juega cada uno. En una doblada (de semana o de finde) el
                // día no es propio: se está cubriendo o devolviendo. Decirlo aquí es lo que permite
                // que el badge no tenga que insinuarlo.
                if (companero) {
                    const esFavor = ['DOBLADA', 'D FDS', 'DOBLADA PERM'].includes(info.tipo_cambio);
                    let conQuien;
                    if (esFavor && rol === 'receptor') {
                        conQuien = `Estás <strong>cubriendo a ${companero}</strong> este día.`;
                    } else if (esFavor) {
                        conQuien = `Estás <strong>devolviéndole el favor a ${companero}</strong>.`;
                    } else if (info.tipo_cambio === 'CAMBIO DESCANSO') {
                        // Trueque: cada uno toma el día del otro, no hay favor ni deuda.
                        conQuien = `Intercambio con <strong>${companero}</strong>.`;
                    } else {
                        conQuien = `Cambio con <strong>${companero}</strong>.`;
                    }
                    mensajeCambio += ` ${conQuien}`;
                    if (fechaAprobacion) mensajeCambio += ` Aprobado el ${fechaAprobacion}.`;
                }

                jornadaHTML += `<div class="info-cambio" style="margin-top: 8px; padding: 10px; background-color: #d1ecf1; border-left: 3px solid #17a2b8; border-radius: 4px; font-size: 0.9rem; color: #0c5460; line-height: 1.5;">
                    <i class="fas fa-exchange-alt" style="margin-right: 6px;"></i>
                    <strong>${NOMBRE_ACUERDO[info.tipo_cambio] || 'Cambio de turno'}:</strong> ${mensajeCambio}
                </div>`;
            } else if (info.tipo === 'predeterminado' && info.jornada) {
                // Mostrar información para días predeterminados (sin cambios)
                const mensajePredeterminado = `Jornada predeterminada: <strong>${info.jornada}</strong>.`;
                jornadaHTML += `<div class="info-predeterminada" style="margin-top: 8px; padding: 8px; background-color: #f8f9fa; border-left: 3px solid #6c757d; border-radius: 4px; font-size: 0.85rem; color: #495057; line-height: 1.4;">
                    <i class="fas fa-info-circle" style="margin-right: 4px;"></i>
                    ${mensajePredeterminado}
                </div>`;
            }

            jornadaDiv.innerHTML = jornadaHTML + permisoHTML + restriccionHTML + sancionHTML;
        } else {
            // Si no hay datos aún, mostrar "Cargando..." temporalmente
            jornadaDiv.innerHTML = `<span class="detail-content por-asignar">Cargando...</span>`;
            
            // Intentar cargar datos si no están disponibles
            const fechaObj = new Date(fechaStr + 'T00:00:00'); // Asegurar zona horaria
            const anio = fechaObj.getFullYear();
            const mes = fechaObj.getMonth() + 1;
            
            // Solo cargar si los datos no están cargados para este mes
            const claveMes = `${anio}-${mes}`;
            const fechaStrInMes = Object.keys(turnosMes).find(f => {
                const fObj = new Date(f + 'T00:00:00');
                return fObj.getFullYear() === anio && (fObj.getMonth() + 1) === mes;
            });
            
            // Verificar si el mes ya está cargado o cargando
            if (!fechaStrInMes && !mesesCargados.has(claveMes) && !mesesCargando.has(claveMes)) {
                cargarDatos(anio, mes);
            } else {
                if (mesesCargando.has(claveMes)) {
                } else if (mesesCargados.has(claveMes)) {
                } else {
                }
            }
        }
    }
}

document.addEventListener('DOMContentLoaded', function() {
    // Función para ajustar tarjetas en pantallas pequeñas
    function adjustForSmallScreens() {
        const weekCards = document.querySelector('.week-cards');
        const dashboardContent = document.querySelector('.dashboard-content');
        
        if (weekCards && dashboardContent) {
            const availableWidth = dashboardContent.offsetWidth;
            
            // Si el espacio es muy pequeño, permitir scroll horizontal
            if (availableWidth < 700) {
                weekCards.style.minWidth = '560px';
                weekCards.style.overflowX = 'auto';
            } else {
                weekCards.style.minWidth = 'auto';
                weekCards.style.overflowX = 'visible';
            }
        }
    }

    // Aplicar inmediatamente
    adjustForSmallScreens();

    // Aplicar cuando cambie el tamaño de ventana
    var resizeTimeout;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(function() {
            adjustForSmallScreens();
            // Solo actualizar tamaño del calendario si realmente cambió significativamente
            // NO hacerlo inmediatamente para evitar bucles
        }, 300); // Debounce de 300ms
    });

    // Forzar recarga del mes actual al cargar la página
    // Esto asegura que los datos se actualicen después de aprobar solicitudes
    // El usuario puede estar volviendo a esta página después de aprobar una solicitud
    const ahora = new Date();
    const anioActual = ahora.getFullYear();
    const mesActual = ahora.getMonth() + 1;
    const claveMesActual = `${anioActual}-${mesActual}`;
    
    // Invalidar caché del mes actual para forzar recarga
    if (mesesCargados.has(claveMesActual)) {
        mesesCargados.delete(claveMesActual);
        delete mesesCargadosTimestamps[claveMesActual];
    }

    // Inicializar FullCalendar
    const calendarEl = document.getElementById('calendar');
    const calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'es',
        height: 500,
        initialDate: new Date(),
        showNonCurrentDates: false, // Ocultar días de otros meses (mejora rendimiento)

        datesSet: function(info) {
            // DEBUG: Log detallado
            
            // Cuando cambia el mes, cargar datos del nuevo mes
            // IMPORTANTE: Este evento se puede disparar múltiples veces durante el renderizado
            // Por eso verificamos cuidadosamente antes de cargar
            
            // info.start puede ser el primer día visible (que puede ser del mes anterior)
            // Necesitamos obtener el mes que está realmente visible en el centro del calendario
            // Usar calendar.getDate() que devuelve la fecha central del mes visible
            const fechaCentro = calendar.getDate();
            const anio = fechaCentro.getFullYear();
            const mes = fechaCentro.getMonth() + 1;
            const claveMes = `${anio}-${mes}`;
            const ahora = Date.now();
            
            
            
            // Prevenir ejecuciones múltiples del mismo mes en un corto período
            if (ultimoMesProcesado === claveMes && fechaUltimoProcesamiento && (ahora - fechaUltimoProcesamiento) < 2000) {
                return;
            }
            
            // Prevenir ejecuciones múltiples con debounce
            if (window.datesSetTimeout) {
                clearTimeout(window.datesSetTimeout);
            }
            
            window.datesSetTimeout = setTimeout(function() {
                // Verificar de nuevo después del delay
                // IMPORTANTE: Usar calendar.getDate() que devuelve la fecha central del mes visible
                // NO usar info.start porque puede ser del mes anterior
                const fechaCentro2 = calendar.getDate();
                const anio2 = fechaCentro2.getFullYear();
                const mes2 = fechaCentro2.getMonth() + 1;
                const claveMes2 = `${anio2}-${mes2}`;
                
                
                // Solo cargar si no está cargado o cargando
                if (!mesesCargados.has(claveMes2) && !mesesCargando.has(claveMes2)) {
                    ultimoMesProcesado = claveMes2;
                    fechaUltimoProcesamiento = Date.now();
                    cargarDatos(anio2, mes2);
                } else {
                    // NUEVO: Aplicar estilos aunque el mes ya esté cargado
                    // Esperar a que las celdas se rendericen
                    setTimeout(() => {
                        aplicarEstilosCambios();
                    }, 800); // Delay para asegurar que viewDidMount haya renderizado
                }
            }, 500); // Debounce de 500ms para agrupar múltiples ejecuciones
        },
        dayCellDidMount: function(info) {
            // Este evento se dispara cuando cada celda del día se renderiza
            // Aplicar estilos inmediatamente si hay datos disponibles
            const { dateStr, el } = info;
            
            // Funciones puras para crear íconos
            const crearIconoCambio = () => {
                const iconElement = document.createElement('span');
                iconElement.className = 'cambio-turno-icon';
                iconElement.innerHTML = '🔄';
                iconElement.style.cssText = 'position: absolute; top: 2px; right: 2px; font-size: 10px; color: #e74c3c; z-index: 10;';
                return iconElement;
            };
            
            const crearIconoDescanso = (turnoInfo) => {
                // ☕ solo para día libre por doblada (cedio/pago); 😴 para cualquier otro descanso
                // (incluido el intercambio de cambio de descanso).
                const di = (turnoInfo && turnoInfo.descanso_info) || {};
                const esDiaLibre = di.origen !== 'cambio_descanso' && (di.tipo === 'cedio' || di.tipo === 'pago');
                const iconElement = document.createElement('span');
                iconElement.className = 'descanso-icon';
                iconElement.innerHTML = esDiaLibre ? '☕' : '😴';
                iconElement.title = esDiaLibre ? 'Día libre (doblada)' : 'Día de descanso';
                iconElement.style.cssText = 'position: absolute; top: 2px; right: 2px; font-size: 10px; z-index: 10;';
                return iconElement;
            };
            
            // Función para aplicar estilos a esta celda (arrow function)
            const aplicarEstiloACelda = () => {
                const turnoInfo = turnosMes[dateStr];
                if (!turnoInfo) return;
                
                // Verificar si el elemento aún existe en el DOM
                if (!el?.parentNode) return;
                
                // Aplicar estilo para cambios
                if (turnoInfo.es_cambio) {
                    requestAnimationFrame(() => {
                        if (el?.parentNode) {
                            el.classList.add('dia-con-cambio');
                            if (!el.querySelector('.cambio-turno-icon')) {
                                el.appendChild(crearIconoCambio());
                            }
                        }
                    });
                }
                
                // Aplicar estilo para descansos
                if (turnoInfo.es_descanso || turnoInfo.tipo === 'descanso') {
                    requestAnimationFrame(() => {
                        if (!el?.parentNode) return;
                        // ANTI-RACE: re-leer los datos actuales antes de pintar.
                        const actual = turnosMes[dateStr];
                        if (!actual || !(actual.es_descanso || actual.tipo === 'descanso')) {
                            const viejo = el.querySelector('.descanso-icon');
                            if (viejo) viejo.remove();
                            el.classList.remove('dia-con-descanso');
                            return;
                        }
                        el.classList.add('dia-con-descanso');
                        if (!el.querySelector('.descanso-icon')) {
                            el.appendChild(crearIconoDescanso(actual));
                        }
                    });
                } else {
                    // El día NO es descanso: quitar cualquier ícono viejo que haya quedado.
                    const viejo = el.querySelector('.descanso-icon');
                    if (viejo) viejo.remove();
                    el.classList.remove('dia-con-descanso');
                }
            };
            
            // Intentar aplicar estilos inmediatamente
            aplicarEstiloACelda();
            
            // Si los datos no están disponibles aún, intentar después de delays progresivos
            if (!turnosMes[dateStr]) {
                const delays = [300, 800, 1500];
                delays.forEach(delay => setTimeout(aplicarEstiloACelda, delay));
            }
        },
        viewDidMount: function() {
            const datosDisponibles = Object.keys(turnosMes).length;
            
            // Cuando el calendario se renderiza completamente, aplicar estilos
            // Este evento se dispara después de que todas las celdas están en el DOM
            // IMPORTANTE: Este evento puede dispararse ANTES de que los datos estén cargados
            // Por eso siempre intentamos aplicar estilos, incluso si no hay datos aún
            // (los datos pueden llegar después y dayCellDidMount los aplicará)
            
            // Prevenir ejecuciones múltiples con debounce
            if (window.viewDidMountTimeout) {
                clearTimeout(window.viewDidMountTimeout);
            }
            
            // Función helper para aplicar estilos con verificación de celdas
            const intentarAplicarEstilos = () => {
                const celdas = document.querySelectorAll('.fc-daygrid-day');
                
                if (celdas.length > 0) {
                    aplicarEstilosCambios();
                    return true;
                }
                return false;
            };
            
            // Siempre intentar aplicar estilos cuando las celdas estén renderizadas
            window.viewDidMountTimeout = setTimeout(() => {
                
                // Intentar aplicar estilos si hay datos
                if (datosDisponibles > 0) {
                    if (!intentarAplicarEstilos()) {
                        // Reintentar con más tiempo
                        setTimeout(() => {
                            if (intentarAplicarEstilos()) {
                            }
                        }, 500);
                    }
                } else {
                }
            }, 300);
        },
        dateClick: function(info) {
            // Cuando hace click en un día, mostrar detalles
            fechaSeleccionada = info.dateStr;
            mostrarDetallesDia(info.dateStr);
            
            // Si los datos no están cargados, cargarlos
            const fechaObj = new Date(info.dateStr);
            const anio = fechaObj.getFullYear();
            const mes = fechaObj.getMonth() + 1;
            
            // Verificar si ya tenemos datos para este mes
            const tieneDatosMes = Object.keys(turnosMes).some(f => {
                const fObj = new Date(f);
                return fObj.getFullYear() === anio && (fObj.getMonth() + 1) === mes;
            });
            
            const claveMes = `${anio}-${mes}`;
            if (!tieneDatosMes && !mesesCargados.has(claveMes) && !mesesCargando.has(claveMes)) {
                cargarDatos(anio, mes);
            } else {
                // Forzar actualización de detalles después de un pequeño delay
                setTimeout(() => {
                    mostrarDetallesDia(info.dateStr);
                }, 100);
            }
        },

    });
    calendar.render();

    //Recalcula el cambio el tamaño real del contenedor
    // DESHABILITADO: Causa bucles infinitos al disparar datesSet repetidamente
    // Si necesitas actualizar el tamaño, hazlo manualmente o con debounce
    /*
    var resizeObserverTimeout;
    const ro = new ResizeObserver(()=>{
        clearTimeout(resizeObserverTimeout);
        resizeObserverTimeout = setTimeout(function() {
            if (window.calendar && typeof window.calendar.updateSize === 'function') { 
                window.calendar.updateSize();
            }
        }, 500); // Debounce de 500ms para evitar bucles
    });
    ro.observe(calendarEl);
    */

    // NO cargar datos aquí - datesSet se ejecutará automáticamente cuando el calendario se renderice
    // Cargar aquí causaría duplicados

    // seleccionar automáticamente el día de hoy si pertenece al mes visible
    setTimeout(function() {
        const hoy = new Date();
        const y = hoy.getFullYear();
        const m = String(hoy.getMonth() + 1).padStart(2, '0');
        const d = String(hoy.getDate()).padStart(2, '0');
        const hoyStr = `${y}-${m}-${d}`;
        if (turnosMes[hoyStr]) {
            fechaSeleccionada = hoyStr;
            mostrarDetallesDia(hoyStr);
        }
    }, 50);

        // Función para cambiar mes
        function cambiarMes(anio, mes) {
            // Usar gotoDate de FullCalendar, pero no disparar cargarDatos si ya está cargado
            const claveMes = `${anio}-${mes}`;
            if (!mesesCargados.has(claveMes) && !mesesCargando.has(claveMes)) {
                calendar.gotoDate(`${anio}-${mes}-01`);
            } else {
                // Solo cambiar la vista sin recargar datos
                calendar.gotoDate(`${anio}-${mes}-01`);
            }
        }

    // Hacer funciones disponibles globalmente
    window.calendar = calendar;
    window.cambiarMes = cambiarMes;
    
    // Redimensionar calendario cuando el sidebar cambia (AdminLTE events)
    // Esto soluciona el problema de días ocultos cuando se expande/colapsa el sidebar
    const redimensionarCalendario = (inmediato = false) => {
        // Si es inmediato, redimensionar sin delay
        if (inmediato) {
            if (window.calendar && typeof window.calendar.updateSize === 'function') {
                window.calendar.updateSize();
                // Re-aplicar estilos después de redimensionar
                setTimeout(() => {
                    aplicarEstilosCambios();
                }, 50);
            }
            return;
        }
        
        // Usar debounce para evitar múltiples llamadas
        if (window.calendarResizeTimeout) {
            clearTimeout(window.calendarResizeTimeout);
        }
        window.calendarResizeTimeout = setTimeout(() => {
            if (window.calendar && typeof window.calendar.updateSize === 'function') {
                window.calendar.updateSize();
                // Re-aplicar estilos después de redimensionar
                setTimeout(() => {
                    aplicarEstilosCambios();
                }, 100);
            }
        }, 400); // Delay para esperar que termine la animación del sidebar
    };
    
    // Escuchar eventos de AdminLTE cuando el sidebar se colapsa/expande
    // jQuery está disponible porque se carga antes en base.html
    if (typeof $ !== 'undefined' && $.fn) {
        // Escuchar cuando se colapsa (inmediato para que se vean todos los días)
        $(document).on('collapsed.lte.pushmenu', '[data-widget="pushmenu"]', () => {
            redimensionarCalendario(true);
        });
        
        // Escuchar cuando termina la animación de colapsado
        $(document).on('collapsed.lte.pushmenu.done', '[data-widget="pushmenu"]', () => {
            redimensionarCalendario();
        });
        
        // Escuchar cuando se expande
        $(document).on('shown.lte.pushmenu', '[data-widget="pushmenu"]', () => {
            redimensionarCalendario();
        });
        
    }
    
    // SIEMPRE usar MutationObserver como respaldo adicional
    // Esto asegura que funcione incluso si los eventos de jQuery fallan
    const observer = new MutationObserver(() => {
        const isCollapsed = document.body.classList.contains('sidebar-collapse');
        if (isCollapsed !== window.sidebarWasCollapsed) {
            window.sidebarWasCollapsed = isCollapsed;
            // Si se colapsa, redimensionar inmediatamente para que se vean todos los días
            // Si se expande, usar delay normal
            redimensionarCalendario(isCollapsed);
        }
    });
    observer.observe(document.body, {
        attributes: true,
        attributeFilter: ['class']
    });
    window.sidebarWasCollapsed = document.body.classList.contains('sidebar-collapse');
    
    // También escuchar cambios en el tamaño de ventana
    window.addEventListener('resize', () => {
        if (window.calendarResizeTimeout) {
            clearTimeout(window.calendarResizeTimeout);
        }
        window.calendarResizeTimeout = setTimeout(() => {
            if (window.calendar && typeof window.calendar.updateSize === 'function') {
                window.calendar.updateSize();
            }
        }, 300);
    });
});
