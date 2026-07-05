(function(){
  const sel = document.getElementById('explorador');
  const cont = document.getElementById('deudas_container');
  const totalBox = document.getElementById('pdh_total_box');
  const btn = document.getElementById('btn_pagar');
  const URL_DEUDAS = cont.dataset.url;

  function recalcular(){
    let total = 0, n = 0;
    cont.querySelectorAll('input[name="deudas"]:checked').forEach(ch => {
      total += parseFloat(ch.dataset.horas || '0'); n++;
    });
    totalBox.textContent = (Math.round(total*100)/100) + ' h';
    btn.disabled = (n === 0);
  }

  function render(deudas){
    if(!deudas || deudas.length === 0){
      cont.innerHTML = '<div class="pdh-empty">Este explorador no tiene deudas pendientes. 🎉</div>';
      recalcular();
      return;
    }
    cont.innerHTML = deudas.map(d => {
      const badge = d.tipo === 'doblada' ? 'badge-doblada' : 'badge-permiso';
      const tipoTxt = d.tipo === 'doblada' ? 'Doblada' : 'Permiso';
      return `<label class="deuda-item">
        <input type="checkbox" name="deudas" value="${d.key}" data-horas="${d.horas}">
        <span class="badge-tipo ${badge}">${tipoTxt}</span>
        <span>${d.descripcion}</span>
        <span class="deuda-horas">${d.horas} h</span>
      </label>`;
    }).join('');
    cont.querySelectorAll('input[name="deudas"]').forEach(ch => ch.addEventListener('change', recalcular));
    recalcular();
  }

  sel.addEventListener('change', function(){
    const id = sel.value;
    if(!id){ cont.innerHTML = '<div class="pdh-empty">Selecciona un explorador para ver sus deudas pendientes.</div>'; recalcular(); return; }
    cont.innerHTML = '<div class="pdh-empty"><i class="fas fa-spinner fa-spin"></i> Cargando deudas…</div>';
    fetch(`${URL_DEUDAS}?explorador_id=${id}`, {headers:{'X-Requested-With':'XMLHttpRequest'}})
      .then(r => r.json())
      .then(data => render(data.deudas))
      .catch(() => { cont.innerHTML = '<div class="pdh-empty text-danger">Error al cargar las deudas.</div>'; recalcular(); });
  });
})();
