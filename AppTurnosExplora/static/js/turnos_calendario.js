/**
 * Calendario de Turnos para Supervisores
 * Permite seleccionar una fecha y visualizar empleados AM y PM
 */

// Esperar a que FullCalendar y el locale estén cargados
document.addEventListener('DOMContentLoaded', function() {
    // Esperar un momento para asegurar que el locale se haya cargado
    setTimeout(function() {
        inicializarAplicacion();
    }, 100);
});

function inicializarAplicacion() {
    let calendar;
    let fechaSeleccionada = null;
    
    // Inicializar calendario
    inicializarCalendario();
    
    // Cargar turnos para la fecha actual al inicio
    const hoy = new Date();
    const fechaHoy = formatearFechaISO(hoy);
    fechaSeleccionada = fechaHoy;
    actualizarFechaSeleccionada(hoy);
    cargarTurnosPorFecha(fechaHoy);
    
    /**
     * Inicializa FullCalendar con configuración personalizada
     */
    function inicializarCalendario() {
        const calendarEl = document.getElementById('calendar');
        if (!calendarEl) return;
        
        calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'dayGridMonth',
            locale: 'es',
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: ''
            },
            firstDay: 1, // Lunes como primer día
            selectable: true,
            height: 'auto',
            dateClick: function(info) {
                // Manejar clic en fecha
                const fecha = info.dateStr;
                fechaSeleccionada = fecha;
                actualizarFechaSeleccionada(info.date);
                cargarTurnosPorFecha(fecha);
                
                // Remover clase de selección anterior
                document.querySelectorAll('.fc-day-selected').forEach(el => {
                    el.classList.remove('fc-day-selected');
                });
                
                // Agregar clase de selección a la fecha clickeada
                info.dayEl.classList.add('fc-day-selected');
            },
            datesSet: function(info) {
                // Cuando cambia el mes/año, mantener la selección si existe
                if (fechaSeleccionada) {
                    const fechaObj = new Date(fechaSeleccionada);
                    const inicioVista = info.start;
                    const finVista = info.end;
                    
                    // Si la fecha seleccionada está en el rango visible, resaltarla
                    if (fechaObj >= inicioVista && fechaObj < finVista) {
                        setTimeout(() => {
                            const dayEl = document.querySelector(`[data-date="${fechaSeleccionada}"]`);
                            if (dayEl) {
                                dayEl.classList.add('fc-day-selected');
                            }
                        }, 100);
                    }
                }
            },
            dayCellDidMount: function(info) {
                // Agregar clase personalizada para estilos
                if (info.dateStr === fechaSeleccionada) {
                    info.el.classList.add('fc-day-selected');
                }
            }
        });
        
        calendar.render();
    }
    
    /**
     * Carga los turnos para una fecha específica desde la API
     * @param {string} fecha - Fecha en formato YYYY-MM-DD
     */
    function cargarTurnosPorFecha(fecha) {
        if (!fecha) return;
        
        // Mostrar estado de carga
        mostrarEstadoCarga();
        
        // Llamar a la API
        fetch(`/turnos/api/turnos-por-dia/?fecha=${fecha}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Error HTTP: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                mostrarEmpleados(data.am || [], data.pm || []);
            })
            .catch(error => {
                console.error('Error al cargar turnos:', error);
                mostrarError('Error al cargar los turnos. Por favor, intente nuevamente.');
            });
    }
    
    /**
     * Muestra los empleados en las listas AM y PM
     * @param {Array} am - Lista de empleados AM
     * @param {Array} pm - Lista de empleados PM
     */
    function mostrarEmpleados(am, pm) {
        const listaAM = document.getElementById('lista-am');
        const listaPM = document.getElementById('lista-pm');
        
        if (!listaAM || !listaPM) return;
        
        // Limpiar listas
        listaAM.innerHTML = '';
        listaPM.innerHTML = '';
        
        // Renderizar empleados AM
        if (am.length === 0) {
            listaAM.innerHTML = '<li class="list-group-item text-muted text-center"><i class="fas fa-info-circle"></i> No hay empleados asignados</li>';
        } else {
            am.forEach(empleado => {
                const item = crearItemEmpleado(empleado, 'AM');
                listaAM.appendChild(item);
            });
        }
        
        // Renderizar empleados PM
        if (pm.length === 0) {
            listaPM.innerHTML = '<li class="list-group-item text-muted text-center"><i class="fas fa-info-circle"></i> No hay empleados asignados</li>';
        } else {
            pm.forEach(empleado => {
                const item = crearItemEmpleado(empleado, 'PM');
                listaPM.appendChild(item);
            });
        }
        
        // Actualizar contadores
        actualizarContadores(am.length, pm.length);
    }
    
    /**
     * Crea un elemento de lista para un empleado
     * @param {Object} empleado - Objeto con id, nombre, apellido, tipo
     * @param {string} jornada - 'AM' o 'PM'
     * @returns {HTMLElement} Elemento de lista
     */
    function crearItemEmpleado(empleado, jornada) {
        const li = document.createElement('li');
        li.className = 'list-group-item empleado-item';
        
        const tipo = empleado.tipo || 'oficial';
        const tipoClass = tipo === 'cambio' ? 'warning' : 'success';
        const tipoTexto = tipo === 'cambio' ? 'Cambio' : 'Oficial';
        const icono = tipo === 'cambio' ? 'exchange-alt' : 'check-circle';
        
        li.innerHTML = `
            <div class="d-flex justify-content-between align-items-center">
                <div class="d-flex align-items-center">
                    <div class="avatar-empleado ${jornada.toLowerCase()}">
                        ${empleado.nombre.charAt(0).toUpperCase()}${empleado.apellido.charAt(0).toUpperCase()}
                    </div>
                    <div class="ml-3">
                        <strong>${empleado.nombre} ${empleado.apellido}</strong>
                    </div>
                </div>
                <span class="badge badge-${tipoClass} badge-pill">
                    <i class="fas fa-${icono}"></i> ${tipoTexto}
                </span>
            </div>
        `;
        
        return li;
    }
    
    /**
     * Actualiza los contadores de empleados
     * @param {number} totalAM - Total de empleados AM
     * @param {number} totalPM - Total de empleados PM
     */
    function actualizarContadores(totalAM, totalPM) {
        const headerAM = document.querySelector('.am-col h5');
        const headerPM = document.querySelector('.pm-col h5');
        
        if (headerAM) {
            const badge = headerAM.querySelector('.badge');
            if (badge) {
                badge.textContent = totalAM;
            } else {
                headerAM.innerHTML = `<i class="fas fa-sun"></i> Exploradores AM <span class="badge badge-primary">${totalAM}</span>`;
            }
        }
        if (headerPM) {
            const badge = headerPM.querySelector('.badge');
            if (badge) {
                badge.textContent = totalPM;
            } else {
                headerPM.innerHTML = `<i class="fas fa-moon"></i> Exploradores PM <span class="badge badge-warning">${totalPM}</span>`;
            }
        }
    }
    
    /**
     * Muestra el estado de carga
     */
    function mostrarEstadoCarga() {
        const listaAM = document.getElementById('lista-am');
        const listaPM = document.getElementById('lista-pm');
        
        if (listaAM) {
            listaAM.innerHTML = '<li class="list-group-item text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</li>';
        }
        if (listaPM) {
            listaPM.innerHTML = '<li class="list-group-item text-center"><i class="fas fa-spinner fa-spin"></i> Cargando...</li>';
        }
    }
    
    /**
     * Muestra un mensaje de error
     * @param {string} mensaje - Mensaje de error
     */
    function mostrarError(mensaje) {
        const listaAM = document.getElementById('lista-am');
        const listaPM = document.getElementById('lista-pm');
        
        const errorHTML = `<li class="list-group-item text-danger text-center"><i class="fas fa-exclamation-triangle"></i> ${mensaje}</li>`;
        
        if (listaAM) listaAM.innerHTML = errorHTML;
        if (listaPM) listaPM.innerHTML = errorHTML;
    }
    
    /**
     * Actualiza el texto de la fecha seleccionada
     * @param {Date} fecha - Objeto Date
     */
    function actualizarFechaSeleccionada(fecha) {
        const fechaSpan = document.getElementById('fecha-seleccionada');
        if (fechaSpan) {
            fechaSpan.textContent = formatearFechaEspañol(fecha);
        }
    }
    
    /**
     * Formatea una fecha a formato ISO (YYYY-MM-DD)
     * @param {Date} fecha - Objeto Date
     * @returns {string} Fecha en formato YYYY-MM-DD
     */
    function formatearFechaISO(fecha) {
        const año = fecha.getFullYear();
        const mes = String(fecha.getMonth() + 1).padStart(2, '0');
        const dia = String(fecha.getDate()).padStart(2, '0');
        return `${año}-${mes}-${dia}`;
    }
    
    /**
     * Formatea una fecha a formato español legible
     * @param {Date} fecha - Objeto Date
     * @returns {string} Fecha formateada en español
     */
    function formatearFechaEspañol(fecha) {
        const opciones = { 
            weekday: 'long', 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric' 
        };
        return fecha.toLocaleDateString('es-CO', opciones);
    }
}

