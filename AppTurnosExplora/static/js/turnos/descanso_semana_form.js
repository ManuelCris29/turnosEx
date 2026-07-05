['id_jornada', 'id_motivo', 'id_descripcion'].forEach(id => {
  const el = document.getElementById(id);
  if (el) el.classList.add('form-control');
});
