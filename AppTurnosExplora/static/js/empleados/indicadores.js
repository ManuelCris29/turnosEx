(function () {
    const el = document.getElementById('chartIndicadores');
    if (!el || !window.Chart) return;
    const meses = JSON.parse(document.getElementById('indicadores-meses').textContent);
    const series = JSON.parse(document.getElementById('indicadores-series').textContent);
    new Chart(el, {
        type: 'bar',
        data: {
            labels: meses,
            datasets: series.map(function (s) {
                return { label: s.label, data: s.data, backgroundColor: s.color, borderWidth: 0, borderRadius: 4 };
            })
        },
        options: {
            responsive: true,
            plugins: { legend: { position: 'top' } },
            scales: { x: { stacked: true }, y: { stacked: true, beginAtZero: true } }
        }
    });
})();
