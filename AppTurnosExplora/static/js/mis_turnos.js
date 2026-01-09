// JavaScript para Mis Turnos - Responsive y FullCalendar
var turnosMes = {};
var fechaSeleccionada = null;

// Variable para rastrear qué meses ya están cargados o están cargando
var mesesCargando = new Set();
var mesesCargados = new Set();

// Variable para prevenir múltiples ejecuciones de datesSet
var ultimoMesProcesado = null;
var fechaUltimoProcesamiento = null;

function cargarDatos(anio, mes) {
    // Crear clave única para el mes
    const claveMes = `${anio}-${mes}`;
    
    console.log(`[DEBUG cargarDatos] Llamado para ${claveMes}`, {
        mesesCargando: Array.from(mesesCargando),
        mesesCargados: Array.from(mesesCargados),
        stack: new Error().stack.split('\n').slice(1, 5).join('\n')
    });
    
    // Si ya está cargando este mes, no hacer nada
    if (mesesCargando.has(claveMes)) {
        console.log(`[DEBUG cargarDatos] Ya se está cargando ${claveMes}, ignorando...`);
        return Promise.resolve();
    }
    
    // Si ya está cargado este mes, no hacer nada
    if (mesesCargados.has(claveMes)) {
        console.log(`[DEBUG cargarDatos] El mes ${claveMes} ya está cargado`);
        return Promise.resolve();
    }
    
    console.log(`[DEBUG cargarDatos] INICIANDO carga de datos para ${anio}-${mes}`);
    mesesCargando.add(claveMes);

    console.log(`[DEBUG cargarDatos] Haciendo fetch a /turnos/api/mis-turnos-por-mes/?mes=${mes}&anio=${anio}`);
    return fetch(`/turnos/api/mis-turnos-por-mes/?mes=${mes}&anio=${anio}`)
        .then(response => {
            console.log(`[DEBUG cargarDatos] Respuesta recibida, status: ${response.status}`);
            return response.json();
        })
        .then(data => {
            console.log(`[DEBUG cargarDatos] Datos parseados, fechas recibidas:`, Object.keys(data).length);
            turnosMes = Object.assign({}, turnosMes, data); // Merge en lugar de reemplazar
            console.log('[DEBUG cargarDatos] Datos cargados, total fechas en turnosMes:', Object.keys(turnosMes).length);
            
            // Marcar como cargado
            mesesCargando.delete(claveMes);
            mesesCargados.add(claveMes);
            console.log(`[DEBUG cargarDatos] Mes ${claveMes} marcado como cargado`);

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
                console.log('[DEBUG cargarDatos] Aplicando estilos después de cargar datos');
                // Verificar que las celdas estén en el DOM antes de aplicar estilos
                const celdas = document.querySelectorAll('.fc-daygrid-day');
                if (celdas.length > 0) {
                    console.log(`[DEBUG cargarDatos] ${celdas.length} celdas encontradas, aplicando estilos`);
                    aplicarEstilosCambios();
                } else {
                    console.log('[DEBUG cargarDatos] No hay celdas aún, esperando más tiempo...');
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
    console.log('[DEBUG aplicarEstilosCambios] Llamado', {
        aplicandoEstilos: aplicandoEstilos,
        datosDisponibles: Object.keys(turnosMes).length,
        stack: new Error().stack.split('\n').slice(1, 4).join('\n')
    });
    
    // Prevenir múltiples ejecuciones simultáneas
    if (aplicandoEstilos) {
        console.log('[DEBUG aplicarEstilosCambios] Ya se está aplicando, ignorando...');
        return;
    }
    aplicandoEstilos = true;
    
    console.log("[DEBUG aplicarEstilosCambios] Aplicando estilos de cambios...");
    console.log("[DEBUG aplicarEstilosCambios] Datos disponibles:", Object.keys(turnosMes).length, "fechas");
    
    // Limpiar estilos anteriores
    document.querySelectorAll('.dia-con-cambio').forEach(el => {
        el.classList.remove('dia-con-cambio');
        const icon = el.querySelector('.cambio-turno-icon');
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
                    console.log(`[DEBUG aplicarEstilosCambios] Mes visible detectado desde calendar.view: ${anioVisible}-${mesVisible}`);
                }
            }
        } catch (e) {
            console.log(`[DEBUG aplicarEstilosCambios] Error obteniendo mes visible desde calendar.view: ${e.message}`);
        }
        
        // Si no se pudo obtener el mes visible, intentar desde las celdas del DOM
        if (!mesVisible || !anioVisible) {
            console.log('[DEBUG aplicarEstilosCambios] Intentando obtener mes visible desde las celdas del DOM...');
            const primeraCelda = document.querySelector('.fc-daygrid-day:not(.fc-day-other)');
            if (primeraCelda) {
                const dataDate = primeraCelda.getAttribute('data-date');
                if (dataDate) {
                    const fechaObj = new Date(dataDate + 'T00:00:00');
                    mesVisible = fechaObj.getMonth() + 1;
                    anioVisible = fechaObj.getFullYear();
                    console.log(`[DEBUG aplicarEstilosCambios] Mes visible detectado desde DOM: ${anioVisible}-${mesVisible}`);
                }
            }
        }
        
        // Si aún no se tiene, usar el mes más común en los datos
        if (!mesVisible || !anioVisible) {
            console.log('[DEBUG aplicarEstilosCambios] Usando mes más común en los datos...');
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
                console.log(`[DEBUG aplicarEstilosCambios] Mes visible detectado desde datos: ${anioVisible}-${mesVisible}`);
            }
        }
        
        console.log(`[DEBUG aplicarEstilosCambios] Mes visible final: ${anioVisible}-${mesVisible}`);
        
        // Verificar primero si hay celdas renderizadas en el DOM
        const celdasExistentes = document.querySelectorAll('.fc-daygrid-day');
        console.log(`[DEBUG aplicarEstilosCambios] Celdas encontradas en DOM: ${celdasExistentes.length}`);
        
        if (celdasExistentes.length === 0) {
            console.log('[DEBUG aplicarEstilosCambios] No hay celdas en el DOM aún, reintentando...');
            if (intentos < maxIntentos) {
                setTimeout(intentarAplicarEstilos, 200);
                return;
            }
        }
        
        // Aplicar estilos a días con cambios
        let totalFechasConCambios = 0;
        let fechasFiltradas = 0;
        
        // Primero, contar todas las fechas con cambios para debug
        for (const [fechaStr, turnoInfo] of Object.entries(turnosMes)) {
            if (turnoInfo && turnoInfo.es_cambio) {
                totalFechasConCambios++;
            }
        }
        console.log(`[DEBUG aplicarEstilosCambios] Total fechas con cambios en turnosMes: ${totalFechasConCambios}`);
        
        // Si no hay fechas con cambios, no hay nada que hacer
        if (totalFechasConCambios === 0) {
            console.log('[DEBUG aplicarEstilosCambios] No hay fechas con cambios en los datos cargados');
            aplicandoEstilos = false;
            return;
        }
        
        for (const [fechaStr, turnoInfo] of Object.entries(turnosMes)) {
            if (turnoInfo && turnoInfo.es_cambio) {
                // Filtrar solo fechas del mes visible
                const fechaObj = new Date(fechaStr + 'T00:00:00');
                const mesFecha = fechaObj.getMonth() + 1;
                const anioFecha = fechaObj.getFullYear();
                
                console.log(`[DEBUG aplicarEstilosCambios] Procesando fecha ${fechaStr}: mesFecha=${mesFecha}, anioFecha=${anioFecha}, mesVisible=${mesVisible}, anioVisible=${anioVisible}`);
                
                // Si hay un mes visible, solo procesar fechas de ese mes
                if (mesVisible && anioVisible && (mesFecha !== mesVisible || anioFecha !== anioVisible)) {
                    fechasFiltradas++;
                    console.log(`[DEBUG aplicarEstilosCambios] Fecha ${fechaStr} filtrada (no está en mes visible ${anioVisible}-${mesVisible})`);
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
        }
        
        console.log(`[DEBUG aplicarEstilosCambios] Intento ${intentos}/${maxIntentos}: ${totalFechasConCambios} fechas con cambios, ${fechasFiltradas} filtradas, ${elementosEncontrados} encontrados, ${elementosNoEncontrados.length} no encontrados`);
        
        // Si hay elementos no encontrados y aún tenemos intentos, reintentar
        if (elementosNoEncontrados.length > 0 && intentos < maxIntentos) {
            console.log(`[DEBUG aplicarEstilosCambios] Reintentando en 200ms...`);
            setTimeout(intentarAplicarEstilos, 200); // Aumentar delay entre intentos
        } else {
            aplicandoEstilos = false; // Permitir nuevas ejecuciones
            if (elementosEncontrados > 0) {
                console.log(`[DEBUG aplicarEstilosCambios] Estilos aplicados correctamente a ${elementosEncontrados} día(s) con cambios`);
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
function mostrarDetallesDia(fechaStr) {
    console.log('Mostrando detalles para:', fechaStr);
    console.log('Turnos disponibles:', turnosMes);
    
    const info = turnosMes[fechaStr];

    const fechaSpan = document.getElementById('fecha-seleccionada');
    const jornadaDiv = document.getElementById('mi-jornada');

    if (fechaSpan) {
        const [y, m, d] = fechaStr.split('-');
        const meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
        fechaSpan.textContent = `${parseInt(d)} de ${meses[parseInt(m)-1]} de ${y}`;
    }

    if (jornadaDiv) {
        if (info && info.jornada) {
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
                jornadaTexto = 'DOBLADA (AM + PM)';
            }
            let jornadaHTML = `<span class="jornada-value ${claseJornada}">${jornadaTexto}</span>`;
            
            // Si hay un cambio, mostrar información adicional
            if (info.es_cambio) {
                const jornadaPredeterminada = info.jornada_predeterminada || 'N/A';
                const coincidePredeterminada = info.coincide_con_predeterminada !== undefined ? info.coincide_con_predeterminada : false;
                
                if (coincidePredeterminada) {
                    // Cambio que coincide con la predeterminada
                    let mensajeInfo = 'Este turno fue modificado por un cambio aprobado, pero la jornada actual coincide con tu jornada predeterminada.';
                    if (info.solicitud_info && info.solicitud_info.companero_nombre) {
                        const companero = info.solicitud_info.companero_nombre;
                        const fecha = info.solicitud_info.fecha_resolucion || 'N/A';
                        mensajeInfo += ` Cambio realizado con ${companero} (aprobado el ${fecha}).`;
                    }
                    jornadaHTML += `<div class="info-cambio-predeterminada" style="margin-top: 8px; padding: 8px; background-color: #fff3cd; border-left: 3px solid #ffc107; border-radius: 4px; font-size: 0.85rem; color: #856404;">
                        <i class="fas fa-info-circle" style="margin-right: 4px;"></i>
                        <strong>Nota:</strong> ${mensajeInfo}
                    </div>`;
                } else {
                    // Cambio que difiere de la predeterminada
                    let mensajeInfo = `Jornada modificada por cambio de turno. Jornada predeterminada: ${jornadaPredeterminada}.`;
                    if (info.solicitud_info && info.solicitud_info.companero_nombre) {
                        const companero = info.solicitud_info.companero_nombre;
                        const fecha = info.solicitud_info.fecha_resolucion || 'N/A';
                        mensajeInfo += ` Cambio realizado con ${companero} (aprobado el ${fecha}).`;
                    }
                    jornadaHTML += `<div class="info-cambio-diferente" style="margin-top: 8px; padding: 8px; background-color: #d1ecf1; border-left: 3px solid #17a2b8; border-radius: 4px; font-size: 0.85rem; color: #0c5460;">
                        <i class="fas fa-exchange-alt" style="margin-right: 4px;"></i>
                        <strong>Cambio de turno:</strong> ${mensajeInfo}
                    </div>`;
                }
            }
            
            jornadaDiv.innerHTML = jornadaHTML;
            console.log('Jornada mostrada:', info.jornada, 'Clase:', claseJornada, 'Es cambio:', info.es_cambio, 'Coincide:', info.coincide_con_predeterminada);
        } else {
            // Si no hay datos aún, mostrar "Cargando..." temporalmente
            jornadaDiv.innerHTML = `<span class="detail-content por-asignar">Cargando...</span>`;
            console.log('No hay información disponible para esta fecha aún. Datos disponibles:', Object.keys(turnosMes));
            
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
                console.log('Cargando datos para el mes:', mes, anio);
                cargarDatos(anio, mes);
            } else {
                if (mesesCargando.has(claveMes)) {
                    console.log('El mes ya se está cargando, esperando...');
                } else if (mesesCargados.has(claveMes)) {
                    console.log('El mes ya está cargado');
                } else {
                    console.log('Datos del mes ya están cargados, pero no hay información para esta fecha específica');
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

    // Inicializar FullCalendar
    var calendarEl = document.getElementById('calendar');
    var calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'es',
        height: 500,
        initialDate: new Date(),

        datesSet: function(info) {
            // DEBUG: Log detallado
            console.log('[DEBUG datesSet] Evento disparado', {
                start: info.start,
                end: info.end,
                view: info.view ? info.view.type : 'N/A',
                stack: new Error().stack.split('\n').slice(1, 4).join('\n')
            });
            
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
            
            console.log('[DEBUG datesSet] Mes detectado', {
                infoStart: info.start,
                fechaCentro: fechaCentro,
                anio: anio,
                mes: mes,
                claveMes: claveMes
            });
            
            console.log('[DEBUG datesSet] Estado actual', {
                claveMes: claveMes,
                ultimoMesProcesado: ultimoMesProcesado,
                fechaUltimoProcesamiento: fechaUltimoProcesamiento,
                tiempoDesdeUltimo: fechaUltimoProcesamiento ? (ahora - fechaUltimoProcesamiento) : 'N/A',
                mesesCargando: Array.from(mesesCargando),
                mesesCargados: Array.from(mesesCargados)
            });
            
            // Prevenir ejecuciones múltiples del mismo mes en un corto período
            if (ultimoMesProcesado === claveMes && fechaUltimoProcesamiento && (ahora - fechaUltimoProcesamiento) < 2000) {
                console.log(`[DEBUG datesSet] IGNORADO para ${claveMes} (ejecutado hace ${ahora - fechaUltimoProcesamiento}ms)`);
                return;
            }
            
            // Prevenir ejecuciones múltiples con debounce
            if (window.datesSetTimeout) {
                console.log('[DEBUG datesSet] Cancelando timeout anterior');
                clearTimeout(window.datesSetTimeout);
            }
            
            console.log('[DEBUG datesSet] Programando carga de datos en 500ms');
            window.datesSetTimeout = setTimeout(function() {
                console.log('[DEBUG datesSet] Timeout ejecutado');
                // Verificar de nuevo después del delay
                // IMPORTANTE: Usar calendar.getDate() que devuelve la fecha central del mes visible
                // NO usar info.start porque puede ser del mes anterior
                const fechaCentro2 = calendar.getDate();
                const anio2 = fechaCentro2.getFullYear();
                const mes2 = fechaCentro2.getMonth() + 1;
                const claveMes2 = `${anio2}-${mes2}`;
                
                console.log('[DEBUG datesSet] Verificando antes de cargar', {
                    fechaCentro2: fechaCentro2,
                    anio2: anio2,
                    mes2: mes2,
                    claveMes2: claveMes2,
                    mesesCargados: mesesCargados.has(claveMes2),
                    mesesCargando: mesesCargando.has(claveMes2)
                });
                
                // Solo cargar si no está cargado o cargando
                if (!mesesCargados.has(claveMes2) && !mesesCargando.has(claveMes2)) {
                    console.log('[DEBUG datesSet] Llamando a cargarDatos para', claveMes2);
                    ultimoMesProcesado = claveMes2;
                    fechaUltimoProcesamiento = Date.now();
                    cargarDatos(anio2, mes2);
                } else {
                    console.log('[DEBUG datesSet] NO se carga porque ya está cargado o cargando');
                }
            }, 500); // Debounce de 500ms para agrupar múltiples ejecuciones
        },
        dayCellDidMount: function(info) {
            // Este evento se dispara cuando cada celda del día se renderiza
            // Aplicar estilos inmediatamente si hay datos disponibles
            const fechaStr = info.dateStr;
            
            // Función para aplicar estilos a esta celda
            function aplicarEstiloACelda() {
                if (turnosMes[fechaStr] && turnosMes[fechaStr].es_cambio) {
                    // Usar requestAnimationFrame para evitar causar re-renderizados
                    requestAnimationFrame(function() {
                        if (info.el && info.el.parentNode) { // Verificar que aún existe
                            info.el.classList.add('dia-con-cambio');
                            
                            // Agregar ícono si no existe
                            if (!info.el.querySelector('.cambio-turno-icon')) {
                                const iconElement = document.createElement('span');
                                iconElement.className = 'cambio-turno-icon';
                                iconElement.innerHTML = '🔄';
                                iconElement.style.cssText = 'position: absolute; top: 2px; right: 2px; font-size: 10px; color: #e74c3c; z-index: 10;';
                                info.el.appendChild(iconElement);
                            }
                        }
                    });
                }
            }
            
            // Intentar aplicar estilos inmediatamente
            aplicarEstiloACelda();
            
            // Si los datos no están disponibles aún, intentar después de delays progresivos
            // Esto maneja el caso donde las celdas se renderizan antes de que los datos se carguen
            if (!turnosMes[fechaStr]) {
                // Intentar varias veces con delays progresivos
                setTimeout(aplicarEstiloACelda, 300);
                setTimeout(aplicarEstiloACelda, 800);
                setTimeout(aplicarEstiloACelda, 1500);
            }
        },
        viewDidMount: function() {
            console.log('[DEBUG viewDidMount] Evento disparado', {
                datosDisponibles: Object.keys(turnosMes).length,
                stack: new Error().stack.split('\n').slice(1, 4).join('\n')
            });
            
            // Cuando el calendario se renderiza completamente, aplicar estilos
            // Este evento se dispara después de que todas las celdas están en el DOM
            // IMPORTANTE: Este evento puede dispararse ANTES de que los datos estén cargados
            // Por eso siempre intentamos aplicar estilos, incluso si no hay datos aún
            // (los datos pueden llegar después y dayCellDidMount los aplicará)
            
            // Prevenir ejecuciones múltiples con debounce
            if (window.viewDidMountTimeout) {
                console.log('[DEBUG viewDidMount] Cancelando timeout anterior');
                clearTimeout(window.viewDidMountTimeout);
            }
            
            // Siempre intentar aplicar estilos cuando las celdas estén renderizadas
            // Este es el momento ideal porque las celdas ya están en el DOM
            console.log('[DEBUG viewDidMount] Programando aplicarEstilosCambios en 300ms');
            window.viewDidMountTimeout = setTimeout(function() {
                console.log('[DEBUG viewDidMount] Timeout ejecutado, verificando celdas y datos');
                const celdas = document.querySelectorAll('.fc-daygrid-day');
                console.log(`[DEBUG viewDidMount] ${celdas.length} celdas encontradas en DOM`);
                
                if (Object.keys(turnosMes).length > 0 && celdas.length > 0) {
                    console.log('[DEBUG viewDidMount] Hay datos y celdas, aplicando estilos');
                    aplicarEstilosCambios();
                } else if (celdas.length === 0) {
                    console.log('[DEBUG viewDidMount] No hay celdas aún, reintentando...');
                    setTimeout(function() {
                        if (Object.keys(turnosMes).length > 0) {
                            aplicarEstilosCambios();
                        }
                    }, 500);
                } else {
                    console.log('[DEBUG viewDidMount] No hay datos aún, pero las celdas ya están renderizadas');
                }
            }, 300); // Delay corto porque viewDidMount se dispara DESPUÉS de que las celdas están renderizadas
        },
        dateClick: function(info) {
            // Cuando hace click en un día, mostrar detalles
            fechaSeleccionada = info.dateStr;
            console.log('Fecha clickeada:', info.dateStr);
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
                console.log('Cargando datos del mes:', mes, anio);
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
});
