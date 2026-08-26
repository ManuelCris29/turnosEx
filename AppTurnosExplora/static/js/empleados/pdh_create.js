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

  function redondear(n){ return Math.round(n * 100) / 100; }

  // El total es la suma de lo REALMENTE marcado: para las deudas que admiten pago parcial
  // cuenta el importe escrito, no el pendiente completo. Si sumara el pendiente, el
  // supervisor vería una cifra distinta de la que se va a registrar.
  function recalcular(){
    let total = 0, n = 0;
    cont.querySelectorAll('input[name="deudas"]:checked').forEach(ch => {
      const importe = cont.querySelector(`input[data-importe-de="${ch.value}"]`);
      const valor = importe ? parseFloat(importe.value || '0') : parseFloat(ch.dataset.horas || '0');
      total += isNaN(valor) ? 0 : valor;
      n++;
    });
    totalBox.textContent = redondear(total) + ' h';
    btn.disabled = (n === 0);
  }

  function span(className, texto){
    const s = document.createElement('span');
    if (className) s.className = className;
    s.textContent = texto;
    return s;
  }

  // Los campos de importe solo se envían si su deuda está marcada: un importe suelto en el
  // POST, de una deuda que el supervisor desmarcó, se interpretaría como un pago que no quiso.
  function sincronizarImporte(ch){
    const importe = cont.querySelector(`input[data-importe-de="${ch.value}"]`);
    if (!importe) return;
    importe.disabled = !ch.checked;
  }

  function crearItem(item, marcar){
    const label = document.createElement('label');
    label.className = 'deuda-item';

    const ch = document.createElement('input');
    ch.type = 'checkbox';
    ch.name = 'deudas';
    ch.value = item.key;
    ch.dataset.horas = item.horas;
    ch.checked = (marcar || []).indexOf(item.key) !== -1;

    label.appendChild(ch);
    label.appendChild(span('badge-tipo ' + (item.tipo === 'doblada' ? 'badge-doblada' : 'badge-permiso'),
                           item.tipo === 'doblada' ? 'Doblada' : 'Permiso'));
    label.appendChild(span('', item.descripcion));

    if (item.parcial) {
      const importe = document.createElement('input');
      importe.type = 'number';
      importe.className = 'deuda-importe';
      importe.name = 'horas_' + item.key;
      importe.dataset.importeDe = item.key;
      importe.step = '0.5';
      importe.min = '0.5';
      importe.max = String(item.horas_pendientes);
      importe.value = String(item.horas_pendientes);
      importe.title = 'Puedes abonar solo una parte de este mes';
      importe.addEventListener('input', recalcular);
      // Un clic en el campo no debe marcar/desmarcar la casilla que lo envuelve.
      importe.addEventListener('click', e => e.stopPropagation());
      label.appendChild(importe);
      label.appendChild(span('deuda-horas', 'de ' + item.horas_pendientes + ' h'));
    } else {
      label.appendChild(span('deuda-horas', item.horas + ' h'));
    }

    ch.addEventListener('change', function(){ sincronizarImporte(ch); recalcular(); });
    sincronizarImporte(ch);
    return label;
  }

  function crearMes(mes, marcar){
    const bloque = document.createElement('div');
    bloque.className = 'pdh-mes' + (mes.vencido ? ' pdh-mes-vencido' : '');

    const cabecera = document.createElement('div');
    cabecera.className = 'pdh-mes-cabecera';
    cabecera.appendChild(span('pdh-mes-nombre', mes.etiqueta));
    if (mes.vencido) {
      cabecera.appendChild(span('badge-vencido', 'VENCIDO'));
    }
    cabecera.appendChild(span('pdh-mes-cifra', 'Debido ' + mes.horas_debidas + ' h'));
    cabecera.appendChild(span('pdh-mes-cifra', 'Pagado ' + mes.horas_pagadas + ' h'));
    cabecera.appendChild(span('pdh-mes-cifra pdh-mes-pendiente',
                              'Pendiente ' + mes.horas_pendientes + ' h'));
    bloque.appendChild(cabecera);

    (mes.items || []).forEach(item => bloque.appendChild(crearItem(item, marcar)));
    return bloque;
  }

  function render(meses, marcar){
    if(!meses || meses.length === 0){
      mensaje('Este explorador no tiene deudas pendientes. 🎉');
      recalcular();
      return;
    }
    // Nodos en vez de innerHTML: la descripción viene de datos de BD y no debe interpretarse como HTML.
    cont.textContent = '';
    meses.forEach(mes => cont.appendChild(crearMes(mes, marcar)));
    recalcular();
  }

  function cargar(id, marcar){
    if(!id){ mensaje('Selecciona un explorador para ver sus deudas pendientes.'); recalcular(); return; }
    mensaje('Cargando deudas…');
    fetch(`${URL_DEUDAS}?explorador_id=${encodeURIComponent(id)}`, {headers:{'X-Requested-With':'XMLHttpRequest'}})
      .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
      .then(data => render(data.meses, marcar))
      .catch(() => { mensaje('Error al cargar las deudas.', 'text-danger'); recalcular(); });
  }

  sel.addEventListener('change', function(){ cargar(sel.value, []); });

  if (sel.value) {
    cargar(sel.value, preseleccion);
  }
})();
