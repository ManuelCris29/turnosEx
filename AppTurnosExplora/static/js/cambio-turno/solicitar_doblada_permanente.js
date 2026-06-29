/**
 * Solicitar Doblada Permanente (varios compañeros)
 *
 * Acuerdo recurrente: por cada día de la semana eliges un compañero (de jornada
 * contraria) que te cubre, y por cada día de devolución eliges a cuál compañero
 * le pagas (doblándote). Al enviar, el backend agrupa por compañero y crea una
 * solicitud independiente por cada uno (igual que la "Cesión Total" de la doblada).
 */
(function () {
    'use strict';

    const URL_EMPLEADOS = '/solicitudes/obtener-empleados-disponibles/';
    const URL_PROCESAR = '/solicitudes/procesar-solicitud/';
    const URL_PREVIEW = '/solicitudes/previsualizar-doblada-permanente/';
    const URL_DIAS_DISP = '/solicitudes/dias-disponibles-doblada-permanente/';
    let dispDias = null;  // {0:n,1:n,...} días válidos por weekday en el rango (lado solicitante)

    const form = document.getElementById('dobladaPermForm');
    if (!form) return;

    const tipoId = document.getElementById('tipo_solicitud_id').value;
    const inputInicio = document.getElementById('fecha_inicio');
    const inputFin = document.getElementById('fecha_fin');
    const btn = document.getElementById('btnEnviarDobladaPerm');

    const cesionRows = document.getElementById('cesion_rows');
    const devolucionRows = document.getElementById('devolucion_rows');
    const btnAddCesion = document.getElementById('btn_add_cesion');
    const btnAddDevolucion = document.getElementById('btn_add_devolucion');
    const cesionHint = document.getElementById('cesion_hint');

    // Solo lunes a viernes: la doblada permanente es recurrente y no aplica fines de semana
    // (un sábado de media jornada es una excepción puntual → Doblada de Fin de Semana).
    const DIAS = [['0', 'Lunes'], ['1', 'Martes'], ['2', 'Miércoles'], ['3', 'Jueves'], ['4', 'Viernes']];
    let companeros = [];  // [{id, nombre, apellido}]

    function notificar(icon, title, text) {
        if (window.Swal) return Swal.fire({ icon, title, html: text, confirmButtonText: 'Entendido' });
        alert(`${title}\n\n${(text || '').replace(/<[^>]+>/g, '')}`);
        return Promise.resolve();
    }

    let fpInicio = null;
    let fpFin = null;

    // Calendarios Desde/Hasta. Se bloquean días especiales: domingos, festivos,
    // mantenimiento y TEMPORADA (igual que CT Permanente). En doblada permanente se parte de
    // UNA jornada y se dobla; en temporada/festivo el día no está en jornada predeterminada,
    // así que no se permite seleccionarlos.
    if (window.DatepickerFestivos && window.DatepickerFestivos.inicializar) {
        window.DatepickerFestivos.inicializar({
            input: inputFin, minDate: 'today', bloquearDiasEspeciales: true, permitirFestivos: false, permitirTemporada: false,
            onDateChange: function () { cargarDisponibilidadDias(); actualizarPreview(); },
        }).then(function (inst) { fpFin = inst; });
        window.DatepickerFestivos.inicializar({
            input: inputInicio, minDate: 'today', bloquearDiasEspeciales: true, permitirFestivos: false, permitirTemporada: false,
            onDateChange: function (str) {
                if (fpFin) fpFin.set('minDate', str || 'today');
                cargarCompaneros(str);
                cargarDisponibilidadDias();
                actualizarPreview();
            },
        }).then(function (inst) { fpInicio = inst; });
    } else {
        fpFin = flatpickr(inputFin, { locale: 'es', dateFormat: 'Y-m-d', minDate: 'today',
            onChange: function () { cargarDisponibilidadDias(); actualizarPreview(); } });
        fpInicio = flatpickr(inputInicio, {
            locale: 'es', dateFormat: 'Y-m-d', minDate: 'today',
            onChange: function (sel, str) { if (fpFin) fpFin.set('minDate', str || 'today'); cargarCompaneros(str); cargarDisponibilidadDias(); actualizarPreview(); },
        });
    }

    function cargarCompaneros(fecha) {
        companeros = [];
        setHabilitado(false);
        if (cesionHint) cesionHint.textContent = 'Cargando compañeros…';
        if (!fecha) { if (cesionHint) cesionHint.textContent = 'Primero elige la fecha de inicio para cargar los compañeros.'; return; }
        fetch(`${URL_EMPLEADOS}?fecha=${encodeURIComponent(fecha)}&tipo_solicitud_id=${tipoId}`,
              { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((data) => {
                companeros = (data && (data.empleados || (data.data && data.data.empleados))) || [];
                // Cambió la base de compañeros: limpiar filas previas SIEMPRE (evita
                // que queden filas obsoletas apuntando a compañeros de la fecha anterior).
                cesionRows.innerHTML = '';
                devolucionRows.innerHTML = '';
                if (!companeros.length) {
                    if (cesionHint) cesionHint.textContent = 'No hay compañeros de jornada contraria disponibles.';
                    return;
                }
                if (cesionHint) cesionHint.textContent = 'Agrega los días que cedes y elige el compañero de cada uno.';
                setHabilitado(true);
            })
            .catch(() => { if (cesionHint) cesionHint.textContent = 'Error cargando compañeros.'; });
    }

    function setHabilitado(on) {
        if (btnAddCesion) btnAddCesion.disabled = !on;
        if (btnAddDevolucion) btnAddDevolucion.disabled = !on;
    }

    // Días ya tomados por los selectores de día (excepto, opcionalmente, uno).
    function diasUsados(excluir) {
        return new Set(
            Array.from(form.querySelectorAll('select[name$="_dia"]'))
                .filter((s) => s !== excluir && s.value !== '')
                .map((s) => s.value)
        );
    }

    function primerDiaLibre() {
        const usados = diasUsados(null);
        const libre = DIAS.find(([v]) => !usados.has(v));
        return libre ? libre[0] : '';
    }

    // Un día solo puede usarse una vez en TODO el acuerdo (ni dos veces en cesión,
    // ni el mismo día en cesión y devolución). Recalcula las opciones de cada
    // selector quitando los que ya tomaron OTROS, pero PRESERVA su propia selección.
    const MESES_AB2 = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    function fmtFechaCorta(iso) { const p = iso.split('-'); return `${parseInt(p[2], 10)}/${MESES_AB2[parseInt(p[1], 10) - 1]}`; }

    function refreshDias() {
        const cnt = (v) => (dispDias ? (dispDias[v] || []).length : null);
        const selects = Array.from(form.querySelectorAll('select[name$="_dia"]'));
        selects.forEach(function (sel) {
            const usadosPorOtros = diasUsados(sel);
            let actual = sel.value;  // su propio día nunca está en "usadosPorOtros"
            const opts = DIAS.filter(([v]) => !usadosPorOtros.has(v));
            // Si el día actual quedó SIN días válidos en el rango, moverlo a uno que sí tenga.
            if (dispDias && actual && cnt(actual) === 0) {
                const libre = opts.find(([v]) => cnt(v) > 0);
                actual = libre ? libre[0] : actual;
            }
            sel.innerHTML = opts.map(([v, n]) => {
                const c = cnt(v);
                const sinDias = c === 0;
                const etiqueta = c === null ? n
                    : (sinDias ? `${n} — sin días disponibles` : `${n} — ${c} ${c === 1 ? 'día' : 'días'} disponible${c === 1 ? '' : 's'}`);
                return `<option value="${v}"${sinDias ? ' disabled' : ''}${v === actual ? ' selected' : ''}>${etiqueta}</option>`;
            }).join('');
            sel.value = actual;
            // Pista con las FECHAS concretas del día elegido en el rango.
            const row = sel.closest('.perm-row');
            const hint = row && row.querySelector('.perm-dias-hint');
            if (hint) {
                if (!dispDias || !actual) {
                    hint.textContent = '';
                } else {
                    const fechas = dispDias[actual] || [];
                    hint.textContent = fechas.length
                        ? 'Fechas en el rango: ' + fechas.map(fmtFechaCorta).join(', ')
                        : 'Sin fechas válidas en el rango';
                }
            }
        });
        actualizarPreview();
    }

    // Disponibilidad de días válidos por weekday en el rango (lado solicitante). Al cambiar el
    // rango, recalcula y refresca los selectores para deshabilitar/anotar los días.
    function cargarDisponibilidadDias() {
        const fi = inputInicio.value, ff = inputFin.value;
        if (!fi || !ff || ff < fi) { dispDias = null; refreshDias(); return; }
        fetch(`${URL_DIAS_DISP}?fecha_inicio=${encodeURIComponent(fi)}&fecha_fin=${encodeURIComponent(ff)}`,
              { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((res) => {
                const d = (res && res.data) ? res.data : res;
                dispDias = (d && d.por_dia) || null;
                refreshDias();
            })
            .catch(() => { dispDias = null; refreshDias(); });
    }

    // Preview de "días que se omitirán" en el rango (festivos, descansos, días libres,
    // dobladas, mantenimiento del solicitante). Enfocado en el solicitante; las exclusiones
    // del compañero se validan al guardar. Coincide con la lógica de aplicación del backend.
    const MESES_AB = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    function actualizarPreview() {
        const box = document.getElementById('preview_omitidos_box');
        if (!box) return;
        const fi = inputInicio.value, ff = inputFin.value;
        const dias = Array.from(diasUsados(null));  // unión de días de cesión y devolución
        if (!fi || !ff || ff < fi || !dias.length) { box.style.display = 'none'; return; }
        // Mapa día_semana -> compañero (para revisar también los turnos del compañero de cada día).
        const mapa = {};
        filas(cesionRows, 'cesion').forEach((r) => { if (r.dia && r.comp) mapa[r.dia] = r.comp; });
        filas(devolucionRows, 'devolucion').forEach((r) => { if (r.dia && r.comp) mapa[r.dia] = r.comp; });
        const qComp = `&dias_companeros=${encodeURIComponent(JSON.stringify(mapa))}`;
        fetch(`${URL_PREVIEW}?fecha_inicio=${encodeURIComponent(fi)}&fecha_fin=${encodeURIComponent(ff)}&dias=${dias.join(',')}${qComp}`,
              { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((res) => {
                const d = (res && res.data) ? res.data : res;
                const exc = (d && d.excluidas) || [];
                const apl = (d && d.aplicables) || [];

                // BALANCE por compañero: cuenta los días APLICABLES de cesión y devolución de cada
                // compañero; deben quedar iguales (te cubre = devuelves). Si no, avisa.
                const cesMap = {}, devMap = {};
                filas(cesionRows, 'cesion').forEach((r) => { if (r.dia && r.comp) cesMap[r.dia] = r.comp; });
                filas(devolucionRows, 'devolucion').forEach((r) => { if (r.dia && r.comp) devMap[r.dia] = r.comp; });
                const pyWd = (iso) => { const p = iso.split('-'); return String((new Date(+p[0], +p[1] - 1, +p[2]).getDay() + 6) % 7); };
                const cubre = {}, devuelve = {};
                apl.forEach((iso) => {
                    const wd = pyWd(iso);
                    if (cesMap[wd]) cubre[cesMap[wd]] = (cubre[cesMap[wd]] || 0) + 1;
                    else if (devMap[wd]) devuelve[devMap[wd]] = (devuelve[devMap[wd]] || 0) + 1;
                });
                const nombreComp = (cid) => { const c = companeros.find((x) => String(x.id) === String(cid)); return c ? `${c.nombre} ${c.apellido}` : 'Compañero'; };
                const balMsgs = [];
                let hayDesbalance = false;
                new Set([...Object.keys(cubre), ...Object.keys(devuelve)]).forEach((cid) => {
                    const c = cubre[cid] || 0, v = devuelve[cid] || 0;
                    if (c !== v) {
                        hayDesbalance = true;
                        balMsgs.push(`<span style="color:#b45309;">⚠️ ${nombreComp(cid)}: te cubre ${c} y devuelves ${v} → se aplicarán ${Math.min(c, v)} (${Math.abs(c - v)} sin contraparte; ajusta el rango/días).</span>`);
                    } else if (c > 0) {
                        balMsgs.push(`✅ ${nombreComp(cid)}: ${c} cubre / ${c} devuelve (balanceado).`);
                    }
                });

                if (!exc.length && !balMsgs.length) { box.style.display = 'none'; return; }
                document.getElementById('preview_lista').innerHTML = exc.map((e) => {
                    const p = e.fecha.split('-');
                    return `<li><strong>${p[2]}/${MESES_AB[parseInt(p[1], 10) - 1]}</strong> — ${e.razon}</li>`;
                }).join('');
                document.getElementById('preview_resumen').textContent = exc.length
                    ? `Se aplicará en ${d.total_aplicables} día(s); se omitirán ${d.total_excluidas} (festivo, descanso, día libre, doblada, mantenimiento o temporada).`
                    : `Se aplicará en ${d.total_aplicables} día(s).`;
                const balEl = document.getElementById('preview_balance');
                if (balEl) balEl.innerHTML = balMsgs.length ? ('<strong>Balance:</strong><br>' + balMsgs.join('<br>')) : '';
                box.style.display = 'block';
            })
            .catch(() => { box.style.display = 'none'; });
    }

    // Compañeros usados actualmente en cesión (para limitar la devolución)
    function companerosEnCesion() {
        const ids = new Set();
        cesionRows.querySelectorAll('select[name="cesion_companero"]').forEach((s) => { if (s.value) ids.add(s.value); });
        return companeros.filter((c) => ids.has(String(c.id)));
    }

    function optCompaneros(lista) {
        return ['<option value="">Compañero…</option>']
            .concat(lista.map((c) => `<option value="${c.id}">${c.nombre} ${c.apellido}</option>`)).join('');
    }

    function nuevaFila(tipo) {
        const row = document.createElement('div');
        row.className = 'perm-row mb-2';
        const lista = (tipo === 'cesion') ? companeros : companerosEnCesion();
        const usados = diasUsados(null);
        const diaSel = primerDiaLibre();
        const optDiasLibres = DIAS.filter(([v]) => !usados.has(v))
            .map(([v, n]) => `<option value="${v}"${v === diaSel ? ' selected' : ''}>${n}</option>`).join('');
        row.innerHTML =
            `<div class="d-flex align-items-center" style="gap:.5rem;">` +
                `<select class="form-control" name="${tipo}_dia" style="max-width:230px;">${optDiasLibres}</select>` +
                `<select class="form-control" name="${tipo}_companero">${optCompaneros(lista)}</select>` +
                `<button type="button" class="btn btn-sm btn-outline-danger perm-remove" title="Quitar"><i class="fas fa-times"></i></button>` +
            `</div>` +
            `<div class="perm-dias-hint small text-muted mt-1" style="margin-left:2px;"></div>`;
        row.querySelector('.perm-remove').addEventListener('click', function () { row.remove(); refreshDias(); });
        row.querySelector('select[name$="_dia"]').addEventListener('change', refreshDias);
        // Cambiar de compañero también recalcula el preview (revisa SUS turnos por día).
        row.querySelector('select[name$="_companero"]').addEventListener('change', actualizarPreview);
        return row;
    }

    function hayDiasLibres() {
        const usados = new Set(
            Array.from(form.querySelectorAll('select[name$="_dia"]')).filter((s) => s.value !== '').map((s) => s.value)
        );
        return DIAS.some(([v]) => !usados.has(v));
    }

    if (btnAddCesion) btnAddCesion.addEventListener('click', function () {
        if (!companeros.length) return;
        if (!hayDiasLibres()) { notificar('info', 'Sin días libres', 'Ya usaste todos los días (lunes a viernes) entre cesión y devolución.'); return; }
        cesionRows.appendChild(nuevaFila('cesion'));
        refreshDias();
    });
    if (btnAddDevolucion) btnAddDevolucion.addEventListener('click', function () {
        const lista = companerosEnCesion();
        if (!lista.length) { notificar('info', 'Primero agrega cesión', 'Agrega al menos un día de cesión con su compañero antes de definir la devolución.'); return; }
        if (!hayDiasLibres()) { notificar('info', 'Sin días libres', 'Ya usaste todos los días (lunes a viernes) entre cesión y devolución.'); return; }
        devolucionRows.appendChild(nuevaFila('devolucion'));
        refreshDias();
    });

    function filas(cont, tipo) {
        return Array.from(cont.querySelectorAll('.perm-row')).map((r) => ({
            dia: r.querySelector(`select[name="${tipo}_dia"]`).value,
            comp: r.querySelector(`select[name="${tipo}_companero"]`).value,
        }));
    }

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        const ces = filas(cesionRows, 'cesion');
        const dev = filas(devolucionRows, 'devolucion');
        const errores = [];

        if (!inputInicio.value || !inputFin.value) errores.push('Selecciona el rango de fechas (Desde y Hasta).');
        if (inputInicio.value && inputFin.value && inputFin.value < inputInicio.value) errores.push('La fecha "Hasta" debe ser posterior a "Desde".');
        if (!ces.length) errores.push('Agrega al menos un día de cesión con su compañero.');
        if (ces.some((r) => !r.comp)) errores.push('Cada día de cesión debe tener un compañero.');
        if (!dev.length) errores.push('Agrega al menos un día de devolución.');
        if (dev.some((r) => !r.comp)) errores.push('Cada día de devolución debe tener un compañero.');

        // Día no puede ser cesión y devolución a la vez (mismo día de semana)
        const diasCes = new Set(ces.map((r) => r.dia));
        if (dev.some((r) => diasCes.has(r.dia))) errores.push('Un día no puede ser de cesión y de devolución a la vez.');

        // Devolución solo a compañeros que te cubren, y balance por compañero
        const cubreCount = {};   // comp -> # días que te cubre
        ces.forEach((r) => { if (r.comp) cubreCount[r.comp] = (cubreCount[r.comp] || 0) + 1; });
        const devCount = {};     // comp -> # días que le devuelves
        dev.forEach((r) => { if (r.comp) devCount[r.comp] = (devCount[r.comp] || 0) + 1; });
        Object.keys(devCount).forEach((comp) => {
            if (!cubreCount[comp]) errores.push('Solo puedes devolverle a un compañero que te cubra.');
        });
        Object.keys(cubreCount).forEach((comp) => {
            if ((devCount[comp] || 0) !== cubreCount[comp]) {
                const c = companeros.find((x) => String(x.id) === String(comp));
                const nom = c ? `${c.nombre} ${c.apellido}` : 'un compañero';
                errores.push(`A ${nom} le devuelves ${(devCount[comp] || 0)} día(s) pero te cubre ${cubreCount[comp]}. Deben ser iguales.`);
            }
        });

        if (!document.getElementById('comentarios').value.trim()) errores.push('Ingresa un comentario.');
        if (errores.length) { notificar('warning', 'Revisa el formulario', errores.map((e) => `• ${e}`).join('<br>')); return; }

        enviarSolicitud(false);
    });

    function restablecerBoton() {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Enviar Solicitud';
    }

    function avisoRestriccion(restricciones, onContinuar) {
        const items = (restricciones || []).map(function (r) {
            return `<li class="mb-1"><strong>${r.explorador}</strong> — <em>${r.tipo}</em>: ${r.nota}</li>`;
        }).join('');
        const html = `<p>Ten cuidado: hay una <strong>restricción médica</strong> vigente en el rango:</p>
                      <ul class="text-left">${items}</ul>
                      <p class="mt-2">¿Deseas continuar de todos modos?</p>`;
        if (window.Swal) {
            Swal.fire({
                icon: 'warning', title: 'Restricción médica', html: html,
                showCancelButton: true, confirmButtonText: 'Continuar de todos modos',
                cancelButtonText: 'Cancelar', confirmButtonColor: '#d97706',
            }).then(function (res) { if (res.isConfirmed) onContinuar(); else restablecerBoton(); });
        } else {
            if (confirm('Hay una restricción médica vigente. ¿Continuar de todos modos?')) onContinuar();
            else restablecerBoton();
        }
    }

    function enviarSolicitud(confirmarRestriccion) {
        const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
        const fd = new FormData(form);
        if (confirmarRestriccion) fd.set('confirmar_restriccion', '1');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Enviando…';
        // Loading bloqueante: evita doble envío. Cualquier Swal posterior lo reemplaza.
        LoadingUI.mostrar('Enviando solicitud...');

        fetch(URL_PROCESAR, { method: 'POST', headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' }, body: fd })
            .then(async (r) => ({ ok: r.ok, data: await r.json().catch(() => ({})) }))
            .then(({ ok, data }) => {
                if (ok && data.success !== false) {
                    notificar('success', '¡Solicitud enviada!',
                        data.message || 'Doblada permanente solicitada. Se notificó a los compañeros y al supervisor.')
                        .then(() => { window.location.href = '/solicitudes/mis-solicitudes/'; });
                } else if (data && data.code === 'advertencia_restriccion') {
                    // No es un error: pedir confirmación y reenviar con el flag.
                    avisoRestriccion(data.restricciones, function () { enviarSolicitud(true); });
                } else {
                    notificar('error', 'No se pudo enviar', data.error || data.message || 'Error al procesar la solicitud.');
                    restablecerBoton();
                }
            })
            .catch(() => {
                notificar('error', 'Error', 'Ocurrió un error de red. Intenta de nuevo.');
                restablecerBoton();
            });
    }
})();
