(function(){
  const sel = document.getElementById('explorador');
  const cont = document.getElementById('deudas_container');
  const totalBox = document.getElementById('pdh_total_box');
  const btn = document.getElementById('btn_pagar');
  const URL_DEUDAS = cont.dataset.url;

  // Si el POST volvió con error, el servidor nos devuelve lo que ya estaba marcado.
  let preseleccion = [];
  const preNode = document.getElementById('pdh_preseleccion');
  if (preNode) {
    try { preseleccion = JSON.parse(preNode.textContent) || []; } catch(e) { preseleccion = []; }
  }

  function mensaje(texto, extraClass){
    cont.textContent = '';
    const div = document.createElement('div');
    div.className = 'pdh-empty' + (extraClass ? ' ' + extraClass : '');
    div.textContent = texto;
    cont.appendChild(div);
  }

  function recalcular(){
    let total = 0, n = 0;
    cont.querySelectorAll('input[name="deudas"]:checked').forEach(ch => {
      total += parseFloat(ch.dataset.horas || '0'); n++;
    });
    totalBox.textContent = (Math.round(total*100)/100) + ' h';
    btn.disabled = (n === 0);
  }

  function span(className, texto){
    const s = document.createElement('span');
    if (className) s.className = className;
    s.textContent = texto;
    return s;
  }

  function render(deudas, marcar){
    if(!deudas || deudas.length === 0){
      mensaje('Este explorador no tiene deudas pendientes. 🎉');
      recalcular();
      return;
    }
    // Nodos en vez de innerHTML: la descripción viene de datos de BD y no debe interpretarse como HTML.
    cont.textContent = '';
    deudas.forEach(d => {
      const esDoblada = d.tipo === 'doblada';
      const label = document.createElement('label');
      label.className = 'deuda-item';

      const ch = document.createElement('input');
      ch.type = 'checkbox';
      ch.name = 'deudas';
      ch.value = d.key;
      ch.dataset.horas = d.horas;
      ch.checked = (marcar || []).indexOf(d.key) !== -1;
      ch.addEventListener('change', recalcular);

      label.appendChild(ch);
      label.appendChild(span('badge-tipo ' + (esDoblada ? 'badge-doblada' : 'badge-permiso'),
                             esDoblada ? 'Doblada' : 'Permiso'));
      label.appendChild(span('', d.descripcion));
      label.appendChild(span('deuda-horas', d.horas + ' h'));
      cont.appendChild(label);
    });
    recalcular();
  }

  function cargar(id, marcar){
    if(!id){ mensaje('Selecciona un explorador para ver sus deudas pendientes.'); recalcular(); return; }
    mensaje('Cargando deudas…');
    fetch(`${URL_DEUDAS}?explorador_id=${encodeURIComponent(id)}`, {headers:{'X-Requested-With':'XMLHttpRequest'}})
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => render(data.deudas, marcar))
      .catch(() => { mensaje('Error al cargar las deudas.', 'text-danger'); recalcular(); });
  }

  sel.addEventListener('change', function(){ cargar(sel.value, []); });

  if (sel.value) {
    cargar(sel.value, preseleccion);
  }
})();
