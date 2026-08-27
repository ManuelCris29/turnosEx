document.addEventListener('DOMContentLoaded', function() {
    const cfg = window.FESTIVOS_INIT || {};
    const tipoSeleccionado = cfg.tipo || '';
    const anioSeleccionado = cfg.anio || 0;
    const url = cfg.url || '';
    const diasPorMes = JSON.parse(document.getElementById('festivos-dias-por-mes').textContent);
    const festivosPorMes = JSON.parse(document.getElementById('festivos-festivos-por-mes').textContent);
    const temporadasPorMes = JSON.parse(document.getElementById('festivos-temporadas-por-mes').textContent);

    if (typeof establecerFestivosYTemporadas === 'function') {
        establecerFestivosYTemporadas(festivosPorMes, temporadasPorMes);
    }
    if (tipoSeleccionado === 'mantenimiento' && festivosPorMes) {
        mostrarFestivos(festivosPorMes, anioSeleccionado);
    }
    if (typeof inicializarCalendarioConDatos === 'function') {
        inicializarCalendarioConDatos(diasPorMes, anioSeleccionado);
    } else {
        console.warn('inicializarCalendarioConDatos no encontrado');
        if (diasPorMes) {
            Object.keys(diasPorMes).forEach(key => {
                diasSeleccionadosPorMes[parseInt(key)] = diasPorMes[key].map(d => parseInt(d));
            });
        }
        for (let mes = 1; mes <= 12; mes++) {
            renderizarCalendarioMes(mes, anioSeleccionado, diasSeleccionadosPorMes[mes] || []);
        }
        actualizarDiasSeleccionados();
    }

    // Guardar reescribe el año entero (borra y vuelve a crear los días), así que sin
    // ningún día tocado el botón queda apagado: ver `utils/guardado_atomico.js`.
    window.guardiaGuardadoAnual = window.guardadoAtomico({
        boton: document.getElementById('btn-guardar'),
        instantanea: obtenerDiasSeleccionados,
    });

    const hayDatos = diasPorMes && Object.keys(diasPorMes).length > 0;
    if (!hayDatos) cargarDiasExistentes(tipoSeleccionado, anioSeleccionado);

    function navegarUrl(params) {
        window.location.href = url + '?' + new URLSearchParams(params).toString();
    }

    document.getElementById('id_tipo').addEventListener('change', function() {
        navegarUrl({ tipo: this.value, anio: document.getElementById('id_anio').value });
    });
    document.getElementById('id_anio').addEventListener('change', function() {
        navegarUrl({ tipo: document.getElementById('id_tipo').value, anio: this.value });
    });
    document.getElementById('btn-cargar-anio').addEventListener('click', function() {
        navegarUrl({ tipo: document.getElementById('id_tipo').value, anio: document.getElementById('id_anio').value });
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
            if (anio >= min && anio <= max) {
                navegarUrl({ tipo: document.getElementById('id_tipo').value, anio });
            } else if (inputAnioPersonalizado.value) {
                alert(`Por favor, ingrese un año entre ${min} y ${max}`);
                inputAnioPersonalizado.value = '';
            }
        }
        inputAnioPersonalizado.addEventListener('keypress', e => { if (e.key === 'Enter') irAnioPersonalizado(); });
        inputAnioPersonalizado.addEventListener('blur', irAnioPersonalizado);
    }

    const form = document.getElementById('form-dias-especiales');
    const campoLimpiar = document.getElementById('id_limpiar_anio');

    form.addEventListener('submit', function(e) {
        const diasSeleccionados = obtenerDiasSeleccionados();
        const totalDias = Object.values(diasSeleccionados).reduce((sum, dias) => sum + dias.length, 0);
        const tipo = document.getElementById('id_tipo').value;
        const tipoTexto = tipo === 'festivo' ? 'festivo' : 'de mantenimiento';
        // El envío con `limpiar_anio` lo dispara el botón de limpiar, que ya confirmó
        // con el usuario: aquí solo se deja pasar sin exigir días seleccionados.
        const esLimpieza = campoLimpiar && campoLimpiar.value === '1';

        if (!esLimpieza && !window.guardiaGuardadoAnual.sucio()) {
            e.preventDefault();
            return;
        }
        if (totalDias === 0 && !esLimpieza) {
            e.preventDefault();
            alert('Por favor, seleccione al menos un día ' + tipoTexto + '.');
            return;
        }
        if (!esLimpieza && cfg.tieneDias && !confirm(`¿Está seguro de reemplazar los ${tipo}s existentes de este año?`)) {
            e.preventDefault();
            return;
        }
        document.getElementById('id_dias_seleccionados').value = esLimpieza ? '{}' : JSON.stringify(diasSeleccionados);
    });

    const btnLimpiar = document.getElementById('btn-limpiar-anio');
    if (btnLimpiar) {
        btnLimpiar.addEventListener('click', function() {
            const tipo = document.getElementById('id_tipo').value;
            const anio = document.getElementById('id_anio').value;
            if (!confirm(`¿Seguro que quieres dejar el año ${anio} SIN ningún día de ${tipo}? Se eliminarán todos los ya guardados.`)) return;
            campoLimpiar.value = '1';
            // form.submit() NO dispara el handler de 'submit', así que los campos
            // ocultos se rellenan aquí explícitamente.
            document.getElementById('id_dias_seleccionados').value = '{}';
            form.submit();
        });
    }

    const btnRegenMant = document.getElementById('btn-regenerar-mantenimiento');
    if (btnRegenMant) {
        btnRegenMant.addEventListener('click', function() {
            regenerarMantenimientoAutomatico(parseInt(document.getElementById('id_anio').value));
        });
    }
    const btnRegenFest = document.getElementById('btn-regenerar-festivos');
    if (btnRegenFest) {
        btnRegenFest.addEventListener('click', function() {
            regenerarFestivosAutomatico(parseInt(document.getElementById('id_anio').value));
        });
    }
});

function mostrarFestivos(festivosPorMes, anio) {
    const contenedor = document.getElementById('festivos-badges');
    if (!contenedor) return;
    const mesesNombres = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
    let html = '';
    if (festivosPorMes && Object.keys(festivosPorMes).length > 0) {
        Object.keys(festivosPorMes).forEach(mesKey => {
            const mes = parseInt(mesKey);
            const dias = festivosPorMes[mesKey];
            if (dias && dias.length > 0) {
                dias.forEach(dia => {
                    html += `<span class="badge badge-secondary mr-1 mb-1">${mesesNombres[mes-1]} ${dia}</span>`;
                });
            }
        });
    } else {
        html = '<span class="text-muted">No hay festivos configurados para este año.</span>';
    }
    contenedor.innerHTML = html;
}

function recargarFestivosYTemporadas(anio) {
    fetch(`/turnos/api/dias-especiales-por-tipo/?tipo=festivo&anio=${anio}`)
        .then(r => r.json())
        .then(data => {
            if (data.por_mes && typeof establecerFestivosYTemporadas === 'function') {
                const fm = {};
                for (const mes in data.por_mes) fm[parseInt(mes)] = data.por_mes[mes];
                establecerFestivosYTemporadas(fm, null);
            }
        }).catch(err => console.error('Error al cargar festivos:', err));
    fetch(`/turnos/api/dias-temporada/?anio=${anio}`)
        .then(r => r.json())
        .then(data => {
            if (data.por_mes && typeof establecerFestivosYTemporadas === 'function') {
                const tm = {};
                for (const mes in data.por_mes) tm[parseInt(mes)] = data.por_mes[mes];
                establecerFestivosYTemporadas(null, tm);
            }
        }).catch(err => console.error('Error al cargar temporadas:', err));
}

function regenerarMantenimientoAutomatico(anio) {
    if (!confirm('¿Está seguro de regenerar automáticamente los días de mantenimiento? Esto reemplazará cualquier selección manual actual.')) return;
    const btn = document.getElementById('btn-regenerar-mantenimiento');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Calculando...'; }
    fetch(`/turnos/api/calcular-mantenimiento-automatico/?anio=${anio}`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then(data => {
            if (data.por_mes) {
                // Vaciar en su lugar la global compartida (declarada con let en
                // calendario_festivos_mantenimiento.js); NO reasignar para no romper
                // el binding compartido ni crear una global implícita.
                Object.keys(diasSeleccionadosPorMes).forEach(m => delete diasSeleccionadosPorMes[m]);
                recargarFestivosYTemporadas(anio);
                Object.keys(data.por_mes).forEach(mesKey => {
                    const mes = parseInt(mesKey);
                    diasSeleccionadosPorMes[mes] = data.por_mes[mesKey].map(d => parseInt(d));
                    renderizarCalendarioMes(mes, anio, data.por_mes[mesKey]);
                });
                actualizarDiasSeleccionados();
                alert(`Se calcularon automáticamente ${data.total} días de mantenimiento para el año ${anio}.`);
            } else {
                alert('No se pudieron calcular los días de mantenimiento automáticamente.');
            }
        })
        .catch(err => { console.error(err); alert('Error al calcular los días de mantenimiento. Intente nuevamente.'); })
        .finally(() => { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-magic"></i> Regenerar Automáticamente'; } });
}

function regenerarFestivosAutomatico(anio) {
    if (!confirm('¿Está seguro de regenerar automáticamente los festivos? Esto complementará los días actuales con los festivos oficiales calculados para ese año.')) return;
    const btn = document.getElementById('btn-regenerar-festivos');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Calculando...'; }
    fetch(`/turnos/api/calcular-festivos-automatico/?anio=${anio}`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
        .then(data => {
            if (data.por_mes) {
                const fm = {};
                Object.keys(data.por_mes).forEach(mesKey => {
                    fm[parseInt(mesKey)] = data.por_mes[mesKey].map(d => parseInt(d));
                });
                if (typeof establecerFestivosYTemporadas === 'function') establecerFestivosYTemporadas(fm, null);
                if (window.FESTIVOS_INIT && window.FESTIVOS_INIT.tipo === 'festivo') {
                    Object.keys(fm).forEach(mesKey => {
                        renderizarCalendarioMes(parseInt(mesKey), anio, diasSeleccionadosPorMes[parseInt(mesKey)] || []);
                    });
                }
                alert(`Se generaron/actualizaron automáticamente festivos para el año ${anio}.`);
            } else {
                alert('No se pudieron calcular los festivos automáticamente.');
            }
        })
        .catch(err => { console.error(err); alert('Error al calcular los festivos. Intente nuevamente.'); })
        .finally(() => { if (btn) { btn.disabled = false; btn.innerHTML = '<i class="fas fa-magic"></i> Regenerar Festivos'; } });
}