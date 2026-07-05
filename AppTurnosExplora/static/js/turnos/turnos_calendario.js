(function(){
  let fechaActual = null;
  let reporteData = null;

  document.addEventListener('DOMContentLoaded', function(){
    setTimeout(function(){
      const cal = new FullCalendar.Calendar(document.getElementById('calendar'), {
        initialView: 'dayGridMonth',
        locale: 'es',
        headerToolbar: { left:'prev,next today', center:'title', right:'' },
        firstDay: 1,
        height: 'auto',
        dateClick: function(info){
          document.querySelectorAll('.fc-day-selected').forEach(el => el.classList.remove('fc-day-selected'));
          info.dayEl.classList.add('fc-day-selected');
          fechaActual = info.dateStr;
          cargarReporte(info.dateStr, info.date);
        },
        dayCellDidMount: function(info){
          if(info.dateStr === fechaActual) info.el.classList.add('fc-day-selected');
        }
      });
      cal.render();
      const hoy = new Date();
      const hoyStr = hoy.toISOString().slice(0,10);
      fechaActual = hoyStr;
      cargarReporte(hoyStr, hoy);
      setTimeout(()=>{
        const el = document.querySelector(`[data-date="${hoyStr}"]`);
        if(el) el.classList.add('fc-day-selected');
      }, 150);
    }, 100);
  });

  function cargarReporte(fechaStr, fechaDate){
    mostrarLoading();
    actualizarFechaHeader(fechaDate, fechaStr);
    fetch(`/turnos/api/reporte-dia/?fecha=${fechaStr}`)
      .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)))
      .then(data => {
        reporteData = { fecha: fechaStr, ...data };
        renderReporte(data);
        document.getElementById('btn-excel').style.display = '';
      })
      .catch(err => mostrarError(err.error || 'Error al cargar el reporte'));
  }

  function renderReporte(data){
    const trabajando = data.trabajando || [];
    const descansando = data.descansando || [];
    const info = data.dia_info || {};

    const am  = trabajando.filter(e => e.jornada_dia === 'AM' || e.jornada_dia === 'DOBLADA');
    const pm  = trabajando.filter(e => e.jornada_dia === 'PM' || e.jornada_dia === 'DOBLADA');
    const desc = descansando;

    document.getElementById('cnt-am').textContent   = am.length;
    document.getElementById('cnt-pm').textContent   = pm.length;
    document.getElementById('cnt-desc').textContent = desc.length;

    document.getElementById('col-am').innerHTML   = am.length   ? am.map(e => cardTrabaja(e,'am')).join('') : vacio('No hay exploradores AM');
    document.getElementById('col-pm').innerHTML   = pm.length   ? pm.map(e => cardTrabaja(e,'pm')).join('') : vacio('No hay exploradores PM');
    document.getElementById('col-desc').innerHTML = desc.length ? desc.map(cardDescansa).join('') : vacio('Todos trabajan este día');

    const badge = document.getElementById('rep-dia-badge');
    badge.innerHTML = '';
    if(info.es_festivo)          badge.innerHTML = '<span class="rep-badge-dia badge-festivo"><i class="fas fa-star"></i> Festivo</span>';
    else if(info.es_finde)       badge.innerHTML = '<span class="rep-badge-dia badge-finde"><i class="fas fa-umbrella-beach"></i> Fin de semana</span>';
    else if(info.es_mantenimiento) badge.innerHTML = '<span class="rep-badge-dia badge-mant"><i class="fas fa-tools"></i> Mantenimiento</span>';
  }

  function cardTrabaja(emp, lado){
    const avClass = emp.jornada_dia === 'DOBLADA' ? 'av-dob' : `av-${lado}`;
    const iniciales = (emp.nombre[0]||'') + (emp.apellido[0]||'');
    let tags = '';
    if(emp.tipo === 'doblada')     tags += '<span class="tag tag-doblada">Dobló</span>';
    else if(emp.tipo === 'cambio') tags += '<span class="tag tag-cambio">Cambio</span>';
    else                           tags += '<span class="tag tag-oficial">Oficial</span>';
    if(emp.permiso) tags += `<span class="tag tag-permiso">${emp.permiso.horas}h permiso</span>`;
    let detalle = '';
    if(emp.jornada_dia === 'DOBLADA') detalle += '<div class="emp-detalle" style="color:#7c3aed;font-weight:600;">AM + PM (dobló)</div>';
    if(emp.cubre_a)   detalle += `<div class="emp-detalle">Cubre a: <b>${emp.cubre_a.nombre}</b></div>`;
    if(emp.permiso && emp.permiso.especificacion) detalle += `<div class="emp-detalle" style="color:#15803d;">${emp.permiso.tipo}: ${emp.permiso.especificacion}</div>`;
    return `
      <div class="emp-card">
        <div class="emp-avatar ${avClass}">${iniciales.toUpperCase()}</div>
        <div class="emp-info">
          <div class="emp-nombre">${emp.nombre} ${emp.apellido}</div>
          ${detalle}
          <div class="emp-tags">${tags}</div>
        </div>
      </div>`;
  }

  function cardDescansa(emp){
    const iniciales = (emp.nombre[0]||'') + (emp.apellido[0]||'');
    const motivo = emp.motivo || 'descanso';
    let detalle = `<div class="emp-detalle"><span class="tag tag-motivo">${capitalizar(motivo)}</span></div>`;
    if(emp.companero) detalle += `<div class="emp-detalle">Con: <b>${emp.companero.nombre}</b></div>`;
    if(emp.permiso && emp.permiso.especificacion) detalle += `<div class="emp-detalle" style="color:#15803d;">${emp.permiso.tipo}: ${emp.permiso.especificacion}</div>`;
    return `
      <div class="emp-card">
        <div class="emp-avatar av-desc">${iniciales.toUpperCase()}</div>
        <div class="emp-info">
          <div class="emp-nombre">${emp.nombre} ${emp.apellido}</div>
          <div class="emp-detalle">Jornada base: <b>${emp.jornada_base || '—'}</b></div>
          ${detalle}
        </div>
      </div>`;
  }

  function vacio(msg){ return `<div class="rep-empty"><i class="fas fa-check-circle" style="color:#86efac;"></i><br>${msg}</div>`; }
  function capitalizar(s){ return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }

  function actualizarFechaHeader(fechaDate, fechaStr){
    const txt = fechaDate.toLocaleDateString('es-CO', {weekday:'long', year:'numeric', month:'long', day:'numeric'});
    document.getElementById('rep-fecha-txt').textContent = txt;
  }

  function mostrarLoading(){
    const spinner = '<div class="rep-loading"><span class="spin">⏳</span> Cargando...</div>';
    ['col-am','col-pm','col-desc'].forEach(id => { document.getElementById(id).innerHTML = spinner; });
    ['cnt-am','cnt-pm','cnt-desc'].forEach(id => { document.getElementById(id).textContent = '…'; });
    document.getElementById('btn-excel').style.display = 'none';
    reporteData = null;
  }
  function mostrarError(msg){
    const html = `<div class="rep-empty" style="color:#dc2626;"><i class="fas fa-exclamation-triangle"></i><br>${msg}</div>`;
    ['col-am','col-pm','col-desc'].forEach(id => { document.getElementById(id).innerHTML = html; });
  }

  window.descargarExcel = function(e){
    e.preventDefault();
    if(!fechaActual) return;
    window.location.href = `/turnos/api/reporte-dia/excel/?fecha=${fechaActual}`;
  };
})();
