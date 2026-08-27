/**
 * Calendario interactivo para selección de días especiales (festivos y mantenimiento) por mes.
 * Permite seleccionar múltiples días en cada mes del año.
 */

// Almacenar días seleccionados por mes
let diasSeleccionadosPorMes = {};

// Nombres de los días de la semana
const DIAS_SEMANA = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

/**
 * Inicializa el calendario con datos pre-cargados del servidor.
 * Maneja la conversión de tipos y renderizado inicial.
 * @param {Object} datos - Objeto con claves de mes y valores de arrays de días
 * @param {number} anio - Año a renderizar
 */
function inicializarCalendarioConDatos(datos, anio) {
    diasSeleccionadosPorMes = {};
    
    if (datos) {
        Object.keys(datos).forEach(mesKey => {
            const mes = parseInt(mesKey);
            // Asegurar que los días sean enteros
            const dias = Array.isArray(datos[mesKey]) ? datos[mesKey].map(d => parseInt(d)) : [];
            diasSeleccionadosPorMes[mes] = dias;
        });
    }

    // Renderizar los 12 meses
    for (let mes = 1; mes <= 12; mes++) {
        const dias = diasSeleccionadosPorMes[mes] || [];
        renderizarCalendarioMes(mes, anio, dias);
    }
    
    actualizarDiasSeleccionados();
}

// Variables globales para festivos y temporadas
let festivosPorMes = {};
let temporadasPorMes = {};

/**
 * Establece los festivos y temporadas para el año actual.
 * @param {Object} festivos - Objeto con mes como clave y array de días como valor
 * @param {Object} temporadas - Objeto con mes como clave y array de días como valor
 */
function establecerFestivosYTemporadas(festivos, temporadas) {
    festivosPorMes = {};
    if (festivos) {
        Object.keys(festivos).forEach(function(k) { festivosPorMes[parseInt(k)] = festivos[k]; });
    }
    temporadasPorMes = {};
    if (temporadas) {
        Object.keys(temporadas).forEach(function(k) { temporadasPorMes[parseInt(k)] = temporadas[k]; });
    }
}

/**
 * Construye el texto del tooltip para un día específico.
 * @param {number} dia - Día del mes
 * @param {number} mes - Mes (1-12)
 * @param {number} anio - Año
 * @param {boolean} esSeleccionado - Si el día está seleccionado
 * @returns {string} Texto del tooltip
 */
function construirTooltip(dia, mes, anio, esSeleccionado) {
    // Validar parámetros
    if (!dia || !mes || !anio) {
        return '';
    }
    
    const mesesNombres = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                          'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
    
    // Validar que el mes esté en rango válido
    if (mes < 1 || mes > 12) {
        return `${dia}/${mes}/${anio}`;
    }
    
    const fechaCompleta = `${dia} de ${mesesNombres[mes - 1]} de ${anio}`;
    const tipos = [];
    
    // Verificar si es festivo (con validación de existencia de variables)
    if (typeof festivosPorMes !== 'undefined' && festivosPorMes[mes] && Array.isArray(festivosPorMes[mes]) && festivosPorMes[mes].includes(dia)) {
        tipos.push('Festivo');
    }
    
    // Verificar si es temporada (con validación de existencia de variables)
    if (typeof temporadasPorMes !== 'undefined' && temporadasPorMes[mes] && Array.isArray(temporadasPorMes[mes]) && temporadasPorMes[mes].includes(dia)) {
        tipos.push('Temporada');
    }
    
    // Verificar si es mantenimiento (seleccionado)
    // Regla de negocio: un día NO puede ser a la vez festivo y mantenimiento.
    // Solo consideramos \"Mantenimiento\" cuando el tipo actual es mantenimiento.
    const tipoActual = (typeof window !== 'undefined' && window.tipoDiasEspeciales) ? window.tipoDiasEspeciales : 'festivo';
    if (esSeleccionado && tipoActual === 'mantenimiento') {
        tipos.push('Mantenimiento');
    }
    
    // Construir el texto del tooltip
    let tooltip = fechaCompleta;
    
    if (tipos.length > 0) {
        tooltip += '\n' + tipos.join(' • ');
    } else {
        tooltip += '\nDía normal';
    }
    
    return tooltip;
}

/**
 * Renderiza un calendario mensual interactivo.
 * @param {number} mes - Número del mes (1-12)
 * @param {number} anio - Año
 * @param {Array<number>} diasIniciales - Días ya seleccionados (opcional)
 */
function renderizarCalendarioMes(mes, anio, diasIniciales = []) {
    const contenedor = document.getElementById(`calendario-${mes}`);
    if (!contenedor) return;
    
    // Inicializar días seleccionados para este mes
    if (!diasSeleccionadosPorMes[mes]) {
        diasSeleccionadosPorMes[mes] = [...diasIniciales];
    } else {
        // Si ya existe, mantener los seleccionados pero agregar los iniciales
        diasIniciales.forEach(dia => {
            if (!diasSeleccionadosPorMes[mes].includes(dia)) {
                diasSeleccionadosPorMes[mes].push(dia);
            }
        });
    }
    
    // Limpiar contenedor
    contenedor.innerHTML = '';
    
    // Agregar encabezados de días de la semana
    DIAS_SEMANA.forEach(dia => {
        const header = document.createElement('div');
        header.className = 'calendario-dia-header';
        header.textContent = dia;
        contenedor.appendChild(header);
    });
    
    // Obtener primer día del mes y cantidad de días
    const primerDia = new Date(anio, mes - 1, 1);
    const ultimoDia = new Date(anio, mes, 0);
    const diaSemanaInicio = primerDia.getDay(); // 0 = Domingo, 1 = Lunes, etc.
    const totalDias = ultimoDia.getDate();
    
    // Agregar celdas vacías antes del primer día
    for (let i = 0; i < diaSemanaInicio; i++) {
        const celdaVacia = document.createElement('div');
        celdaVacia.className = 'calendario-dia vacio';
        contenedor.appendChild(celdaVacia);
    }
    
    // Determinar tipo actual (festivo o mantenimiento) para aplicar estilos adecuados
    const tipoSelect = document.getElementById('id_tipo');
    const tipoActual = tipoSelect ? tipoSelect.value : (typeof window !== 'undefined' && window.tipoDiasEspeciales ? window.tipoDiasEspeciales : 'festivo');
    
    // Agregar días del mes
    for (let dia = 1; dia <= totalDias; dia++) {
        const celdaDia = document.createElement('div');
        celdaDia.className = 'calendario-dia';
        celdaDia.textContent = dia;
        celdaDia.dataset.dia = dia;
        celdaDia.dataset.mes = mes;
        
        // Verificar si está seleccionado
        const esSeleccionado = diasSeleccionadosPorMes[mes] && diasSeleccionadosPorMes[mes].includes(dia);
        
        // Verificar si es festivo
        if (festivosPorMes[mes] && festivosPorMes[mes].includes(dia)) {
            celdaDia.classList.add('festivo');
        }
        
        // Verificar si es temporada
        if (temporadasPorMes[mes] && temporadasPorMes[mes].includes(dia)) {
            celdaDia.classList.add('temporada');
        }
        
        // Marcar como seleccionado si está en la lista (solo aplica para mantenimiento).
        // Para festivos, el estilo principal es la clase 'festivo', no 'seleccionado'.
        if (esSeleccionado && tipoActual === 'mantenimiento') {
            celdaDia.classList.add('seleccionado');
        }
        
        // Agregar tooltip informativo
        const tooltip = construirTooltip(dia, mes, anio, esSeleccionado);
        celdaDia.setAttribute('title', tooltip);
        
        // Event listener para seleccionar/deseleccionar
        celdaDia.addEventListener('click', function() {
            toggleDia(mes, dia);
        });
        
        contenedor.appendChild(celdaDia);
    }
    
    // Actualizar resumen del mes
    actualizarResumenMes(mes);
}

/**
 * Alterna la selección de un día.
 * @param {number} mes - Número del mes (1-12)
 * @param {number} dia - Día del mes
 */
function toggleDia(mes, dia) {
    if (!diasSeleccionadosPorMes[mes]) {
        diasSeleccionadosPorMes[mes] = [];
    }
    
    // Determinar tipo actual (festivo o mantenimiento)
    const tipoSelect = document.getElementById('id_tipo');
    const tipoActual = tipoSelect ? tipoSelect.value : (typeof window !== 'undefined' && window.tipoDiasEspeciales ? window.tipoDiasEspeciales : 'festivo');
    
    // Regla: si estamos configurando mantenimiento, NO permitir seleccionar días festivos
    if (tipoActual === 'mantenimiento') {
        if (festivosPorMes[mes] && Array.isArray(festivosPorMes[mes]) && festivosPorMes[mes].includes(dia)) {
            // Día festivo: no se puede marcar como mantenimiento
            console.warn(`Día ${dia}/${mes} es festivo. No se puede marcar como mantenimiento.`);
            return;
        }
    }
    
    const index = diasSeleccionadosPorMes[mes].indexOf(dia);
    const celda = document.querySelector(`#calendario-${mes} .calendario-dia[data-dia="${dia}"]`);
    
    // Obtener el año actual del selector
    const anioInput = document.getElementById('id_anio');
    const anio = anioInput ? parseInt(anioInput.value) : new Date().getFullYear();
    
    if (index > -1) {
        // Deseleccionar
        diasSeleccionadosPorMes[mes].splice(index, 1);
        
        if (tipoActual === 'festivo') {
            // Quitar del mapa de festivos en memoria y de la clase visual
            if (festivosPorMes[mes]) {
                festivosPorMes[mes] = festivosPorMes[mes].filter(d => d !== dia);
            }
            if (celda) {
                celda.classList.remove('festivo');
            }
        }
        
        if (celda) {
            // Quitar siempre 'seleccionado' al desmarcar (por seguridad)
            celda.classList.remove('seleccionado');
            
            // Actualizar tooltip
            const esSeleccionado = false;
            const tooltip = construirTooltip(dia, mes, anio, esSeleccionado);
            celda.setAttribute('title', tooltip);
        }
    } else {
        // Seleccionar
        diasSeleccionadosPorMes[mes].push(dia);
        diasSeleccionadosPorMes[mes].sort((a, b) => a - b);
        
        if (tipoActual === 'festivo') {
            // Añadir al mapa de festivos en memoria y marcar en rojo inmediatamente
            if (!festivosPorMes[mes]) {
                festivosPorMes[mes] = [];
            }
            if (!festivosPorMes[mes].includes(dia)) {
                festivosPorMes[mes].push(dia);
            }
            if (celda) {
                celda.classList.add('festivo');
            }
        }
        
        if (celda) {
            // Solo resaltar en azul cuando el tipo es mantenimiento.
            if (tipoActual === 'mantenimiento') {
                celda.classList.add('seleccionado');
            }
            // Actualizar tooltip
            const esSeleccionado = true;
            const tooltip = construirTooltip(dia, mes, anio, esSeleccionado);
            celda.setAttribute('title', tooltip);
        }
    }
    
    // Actualizar resumen y contador
    actualizarResumenMes(mes);
    actualizarDiasSeleccionados();
}

/**
 * Actualiza el resumen visual de días seleccionados para un mes.
 * @param {number} mes - Número del mes (1-12)
 */
function actualizarResumenMes(mes) {
    const dias = diasSeleccionadosPorMes[mes] || [];
    const resumenTexto = document.getElementById(`dias-texto-${mes}`);
    const badge = document.getElementById(`badge-${mes}`);
    
    if (resumenTexto) {
        if (dias.length === 0) {
            resumenTexto.textContent = 'Ninguno';
        } else {
            resumenTexto.textContent = dias.join(', ');
        }
    }
    
    if (badge) {
        badge.textContent = `${dias.length} día${dias.length !== 1 ? 's' : ''}`;
    }
}

/**
 * Obtiene todos los días seleccionados agrupados por mes.
 * @returns {Object} Objeto con mes como clave y array de días como valor
 */
function obtenerDiasSeleccionados() {
    const resultado = {};
    
    for (let mes = 1; mes <= 12; mes++) {
        if (diasSeleccionadosPorMes[mes] && diasSeleccionadosPorMes[mes].length > 0) {
            resultado[mes] = [...diasSeleccionadosPorMes[mes]];
        }
    }
    
    return resultado;
}

/**
 * Actualiza el campo hidden del formulario con los días seleccionados.
 */
function actualizarDiasSeleccionados() {
    const dias = obtenerDiasSeleccionados();
    const campoHidden = document.getElementById('id_dias_seleccionados');
    
    if (campoHidden) {
        campoHidden.value = JSON.stringify(dias);
    }
    // Guardado atómico: si el estado volvió a ser el publicado, el botón se apaga.
    if (window.guardiaGuardadoAnual) window.guardiaGuardadoAnual.revisar();
}

/**
 * Carga días especiales existentes desde el servidor.
 * @param {string} tipo - Tipo de día especial ('festivo' o 'mantenimiento')
 * @param {number} anio - Año a cargar
 */
function cargarDiasExistentes(tipo, anio) {
    if (!tipo || !anio) {
        console.error('Tipo y año son requeridos para cargar días existentes');
        return;
    }
    
    fetch(`/turnos/api/dias-especiales-por-tipo/?tipo=${tipo}&anio=${anio}`)
        .then(response => {
            if (!response.ok) {
                throw new Error(`Error HTTP: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.por_mes) {
                diasSeleccionadosPorMes = {};
                
                for (const mes in data.por_mes) {
                    const mesNum = parseInt(mes);
                    diasSeleccionadosPorMes[mesNum] = data.por_mes[mes];
                    renderizarCalendarioMes(mesNum, anio, data.por_mes[mes]);
                }
                
                actualizarDiasSeleccionados();
            } else {
                // Si no hay días existentes, limpiar todos los calendarios
                diasSeleccionadosPorMes = {};
                for (let mes = 1; mes <= 12; mes++) {
                    renderizarCalendarioMes(mes, anio, []);
                }
                actualizarDiasSeleccionados();
            }
            
            // Re-renderizar todos los meses para asegurar que festivos y temporadas se muestren
            for (let mes = 1; mes <= 12; mes++) {
                const dias = diasSeleccionadosPorMes[mes] || [];
                renderizarCalendarioMes(mes, anio, dias);
            }
            // Lo recién cargado del servidor ES lo publicado, no un cambio del usuario:
            // se toma como nueva referencia para el guardado atómico.
            if (window.guardiaGuardadoAnual) window.guardiaGuardadoAnual.reiniciar();
        })
        .catch(error => {
            console.error('Error al cargar días existentes:', error);
            // En caso de error, limpiar calendarios
            diasSeleccionadosPorMes = {};
            for (let mes = 1; mes <= 12; mes++) {
                renderizarCalendarioMes(mes, anio, []);
            }
            actualizarDiasSeleccionados();
            if (window.guardiaGuardadoAnual) window.guardiaGuardadoAnual.reiniciar();
        });
}

/**
 * Valida que haya al menos un día seleccionado.
 * @returns {boolean} True si hay al menos un día seleccionado
 */
function validarSeleccion() {
    const dias = obtenerDiasSeleccionados();
    const totalDias = Object.values(dias).reduce((sum, diasMes) => sum + diasMes.length, 0);
    return totalDias > 0;
}

