(function(){
  const roles = document.getElementById('id_roles');
  const grpSalas = document.getElementById('grp_salas');
  const grpJornada = document.getElementById('grp_jornada');
  const grpSupervisor = document.getElementById('grp_supervisor');
  const aviso = document.getElementById('aviso_supervisor');
  if(!roles) return;

  function esSupervisor(){
    return Array.from(roles.selectedOptions || []).some(o => (o.text || '').toLowerCase().includes('supervisor'));
  }
  function toggle(){
    const sup = esSupervisor();
    [grpSalas, grpJornada, grpSupervisor].forEach(g => { if(g) g.style.display = sup ? 'none' : ''; });
    if(aviso) aviso.style.display = sup ? '' : 'none';
    if(sup){
      const salas = document.getElementById('id_salas');
      const jornada = document.getElementById('id_jornada');
      const supervisor = document.getElementById('id_supervisor');
      if(salas) Array.from(salas.options).forEach(o => o.selected = false);
      if(jornada) jornada.value = '';
      if(supervisor) supervisor.value = '';
    }
  }
  roles.addEventListener('change', toggle);
  toggle();
})();
