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
        COMPANEROS_FINDE: '/solicitudes/dfds-companeros/',
        DESCANSOS: '/solicitudes/descansos-semana-usuario/',
        PROCESAR: '/solicitudes/procesar-solicitud/',
        DOBLADAS_SEMANA: '/solicitudes/dobladas-semana/',
        COBERTURA_CANDIDATOS: '/solicitudes/cobertura-candidatos/',
        COINCIDENCIA: '/solicitudes/verificar-coincidencia-jornadas/',
        PERMISO_MEDIA_JORNADA: '/permisos/permisos-especiales/media-jornada/create/',
    };

    const MI_JORNADA = (window.MI_JORNADA || '').toUpperCase();
    const MI_EMPLEADO_ID = window.MI_EMPLEADO_ID || '';
    const TIPO_ID = document.getElementById('tipo_solicitud_id').value;

    let modo = 'finde';
    let finesDeSemana = [];      // [{ sabado, domingo, diaTrabajo, seleccionable }] del mes cargado
    let mesesDisponibles = [];   // [{anio, mes, label}]
    let mesSelectorInit = false;
    let mesSemana = null;        // {anio, mes} seleccionado en la modalidad entre semana
    let cesion = null;           // { sabado, domingo, diaTrabajo, fechaTrabajoISO }
    let pago = null;             // idem
    let empleadoReceptor = null;
    let cargaCompañerosToken = 0;    // descarta respuestas de cargas de compañeros ya superadas
    let descansoSolicitante = null;  // { fecha } (entre semana): MI día de descanso
    let descansoReceptor = null;     // { fecha } (entre semana): descanso del contrario = MI día de TRABAJO completo

    // Sub-modalidades entre semana (temporada)
    let subtipoSemana = null;        // intercambio_dia | jornadas_partidas | cobertura_misma_semana | cambio_doblada | permiso_media_jornada
    let jpJornada = null;            // jornadas_partidas: jornada que tomo yo (AM/PM)
    let cobOpcion = null;            // cobertura: AM | PM | DOS (el día completo con 1 compañero se quitó: lo cubre "Intercambiar el día")
    let cobDiaPago = null;           // cobertura: ISO del día de pago
    let empleadoReceptor2 = null;    // cobertura DOS: segundo compañero (cubre PM)
    let coberturaBloqueoCT = false;  // cobertura: pago con misma jornada → hay que hacer un CT sencillo
    let miJornadaPago = null;        // cobertura: mi jornada en el día de pago (para "tú tienes X")
    let cobJornadaPago = null;       // cobertura: jornada elegida para pagar (AM/PM) cuando estoy libre
    let cobCandidato1 = null;        // cobertura: candidato del slot 1 seleccionado (para refrescar info)
    let cobPagoImposible = false;    // cobertura: ya doblo el día de pago → no me queda jornada para pagar
    let dobladaSel = null;           // cambio_doblada: {empleado_id, nombre, fecha}
    let permJornada = null;          // permiso: jornada que trabajo mi día completo

    function miDiaTrabajo() { return descansoReceptor ? descansoReceptor.fecha : null; }
    function miDescanso() { return descansoSolicitante ? descansoSolicitante.fecha : null; }

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

    // OJO: solo los botones de modalidad reales (con data-modo). Los sub-botones de
    // las opciones entre semana (jp-jornada, cob-opcion, perm-jornada) reutilizan la
    // clase .modo-btn solo por estilo y tienen sus propios handlers.
    document.querySelectorAll('.modo-btn[data-modo]').forEach(btn => {
        btn.addEventListener('click', function () {
            if (this.disabled) return;
            modo = this.dataset.modo;
            document.getElementById('modo_descanso').value = modo;

            document.querySelectorAll('.modo-btn[data-modo]').forEach(b => b.classList.remove('active'));
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
        resetSubtipos();
    }

    function resetSubtipos() {
        subtipoSemana = null; jpJornada = null; cobOpcion = null; cobDiaPago = null;
        empleadoReceptor2 = null; dobladaSel = null; permJornada = null;
        const st = document.getElementById('subtipo-semana-container');
        if (st) st.style.display = 'none';
        document.querySelectorAll('.subtipo-card').forEach(c => c.classList.remove('selected'));
        document.querySelectorAll('.subtipo-bloque').forEach(b => b.style.display = 'none');
        document.querySelectorAll('.jp-jornada, .cob-opcion, .perm-jornada').forEach(b => b.classList.remove('active'));
        const sm = document.getElementById('submodalidad_semana');
        if (sm) sm.value = '';
        const tc = document.getElementById('tipo_cesion_input');
        if (tc) tc.value = '';
        const jc = document.getElementById('jornada_cedida_input');
        if (jc) jc.value = '';
        const c2 = document.getElementById('cob-companero-2');
        if (c2) c2.style.display = 'none';
        const adp = document.getElementById('cob-dia-pago-grupo');
        if (adp) adp.style.display = 'none';
        const av = document.getElementById('aviso-deuda-cob');
        if (av) av.style.display = 'none';
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
                    motivo: f.motivo,                 // razón si NO es seleccionable
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
        // Deshabilitado: mostrar el MOTIVO (igual que en D FDS), no solo "no disponible".
        if (!f.seleccionable) {
            detalle = `<div class="semana-jor neutro">${f.motivo || 'No disponible para cambio'}</div>`;
        } else if (f.diaTrabajo === 'sabado') {
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
        // Endpoint con DISPONIBILIDAD por finde: muestra el día del compañero y deshabilita,
        // con motivo, a quien no puede intercambiar (p. ej. ya trabaja los dos días).
        fetch(`${URLs.COMPANEROS_FINDE}?fecha=${encodeURIComponent(fechaISO)}&tipo_solicitud_id=${TIPO_ID}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(r => r.json())
            .then(res => {
                const data = (res && res.data) ? res.data : res;
                const comps = data.companeros || [];
                if (!comps.length) {
                    sel.innerHTML = '<option value="">No hay compañeros del grupo contrario</option>';
                    return;
                }
                sel.innerHTML = '<option value="">Selecciona un compañero…</option>';
                comps.forEach(c => {
                    const o = document.createElement('option');
                    o.value = c.id;
                    o.dataset.emp = JSON.stringify({ id: c.id, nombre: c.nombre, apellido: '' });
                    if (c.disponible) {
                        // `etiqueta` la manda el backend según el tipo de cambio; para el
                        // intercambio sigue siendo "trabaja <el otro día del finde>".
                        o.textContent = `${c.nombre} — ${c.etiqueta || `trabaja ${c.dia} ${c.dia_fecha}`}`;
                    } else {
                        o.textContent = `${c.nombre} — ✕ ${c.motivo}`;
                        o.disabled = true;
                    }
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
        const _sinc2 = document.getElementById('sin-descanso-contrario');
        if (_sinc2) _sinc2.style.display = 'none';
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
                    // ¿Está vacío porque el (único) día de temporada del mes YA se cambió?
                    // En ese caso lo explicamos con el/los compañero(s) para que no parezca un error.
                    const cambios = (data && data.cambios_temporada) || {};
                    const cambiosMes = Object.entries(cambios)
                        .filter(([f]) => { const d = parseISO(f); return d.getMonth() + 1 === mes && d.getFullYear() === anio; })
                        .sort();
                    if (cambiosMes.length) {
                        const items = cambiosMes.map(([f, nombres]) => {
                            const d = parseISO(f);
                            const conQuien = (nombres && nombres.length) ? ` con ${nombres.join(' y ')}` : '';
                            return `<li>${nombreDia(d)} ${fmt(d)}${conQuien}</li>`;
                        }).join('');
                        cont.innerHTML = '<div class="alert-warning-info">' +
                            '<strong>Ya hiciste el cambio de descanso de temporada de este mes.</strong>' +
                            `<ul class="mb-1 mt-1">${items}</ul>` +
                            'Por eso no aparece disponible para intercambiar (no es un error). ' +
                            'Si necesitas otro cambio, elige otro mes con día de temporada.</div>';
                        return;
                    }
                    // ¿Está vacío porque usó su día de temporada en un permiso de media jornada?
                    const permisos = (data && data.permisos_temporada) || {};
                    const permMes = Object.entries(permisos)
                        .filter(([f]) => { const d = parseISO(f); return d.getMonth() + 1 === mes && d.getFullYear() === anio; })
                        .sort();
                    if (permMes.length) {
                        const items = permMes.map(([fcomp, info]) => {
                            const dC = parseISO(fcomp);
                            const jt = (info.jornada_trabaja || '').toUpperCase();
                            const otra = jt === 'AM' ? 'PM' : (jt === 'PM' ? 'AM' : '');
                            const dT = info.fecha_trabajo ? parseISO(info.fecha_trabajo) : null;
                            const trabajoTxt = (dT && jt) ? `trabajas <strong>${jt}</strong> el ${nombreDia(dT)} ${fmt(dT)}` : 'trabajas media jornada';
                            const compTxt = otra ? ` y <strong>${otra}</strong> el ${nombreDia(dC)} ${fmt(dC)}` : ` y la otra media el ${nombreDia(dC)} ${fmt(dC)}`;
                            return `<li>${trabajoTxt}${compTxt}</li>`;
                        }).join('');
                        cont.innerHTML = '<div class="alert-warning-info">' +
                            '<strong>Usaste tu día de temporada en un permiso de media jornada.</strong>' +
                            `<ul class="mb-1 mt-1">${items}</ul>` +
                            'Por eso no tienes un día de descanso libre este mes para intercambiar (no es un error).</div>';
                        return;
                    }
                    cont.innerHTML = '<div class="alert-warning-info">No tienes días de descanso de temporada este mes. ' +
                        'Prueba con otro mes (el intercambio entre semana solo aplica en temporada).</div>';
                    return;
                }
                dias.forEach(f => {
                    const fecha = parseISO(f);
                    const card = document.createElement('div');
                    // Color por grupo (convención anual): tu descanso lleva el color de TU jornada
                    // (AM = azul, PM = amarillo).
                    card.className = 'descanso-card grupo-' + MI_JORNADA.toLowerCase();
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
        resetSubtipos();

        // `cargarCompañerosSemana` NO se llama aquí: necesita la fecha_pago (el descanso del grupo
        // contrario en esta semana), que solo se conoce dentro de `buscarDescansoContrario`. Antes
        // se llamaba con `fecha` —MI descanso— y el desplegable ofrecía compañeros que la
        // validación rechazaba luego por su estado en la OTRA fecha.
        buscarDescansoContrario(fecha);
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
                const subCont = document.getElementById('subtipo-semana-container');
                if (match) {
                    descansoReceptor = { fecha: match[0] };
                    document.getElementById('fecha_pago').value = match[0];
                    const fp = parseISO(match[0]);
                    if (infoDia) infoDia.textContent = `${nombreDia(fp)} ${fmt(fp)} — trabajas TODO el día`;
                    // Tu día de trabajo es cuando descansa el grupo CONTRARIO: la tarjeta lleva
                    // el color de ese grupo (AM = azul, PM = amarillo).
                    const contCard = document.querySelector('#descanso-contrario-info .descanso-contrario-card');
                    if (contCard) {
                        contCard.classList.remove('grupo-am', 'grupo-pm');
                        contCard.classList.add('grupo-' + jornadaContraria.toLowerCase());
                    }
                    if (info) info.style.display = 'block';
                    if (subCont) subCont.style.display = 'block';
                    const _sinc = document.getElementById('sin-descanso-contrario');
                    if (_sinc) _sinc.style.display = 'none';
                    // Ya se conoce la fecha_pago: los compañeros se piden filtrados por ELLA
                    // (deben seguir descansando ese día), no por mi propio descanso.
                    cargarCompañerosSemana(fecha, match[0]);
                } else {
                    // No hay descanso del grupo contrario esa semana → no se puede intercambiar.
                    // En vez de ocultar todo en silencio (parece que "no hace nada"), avisamos.
                    if (info) info.style.display = 'none';
                    if (subCont) subCont.style.display = 'none';
                    const _compa = document.getElementById('compa-container-semana');
                    if (_compa) _compa.style.display = 'none';
                    const _sinc = document.getElementById('sin-descanso-contrario');
                    if (_sinc) _sinc.style.display = 'block';
                    descansoReceptor = null;
                    document.getElementById('fecha_pago').value = '';
                }
                actualizarResumenSemana();
            })
            .catch(() => {});
    }

    // `fechaPago` = el descanso del grupo contrario en esta semana. El servidor excluye a quien
    // ya NO descanse ese día (misma comprobación que la validación al enviar), para no ofrecer
    // compañeros que luego se rechazan con "Tu compañero ya no descansa el ...".
    function cargarCompañerosSemana(fecha, fechaPago) {
        const sel = document.getElementById('select-receptor-semana');
        // Lo que hubiera elegido el usuario antes de repoblar: si sigue estando en la lista nueva
        // se le devuelve la selección, en vez de dejársela borrada sin avisar.
        const previo = sel.value;
        sel.innerHTML = '<option value="">Cargando…</option>';
        let url = `${URLs.EMPLEADOS}?fecha=${encodeURIComponent(fecha)}&tipo_solicitud_id=${TIPO_ID}`;
        if (fechaPago) url += `&fecha_descanso_receptor=${encodeURIComponent(fechaPago)}`;
        // Solo la respuesta de la ÚLTIMA petición puede pintar el select: al mover esta carga
        // detrás de `buscarDescansoContrario` son dos fetch encadenados, y dos cambios seguidos
        // de descanso dejaban en vuelo dos respuestas cuyo orden de llegada no está garantizado.
        const token = ++cargaCompañerosToken;
        fetch(url, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(r => r.json())
            .then(data => {
                if (token !== cargaCompañerosToken) return;  // llegó tarde: la ignoramos
                const emps = (data && data.empleados) || [];
                if (!emps.length) {
                    sel.innerHTML = '<option value="">Ningún compañero descansa ese día</option>';
                    sincronizarReceptorSemana();
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
                if (previo && sel.querySelector(`option[value="${previo}"]`)) sel.value = previo;
                sincronizarReceptorSemana();
            })
            .catch(() => {
                if (token !== cargaCompañerosToken) return;
                sel.innerHTML = '<option value="">Error cargando compañeros</option>';
                sincronizarReceptorSemana();
            });
    }

    /**
     * Deja `empleadoReceptor` y el input oculto en SINCRONÍA con lo que muestra el select.
     *
     * El select es la única fuente de verdad. Antes `empleadoReceptor` solo se actualizaba en el
     * evento `change`, que NO se dispara cuando la lista se repuebla o se restaura la selección
     * por código: el usuario veía a su compañero elegido y el envío respondía "Selecciona el
     * compañero". Se llama al repoblar, al cambiar y antes de validar.
     */
    function sincronizarReceptorSemana() {
        const sel = document.getElementById('select-receptor-semana');
        const opt = sel.options[sel.selectedIndex];
        if (sel.value && opt && opt.dataset.emp) {
            empleadoReceptor = JSON.parse(opt.dataset.emp);
            document.getElementById('empleado_receptor').value = empleadoReceptor.id;
        } else {
            empleadoReceptor = null;
            document.getElementById('empleado_receptor').value = '';
        }
        actualizarResumenSemana();
    }

    document.getElementById('select-receptor-semana').addEventListener('change', sincronizarReceptorSemana);

    function actualizarResumenSemana() {
        const resumen = document.getElementById('resumen-box');
        if (!descansoSolicitante || !descansoReceptor || !subtipoSemana) {
            resumen.classList.remove('show');
            return;
        }
        const fDesc = parseISO(miDescanso());       // mi descanso
        const fTrab = parseISO(miDiaTrabajo());     // mi día de trabajo completo
        const dDesc = `${nombreDia(fDesc)} ${fmt(fDesc)}`;
        const dTrab = `${nombreDia(fTrab)} ${fmt(fTrab)}`;
        const compa = empleadoReceptor ? `${empleadoReceptor.nombre} ${empleadoReceptor.apellido}` : null;
        let html = '';

        if (subtipoSemana === 'intercambio_dia') {
            if (!compa) { resumen.classList.remove('show'); return; }
            html = `<div style="font-weight:600;margin-bottom:6px;"><i class="fas fa-exchange-alt mr-1"></i> Intercambio de descanso</div>` +
                `<div style="margin-bottom:4px;"><span style="color:#64748b;">Ahora:</span> ` +
                `tú descansas <strong>${dDesc}</strong> · ${compa} descansa <strong>${dTrab}</strong></div>` +
                `<div><span style="color:#64748b;">Después del cambio:</span> ` +
                `tú descansarás <strong>${dTrab}</strong> · ${compa} descansará <strong>${dDesc}</strong>. Sin deuda.</div>`;
        } else if (subtipoSemana === 'jornadas_partidas') {
            if (!compa || !jpJornada) { resumen.classList.remove('show'); return; }
            const otra = jpJornada === 'AM' ? 'PM' : 'AM';
            html = `<div style="font-weight:600;margin-bottom:6px;"><i class="fas fa-adjust mr-1"></i> Jornadas partidas</div>` +
                `<div>Tú trabajas <strong>${jpJornada}</strong> el ${dTrab} y el ${dDesc}. ` +
                `${compa} trabaja <strong>${otra}</strong> ambos días. Sin deuda.</div>`;
        } else if (subtipoSemana === 'cobertura_misma_semana') {
            if (!cobOpcion || !cobDiaPago) { resumen.classList.remove('show'); return; }
            const fPago = parseISO(cobDiaPago);
            const dPago = `${nombreDia(fPago)} ${fmt(fPago)}`;
            if (cobOpcion === 'DOS') {
                const compa2 = empleadoReceptor2 ? `${empleadoReceptor2.nombre} ${empleadoReceptor2.apellido}` : null;
                if (!compa || !compa2) { resumen.classList.remove('show'); return; }
                html = `<div style="font-weight:600;margin-bottom:6px;"><i class="fas fa-hands-helping mr-1"></i> Cobertura (2 compañeros)</div>` +
                    `<div>El ${dTrab}: <strong>${compa}</strong> cubre AM y <strong>${compa2}</strong> cubre PM.</div>` +
                    `<div>El ${dPago} pagas a cada uno su media jornada. Se crean <strong>2 solicitudes</strong>.</div>`;
            } else {
                if (!compa) { resumen.classList.remove('show'); return; }
                const que = `la jornada ${cobOpcion}`;
                html = `<div style="font-weight:600;margin-bottom:6px;"><i class="fas fa-hands-helping mr-1"></i> Cobertura misma semana</div>` +
                    `<div>El ${dTrab}: <strong>${compa}</strong> te cubre ${que}.</div>` +
                    `<div>El ${dPago} le pagas lo equivalente.</div>`;
            }
        } else if (subtipoSemana === 'cambio_doblada') {
            if (!dobladaSel) { resumen.classList.remove('show'); return; }
            const fDob = parseISO(dobladaSel.fecha);
            html = `<div style="font-weight:600;margin-bottom:6px;"><i class="fas fa-retweet mr-1"></i> Cambio de doblada</div>` +
                `<div>Tú tomas la doblada de <strong>${dobladaSel.nombre}</strong> el ` +
                `<strong>${nombreDia(fDob)} ${fmt(fDob)}</strong> y él toma tu día completo del ${dTrab}. ` +
                `Sin deuda nueva (ambos ya doblaban).</div>`;
        } else if (subtipoSemana === 'permiso_media_jornada') {
            if (!permJornada) { resumen.classList.remove('show'); return; }
            const otra = permJornada === 'AM' ? 'PM' : 'AM';
            html = `<div style="font-weight:600;margin-bottom:6px;"><i class="fas fa-file-signature mr-1"></i> Permiso media jornada (temporada)</div>` +
                `<div>Trabajas <strong>${permJornada}</strong> el ${dTrab} y <strong>${otra}</strong> el ${dDesc}. ` +
                `Lo aprueba tu supervisor como PERMISO. Sin deuda.</div>`;
        }
        resumen.innerHTML = html;
        resumen.classList.add('show');
    }

    // ============== SUB-TIPOS ENTRE SEMANA (temporada) ==============

    document.querySelectorAll('.subtipo-card').forEach(card => {
        card.addEventListener('click', function () {
            document.querySelectorAll('.subtipo-card').forEach(c => c.classList.remove('selected'));
            this.classList.add('selected');
            seleccionarSubtipo(this.dataset.subtipo);
        });
    });

    function seleccionarSubtipo(st) {
        subtipoSemana = st;
        jpJornada = null; cobOpcion = null; cobDiaPago = null;
        empleadoReceptor2 = null; dobladaSel = null; permJornada = null;
        document.querySelectorAll('.jp-jornada, .cob-opcion, .perm-jornada').forEach(b => b.classList.remove('active'));
        document.getElementById('submodalidad_semana').value = st === 'permiso_media_jornada' ? '' : st;
        document.getElementById('resumen-box').classList.remove('show');

        // Bloques específicos
        document.querySelectorAll('.subtipo-bloque').forEach(b => b.style.display = 'none');
        const bloques = {
            jornadas_partidas: 'bloque-jornadas-partidas',
            cobertura_misma_semana: 'bloque-cobertura',
            cambio_doblada: 'bloque-cambio-doblada',
            permiso_media_jornada: 'bloque-permiso',
        };
        if (bloques[st]) document.getElementById(bloques[st]).style.display = 'block';

        // Reset del sub-flujo de cobertura (tarjetas) al cambiar de sub-tipo.
        empleadoReceptor2 = null; coberturaBloqueoCT = false; cobPagoImposible = false;
        cobJornadaPago = null; cobCandidato1 = null;
        ['cob-candidatos-grupo', 'cob-candidatos-2-grupo', 'cob-dia-pago-grupo', 'cob-jornada-pago-grupo',
         'aviso-deuda-cob', 'cob-aviso-ct', 'cob-mi-jornada-pago', 'cob-info-1', 'cob-info-2'].forEach(id => {
            const el = document.getElementById(id); if (el) el.style.display = 'none';
        });

        // Compañero: en COBERTURA se elige con tarjetas (no el select compartido); en
        // cambio_doblada viene de la doblada y en permiso no aplica.
        const compa = document.getElementById('compa-container-semana');
        const label = document.getElementById('label-receptor-semana');
        const hint = document.getElementById('hint-receptor-semana');
        if (st === 'cambio_doblada' || st === 'permiso_media_jornada' || st === 'cobertura_misma_semana') {
            compa.style.display = 'none';
        } else {
            compa.style.display = 'block';
            if (st === 'intercambio_dia') {
                label.innerHTML = '<i class="fas fa-user mr-1"></i>Compañero (intercambia su descanso) <span class="text-danger">*</span>';
                hint.textContent = 'Compañeros del grupo contrario que descansan tu día de trabajo.';
            } else if (st === 'jornadas_partidas') {
                label.innerHTML = '<i class="fas fa-user mr-1"></i>Compañero (parte jornadas contigo) <span class="text-danger">*</span>';
                hint.textContent = 'Compañero del grupo contrario: trabajará la jornada contraria ambos días.';
            } else {
                label.innerHTML = '<i class="fas fa-user mr-1"></i>Compañero que te cubre ' +
                    '<span id="cob-label-jornada"></span> <span class="text-danger">*</span>';
                hint.textContent = 'Si al cubrir queda con AM y PM el mismo día, el sistema le calcula la deuda de 30 min.';
            }
        }

        if (st === 'cambio_doblada') cargarDobladasSemana();
        if (st === 'cobertura_misma_semana') poblarDiasPagoCobertura();
        actualizarResumenSemana();
    }

    // --- jornadas partidas: jornada que tomo yo ---
    document.querySelectorAll('.jp-jornada').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.jp-jornada').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            jpJornada = this.dataset.jornada;
            document.getElementById('jornada_cedida_input').value = jpJornada;
            actualizarResumenSemana();
        });
    });

    // --- cobertura: qué me cubren + día de pago ---
    document.querySelectorAll('.cob-opcion').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.cob-opcion').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            cobOpcion = this.dataset.cob;
            // Reset de selección de compañeros al cambiar de opción.
            empleadoReceptor = null; empleadoReceptor2 = null; coberturaBloqueoCT = false;
            cobJornadaPago = null; cobCandidato1 = null; cobPagoImposible = false;
            document.getElementById('empleado_receptor').value = '';
            document.getElementById('cob-aviso-ct').style.display = 'none';
            document.getElementById('cob-jornada-pago-grupo').style.display = 'none';
            document.getElementById('cob-dia-pago-grupo').style.display = 'block';
            const lbl = document.getElementById('cob-candidatos-label');
            if (lbl) lbl.innerHTML = cobOpcion === 'DOS'
                ? '<i class="fas fa-user mr-1"></i>Compañero que cubre la AM <span class="text-danger">*</span>'
                : `<i class="fas fa-user mr-1"></i>Compañero que te cubre (la ${cobOpcion}) <span class="text-danger">*</span>`;
            const aviso = document.getElementById('aviso-deuda-cob');
            aviso.style.display = 'block';
            aviso.innerHTML = '<i class="fas fa-info-circle mr-1"></i> <strong>Deuda de 30 min:</strong> solo la debe ' +
                'quien termine doblando sobre su PROPIA jornada (tú al pagar en un día donde ya trabajas media, o el ' +
                'compañero si ya tenía media ese día). Cubrir o pagar en el día libre NO genera deuda.';
            recargarCandidatosCobertura();
            actualizarResumenSemana();
        });
    });

    function poblarDiasPagoCobertura() {
        const sel = document.getElementById('cob-dia-pago');
        sel.innerHTML = '';
        if (!miDiaTrabajo()) return;
        const lunes = lunesDeLaSemana(parseISO(miDiaTrabajo()));
        const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
        for (let i = 0; i < 5; i++) {
            const d = new Date(lunes); d.setDate(lunes.getDate() + i);
            const iso = toISO(d);
            if (iso === miDiaTrabajo() || d < hoy) continue;
            const o = document.createElement('option');
            o.value = iso;
            o.textContent = `${nombreDia(d)} ${fmt(d)}` + (iso === miDescanso() ? ' (tu día libre — sin deuda tuya)' : '');
            if (iso === miDescanso()) o.selected = true;
            sel.appendChild(o);
        }
        cobDiaPago = sel.value || null;
        sel.onchange = function () {
            cobDiaPago = this.value || null;
            // El día de pago cambia la jornada_pago de cada candidato y la validación de coincidencia.
            recargarCandidatosCobertura();
            verificarPagoCobertura();
            actualizarResumenSemana();
        };
    }

    // Carga los desplegables de candidatos según la opción elegida (uno, o dos en modo DOS).
    function recargarCandidatosCobertura() {
        if (!cobOpcion || !miDiaTrabajo()) return;
        const g1 = document.getElementById('cob-candidatos-grupo');
        const g2 = document.getElementById('cob-candidatos-2-grupo');
        g1.style.display = 'block';
        if (cobOpcion === 'DOS') {
            g2.style.display = 'block';
            cargarCandidatosCobertura('AM', 'cob-select-1', 1);
            cargarCandidatosCobertura('PM', 'cob-select-2', 2);
        } else {
            g2.style.display = 'none';
            cargarCandidatosCobertura(cobOpcion, 'cob-select-1', 1);
        }
    }

    // Llena un <select> con los candidatos: disponibles seleccionables; no disponibles como
    // opción DESHABILITADA con su motivo. Los datos completos van en dataset.cand para el
    // detalle del seleccionado (jornada que cubre / jornada de pago / deuda).
    function cargarCandidatosCobertura(opcion, selectId, slot) {
        const sel = document.getElementById(selectId);
        sel.innerHTML = '<option value="">Cargando…</option>';
        const params = new URLSearchParams({ fecha_trabajo: miDiaTrabajo(), opcion });
        if (cobDiaPago) params.set('fecha_pago', cobDiaPago);
        fetch(`${URLs.COBERTURA_CANDIDATOS}?${params.toString()}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(r => r.json())
            .then(res => {
                const data = (res && res.data) || res || {};
                const cands = data.candidatos || [];
                miJornadaPago = data.mi_jornada_pago || null;
                mostrarMiJornadaPago();
                const disp = cands.filter(c => c.disponible);
                const nodisp = cands.filter(c => !c.disponible);
                sel.innerHTML = `<option value="">${slot === 2 ? 'Selecciona el segundo compañero…' : 'Selecciona un compañero…'}</option>`;
                disp.forEach(c => {
                    const o = document.createElement('option');
                    o.value = c.id;
                    o.textContent = `${c.nombre} ${c.apellido}` + (c.genera_deuda ? ' — dobla (30 min)' : '');
                    o.dataset.cand = JSON.stringify(c);
                    sel.appendChild(o);
                });
                if (nodisp.length) {
                    const og = document.createElement('optgroup');
                    og.label = 'No disponibles';
                    nodisp.forEach(c => {
                        const o = document.createElement('option');
                        o.disabled = true;
                        o.textContent = `${c.nombre} ${c.apellido} — ${c.motivo}`;
                        og.appendChild(o);
                    });
                    sel.appendChild(og);
                }
                // Reset de la selección de este slot al recargar la lista.
                const infoId = slot === 2 ? 'cob-info-2' : 'cob-info-1';
                const info = document.getElementById(infoId);
                if (info) info.style.display = 'none';
                if (slot === 2) {
                    empleadoReceptor2 = null;
                } else {
                    empleadoReceptor = null;
                    cobCandidato1 = null;
                    cobJornadaPago = null;
                    document.getElementById('empleado_receptor').value = '';
                    document.getElementById('cob-jornada-pago-grupo').style.display = 'none';
                    coberturaBloqueoCT = false;
                    document.getElementById('cob-aviso-ct').style.display = 'none';
                }
            })
            .catch(() => { sel.innerHTML = '<option value="">Error cargando compañeros</option>'; });
    }

    // Muestra el selector "¿con qué jornada pagas?" solo cuando hay elección real: opción simple
    // (AM/PM), estoy LIBRE el día de pago, y el compañero trabaja AMBAS ese día. Default = cedida.
    function actualizarSelectorJornadaPago(c) {
        const grupo = document.getElementById('cob-jornada-pago-grupo');
        const puedeElegir = (cobOpcion === 'AM' || cobOpcion === 'PM')
            && miJornadaPago === 'DESCANSO' && c && c.jornada_pago === 'DOBLADA';
        if (puedeElegir) {
            if (cobJornadaPago !== 'AM' && cobJornadaPago !== 'PM') cobJornadaPago = cobOpcion; // default: la cedida
            document.querySelectorAll('input[name="cob_jpago"]').forEach(r => { r.checked = (r.value === cobJornadaPago); });
            grupo.style.display = 'block';
        } else {
            grupo.style.display = 'none';
            cobJornadaPago = null; // sin elección → el backend usa la jornada cedida
        }
    }

    // Refresca la línea de info del slot 1 con la jornada de pago EFECTIVA (elegida o cedida).
    function refrescarInfoSlot1() {
        if (!cobCandidato1) return;
        const jornadaCubierta = cobJornadaPago || (cobOpcion === 'DOS' ? 'AM' : cobOpcion);
        mostrarInfoCandidato(cobCandidato1, 'cob-info-1', jornadaCubierta);
    }

    document.querySelectorAll('input[name="cob_jpago"]').forEach(r => {
        r.addEventListener('change', function () {
            cobJornadaPago = this.value;
            refrescarInfoSlot1();
            actualizarResumenSemana();
        });
    });

    // Línea persistente bajo el día de pago: MI jornada ese día (independiente del compañero).
    function mostrarMiJornadaPago() {
        const el = document.getElementById('cob-mi-jornada-pago');
        if (!el) return;
        const pago = cobDiaPago ? fmt(parseISO(cobDiaPago)) : '';
        if (!miJornadaPago || !pago) { el.style.display = 'none'; return; }
        // Si ya doblo (AM+PM) ese día no me queda jornada con la que pagar: cubrir al compañero
        // sería ficticio (ya estoy ese día completo). El backend lo rechaza
        // (`_validar_semana_cobertura`: "ya trabajas esa jornada"), así que se avisa aquí en vez
        // de dejar llenar todo el formulario para fallar al enviar.
        cobPagoImposible = (miJornadaPago === 'DOBLADA');
        const txt = miJornadaPago === 'DESCANSO'
            ? 'estás <strong>libre</strong> (puedes cubrir sin deuda)'
            : (cobPagoImposible
                ? 'ya trabajas <strong>AM+PM</strong> (doblada): no te queda jornada con la que pagar. Elige otro día de pago'
                : `trabajas <strong>${miJornadaPago}</strong>`);
        el.style.display = 'block';
        el.innerHTML = `<i class="fas fa-user-clock mr-1"></i>El día de pago (${pago}) ${txt}.`;
    }

    // Detalle del compañero elegido: su jornada el día que cubre + qué pasa el día de pago.
    // OJO: aunque el compañero trabaje DOBLADA el día de pago, tú solo devuelves UNA jornada
    // (la que cubres), no las dos. `jornadaCubierta` es la jornada que le pagas (la cedida).
    function mostrarInfoCandidato(c, infoId, jornadaCubierta) {
        const info = document.getElementById(infoId);
        if (!info) return;
        const work = miDiaTrabajo() ? fmt(parseISO(miDiaTrabajo())) : '';
        const pago = cobDiaPago ? fmt(parseISO(cobDiaPago)) : '';
        const estadoWork = c.jornada_cubre === 'DESCANSO'
            ? 'está <strong>libre</strong> (por eso puede cubrirte)'
            : `trabaja <strong>${c.jornada_cubre}</strong>`;
        const cubreDeuda = c.genera_deuda
            ? ' Al cubrirte queda AM+PM ese día → <strong>30 min</strong> para él.'
            : '';

        // Día de pago: solo devuelves UNA jornada (la cedida). Se muestra la jornada del
        // compañero ese día como contexto y la consecuencia según TU jornada ese día.
        let pagoTxt = '';
        if (pago) {
            const suTxt = c.jornada_pago === 'DESCANSO' ? 'libre' : (c.jornada_pago || '—');
            let consecuencia;
            if (miJornadaPago === 'DESCANSO') {
                consecuencia = `estás <strong>libre</strong> → le cubres su <strong>${jornadaCubierta}</strong> (él descansa esa jornada). Sin deuda.`;
            } else if (miJornadaPago === 'DOBLADA') {
                consecuencia = `tú ya trabajas <strong>AM+PM</strong> ese día → no te queda jornada con la que pagarle. Elige otro día de pago.`;
            } else if (miJornadaPago === jornadaCubierta) {
                consecuencia = `tú también trabajas <strong>${jornadaCubierta}</strong> ese día → no puedes cubrir esa jornada. Hazlo con un Cambio de Turno sencillo (aviso abajo).`;
            } else {
                consecuencia = `le cubres su <strong>${jornadaCubierta}</strong> y quedas AM+PM → <strong>30 min</strong> tuyos.`;
            }
            pagoTxt = `<br><i class="fas fa-calendar-check mr-1"></i>El día de pago (${pago}): ${c.nombre} trabaja <strong>${suTxt}</strong>; ${consecuencia}`;
        }

        info.style.display = 'block';
        info.innerHTML = `<i class="fas fa-info-circle mr-1"></i>Ese día (${work}) ${estadoWork}.${cubreDeuda}${pagoTxt}`;
    }

    // Handlers de los desplegables de compañero (se registran una sola vez).
    (function registrarSelectsCobertura() {
        const s1 = document.getElementById('cob-select-1');
        const s2 = document.getElementById('cob-select-2');
        if (s1) s1.addEventListener('change', function () {
            const o = this.options[this.selectedIndex];
            const c = (this.value && o.dataset.cand) ? JSON.parse(o.dataset.cand) : null;
            if (c) {
                empleadoReceptor = { id: c.id, nombre: c.nombre, apellido: c.apellido };
                cobCandidato1 = c;
                document.getElementById('empleado_receptor').value = c.id;
                actualizarSelectorJornadaPago(c);
                refrescarInfoSlot1();
                verificarPagoCobertura();
            } else {
                empleadoReceptor = null;
                cobCandidato1 = null;
                document.getElementById('empleado_receptor').value = '';
                document.getElementById('cob-info-1').style.display = 'none';
                document.getElementById('cob-jornada-pago-grupo').style.display = 'none';
                coberturaBloqueoCT = false;
                document.getElementById('cob-aviso-ct').style.display = 'none';
            }
            actualizarResumenSemana();
        });
        if (s2) s2.addEventListener('change', function () {
            const o = this.options[this.selectedIndex];
            const c = (this.value && o.dataset.cand) ? JSON.parse(o.dataset.cand) : null;
            if (c) {
                empleadoReceptor2 = { id: c.id, nombre: c.nombre, apellido: c.apellido };
                mostrarInfoCandidato(c, 'cob-info-2', 'PM');
            } else {
                empleadoReceptor2 = null;
                document.getElementById('cob-info-2').style.display = 'none';
            }
            actualizarResumenSemana();
        });
    })();

    // Valida el DÍA DE PAGO: si el emisor y el compañero tienen la MISMA jornada ese día, no se
    // puede pagar (trabajaría dos veces la misma jornada) → hay que hacer un Cambio de Turno sencillo.
    function verificarPagoCobertura() {
        coberturaBloqueoCT = false;
        const aviso = document.getElementById('cob-aviso-ct');
        aviso.style.display = 'none';
        if (!empleadoReceptor || !cobDiaPago || !MI_EMPLEADO_ID) return;
        const params = new URLSearchParams({
            deudor_id: MI_EMPLEADO_ID, acreedor_id: empleadoReceptor.id, fecha_pago: cobDiaPago,
        });
        fetch(`${URLs.COINCIDENCIA}?${params.toString()}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(r => r.json())
            .then(res => {
                const data = (res && res.data) || res || {};
                if (data.requiere_cambio_turno) {
                    coberturaBloqueoCT = true;
                    aviso.style.display = 'block';
                    aviso.innerHTML = `<i class="fas fa-exclamation-triangle mr-1"></i> ` +
                        `<strong>Misma jornada en el día de pago (${data.jornada_comun || ''}).</strong> ` +
                        `No puedes pagar trabajando dos veces la misma jornada. Para este caso haz un ` +
                        `<strong>Cambio de Turno sencillo</strong> ese día y luego vuelve. ` +
                        `<a href="/solicitudes/cambio-turno/solicitar/1/" class="btn btn-sm btn-outline-primary mt-1">` +
                        `<i class="fas fa-exchange-alt mr-1"></i>Ir a Cambio de Turno</a>`;
                }
            })
            .catch(() => {});
    }

    // --- cambio de doblada: cargar dobladas de la semana ---
    function cargarDobladasSemana() {
        const sel = document.getElementById('select-doblada-semana');
        sel.innerHTML = '<option value="">Cargando…</option>';
        fetch(`${URLs.DOBLADAS_SEMANA}?fecha=${encodeURIComponent(miDiaTrabajo())}`, {
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(r => r.json())
            .then(res => {
                const data = (res && res.data) || res || {};
                const dobladas = data.dobladas || [];
                if (!dobladas.length) {
                    sel.innerHTML = '<option value="">Nadie tiene doblada esa semana</option>';
                    return;
                }
                sel.innerHTML = '<option value="">Selecciona la doblada…</option>';
                dobladas.forEach(d => {
                    const f = parseISO(d.fecha);
                    const o = document.createElement('option');
                    o.value = `${d.empleado_id}|${d.fecha}`;
                    o.textContent = `${d.nombre} — dobla el ${nombreDia(f)} ${fmt(f)}`;
                    o.dataset.dob = JSON.stringify(d);
                    sel.appendChild(o);
                });
                sel.onchange = function () {
                    const opt = this.options[this.selectedIndex];
                    dobladaSel = (this.value && opt.dataset.dob) ? JSON.parse(opt.dataset.dob) : null;
                    actualizarResumenSemana();
                };
            })
            .catch(() => { sel.innerHTML = '<option value="">Error cargando dobladas</option>'; });
    }

    // --- permiso: jornada que trabajo mi día completo ---
    document.querySelectorAll('.perm-jornada').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('.perm-jornada').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            permJornada = this.dataset.jornada;
            actualizarResumenSemana();
        });
    });

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
            // El select manda: si por lo que sea la variable quedó desincronizada, se corrige
            // aquí antes de decidir si falta el compañero (el usuario lo veía elegido y el
            // formulario le decía que no lo había elegido).
            // SOLO para los sub-tipos que usan el select COMPARTIDO. En cobertura el compañero
            // se elige en `cob-select-1` y el compartido está oculto y vacío: sincronizar contra
            // él borraba la selección buena y devolvía "Selecciona el compañero que te cubre".
            if (subtipoSemana === 'intercambio_dia' || subtipoSemana === 'jornadas_partidas') {
                sincronizarReceptorSemana();
            }
            if (!descansoSolicitante) errores.push('Selecciona tu descanso (define la semana).');
            if (!descansoReceptor) errores.push('No se encontró el día del grupo contrario en esa semana.');
            if (!subtipoSemana) errores.push('Elige qué quieres hacer esa semana.');
            if (subtipoSemana === 'intercambio_dia' && !empleadoReceptor) errores.push('Selecciona el compañero.');
            if (subtipoSemana === 'jornadas_partidas') {
                if (!jpJornada) errores.push('Elige qué jornada trabajarás tú.');
                if (!empleadoReceptor) errores.push('Selecciona el compañero.');
            }
            if (subtipoSemana === 'cobertura_misma_semana') {
                if (!cobOpcion) errores.push('Elige qué te cubren (Solo AM, Solo PM o día completo con 2 compañeros).');
                if (!cobDiaPago) errores.push('Elige el día de pago (misma semana).');
                if (!empleadoReceptor) errores.push('Selecciona el compañero que te cubre.');
                if (cobOpcion === 'DOS') {
                    if (!empleadoReceptor2) errores.push('Selecciona el segundo compañero (cubre PM).');
                    if (empleadoReceptor && empleadoReceptor2 && empleadoReceptor.id === empleadoReceptor2.id)
                        errores.push('Los dos compañeros deben ser personas distintas.');
                }
                if (cobPagoImposible)
                    errores.push('El día de pago ya trabajas AM+PM (doblada): no te queda jornada con la que pagar. Elige otro día.');
                if (coberturaBloqueoCT)
                    errores.push('En el día de pago tienes la misma jornada que el compañero: primero haz un Cambio de Turno sencillo.');
            }
            if (subtipoSemana === 'cambio_doblada' && !dobladaSel) errores.push('Selecciona la doblada que tomas.');
            if (subtipoSemana === 'permiso_media_jornada' && !permJornada) errores.push('Elige qué media jornada trabajas tu día.');
        }

        if (errores.length) {
            notificar('warning', 'Faltan datos', errores.map(e => `• ${e}`).join('<br>'));
            return;
        }
        confirmar();
    });

    // Deja los campos ocultos coherentes con el sub-tipo elegido (envío único).
    function prepararCamposSemana() {
        const fs = document.getElementById('fecha_solicitud');
        const fp = document.getElementById('fecha_pago');
        const er = document.getElementById('empleado_receptor');
        const sm = document.getElementById('submodalidad_semana');
        const tc = document.getElementById('tipo_cesion_input');
        const jc = document.getElementById('jornada_cedida_input');

        if (subtipoSemana === 'intercambio_dia') {
            fs.value = miDescanso(); fp.value = miDiaTrabajo();
            sm.value = 'intercambio_dia'; tc.value = ''; jc.value = '';
        } else if (subtipoSemana === 'jornadas_partidas') {
            fs.value = miDiaTrabajo(); fp.value = miDescanso();
            sm.value = 'jornadas_partidas'; tc.value = ''; jc.value = jpJornada;
        } else if (subtipoSemana === 'cobertura_misma_semana') {
            fs.value = miDiaTrabajo(); fp.value = cobDiaPago;
            sm.value = 'cobertura_misma_semana';
            const jp = document.getElementById('jornada_cubre_en_pago_input');
            if (jp) jp.value = (cobOpcion !== 'DOS' && (cobJornadaPago === 'AM' || cobJornadaPago === 'PM')) ? cobJornadaPago : '';
            if (cobOpcion === 'AM') { tc.value = 'cesion_parcial_am'; jc.value = 'AM'; }
            else if (cobOpcion === 'PM') { tc.value = 'cesion_parcial_pm'; jc.value = 'PM'; }
        } else if (subtipoSemana === 'cambio_doblada') {
            fs.value = miDiaTrabajo(); fp.value = dobladaSel.fecha;
            er.value = dobladaSel.empleado_id;
            sm.value = 'cambio_doblada'; tc.value = ''; jc.value = '';
        }
    }

    function confirmar() {
        let html = '<div style="text-align:left;font-size:.95rem;">';
        if (modo === 'finde') {
            const fc = parseISO(document.getElementById('fecha_solicitud').value);
            const fp = parseISO(document.getElementById('fecha_pago').value);
            html += `<p><strong>Modalidad:</strong> Fin de semana</p>`;
            html += `<p><strong>Cambias:</strong> ${nombreDia(fc)} ${fmt(fc)}</p>`;
            html += `<p><strong>Devuelves:</strong> ${nombreDia(fp)} ${fmt(fp)}</p>`;
            html += `<p><strong>Compañero:</strong> ${empleadoReceptor.nombre} ${empleadoReceptor.apellido}</p>`;
        } else {
            const resumen = document.getElementById('resumen-box');
            html += `<p><strong>Modalidad:</strong> Entre semana (temporada)</p>` +
                `<div style="border-top:1px solid #e5e7eb;padding-top:8px;">${resumen.innerHTML}</div>`;
            if (subtipoSemana === 'permiso_media_jornada') {
                html += `<p class="mt-2"><strong>Nota:</strong> se envía a tu supervisor como PERMISO.</p>`;
            } else if (subtipoSemana === 'cobertura_misma_semana' && cobOpcion === 'DOS') {
                html += `<p class="mt-2"><strong>Nota:</strong> se crearán 2 solicitudes (AM y PM) ` +
                    `en un solo envío: o se crean las dos o no se crea ninguna.</p>`;
            }
        }
        html += '</div>';

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

    function deshabilitarForm() {
        const btn = document.getElementById('btnEnviarCd');
        btn.disabled = true;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Enviando…';
        form.querySelectorAll('input, select, textarea').forEach(el => el.disabled = true);
        document.querySelectorAll('.modo-btn[data-modo]').forEach(el => el.disabled = true);
        if (window.LoadingUI) LoadingUI.mostrar('Enviando solicitud...');
    }

    function postForm(url, fd, csrf) {
        return fetch(url, {
            method: 'POST',
            headers: { 'X-CSRFToken': csrf, 'X-Requested-With': 'XMLHttpRequest' },
            body: fd
        }).then(async r => ({ ok: r.ok, data: await r.json().catch(() => ({})) }));
    }

    function irAMisSolicitudes(msg) {
        notificar('success', '¡Enviado!', msg).then(() => {
            window.location.href = '/solicitudes/mis-solicitudes/';
        });
    }

    function enviar() {
        const csrf = form.querySelector('[name=csrfmiddlewaretoken]').value;

        // PERMISO media jornada: va a la app de permisos (flujo de PERMISO, no de solicitud).
        if (modo === 'semana' && subtipoSemana === 'permiso_media_jornada') {
            deshabilitarForm();
            const fd = new FormData();
            fd.append('csrfmiddlewaretoken', csrf);
            fd.append('fecha_trabajo', miDiaTrabajo());
            fd.append('fecha_compensacion', miDescanso());
            fd.append('jornada_trabaja', permJornada);
            fd.append('motivo', document.getElementById('comentarios').value.trim());
            postForm(URLs.PERMISO_MEDIA_JORNADA, fd, csrf)
                .then(({ ok, data }) => {
                    if (ok && data.success !== false) {
                        const msg = (data.data && data.data.message) || data.message || 'Permiso enviado a tu supervisor.';
                        notificar('success', '¡Permiso enviado!', msg).then(() => {
                            window.location.href = '/permisos/permisos-especiales/';
                        });
                    } else {
                        notificar('error', 'No se pudo enviar', data.error || data.message || 'Intenta de nuevo.');
                        rehabilitar();
                    }
                })
                .catch(() => { notificar('error', 'Error de red', CodigoReferencia.htmlMensaje('Intenta de nuevo.')); rehabilitar(); });
            return;
        }

        // COBERTURA con 2 compañeros: son DOS solicitudes (AM al 1º, PM al 2º), pero se envían
        // en UN solo POST. El servidor las valida y las crea en una transacción: o quedan las
        // dos o ninguna (media cobertura dejaría media jornada sin resolver).
        if (modo === 'semana' && subtipoSemana === 'cobertura_misma_semana' && cobOpcion === 'DOS') {
            deshabilitarForm();
            const fd = new FormData();
            Object.entries({
                csrfmiddlewaretoken: csrf,
                tipo_solicitud_id: TIPO_ID,
                modo_descanso: 'semana',
                fecha_solicitud: miDiaTrabajo(),
                fecha_pago: cobDiaPago,
                submodalidad_semana: 'cobertura_misma_semana',
                comentarios: document.getElementById('comentarios').value.trim(),
                empleado_receptor: empleadoReceptor.id,      // cubre la AM
                empleado_receptor_2: empleadoReceptor2.id,   // cubre la PM
            }).forEach(([k, v]) => fd.append(k, v));

            postForm(URLs.PROCESAR, fd, csrf)
                .then(({ ok, data }) => {
                    if (ok && data.success !== false) {
                        const msg = (data.data && data.data.message) || data.message ||
                            'Se crearon las 2 solicitudes de cobertura (AM y PM).';
                        irAMisSolicitudes(msg);
                    } else {
                        notificar('error', 'No se pudo enviar',
                            (data.error || data.message || 'Intenta de nuevo.'));
                        rehabilitar();
                    }
                })
                .catch(() => { notificar('error', 'Error de red', CodigoReferencia.htmlMensaje('Intenta de nuevo.')); rehabilitar(); });
            return;
        }

        // Resto: envío único con el form completo.
        // (FormData ANTES de deshabilitar: los inputs disabled no se serializan.)
        if (modo === 'semana') prepararCamposSemana();
        const fd = new FormData(form);
        deshabilitarForm();

        postForm(URLs.PROCESAR, fd, csrf)
            .then(({ ok, data }) => {
                if (ok && data.success !== false) {
                    const msg = (data.data && data.data.message) || data.message || 'Solicitud enviada correctamente.';
                    irAMisSolicitudes(msg);
                } else {
                    notificar('error', 'No se pudo enviar', data.error || data.message || 'Intenta de nuevo.');
                    rehabilitar();
                }
            })
            .catch(() => { notificar('error', 'Error de red', CodigoReferencia.htmlMensaje('Intenta de nuevo.')); rehabilitar(); });
    }

    function rehabilitar() {
        const btn = document.getElementById('btnEnviarCd');
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane mr-2"></i>Enviar Solicitud';
        form.querySelectorAll('input, select, textarea').forEach(el => el.disabled = false);
        document.querySelectorAll('.modo-btn[data-modo]').forEach(el => el.disabled = false);
    }

    // ===================== INIT =====================
    cargarMes();  // carga meses + findes del mes actual

})();
