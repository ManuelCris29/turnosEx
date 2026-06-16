/**
 * Solicitar Doblada Permanente
 *
 * Acuerdo recurrente entre dos exploradores sobre días fijos de la semana en un
 * rango. El backend valida toda la regla de negocio; aquí solo se cargan los
 * compañeros (jornada contraria), se restringe el rango y se valida lo básico.
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
    const selectReceptor = document.getElementById('empleado_receptor');
    const btn = document.getElementById('btnEnviarDobladaPerm');

    function notificar(icon, title, text) {
        if (window.Swal) return Swal.fire({ icon, title, html: text, confirmButtonText: 'Entendido' });
        alert(`${title}\n\n${(text || '').replace(/<[^>]+>/g, '')}`);
        return Promise.resolve();
    }

    let fpFin = flatpickr(inputFin, { locale: 'es', dateFormat: 'Y-m-d', minDate: 'today' });
    flatpickr(inputInicio, {
        locale: 'es', dateFormat: 'Y-m-d', minDate: 'today',
        onChange: function (sel, str) {
            if (fpFin) fpFin.set('minDate', str || 'today');
            cargarCompaneros(str);
        },
    });

    function cargarCompaneros(fecha) {
        selectReceptor.innerHTML = '<option value="">Cargando…</option>';
        selectReceptor.disabled = true;
        if (!fecha) {
            selectReceptor.innerHTML = '<option value="">Primero elige la fecha de inicio…</option>';
            return;
        }
        fetch(`${URL_EMPLEADOS}?fecha=${encodeURIComponent(fecha)}&tipo_solicitud_id=${tipoId}`,
              { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((data) => {
                const emps = (data && (data.empleados || (data.data && data.data.empleados))) || [];
                if (!emps.length) {
                    selectReceptor.innerHTML = '<option value="">No hay compañeros de jornada contraria</option>';
                    return;
                }
                selectReceptor.innerHTML = '<option value="">Selecciona un compañero…</option>';
                emps.forEach((e) => {
                    const o = document.createElement('option');
                    o.value = e.id; o.textContent = `${e.nombre} ${e.apellido}`;
                    selectReceptor.appendChild(o);
                });
                selectReceptor.disabled = false;
            })
            .catch(() => { selectReceptor.innerHTML = '<option value="">Error cargando compañeros</option>'; });
    }

    function checks(name) {
        return Array.from(form.querySelectorAll(`input[name="${name}"]:checked`)).map((c) => c.value);
    }

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        const ces = checks('dias_cesion');
        const dev = checks('dias_devolucion');
        const errores = [];
        if (!inputInicio.value || !inputFin.value) errores.push('Selecciona el rango de fechas (Desde y Hasta).');
        if (inputInicio.value && inputFin.value && inputFin.value < inputInicio.value) errores.push('La fecha "Hasta" debe ser posterior a "Desde".');
        if (!ces.length) errores.push('Selecciona al menos un día que cedes.');
        if (!dev.length) errores.push('Selecciona al menos un día en que devuelves.');
        if (ces.some((d) => dev.includes(d))) errores.push('Un mismo día no puede ser de cesión y de devolución.');
        if (!selectReceptor.value) errores.push('Selecciona el compañero que te cubrirá.');
        if (!document.getElementById('comentarios').value.trim()) errores.push('Ingresa un comentario.');
        if (errores.length) { notificar('warning', 'Faltan datos', errores.map((e) => `• ${e}`).join('<br>')); return; }

        const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
        const fd = new FormData(form);
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Enviando…';

        fetch(URL_PROCESAR, { method: 'POST', headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' }, body: fd })
            .then(async (r) => ({ ok: r.ok, data: await r.json().catch(() => ({})) }))
            .then(({ ok, data }) => {
                if (ok && data.success !== false) {
                    notificar('success', '¡Solicitud enviada!',
                        data.message || 'Doblada permanente solicitada. Se notificó al compañero y al supervisor.')
                        .then(() => { window.location.href = '/solicitudes/mis-solicitudes/'; });
                } else {
                    notificar('error', 'No se pudo enviar', data.error || data.message || 'Error al procesar la solicitud.');
                    btn.disabled = false; btn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Enviar Solicitud';
                }
            })
            .catch(() => {
                notificar('error', 'Error', 'Ocurrió un error de red. Intenta de nuevo.');
                btn.disabled = false; btn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Enviar Solicitud';
            });
    });
})();
