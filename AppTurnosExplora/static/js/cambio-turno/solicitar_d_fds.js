/**
 * Solicitar Doblada de Fin de Semana (D FDS) — selección por TARJETAS.
 *
 * Flujo:
 *  1. Elegir mes.
 *  2. Ver tarjetas de cada fin de semana con el día que TRABAJAS resaltado.
 *  3. Tocar el finde que cedes (solo los que trabajas un día).
 *  4. Elegir compañero (grupo contrario).
 *  5. Tocar el finde de devolución (mismo día de la semana; donde cubres a tu compañero).
 *  6. Enviar.
 *
 * La lógica de negocio (alternancia, grupos, mismo mes, deudas) la valida el backend.
 */
(function () {
    'use strict';

    const URLs = {
        ALTERNANCIA_MES: '/solicitudes/alternancia-mes/',
        COMPANEROS: '/solicitudes/dfds-companeros/',
        PROCESAR: '/solicitudes/procesar-solicitud/',
    };

    const form = document.getElementById('dfdsForm');
    if (!form) return;

    const tipoId = document.getElementById('tipo_solicitud_id').value;
    const inputCesion = document.getElementById('fecha_solicitud');
    const inputPago = document.getElementById('fecha_pago');
    const selectReceptor = document.getElementById('empleado_receptor');
    const selectorMes = document.getElementById('fds-selector-mes');
    const cardsCesion = document.getElementById('fds-cards-cesion');
    const cardsPago = document.getElementById('fds-cards-pago');
    const compaGroup = document.getElementById('fds-compa-group');
    const pagoGroup = document.getElementById('fds-pago-group');
    const resumen = document.getElementById('fds_resumen');
    const btnEnviar = document.getElementById('btnEnviarDfds');

    let findes = [];         // findes del mes cargado
    let cesionSel = null;    // finde de cesión elegido
    let diaCesion = null;    // 'sabado' | 'domingo'
    let empleadoReceptor = null;

    const NOMBRE_DIA = { sabado: 'sábado', domingo: 'domingo' };
    const ABREV = { sabado: 'Sáb', domingo: 'Dom' };

    function notificar(icon, title, text) {
        if (window.Swal) return Swal.fire({ icon, title, html: text, confirmButtonText: 'Entendido' });
        alert(`${title}\n\n${(text || '').replace(/<[^>]+>/g, '')}`);
        return Promise.resolve();
    }

    // ===================== MES =====================

    function cargarMes(anio, mes) {
        cardsCesion.innerHTML = '<div class="text-muted">Cargando fines de semana…</div>';
        limpiarSeleccion();
        const q = (anio && mes) ? `?anio=${anio}&mes=${mes}` : '';
        fetch(`${URLs.ALTERNANCIA_MES}${q}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((res) => {
                const data = (res && res.data) ? res.data : res;
                if (data.meses && !selectorMes.options.length) poblarMeses(data.meses, data.anio, data.mes);
                findes = data.findes || [];
                renderCesion();
            })
            .catch(() => { cardsCesion.innerHTML = '<div class="alert-warning-info">Error cargando fines de semana.</div>'; });
    }

    function poblarMeses(meses, anioSel, mesSel) {
        selectorMes.innerHTML = '';
        meses.forEach((m) => {
            const o = document.createElement('option');
            o.value = `${m.anio}-${m.mes}`;
            o.textContent = m.label;
            if (m.anio === anioSel && m.mes === mesSel) o.selected = true;
            selectorMes.appendChild(o);
        });
        selectorMes.onchange = function () {
            const [a, mm] = this.value.split('-').map(Number);
            cargarMes(a, mm);
        };
    }

    function limpiarSeleccion() {
        cesionSel = null; diaCesion = null; empleadoReceptor = null;
        inputCesion.value = ''; inputPago.value = ''; selectReceptor.value = '';
        compaGroup.style.display = 'none';
        pagoGroup.style.display = 'none';
        cardsPago.innerHTML = '';
        resumen.style.display = 'none';
    }

    // ===================== TARJETAS =====================

    // Construye una tarjeta de finde. `modo` = 'cesion' | 'pago'.
    function crearCard(f, modo) {
        const card = document.createElement('div');
        card.className = 'fds-card';
        card.dataset.sabado = f.sabado.fecha;

        const rango = `${f.sabado.dia} · ${f.domingo.dia}`;
        let cuerpo, seleccionable, fechaSel;

        if (modo === 'cesion') {
            seleccionable = f.seleccionable;
            fechaSel = f.mi_dia === 'sabado' ? f.sabado.fecha : (f.mi_dia === 'domingo' ? f.domingo.fecha : null);
            if (f.trabaja_ambos) {
                cuerpo = '<div class="fds-nota">Trabajas los dos días — no se puede ceder</div>';
            } else if (f.mi_dia) {
                const mi = f.mi_dia === 'sabado' ? f.sabado : f.domingo;
                const otro = f.mi_dia === 'sabado' ? f.domingo : f.sabado;
                const otroDia = f.mi_dia === 'sabado' ? 'domingo' : 'sabado';
                cuerpo =
                    `<div class="fds-dia-linea mio"><i class="fas fa-user mr-1"></i>` +
                    `Trabajas <strong>${NOMBRE_DIA[f.mi_dia].toUpperCase()} ${mi.dia}</strong> ` +
                    `<span class="jor jor-${mi.jornada}">${mi.jornada || '?'}</span></div>` +
                    `<div class="fds-dia-linea descanso">Descansas ${NOMBRE_DIA[otroDia]} ${otro.dia}</div>`;
            } else {
                cuerpo = '<div class="fds-nota">Descansas todo el finde — nada que ceder</div>';
            }
        } else { // pago
            // Cubres el día de tu compañero (el mismo día que cediste) en este finde.
            const diaObj = diaCesion === 'sabado' ? f.sabado : f.domingo;
            fechaSel = diaObj.fecha;
            // Disponibilidad calculada por renderPago (ambos lados).
            seleccionable = f._pago_ok;
            if (f._pago_ok) {
                cuerpo =
                    `<div class="fds-dia-linea mio"><i class="fas fa-hands-helping mr-1"></i>` +
                    `Cubres <strong>${NOMBRE_DIA[diaCesion].toUpperCase()} ${diaObj.dia}</strong> ` +
                    `<span class="jor jor-${diaObj.jornada}">${diaObj.jornada || '?'}</span> a tu compañero</div>` +
                    `<div class="fds-dia-linea descanso">+ tu día normal — te doblas el finde</div>`;
            } else {
                cuerpo = `<div class="fds-nota">${f._pago_motivo}</div>`;
            }
        }

        card.innerHTML = `<div class="fds-card-fechas">Fin de semana ${rango}</div>` +
                         `<div class="fds-card-body">${cuerpo}</div>`;

        if (!seleccionable) {
            card.classList.add('disabled');
        } else {
            card.addEventListener('click', () => {
                if (modo === 'cesion') seleccionarCesion(f, card, fechaSel);
                else seleccionarPago(f, card, fechaSel);
            });
        }
        return card;
    }

    function renderCesion() {
        cardsCesion.innerHTML = '';
        if (!findes.length) {
            cardsCesion.innerHTML = '<div class="alert-warning-info">Este mes no tiene fines de semana.</div>';
            return;
        }
        const hayElegibles = findes.some((f) => f.seleccionable);
        findes.forEach((f) => cardsCesion.appendChild(crearCard(f, 'cesion')));
        if (!hayElegibles) {
            const aviso = document.createElement('div');
            aviso.className = 'alert-warning-info';
            aviso.innerHTML = 'En este mes no hay un finde donde trabajes un solo día para ceder. Prueba otro mes.';
            cardsCesion.appendChild(aviso);
        }
    }

    function seleccionarCesion(f, card, fechaSel) {
        document.querySelectorAll('#fds-cards-cesion .fds-card').forEach((c) => c.classList.remove('selected'));
        card.classList.add('selected');
        cesionSel = f;
        diaCesion = f.mi_dia;
        inputCesion.value = fechaSel;
        // reset pago/compañero
        inputPago.value = ''; empleadoReceptor = null; selectReceptor.value = '';
        pagoGroup.style.display = 'none';
        resumen.style.display = 'none';
        cargarCompaneros(fechaSel);
        compaGroup.style.display = 'block';
    }

    function renderPago() {
        cardsPago.innerHTML = '';
        const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
        const diaKey = diaCesion === 'sabado' ? 'sabado_mio' : 'domingo_mio';

        // Candidatos: mismo día de la semana que la cesión, otro finde del mes, no pasado.
        // Cada uno se marca disponible o NO (con motivo) mirando AMBOS lados:
        //   - Tú: debes estar LIBRE ese día (para poder cubrirlo).
        //   - Compañero: debe TRABAJAR ese día (para que tú lo cubras) y no doblar los dos.
        const candidatos = findes.filter((f) => {
            if (f.sabado.fecha === cesionSel.sabado.fecha) return false;
            const diaObj = diaCesion === 'sabado' ? f.sabado : f.domingo;
            const [y, m, d] = diaObj.fecha.split('-').map(Number);
            return new Date(y, m - 1, d) >= hoy;
        });

        candidatos.forEach((f) => {
            const diaObj = diaCesion === 'sabado' ? f.sabado : f.domingo;
            const yoLibre = !diaObj.mio;
            const rec = f.receptor || {};
            const recTrabaja = !!rec[diaKey];
            const recAmbos = !!rec.trabaja_ambos;
            if (!yoLibre) {
                f._pago_ok = false; f._pago_motivo = `Ya trabajas ese ${NOMBRE_DIA[diaCesion]} — no puedes doblarte de nuevo`;
            } else if (recAmbos) {
                f._pago_ok = false; f._pago_motivo = 'Tu compañero ya trabaja los dos días — no puede descansar';
            } else if (!recTrabaja) {
                f._pago_ok = false; f._pago_motivo = `Tu compañero no trabaja ese ${NOMBRE_DIA[diaCesion]} — no hay día que cubrir`;
            } else {
                f._pago_ok = true; f._pago_motivo = null;
            }
        });

        if (!candidatos.length) {
            cardsPago.innerHTML = '<div class="alert-warning-info">No hay otro ' +
                NOMBRE_DIA[diaCesion] + ' en este mes para el pago.</div>';
            return;
        }
        candidatos.forEach((f) => cardsPago.appendChild(crearCard(f, 'pago')));
        if (!candidatos.some((f) => f._pago_ok)) {
            const aviso = document.createElement('div');
            aviso.className = 'alert-warning-info';
            aviso.innerHTML = 'Ningún finde de este mes sirve para pagarle a este compañero. ' +
                'Prueba con otro compañero o revisa los motivos en cada tarjeta.';
            cardsPago.appendChild(aviso);
        }
    }

    function seleccionarPago(f, card, fechaSel) {
        document.querySelectorAll('#fds-cards-pago .fds-card').forEach((c) => c.classList.remove('selected'));
        card.classList.add('selected');
        inputPago.value = fechaSel;
        actualizarResumen();
    }

    // ===================== COMPAÑEROS =====================

    function cargarCompaneros(fechaCesion) {
        selectReceptor.innerHTML = '<option value="">Cargando…</option>';
        fetch(`${URLs.COMPANEROS}?fecha=${encodeURIComponent(fechaCesion)}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then((r) => r.json())
            .then((res) => {
                const data = (res && res.data) ? res.data : res;
                const comps = data.companeros || [];
                if (!comps.length) {
                    selectReceptor.innerHTML = '<option value="">No hay compañeros del grupo contrario ese finde</option>';
                    return;
                }
                selectReceptor.innerHTML = '<option value="">Selecciona un compañero…</option>';
                comps.forEach((c) => {
                    const o = document.createElement('option');
                    o.value = c.id;
                    o.dataset.nombre = c.nombre;
                    if (c.disponible) {
                        o.textContent = `${c.nombre} — trabaja ${c.dia} ${c.dia_fecha}`;
                    } else {
                        // Compañero que NO puede cubrir ese finde: visible pero deshabilitado, con motivo.
                        o.textContent = `${c.nombre} — ✕ ${c.motivo}`;
                        o.disabled = true;
                    }
                    selectReceptor.appendChild(o);
                });
            })
            .catch(() => { selectReceptor.innerHTML = '<option value="">Error cargando compañeros</option>'; });
    }

    selectReceptor.addEventListener('change', function () {
        const opt = this.options[this.selectedIndex];
        empleadoReceptor = this.value ? { id: this.value, nombre: opt.dataset.nombre } : null;
        inputPago.value = '';
        resumen.style.display = 'none';
        if (empleadoReceptor) {
            pagoGroup.style.display = 'block';
            cardsPago.innerHTML = '<div class="text-muted">Cargando fines de semana…</div>';
            // Recargar el mes CON el receptor para saber, finde a finde, si él puede recibir el pago.
            const [a, mm] = selectorMes.value.split('-').map(Number);
            fetch(`${URLs.ALTERNANCIA_MES}?anio=${a}&mes=${mm}&receptor_id=${empleadoReceptor.id}`, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
            })
                .then((r) => r.json())
                .then((res) => {
                    const data = (res && res.data) ? res.data : res;
                    findes = data.findes || findes;
                    renderPago();
                })
                .catch(() => renderPago());
        } else {
            pagoGroup.style.display = 'none';
        }
        actualizarResumen();
    });

    function actualizarResumen() {
        if (inputCesion.value && inputPago.value && empleadoReceptor) {
            const fc = fmtLargo(inputCesion.value);
            const fp = fmtLargo(inputPago.value);
            resumen.innerHTML =
                `<i class="fas fa-check-circle mr-1"></i> <strong>${empleadoReceptor.nombre}</strong> se doblará el ` +
                `<strong>${fc}</strong> (tu ${NOMBRE_DIA[diaCesion]}). Tú te doblarás el <strong>${fp}</strong> ` +
                `para devolverle el favor.`;
            resumen.style.display = 'block';
        } else {
            resumen.style.display = 'none';
        }
    }

    function fmtLargo(iso) {
        const [y, m, d] = iso.split('-').map(Number);
        const dt = new Date(y, m - 1, d);
        return `${ABREV[dt.getDay() === 6 ? 'sabado' : 'domingo']} ${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}`;
    }

    // ===================== ENVÍO =====================

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        const errores = [];
        if (!inputCesion.value) errores.push('Selecciona el fin de semana que cedes.');
        if (!selectReceptor.value) errores.push('Selecciona el compañero que se doblará.');
        if (!inputPago.value) errores.push('Selecciona el fin de semana de devolución (pago).');
        if (!document.getElementById('comentarios').value.trim()) errores.push('Ingresa un comentario.');
        if (errores.length) {
            notificar('warning', 'Faltan datos', errores.map((e) => `• ${e}`).join('<br>'));
            return;
        }
        enviar(false);
    });

    function restablecer() {
        btnEnviar.disabled = false;
        btnEnviar.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Enviar Solicitud';
        form.querySelectorAll('input, select, textarea').forEach((el) => { el.disabled = false; });
    }

    function enviar(confirmarRestriccion) {
        const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
        const fd = new FormData(form);
        if (confirmarRestriccion) fd.set('confirmar_restriccion', '1');

        btnEnviar.disabled = true;
        btnEnviar.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Enviando…';
        if (window.LoadingUI) LoadingUI.mostrar('Enviando solicitud...');

        fetch(URLs.PROCESAR, {
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
                    return;
                } else {
                    notificar('error', 'No se pudo enviar', data.error || data.message || 'No se pudo procesar la solicitud.');
                    restablecer();
                }
            })
            .catch(() => { notificar('error', 'Error', 'Ocurrió un error de red. Intenta de nuevo.'); restablecer(); });
    }

    // ===================== INIT =====================
    cargarMes();
})();
