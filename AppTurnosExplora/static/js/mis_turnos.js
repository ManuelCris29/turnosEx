// JavaScript para Mis Turnos - Responsive y FullCalendar
var turnosMes = {};
var fechaSeleccionada = null;

function cargarDatos(anio, mes) {

    console.log(`Cargando datos para ${anio}-${mes}`);

    fetch(`/turnos/api/mis-turnos-por-mes/?mes=${mes}&anio=${anio}`)
        .then(response => response.json())
        .then(data => {
            turnosMes = data;
            console.log(turnosMes);

            // Refrescar detalles si ya hay una fecha seleccionada
            if (fechaSeleccionada && turnosMes[fechaSeleccionada]) {
                mostrarDetallesDia(fechaSeleccionada);
            }

            // Forzar recalculo del layout del calendario tras la carga
            setTimeout(function() { if (window.calendar && typeof window.calendar.updateSize === 'function') { window.calendar.updateSize(); } }, 0);
            
            // Aplicar estilos a días con cambios después de cargar datos
            setTimeout(function() { 
                aplicarEstilosCambios();
            }, 100);

        })
        .catch(error => {
            console.error('Error al cargar datos:', error);
        });

}

// Aplica estilos distintivos a días con cambios de turno
function aplicarEstilosCambios() {
    console.log("Aplicando estilos de cambios...");
    
    // Limpiar estilos anteriores
    document.querySelectorAll('.dia-con-cambio').forEach(el => {
        el.classList.remove('dia-con-cambio');
        const icon = el.querySelector('.cambio-turno-icon');
        if (icon) icon.remove();
    });
    
    // Aplicar estilos a días con cambios
    for (const [fechaStr, turnoInfo] of Object.entries(turnosMes)) {
        if (turnoInfo && turnoInfo.es_cambio) {
            console.log(`Aplicando estilo de cambio para ${fechaStr}`);
            
            // Buscar la celda del día en el calendario
            const cellSelector = `[data-date="${fechaStr}"]`;
            const cellElement = document.querySelector(cellSelector);
            
            if (cellElement) {
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
        }
    }
}

// Muestra los detalles del día seleccionado en los contenedores del template
function mostrarDetallesDia(fechaStr) {
    const info = turnosMes[fechaStr];

    const fechaSpan = document.getElementById('fecha-seleccionada');
    const jornadaDiv = document.getElementById('mi-jornada');
    const salaDiv = document.getElementById('mi-sala');

    if (fechaSpan) {
        const [y, m, d] = fechaStr.split('-');
        const meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
        fechaSpan.textContent = `${parseInt(d)} de ${meses[parseInt(m)-1]} de ${y}`;
    }

    if (jornadaDiv && salaDiv) {
        if (info) {
            jornadaDiv.innerHTML = `<span class="jornada-value ${info.jornada.toLowerCase()}">${info.jornada}</span>`;
            salaDiv.innerHTML = info.sala ? `<span class="sala-value">${info.sala}</span>` : `<span class="detail-content por-asignar">Por asignar</span>`;
        } else {
            jornadaDiv.innerHTML = `<span class="detail-content por-asignar">Sin datos</span>`;
            salaDiv.innerHTML = `<span class="detail-content por-asignar">Por asignar</span>`;
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
    window.addEventListener('resize', function() {
        setTimeout(adjustForSmallScreens, 100);
        // Forzar a FullCalendar a recalcular tamaños cuando cambie el viewport (p.ej., al abrir DevTools)
        setTimeout(function() { if (window.calendar && typeof window.calendar.updateSize === 'function') { window.calendar.updateSize(); } }, 0);
    });

    // Inicializar FullCalendar
    var calendarEl = document.getElementById('calendar');
    var calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'es',
        height: 500,
        initialDate: new Date(),

        datesSet: function(info) {
            // Cuando cambia el mes, cargar datos del nuevo mes
            const fechaCentro = calendar.getDate( );  // mes enfocado
            const anio = fechaCentro.getFullYear();
            const mes = fechaCentro.getMonth() + 1;
            cargarDatos(anio, mes);
        },
        dateClick: function(info) {
            // Cuando hace click en un día, mostrar detalles
            fechaSeleccionada = info.dateStr;
            mostrarDetallesDia(info.dateStr);
        },

    });
    calendar.render();

    //Recalcula el cambio el tamaño real del contenedor
    const ro = new ResizeObserver(()=>{
        if (window.calendar && typeof window.calendar.updateSize === 'function') { 
            window.calendar.updateSize();
        }
});
ro.observe(calendarEl);

    // Cargar datos del mes actual al inicializar
    const fechaActual = new Date();
    const anio = fechaActual.getFullYear();
    const mes = fechaActual.getMonth() + 1;
    cargarDatos(anio, mes);

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
        calendar.gotoDate(`${anio}-${mes}-01`);
    }

    // Hacer funciones disponibles globalmente
    window.calendar = calendar;
    window.cambiarMes = cambiarMes;
});
