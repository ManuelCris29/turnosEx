/**
 * API Client - Cliente HTTP reutilizable para todas las peticiones AJAX
 * 
 * Proporciona métodos centralizados para realizar peticiones HTTP con manejo
 * de errores, autenticación y transformación de datos.
 * 
 * @module utils/api-client
 */

/**
 * Clase para manejar peticiones HTTP de forma centralizada
 */
class ApiClient {
  /**
   * Realiza una petición GET
   * @param {string} url - URL del endpoint
   * @param {Object} params - Parámetros de query string
   * @returns {Promise<any>} Respuesta parseada como JSON
   */
  static async get(url, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const fullUrl = queryString ? `${url}?${queryString}` : url;

    try {
      const response = await fetch(fullUrl, {
        method: 'GET',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Content-Type': 'application/json',
        },
        credentials: 'same-origin',
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Error en GET ${url}:`, error);
      throw error;
    }
  }

  /**
   * Realiza una petición POST
   * @param {string} url - URL del endpoint
   * @param {Object} data - Datos a enviar
   * @returns {Promise<any>} Respuesta parseada como JSON
   */
  static async post(url, data = {}) {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Content-Type': 'application/json',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'same-origin',
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Error en POST ${url}:`, error);
      throw error;
    }
  }

  /**
   * Realiza una petición PUT
   * @param {string} url - URL del endpoint
   * @param {Object} data - Datos a enviar
   * @returns {Promise<any>} Respuesta parseada como JSON
   */
  static async put(url, data = {}) {
    try {
      const response = await fetch(url, {
        method: 'PUT',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'Content-Type': 'application/json',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'same-origin',
        body: JSON.stringify(data),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Error en PUT ${url}:`, error);
      throw error;
    }
  }

  /**
   * Realiza una petición DELETE
   * @param {string} url - URL del endpoint
   * @returns {Promise<any>} Respuesta parseada como JSON
   */
  static async delete(url) {
    try {
      const response = await fetch(url, {
        method: 'DELETE',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
          'X-CSRFToken': this.getCsrfToken(),
        },
        credentials: 'same-origin',
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`[ApiClient] Error en DELETE ${url}:`, error);
      throw error;
    }
  }

  /**
   * Obtiene el token CSRF de Django
   * @returns {string} Token CSRF
   */
  static getCsrfToken() {
    const cookieValue = document.cookie
      .split('; ')
      .find(row => row.startsWith('csrftoken='))
      ?.split('=')[1];

    if (!cookieValue) {
      const csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
      return csrfInput?.value || '';
    }

    return cookieValue;
  }

  /**
   * Maneja errores de forma consistente
   * @param {Error} error - Error capturado
   * @param {string} context - Contexto donde ocurrió el error
   * @returns {Object} Objeto con información del error
   */
  static handleError(error, context = '') {
    const errorMessage = error.message || 'Error desconocido';
    console.error(`[ApiClient] Error en ${context}:`, error);

    return {
      success: false,
      error: errorMessage,
      context,
    };
  }
}

// Exportar para uso en módulos ES6
if (typeof module !== 'undefined' && module.exports) {
  module.exports = ApiClient;
}

// Exportar para uso global
window.ApiClient = ApiClient;

