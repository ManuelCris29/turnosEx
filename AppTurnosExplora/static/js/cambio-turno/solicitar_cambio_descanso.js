/**
 * Solicitar Cambio de Día de Descanso (REORGANIZADO).
 *
 * Modalidad FIN DE SEMANA:
 *  - Muestra los próximos fines de semana (ventana de ~10 semanas).
 *  - Eliges la semana de CESIÓN (donde trabajas un día por alternancia).
 *  - Eliges un compañero del grupo contrario.
 *  - Eliges la semana de DEVOLUCIÓN: del mismo mes y donde trabajas el día CONTRARIO.
 *    Esto mantiene tu balance de domingos. Si el mes tiene 5 domingos: advertencia.
 *
 * Modalidad ENTRE SEMANA (Temporada):
 *  - Eliges tu día de descanso de temporada.
 *  - El sistema busca el descanso del grupo contrario en esa misma semana.
 *  - Intercambio DIRECTO (sin devolución).
 */
(function () {
    'use strict';

    const form = document.getElementById('cdForm');
    if (!form) return;

    const URLs = {
        FINDES: '/solicitudes/cambio-descanso-findes/',
        EMPLEADOS: '/solicitudes/obtener-empleados-disponibles/',
        DESCANSOS: '/solicitudes/descansos-semana-usuario/',
        PROCESAR: '/solicitudes/procesar-solicitud/',
    };

    const MI_JORNADA = (window.MI_JORNADA || '').toUpperCase();
    const TIPO_ID = document.getElementById('tipo_solicitud_id').value;

    let modo = 'finde';
    let finesDeSemana = [];      // [{ sabado, domingo, diaTrabajo, seleccionable }] del mes cargado
    let mesesDisponibles = [];   // [{anio, mes, label}]
    let mesSelectorInit = false;
    let mesSemana = null;        // {anio, mes} seleccionado en la modalidad entre semana
    let cesion = null;           // { sabado, domingo, diaTrabajo, fechaTrabajoISO }
    let pago = null;             // idem
    let empleadoReceptor = null;
    let descansoSolicitante = null;  // { fecha } (entre semana)
    let descansoReceptor = null;     // { fecha } (entre semana)

    // ===================== HELPERS =====================

    function toISO(d) {
        const m = String(d.getMonth() + 1).padStart(2, '0');
        const day = String(d.getDate()).padStart(2, '0');
        return d.getFullYear() + '-' + m + '-' + day;
    }
    function parseISO(s) {
        const [y, m, d] = s.split('-').map(Number);
        return new Date(y, m - 1, d);
    }
    function nombreDia(d) {
        return ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'][d.getDay()];
    }
    function fmt(d) { return `${d.getDate()}/${d.getMonth() + 1}`; }

    function lunesDeLaSemana(d) {
        const r = new Date(d);
        const day = r.getDay();
        r.setDate(r.getDate() + (day === 0 ? -6 : 1 - day));
        r.setHours(0, 0, 0, 0);
        return r;
    }
    function notificar(icon, title, html) {
        if (window.Swal) return Swal.fire({ icon, title, html });
        alert(`${title}\n\n${(html || '').replace(/<[^>]+>/g, '')}`);
        return Promise.resolve();
    }

    // ===================== MODO TOGGLE =====================

    document.querySelectorAll('.modo-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            if (this.disabled) return;
            modo = this.dataset.modo;
            document.getElementById('modo_descanso').value = modo;

            document.querySelectorAll('.modo-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            document.getElementById('modo-finde').style.display = modo === 'finde' ? 'block' : 'none';
            document.getElementById('modo-semana').style.display = modo === 'semana' ? 'block' : 'none';

            limpiar();

            const infoBox = document.getElementById('infoBox');
            if (modo === 'finde') {
                infoBox.innerHTML = '<h5 class="mb-1"><i class="fas fa-info-circle mr-2"></i>Fin de semana</h5>' +
                    '<p class="mb-0">Intercambia el día que trabajas: si trabajas sábado, cambias para trabajar domingo (y viceversa). ' +
                    'Es <strong>ida y vuelta</strong> en el mismo mes para que ambos queden con los <strong>mismos domingos</strong>.</p>';
                renderCesionFinde();  // ya hay datos del mes cargado
            } else {
                infoBox.innerHTML = '<h5 class="mb-1"><i class="fas fa-info-circle mr-2"></i>Entre semana (temporada)</h5>' +
                    '<p class="mb-0">En temporada, el supervisor define qué día descansa AM y qué día descansa PM. ' +
                    'Aquí puedes <strong>intercambiar tu día de descanso</strong> con un compañero del grupo contrario ' +
                    '(ej. martes por viernes). Es un intercambio directo, sin devolución.</p>';
                poblarSelectorMesSemana();
                cargarDescansosEntreSemana();
            }
        });
    });

    function limpiar() {
        cesion = null; pago = null; empleadoReceptor = null;
        descansoSolicitante = null; descansoReceptor = null;
        document.getElementById('semanas-cesion').innerHTML = '';
        document.getElementById('semanas-pago').innerHTML = '';
        document.getElementById('descansos-solicitante').innerHTML = '';
        document.getElementById('compa-container-finde').style.display = 'none';
        document.getElementById('grupo-devolucion-finde').style.display = 'none';
        document.getElementById('compa-container-semana').style.display = 'none';
        const _dci = document.getElementById('descanso-contrario-info');
        if (_dci) _dci.style.display = 'none';
        document.getElementById('resumen-box').classList.remove('show');
        document.getElementById('advertencia-domingos').style.display = 'none';
        document.getElementById('fecha_solicitud').value = '';
        document.getElementById('fecha_pago').value = '';
        document.getElementById('empleado_receptor').value = '';
    }

    // ===================== FIN DE SEMANA =====================

    // Carga los fines de semana de un mes según los TURNOS REALES (backend).
    function cargarMes(anio, mes) {
        const cont = document.getElementById('semanas-cesion');
        cont.innerHTML = '<div class="text-muted">Cargando fines de semana…</div>';
        const q = (anio && mes) ? `?anio=${anio}&mes=${mes}` : '';
        return fetch(`${URLs.FINDES}${q}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(r => r.json())
            .then(res => {
                if (res && res.meses && !mesSelectorInit) {
                    mesesDisponibles = res.meses;
                    poblarSelectorMes(res.anio, res.mes);
                    mesSelectorInit = true;
                }
                finesDeSemana = ((res && res.findes) || []).map(f => ({
                    sabado: parseISO(f.sabado),
                    domingo: parseISO(f.domingo),
                    diaTrabajo: f.dia_trabajo,        // 'sabado' | 'domingo' | null
                    seleccionable: f.seleccionable,
                }));
                window._sinTurnosMes = !!(res && res.sin_turnos_mes);
                // Sincronizar el selector con el mes que realmente devolvió el backend
                if (res && res.anio && res.mes) {
                    const sel = document.getElementById('selector-mes');
                    if (sel) sel.value = `${res.anio}-${res.mes}`;
                }
                // Reset selección al cambiar de mes
                cesion = null; pago = null; empleadoReceptor = null;
                document.getElementById('fecha_solicitud').value = '';
                document.getElementById('fecha_pago').value = '';
                document.getElementById('empleado_receptor').value = '';
                document.getElementById('compa-container-finde').style.display = 'none';
                document.getElementById('grupo-devolucion-finde').style.display = 'none';
                document.getElementById('semanas-pago').innerHTML = '';
                document.getElementById('resumen-box').classList.remove('show');
                renderCesionFinde();
            })
            .catch(() => { cont.innerHTML = '<div class="alert-warning-info">Error cargando fines de semana.</div>'; });
    }

    function poblarSelectorMes(anioSel, mesSel) {
        const sel = document.getElementById('selector-mes');
        if (!sel) return;
        sel.innerHTML = '';
        mesesDisponibles.forEach(m => {
            const o = document.createElement('option');
            o.value = `${m.anio}-${m.mes}`;
            o.textContent = m.tiene_turnos ? m.label : `${m.label} (sin turnos publicados)`;
            if (m.anio === anioSel && m.mes === mesSel) o.selected = true;
            sel.appendChild(o);
        });
        sel.onchange = function () {
            const [a, mm] = this.value.split('-').map(Number);
            cargarMes(a, mm);
        };
    }

    function renderCesionFinde() {
        const cont = document.getElementById('semanas-cesion');
        cont.innerHTML = '';

        // Mes sin turnos publicados aún
        if (window._sinTurnosMes) {
            cont.innerHTML = '<div class="alert-warning-info"><i class="fas fa-clock mr-1"></i> ' +
                'Los turnos de este mes aún no están publicados. Elige un mes con turnos publicados.</div>';
            return;
        }
        if (!finesDeSemana.length) {
            cont.innerHTML = '<div class="alert-warning-info">Este mes no tiene fines de semana para mostrar.</div>';
            return;
        }
        const hayElegibles = finesDeSemana.some(f => f.seleccionable);
        finesDeSemana.forEach(f => {
            const card = crearCardSemana(f);
            if (f.seleccionable) {
                card.addEventListener('click', () => seleccionarCesion(f, card));
            }
            cont.appendChild(card);
        });
        if (!hayElegibles) {
            const aviso = document.createElement('div');
            aviso.className = 'alert-warning-info';
            aviso.innerHTML = 'En este mes descansas todos los fines de semana o ya pasaron. Prueba con otro mes.';
            cont.appendChild(aviso);
        }
    }

    function crearCardSemana(f) {
        const card = document.createElement('div');
        card.className = 'semana-card';
        if (!f.seleccionable) card.classList.add('disabled');

        let detalle;
        if (f.diaTrabajo === 'sabado') {
            detalle = '<div class="semana-jor yo">Trabajas SÁBADO</div><div class="semana-jor descanso">Descansas domingo</div>';
        } else if (f.diaTrabajo === 'domingo') {
            detalle = '<div class="semana-jor yo">Trabajas DOMINGO</div><div class="semana-jor descanso">Descansas sábado</div>';
        } else {
            detalle = '<div class="semana-jor neutro">No disponible para cambio</div>';
        }
        card.innerHTML = `
            <div class="semana-fecha">Sáb ${fmt(f.sabado)} · Dom ${fmt(f.domingo)}</div>
            <div class="semana-info">${detalle}</div>`;
        return card;
    }

    function seleccionarCesion(f, card) {
        document.querySelectorAll('#semanas-cesion .semana-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');

        const fechaTrabajo = f.diaTrabajo === 'sabado' ? f.sabado : f.domingo;
        cesion = { ...f, fechaTrabajoISO: toISO(fechaTrabajo) };
        document.getElementById('fecha_solicitud').value = cesion.fechaTrabajoISO;

        // Reset pago/compañero
        pago = null; empleadoReceptor = null;
        document.getElementById('fecha_pago').value = '';
        document.getElementById('empleado_receptor').value = '';
        document.getElementById('resumen-box').classList.remove('show');
        document.getElementById('advertencia-domingos').style.display = 'none';

        cargarCompañerosFinde(cesion.fechaTrabajoISO);
        renderDevolucionFinde();

        document.getElementById('compa-container-finde').style.display = 'block';
        document.getElementById('grupo-devolucion-finde').style.display = 'block';
    }

    function cargarCompañerosFinde(fechaISO) {
        const sel = document.getElementById('select-receptor-finde');
        sel.innerHTML = '<option value="">Cargando…</option>';
        fetch(`${URLs.EMPLEADOS}?fecha=${encodeURIComponent(fechaISO)}&tipo_solicitud_id=${TIPO_ID}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(r => r.json())
            .then(data => {
                const emps = (data && data.empleados) || [];
                if (!emps.length) {
                    sel.innerHTML = '<option value="">No hay compañeros disponibles</option>';
                    return;
                }
                sel.innerHTML = '<option value="">Selecciona un compañero…</option>';
                emps.forEach(e => {
                    const o = document.createElement('option');
                    o.value = e.id;
                    o.textContent = `${e.nombre} ${e.apellido}`;
                    o.dataset.emp = JSON.stringify(e);
                    sel.appendChild(o);
                });
            })
            .catch(() => { sel.innerHTML = '<option value="">Error cargando compañeros</option>'; });
    }

    document.getElementById('select-receptor-finde').addEventListener('change', function () {
        const opt = this.options[this.selectedIndex];
        if (this.value && opt.dataset.emp) {
            empleadoReceptor = JSON.parse(opt.dataset.emp);
            document.getElementById('empleado_receptor').value = empleadoReceptor.id;
        } else {
            empleadoReceptor = null;
            document.getElementById('empleado_receptor').value = '';
        }
        actualizarResumenFinde();
    });

    // Devolución: mismo mes, día de trabajo CONTRARIO, distinta a la cesión.
    function renderDevolucionFinde() {
        const cont = document.getElementById('semanas-pago');
        cont.innerHTML = '';
        if (!cesion) return;

        const mes = cesion.sabado.getMonth();
        const anio = cesion.sabado.getFullYear();
        const diaContrario = cesion.diaTrabajo === 'sabado' ? 'domingo' : 'sabado';

        const opciones = finesDeSemana.filter(f =>
            f.seleccionable &&
            f.diaTrabajo === diaContrario &&
            f.sabado.getMonth() === mes &&
            f.sabado.getFullYear() === anio &&
            toISO(f.sabado) !== toISO(cesion.sabado)
        );

        if (!opciones.length) {
            cont.innerHTML = '<div class="alert-warning-info">No hay otra semana en este mes donde trabajes el día contrario. ' +
                'El intercambio necesita dos findes del mismo mes con días opuestos (sábado ↔ domingo).</div>';
            return;
        }

        opciones.forEach(f => {
            const card = crearCardSemana(f);
            card.addEventListener('click', () => seleccionarPago(f, card));
            cont.appendChild(card);
        });
    }

    function seleccionarPago(f, card) {
        document.querySelectorAll('#semanas-pago .semana-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');

        const fechaTrabajo = f.diaTrabajo === 'sabado' ? f.sabado : f.domingo;
        pago = { ...f, fechaTrabajoISO: toISO(fechaTrabajo) };
        document.getElementById('fecha_pago').value = pago.fechaTrabajoISO;

        validarBalanceDomingos();
        actualizarResumenFinde();
    }

    function validarBalanceDomingos() {
        const adv = document.getElementById('advertencia-domingos');
        const mes = cesion.sabado.getMonth();
        const anio = cesion.sabado.getFullYear();
        let domingos = 0;
        for (let d = 1; d <= 31; d++) {
            const f = new Date(anio, mes, d);
            if (f.getMonth() !== mes) break;
            if (f.getDay() === 0) domingos++;
        }
        if (domingos === 5) {
            adv.innerHTML = '<strong>⚠️ Atención:</strong> Este mes tiene 5 domingos (impar). ' +
                'Uno trabajará 3 domingos y el otro 2. Confirmen ambos antes de continuar.';
            adv.style.display = 'block';
        } else {
            adv.style.display = 'none';
        }
    }

    function actualizarResumenFinde() {
        const resumen = document.getElementById('resumen-box');
        if (!cesion || !pago || !empleadoReceptor) {
            resumen.classList.remove('show');
            return;
        }
        // Día que trabajas HOY en cada finde y el día al que CAMBIAS (el contrario del finde).
        const cesAhora  = cesion.diaTrabajo === 'sabado' ? cesion.sabado : cesion.domingo;
        const cesNuevo  = cesion.diaTrabajo === 'sabado' ? cesion.domingo : cesion.sabado;
        const pagoAhora = pago.diaTrabajo === 'sabado' ? pago.sabado : pago.domingo;
        const pagoNuevo = pago.diaTrabajo === 'sabado' ? pago.domingo : pago.sabado;
        const comp = `${empleadoReceptor.nombre} ${empleadoReceptor.apellido}`;
        resumen.innerHTML =
            `<div class="mb-1"><i class="fas fa-exchange-alt mr-1"></i> Intercambio con <strong>${comp}</strong>:</div>` +
            `<div class="ml-3">• <strong>Semana del cambio:</strong> dejas de trabajar el ` +
                `${nombreDia(cesAhora)} ${fmt(cesAhora)} y pasas a trabajar el ` +
                `<strong>${nombreDia(cesNuevo)} ${fmt(cesNuevo)}</strong>.</div>` +
            `<div class="ml-3">• <strong>Semana de devolución:</strong> dejas de trabajar el ` +
                `${nombreDia(pagoAhora)} ${fmt(pagoAhora)} y pasas a trabajar el ` +
                `<strong>${nombreDia(pagoNuevo)} ${fmt(pagoNuevo)}</strong>.</div>` +
            `<div class="mt-1 text-muted"><small>Tu compañero hace lo contrario. ` +
                `Ambos quedan con los mismos domingos del mes.</small></div>`;
        resumen.classList.add('show');
    }

    // ===================== ENTRE SEMANA =====================

    const MESES_ES = ['', 'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

    function poblarSelectorMesSemana() {
        const sel = document.getElementById('selector-mes-semana');
        if (!sel) return;
        // Reutiliza los meses del finde si ya se cargaron; si no, construye 7 desde hoy.
        let meses = mesesDisponibles;
        if (!meses || !meses.length) {
            meses = [];
            const hoy = new Date(); let y = hoy.getFullYear(); let m = hoy.getMonth() + 1;
            for (let i = 0; i < 7; i++) { meses.push({ anio: y, mes: m, label: `${MESES_ES[m]} ${y}` }); m++; if (m > 12) { m = 1; y++; } }
        }
        sel.innerHTML = '';
        meses.forEach(mm => {
            const o = document.createElement('option');
            o.value = `${mm.anio}-${mm.mes}`;
            o.textContent = mm.label;
            sel.appendChild(o);
        });
        if (!mesSemana) mesSemana = { anio: meses[0].anio, mes: meses[0].mes };
        sel.value = `${mesSemana.anio}-${mesSemana.mes}`;
        sel.onchange = function () {
            const [a, mm] = this.value.split('-').map(Number);
            mesSemana = { anio: a, mes: mm };
            cargarDescansosEntreSemana(a, mm);
        };
    }

    function cargarDescansosEntreSemana(anio, mes) {
        if (!anio || !mes) {
            if (mesSemana) { anio = mesSemana.anio; mes = mesSemana.mes; }
            else { const h = new Date(); anio = h.getFullYear(); mes = h.getMonth() + 1; }
        }
        const cont = document.getElementById('descansos-solicitante');
        cont.innerHTML = '<div class="text-muted">Cargando descansos…</div>';
        const hoy = new Date(); hoy.setHours(0, 0, 0, 0);

        // Reset selección al cambiar de mes
        descansoSolicitante = null; descansoReceptor = null; empleadoReceptor = null;
        document.getElementById('fecha_solicitud').value = '';
        document.getElementById('fecha_pago').value = '';
        document.getElementById('empleado_receptor').value = '';
        document.getElementById('compa-container-semana').style.display = 'none';
        const _dci2 = document.getElementById('descanso-contrario-info');
        if (_dci2) _dci2.style.display = 'none';
        document.getElementById('resumen-box').classList.remove('show');

        fetch(`${URLs.DESCANSOS}?anio=${anio}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(r => r.json())
            .then(data => {
                const descansos = (data && data.descansos) || {};
                // Solo días de TEMPORADA del mes elegido y no pasados.
                const dias = Object.entries(descansos)
                    .filter(([f, motivo]) => {
                        const d = parseISO(f);
                        return motivo === 'temporada' && d.getMonth() + 1 === mes && d.getFullYear() === anio && d >= hoy;
                    })
                    .map(([f]) => f)
                    .sort();
                cont.innerHTML = '';
                if (!dias.length) {
                    cont.innerHTML = '<div class="alert-warning-info">No tienes días de descanso de temporada este mes. ' +
                        'Prueba con otro mes (el intercambio entre semana solo aplica en temporada).</div>';
                    return;
                }
                dias.forEach(f => {
                    const fecha = parseISO(f);
                    const card = document.createElement('div');
                    card.className = 'descanso-card';
                    card.innerHTML = `<div class="descanso-dia">Descansas ${nombreDia(fecha)} ${fmt(fecha)}</div>` +
                        `<div class="descanso-grupo">Tu grupo (${MI_JORNADA})</div>`;
                    card.addEventListener('click', () => seleccionarDescanso(f, card));
                    cont.appendChild(card);
                });
            })
            .catch(() => { cont.innerHTML = '<div class="alert-warning-info">Error cargando descansos.</div>'; });
    }

    function seleccionarDescanso(fecha, card) {
        document.querySelectorAll('#descansos-solicitante .descanso-card').forEach(c => c.classList.remove('selected'));
        card.classList.add('selected');

        descansoSolicitante = { fecha };
        descansoReceptor = null;
        empleadoReceptor = null;
        document.getElementById('fecha_solicitud').value = fecha;
        document.getElementById('fecha_pago').value = '';
        document.getElementById('empleado_receptor').value = '';
        document.getElementById('resumen-box').classList.remove('show');

        buscarDescansoContrario(fecha);
        cargarCompañerosSemana(fecha);
        document.getElementById('compa-container-semana').style.display = 'block';
    }

    // Busca el descanso de temporada del grupo CONTRARIO en la misma semana.
    function buscarDescansoContrario(fecha) {
        const anio = parseISO(fecha).getFullYear();
        const jornadaContraria = MI_JORNADA === 'AM' ? 'PM' : 'AM';
        const lunesRef = lunesDeLaSemana(parseISO(fecha)).getTime();

        fetch(`${URLs.DESCANSOS}?anio=${anio}&jornada=${jornadaContraria}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(r => r.json())
            .then(data => {
                const descansos = (data && data.descansos) || {};
                const match = Object.entries(descansos).find(([f, motivo]) =>
                    motivo === 'temporada' &&
                    f !== fecha &&
                    lunesDeLaSemana(parseISO(f)).getTime() === lunesRef
                );
                const info = document.getElementById('descanso-contrario-info');
                const infoDia = document.getElementById('descanso-contrario-dia');
                if (match) {
                    descansoReceptor = { fecha: match[0] };
                    document.getElementById('fecha_pago').value = match[0];
                    const fp = parseISO(match[0]);
                    if (infoDia) infoDia.textContent = `${nombreDia(fp)} ${fmt(fp)}`;
                    if (info) info.style.display = 'block';
                } else {
                    if (info) info.style.display = 'none';
                }
                actualizarResumenSemana();
            })
            .catch(() => {});
    }

    function cargarCompañerosSemana(fecha) {
        const sel = document.getElementById('select-receptor-semana');
        sel.innerHTML = '<option value="">Cargando…</option>';
        fetch(`${URLs.EMPLEADOS}?fecha=${encodeURIComponent(fecha)}&tipo_solicitud_id=${TIPO_ID}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(r => r.json())
            .then(data => {
                const emps = (data && data.empleados) || [];
                if (!emps.length) {
                    sel.innerHTML = '<option value="">No hay compañeros disponibles</option>';
                    return;
                }
                sel.innerHTML = '<option value="">Selecciona un compañero…</option>';
                emps.forEach(e => {
                    const o = document.createElement('option');
                    o.value = e.id;
                    o.textContent = `${e.nombre} ${e.apellido}`;
                    o.dataset.emp = JSON.stringify(e);
                    sel.appendChild(o);
                });
            })
            .catch(() => { sel.innerHTML = '<option value="">Error cargando compañeros</option>'; });
    }

    document.getElementById('select-receptor-semana').addEventListener('change', function () {
        const opt = this.options[this.selectedIndex];
        if (this.value && opt.dataset.emp) {
            empleadoReceptor = JSON.parse(opt.dataset.emp);
            document.getElementById('empleado_receptor').value = empleadoReceptor.id;
        } else {
            empleadoReceptor = null;
            document.getElementById('empleado_receptor').value = '';
        }
        actualizarResumenSemana();
    });

    function actualizarResumenSemana() {
        const resumen = document.getElementById('resumen-box');
        if (!descansoSolicitante || !descansoReceptor || !empleadoReceptor) {
            resumen.classList.remove('show');
            return;
        }
        const fc = parseISO(descansoSolicitante.fecha);     // tu descanso actual
        const fp = parseISO(descansoReceptor.fecha);        // descanso del compañero
        const compa = `${empleadoReceptor.nombre} ${empleadoReceptor.apellido}`;
        const diaTuyo = `${nombreDia(fc)} ${fmt(fc)}`;
        const diaCompa = `${nombreDia(fp)} ${fmt(fp)}`;
        resumen.innerHTML =
            `<div style="font-weight:600;margin-bottom:6px;"><i class="fas fa-exchange-alt mr-1"></i> Intercambio de descanso</div>` +
            `<div style="margin-bottom:4px;"><span style="color:#64748b;">Ahora:</span> ` +
            `tú descansas <strong>${diaTuyo}</strong> · ${compa} descansa <strong>${diaCompa}</strong></div>` +
            `<div><span style="color:#64748b;">Después del cambio:</span> ` +
            `tú descansarás <strong>${diaCompa}</strong> · ${compa} descansará <strong>${diaTuyo}</strong></div>`;
        resumen.classList.add('show');
    }

    // ===================== SUBMIT =====================

    form.addEventListener('submit', function (ev) {
        ev.preventDefault();
        const errores = [];
        if (!document.getElementById('comentarios').value.trim()) errores.push('Ingresa un comentario.');

        if (modo === 'finde') {
            if (!cesion) errores.push('Selecciona la semana que cambias.');
            if (!empleadoReceptor) errores.push('Selecciona el compañero.');
            if (!pago) errores.push('Selecciona la semana de devolución.');
        } else {
            if (!descansoSolicitante) errores.push('Selecciona tu descanso.');
            if (!descansoReceptor) errores.push('No se encontró un descanso del grupo contrario en esa semana.');
            if (!empleadoReceptor) errores.push('Selecciona el compañero.');
        }

        if (errores.length) {
            notificar('warning', 'Faltan datos', errores.map(e => `• ${e}`).join('<br>'));
            return;
        }
        confirmar();
    });

    function confirmar() {
        const fc = parseISO(document.getElementById('fecha_solicitud').value);
        const fp = parseISO(document.getElementById('fecha_pago').value);
        let html = '<div style="text-align:left;font-size:.95rem;">';
        if (modo === 'finde') {
            html += `<p><strong>Modalidad:</strong> Fin de semana</p>`;
            html += `<p><strong>Cambias:</strong> ${nombreDia(fc)} ${fmt(fc)}</p>`;
            html += `<p><strong>Devuelves:</strong> ${nombreDia(fp)} ${fmt(fp)}</p>`;
        } else {
            html += `<p><strong>Modalidad:</strong> Entre semana</p>`;
            html += `<p><strong>Tu descanso:</strong> ${nombreDia(fc)} ${fmt(fc)}</p>`;
            html += `<p><strong>Descanso del compañero:</strong> ${nombreDia(fp)} ${fmt(fp)}</p>`;
        }
        html += `<p><strong>Compañero:</strong> ${empleadoReceptor.nombre} ${empleadoReceptor.apellido}</p></div>`;

        if (window.Swal) {
            Swal.fire({
                title: '¿Confirmar solicitud?', html, icon: 'question',
                showCancelButton: true, confirmButtonText: 'Sí, enviar',
                cancelButtonText: 'Cancelar', reverseButtons: true
            }).then(r => { if (r.isConfirmed) enviar(); });
        } else if (confirm('¿Enviar esta solicitud?')) {
            enviar();
        }
    }

    function enviar() {
        const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;
        const fd = new FormData(form);
        const btn = document.getElementById('btnEnviarCd');

        // Form Submit Disable (patrón #5)
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Enviando…';
        form.querySelectorAll('input, select, textarea').forEach(el => el.disabled = true);
        document.querySelectorAll('.modo-btn').forEach(el => el.disabled = true);

        if (window.LoadingUI) LoadingUI.mostrar('Enviando solicitud...');

        fetch(URLs.PROCESAR, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
            body: fd
        })
            .then(async r => ({ ok: r.ok, data: await r.json().catch(() => ({})) }))
            .then(({ ok, data }) => {
                if (ok && data.success !== false) {
                    const msg = (data.data && data.data.message) || data.message || 'Solicitud enviada correctamente.';
                    notificar('success', '¡Solicitud enviada!', msg).then(() => {
                        window.location.href = '/solicitudes/mis-solicitudes/';
                    });
                } else {
                    notificar('error', 'No se pudo enviar', data.error || data.message || 'Intenta de nuevo.');
                    rehabilitar();
                }
            })
            .catch(() => { notificar('error', 'Error de red', 'Intenta de nuevo.'); rehabilitar(); });
    }

    function rehabilitar() {
        const btn = document.getElementById('btnEnviarCd');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Enviar Solicitud';
        form.querySelectorAll('input, select, textarea').forEach(el => el.disabled = false);
        document.querySelectorAll('.modo-btn').forEach(el => el.disabled = false);
    }

    // ===================== INIT =====================
    cargarMes();  // carga meses + findes del mes actual

})();
