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

    const DIAS = [['0', 'Lunes'], ['1', 'Martes'], ['2', 'Miércoles'], ['3', 'Jueves'], ['4', 'Viernes'], ['5', 'Sábado']];
    let companeros = [];  // [{id, nombre, apellido}]

    function notificar(icon, title, text) {
        if (window.Swal) return Swal.fire({ icon, title, html: text, confirmButtonText: 'Entendido' });
        alert(`${title}\n\n${(text || '').replace(/<[^>]+>/g, '')}`);
        return Promise.resolve();
    }

    let fpInicio = null;
    let fpFin = null;

    // Calendarios Desde/Hasta (festivos/mantenimiento/temporada como en la doblada normal)
    if (window.DatepickerFestivos && window.DatepickerFestivos.inicializar) {
        window.DatepickerFestivos.inicializar({
            input: inputFin, minDate: 'today', bloquearDiasEspeciales: true, permitirFestivos: true, permitirTemporada: true,
        }).then(function (inst) { fpFin = inst; });
        window.DatepickerFestivos.inicializar({
            input: inputInicio, minDate: 'today', bloquearDiasEspeciales: true, permitirFestivos: true, permitirTemporada: true,
            onDateChange: function (str) {
                if (fpFin) fpFin.set('minDate', str || 'today');
                cargarCompaneros(str);
            },
        }).then(function (inst) { fpInicio = inst; });
    } else {
        fpFin = flatpickr(inputFin, { locale: 'es', dateFormat: 'Y-m-d', minDate: 'today' });
        fpInicio = flatpickr(inputInicio, {
            locale: 'es', dateFormat: 'Y-m-d', minDate: 'today',
            onChange: function (sel, str) { if (fpFin) fpFin.set('minDate', str || 'today'); cargarCompaneros(str); },
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
    function refreshDias() {
        const selects = Array.from(form.querySelectorAll('select[name$="_dia"]'));
        selects.forEach(function (sel) {
            const usadosPorOtros = diasUsados(sel);
            const actual = sel.value;  // su propio día nunca está en "usadosPorOtros"
            const opts = DIAS.filter(([v]) => !usadosPorOtros.has(v));
            sel.innerHTML = opts
                .map(([v, n]) => `<option value="${v}"${v === actual ? ' selected' : ''}>${n}</option>`)
                .join('');
            sel.value = actual;
        });
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
        row.className = 'perm-row d-flex align-items-center mb-2';
        row.style.gap = '.5rem';
        const lista = (tipo === 'cesion') ? companeros : companerosEnCesion();
        const usados = diasUsados(null);
        const diaSel = primerDiaLibre();
        const optDiasLibres = DIAS.filter(([v]) => !usados.has(v))
            .map(([v, n]) => `<option value="${v}"${v === diaSel ? ' selected' : ''}>${n}</option>`).join('');
        row.innerHTML =
            `<select class="form-control" name="${tipo}_dia" style="max-width:160px;">${optDiasLibres}</select>` +
            `<select class="form-control" name="${tipo}_companero">${optCompaneros(lista)}</select>` +
            `<button type="button" class="btn btn-sm btn-outline-danger perm-remove" title="Quitar"><i class="fas fa-times"></i></button>`;
        row.querySelector('.perm-remove').addEventListener('click', function () { row.remove(); refreshDias(); });
        row.querySelector('select[name$="_dia"]').addEventListener('change', refreshDias);
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
        if (!hayDiasLibres()) { notificar('info', 'Sin días libres', 'Ya usaste todos los días (lunes a sábado) entre cesión y devolución.'); return; }
        cesionRows.appendChild(nuevaFila('cesion'));
        refreshDias();
    });
    if (btnAddDevolucion) btnAddDevolucion.addEventListener('click', function () {
        const lista = companerosEnCesion();
        if (!lista.length) { notificar('info', 'Primero agrega cesión', 'Agrega al menos un día de cesión con su compañero antes de definir la devolución.'); return; }
        if (!hayDiasLibres()) { notificar('info', 'Sin días libres', 'Ya usaste todos los días (lunes a sábado) entre cesión y devolución.'); return; }
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

        // Sábado por sábado: si el sábado (5) está en cesión y en devolución
        if (diasCes.has('5') && dev.some((r) => r.dia === '5')) errores.push('No puedes ceder y devolver en sábado a la vez (eso es Doblada de Fin de Semana).');

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
