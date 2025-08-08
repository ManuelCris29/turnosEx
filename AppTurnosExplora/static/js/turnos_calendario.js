document.addEventListener('DOMContentLoaded', function() {
    var calendarEl = document.getElementById('calendar');
    var turnosPorMes = {};
    var fechaSeleccionada = null;
    var calendar = new FullCalendar.Calendar(calendarEl, {
        initialView: 'dayGridMonth',
        locale: 'es',
        height: 500,
        initialDate: new Date().toISOString().slice(0, 10),
        datesSet: function(info) {
            cargarTurnosPorMes(info.startStr, info.endStr);
        },
        dateClick: function(info) {
            const fecha = info.dateStr.slice(0, 10);
            seleccionarDia(fecha);
        },
        dayCellDidMount: function(arg) {
            // Resalta el día actual
            const today = new Date().toISOString().slice(0, 10);
            if (arg.date.toISOString().slice(0, 10) === today) {
                arg.el.classList.add('fc-day-today-custom');
            }
        }
    });
    calendar.render();

    function cargarTurnosPorMes(fechaInicio, fechaFin) {
        fetch(`/turnos/api/turnos-por-mes/?fecha_inicio=${fechaInicio}&fecha_fin=${fechaFin}`)
            .then(response => response.json())
            .then(data => {
                turnosPorMes = data;
                // Selecciona el día actual si está en el rango, si no el primer día
                const today = new Date().toISOString().slice(0, 10);
                if (turnosPorMes[today]) {
                    seleccionarDia(today);
                } else {
                    const primerDia = Object.keys(turnosPorMes)[0];
                    seleccionarDia(primerDia);
                }
            });
    }

    function seleccionarDia(fecha) {
        fechaSeleccionada = fecha;
        mostrarTurnosDelDia(fecha);
        resaltarDiaEnCalendario(fecha);
        mostrarFechaSeleccionada(fecha);
    }

    function mostrarTurnosDelDia(fecha) {
        const fechaKey = fecha.slice(0, 10);
        const data = turnosPorMes[fechaKey] || {am: [], pm: []};
        renderLista('lista-am', data.am);
        renderLista('lista-pm', data.pm);
    }

    function mostrarFechaSeleccionada(fecha) {
        const span = document.getElementById('fecha-seleccionada');
        if (span) {
            // Formato amigable sin problemas de zona horaria
            const [anio, mes, dia] = fecha.split('-');
            const meses = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
            span.textContent = `${parseInt(dia)} de ${meses[parseInt(mes)-1]} de ${anio}`;
        }
    }

    function resaltarDiaEnCalendario(fecha) {
        // Quitar resaltado anterior
        document.querySelectorAll('.fc-daygrid-day.fc-day-selected').forEach(el => {
            el.classList.remove('fc-day-selected');
        });
        // Buscar el día y agregar clase
        const celdas = document.querySelectorAll('.fc-daygrid-day');
        celdas.forEach(celda => {
            if (celda.getAttribute('data-date') === fecha) {
                celda.classList.add('fc-day-selected');
            }
        });
    }

    function renderLista(elementId, lista) {
        const ul = document.getElementById(elementId);
        ul.innerHTML = '';
        if (lista.length === 0) {
            ul.innerHTML = '<li class="text-muted">Ningún explorador</li>';
            return;
        }
        lista.forEach(e => {
            let icono = e.tipo === 'cambio' ? '🔄' : '🟢';
            ul.innerHTML += `<li>${icono} ${e.nombre} ${e.apellido}</li>`;
        });
    }

    // Estilos para el día seleccionado y el día actual
    const style = document.createElement('style');
    style.innerHTML = `
        .fc-day-selected {
            background: #007bff !important;
            color: #fff !important;
            border-radius: 50%;
            width: 2em !important;
            height: 2em !important;
            margin: auto;
            padding: 0 !important;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .fc-day-today-custom {
            border: 2px solid #28a745 !important;
        }
    `;
    document.head.appendChild(style);
}); 