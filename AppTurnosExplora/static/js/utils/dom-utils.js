/**
 * Utilidades para manipulación del DOM
 * 
 * Proporciona funciones reutilizables para trabajar con elementos DOM,
 * eventos y manipulación de clases/atributos.
 * 
 * @module utils/dom-utils
 */

/**
 * Utilidades para DOM
 */
class DomUtils {
  /**
   * Obtiene un elemento del DOM de forma segura
   * @param {string} selector - Selector CSS
   * @param {HTMLElement} context - Contexto donde buscar (default: document)
   * @returns {HTMLElement|null} Elemento encontrado o null
   */
  static $(selector, context = document) {
    return context.querySelector(selector);
  }

  /**
   * Obtiene múltiples elementos del DOM
   * @param {string} selector - Selector CSS
   * @param {HTMLElement} context - Contexto donde buscar
   * @returns {NodeList} Lista de elementos
   */
  static $$(selector, context = document) {
    return context.querySelectorAll(selector);
  }

  /**
   * Espera a que el DOM esté listo
   * @param {Function} callback - Función a ejecutar
   */
  static ready(callback) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', callback);
    } else {
      callback();
    }
  }

  /**
   * Agrega una clase a un elemento
   * @param {HTMLElement} element - Elemento
   * @param {string} className - Nombre de la clase
   */
  static addClass(element, className) {
    if (element) {
      element.classList.add(className);
    }
  }

  /**
   * Remueve una clase de un elemento
   * @param {HTMLElement} element - Elemento
   * @param {string} className - Nombre de la clase
   */
  static removeClass(element, className) {
    if (element) {
      element.classList.remove(className);
    }
  }

  /**
   * Toggle de una clase
   * @param {HTMLElement} element - Elemento
   * @param {string} className - Nombre de la clase
   * @returns {boolean} true si la clase fue agregada
   */
  static toggleClass(element, className) {
    if (element) {
      return element.classList.toggle(className);
    }
    return false;
  }

  /**
   * Verifica si un elemento tiene una clase
   * @param {HTMLElement} element - Elemento
   * @param {string} className - Nombre de la clase
   * @returns {boolean} true si tiene la clase
   */
  static hasClass(element, className) {
    return element?.classList.contains(className) || false;
  }

  /**
   * Muestra un elemento
   * @param {HTMLElement} element - Elemento
   */
  static show(element) {
    if (element) {
      element.style.display = '';
    }
  }

  /**
   * Oculta un elemento
   * @param {HTMLElement} element - Elemento
   */
  static hide(element) {
    if (element) {
      element.style.display = 'none';
    }
  }

  /**
   * Toggle de visibilidad
   * @param {HTMLElement} element - Elemento
   */
  static toggle(element) {
    if (element) {
      element.style.display = element.style.display === 'none' ? '' : 'none';
    }
  }

  /**
   * Crea un elemento HTML
   * @param {string} tag - Tag HTML
   * @param {Object} attributes - Atributos del elemento
   * @param {string|HTMLElement} content - Contenido (texto o elemento)
   * @returns {HTMLElement} Elemento creado
   */
  static createElement(tag, attributes = {}, content = '') {
    const element = document.createElement(tag);
    
    Object.entries(attributes).forEach(([key, value]) => {
      if (key === 'className') {
        element.className = value;
      } else if (key === 'textContent') {
        element.textContent = value;
      } else {
        element.setAttribute(key, value);
      }
    });

    if (content) {
      if (typeof content === 'string') {
        element.textContent = content;
      } else {
        element.appendChild(content);
      }
    }

    return element;
  }

  /**
   * Limpia el contenido de un elemento
   * @param {HTMLElement} element - Elemento
   */
  static clear(element) {
    if (element) {
      element.innerHTML = '';
    }
  }

  /**
   * Agrega un event listener de forma segura
   * @param {HTMLElement} element - Elemento
   * @param {string} event - Nombre del evento
   * @param {Function} handler - Manejador del evento
   * @param {Object} options - Opciones del evento
   */
  static on(element, event, handler, options = {}) {
    if (element) {
      element.addEventListener(event, handler, options);
    }
  }

  /**
   * Remueve un event listener
   * @param {HTMLElement} element - Elemento
   * @param {string} event - Nombre del evento
   * @param {Function} handler - Manejador del evento
   */
  static off(element, event, handler) {
    if (element) {
      element.removeEventListener(event, handler);
    }
  }

  /**
   * Debounce de una función
   * @param {Function} func - Función a debounce
   * @param {number} wait - Tiempo de espera en ms
   * @returns {Function} Función con debounce
   */
  static debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }

  /**
   * Throttle de una función
   * @param {Function} func - Función a throttle
   * @param {number} limit - Límite de tiempo en ms
   * @returns {Function} Función con throttle
   */
  static throttle(func, limit) {
    let inThrottle;
    return function executedFunction(...args) {
      if (!inThrottle) {
        func(...args);
        inThrottle = true;
        setTimeout(() => (inThrottle = false), limit);
      }
    };
  }
}

// Exportar para uso en módulos ES6
if (typeof module !== 'undefined' && module.exports) {
  module.exports = DomUtils;
}

// Exportar para uso global
window.DomUtils = DomUtils;

