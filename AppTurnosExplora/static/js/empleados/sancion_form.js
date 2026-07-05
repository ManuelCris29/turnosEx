(function () {
    const inicio = document.getElementById('id_fecha_inicio');
    const dur = document.getElementById('id_duracion');
    const custom = document.getElementById('id_dias_personalizado');
    const grupoCustom = document.getElementById('grupo-dias-custom');
    const preview = document.getElementById('preview-fin');
    const previewFecha = document.getElementById('preview-fecha');
    const meses = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];

    function dias() {
        if (dur.value === 'otro') return parseInt(custom.value) || 0;
        return parseInt(dur.value) || 0;
    }
    function actualizar() {
        grupoCustom.style.display = (dur.value === 'otro') ? '' : 'none';
        const d = dias();
        if (inicio.value && d > 0) {
            const f = new Date(inicio.value + 'T00:00:00');
            f.setDate(f.getDate() + d - 1);
            previewFecha.textContent = `${f.getDate()} de ${meses[f.getMonth()]} de ${f.getFullYear()}`;
            preview.style.display = '';
        } else {
            preview.style.display = 'none';
        }
    }
    [inicio, dur, custom].forEach(el => { if (el) { el.addEventListener('change', actualizar); el.addEventListener('input', actualizar); } });
    actualizar();
})();
