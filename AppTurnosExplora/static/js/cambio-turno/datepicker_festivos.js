/**
 * Módulo común para inicializar datepickers con festivos colombianos
 * 
 * Este módulo proporciona funciones reutilizables para:
 * - Cargar festivos (calculados + BD)
 * - Marcar festivos en calendarios Flatpickr
 * - Verificar si una fecha es festivo
 * - Inicializar datepickers con festivos marcados
 * 
 * Uso:
 *   import { inicializarDatepickerFestivos } from './datepicker_festivos.js';
 *   
 *   inicializarDatepickerFestivos({
 *       input: document.getElementById('fecha'),
 *       minDate: '2025-01-01',
 *       onDateChange: (fecha) => { // callback personalizado },
 *       indicadorFestivo: document.getElementById('indicador_festivo'),
 *       descripcionFestivo: document.getElementById('descripcion_festivo')
 *   });
 */

// Cache global de festivos (compartido entre todas las instancias)
let festivosCacheGlobal = null;
// Promesa de carga en curso para evitar peticiones duplicadas simultáneas
let festivosCargaEnCurso = null;

// Cache global de días de mantenimiento (compartido entre todas las instancias)
let mantenimientoCacheGlobal = null;
// Promesa de carga en curso para evitar peticiones duplicadas simultáneas
let mantenimientoCargaEnCurso = null;

// Cache global de días de temporada (compartido entre todas las instancias)
// Estructura: Map con clave "año" -> Map de fechas
let temporadaCacheGlobal = new Map();
// Promesas de carga en curso por año para evitar peticiones duplicadas simultáneas
let temporadaCargaEnCurso = new Map();

/**
 * Incrementa una fecha en formato YYYY-MM-DD en un día
 * @param {string} fecha - Fecha en formato YYYY-MM-DD
 * @returns {string} Fecha incrementada en un día
 */
function incrementarFecha(fecha) {
    const fechaObj = new Date(fecha + 'T00:00:00');
    fechaObj.setDate(fechaObj.getDate() + 1);
    const año = fechaObj.getFullYear();
    const mes = String(fechaObj.getMonth() + 1).padStart(2, '0');
    const dia = String(fechaObj.getDate()).padStart(2, '0');
    return `${año}-${mes}-${dia}`;
}

// Forzar lunes como primer día de la semana en el locale español de Flatpickr.
// Sin esto, la cuadrícula (domingo primero) y las cabeceras Lun–Dom quedan desalineadas.
(function() {
    function aplicarFirstDayOfWeekLunes() {
        if (typeof flatpickr !== 'undefined' && flatpickr.l10ns) {
            if (flatpickr.l10ns.es) {
                flatpickr.l10ns.es.firstDayOfWeek = 1;
            }
            if (flatpickr.l10ns.default) {
                flatpickr.l10ns.default.firstDayOfWeek = 1;
            }
        }
    }
    if (typeof flatpickr !== 'undefined') {
        aplicarFirstDayOfWeekLunes();
    } else {
        window.addEventListener('load', aplicarFirstDayOfWeekLunes);
    }
})();

/**
 * Carga días festivos combinando cálculo JavaScript + API de BD
 * 
 * @param {number|null} añoEspecifico - Año específico a cargar, o null para rango por defecto
 * @returns {Promise<Map>} Map con fecha (YYYY-MM-DD) como clave y descripción como valor
 */
function cargarDiasFestivos(añoEspecifico = null) {
    // Si ya tenemos el caché y no se solicita un año específico, retornar caché
    if (festivosCacheGlobal !== null && añoEspecifico === null) {
        return Promise.resolve(festivosCacheGlobal);
    }
    
    // Si hay una carga en curso, esperar a que termine en lugar de iniciar otra
    if (festivosCargaEnCurso !== null && añoEspecifico === null) {
        return festivosCargaEnCurso.then(() => festivosCacheGlobal);
    }
    
    // Si se solicita un año específico y ya está en caché, verificar antes de cargar
    if (festivosCacheGlobal !== null && añoEspecifico !== null) {
        // Verificar si tenemos al menos un festivo para ese año en el caché
        // (no necesitamos verificar todos los días, solo verificar si hay alguno)
        const fechaInicioAño = `${añoEspecifico}-01-01`;
        const fechaFinAño = `${añoEspecifico}-12-31`;
        let tieneDatosParaAño = false;
        
        // Verificar si tenemos datos para ese año en el caché (muestreo cada 30 días para eficiencia)
        for (let fecha = fechaInicioAño; fecha <= fechaFinAño; ) {
            if (festivosCacheGlobal.has(fecha)) {
                tieneDatosParaAño = true;
                break;
            }
            // Incrementar 30 días para muestreo eficiente
            const fechaObj = new Date(fecha + 'T00:00:00');
            fechaObj.setDate(fechaObj.getDate() + 30);
            const año = fechaObj.getFullYear();
            const mes = String(fechaObj.getMonth() + 1).padStart(2, '0');
            const dia = String(fechaObj.getDate()).padStart(2, '0');
            fecha = `${año}-${mes}-${dia}`;
            if (fecha > fechaFinAño) break;
        }
        
        // Si tenemos datos para ese año, retornar caché sin recargar
        if (tieneDatosParaAño) {
            return Promise.resolve(festivosCacheGlobal);
        }
    }
    
    const añoActual = new Date().getFullYear();
    const añoInicio = añoActual;      // Solo año actual
    const añoFin = añoActual + 2;     // Solo 2 años futuros (suficiente para planificación)
    
    // Calcular festivos de Colombia
    let festivosCalculados;
    if (añoEspecifico !== null) {
        if (añoEspecifico < añoInicio || añoEspecifico > añoFin) {
            // Año fuera del rango inicial, calcular solo para ese año
            festivosCalculados = obtenerFestivosRango(añoEspecifico, añoEspecifico);
        } else {
            // Año dentro del rango, calcular rango completo
            festivosCalculados = obtenerFestivosRango(añoInicio, añoFin);
        }
    } else {
        // Calcular rango completo por defecto
        festivosCalculados = obtenerFestivosRango(añoInicio, añoFin);
    }
    
    // Marcar que hay una carga en curso
    festivosCargaEnCurso = fetch('/turnos/api/dias-festivos/', {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        }
    })
    .then(response => response.json())
    .then(data => {
        // Combinar festivos calculados + festivos de BD
        if (festivosCacheGlobal === null) {
            festivosCacheGlobal = new Map(festivosCalculados);
        } else {
            // Agregar nuevos festivos calculados al caché existente
            festivosCalculados.forEach((descripcion, fecha) => {
                festivosCacheGlobal.set(fecha, descripcion);
            });
        }
        
        if (data.festivos) {
            // Los festivos de BD tienen prioridad (pueden sobrescribir o agregar)
            data.festivos.forEach(festivo => {
                festivosCacheGlobal.set(festivo.fecha, festivo.descripcion || 'Día festivo');
            });
        }
        
        // Limpiar la promesa de carga en curso
        festivosCargaEnCurso = null;
        return festivosCacheGlobal;
    })
    .catch(error => {
        console.error('Error al cargar días festivos de BD:', error);
        // Si falla la BD, usar solo los calculados
        if (festivosCacheGlobal === null) {
            festivosCacheGlobal = festivosCalculados || new Map();
        } else {
            festivosCalculados.forEach((descripcion, fecha) => {
                festivosCacheGlobal.set(fecha, descripcion);
            });
        }
        // Limpiar la promesa de carga en curso incluso en caso de error
        festivosCargaEnCurso = null;
        return festivosCacheGlobal;
    });
    
    return festivosCargaEnCurso;
}

/**
 * Carga días de mantenimiento desde la API
 * 
 * @param {number|null} añoEspecifico - Año específico a cargar, o null para rango por defecto
 * @returns {Promise<Map>} Map con fecha (YYYY-MM-DD) como clave y descripción como valor
 */
function cargarDiasMantenimiento(añoEspecifico = null) {
    // Si ya tenemos el caché y no se solicita un año específico, retornar caché
    if (mantenimientoCacheGlobal !== null && añoEspecifico === null) {
        return Promise.resolve(mantenimientoCacheGlobal);
    }
    
    // Si hay una carga en curso, esperar a que termine en lugar de iniciar otra
    if (mantenimientoCargaEnCurso !== null && añoEspecifico === null) {
        return mantenimientoCargaEnCurso.then(() => mantenimientoCacheGlobal);
    }
    
    // Si se solicita un año específico y ya está en caché, verificar antes de cargar
    if (mantenimientoCacheGlobal !== null && añoEspecifico !== null) {
        // Verificar si tenemos al menos un día de mantenimiento para ese año en el caché
        // (no necesitamos verificar todos los días, solo verificar si hay alguno)
        const fechaInicioAño = `${añoEspecifico}-01-01`;
        const fechaFinAño = `${añoEspecifico}-12-31`;
        let tieneDatosParaAño = false;
        
        // Verificar si tenemos datos para ese año en el caché (muestreo cada 30 días para eficiencia)
        for (let fecha = fechaInicioAño; fecha <= fechaFinAño; ) {
            if (mantenimientoCacheGlobal.has(fecha)) {
                tieneDatosParaAño = true;
                break;
            }
            // Incrementar 30 días para muestreo eficiente
            const fechaObj = new Date(fecha + 'T00:00:00');
            fechaObj.setDate(fechaObj.getDate() + 30);
            const año = fechaObj.getFullYear();
            const mes = String(fechaObj.getMonth() + 1).padStart(2, '0');
            const dia = String(fechaObj.getDate()).padStart(2, '0');
            fecha = `${año}-${mes}-${dia}`;
            if (fecha > fechaFinAño) break;
        }
        
        // Si tenemos datos para ese año, retornar caché sin recargar
        if (tieneDatosParaAño) {
            return Promise.resolve(mantenimientoCacheGlobal);
        }
    }
    
    const añoActual = new Date().getFullYear();
    const añoInicio = añoActual;      // Solo año actual
    const añoFin = añoActual + 2;     // Solo 2 años futuros (suficiente para planificación)
    
    // Cargar días de mantenimiento de la BD para el rango de años
    const añosACargar = [];
    if (añoEspecifico !== null) {
        // Si se solicita un año específico fuera del rango inicial, cargar solo ese año
        if (añoEspecifico < añoInicio || añoEspecifico > añoFin) {
            añosACargar.push(añoEspecifico);
        } else {
            // Si está dentro del rango, cargar el rango completo para tener datos consistentes
            for (let año = añoInicio; año <= añoFin; año++) {
                añosACargar.push(año);
            }
        }
    } else {
        // Cargar rango inicial reducido
        for (let año = añoInicio; año <= añoFin; año++) {
            añosACargar.push(año);
        }
    }
    
    // Cargar días de mantenimiento para todos los años del rango
    const promesas = añosACargar.map(año => {
        return fetch(`/turnos/api/dias-especiales-por-tipo/?tipo=mantenimiento&anio=${año}`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            const mantenimientoMap = new Map();
            if (data.dias) {
                data.dias.forEach(dia => {
                    mantenimientoMap.set(dia.fecha, dia.descripcion || 'Día de mantenimiento');
                });
            }
            return mantenimientoMap;
        })
        .catch(error => {
            console.error(`Error al cargar días de mantenimiento para año ${año}:`, error);
            return new Map();
        });
    });
    
    // Marcar que hay una carga en curso
    mantenimientoCargaEnCurso = Promise.all(promesas).then(maps => {
        // Combinar todos los Maps en uno solo
        if (mantenimientoCacheGlobal === null) {
            mantenimientoCacheGlobal = new Map();
        }
        
        maps.forEach(map => {
            map.forEach((descripcion, fecha) => {
                mantenimientoCacheGlobal.set(fecha, descripcion);
            });
        });
        
        // Limpiar la promesa de carga en curso
        mantenimientoCargaEnCurso = null;
        return mantenimientoCacheGlobal;
    }).catch(error => {
        console.error('Error al cargar días de mantenimiento:', error);
        // Limpiar la promesa de carga en curso incluso en caso de error
        mantenimientoCargaEnCurso = null;
        return mantenimientoCacheGlobal || new Map();
    });
    
    return mantenimientoCargaEnCurso;
}

/**
 * Verifica si una fecha es festivo y actualiza el indicador visual
 * 
 * @param {string} fecha - Fecha en formato YYYY-MM-DD
 * @param {HTMLElement|null} indicador - Elemento HTML para mostrar/ocultar indicador
 * @param {HTMLElement|null} descripcion - Elemento HTML para mostrar descripción del festivo
 */
function verificarDiaFestivo(fecha, indicador = null, descripcion = null) {
    if (!fecha || !indicador || !descripcion) {
        return;
    }
    
    cargarDiasFestivos().then(festivos => {
        const descripcionFestivo = festivos.get(fecha);
        if (descripcionFestivo) {
            descripcion.textContent = descripcionFestivo;
            indicador.style.display = 'block';
        } else {
            indicador.style.display = 'none';
        }
    });
}

/**
 * Verifica si una fecha es día de mantenimiento y actualiza el indicador visual
 * 
 * @param {string} fecha - Fecha en formato YYYY-MM-DD
 * @param {HTMLElement|null} indicador - Elemento HTML para mostrar/ocultar indicador
 * @param {HTMLElement|null} descripcion - Elemento HTML para mostrar descripción
 * @returns {Promise<boolean>} Promise que resuelve con true si es día de mantenimiento, false en caso contrario
 */
function verificarDiaMantenimiento(fecha, indicador = null, descripcion = null) {
    if (!fecha) {
        return Promise.resolve(false);
    }
    
    // Extraer año de la fecha
    const año = parseInt(fecha.split('-')[0]);
    
    return cargarDiasMantenimiento(año).then(mantenimiento => {
        const descripcionMantenimiento = mantenimiento.get(fecha);
        const esMantenimiento = !!descripcionMantenimiento;
        
        if (indicador && descripcion) {
            if (esMantenimiento) {
                descripcion.textContent = descripcionMantenimiento;
                indicador.style.display = 'block';
            } else {
                indicador.style.display = 'none';
            }
        }
        
        return esMantenimiento;
    });
}

/**
 * Marca días festivos en un calendario Flatpickr
 * 
 * @param {Object} instance - Instancia de Flatpickr
 * @param {Map} festivosMap - Map con festivos (fecha -> descripción)
 */
function marcarFestivosEnCalendario(instance, festivosMap) {
    if (!instance || !instance.calendarContainer || !festivosMap) {
        return;
    }
    
    const fechasFestivos = Array.from(festivosMap.keys());
    const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day:not(.flatpickr-disabled)');
    
    dayElements.forEach(day => {
        if (day.dateObj) {
            const dayDate = new Date(day.dateObj);
            const dayDateStr = dayDate.toISOString().split('T')[0];
            
            if (fechasFestivos.includes(dayDateStr)) {
                // Es festivo: agregar clase y actualizar tooltip
                day.classList.add('festivo');
                day.title = festivosMap.get(dayDateStr) || 'Día festivo';
            } else {
                // No es festivo: remover clase si existe (por si cambió de mes/año)
                day.classList.remove('festivo');
            }
        }
    });
}

/**
 * Marca días de mantenimiento en un calendario Flatpickr
 * 
 * @param {Object} instance - Instancia de Flatpickr
 * @param {Map} mantenimientoMap - Map con días de mantenimiento (fecha -> descripción)
 */
function marcarMantenimientoEnCalendario(instance, mantenimientoMap) {
    if (!instance || !instance.calendarContainer || !mantenimientoMap) {
        return;
    }
    
    const fechasMantenimiento = Array.from(mantenimientoMap.keys());
    const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day:not(.flatpickr-disabled)');
    
    dayElements.forEach(day => {
        if (day.dateObj) {
            const dayDate = new Date(day.dateObj);
            const dayDateStr = dayDate.toISOString().split('T')[0];
            
            if (fechasMantenimiento.includes(dayDateStr)) {
                // Es día de mantenimiento: agregar clase y actualizar tooltip
                day.classList.add('mantenimiento');
                const descripcion = mantenimientoMap.get(dayDateStr) || 'Día de mantenimiento';
                
                // Si ya tiene un title (festivo), agregar información de mantenimiento
                const titleActual = day.title || '';
                if (titleActual && !titleActual.includes(descripcion)) {
                    day.title = titleActual + ' | ' + descripcion;
                } else if (!titleActual) {
                    day.title = descripcion;
                }
            } else {
                // No es día de mantenimiento: remover clase si existe (por si cambió de mes/año)
                day.classList.remove('mantenimiento');
                
                // Limpiar tooltip de mantenimiento si existe, pero mantener festivo si hay
                const titleActual = day.title || '';
                if (titleActual.includes(' | ')) {
                    const partes = titleActual.split(' | ');
                    const parteFestivo = partes.find(p => !p.includes('mantenimiento'));
                    day.title = parteFestivo || titleActual.replace(/ \| .*mantenimiento.*/i, '');
                } else if (titleActual.toLowerCase().includes('mantenimiento')) {
                    day.title = '';
                }
            }
        }
    });
}

/**
 * Carga días de temporada desde el API
 * 
 * @param {number} anio - Año específico a cargar
 * @returns {Promise<Map>} Map con fecha (YYYY-MM-DD) como clave y descripción como valor
 */
function cargarDiasTemporada(anio = null) {
    if (anio === null) {
        anio = new Date().getFullYear();
    }
    
    // Si ya tenemos el caché para este año, retornar caché
    if (temporadaCacheGlobal.has(anio)) {
        return Promise.resolve(temporadaCacheGlobal.get(anio));
    }
    
    // Si hay una carga en curso para este año, esperar a que termine
    if (temporadaCargaEnCurso.has(anio)) {
        return temporadaCargaEnCurso.get(anio).then(() => temporadaCacheGlobal.get(anio));
    }
    
    // Marcar que hay una carga en curso para este año
    const promesaCarga = fetch(`/turnos/api/dias-temporada/?anio=${anio}`)
        .then(response => response.json())
        .then(data => {
            const temporadaMap = new Map();
            
            // El endpoint devuelve {por_mes: {mes: [dias]}, ...} o {temporadas: [...], por_mes: {...}}
            if (data.por_mes) {
                // Convertir estructura {mes: [dias]} a Map de fechas YYYY-MM-DD
                for (const mes in data.por_mes) {
                    const dias = data.por_mes[mes];
                    if (Array.isArray(dias)) {
                        dias.forEach(dia => {
                            const fechaStr = `${anio}-${String(mes).padStart(2, '0')}-${String(dia).padStart(2, '0')}`;
                            temporadaMap.set(fechaStr, 'Día de temporada');
                        });
                    }
                }
            } else if (data.temporadas && Array.isArray(data.temporadas)) {
                // Si no hay por_mes, intentar con temporadas (array de objetos con fecha)
                data.temporadas.forEach(temp => {
                    if (temp.fecha) {
                        temporadaMap.set(temp.fecha, temp.descripcion || 'Día de temporada');
                    }
                });
            }
            
            // Guardar en caché
            temporadaCacheGlobal.set(anio, temporadaMap);
            
            // Limpiar la promesa de carga en curso
            temporadaCargaEnCurso.delete(anio);
            
            return temporadaMap;
        })
        .catch(error => {
            console.error('Error cargando días de temporada:', error);
            // Limpiar la promesa de carga en curso incluso en caso de error
            temporadaCargaEnCurso.delete(anio);
            const mapaVacio = new Map();
            temporadaCacheGlobal.set(anio, mapaVacio);
            return mapaVacio;
        });
    
    // Guardar la promesa de carga en curso
    temporadaCargaEnCurso.set(anio, promesaCarga);
    
    return promesaCarga;
}

/**
 * Marca días festivos en un calendario Flatpickr incluyendo días deshabilitados
 * 
 * @param {Object} instance - Instancia de Flatpickr
 * @param {Map} festivosMap - Map con festivos (fecha -> descripción)
 */
function marcarFestivosEnCalendarioIncluyendoDeshabilitados(instance, festivosMap) {
    if (!instance || !instance.calendarContainer || !festivosMap) {
        return;
    }
    
    const fechasFestivos = Array.from(festivosMap.keys());
    // Incluir TODOS los días, incluso los deshabilitados
    const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day');
    
    dayElements.forEach(day => {
        if (day.dateObj) {
            const dayDate = new Date(day.dateObj);
            const dayDateStr = dayDate.toISOString().split('T')[0];
            
            if (fechasFestivos.includes(dayDateStr)) {
                // Es festivo: agregar clase y actualizar tooltip
                day.classList.add('festivo');
                day.title = festivosMap.get(dayDateStr) || 'Día festivo';
            } else {
                // No es festivo: remover clase si existe (por si cambió de mes/año)
                day.classList.remove('festivo');
            }
        }
    });
}

/**
 * Marca días de mantenimiento en un calendario Flatpickr incluyendo días deshabilitados
 * 
 * @param {Object} instance - Instancia de Flatpickr
 * @param {Map} mantenimientoMap - Map con días de mantenimiento (fecha -> descripción)
 */
function marcarMantenimientoEnCalendarioIncluyendoDeshabilitados(instance, mantenimientoMap) {
    if (!instance || !instance.calendarContainer || !mantenimientoMap) {
        return;
    }
    
    const fechasMantenimiento = Array.from(mantenimientoMap.keys());
    // Incluir TODOS los días, incluso los deshabilitados
    const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day');
    
    dayElements.forEach(day => {
        if (day.dateObj) {
            const dayDate = new Date(day.dateObj);
            const dayDateStr = dayDate.toISOString().split('T')[0];
            
            if (fechasMantenimiento.includes(dayDateStr)) {
                // Es día de mantenimiento: agregar clase y actualizar tooltip
                day.classList.add('mantenimiento');
                const descripcion = mantenimientoMap.get(dayDateStr) || 'Día de mantenimiento';
                
                // Si ya tiene un title (festivo), agregar información de mantenimiento
                const titleActual = day.title || '';
                if (titleActual && !titleActual.includes(descripcion)) {
                    day.title = titleActual + ' | ' + descripcion;
                } else if (!titleActual) {
                    day.title = descripcion;
                }
            } else {
                // No es día de mantenimiento: remover clase si existe (por si cambió de mes/año)
                day.classList.remove('mantenimiento');
                
                // Limpiar tooltip de mantenimiento si existe, pero mantener festivo si hay
                const titleActual = day.title || '';
                if (titleActual.includes(' | ')) {
                    const partes = titleActual.split(' | ');
                    const parteFestivo = partes.find(p => !p.includes('mantenimiento'));
                    day.title = parteFestivo || titleActual.replace(/ \| .*mantenimiento.*/i, '');
                } else if (titleActual.toLowerCase().includes('mantenimiento')) {
                    day.title = '';
                }
            }
        }
    });
}

/**
 * Marca domingos en el calendario Flatpickr (días deshabilitados por ser domingo).
 * Solo añade clase "domingo" si el día no tiene ya festivo/mantenimiento/temporada,
 * para que prevalezca el distintivo de esos tipos.
 *
 * @param {Object} instance - Instancia de Flatpickr
 */
function marcarDomingosEnCalendario(instance) {
    if (!instance || !instance.calendarContainer) {
        return;
    }
    const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day');
    const currentYear = instance.currentYear != null ? instance.currentYear : new Date().getFullYear();
    const currentMonth = instance.currentMonth != null ? instance.currentMonth : new Date().getMonth();

    dayElements.forEach(day => {
        let dayDate = null;
        if (day.dateObj) {
            dayDate = new Date(day.dateObj);
        } else {
            // Fallback: algunos entornos o versiones de Flatpickr pueden no tener dateObj en el elemento
            const isPrevOrNext = day.classList.contains('prevMonthDay') || day.classList.contains('nextMonthDay');
            if (!isPrevOrNext) {
                const dayNum = parseInt(day.textContent && day.textContent.trim(), 10);
                if (!isNaN(dayNum)) {
                    dayDate = new Date(currentYear, currentMonth, dayNum);
                }
            }
        }
        if (dayDate) {
            const esDomingo = dayDate.getDay() === 0;
            const yaTieneDistintivo = day.classList.contains('festivo') ||
                day.classList.contains('mantenimiento') ||
                day.classList.contains('temporada');
            if (esDomingo && !yaTieneDistintivo) {
                day.classList.add('domingo');
                if (!day.title) {
                    day.title = 'Domingo (no disponible)';
                }
            } else if (!esDomingo) {
                day.classList.remove('domingo');
            }
        }
    });
}

/**
 * Marca sábados en el calendario Flatpickr (días deshabilitados por ser sábado).
 * Solo añade clase "sabado" si el día no tiene ya festivo/mantenimiento/temporada,
 * para que prevalezca el distintivo de esos tipos.
 *
 * @param {Object} instance - Instancia de Flatpickr
 */
function marcarSabadosEnCalendario(instance) {
    if (!instance || !instance.calendarContainer) {
        return;
    }
    const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day');
    const currentYear = instance.currentYear != null ? instance.currentYear : new Date().getFullYear();
    const currentMonth = instance.currentMonth != null ? instance.currentMonth : new Date().getMonth();

    dayElements.forEach(day => {
        let dayDate = null;
        if (day.dateObj) {
            dayDate = new Date(day.dateObj);
        } else {
            // Fallback: algunos entornos o versiones de Flatpickr pueden no tener dateObj en el elemento
            const isPrevOrNext = day.classList.contains('prevMonthDay') || day.classList.contains('nextMonthDay');
            if (!isPrevOrNext) {
                const dayNum = parseInt(day.textContent && day.textContent.trim(), 10);
                if (!isNaN(dayNum)) {
                    dayDate = new Date(currentYear, currentMonth, dayNum);
                }
            }
        }
        if (dayDate) {
            const esSabado = dayDate.getDay() === 6;
            const yaTieneDistintivo = day.classList.contains('festivo') ||
                day.classList.contains('mantenimiento') ||
                day.classList.contains('temporada') ||
                day.classList.contains('domingo');
            if (esSabado && !yaTieneDistintivo) {
                day.classList.add('sabado');
                if (!day.title) {
                    day.title = 'Sábado (no disponible)';
                }
            } else if (!esSabado) {
                day.classList.remove('sabado');
            }
        }
    });
}

/**
 * Marca días de temporada en un calendario Flatpickr
 * 
 * @param {Object} instance - Instancia de Flatpickr
 * @param {Map} temporadaMap - Map con días de temporada (fecha -> descripción)
 */
function marcarTemporadaEnCalendario(instance, temporadaMap) {
    if (!instance || !instance.calendarContainer || !temporadaMap) {
        return;
    }
    
    const fechasTemporada = Array.from(temporadaMap.keys());
    // Marcar todos los días de temporada (incluidos deshabilitados cuando bloquearDiasEspeciales es true)
    const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day');
    
    dayElements.forEach(day => {
        if (day.dateObj) {
            const dayDate = new Date(day.dateObj);
            const dayDateStr = dayDate.toISOString().split('T')[0];
            
            if (fechasTemporada.includes(dayDateStr)) {
                // Es día de temporada: agregar clase y actualizar tooltip
                day.classList.add('temporada');
                const descripcion = temporadaMap.get(dayDateStr) || 'Día de temporada';
                
                // Si ya tiene un title (festivo o mantenimiento), agregar información de temporada
                const titleActual = day.title || '';
                if (titleActual && !titleActual.includes(descripcion)) {
                    day.title = titleActual + ' | ' + descripcion;
                } else if (!titleActual) {
                    day.title = descripcion;
                }
            } else {
                // No es día de temporada: remover clase si existe
                day.classList.remove('temporada');
                
                // Limpiar tooltip de temporada si existe, pero mantener otros si hay
                const titleActual = day.title || '';
                if (titleActual.includes(' | ')) {
                    const partes = titleActual.split(' | ');
                    const partesFiltradas = partes.filter(p => !p.toLowerCase().includes('temporada'));
                    day.title = partesFiltradas.join(' | ');
                } else if (titleActual.toLowerCase().includes('temporada')) {
                    day.title = '';
                }
            }
        }
    });
}

/**
 * Inicializa un datepicker Flatpickr con festivos marcados
 * 
 * @param {Object} config - Configuración del datepicker
 * @param {HTMLElement} config.input - Input element para el datepicker
 * @param {string} [config.minDate] - Fecha mínima permitida (YYYY-MM-DD)
 * @param {string} [config.maxDate] - Fecha máxima permitida (YYYY-MM-DD)
 * @param {Function} [config.onDateChange] - Callback cuando cambia la fecha (recibe fecha como string)
 * @param {HTMLElement} [config.indicadorFestivo] - Elemento para mostrar indicador de festivo
 * @param {HTMLElement} [config.descripcionFestivo] - Elemento para mostrar descripción del festivo
 * @param {Object} [config.flatpickrOptions] - Opciones adicionales para Flatpickr
 * @returns {Promise<Object>} Promise que resuelve con la instancia de Flatpickr
 */
function inicializarDatepickerFestivos(config) {
    const {
        input,
        minDate = null,
        maxDate = null,
        onDateChange = null,
        indicadorFestivo = null,
        descripcionFestivo = null,
        flatpickrOptions = {},
        bloquearDiasEspeciales = false,
        bloquearSabados = false,
        permitirFestivos = false,  // Si true, permite seleccionar festivos
        permitirTemporada = false  // Si true, permite seleccionar días de temporada (solo CT Permanente los bloquea)
    } = config;
    
    if (!input) {
        console.error('DatepickerFestivos: input element es requerido');
        return Promise.reject(new Error('input element es requerido'));
    }
    
    // Obtener fecha mínima del atributo data o del parámetro
    const fechaMinima = minDate || input.getAttribute('data-min-date') || new Date().toISOString().split('T')[0];
    
    // Obtener año para cargar temporadas
    const añoActual = new Date().getFullYear();
    
    // Cargar festivos, mantenimiento y temporadas en paralelo
    return Promise.all([
        cargarDiasFestivos(),
        cargarDiasMantenimiento(),
        cargarDiasTemporada(añoActual)
    ]).then(([festivosMap, mantenimientoMap, temporadaMap]) => {
        // Configuración base de Flatpickr.
        // Forzar firstDayOfWeek: 1 (lunes) para que la cuadrícula y las cabeceras Lun–Dom coincidan.
        // El locale 'es' de Flatpickr puede usar domingo como primer día, provocando desalineación.
        const localeEs = (typeof flatpickr !== 'undefined' && flatpickr.l10ns && flatpickr.l10ns.es)
            ? { ...flatpickr.l10ns.es, firstDayOfWeek: 1 }
            : 'es';
        const opcionesBase = {
            locale: localeEs,
            dateFormat: 'Y-m-d',
            minDate: fechaMinima,
            ...flatpickrOptions
        };
        
        if (maxDate) {
            opcionesBase.maxDate = maxDate;
        }

        // Forzar lunes como primer día de la semana para alinear cabeceras (Lun–Dom) con la cuadrícula.
        // Si flatpickrOptions ha sobrescrito locale, reaplicamos firstDayOfWeek: 1 para español.
        if (opcionesBase.locale === 'es' || (opcionesBase.locale && typeof opcionesBase.locale === 'object' && opcionesBase.locale.firstDayOfWeek !== 1)) {
            opcionesBase.locale = (typeof flatpickr !== 'undefined' && flatpickr.l10ns && flatpickr.l10ns.es)
                ? { ...flatpickr.l10ns.es, firstDayOfWeek: 1 }
                : opcionesBase.locale;
        }

        // Variables para mantener los Maps actualizados (para uso en callbacks)
        let festivosMapActual = festivosMap;
        let mantenimientoMapActual = mantenimientoMap;
        let temporadaMapActual = temporadaMap;
        
        // Función auxiliar para marcar todos los días especiales
        // Si bloquearDiasEspeciales es true, marca también días deshabilitados
        const marcarTodosLosDiasEspeciales = (instance) => {
            // Usar un timeout más largo para asegurar que el DOM esté completamente renderizado
            setTimeout(() => {
                if (instance && instance.calendarContainer) {
                    if (bloquearDiasEspeciales) {
                        // Marcar incluyendo días deshabilitados (festivo, mantenimiento, temporada, domingo)
                        marcarFestivosEnCalendarioIncluyendoDeshabilitados(instance, festivosMapActual);
                        marcarMantenimientoEnCalendarioIncluyendoDeshabilitados(instance, mantenimientoMapActual);
                        marcarTemporadaEnCalendario(instance, temporadaMapActual);
                        marcarDomingosEnCalendario(instance);
                        // Si bloquearSabados es true, también marcar sábados (para CT Sencillo)
                        if (bloquearSabados) {
                            marcarSabadosEnCalendario(instance);
                        }
                    } else {
                        // Marcar solo días habilitados (comportamiento normal)
                        marcarFestivosEnCalendario(instance, festivosMapActual);
                        marcarMantenimientoEnCalendario(instance, mantenimientoMapActual);
                        marcarTemporadaEnCalendario(instance, temporadaMapActual);
                    }
                    
                    // Si permitirFestivos es true, marcar festivos incluso si están habilitados
                    if (permitirFestivos && !bloquearDiasEspeciales) {
                        marcarFestivosEnCalendario(instance, festivosMapActual);
                    }
                }
            }, 100);
        };
        
        // Marcado SÍNCRONO de días especiales en onDayCreate (por cada día, en el momento de
        // crearse), usando las fechas ya cargadas. Esto evita la inconsistencia y el solapamiento
        // del marcado posterior por setTimeout/querySelectorAll (que a veces aparecía y a veces no).
        const _fechaLocalISO = (d) => {
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const day = String(d.getDate()).padStart(2, '0');
            return d.getFullYear() + '-' + m + '-' + day;
        };
        const _userOnDayCreateGlobal = opcionesBase.onDayCreate;
        opcionesBase.onDayCreate = function(dates, str, inst, dayElem) {
            if (dayElem && dayElem.dateObj) {
                const wd = dayElem.dateObj.getDay();
                const iso = _fechaLocalISO(dayElem.dateObj);
                // Limpiar marcas previas (la celda se reutiliza al cambiar de mes).
                dayElem.classList.remove('festivo', 'mantenimiento', 'temporada', 'domingo', 'sabado');
                if (wd === 0) {
                    dayElem.classList.add('domingo');
                    if (!dayElem.title) dayElem.title = 'Domingo (no disponible)';
                } else if (bloquearSabados && wd === 6) {
                    dayElem.classList.add('sabado');
                    if (!dayElem.title) dayElem.title = 'Sábado (no disponible)';
                }
                // Temporada manda sobre mantenimiento; festivo puede coexistir (CSS combina).
                if (temporadaMapActual && temporadaMapActual.has(iso)) {
                    dayElem.classList.add('temporada');
                } else if (mantenimientoMapActual && mantenimientoMapActual.has(iso)) {
                    dayElem.classList.add('mantenimiento');
                }
                if (festivosMapActual && festivosMapActual.has(iso)) {
                    dayElem.classList.add('festivo');
                    dayElem.title = festivosMapActual.get(iso) || 'Día festivo';
                }
            }
            if (_userOnDayCreateGlobal) _userOnDayCreateGlobal(dates, str, inst, dayElem);
        };

        // Si bloquearDiasEspeciales es true, configurar disable: domingos, festivos, mantenimiento y temporada
        // permitirFestivos: no bloquear festivos. permitirTemporada: no bloquear temporada (CT Permanente sí bloquea)
        if (bloquearDiasEspeciales) {
            const fechasFestivos = Array.from(festivosMap.keys());
            const fechasMantenimiento = Array.from(mantenimientoMap.keys());
            const fechasTemporada = Array.from(temporadaMap.keys());

            if (!opcionesBase.disable) {
                opcionesBase.disable = [];
            }
            if (!Array.isArray(opcionesBase.disable)) {
                opcionesBase.disable = [opcionesBase.disable];
            }

            opcionesBase.disable.push(
                function(date) { return date.getDay() === 0; }, // Domingo
                ...(permitirFestivos ? [] : [function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasFestivos.includes(fechaStr);
                }]),
                function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    // La temporada manda: un día de mantenimiento que cae en temporada NO se bloquea.
                    if (fechasTemporada.includes(fechaStr)) return false;
                    return fechasMantenimiento.includes(fechaStr);
                },
                // Temporada: solo bloquear si NO se permite seleccionarlos (CT Permanente no permite)
                ...(permitirTemporada ? [] : [function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasTemporada.includes(fechaStr);
                }])
            );
            
            // Si bloquearSabados es true, también deshabilitar sábados (para CT Sencillo)
            if (bloquearSabados) {
                opcionesBase.disable.push(
                    function(date) { return date.getDay() === 6; } // Sábado (0=domingo, 6=sábado)
                );
            }

            // (El marcado de domingos/sábados y días especiales ya se hace en el onDayCreate
            //  unificado de arriba, de forma síncrona y consistente.)
        }
        
        // Callbacks para marcar festivos y mantenimiento
        opcionesBase.onReady = function(selectedDates, dateStr, instance) {
            marcarTodosLosDiasEspeciales(instance);
            
            // Ejecutar callback personalizado si existe
            if (flatpickrOptions.onReady) {
                flatpickrOptions.onReady(selectedDates, dateStr, instance);
            }
        };
        
        // Callback onOpen: Se ejecuta cada vez que el calendario se abre
        // Esto asegura que los días especiales se re-marquen cada vez que se abre el calendario
        opcionesBase.onOpen = function(selectedDates, dateStr, instance) {
            // Re-marcar días especiales cada vez que se abre el calendario
            marcarTodosLosDiasEspeciales(instance);
            
            // Ejecutar callback personalizado si existe
            if (flatpickrOptions.onOpen) {
                flatpickrOptions.onOpen(selectedDates, dateStr, instance);
            }
        };
        
        opcionesBase.onChange = function(selectedDates, dateStr, instance) {
            // Verificar si es festivo
            if (indicadorFestivo && descripcionFestivo) {
                verificarDiaFestivo(dateStr, indicadorFestivo, descripcionFestivo);
            }
            
            // Ejecutar callback personalizado
            if (onDateChange) {
                onDateChange(dateStr);
            }
            
            // Ejecutar callback personalizado de Flatpickr si existe
            if (flatpickrOptions.onChange) {
                flatpickrOptions.onChange(selectedDates, dateStr, instance);
            }
        };
        
        opcionesBase.onMonthChange = function(selectedDates, dateStr, instance) {
            // Verificar si el año cambió al cambiar el mes (ej: diciembre 2025 -> enero 2026)
            const añoVisible = instance.currentYear;
            const añoActual = new Date().getFullYear();
            const añoCargado = temporadaMapActual && temporadaMapActual.size > 0 ? 
                parseInt(Array.from(temporadaMapActual.keys())[0].split('-')[0]) : añoActual;
            
            // Si el año visible es diferente al año cargado, cargar bajo demanda festivos, mantenimiento y temporadas
            if (añoVisible !== añoCargado) {
                Promise.all([
                    cargarDiasFestivos(añoVisible),
                    cargarDiasMantenimiento(añoVisible),
                    cargarDiasTemporada(añoVisible)
                ]).then(([nuevosFestivos, nuevoMantenimiento, nuevaTemporada]) => {
                    // Actualizar los Maps locales
                    festivosMap = nuevosFestivos;
                    mantenimientoMap = nuevoMantenimiento;
                    temporadaMap = nuevaTemporada;
                    festivosMapActual = nuevosFestivos;
                    mantenimientoMapActual = nuevoMantenimiento;
                    temporadaMapActual = nuevaTemporada;
                    marcarTodosLosDiasEspeciales(instance);
                });
            } else {
                marcarTodosLosDiasEspeciales(instance);
            }
            
            // Ejecutar callback personalizado si existe
            if (flatpickrOptions.onMonthChange) {
                flatpickrOptions.onMonthChange(selectedDates, dateStr, instance);
            }
        };
        
        opcionesBase.onYearChange = function(selectedDates, dateStr, instance) {
            const nuevoAño = instance.currentYear;
            const añoActual = new Date().getFullYear();
            
            // Cargar bajo demanda festivos, mantenimiento y temporadas para el nuevo año
            // La función cargarDiasFestivos/cargarDiasMantenimiento verifica el caché antes de hacer petición
            Promise.all([
                cargarDiasFestivos(nuevoAño),
                cargarDiasMantenimiento(nuevoAño),
                cargarDiasTemporada(nuevoAño)
            ]).then(([nuevosFestivos, nuevoMantenimiento, nuevaTemporada]) => {
                // Actualizar los Maps (tanto locales como actuales)
                festivosMap = nuevosFestivos;
                mantenimientoMap = nuevoMantenimiento;
                temporadaMap = nuevaTemporada;
                festivosMapActual = nuevosFestivos;
                mantenimientoMapActual = nuevoMantenimiento;
                temporadaMapActual = nuevaTemporada;
                
                // Re-marcar todos los días especiales
                marcarTodosLosDiasEspeciales(instance);
            });
            
            // Ejecutar callback personalizado si existe
            if (flatpickrOptions.onYearChange) {
                flatpickrOptions.onYearChange(selectedDates, dateStr, instance);
            }
        };
        
        // Inicializar Flatpickr
        const flatpickrInstance = flatpickr(input, opcionesBase);
        
        // Cargar temporadas para el año inicial del calendario si es diferente al año actual
        // Esto es importante si el calendario muestra un año diferente (ej: diciembre 2025 -> enero 2026)
        setTimeout(() => {
            if (flatpickrInstance && flatpickrInstance.calendarContainer) {
                const añoInicial = flatpickrInstance.currentYear || añoActual;
                if (añoInicial !== añoActual) {
                    cargarDiasTemporada(añoInicial).then(nuevaTemporada => {
                        temporadaMapActual = nuevaTemporada;
                        marcarTodosLosDiasEspeciales(flatpickrInstance);
                    });
                } else {
                    // Asegurar que se marquen las temporadas incluso si el calendario ya está renderizado
                    marcarTodosLosDiasEspeciales(flatpickrInstance);
                }
            }
        }, 200);
        
        // Si hay fecha inicial, establecerla
        if (input.value) {
            flatpickrInstance.setDate(input.value, false);
            if (indicadorFestivo && descripcionFestivo) {
                verificarDiaFestivo(input.value, indicadorFestivo, descripcionFestivo);
            }
            // Verificar también si es día de mantenimiento (si hay elementos para ello)
            // Esto se manejará en el callback onDateChange si está configurado
        }
        
        return flatpickrInstance;
    });
}

// Exportar funciones para uso en otros módulos
// Nota: Si usas módulos ES6, puedes usar: export { inicializarDatepickerFestivos, cargarDiasFestivos, verificarDiaFestivo };
// Para compatibilidad con scripts tradicionales, las funciones están en el scope global
// pero con prefijo para evitar conflictos
window.DatepickerFestivos = {
    inicializar: inicializarDatepickerFestivos,
    cargarDiasFestivos: cargarDiasFestivos,
    cargarDiasMantenimiento: cargarDiasMantenimiento,
    cargarDiasTemporada: cargarDiasTemporada,
    verificarDiaFestivo: verificarDiaFestivo,
    verificarDiaMantenimiento: verificarDiaMantenimiento,
    marcarFestivosEnCalendario: marcarFestivosEnCalendario,
    marcarMantenimientoEnCalendario: marcarMantenimientoEnCalendario,
    marcarTemporadaEnCalendario: marcarTemporadaEnCalendario
};

