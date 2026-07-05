document.addEventListener('DOMContentLoaded', function() {
    const cfg = window.TEMPORADAS_INIT || {};
    const anioSeleccionado = cfg.anio;
    const diasPorMes = cfg.diasPorMes || {};
    const url = cfg.url || '';

    for (let mes = 1; mes <= 12; mes++) {
        renderizarCalendarioMes(mes, anioSeleccionado, diasPorMes[mes] || []);
    }
    actualizarDiasSeleccionados();

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
            if (anio >= 2000) navegarAnio(anio);
            else if (inputAnioPersonalizado.value) { alert('Ingrese un año mayor o igual a 2000'); inputAnioPersonalizado.value = ''; }
        }
        inputAnioPersonalizado.addEventListener('keypress', e => { if (e.key === 'Enter') irAnioPersonalizado(); });
        inputAnioPersonalizado.addEventListener('blur', irAnioPersonalizado);
    }

    document.getElementById('form-temporadas').addEventListener('submit', function(e) {
        const diasSeleccionados = obtenerDiasSeleccionados();
        const totalDias = Object.values(diasSeleccionados).reduce((sum, dias) => sum + dias.length, 0);
        if (totalDias === 0) { e.preventDefault(); alert('Por favor, seleccione al menos un día de temporada.'); return; }
        if (cfg.tieneTemporadas && !confirm('¿Está seguro de reemplazar las temporadas existentes de este año?')) {
            e.preventDefault(); return;
        }
        document.getElementById('id_dias_seleccionados').value = JSON.stringify(diasSeleccionados);
    });
});
