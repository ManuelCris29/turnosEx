/**
 * Utilidades para manejo de fechas
 * 
 * Proporciona funciones reutilizables para trabajar con fechas,
 * validaciones y transformaciones.
 * 
 * @module utils/date-utils
 */

/**
 * Utilidades para fechas
 */
class DateUtils {
  /**
   * Verifica si una fecha es domingo
   * @param {string|Date} date - Fecha a verificar (YYYY-MM-DD o Date)
   * @returns {boolean} true si es domingo
   */
  static isSunday(date) {
    const dateObj = typeof date === 'string' 
      ? new Date(`${date}T00:00:00`) 
      : date;
    return dateObj.getDay() === 0;
  }

  /**
   * Verifica si una fecha es sábado
   * @param {string|Date} date - Fecha a verificar (YYYY-MM-DD o Date)
   * @returns {boolean} true si es sábado
   */
  static isSaturday(date) {
    const dateObj = typeof date === 'string' 
      ? new Date(`${date}T00:00:00`) 
      : date;
    return dateObj.getDay() === 6;
  }

  /**
   * Verifica si una fecha es fin de semana
   * @param {string|Date} date - Fecha a verificar
   * @returns {boolean} true si es sábado o domingo
   */
  static isWeekend(date) {
    return this.isSaturday(date) || this.isSunday(date);
  }

  /**
   * Obtiene el nombre del día de la semana
   * @param {string|Date} date - Fecha
   * @param {string} locale - Locale (default: 'es-ES')
   * @returns {string} Nombre del día
   */
  static getDayName(date, locale = 'es-ES') {
    const dateObj = typeof date === 'string' 
      ? new Date(`${date}T00:00:00`) 
      : date;
    return dateObj.toLocaleDateString(locale, { weekday: 'long' });
  }

  /**
   * Formatea una fecha a formato español
   * @param {string|Date} date - Fecha a formatear
   * @param {Object} options - Opciones de formato
   * @returns {string} Fecha formateada
   */
  static formatDate(date, options = {}) {
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    const defaultOptions = {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      ...options,
    };
    return dateObj.toLocaleDateString('es-ES', defaultOptions);
  }

  /**
   * Obtiene la fecha de hoy en formato YYYY-MM-DD
   * @returns {string} Fecha de hoy
   */
  static getToday() {
    return new Date().toISOString().split('T')[0];
  }

  /**
   * Compara dos fechas
   * @param {string|Date} date1 - Primera fecha
   * @param {string|Date} date2 - Segunda fecha
   * @returns {number} -1 si date1 < date2, 0 si son iguales, 1 si date1 > date2
   */
  static compareDates(date1, date2) {
    const d1 = typeof date1 === 'string' ? new Date(date1) : date1;
    const d2 = typeof date2 === 'string' ? new Date(date2) : date2;
    
    d1.setHours(0, 0, 0, 0);
    d2.setHours(0, 0, 0, 0);
    
    if (d1 < d2) return -1;
    if (d1 > d2) return 1;
    return 0;
  }

  /**
   * Verifica si una fecha es pasada
   * @param {string|Date} date - Fecha a verificar
   * @returns {boolean} true si la fecha es pasada
   */
  static isPastDate(date) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    dateObj.setHours(0, 0, 0, 0);
    
    return dateObj < today;
  }

  /**
   * Verifica si una fecha es futura
   * @param {string|Date} date - Fecha a verificar
   * @returns {boolean} true si la fecha es futura
   */
  static isFutureDate(date) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    dateObj.setHours(0, 0, 0, 0);
    
    return dateObj > today;
  }

  /**
   * Agrega días a una fecha
   * @param {string|Date} date - Fecha base
   * @param {number} days - Número de días a agregar
   * @returns {Date} Nueva fecha
   */
  static addDays(date, days) {
    const dateObj = typeof date === 'string' ? new Date(date) : date;
    dateObj.setDate(dateObj.getDate() + days);
    return dateObj;
  }

  /**
   * Obtiene el rango de fechas para un mes
   * @param {number} year - Año
   * @param {number} month - Mes (1-12)
   * @returns {Object} Objeto con fechaInicio y fechaFin
   */
  static getMonthRange(year, month) {
    const fechaInicio = new Date(year, month - 1, 1);
    const fechaFin = new Date(year, month, 0);
    
    return {
      fechaInicio: fechaInicio.toISOString().split('T')[0],
      fechaFin: fechaFin.toISOString().split('T')[0],
    };
  }
}

// Exportar para uso en módulos ES6
if (typeof module !== 'undefined' && module.exports) {
  module.exports = DateUtils;
}

// Exportar para uso global
window.DateUtils = DateUtils;

