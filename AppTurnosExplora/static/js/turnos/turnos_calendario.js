(function(){
  let fechaActual = null;
  let reporteData = null;
  // Contador de peticiones: si el supervisor hace clic en varias fechas seguidas,
  // una respuesta lenta de la anterior podía pintarse encima de la nueva. Solo se
  // renderiza la respuesta de la última petición lanzada.
  let peticionActual = 0;
  // Tipo de día del mes visible ('YYYY-MM-DD' -> {es_festivo,…}), para pintar la
  // cuadrícula sin una petición por celda. Es una capa visual: si falla, el
  // calendario sigue funcionando exactamente igual.
  let diasMes = {};
  let mesCargado = null;

  // Todo el contenido dinámico se inserta con innerHTML, así que cualquier texto
  // que venga de la base de datos (nombres, especificación del permiso, motivos)
  // tiene que escaparse: son campos que capturan los propios usuarios.
  function esc(v){
    if(v === null || v === undefined) return '';
    return String(v).replace(/[&<>"']/g, ch => ({
      '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
    })[ch]);
  }

  // La fecha del navegador en horario LOCAL. `toISOString()` da la fecha UTC y en
  // Colombia (UTC-5) a partir de las 19:00 devolvía el día siguiente: la página
  // abría con el reporte de mañana sin que se notara.
  function fechaLocalISO(d){
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${mm}-${dd}`;
  }

  document.addEventListener('DOMContentLoaded', function(){
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
        pintarCelda(info.el, info.dateStr);
      },
      datesSet: function(info){
        // `view.currentStart` es el mes real mostrado; `info.start` incluye los días
        // de relleno del mes anterior y daría el mes equivocado en las primeras filas.
        const ref = info.view.currentStart;
        cargarMes(ref.getFullYear(), ref.getMonth() + 1);
      }
    });
    const hoy = new Date();
    const hoyStr = fechaLocalISO(hoy);
    // Se fija antes de render() para que dayCellDidMount marque ya la celda de hoy.
    fechaActual = hoyStr;
    cal.render();
    cargarReporte(hoyStr, hoy);
  });

  function cargarMes(anio, mes){
    const clave = `${anio}-${mes}`;
    if(mesCargado === clave) return;
    mesCargado = clave;
    fetch(`/turnos/api/reporte-mes/dias/?anio=${anio}&mes=${mes}`)
      .then(r => r.ok ? r.json() : Promise.reject(r))
      .then(data => {
        diasMes = Object.assign({}, diasMes, data.dias || {});
        repintarCalendario();
      })
      .catch(() => { /* el color es un extra: sin él la página sigue completa */ });
  }

  const CLASES_DIA = ['fc-day-festivo','fc-day-mant','fc-day-finde','fc-day-sinplan'];

  function pintarCelda(el, fechaStr){
    CLASES_DIA.forEach(c => el.classList.remove(c));
    const d = diasMes[fechaStr];
    if(!d) return;
    // Un mismo día puede ser festivo Y estar sin planificar: gana el aviso, que es
    // lo accionable (falta publicar la alternancia).
    if(d.sin_planificar)         el.classList.add('fc-day-sinplan');
    else if(d.es_festivo)        el.classList.add('fc-day-festivo');
    else if(d.es_mantenimiento)  el.classList.add('fc-day-mant');
    else if(d.es_finde)          el.classList.add('fc-day-finde');
    el.title = [d.es_festivo && 'Festivo', d.es_finde && 'Fin de semana',
                d.es_mantenimiento && 'Día de mantenimiento',
                d.sin_planificar && 'Sin alternancia publicada: nadie ha planificado este día']
                .filter(Boolean).join(' · ');
  }

  function repintarCalendario(){
    document.querySelectorAll('#calendar .fc-daygrid-day[data-date]').forEach(el => {
      pintarCelda(el, el.getAttribute('data-date'));
    });
  }

  function cargarReporte(fechaStr, fechaDate){
    const miPeticion = ++peticionActual;
    mostrarLoading();
    actualizarFechaHeader(fechaDate, fechaStr);
    fetch(`/turnos/api/reporte-dia/?fecha=${encodeURIComponent(fechaStr)}`)
      .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)))
      .then(data => {
        if(miPeticion !== peticionActual) return;  // llegó tarde: ya hay otra fecha en pantalla
        reporteData = { fecha: fechaStr, ...data };
        renderReporte(data);
        document.getElementById('btn-excel').style.display = '';
      })
      .catch(err => {
        if(miPeticion !== peticionActual) return;
        mostrarError((err && err.error) || 'Error al cargar el reporte');
      });
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

    // Sin alternancia publicada nadie sale trabajando, pero eso NO es un descanso:
    // es un día sin planificar. Sin este aviso, el reporte de un año no sembrado es
    // indistinguible de uno real con las columnas vacías.
    const msgVacio = info.sin_planificar
      ? 'Día sin alternancia publicada: no se sabe quién trabaja'
      : null;

    document.getElementById('col-am').innerHTML   = am.length   ? am.map(e => cardTrabaja(e,'am')).join('') : vacio(msgVacio || 'No hay exploradores AM');
    document.getElementById('col-pm').innerHTML   = pm.length   ? pm.map(e => cardTrabaja(e,'pm')).join('') : vacio(msgVacio || 'No hay exploradores PM');
    document.getElementById('col-desc').innerHTML = desc.length ? desc.map(cardDescansa).join('') : vacio('Todos trabajan este día');

    renderDeuda(data.deuda_corte);

    const badge = document.getElementById('rep-dia-badge');
    badge.innerHTML = '';
    if(info.es_festivo)          badge.innerHTML = '<span class="rep-badge-dia badge-festivo"><i class="fas fa-star"></i> Festivo</span>';
    else if(info.es_finde)       badge.innerHTML = '<span class="rep-badge-dia badge-finde"><i class="fas fa-umbrella-beach"></i> Fin de semana</span>';
    else if(info.es_mantenimiento) badge.innerHTML = '<span class="rep-badge-dia badge-mant"><i class="fas fa-tools"></i> Mantenimiento</span>';
    if(info.sin_planificar){
      badge.innerHTML += '<span class="rep-badge-dia badge-sinplan" title="Este día no tiene publicada la alternancia de findes/festivos">'
                       + '<i class="fas fa-exclamation-triangle"></i> Sin planificar</span>';
    }
  }

  // Los MISMOS avisos que el Excel pinta en sus columnas Restricción / Sanción /
  // Doblada pendiente. Los datos ya venían en el JSON; sin esto había que descargar
  // el Excel para enterarse de que alguien está sancionado o con restricción médica.
  function chipsAviso(emp){
    let out = '';
    const r = emp.restriccion, sa = emp.sancion, d = emp.deuda_reprogramacion;
    if(r){
      const det = [r.tipo, r.recomendacion, r.fecha_fin ? `Hasta ${fmtFecha(r.fecha_fin)}` : 'Sin fecha de fin']
                    .filter(Boolean).join(' · ');
      out += `<span class="tag tag-restriccion" title="${esc(det)}">⚠ Restricción</span>`;
    }
    if(sa){
      const det = [sa.motivo, `Del ${fmtFecha(sa.fecha_inicio)} al ${sa.fecha_fin ? fmtFecha(sa.fecha_fin) : '—'}`]
                    .filter(Boolean).join(' · ');
      out += `<span class="tag tag-sancion" title="${esc(det)}">⛔ Sancionado</span>`;
    }
    if(d){
      if(d.paga_hoy){
        out += `<span class="tag tag-paga-hoy" title="${esc('Hoy cumple la doblada que debía del ' + fmtFecha(d.fecha_original))}">💥 Paga doblada hoy</span>`;
      } else {
        const det = `Debe la doblada del ${fmtFecha(d.fecha_original)}`
                  + (d.fecha_reprogramada ? ` · la paga el ${fmtFecha(d.fecha_reprogramada)}` : ' · sin fecha asignada');
        out += `<span class="tag tag-deuda" title="${esc(det)}">🔁 Debe doblada</span>`;
      }
    }
    return out;
  }

  // El permiso es el MISMO dato en las dos columnas, así que lo pinta una sola función:
  // "Trabajan" lo sacaba con horas pero SIN el estado (un permiso pendiente se leía como
  // concedido) y "Descansan" no lo sacaba en absoluto.
  //
  // QUÉ decir lo decide `PermisoChip` —lógica pura, probada en `tests_js/`—; aquí solo se
  // pinta y se escapa, que es lo que sí necesita el DOM.
  function chipPermiso(emp){
    const chip = window.PermisoChip && window.PermisoChip.describir(emp.permiso);
    if(!chip) return '';
    return `<span class="tag ${chip.clase}" title="${esc(chip.detalle)}">${esc(chip.etiqueta)}</span>`;
  }

  function fmtFecha(iso){
    if(!iso) return '';
    const p = String(iso).split('-');
    return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : String(iso);
  }

  function cardTrabaja(emp, lado){
    const avClass = emp.jornada_dia === 'DOBLADA' ? 'av-dob' : `av-${lado}`;
    const iniciales = (emp.nombre[0]||'') + (emp.apellido[0]||'');
    let tags = '';
    if(emp.tipo === 'doblada')     tags += '<span class="tag tag-doblada">Dobló</span>';
    else if(emp.tipo === 'cambio') tags += '<span class="tag tag-cambio">Cambio</span>';
    else                           tags += '<span class="tag tag-oficial">Oficial</span>';
    tags += chipPermiso(emp);
    tags += chipsAviso(emp);
    let detalle = '';
    if(emp.jornada_dia === 'DOBLADA') detalle += '<div class="emp-detalle" style="color:#7c3aed;font-weight:600;">AM + PM (dobló)</div>';
    if(emp.cubre_a)   detalle += `<div class="emp-detalle">Cubre a: <b>${esc(emp.cubre_a.nombre)}</b></div>`;
    if(emp.permiso && emp.permiso.especificacion) detalle += `<div class="emp-detalle" style="color:#15803d;">${esc(emp.permiso.tipo)}: ${esc(emp.permiso.especificacion)}</div>`;
    return `
      <div class="emp-card">
        <div class="emp-avatar ${avClass}">${esc(iniciales.toUpperCase())}</div>
        <div class="emp-info">
          <div class="emp-nombre">${esc(emp.nombre)} ${esc(emp.apellido)}</div>
          ${detalle}
          <div class="emp-tags">${tags}</div>
        </div>
      </div>`;
  }

  function cardDescansa(emp){
    const iniciales = (emp.nombre[0]||'') + (emp.apellido[0]||'');
    const motivo = emp.motivo || 'descanso';
    const esSinPlan = motivo === 'sin alternancia publicada';
    const tagCls = esSinPlan ? 'tag tag-motivo tag-sinplan' : 'tag tag-motivo';
    let detalle = `<div class="emp-detalle"><span class="${tagCls}">${esc(capitalizar(motivo))}</span></div>`;
    if(emp.companero) detalle += `<div class="emp-detalle">Con: <b>${esc(emp.companero.nombre)}</b></div>`;
    if(emp.permiso && emp.permiso.especificacion) detalle += `<div class="emp-detalle" style="color:#15803d;">${esc(emp.permiso.tipo)}: ${esc(emp.permiso.especificacion)}</div>`;
    // El chip de permiso también aquí: quien descansa puede tener permiso ese día (un rango
    // que abarca su descanso), y sin él la columna solo lo delataba si traía especificación.
    const avisos = chipPermiso(emp) + chipsAviso(emp);
    if(avisos) detalle += `<div class="emp-tags">${avisos}</div>`;
    return `
      <div class="emp-card">
        <div class="emp-avatar av-desc">${esc(iniciales.toUpperCase())}</div>
        <div class="emp-info">
          <div class="emp-nombre">${esc(emp.nombre)} ${esc(emp.apellido)}</div>
          <div class="emp-detalle">Jornada base: <b>${esc(emp.jornada_base || '—')}</b></div>
          ${detalle}
        </div>
      </div>`;
  }

  // Titular de la deuda del mes hasta la fecha elegida. El detalle nominal vive en
  // /empleados/sanciones/morosos/?corte=…, que es a donde lleva el enlace: aquí solo
  // interesa saber si hay algo que mirar.
  function renderDeuda(d){
    const box = document.getElementById('rep-deuda');
    if(!box) return;
    if(!d){ box.style.display = 'none'; return; }
    const dia = Number(fechaActual.split('-')[2]);
    box.style.display = '';
    if(!d.exploradores){
      box.className = 'rep-deuda rep-deuda-ok';
      box.innerHTML = `<i class="fas fa-check-circle"></i> Nadie debe horas del 1 al ${dia} de este mes.`;
      return;
    }
    const etiqueta = d.proyectada ? 'Deuda proyectada' : 'Deuda pendiente';
    const nota = d.proyectada
      ? ' <small>(la fecha aún no ha llegado: incluye días no vencidos)</small>' : '';
    box.className = 'rep-deuda rep-deuda-hay';
    box.innerHTML = `<i class="fas fa-hand-holding-usd"></i> ${etiqueta} del 1 al ${dia}: `
      + `<b>${esc(d.exploradores)}</b> explorador(es) · <b>${esc(d.horas)} h</b> (${esc(d.minutos)} min)${nota}`
      + `<a href="${esc(box.dataset.urlMorosos)}?corte=${encodeURIComponent(fechaActual)}">Ver quién debe</a>`;
  }

  // SweetAlert2 lo carga base.html; el alert nativo es solo por si faltara.
  function avisarError(msg){
    if(typeof Swal !== 'undefined') Swal.fire({icon:'error', title:'Descarga fallida', text:msg});
    else alert(msg);
  }

  function vacio(msg){ return `<div class="rep-empty"><i class="fas fa-check-circle" style="color:#86efac;"></i><br>${esc(msg)}</div>`; }
  function capitalizar(s){ return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }

  function actualizarFechaHeader(fechaDate, fechaStr){
    const txt = fechaDate.toLocaleDateString('es-CO', {weekday:'long', year:'numeric', month:'long', day:'numeric'});
    document.getElementById('rep-fecha-txt').textContent = txt;
  }

  function mostrarLoading(){
    const spinner = '<div class="rep-loading"><span class="spin">⏳</span> Cargando...</div>';
    ['col-am','col-pm','col-desc'].forEach(id => { document.getElementById(id).innerHTML = spinner; });
    ['cnt-am','cnt-pm','cnt-desc'].forEach(id => { document.getElementById(id).textContent = '…'; });
    document.getElementById('rep-dia-badge').innerHTML = '';
    document.getElementById('rep-deuda').style.display = 'none';
    document.getElementById('btn-excel').style.display = 'none';
    reporteData = null;
  }
  function mostrarError(msg){
    const html = `<div class="rep-empty" style="color:#dc2626;"><i class="fas fa-exclamation-triangle"></i><br>${esc(msg)}</div>`;
    ['col-am','col-pm','col-desc'].forEach(id => { document.getElementById(id).innerHTML = html; });
  }

  // Con `window.location.href`, un 500 del endpoint hacía que el navegador abriera el
  // JSON de error como si fuera la descarga. Así el error se ve donde el supervisor
  // está mirando, y el botón vuelve a su estado.
  function descargarExcel(e){
    e.preventDefault();
    if(!fechaActual) return;
    const btn = document.getElementById('btn-excel');
    const original = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generando…';
    btn.style.pointerEvents = 'none';
    fetch(`/turnos/api/reporte-dia/excel/?fecha=${encodeURIComponent(fechaActual)}`)
      .then(r => {
        if(r.ok) return r.blob();
        return r.json().then(j => Promise.reject(j && j.error), () => Promise.reject(null));
      })
      .then(blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `reporte_operacion_${fechaActual}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
      })
      .catch(msg => avisarError(msg || 'No se pudo generar el Excel. Inténtalo de nuevo.'))
      .finally(() => { btn.innerHTML = original; btn.style.pointerEvents = ''; });
  }

  document.addEventListener('DOMContentLoaded', function(){
    document.getElementById('btn-excel').addEventListener('click', descargarExcel);
  });
})();
