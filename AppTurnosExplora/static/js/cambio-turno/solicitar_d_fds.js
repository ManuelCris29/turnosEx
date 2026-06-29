/**
 * Solicitar Doblada de Fin de Semana (D FDS)
 *
 * Flujo simple (sin AM/PM):
 *  1. Elegir el fin de semana que se cede (solo sáb/dom, futuro).
 *  2. Cargar compañeros del grupo contrario (endpoint del backend).
 *  3. Elegir el fin de semana de devolución (mismo mes, otro finde).
 *  4. Enviar.
 *
 * Toda la lógica de negocio (alternancia, grupos, mismo mes, deudas) la valida
 * el backend; aquí solo se restringen los selectores y se da feedback básico.
 */
(function () {
    'use strict';

    const URL_EMPLEADOS = '/solicitudes/obtener-empleados-disponibles/';
    const URL_PROCESAR = '/solicitudes/procesar-solicitud/';
    const URL_ALTERNANCIA = '/solicitudes/alternancia-finde/';

    const form = document.getElementById('dfdsForm');
    if (!form) return;

    const tipoId = document.getElementById('tipo_solicitud_id').value;
    const inputCesion = document.getElementById('fecha_solicitud');
    const selectReceptor = document.getElementById('empleado_receptor');
    const inputPago = document.getElementById('fecha_pago');
    const resumen = document.getElementById('fds_resumen');
    const btnEnviar = document.getElementById('btnEnviarDfds');
    const distintivoCesion = document.getElementById('fds_distintivo_cesion');
    const distintivoPago = document.getElementById('fds_distintivo_pago');

    // Día de la semana del finde cedido (0=domingo, 6=sábado) para exigir el mismo en el pago.
    let diaCesion = null;

    // Jornada predeterminada del solicitante (AM/PM), para resaltar "tú eres ...".
    const MI_JORNADA = (window.MI_JORNADA || '').toUpperCase();

    // Pinta el distintivo AM/PM del fin de semana de una fecha en el contenedor dado.
    // El día/jornada que le corresponde al propio solicitante se resalta con una etiqueta "Tú".
    function mostrarDistintivo(contenedor, fechaStr) {
        if (!contenedor) return;
        if (!fechaStr) { contenedor.style.display = 'none'; contenedor.innerHTML = ''; return; }
        fetch(`${URL_ALTERNANCIA}?fecha=${encodeURIComponent(fechaStr)}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((res) => {
                const d = (res && res.data) ? res.data : res;
                if (!d || !d.sabado || !d.domingo) { contenedor.style.display = 'none'; return; }
                // "Tú" se marca según el día que el usuario trabaja REALMENTE (flag `mio` del
                // backend, calculado con la fuente de verdad), no comparando con la jornada base.
                // Así refleja cambios aprobados (p. ej. cambio de descanso que movió el día).
                const chip = (label, dia, jor, mio) => {
                    const esMio = !!mio;
                    const tuTag = esMio ? ` <span class="tu-tag"><i class="fas fa-user"></i> Tú</span>` : '';
                    return `<span class="fds-dia${esMio ? ' es-mio' : ''}">${label} ${dia} ` +
                           `<span class="jor jor-${jor}">${jor || '?'}</span>${tuTag}</span>`;
                };
                contenedor.innerHTML =
                    chip('Sáb', d.sabado.dia, d.sabado.jornada, d.sabado.mio) +
                    chip('Dom', d.domingo.dia, d.domingo.jornada, d.domingo.mio);
                contenedor.style.display = 'flex';
            })
            .catch(() => { contenedor.style.display = 'none'; });
    }

    const esFinde = (d) => d.getDay() === 0 || d.getDay() === 6;
    const soloFindes = [(date) => !esFinde(date)];

    const hoy = new Date();
    hoy.setHours(0, 0, 0, 0);

    function notificar(icon, title, text) {
        if (window.Swal) {
            return Swal.fire({ icon, title, html: text, confirmButtonText: 'Entendido' });
        }
        alert(`${title}\n\n${(text || '').replace(/<[^>]+>/g, '')}`);
        return Promise.resolve();
    }

    // --- Picker de fecha de cesión: solo findes, desde hoy ---
    const fpCesion = flatpickr(inputCesion, {
        locale: 'es',
        dateFormat: 'Y-m-d',
        minDate: 'today',
        disable: soloFindes,
        onChange: onCesionChange,
    });

    // Picker de pago (se reconfigura al elegir cesión)
    let fpPago = flatpickr(inputPago, {
        locale: 'es',
        dateFormat: 'Y-m-d',
        disable: soloFindes,
    });

    function resetReceptorYPago() {
        selectReceptor.innerHTML = '<option value="">Primero selecciona el fin de semana…</option>';
        selectReceptor.disabled = true;
        inputPago.value = '';
        inputPago.disabled = true;
        resumen.style.display = 'none';
        if (distintivoPago) { distintivoPago.style.display = 'none'; distintivoPago.innerHTML = ''; }
    }

    function onCesionChange(selectedDates, dateStr) {
        resetReceptorYPago();
        if (!dateStr) {
            if (distintivoCesion) { distintivoCesion.style.display = 'none'; distintivoCesion.innerHTML = ''; }
            diaCesion = null;
            return;
        }
        diaCesion = selectedDates[0].getDay();  // 0=domingo, 6=sábado
        mostrarDistintivo(distintivoCesion, dateStr);
        cargarCompaneros(dateStr);
        configurarPagoMismoMes(selectedDates[0], dateStr);
    }

    function configurarPagoMismoMes(fechaCesion, cesionStr) {
        const y = fechaCesion.getFullYear();
        const m = fechaCesion.getMonth();
        const primero = new Date(y, m, 1);
        const ultimo = new Date(y, m + 1, 0);
        const minDate = primero < hoy ? hoy : primero;

        if (fpPago) fpPago.destroy();
        fpPago = flatpickr(inputPago, {
            locale: 'es',
            dateFormat: 'Y-m-d',
            minDate: minDate,
            maxDate: ultimo,
            // Solo el MISMO día de la semana que la cesión (sáb→sáb, dom→dom) y nunca la propia cesión.
            disable: [
                (date) => date.getDay() !== diaCesion,
                cesionStr,
            ],
            onChange: actualizarResumen,
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
                    selectReceptor.disabled = true;
                    return;
                }
                selectReceptor.innerHTML = '<option value="">Selecciona un compañero…</option>';
                empleados.forEach((e) => {
                    const opt = document.createElement('option');
                    opt.value = e.id;
                    opt.textContent = `${e.nombre} ${e.apellido}`;
                    selectReceptor.appendChild(opt);
                });
                selectReceptor.disabled = false;
            })
            .catch(() => {
                selectReceptor.innerHTML = '<option value="">Error cargando compañeros</option>';
                selectReceptor.disabled = true;
            });
        selectReceptor.onchange = actualizarResumen;
    }

    function actualizarResumen() {
        const ces = inputCesion.value;
        const pago = inputPago.value;
        const comp = selectReceptor.options[selectReceptor.selectedIndex];
        mostrarDistintivo(distintivoPago, pago);
        if (ces && pago && selectReceptor.value) {
            resumen.innerHTML =
                `<i class="fas fa-check-circle me-1"></i> <strong>${comp.textContent}</strong> se doblará el ` +
                `<strong>${ces}</strong>. Tú te doblarás el <strong>${pago}</strong> para devolverle el favor.`;
            resumen.style.display = 'block';
        } else {
            resumen.style.display = 'none';
        }
    }

    // --- Envío ---
    form.addEventListener('submit', function (ev) {
        ev.preventDefault();

        const errores = [];
        if (!inputCesion.value) errores.push('Selecciona el fin de semana que cedes.');
        if (!selectReceptor.value) errores.push('Selecciona el compañero que se doblará.');
        if (!inputPago.value) errores.push('Selecciona el fin de semana de devolución (pago).');
        if (!document.getElementById('comentarios').value.trim()) errores.push('Ingresa un comentario.');
        if (inputCesion.value && inputPago.value && inputCesion.value === inputPago.value) {
            errores.push('La fecha de pago debe ser un fin de semana distinto al de cesión.');
        }
        if (errores.length) {
            notificar('warning', 'Faltan datos', errores.map((e) => `• ${e}`).join('<br>'));
            return;
        }

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

            fetch(URL_PROCESAR, {
                method: 'POST',
                headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
                body: fd,
            })
                .then(async (r) => ({ ok: r.ok, data: await r.json().catch(() => ({})) }))
                .then(({ ok, data }) => {
                    const success = ok && (data.success !== false);
                    if (success) {
                        const msg = (data.data && data.data.message) || data.message ||
                            'Solicitud de doblada de fin de semana enviada correctamente.';
                        notificar('success', '¡Solicitud enviada!', msg).then(() => {
                            window.location.href = '/solicitudes/mis-solicitudes/';
                        });
                    } else if (window.RestriccionAdvertencia &&
                               RestriccionAdvertencia.manejar(data, function () { enviar(true); }, restablecer)) {
                        return;  // advertencia de restricción: ya se mostró el aviso
                    } else {
                        const msg = data.error || data.message || 'No se pudo procesar la solicitud.';
                        notificar('error', 'No se pudo enviar', msg);
                        restablecer();
                    }
                })
                .catch(() => {
                    notificar('error', 'Error', 'Ocurrió un error de red. Intenta de nuevo.');
                    restablecer();
                });
        }
    });
})();
