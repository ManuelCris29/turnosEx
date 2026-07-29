/**
 * Asignación manual de fines de semana y festivos.
 *
 * Solo son clickeables los sábados/domingos y los festivos entre semana. Al hacer clic
 * se cicla el grupo que TRABAJA el día completo: automático → AM → PM → automático.
 * El default automático se muestra como pista tenue (clase auto-am / auto-pm).
 */
(function () {
    const pre = JSON.parse(document.getElementById('ae-preseleccion').textContent);       // {fecha: 'AM'/'PM'} overrides
    const festivos = new Set(JSON.parse(document.getElementById('ae-festivos').textContent)); // fechas festivo lun-vie
    // Festivos que caen en sáb/dom: se marcan igual, pero NO son un caso aparte —
    // manda la alternancia del finde, así que no cambian el comportamiento del clic.
    const festivosFinde = new Set(JSON.parse(document.getElementById('ae-festivos-finde').textContent));
    const auto = JSON.parse(document.getElementById('ae-auto').textContent);              // {fecha: 'AM'/'PM'} automático
    const bloqueadas = new Set(JSON.parse(document.getElementById('ae-bloqueadas').textContent)); // findes/festivos con solicitudes
    const form = document.getElementById('aeForm');
    const hidden = document.getElementById('seleccion');

    const estado = {};  // solo overrides manuales: {fecha: 'AM'/'PM'}
    Object.keys(pre).forEach(f => { estado[f] = pre[f]; });

    const CICLO = [null, 'AM', 'PM'];

    function esEspecial(span) {
        const wd = parseInt(span.dataset.weekday, 10);
        return wd >= 5 || festivos.has(span.dataset.fecha);
    }

    function pintar(span) {
        const f = span.dataset.fecha;
        span.classList.remove('sel-am', 'sel-pm', 'auto-am', 'auto-pm');
        const et = span.querySelector('.et');
        if (estado[f] === 'AM') { span.classList.add('sel-am'); et.textContent = 'AM'; }
        else if (estado[f] === 'PM') { span.classList.add('sel-pm'); et.textContent = 'PM'; }
        else {
            // Sin override: mostrar el automático como pista tenue
            const a = auto[f];
            if (a === 'AM') { span.classList.add('auto-am'); et.textContent = 'am'; }
            else if (a === 'PM') { span.classList.add('auto-pm'); et.textContent = 'pm'; }
            else { et.textContent = ''; }
        }
    }

    document.querySelectorAll('.dia[data-fecha]').forEach(span => {
        if (!esEspecial(span)) {
            // Día normal entre semana: no aplica aquí
            span.classList.add('bloqueado');
            return;
        }
        if (festivos.has(span.dataset.fecha) || festivosFinde.has(span.dataset.fecha)) {
            const cont = document.createElement('span');
            cont.className = 'marks';
            const d = document.createElement('span');
            d.className = 'mk mk-festivo';
            d.title = festivosFinde.has(span.dataset.fecha)
                ? 'festivo en fin de semana (manda la alternancia del finde)'
                : 'festivo';
            cont.appendChild(d);
            span.appendChild(cont);
        }
        pintar(span);
        // Finde/festivo con solicitudes aprobadas: BLOQUEADO, no se puede alterar.
        if (bloqueadas.has(span.dataset.fecha)) {
            span.classList.add('bloqueado');
            span.title = 'Este día ya tiene solicitudes aprobadas; no se puede alterar la alternancia.';
            const lock = document.createElement('span');
            lock.className = 'ae-lock';
            lock.textContent = '🔒';
            span.appendChild(lock);
            return;
        }
        span.addEventListener('click', () => {
            const f = span.dataset.fecha;
            const actual = estado[f] || null;
            let idx = CICLO.indexOf(actual);
            if (idx < 0) idx = 0;
            const siguiente = CICLO[(idx + 1) % CICLO.length];
            if (siguiente) estado[f] = siguiente; else delete estado[f];
            pintar(span);
        });
    });

    // ===========================================================
    //  SEMBRAR: fija el grupo del primer día y rellena TODO el año
    //  siguiendo la alternancia. Solo existe cuando el año está en
    //  limpio (los botones no se renderizan si hay solicitudes).
    // ===========================================================
    const DAY = 86400000;
    const oppos = (g) => (g === 'AM' ? 'PM' : 'AM');
    const parseISO = (s) => { const [y, m, d] = s.split('-').map(Number); return Date.UTC(y, m - 1, d); };
    const isoFromMs = (ms) => {
        const d = new Date(ms);
        return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-${String(d.getUTCDate()).padStart(2, '0')}`;
    };
    const isoMinus1 = (iso) => isoFromMs(parseISO(iso) - DAY);

    // Celdas especiales (sáb/dom y festivos lun-vie) presentes en el calendario.
    const celdas = Array.from(document.querySelectorAll('.dia[data-fecha]')).filter(esEspecial);

    // Primer sábado del año (ISO menor entre las celdas con weekday 5).
    function primerSabadoISO() {
        let best = null;
        celdas.forEach(s => {
            if (parseInt(s.dataset.weekday, 10) === 5) {
                const iso = s.dataset.fecha;
                if (best === null || iso < best) best = iso;
            }
        });
        return best;
    }

    // Grupo que trabaja un sábado dado, según paridad de semanas desde el primer sábado.
    function grupoSabado(satISO, primerSabISO, primerGrupo) {
        const semanas = Math.floor((parseISO(satISO) - parseISO(primerSabISO)) / (7 * DAY));
        return (semanas % 2 === 0) ? primerGrupo : oppos(primerGrupo);
    }

    function repintarTodo() { celdas.forEach(pintar); }

    function sembrarFindes(primerGrupo) {
        const primerSab = primerSabadoISO();
        if (!primerSab) return;
        celdas.forEach(s => {
            const iso = s.dataset.fecha;
            if (bloqueadas.has(iso)) return;  // seguridad: nunca tocar días bloqueados
            const wd = parseInt(s.dataset.weekday, 10);
            if (wd === 5) {
                estado[iso] = grupoSabado(iso, primerSab, primerGrupo);
            } else if (wd === 6) {
                // Domingo: grupo contrario al de SU sábado (fecha - 1 día).
                estado[iso] = oppos(grupoSabado(isoMinus1(iso), primerSab, primerGrupo));
            }
        });
        repintarTodo();
    }

    function sembrarFestivos(primerGrupo) {
        const fechas = celdas
            .filter(s => festivos.has(s.dataset.fecha) && !bloqueadas.has(s.dataset.fecha))
            .map(s => s.dataset.fecha)
            .sort();  // ISO ordena cronológicamente
        let g = primerGrupo;
        fechas.forEach(iso => { estado[iso] = g; g = oppos(g); });
        repintarTodo();
    }

    // Prefijar los selectores con el grupo automático del primer día (pista útil).
    const selFinde = document.getElementById('seed-finde');
    const selFestivo = document.getElementById('seed-festivo');
    const btnFinde = document.getElementById('btn-sembrar-finde');
    const btnFestivo = document.getElementById('btn-sembrar-festivo');
    if (selFinde) {
        const ps = primerSabadoISO();
        if (ps && auto[ps]) selFinde.value = auto[ps];
    }
    if (selFestivo) {
        const primerFest = celdas.filter(s => festivos.has(s.dataset.fecha)).map(s => s.dataset.fecha).sort()[0];
        if (primerFest && auto[primerFest]) selFestivo.value = auto[primerFest];
    }
    if (btnFinde) btnFinde.addEventListener('click', () => sembrarFindes(selFinde.value));
    if (btnFestivo) btnFestivo.addEventListener('click', () => sembrarFestivos(selFestivo.value));

    form.addEventListener('submit', () => { hidden.value = JSON.stringify(estado); });
})();
