(function(){
  const sel = document.getElementById('explorador');
  const cont = document.getElementById('deudas_container');
  const totalBox = document.getElementById('pdh_total_box');
  const btn = document.getElementById('btn_pagar');
  const URL_DEUDAS = cont.dataset.url;
  const credBloque = document.getElementById('credito_bloque');
  const credSaldoBox = document.getElementById('credito_saldo');
  const credInput = document.getElementById('horas_credito');
  let credDisponible = 0;

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
    limitarCredito(total);
  }

  // El crédito es un MEDIO DE PAGO de este PDH, así que no puede exceder ni el saldo a
  // favor ni lo que el pago salda. El tope se recalcula con cada cambio de selección
  // porque el total baila: si no, un importe válido para 2 h quedaría de más al desmarcar
  // una deuda, y el servidor lo rechazaría tras enviar el formulario.
  function limitarCredito(total){
    if (!credInput) return;
    const tope = redondear(Math.min(credDisponible, total));
    credInput.max = String(tope);
    const valor = parseFloat(credInput.value || '0');
    if (!isNaN(valor) && valor > tope) credInput.value = tope > 0 ? String(tope) : '';
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

  // Un mes vencido ya no se cobra: se salda cumpliendo la sanción. La casilla se deshabilita
  // en vez de ocultar el mes, porque el supervisor necesita seguir viendo lo que se debe.
  function crearItem(item, marcar, pagable){
    const label = document.createElement('label');
    label.className = 'deuda-item';

    const ch = document.createElement('input');
    ch.type = 'checkbox';
    ch.name = 'deudas';
    ch.value = item.key;
    ch.dataset.horas = item.horas;
    ch.checked = pagable && (marcar || []).indexOf(item.key) !== -1;
    ch.disabled = !pagable;
    if (!pagable) {
      label.classList.add('deuda-item-bloqueada');
      label.title = 'El plazo de este mes venció: esta deuda ya no se paga.';
    }

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
      importe.disabled = !pagable;
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
    if (!mes.pagable) {
      cabecera.appendChild(span('pdh-mes-nota', 'No se puede pagar: el plazo cerró'));
    } else if (mes.fin_de_plazo) {
      // AVISO PREVIO. Sin esto la pantalla solo hablaba del plazo una vez perdido: el día 1
      // el mes salía VENCIDO y bloqueado, pero el día 31 nada advertía de que cerraba esa
      // noche. Y perderlo no se arregla pagando después — el explorador queda sancionado.
      // El día, los días restantes y la urgencia los calcula el servidor (PagoHorasService).
      var texto = mes.dias_restantes === 0
        ? 'Último día para pagar este mes (' + mes.fin_de_plazo + ')'
        : 'Se puede pagar hasta el ' + mes.fin_de_plazo
          + ' · quedan ' + mes.dias_restantes + ' días';
      cabecera.appendChild(span('pdh-mes-plazo' + (mes.urgente ? ' pdh-mes-plazo-urgente' : ''),
                                texto));
    }
    cabecera.appendChild(span('pdh-mes-cifra', 'Debido ' + mes.horas_debidas + ' h'));
    cabecera.appendChild(span('pdh-mes-cifra', 'Pagado ' + mes.horas_pagadas + ' h'));
    cabecera.appendChild(span('pdh-mes-cifra pdh-mes-pendiente',
                              'Pendiente ' + mes.horas_pendientes + ' h'));
    bloque.appendChild(cabecera);

    // `pagable` lo decide el servidor (PagoHorasService): aquí no se recalcula la fecha.
    (mes.items || []).forEach(item => bloque.appendChild(crearItem(item, marcar, mes.pagable !== false)));
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
      .then(data => { mostrarCredito(data.horas_credito || 0); render(data.meses, marcar); })
      .catch(() => { mensaje('Error al cargar las deudas.', 'text-danger'); recalcular(); });
  }

  // Sin saldo no se enseña el bloque: un campo a cero solo invita a preguntar qué es.
  function mostrarCredito(horas){
    credDisponible = parseFloat(horas) || 0;
    if (!credBloque) return;
    credBloque.hidden = credDisponible <= 0;
    if (credSaldoBox) credSaldoBox.textContent = String(credDisponible);
    if (credBloque.hidden && credInput) credInput.value = '';
  }

  if (credInput) credInput.addEventListener('input', recalcular);

  sel.addEventListener('change', function(){ mostrarCredito(0); cargar(sel.value, []); });

  if (sel.value) {
    cargar(sel.value, preseleccion);
  }
})();
