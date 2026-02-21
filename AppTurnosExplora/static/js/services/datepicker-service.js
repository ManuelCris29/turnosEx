/**
 * Servicio para manejo de datepickers Flatpickr
 * 
 * Proporciona una interfaz unificada para inicializar y manejar
 * datepickers con festivos, mantenimiento y validaciones.
 * 
 * @module services/datepicker-service
 */

/**
 * Servicio para datepickers
 */
class DatepickerService {
  /**
   * Inicializa un datepicker con configuración personalizada
   * @param {Object} options - Opciones de configuración
   * @param {HTMLElement} options.input - Input element
   * @param {Object} options.config - Configuración de Flatpickr
   * @param {Function} options.onDateChange - Callback cuando cambia la fecha
   * @param {HTMLElement} options.indicadorFestivo - Elemento para mostrar indicador de festivo
   * @param {HTMLElement} options.indicadorMantenimiento - Elemento para mostrar indicador de mantenimiento
   * @returns {Object} Instancia de Flatpickr
   */
  static async initialize({
    input,
    config = {},
    onDateChange = null,
    indicadorFestivo = null,
    indicadorMantenimiento = null,
  }) {
    if (!input || typeof flatpickr === 'undefined') {
      console.error('[DatepickerService] Input o Flatpickr no disponible');
      return null;
    }

    // Configuración por defecto
    const defaultConfig = {
      locale: 'es',
      dateFormat: 'Y-m-d',
      minDate: 'today',
      allowInput: false,
      clickOpens: true,
      ...config,
    };

    // Inicializar Flatpickr
    const flatpickrInstance = flatpickr(input, defaultConfig);

    // Configurar callbacks
    if (onDateChange) {
      flatpickrInstance.config.onChange.push((selectedDates, dateStr) => {
        onDateChange(dateStr, selectedDates[0]);
      });
    }

    // Cargar y marcar festivos si hay indicadores
    if (indicadorFestivo || indicadorMantenimiento) {
      await this.loadAndMarkSpecialDays(flatpickrInstance, {
        indicadorFestivo,
        indicadorMantenimiento,
      });
    }

    return flatpickrInstance;
  }

  /**
   * Carga y marca días especiales (festivos, mantenimiento)
   * @param {Object} flatpickrInstance - Instancia de Flatpickr
   * @param {Object} options - Opciones
   */
  static async loadAndMarkSpecialDays(flatpickrInstance, options = {}) {
    try {
      // Cargar festivos
      const festivosResponse = await fetch('/turnos/api/dias-festivos/');
      const festivosData = await festivosResponse.json();
      const festivos = new Set(festivosData.festivos?.map(f => f.fecha) || []);

      // Cargar mantenimiento
      const mantenimientoResponse = await fetch('/turnos/api/dias-mantenimiento/');
      const mantenimientoData = await mantenimientoResponse.json();
      const mantenimiento = new Set(
        mantenimientoData.mantenimiento?.map(m => m.fecha) || []
      );

      // Marcar días en el calendario
      flatpickrInstance.config.onReady.push((selectedDates, dateStr, instance) => {
        const calendar = instance.calendarContainer;
        const days = calendar.querySelectorAll('.flatpickr-day');

        days.forEach(day => {
          const date = day.getAttribute('aria-label');
          if (!date) return;

          // Convertir fecha a formato YYYY-MM-DD
          const dateObj = new Date(date);
          const dateStr = dateObj.toISOString().split('T')[0];

          if (festivos.has(dateStr)) {
            day.classList.add('festivo');
            if (options.indicadorFestivo) {
              // Mostrar indicador
            }
          }

          if (mantenimiento.has(dateStr)) {
            day.classList.add('mantenimiento');
            if (options.indicadorMantenimiento) {
              // Mostrar indicador
            }
          }
        });
      });
    } catch (error) {
      console.error('[DatepickerService] Error cargando días especiales:', error);
    }
  }

  /**
   * Deshabilita días específicos
   * @param {Object} flatpickrInstance - Instancia de Flatpickr
   * @param {Array<string>} dates - Array de fechas a deshabilitar (YYYY-MM-DD)
   */
  static disableDates(flatpickrInstance, dates) {
    if (!flatpickrInstance) return;

    const disableFunction = (date) => {
      const dateStr = date.toISOString().split('T')[0];
      return dates.includes(dateStr);
    };

    flatpickrInstance.set('disable', [
      ...(flatpickrInstance.config.disable || []),
      disableFunction,
    ]);
  }

  /**
   * Habilita solo días específicos
   * @param {Object} flatpickrInstance - Instancia de Flatpickr
   * @param {Array<string>} dates - Array de fechas a habilitar (YYYY-MM-DD)
   */
  static enableOnlyDates(flatpickrInstance, dates) {
    if (!flatpickrInstance) return;

    const enableFunction = (date) => {
      const dateStr = date.toISOString().split('T')[0];
      return !dates.includes(dateStr);
    };

    flatpickrInstance.set('disable', [
      ...(flatpickrInstance.config.disable || []),
      enableFunction,
    ]);
  }

  /**
   * Destruye una instancia de Flatpickr
   * @param {Object} flatpickrInstance - Instancia a destruir
   */
  static destroy(flatpickrInstance) {
    if (flatpickrInstance && typeof flatpickrInstance.destroy === 'function') {
      flatpickrInstance.destroy();
    }
  }
}

// Exportar para uso en módulos ES6
if (typeof module !== 'undefined' && module.exports) {
  module.exports = DatepickerService;
}

// Exportar para uso global
window.DatepickerService = DatepickerService;



