/**
 * JavaScript para formulario de solicitud de doblada
 * 
 * Maneja:
 * - Inicialización de datepickers con bloqueo de domingos, festivos y mantenimiento
 * - Verificación de doblada existente
 * - Carga dinámica de exploradores disponibles
 * - Validación de fecha de pago
 * - Vista previa del acuerdo
 * - Manejo del caso crítico de coincidencia de jornadas
 */

(function() {
    'use strict';
    
    // Elementos del formulario
    const form = document.getElementById('dobladaForm');
    const fechaCesionInput = document.getElementById('fecha_cesion');
    const fechaPagoInput = document.getElementById('fecha_pago');
    const empleadoReceptorSelect = document.getElementById('empleado_receptor');
    const jornadaCedidaRadios = document.querySelectorAll('input[name="jornada_cedida"]');
    const tipoCesionHidden = document.getElementById('tipo_cesion');
    const tipoCesionOpcionRadios = document.querySelectorAll('input[name="tipo_cesion_opcion"]');
    const dobladaExistenteInfo = document.getElementById('doblada_existente_info');
    const vistaPreviaAcuerdo = document.getElementById('vista_previa_acuerdo');
    const resumenAcuerdo = document.getElementById('resumen_acuerdo');
    
    // Elementos para cesión total
    const opcionesCesionParcial = document.getElementById('opciones_cesion_parcial');
    const opcionesCesionTotal = document.getElementById('opciones_cesion_total');
    const receptorParcial = document.getElementById('receptor_parcial');
    const receptoresTotal = document.getElementById('receptores_total');
    const empleadoReceptorAM = document.getElementById('empleado_receptor_am');
    const empleadoReceptorPM = document.getElementById('empleado_receptor_pm');
    const fechaPagoParcial = document.getElementById('fecha_pago_parcial');
    const fechasPagoTotal = document.getElementById('fechas_pago_total');
    const fechaPagoAM = document.getElementById('fecha_pago_am');
    const fechaPagoPM = document.getElementById('fecha_pago_pm');
    
    // Indicadores
    const indicadorFestivoCesion = document.getElementById('indicador_festivo_cesion');
    const indicadorMantenimientoCesion = document.getElementById('indicador_mantenimiento_cesion');
    const indicadorDomingoCesion = document.getElementById('indicador_domingo_cesion');
    const indicadorFestivoPago = document.getElementById('indicador_festivo_pago');
    const indicadorMantenimientoPago = document.getElementById('indicador_mantenimiento_pago');
    const indicadorDomingoPago = document.getElementById('indicador_domingo_pago');
    const opcionesPagoSabado = document.getElementById('opciones_pago_sabado');
    const mensajeNoNecesarioPagoSabado = document.getElementById('mensaje_no_necesario_pago_sabado');
    const jornadaPagoSabadoRadios = document.querySelectorAll('input[name="jornada_pago_sabado"]');
    
    // Variables globales
    let flatpickrCesion = null;
    let flatpickrPago = null;
    let tieneDobladaExistente = false;
    let jornadasDobladaExistente = [];
    let fechaCreacionSolicitud = new Date().toISOString().split('T')[0]; // Fecha de hoy
    let fechasDescanso = []; // Fechas donde el usuario está descansando
    
    // Elementos para mostrar jornadas (fecha de cesión)
    const turnoSolicitanteInfo = document.getElementById('turno_solicitante_info');
    const turnoSolicitanteDetalles = document.getElementById('turno_solicitante_detalles');
    const salasSolicitanteDetalles = document.getElementById('salas_solicitante_detalles');
    const turnoReceptorInfo = document.getElementById('turno_receptor_info');
    const turnoReceptorDetalles = document.getElementById('turno_receptor_detalles');
    const salasReceptorDetalles = document.getElementById('salas_receptor_detalles');
    
    // Elementos para mostrar jornadas (fecha de pago)
    const turnoSolicitantePagoInfo = document.getElementById('turno_solicitante_pago_info');
    const turnoSolicitantePagoDetalles = document.getElementById('turno_solicitante_pago_detalles');
    const salasSolicitantePagoDetalles = document.getElementById('salas_solicitante_pago_detalles');
    const turnoReceptorPagoInfo = document.getElementById('turno_receptor_pago_info');
    const turnoReceptorPagoDetalles = document.getElementById('turno_receptor_pago_detalles');
    const salasReceptorPagoDetalles = document.getElementById('salas_receptor_pago_detalles');
    
    /**
     * Función reutilizable para renderizar turno y salas de manera ordenada.
     * @param {Object|null} turno - Datos del turno o null
     * @param {HTMLElement} detallesElem - Contenedor de detalles de jornada
     * @param {HTMLElement} salasElem - Contenedor de salas
     * @param {boolean} esDoblada - Si tiene doblada (AM+PM)
     * @param {string[]} jornadas - Lista de jornadas
     * @param {{ contexto?: 'solicitante'|'receptor' }} opciones - Si contexto es 'receptor' y no hay turno, se muestra estado "Descanso"
     */
    function renderTurnoYSalas(turno, detallesElem, salasElem, esDoblada = false, jornadas = [], opciones = {}) {
        if (!turno) {
            if (opciones.contexto === 'receptor') {
                // Estado profesional: el receptor está en día de descanso
                detallesElem.innerHTML = `
                    <div class="card mb-3 border-secondary">
                        <div class="card-body text-center py-4">
                            <i class="fas fa-moon text-secondary fa-2x mb-2" aria-hidden="true"></i>
                            <p class="mb-1 font-weight-bold text-secondary">Descanso</p>
                            <p class="mb-0 small text-muted">El receptor no tiene jornada asignada para esta fecha. Corresponde su día de descanso según su turno.</p>
                        </div>
                    </div>
                `;
                salasElem.innerHTML = `
                    <div class="card mb-3 border-0 bg-light">
                        <div class="card-body py-2 text-center">
                            <span class="text-muted small">Sin asignación — día de descanso</span>
                        </div>
                    </div>
                `;
            } else {
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
                            <span class="text-muted">No tiene salas asignadas</span>
                        </div>
                    </div>
                `;
            }
            return;
        }
        
        // CORRECCIÓN: Detectar si es doblada
        const esJornadaFija = turno.es_turno_virtual;
        let badgeClass, badgeText, jornadaTexto;
        
        if (esDoblada) {
            // Es una DOBLADA (AM + PM)
            badgeClass = 'badge-warning';
            badgeText = 'DOBLADA';
            jornadaTexto = `${jornadas.join(' + ')}`;
        } else {
            // Jornada simple
            badgeClass = esJornadaFija ? 'badge-info' : 'badge-success';
            badgeText = esJornadaFija ? 'Jornada Fija' : 'Turno Asignado';
            jornadaTexto = turno.jornada || '-';
        }
        
        detallesElem.innerHTML = `
            <div class="card mb-3">
                <div class="card-body">
                    <div class="row align-items-center mb-2">
                        <div class="col-12 col-md-6 mb-2 mb-md-0">
                            <strong>Jornada:</strong> ${jornadaTexto}
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
                        <span class="text-muted">No tiene salas asignadas</span>
                    </div>
                </div>
            `;
        }
    }
    
    /**
     * Verificar si una fecha es domingo
     */
    function esDomingo(fecha) {
        const fechaObj = new Date(fecha + 'T00:00:00');
        return fechaObj.getDay() === 0; // 0 = Domingo
    }

    /**
     * Verificar si una fecha es sábado
     */
    function esSabado(fecha) {
        const fechaObj = new Date(fecha + 'T00:00:00');
        return fechaObj.getDay() === 6; // 6 = Sábado
    }

    function limpiarSeleccionPagoSabado() {
        if (jornadaPagoSabadoRadios && jornadaPagoSabadoRadios.length > 0) {
            jornadaPagoSabadoRadios.forEach(r => { r.checked = false; });
        }
    }

    function mostrarOpcionesPagoSabado(mostrar) {
        if (!opcionesPagoSabado) return;
        opcionesPagoSabado.style.display = mostrar ? 'block' : 'none';
        if (!mostrar) limpiarSeleccionPagoSabado();
    }

    function mostrarMensajeNoNecesarioPagoSabado(mostrar) {
        if (!mensajeNoNecesarioPagoSabado) return;
        mensajeNoNecesarioPagoSabado.style.display = mostrar ? 'block' : 'none';
    }
    
    /**
     * Marca días festivos en calendario (incluyendo deshabilitados)
     */
    function marcarFestivosIncluyendoDeshabilitados(instance, festivosMap) {
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
                    // No es festivo: remover clase si existe
                    day.classList.remove('festivo');
                }
            }
        });
    }
    
    /**
     * Marca días de mantenimiento en calendario (incluyendo deshabilitados)
     */
    function marcarMantenimientoIncluyendoDeshabilitados(instance, mantenimientoMap) {
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
                    // No es día de mantenimiento: remover clase si existe
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
     * Marca días de temporada en calendario (incluyendo deshabilitados)
     */
    function marcarTemporadaIncluyendoDeshabilitados(instance, temporadaMap) {
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
     * Bloquear domingos, festivos, mantenimiento y temporada en Flatpickr.
     * Marca visualmente los días especiales (colores distintivos se mantienen).
     */
    function bloquearDiasEspeciales(instance) {
        if (!instance) return;
        
        // Almacenar Maps en la instancia para acceso desde callbacks
        if (!instance._diasEspecialesMaps) {
            instance._diasEspecialesMaps = {
                festivos: null,
                mantenimiento: null,
                temporada: null
            };
        }
        
        // Obtener año para cargar temporadas
        const añoActual = new Date().getFullYear();
        
        // Cargar festivos, mantenimiento y temporadas
        Promise.all([
            window.DatepickerFestivos.cargarDiasFestivos(),
            window.DatepickerFestivos.cargarDiasMantenimiento(),
            window.DatepickerFestivos.cargarDiasTemporada(añoActual)
        ]).then(([festivosMap, mantenimientoMap, temporadaMap]) => {
            // Guardar Maps en la instancia para acceso desde callbacks
            instance._diasEspecialesMaps.festivos = festivosMap;
            instance._diasEspecialesMaps.mantenimiento = mantenimientoMap;
            instance._diasEspecialesMaps.temporada = temporadaMap;
            
            const fechasFestivos = Array.from(festivosMap.keys());
            const fechasMantenimiento = Array.from(mantenimientoMap.keys());
            const fechasTemporada = Array.from(temporadaMap.keys());

            instance.set('disable', [
                function(date) { return date.getDay() === 0; },
                function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasFestivos.includes(fechaStr);
                },
                function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasMantenimiento.includes(fechaStr);
                },
                function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasTemporada.includes(fechaStr);
                }
            ]);
            
            // Función auxiliar para marcar todos los días especiales (incluyendo deshabilitados)
            const marcarTodosLosDiasEspeciales = () => {
                // Usar Maps de la instancia para asegurar que estén disponibles
                const festivos = instance._diasEspecialesMaps.festivos;
                const mantenimiento = instance._diasEspecialesMaps.mantenimiento;
                const temporada = instance._diasEspecialesMaps.temporada;
                
                if (!festivos || !mantenimiento) {
                    return; // Maps aún no están cargados
                }
                
                setTimeout(() => {
                    if (instance && instance.calendarContainer) {
                        // Marcar festivos (incluyendo deshabilitados)
                        marcarFestivosIncluyendoDeshabilitados(instance, festivos);
                        // Marcar días de mantenimiento (incluyendo deshabilitados)
                        marcarMantenimientoIncluyendoDeshabilitados(instance, mantenimiento);
                        // Marcar días de temporada (incluyendo deshabilitados) - solo si está disponible
                        if (temporada) {
                            marcarTemporadaIncluyendoDeshabilitados(instance, temporada);
                        }
                    }
                }, 150);
            };
            
            // Marcar visualmente los días especiales en el calendario
            marcarTodosLosDiasEspeciales();
            
            // También marcar inmediatamente si el calendario ya está abierto/renderizado
            setTimeout(() => {
                if (instance && instance.calendarContainer) {
                    marcarTodosLosDiasEspeciales();
                }
            }, 300);
            
            // Configurar callbacks para re-marcar cuando cambie el mes o el año
            // Guardar callbacks existentes si existen
            const onMonthChangeOriginal = instance.config.onMonthChange;
            const onYearChangeOriginal = instance.config.onYearChange;
            const onOpenOriginal = instance.config.onOpen;
            const onReadyOriginal = instance.config.onReady;
            
            // Configurar onReady para marcar días cuando el calendario esté listo
            instance.config.onReady = function(selectedDates, dateStr, inst) {
                marcarTodosLosDiasEspeciales();
                // Ejecutar callback original si existe
                if (onReadyOriginal) {
                    onReadyOriginal(selectedDates, dateStr, inst);
                }
            };
            
            // Configurar onMonthChange para re-marcar días
            instance.config.onMonthChange = function(selectedDates, dateStr, inst) {
                // Verificar si el año cambió al cambiar el mes
                const añoVisible = inst.currentYear;
                const añoCargado = instance._diasEspecialesMaps.temporada && instance._diasEspecialesMaps.temporada.size > 0 ?
                    parseInt(Array.from(instance._diasEspecialesMaps.temporada.keys())[0].split('-')[0]) : añoActual;
                
                // Si el año visible es diferente, recargar temporadas
                if (añoVisible !== añoCargado && window.DatepickerFestivos && window.DatepickerFestivos.cargarDiasTemporada) {
                    window.DatepickerFestivos.cargarDiasTemporada(añoVisible).then(nuevaTemporada => {
                        instance._diasEspecialesMaps.temporada = nuevaTemporada;
                        marcarTodosLosDiasEspeciales();
                    });
                } else {
                    marcarTodosLosDiasEspeciales();
                }
                // Ejecutar callback original si existe
                if (onMonthChangeOriginal) {
                    onMonthChangeOriginal(selectedDates, dateStr, inst);
                }
            };
            
            // Configurar onYearChange para re-marcar días
            instance.config.onYearChange = function(selectedDates, dateStr, inst) {
                const nuevoAño = inst.currentYear;
                // Cargar temporadas para el nuevo año
                if (window.DatepickerFestivos && window.DatepickerFestivos.cargarDiasTemporada) {
                    window.DatepickerFestivos.cargarDiasTemporada(nuevoAño).then(nuevaTemporada => {
                        instance._diasEspecialesMaps.temporada = nuevaTemporada;
                        marcarTodosLosDiasEspeciales();
                    });
                } else {
                    marcarTodosLosDiasEspeciales();
                }
                // Ejecutar callback original si existe
                if (onYearChangeOriginal) {
                    onYearChangeOriginal(selectedDates, dateStr, inst);
                }
            };
            
            // También re-marcar cuando se abre el calendario
            instance.config.onOpen = function(selectedDates, dateStr, inst) {
                // Verificar año visible y cargar temporadas si es necesario
                const añoVisible = inst.currentYear || añoActual;
                const añoCargado = instance._diasEspecialesMaps.temporada && instance._diasEspecialesMaps.temporada.size > 0 ?
                    parseInt(Array.from(instance._diasEspecialesMaps.temporada.keys())[0].split('-')[0]) : añoActual;
                
                if (añoVisible !== añoCargado && window.DatepickerFestivos && window.DatepickerFestivos.cargarDiasTemporada) {
                    window.DatepickerFestivos.cargarDiasTemporada(añoVisible).then(nuevaTemporada => {
                        instance._diasEspecialesMaps.temporada = nuevaTemporada;
                        marcarTodosLosDiasEspeciales();
                    });
                } else {
                    marcarTodosLosDiasEspeciales();
                }
                // Ejecutar callback original si existe
                if (onOpenOriginal) {
                    onOpenOriginal(selectedDates, dateStr, inst);
                }
            };
        }).catch(error => {
            console.error('Error cargando días especiales para bloqueo:', error);
            // Si falla, al menos bloquear domingos
            instance.set('disable', [
                function(date) {
                    return date.getDay() === 0; // Domingo
                }
            ]);
        });
    }
    
    /**
     * Cargar fechas donde el usuario está descansando (cedió su jornada)
     */
    async function cargarFechasDescanso() {
        try {
            const response = await fetch('/solicitudes/obtener-fechas-descanso/');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            if (data.success && Array.isArray(data.fechas)) {
                fechasDescanso = data.fechas;
                console.log(`✅ Fechas de descanso cargadas: ${fechasDescanso.length}`);
                
                // Aplicar marcado visual en el calendario
                if (flatpickrCesion) {
                    marcarFechasDescansoEnCalendario();
                }
            }
        } catch (error) {
            console.error('Error cargando fechas de descanso:', error);
            fechasDescanso = [];
        }
    }
    
    /**
     * Marcar visualmente las fechas de descanso en el calendario
     */
    function marcarFechasDescansoEnCalendario() {
        if (!flatpickrCesion) return;
        
        setTimeout(() => {
            fechasDescanso.forEach(fecha => {
                const fechaObj = new Date(fecha + 'T00:00:00');
                const dias = flatpickrCesion.calendarContainer.querySelectorAll('.flatpickr-day');
                dias.forEach(dia => {
                    const diaFecha = new Date(dia.dateObj);
                    if (diaFecha.toDateString() === fechaObj.toDateString()) {
                        dia.classList.add('descanso');
                    }
                });
            });
        }, 100);
    }
    
    /**
     * Inicializar datepicker para fecha de cesión
     */
    function inicializarDatepickerCesion() {
        if (!fechaCesionInput || !window.DatepickerFestivos) {
            console.error('DatepickerFestivos no está disponible');
            return;
        }
        
        const fechaMinima = fechaCesionInput.getAttribute('data-min-date') || new Date().toISOString().split('T')[0];
        
        // Cargar fechas de descanso antes de inicializar
        cargarFechasDescanso();
        
        window.DatepickerFestivos.inicializar({
            input: fechaCesionInput,
            minDate: fechaMinima,
            indicadorFestivo: indicadorFestivoCesion,
            descripcionFestivo: document.getElementById('descripcion_festivo_cesion'),
            bloquearDiasEspeciales: true,
            permitirFestivos: true,
            permitirTemporada: true, // En temporada sí se pueden hacer solicitudes de doblada
            onReady: function(flatpickrInstance) {
                flatpickrCesion = flatpickrInstance;
                marcarFechasDescansoEnCalendario();
            },
            onDateChange: function(fecha) {
                if (!fecha) return;
                
                // Verificar si es domingo
                if (esDomingo(fecha)) {
                    indicadorDomingoCesion.style.display = 'block';
                    fechaCesionInput.value = '';
                    return;
                } else {
                    indicadorDomingoCesion.style.display = 'none';
                }
                
                // Verificar si es día de mantenimiento
                if (window.DatepickerFestivos && window.DatepickerFestivos.verificarDiaMantenimiento) {
                    window.DatepickerFestivos.verificarDiaMantenimiento(
                        fecha,
                        indicadorMantenimientoCesion,
                        document.getElementById('descripcion_mantenimiento_cesion')
                    ).then(esMantenimiento => {
                        if (esMantenimiento) {
                            fechaCesionInput.value = '';
                        }
                    });
                }
                
                // Verificar doblada existente (esto cargará exploradores y jornada según el caso)
                verificarDobladaExistente(fecha);
            }
        }).then(instance => {
            flatpickrCesion = instance;
            // bloquearDiasEspeciales ya se maneja dentro de inicializar() con bloquearDiasEspeciales: true
            
            // Si ya hay una fecha seleccionada al cargar, verificar doblada (cargará jornada si aplica)
            const fechaInicial = fechaCesionInput.value;
            if (fechaInicial) {
                verificarDobladaExistente(fechaInicial);
            }
        }).catch(error => {
            console.error('Error inicializando datepicker de cesión:', error);
        });
    }
    
    /**
     * Inicializar datepicker para fecha de pago
     */
    function inicializarDatepickerPago() {
        if (!fechaPagoInput || !window.DatepickerFestivos) {
            console.error('DatepickerFestivos no está disponible');
            return;
        }
        
        const fechaMinima = fechaPagoInput.getAttribute('data-min-date') || new Date().toISOString().split('T')[0];
        
        window.DatepickerFestivos.inicializar({
            input: fechaPagoInput,
            minDate: fechaMinima,
            indicadorFestivo: indicadorFestivoPago,
            descripcionFestivo: document.getElementById('descripcion_festivo_pago'),
            bloquearDiasEspeciales: true,
            permitirFestivos: true,
            permitirTemporada: true,
            onDateChange: function(fecha) {
                if (!fecha) return;
                
                // Verificar si es domingo
                if (esDomingo(fecha)) {
                    indicadorDomingoPago.style.display = 'block';
                    fechaPagoInput.value = '';
                    mostrarOpcionesPagoSabado(false);
                    return;
                } else {
                    indicadorDomingoPago.style.display = 'none';
                }

                // Si es sábado, cargarJornadaSolicitantePago decidirá si mostrar selector o mensaje "no necesario"
                if (!esSabado(fecha)) {
                    mostrarOpcionesPagoSabado(false);
                    mostrarMensajeNoNecesarioPagoSabado(false);
                }
                
                // Verificar si es día de mantenimiento
                if (window.DatepickerFestivos && window.DatepickerFestivos.verificarDiaMantenimiento) {
                    window.DatepickerFestivos.verificarDiaMantenimiento(
                        fecha,
                        indicadorMantenimientoPago,
                        document.getElementById('descripcion_mantenimiento_pago')
                    ).then(esMantenimiento => {
                        if (esMantenimiento) {
                            fechaPagoInput.value = '';
                        }
                    });
                }
                
                // Validar que sea posterior a fecha de creación
                if (fecha <= fechaCreacionSolicitud) {
                    Swal.fire({
                        icon: 'error',
                        title: 'Fecha Inválida',
                        text: `La fecha de pago debe ser posterior a ${fechaCreacionSolicitud}.`
                    });
                    fechaPagoInput.value = '';
                    return;
                }
                
                // Verificar si tiene doblada en esta fecha (validación preventiva)
                verificarDobladaEnFechaPago(fecha, 'Pago');
                
                // Cargar jornada del solicitante en fecha de pago
                cargarJornadaSolicitantePago(fecha);
                
                // Si ya hay receptor seleccionado, cargar su jornada en fecha de pago
                const empleadoReceptorId = empleadoReceptorSelect.value;
                if (empleadoReceptorId) {
                    cargarJornadaReceptorPago(empleadoReceptorId, fecha);
                }
                
                // ✅ NUEVA VALIDACIÓN: Si es sábado y hay receptor, validar que el sábado corresponda a la jornada del receptor
                if (esSabado(fecha) && empleadoReceptorId && fechaCesionInput?.value) {
                    validarSabadoCorrespondeReceptor(fecha, empleadoReceptorId, fechaCesionInput.value);
                }
                
                // NOTA IMPORTANTE:
                // Ya NO recargamos la lista de \"Compañero que te cubrirá\" con la fecha de pago.
                // La lista de compañeros para cesión parcial SIEMPRE se calcula con la fecha de cesión
                // (día de semana). La fecha de pago (sábado) solo se usa para validaciones de alternancia.
                
                // Actualizar vista previa
                actualizarVistaPrevia();
            }
        }).then(instance => {
            flatpickrPago = instance;
            // bloquearDiasEspeciales ya se maneja dentro de inicializar() con bloquearDiasEspeciales: true
        }).catch(error => {
            console.error('Error inicializando datepicker de pago:', error);
        });
    }
    
    /**
     * Inicializar datepicker para fecha de pago AM (cesión total)
     */
    function inicializarDatepickerPagoAM() {
        if (!fechaPagoAM || !window.DatepickerFestivos) {
            return;
        }
        
        const fechaMinima = fechaPagoAM.getAttribute('data-min-date') || new Date().toISOString().split('T')[0];
        
        window.DatepickerFestivos.inicializar({
            input: fechaPagoAM,
            minDate: fechaMinima,
            bloquearDiasEspeciales: true,
            permitirFestivos: true,
            permitirTemporada: true,
            onDateChange: function(fecha) {
                if (!fecha) return;
                if (esDomingo(fecha)) {
                    fechaPagoAM.value = '';
                    return;
                }
                actualizarVistaPrevia();
            }
        }).then(instance => {
            // bloquearDiasEspeciales ya se maneja dentro de inicializar() con bloquearDiasEspeciales: true
            fechaPagoAM.setAttribute('data-initialized', 'true');
        }).catch(error => {
            console.error('Error inicializando datepicker de pago AM:', error);
        });
    }
    
    /**
     * Inicializar datepicker para fecha de pago PM (cesión total)
     */
    function inicializarDatepickerPagoPM() {
        if (!fechaPagoPM || !window.DatepickerFestivos) {
            return;
        }
        
        const fechaMinima = fechaPagoPM.getAttribute('data-min-date') || new Date().toISOString().split('T')[0];
        
        window.DatepickerFestivos.inicializar({
            input: fechaPagoPM,
            minDate: fechaMinima,
            bloquearDiasEspeciales: true,
            permitirFestivos: true,
            permitirTemporada: true,
            onDateChange: function(fecha) {
                if (!fecha) return;
                if (esDomingo(fecha)) {
                    fechaPagoPM.value = '';
                    return;
                }
                actualizarVistaPrevia();
            }
        }).then(instance => {
            // bloquearDiasEspeciales ya se maneja dentro de inicializar() con bloquearDiasEspeciales: true
            fechaPagoPM.setAttribute('data-initialized', 'true');
        }).catch(error => {
            console.error('Error inicializando datepicker de pago PM:', error);
        });
    }
    
    /**
     * Cargar jornada del solicitante para la fecha de cesión
     */
    function cargarJornadaSolicitante(fecha) {
        if (!fecha || !window.solicitanteId) {
            if (turnoSolicitanteInfo) {
                turnoSolicitanteInfo.style.display = 'none';
            }
            return;
        }
        
        if (turnoSolicitanteDetalles) {
            turnoSolicitanteDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (salasSolicitanteDetalles) {
            salasSolicitanteDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (turnoSolicitanteInfo) {
            turnoSolicitanteInfo.style.display = 'block';
        }
        
        const tipoSolicitudInput = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudId = tipoSolicitudInput ? tipoSolicitudInput.value : '';
        const urlSolicitanteCesion = `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fecha}${tipoSolicitudId ? `&tipo_solicitud_id=${tipoSolicitudId}` : ''}`;
        
        fetch(urlSolicitanteCesion, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            console.log('[DEBUG] Respuesta obtener-turno-explorador:', data);
            if (data.success && data.turno) {
                // ✅ CORRECCIÓN: Solo es doblada si hay TURNOS REALES asignados (AM+PM)
                // No considerar jornada predeterminada como doblada
                const esDobladaReal = data.es_doblada === true && data.jornadas && data.jornadas.length >= 2;
                console.log('[DEBUG] es_doblada:', data.es_doblada, 'jornadas:', data.jornadas, 'esDobladaReal:', esDobladaReal);
                
                // CORRECCIÓN: Pasar información de doblada
                renderTurnoYSalas(
                    data.turno, 
                    turnoSolicitanteDetalles, 
                    salasSolicitanteDetalles,
                    esDobladaReal,
                    data.jornadas || []
                );
            } else {
                renderTurnoYSalas(null, turnoSolicitanteDetalles, salasSolicitanteDetalles, false, []);
            }
        })
        .catch(error => {
            console.error('Error al cargar información del solicitante:', error);
            if (turnoSolicitanteDetalles) {
                turnoSolicitanteDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            if (salasSolicitanteDetalles) {
                salasSolicitanteDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
        });
    }
    
    /**
     * Cargar jornada del receptor cuando se selecciona
     */
    function cargarJornadaReceptor(empleadoId, fecha) {
        if (!fecha || !empleadoId) {
            if (turnoReceptorInfo) {
                turnoReceptorInfo.style.display = 'none';
            }
            return;
        }
        
        if (turnoReceptorDetalles) {
            turnoReceptorDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (salasReceptorDetalles) {
            salasReceptorDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (turnoReceptorInfo) {
            turnoReceptorInfo.style.display = 'block';
        }
        
        const tipoSolicitudInput = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudId = tipoSolicitudInput ? tipoSolicitudInput.value : '';
        const urlReceptorCesion = `/solicitudes/obtener-turno-explorador/?explorador_id=${empleadoId}&fecha=${fecha}${tipoSolicitudId ? `&tipo_solicitud_id=${tipoSolicitudId}` : ''}`;
        
        fetch(urlReceptorCesion, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success && data.turno) {
                // CORRECCIÓN: Pasar información de doblada
                renderTurnoYSalas(
                    data.turno, 
                    turnoReceptorDetalles, 
                    salasReceptorDetalles,
                    data.es_doblada || false,
                    data.jornadas || []
                );
            } else {
                renderTurnoYSalas(null, turnoReceptorDetalles, salasReceptorDetalles, false, [], { contexto: 'receptor' });
            }
        })
        .catch(error => {
            console.error('Error al cargar información del receptor:', error);
            if (turnoReceptorDetalles) {
                turnoReceptorDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            if (salasReceptorDetalles) {
                salasReceptorDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
        });
    }
    
    /**
     * Cargar jornada del solicitante (deudor) para la fecha de pago
     */
    function cargarJornadaSolicitantePago(fecha) {
        if (!fecha || !window.solicitanteId) {
            if (turnoSolicitantePagoInfo) {
                turnoSolicitantePagoInfo.style.display = 'none';
            }
            return;
        }
        
        if (turnoSolicitantePagoDetalles) {
            turnoSolicitantePagoDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (salasSolicitantePagoDetalles) {
            salasSolicitantePagoDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (turnoSolicitantePagoInfo) {
            turnoSolicitantePagoInfo.style.display = 'block';
        }
        
        const tipoSolicitudInputPago = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudIdPago = tipoSolicitudInputPago ? tipoSolicitudInputPago.value : '';
        const urlSolicitantePago = `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fecha}${tipoSolicitudIdPago ? `&tipo_solicitud_id=${tipoSolicitudIdPago}` : ''}`;
        
        fetch(urlSolicitantePago, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success && data.turno) {
                // Incluir doblada de sábado (backend devuelve jornada 'DOBLADA' cuando corresponde por alternancia)
                const esDoblada = data.es_doblada || (data.turno.jornada === 'DOBLADA');
                const jornadas = (data.jornadas && data.jornadas.length) ? data.jornadas : (data.turno.jornada === 'DOBLADA' ? ['AM', 'PM'] : []);
                renderTurnoYSalas(
                    data.turno, 
                    turnoSolicitantePagoDetalles, 
                    salasSolicitantePagoDetalles,
                    esDoblada,
                    jornadas
                );
            } else {
                // Cuando no hay turno en fecha de pago (por ejemplo, festivo donde descansas),
                // mostrar la tarjeta en modo "Descanso" en lugar de los avisos amarillos.
                renderTurnoYSalas(
                    null,
                    turnoSolicitantePagoDetalles,
                    salasSolicitantePagoDetalles,
                    false,
                    [],
                    { contexto: 'receptor' }
                );
            }
            // Regla doblada: si la fecha de pago es sábado, mostrar selector solo si NO te corresponde trabajar ese sábado por alternancia
            if (data.jornada_trabaja_sabado !== undefined) {
                const correspondeTrabajarSabado = data.turno && (
                    data.turno.jornada === data.jornada_trabaja_sabado ||
                    data.turno.jornada === 'DOBLADA'
                );
                if (correspondeTrabajarSabado) {
                    mostrarOpcionesPagoSabado(false);
                    mostrarMensajeNoNecesarioPagoSabado(true);
                    // Marcar la jornada que corresponde (para que el backend reciba jornada_pago_sabado al enviar)
                    const radioAuto = document.querySelector(`input[name="jornada_pago_sabado"][value="${data.jornada_trabaja_sabado}"]`);
                    if (radioAuto) radioAuto.checked = true;
                } else {
                    mostrarOpcionesPagoSabado(true);
                    mostrarMensajeNoNecesarioPagoSabado(false);
                    limpiarSeleccionPagoSabado();
                }
            } else {
                mostrarOpcionesPagoSabado(false);
                mostrarMensajeNoNecesarioPagoSabado(false);
            }
        })
        .catch(error => {
            console.error('Error al cargar información del solicitante en fecha de pago:', error);
            if (turnoSolicitantePagoDetalles) {
                turnoSolicitantePagoDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            if (salasSolicitantePagoDetalles) {
                salasSolicitantePagoDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
        });
    }
    
    /**
     * Cargar jornada del receptor (acreedor) para la fecha de pago
     */
    function cargarJornadaReceptorPago(empleadoId, fecha) {
        if (!fecha || !empleadoId) {
            if (turnoReceptorPagoInfo) {
                turnoReceptorPagoInfo.style.display = 'none';
            }
            return;
        }
        
        if (turnoReceptorPagoDetalles) {
            turnoReceptorPagoDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (salasReceptorPagoDetalles) {
            salasReceptorPagoDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (turnoReceptorPagoInfo) {
            turnoReceptorPagoInfo.style.display = 'block';
        }
        
        const tipoSolicitudInputReceptorPago = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudIdReceptorPago = tipoSolicitudInputReceptorPago ? tipoSolicitudInputReceptorPago.value : '';
        const urlReceptorPago = `/solicitudes/obtener-turno-explorador/?explorador_id=${empleadoId}&fecha=${fecha}${tipoSolicitudIdReceptorPago ? `&tipo_solicitud_id=${tipoSolicitudIdReceptorPago}` : ''}`;
        
        fetch(urlReceptorPago, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success && data.turno) {
                // CORRECCIÓN: Pasar información de doblada
                renderTurnoYSalas(
                    data.turno, 
                    turnoReceptorPagoDetalles, 
                    salasReceptorPagoDetalles,
                    data.es_doblada || false,
                    data.jornadas || []
                );
            } else {
                renderTurnoYSalas(null, turnoReceptorPagoDetalles, salasReceptorPagoDetalles, false, [], { contexto: 'receptor' });
            }
        })
        .catch(error => {
            console.error('Error al cargar información del receptor en fecha de pago:', error);
            if (turnoReceptorPagoDetalles) {
                turnoReceptorPagoDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            if (salasReceptorPagoDetalles) {
                salasReceptorPagoDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
        });
    }
    
    /**
     * Cargar jornada del solicitante para fecha de pago AM (Cesión Total)
     */
    function cargarJornadaSolicitantePagoAM(fecha) {
        if (!fecha || !window.solicitanteId) {
            const infoDiv = document.getElementById('turno_solicitante_pago_am_info');
            if (infoDiv) infoDiv.style.display = 'none';
            return;
        }
        
        const detallesDiv = document.getElementById('turno_solicitante_pago_am_detalles');
        const salasDiv = document.getElementById('salas_solicitante_pago_am_detalles');
        const infoDiv = document.getElementById('turno_solicitante_pago_am_info');
        
        if (detallesDiv) detallesDiv.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>';
        if (salasDiv) salasDiv.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>';
        if (infoDiv) infoDiv.style.display = 'block';
        
        const tipoSolicitudInputPagoAM = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudIdPagoAM = tipoSolicitudInputPagoAM ? tipoSolicitudInputPagoAM.value : '';
        const urlSolicitantePagoAM = `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fecha}${tipoSolicitudIdPagoAM ? `&tipo_solicitud_id=${tipoSolicitudIdPagoAM}` : ''}`;
        
        fetch(urlSolicitantePagoAM)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.turno) {
                    renderTurnoYSalas(data.turno, detallesDiv, salasDiv, data.es_doblada || false, data.jornadas || []);
                } else {
                    renderTurnoYSalas(null, detallesDiv, salasDiv, false, []);
                }
            })
            .catch(error => {
                console.error('Error al cargar jornada solicitante AM:', error);
                if (detallesDiv) detallesDiv.innerHTML = '<div class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> Error</div>';
                if (salasDiv) salasDiv.innerHTML = '<div class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> Error</div>';
            });
    }
    
    /**
     * Cargar jornada del solicitante para fecha de pago PM (Cesión Total)
     */
    function cargarJornadaSolicitantePagoPM(fecha) {
        if (!fecha || !window.solicitanteId) {
            const infoDiv = document.getElementById('turno_solicitante_pago_pm_info');
            if (infoDiv) infoDiv.style.display = 'none';
            return;
        }
        
        const detallesDiv = document.getElementById('turno_solicitante_pago_pm_detalles');
        const salasDiv = document.getElementById('salas_solicitante_pago_pm_detalles');
        const infoDiv = document.getElementById('turno_solicitante_pago_pm_info');
        
        if (detallesDiv) detallesDiv.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>';
        if (salasDiv) salasDiv.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>';
        if (infoDiv) infoDiv.style.display = 'block';
        
        const tipoSolicitudInputPagoPM = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudIdPagoPM = tipoSolicitudInputPagoPM ? tipoSolicitudInputPagoPM.value : '';
        const urlSolicitantePagoPM = `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fecha}${tipoSolicitudIdPagoPM ? `&tipo_solicitud_id=${tipoSolicitudIdPagoPM}` : ''}`;
        
        fetch(urlSolicitantePagoPM)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.turno) {
                    renderTurnoYSalas(data.turno, detallesDiv, salasDiv, data.es_doblada || false, data.jornadas || []);
                } else {
                    renderTurnoYSalas(null, detallesDiv, salasDiv, false, []);
                }
            })
            .catch(error => {
                console.error('Error al cargar jornada solicitante PM:', error);
                if (detallesDiv) detallesDiv.innerHTML = '<div class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> Error</div>';
                if (salasDiv) salasDiv.innerHTML = '<div class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> Error</div>';
            });
    }
    
    /**
     * Cargar jornada del receptor para fecha de pago AM (Cesión Total)
     */
    function cargarJornadaReceptorPagoAM(empleadoId, fecha) {
        if (!fecha || !empleadoId) {
            const infoDiv = document.getElementById('turno_receptor_pago_am_info');
            if (infoDiv) infoDiv.style.display = 'none';
            return;
        }
        
        const detallesDiv = document.getElementById('turno_receptor_pago_am_detalles');
        const salasDiv = document.getElementById('salas_receptor_pago_am_detalles');
        const infoDiv = document.getElementById('turno_receptor_pago_am_info');
        
        if (detallesDiv) detallesDiv.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>';
        if (salasDiv) salasDiv.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>';
        if (infoDiv) infoDiv.style.display = 'block';
        
        const tipoSolicitudInputReceptorPagoAM = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudIdReceptorPagoAM = tipoSolicitudInputReceptorPagoAM ? tipoSolicitudInputReceptorPagoAM.value : '';
        const urlReceptorPagoAM = `/solicitudes/obtener-turno-explorador/?explorador_id=${empleadoId}&fecha=${fecha}${tipoSolicitudIdReceptorPagoAM ? `&tipo_solicitud_id=${tipoSolicitudIdReceptorPagoAM}` : ''}`;
        
        fetch(urlReceptorPagoAM)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.turno) {
                    renderTurnoYSalas(data.turno, detallesDiv, salasDiv, data.es_doblada || false, data.jornadas || []);
                } else {
                    renderTurnoYSalas(null, detallesDiv, salasDiv, false, [], { contexto: 'receptor' });
                }
            })
            .catch(error => {
                console.error('Error al cargar jornada receptor AM:', error);
                if (detallesDiv) detallesDiv.innerHTML = '<div class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> Error</div>';
                if (salasDiv) salasDiv.innerHTML = '<div class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> Error</div>';
            });
    }
    
    /**
     * Cargar jornada del receptor para fecha de pago PM (Cesión Total)
     */
    function cargarJornadaReceptorPagoPM(empleadoId, fecha) {
        if (!fecha || !empleadoId) {
            const infoDiv = document.getElementById('turno_receptor_pago_pm_info');
            if (infoDiv) infoDiv.style.display = 'none';
            return;
        }
        
        const detallesDiv = document.getElementById('turno_receptor_pago_pm_detalles');
        const salasDiv = document.getElementById('salas_receptor_pago_pm_detalles');
        const infoDiv = document.getElementById('turno_receptor_pago_pm_info');
        
        if (detallesDiv) detallesDiv.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>';
        if (salasDiv) salasDiv.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</div>';
        if (infoDiv) infoDiv.style.display = 'block';
        
        const tipoSolicitudInputReceptorPagoPM = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudIdReceptorPagoPM = tipoSolicitudInputReceptorPagoPM ? tipoSolicitudInputReceptorPagoPM.value : '';
        const urlReceptorPagoPM = `/solicitudes/obtener-turno-explorador/?explorador_id=${empleadoId}&fecha=${fecha}${tipoSolicitudIdReceptorPagoPM ? `&tipo_solicitud_id=${tipoSolicitudIdReceptorPagoPM}` : ''}`;
        
        fetch(urlReceptorPagoPM)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.turno) {
                    renderTurnoYSalas(data.turno, detallesDiv, salasDiv, data.es_doblada || false, data.jornadas || []);
                } else {
                    renderTurnoYSalas(null, detallesDiv, salasDiv, false, [], { contexto: 'receptor' });
                }
            })
            .catch(error => {
                console.error('Error al cargar jornada receptor PM:', error);
                if (detallesDiv) detallesDiv.innerHTML = '<div class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> Error</div>';
                if (salasDiv) salasDiv.innerHTML = '<div class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> Error</div>';
            });
    }
    
    /**
     * Restaurar la estructura HTML del bloque doblada_existente_info.
     * Se usa cuando CASO 1 o 1.5 (descansando / no puede ceder) reemplazaron el innerHTML
     * y el usuario vuelve a una fecha con doblada existente.
     */
    function restaurarEstructuraDobladaExistente() {
        if (!dobladaExistenteInfo) return;
        dobladaExistenteInfo.innerHTML = `
            <div class="alert alert-info">
                <h6 class="alert-heading">
                    <i class="fas fa-info-circle mr-2"></i>Doblada Existente Detectada
                </h6>
                <p class="mb-2">Ya tienes una doblada aprobada para esta fecha. Puedes ceder una jornada (AM o PM) o ambas jornadas (cesión total).</p>
                <div class="form-group">
                    <label for="tipo_cesion_opcion">
                        <i class="fas fa-clock mr-1"></i>Tipo de Cesión <span class="text-danger">*</span>
                    </label>
                    <div class="form-check">
                        <input class="form-check-input" type="radio" name="tipo_cesion_opcion" id="cesion_parcial" value="parcial" checked>
                        <label class="form-check-label" for="cesion_parcial">
                            Cesión Parcial (solo una jornada)
                        </label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="radio" name="tipo_cesion_opcion" id="cesion_total" value="total">
                        <label class="form-check-label" for="cesion_total">
                            Cesión Total (ambas jornadas - AM y PM)
                        </label>
                    </div>
                    <input type="hidden" id="tipo_cesion" name="tipo_cesion" value="cesion_parcial_am">
                </div>
                <div id="opciones_cesion_parcial" class="form-group">
                    <label for="jornada_cedida">
                        <i class="fas fa-clock mr-1"></i>Jornada a Ceder <span class="text-danger">*</span>
                    </label>
                    <div class="form-check">
                        <input class="form-check-input" type="radio" name="jornada_cedida" id="jornada_am" value="AM">
                        <label class="form-check-label" for="jornada_am">
                            AM (Mañana)
                        </label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="radio" name="jornada_cedida" id="jornada_pm" value="PM">
                        <label class="form-check-label" for="jornada_pm">
                            PM (Tarde)
                        </label>
                    </div>
                </div>
                <div id="opciones_cesion_total" class="form-group" style="display: none;">
                    <div class="alert alert-warning">
                        <strong>Cesión Total:</strong> Cederás ambas jornadas (AM y PM) a dos compañeros diferentes. Se crearán 2 solicitudes independientes.
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Verificar si el solicitante tiene doblada existente en la fecha
     */
    function verificarDobladaExistente(fecha) {
        if (!fecha) return;
        console.log('[DEBUG] Verificando doblada existente para fecha:', fecha);
        fetch(`/solicitudes/verificar-doblada-existente/?fecha=${fecha}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                console.log('[DEBUG] Respuesta verificar-doblada-existente:', data);
                if (data.success) {
                    // El endpoint retorna: {success: true, tiene_doblada, esta_descansando, puede_ceder, jornadas, mensaje}
                    tieneDobladaExistente = data.tiene_doblada || false;
                    jornadasDobladaExistente = data.jornadas || [];
                    const estaDescansando = data.esta_descansando || false;
                    const puedeCeder = data.puede_ceder !== false; // Default true
                    console.log('[DEBUG] tieneDobladaExistente:', tieneDobladaExistente, 'jornadas:', jornadasDobladaExistente, 'estaDescansando:', estaDescansando);
                    
                    // CASO 1: Usuario está descansando (cedió su jornada)
                    if (estaDescansando) {
                        dobladaExistenteInfo.style.display = 'block';
                        dobladaExistenteInfo.innerHTML = `
                            <div class="alert alert-info">
                                <i class="fas fa-bed mr-2"></i>
                                <strong>Estás Descansando</strong>
                                <p class="mb-1">${data.mensaje || 'Ya cediste tu jornada para esta fecha.'}</p>
                                <small class="text-muted">
                                    <i class="fas fa-info-circle"></i> 
                                    Para realizar cambios, selecciona otra fecha o cancela la solicitud existente.
                                </small>
                            </div>
                        `;

                        // Ocultar y limpiar la sección de jornada del solicitante
                        if (turnoSolicitanteInfo) {
                            turnoSolicitanteInfo.style.display = 'none';
                        }
                        if (turnoSolicitanteDetalles) {
                            turnoSolicitanteDetalles.innerHTML = '';
                        }
                        if (salasSolicitanteDetalles) {
                            salasSolicitanteDetalles.innerHTML = '';
                        }
                        
                        // Deshabilitar todos los controles del formulario
                        deshabilitarFormularioDoblada();
                        return;
                    }
                    
                    // CASO 1.5: Usuario no puede ceder (tiene CT aprobado u otra razón)
                    if (!puedeCeder && !tieneDobladaExistente && !estaDescansando) {
                        dobladaExistenteInfo.style.display = 'block';
                        dobladaExistenteInfo.innerHTML = `
                            <div class="alert alert-warning">
                                <i class="fas fa-exclamation-triangle mr-2"></i>
                                <strong>No Puedes Solicitar Doblada</strong>
                                <p class="mb-1">${data.mensaje || 'No puedes solicitar doblada para esta fecha.'}</p>
                                <small class="text-muted">
                                    <i class="fas fa-info-circle"></i> 
                                    Para realizar cambios, selecciona otra fecha.
                                </small>
                            </div>
                        `;
                        
                        // Deshabilitar todos los controles del formulario
                        deshabilitarFormularioDoblada();
                        limpiarEstadoDoblada();
                        return;
                    }
                    
                    // CASO 2: Usuario tiene doblada (es receptor)
                    if (tieneDobladaExistente) {
                        // 1. Restaurar estructura si fue destruida por CASO 1 o 1.5 (descansando / no puede ceder)
                        if (!document.getElementById('opciones_cesion_parcial')) {
                            restaurarEstructuraDobladaExistente();
                        }

                        // 2. Mostrar el contenedor principal
                        dobladaExistenteInfo.style.display = 'block';
                        
                        // 3. DETECTAR INCONSISTENCIAS DE DATOS
                        const tieneInconsistencia = data.datos_inconsistentes || false;
                        const requiereAtencion = data.requiere_atencion_admin || false;
                        
                        // 4. Actualizar mensaje del alert (opcional, si existe)
                        const alertDiv = dobladaExistenteInfo.querySelector('.alert');
                        if (alertDiv) {
                            if (tieneInconsistencia) {
                                alertDiv.className = 'alert alert-warning';
                                const alertHeading = alertDiv.querySelector('.alert-heading');
                                const alertMessage = alertDiv.querySelector('p');
                                
                                if (alertHeading) {
                                    alertHeading.innerHTML = '<i class="fas fa-exclamation-triangle mr-2"></i>Doblada con Datos Inconsistentes';
                                }
                                if (alertMessage) {
                                    alertMessage.innerHTML = `${data.mensaje || 'Datos inconsistentes detectados.'}<hr><p class="mb-0"><i class="fas fa-tools mr-1"></i><strong>Acción requerida:</strong> Esta solicitud requiere atención del administrador. Puedes intentar <a href="/solicitudes/mis-solicitudes/" class="alert-link">cancelar la solicitud existente</a> y crear una nueva.</p>`;
                                }
                            } else {
                                // Sin inconsistencia: Actualizar mensaje normal
                                const alertHeading = alertDiv.querySelector('.alert-heading');
                                const alertMessage = alertDiv.querySelector('p');
                                
                                if (alertHeading) {
                                    alertHeading.innerHTML = '<i class="fas fa-info-circle mr-2"></i>Doblada Existente Detectada';
                                }
                                if (alertMessage) {
                                    alertMessage.textContent = data.mensaje || 'Ya tienes una doblada aprobada para esta fecha. Puedes ceder una jornada (AM o PM) o ambas jornadas (cesión total).';
                                }
                            }
                        }
                        
                        // 5. SIEMPRE mostrar/ocultar opciones de cesión (independientemente de alertDiv)
                        const opcionesParcial = document.getElementById('opciones_cesion_parcial');
                        const opcionesTotal = document.getElementById('opciones_cesion_total');
                        
                        if (tieneInconsistencia) {
                            // Ocultar opciones si hay inconsistencia
                            if (opcionesParcial) opcionesParcial.style.display = 'none';
                            if (opcionesTotal) opcionesTotal.style.display = 'none';
                            // Deshabilitar formulario si hay inconsistencia
                            deshabilitarFormularioDoblada();
                        } else {
                            // Mostrar opciones si NO hay inconsistencia
                            if (opcionesParcial) opcionesParcial.style.display = 'block';
                            
                            // Habilitar controles
                            habilitarFormularioDoblada();
                            
                            // Seleccionar jornada por defecto según las jornadas disponibles
                            if (jornadasDobladaExistente.length === 1) {
                                // Si solo tiene una jornada, seleccionarla automáticamente
                                const jornada = jornadasDobladaExistente[0];
                                const radioJornada = document.getElementById(`jornada_${jornada.toLowerCase()}`);
                                if (radioJornada) {
                                    radioJornada.checked = true;
                                    if (tipoCesionHidden) tipoCesionHidden.value = `cesion_parcial_${jornada.toLowerCase()}`;
                                }
                            } else if (jornadasDobladaExistente.length === 2) {
                                // Si tiene ambas jornadas (AM y PM), seleccionar AM por defecto
                                const radioAM = document.getElementById('jornada_am');
                                if (radioAM) {
                                    radioAM.checked = true;
                                    if (tipoCesionHidden) tipoCesionHidden.value = 'cesion_parcial_am';
                                }
                            }
                            
                            // Si no se seleccionó ninguna jornada, usar AM como default
                            const jornadaSeleccionada = document.querySelector('input[name="jornada_cedida"]:checked');
                            if (!jornadaSeleccionada && tipoCesionHidden) {
                                tipoCesionHidden.value = 'cesion_parcial_am';
                            }
                            // Sincronizar vista con tipo de cesión: si está "Cesión Total", ocultar "Jornada a Ceder"
                            const esCesionTotalChecked = document.querySelector('input[name="tipo_cesion_opcion"]:checked')?.value === 'total';
                            if (esCesionTotalChecked && typeof toggleCesionTipo === 'function') {
                                toggleCesionTipo(true);
                            }
                        }
                    } 
                    // CASO 3: No hay doblada (usuario normal) o festivo donde el usuario descansa
                    else {
                        const mensajeFestivoDescansa = data.mensaje_festivo_descansa || '';
                        if (mensajeFestivoDescansa) {
                            // Limpiar opciones/radios PRIMERO (sin tocar display de dobladaExistenteInfo)
                            limpiarEstadoDoblada();
                            // Ocultar sección de jornada del solicitante (descansa ese día, no tiene turno)
                            if (turnoSolicitanteInfo) turnoSolicitanteInfo.style.display = 'none';
                            if (turnoSolicitanteDetalles) turnoSolicitanteDetalles.innerHTML = '';
                            if (salasSolicitanteDetalles) salasSolicitanteDetalles.innerHTML = '';
                            // Mostrar mensaje en indicador de festivo (visible al seleccionar festivo)
                            const descripcionFestivo = document.getElementById('descripcion_festivo_cesion');
                            if (indicadorFestivoCesion && descripcionFestivo) {
                                indicadorFestivoCesion.style.display = 'block';
                                descripcionFestivo.innerHTML = `<span class="d-block">${mensajeFestivoDescansa}</span>`;
                            }
                            habilitarFormularioDoblada();
                        } else {
                            // Sin mensaje especial: limpiar y habilitar
                            limpiarEstadoDoblada();
                            habilitarFormularioDoblada();
                        }
                    }
                    
                    // Cargar exploradores disponibles (centralizado aquí para evitar llamadas duplicadas)
                    // Solo se carga si puedeCeder es true y no está descansando
                    if (puedeCeder && !estaDescansando) {
                        // Si hay doblada existente y es cesión total, cargar para AM y PM por separado
                        const esCesionTotal = document.querySelector('input[name="tipo_cesion_opcion"]:checked')?.value === 'total';
                        if (tieneDobladaExistente && esCesionTotal) {
                            cargarExploradoresDisponibles(fecha, 'AM', empleadoReceptorAM);
                            cargarExploradoresDisponibles(fecha, 'PM', empleadoReceptorPM);
                        } else {
                            // Cesión parcial o sin doblada: cargar una sola vez
                            // En sábados con doblada existente, jornada_cedida ya está preseleccionada arriba
                            cargarExploradoresDisponibles(fecha);
                        }
                    }

                    // Cargar jornada del solicitante solo cuando tiene turno ese día
                    // (no cargar si está descansando o si es festivo donde descansa)
                    if (!estaDescansando && !(data.mensaje_festivo_descansa || '')) {
                        cargarJornadaSolicitante(fecha);
                    }
                }
            })
            .catch(error => {
                console.error('Error verificando doblada existente:', error);
            });
    }
    
    /**
     * Limpiar estado de doblada cuando se cambia a una fecha sin doblada
     * Aplica patrones modernos: optional chaining, nullish coalescing, arrow functions
     */
    function limpiarEstadoDoblada() {
        // Ocultar información de doblada existente usando optional chaining
        dobladaExistenteInfo?.style.setProperty('display', 'none');
        
        // Limpiar y ocultar opciones de cesión parcial usando optional chaining
        const opcionesParcial = document.getElementById('opciones_cesion_parcial');
        opcionesParcial?.style.setProperty('display', 'none');
        
        // Limpiar selección de radio buttons de jornada cedida usando forEach con arrow function
        jornadaCedidaRadios?.forEach(radio => {
            radio.checked = false;
        });
        
        // Asegurar que se muestre solo cesión completa (normal)
        if (tipoCesionHidden) {
            tipoCesionHidden.value = 'cesion_completa';
        }
        
        // Seleccionar "cesión completa" usando optional chaining
        const radioCesionCompleta = document.querySelector('input[name="tipo_cesion_opcion"][value="completa"]');
        radioCesionCompleta && (radioCesionCompleta.checked = true);
        
        // Asegurar que se muestren los campos de cesión completa (no parcial)
        // Usando optional chaining y operador de asignación lógica
        opcionesCesionTotal?.style.setProperty('display', 'none');
        receptoresTotal?.style.setProperty('display', 'none');
        fechasPagoTotal?.style.setProperty('display', 'none');
        receptorParcial?.style.setProperty('display', 'block');
        fechaPagoParcial?.style.setProperty('display', 'block');
        
        // Limpiar campos de cesión total usando optional chaining y operador lógico
        empleadoReceptorAM && (empleadoReceptorAM.value = '');
        empleadoReceptorPM && (empleadoReceptorPM.value = '');
        fechaPagoAM && (fechaPagoAM.value = '');
        fechaPagoPM && (fechaPagoPM.value = '');
    }
    
    /**
     * Deshabilitar formulario cuando el usuario está descansando
     */
    function deshabilitarFormularioDoblada() {
        if (empleadoReceptorSelect) empleadoReceptorSelect.disabled = true;
        if (fechaPagoInput) fechaPagoInput.disabled = true;
        if (empleadoReceptorAM) empleadoReceptorAM.disabled = true;
        if (empleadoReceptorPM) empleadoReceptorPM.disabled = true;
        if (fechaPagoAM) fechaPagoAM.disabled = true;
        if (fechaPagoPM) fechaPagoPM.disabled = true;
        
        const submitBtn = document.querySelector('button[type="submit"]');
        if (submitBtn) submitBtn.disabled = true;
    }
    
    /**
     * Habilitar formulario cuando el usuario puede ceder
     */
    function habilitarFormularioDoblada() {
        if (empleadoReceptorSelect) empleadoReceptorSelect.disabled = false;
        if (fechaPagoInput) fechaPagoInput.disabled = false;
        if (empleadoReceptorAM) empleadoReceptorAM.disabled = false;
        if (empleadoReceptorPM) empleadoReceptorPM.disabled = false;
        if (fechaPagoAM) fechaPagoAM.disabled = false;
        if (fechaPagoPM) fechaPagoPM.disabled = false;
        
        const submitBtn = document.querySelector('button[type="submit"]');
        if (submitBtn) submitBtn.disabled = false;
    }
    
    /**
     * Cargar exploradores disponibles para doblada
     */
    /**
     * Cargar exploradores disponibles para "Compañero que te cubrirá".
     * Usa la fecha en la que el receptor trabajará (fecha de pago cuando aplique).
     * Si la fecha es sábado, el backend devuelve solo quienes trabajan ese sábado (alternancia).
     * @param {string} fecha - Fecha para la que se buscan compañeros (cesión o fecha de pago)
     * @param {string} jornada - Jornada específica ('AM' o 'PM') para cesión total (opcional)
     * @param {HTMLElement} selectElement - Elemento select donde cargar (opcional, por defecto empleadoReceptorSelect)
     */
    function cargarExploradoresDisponibles(fecha, jornada = null, selectElement = null) {
        if (!fecha) {
            const targetSelect = selectElement || empleadoReceptorSelect;
            if (targetSelect) {
                targetSelect.innerHTML = '<option value="">Selecciona primero la fecha de cesión</option>';
            }
            return;
        }
        
        const targetSelect = selectElement || empleadoReceptorSelect;
        if (!targetSelect) {
            return;
        }
        
        // CORRECCIÓN: Obtener jornada cedida - Lógica simplificada
        let jornadaCedida = null;
        
        // Prioridad 1: Si se pasó jornada explícitamente como parámetro (cesión total)
        if (jornada) {
            jornadaCedida = jornada;
        } 
        // Prioridad 2: Obtener del radio button seleccionado (cesión parcial)
        else {
            const radioSeleccionado = document.querySelector('input[name="jornada_cedida"]:checked');
            if (radioSeleccionado) {
                jornadaCedida = radioSeleccionado.value;
            }
        }
        
        const url = `/solicitudes/obtener-exploradores-doblada/?fecha=${fecha}${jornadaCedida ? `&jornada_cedida=${jornadaCedida}` : ''}`;
        
        targetSelect.innerHTML = '<option value="">Cargando...</option>';
        
        fetch(url)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // #region agent log
                fetch('http://127.0.0.1:7242/ingest/b42d6aa4-60e5-456e-b2ef-83a8940b0ea5',{
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:JSON.stringify({
                        hypothesisId:'F2',
                        location:'solicitar_doblada.js:cargarExploradoresDisponibles',
                        message:'respuesta_obtener_exploradores_doblada',
                        data:{
                            fecha: fecha,
                            jornada_param: jornada,
                            jornadaCedidaCalculada: jornadaCedida,
                            total: data && typeof data.total === 'number' ? data.total : (data.empleados ? data.empleados.length : null)
                        },
                        timestamp: Date.now()
                    })
                }).catch(function(){});
                // #endregion
                if (data.success) {
                    targetSelect.innerHTML = '<option value="">Selecciona un compañero...</option>';
                    
                    // El endpoint retorna: {success: true, empleados: [...], total: N}
                    if (data.empleados && data.empleados.length > 0) {
                        data.empleados.forEach(empleado => {
                            const option = document.createElement('option');
                            option.value = empleado.id;
                            option.textContent = `${empleado.nombre} ${empleado.apellido} (${empleado.jornada})`;
                            targetSelect.appendChild(option);
                        });
                    } else {
                        targetSelect.innerHTML = '<option value="">No hay compañeros disponibles para esta fecha</option>';
                    }
                    
                    // Actualizar vista previa
                    actualizarVistaPrevia();
                } else {
                    console.error('Error en respuesta:', data.error || 'Error desconocido');
                    targetSelect.innerHTML = '<option value="">Error al cargar compañeros</option>';
                }
            })
            .catch(error => {
                console.error('Error cargando exploradores disponibles:', error);
                targetSelect.innerHTML = '<option value="">Error al cargar compañeros</option>';
            });
    }
    
    /**
     * Actualizar vista previa del acuerdo
     * Formato: "El día X cedes tu jornada AM/PM a Y. Y te cubrirá el día Z"
     * Maneja tanto cesión parcial como cesión total
     */
    function actualizarVistaPreviaAcuerdo() {
        const fechaCesion = fechaCesionInput.value;
        const esCesionTotal = document.querySelector('input[name="tipo_cesion_opcion"]:checked')?.value === 'total';
        
        if (!vistaPreviaAcuerdo || !resumenAcuerdo) {
            return;
        }
        
        if (esCesionTotal) {
            // Cesión Total: mostrar resumen de ambas solicitudes
            const empleadoReceptorAMId = empleadoReceptorAM ? empleadoReceptorAM.value : null;
            const empleadoReceptorPMId = empleadoReceptorPM ? empleadoReceptorPM.value : null;
            const fechaPagoAMVal = fechaPagoAM ? fechaPagoAM.value : null;
            const fechaPagoPMVal = fechaPagoPM ? fechaPagoPM.value : null;
            
            if (fechaCesion && empleadoReceptorAMId && empleadoReceptorPMId && fechaPagoAMVal && fechaPagoPMVal) {
                const receptorAMOption = empleadoReceptorAM.options[empleadoReceptorAM.selectedIndex];
                const receptorPMOption = empleadoReceptorPM.options[empleadoReceptorPM.selectedIndex];
                const receptorAMNombre = receptorAMOption ? receptorAMOption.text.split(' (')[0] : '';
                const receptorPMNombre = receptorPMOption ? receptorPMOption.text.split(' (')[0] : '';
                
                const fechaCesionFormateada = formatearFecha(fechaCesion);
                const fechaPagoAMFormateada = formatearFecha(fechaPagoAMVal);
                const fechaPagoPMFormateada = formatearFecha(fechaPagoPMVal);
                
                resumenAcuerdo.innerHTML = `
                    <div class="alert alert-info mb-0">
                        <strong>Resumen del Acuerdo (Cesión Total):</strong><br>
                        <p class="mb-2">El día <strong>${fechaCesionFormateada}</strong> cederás ambas jornadas:</p>
                        <ul class="text-left mb-2">
                            <li><strong>AM</strong> a <strong>${receptorAMNombre}</strong>. Te cubrirá el día <strong>${fechaPagoAMFormateada}</strong>.</li>
                            <li><strong>PM</strong> a <strong>${receptorPMNombre}</strong>. Te cubrirá el día <strong>${fechaPagoPMFormateada}</strong>.</li>
                        </ul>
                        <p class="mb-0"><small><strong>Nota:</strong> Se crearán 2 solicitudes independientes.</small></p>
                    </div>
                `;
                
                vistaPreviaAcuerdo.style.display = 'block';
            } else {
                vistaPreviaAcuerdo.style.display = 'none';
            }
        } else {
            // Cesión Parcial: mostrar resumen normal
            const fechaPago = fechaPagoInput.value;
            const empleadoReceptorId = empleadoReceptorSelect.value;
            const empleadoReceptorOption = empleadoReceptorSelect.options[empleadoReceptorSelect.selectedIndex];
            const empleadoReceptorNombre = empleadoReceptorOption ? empleadoReceptorOption.text.split(' (')[0] : ''; // Extraer solo el nombre sin la jornada
            
            if (fechaCesion && fechaPago && empleadoReceptorId && empleadoReceptorNombre) {
                // Determinar jornada cedida
                let jornadaCedidaTexto = 'tu jornada';
                if (tieneDobladaExistente) {
                    const jornadaCedidaRadio = document.querySelector('input[name="jornada_cedida"]:checked');
                    if (jornadaCedidaRadio) {
                        const jornadaCedida = jornadaCedidaRadio.value;
                        jornadaCedidaTexto = `tu jornada ${jornadaCedida}`;
                    }
                }
                
                // Formatear fechas para mostrar
                const fechaCesionFormateada = formatearFecha(fechaCesion);
                const fechaPagoFormateada = formatearFecha(fechaPago);
                
                // Construir mensaje según el plan de doblada:
                // - En la fecha de cesión: el compañero se dobla por ti (tú descansas).
                // - En la fecha de pago: tú trabajas por el compañero (cubres una de sus jornadas).
                resumenAcuerdo.innerHTML = `
                    <div class="alert alert-info mb-0">
                        <strong>Resumen del Acuerdo:</strong><br>
                        El día <strong>${fechaCesionFormateada}</strong> cedes <strong>${jornadaCedidaTexto}</strong> a <strong>${empleadoReceptorNombre}</strong> (él se dobla por ti y tú descansas).<br>
                        El día <strong>${fechaPagoFormateada}</strong> <strong>tú</strong> cubrirás una de las jornadas de <strong>${empleadoReceptorNombre}</strong> como pago de la doblada.
                    </div>
                `;
                
                vistaPreviaAcuerdo.style.display = 'block';
            } else {
                vistaPreviaAcuerdo.style.display = 'none';
            }
        }
    }
    
    /**
     * Formatear fecha de YYYY-MM-DD a DD/MM/YYYY
     */
    function formatearFecha(fecha) {
        if (!fecha) return '';
        const partes = fecha.split('-');
        if (partes.length === 3) {
            return `${partes[2]}/${partes[1]}/${partes[0]}`;
        }
        return fecha;
    }
    
    /**
     * Alias para mantener compatibilidad
     */
    function actualizarVistaPrevia() {
        actualizarVistaPreviaAcuerdo();
    }
    
    /**
     * Manejar cambio entre cesión parcial y total
     */
    if (tipoCesionOpcionRadios && tipoCesionOpcionRadios.length > 0) {
        tipoCesionOpcionRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                if (this.checked) {
                    const esTotal = this.value === 'total';
                    toggleCesionTipo(esTotal);
                }
            });
        });
    }
    
    /**
     * Mostrar/ocultar campos según tipo de cesión
     */
    function toggleCesionTipo(esTotal) {
        if (esTotal) {
            // Cesión Total
            tipoCesionHidden.value = 'cesion_completa';
            
            // Mostrar campos de cesión total
            if (opcionesCesionTotal) opcionesCesionTotal.style.display = 'block';
            if (opcionesCesionParcial) opcionesCesionParcial.style.display = 'none';
            if (receptoresTotal) receptoresTotal.style.display = 'block';
            if (receptorParcial) receptorParcial.style.display = 'none';
            if (fechasPagoTotal) fechasPagoTotal.style.display = 'block';
            if (fechaPagoParcial) fechaPagoParcial.style.display = 'none';
            
            // Limpiar campos de cesión parcial
            if (empleadoReceptorSelect) empleadoReceptorSelect.value = '';
            if (fechaPagoInput) fechaPagoInput.value = '';
            
            // Cargar exploradores para AM y PM
            if (fechaCesionInput && fechaCesionInput.value) {
                cargarExploradoresDisponibles(fechaCesionInput.value, 'AM', empleadoReceptorAM);
                cargarExploradoresDisponibles(fechaCesionInput.value, 'PM', empleadoReceptorPM);
            }
            
            // Inicializar datepickers para fechas de pago AM y PM si no están inicializados
            if (fechaPagoAM && !fechaPagoAM.hasAttribute('data-initialized')) {
                inicializarDatepickerPagoAM();
            }
            if (fechaPagoPM && !fechaPagoPM.hasAttribute('data-initialized')) {
                inicializarDatepickerPagoPM();
            }
        } else {
            // Cesión Parcial
            if (jornadaCedidaRadios && jornadaCedidaRadios.length > 0) {
                const jornadaSeleccionada = document.querySelector('input[name="jornada_cedida"]:checked');
                if (jornadaSeleccionada) {
                    tipoCesionHidden.value = `cesion_parcial_${jornadaSeleccionada.value.toLowerCase()}`;
                } else {
                    tipoCesionHidden.value = 'cesion_parcial_am';
                }
            }
            
            // Mostrar campos de cesión parcial
            if (opcionesCesionTotal) opcionesCesionTotal.style.display = 'none';
            if (opcionesCesionParcial) opcionesCesionParcial.style.display = 'block';
            if (receptoresTotal) receptoresTotal.style.display = 'none';
            if (receptorParcial) receptorParcial.style.display = 'block';
            if (fechasPagoTotal) fechasPagoTotal.style.display = 'none';
            if (fechaPagoParcial) fechaPagoParcial.style.display = 'block';
            
            // Limpiar campos de cesión total
            if (empleadoReceptorAM) empleadoReceptorAM.value = '';
            if (empleadoReceptorPM) empleadoReceptorPM.value = '';
            if (fechaPagoAM) fechaPagoAM.value = '';
            if (fechaPagoPM) fechaPagoPM.value = '';
            
            // Cargar exploradores para cesión parcial (usar fecha de pago si está elegida)
            if (fechaCesionInput && fechaCesionInput.value) {
                const fechaParaLista = (fechaPagoInput && fechaPagoInput.value) ? fechaPagoInput.value : fechaCesionInput.value;
                cargarExploradoresDisponibles(fechaParaLista);
            }
        }
        
        actualizarVistaPrevia();
    }
    
    /**
     * Manejar cambio en jornada cedida (si está en doblada)
     */
    jornadaCedidaRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.checked) {
                tipoCesionHidden.value = `cesion_parcial_${this.value.toLowerCase()}`;
                // Recargar exploradores disponibles SIEMPRE con la fecha de cesión.
                // La fecha de pago sábado no debe cambiar el grupo de compañeros.
                const fechaParaLista = fechaCesionInput.value;
                if (fechaParaLista) {
                    cargarExploradoresDisponibles(fechaParaLista);
                }
                actualizarVistaPrevia();
            }
        });
    });
    
    /**
     * Validar que el sábado de pago corresponda a la jornada del receptor (quien hizo el doble turno)
     * Regla de negocio:
     * - Si cedes jornada AM → receptor es PM → sábado de pago debe ser para PM
     * - Si cedes jornada PM → receptor es AM → sábado de pago debe ser para AM
     * Aplica patrones modernos: async/await, optional chaining, destructuring
     */
    async function validarSabadoCorrespondeReceptor(fechaPago, receptorId, fechaCesion) {
        if (!fechaPago || !receptorId || !fechaCesion) return;
        
        try {
            // Obtener jornada del receptor en fecha de cesión (quien hizo el doble turno)
            const [responseReceptor, responsePago] = await Promise.all([
                fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${receptorId}&fecha=${fechaCesion}`),
                fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fechaPago}`)
            ]);
            
            const [dataReceptor, dataPago] = await Promise.all([
                responseReceptor.json(),
                responsePago.json()
            ]);
            
            if (!dataReceptor.success || !dataReceptor.turno) {
                return; // No validar si no hay datos del receptor
            }
            
            // Obtener jornada del receptor en fecha de cesión
            const jornadaReceptorCesion = dataReceptor.turno.jornada?.toUpperCase();
            if (!jornadaReceptorCesion || !['AM', 'PM'].includes(jornadaReceptorCesion)) {
                return; // No validar si no hay jornada válida
            }
            
            // Obtener jornada que trabaja ese sábado (alternancia)
            const jornadaTrabajaSabado = dataPago.jornada_trabaja_sabado?.toUpperCase();
            if (!jornadaTrabajaSabado) {
                return; // No validar si no se puede determinar alternancia
            }
            
            // Validar que el sábado corresponda a la jornada del receptor
            if (jornadaReceptorCesion !== jornadaTrabajaSabado) {
                // Obtener jornada que se está cediendo para el mensaje
                let jornadaCedida = null;
                if (tieneDobladaExistente) {
                    const radioJornada = document.querySelector('input[name="jornada_cedida"]:checked');
                    if (radioJornada) {
                        jornadaCedida = radioJornada.value.toUpperCase();
                    }
                } else {
                    // Obtener jornada del solicitante en fecha de cesión
                    const responseSolicitante = await fetch(
                        `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fechaCesion}`
                    );
                    const dataSolicitante = await responseSolicitante.json();
                    if (dataSolicitante.success && dataSolicitante.turno) {
                        jornadaCedida = dataSolicitante.turno.jornada?.toUpperCase();
                    }
                }
                
                const fechaPagoFormateada = formatearFecha(fechaPago);
                const mensaje = jornadaCedida 
                    ? `No se puede realizar esta solicitud. El sábado ${fechaPagoFormateada} corresponde al turno ${jornadaTrabajaSabado}, pero el compañero que cubrirá tu jornada ${jornadaCedida} tiene jornada ${jornadaReceptorCesion}. El sábado de pago siempre debe coincidir con el turno de la persona que realizó el doble turno. Por favor, selecciona otro sábado que corresponda al turno ${jornadaReceptorCesion}.`
                    : `No se puede realizar esta solicitud. El sábado ${fechaPagoFormateada} corresponde al turno ${jornadaTrabajaSabado}, pero el compañero que cubrirá tu jornada tiene jornada ${jornadaReceptorCesion}. El sábado de pago siempre debe coincidir con el turno de la persona que realizó el doble turno. Por favor, selecciona otro sábado que corresponda al turno ${jornadaReceptorCesion}.`;
                
                Swal.fire({
                    icon: 'error',
                    title: 'Sábado No Válido',
                    html: `<div class="text-left"><p>${mensaje}</p></div>`,
                    confirmButtonText: 'Entendido',
                    confirmButtonColor: '#d33',
                    width: '600px'
                });
                
                // Limpiar fecha de pago
                fechaPagoInput.value = '';
                mostrarOpcionesPagoSabado(false);
                mostrarMensajeNoNecesarioPagoSabado(false);
            }
        } catch (error) {
            console.error('Error validando sábado corresponde receptor:', error);
            // No mostrar error al usuario si falla la validación (el backend validará)
        }
    }
    
    /**
     * Manejar cambio en empleado receptor
     */
    empleadoReceptorSelect.addEventListener('change', function() {
        const empleadoId = this.value;
        const fechaCesion = fechaCesionInput.value;
        const fechaPago = fechaPagoInput.value;
        
        // Cargar jornada en fecha de cesión
        if (empleadoId && fechaCesion) {
            cargarJornadaReceptor(empleadoId, fechaCesion);
        } else {
            if (turnoReceptorInfo) {
                turnoReceptorInfo.style.display = 'none';
            }
        }
        
        // Cargar jornada en fecha de pago (si está seleccionada)
        if (empleadoId && fechaPago) {
            cargarJornadaReceptorPago(empleadoId, fechaPago);
        } else {
            if (turnoReceptorPagoInfo) {
                turnoReceptorPagoInfo.style.display = 'none';
            }
        }
        
        // ✅ NUEVA VALIDACIÓN: Si hay fecha de pago sábado, validar que corresponda a la jornada del receptor
        if (empleadoId && fechaPago && esSabado(fechaPago) && fechaCesion) {
            validarSabadoCorrespondeReceptor(fechaPago, empleadoId, fechaCesion);
        }
        
        actualizarVistaPrevia();
    });
    
    /**
     * Manejar cambios en receptores y fechas de pago para cesión total
     */
    if (empleadoReceptorAM) {
        empleadoReceptorAM.addEventListener('change', function() {
            const empleadoId = this.value;
            const fechaPago = fechaPagoAM ? fechaPagoAM.value : null;
            
            // Cargar jornada del receptor para la fecha de pago AM
            if (empleadoId && fechaPago) {
                cargarJornadaReceptorPagoAM(empleadoId, fechaPago);
            }
            actualizarVistaPrevia();
        });
    }
    
    if (empleadoReceptorPM) {
        empleadoReceptorPM.addEventListener('change', function() {
            const empleadoId = this.value;
            const fechaPago = fechaPagoPM ? fechaPagoPM.value : null;
            
            // Cargar jornada del receptor para la fecha de pago PM
            if (empleadoId && fechaPago) {
                cargarJornadaReceptorPagoPM(empleadoId, fechaPago);
            }
            actualizarVistaPrevia();
        });
    }
    
    // Función para verificar si el usuario tiene doblada en una fecha (validación preventiva)
    function verificarDobladaEnFechaPago(fecha, jornada) {
        fetch(`/solicitudes/verificar-doblada-existente/?fecha=${fecha}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.tiene_doblada) {
                    // Usuario tiene doblada en esta fecha
                    Swal.fire({
                        icon: 'warning',
                        title: 'Advertencia: Doblada Existente',
                        html: `
                            <div class="text-left">
                                <p>⚠️ <strong>Ya tienes una doblada</strong> programada para la fecha seleccionada como pago (${fecha}).</p>
                                <p class="mt-2">Jornadas detectadas: <strong>${data.jornadas.join(' + ')}</strong></p>
                                <p class="mt-3"><strong>Importante:</strong></p>
                                <p class="mt-2">No podrás enviar esta solicitud porque ya estás trabajando ambas jornadas ese día. 
                                Por favor, elige otra fecha de pago.</p>
                            </div>
                        `,
                        confirmButtonText: 'Entendido',
                        confirmButtonColor: '#ffc107'
                    });
                }
            })
            .catch(error => {
                console.error('Error verificando doblada en fecha de pago:', error);
            });
    }
    
    if (fechaPagoAM) {
        fechaPagoAM.addEventListener('change', function() {
            const fecha = this.value;
            if (fecha) {
                // Verificar si tiene doblada en esta fecha (validación preventiva)
                verificarDobladaEnFechaPago(fecha, 'AM');
                
                // Cargar jornada del solicitante para esta fecha de pago AM
                cargarJornadaSolicitantePagoAM(fecha);
                
                // Cargar jornada del receptor AM para esta fecha de pago
                const receptorAM = empleadoReceptorAM ? empleadoReceptorAM.value : null;
                if (receptorAM) {
                    cargarJornadaReceptorPagoAM(receptorAM, fecha);
                }
            }
            actualizarVistaPrevia();
        });
    }
    
    if (fechaPagoPM) {
        fechaPagoPM.addEventListener('change', function() {
            const fecha = this.value;
            if (fecha) {
                // Verificar si tiene doblada en esta fecha (validación preventiva)
                verificarDobladaEnFechaPago(fecha, 'PM');
                
                // Cargar jornada del solicitante para esta fecha de pago PM
                cargarJornadaSolicitantePagoPM(fecha);
                
                // Cargar jornada del receptor PM para esta fecha de pago
                const receptorPM = empleadoReceptorPM ? empleadoReceptorPM.value : null;
                if (receptorPM) {
                    cargarJornadaReceptorPagoPM(receptorPM, fecha);
                }
            }
            actualizarVistaPrevia();
        });
    }
    
    /**
     * Función auxiliar para enviar el formulario
     */
    function enviarFormulario() {
        const formData = new FormData(form);
    
        fetch('/solicitudes/procesar-solicitud/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        })
        .then(async response => {
            // Intentar parsear el JSON siempre, incluso si response.ok es false
            let data;
            try {
                const text = await response.text();
                if (text) {
                    data = JSON.parse(text);
                } else {
                    data = { success: false, error: `Error ${response.status}: ${response.statusText}` };
                }
            } catch (e) {
                // Si no se puede parsear, crear objeto de error genérico
                data = { 
                    success: false, 
                    error: `Error ${response.status}: ${response.statusText}`,
                    message: `Error ${response.status}: ${response.statusText}`
                };
            }
            
            // Si la respuesta no es OK, lanzar error con los datos parseados
            if (!response.ok) {
                // Caso especial: coincidencia de jornadas en fecha de pago (requiere cambio de turno previo)
                if (data && data.code === 'requiere_cambio_turno_previo') {
                    // No lanzamos error aquí para que el siguiente .then maneje el flujo especial
                    return data;
                }

                const errorMessage = data.error || data.message || `Error ${response.status}: ${response.statusText}`;
                const errorObj = {
                    ...data,
                    status: response.status,
                    statusText: response.statusText
                };
                throw errorObj;
            }
            
            return data;
        })
        .then(data => {
            // Verificar si requiere cambio de turno previo (caso crítico)
            if (data.code === 'requiere_cambio_turno_previo') {
                const fechaPago = data.fecha_pago || fechaPagoInput.value;
                const jornadaComun = data.jornada_comun || 'la misma jornada';
                const jornadaAfectada = data.jornada_afectada || '';
                
                // Construir mensaje específico si es cesión total
                const mensajeJornada = jornadaAfectada 
                    ? `<li>Problema detectado en la <strong>fecha de pago para ${jornadaAfectada}</strong> (${fechaPago}).</li>`
                    : `<li>En la fecha de pago (${fechaPago}), ambos exploradores tienen ${jornadaComun}.</li>`;
                
                Swal.fire({
                    icon: 'warning',
                    title: 'Cambio de Turno Requerido',
                    html: `
                        <div class="text-left">
                            <p><strong>No se puede realizar la doblada en este momento.</strong></p>
                            <p class="mt-2">${data.message || 'No se puede pagar trabajando dos veces la misma jornada.'}</p>
                            <p class="mt-3"><strong>Razón:</strong></p>
                            <ul class="text-left mt-2">
                                ${mensajeJornada}
                                <li>En la fecha de pago (${fechaPago}), ambos exploradores tienen jornada <strong>${jornadaComun}</strong>.</li>
                                <li>No se puede aplicar la doblada de pago trabajando dos veces la misma jornada.</li>
                            </ul>
                            <p class="mt-3"><strong>Solución:</strong></p>
                            <p class="mt-2">Debes primero realizar un <strong>cambio de turno sencillo</strong> para tener jornada contraria en la fecha de pago.</p>
                        </div>
                    `,
                    showCancelButton: true,
                    confirmButtonText: 'Ir a Cambio de Turno Sencillo',
                    cancelButtonText: 'Cancelar',
                    confirmButtonColor: '#007bff',
                    cancelButtonColor: '#6c757d',
                    width: '600px'
                }).then((result) => {
                    if (result.isConfirmed) {
                        // Redirigir a formulario de CT Sencillo con fecha prellenada
                        // tipo_id=1 corresponde a "Cambio de Turno Sencillo" (CT)
                        window.location.href = `/solicitudes/cambio-turno/solicitar/1/?fecha_solicitud=${fechaPago}`;
                    }
                });
                return;
            }
            
            // Verificar si el compañero receptor ya tiene doblada en la fecha de cesión
            if (data.code === 'doblada_receptor_existente') {
                Swal.fire({
                    icon: 'error',
                    title: 'Compañero no disponible',
                    html: `
                        <div class="text-left">
                            <p><strong>No se puede crear la solicitud con este compañero.</strong></p>
                            <p class="mt-2">
                                ${data.message || 'El compañero seleccionado ya tiene una doblada (AM+PM) en la fecha de cesión y no puede cubrirte.'}
                            </p>
                            <p class="mt-3"><strong>¿Qué debes hacer?</strong></p>
                            <ul class="text-left mt-2">
                                <li>Mantendremos la fecha de cesión seleccionada.</li>
                                <li>Por favor, elige <strong>otro compañero disponible</strong> para esa fecha.</li>
                            </ul>
                        </div>
                    `,
                    confirmButtonText: 'Entendido',
                    confirmButtonColor: '#d33',
                    width: '600px'
                }).then(() => {
                    // Opcional: deseleccionar al compañero inválido para forzar que el usuario elija otro
                    if (empleadoReceptorSelect) {
                        empleadoReceptorSelect.value = '';
                    }
                });
                return;
            }
            
            // Verificar si es error de doblada existente en fecha de pago
            if (data.code === 'doblada_existente') {
                const fechaConflicto = data.fecha_conflicto || 'desconocida';
                const jornadaAfectada = data.jornada_afectada || '';
                
                Swal.fire({
                    icon: 'error',
                    title: 'Fecha de Pago No Disponible',
                    html: `
                        <div class="text-left">
                            <p><strong>No se puede crear la solicitud</strong></p>
                            <p class="mt-2">${data.message || 'Ya tienes una doblada en la fecha de pago seleccionada.'}</p>
                            <p class="mt-3"><strong>Detalles:</strong></p>
                            <ul class="text-left mt-2">
                                <li>Fecha conflictiva: <strong>${fechaConflicto}</strong></li>
                                <li>Jornada afectada: <strong>${jornadaAfectada}</strong></li>
                                <li>Ya tienes una <strong>doblada (AM + PM)</strong> programada para esta fecha</li>
                            </ul>
                            <p class="mt-3"><strong>Solución:</strong></p>
                            <p class="mt-2">Elige otra fecha de pago que no tenga doblada, o cancela/modifica la doblada existente primero.</p>
                        </div>
                    `,
                    confirmButtonText: 'Entendido',
                    confirmButtonColor: '#d33',
                    width: '600px'
                });
                return;
            }
            
            if (data.success) {
                // Verificar si es cesión total (2 solicitudes)
                if (data.es_cesion_total) {
                    Swal.fire({
                        icon: 'success',
                        title: 'Solicitudes Enviadas',
                        html: `
                            <p>${data.message || 'Tus solicitudes de cesión total han sido enviadas correctamente.'}</p>
                            <p class="mt-2"><strong>Se han creado 2 solicitudes independientes:</strong></p>
                            <ul class="text-left mt-2">
                                <li>Solicitud AM (ID: ${data.solicitud_am_id})</li>
                                <li>Solicitud PM (ID: ${data.solicitud_pm_id})</li>
                            </ul>
                        `,
                        confirmButtonText: 'OK'
                    }).then(() => {
                        window.location.href = '/solicitudes/mis-solicitudes/';
                    });
                } else {
                    // Éxito normal (cesión parcial)
                    Swal.fire({
                        icon: 'success',
                        title: 'Solicitud Enviada',
                        text: data.message || 'Tu solicitud de doblada ha sido enviada correctamente.',
                        confirmButtonText: 'OK'
                    }).then(() => {
                        window.location.href = '/solicitudes/mis-solicitudes/';
                    });
                }
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: data.message || 'Error al enviar la solicitud'
                });
            }
        })
        .catch(error => {
            console.error('Error enviando solicitud:', error);
            let mensajeError = 'Error al enviar la solicitud. Por favor, intenta nuevamente.';
            
            // Si el error es un objeto (del throw que hicimos arriba)
            if (typeof error === 'object' && error !== null) {
                // Prioridad: error > message > statusText
                mensajeError = error.error || error.message || error.statusText || mensajeError;
                
                // Si tiene código especial, manejarlo
                if (error.code === 'requiere_cambio_turno_previo') {
                    // Este caso ya se maneja arriba, pero por si acaso
                    return;
                }
            } else if (typeof error === 'string') {
                mensajeError = error;
            } else if (error.message) {
                // Intentar parsear si viene como string JSON
                try {
                    const errorData = JSON.parse(error.message);
                    mensajeError = errorData.error || errorData.message || mensajeError;
                } catch (e) {
                    mensajeError = error.message;
                }
            }
            
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: mensajeError,
                width: '600px'
            });
        });
    }
    
    /**
     * Manejar envío del formulario
     */
    form.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Verificar si es cesión total ANTES de validar
        const esCesionTotal = document.querySelector('input[name="tipo_cesion_opcion"]:checked')?.value === 'total';
        
        // Guardar estado de 'required' para restaurar después
        const camposARestaurar = [];
        
        // REMOVER temporalmente atributo 'required' de campos que no corresponden
        // para que el validador genérico no los valide
        if (esCesionTotal) {
            // Cesión Total: remover 'required' de campos de cesión parcial
            if (empleadoReceptorSelect && empleadoReceptorSelect.hasAttribute('required')) {
                empleadoReceptorSelect.removeAttribute('required');
                camposARestaurar.push({element: empleadoReceptorSelect, attr: 'required'});
            }
            if (fechaPagoInput && fechaPagoInput.hasAttribute('required')) {
                fechaPagoInput.removeAttribute('required');
                camposARestaurar.push({element: fechaPagoInput, attr: 'required'});
            }
            jornadaCedidaRadios.forEach(radio => {
                if (radio.hasAttribute('required')) {
                    radio.removeAttribute('required');
                    camposARestaurar.push({element: radio, attr: 'required'});
                }
            });
        } else {
            // Cesión Parcial: remover 'required' de campos de cesión total
            if (empleadoReceptorAM && empleadoReceptorAM.hasAttribute('required')) {
                empleadoReceptorAM.removeAttribute('required');
                camposARestaurar.push({element: empleadoReceptorAM, attr: 'required'});
            }
            if (empleadoReceptorPM && empleadoReceptorPM.hasAttribute('required')) {
                empleadoReceptorPM.removeAttribute('required');
                camposARestaurar.push({element: empleadoReceptorPM, attr: 'required'});
            }
            if (fechaPagoAM && fechaPagoAM.hasAttribute('required')) {
                fechaPagoAM.removeAttribute('required');
                camposARestaurar.push({element: fechaPagoAM, attr: 'required'});
            }
            if (fechaPagoPM && fechaPagoPM.hasAttribute('required')) {
                fechaPagoPM.removeAttribute('required');
                camposARestaurar.push({element: fechaPagoPM, attr: 'required'});
            }
        }
        
        // VALIDACIÓN PERSONALIZADA PARA DOBLADA
        // No usar validador genérico porque no distingue entre cesión parcial/total
        const erroresValidacion = [];
        
        // Comentario obligatorio
        const comentariosInput = document.getElementById('comentarios');
        const comentarioValor = comentariosInput ? comentariosInput.value.trim() : '';
        if (!comentarioValor) {
            erroresValidacion.push('El comentario es obligatorio. Explica el motivo de la doblada.');
        }
        
        // Validar fecha de cesión (común para ambos modos)
        const fechaCesionInput = form.querySelector('#fecha_cesion');
        if (!fechaCesionInput || !fechaCesionInput.value) {
            erroresValidacion.push('Fecha de cesión es requerida');
        }
        
        // Validar según el modo de cesión
        if (esCesionTotal) {
            // VALIDACIÓN CESIÓN TOTAL
            if (!empleadoReceptorAM || !empleadoReceptorAM.value) {
                erroresValidacion.push('Compañero para AM (Mañana) es requerido');
            }
            if (!empleadoReceptorPM || !empleadoReceptorPM.value) {
                erroresValidacion.push('Compañero para PM (Tarde) es requerido');
            }
            if (!fechaPagoAM || !fechaPagoAM.value) {
                erroresValidacion.push('Fecha de pago para AM es requerida');
            }
            if (!fechaPagoPM || !fechaPagoPM.value) {
                erroresValidacion.push('Fecha de pago para PM es requerida');
            }
        } else {
            // VALIDACIÓN CESIÓN PARCIAL
            if (!empleadoReceptorSelect || !empleadoReceptorSelect.value) {
                erroresValidacion.push('Compañero que te cubrirá es requerido');
            }
            if (!fechaPagoInput || !fechaPagoInput.value) {
                erroresValidacion.push('Fecha de pago es requerida');
            }

            // Si la fecha de pago es sábado y se muestra el selector (no te corresponde trabajar ese sábado por alternancia), exigir selección
            if (fechaPagoInput && fechaPagoInput.value && esSabado(fechaPagoInput.value) &&
                opcionesPagoSabado && opcionesPagoSabado.style.display !== 'none') {
                const jornadaPagoSabadoSel = form.querySelector('input[name="jornada_pago_sabado"]:checked');
                if (!jornadaPagoSabadoSel) {
                    erroresValidacion.push('Debes seleccionar qué jornada trabajarás el sábado (AM o PM)');
                }
            }
            
            // Validar jornada a ceder si hay doblada existente
            if (tieneDobladaExistente) {
                const jornadaCedida = form.querySelector('input[name="jornada_cedida"]:checked');
                if (!jornadaCedida) {
                    erroresValidacion.push('Debe seleccionar la jornada a ceder (AM o PM)');
                }
            }
        }
        
        // RESTAURAR atributos 'required' que removimos temporalmente
        camposARestaurar.forEach(({element, attr}) => {
            element.setAttribute(attr, '');
        });
        
        // Mostrar errores si hay
        if (erroresValidacion.length > 0) {
            if (window.ValidadoresSolicitudes && window.ValidadoresSolicitudes.mostrarErroresValidacion) {
                window.ValidadoresSolicitudes.mostrarErroresValidacion(erroresValidacion);
            } else {
                // Fallback manual si el validador no está disponible
                Swal.fire({
                    icon: 'warning',
                    title: 'Campos requeridos',
                    html: '<ul style="text-align: left;">' + 
                          erroresValidacion.map(e => `<li>${e}</li>`).join('') + 
                          '</ul>',
                    confirmButtonText: 'Entendido'
                });
            }
            return;
        }
        
        if (esCesionTotal) {
            // Validaciones para cesión total
            if (!empleadoReceptorAM || !empleadoReceptorAM.value) {
                Swal.fire({
                    icon: 'error',
                    title: 'Campo Requerido',
                    text: 'Debes seleccionar un compañero para la jornada AM.'
                });
                return;
            }
            if (!empleadoReceptorPM || !empleadoReceptorPM.value) {
                Swal.fire({
                    icon: 'error',
                    title: 'Campo Requerido',
                    text: 'Debes seleccionar un compañero para la jornada PM.'
                });
                return;
            }
            if (!fechaPagoAM || !fechaPagoAM.value) {
                Swal.fire({
                    icon: 'error',
                    title: 'Campo Requerido',
                    text: 'Debes seleccionar una fecha de pago para la jornada AM.'
                });
                return;
            }
            if (!fechaPagoPM || !fechaPagoPM.value) {
                Swal.fire({
                    icon: 'error',
                    title: 'Campo Requerido',
                    text: 'Debes seleccionar una fecha de pago para la jornada PM.'
                });
                return;
            }
            
            // Validar que fechas de pago sean posteriores a fecha de creación
            if (fechaPagoAM.value <= fechaCreacionSolicitud) {
                Swal.fire({
                    icon: 'error',
                    title: 'Fecha Inválida',
                    text: `La fecha de pago para AM debe ser posterior a ${fechaCreacionSolicitud}.`
                });
                return;
            }
            if (fechaPagoPM.value <= fechaCreacionSolicitud) {
                Swal.fire({
                    icon: 'error',
                    title: 'Fecha Inválida',
                    text: `La fecha de pago para PM debe ser posterior a ${fechaCreacionSolicitud}.`
                });
                return;
            }
            // Validar que ninguna fecha de pago sea igual a la fecha de cesión (total)
            const fechaCesionVal = fechaCesionInput ? fechaCesionInput.value : null;
            if (fechaCesionVal) {
                if (fechaPagoAM.value === fechaCesionVal) {
                    Swal.fire({
                        icon: 'error',
                        title: 'Fecha Inválida',
                        text: `La fecha de pago para AM (${fechaPagoAM.value}) no puede ser la misma que la fecha de cesión. Si cedes tu jornada ese día, no puedes trabajar y descansar al mismo tiempo.`
                    });
                    return;
                }
                if (fechaPagoPM.value === fechaCesionVal) {
                    Swal.fire({
                        icon: 'error',
                        title: 'Fecha Inválida',
                        text: `La fecha de pago para PM (${fechaPagoPM.value}) no puede ser la misma que la fecha de cesión. Si cedes tu jornada ese día, no puedes trabajar y descansar al mismo tiempo.`
                    });
                    return;
                }
            }
            // Caso A: fecha_pago debe estar en el mismo mes que fecha_cesion
            const mesCesionAM = fechaCesionInput && fechaCesionInput.value ? fechaCesionInput.value.slice(0, 7) : null;
            if (mesCesionAM && fechaPagoAM.value && fechaPagoAM.value.slice(0, 7) !== mesCesionAM) {
                Swal.fire({
                    icon: 'error',
                    title: 'Fecha de pago inválida',
                    text: `La fecha de pago AM (${fechaPagoAM.value}) debe estar en el mismo mes que la fecha de cesión. Ambas deben pertenecer al mes ${mesCesionAM}.`
                });
                return;
            }
            if (mesCesionAM && fechaPagoPM.value && fechaPagoPM.value.slice(0, 7) !== mesCesionAM) {
                Swal.fire({
                    icon: 'error',
                    title: 'Fecha de pago inválida',
                    text: `La fecha de pago PM (${fechaPagoPM.value}) debe estar en el mismo mes que la fecha de cesión. Ambas deben pertenecer al mes ${mesCesionAM}.`
                });
                return;
            }
        } else {
            // Validación adicional: fecha de pago posterior a fecha de creación (cesión parcial)
            const fechaPago = fechaPagoInput.value;
            if (fechaPago <= fechaCreacionSolicitud) {
                Swal.fire({
                    icon: 'error',
                    title: 'Fecha Inválida',
                    text: `La fecha de pago debe ser posterior a ${fechaCreacionSolicitud}.`
                });
                return;
            }
            // Validar que fecha de pago no sea igual a fecha de cesión (cesión parcial)
            const fechaCesionVal = fechaCesionInput ? fechaCesionInput.value : null;
            if (fechaCesionVal && fechaPago === fechaCesionVal) {
                Swal.fire({
                    icon: 'error',
                    title: 'Fecha Inválida',
                    text: `La fecha de pago (${fechaPago}) no puede ser la misma que la fecha de cesión. Si cedes tu jornada ese día, no puedes trabajar y descansar al mismo tiempo.`
                });
                return;
            }
            // Caso A: fecha_pago debe estar en el mismo mes que fecha_cesion
            const mesCesion = fechaCesionInput && fechaCesionInput.value ? fechaCesionInput.value.slice(0, 7) : null;
            if (mesCesion && fechaPago && fechaPago.slice(0, 7) !== mesCesion) {
                Swal.fire({
                    icon: 'error',
                    title: 'Fecha de pago inválida',
                    text: `La fecha de pago (${fechaPago}) debe estar en el mismo mes que la fecha de cesión. Ambas deben pertenecer al mes ${mesCesion}.`
                });
                return;
            }
        }
        
        // Validación frontend de días especiales (domingo y mantenimiento bloqueados; festivos permitidos con regla mismo mes)
        const fechaCesion = fechaCesionInput.value;
        const erroresDiasEspeciales = [];
        
        if (fechaCesion) {
            if (esDomingo(fechaCesion)) {
                erroresDiasEspeciales.push(`La fecha de cesión (${formatearFecha(fechaCesion)}) no puede ser domingo.`);
            }
            
            if (window.DatepickerFestivos) {
                Promise.all([
                    window.DatepickerFestivos.cargarDiasFestivos(),
                    window.DatepickerFestivos.cargarDiasMantenimiento()
                ]).then(([festivosMap, mantenimientoMap]) => {
                    // Mantenimiento nunca permitido
                    if (mantenimientoMap.has(fechaCesion)) {
                        erroresDiasEspeciales.push(`La fecha de cesión (${formatearFecha(fechaCesion)}) es un día de mantenimiento: ${mantenimientoMap.get(fechaCesion)}.`);
                    }
                    
                    const cesionEsFestivo = festivosMap.has(fechaCesion);
                    const mesCesion = fechaCesion ? fechaCesion.slice(0, 7) : ''; // YYYY-MM
                    
                    if (esCesionTotal) {
                        if (fechaPagoAM && fechaPagoAM.value) {
                            const fechaPagoAMVal = fechaPagoAM.value;
                            if (esDomingo(fechaPagoAMVal)) {
                                erroresDiasEspeciales.push(`La fecha de pago para AM (${formatearFecha(fechaPagoAMVal)}) no puede ser domingo.`);
                            }
                            if (mantenimientoMap.has(fechaPagoAMVal)) {
                                erroresDiasEspeciales.push(`La fecha de pago para AM (${formatearFecha(fechaPagoAMVal)}) es un día de mantenimiento: ${mantenimientoMap.get(fechaPagoAMVal)}.`);
                            }
                            if (cesionEsFestivo && !festivosMap.has(fechaPagoAMVal)) {
                                erroresDiasEspeciales.push('Si la cesión es en día festivo, la fecha de pago para AM debe ser otro festivo del mismo mes.');
                            } else if (festivosMap.has(fechaPagoAMVal) && !cesionEsFestivo) {
                                erroresDiasEspeciales.push('Si el pago es en día festivo, la fecha de cesión debe ser otro festivo del mismo mes.');
                            } else if (cesionEsFestivo && festivosMap.has(fechaPagoAMVal) && fechaPagoAMVal.slice(0, 7) !== mesCesion) {
                                erroresDiasEspeciales.push('Cesión y pago en festivos deben ser del mismo mes.');
                            }
                        }
                        if (fechaPagoPM && fechaPagoPM.value) {
                            const fechaPagoPMVal = fechaPagoPM.value;
                            if (esDomingo(fechaPagoPMVal)) {
                                erroresDiasEspeciales.push(`La fecha de pago para PM (${formatearFecha(fechaPagoPMVal)}) no puede ser domingo.`);
                            }
                            if (mantenimientoMap.has(fechaPagoPMVal)) {
                                erroresDiasEspeciales.push(`La fecha de pago para PM (${formatearFecha(fechaPagoPMVal)}) es un día de mantenimiento: ${mantenimientoMap.get(fechaPagoPMVal)}.`);
                            }
                            if (cesionEsFestivo && !festivosMap.has(fechaPagoPMVal)) {
                                erroresDiasEspeciales.push('Si la cesión es en día festivo, la fecha de pago para PM debe ser otro festivo del mismo mes.');
                            } else if (festivosMap.has(fechaPagoPMVal) && !cesionEsFestivo) {
                                erroresDiasEspeciales.push('Si el pago es en día festivo, la fecha de cesión debe ser otro festivo del mismo mes.');
                            } else if (cesionEsFestivo && festivosMap.has(fechaPagoPMVal) && fechaPagoPMVal.slice(0, 7) !== mesCesion) {
                                erroresDiasEspeciales.push('Cesión y pago en festivos deben ser del mismo mes.');
                            }
                        }
                    } else {
                        const fechaPago = fechaPagoInput.value;
                        if (fechaPago) {
                            if (esDomingo(fechaPago)) {
                                erroresDiasEspeciales.push(`La fecha de pago (${formatearFecha(fechaPago)}) no puede ser domingo.`);
                            }
                            if (mantenimientoMap.has(fechaPago)) {
                                erroresDiasEspeciales.push(`La fecha de pago (${formatearFecha(fechaPago)}) es un día de mantenimiento: ${mantenimientoMap.get(fechaPago)}.`);
                            }
                            const pagoEsFestivo = festivosMap.has(fechaPago);
                            if (cesionEsFestivo && !pagoEsFestivo) {
                                erroresDiasEspeciales.push('Si la cesión es en día festivo, la fecha de pago debe ser otro festivo del mismo mes.');
                            } else if (pagoEsFestivo && !cesionEsFestivo) {
                                erroresDiasEspeciales.push('Si el pago es en día festivo, la fecha de cesión debe ser otro festivo del mismo mes.');
                            } else if (cesionEsFestivo && pagoEsFestivo && fechaPago.slice(0, 7) !== mesCesion) {
                                erroresDiasEspeciales.push('Cesión y pago en festivos deben ser del mismo mes.');
                            }
                        }
                    }
                    
                    if (erroresDiasEspeciales.length > 0) {
                        Swal.fire({
                            icon: 'error',
                            title: 'Fechas Inválidas',
                            html: `<p>No se puede realizar la doblada:</p><ul class="text-left mt-2">${erroresDiasEspeciales.map(e => `<li>${e}</li>`).join('')}</ul>`,
                            confirmButtonText: 'OK'
                        });
                        return;
                    }
                    
                    enviarFormulario();
                }).catch(error => {
                    console.error('Error validando días especiales:', error);
                    enviarFormulario();
                });
            } else {
                enviarFormulario();
            }
        } else {
            enviarFormulario();
        }
    });
    
    // Inicializar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            inicializarDatepickerCesion();
            inicializarDatepickerPago();
        });
    } else {
        inicializarDatepickerCesion();
        inicializarDatepickerPago();
    }
})();

