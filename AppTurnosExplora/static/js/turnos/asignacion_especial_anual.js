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
        if (festivos.has(span.dataset.fecha)) {
            const cont = document.createElement('span');
            cont.className = 'marks';
            const d = document.createElement('span');
            d.className = 'mk mk-festivo'; d.title = 'festivo';
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

    form.addEventListener('submit', () => { hidden.value = JSON.stringify(estado); });
})();
