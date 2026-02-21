# JavaScript - Estructura Modular

## 📁 Estructura de Carpetas

```
js/
├── core/
│   └── app.js                    # Aplicación principal
├── utils/
│   ├── api-client.js            # Cliente HTTP
│   ├── date-utils.js            # Utilidades de fechas
│   ├── dom-utils.js              # Utilidades de DOM
│   └── validators.js             # Validadores
├── services/
│   └── datepicker-service.js    # Servicio de datepickers
└── [app-specific]/              # Código específico por app
```

## 🚀 Uso Rápido

### Cargar Módulos en Templates

```html
<!-- En tu template base.html o en templates específicos -->
<script src="{% static 'js/utils/api-client.js' %}"></script>
<script src="{% static 'js/utils/date-utils.js' %}"></script>
<script src="{% static 'js/utils/dom-utils.js' %}"></script>
<script src="{% static 'js/utils/validators.js' %}"></script>
<script src="{% static 'js/services/datepicker-service.js' %}"></script>
<script src="{% static 'js/core/app.js' %}"></script>
```

### Ejemplo de Uso

```javascript
// Usar ApiClient para peticiones HTTP
const empleados = await ApiClient.get('/solicitudes/obtener-empleados-disponibles/', {
  fecha: '2025-01-15'
});

// Usar DateUtils para fechas
const esDomingo = DateUtils.isSunday('2025-01-19');
const fechaFormateada = DateUtils.formatDate(new Date());

// Usar DomUtils para DOM
const elemento = DomUtils.$('#mi-elemento');
DomUtils.addClass(elemento, 'active');
DomUtils.show(elemento);

// Usar Validators para validación
const validation = Validators.required(fecha, 'La fecha');
if (!validation.valid) {
  App.showError(validation.message);
}

// Usar DatepickerService
const datepicker = await DatepickerService.initialize({
  input: document.getElementById('fecha'),
  config: { minDate: 'today' },
  onDateChange: (date) => console.log(date)
});
```

## 📚 Documentación de Módulos

### ApiClient

Cliente HTTP centralizado para peticiones AJAX.

```javascript
// GET
const data = await ApiClient.get('/api/endpoint', { param: 'value' });

// POST
const result = await ApiClient.post('/api/endpoint', { name: 'John' });

// PUT
const updated = await ApiClient.put('/api/endpoint/1', { name: 'Jane' });

// DELETE
await ApiClient.delete('/api/endpoint/1');
```

### DateUtils

Utilidades para trabajar con fechas.

```javascript
// Verificar día de semana
DateUtils.isSunday('2025-01-19');      // true
DateUtils.isSaturday('2025-01-18');    // true
DateUtils.isWeekend('2025-01-19');     // true

// Formatear
DateUtils.formatDate(new Date());      // "19/01/2025"

// Comparar
DateUtils.compareDates('2025-01-15', '2025-01-20'); // -1

// Obtener hoy
const hoy = DateUtils.getToday();      // "2025-01-19"
```

### DomUtils

Utilidades para manipulación del DOM.

```javascript
// Selectores
const el = DomUtils.$('#id');
const all = DomUtils.$$('.class');

// Clases
DomUtils.addClass(el, 'active');
DomUtils.removeClass(el, 'inactive');
DomUtils.toggleClass(el, 'visible');

// Visibilidad
DomUtils.show(el);
DomUtils.hide(el);
DomUtils.toggle(el);

// Eventos con debounce
const debounced = DomUtils.debounce(() => {
  console.log('Ejecutado después de 300ms');
}, 300);
```

### Validators

Validadores reutilizables.

```javascript
// Validaciones básicas
Validators.required('', 'Campo');           // { valid: false, message: "..." }
Validators.email('test@example.com');       // { valid: true, message: "" }
Validators.futureDate('2025-12-31');        // { valid: true, message: "" }

// Validaciones de fechas
Validators.dateAfter('2025-01-01', '2025-01-15', 'Fecha fin');

// Múltiples reglas
const rules = [
  (v) => Validators.required(v, 'Campo'),
  (v) => Validators.minLength(v, 5, 'Campo')
];
Validators.validate('test', rules);
```

### DatepickerService

Servicio para datepickers Flatpickr.

```javascript
const datepicker = await DatepickerService.initialize({
  input: document.getElementById('fecha'),
  config: {
    minDate: 'today',
    dateFormat: 'Y-m-d'
  },
  onDateChange: (date) => {
    console.log('Fecha seleccionada:', date);
  },
  indicadorFestivo: document.getElementById('indicador'),
  indicadorMantenimiento: document.getElementById('mantenimiento')
});

// Deshabilitar fechas específicas
DatepickerService.disableDates(datepicker, ['2025-01-20', '2025-01-21']);
```

### App

Aplicación principal con utilidades de UI.

```javascript
// Mostrar mensajes
App.showError('Ocurrió un error', 'Error');
App.showSuccess('Operación exitosa', 'Éxito');

// Confirmación
const confirmed = await App.confirm('¿Está seguro?', 'Confirmar');
if (confirmed) {
  // Usuario confirmó
}
```

## 🔄 Migración de Código Legacy

### Antes (Legacy)

```javascript
(function() {
  'use strict';
  
  var fechaInput = document.getElementById('fecha');
  var empleadoSelect = document.getElementById('empleado');
  
  function actualizarEmpleados() {
    var fecha = fechaInput.value;
    if (!fecha) return;
    
    fetch('/api/empleados?fecha=' + fecha)
      .then(function(response) {
        return response.json();
      })
      .then(function(data) {
        empleadoSelect.innerHTML = '';
        data.empleados.forEach(function(empleado) {
          var option = document.createElement('option');
          option.value = empleado.id;
          option.textContent = empleado.nombre;
          empleadoSelect.appendChild(option);
        });
      })
      .catch(function(error) {
        console.error(error);
        alert('Error al cargar empleados');
      });
  }
  
  fechaInput.addEventListener('change', actualizarEmpleados);
})();
```

### Después (Moderno)

```javascript
(async () => {
  'use strict';
  
  const fechaInput = DomUtils.$('#fecha');
  const empleadoSelect = DomUtils.$('#empleado');
  
  const actualizarEmpleados = async () => {
    const fecha = fechaInput?.value;
    if (!fecha) return;
    
    try {
      const data = await ApiClient.get('/api/empleados', { fecha });
      
      DomUtils.clear(empleadoSelect);
      data.empleados.forEach(empleado => {
        const option = DomUtils.createElement('option', {
          value: empleado.id
        }, empleado.nombre);
        empleadoSelect?.appendChild(option);
      });
    } catch (error) {
      App.showError('Error al cargar empleados');
    }
  };
  
  DomUtils.on(fechaInput, 'change', actualizarEmpleados);
})();
```

## ✅ Mejores Prácticas

1. **Usar const por defecto**, solo `let` cuando necesites reasignar
2. **Arrow functions** para callbacks y funciones cortas
3. **Template literals** en lugar de concatenación
4. **Destructuring** para objetos y arrays
5. **Async/await** en lugar de Promise chains
6. **Optional chaining** (`?.`) para acceso seguro
7. **Nullish coalescing** (`??`) para valores por defecto
8. **Try/catch** para manejo de errores en async

## 📝 Notas

- Todos los módulos están disponibles globalmente en `window.*`
- Compatible con código legacy existente
- Migración gradual posible
- No requiere build process (funciona directamente en navegador)



