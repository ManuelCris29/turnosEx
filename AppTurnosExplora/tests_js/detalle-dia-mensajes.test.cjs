/**
 * `static/js/utils/detalle-dia-mensajes.js`
 *
 * Los textos de «Detalles del día → Mi Jornada», la pantalla que más mira el explorador.
 * Lo que se prueba aquí no es cosmético: es la frase que dice CON QUIÉN es el acuerdo. Sin
 * ella, un día de doblada permanente decía que ahora se trabaja AM+PM sin nombrar a la
 * persona a la que se está cubriendo, que es el dato que hace falta para reclamar, cuadrar
 * o simplemente entender el día.
 *
 * Es lógica pura (cero `document`), así que se prueba sin jsdom y sin instalar nada.
 */
const test = require('node:test');
const assert = require('node:assert/strict');

const { cargarUtil } = require('./_setup.cjs');

const M = cargarUtil('utils/detalle-dia-mensajes.js');

// 2026-09-01 es martes; 2026-09-05 sábado y 2026-09-06 domingo.
const MARTES = '2026-09-01';
const SABADO = '2026-09-05';
const DOMINGO = '2026-09-06';


test('nombreAcuerdo', async (t) => {
  await t.test('traduce cada tipo a su nombre legible', () => {
    assert.equal(M.nombreAcuerdo('DOBLADA PERM'), 'Doblada permanente');
    assert.equal(M.nombreAcuerdo('CAMBIO DESCANSO'), 'Cambio de día de descanso');
    assert.equal(M.nombreAcuerdo('D FDS'), 'Doblada de fin de semana');
    assert.equal(M.nombreAcuerdo('CT PERMANENTE'), 'Cambio de turno permanente');
    assert.equal(M.nombreAcuerdo('PAGO REPROGRAMADO'), 'Pago reprogramado');
  });

  await t.test('entiende también el vocabulario de los TIPOS DE SOLICITUD', () => {
    // `Turno.tipo_cambio` dice 'DOBLADA PERM' y `TipoSolicitudCambio.nombre` dice
    // 'DOBLADA PERMANENTE'. El descanso rotula con el segundo, así que ambos tienen
    // que dar el mismo nombre legible o el mismo acuerdo se anunciaría distinto
    // según el lado del día en que se mire.
    assert.equal(M.nombreAcuerdo('DOBLADA PERMANENTE'), 'Doblada permanente');
    assert.equal(M.nombreAcuerdo('CAMBIO TURNO'), 'Cambio de turno');
  });

  await t.test('un tipo desconocido no rompe la ficha', () => {
    assert.equal(M.nombreAcuerdo('LO QUE SEA'), 'Cambio de turno');
    assert.equal(M.nombreAcuerdo(undefined), 'Cambio de turno');
  });
});


test('esFinDeSemana', async (t) => {
  await t.test('reconoce sábado y domingo sin desfase de zona horaria', () => {
    assert.equal(M.esFinDeSemana(SABADO), true);
    assert.equal(M.esFinDeSemana(DOMINGO), true);
    assert.equal(M.esFinDeSemana(MARTES), false);
  });

  await t.test('una fecha vacía o mal formada no rompe', () => {
    assert.equal(M.esFinDeSemana(''), false);
    assert.equal(M.esFinDeSemana(null), false);
    assert.equal(M.esFinDeSemana('no-es-fecha'), false);
  });
});


test('etiquetaJornada / loQueTrabaja', async (t) => {
  await t.test('en finde una doblada es un DÍA COMPLETO, no una doblada', () => {
    // "Doblada" significa algo preciso: cubrir un día de más por un favor, con deuda de
    // 30 min y solo de lunes a viernes. Llamar así al sábado propio afirma un esfuerzo
    // extra que no existe.
    assert.equal(M.etiquetaJornada('DOBLADA', true), 'DÍA COMPLETO (AM + PM)');
    assert.equal(M.loQueTrabaja('DOBLADA', true), 'el día completo (AM + PM)');
  });

  await t.test('entre semana sí es una doblada', () => {
    assert.equal(M.etiquetaJornada('DOBLADA', false), 'DOBLADA (AM + PM)');
    assert.equal(M.loQueTrabaja('DOBLADA', false), 'DOBLADA (AM + PM)');
  });

  await t.test('una jornada normal se muestra tal cual', () => {
    assert.equal(M.etiquetaJornada('AM', false), 'AM');
    assert.equal(M.loQueTrabaja('PM', true), 'PM');
  });
});


test('conQuien', async (t) => {
  await t.test('en una doblada distingue cubrir de devolver el favor', () => {
    assert.match(
      M.conQuien({ tipoCambio: 'DOBLADA', companero: 'arley arley', rol: 'receptor' }),
      /cubriendo a arley arley/);
    assert.match(
      M.conQuien({ tipoCambio: 'DOBLADA', companero: 'arley arley', rol: 'solicitante' }),
      /devolviéndole el favor a arley arley/);
  });

  await t.test('la doblada permanente se trata como favor, igual que la puntual', () => {
    // Era el hueco: `DOBLADA PERM` no traía compañero del backend, así que esta frase
    // nunca llegaba a construirse y el día se quedaba sin decir a quién se cubre.
    assert.match(
      M.conQuien({ tipoCambio: 'DOBLADA PERM', companero: 'arley arley', rol: 'receptor' }),
      /cubriendo a arley arley/);
    assert.match(
      M.conQuien({ tipoCambio: 'DOBLADA PERMANENTE', companero: 'arley arley', rol: 'solicitante' }),
      /devolviéndole el favor a arley arley/);
  });

  await t.test('el cambio de descanso es un trueque, no un favor', () => {
    // No hay deuda ni favor: cada uno toma el día del otro.
    const frase = M.conQuien({ tipoCambio: 'CAMBIO DESCANSO', companero: 'Jessika', rol: 'receptor' });
    assert.match(frase, /Intercambio con <strong>Jessika<\/strong>/);
    assert.doesNotMatch(frase, /cubriendo|favor/);
  });

  await t.test('un cambio de turno (puntual o permanente) solo dice con quién', () => {
    assert.match(M.conQuien({ tipoCambio: 'CT', companero: 'Jhon Areiza', rol: 'receptor' }),
      /Cambio con <strong>Jhon Areiza<\/strong>/);
    assert.match(M.conQuien({ tipoCambio: 'CT PERMANENTE', companero: 'Marco', rol: 'solicitante' }),
      /Cambio con <strong>Marco<\/strong>/);
  });

  await t.test('sin compañero devuelve cadena vacía, para poder concatenar sin comprobar', () => {
    assert.equal(M.conQuien({ tipoCambio: 'DOBLADA', companero: null, rol: 'receptor' }), '');
    assert.equal(M.conQuien({ tipoCambio: 'DOBLADA', companero: undefined }), '');
  });
});


test('mensajeCambio', async (t) => {
  // El caso que originó el trabajo: 01/09/2026, isabel dobla cubriendo a arley por una
  // doblada permanente. El mensaje decía qué trabaja, pero no con quién.
  const dobladaPermanente = {
    jornada: 'DOBLADA',
    jornadaPredeterminada: 'AM',
    coincidePredeterminada: false,
    esFinde: false,
    tipoCambio: 'DOBLADA PERM',
    solicitudInfo: {
      companero_nombre: 'arley arley',
      rol: 'receptor',
      fecha_resolucion: '27/08/2026 14:29',
    },
  };

  await t.test('dice qué cambió, con quién y cuándo se aprobó', () => {
    const texto = M.mensajeCambio(dobladaPermanente);
    assert.match(texto, /Tu jornada predeterminada era <strong>AM<\/strong>/);
    assert.match(texto, /ahora trabajas <strong>DOBLADA \(AM \+ PM\)<\/strong>/);
    assert.match(texto, /cubriendo a arley arley/);
    assert.match(texto, /Aprobado el 27\/08\/2026 14:29/);
  });

  await t.test('sin solicitud_info no inventa compañero ni fecha', () => {
    const texto = M.mensajeCambio({ ...dobladaPermanente, solicitudInfo: null });
    assert.match(texto, /ahora trabajas/);
    assert.doesNotMatch(texto, /cubriendo|Aprobado/);
  });

  await t.test('si ese día descansaba, no habla de "jornada predeterminada"', () => {
    const texto = M.mensajeCambio({ ...dobladaPermanente, jornadaPredeterminada: 'DESCANSO' });
    assert.match(texto, /Normalmente <strong>descansabas<\/strong> este día/);
  });

  await t.test('en finde el backend manda "Descanso" en minúsculas y también cuenta', () => {
    // La comparación era `=== 'DESCANSO'` y en finde llega 'Descanso' (title case), así
    // que la explicación buena era inalcanzable justo los findes.
    const texto = M.mensajeCambio({
      ...dobladaPermanente, jornadaPredeterminada: 'Descanso', esFinde: true,
    });
    assert.match(texto, /Normalmente <strong>descansabas<\/strong>/);
    assert.match(texto, /el día completo \(AM \+ PM\)/);
  });

  await t.test('cuando la jornada coincide con la predeterminada, lo dice así', () => {
    const texto = M.mensajeCambio({
      ...dobladaPermanente, jornada: 'AM', coincidePredeterminada: true,
    });
    assert.match(texto, /coincide con tu jornada predeterminada/);
  });

  await t.test('el pago reprogramado nombra al supervisor y a la doblada pendiente', () => {
    const texto = M.mensajeCambio({
      jornada: 'DOBLADA',
      jornadaPredeterminada: 'AM',
      coincidePredeterminada: false,
      esFinde: false,
      tipoCambio: 'PAGO REPROGRAMADO',
      solicitudInfo: { companero_nombre: 'mildrey gil', rol: 'solicitante' },
    });
    assert.match(texto, /Programado por el supervisor/);
    assert.match(texto, /quedó pendiente con <strong>mildrey gil<\/strong>/);
  });
});


test('mensajeDescanso', async (t) => {
  await t.test('un día libre por doblada permanente nombra el acuerdo y la aprobación', () => {
    // Caso 02/09/2026: isabel descansa porque arley le devuelve el día.
    const d = M.mensajeDescanso({
      tipo: 'pago',
      tipo_solicitud: 'DOBLADA PERMANENTE',
      companero_nombre: 'arley arley',
      solicitud_id: 625,
      fecha_aprobacion: '27/08/2026 14:29',
    });
    assert.equal(d.encabezado, 'Doblada permanente');
    assert.equal(d.etiqueta, 'DÍA LIBRE');
    assert.equal(d.icono, 'fa-mug-hot');
    assert.match(d.texto, /arley arley<\/strong> está trabajando por ti este día/);
    // «hoy» no: la ficha habla del día seleccionado, no de la fecha actual.
    assert.doesNotMatch(d.texto, /por ti hoy/);
    assert.match(d.texto, /Aprobado el 27\/08\/2026 14:29/);
  });

  await t.test('el cambio de descanso se ve como DESCANSO, no como día libre', () => {
    // Tu descanso solo se movió de día: no hay favor que devolver ni café que celebrar.
    const d = M.mensajeDescanso({
      tipo: 'cedio', origen: 'cambio_descanso', tipo_solicitud: 'CAMBIO DESCANSO',
      companero_nombre: 'Jessika Cardona Yepes', solicitud_id: 658,
      fecha_aprobacion: '08/09/2026 16:18',
    });
    assert.equal(d.etiqueta, 'DESCANSO');
    assert.equal(d.icono, 'fa-bed');
    assert.equal(d.encabezado, 'Cambio de día de descanso');
    assert.match(d.texto, /Descanso intercambiado con <strong>Jessika Cardona Yepes<\/strong>/);
    assert.match(d.texto, /Aprobado el 08\/09\/2026 16:18/);
  });

  await t.test('la cesión de una doblada anuncia cuándo se paga', () => {
    const d = M.mensajeDescanso({
      tipo: 'cedio', tipo_solicitud: 'DOBLADA', companero_nombre: 'Rec PM',
      fecha_pago: '10/09/2026', solicitud_id: 7, fecha_aprobacion: '01/09/2026 08:00',
    });
    assert.match(d.texto, /está trabajando por ti este día/);
    assert.match(d.texto, /Pagarás el 10\/09\/2026/);
  });

  await t.test('un descanso ASIGNADO no viene de ningún trámite y no lleva fecha', () => {
    const d = M.mensajeDescanso({ tipo: 'descanso_semana', motivo: 'mantenimiento' });
    assert.equal(d.encabezado, 'Día de descanso');
    assert.equal(d.etiqueta, 'DESCANSO');
    assert.equal(d.texto, 'Descanso por día de mantenimiento.');
  });

  await t.test('temporada y descanso genérico tienen su propio texto', () => {
    assert.equal(M.mensajeDescanso({ tipo: 'descanso_semana', motivo: 'temporada' }).texto,
      'Descanso de temporada.');
    assert.equal(M.mensajeDescanso({ tipo: 'descanso_semana' }).texto,
      'Día de descanso asignado.');
  });

  await t.test('sin descanso_info no rompe', () => {
    const d = M.mensajeDescanso(undefined);
    assert.equal(d.etiqueta, 'DESCANSO');
    assert.equal(typeof d.texto, 'string');
  });
});
