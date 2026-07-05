document.addEventListener('DOMContentLoaded', function () {
    const pills = document.querySelectorAll('.filter-pill');
    const rows = document.querySelectorAll('[id^="tabla-"] tbody tr');
    pills.forEach(b => b.addEventListener('click', () => {
        pills.forEach(x => x.classList.remove('active'));
        b.classList.add('active');
        const f = b.dataset.filter;
        rows.forEach(r => { r.style.display = (f === 'todos' || r.dataset.estado === f) ? '' : 'none'; });
    }));
});
