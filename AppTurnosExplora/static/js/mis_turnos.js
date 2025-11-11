// JavaScript para Mis Turnos - Responsive y FullCalendar
var turnosMes = {};
var fechaSeleccionada = null;

function cargarDatos(anio, mes) {

    console.log(`Cargando datos para ${anio}-${mes}`);

    fetch(`/turnos/api/mis-turnos-por-mes/?mes=${mes}&anio=${anio}`)
        .then(response => response.json())
        .then(data => {
            turnosMes = data;
            console.log('Datos cargados:', turnosMes);

            // Refrescar detalles si ya hay una fecha seleccionada
            if (fechaSeleccionada) {
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
            // Asegurar que el nombre de la clase coincida (am, pm, descanso)
            let claseJornada = jornadaLower;
            if (jornadaLower === 'descanso' || jornadaLower.includes('descanso')) {
                claseJornada = 'descanso';
            }
            
            // Construir HTML para la jornada
            let jornadaHTML = `<span class="jornada-value ${claseJornada}">${info.jornada}</span>`;
            
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
            const fechaStrInMes = Object.keys(turnosMes).find(f => {
                const fObj = new Date(f + 'T00:00:00');
                return fObj.getFullYear() === anio && (fObj.getMonth() + 1) === mes;
            });
            if (!fechaStrInMes) {
                console.log('Cargando datos para el mes:', mes, anio);
                cargarDatos(anio, mes);
            } else {
                console.log('Datos del mes ya están cargados, pero no hay información para esta fecha específica');
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
            
            if (!tieneDatosMes) {
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
