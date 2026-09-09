/**
 * Los textos de «Detalles del día → Mi Jornada» (Mis Turnos).
 *
 * POR QUÉ ESTE FICHERO
 * --------------------
 * Estas frases vivían dentro de `mostrarDetallesDia`, mezcladas con el HTML y los estilos
 * en línea. Eran la parte que más se toca —cada vez que hay que explicar mejor un tipo de
 * acuerdo— y la única que no podía probarse: `mis_turnos.js` necesita `document`,
 * `fullcalendar` y una respuesta del servidor solo para llegar a ellas.
 *
 * Aquí son lógica PURA (cero `document`, cero `fetch`), así que `tests_js` las prueba con
 * el runner de Node, sin jsdom y sin dependencias. `mis_turnos.js` se queda con el HTML.
 *
 * LO QUE ESTAS FRASES TIENEN QUE DECIR SIEMPRE
 * --------------------------------------------
 * Un día modificado por una solicitud aprobada no es un día propio: se está cubriendo a
 * alguien, devolviendo un favor o intercambiando. Decir solo «ahora trabajas DOBLADA» deja
 * fuera el dato que el explorador necesita —CON QUIÉN—, y era justo lo que faltaba en la
 * doblada permanente y en el cambio de descanso.
 */

/**
 * Nombre legible del acuerdo que modificó un día, a partir de `Turno.tipo_cambio`
 * (vocabulario `core.constants.TipoCambioTurno`, que NO es el de los tipos de solicitud).
 * El detalle del día decía "Cambio de turno" para TODOS los tipos, así que un intercambio de
 * descanso o una doblada de finde se anunciaban con el nombre de otro trámite.
 */
const NOMBRE_ACUERDO = {
  'CAMBIO DESCANSO': 'Cambio de día de descanso',
  'D FDS': 'Doblada de fin de semana',
  'DOBLADA': 'Doblada',
  'DOBLADA PERM': 'Doblada permanente',
  'DOBLADA PERMANENTE': 'Doblada permanente',
  'CT': 'Cambio de turno',
  'CAMBIO TURNO': 'Cambio de turno',
  'CT PERMANENTE': 'Cambio de turno permanente',
  'PAGO REPROGRAMADO': 'Pago reprogramado',
};

// Tipos en los que el día NO es propio: alguien hace un favor y el otro lo devuelve.
// Determina si la frase habla de "cubrir" y "devolver el favor" o de un simple cambio.
const TIPOS_DE_FAVOR = ['DOBLADA', 'D FDS', 'DOBLADA PERM', 'DOBLADA PERMANENTE'];

const DetalleDiaMensajes = {

  NOMBRE_ACUERDO,

  /** Nombre legible del acuerdo; 'Cambio de turno' si el tipo no está en el mapa. */
  nombreAcuerdo(tipoCambio) {
    return NOMBRE_ACUERDO[tipoCambio] || 'Cambio de turno';
  },

  /**
   * `YYYY-MM-DD` → ¿sábado o domingo? Se parte la cadena a mano: `new Date('YYYY-MM-DD')` se
   * interpreta en UTC y en zonas al oeste devuelve el día anterior.
   */
  esFinDeSemana(fechaStr) {
    const partes = (fechaStr || '').split('-').map(Number);
    const [a, m, d] = partes;
    if (!a || !m || !d) return false;
    const wd = new Date(a, m - 1, d).getDay();
    return wd === 0 || wd === 6;
  },

  /**
   * Lo que se trabaja ese día, dicho como lo entiende quien lo lee.
   *
   * En FIN DE SEMANA un día trabajado es AM+PM POR DEFINICIÓN: la unidad del finde es el día
   * completo, no media jornada. Llamarlo "DOBLADA" afirma un esfuerzo extra que no existe —y
   * en este dominio "doblada" significa algo preciso: cubrir un día de más por un favor, con
   * contraparte y con 30 min de deuda (solo de lunes a viernes)—. Quien trabaja su sábado por
   * un cambio de descanso leía "DOBLADA" y parecía que le debían algo.
   */
  loQueTrabaja(jornada, esFinde) {
    if (jornada !== 'DOBLADA') return jornada;
    return esFinde ? 'el día completo (AM + PM)' : 'DOBLADA (AM + PM)';
  },

  /** Etiqueta del badge de la jornada (mismo criterio que `loQueTrabaja`). */
  etiquetaJornada(jornada, esFinde) {
    if (jornada !== 'DOBLADA') return jornada;
    return esFinde ? 'DÍA COMPLETO (AM + PM)' : 'DOBLADA (AM + PM)';
  },

  /**
   * Con QUIÉN es el acuerdo, y qué papel juega cada uno.
   *
   * Es la frase que faltaba: sin ella el explorador ve que su jornada cambió pero no a quién
   * está cubriendo ni a quién le devuelve el favor. Devuelve '' si no hay compañero, para que
   * quien la use pueda concatenarla sin comprobar nada.
   */
  conQuien({ tipoCambio, companero, rol }) {
    if (!companero) return '';
    if (TIPOS_DE_FAVOR.includes(tipoCambio)) {
      return rol === 'receptor'
        ? `Estás <strong>cubriendo a ${companero}</strong> este día.`
        : `Estás <strong>devolviéndole el favor a ${companero}</strong>.`;
    }
    if (tipoCambio === 'CAMBIO DESCANSO') {
      // Trueque: cada uno toma el día del otro, no hay favor ni deuda.
      return `Intercambio con <strong>${companero}</strong>.`;
    }
    if (tipoCambio === 'PAGO REPROGRAMADO') {
      return `Es la doblada que quedó pendiente con <strong>${companero}</strong>.`;
    }
    return `Cambio con <strong>${companero}</strong>.`;
  },

  /**
   * El texto completo de un día que una solicitud aprobada dejó TRABAJADO.
   *
   * `solicitudInfo` lo produce `AcuerdoPorDiaService` (backend) y llega para TODOS los tipos.
   * Antes solo llegaba para algunos, así que la frase de "con quién" aparecía o desaparecía
   * según el trámite; ahora la ausencia de compañero solo puede significar que no lo hay.
   */
  mensajeCambio({ jornada, jornadaPredeterminada, coincidePredeterminada, esFinde,
                  tipoCambio, solicitudInfo }) {
    const trabaja = DetalleDiaMensajes.loQueTrabaja(jornada, esFinde);
    const predeterminada = jornadaPredeterminada || 'N/A';
    // La comparación era `=== 'DESCANSO'`, pero en FINDE el backend devuelve 'Descanso'
    // (title case, ver `JornadaUtils.calcular_jornada_dia`). Resultado: la explicación
    // buena era inalcanzable justo en los findes, y siempre salía la genérica.
    const descansabaEseDia = String(predeterminada).toUpperCase() === 'DESCANSO';

    let mensaje;
    if (tipoCambio === 'PAGO REPROGRAMADO') {
      // El explorador no pudo cumplir su día de doblada y el supervisor le programó este
      // para pagarlo.
      mensaje = 'hoy te doblas (AM + PM) para pagar un día de doblada que no pudiste cumplir. '
        + 'Programado por el supervisor.';
    } else if (coincidePredeterminada) {
      mensaje = `Este turno fue modificado por un cambio aprobado. Tu jornada actual (${trabaja}) `
        + 'coincide con tu jornada predeterminada.';
    } else if (descansabaEseDia) {
      // Ese día en realidad DESCANSABA (temporada o alternancia del finde) y ahora trabaja
      // por un acuerdo: no tenía jornada "predeterminada" que mostrar.
      mensaje = `Normalmente <strong>descansabas</strong> este día; por este acuerdo trabajas `
        + `<strong>${trabaja}</strong>.`;
    } else {
      mensaje = `Tu jornada predeterminada era <strong>${predeterminada}</strong>; ahora trabajas `
        + `<strong>${trabaja}</strong>.`;
    }

    const info = solicitudInfo || {};
    const conQuien = DetalleDiaMensajes.conQuien({
      tipoCambio, companero: info.companero_nombre, rol: info.rol,
    });
    if (conQuien) mensaje += ` ${conQuien}`;
    if (info.fecha_resolucion) mensaje += ` Aprobado el ${info.fecha_resolucion}.`;
    return mensaje;
  },

  /**
   * El texto de un día SIN jornada: descanso propio o día libre por un acuerdo.
   *
   * Devuelve también cómo se rotula, porque las dos cosas se deciden juntas: un CAMBIO DE
   * DESCANSO es un INTERCAMBIO —tu descanso se movió de día—, no un "día libre" ganado por
   * un favor, y el café/DÍA LIBRE solo aplica a la doblada (cesión o pago).
   */
  mensajeDescanso(descansoInfo) {
    const info = descansoInfo || {};
    const companero = info.companero_nombre || 'un compañero';
    const esCambioDescanso = info.origen === 'cambio_descanso';
    const esDiaLibre = !esCambioDescanso && (info.tipo === 'cedio' || info.tipo === 'pago');
    const esDescansoReal = !esDiaLibre;

    let texto;
    if (esCambioDescanso) {
      texto = `Descanso intercambiado con <strong>${companero}</strong>.`;
    } else if (esDescansoReal) {
      if (info.motivo === 'mantenimiento') {
        texto = 'Descanso por día de mantenimiento.';
      } else if (info.motivo === 'temporada') {
        texto = 'Descanso de temporada.';
      } else {
        texto = 'Día de descanso asignado.';
      }
    } else if (info.tipo === 'cedio') {
      texto = `El compañero <strong>${companero}</strong> está trabajando por ti este día.`;
      if (info.fecha_pago) texto += ` Pagarás el ${info.fecha_pago}.`;
    } else if (info.tipo === 'pago') {
      // «este día», no «hoy»: la ficha habla del día SELECCIONADO en el calendario, que
      // rara vez es la fecha actual. Mirando septiembre desde agosto, «hoy» se leía como
      // hoy de verdad. La rama de la cesión ya decía «este día»; ahora las dos coinciden.
      texto = `El compañero <strong>${companero}</strong> está trabajando por ti este día.`;
      if (info.fecha_cesion) texto += ` Tú lo cubriste el ${info.fecha_cesion}.`;
    } else {
      texto = 'Quedaste libre por una doblada. El compañero que te cubrió está trabajando por ti.';
    }

    // Mismo listón que los días trabajados: si el día viene de una solicitud aprobada, se
    // dice cuándo se aprobó. Un día de descanso ASIGNADO (temporada, mantenimiento, finde)
    // no viene de ningún trámite y no lleva fecha.
    if (info.fecha_aprobacion && info.solicitud_id) {
      texto += ` Aprobado el ${info.fecha_aprobacion}.`;
    }

    return {
      texto,
      // El encabezado nombra el ACUERDO cuando lo hay: «Doblada permanente:» dice mucho más
      // que «Día libre:», y es el mismo criterio que en los días trabajados.
      encabezado: info.tipo_solicitud
        ? DetalleDiaMensajes.nombreAcuerdo(info.tipo_solicitud)
        : (esDescansoReal ? 'Día de descanso' : 'Día libre'),
      etiqueta: esDescansoReal ? 'DESCANSO' : 'DÍA LIBRE',
      icono: esDescansoReal ? 'fa-bed' : 'fa-mug-hot',
    };
  },
};

// Exportar para las pruebas de Node (`tests_js/`)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = DetalleDiaMensajes;
}

// Exportar para uso global
window.DetalleDiaMensajes = DetalleDiaMensajes;
