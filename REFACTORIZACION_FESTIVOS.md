# Refactorización: Módulo Común para Festivos

## Problema Identificado

El código para manejar festivos en los datepickers estaba **duplicado** en dos archivos:
- `solicitar_cambio_turno.js` (Cambio Turno normal)
- `solicitar_ct_permanente.js` (Cambio Turno Permanente)

Esto viola el principio DRY (Don't Repeat Yourself) y hace el mantenimiento más difícil.

## Solución Implementada

Se creó un **módulo común reutilizable**: `datepicker_festivos.js`

### Archivo Creado

**`static/js/cambio-turno/datepicker_festivos.js`**

Este módulo exporta las siguientes funciones:

1. **`cargarDiasFestivos(añoEspecifico)`**
   - Carga festivos calculados (JavaScript) + festivos de BD
   - Usa caché global compartido
   - Retorna Promise con Map de festivos

2. **`verificarDiaFestivo(fecha, indicador, descripcion)`**
   - Verifica si una fecha es festivo
   - Actualiza indicador visual

3. **`marcarFestivosEnCalendario(instance, festivosMap)`**
   - Marca días festivos en calendario Flatpickr
   - Aplica estilos CSS

4. **`inicializarDatepickerFestivos(config)`**
   - Función principal para inicializar datepicker
   - Acepta configuración flexible
   - Maneja callbacks personalizados

### API del Módulo

```javascript
window.DatepickerFestivos.inicializar({
    input: document.getElementById('fecha'),
    minDate: '2025-01-01',
    maxDate: '2025-12-31',
    indicadorFestivo: document.getElementById('indicador'),
    descripcionFestivo: document.getElementById('descripcion'),
    onDateChange: function(fecha) {
        // Callback personalizado
    },
    flatpickrOptions: {
        // Opciones adicionales de Flatpickr
    }
});
```

## Archivos Modificados

### 1. Templates

**`solicitar_cambio_turno.html`** y **`solicitar_ct_permanente.html`**
- Agregado: `<script src="{% static 'js/cambio-turno/datepicker_festivos.js' %}"></script>`

### 2. JavaScript

**`solicitar_cambio_turno.js`**
- ❌ Eliminado: ~170 líneas de código duplicado
- ✅ Agregado: Uso del módulo común (3 líneas)

**`solicitar_ct_permanente.js`**
- ❌ Eliminado: ~200 líneas de código duplicado
- ✅ Agregado: Uso del módulo común (40 líneas)

## Beneficios

1. **DRY (Don't Repeat Yourself)**: Código centralizado
2. **Mantenibilidad**: Cambios en un solo lugar
3. **Reutilización**: Fácil agregar a otros tipos de solicitud
4. **Consistencia**: Mismo comportamiento en todos los formularios
5. **Caché compartido**: Mejor rendimiento (festivos cargados una vez)

## Uso Futuro

Para agregar festivos a un nuevo tipo de solicitud:

```javascript
// 1. Incluir el módulo en el template
<script src="{% static 'js/cambio-turno/datepicker_festivos.js' %}"></script>

// 2. Inicializar en el JavaScript
window.DatepickerFestivos.inicializar({
    input: document.getElementById('fecha'),
    indicadorFestivo: document.getElementById('indicador'),
    descripcionFestivo: document.getElementById('descripcion'),
    onDateChange: function(fecha) {
        // Tu lógica personalizada
    }
});
```

## Estado

✅ **Completado**: Refactorización exitosa
- Módulo común creado
- Ambos archivos refactorizados
- Funcionalidad preservada
- Código más limpio y mantenible


