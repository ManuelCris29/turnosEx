/**
 * Aplicación principal - Punto de entrada y configuración global
 * 
 * Inicializa la aplicación y proporciona configuración global,
 * manejo de errores y utilidades compartidas.
 * 
 * @module core/app
 * 
 * NOTA: Este módulo requiere que los siguientes módulos estén cargados:
 * - DomUtils (utils/dom-utils.js)
 */

/**
 * Aplicación principal
 */
class App {
  constructor() {
    this.config = {
      apiBaseUrl: '',
      debug: window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1',
    };

    this.init();
  }

  /**
   * Inicializa la aplicación
   */
  init() {
    // Configurar manejo global de errores
    this.setupErrorHandling();

    // Configurar CSRF token para todas las peticiones
    this.setupCSRF();

    // Log de inicialización en modo debug
    if (this.config.debug) {
    }
  }

  /**
   * Configura el manejo global de errores
   */
  setupErrorHandling() {
    window.addEventListener('error', (event) => {
      console.error('[App] Error global:', event.error);
      // Aquí se puede agregar logging a un servicio externo
    });

    window.addEventListener('unhandledrejection', (event) => {
      console.error('[App] Promise rechazada sin manejar:', event.reason);
      // Aquí se puede agregar logging a un servicio externo
    });
  }

  /**
   * Configura CSRF token
   */
  setupCSRF() {
    // El token CSRF se obtiene automáticamente en ApiClient
    // Esta función puede usarse para configuraciones adicionales
  }

  /**
   * Muestra un mensaje de error al usuario
   * @param {string} message - Mensaje de error
   * @param {string} title - Título del error
   */
  static showError(message, title = 'Error') {
    if (typeof Swal !== 'undefined') {
      Swal.fire({
        icon: 'error',
        title,
        text: message,
        confirmButtonText: 'Aceptar',
      });
    } else {
      alert(`${title}: ${message}`);
    }
  }

  /**
   * Muestra un mensaje de éxito
   * @param {string} message - Mensaje de éxito
   * @param {string} title - Título
   */
  static showSuccess(message, title = 'Éxito') {
    if (typeof Swal !== 'undefined') {
      Swal.fire({
        icon: 'success',
        title,
        text: message,
        confirmButtonText: 'Aceptar',
        timer: 3000,
        timerProgressBar: true,
      });
    } else {
      alert(`${title}: ${message}`);
    }
  }

  /**
   * Muestra un mensaje de confirmación
   * @param {string} message - Mensaje
   * @param {string} title - Título
   * @returns {Promise<boolean>} true si se confirma
   */
  static async confirm(message, title = 'Confirmar') {
    if (typeof Swal !== 'undefined') {
      const result = await Swal.fire({
        icon: 'question',
        title,
        text: message,
        showCancelButton: true,
        confirmButtonText: 'Sí',
        cancelButtonText: 'No',
      });
      return result.isConfirmed;
    }
    return confirm(`${title}: ${message}`);
  }
}

// Inicializar aplicación cuando el DOM esté listo
// Usar DomUtils si está disponible, sino usar método nativo
if (typeof DomUtils !== 'undefined') {
  DomUtils.ready(() => {
    window.app = new App();
  });
} else {
  // Fallback si DomUtils no está cargado
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      window.app = new App();
    });
  } else {
    window.app = new App();
  }
}

// Exportar para uso en módulos ES6
if (typeof module !== 'undefined' && module.exports) {
  module.exports = App;
}

// Exportar para uso global
window.App = App;

