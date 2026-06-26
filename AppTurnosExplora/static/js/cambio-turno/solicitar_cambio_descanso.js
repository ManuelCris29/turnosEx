/**
 * Solicitar Cambio de Día de Descanso (fin de semana).
 *
 * Intercambio de descansos (descanso por descanso), ida y vuelta el mismo mes:
 *  1. Elegir el finde que cambias (día que trabajas por alternancia).
 *  2. Cargar compañeros del grupo contrario.
 *  3. Elegir el finde de devolución (mismo mes, MISMO día sáb/dom).
 *  4. Enviar.
 *
 * El backend valida toda la regla (alternancia, mismo mes, mismo día, balance de domingos).
 */
(function () {
    'use strict';

    const URL_EMPLEADOS = '/solicitudes/obtener-empleados-disponibles/';
    const URL_PROCESAR = '/solicitudes/procesar-solicitud/';
    const URL_ALTERNANCIA = '/solicitudes/alternancia-finde/';
    const URL_DESCANSOS_SEMANA = '/solicitudes/descansos-semana-usuario/';

    // Jornada predeterminada del solicitante (AM/PM), para resaltar "tú eres ...".
    const MI_JORNADA = (window.MI_JORNADA || '').toUpperCase();

    // Descansos de entre semana del usuario por año (temporada/mantenimiento), para marcar el calendario.
    const descansosSemana = {};   // { 'YYYY-MM-DD': 'temporada'|'mantenimiento' }
    const aniosDescansoCargados = {};

    function toISO(d) {
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return d.getFullYear() + '-' + m + '-' + day;
    }
    function cargarDescansosSemana(anio, cb) {
        if (aniosDescansoCargados[anio]) { if (cb) cb(); return; }
        fetch(`${URL_DESCANSOS_SEMANA}?anio=${anio}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((res) => {
                const d = (res && res.data) ? res.data : res;
                Object.assign(descansosSemana, (d && d.descansos) || {});
                aniosDescansoCargados[anio] = true;
                if (cb) cb();
            })
            .catch(() => { if (cb) cb(); });
    }

    const form = document.getElementById('cdForm');
    if (!form) return;

    const tipoId = document.getElementById('tipo_solicitud_id').value;
    const inputCesion = document.getElementById('fecha_solicitud');
    const selectReceptor = document.getElementById('empleado_receptor');
    const inputPago = document.getElementById('fecha_pago');
    const resumen = document.getElementById('cd_resumen');
    const btnEnviar = document.getElementById('btnEnviarCd');
    const distintivoCesion = document.getElementById('cd_distintivo_cesion');
    const distintivoPago = document.getElementById('cd_distintivo_pago');

    let diaCesion = null;  // 0=domingo, 6=sábado
    let modo = 'finde';    // 'finde' | 'semana'

    const esFinde = (d) => d.getDay() === 0 || d.getDay() === 6;
    const esSemana = (d) => d.getDay() >= 1 && d.getDay() <= 5;
    const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
    // Días deshabilitados en el picker de cesión según la modalidad.
    const disableCesion = () => modo === 'finde' ? [(d) => !esFinde(d)] : [(d) => !esSemana(d)];

    const jornadaBase = (window.jornadaBase || '').toUpperCase();

    // Según la alternancia (ref: sábado 10/01/2026 trabaja PM), determina si en ese día de
    // finde el usuario TRABAJA o DESCANSA, para marcarlo en el calendario.
    function estadoFinde(date) {
        if (!jornadaBase || (date.getDay() !== 0 && date.getDay() !== 6)) return null;
        const sabado = new Date(date);
        if (date.getDay() === 0) sabado.setDate(sabado.getDate() - 1);
        const refUTC = Date.UTC(2026, 0, 10);
        const sabUTC = Date.UTC(sabado.getFullYear(), sabado.getMonth(), sabado.getDate());
        const deltaWeeks = Math.floor((sabUTC - refUTC) / (7 * 86400000));
        const even = (((deltaWeeks % 2) + 2) % 2) === 0;
        const trabajaSab = even ? 'PM' : 'AM';
        const trabajaDom = trabajaSab === 'AM' ? 'PM' : 'AM';
        const trabajaHoy = (date.getDay() === 6) ? trabajaSab : trabajaDom;
        return jornadaBase === trabajaHoy ? 'trabaja' : 'descansa';
    }

    function marcarDia(dObj, dStr, fp, dayElem) {
        const d = dayElem.dateObj;
        if (modo === 'finde') {
            const est = estadoFinde(d);
            if (!est) return;
            dayElem.classList.add('cd-' + est);
            dayElem.title = est === 'trabaja' ? 'Trabajas este día' : 'Descansas este día';
        } else {
            // Entre semana: marcar los días que el usuario DESCANSA (temporada/mantenimiento).
            if (d.getDay() < 1 || d.getDay() > 5) return;
            const motivo = descansosSemana[toISO(d)];
            if (!motivo) return;
            dayElem.classList.add('cd-descansa');
            dayElem.title = motivo === 'mantenimiento' ? 'Descanso (mantenimiento)' : 'Descanso (temporada)';
        }
    }

    function notificar(icon, title, text) {
        if (window.Swal) return Swal.fire({ icon, title, html: text, confirmButtonText: 'Entendido' });
        alert(`${title}\n\n${(text || '').replace(/<[^>]+>/g, '')}`);
        return Promise.resolve();
    }

    function mostrarDistintivo(contenedor, fechaStr) {
        if (!contenedor) return;
        if (!fechaStr) { contenedor.style.display = 'none'; contenedor.innerHTML = ''; return; }
        fetch(`${URL_ALTERNANCIA}?fecha=${encodeURIComponent(fechaStr)}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((res) => {
                const d = (res && res.data) ? res.data : res;
                if (!d || !d.sabado || !d.domingo) { contenedor.style.display = 'none'; return; }
                const chip = (label, dia, jor) => {
                    const esMio = MI_JORNADA && (jor || '').toUpperCase() === MI_JORNADA;
                    const tuTag = esMio ? ` <span class="tu-tag"><i class="fas fa-user"></i> Tú</span>` : '';
                    return `<span class="fds-dia${esMio ? ' es-mio' : ''}">${label} ${dia} ` +
                           `<span class="jor jor-${jor}">${jor || '?'}</span>${tuTag}</span>`;
                };
                contenedor.innerHTML = chip('Sáb', d.sabado.dia, d.sabado.jornada) + chip('Dom', d.domingo.dia, d.domingo.jornada);
                contenedor.style.display = 'flex';
            })
            .catch(() => { contenedor.style.display = 'none'; });
    }

    // Carga los descansos del año visible y redibuja el calendario (modalidad entre semana).
    function cargarYRedraw(fp) {
        if (modo !== 'semana') return;
        const y = fp.currentYear || new Date().getFullYear();
        cargarDescansosSemana(y, () => fp.redraw());
    }
    function crearPickerCesion() {
        if (fpCesion) fpCesion.destroy();
        fpCesion = flatpickr(inputCesion, {
            locale: 'es', dateFormat: 'Y-m-d', minDate: 'today', disable: disableCesion(),
            onChange: onCesionChange, onDayCreate: marcarDia,
            onReady: function () { cargarYRedraw(this); },
            onYearChange: function () { cargarYRedraw(this); },
            onMonthChange: function () { cargarYRedraw(this); },
        });
    }

    let fpCesion = null;
    crearPickerCesion();
    let fpPago = flatpickr(inputPago, { locale: 'es', dateFormat: 'Y-m-d', disable: disableCesion(), onDayCreate: marcarDia });

    // Cambio de modalidad (fin de semana / entre semana)
    document.querySelectorAll('input[name="modo_descanso"]').forEach((r) => {
        r.addEventListener('change', function () {
            modo = this.value;
            const finde = modo === 'finde';
            document.getElementById('lbl_modo_finde').classList.toggle('active', finde);
            document.getElementById('lbl_modo_semana').classList.toggle('active', !finde);
            document.getElementById('lbl_cesion').textContent = finde ? 'Fin de Semana que Cambias' : 'Día (entre semana) que Cambias';
            document.getElementById('modo_ayuda').textContent = finde
                ? 'Intercambia tu descanso de sábado o domingo (ida y vuelta, mismos domingos).'
                : 'Intercambia un día de descanso de lunes a viernes. Los días grises son tus descansos (temporada/mantenimiento). Si es festivo, debe ser festivo por festivo.';
            // Resetear todo y reconfigurar el picker de cesión.
            inputCesion.value = ''; diaCesion = null;
            resetReceptorYPago();
            if (distintivoCesion) { distintivoCesion.style.display = 'none'; distintivoCesion.innerHTML = ''; }
            // La leyenda se muestra en ambas modalidades; en entre semana solo aplica "Descansas".
            actualizarLeyenda(finde);
            crearPickerCesion();
            if (!finde) cargarDescansosSemana(new Date().getFullYear(), () => fpCesion && fpCesion.redraw());
        });
    });

    function actualizarLeyenda(finde) {
        const ley = document.getElementById('cd_leyenda');
        if (!ley) return;
        ley.style.display = 'flex';
        ley.innerHTML = finde
            ? '<span><i class="box cd-box-trab"></i> Trabajas</span><span><i class="box cd-box-desc"></i> Descansas</span>'
            : '<span><i class="box cd-box-desc"></i> Tus descansos (temporada/mantenimiento)</span>';
    }

    function resetReceptorYPago() {
        selectReceptor.innerHTML = '<option value="">Primero selecciona el fin de semana…</option>';
        selectReceptor.disabled = true;
        inputPago.value = ''; inputPago.disabled = true;
        resumen.style.display = 'none';
        if (distintivoPago) { distintivoPago.style.display = 'none'; distintivoPago.innerHTML = ''; }
    }

    function onCesionChange(selectedDates, dateStr) {
        resetReceptorYPago();
        if (!dateStr) {
            if (distintivoCesion) { distintivoCesion.style.display = 'none'; distintivoCesion.innerHTML = ''; }
            diaCesion = null; return;
        }
        diaCesion = selectedDates[0].getDay();
        if (modo === 'finde') mostrarDistintivo(distintivoCesion, dateStr);
        cargarCompaneros(dateStr);
        configurarPagoMismoMes(selectedDates[0], dateStr);
    }

    function configurarPagoMismoMes(fechaCesion, cesionStr) {
        const y = fechaCesion.getFullYear(); const m = fechaCesion.getMonth();
        const primero = new Date(y, m, 1); const ultimo = new Date(y, m + 1, 0);
        const minDate = primero < hoy ? hoy : primero;
        if (fpPago) fpPago.destroy();
        // Finde: solo el MISMO día (sáb/dom). Entre semana: cualquier día lun-vie.
        const reglaDia = modo === 'finde'
            ? (date) => date.getDay() !== diaCesion
            : (date) => !esSemana(date);
        fpPago = flatpickr(inputPago, {
            locale: 'es', dateFormat: 'Y-m-d', minDate: minDate, maxDate: ultimo,
            disable: [reglaDia, cesionStr],
            onChange: actualizarResumen,
            onDayCreate: marcarDia,
        });
        inputPago.disabled = false;
    }

    function cargarCompaneros(fechaCesion) {
        selectReceptor.innerHTML = '<option value="">Cargando…</option>';
        const url = `${URL_EMPLEADOS}?fecha=${encodeURIComponent(fechaCesion)}&tipo_solicitud_id=${tipoId}`;
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((data) => {
                const empleados = (data && (data.empleados || (data.data && data.data.empleados))) || [];
                if (!empleados.length) {
                    selectReceptor.innerHTML = '<option value="">No hay compañeros disponibles ese fin de semana</option>';
                    selectReceptor.disabled = true; return;
                }
                selectReceptor.innerHTML = '<option value="">Selecciona un compañero…</option>';
                empleados.forEach((e) => {
                    const opt = document.createElement('option');
                    opt.value = e.id; opt.textContent = `${e.nombre} ${e.apellido}`;
                    selectReceptor.appendChild(opt);
                });
                selectReceptor.disabled = false;
            })
            .catch(() => { selectReceptor.innerHTML = '<option value="">Error cargando compañeros</option>'; selectReceptor.disabled = true; });
        selectReceptor.onchange = actualizarResumen;
    }

    function actualizarResumen() {
        const ces = inputCesion.value; const pago = inputPago.value;
        const comp = selectReceptor.options[selectReceptor.selectedIndex];
        if (modo === 'finde') mostrarDistintivo(distintivoPago, pago);
        if (ces && pago && selectReceptor.value) {
            const cola = modo === 'finde' ? ' Quedan con los mismos domingos.' : '';
            resumen.innerHTML =
                `<i class="fas fa-exchange-alt me-1"></i> Intercambias tu descanso del <strong>${ces}</strong> con ` +
                `<strong>${comp.textContent}</strong>, y devuelves el <strong>${pago}</strong>.${cola}`;
            resumen.style.display = 'block';
        } else { resumen.style.display = 'none'; }
    }

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        const errores = [];
        if (!inputCesion.value) errores.push('Selecciona el fin de semana que cambias.');
        if (!selectReceptor.value) errores.push('Selecciona el compañero con quien intercambias.');
        if (!inputPago.value) errores.push('Selecciona el fin de semana de devolución.');
        if (!document.getElementById('comentarios').value.trim()) errores.push('Ingresa un comentario.');
        if (inputCesion.value && inputPago.value && inputCesion.value === inputPago.value) {
            errores.push('La devolución debe ser un fin de semana distinto al que cambias.');
        }
        if (errores.length) { notificar('warning', 'Faltan datos', errores.map((e) => `• ${e}`).join('<br>')); return; }
        enviar(false);

        function restablecer() {
            btnEnviar.disabled = false;
            btnEnviar.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Enviar Solicitud';
        }
        function enviar(confirmarRestriccion) {
            const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
            const fd = new FormData(form);
            if (confirmarRestriccion) fd.set('confirmar_restriccion', '1');
            btnEnviar.disabled = true;
            btnEnviar.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Enviando…';
            // Loading bloqueante: evita doble envío. Cualquier Swal posterior lo reemplaza.
            LoadingUI.mostrar('Enviando solicitud...');
            fetch(URL_PROCESAR, { method: 'POST', headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' }, body: fd })
                .then(async (r) => ({ ok: r.ok, data: await r.json().catch(() => ({})) }))
                .then(({ ok, data }) => {
                    const success = ok && (data.success !== false);
                    if (success) {
                        const msg = (data.data && data.data.message) || data.message || 'Solicitud de cambio de descanso enviada correctamente.';
                        notificar('success', '¡Solicitud enviada!', msg).then(() => { window.location.href = '/solicitudes/mis-solicitudes/'; });
                    } else if (window.RestriccionAdvertencia && RestriccionAdvertencia.manejar(data, function () { enviar(true); }, restablecer)) {
                        return;
                    } else {
                        notificar('error', 'No se pudo enviar', data.error || data.message || 'No se pudo procesar la solicitud.');
                        restablecer();
                    }
                })
                .catch(() => { notificar('error', 'Error', 'Ocurrió un error de red. Intenta de nuevo.'); restablecer(); });
        }
    });
})();
