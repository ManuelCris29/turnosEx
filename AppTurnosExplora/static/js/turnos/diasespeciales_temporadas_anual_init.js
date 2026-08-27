document.addEventListener('DOMContentLoaded', function() {
    const cfg = window.TEMPORADAS_INIT || {};
    const anioSeleccionado = cfg.anio;
    const diasPorMes = cfg.diasPorMes || {};
    const url = cfg.url || '';

    for (let mes = 1; mes <= 12; mes++) {
        renderizarCalendarioMes(mes, anioSeleccionado, diasPorMes[mes] || []);
    }
    actualizarDiasSeleccionados();

    // Guardar reescribe el año entero (borra y vuelve a crear las temporadas), así que
    // sin ningún día tocado el botón queda apagado: ver `utils/guardado_atomico.js`.
    window.guardiaGuardadoAnual = window.guardadoAtomico({
        boton: document.getElementById('btn-guardar'),
        instantanea: obtenerDiasSeleccionados,
    });

    function navegarAnio(anio) {
        window.location.href = url + '?anio=' + anio;
    }

    document.getElementById('id_anio').addEventListener('change', function() {
        navegarAnio(this.value);
    });
    document.getElementById('btn-cargar-anio').addEventListener('click', function() {
        navegarAnio(document.getElementById('id_anio').value);
    });

    const btnAnioPersonalizado = document.getElementById('btn-anio-personalizado');
    const inputAnioPersonalizado = document.getElementById('anio-personalizado-input');
    if (btnAnioPersonalizado && inputAnioPersonalizado) {
        btnAnioPersonalizado.addEventListener('click', function() {
            const visible = inputAnioPersonalizado.style.display !== 'none';
            inputAnioPersonalizado.style.display = visible ? 'none' : 'block';
            if (!visible) inputAnioPersonalizado.focus();
        });
        function irAnioPersonalizado() {
            const anio = parseInt(inputAnioPersonalizado.value);
            const min = parseInt(inputAnioPersonalizado.min), max = parseInt(inputAnioPersonalizado.max);
            if (anio >= min && anio <= max) navegarAnio(anio);
            else if (inputAnioPersonalizado.value) { alert(`Ingrese un año entre ${min} y ${max}`); inputAnioPersonalizado.value = ''; }
        }
        inputAnioPersonalizado.addEventListener('keypress', e => { if (e.key === 'Enter') irAnioPersonalizado(); });
        inputAnioPersonalizado.addEventListener('blur', irAnioPersonalizado);
    }

    const form = document.getElementById('form-temporadas');
    const campoLimpiar = document.getElementById('id_limpiar_anio');

    form.addEventListener('submit', function(e) {
        const diasSeleccionados = obtenerDiasSeleccionados();
        const totalDias = Object.values(diasSeleccionados).reduce((sum, dias) => sum + dias.length, 0);
        // El envío con `limpiar_anio` lo dispara el botón de limpiar, que ya confirmó
        // con el usuario: aquí solo se deja pasar sin exigir días seleccionados.
        const esLimpieza = campoLimpiar && campoLimpiar.value === '1';

        if (!esLimpieza && !window.guardiaGuardadoAnual.sucio()) {
            e.preventDefault();
            return;
        }
        if (totalDias === 0 && !esLimpieza) {
            e.preventDefault();
            alert('Por favor, seleccione al menos un día de temporada.');
            return;
        }
        if (!esLimpieza && cfg.tieneTemporadas && !confirm('¿Está seguro de reemplazar las temporadas existentes de este año?')) {
            e.preventDefault(); return;
        }
        document.getElementById('id_dias_seleccionados').value = esLimpieza ? '{}' : JSON.stringify(diasSeleccionados);
    });

    const btnLimpiar = document.getElementById('btn-limpiar-anio');
    if (btnLimpiar) {
        btnLimpiar.addEventListener('click', function() {
            if (!confirm(`¿Seguro que quieres dejar el año ${anioSeleccionado} SIN ningún día de temporada? Se eliminarán todos los ya guardados.`)) return;
            campoLimpiar.value = '1';
            // form.submit() NO dispara el handler de 'submit', así que los campos
            // ocultos se rellenan aquí explícitamente.
            document.getElementById('id_dias_seleccionados').value = '{}';
            form.submit();
        });
    }
});
