/**
 * JavaScript para formulario de solicitud de doblada
 * 
 * Maneja:
 * - Inicialización de datepickers con bloqueo de domingos, festivos y mantenimiento
 * - Verificación de doblada existente
 * - Carga dinámica de exploradores disponibles
 * - Validación de fecha de pago
 * - Vista previa del acuerdo
 * - Manejo del caso crítico de coincidencia de jornadas
 */

(function() {
    'use strict';
    
    // Elementos del formulario
    const form = document.getElementById('dobladaForm');
    const fechaCesionInput = document.getElementById('fecha_cesion');
    const fechaPagoInput = document.getElementById('fecha_pago');
    const empleadoReceptorSelect = document.getElementById('empleado_receptor');
    const jornadaCedidaRadios = document.querySelectorAll('input[name="jornada_cedida"]');
    const tipoCesionHidden = document.getElementById('tipo_cesion');
    const dobladaExistenteInfo = document.getElementById('doblada_existente_info');
    const vistaPreviaAcuerdo = document.getElementById('vista_previa_acuerdo');
    const resumenAcuerdo = document.getElementById('resumen_acuerdo');
    
    const receptorParcial = document.getElementById('receptor_parcial');
    const fechaPagoParcial = document.getElementById('fecha_pago_parcial');

    // --- MODO INTERCAMBIO: panel dedicado + reubicación de los campos canónicos -------------
    const panelIntercambio = document.getElementById('panel_intercambio');
    const panelIntercambioSlot = document.getElementById('panel_intercambio_slot');
    const resumenIntercambio = document.getElementById('resumen_intercambio');
    const resumenIntercambioWrap = document.getElementById('resumen_intercambio_wrap');
    const intercambioAviso = document.getElementById('intercambio_aviso');
    const intercambioAvisoTexto = document.getElementById('intercambio_aviso_texto');
    // Fuente de verdad del modo. La UI la refleja el checkbox #intercambiar_doblada.
    let modoIntercambio = false;
    // Token para cancelar respuestas en vuelo de la carga de compañeros con doblada (evita que
    // una respuesta tardía de un modo pise el estado del otro al alternar el checkbox).
    let interReqToken = 0;
    // Posición original en el DOM de los grupos que se reubican (para devolverlos al desmarcar).
    const _origFechaPagoParent = fechaPagoParcial ? fechaPagoParcial.parentNode : null;
    const _origFechaPagoNext = fechaPagoParcial ? fechaPagoParcial.nextElementSibling : null;
    const _origReceptorParent = receptorParcial ? receptorParcial.parentNode : null;
    const _origReceptorNext = receptorParcial ? receptorParcial.nextElementSibling : null;
    // Textos originales de etiqueta/ayuda del selector de compañero (para restaurar al salir).
    const _receptorLabelEl = receptorParcial ? receptorParcial.querySelector('label') : null;
    const _receptorHelpEl = receptorParcial ? receptorParcial.querySelector('.form-text') : null;
    const _receptorLabelHTML = _receptorLabelEl ? _receptorLabelEl.innerHTML : '';
    const _receptorHelpHTML = _receptorHelpEl ? _receptorHelpEl.innerHTML : '';

    // Indicadores
    const indicadorFestivoCesion = document.getElementById('indicador_festivo_cesion');
    const indicadorMantenimientoCesion = document.getElementById('indicador_mantenimiento_cesion');
    const indicadorDomingoCesion = document.getElementById('indicador_domingo_cesion');
    const indicadorFestivoPago = document.getElementById('indicador_festivo_pago');
    const indicadorMantenimientoPago = document.getElementById('indicador_mantenimiento_pago');
    const indicadorDomingoPago = document.getElementById('indicador_domingo_pago');
    const opcionesPagoSabado = document.getElementById('opciones_pago_sabado');
    const mensajeNoNecesarioPagoSabado = document.getElementById('mensaje_no_necesario_pago_sabado');
    const jornadaPagoSabadoRadios = document.querySelectorAll('input[name="jornada_pago_sabado"]');
    const avisoSabadoComprometido = document.getElementById('aviso_sabado_comprometido');
    const avisoSabadoComprometidoTexto = document.getElementById('aviso_sabado_comprometido_texto');
    const avisoDeudorDobladaPago = document.getElementById('aviso_deudor_doblada_pago');
    const avisoDeudorDobladaPagoTexto = document.getElementById('aviso_deudor_doblada_pago_texto');
    // True si el sábado de pago elegido ya está comprometido por otra doblada aprobada del usuario
    // (un sábado solo admite un pago de doblada). Bloquea el envío y oculta el selector AM/PM.
    let sabadoPagoComprometido = false;
    // True si el DEUDOR ya tiene una doblada (AM+PM) en la fecha de pago (día de semana): no puede
    // pagar ahí (no le queda jornada libre). Bloquea el envío y oculta el bloque "¿qué cubrirás?".
    let deudorDobladaEnPago = false;
    // Cuando el sábado de pago tiene UNA mitad ya comprometida por otra doblada tuya, aquí queda la
    // mitad LIBRE ('AM'|'PM'). En ese caso no hay elección: se oculta el selector genérico "elige
    // AM o PM" (redundante y confuso junto al aviso) y se fija esta mitad para el envío.
    let sabadoSoloMitadLibre = null;

    // Variables globales
    let flatpickrCesion = null;
    let flatpickrPago = null;
    let tieneDobladaExistente = false;
    let jornadasDobladaExistente = [];
    let fechaCreacionSolicitud = new Date().toISOString().split('T')[0]; // Fecha de hoy
    let fechasDescanso = []; // Fechas donde el usuario está descansando
    // Indica si el solicitante está descansando en la FECHA DE CESIÓN (según VerificarDobladaExistenteView)
    let solicitanteDescansaCesion = false;
    // True si en la FECHA DE CESIÓN el solicitante está en descanso de la semana (temporada/mantenimiento):
    // se muestra la tarjeta limpia "Estás Descansando" y se suprime el aviso amarillo "No hay jornada a ceder".
    let solicitanteCesionEnDescanso = false;
    /** True si en fecha de cesión el solicitante tiene DOBLADA real (AM+PM) en BD — matriz CASO 4.x (cesión parcial) */
    let solicitanteCesionEsDoblada = false;
    /**
     * Token de secuencia para la FECHA DE CESIÓN. Se incrementa cada vez que arranca
     * verificarDobladaExistente (es decir, en cada cambio de fecha de cesión). Todas las
     * peticiones asíncronas encadenadas (verificar-doblada, jornada del solicitante,
     * exploradores disponibles) capturan el valor vigente y descartan su respuesta si llega
     * un token más nuevo. Esto evita la condición de carrera: seleccionar 18 (doblada) y
     * luego 20 (festivo) podía dejar visible la info del 18 si su respuesta llegaba después.
     */
    let cesionReqToken = 0;
    /** Token de secuencia análogo para la FECHA DE PAGO (mismo motivo: evitar respuestas obsoletas). */
    let pagoReqToken = 0;

    // Receptor en fecha de cesión: cubre reglas CASO 2 (doblada = inválido) y serie 3.x (descansa por deuda)
    let receptorCesionDescansa = false;
    let receptorCesionDoblada = false;

    /** True tras completar la última petición de turno del solicitante para la fecha de cesión (evita falsos positivos CASO 7–9 mientras carga). */
    let solicitanteCesionTurnoFetchCompleto = false;
    // Jornadas cargadas para validación Caso 1.1 (Emisor 1 jornada | Receptor 1 jornada en cesión y pago)
    let ultimaJornadaSolicitanteCesion = null; // 'AM' | 'PM' | null
    let ultimaJornadaReceptorCesion = null;
    let ultimaJornadaSolicitantePago = null;
    let ultimaJornadaReceptorPago = null;

    // Estado en fecha de pago para clasificación casos 1.2-1.10: 'descansando' | 'una_jornada' | 'doblada'
    let estadoSolicitantePago = null;
    let estadoReceptorPago = null;
    // True si la FECHA DE PAGO es festivo: en festivo se trabaja/cubre el DÍA COMPLETO, así que
    // no aplica elegir media jornada (AM/PM) → se oculta el selector "¿Qué cubrirás ese día?".
    let pagoEsFestivo = false;

    // Si el caso de pago es RECHAZADO (1.2, 1.5, 1.8, 1.9, 1.10) y mensaje para Swal
    let casoPagoRechazado = false;
    let mensajeRechazoPago = '';
    /** Misma jornada en fecha de pago (caso 1.6): ofrecer Ir a CT Sencillo — misma URL que requiere_cambio_turno_previo */
    let casoPagoRequiereRedireccionCT = false;
    
    // Elementos para mostrar jornadas (fecha de cesión)
    const turnoSolicitanteInfo = document.getElementById('turno_solicitante_info');
    const turnoSolicitanteDetalles = document.getElementById('turno_solicitante_detalles');
    const salasSolicitanteDetalles = document.getElementById('salas_solicitante_detalles');
    const turnoReceptorInfo = document.getElementById('turno_receptor_info');
    const turnoReceptorDetalles = document.getElementById('turno_receptor_detalles');
    const salasReceptorDetalles = document.getElementById('salas_receptor_detalles');
    
    // Elementos para mostrar jornadas (fecha de pago)
    const turnoSolicitantePagoInfo = document.getElementById('turno_solicitante_pago_info');
    const turnoSolicitantePagoDetalles = document.getElementById('turno_solicitante_pago_detalles');
    const salasSolicitantePagoDetalles = document.getElementById('salas_solicitante_pago_detalles');
    const turnoReceptorPagoInfo = document.getElementById('turno_receptor_pago_info');
    const turnoReceptorPagoDetalles = document.getElementById('turno_receptor_pago_detalles');
    const salasReceptorPagoDetalles = document.getElementById('salas_receptor_pago_detalles');
    
    /**
     * Función reutilizable para renderizar turno y salas de manera ordenada.
     * @param {Object|null} turno - Datos del turno o null
     * @param {HTMLElement} detallesElem - Contenedor de detalles de jornada
     * @param {HTMLElement} salasElem - Contenedor de salas
     * @param {boolean} esDoblada - Si tiene doblada (AM+PM)
     * @param {string[]} jornadas - Lista de jornadas
     * @param {{ contexto?: 'solicitante'|'receptor' }} opciones - Si contexto es 'receptor' y no hay turno, se muestra estado "Descanso"
     */
    function renderTurnoYSalas(turno, detallesElem, salasElem, esDoblada = false, jornadas = [], opciones = {}) {
        if (!turno) {
            if (opciones.contexto === 'solicitante') {
                // El DEUDOR descansa ese día (p. ej. sábado por alternancia o festivo): no tiene turno
                // propio, pero como debe una jornada la pagará trabajando. Texto en primera persona.
                detallesElem.innerHTML = `
                    <div class="card mb-3 border-info">
                        <div class="card-body text-center py-4">
                            <i class="fas fa-moon text-info fa-2x mb-2" aria-hidden="true"></i>
                            <p class="mb-1 font-weight-bold text-info">Ese día descansas</p>
                            <p class="mb-0 small text-muted">No tienes un turno propio en la fecha de pago. Como debes una jornada, la pagarás trabajando el turno que cubres a tu compañero.</p>
                        </div>
                    </div>
                `;
                salasElem.innerHTML = `
                    <div class="card mb-3 border-0 bg-light">
                        <div class="card-body py-2 text-center">
                            <span class="text-muted small">Sin turno propio — trabajarás para pagar</span>
                        </div>
                    </div>
                `;
            } else if (opciones.contexto === 'receptor') {
                // Estado profesional: el receptor está en día de descanso
                detallesElem.innerHTML = `
                    <div class="card mb-3 border-secondary">
                        <div class="card-body text-center py-4">
                            <i class="fas fa-moon text-secondary fa-2x mb-2" aria-hidden="true"></i>
                            <p class="mb-1 font-weight-bold text-secondary">Descanso</p>
                            <p class="mb-0 small text-muted">El receptor no tiene jornada asignada para esta fecha. Corresponde su día de descanso según su turno.</p>
                        </div>
                    </div>
                `;
                salasElem.innerHTML = `
                    <div class="card mb-3 border-0 bg-light">
                        <div class="card-body py-2 text-center">
                            <span class="text-muted small">Sin asignación — día de descanso</span>
                        </div>
                    </div>
                `;
            } else {
                detallesElem.innerHTML = `
                    <div class="card mb-3">
                        <div class="card-body text-center">
                            <i class="fas fa-exclamation-triangle text-warning"></i>
                            <span class="text-muted">No tiene jornada asignada para esta fecha</span>
                        </div>
                    </div>
                `;
                salasElem.innerHTML = `
                    <div class="card mb-3">
                        <div class="card-body text-center">
                            <i class="fas fa-exclamation-triangle text-warning"></i>
                            <span class="text-muted">No tiene salas asignadas</span>
                        </div>
                    </div>
                `;
            }
            return;
        }
        
        // CORRECCIÓN: Detectar si es doblada
        const esJornadaFija = turno.es_turno_virtual;
        let badgeClass, badgeText, jornadaTexto;
        
        if (esDoblada) {
            // Es una DOBLADA (AM + PM)
            badgeClass = 'badge-warning';
            badgeText = 'DOBLADA';
            jornadaTexto = `${jornadas.join(' + ')}`;
        } else {
            // Jornada simple
            badgeClass = esJornadaFija ? 'badge-info' : 'badge-success';
            badgeText = esJornadaFija ? 'Jornada Fija' : 'Turno Asignado';
            jornadaTexto = turno.jornada || '-';
        }
        
        detallesElem.innerHTML = `
            <div class="card mb-3">
                <div class="card-body">
                    <div class="row align-items-center mb-2">
                        <div class="col-12 col-md-6 mb-2 mb-md-0">
                            <strong>Jornada:</strong> ${jornadaTexto}
                            <span class="badge ${badgeClass} ml-1">${badgeText}</span>
                        </div>
                        <div class="col-12 col-md-6">
                            <strong>Horario:</strong> ${turno.hora_inicio || '-'} - ${turno.hora_fin || '-'}
                        </div>
                    </div>
                </div>
            </div>
        `;
        let salasHtml = `<div class="card mb-3"><div class="card-body"><div class="row"><div class="col-12"><strong>Salas:</strong> `;
        let haySalas = false;
        if (turno.tipo_sala === 'competencia' && turno.salas_competencia && turno.salas_competencia.length > 0) {
            turno.salas_competencia.forEach(sala => {
                salasHtml += `<span class="badge badge-info ml-1">${sala.nombre}</span> `;
            });
            haySalas = true;
        } else if (turno.sala) {
            salasHtml += `<span class="badge badge-info ml-1">${turno.sala}</span>`;
            haySalas = true;
        }
        salasHtml += `</div></div></div></div>`;
        if (haySalas) {
            salasElem.innerHTML = salasHtml;
        } else {
            salasElem.innerHTML = `
                <div class="card mb-3">
                    <div class="card-body text-center">
                        <i class="fas fa-exclamation-triangle text-warning"></i>
                        <span class="text-muted">No tiene salas asignadas</span>
                    </div>
                </div>
            `;
        }
    }
    
    /**
     * Verificar si una fecha es domingo
     */
    function esDomingo(fecha) {
        const fechaObj = new Date(fecha + 'T00:00:00');
        return fechaObj.getDay() === 0; // 0 = Domingo
    }

    /**
     * Verificar si una fecha es sábado
     */
    function esSabado(fecha) {
        const fechaObj = new Date(fecha + 'T00:00:00');
        return fechaObj.getDay() === 6; // 6 = Sábado
    }

    function limpiarSeleccionPagoSabado() {
        if (jornadaPagoSabadoRadios && jornadaPagoSabadoRadios.length > 0) {
            jornadaPagoSabadoRadios.forEach(r => { r.checked = false; });
        }
    }

    function mostrarOpcionesPagoSabado(mostrar) {
        if (!opcionesPagoSabado) return;
        opcionesPagoSabado.style.display = mostrar ? 'block' : 'none';
        if (!mostrar) limpiarSeleccionPagoSabado();
    }

    function mostrarMensajeNoNecesarioPagoSabado(mostrar) {
        if (!mensajeNoNecesarioPagoSabado) return;
        mensajeNoNecesarioPagoSabado.style.display = mostrar ? 'block' : 'none';
    }

    /**
     * Sábado con UNA mitad ya comprometida por otra doblada tuya: no hay elección de mitad.
     * Se oculta el selector genérico "Pago en Sábado / elige AM o PM" (redundante y confuso al lado
     * del aviso amarillo que ya explica la situación) y se fija la mitad libre para el envío.
     */
    function aplicarSabadoMitadLibre(libre) {
        mostrarMensajeNoNecesarioPagoSabado(false);
        if (opcionesPagoSabado) opcionesPagoSabado.style.display = 'none';
        const r = document.querySelector(`input[name="jornada_pago_sabado"][value="${libre}"]`);
        if (r) r.checked = true;
    }

    /**
     * Espejo en la UI del guard del backend: si el sábado de pago elegido ya está comprometido
     * por otra doblada aprobada del usuario (un sábado solo admite UN pago de doblada), avisar
     * de una vez y ocultar el selector AM/PM, en lugar de dejar que falle al enviar.
     */
    function verificarSabadoComprometido(fecha, token) {
        if (!fecha || !esSabado(fecha)) {
            sabadoPagoComprometido = false;
            if (avisoSabadoComprometido) avisoSabadoComprometido.style.display = 'none';
            return;
        }
        const _sid = (typeof solicitudIdActual !== 'undefined' && solicitudIdActual) ? `&solicitud_id=${solicitudIdActual}` : '';
        fetch(`/solicitudes/sabado-pago-comprometido/?fecha=${fecha}${_sid}`)
            .then(r => r.json())
            .then(d => {
                // Descartar si la fecha de pago cambió mientras cargaba.
                if (token != null && token !== pagoReqToken) return;
                if (d && d.comprometido) {
                    // Sábado LLENO (ambas mitades ya ocupadas): bloquear el envío.
                    sabadoPagoComprometido = true;
                    sabadoSoloMitadLibre = null;
                    mostrarOpcionesPagoSabado(false);
                    mostrarMensajeNoNecesarioPagoSabado(false);
                    if (avisoSabadoComprometido && avisoSabadoComprometidoTexto) {
                        const delDia = d.fecha_cesion ? ` (cesión del ${d.fecha_cesion})` : '';
                        avisoSabadoComprometidoTexto.innerHTML =
                            ` ese sábado ya lo tienes comprometido por completo como pago de otra(s) doblada(s) tuya(s)${delDia}. ` +
                            'Sus dos mitades (AM y PM) ya están ocupadas. ' +
                            '<strong>Elige otro día de pago</strong> — un día de semana del mismo mes, u otro sábado válido.';
                        avisoSabadoComprometido.style.display = 'block';
                    }
                } else if (d && d.mitad_libre) {
                    // Una mitad ocupada, la otra LIBRE: se permite pagar esta doblada con la mitad libre
                    // (terminarías doblado AM+PM, cada mitad pagando a una persona). No se bloquea.
                    sabadoPagoComprometido = false;
                    if (avisoSabadoComprometido && avisoSabadoComprometidoTexto) {
                        const delDia = d.fecha_cesion ? ` (cesión del ${d.fecha_cesion})` : '';
                        avisoSabadoComprometidoTexto.innerHTML =
                            ` ese sábado ya usas la mitad <strong>${d.mitad_ocupada}</strong> para pagar otra doblada tuya${delDia}. ` +
                            `Esta se paga con la otra mitad (<strong>${d.mitad_libre}</strong>): ese día trabajarás <strong>AM+PM</strong> ` +
                            `y cubrirás las dos jornadas que debes.`;
                        avisoSabadoComprometido.style.display = 'block';
                    }
                    // No hay elección de mitad: ocultar el selector genérico "elige AM o PM" (redundante
                    // y confuso al lado del aviso) y fijar la mitad libre. La variable hace que la
                    // carga de jornada del solicitante tampoco lo re-muestre (evita la carrera async).
                    sabadoSoloMitadLibre = d.mitad_libre;
                    aplicarSabadoMitadLibre(d.mitad_libre);
                } else {
                    sabadoPagoComprometido = false;
                    sabadoSoloMitadLibre = null;
                    if (avisoSabadoComprometido) avisoSabadoComprometido.style.display = 'none';
                }
            })
            .catch(() => { /* si falla la comprobación, el guard del backend sigue protegiendo */ });
    }

    /**
     * Si el receptor tiene doblada en fecha de pago (día laborable, no sábado con regla especial),
     * mostrar AM / PM para persistir en DobladaDetalle.jornada_cubre_en_pago (solo se debe una jornada).
     */
    function sincronizarOpcionesCubrePagoReceptorDoblada() {
        const cont = document.getElementById('opciones_cubre_pago_receptor_doblada');
        if (!cont) {
            actualizarVistaPrevia();
            return;
        }
        const fp = fechaPagoInput && fechaPagoInput.value;
        const radios = cont.querySelectorAll('input[name="jornada_cubre_en_pago"]');
        // Modo INTERCAMBIO: ya decidiste cubrir la doblada ENTERA del compañero (es un swap de días),
        // así que NO tiene sentido preguntar qué jornada cubres → se oculta el selector.
        const _interActivo = !!(document.getElementById('intercambiar_doblada') &&
                                document.getElementById('intercambiar_doblada').checked);
        // En FESTIVO se trabaja/cubre el DÍA COMPLETO (no hay media jornada), y el intercambio es
        // festivo por festivo: no aplica elegir AM/PM → se oculta el selector.
        // Si el DEUDOR ya tiene DOBLADA ese día no puede pagar ahí (no le queda jornada libre):
        // se oculta el selector y el aviso lo explica (mismo criterio que el guard del backend).
        const deudorDobladaPago = estadoSolicitantePago === 'doblada';
        const ocultar = _interActivo || !fp || esSabado(fp) || pagoEsFestivo ||
                        estadoReceptorPago !== 'doblada' || deudorDobladaPago;
        if (ocultar) {
            cont.style.display = 'none';
            radios.forEach(r => {
                r.checked = false;
                r.removeAttribute('required');
            });
            actualizarVistaPrevia();
            return;
        }
        cont.style.display = 'block';
        // Defensa: el selector de sábado y este (día de semana) NUNCA deben verse a la vez. Al mostrar
        // este, ocultar el de sábado por si quedó visible de un estado anterior (evita el "duplicado").
        if (opcionesPagoSabado) opcionesPagoSabado.style.display = 'none';
        radios.forEach(r => r.setAttribute('required', 'required'));

        // En una doblada solo se debe UNA jornada, así que al pagar solo se cubre AM o PM (la opción
        // "toda la doblada" se eliminó del selector). Aquí solo se ajusta la nota de aviso: si ese día
        // el deudor ya trabaja una jornada, se le orienta a cubrir la contraria.
        const trabajaUna = estadoSolicitantePago === 'una_jornada'
            && (ultimaJornadaSolicitantePago === 'AM' || ultimaJornadaSolicitantePago === 'PM');
        // Nota explicativa dentro del contenedor
        let nota = cont.querySelector('.nota-cubre-jornada');
        if (!nota) {
            nota = document.createElement('small');
            nota.className = 'nota-cubre-jornada form-text';
            nota.style.cssText = 'display:block; margin-top:4px; color:#92400e;';
            cont.appendChild(nota);
        }
        let contrariaPago = null;
        if (trabajaUna) {
            // Ese día el deudor trabaja una jornada: lo normal es cubrir la CONTRARIA; si elige la
            // MISMA, al enviar se le pedirá un cambio de turno sencillo (bloqueo suave). Ambas quedan
            // seleccionables (no se deshabilita ninguna).
            const propia = ultimaJornadaSolicitantePago;
            const contraria = propia === 'AM' ? 'PM' : 'AM';
            contrariaPago = contraria;
            nota.innerHTML = `<i class="fas fa-info-circle mr-1"></i>Ese día tú trabajas <strong>${propia}</strong>. `
                + `Lo normal es cubrir la jornada contraria (<strong>${contraria}</strong>). `
                + `Si eliges <strong>${propia}</strong> (tu misma jornada), primero deberás hacer un `
                + `<strong>cambio de turno sencillo</strong>.`;
            nota.style.display = 'block';
        } else {
            nota.style.display = 'none';
        }

        // Selección por defecto: preferir la jornada CONTRARIA (la opción limpia); si no, AM/PM.
        const anyChecked = Array.from(radios).some(r => r.checked && !r.disabled);
        if (!anyChecked) {
            const jc = document.querySelector('input[name="jornada_cedida"]:checked');
            const preferida = contrariaPago
                || (jc && (jc.value === 'AM' || jc.value === 'PM') ? jc.value : 'AM');
            const candidatos = [preferida, 'AM', 'PM'];
            for (const v of candidatos) {
                const rSel = cont.querySelector(`input[name="jornada_cubre_en_pago"][value="${v}"]`);
                if (rSel && !rSel.disabled) { rSel.checked = true; break; }
            }
        }
        actualizarVistaPrevia();
    }
    
    /**
     * Marca días festivos en calendario (incluyendo deshabilitados)
     */
    function marcarFestivosIncluyendoDeshabilitados(instance, festivosMap) {
        if (!instance || !instance.calendarContainer || !festivosMap) {
            return;
        }
        
        const fechasFestivos = Array.from(festivosMap.keys());
        // Incluir TODOS los días, incluso los deshabilitados
        const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day');
        
        dayElements.forEach(day => {
            if (day.dateObj) {
                const dayDate = new Date(day.dateObj);
                const dayDateStr = dayDate.toISOString().split('T')[0];
                
                if (fechasFestivos.includes(dayDateStr)) {
                    // Es festivo: agregar clase y actualizar tooltip
                    day.classList.add('festivo');
                    day.title = festivosMap.get(dayDateStr) || 'Día festivo';
                } else {
                    // No es festivo: remover clase si existe
                    day.classList.remove('festivo');
                }
            }
        });
    }
    
    /**
     * Marca días de mantenimiento en calendario (incluyendo deshabilitados)
     */
    function marcarMantenimientoIncluyendoDeshabilitados(instance, mantenimientoMap) {
        if (!instance || !instance.calendarContainer || !mantenimientoMap) {
            return;
        }
        
        const fechasMantenimiento = Array.from(mantenimientoMap.keys());
        // Incluir TODOS los días, incluso los deshabilitados
        const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day');
        
        dayElements.forEach(day => {
            if (day.dateObj) {
                const dayDate = new Date(day.dateObj);
                const dayDateStr = dayDate.toISOString().split('T')[0];
                
                if (fechasMantenimiento.includes(dayDateStr)) {
                    // Es día de mantenimiento: agregar clase y actualizar tooltip
                    day.classList.add('mantenimiento');
                    const descripcion = mantenimientoMap.get(dayDateStr) || 'Día de mantenimiento';
                    
                    // Si ya tiene un title (festivo), agregar información de mantenimiento
                    const titleActual = day.title || '';
                    if (titleActual && !titleActual.includes(descripcion)) {
                        day.title = titleActual + ' | ' + descripcion;
                    } else if (!titleActual) {
                        day.title = descripcion;
                    }
                } else {
                    // No es día de mantenimiento: remover clase si existe
                    day.classList.remove('mantenimiento');
                    
                    // Limpiar tooltip de mantenimiento si existe, pero mantener festivo si hay
                    const titleActual = day.title || '';
                    if (titleActual.includes(' | ')) {
                        const partes = titleActual.split(' | ');
                        const parteFestivo = partes.find(p => !p.includes('mantenimiento'));
                        day.title = parteFestivo || titleActual.replace(/ \| .*mantenimiento.*/i, '');
                    } else if (titleActual.toLowerCase().includes('mantenimiento')) {
                        day.title = '';
                    }
                }
            }
        });
    }
    
    /**
     * Marca días de temporada en calendario (incluyendo deshabilitados)
     */
    function marcarTemporadaIncluyendoDeshabilitados(instance, temporadaMap) {
        if (!instance || !instance.calendarContainer || !temporadaMap) {
            return;
        }
        
        const fechasTemporada = Array.from(temporadaMap.keys());
        // Incluir TODOS los días, incluso los deshabilitados (temporada no bloquea, solo marca)
        const dayElements = instance.calendarContainer.querySelectorAll('.flatpickr-day');
        
        dayElements.forEach(day => {
            if (day.dateObj) {
                const dayDate = new Date(day.dateObj);
                const dayDateStr = dayDate.toISOString().split('T')[0];
                
                if (fechasTemporada.includes(dayDateStr)) {
                    // Es día de temporada: agregar clase y actualizar tooltip
                    day.classList.add('temporada');
                    const descripcion = temporadaMap.get(dayDateStr) || 'Día de temporada';
                    
                    // Si ya tiene un title (festivo o mantenimiento), agregar información de temporada
                    const titleActual = day.title || '';
                    if (titleActual && !titleActual.includes(descripcion)) {
                        day.title = titleActual + ' | ' + descripcion;
                    } else if (!titleActual) {
                        day.title = descripcion;
                    }
                } else {
                    // No es día de temporada: remover clase si existe
                    day.classList.remove('temporada');
                    
                    // Limpiar tooltip de temporada si existe, pero mantener otros si hay
                    const titleActual = day.title || '';
                    if (titleActual.includes(' | ')) {
                        const partes = titleActual.split(' | ');
                        const partesFiltradas = partes.filter(p => !p.toLowerCase().includes('temporada'));
                        day.title = partesFiltradas.join(' | ');
                    } else if (titleActual.toLowerCase().includes('temporada')) {
                        day.title = '';
                    }
                }
            }
        });
    }
    
    /**
     * Bloquear domingos, festivos, mantenimiento y temporada en Flatpickr.
     * Marca visualmente los días especiales (colores distintivos se mantienen).
     */
    function bloquearDiasEspeciales(instance) {
        if (!instance) return;
        
        // Almacenar Maps en la instancia para acceso desde callbacks
        if (!instance._diasEspecialesMaps) {
            instance._diasEspecialesMaps = {
                festivos: null,
                mantenimiento: null,
                temporada: null
            };
        }
        
        // Obtener año para cargar temporadas
        const añoActual = new Date().getFullYear();
        
        // Cargar festivos, mantenimiento y temporadas
        Promise.all([
            window.DatepickerFestivos.cargarDiasFestivos(),
            window.DatepickerFestivos.cargarDiasMantenimiento(),
            window.DatepickerFestivos.cargarDiasTemporada(añoActual)
        ]).then(([festivosMap, mantenimientoMap, temporadaMap]) => {
            // Guardar Maps en la instancia para acceso desde callbacks
            instance._diasEspecialesMaps.festivos = festivosMap;
            instance._diasEspecialesMaps.mantenimiento = mantenimientoMap;
            instance._diasEspecialesMaps.temporada = temporadaMap;
            
            const fechasFestivos = Array.from(festivosMap.keys());
            const fechasMantenimiento = Array.from(mantenimientoMap.keys());
            const fechasTemporada = Array.from(temporadaMap.keys());

            instance.set('disable', [
                function(date) { return date.getDay() === 0; },
                function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasFestivos.includes(fechaStr);
                },
                function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasMantenimiento.includes(fechaStr);
                },
                function(date) {
                    const fechaStr = date.toISOString().split('T')[0];
                    return fechasTemporada.includes(fechaStr);
                }
            ]);
            
            // Función auxiliar para marcar todos los días especiales (incluyendo deshabilitados)
            const marcarTodosLosDiasEspeciales = () => {
                // Usar Maps de la instancia para asegurar que estén disponibles
                const festivos = instance._diasEspecialesMaps.festivos;
                const mantenimiento = instance._diasEspecialesMaps.mantenimiento;
                const temporada = instance._diasEspecialesMaps.temporada;
                
                if (!festivos || !mantenimiento) {
                    return; // Maps aún no están cargados
                }
                
                setTimeout(() => {
                    if (instance && instance.calendarContainer) {
                        // Marcar festivos (incluyendo deshabilitados)
                        marcarFestivosIncluyendoDeshabilitados(instance, festivos);
                        // Marcar días de mantenimiento (incluyendo deshabilitados)
                        marcarMantenimientoIncluyendoDeshabilitados(instance, mantenimiento);
                        // Marcar días de temporada (incluyendo deshabilitados) - solo si está disponible
                        if (temporada) {
                            marcarTemporadaIncluyendoDeshabilitados(instance, temporada);
                        }
                    }
                }, 150);
            };
            
            // Marcar visualmente los días especiales en el calendario
            marcarTodosLosDiasEspeciales();
            
            // También marcar inmediatamente si el calendario ya está abierto/renderizado
            setTimeout(() => {
                if (instance && instance.calendarContainer) {
                    marcarTodosLosDiasEspeciales();
                }
            }, 300);
            
            // Configurar callbacks para re-marcar cuando cambie el mes o el año
            // Guardar callbacks existentes si existen
            const onMonthChangeOriginal = instance.config.onMonthChange;
            const onYearChangeOriginal = instance.config.onYearChange;
            const onOpenOriginal = instance.config.onOpen;
            const onReadyOriginal = instance.config.onReady;
            
            // Configurar onReady para marcar días cuando el calendario esté listo
            instance.config.onReady = function(selectedDates, dateStr, inst) {
                marcarTodosLosDiasEspeciales();
                // Ejecutar callback original si existe
                if (onReadyOriginal) {
                    onReadyOriginal(selectedDates, dateStr, inst);
                }
            };
            
            // Configurar onMonthChange para re-marcar días
            instance.config.onMonthChange = function(selectedDates, dateStr, inst) {
                // Verificar si el año cambió al cambiar el mes
                const añoVisible = inst.currentYear;
                const añoCargado = instance._diasEspecialesMaps.temporada && instance._diasEspecialesMaps.temporada.size > 0 ?
                    parseInt(Array.from(instance._diasEspecialesMaps.temporada.keys())[0].split('-')[0]) : añoActual;
                
                // Si el año visible es diferente, recargar temporadas
                if (añoVisible !== añoCargado && window.DatepickerFestivos && window.DatepickerFestivos.cargarDiasTemporada) {
                    window.DatepickerFestivos.cargarDiasTemporada(añoVisible).then(nuevaTemporada => {
                        instance._diasEspecialesMaps.temporada = nuevaTemporada;
                        marcarTodosLosDiasEspeciales();
                    });
                } else {
                    marcarTodosLosDiasEspeciales();
                }
                // Ejecutar callback original si existe
                if (onMonthChangeOriginal) {
                    onMonthChangeOriginal(selectedDates, dateStr, inst);
                }
            };
            
            // Configurar onYearChange para re-marcar días
            instance.config.onYearChange = function(selectedDates, dateStr, inst) {
                const nuevoAño = inst.currentYear;
                // Cargar temporadas para el nuevo año
                if (window.DatepickerFestivos && window.DatepickerFestivos.cargarDiasTemporada) {
                    window.DatepickerFestivos.cargarDiasTemporada(nuevoAño).then(nuevaTemporada => {
                        instance._diasEspecialesMaps.temporada = nuevaTemporada;
                        marcarTodosLosDiasEspeciales();
                    });
                } else {
                    marcarTodosLosDiasEspeciales();
                }
                // Ejecutar callback original si existe
                if (onYearChangeOriginal) {
                    onYearChangeOriginal(selectedDates, dateStr, inst);
                }
            };
            
            // También re-marcar cuando se abre el calendario
            instance.config.onOpen = function(selectedDates, dateStr, inst) {
                // Verificar año visible y cargar temporadas si es necesario
                const añoVisible = inst.currentYear || añoActual;
                const añoCargado = instance._diasEspecialesMaps.temporada && instance._diasEspecialesMaps.temporada.size > 0 ?
                    parseInt(Array.from(instance._diasEspecialesMaps.temporada.keys())[0].split('-')[0]) : añoActual;
                
                if (añoVisible !== añoCargado && window.DatepickerFestivos && window.DatepickerFestivos.cargarDiasTemporada) {
                    window.DatepickerFestivos.cargarDiasTemporada(añoVisible).then(nuevaTemporada => {
                        instance._diasEspecialesMaps.temporada = nuevaTemporada;
                        marcarTodosLosDiasEspeciales();
                    });
                } else {
                    marcarTodosLosDiasEspeciales();
                }
                // Ejecutar callback original si existe
                if (onOpenOriginal) {
                    onOpenOriginal(selectedDates, dateStr, inst);
                }
            };
        }).catch(error => {
            console.error('Error cargando días especiales para bloqueo:', error);
            // Si falla, al menos bloquear domingos
            instance.set('disable', [
                function(date) {
                    return date.getDay() === 0; // Domingo
                }
            ]);
        });
    }
    
    /**
     * Cargar fechas donde el usuario está descansando (cedió su jornada)
     */
    async function cargarFechasDescanso() {
        try {
            const response = await fetch('/solicitudes/obtener-fechas-descanso/');
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            if (data.success && Array.isArray(data.fechas)) {
                fechasDescanso = data.fechas;
                console.log(`✅ Fechas de descanso cargadas: ${fechasDescanso.length}`);
                
                // Aplicar marcado visual en el calendario
                if (flatpickrCesion) {
                    marcarFechasDescansoEnCalendario();
                }
            }
        } catch (error) {
            console.error('Error cargando fechas de descanso:', error);
            fechasDescanso = [];
        }
    }
    
    /**
     * Marcar visualmente las fechas de descanso en el calendario.
     * El marcado real se hace en onDayCreate (síncrono y consistente); aquí solo se
     * redibuja para que onDayCreate vuelva a correr con las fechas ya cargadas.
     */
    function marcarFechasDescansoEnCalendario() {
        if (flatpickrCesion && typeof flatpickrCesion.redraw === 'function') {
            flatpickrCesion.redraw();
        }
    }
    
    /**
     * Inicializar datepicker para fecha de cesión
     */
    function inicializarDatepickerCesion() {
        if (!fechaCesionInput || !window.DatepickerFestivos) {
            console.error('DatepickerFestivos no está disponible');
            return;
        }
        
        const fechaMinima = fechaCesionInput.getAttribute('data-min-date') || new Date().toISOString().split('T')[0];
        
        // Cargar fechas de descanso antes de inicializar
        cargarFechasDescanso();
        
        window.DatepickerFestivos.inicializar({
            input: fechaCesionInput,
            minDate: fechaMinima,
            indicadorFestivo: indicadorFestivoCesion,
            descripcionFestivo: document.getElementById('descripcion_festivo_cesion'),
            bloquearDiasEspeciales: true,
            permitirFestivos: true,
            permitirTemporada: true, // En temporada sí se pueden hacer solicitudes de doblada
            // Marcar los días de descanso (día libre) en el momento de crear cada celda,
            // de forma síncrona y consistente (evita el marcado flaky por setTimeout).
            flatpickrOptions: {
                onDayCreate: function(dates, str, inst, dayElem) {
                    if (dayElem && dayElem.dateObj && Array.isArray(fechasDescanso) && fechasDescanso.length) {
                        const d = dayElem.dateObj;
                        const iso = d.getFullYear() + '-' +
                            String(d.getMonth() + 1).padStart(2, '0') + '-' +
                            String(d.getDate()).padStart(2, '0');
                        if (fechasDescanso.includes(iso)) {
                            dayElem.classList.add('descanso');
                        }
                    }
                }
            },
            onReady: function(flatpickrInstance) {
                flatpickrCesion = flatpickrInstance;
                marcarFechasDescansoEnCalendario();
            },
            onDateChange: function(fecha) {
                if (!fecha) return;

                // Cambiar la fecha de cesión (día A) invalida cualquier intercambio en curso:
                // estaba atado al día anterior. Salir del modo SIN re-disparar el change (ya
                // estamos dentro del handler); verificarDobladaExistente re-ofrecerá el intercambio
                // más abajo si el nuevo día también tiene doblada. Así el panel/aviso no se ancla.
                if (modoIntercambio) {
                    const _cbInter = document.getElementById('intercambiar_doblada');
                    if (_cbInter) _cbInter.checked = false;
                    setModoIntercambio(false, false);
                }

                // Verificar si es domingo
                if (esDomingo(fecha)) {
                    indicadorDomingoCesion.style.display = 'block';
                    fechaCesionInput.value = '';
                    return;
                } else {
                    indicadorDomingoCesion.style.display = 'none';
                }
                
                // Verificar si es día de mantenimiento
                if (window.DatepickerFestivos && window.DatepickerFestivos.verificarDiaMantenimiento) {
                    window.DatepickerFestivos.verificarDiaMantenimiento(
                        fecha,
                        indicadorMantenimientoCesion,
                        document.getElementById('descripcion_mantenimiento_cesion')
                    ).then(esMantenimiento => {
                        if (esMantenimiento) {
                            fechaCesionInput.value = '';
                        }
                    });
                }
                
                // Al cambiar la fecha de cesión, resetear la sección de pago para que no queden
                // visibles datos/paneles calculados para la fecha anterior.
                resetearSeccionPagoPorCambioCesion();

                // Limpieza inmediata (antes de que llegue la nueva respuesta) del panel "Tu Jornada
                // para la Fecha de Cesión" y del de doblada existente, para que NUNCA se vea el
                // contenido de la fecha anterior durante la latencia del fetch. La respuesta nueva
                // (verificarDobladaExistente) los repuebla según el caso.
                if (turnoSolicitanteDetalles) turnoSolicitanteDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando…</div>';
                if (salasSolicitanteDetalles) salasSolicitanteDetalles.innerHTML = '';
                if (dobladaExistenteInfo) dobladaExistenteInfo.style.display = 'none';

                // Verificar doblada existente (esto cargará exploradores y jornada según el caso)
                verificarDobladaExistente(fecha);
            }
        }).then(instance => {
            flatpickrCesion = instance;
            // bloquearDiasEspeciales ya se maneja dentro de inicializar() con bloquearDiasEspeciales: true
            
            // Si ya hay una fecha seleccionada al cargar, verificar doblada (cargará jornada si aplica)
            const fechaInicial = fechaCesionInput.value;
            if (fechaInicial) {
                verificarDobladaExistente(fechaInicial);
            }
        }).catch(error => {
            console.error('Error inicializando datepicker de cesión:', error);
        });
    }
    
    /**
     * Inicializar datepicker para fecha de pago
     */
    function inicializarDatepickerPago() {
        if (!fechaPagoInput || !window.DatepickerFestivos) {
            console.error('DatepickerFestivos no está disponible');
            return;
        }
        
        const fechaMinima = fechaPagoInput.getAttribute('data-min-date') || new Date().toISOString().split('T')[0];
        
        window.DatepickerFestivos.inicializar({
            input: fechaPagoInput,
            minDate: fechaMinima,
            indicadorFestivo: indicadorFestivoPago,
            descripcionFestivo: document.getElementById('descripcion_festivo_pago'),
            bloquearDiasEspeciales: true,
            permitirFestivos: true,
            permitirTemporada: true,
            onDateChange: function(fecha) {
                if (!fecha) return;
                // Nueva selección de fecha de pago: invalida respuestas en vuelo de la fecha anterior.
                const pagoToken = ++pagoReqToken;

                // Verificar si es domingo
                if (esDomingo(fecha)) {
                    indicadorDomingoPago.style.display = 'block';
                    fechaPagoInput.value = '';
                    mostrarOpcionesPagoSabado(false);
                    // Intercambio: al invalidar la fecha, refrescar (limpia el aviso viejo).
                    if (modoIntercambio) cargarCompanerosIntercambio();
                    return;
                } else {
                    indicadorDomingoPago.style.display = 'none';
                }

                // Si es sábado, cargarJornadaSolicitantePago decidirá si mostrar selector o mensaje "no necesario"
                if (!esSabado(fecha)) {
                    mostrarOpcionesPagoSabado(false);
                    mostrarMensajeNoNecesarioPagoSabado(false);
                }
                // ¿Ese sábado ya está comprometido por otra doblada mía? (espejo del guard backend).
                // Resetear y comprobar; si lo está, oculta el selector AM/PM y bloquea el envío.
                sabadoPagoComprometido = false;
                sabadoSoloMitadLibre = null;
                if (avisoSabadoComprometido) avisoSabadoComprometido.style.display = 'none';
                if (esSabado(fecha)) {
                    verificarSabadoComprometido(fecha, pagoToken);
                }

                // Verificar si es día de mantenimiento
                if (window.DatepickerFestivos && window.DatepickerFestivos.verificarDiaMantenimiento) {
                    window.DatepickerFestivos.verificarDiaMantenimiento(
                        fecha,
                        indicadorMantenimientoPago,
                        document.getElementById('descripcion_mantenimiento_pago')
                    ).then(esMantenimiento => {
                        if (esMantenimiento) {
                            fechaPagoInput.value = '';
                            // Intercambio: al invalidar la fecha, refrescar (limpia el aviso viejo).
                            if (modoIntercambio) cargarCompanerosIntercambio();
                        }
                    });
                }
                
                // Validar que sea posterior a fecha de creación
                if (fecha <= fechaCreacionSolicitud) {
                    Swal.fire({
                        icon: 'error',
                        title: 'Fecha Inválida',
                        text: `La fecha de pago debe ser posterior a ${fechaCreacionSolicitud}.`
                    });
                    fechaPagoInput.value = '';
                    // Intercambio: al invalidar la fecha, refrescar (limpia el aviso viejo).
                    if (modoIntercambio) cargarCompanerosIntercambio();
                    return;
                }

                // MODO INTERCAMBIO: la fecha de pago es el día de la doblada del compañero (día B).
                // No aplica NADA de la lógica de cesión (pago-sábado, matriz, "¿qué cubres?"):
                // solo recargar la lista de compañeros con doblada ese día y refrescar el resumen.
                if (modoIntercambio) {
                    cargarCompanerosIntercambio();
                    actualizarResumenIntercambio();
                    return;
                }

                // Verificar si tiene doblada en esta fecha (validación preventiva)
                verificarDobladaEnFechaPago(fecha, 'Pago');

                // Evitar dejar bloqueo/mensaje de la fecha de pago anterior (la matriz se recalcula al terminar los fetch).
                casoPagoRechazado = false;
                mensajeRechazoPago = '';
                casoPagoRequiereRedireccionCT = false;
                // Ocultar el aviso de coincidencia de la fecha anterior; se re-evalúa al cargar el receptor.
                const _avCoincFecha = document.getElementById('aviso_coincidencia_pago');
                if (_avCoincFecha) _avCoincFecha.style.display = 'none';
                // No usar estado del receptor de la fecha anterior hasta que llegue el nuevo fetch
                estadoReceptorPago = null;
                ultimaJornadaReceptorPago = null;
                // ¿La fecha de pago es festivo? En festivo se cubre el día completo → sin selector AM/PM.
                if (window.DatepickerFestivos && window.DatepickerFestivos.cargarDiasFestivos) {
                    window.DatepickerFestivos.cargarDiasFestivos().then(festivos => {
                        pagoEsFestivo = !!(festivos && festivos.get && festivos.get(fecha));
                        sincronizarOpcionesCubrePagoReceptorDoblada();
                    }).catch(() => { pagoEsFestivo = false; });
                } else {
                    pagoEsFestivo = false;
                }
                sincronizarOpcionesCubrePagoReceptorDoblada();
                
                // Cargar jornada del solicitante en fecha de pago
                cargarJornadaSolicitantePago(fecha, pagoToken);

                // Si ya hay receptor seleccionado, cargar su jornada en fecha de pago
                const empleadoReceptorId = empleadoReceptorSelect.value;
                if (empleadoReceptorId) {
                    cargarJornadaReceptorPago(empleadoReceptorId, fecha, pagoToken);
                }
                
                // ✅ NUEVA VALIDACIÓN: Si es sábado y hay receptor, validar que el sábado corresponda a la jornada del receptor
                if (esSabado(fecha) && empleadoReceptorId && fechaCesionInput?.value) {
                    validarSabadoCorrespondeReceptor(fecha, empleadoReceptorId, fechaCesionInput.value);
                }
                
                // NOTA IMPORTANTE:
                // Ya NO recargamos la lista de \"Compañero que te cubrirá\" con la fecha de pago.
                // La lista de compañeros para cesión parcial SIEMPRE se calcula con la fecha de cesión
                // (día de semana). La fecha de pago (sábado) solo se usa para validaciones de alternancia.
                //
                // actualizarVistaPrevia() se llama al terminar cargarJornadaSolicitantePago / cargarJornadaReceptorPago
                // para no clasificar con estados de la fecha anterior ni antes de que llegue la respuesta del servidor.
            }
        }).then(instance => {
            flatpickrPago = instance;
            // bloquearDiasEspeciales ya se maneja dentro de inicializar() con bloquearDiasEspeciales: true
        }).catch(error => {
            console.error('Error inicializando datepicker de pago:', error);
        });
    }
    
    /**
     * Cargar jornada del solicitante para la fecha de cesión
     */
    function cargarJornadaSolicitante(fecha, token = null) {
        if (!fecha || !window.solicitanteId) {
            solicitanteCesionEsDoblada = false;
            solicitanteCesionTurnoFetchCompleto = false;
            ultimaJornadaSolicitanteCesion = null;
            if (turnoSolicitanteInfo) {
                turnoSolicitanteInfo.style.display = 'none';
            }
            return;
        }
        solicitanteCesionTurnoFetchCompleto = false;
        
        if (turnoSolicitanteDetalles) {
            turnoSolicitanteDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (salasSolicitanteDetalles) {
            salasSolicitanteDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (turnoSolicitanteInfo) {
            turnoSolicitanteInfo.style.display = 'block';
        }
        
        const tipoSolicitudInput = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudId = tipoSolicitudInput ? tipoSolicitudInput.value : '';
        const urlSolicitanteCesion = `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fecha}${tipoSolicitudId ? `&tipo_solicitud_id=${tipoSolicitudId}` : ''}`;
        
        fetch(urlSolicitanteCesion, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            // Descartar si ya se seleccionó otra fecha de cesión mientras cargaba.
            if (token != null && token !== cesionReqToken) {
                console.log('[DEBUG] Respuesta jornada solicitante DESCARTADA (token obsoleto):', token, '!=', cesionReqToken);
                return;
            }
            console.log('[DEBUG] Respuesta obtener-turno-explorador:', data);
            solicitanteCesionEnDescanso = false;
            // Descanso en la fecha de cesión, ya sea por la semana (temporada/mantenimiento) O por una
            // solicitud aprobada (doblada, cambio de turno, cambio de descanso). En vez de las tarjetas
            // genéricas "No tiene jornada/salas" + aviso amarillo, mostrar una sola tarjeta clara
            // "Estás Descansando" con el MOTIVO (igual que en Mis Turnos).
            if (data.esta_descansando) {
                const di = data.descanso_info || {};
                let razon;
                if (di.tipo === 'descanso_semana') {
                    razon = di.motivo === 'mantenimiento'
                        ? 'Es tu día de descanso por mantenimiento.'
                        : 'Es tu día de descanso de la semana (temporada).';
                } else if (di.motivo) {
                    const comp = di.companero_nombre ? ` (con ${di.companero_nombre})` : '';
                    razon = `Descansas este día por ${di.motivo}${comp}.`;
                } else if (di.companero_nombre) {
                    razon = di.tipo === 'pago'
                        ? `Descansas este día: tu compañero ${di.companero_nombre} cubre tu doblada.`
                        : `Descansas este día por un acuerdo con ${di.companero_nombre}.`;
                } else {
                    razon = 'Descansas este día por una solicitud aprobada.';
                }
                if (turnoSolicitanteDetalles) {
                    turnoSolicitanteDetalles.innerHTML = `
                        <div class="alert alert-info mb-0">
                            <i class="fas fa-bed mr-2"></i>
                            <strong>Estás Descansando</strong>
                            <p class="mb-1 mt-1">${razon}</p>
                            <small class="text-muted">
                                <i class="fas fa-info-circle"></i>
                                No puedes ceder jornada en un día de descanso. Elige otra fecha de cesión.
                            </small>
                        </div>`;
                }
                if (salasSolicitanteDetalles) {
                    salasSolicitanteDetalles.innerHTML = '';
                }
                solicitanteCesionEnDescanso = true;
                solicitanteCesionEsDoblada = false;
                ultimaJornadaSolicitanteCesion = null;
                solicitanteCesionTurnoFetchCompleto = true;
                actualizarVistaPrevia();
                return;
            }
            if (data.success && data.turno) {
                // Alineado con fecha de pago: backend puede marcar jornada 'DOBLADA' o es_doblada sin dos entradas en jornadas[]
                const esDobladaReal = Boolean(
                    data.es_doblada ||
                    (data.turno.jornada || '').toUpperCase() === 'DOBLADA'
                );
                let jornadasCesion = (data.jornadas && data.jornadas.length) ? data.jornadas : [];
                if (esDobladaReal && jornadasCesion.length < 2) {
                    jornadasCesion = ['AM', 'PM'];
                }
                solicitanteCesionEsDoblada = esDobladaReal && jornadasCesion.length >= 2;
                const j = (data.turno.jornada || '').toUpperCase();
                ultimaJornadaSolicitanteCesion = (!solicitanteCesionEsDoblada && (j === 'AM' || j === 'PM')) ? j : null;

                renderTurnoYSalas(
                    data.turno,
                    turnoSolicitanteDetalles,
                    salasSolicitanteDetalles,
                    solicitanteCesionEsDoblada,
                    jornadasCesion
                );
            } else {
                ultimaJornadaSolicitanteCesion = null;
                solicitanteCesionEsDoblada = false;
                renderTurnoYSalas(null, turnoSolicitanteDetalles, salasSolicitanteDetalles, false, []);
            }
            solicitanteCesionTurnoFetchCompleto = true;
            actualizarVistaPrevia();
        })
        .catch(error => {
            if (token != null && token !== cesionReqToken) {
                return;
            }
            solicitanteCesionEsDoblada = false;
            solicitanteCesionEnDescanso = false;
            ultimaJornadaSolicitanteCesion = null;
            solicitanteCesionTurnoFetchCompleto = true;
            console.error('Error al cargar información del solicitante:', error);
            if (turnoSolicitanteDetalles) {
                turnoSolicitanteDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            if (salasSolicitanteDetalles) {
                salasSolicitanteDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            actualizarVistaPrevia();
        });
    }
    
    /**
     * Cargar jornada del receptor cuando se selecciona
     */
    function cargarJornadaReceptor(empleadoId, fecha) {
        if (!fecha || !empleadoId) {
            receptorCesionDescansa = false;
            receptorCesionDoblada = false;
            if (turnoReceptorInfo) {
                turnoReceptorInfo.style.display = 'none';
            }
            return;
        }
        
        if (turnoReceptorDetalles) {
            turnoReceptorDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (salasReceptorDetalles) {
            salasReceptorDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (turnoReceptorInfo) {
            turnoReceptorInfo.style.display = 'block';
        }
        
        const tipoSolicitudInput = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudId = tipoSolicitudInput ? tipoSolicitudInput.value : '';
        const urlReceptorCesion = `/solicitudes/obtener-turno-explorador/?explorador_id=${empleadoId}&fecha=${fecha}${tipoSolicitudId ? `&tipo_solicitud_id=${tipoSolicitudId}` : ''}`;
        
        fetch(urlReceptorCesion, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            // Descartar respuesta OBSOLETA: si el usuario ya cambió de compañero o de fecha de
            // cesión, no pisar las etiquetas con datos viejos (evita que se queden "pegadas").
            if (String(empleadoReceptorSelect.value) !== String(empleadoId)
                    || fechaCesionInput.value !== fecha) {
                return;
            }
            if (data.success && data.turno) {
                const j = (data.turno.jornada || '').toUpperCase();
                const esDobladaReal = Boolean(data.es_doblada || j === 'DOBLADA');
                let jornadasR = (data.jornadas && data.jornadas.length) ? data.jornadas : [];
                if (esDobladaReal && jornadasR.length < 2) {
                    jornadasR = ['AM', 'PM'];
                }
                receptorCesionDoblada = esDobladaReal && jornadasR.length >= 2;
                receptorCesionDescansa = false;
                ultimaJornadaReceptorCesion = (!receptorCesionDoblada && (j === 'AM' || j === 'PM')) ? j : null;
                renderTurnoYSalas(
                    data.turno,
                    turnoReceptorDetalles,
                    salasReceptorDetalles,
                    receptorCesionDoblada,
                    jornadasR
                );
            } else {
                ultimaJornadaReceptorCesion = null;
                receptorCesionDoblada = false;
                receptorCesionDescansa = !!(data && data.success);
                renderTurnoYSalas(null, turnoReceptorDetalles, salasReceptorDetalles, false, [], { contexto: 'receptor' });
            }
            actualizarVistaPrevia();
        })
        .catch(error => {
            receptorCesionDescansa = false;
            receptorCesionDoblada = false;
            console.error('Error al cargar información del receptor:', error);
            if (turnoReceptorDetalles) {
                turnoReceptorDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            if (salasReceptorDetalles) {
                salasReceptorDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            actualizarVistaPrevia();
        });
    }
    
    /**
     * Cargar jornada del solicitante (deudor) para la fecha de pago
     */
    function cargarJornadaSolicitantePago(fecha, token = null) {
        if (!fecha || !window.solicitanteId) {
            if (turnoSolicitantePagoInfo) {
                turnoSolicitantePagoInfo.style.display = 'none';
            }
            return;
        }
        
        if (turnoSolicitantePagoDetalles) {
            turnoSolicitantePagoDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (salasSolicitantePagoDetalles) {
            salasSolicitantePagoDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (turnoSolicitantePagoInfo) {
            turnoSolicitantePagoInfo.style.display = 'block';
        }
        
        const tipoSolicitudInputPago = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudIdPago = tipoSolicitudInputPago ? tipoSolicitudInputPago.value : '';
        const urlSolicitantePago = `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fecha}${tipoSolicitudIdPago ? `&tipo_solicitud_id=${tipoSolicitudIdPago}` : ''}`;
        
        fetch(urlSolicitantePago, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            // Descartar si ya se seleccionó otra fecha de pago mientras cargaba.
            if (token != null && token !== pagoReqToken) {
                return;
            }
            if (data.success && data.turno) {
                // Incluir doblada de sábado (backend devuelve jornada 'DOBLADA' cuando corresponde por alternancia)
                const esDoblada = data.es_doblada || (data.turno.jornada === 'DOBLADA');
                const jornadas = (data.jornadas && data.jornadas.length) ? data.jornadas : (data.turno.jornada === 'DOBLADA' ? ['AM', 'PM'] : []);
                const j = (data.turno.jornada || '').toUpperCase();
                if (esDoblada && (jornadas.length >= 2 || data.turno.jornada === 'DOBLADA')) {
                    estadoSolicitantePago = 'doblada';
                    ultimaJornadaSolicitantePago = null;
                } else if (j === 'AM' || j === 'PM') {
                    estadoSolicitantePago = 'una_jornada';
                    ultimaJornadaSolicitantePago = j;
                } else {
                    estadoSolicitantePago = null;
                    ultimaJornadaSolicitantePago = null;
                }
                renderTurnoYSalas(
                    data.turno, 
                    turnoSolicitantePagoDetalles, 
                    salasSolicitantePagoDetalles,
                    esDoblada,
                    jornadas
                );
            } else {
                ultimaJornadaSolicitantePago = null;
                estadoSolicitantePago = 'descansando';
                // Cuando no hay turno en fecha de pago (por ejemplo, festivo o sábado donde descansas),
                // mostrar la tarjeta en modo "Descanso" con texto en primera persona (deudor), no el
                // texto del receptor.
                renderTurnoYSalas(
                    null,
                    turnoSolicitantePagoDetalles,
                    salasSolicitantePagoDetalles,
                    false,
                    [],
                    { contexto: 'solicitante' }
                );
            }
            // El DEUDOR ya tiene DOBLADA (AM+PM) en la fecha de pago (día de semana): no le queda
            // jornada libre para pagar ahí. Avisar de una vez (espejo del guard del backend) y ocultar
            // el bloque "¿qué cubrirás?". En sábado esto lo gobierna la regla de pago-en-sábado.
            const _pagoEsSab = esSabado(fecha);
            if (estadoSolicitantePago === 'doblada' && !_pagoEsSab) {
                deudorDobladaEnPago = true;
                if (avisoDeudorDobladaPago && avisoDeudorDobladaPagoTexto) {
                    avisoDeudorDobladaPagoTexto.textContent =
                        ` ese día (${formatearFecha(fecha)}) ya tienes una doblada (AM + PM), así que no te ` +
                        `queda jornada libre para trabajar y devolverla. Elige otra fecha de pago en la que estés libre.`;
                    avisoDeudorDobladaPago.style.display = 'block';
                }
            } else {
                deudorDobladaEnPago = false;
                if (avisoDeudorDobladaPago) avisoDeudorDobladaPago.style.display = 'none';
            }
            // Regla doblada: si la fecha de pago es sábado, mostrar selector solo si NO te corresponde trabajar ese sábado por alternancia.
            // IMPORTANTE: usar corresponde_trabajar_sabado (tu GRUPO/alternancia), NO data.turno.jornada,
            // porque otra doblada pudo dejarte un turno que coincide con el grupo que trabaja y daría un
            // falso "ya te corresponde trabajar".
            if (sabadoSoloMitadLibre) {
                // Sábado con una mitad ya comprometida: no hay elección, se paga con la mitad libre.
                // El aviso amarillo lo explica; aquí solo se oculta el selector genérico y se fija.
                aplicarSabadoMitadLibre(sabadoSoloMitadLibre);
            } else if (sabadoPagoComprometido) {
                // Ese sábado ya está comprometido por otra doblada: no mostrar selector ni "no necesario"
                // (el aviso ya está visible y el envío queda bloqueado).
                mostrarOpcionesPagoSabado(false);
                mostrarMensajeNoNecesarioPagoSabado(false);
            } else if (data.jornada_trabaja_sabado !== undefined) {
                const correspondeTrabajarSabado = data.corresponde_trabajar_sabado === true;
                if (correspondeTrabajarSabado) {
                    mostrarOpcionesPagoSabado(false);
                    mostrarMensajeNoNecesarioPagoSabado(true);
                    // Marcar la jornada que corresponde (para que el backend reciba jornada_pago_sabado al enviar)
                    const radioAuto = document.querySelector(`input[name="jornada_pago_sabado"][value="${data.jornada_trabaja_sabado}"]`);
                    if (radioAuto) radioAuto.checked = true;
                } else {
                    mostrarOpcionesPagoSabado(true);
                    mostrarMensajeNoNecesarioPagoSabado(false);
                    limpiarSeleccionPagoSabado();
                }
            } else {
                mostrarOpcionesPagoSabado(false);
                mostrarMensajeNoNecesarioPagoSabado(false);
            }
            // Tras actualizar estado/jornada re-evaluar matriz de pago y bloque "cubre doblada receptor".
            sincronizarOpcionesCubrePagoReceptorDoblada();
        })
        .catch(error => {
            if (token != null && token !== pagoReqToken) {
                return;
            }
            console.error('Error al cargar información del solicitante en fecha de pago:', error);
            if (turnoSolicitantePagoDetalles) {
                turnoSolicitantePagoDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            if (salasSolicitantePagoDetalles) {
                salasSolicitantePagoDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
        });
    }
    
    /**
     * Cargar jornada del receptor (acreedor) para la fecha de pago
     */
    function cargarJornadaReceptorPago(empleadoId, fecha, token = null) {
        if (!fecha || !empleadoId) {
            if (turnoReceptorPagoInfo) {
                turnoReceptorPagoInfo.style.display = 'none';
            }
            return;
        }
        
        if (turnoReceptorPagoDetalles) {
            turnoReceptorPagoDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (salasReceptorPagoDetalles) {
            salasReceptorPagoDetalles.innerHTML = '<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Cargando información...</div>';
        }
        if (turnoReceptorPagoInfo) {
            turnoReceptorPagoInfo.style.display = 'block';
        }
        
        const tipoSolicitudInputReceptorPago = document.getElementById('tipo_solicitud_id');
        const tipoSolicitudIdReceptorPago = tipoSolicitudInputReceptorPago ? tipoSolicitudInputReceptorPago.value : '';
        const urlReceptorPago = `/solicitudes/obtener-turno-explorador/?explorador_id=${empleadoId}&fecha=${fecha}${tipoSolicitudIdReceptorPago ? `&tipo_solicitud_id=${tipoSolicitudIdReceptorPago}` : ''}`;
        
        fetch(urlReceptorPago, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        })
        .then(response => response.json())
        .then(data => {
            // Descartar si ya se seleccionó otra fecha de pago mientras cargaba.
            if (token != null && token !== pagoReqToken) {
                return;
            }
            // Descartar si cambió el COMPAÑERO (respuesta obsoleta): así las etiquetas del receptor
            // no se quedan pegadas con datos de otra persona. La staleness por FECHA ya la cubre el
            // token de pago de arriba (no se compara la fecha aquí porque el `fecha` que llega puede
            // venir del datepicker en otro formato y descartaría respuestas válidas).
            if (String(empleadoReceptorSelect.value) !== String(empleadoId)) {
                return;
            }
            if (data.success && data.turno) {
                const esDoblada = data.es_doblada || (data.turno.jornada === 'DOBLADA');
                let jornadas = (data.jornadas && data.jornadas.length) ? data.jornadas : (data.turno.jornada === 'DOBLADA' ? ['AM', 'PM'] : []);
                const j = (data.turno.jornada || '').toUpperCase();
                if (esDoblada && (jornadas.length >= 2 || data.turno.jornada === 'DOBLADA')) {
                    estadoReceptorPago = 'doblada';
                    ultimaJornadaReceptorPago = null;
                } else if (j === 'AM' || j === 'PM') {
                    estadoReceptorPago = 'una_jornada';
                    ultimaJornadaReceptorPago = j;
                } else {
                    estadoReceptorPago = null;
                    ultimaJornadaReceptorPago = null;
                }
                // CORRECCIÓN: Pasar información de doblada
                renderTurnoYSalas(
                    data.turno, 
                    turnoReceptorPagoDetalles, 
                    salasReceptorPagoDetalles,
                    esDoblada,
                    jornadas
                );
            } else {
                ultimaJornadaReceptorPago = null;
                estadoReceptorPago = 'descansando';
                renderTurnoYSalas(null, turnoReceptorPagoDetalles, salasReceptorPagoDetalles, false, [], { contexto: 'receptor' });
            }
            sincronizarOpcionesCubrePagoReceptorDoblada();
            verificarCoincidenciaPago();
        })
        .catch(error => {
            if (token != null && token !== pagoReqToken) {
                return;
            }
            console.error('Error al cargar información del receptor en fecha de pago:', error);
            estadoReceptorPago = null;
            if (turnoReceptorPagoDetalles) {
                turnoReceptorPagoDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            if (salasReceptorPagoDetalles) {
                salasReceptorPagoDetalles.innerHTML = `
                    <div class="text-center text-danger">
                        <i class="fas fa-exclamation-triangle"></i>
                        Error al cargar información
                    </div>
                `;
            }
            sincronizarOpcionesCubrePagoReceptorDoblada();
        });
    }
    
    /**
     * Verificación UPFRONT de coincidencia de jornadas en la fecha de pago.
     * Reusa el endpoint `verificar-coincidencia-jornadas` (la MISMA regla que valida el
     * servidor al enviar). Si el deudor trabajaría dos veces la misma jornada, muestra el
     * aviso con el motivo y el botón "Ir a CT" — ANTES de enviar, para no rebotar.
     */
    function verificarCoincidenciaPago() {
        const aviso = document.getElementById('aviso_coincidencia_pago');
        if (!aviso) return;
        const receptorId = empleadoReceptorSelect ? empleadoReceptorSelect.value : '';
        const fechaPago = fechaPagoInput ? fechaPagoInput.value : '';
        const deudorId = window.solicitanteId;
        // Solo aplica cuando hay pago normal (no sábado) con receptor y fecha.
        if (!deudorId || !receptorId || !fechaPago) {
            aviso.style.display = 'none';
            return;
        }
        // Si el compañero tiene DOBLADA en la fecha de pago, NO hay un choque fijo: depende de qué
        // jornada elijas cubrir. Ese caso lo gobierna la selección (_avisoCoincidenciaSegunCubre),
        // no la verificación genérica (que compararía tu jornada con una de las dos del compañero
        // y avisaría siempre, aunque cubras la contraria).
        if (estadoReceptorPago === 'doblada') {
            _avisoCoincidenciaSegunCubre();
            return;
        }
        const url = `/solicitudes/verificar-coincidencia-jornadas/?deudor_id=${deudorId}` +
                    `&acreedor_id=${receptorId}&fecha_pago=${encodeURIComponent(fechaPago)}`;
        // Estado vigente al lanzar el fetch: si al llegar la respuesta cambió la fecha de pago o el
        // compañero, se descarta (evita que un aviso viejo se quede "pegado" sobre el estado nuevo).
        const _vigente = () =>
            (empleadoReceptorSelect ? String(empleadoReceptorSelect.value) : '') === String(receptorId)
            && (fechaPagoInput ? fechaPagoInput.value : '') === fechaPago;
        fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then((r) => r.json())
            .then((res) => {
                if (!_vigente()) return;
                const d = (res && res.data) ? res.data : res;
                if (d && d.requiere_cambio_turno) {
                    const txt = document.getElementById('aviso_coincidencia_texto');
                    const link = document.getElementById('aviso_coincidencia_ct');
                    if (txt) txt.textContent = d.mensaje ||
                        'Trabajarías dos veces la misma jornada ese día. Haz un cambio de turno primero.';
                    if (link && typeof urlCambioTurnoSencillo === 'function') {
                        link.href = urlCambioTurnoSencillo(fechaPago);
                    }
                    aviso.style.display = 'block';
                } else {
                    aviso.style.display = 'none';
                }
            })
            .catch(() => { if (_vigente()) aviso.style.display = 'none'; });
    }

    /**
     * Compañero con DOBLADA en la fecha de pago: el aviso de "trabajarías dos veces la misma jornada"
     * SOLO aplica si eliges cubrir TU MISMA jornada (la que ya trabajas ese día). Si cubres la
     * contraria (lo normal) o aún no eliges, no hay choque → no mostrar el aviso (evita confusión).
     */
    function _avisoCoincidenciaSegunCubre() {
        const aviso = document.getElementById('aviso_coincidencia_pago');
        if (!aviso) return;
        const sel = document.querySelector('input[name="jornada_cubre_en_pago"]:checked');
        const jd = ultimaJornadaSolicitantePago;   // jornada del deudor en la fecha de pago
        if (sel && (jd === 'AM' || jd === 'PM') && String(sel.value).toUpperCase() === jd) {
            const contraria = jd === 'AM' ? 'PM' : 'AM';
            const txt = document.getElementById('aviso_coincidencia_texto');
            const link = document.getElementById('aviso_coincidencia_ct');
            if (txt) txt.textContent =
                `No puedes cubrir la jornada ${jd}: ese día ya la trabajas, la harías dos veces. ` +
                `Cubre la jornada contraria (${contraria}), o realiza primero un cambio de turno sencillo.`;
            if (link && typeof urlCambioTurnoSencillo === 'function') {
                link.href = urlCambioTurnoSencillo(fechaPagoInput ? fechaPagoInput.value : '');
            }
            aviso.style.display = 'block';
        } else {
            aviso.style.display = 'none';
        }
    }

    /**
     * Restaurar la estructura HTML del bloque doblada_existente_info.
     * Se usa cuando CASO 1 o 1.5 (descansando / no puede ceder) reemplazaron el innerHTML
     * y el usuario vuelve a una fecha con doblada existente.
     */
    function restaurarEstructuraDobladaExistente() {
        if (!dobladaExistenteInfo) return;
        dobladaExistenteInfo.innerHTML = `
            <div class="alert alert-info">
                <h6 class="alert-heading">
                    <i class="fas fa-info-circle mr-2"></i>Doblada Existente Detectada
                </h6>
                <p class="mb-2">Tienes jornada <strong>doblada (AM + PM)</strong> ese día. Elige qué hacer:</p>
                <input type="hidden" id="tipo_cesion" name="tipo_cesion" value="cesion_parcial_am">

                <!-- Opción A: intercambiar la doblada -->
                <div class="form-check mb-2">
                    <input class="form-check-input" type="checkbox" id="intercambiar_doblada" name="intercambio_doblada" value="1">
                    <label class="form-check-label" for="intercambiar_doblada">
                        <i class="fas fa-exchange-alt mr-1"></i><strong>Intercambiar mi doblada</strong> por la de un compañero
                        <small class="d-block text-muted">Elige como <em>Fecha de Pago</em> el día de la doblada del compañero. No se cede jornada.</small>
                    </label>
                </div>

                <hr class="my-2">

                <!-- Opción B: ceder una jornada (se desactiva si eliges intercambiar) -->
                <div id="opciones_cesion_parcial" class="form-group mb-0">
                    <label for="jornada_cedida" class="mb-1">
                        <i class="fas fa-clock mr-1"></i>O ceder una jornada — <strong>Jornada a Ceder</strong> <span class="text-danger">*</span>
                    </label>
                    <div class="form-check">
                        <input class="form-check-input" type="radio" name="jornada_cedida" id="jornada_am" value="AM">
                        <label class="form-check-label" for="jornada_am">AM (Mañana)</label>
                    </div>
                    <div class="form-check">
                        <input class="form-check-input" type="radio" name="jornada_cedida" id="jornada_pm" value="PM">
                        <label class="form-check-label" for="jornada_pm">PM (Tarde)</label>
                    </div>
                </div>
            </div>
        `;
    }

    /**
     * Modo INTERCAMBIO: cargar en el selector de compañero solo a quienes tienen una DOBLADA
     * (AM+PM) en el día B (fecha de pago). Se llama al entrar al modo y al cambiar la fecha de pago.
     * Usa un token para descartar respuestas en vuelo si se sale del modo o cambia la fecha.
     */
    function _mostrarAvisoIntercambio(texto) {
        if (!intercambioAviso || !intercambioAvisoTexto) return;
        if (texto) {
            intercambioAvisoTexto.textContent = texto;
            intercambioAviso.style.display = 'block';
        } else {
            intercambioAviso.style.display = 'none';
        }
    }

    /** Mensaje claro según por qué no hay candidatos (o cadena vacía si sí los hay). */
    function _motivoSinCandidatos(motivo) {
        const A = fechaCesionInput ? formatearFecha(fechaCesionInput.value) : '';
        const B = fechaPagoInput ? formatearFecha(fechaPagoInput.value) : '';
        switch (motivo) {
            case 'solicitante_ocupado':
                return `No estás libre el ${B} (ese día ya trabajas). Para intercambiar tu doblada, elige un día en que descanses.`;
            case 'ninguno_libre_dia_a':
                return `Hay compañeros con doblada el ${B}, pero ninguno descansa el ${A} para poder cubrir la tuya. Prueba con otro día.`;
            case 'mismo_dia':
                return `El día de la doblada del compañero debe ser distinto al de la tuya.`;
            default:
                return `Ningún compañero tiene doblada el ${B}.`;
        }
    }

    function cargarCompanerosIntercambio() {
        if (!modoIntercambio || !empleadoReceptorSelect) return;
        const fp = fechaPagoInput ? fechaPagoInput.value : '';
        if (!fp) {
            empleadoReceptorSelect.innerHTML = '<option value="">Elige primero el día de la doblada de tu compañero…</option>';
            empleadoReceptorSelect.disabled = true;
            _mostrarAvisoIntercambio('');
            return;
        }
        // Espejo del guard del backend (_validar_intercambio): sábado por sábado se gestiona en
        // D FDS, no aquí. Se avisa ANTES de pedir candidatos para no dejar armar una solicitud
        // que el backend va a rechazar al enviar.
        const fcSab = fechaCesionInput ? fechaCesionInput.value : '';
        if (fcSab && esSabado(fcSab) && esSabado(fp)) {
            ++interReqToken;   // invalida cualquier carga de candidatos en vuelo
            empleadoReceptorSelect.innerHTML = '<option value="">No disponible para sábado ↔ sábado</option>';
            empleadoReceptorSelect.disabled = true;
            _mostrarAvisoIntercambio(
                'No puedes intercambiar una doblada de sábado por otra de sábado. Para intercambiar ' +
                'sábados usa una Doblada de Fin de Semana (D FDS). En este formulario el sábado solo ' +
                'se cruza con un día de semana del mismo mes.'
            );
            actualizarResumenIntercambio();
            return;
        }
        const myToken = ++interReqToken;
        empleadoReceptorSelect.innerHTML = '<option value="">Cargando compañeros con doblada…</option>';
        empleadoReceptorSelect.disabled = true;
        _mostrarAvisoIntercambio('');
        // Día A (fecha de cesión): el candidato debe tener doblada el día B Y estar LIBRE el día A.
        const fc = fechaCesionInput ? fechaCesionInput.value : '';
        const qs = `fecha=${fp}` + (fc ? `&fecha_cesion=${fc}` : '');
        fetch(`/solicitudes/exploradores-con-doblada/?${qs}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(r => r.json())
            .then(d => {
                // Respuesta obsoleta (se salió del modo o cambió la fecha): descartar.
                if (myToken !== interReqToken || !modoIntercambio) return;
                const exps = (d && d.exploradores) || [];
                if (exps.length) {
                    empleadoReceptorSelect.innerHTML =
                        '<option value="">Selecciona un compañero con doblada ese día…</option>' +
                        exps.map(e => `<option value="${e.id}">${e.nombre} (DOBLADA)</option>`).join('');
                    empleadoReceptorSelect.disabled = false;
                    _mostrarAvisoIntercambio('');
                } else {
                    // Sin candidatos: explicar el motivo real en el aviso del panel.
                    empleadoReceptorSelect.innerHTML = '<option value="">Sin compañeros disponibles</option>';
                    empleadoReceptorSelect.disabled = true;
                    _mostrarAvisoIntercambio(_motivoSinCandidatos(d && d.motivo));
                }
                actualizarResumenIntercambio();
            })
            .catch(() => {
                if (myToken !== interReqToken || !modoIntercambio) return;
                empleadoReceptorSelect.disabled = false;
            });
    }

    /** Resumen del intercambio dentro del panel (día A ↔ día B). */
    function actualizarResumenIntercambio() {
        if (!resumenIntercambio || !resumenIntercambioWrap) return;
        const fCes = fechaCesionInput ? fechaCesionInput.value : '';
        const fPago = fechaPagoInput ? fechaPagoInput.value : '';
        const opt = empleadoReceptorSelect && empleadoReceptorSelect.selectedIndex >= 0
            ? empleadoReceptorSelect.options[empleadoReceptorSelect.selectedIndex] : null;
        const nombre = (opt && opt.value) ? opt.text.split(' (')[0] : '';
        if (fCes && fPago && nombre) {
            resumenIntercambio.innerHTML =
                `El día <strong>${formatearFecha(fCes)}</strong> <strong>${nombre}</strong> trabaja tu doblada completa (AM + PM) y <strong>tú descansas</strong>.<br>` +
                `El día <strong>${formatearFecha(fPago)}</strong> <strong>tú</strong> trabajas la doblada completa (AM + PM) de <strong>${nombre}</strong> y <strong>él/ella descansa</strong>.<br>` +
                `<small class="text-muted">Es un intercambio de días doblados: no se generan ni alteran deudas.</small>`;
            resumenIntercambioWrap.style.display = 'block';
        } else {
            resumenIntercambioWrap.style.display = 'none';
        }
    }

    /** Bloques que son EXCLUSIVOS del flujo de cesión: se ocultan por completo en intercambio. */
    function _bloquesSoloCesion() {
        return [
            'opciones_cesion_parcial', 'turno_receptor_info', 'fechas_pago_total',
            'turno_solicitante_pago_info', 'turno_receptor_pago_info', 'aviso_coincidencia_pago',
            'turno_solicitante_pago_am_info', 'turno_receptor_pago_am_info',
            'turno_solicitante_pago_pm_info', 'turno_receptor_pago_pm_info',
            'vista_previa_acuerdo', 'opciones_pago_sabado', 'mensaje_no_necesario_pago_sabado',
            'opciones_cubre_pago_receptor_doblada', 'aviso_sabado_comprometido',
            'aviso_deudor_doblada_pago'
        ].map(id => document.getElementById(id)).filter(Boolean);
    }

    /**
     * CONTROLADOR CENTRAL del modo intercambio. Única autoridad para entrar/salir del modo:
     *  - Reubica los campos canónicos (Fecha de Pago y Compañero) en el panel dedicado.
     *  - Oculta TODO el aparato de cesión (evita cruces como pago-sábado o "¿qué cubres?").
     *  - Cancela peticiones en vuelo y restaura limpio al salir.
     */
    function setModoIntercambio(activo, reconstruirCesion = true) {
        modoIntercambio = activo;
        // Invalida cualquier carga de compañeros en vuelo del estado anterior.
        interReqToken++;

        if (activo) {
            // Reubicar Fecha de Pago primero y Compañero después (orden natural del intercambio).
            if (panelIntercambioSlot && fechaPagoParcial) panelIntercambioSlot.appendChild(fechaPagoParcial);
            if (panelIntercambioSlot && receptorParcial) panelIntercambioSlot.appendChild(receptorParcial);
            fechaPagoParcial?.style.setProperty('display', 'block');
            receptorParcial?.style.setProperty('display', 'block');
            // Etiquetas propias del intercambio.
            if (_receptorLabelEl) _receptorLabelEl.innerHTML = '<i class="fas fa-user mr-1"></i>Compañero con doblada ese día <span class="text-danger">*</span>';
            if (_receptorHelpEl) _receptorHelpEl.textContent = 'Solo aparecen compañeros que tienen una doblada (AM + PM) ese día.';
            // Ocultar el resto del aparato de cesión.
            _bloquesSoloCesion().forEach(el => { el.style.display = 'none'; });
            // Limpiar la jornada a ceder (no aplica en intercambio; evita enviarla por error).
            document.querySelectorAll('input[name="jornada_cedida"]').forEach(r => { r.checked = false; });
            // Mostrar panel y (re)cargar candidatos con la fecha de pago actual.
            if (panelIntercambio) panelIntercambio.style.display = 'block';
            empleadoReceptorSelect.value = '';
            cargarCompanerosIntercambio();
            actualizarResumenIntercambio();
        } else {
            // Salir: ocultar panel y devolver los campos a su posición original.
            if (panelIntercambio) panelIntercambio.style.display = 'none';
            if (resumenIntercambioWrap) resumenIntercambioWrap.style.display = 'none';
            if (intercambioAviso) intercambioAviso.style.display = 'none';
            if (_origFechaPagoParent) _origFechaPagoParent.insertBefore(fechaPagoParcial, _origFechaPagoNext);
            if (_origReceptorParent) _origReceptorParent.insertBefore(receptorParcial, _origReceptorNext);
            // Restaurar etiquetas de cesión.
            if (_receptorLabelEl) _receptorLabelEl.innerHTML = _receptorLabelHTML;
            if (_receptorHelpEl) _receptorHelpEl.innerHTML = _receptorHelpHTML;
            // Limpiar selección para no arrastrar un compañero-doblada al flujo de cesión.
            empleadoReceptorSelect.value = '';
            empleadoReceptorSelect.disabled = false;
            // Volvemos a una doblada existente: re-mostrar el selector "Jornada a Ceder" (AM/PM),
            // que se había ocultado al entrar en intercambio.
            const _oc = document.getElementById('opciones_cesion_parcial');
            if (_oc && tieneDobladaExistente) _oc.style.display = 'block';
            // Reconstruir el flujo de cesión desde la fecha de cesión (recandidatos, estado, vista previa).
            // Se omite cuando ya estamos dentro del onChange de cesión (evita recursión).
            if (reconstruirCesion && fechaCesionInput && fechaCesionInput.value) {
                fechaCesionInput.dispatchEvent(new Event('change'));
            }
        }
    }

    // Wiring del modo intercambio (checkbox inyectado dinámicamente → delegación en el form).
    form.addEventListener('change', function (ev) {
        const t = ev.target;
        if (!t) return;
        if (t.id === 'intercambiar_doblada') {
            setModoIntercambio(t.checked);
        } else if (modoIntercambio && (t.id === 'empleado_receptor' || t.name === 'empleado_receptor')) {
            // En intercambio, elegir compañero solo actualiza el resumen (sin lógica de cesión).
            actualizarResumenIntercambio();
        }
    });

    /**
     * Verificar si el solicitante tiene doblada existente en la fecha
     */
    function verificarDobladaExistente(fecha) {
        if (!fecha) return;
        // Nueva selección de fecha de cesión: invalida cualquier respuesta en vuelo de una fecha anterior.
        const myToken = ++cesionReqToken;
        console.log('[DEBUG] Verificando doblada existente para fecha:', fecha, 'token:', myToken);
        fetch(`/solicitudes/verificar-doblada-existente/?fecha=${fecha}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // Si ya se seleccionó otra fecha de cesión, descartar esta respuesta obsoleta.
                if (myToken !== cesionReqToken) {
                    console.log('[DEBUG] Respuesta verificar-doblada-existente DESCARTADA (token obsoleto):', myToken, '!=', cesionReqToken);
                    return;
                }
                console.log('[DEBUG] Respuesta verificar-doblada-existente:', data);
                if (data.success) {
                    // El endpoint retorna: {success: true, tiene_doblada, esta_descansando, puede_ceder, jornadas, mensaje}
                    tieneDobladaExistente = data.tiene_doblada || false;
                    jornadasDobladaExistente = data.jornadas || [];
                    const estaDescansando = data.esta_descansando || false;
                    const puedeCeder = data.puede_ceder !== false; // Default true
                    // Guardar flag global para uso al cargar compañeros
                    solicitanteDescansaCesion = !!estaDescansando;
                    console.log('[DEBUG] tieneDobladaExistente:', tieneDobladaExistente, 'jornadas:', jornadasDobladaExistente, 'estaDescansando:', estaDescansando);
                    
                    // CASO 1: Usuario está descansando (cedió su jornada)
                    if (estaDescansando) {
                        dobladaExistenteInfo.style.display = 'block';
                        dobladaExistenteInfo.innerHTML = `
                            <div class="alert alert-info">
                                <i class="fas fa-mug-hot mr-2"></i>
                                <strong>Día Libre</strong>
                                <p class="mb-1">${data.mensaje || 'Ese día cediste tu jornada a un compañero, así que estás libre.'}</p>
                                <small class="text-muted">
                                    <i class="fas fa-info-circle"></i>
                                    Un día libre está <strong>disponible</strong>: un compañero puede pedirte que lo cubras, o puedes usarlo para <strong>pagar</strong> una doblada (trabajándolo) eligiéndolo como <strong>Fecha de Pago</strong>. Lo que no puedes es <strong>ceder</strong> este día (ya no tienes jornada que ceder aquí): para ceder, elige como Fecha de Cesión un día en el que sí trabajes.
                                </small>
                            </div>
                        `;

                        // No deshabilitar el formulario ni hacer return: permitimos continuar
                    }
                    
                    // CASO 1.5: Usuario no puede ceder (festivo donde su grupo descansa, CT aprobado, etc.)
                    if (!puedeCeder && !tieneDobladaExistente && !estaDescansando) {
                        const esFestivoDescansa = !!(data.mensaje_festivo_descansa || '');
                        const esTemporadaDiaCompleto = !!data.es_temporada_dia_completo;
                        const razon = data.mensaje || 'No puedes solicitar doblada para esta fecha.';
                        const titulo = esTemporadaDiaCompleto
                            ? 'Este día trabajas completo por temporada'
                            : (esFestivoDescansa
                                ? 'Este día festivo descansas: no puedes ceder doblada'
                                : 'No Puedes Solicitar Doblada');

                        // En temporada, guiar al flujo correcto (cobertura) con un botón.
                        const ayudaTemporada = esTemporadaDiaCompleto
                            ? `<a href="/solicitudes/cambio-turno/solicitar/6/" class="btn btn-sm btn-outline-primary mt-2">
                                   <i class="fas fa-hands-helping mr-1"></i>Ir a Cambio de Descanso (cobertura)
                               </a>`
                            : `<small class="text-muted">
                                   <i class="fas fa-info-circle"></i>
                                   Para solicitar una doblada, selecciona una fecha en la que tengas turno asignado.
                               </small>`;

                        // IMPORTANTE: deshabilitar y limpiar estado ANTES de pintar el mensaje.
                        // limpiarEstadoDoblada() oculta dobladaExistenteInfo (display:none); si lo
                        // llamáramos DESPUÉS de pintar, el mensaje quedaría invisible. En festivo no
                        // se notaba (su aviso visible va en el indicador de festivo), pero en temporada
                        // dobladaExistenteInfo es el ÚNICO lugar del mensaje → "no aparece nada".
                        deshabilitarFormularioDoblada();
                        limpiarEstadoDoblada();

                        dobladaExistenteInfo.style.display = 'block';
                        dobladaExistenteInfo.innerHTML = `
                            <div class="alert alert-warning">
                                <i class="fas fa-exclamation-triangle mr-2"></i>
                                <strong>${titulo}</strong>
                                <p class="mb-1">${razon}</p>
                                ${ayudaTemporada}
                            </div>
                        `;

                        // FESTIVO o TEMPORADA día completo: por este flujo NO hay un turno "cedible",
                        // así que ocultamos la sección "Tu Jornada para la Fecha de Cesión" (que quedó
                        // en "Cargando…" porque en estos casos NO se llama a cargarJornadaSolicitante) y
                        // neutralizamos el aviso genérico "No hay jornada a ceder": el mensaje de arriba
                        // ya explica el caso (y en temporada guía a cobertura).
                        if (esFestivoDescansa || esTemporadaDiaCompleto) {
                            if (turnoSolicitanteInfo) turnoSolicitanteInfo.style.display = 'none';
                            if (turnoSolicitanteDetalles) turnoSolicitanteDetalles.innerHTML = '';
                            if (salasSolicitanteDetalles) salasSolicitanteDetalles.innerHTML = '';
                            // Resetear flags para que actualizarAvisoSinJornadaCeder no dispare el aviso
                            // con datos de un fetch previo, y ocultarlo explícitamente.
                            solicitanteCesionTurnoFetchCompleto = false;
                            solicitanteCesionEsDoblada = false;
                            ultimaJornadaSolicitanteCesion = null;
                            const avisoSinJornada = document.getElementById('aviso_sin_jornada_ceder_cesion');
                            if (avisoSinJornada) avisoSinJornada.style.display = 'none';
                        }

                        // Festivo donde descansas: el aviso amarillo de arriba ya lo explica de forma
                        // concisa. Ocultamos el indicador de festivo para NO repetir el mismo mensaje
                        // dos veces (antes se pintaba también aquí el texto largo).
                        if (esFestivoDescansa && indicadorFestivoCesion) {
                            indicadorFestivoCesion.style.display = 'none';
                        }

                        return;
                    }
                    
                    // CASO 2: Usuario tiene doblada (es receptor)
                    if (tieneDobladaExistente) {
                        // 1. Restaurar estructura si fue destruida por CASO 1 o 1.5 (descansando / no puede ceder)
                        if (!document.getElementById('opciones_cesion_parcial')) {
                            restaurarEstructuraDobladaExistente();
                        }

                        // 2. Mostrar el contenedor principal
                        dobladaExistenteInfo.style.display = 'block';
                        
                        // 3. DETECTAR INCONSISTENCIAS DE DATOS
                        const tieneInconsistencia = data.datos_inconsistentes || false;
                        const requiereAtencion = data.requiere_atencion_admin || false;
                        // FESTIVO: el día se trabaja COMPLETO (AM+PM). Por regla de negocio NO se elige
                        // AM/PM: se cede el día completo a un solo compañero y se paga con otro festivo
                        // del mismo mes.
                        const esFestivoDoblada = !!data.es_festivo;

                        // 4. Actualizar mensaje del alert (opcional, si existe)
                        const alertDiv = dobladaExistenteInfo.querySelector('.alert');
                        if (alertDiv) {
                            if (tieneInconsistencia) {
                                alertDiv.className = 'alert alert-warning';
                                const alertHeading = alertDiv.querySelector('.alert-heading');
                                const alertMessage = alertDiv.querySelector('p');
                                
                                if (alertHeading) {
                                    alertHeading.innerHTML = '<i class="fas fa-exclamation-triangle mr-2"></i>Doblada con Datos Inconsistentes';
                                }
                                if (alertMessage) {
                                    alertMessage.innerHTML = `${data.mensaje || 'Datos inconsistentes detectados.'}<hr><p class="mb-0"><i class="fas fa-tools mr-1"></i><strong>Acción requerida:</strong> Esta solicitud requiere atención del administrador. Puedes intentar <a href="/solicitudes/mis-solicitudes/" class="alert-link">cancelar la solicitud existente</a> y crear una nueva.</p>`;
                                }
                            } else {
                                // Sin inconsistencia: Actualizar mensaje normal
                                const alertHeading = alertDiv.querySelector('.alert-heading');
                                const alertMessage = alertDiv.querySelector('p');
                                
                                if (alertHeading) {
                                    alertHeading.innerHTML = esFestivoDoblada
                                        ? '<i class="fas fa-calendar-day mr-2"></i>Día Festivo: jornada completa'
                                        : '<i class="fas fa-info-circle mr-2"></i>Doblada Existente Detectada';
                                }
                                if (alertMessage) {
                                    alertMessage.textContent = data.mensaje || 'Ya tienes una doblada aprobada para esta fecha. Puedes ceder una jornada (AM o PM).';
                                }
                            }
                        }
                        
                        // 5. SIEMPRE mostrar/ocultar opciones de cesión (independientemente de alertDiv)
                        const opcionesParcial = document.getElementById('opciones_cesion_parcial');

                        if (tieneInconsistencia) {
                            // Ocultar opciones si hay inconsistencia
                            if (opcionesParcial) opcionesParcial.style.display = 'none';
                            // Deshabilitar formulario si hay inconsistencia
                            deshabilitarFormularioDoblada();
                        } else if (esFestivoDoblada) {
                            // FESTIVO: cesión del día COMPLETO a un solo compañero. Sin selector AM/PM.
                            if (opcionesParcial) opcionesParcial.style.display = 'none';
                            // Limpiar cualquier selección AM/PM previa (no aplica en festivo).
                            document.querySelectorAll('input[name="jornada_cedida"]').forEach(r => { r.checked = false; });
                            if (tipoCesionHidden) tipoCesionHidden.value = 'cesion_completa';
                            // Asegurar visible el flujo de un solo compañero.
                            receptorParcial?.style.setProperty('display', 'block');
                            fechaPagoParcial?.style.setProperty('display', 'block');
                            habilitarFormularioDoblada();
                        } else {
                            // Mostrar opciones si NO hay inconsistencia
                            if (opcionesParcial) opcionesParcial.style.display = 'block';

                            // Habilitar controles
                            habilitarFormularioDoblada();

                            // Seleccionar jornada por defecto según las jornadas disponibles
                            if (jornadasDobladaExistente.length === 1) {
                                // Si solo tiene una jornada, seleccionarla automáticamente
                                const jornada = jornadasDobladaExistente[0];
                                const radioJornada = document.getElementById(`jornada_${jornada.toLowerCase()}`);
                                if (radioJornada) {
                                    radioJornada.checked = true;
                                    if (tipoCesionHidden) tipoCesionHidden.value = `cesion_parcial_${jornada.toLowerCase()}`;
                                }
                            } else if (jornadasDobladaExistente.length === 2) {
                                // Si tiene ambas jornadas (AM y PM), seleccionar AM por defecto
                                const radioAM = document.getElementById('jornada_am');
                                if (radioAM) {
                                    radioAM.checked = true;
                                    if (tipoCesionHidden) tipoCesionHidden.value = 'cesion_parcial_am';
                                }
                            }

                            // Si no se seleccionó ninguna jornada, usar AM como default
                            const jornadaSeleccionada = document.querySelector('input[name="jornada_cedida"]:checked');
                            if (!jornadaSeleccionada && tipoCesionHidden) {
                                tipoCesionHidden.value = 'cesion_parcial_am';
                            }
                        }
                    }
                    // CASO 3: No hay doblada (usuario normal) o festivo donde el usuario descansa.
                    // IMPORTANTE: Este bloque NO debe ejecutarse cuando estaDescansando === true,
                    // porque el CASO 1 ya mostró el aviso de descanso y no queremos ocultarlo.
                    else if (!estaDescansando) {
                        const mensajeFestivoDescansa = data.mensaje_festivo_descansa || '';
                        if (mensajeFestivoDescansa) {
                            // Limpiar opciones/radios PRIMERO (sin tocar display de dobladaExistenteInfo)
                            limpiarEstadoDoblada();
                            // Ocultar sección de jornada del solicitante (descansa ese día, no tiene turno)
                            if (turnoSolicitanteInfo) turnoSolicitanteInfo.style.display = 'none';
                            if (turnoSolicitanteDetalles) turnoSolicitanteDetalles.innerHTML = '';
                            if (salasSolicitanteDetalles) salasSolicitanteDetalles.innerHTML = '';
                            // Mostrar mensaje en indicador de festivo (visible al seleccionar festivo)
                            const descripcionFestivo = document.getElementById('descripcion_festivo_cesion');
                            if (indicadorFestivoCesion && descripcionFestivo) {
                                indicadorFestivoCesion.style.display = 'block';
                                descripcionFestivo.innerHTML = `<span class="d-block">${mensajeFestivoDescansa}</span>`;
                            }
                            habilitarFormularioDoblada();
                        } else {
                            // Sin mensaje especial: limpiar y habilitar
                            limpiarEstadoDoblada();
                            habilitarFormularioDoblada();
                        }
                    }
                    
                    // Cargar exploradores disponibles (centralizado aquí para evitar llamadas duplicadas)
                    // REGLA ACTUALIZADA:
                    // - Si puedeCeder === true (casos normales), cargamos como siempre.
                    // - Si está descansando por una doblada/cesión previa (estaDescansando === true),
                    //   también permitimos cargar compañeros (puede solicitar nueva doblada en día libre).
                    if (puedeCeder || estaDescansando) {
                        // Cesión parcial: cargar lista de compañeros una sola vez.
                        // Incluimos también compañeros en descanso (sin doblada activa) para cubrir casos 3.x y 6.x.
                        cargarExploradoresDisponibles(fecha, null, null, { incluirDescanso: true, token: myToken });
                    }

                    // Jornada del solicitante en fecha de cesión: necesaria para CASO 7–9 y matriz de pago.
                    // Si descansa o festivo sin turno y NO tiene doblada existente, no llamar a la API
                    // (evita volver a mostrar el bloque de turno oculto en festivo) y marcar explícitamente sin jornada cedible.
                    const omitirFetchTurnoCesion =
                        (estaDescansando || !!(data.mensaje_festivo_descansa || '')) && !tieneDobladaExistente;
                    if (omitirFetchTurnoCesion) {
                        ultimaJornadaSolicitanteCesion = null;
                        solicitanteCesionEsDoblada = false;
                        solicitanteCesionTurnoFetchCompleto = true;
                        // No hay jornada que mostrar (día libre / festivo donde descansa): ocultar y
                        // limpiar el panel "Tu Jornada para la Fecha de Cesión" para que no quede el
                        // de la fecha anterior.
                        if (turnoSolicitanteInfo) turnoSolicitanteInfo.style.display = 'none';
                        if (turnoSolicitanteDetalles) turnoSolicitanteDetalles.innerHTML = '';
                        if (salasSolicitanteDetalles) salasSolicitanteDetalles.innerHTML = '';
                        actualizarVistaPrevia();
                    } else {
                        cargarJornadaSolicitante(fecha, myToken);
                    }
                }
            })
            .catch(error => {
                console.error('Error verificando doblada existente:', error);
            });
    }
    
    /**
     * Limpiar estado de doblada cuando se cambia a una fecha sin doblada
     * Aplica patrones modernos: optional chaining, nullish coalescing, arrow functions
     */
    function limpiarEstadoDoblada() {
        // Ocultar información de doblada existente usando optional chaining
        dobladaExistenteInfo?.style.setProperty('display', 'none');
        
        // Limpiar y ocultar opciones de cesión parcial usando optional chaining
        const opcionesParcial = document.getElementById('opciones_cesion_parcial');
        opcionesParcial?.style.setProperty('display', 'none');
        
        // Limpiar selección de radio buttons de jornada cedida usando forEach con arrow function
        jornadaCedidaRadios?.forEach(radio => {
            radio.checked = false;
        });
        
        // Asegurar que se muestre solo cesión completa (normal)
        if (tipoCesionHidden) {
            tipoCesionHidden.value = 'cesion_completa';
        }
        
        // Asegurar que se muestren los campos de cesión parcial
        receptorParcial?.style.setProperty('display', 'block');
        fechaPagoParcial?.style.setProperty('display', 'block');
    }

    /**
     * Resetea TODA la sección de pago (fechas, compañeros, paneles "Tu Jornada para Fecha de
     * Pago" y selectores de pago en sábado) cuando cambia la FECHA DE CESIÓN. Sin esto, al
     * cambiar de fecha quedaban visibles datos/paneles calculados para la fecha anterior.
     */
    function resetearSeccionPagoPorCambioCesion() {
        // Fechas de pago
        if (fechaPagoInput) fechaPagoInput.value = '';
        try { flatpickrPago && flatpickrPago.clear && flatpickrPago.clear(); } catch (e) {}
        // Compañeros (su disponibilidad depende de la fecha; verificarDobladaExistente los recarga)
        if (empleadoReceptorSelect) empleadoReceptorSelect.value = '';
        // Panel "Jornada del Explorador que te Cubrirá" (receptor en fecha de cesión): se invalida
        // al cambiar fecha o tipo de cesión, así que se oculta hasta elegir compañero de nuevo.
        if (turnoReceptorInfo) turnoReceptorInfo.style.display = 'none';
        if (turnoReceptorDetalles) turnoReceptorDetalles.innerHTML = '';
        if (salasReceptorDetalles) salasReceptorDetalles.innerHTML = '';
        // Paneles "Tu Jornada / Jornada del receptor para la Fecha de Pago"
        [
            turnoSolicitantePagoInfo, turnoReceptorPagoInfo,
            document.getElementById('turno_solicitante_pago_am_info'),
            document.getElementById('turno_solicitante_pago_pm_info'),
            document.getElementById('turno_receptor_pago_am_info'),
            document.getElementById('turno_receptor_pago_pm_info'),
            document.getElementById('aviso_coincidencia_pago'),
        ].forEach(el => { if (el) el.style.display = 'none'; });
        // Selectores de pago en sábado (cesión parcial y cesión total)
        [
            opcionesPagoSabado, mensajeNoNecesarioPagoSabado,
            document.getElementById('jornada_sabado_am_wrap'),
            document.getElementById('jornada_sabado_pm_wrap'),
        ].forEach(el => { if (el) el.style.display = 'none'; });
        document.querySelectorAll(
            'input[name="jornada_pago_sabado"], input[name="jornada_pago_sabado_am"], input[name="jornada_pago_sabado_pm"]'
        ).forEach(r => { r.checked = false; });
        // Bloque "¿Qué cubrirás ese día?" (receptor con doblada en el pago): ocultar y desmarcar.
        const cubreBlock = document.getElementById('opciones_cubre_pago_receptor_doblada');
        if (cubreBlock) {
            cubreBlock.style.display = 'none';
            cubreBlock.querySelectorAll('input[name="jornada_cubre_en_pago"]').forEach(r => {
                r.checked = false;
                r.removeAttribute('required');
            });
            const notaCubre = cubreBlock.querySelector('.nota-cubre-jornada');
            if (notaCubre) notaCubre.style.display = 'none';
        }
        // Estado de clasificación del pago
        estadoSolicitantePago = null;
        estadoReceptorPago = null;
        ultimaJornadaSolicitantePago = null;
        ultimaJornadaReceptorPago = null;
        pagoEsFestivo = false;
        casoPagoRechazado = false;
        mensajeRechazoPago = '';
        casoPagoRequiereRedireccionCT = false;
        // Ocultar la vista previa del acuerdo (se vuelve a mostrar cuando todo esté completo de nuevo)
        if (vistaPreviaAcuerdo) vistaPreviaAcuerdo.style.display = 'none';
    }
    
    /**
     * Deshabilitar formulario cuando el usuario está descansando
     */
    function deshabilitarFormularioDoblada() {
        if (empleadoReceptorSelect) empleadoReceptorSelect.disabled = true;
        if (fechaPagoInput) fechaPagoInput.disabled = true;

        const submitBtn = document.querySelector('button[type="submit"]');
        if (submitBtn) submitBtn.disabled = true;
    }

    /**
     * Habilitar formulario cuando el usuario puede ceder
     */
    function habilitarFormularioDoblada() {
        if (empleadoReceptorSelect) empleadoReceptorSelect.disabled = false;
        if (fechaPagoInput) fechaPagoInput.disabled = false;

        const submitBtn = document.querySelector('button[type="submit"]');
        if (submitBtn) submitBtn.disabled = false;
    }
    
    /**
     * Cargar exploradores disponibles para doblada
     */
    /**
     * Cargar exploradores disponibles para "Compañero que te cubrirá".
     * Usa la fecha en la que el receptor trabajará (fecha de pago cuando aplique).
     * Si la fecha es sábado, el backend devuelve solo quienes trabajan ese sábado (alternancia).
     * @param {string} fecha - Fecha para la que se buscan compañeros (cesión o fecha de pago)
     * @param {string} jornada - Jornada específica ('AM' o 'PM') para cesión total (opcional)
     * @param {HTMLElement} selectElement - Elemento select donde cargar (opcional, por defecto empleadoReceptorSelect)
     */
    function cargarExploradoresDisponibles(fecha, jornada = null, selectElement = null, opciones = {}) {
        // En modo intercambio los candidatos los gestiona cargarCompanerosIntercambio (compañeros
        // con doblada ese día). No dejar que el flujo de cesión pise ese selector reubicado.
        if (modoIntercambio && (!selectElement || selectElement === empleadoReceptorSelect)) {
            return;
        }
        if (!fecha) {
            const targetSelect = selectElement || empleadoReceptorSelect;
            if (targetSelect) {
                targetSelect.innerHTML = '<option value="">Selecciona primero la fecha de cesión</option>';
            }
            return;
        }
        
        const targetSelect = selectElement || empleadoReceptorSelect;
        if (!targetSelect) {
            return;
        }
        
        let jornadaCedida = null;
        
        if (jornada) {
            jornadaCedida = jornada;
        } 
        else {
            const radioSeleccionado = document.querySelector('input[name="jornada_cedida"]:checked');
            if (radioSeleccionado) {
                jornadaCedida = radioSeleccionado.value;
            }
        }
        
        const flagDescanso = solicitanteDescansaCesion ? '&solicitante_descansa=1' : '';
        const flagIncluirDescanso = opciones.incluirDescanso ? '&incluir_descanso=1' : '';
        const url = `/solicitudes/obtener-exploradores-doblada/?fecha=${fecha}${jornadaCedida ? `&jornada_cedida=${jornadaCedida}` : ''}${flagDescanso}${flagIncluirDescanso}`;
        
        // Por defecto, capturar el token de cesión VIGENTE: así toda respuesta que llegue tarde
        // (tras cambiar de fecha) se descarta y la lista no se queda "pegada" con datos viejos.
        const token = (opciones && opciones.token != null) ? opciones.token : cesionReqToken;
        targetSelect.innerHTML = '<option value="">Cargando...</option>';

        fetch(url)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                // Descartar si ya se seleccionó otra fecha de cesión mientras cargaba.
                if (token != null && token !== cesionReqToken) {
                    return;
                }
                if (data.success) {
                    targetSelect.innerHTML = '<option value="">Selecciona un compañero...</option>';
                    
                    // El endpoint retorna: {success: true, empleados: [...], total: N}
                    if (data.empleados && data.empleados.length > 0) {
                        data.empleados.forEach(empleado => {
                            const option = document.createElement('option');
                            option.value = empleado.id;
                            option.textContent = `${empleado.nombre} ${empleado.apellido} (${empleado.jornada})`;
                            targetSelect.appendChild(option);
                        });
                    } else {
                        targetSelect.innerHTML = '<option value="">No hay compañeros disponibles para esta fecha</option>';
                    }
                    
                    // Actualizar vista previa
                    actualizarVistaPrevia();
                } else {
                    console.error('Error en respuesta:', data.error || 'Error desconocido');
                    targetSelect.innerHTML = '<option value="">Error al cargar compañeros</option>';
                }
            })
            .catch(error => {
                if (token != null && token !== cesionReqToken) {
                    return;
                }
                console.error('Error cargando exploradores disponibles:', error);
                targetSelect.innerHTML = '<option value="">Error al cargar compañeros</option>';
            });
    }
    
    /**
     * Actualizar vista previa del acuerdo
     * Formato: "El día X cedes tu jornada AM/PM a Y. Y te cubrirá el día Z"
     * Maneja tanto cesión parcial como cesión total
     */
    /** CASO 7–9: aviso «Paso 2» cuando no hay jornada a ceder (sin AM/PM ni doblada en cesión). */
    function actualizarAvisoSinJornadaCeder() {
        if (!fechaCesionInput) {
            return;
        }
        const fec = fechaCesionInput.value;
        // "Sin jornada a ceder": el fetch de la jornada del solicitante terminó y no tiene
        // AM, PM ni doblada en la fecha de cesión (descansa ese día / festivo de su grupo).
        const sinJornadaCeder = solicitanteCesionTurnoFetchCompleto && !tieneDobladaExistente && !solicitanteCesionEsDoblada &&
            ultimaJornadaSolicitanteCesion !== 'AM' && ultimaJornadaSolicitanteCesion !== 'PM';

        const el = document.getElementById('aviso_sin_jornada_ceder_cesion');
        if (el) {
            // Si es un DÍA LIBRE (cedió su jornada) o un descanso de la semana (temporada/mantenimiento),
            // la tarjeta correspondiente ya explica el caso: no repetir el aviso amarillo genérico.
            const esDiaLibre = !!solicitanteDescansaCesion || !!solicitanteCesionEnDescanso;
            el.style.display = (fec && sinJornadaCeder && !esDiaLibre) ? 'block' : 'none';
        }

        // GUARDIA CENTRAL: si no hay jornada que ceder, no se puede elegir compañero ni
        // fecha de pago ni enviar — independientemente de lo que haya respondido
        // verificar-doblada-existente (evita la carrera entre ambos fetch async).
        if (fec && sinJornadaCeder) {
            deshabilitarFormularioDoblada();
        }
    }

    function actualizarVistaPreviaAcuerdo() {
        const fechaCesion = fechaCesionInput.value;

        // MODO INTERCAMBIO: la vista previa vive en el panel dedicado (resumen_intercambio).
        // Aquí no se ejecuta NADA de la lógica/matriz de cesión y se oculta la vista previa normal.
        if (modoIntercambio) {
            casoPagoRechazado = false;
            casoPagoRequiereRedireccionCT = false;
            mensajeRechazoPago = '';
            if (vistaPreviaAcuerdo) vistaPreviaAcuerdo.style.display = 'none';
            actualizarResumenIntercambio();
            return;
        }

        if (!vistaPreviaAcuerdo || !resumenAcuerdo) {
            actualizarAvisoSinJornadaCeder();
            return;
        }

        {
            // Cesión Parcial: mostrar resumen normal
            const fechaPago = fechaPagoInput.value;
            const empleadoReceptorId = empleadoReceptorSelect.value;
            const empleadoReceptorOption = empleadoReceptorSelect.options[empleadoReceptorSelect.selectedIndex];
            const empleadoReceptorNombre = empleadoReceptorOption ? empleadoReceptorOption.text.split(' (')[0] : ''; // Extraer solo el nombre sin la jornada
            
            if (fechaCesion && fechaPago && empleadoReceptorId && empleadoReceptorNombre) {
                let rechazoRequiereCTSencillo = false;
                // Determinar jornada cedida
                let jornadaCedidaTexto = 'tu jornada';
                if (tieneDobladaExistente) {
                    const jornadaCedidaRadio = document.querySelector('input[name="jornada_cedida"]:checked');
                    if (jornadaCedidaRadio) {
                        const jornadaCedida = jornadaCedidaRadio.value;
                        jornadaCedidaTexto = `tu jornada ${jornadaCedida}`;
                    }
                }

                // Casos 1.x / 3.x: emisor 1 jornada en cesión (+ receptor contrario o descanso)
                // Casos 4.x: emisor DOBLADA en cesión, cesión parcial con jornada a ceder elegida, receptor contrario a esa media jornada
                // CASO 7–9: emisor descansando / sin turno cedible (sin doblada existente ni AM+PM real)
                const jornadaSolCesion = ultimaJornadaSolicitanteCesion;
                const emisorDobladaCesion = solicitanteCesionEsDoblada || tieneDobladaExistente;
                const emisorSinJornadaParaCederEnCesion = solicitanteCesionTurnoFetchCompleto && !tieneDobladaExistente && !solicitanteCesionEsDoblada &&
                    jornadaSolCesion !== 'AM' && jornadaSolCesion !== 'PM';
                const jornadaRecCesion = ultimaJornadaReceptorCesion;
                const jornadaSolPago = ultimaJornadaSolicitantePago;
                const jornadaRecPago = ultimaJornadaReceptorPago;
                const contrariasCesion = (jornadaSolCesion === 'AM' && jornadaRecCesion === 'PM') || (jornadaSolCesion === 'PM' && jornadaRecCesion === 'AM');
                const contrariasPago = (jornadaSolPago === 'AM' && jornadaRecPago === 'PM') || (jornadaSolPago === 'PM' && jornadaRecPago === 'AM');
                const emisorUnaJornadaCesion = jornadaSolCesion === 'AM' || jornadaSolCesion === 'PM';
                const receptorUnaJornadaCesion = jornadaRecCesion === 'AM' || jornadaRecCesion === 'PM';

                let jornadaCedidaVal = null;
                if (tieneDobladaExistente || solicitanteCesionEsDoblada) {
                    const jcr = document.querySelector('input[name="jornada_cedida"]:checked');
                    if (jcr) jornadaCedidaVal = String(jcr.value).toUpperCase();
                }
                const cedidaOk = jornadaCedidaVal === 'AM' || jornadaCedidaVal === 'PM';
                const contrariasCesionParcialDoblada = cedidaOk && receptorUnaJornadaCesion &&
                    ((jornadaCedidaVal === 'AM' && jornadaRecCesion === 'PM') || (jornadaCedidaVal === 'PM' && jornadaRecCesion === 'AM'));

                const cesionContrariasOk = receptorUnaJornadaCesion && contrariasCesion;
                const cesionReceptorDescansaOk = receptorCesionDescansa && !receptorCesionDoblada;
                const cesionValidaEmisorUnaJornada = emisorUnaJornadaCesion && !receptorCesionDoblada && (cesionContrariasOk || cesionReceptorDescansaOk);
                /** Emisor con doblada en cesión (existente o turnos AM+PM) y jornada a ceder elegida */
                const emisorTieneDobladaParcialCesion = (solicitanteCesionEsDoblada || tieneDobladaExistente) && cedidaOk;
                const cesionValidaEmisorDobladaParcial = emisorTieneDobladaParcialCesion && !receptorCesionDoblada && contrariasCesionParcialDoblada;
                /** CASO 6: emisor doblada parcial, receptor descansando en fecha de cesión */
                const cesionValidaEmisorDobladaReceptorDescansa = emisorTieneDobladaParcialCesion && cesionReceptorDescansaOk;
                const aplicaCasosPago = cesionValidaEmisorUnaJornada || cesionValidaEmisorDobladaParcial || cesionValidaEmisorDobladaReceptorDescansa;

                const jornadaEmisorReferencia = emisorTieneDobladaParcialCesion ? jornadaCedidaVal : jornadaSolCesion;
                const contrariasCesionEfectiva = emisorTieneDobladaParcialCesion
                    ? contrariasCesionParcialDoblada
                    : contrariasCesion;

                const estadoSol = estadoSolicitantePago;
                const estadoRec = estadoReceptorPago;

                let casoNum = null;
                let mensajeValidacion = '';
                let esRechazado = false;

                if (emisorSinJornadaParaCederEnCesion) {
                    // CASO 7 (receptor 1 jornada), 8 (receptor doblada), 9 (ambos descansando): prevalece mensaje de emisor
                    casoNum = '7-9';
                    esRechazado = true;
                    mensajeValidacion = 'El solicitante no tiene jornada asignada para esa fecha';
                } else if (receptorCesionDoblada && emisorDobladaCesion) {
                    casoNum = '5';
                    esRechazado = true;
                    mensajeValidacion = 'El receptor no puede tener doblada el día de la cesión.';
                } else if (aplicaCasosPago && estadoSol != null && estadoRec != null) {
                    // Matriz 1.2–1.10 (deudor = solicitante, acreedor = receptor)
                    if (estadoSol === 'descansando' && estadoRec === 'descansando') {
                        casoNum = '1.2';
                        esRechazado = true;
                        mensajeValidacion = 'Los dos están descansando. No se puede realizar el pago en esa fecha.';
                    } else if (estadoSol === 'descansando' && estadoRec === 'una_jornada') {
                        casoNum = '1.3';
                        mensajeValidacion = cesionValidaEmisorDobladaReceptorDescansa
                            ? `Se puede realizar el cambio. Ese día lo tienes libre y por ende puedes cubrir el día y así pagar tu deuda. En ese caso ${empleadoReceptorNombre} descansa y tú reemplazas su jornada.`
                            : `El emisor está descansando, por lo tanto puede pagar el turno que debe. En ese caso ${empleadoReceptorNombre} descansa y tú lo reemplazas en su jornada AM o PM.`;
                    } else if (estadoSol === 'descansando' && estadoRec === 'doblada') {
                        casoNum = '1.4';
                        mensajeValidacion = `Se puede realizar el pago. Ese día lo tienes libre y el receptor tiene doblada (AM+PM). Como solo le debes una jornada, elige cuál le cubres (AM o PM); él conserva la otra. Por defecto se sugiere la misma jornada que cediste en la cesión.`;
                    } else if (estadoSol === 'una_jornada' && estadoRec === 'descansando') {
                        casoNum = '1.5/1.8';
                        esRechazado = true;
                        mensajeValidacion = 'El receptor se encuentra descansando ese día. No puedes pagarle en esta fecha. Debes elegir otra fecha de pago.';
                    } else if (estadoSol === 'una_jornada' && estadoRec === 'una_jornada') {
                        casoNum = '1.6';
                        const mismaJornadaAmbosEnPago = jornadaSolPago && jornadaRecPago && jornadaSolPago === jornadaRecPago;
                        if (mismaJornadaAmbosEnPago) {
                            esRechazado = true;
                            rechazoRequiereCTSencillo = true;
                            const fechaPagoFmt = formatearFecha(fechaPago);
                            if (emisorTieneDobladaParcialCesion) {
                                mensajeValidacion =
                                    `Se puede realizar el pago en cuanto a reglas, pero en la fecha de pago (${fechaPagoFmt}) tú y ${empleadoReceptorNombre} tienen la misma jornada (${jornadaSolPago}). ` +
                                    'Debes realizar primero un cambio de turno sencillo para quedar en jornada opuesta; ese día tú doblarás y el receptor descansará.';
                            } else {
                                mensajeValidacion =
                                    `En la fecha de pago (${fechaPagoFmt}), tú y ${empleadoReceptorNombre} tienen la misma jornada (${jornadaSolPago}). ` +
                                    'Para pagar la doblada deben quedar en jornadas contrarias. Realiza primero un cambio de turno sencillo para tener horario opuesto en esa fecha.';
                            }
                        } else {
                        const mismaJornada = jornadaSolPago && jornadaEmisorReferencia && jornadaSolPago === jornadaEmisorReferencia;
                        if (mismaJornada) {
                            mensajeValidacion = emisorTieneDobladaParcialCesion
                                ? `Misma jornada en pago que la que cediste (${jornadaEmisorReferencia}). Necesitas un cambio de turno sencillo para quedar en horario opuesto: ese día tú doblarás y ${empleadoReceptorNombre} descansará.`
                                : `Misma jornada en pago que la que cediste. Necesitas un cambio de turno sencillo para quedar en horario opuesto: ese día tú doblarás y ${empleadoReceptorNombre} descansará.`;
                        } else {
                            mensajeValidacion = `Si tienen jornadas diferentes se puede realizar el pago. Tú tienes ${jornadaSolPago || 'jornada'} y ${empleadoReceptorNombre} tiene ${jornadaRecPago || 'jornada'}. Como tienen jornadas distintas, el pago se realiza directamente sin necesidad de un cambio adicional. Ese día tú doblarás y ${empleadoReceptorNombre} descansará.`;
                        }
                        }
                    } else if (estadoSol === 'una_jornada' && estadoRec === 'doblada') {
                        casoNum = '1.7';
                        const mismaQueCedio = jornadaSolPago && jornadaEmisorReferencia && jornadaSolPago === jornadaEmisorReferencia;
                        mensajeValidacion = mismaQueCedio
                            ? `Se puede realizar el pago. Como el emisor solo tiene un turno (${jornadaSolPago || jornadaEmisorReferencia}), puede pagar su deuda aunque el receptor tenga doblada. Si tienes la misma jornada que cediste (${jornadaEmisorReferencia}), deberás realizar un cambio de turno sencillo con otro explorador para quedar en horario opuesto y pagar la jornada cedida. Ese día trabajarás tu jornada propia más la que debes, y ${empleadoReceptorNombre} solo la jornada restante de su doblada.`
                            : `Se puede realizar el pago. Ese día tú tienes una jornada y ${empleadoReceptorNombre} tiene doblada; pagas cubriendo una de sus jornadas.`;
                    } else if (estadoSol === 'doblada' && estadoRec === 'descansando') {
                        casoNum = '3.9';
                        esRechazado = true;
                        mensajeValidacion =
                            'El emisor tiene una doblada para la fecha de pago y el receptor se encuentra descansando. ' +
                            'No es posible realizar el pago en esta fecha. Selecciona otra fecha de pago.';
                    } else if (estadoSol === 'doblada' && estadoRec === 'una_jornada') {
                        casoNum = '1.9';
                        esRechazado = true;
                        mensajeValidacion = 'No puedes realizar el pago en esta fecha porque tienes una doblada ese día y por ende no tienes jornada libre para cubrir. Debes seleccionar otra fecha de pago.';
                    } else if (estadoSol === 'doblada' && estadoRec === 'doblada') {
                        casoNum = '1.10';
                        esRechazado = true;
                        mensajeValidacion = 'Ambos tienen doblada para la fecha de pago. No es posible pagar la deuda en esta fecha. Selecciona otra fecha.';
                    }
                }

                // Caso 1.1: contrarias en cesión (incl. parcial desde doblada) y en pago (ambos una_jornada)
                const esCaso1_1 = aplicaCasosPago && contrariasCesionEfectiva && contrariasPago && jornadaSolPago && jornadaRecPago && estadoSol === 'una_jornada' && estadoRec === 'una_jornada';

                casoPagoRechazado = esRechazado;
                mensajeRechazoPago = mensajeValidacion;
                casoPagoRequiereRedireccionCT = rechazoRequiereCTSencillo;

                // Formatear fechas para mostrar
                const fechaCesionFormateada = formatearFecha(fechaCesion);
                const fechaPagoFormateada = formatearFecha(fechaPago);

                // Bloque "Paso 3 – Validación y envío" no mostrado: la Vista Previa del Acuerdo ya resume el acuerdo.
                // Se mantiene casoPagoRechazado/mensajeRechazoPago para bloquear envío cuando aplique.

                // Construir mensaje según el plan de doblada:
                // - En la fecha de cesión: el compañero se dobla por ti (tú descansas).
                // - En la fecha de pago: según matriz; si receptor doblada, texto según jornada_cubre_en_pago.
                const bloqueCubreDoblada = document.getElementById('opciones_cubre_pago_receptor_doblada');
                const cubreVisible = bloqueCubreDoblada && bloqueCubreDoblada.style.display !== 'none';
                const radioCubre = document.querySelector('input[name="jornada_cubre_en_pago"]:checked');
                const valCubre = radioCubre ? radioCubre.value : '';
                let lineaPagoDoblada = `El día <strong>${fechaPagoFormateada}</strong> <strong>tú</strong> cubrirás una de las jornadas de <strong>${empleadoReceptorNombre}</strong> como pago de la doblada.`;
                if (estadoSol === 'descansando' && estadoRec === 'doblada' && cubreVisible) {
                    if (valCubre === 'AM' || valCubre === 'PM') {
                        lineaPagoDoblada = `El día <strong>${fechaPagoFormateada}</strong> <strong>tú</strong> cubrirás su jornada <strong>${valCubre}</strong>; él conserva la otra media jornada.`;
                    }
                } else if (estadoRec === 'una_jornada' && (ultimaJornadaReceptorPago === 'AM' || ultimaJornadaReceptorPago === 'PM')) {
                    // El compañero tiene UNA sola jornada ese día: se cubre exactamente esa.
                    lineaPagoDoblada = `El día <strong>${fechaPagoFormateada}</strong> <strong>tú</strong> cubrirás la jornada <strong>${ultimaJornadaReceptorPago}</strong> de <strong>${empleadoReceptorNombre}</strong> (su único turno ese día) como pago de la doblada.`;
                }
                if (emisorSinJornadaParaCederEnCesion) {
                    resumenAcuerdo.innerHTML = `
                    <div class="alert alert-danger mb-0">
                        <strong>No se puede enviar la solicitud</strong><br>
                        ${mensajeValidacion}
                    </div>
                `;
                } else {
                resumenAcuerdo.innerHTML = `
                    <div class="alert alert-info mb-0">
                        <strong>Resumen del Acuerdo:</strong><br>
                        El día <strong>${fechaCesionFormateada}</strong> cedes <strong>${jornadaCedidaTexto}</strong> a <strong>${empleadoReceptorNombre}</strong> (él se dobla por ti y tú descansas).<br>
                        ${lineaPagoDoblada}
                    </div>
                `;
                }
                
                vistaPreviaAcuerdo.style.display = 'block';
            } else {
                casoPagoRechazado = false;
                casoPagoRequiereRedireccionCT = false;
                mensajeRechazoPago = '';
                vistaPreviaAcuerdo.style.display = 'none';
            }
        }
        actualizarAvisoSinJornadaCeder();
    }
    
    /** Misma ruta que el manejo de `requiere_cambio_turno_previo` tras enviar al servidor */
    function urlCambioTurnoSencillo(fechaIso) {
        if (!fechaIso) {
            return '/solicitudes/cambio-turno/solicitar/1/';
        }
        return `/solicitudes/cambio-turno/solicitar/1/?fecha_solicitud=${encodeURIComponent(fechaIso)}`;
    }
    
    /**
     * Formatear fecha de YYYY-MM-DD a DD/MM/YYYY
     */
    function formatearFecha(fecha) {
        if (!fecha) return '';
        const partes = fecha.split('-');
        if (partes.length === 3) {
            return `${partes[2]}/${partes[1]}/${partes[0]}`;
        }
        return fecha;
    }
    
    /**
     * Alias para mantener compatibilidad
     */
    function actualizarVistaPrevia() {
        actualizarVistaPreviaAcuerdo();
    }
    
    /**
     * Manejar cambio en jornada cedida (si está en doblada)
     */
    jornadaCedidaRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.checked) {
                tipoCesionHidden.value = `cesion_parcial_${this.value.toLowerCase()}`;
                // Recargar exploradores disponibles SIEMPRE con la fecha de cesión.
                // La fecha de pago sábado no debe cambiar el grupo de compañeros.
                const fechaParaLista = fechaCesionInput.value;
                if (fechaParaLista) {
                    cargarExploradoresDisponibles(fechaParaLista, null, null, { incluirDescanso: true });
                }
                sincronizarOpcionesCubrePagoReceptorDoblada();
            }
        });
    });

    if (form) {
        form.addEventListener('change', function(e) {
            if (e.target && e.target.name === 'jornada_cubre_en_pago') {
                // El aviso "trabajarías dos veces la misma jornada" depende de la opción elegida.
                _avisoCoincidenciaSegunCubre();
                actualizarVistaPrevia();
            }
        });
    }
    
    /**
     * Validar que el sábado de pago corresponda a la jornada del receptor (quien hizo el doble turno)
     * Regla de negocio:
     * - Si cedes jornada AM → receptor es PM → sábado de pago debe ser para PM
     * - Si cedes jornada PM → receptor es AM → sábado de pago debe ser para AM
     * Aplica patrones modernos: async/await, optional chaining, destructuring
     */
    async function validarSabadoCorrespondeReceptor(fechaPago, receptorId, fechaCesion) {
        if (!fechaPago || !receptorId || !fechaCesion) return;
        
        try {
            // Obtener jornada del receptor en fecha de cesión + turno real del receptor en fecha de pago
            const [responseReceptor, responsePago, responseReceptorPago] = await Promise.all([
                fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${receptorId}&fecha=${fechaCesion}`),
                fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fechaPago}`),
                fetch(`/solicitudes/obtener-turno-explorador/?explorador_id=${receptorId}&fecha=${fechaPago}`)
            ]);

            const [dataReceptor, dataPago, dataReceptorPago] = await Promise.all([
                responseReceptor.json(),
                responsePago.json(),
                responseReceptorPago.json()
            ]);

            if (!dataReceptor.success || !dataReceptor.turno) {
                return; // No validar si no hay datos del receptor
            }

            // Obtener jornada del receptor en fecha de cesión
            const jornadaReceptorCesion = dataReceptor.turno.jornada?.toUpperCase();
            if (!jornadaReceptorCesion || !['AM', 'PM'].includes(jornadaReceptorCesion)) {
                return; // No validar si no hay jornada válida
            }

            // Obtener jornada que trabaja ese sábado (alternancia)
            const jornadaTrabajaSabado = dataPago.jornada_trabaja_sabado?.toUpperCase();
            if (!jornadaTrabajaSabado) {
                return; // No validar si no se puede determinar alternancia
            }

            // Si el receptor tiene un turno REAL en el sábado de pago (p. ej. por un cambio de
            // descanso previo que le asignó ese día), ese turno supera a la alternancia y el
            // sábado es válido para él independientemente de su jornada base.
            const receptorTrabajaSabPorTurno = dataReceptorPago.success === true &&
                dataReceptorPago.tiene_turno === true;

            // Validar que el sábado corresponda a la jornada del receptor
            if (!receptorTrabajaSabPorTurno && jornadaReceptorCesion !== jornadaTrabajaSabado) {
                // Obtener jornada que se está cediendo para el mensaje
                let jornadaCedida = null;
                if (tieneDobladaExistente) {
                    const radioJornada = document.querySelector('input[name="jornada_cedida"]:checked');
                    if (radioJornada) {
                        jornadaCedida = radioJornada.value.toUpperCase();
                    }
                } else {
                    // Obtener jornada del solicitante en fecha de cesión
                    const responseSolicitante = await fetch(
                        `/solicitudes/obtener-turno-explorador/?explorador_id=${window.solicitanteId}&fecha=${fechaCesion}`
                    );
                    const dataSolicitante = await responseSolicitante.json();
                    if (dataSolicitante.success && dataSolicitante.turno) {
                        jornadaCedida = dataSolicitante.turno.jornada?.toUpperCase();
                    }
                }
                
                const fechaPagoFormateada = formatearFecha(fechaPago);
                const mensaje = jornadaCedida 
                    ? `No se puede realizar esta solicitud. El sábado ${fechaPagoFormateada} corresponde al turno ${jornadaTrabajaSabado}, pero el compañero que cubrirá tu jornada ${jornadaCedida} tiene jornada ${jornadaReceptorCesion}. El sábado de pago siempre debe coincidir con el turno de la persona que realizó el doble turno. Por favor, selecciona otro sábado que corresponda al turno ${jornadaReceptorCesion}.`
                    : `No se puede realizar esta solicitud. El sábado ${fechaPagoFormateada} corresponde al turno ${jornadaTrabajaSabado}, pero el compañero que cubrirá tu jornada tiene jornada ${jornadaReceptorCesion}. El sábado de pago siempre debe coincidir con el turno de la persona que realizó el doble turno. Por favor, selecciona otro sábado que corresponda al turno ${jornadaReceptorCesion}.`;
                
                Swal.fire({
                    icon: 'error',
                    title: 'Sábado No Válido',
                    html: `<div class="text-left"><p>${mensaje}</p></div>`,
                    confirmButtonText: 'Entendido',
                    confirmButtonColor: '#d33',
                    width: '600px'
                });
                
                // Limpiar fecha de pago
                fechaPagoInput.value = '';
                mostrarOpcionesPagoSabado(false);
                mostrarMensajeNoNecesarioPagoSabado(false);
            }
        } catch (error) {
            console.error('Error validando sábado corresponde receptor:', error);
            // No mostrar error al usuario si falla la validación (el backend validará)
        }
    }
    
    /**
     * Manejar cambio en empleado receptor
     */
    empleadoReceptorSelect.addEventListener('change', function() {
        // En intercambio, elegir compañero NO dispara la lógica de cesión (jornadas/matriz);
        // el resumen del panel se actualiza vía el handler delegado del form.
        if (modoIntercambio) {
            actualizarResumenIntercambio();
            return;
        }
        const empleadoId = this.value;
        const fechaCesion = fechaCesionInput.value;
        const fechaPago = fechaPagoInput.value;

        // El aviso de coincidencia depende del compañero: ocultarlo de inmediato para que no quede
        // pegado del compañero anterior; se re-evalúa tras cargar la jornada del nuevo (o queda
        // oculto si ya no aplica).
        const _avCoincRec = document.getElementById('aviso_coincidencia_pago');
        if (_avCoincRec) _avCoincRec.style.display = 'none';

        // Cargar jornada en fecha de cesión
        if (empleadoId && fechaCesion) {
            cargarJornadaReceptor(empleadoId, fechaCesion);
        } else {
            ultimaJornadaReceptorCesion = null;
            receptorCesionDescansa = false;
            receptorCesionDoblada = false;
            if (turnoReceptorInfo) {
                turnoReceptorInfo.style.display = 'none';
            }
        }
        
        // Cargar jornada en fecha de pago (si está seleccionada)
        if (empleadoId && fechaPago) {
            estadoReceptorPago = null;
            ultimaJornadaReceptorPago = null;
            sincronizarOpcionesCubrePagoReceptorDoblada();
            cargarJornadaReceptorPago(empleadoId, fechaPago);
        } else {
            ultimaJornadaReceptorPago = null;
            estadoReceptorPago = null;
            sincronizarOpcionesCubrePagoReceptorDoblada();
            if (turnoReceptorPagoInfo) {
                turnoReceptorPagoInfo.style.display = 'none';
            }
        }
        
        // ✅ NUEVA VALIDACIÓN: Si hay fecha de pago sábado, validar que corresponda a la jornada del receptor
        if (empleadoId && fechaPago && esSabado(fechaPago) && fechaCesion) {
            validarSabadoCorrespondeReceptor(fechaPago, empleadoId, fechaCesion);
        }

        // actualizarVistaPrevia: tras cargar jornada cesión (cargarJornadaReceptor) y/o pago (cargarJornadaReceptorPago)
        if (!empleadoId || !fechaCesion) {
            actualizarVistaPrevia();
        }
    });
    
    // Función para verificar si el usuario tiene doblada en una fecha (validación preventiva)
    function verificarDobladaEnFechaPago(fecha, jornada) {
        // El caso "el deudor ya tiene doblada en la fecha de pago" ahora se avisa de forma
        // PERSISTENTE e inline (aviso_deudor_doblada_pago, calculado en cargarJornadaSolicitantePago),
        // en lugar de un popup transitorio. Se conserva la función por compatibilidad de llamadas.
    }
    
    /**
     * Función auxiliar para enviar el formulario
     */
    function enviarFormulario() {
        const formData = new FormData(form);

        // Loading bloqueante: evita doble envío y avisa que se está procesando.
        // Cualquier Swal.fire posterior (éxito/error) reemplaza este modal.
        LoadingUI.mostrar('Enviando solicitud...');

        fetch('/solicitudes/procesar-solicitud/', {
            method: 'POST',
            body: formData,
            headers: {
                'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
            }
        })
        .then(async response => {
            // Intentar parsear el JSON siempre, incluso si response.ok es false
            let data;
            try {
                const text = await response.text();
                if (text) {
                    data = JSON.parse(text);
                } else {
                    data = { success: false, error: `Error ${response.status}: ${response.statusText}` };
                }
            } catch (e) {
                // Si no se puede parsear, crear objeto de error genérico
                data = { 
                    success: false, 
                    error: `Error ${response.status}: ${response.statusText}`,
                    message: `Error ${response.status}: ${response.statusText}`
                };
            }
            
            // Si la respuesta no es OK, lanzar error con los datos parseados
            if (!response.ok) {
                // Caso especial: coincidencia de jornadas en fecha de pago (requiere cambio de turno previo)
                if (data && data.code === 'requiere_cambio_turno_previo') {
                    // No lanzamos error aquí para que el siguiente .then maneje el flujo especial
                    return data;
                }
                // Advertencia (no bloqueo) por restricción médica: dejar que el siguiente .then la maneje
                if (data && data.code === 'advertencia_restriccion') {
                    return data;
                }

                const errorMessage = data.error || data.message || `Error ${response.status}: ${response.statusText}`;
                const errorObj = {
                    ...data,
                    status: response.status,
                    statusText: response.statusText
                };
                throw errorObj;
            }
            
            return data;
        })
        .then(data => {
            // Advertencia (no bloqueo) por restricción médica: avisar y reenviar al confirmar
            if (data.code === 'advertencia_restriccion') {
                if (window.RestriccionAdvertencia) {
                    // RestriccionAdvertencia usa Swal.fire, que reemplaza el modal de carga.
                    RestriccionAdvertencia.mostrar(data.restricciones, function () {
                        LoadingUI.mostrar('Enviando solicitud...');
                        formData.set('confirmar_restriccion', '1');
                        fetch('/solicitudes/procesar-solicitud/', {
                            method: 'POST', body: formData,
                            headers: { 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value }
                        })
                        .then(r => r.json().catch(() => ({})))
                        .then(d2 => {
                            if (d2 && d2.success) {
                                Swal.fire({ icon: 'success', title: '¡Solicitud enviada!', text: d2.message || 'Solicitud enviada correctamente.' })
                                    .then(() => { window.location.href = '/solicitudes/mis-solicitudes/'; });
                            } else {
                                Swal.fire({ icon: 'error', title: 'No se pudo enviar', text: (d2 && (d2.error || d2.message)) || 'Error al procesar la solicitud.' });
                            }
                        })
                        .catch(() => Swal.fire({ icon: 'error', title: 'Error', text: 'Ocurrió un error de red.' }));
                    });
                }
                return;
            }
            // Verificar si requiere cambio de turno previo (caso crítico)
            if (data.code === 'requiere_cambio_turno_previo') {
                const fechaPago = data.fecha_pago || fechaPagoInput.value;
                const jornadaComun = data.jornada_comun || 'la misma jornada';
                const jornadaAfectada = data.jornada_afectada || '';
                
                // Construir mensaje específico si es cesión total
                const mensajeJornada = jornadaAfectada 
                    ? `<li>Problema detectado en la <strong>fecha de pago para ${jornadaAfectada}</strong> (${fechaPago}).</li>`
                    : `<li>En la fecha de pago (${fechaPago}), ambos exploradores tienen ${jornadaComun}.</li>`;
                
                Swal.fire({
                    icon: 'warning',
                    title: 'Cambio de Turno Requerido',
                    html: `
                        <div class="text-left">
                            <p><strong>No se puede realizar la doblada en este momento.</strong></p>
                            <p class="mt-2">${data.message || 'No se puede pagar trabajando dos veces la misma jornada.'}</p>
                            <p class="mt-3"><strong>Razón:</strong></p>
                            <ul class="text-left mt-2">
                                ${mensajeJornada}
                                <li>En la fecha de pago (${fechaPago}), ambos exploradores tienen jornada <strong>${jornadaComun}</strong>.</li>
                                <li>No se puede aplicar la doblada de pago trabajando dos veces la misma jornada.</li>
                            </ul>
                            <p class="mt-3"><strong>Solución:</strong></p>
                            <p class="mt-2">Debes primero realizar un <strong>cambio de turno sencillo</strong> para tener jornada contraria en la fecha de pago.</p>
                        </div>
                    `,
                    showCancelButton: true,
                    confirmButtonText: 'Ir a Cambio de Turno Sencillo',
                    cancelButtonText: 'Cancelar',
                    confirmButtonColor: '#007bff',
                    cancelButtonColor: '#6c757d',
                    width: '600px'
                }).then((result) => {
                    if (result.isConfirmed) {
                        window.location.href = urlCambioTurnoSencillo(fechaPago);
                    }
                });
                return;
            }
            
            // Verificar si el compañero receptor ya tiene doblada en la fecha de cesión
            if (data.code === 'doblada_receptor_existente') {
                Swal.fire({
                    icon: 'error',
                    title: 'Compañero no disponible',
                    html: `
                        <div class="text-left">
                            <p><strong>No se puede crear la solicitud con este compañero.</strong></p>
                            <p class="mt-2">
                                ${data.message || 'El compañero seleccionado ya tiene una doblada (AM+PM) en la fecha de cesión y no puede cubrirte.'}
                            </p>
                            <p class="mt-3"><strong>¿Qué debes hacer?</strong></p>
                            <ul class="text-left mt-2">
                                <li>Mantendremos la fecha de cesión seleccionada.</li>
                                <li>Por favor, elige <strong>otro compañero disponible</strong> para esa fecha.</li>
                            </ul>
                        </div>
                    `,
                    confirmButtonText: 'Entendido',
                    confirmButtonColor: '#d33',
                    width: '600px'
                }).then(() => {
                    // Opcional: deseleccionar al compañero inválido para forzar que el usuario elija otro
                    if (empleadoReceptorSelect) {
                        empleadoReceptorSelect.value = '';
                    }
                });
                return;
            }
            
            // Verificar si es error de doblada existente en fecha de pago
            if (data.code === 'doblada_existente') {
                const fechaConflicto = data.fecha_conflicto || 'desconocida';
                const jornadaAfectada = data.jornada_afectada || '';
                
                Swal.fire({
                    icon: 'error',
                    title: 'Fecha de Pago No Disponible',
                    html: `
                        <div class="text-left">
                            <p><strong>No se puede crear la solicitud</strong></p>
                            <p class="mt-2">${data.message || 'Ya tienes una doblada en la fecha de pago seleccionada.'}</p>
                            <p class="mt-3"><strong>Detalles:</strong></p>
                            <ul class="text-left mt-2">
                                <li>Fecha conflictiva: <strong>${fechaConflicto}</strong></li>
                                <li>Jornada afectada: <strong>${jornadaAfectada}</strong></li>
                                <li>Ya tienes una <strong>doblada (AM + PM)</strong> programada para esta fecha</li>
                            </ul>
                            <p class="mt-3"><strong>Solución:</strong></p>
                            <p class="mt-2">Elige otra fecha de pago que no tenga doblada, o cancela/modifica la doblada existente primero.</p>
                        </div>
                    `,
                    confirmButtonText: 'Entendido',
                    confirmButtonColor: '#d33',
                    width: '600px'
                });
                return;
            }
            
            if (data.success) {
                Swal.fire({
                    icon: 'success',
                    title: 'Solicitud Enviada',
                    text: data.message || 'Tu solicitud de doblada ha sido enviada correctamente.',
                    confirmButtonText: 'OK'
                }).then(() => {
                    window.location.href = '/solicitudes/mis-solicitudes/';
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Error',
                    text: data.message || 'Error al enviar la solicitud'
                });
            }
        })
        .catch(error => {
            console.error('Error enviando solicitud:', error);
            let mensajeError = 'Error al enviar la solicitud. Por favor, intenta nuevamente.';
            
            // Si el error es un objeto (del throw que hicimos arriba)
            if (typeof error === 'object' && error !== null) {
                // Prioridad: error > message > statusText
                mensajeError = error.error || error.message || error.statusText || mensajeError;
                
                // Si tiene código especial, manejarlo
                if (error.code === 'requiere_cambio_turno_previo') {
                    // Este caso ya se maneja arriba, pero por si acaso
                    return;
                }
            } else if (typeof error === 'string') {
                mensajeError = error;
            } else if (error.message) {
                // Intentar parsear si viene como string JSON
                try {
                    const errorData = JSON.parse(error.message);
                    mensajeError = errorData.error || errorData.message || mensajeError;
                } catch (e) {
                    mensajeError = error.message;
                }
            }
            
            Swal.fire({
                icon: 'error',
                title: 'Error',
                text: mensajeError,
                width: '600px'
            });
        });
    }
    
    /**
     * Manejar envío del formulario
     */
    form.addEventListener('submit', function(e) {
        e.preventDefault();

        // VALIDACIÓN PERSONALIZADA PARA DOBLADA (cesión parcial)
        const erroresValidacion = [];
        // Modo INTERCAMBIO de dobladas: no aplican las reglas de "jornada a ceder", pago-sábado,
        // ni "cubre"; el backend valida que ambos tengan doblada. Día A = cesión, día B = pago.
        const _inter = !!(document.getElementById('intercambiar_doblada') &&
                          document.getElementById('intercambiar_doblada').checked);

        // Comentario obligatorio
        const comentariosInput = document.getElementById('comentarios');
        const comentarioValor = comentariosInput ? comentariosInput.value.trim() : '';
        if (!comentarioValor) {
            erroresValidacion.push('El comentario es obligatorio. Explica el motivo de la doblada.');
        }

        // Validar fecha de cesión
        const fechaCesionInput = form.querySelector('#fecha_cesion');
        if (!fechaCesionInput || !fechaCesionInput.value) {
            erroresValidacion.push('Fecha de cesión es requerida');
        }

        // VALIDACIÓN CESIÓN PARCIAL
        if (!empleadoReceptorSelect || !empleadoReceptorSelect.value) {
            erroresValidacion.push('Compañero que te cubrirá es requerido');
        }
        if (!fechaPagoInput || !fechaPagoInput.value) {
            erroresValidacion.push('Fecha de pago es requerida');
        }

        // Ese sábado ya está comprometido por otra doblada mía: no se puede pagar aquí (espejo del guard).
        if (!_inter && sabadoPagoComprometido) {
            erroresValidacion.push('Ese sábado ya está comprometido como pago por otra doblada tuya. Elige otro día de pago.');
        }
        // El deudor ya tiene doblada en la fecha de pago: no le queda jornada libre para pagar ahí.
        if (!_inter && deudorDobladaEnPago) {
            erroresValidacion.push('Ya tienes una doblada (AM + PM) en la fecha de pago; no te queda jornada libre para pagar ahí. Elige otra fecha.');
        }

        // Si la fecha de pago es sábado y se muestra el selector, exigir selección (no en intercambio)
        if (!_inter && fechaPagoInput && fechaPagoInput.value && esSabado(fechaPagoInput.value) &&
            opcionesPagoSabado && opcionesPagoSabado.style.display !== 'none') {
            const jornadaPagoSabadoSel = form.querySelector('input[name="jornada_pago_sabado"]:checked');
            if (!jornadaPagoSabadoSel) {
                erroresValidacion.push('Debes seleccionar qué jornada trabajarás el sábado (AM o PM)');
            }
        }

        const bloqueCubre = document.getElementById('opciones_cubre_pago_receptor_doblada');
        if (!_inter && bloqueCubre && bloqueCubre.style.display !== 'none') {
            const selCubre = form.querySelector('input[name="jornada_cubre_en_pago"]:checked');
            if (!selCubre) {
                erroresValidacion.push('Indica qué jornada (AM o PM) del compañero cubres en la fecha de pago.');
            }
        }

        // Validar jornada a ceder si hay doblada existente (no en modo intercambio).
        // Excepción: festivo (tipo_cesion === 'cesion_completa') cede el día COMPLETO.
        if (!_inter && tieneDobladaExistente && tipoCesionHidden && tipoCesionHidden.value !== 'cesion_completa') {
            const jornadaCedida = form.querySelector('input[name="jornada_cedida"]:checked');
            if (!jornadaCedida) {
                erroresValidacion.push('Debe seleccionar la jornada a ceder (AM o PM)');
            }
        }

        // CASO 7–9: emisor sin turno cedible en fecha de cesión
        const sinJornadaParaCeder = solicitanteCesionTurnoFetchCompleto && !tieneDobladaExistente && !solicitanteCesionEsDoblada &&
            ultimaJornadaSolicitanteCesion !== 'AM' && ultimaJornadaSolicitanteCesion !== 'PM';
        if (sinJornadaParaCeder) {
            erroresValidacion.push('El solicitante no tiene jornada asignada para esa fecha');
        }
        
        // Mostrar errores si hay
        if (erroresValidacion.length > 0) {
            if (window.ValidadoresSolicitudes && window.ValidadoresSolicitudes.mostrarErroresValidacion) {
                window.ValidadoresSolicitudes.mostrarErroresValidacion(erroresValidacion);
            } else {
                // Fallback manual si el validador no está disponible
                Swal.fire({
                    icon: 'warning',
                    title: 'Campos requeridos',
                    html: '<ul style="text-align: left;">' + 
                          erroresValidacion.map(e => `<li>${e}</li>`).join('') + 
                          '</ul>',
                    confirmButtonText: 'Entendido'
                });
            }
            return;
        }
        
        // Bloquear envío si el caso de pago es RECHAZADO (p. ej. 1.2, 1.6 misma jornada, 1.9…)
        if (casoPagoRechazado) {
            const fechaPagoVal = fechaPagoInput && fechaPagoInput.value ? fechaPagoInput.value : '';
            if (casoPagoRequiereRedireccionCT) {
                Swal.fire({
                    icon: 'warning',
                    title: 'Cambio de Turno Requerido',
                    html: `
                        <div class="text-left">
                            <p><strong>No se puede enviar la doblada en este momento.</strong></p>
                            <p class="mt-2">${mensajeRechazoPago || ''}</p>
                            <p class="mt-3"><strong>Solución:</strong> realiza primero un <strong>cambio de turno sencillo</strong> para tener jornada contraria en la fecha de pago.</p>
                        </div>
                    `,
                    showCancelButton: true,
                    confirmButtonText: 'Ir a Cambio de Turno Sencillo',
                    cancelButtonText: 'Cancelar',
                    confirmButtonColor: '#007bff',
                    cancelButtonColor: '#6c757d',
                    width: '600px'
                }).then((result) => {
                    if (result.isConfirmed) {
                        window.location.href = urlCambioTurnoSencillo(fechaPagoVal);
                    }
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'No se puede enviar',
                    text: mensajeRechazoPago || 'No se puede realizar el pago en la fecha seleccionada. Elige otra fecha de pago.'
                });
            }
            return;
        }
        
        // Validación adicional: fecha de pago posterior a fecha de creación
        const fechaPago = fechaPagoInput.value;
        if (fechaPago <= fechaCreacionSolicitud) {
            Swal.fire({
                icon: 'error',
                title: 'Fecha Inválida',
                text: `La fecha de pago debe ser posterior a ${fechaCreacionSolicitud}.`
            });
            return;
        }
        // Validar que fecha de pago no sea igual a fecha de cesión
        const fechaCesionVal = fechaCesionInput ? fechaCesionInput.value : null;
        if (fechaCesionVal && fechaPago === fechaCesionVal) {
            Swal.fire({
                icon: 'error',
                title: 'Fecha Inválida',
                text: `La fecha de pago (${fechaPago}) no puede ser la misma que la fecha de cesión. Si cedes tu jornada ese día, no puedes trabajar y descansar al mismo tiempo.`
            });
            return;
        }
        // Caso A: fecha_pago debe estar en el mismo mes que fecha_cesion
        const mesCesion = fechaCesionInput && fechaCesionInput.value ? fechaCesionInput.value.slice(0, 7) : null;
        if (mesCesion && fechaPago && fechaPago.slice(0, 7) !== mesCesion) {
            Swal.fire({
                icon: 'error',
                title: 'Fecha de pago inválida',
                text: `La fecha de pago (${fechaPago}) debe estar en el mismo mes que la fecha de cesión. Ambas deben pertenecer al mes ${mesCesion}.`
            });
            return;
        }
        
        // Validación frontend de días especiales (domingo y mantenimiento bloqueados; festivos permitidos con regla mismo mes)
        const fechaCesion = fechaCesionInput.value;
        const erroresDiasEspeciales = [];
        
        if (fechaCesion) {
            if (esDomingo(fechaCesion)) {
                erroresDiasEspeciales.push(`La fecha de cesión (${formatearFecha(fechaCesion)}) no puede ser domingo.`);
            }
            
            if (window.DatepickerFestivos) {
                Promise.all([
                    window.DatepickerFestivos.cargarDiasFestivos(),
                    window.DatepickerFestivos.cargarDiasMantenimiento()
                ]).then(([festivosMap, mantenimientoMap]) => {
                    // Mantenimiento nunca permitido
                    if (mantenimientoMap.has(fechaCesion)) {
                        erroresDiasEspeciales.push(`La fecha de cesión (${formatearFecha(fechaCesion)}) es un día de mantenimiento: ${mantenimientoMap.get(fechaCesion)}.`);
                    }
                    
                    const cesionEsFestivo = festivosMap.has(fechaCesion);
                    const mesCesion = fechaCesion ? fechaCesion.slice(0, 7) : ''; // YYYY-MM
                    
                    const fechaPagoVal = fechaPagoInput.value;
                    if (fechaPagoVal) {
                        if (esDomingo(fechaPagoVal)) {
                            erroresDiasEspeciales.push(`La fecha de pago (${formatearFecha(fechaPagoVal)}) no puede ser domingo.`);
                        }
                        if (mantenimientoMap.has(fechaPagoVal)) {
                            erroresDiasEspeciales.push(`La fecha de pago (${formatearFecha(fechaPagoVal)}) es un día de mantenimiento: ${mantenimientoMap.get(fechaPagoVal)}.`);
                        }
                        const pagoEsFestivo = festivosMap.has(fechaPagoVal);
                        if (cesionEsFestivo && !pagoEsFestivo) {
                            erroresDiasEspeciales.push(`La cesión es en día festivo. La fecha de pago también debe ser un festivo del mismo mes (${new Date(fechaCesion + 'T00:00:00').toLocaleString('es-CO', {month: 'long'})}).`);
                        } else if (pagoEsFestivo && !cesionEsFestivo) {
                            erroresDiasEspeciales.push('La fecha de pago es un festivo. La fecha de cesión también debe ser un festivo del mismo mes.');
                        } else if (cesionEsFestivo && pagoEsFestivo && fechaPagoVal.slice(0, 7) !== mesCesion) {
                            erroresDiasEspeciales.push('Cesión y pago en festivos deben ser del mismo mes.');
                        }
                    }
                    
                    if (erroresDiasEspeciales.length > 0) {
                        Swal.fire({
                            icon: 'error',
                            title: 'Fechas Inválidas',
                            html: `<p>No se puede realizar la doblada:</p><ul class="text-left mt-2">${erroresDiasEspeciales.map(e => `<li>${e}</li>`).join('')}</ul>`,
                            confirmButtonText: 'OK'
                        });
                        return;
                    }
                    
                    enviarFormulario();
                }).catch(error => {
                    console.error('Error validando días especiales:', error);
                    enviarFormulario();
                });
            } else {
                enviarFormulario();
            }
        } else {
            enviarFormulario();
        }
    });

    // Inicializar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            inicializarDatepickerCesion();
            inicializarDatepickerPago();
        });
    } else {
        inicializarDatepickerCesion();
        inicializarDatepickerPago();
    }
})();
