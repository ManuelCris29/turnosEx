/**
 * Calendario interactivo para selección de días de temporada por mes.
 * Permite seleccionar múltiples días en cada mes del año.
 */

// Almacenar días seleccionados por mes
let diasSeleccionadosPorMes = {};

// Nombres de los días de la semana
const DIAS_SEMANA = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];

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
    
    // Agregar días del mes
    for (let dia = 1; dia <= totalDias; dia++) {
        const celdaDia = document.createElement('div');
        celdaDia.className = 'calendario-dia';
        celdaDia.textContent = dia;
        celdaDia.dataset.dia = dia;
        celdaDia.dataset.mes = mes;
        
        // Marcar como seleccionado si está en la lista
        if (diasSeleccionadosPorMes[mes] && diasSeleccionadosPorMes[mes].includes(dia)) {
            celdaDia.classList.add('seleccionado');
        }
        
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
    
    const index = diasSeleccionadosPorMes[mes].indexOf(dia);
    const celda = document.querySelector(`#calendario-${mes} .calendario-dia[data-dia="${dia}"]`);
    
    if (index > -1) {
        // Deseleccionar
        diasSeleccionadosPorMes[mes].splice(index, 1);
        if (celda) {
            celda.classList.remove('seleccionado');
        }
    } else {
        // Seleccionar
        diasSeleccionadosPorMes[mes].push(dia);
        diasSeleccionadosPorMes[mes].sort((a, b) => a - b);
        if (celda) {
            celda.classList.add('seleccionado');
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
}

/**
 * Selecciona un rango de días en un mes.
 * @param {number} mes - Número del mes (1-12)
 * @param {number} diaInicio - Día de inicio
 * @param {number} diaFin - Día de fin
 */
function seleccionarRango(mes, diaInicio, diaFin) {
    if (!diasSeleccionadosPorMes[mes]) {
        diasSeleccionadosPorMes[mes] = [];
    }
    
    const inicio = Math.min(diaInicio, diaFin);
    const fin = Math.max(diaInicio, diaFin);
    
    for (let dia = inicio; dia <= fin; dia++) {
        if (!diasSeleccionadosPorMes[mes].includes(dia)) {
            diasSeleccionadosPorMes[mes].push(dia);
        }
    }
    
    diasSeleccionadosPorMes[mes].sort((a, b) => a - b);
    
    // Re-renderizar el calendario para actualizar visualmente
    const anio = parseInt(document.getElementById('id_anio').value) || new Date().getFullYear();
    renderizarCalendarioMes(mes, anio, diasSeleccionadosPorMes[mes]);
    actualizarDiasSeleccionados();
}

/**
 * Carga días de temporada existentes desde el servidor.
 * @param {number} anio - Año a cargar
 */
function cargarTemporadasExistentes(anio) {
    fetch(`/turnos/api/dias-temporada/?anio=${anio}`)
        .then(response => response.json())
        .then(data => {
            if (data.por_mes) {
                diasSeleccionadosPorMes = {};
                
                for (const mes in data.por_mes) {
                    const mesNum = parseInt(mes);
                    diasSeleccionadosPorMes[mesNum] = data.por_mes[mes];
                    renderizarCalendarioMes(mesNum, anio, data.por_mes[mes]);
                }
                
                actualizarDiasSeleccionados();
            }
        })
        .catch(error => {
            console.error('Error al cargar temporadas existentes:', error);
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


