/**
 * Cómo se anuncia un PERMISO ESPECIAL en el reporte operacional del día.
 *
 * POR QUÉ ES UN MÓDULO APARTE
 * ---------------------------
 * `ReporteDiaService` manda al reporte los permisos APROBADOS y los PENDIENTES, y lo hace a
 * propósito: el supervisor necesita ver lo que todavía está por resolver. Pero la tarjeta los
 * pintaba idénticos —«3h permiso» en verde, sin más—, así que una ausencia que NADIE ha
 * autorizado se leía exactamente igual que una concedida, y el supervisor planeaba el día
 * contando con ella. El Excel sí imprime el estado; esta es la misma información en pantalla.
 *
 * Decidir CÓMO se anuncia es lógica pura, así que vive aquí y se prueba sin navegador
 * (`tests_js/permiso-chip.test.cjs`). El HTML y el escapado se quedan en la pantalla, que es
 * quien sabe de DOM. Mismo reparto que `detalle-dia-mensajes.js`.
 */
const PermisoChip = {
  /** Un permiso solo cuenta como concedido si está APROBADO; cualquier otra cosa es aviso. */
  estaAprobado(permiso) {
    return String((permiso && permiso.estado) || '').trim().toUpperCase() === 'APROBADO';
  },

  /**
   * `{clase, etiqueta, detalle}` del chip de permiso, o `null` si no hay permiso.
   *
   * `clase` es el modificador CSS (`tag-permiso` / `tag-permiso-pend`), `etiqueta` el texto
   * corto del chip y `detalle` lo que se lee al posar el cursor. Todo texto plano: quien lo
   * pinta se encarga de escaparlo.
   */
  describir(permiso) {
    if (!permiso) return null;
    const aprobado = PermisoChip.estaAprobado(permiso);
    const estado = String(permiso.estado || '').trim();
    // Sin horas no se inventa un 0: se omite la cifra y queda «Permiso».
    const horas = (permiso.horas === null || permiso.horas === undefined || permiso.horas === '')
      ? null : permiso.horas;
    const base = horas === null ? 'Permiso' : `${horas}h permiso`;
    return {
      clase: aprobado ? 'tag-permiso' : 'tag-permiso-pend',
      etiqueta: aprobado ? base : `${base} · ${PermisoChip._legible(estado)}`,
      detalle: [
        permiso.tipo,
        permiso.especificacion,
        aprobado
          ? 'Permiso aprobado'
          : 'Todavía sin aprobar: no cuentes con esta ausencia al planear el día',
      ].filter(Boolean).join(' · '),
    };
  },

  /** 'PENDIENTE' -> 'Pendiente'. Un estado vacío no debe dejar el chip a medias. */
  _legible(estado) {
    if (!estado) return 'Sin aprobar';
    const txt = estado.toLowerCase();
    return txt.charAt(0).toUpperCase() + txt.slice(1);
  },
};

// Exportar para las pruebas de Node (`tests_js/`)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = PermisoChip;
}

// Exportar para uso global
window.PermisoChip = PermisoChip;
