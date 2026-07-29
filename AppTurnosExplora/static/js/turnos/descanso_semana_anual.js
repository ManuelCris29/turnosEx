(function(){
  const leer = (id) => {
    const el = document.getElementById(id);
    return el ? JSON.parse(el.textContent) : null;
  };
  const pre = leer('dsa-preseleccion') || {};
  const marcadores = leer('dsa-marcadores') || {};
  const bloqueadas = new Set(leer('dsa-bloqueadas') || []);   // días con solicitud aprobada
  const otrosMotivos = leer('dsa-otros-motivos') || {};        // descansos individuales (solo lectura)
  const form = document.getElementById('dsaForm');
  const hidden = document.getElementById('seleccion');

  // Días que no admiten descanso manual: en festivo se trabaja y el de mantenimiento ya es
  // el descanso normal de la semana. Los de temporada SÍ son editables: esta pantalla existe
  // justamente para elegir qué día de la semana de temporada descansa cada jornada.
  const TAGS_NO_EDITABLES = ['festivo', 'mantenimiento'];
  document.querySelectorAll('.dia[data-fecha]').forEach(span => {
    const f = span.dataset.fecha;
    const tags = marcadores[f];
    if(tags && tags.length){
      const cont = document.createElement('span');
      cont.className = 'marks';
      tags.forEach(t => { const d = document.createElement('span'); d.className = 'mk mk-' + t; d.title = t; cont.appendChild(d); });
      span.appendChild(cont);
      if(tags.indexOf('temporada') >= 0) span.classList.add('tem-bg');
      if(tags.some(t => TAGS_NO_EDITABLES.includes(t))) span.classList.add('bloqueado');
    }
    // Un día con solicitud aprobada tampoco se toca: la solicitud se apoya en ese descanso.
    if(bloqueadas.has(f)){
      span.classList.add('bloqueado', 'bloqueado-solicitud');
      span.title = 'Ya tiene solicitudes aprobadas: no se puede cambiar su descanso.';
    }
  });

  const estado = {};
  Object.keys(pre).forEach(f => { estado[f] = pre[f].slice().sort(); });

  const ESTADOS = [[], ['AM'], ['PM'], ['AM','PM']];
  function claseDe(arr){
    if(arr.length === 2) return 'sel-amb';
    if(arr[0] === 'AM') return 'sel-am';
    if(arr[0] === 'PM') return 'sel-pm';
    return '';
  }
  function etiqueta(arr){
    if(arr.length === 2) return 'AM·PM';
    return arr[0] || '';
  }
  function pintar(span){
    const f = span.dataset.fecha;
    const arr = estado[f] || [];
    span.classList.remove('sel-am','sel-pm','sel-amb');
    const c = claseDe(arr); if(c) span.classList.add(c);
    const et = span.querySelector('.et');
    if(et) et.textContent = etiqueta(arr);
  }

  // Pintar TODOS los días de semana (incluidos los no editables): un descanso ya guardado
  // debe verse siempre, aunque el día no se pueda modificar.
  const dias = document.querySelectorAll('.dia[data-fecha]:not(.finde):not(.otro)');
  dias.forEach(span => {
    const f = span.dataset.fecha;
    pintar(span);

    // Descansos individuales de otro motivo: referencia de solo lectura (la pantalla anual
    // no los gestiona, así que no entran en `estado` ni se envían).
    const otros = otrosMotivos[f];
    if(otros && otros.length && !(estado[f] || []).length){
      span.classList.add('otro-motivo');
      const et = span.querySelector('.et');
      if(et) et.textContent = otros.length === 2 ? 'AM·PM' : otros[0];
      span.title = 'Descanso individual (otro motivo). Edítalo desde la lista.';
    }

    if(span.classList.contains('bloqueado')) return;
    span.addEventListener('click', () => {
      const actual = estado[f] || [];
      let idx = ESTADOS.findIndex(e => e.length === actual.length && e.every((v,i)=>v===actual[i]));
      if(idx < 0) idx = 0;
      const siguiente = ESTADOS[(idx + 1) % ESTADOS.length];
      if(siguiente.length) estado[f] = siguiente.slice(); else delete estado[f];
      pintar(span);
    });
  });

  form.addEventListener('submit', () => { hidden.value = JSON.stringify(estado); });
})();
