/**
 * Alternancia anual de fines de semana y festivos.
 *
 * Lo que se guarda aquí es la FUENTE DE VERDAD: no hay cálculo automático detrás. Un
 * sábado, domingo o festivo entre semana sin grupo asignado queda SIN PLANIFICAR y así
 * lo verá el explorador, con lo cual el año no está listo hasta que no quede ninguno.
 *
 * Clic en un día: AM trabaja → PM trabaja → sin planificar → AM…
 *
 * La regla de siembra NO vive aquí: se pide al servidor (`/siembra/`). Antes estaba
 * duplicada en este archivo con una variante propia que alternaba los festivos por
 * posición en la lista, de modo que un festivo bloqueado intercalado invertía todos los
 * siguientes sin que nadie se enterara.
 */
(function () {
    const pre = JSON.parse(document.getElementById('ae-preseleccion').textContent);       // {fecha: 'AM'/'PM'} publicado
    const festivos = new Set(JSON.parse(document.getElementById('ae-festivos').textContent)); // festivos lun-vie
    // Festivos que caen en sáb/dom: se marcan igual, pero NO son un caso aparte —
    // manda la alternancia del finde, así que no cambian el comportamiento del clic.
    const festivosFinde = new Set(JSON.parse(document.getElementById('ae-festivos-finde').textContent));
    const bloqueadas = new Set(JSON.parse(document.getElementById('ae-bloqueadas').textContent)); // con solicitudes
    const form = document.getElementById('aeForm');
    const hidden = document.getElementById('seleccion');
    const btnGuardar = document.getElementById('aeGuardar');
    const anio = parseInt(form.querySelector('input[name="anio"]').value, 10);

    const estado = {};  // {fecha: 'AM'/'PM'}; una fecha ausente = sin planificar
    Object.keys(pre).forEach(f => { estado[f] = pre[f]; });

    const CICLO = ['AM', 'PM', null];

    function esEspecial(span) {
        const wd = parseInt(span.dataset.weekday, 10);
        return wd >= 5 || festivos.has(span.dataset.fecha);
    }

    function pintar(span) {
        const f = span.dataset.fecha;
        span.classList.remove('sel-am', 'sel-pm', 'sin-planificar');
        const et = span.querySelector('.et');
        if (estado[f] === 'AM') { span.classList.add('sel-am'); et.textContent = 'AM'; }
        else if (estado[f] === 'PM') { span.classList.add('sel-pm'); et.textContent = 'PM'; }
        else {
            // Sin publicar: no se insinúa ningún grupo, porque no hay ninguno.
            span.classList.add('sin-planificar');
            et.textContent = '—';
            span.title = 'Sin planificar: el explorador no verá turno este día hasta que lo asignes.';
        }
    }

    const celdas = Array.from(document.querySelectorAll('.dia[data-fecha]')).filter(esEspecial);

    function actualizarContador() {
        const faltan = celdas.filter(s => !estado[s.dataset.fecha]).length;
        const chip = document.getElementById('ae-contador');
        if (!chip) return;
        chip.textContent = faltan === 0
            ? 'Año completo: no queda ningún día sin planificar.'
            : `Faltan ${faltan} día(s) por planificar.`;
        chip.className = faltan === 0 ? 'alert alert-success' : 'alert alert-warning';
    }

    document.querySelectorAll('.dia[data-fecha]').forEach(span => {
        if (!esEspecial(span)) {
            span.classList.add('bloqueado');   // día normal: no aplica aquí
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
            const siguiente = CICLO[(CICLO.indexOf(estado[f] || null) + 1) % CICLO.length];
            if (siguiente) estado[f] = siguiente; else delete estado[f];
            pintar(span);
            actualizarContador();
            guardia.revisar();
        });
    });

    // Sin ningún día modificado no se reescribe el año: ver `guardado_atomico.js`.
    const guardia = window.guardadoAtomico({ boton: btnGuardar, instantanea: () => estado });

    // ===========================================================
    //  SEMBRAR: el servidor propone el año entero; aquí solo se pinta.
    //  Los días bloqueados NUNCA se tocan.
    // ===========================================================
    const selFinde = document.getElementById('seed-finde');
    const selFestivo = document.getElementById('seed-festivo');
    const btnSembrar = document.getElementById('btn-sembrar');

    async function sembrar() {
        btnSembrar.disabled = true;
        try {
            const url = `${form.dataset.siembraUrl}?anio=${anio}`
                + `&finde=${encodeURIComponent(selFinde.value)}`
                + `&festivo=${encodeURIComponent(selFestivo.value)}`;
            const resp = await fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.error || 'No se pudo calcular la siembra.');
            Object.entries(data.siembra).forEach(([iso, grupo]) => {
                if (bloqueadas.has(iso)) return;   // seguridad: nunca tocar días bloqueados
                estado[iso] = grupo;
            });
            celdas.forEach(pintar);
            actualizarContador();
            guardia.revisar();   // sembrar sobre un año ya sembrado igual no habilita nada
        } catch (e) {
            alert(e.message);
        } finally {
            btnSembrar.disabled = false;
        }
    }

    if (btnSembrar) btnSembrar.addEventListener('click', sembrar);

    actualizarContador();
    guardia.revisar();
    form.addEventListener('submit', (e) => {
        if (!guardia.sucio()) { e.preventDefault(); return; }
        hidden.value = JSON.stringify(estado);
    });
})();
