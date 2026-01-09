/**
 * Validador genérico para formularios de solicitudes de cambio de turno
 * 
 * Este módulo proporciona funciones reutilizables para validar campos requeridos
 * antes de enviar solicitudes, manteniendo consistencia en toda la aplicación.
 */

/**
 * Reglas de validación por tipo de solicitud
 */
const REGLAS_VALIDACION = {
    'CT': {
        campos: [
            { id: 'tipo_solicitud_id', nombre: 'Tipo de solicitud', requerido: true },
            { id: 'empleado_receptor', nombre: 'Compañero para intercambiar', requerido: true },
            { id: 'fecha_solicitud', nombre: 'Fecha del cambio', requerido: true }
        ],
        validacionesPersonalizadas: []
    },
    'CT PERMANENTE': {
        campos: [
            { id: 'tipo_solicitud_id', nombre: 'Tipo de solicitud', requerido: true },
            { id: 'empleado_receptor', nombre: 'Compañero para intercambiar', requerido: true },
            { id: 'fecha_inicio', nombre: 'Fecha de inicio', requerido: true },
            { id: 'fecha_fin', nombre: 'Fecha de fin', requerido: true },
            { id: 'dias_seleccionados', nombre: 'Días seleccionados', requerido: true, tipo: 'json' }
        ],
        validacionesPersonalizadas: [
            {
                nombre: 'fecha_fin_posterior',
                validar: (form) => {
                    const fechaInicio = form.querySelector('#fecha_inicio')?.value;
                    const fechaFin = form.querySelector('#fecha_fin')?.value;
                    if (fechaInicio && fechaFin && fechaFin <= fechaInicio) {
                        return 'La fecha de fin debe ser posterior a la fecha de inicio';
                    }
                    return null;
                }
            },
            {
                nombre: 'dias_seleccionados_validos',
                validar: (form) => {
                    const diasHidden = form.querySelector('#dias_seleccionados');
                    if (!diasHidden || !diasHidden.value) {
                        return 'Debe seleccionar al menos un día de la semana (lunes a viernes)';
                    }
                    try {
                        const dias = JSON.parse(diasHidden.value);
                        const tieneDiasSemana = dias.dias_semana && dias.dias_semana.length > 0;
                        const tieneFechasEspecificas = dias.fechas_especificas && dias.fechas_especificas.length > 0;
                        if (!tieneDiasSemana && !tieneFechasEspecificas) {
                            return 'Debe seleccionar al menos un día de la semana (lunes a viernes)';
                        }
                    } catch (e) {
                        return 'Error al procesar los días seleccionados';
                    }
                    return null;
                }
            }
        ]
    },
    'DOBLADA': {
        campos: [
            { id: 'tipo_solicitud_id', nombre: 'Tipo de solicitud', requerido: true },
            { id: 'fecha_solicitud', nombre: 'Fecha de la doblada', requerido: true }
        ],
        validacionesPersonalizadas: [
            {
                nombre: 'fecha_no_pasado',
                validar: (form) => {
                    const fechaInput = form.querySelector('#fecha_solicitud')?.value;
                    if (!fechaInput) return null;
                    try {
                        const fecha = new Date(fechaInput);
                        const hoy = new Date();
                        hoy.setHours(0, 0, 0, 0);
                        fecha.setHours(0, 0, 0, 0);
                        if (fecha < hoy) {
                            return 'No se pueden solicitar dobladas para fechas pasadas';
                        }
                    } catch (e) {
                        return 'Fecha inválida';
                    }
                    return null;
                }
            }
        ]
    },
    'DOBLADA': {
        campos: [
            { id: 'tipo_solicitud_id', nombre: 'Tipo de solicitud', requerido: true },
            { id: 'fecha_cesion', nombre: 'Fecha de cesión', requerido: true, alias: 'fecha_solicitud' },
            { id: 'empleado_receptor', nombre: 'Compañero que te cubrirá', requerido: true },
            { id: 'fecha_pago', nombre: 'Fecha de pago', requerido: true }
        ],
        validacionesPersonalizadas: [
            {
                nombre: 'fecha_pago_posterior_creacion',
                validar: (form) => {
                    const fechaPagoInput = form.querySelector('#fecha_pago');
                    if (!fechaPagoInput || !fechaPagoInput.value) return null;
                    
                    try {
                        const fechaPago = new Date(fechaPagoInput.value + 'T00:00:00');
                        const hoy = new Date();
                        hoy.setHours(0, 0, 0, 0);
                        fechaPago.setHours(0, 0, 0, 0);
                        
                        if (fechaPago <= hoy) {
                            return 'La fecha de pago debe ser posterior a la fecha de creación de la solicitud';
                        }
                    } catch (e) {
                        return 'Fecha de pago inválida';
                    }
                    return null;
                }
            },
            {
                nombre: 'jornada_cedida_requerida_si_doblada',
                validar: (form) => {
                    const dobladaExistenteInfo = form.querySelector('#doblada_existente_info');
                    if (dobladaExistenteInfo && dobladaExistenteInfo.style.display !== 'none') {
                        const jornadaCedida = form.querySelector('input[name="jornada_cedida"]:checked');
                        if (!jornadaCedida) {
                            return 'Debe seleccionar la jornada a ceder (AM o PM)';
                        }
                    }
                    return null;
                }
            }
        ]
    },
    'D FDS': {
        campos: [
            { id: 'tipo_solicitud_id', nombre: 'Tipo de solicitud', requerido: true },
            { id: 'fecha_solicitud', nombre: 'Fecha (fin de semana)', requerido: true }
        ],
        validacionesPersonalizadas: [
            {
                nombre: 'fecha_fin_de_semana',
                validar: (form) => {
                    const fechaInput = form.querySelector('#fecha_solicitud')?.value;
                    if (!fechaInput) return null;
                    try {
                        const fecha = new Date(fechaInput);
                        const diaSemana = fecha.getDay(); // 0=domingo, 6=sábado
                        if (diaSemana !== 0 && diaSemana !== 6) {
                            return 'D FDS solo se puede solicitar para fines de semana (sábado o domingo)';
                        }
                    } catch (e) {
                        return 'Fecha inválida';
                    }
                    return null;
                }
            },
            {
                nombre: 'fecha_no_pasado',
                validar: (form) => {
                    const fechaInput = form.querySelector('#fecha_solicitud')?.value;
                    if (!fechaInput) return null;
                    try {
                        const fecha = new Date(fechaInput);
                        const hoy = new Date();
                        hoy.setHours(0, 0, 0, 0);
                        fecha.setHours(0, 0, 0, 0);
                        if (fecha < hoy) {
                            return 'No se pueden solicitar dobladas para fechas pasadas';
                        }
                    } catch (e) {
                        return 'Fecha inválida';
                    }
                    return null;
                }
            }
        ]
    }
};

/**
 * Valida un campo individual según sus reglas
 * @param {HTMLElement} campo - Elemento del formulario
 * @param {Object} regla - Regla de validación del campo
 * @returns {Object|null} - Objeto con error o null si es válido
 */
function validarCampo(campo, regla) {
    // Si no hay campo pero tiene alias, intentar buscar por alias
    if (!campo && regla.alias) {
        campo = document.getElementById(regla.alias);
    }
    
    if (!campo && regla.requerido) {
        return {
            campo: regla.nombre,
            mensaje: `${regla.nombre} es requerido`
        };
    }

    if (!regla.requerido) {
        return null; // Campo opcional, no validar si está vacío
    }

    const valor = campo ? (campo.value ? campo.value.trim() : '') : '';
    
    if (!valor) {
        return {
            campo: regla.nombre,
            mensaje: `${regla.nombre} es requerido`
        };
    }

    // Validación especial para campos JSON
    if (regla.tipo === 'json') {
        try {
            JSON.parse(valor);
        } catch (e) {
            return {
                campo: regla.nombre,
                mensaje: `${regla.nombre} tiene un formato inválido`
            };
        }
    }

    return null;
}

/**
 * Marca visualmente un campo con error
 * @param {HTMLElement} campo - Elemento del formulario
 * @param {string} mensaje - Mensaje de error
 */
function marcarCampoConError(campo, mensaje) {
    if (!campo) return;
    
    campo.classList.add('is-invalid');
    
    // Remover mensaje de error anterior si existe
    const errorAnterior = campo.parentElement.querySelector('.invalid-feedback');
    if (errorAnterior) {
        errorAnterior.remove();
    }
    
    // Agregar mensaje de error
    const errorDiv = document.createElement('div');
    errorDiv.className = 'invalid-feedback';
    errorDiv.textContent = mensaje;
    campo.parentElement.appendChild(errorDiv);
}

/**
 * Limpia los errores visuales de un campo
 * @param {HTMLElement} campo - Elemento del formulario
 */
function limpiarErrorCampo(campo) {
    if (!campo) return;
    campo.classList.remove('is-invalid');
    const errorDiv = campo.parentElement.querySelector('.invalid-feedback');
    if (errorDiv) {
        errorDiv.remove();
    }
}

/**
 * Valida un formulario completo según el tipo de solicitud
 * @param {HTMLElement} form - Formulario a validar
 * @param {string} tipoSolicitud - Tipo de solicitud ('CT', 'CT PERMANENTE', 'DOBLADA', 'D FDS')
 * @returns {Object} - { valido: boolean, errores: Array }
 */
function validarFormularioSolicitud(form, tipoSolicitud) {
    if (!form) {
        return {
            valido: false,
            errores: ['Formulario no encontrado']
        };
    }

    const reglas = REGLAS_VALIDACION[tipoSolicitud];
    if (!reglas) {
        console.warn(`No hay reglas de validación para el tipo: ${tipoSolicitud}`);
        return {
            valido: true,
            errores: []
        };
    }

    const errores = [];
    
    // Limpiar errores previos
    reglas.campos.forEach(regla => {
        // Buscar campo por ID, o por alias si existe
        let campo = form.querySelector(`#${regla.id}`);
        if (!campo && regla.alias) {
            campo = form.querySelector(`#${regla.alias}`);
        }
        if (campo) {
            limpiarErrorCampo(campo);
        }
    });

    // Validar campos requeridos
    reglas.campos.forEach(regla => {
        // Buscar campo por ID, o por alias si existe
        let campo = form.querySelector(`#${regla.id}`);
        if (!campo && regla.alias) {
            campo = form.querySelector(`#${regla.alias}`);
        }
        
        const error = validarCampo(campo, regla);
        if (error) {
            errores.push(error);
            if (campo) {
                marcarCampoConError(campo, error.mensaje);
            }
        }
    });

    // Validaciones personalizadas
    reglas.validacionesPersonalizadas.forEach(validacion => {
        const error = validacion.validar(form);
        if (error) {
            errores.push({
                campo: validacion.nombre,
                mensaje: error
            });
        }
    });

    return {
        valido: errores.length === 0,
        errores: errores
    };
}

/**
 * Muestra errores de validación usando SweetAlert2
 * @param {Array} errores - Array de objetos { campo, mensaje }
 */
function mostrarErroresValidacion(errores) {
    if (!errores || errores.length === 0) return;

    const mensajes = errores.map(e => `• ${e.mensaje}`).join('\n');
    
    Swal.fire({
        icon: 'warning',
        title: 'Campos requeridos',
        html: `<div style="text-align: left;">${mensajes.replace(/\n/g, '<br>')}</div>`,
        confirmButtonText: 'Entendido'
    });
}

/**
 * Obtiene el tipo de solicitud desde el formulario
 * @param {HTMLElement} form - Formulario
 * @returns {string|null} - Tipo de solicitud o null
 */
function obtenerTipoSolicitud(form) {
    const tipoInput = form.querySelector('#tipo_solicitud_id');
    if (!tipoInput || !tipoInput.value) return null;
    
    // Intentar obtener el nombre del tipo desde el contexto o un elemento oculto
    const tipoNombreElement = form.querySelector('[data-tipo-nombre]');
    if (tipoNombreElement) {
        return tipoNombreElement.getAttribute('data-tipo-nombre');
    }
    
    // Fallback: usar el valor del input si contiene el nombre
    return tipoInput.value;
}

// Exportar funciones para uso global
window.ValidadoresSolicitudes = {
    validarFormularioSolicitud,
    mostrarErroresValidacion,
    obtenerTipoSolicitud,
    REGLAS_VALIDACION,
    marcarCampoConError,
    limpiarErrorCampo
};

