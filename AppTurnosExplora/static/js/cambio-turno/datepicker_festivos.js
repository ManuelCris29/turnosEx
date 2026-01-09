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

// Cache global de días de mantenimiento (compartido entre todas las instancias)
let mantenimientoCacheGlobal = null;

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
    
    const añoActual = new Date().getFullYear();
    const añoInicio = añoActual - 1; // Incluir año anterior
    const añoFin = añoActual + 10;   // Incluir 10 años futuros
    
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
    
    // Cargar festivos adicionales de la BD
    return fetch('/turnos/api/dias-festivos/', {
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
        return festivosCacheGlobal;
    });
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
    
    const añoActual = new Date().getFullYear();
    const añoInicio = añoActual - 1; // Incluir año anterior
    const añoFin = añoActual + 10;   // Incluir 10 años futuros
    
    // Cargar días de mantenimiento de la BD para el rango de años
    const añosACargar = [];
    if (añoEspecifico !== null) {
        añosACargar.push(añoEspecifico);
    } else {
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
    
    return Promise.all(promesas).then(maps => {
        // Combinar todos los Maps en uno solo
        if (mantenimientoCacheGlobal === null) {
            mantenimientoCacheGlobal = new Map();
        }
        
        maps.forEach(map => {
            map.forEach((descripcion, fecha) => {
                mantenimientoCacheGlobal.set(fecha, descripcion);
            });
        });
        
        return mantenimientoCacheGlobal;
    });
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
    
    return fetch(`/turnos/api/dias-temporada/?anio=${anio}`)
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
            
            return temporadaMap;
        })
        .catch(error => {
            console.error('Error cargando días de temporada:', error);
            return new Map();
        });
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
    // Incluir TODOS los días, incluso los deshabilitados (temporada no bloquea, solo marca)
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
        bloquearDiasEspeciales = false
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
        // Configuración base de Flatpickr
        const opcionesBase = {
            locale: 'es',
            dateFormat: 'Y-m-d',
            minDate: fechaMinima,
            ...flatpickrOptions
        };
        
        if (maxDate) {
            opcionesBase.maxDate = maxDate;
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
                        // Marcar incluyendo días deshabilitados
                        marcarFestivosEnCalendarioIncluyendoDeshabilitados(instance, festivosMapActual);
                        marcarMantenimientoEnCalendarioIncluyendoDeshabilitados(instance, mantenimientoMapActual);
                        marcarTemporadaEnCalendario(instance, temporadaMapActual); // Temporada siempre incluye deshabilitados
                    } else {
                        // Marcar solo días habilitados (comportamiento normal)
                        marcarFestivosEnCalendario(instance, festivosMapActual);
                        marcarMantenimientoEnCalendario(instance, mantenimientoMapActual);
                        marcarTemporadaEnCalendario(instance, temporadaMapActual);
                    }
                }
            }, 100);
        };
        
        // Si bloquearDiasEspeciales es true, configurar disable para bloquear domingos, festivos y mantenimiento
        if (bloquearDiasEspeciales) {
            const fechasFestivos = Array.from(festivosMap.keys());
            const fechasMantenimiento = Array.from(mantenimientoMap.keys());
            
            // Agregar funciones de disable a las opciones base
            if (!opcionesBase.disable) {
                opcionesBase.disable = [];
            }
            
            // Asegurar que disable sea un array
            if (!Array.isArray(opcionesBase.disable)) {
                opcionesBase.disable = [opcionesBase.disable];
            }
            
            // Agregar funciones de bloqueo
            opcionesBase.disable.push(
                // Bloquear domingos
                function(date) {
                    return date.getDay() === 0; // Domingo
                },
                // Bloquear festivos
                function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasFestivos.includes(fechaStr);
                },
                // Bloquear días de mantenimiento
                function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasMantenimiento.includes(fechaStr);
                }
            );
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
            const añoCargado = temporadaMapActual && temporadaMapActual.size > 0 ? 
                parseInt(Array.from(temporadaMapActual.keys())[0].split('-')[0]) : añoActual;
            
            // Si el año visible es diferente al año cargado, recargar temporadas
            if (añoVisible !== añoCargado) {
                cargarDiasTemporada(añoVisible).then(nuevaTemporada => {
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
            
            // Si el año está fuera del rango cargado, cargar festivos, mantenimiento y temporadas para ese año
            if (nuevoAño < añoActual - 1 || nuevoAño > añoActual + 10) {
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
            } else {
                // Cargar temporadas para el nuevo año si cambió
                if (nuevoAño !== añoActual) {
                    cargarDiasTemporada(nuevoAño).then(nuevaTemporada => {
                        temporadaMapActual = nuevaTemporada;
                        marcarTodosLosDiasEspeciales(instance);
                    });
                } else {
                    // Re-marcar días especiales del año actual
                    marcarTodosLosDiasEspeciales(instance);
                }
            }
            
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

