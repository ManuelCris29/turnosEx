/**
 * Validadores reutilizables para formularios
 * 
 * Proporciona funciones de validación comunes para formularios,
 * con mensajes de error personalizables.
 * 
 * @module utils/validators
 */

/**
 * Validadores comunes
 */
class Validators {
  /**
   * Valida que un campo no esté vacío
   * @param {string} value - Valor a validar
   * @param {string} fieldName - Nombre del campo (para mensaje de error)
   * @returns {Object} { valid: boolean, message: string }
   */
  static required(value, fieldName = 'Este campo') {
    const trimmed = typeof value === 'string' ? value.trim() : value;
    return {
      valid: trimmed !== '' && trimmed != null,
      message: `${fieldName} es requerido`,
    };
  }

  /**
   * Valida formato de email
   * @param {string} email - Email a validar
   * @returns {Object} { valid: boolean, message: string }
   */
  static email(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return {
      valid: emailRegex.test(email),
      message: 'El email no es válido',
    };
  }

  /**
   * Valida que una fecha sea futura
   * @param {string} date - Fecha a validar (YYYY-MM-DD)
   * @returns {Object} { valid: boolean, message: string }
   */
  static futureDate(date) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const dateObj = new Date(date);
    dateObj.setHours(0, 0, 0, 0);
    
    return {
      valid: dateObj >= today,
      message: 'La fecha debe ser hoy o una fecha futura',
    };
  }

  /**
   * Valida que una fecha sea pasada
   * @param {string} date - Fecha a validar (YYYY-MM-DD)
   * @returns {Object} { valid: boolean, message: string }
   */
  static pastDate(date) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const dateObj = new Date(date);
    dateObj.setHours(0, 0, 0, 0);
    
    return {
      valid: dateObj < today,
      message: 'La fecha debe ser una fecha pasada',
    };
  }

  /**
   * Valida que fecha2 sea posterior a fecha1
   * @param {string} date1 - Primera fecha
   * @param {string} date2 - Segunda fecha
   * @param {string} fieldName - Nombre del campo (para mensaje)
   * @returns {Object} { valid: boolean, message: string }
   */
  static dateAfter(date1, date2, fieldName = 'La fecha de fin') {
    const d1 = new Date(date1);
    const d2 = new Date(date2);
    
    d1.setHours(0, 0, 0, 0);
    d2.setHours(0, 0, 0, 0);
    
    return {
      valid: d2 > d1,
      message: `${fieldName} debe ser posterior a la fecha de inicio`,
    };
  }

  /**
   * Valida longitud mínima
   * @param {string} value - Valor a validar
   * @param {number} minLength - Longitud mínima
   * @param {string} fieldName - Nombre del campo
   * @returns {Object} { valid: boolean, message: string }
   */
  static minLength(value, minLength, fieldName = 'Este campo') {
    return {
      valid: value.length >= minLength,
      message: `${fieldName} debe tener al menos ${minLength} caracteres`,
    };
  }

  /**
   * Valida longitud máxima
   * @param {string} value - Valor a validar
   * @param {number} maxLength - Longitud máxima
   * @param {string} fieldName - Nombre del campo
   * @returns {Object} { valid: boolean, message: string }
   */
  static maxLength(value, maxLength, fieldName = 'Este campo') {
    return {
      valid: value.length <= maxLength,
      message: `${fieldName} no puede tener más de ${maxLength} caracteres`,
    };
  }

  /**
   * Valida un número
   * @param {string|number} value - Valor a validar
   * @returns {Object} { valid: boolean, message: string }
   */
  static number(value) {
    return {
      valid: !isNaN(value) && !isNaN(parseFloat(value)),
      message: 'Debe ser un número válido',
    };
  }

  /**
   * Valida un número positivo
   * @param {string|number} value - Valor a validar
   * @returns {Object} { valid: boolean, message: string }
   */
  static positiveNumber(value) {
    const num = parseFloat(value);
    return {
      valid: !isNaN(num) && num > 0,
      message: 'Debe ser un número positivo',
    };
  }

  /**
   * Valida que un valor esté en un rango
   * @param {number} value - Valor a validar
   * @param {number} min - Valor mínimo
   * @param {number} max - Valor máximo
   * @returns {Object} { valid: boolean, message: string }
   */
  static range(value, min, max) {
    const num = parseFloat(value);
    return {
      valid: !isNaN(num) && num >= min && num <= max,
      message: `El valor debe estar entre ${min} y ${max}`,
    };
  }

  /**
   * Valida múltiples reglas
   * @param {string} value - Valor a validar
   * @param {Array<Function>} rules - Array de funciones de validación
   * @returns {Object} { valid: boolean, message: string }
   */
  static validate(value, rules) {
    for (const rule of rules) {
      const result = rule(value);
      if (!result.valid) {
        return result;
      }
    }
    return { valid: true, message: '' };
  }
}

// Exportar para uso en módulos ES6
if (typeof module !== 'undefined' && module.exports) {
  module.exports = Validators;
}

// Exportar para uso global
window.Validators = Validators;

