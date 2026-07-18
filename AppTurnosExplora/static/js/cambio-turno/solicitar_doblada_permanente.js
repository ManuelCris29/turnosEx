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
    let dispDias = null;  // {0:[fechas],...} fechas válidas del SOLICITANTE por weekday en el rango
    let dispPar = {};     // {"weekday|compId":[fechas]} fechas válidas por PAR (día+compañero)
    let checkState = {};  // `${rid}|${weekday}|${comp}` -> Set de fechas ISO marcadas (si no existe: todas)
    let rowSeq = 0;       // id incremental por fila (permite el MISMO día de semana con varios compañeros)
    let _hayExcl = false, _hayBal = false;  // control de visibilidad del recuadro de preview

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

    // Días ya tomados por los selectores de día (excepto, opcionalmente, uno). Unión de ambos lados.
    function diasUsados(excluir) {
        return new Set(
            Array.from(form.querySelectorAll('select[name$="_dia"]'))
                .filter((s) => s !== excluir && s.value !== '')
                .map((s) => s.value)
        );
    }

    function ladoDe(sel) { return sel && sel.name && sel.name.indexOf('cesion') === 0 ? 'cesion' : 'devolucion'; }
    function contDe(tipo) { return tipo === 'cesion' ? cesionRows : devolucionRows; }

    // Días usados en el LADO CONTRARIO (un día de la semana no puede ser de cesión y de devolución
    // a la vez). En el MISMO lado sí se permite repetir el día con OTRO compañero (para cubrir sus
    // fechas AM con uno y las PM con otro).
    function diasUsadosOtroLado(tipo) {
        const otro = tipo === 'cesion' ? devolucionRows : cesionRows;
        return new Set(Array.from(otro.querySelectorAll('select[name$="_dia"]'))
            .filter((s) => s.value !== '').map((s) => s.value));
    }

    function primerDiaLibre(tipo) {
        const otroLado = diasUsadosOtroLado(tipo);
        const esteLado = new Set(Array.from(contDe(tipo).querySelectorAll('select[name$="_dia"]'))
            .filter((s) => s.value !== '').map((s) => s.value));
        // Preferir un día no usado aún en este lado; si no queda, cualquiera libre del otro lado.
        const libre = DIAS.find(([v]) => !otroLado.has(v) && !esteLado.has(v))
            || DIAS.find(([v]) => !otroLado.has(v));
        return libre ? libre[0] : '';
    }

    // Un día solo puede usarse una vez en TODO el acuerdo (ni dos veces en cesión,
    // ni el mismo día en cesión y devolución). Recalcula las opciones de cada
    // selector quitando los que ya tomaron OTROS, pero PRESERVA su propia selección.
    const MESES_AB2 = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
    function fmtFechaCorta(iso) { const p = iso.split('-'); return `${parseInt(p[2], 10)}/${MESES_AB2[parseInt(p[1], 10) - 1]}`; }

    function refreshDias() {
        const arrDia = (v) => (dispDias && dispDias[v]) ? dispDias[v] : null;  // [{f, ys}] o null
        const cnt = (v) => (arrDia(v) ? arrDia(v).length : null);
        const nombreDia = (v) => { const x = DIAS.find(([val]) => val === v); return x ? x[1] : ''; };
        const badge = (j) => `<span class="jr-badge ${j === 'AM' ? 'jr-am' : (j === 'PM' ? 'jr-pm' : 'jr-none')}">${j || '—'}</span>`;
        const contraria = (j) => (j === 'AM' ? 'PM' : 'AM');
        // Snapshot de fechas MARCADAS por fila (antes de re-render): una fecha = UN solo compañero, así
        // que una fecha ya marcada en otra fila del mismo lado se bloquea (no doble cobertura).
        const marcadasPorFila = Array.from(form.querySelectorAll('.perm-row')).map((r) => ({
            rid: r.dataset.rid || '',
            tipo: r.querySelector('select[name="cesion_dia"]') ? 'cesion' : 'devolucion',
            comp: (r.querySelector('select[name$="_companero"]') || {}).value || '',
            fechas: new Set(Array.from(r.querySelectorAll('.perm-fecha:checked')).map((c) => c.value)),
        }));
        const nombreDeComp = (cid) => { const c = companeros.find((x) => String(x.id) === String(cid)); return c ? `${c.nombre} ${c.apellido}` : 'otro compañero'; };
        const selects = Array.from(form.querySelectorAll('select[name$="_dia"]'));
        selects.forEach(function (sel) {
            const tipo = ladoDe(sel);              // 'cesion' | 'devolucion'
            const bloqueados = diasUsadosOtroLado(tipo);  // solo el LADO CONTRARIO bloquea el día
            let actual = sel.value;
            const opts = DIAS.filter(([v]) => !bloqueados.has(v));
            if (dispDias && actual && cnt(actual) === 0) {
                const libre = opts.find(([v]) => cnt(v) > 0);
                actual = libre ? libre[0] : actual;
            }
            sel.innerHTML = opts.map(([v, n]) => {
                const arr = arrDia(v);
                const c = arr ? arr.length : null;
                const sinDias = c === 0;
                let etiqueta;
                if (c === null) { etiqueta = n; }
                else if (sinDias) { etiqueta = `${n} — sin días disponibles`; }
                else {
                    const am = arr.filter((o) => o.ys === 'AM').length;
                    const pm = arr.filter((o) => o.ys === 'PM').length;
                    // Indica el split AM/PM en la etiqueta para saber qué jornada de compañero elegir.
                    const split = (am && pm) ? ` (${am} en AM, ${pm} en PM)` : (am ? ' (en AM)' : ' (en PM)');
                    etiqueta = `${n} — ${c} ${c === 1 ? 'día' : 'días'}${split}`;
                }
                return `<option value="${v}"${sinDias ? ' disabled' : ''}${v === actual ? ' selected' : ''}>${etiqueta}</option>`;
            }).join('');
            sel.value = actual;

            const row = sel.closest('.perm-row');
            const cont = row && row.querySelector('.perm-dias-hint');
            if (cont) {
                const rid = row.dataset.rid || '';
                const comp = (row.querySelector('select[name$="_companero"]') || {}).value || '';
                const misFechas = (actual && arrDia(actual)) ? arrDia(actual) : [];  // [{f, ys}]
                // Línea "Tus <día>: 11/ago [AM] · 25/ago [PM]" — para saber, ANTES de elegir compañero,
                // en qué fechas estás AM y en cuáles PM (y qué jornada de compañero necesitas en cada una).
                const tusFechasHtml = misFechas.length
                    ? `<div class="perm-tus-fechas">Tus ${nombreDia(actual).toLowerCase()}: ` +
                      misFechas.map((o) => `<span class="tf-item">${fmtFechaCorta(o.f)} ${badge(o.ys)}</span>`).join(' · ') +
                      `</div>`
                    : '';
                // Con compañero: objetos {f, ys, yc} del PAR (fechas donde es contrario a ti).
                const items = (actual && comp) ? (dispPar[`${actual}|${comp}`] || []) : [];
                const key = `${rid}|${actual}|${comp}`;
                const prev = checkState[key];  // Set de fechas marcadas, o undefined (default: todas)

                if (!comp) {
                    cont.innerHTML = tusFechasHtml + (actual
                        ? '<div class="perm-fila-vacia">Elige un compañero de jornada <strong>contraria</strong> a cada fecha: para tus fechas <span class="jr-badge jr-am">AM</span> uno en <span class="jr-badge jr-pm">PM</span>, y para tus <span class="jr-badge jr-pm">PM</span> uno en <span class="jr-badge jr-am">AM</span>. Puedes usar dos compañeros en el mismo día.</div>'
                        : '');
                } else if (!items.length) {
                    cont.innerHTML = tusFechasHtml + '<div class="perm-fila-sin">Ese compañero no te cubre ninguna de esas fechas (su jornada no es contraria a la tuya esos días). Elige un compañero con la jornada contraria a las fechas de arriba.</div>';
                } else {
                    const compObj = companeros.find((x) => String(x.id) === String(comp));
                    const compNom = compObj ? compObj.nombre : 'Compañero';
                    const quePasa = () => (tipo === 'cesion')
                        ? `<span class="accion-dobla comp">${compNom} se dobla (AM+PM)</span> · <span class="accion-descansa">tú descansas</span>`
                        : `<span class="accion-dobla yo">tú te doblas (AM+PM)</span> · <span class="accion-descansa">${compNom} descansa</span>`;
                    // Fechas ya MARCADAS en OTRAS filas del MISMO lado → no se pueden re-asignar aquí.
                    const tomadas = {};  // {fecha: nombreCompañero}
                    marcadasPorFila.forEach((mf) => {
                        if (mf.rid === rid || mf.tipo !== tipo) return;
                        mf.fechas.forEach((f) => { if (!tomadas[f]) tomadas[f] = nombreDeComp(mf.comp); });
                    });
                    const filasHtml = items.map((o) => {
                        const tomadaPor = tomadas[o.f];
                        if (tomadaPor) {
                            // Una fecha solo puede tener un compañero: se muestra deshabilitada.
                            return `<tr class="perm-fecha-tomada">` +
                                `<td class="col-check"><input type="checkbox" class="perm-fecha" value="${o.f}" disabled></td>` +
                                `<td class="col-fecha">${fmtFechaCorta(o.f)}</td>` +
                                `<td>${badge(o.ys)}</td>` +
                                `<td>${badge(o.yc)}</td>` +
                                `<td class="col-quepasa"><span class="perm-tomada-nota"><i class="fas fa-lock mr-1"></i>ya asignado a ${tomadaPor}</span></td>` +
                                `</tr>`;
                        }
                        const marcado = prev ? prev.has(o.f) : true;
                        return `<tr>` +
                            `<td class="col-check"><input type="checkbox" class="perm-fecha" value="${o.f}"${marcado ? ' checked' : ''}></td>` +
                            `<td class="col-fecha">${fmtFechaCorta(o.f)}</td>` +
                            `<td>${badge(o.ys)}</td>` +
                            `<td>${badge(o.yc)}</td>` +
                            `<td class="col-quepasa">${quePasa()}</td>` +
                            `</tr>`;
                    }).join('');
                    // Fechas de este día que ESTE compañero no cubre (jornada no contraria) → aviso claro.
                    const cubiertas = new Set(items.map((o) => o.f));
                    const faltan = misFechas.filter((o) => !cubiertas.has(o.f));
                    // El consejo correcto difiere por lado: en CESIÓN basta agregar un compañero
                    // contrario que te cubra; en DEVOLUCIÓN NO basta —ese compañero además debe
                    // haberte cubierto en la cesión, o crearías un desbalance (evita el callejón
                    // sin salida de "agrega un compañero PM" que en realidad no equilibra).
                    const faltanFechas = faltan.map((o) => `${fmtFechaCorta(o.f)} (estás ${o.ys})`).join(', ');
                    const cierre = (tipo === 'cesion')
                        ? `Necesitas un compañero <strong>${contraria(faltan.length ? faltan[0].ys : 'AM')}</strong> que te cubra esos días: agrega otra fila de este mismo día con un compañero de esa jornada.`
                        : `Esos días tú te doblas, así que solo puedes devolvérselos a un compañero <strong>${contraria(faltan.length ? faltan[0].ys : 'AM')}</strong> que <strong>además te haya cubierto</strong> en la cesión. Si no lo hay, quítalos o reduce tu cesión para equilibrar.`;
                    const faltanHtml = faltan.length
                        ? `<div class="perm-faltan"><i class="fas fa-info-circle mr-1"></i>Falta por cubrir: ${faltanFechas}. ${cierre}</div>`
                        : '';
                    cont.innerHTML = tusFechasHtml +
                        `<div class="perm-tabla-wrap"><table class="perm-tabla">` +
                        `<thead><tr><th class="col-check">✓</th><th>Fecha</th><th>Tú</th><th>${compNom}</th><th>Qué pasa ese día</th></tr></thead>` +
                        `<tbody>${filasHtml}</tbody></table></div>` + faltanHtml;
                    // Default: marcar todas MENOS las ya tomadas por otra fila (no doble asignación).
                    if (!prev) checkState[key] = new Set(items.filter((o) => !tomadas[o.f]).map((o) => o.f));
                    cont.querySelectorAll('.perm-fecha:not(:disabled)').forEach((chk) => chk.addEventListener('change', function () {
                        checkState[key] = new Set(Array.from(cont.querySelectorAll('.perm-fecha:checked')).map((c) => c.value));
                        refreshDias();  // re-render: propaga el bloqueo de fechas tomadas a las filas hermanas
                    }));
                }
            }
        });
        actualizarPreview();
        actualizarBalance();
    }

    // Disponibilidad de días válidos por weekday en el rango (lado solicitante). Al cambiar el
    // rango, recalcula y refresca los selectores para deshabilitar/anotar los días.
    function cargarDisponibilidadDias() {
        const fi = inputInicio.value, ff = inputFin.value;
        if (!fi || !ff || ff < fi) { dispDias = null; dispPar = {}; refreshDias(); return; }
        // Por-par: se envían TODOS los pares (día + compañero) de ambos lados, para calcular las
        // fechas que cubre cada compañero por separado (el mismo día puede ir con varios compañeros).
        const pares = [];
        filas(cesionRows, 'cesion').forEach((r) => { if (r.dia && r.comp) pares.push({ dia: r.dia, comp: r.comp }); });
        filas(devolucionRows, 'devolucion').forEach((r) => { if (r.dia && r.comp) pares.push({ dia: r.dia, comp: r.comp }); });
        const qPares = `&pares=${encodeURIComponent(JSON.stringify(pares))}`;
        fetch(`${URL_DIAS_DISP}?fecha_inicio=${encodeURIComponent(fi)}&fecha_fin=${encodeURIComponent(ff)}${qPares}`,
              { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((res) => {
                const d = (res && res.data) ? res.data : res;
                dispDias = (d && d.por_dia) || null;
                dispPar = (d && d.por_par) || {};
                refreshDias();
            })
            .catch(() => { dispDias = null; dispPar = {}; refreshDias(); });
    }

    function _syncBox() {
        const box = document.getElementById('preview_omitidos_box');
        if (box) box.style.display = (_hayExcl || _hayBal) ? 'block' : 'none';
    }

    // Balance por compañero contando FECHAS marcadas (no ocurrencias del weekday). Bloquea el
    // botón de envío si por algún compañero las fechas de cesión y devolución no coinciden.
    function contarPorComp(cont, tipo) {
        const m = {};
        Array.from(cont.querySelectorAll('.perm-row')).forEach((r) => {
            const comp = r.querySelector(`select[name="${tipo}_companero"]`).value;
            if (!comp) return;
            const n = r.querySelectorAll('.perm-fecha:checked').length;
            m[comp] = (m[comp] || 0) + n;
        });
        return m;
    }

    // Fechas contrarias DISPONIBLES por compañero en un lado (unión sobre sus filas): es el
    // MÁXIMO de días que ese compañero podría cubrirte/devolverte en el rango. Sirve para decir
    // cuántos se pueden equilibrar realmente (no basta pedir "iguales" si un lado no tiene días).
    function dispPorComp(rows, tipo) {
        const m = {};  // cid -> Set(fechas)
        filas(rows, tipo).forEach((r) => {
            if (!r.dia || !r.comp) return;
            const items = dispPar[`${r.dia}|${r.comp}`] || [];
            const s = m[r.comp] || (m[r.comp] = new Set());
            items.forEach((o) => s.add(o.f));
        });
        return m;
    }

    function actualizarBalance() {
        const cubre = contarPorComp(cesionRows, 'cesion');
        const devuelve = contarPorComp(devolucionRows, 'devolucion');
        const dispCes = dispPorComp(cesionRows, 'cesion');
        const dispDev = dispPorComp(devolucionRows, 'devolucion');
        const nombreComp = (cid) => { const c = companeros.find((x) => String(x.id) === String(cid)); return c ? `${c.nombre} ${c.apellido}` : 'Compañero'; };
        const comps = new Set([...Object.keys(cubre), ...Object.keys(devuelve)]);
        const msgs = []; let ok = comps.size > 0;
        comps.forEach((cid) => {
            const c = cubre[cid] || 0, v = devuelve[cid] || 0;
            if (c !== v) {
                ok = false;
                const nom = nombreComp(cid);
                // Máximo que SÍ se puede equilibrar con este compañero = min de días contrarios
                // disponibles en cada lado. Si un lado no tiene suficientes, "poner iguales" pasa
                // por REDUCIR el lado mayor a ese máximo (o elegir otro día/rango).
                const maxEq = Math.min((dispCes[cid] || new Set()).size, (dispDev[cid] || new Set()).size);
                if (maxEq === 0) {
                    msgs.push(`<span style="color:#b45309;">⚠️ ${nom}: no hay días en este rango en que queden en jornada contraria para equilibrar. Elige otro compañero, otro día de la semana o amplía el rango.</span>`);
                } else {
                    msgs.push(`<span style="color:#b45309;">⚠️ ${nom}: te cubre ${c} y le devuelves ${v} — deben ser iguales. En este rango solo puedes equilibrar <strong>${maxEq}</strong> día(s) con ${nom} (los días en que quedan en jornada contraria). Reduce el lado mayor a ${maxEq}, o elige otro día de la semana / amplía el rango.</span>`);
                }
            } else if (c > 0) {
                msgs.push(`✅ ${nombreComp(cid)}: ${c} cubre / ${c} devuelve (balanceado).`);
            }
        });
        const balEl = document.getElementById('preview_balance');
        if (balEl) balEl.innerHTML = msgs.length ? ('<strong>Balance:</strong><br>' + msgs.join('<br>')) : '';
        _hayBal = msgs.length > 0;
        _syncBox();
        if (btn) {
            btn.disabled = !ok;
            btn.title = ok ? '' : 'Ajusta las fechas: por cada compañero, las que te cubre y las que devuelves deben ser iguales.';
        }
        actualizarResumen();
    }

    // Fechas MARCADAS agrupadas por compañero (para el resumen ejecutivo).
    function fechasMarcadasPorComp(cont, tipo) {
        const m = {};
        Array.from(cont.querySelectorAll('.perm-row')).forEach((r) => {
            const comp = r.querySelector(`select[name="${tipo}_companero"]`).value;
            if (!comp) return;
            const fs = Array.from(r.querySelectorAll('.perm-fecha:checked')).map((c) => c.value);
            m[comp] = (m[comp] || []).concat(fs);
        });
        return m;
    }

    // Resumen ejecutivo en lenguaje natural: por compañero, qué te cubre (descansas) y qué le
    // devuelves (te doblas), con el balance. Complementa la mini-tabla por fecha.
    function actualizarResumen() {
        const box = document.getElementById('resumen_acuerdo');
        if (!box) return;
        const nombreComp = (cid) => { const c = companeros.find((x) => String(x.id) === String(cid)); return c ? `${c.nombre} ${c.apellido}` : 'Compañero'; };
        const fmtLista = (arr) => arr.slice().sort().map(fmtFechaCorta).join(', ');
        const cubre = fechasMarcadasPorComp(cesionRows, 'cesion');
        const devu = fechasMarcadasPorComp(devolucionRows, 'devolucion');
        const comps = Array.from(new Set([...Object.keys(cubre), ...Object.keys(devu)]));
        if (!comps.length) { box.style.display = 'none'; box.innerHTML = ''; return; }
        let html = '<div class="resumen-titulo"><i class="fas fa-clipboard-check mr-1"></i>Resumen del acuerdo</div>';
        comps.forEach((cid) => {
            const c = cubre[cid] || [], v = devu[cid] || [];
            const partes = [];
            if (c.length) partes.push(`<span class="cubre">te cubre <strong>${c.length}</strong> día(s) (${fmtLista(c)}) → <strong>tú descansas</strong></span>`);
            if (v.length) partes.push(`<span class="devuelve">le devuelves <strong>${v.length}</strong> día(s) (${fmtLista(v)}) → <strong>tú te doblas</strong></span>`);
            const bal = (c.length === v.length && c.length > 0)
                ? `<span class="bal-ok">✓ balanceado (${c.length}/${v.length})</span>`
                : `<span class="bal-warn">⚠ te cubre ${c.length} y devuelves ${v.length} — deben ser iguales</span>`;
            html += `<div class="comp-line"><span class="comp-nombre">${nombreComp(cid)}</span>: ${partes.join('; ') || 'sin fechas marcadas'}. ${bal}</div>`;
        });
        html += '<div class="resumen-nota">Cada doblada suma 30 min a tu consolidado. Los días omitidos (festivo, descanso, día libre, doblada, temporada o mantenimiento) no se aplican.</div>';
        box.innerHTML = html;
        box.style.display = 'block';
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
        if (!fi || !ff || ff < fi || !dias.length) { _hayExcl = false; _syncBox(); return; }
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
                // El BALANCE ahora se calcula con las FECHAS marcadas (actualizarBalance). Aquí solo
                // se muestran las fechas que se OMITIRÁN (para explicar por qué no aparecen como casilla).
                document.getElementById('preview_lista').innerHTML = exc.map((e) => {
                    const p = e.fecha.split('-');
                    return `<li><strong>${p[2]}/${MESES_AB[parseInt(p[1], 10) - 1]}</strong> — ${e.razon}</li>`;
                }).join('');
                document.getElementById('preview_resumen').textContent = exc.length
                    ? `Se omitirán ${exc.length} día(s) del rango (festivo, descanso, día libre, doblada, mantenimiento o temporada); no aparecen como casilla.`
                    : '';
                _hayExcl = exc.length > 0;
                _syncBox();
            })
            .catch(() => { _hayExcl = false; _syncBox(); });
    }

    // Compañeros usados actualmente en cesión (para limitar la devolución)
    function companerosEnCesion() {
        const ids = new Set();
        cesionRows.querySelectorAll('select[name="cesion_companero"]').forEach((s) => { if (s.value) ids.add(s.value); });
        return companeros.filter((c) => ids.has(String(c.id)));
    }

    function optCompaneros(lista) {
        // Se ofrecen compañeros de AMBAS jornadas (AM y PM): dentro del rango tu jornada real puede
        // variar por fecha (por CT sencillo/permanente), así que unos días necesitas un compañero PM
        // y otros uno AM. La etiqueta muestra la jornada real del compañero; las casillas de fecha de
        // cada fila (jornada-aware) indican en qué fechas concretas ese compañero te cubre.
        return ['<option value="">Compañero…</option>']
            .concat(lista.map((c) => {
                const j = c.jornada ? ` (${c.jornada})` : '';
                return `<option value="${c.id}">${c.nombre} ${c.apellido}${j}</option>`;
            })).join('');
    }

    function nuevaFila(tipo) {
        const row = document.createElement('div');
        row.className = 'perm-row mb-2';
        row.dataset.rid = String(++rowSeq);  // id estable → permite el mismo día con varios compañeros
        const lista = (tipo === 'cesion') ? companeros : companerosEnCesion();
        // Solo se excluyen los días usados en el LADO CONTRARIO (un día no puede ser cesión y
        // devolución a la vez). En el MISMO lado el día puede repetirse con otro compañero.
        const bloqueados = diasUsadosOtroLado(tipo);
        const diaSel = primerDiaLibre(tipo);
        const optDiasLibres = DIAS.filter(([v]) => !bloqueados.has(v))
            .map(([v, n]) => `<option value="${v}"${v === diaSel ? ' selected' : ''}>${n}</option>`).join('');
        row.innerHTML =
            `<div class="d-flex align-items-center" style="gap:.5rem;">` +
                `<select class="form-control" name="${tipo}_dia" style="max-width:230px;">${optDiasLibres}</select>` +
                `<select class="form-control" name="${tipo}_companero">${optCompaneros(lista)}</select>` +
                `<button type="button" class="btn btn-sm btn-outline-danger perm-remove" title="Quitar"><i class="fas fa-times"></i></button>` +
            `</div>` +
            `<div class="perm-dias-hint small text-muted mt-1" style="margin-left:2px;"></div>`;
        // Cualquier cambio estructural (quitar fila, cambiar día o compañero) recalcula la
        // disponibilidad compañero-aware y repinta las casillas de fecha.
        row.querySelector('.perm-remove').addEventListener('click', function () { row.remove(); cargarDisponibilidadDias(); });
        row.querySelector('select[name$="_dia"]').addEventListener('change', cargarDisponibilidadDias);
        row.querySelector('select[name$="_companero"]').addEventListener('change', cargarDisponibilidadDias);
        return row;
    }

    function hayDiasLibres(tipo) {
        // Hay días para agregar en este lado si queda al menos un día no usado en el lado contrario.
        const bloqueados = diasUsadosOtroLado(tipo);
        return DIAS.some(([v]) => !bloqueados.has(v));
    }

    if (btnAddCesion) btnAddCesion.addEventListener('click', function () {
        if (!companeros.length) return;
        if (!hayDiasLibres('cesion')) { notificar('info', 'Sin días libres', 'Esos días de la semana ya los usas en la devolución.'); return; }
        cesionRows.appendChild(nuevaFila('cesion'));
        cargarDisponibilidadDias();
    });
    if (btnAddDevolucion) btnAddDevolucion.addEventListener('click', function () {
        const lista = companerosEnCesion();
        if (!lista.length) { notificar('info', 'Primero agrega cesión', 'Agrega al menos un día de cesión con su compañero antes de definir la devolución.'); return; }
        if (!hayDiasLibres('devolucion')) { notificar('info', 'Sin días libres', 'Esos días de la semana ya los usas en la cesión.'); return; }
        devolucionRows.appendChild(nuevaFila('devolucion'));
        cargarDisponibilidadDias();
    });

    function filas(cont, tipo) {
        return Array.from(cont.querySelectorAll('.perm-row')).map((r) => ({
            dia: r.querySelector(`select[name="${tipo}_dia"]`).value,
            comp: r.querySelector(`select[name="${tipo}_companero"]`).value,
        }));
    }

    // Fechas MARCADAS por fila, con su compañero: [{fecha, comp}].
    function gatherFechas(cont, tipo) {
        const out = [];
        Array.from(cont.querySelectorAll('.perm-row')).forEach((r) => {
            const comp = r.querySelector(`select[name="${tipo}_companero"]`).value;
            if (!comp) return;
            r.querySelectorAll('.perm-fecha:checked').forEach((chk) => out.push({ fecha: chk.value, comp }));
        });
        return out;
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

        // El mismo día de semana SÍ puede ir con varios compañeros, pero no repetir el MISMO par
        // (día + compañero): sería una fila duplicada.
        const parDup = (rows) => {
            const seen = new Set();
            for (const r of rows) {
                if (!r.dia || !r.comp) continue;
                const k = `${r.dia}|${r.comp}`;
                if (seen.has(k)) return true;
                seen.add(k);
            }
            return false;
        };
        if (parDup(ces) || parDup(dev)) errores.push('Tienes dos filas con el mismo día y el mismo compañero. Usa compañeros distintos para el mismo día, o quita la fila repetida.');

        // Balance por FECHAS marcadas (no por weekday): por cada compañero, nº fechas que te cubre
        // == nº fechas que le devuelves. Cada fila debe tener al menos una fecha marcada.
        const cubreCount = contarPorComp(cesionRows, 'cesion');   // comp -> # fechas de cesión marcadas
        const devCount = contarPorComp(devolucionRows, 'devolucion');
        const fCes = gatherFechas(cesionRows, 'cesion');
        const fDev = gatherFechas(devolucionRows, 'devolucion');
        if (ces.length && !fCes.length) errores.push('Marca al menos una fecha en los días que cedes.');
        if (dev.length && !fDev.length) errores.push('Marca al menos una fecha en los días que devuelves.');
        // Una fecha = un solo compañero: no puede estar marcada en dos filas del mismo lado.
        const fechaDup = (arr) => { const s = new Set(); for (const x of arr) { if (s.has(x.fecha)) return x.fecha; s.add(x.fecha); } return null; };
        const dupC = fechaDup(fCes), dupD = fechaDup(fDev);
        if (dupC) errores.push(`El ${fmtFechaCorta(dupC)} está asignado a dos compañeros en los días que cedes. Una fecha solo puede cubrirla un compañero.`);
        if (dupD) errores.push(`El ${fmtFechaCorta(dupD)} está asignado a dos compañeros en los días que devuelves. Una fecha solo puede pagarla un compañero.`);
        Object.keys(devCount).forEach((comp) => {
            if (!cubreCount[comp]) errores.push('Solo puedes devolverle a un compañero que te cubra.');
        });
        Object.keys(cubreCount).forEach((comp) => {
            if ((devCount[comp] || 0) !== cubreCount[comp]) {
                const c = companeros.find((x) => String(x.id) === String(comp));
                const nom = c ? `${c.nombre} ${c.apellido}` : 'un compañero';
                errores.push(`A ${nom} le devuelves ${(devCount[comp] || 0)} fecha(s) pero te cubre ${cubreCount[comp]}. Deben ser iguales.`);
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
        // Fechas ESPECÍFICAS marcadas por compañero (listas paralelas). El backend las usa con
        // prioridad sobre los weekdays (cesion_dia/cesion_companero, que se siguen enviando).
        gatherFechas(cesionRows, 'cesion').forEach((x) => { fd.append('cesion_fecha', x.fecha); fd.append('cesion_fecha_companero', x.comp); });
        gatherFechas(devolucionRows, 'devolucion').forEach((x) => { fd.append('devolucion_fecha', x.fecha); fd.append('devolucion_fecha_companero', x.comp); });
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
