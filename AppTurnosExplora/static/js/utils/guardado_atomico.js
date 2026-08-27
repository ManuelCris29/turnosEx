/**
 * Guardado atómico: el botón de guardar solo se habilita si de verdad cambió algo.
 *
 * Las pantallas anuales (descansos de semana, fines de semana/festivos, temporadas,
 * festivos/mantenimiento) reescriben el año COMPLETO al guardar: borran lo publicado
 * y lo vuelven a escribir. Si nadie tocó un día, ese reescribir no aporta nada y sí
 * arriesga (rompe la relación con lo ya aprobado, mueve fechas de auditoría, y deja
 * al usuario sin saber si guardó o no). Por eso, sin cambios no hay guardado.
 *
 * Uso:
 *   const guardia = guardadoAtomico({ boton, instantanea: () => estado });
 *   ...tras cada cambio:  guardia.revisar();
 *
 * `instantanea()` devuelve el estado actual; se compara contra el que había al cargar
 * la página, normalizado (claves ordenadas y arrays ordenados), de modo que volver a
 * dejar un día como estaba cuenta como "sin cambios" y vuelve a deshabilitar el botón.
 */
(function (global) {
  // Orden estable: las claves de un objeto y el contenido de los arrays de valores
  // simples no tienen significado posicional en estas pantallas (son conjuntos de
  // días/jornadas), así que se ordenan para que dos estados iguales serialicen igual.
  function normalizar(valor) {
    if (Array.isArray(valor)) {
      const items = valor.map(normalizar);
      const simples = items.every(v => typeof v === 'string' || typeof v === 'number');
      return simples ? items.slice().sort() : items;
    }
    if (valor && typeof valor === 'object') {
      const salida = {};
      Object.keys(valor).sort().forEach(k => { salida[k] = normalizar(valor[k]); });
      return salida;
    }
    return valor;
  }

  function huella(valor) {
    return JSON.stringify(normalizar(valor));
  }

  function guardadoAtomico(opciones) {
    const boton = opciones.boton;
    const instantanea = opciones.instantanea;
    const tituloSinCambios = opciones.tituloSinCambios
      || 'No has modificado ningún día: no hay nada que guardar.';
    // Sin botón (oculto por permisos, plantilla distinta) el guardia se vuelve inerte
    // y declara SIEMPRE que hay cambios: nunca puede ser él quien bloquee un envío.
    if (!boton || typeof instantanea !== 'function') {
      return { revisar() {}, reiniciar() {}, sucio: () => true };
    }

    let referencia = huella(instantanea());
    const tituloOriginal = boton.title || '';

    function sucio() {
      return huella(instantanea()) !== referencia;
    }

    function revisar() {
      const hayCambios = sucio();
      boton.disabled = !hayCambios;
      boton.classList.toggle('pg-btn-disabled', !hayCambios);
      boton.title = hayCambios ? tituloOriginal : tituloSinCambios;
      return hayCambios;
    }

    // Referencia nueva: lo que hay ahora pasa a ser "lo guardado".
    function reiniciar() {
      referencia = huella(instantanea());
      revisar();
    }

    revisar();
    return { revisar, reiniciar, sucio };
  }

  /**
   * Variante para un <form> normal de Django: la instantánea son sus propios campos.
   *
   * Sirve para las pantallas que no llevan estado en JS pero cuyo guardado TAMPOCO es
   * inocuo: al guardar borran y recrean filas (roles y salas del explorador, o la
   * asignación de jornada, que además estampa `fecha_inicio` con el día de hoy). Volver
   * a guardar sin tocar nada reescribiría ese historial con una fecha nueva.
   *
   * El token CSRF se excluye: cambia entre cargas y no es un dato editado por nadie.
   */
  function paraFormulario(form, boton, opciones) {
    if (!form || !boton) return guardadoAtomico({ boton: null, instantanea: null });

    function campos() {
      const datos = {};
      new FormData(form).forEach((valor, clave) => {
        if (clave === 'csrfmiddlewaretoken') return;
        // Un fichero no se puede comparar por texto (todos serializarian igual y un
        // cambio de adjunto pasaria desapercibido): se marca como cambio siempre.
        const texto = (typeof File !== 'undefined' && valor instanceof File)
          ? (valor.name ? 'archivo:' + valor.name + ':' + valor.size + ':' + Math.random() : '')
          : String(valor);
        // Los multi-select mandan la misma clave varias veces: se acumulan.
        (datos[clave] = datos[clave] || []).push(texto);
      });
      return datos;
    }

    const guardia = guardadoAtomico(Object.assign(
      { boton: boton, instantanea: campos },
      opciones || {}
    ));
    // `input` cubre texto y `change` cubre selects, checkboxes y radios en todos los
    // navegadores; escuchar en el form aprovecha el burbujeo, así que los campos que
    // Django pinte después también quedan cubiertos.
    form.addEventListener('input', guardia.revisar);
    form.addEventListener('change', guardia.revisar);
    return guardia;
  }

  guardadoAtomico.paraFormulario = paraFormulario;
  guardadoAtomico.huella = huella;   // expuesto para pruebas

  // Exportar para uso en módulos ES6 (y para `tests_js/`)
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = guardadoAtomico;
  }

  /**
   * Auto-enganche declarativo: `<form data-guardado-atomico>` con un botón
   * `data-guardar` dentro. Así una plantilla no necesita un fichero JS propio solo
   * para esto, y el envío se cancela si no hay nada que guardar.
   */
  function autoEnganchar(doc) {
    doc.querySelectorAll('form[data-guardado-atomico]').forEach(form => {
      const boton = form.querySelector('[data-guardar]');
      const guardia = paraFormulario(form, boton, {
        tituloSinCambios: form.dataset.guardadoAtomico
          || 'No has modificado nada: no hay nada que guardar.',
      });
      form.addEventListener('submit', e => { if (!guardia.sucio()) e.preventDefault(); });
    });
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => autoEnganchar(document));
    } else {
      autoEnganchar(document);
    }
  }

  global.guardadoAtomico = guardadoAtomico;
})(typeof window !== 'undefined' ? window : globalThis);
