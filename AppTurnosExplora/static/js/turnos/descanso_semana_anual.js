(function(){
  const pre = JSON.parse(document.getElementById('dsa-preseleccion').textContent);
  const marcadores = JSON.parse(document.getElementById('dsa-marcadores').textContent);
  const form = document.getElementById('dsaForm');
  const hidden = document.getElementById('seleccion');

  const TAGS_BLOQUEADOS = ['temporada', 'festivo', 'mantenimiento'];
  document.querySelectorAll('.dia[data-fecha]').forEach(span => {
    const tags = marcadores[span.dataset.fecha];
    if(!tags || !tags.length) return;
    const cont = document.createElement('span');
    cont.className = 'marks';
    tags.forEach(t => { const d = document.createElement('span'); d.className = 'mk mk-' + t; d.title = t; cont.appendChild(d); });
    span.appendChild(cont);
    if(tags.indexOf('temporada') >= 0) span.classList.add('tem-bg');
    if(tags.some(t => TAGS_BLOQUEADOS.includes(t))) span.classList.add('bloqueado');
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
    span.querySelector('.et').textContent = etiqueta(arr);
  }
  document.querySelectorAll('.dia[data-fecha]:not(.finde):not(.bloqueado)').forEach(span => {
    pintar(span);
    span.addEventListener('click', () => {
      const f = span.dataset.fecha;
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
