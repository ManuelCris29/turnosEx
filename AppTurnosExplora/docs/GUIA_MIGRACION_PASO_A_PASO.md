# Guía Paso a Paso - Migración JavaScript

## 🎯 Objetivo

Migrar código JavaScript legacy a patrones modernos de forma **segura y gradual**.

---

## Paso 1: Cargar Módulos en Templates (Riesgo: 🟢 Muy Bajo)

### 1.1 Modificar `templates/solicitudes/solicitar_doblada.html`

**Buscar** (al final del archivo, antes de `</body>` o en `{% block extra_js %}`):

```html
<script src="{% static 'js/cambio-turno/solicitar_doblada.js' %}"></script>
```

**Agregar ANTES**:

```html
{% block extra_js %}
<!-- Módulos modernos (cargar primero) -->
<script src="{% static 'js/utils/api-client.js' %}"></script>
<script src="{% static 'js/utils/date-utils.js' %}"></script>
<script src="{% static 'js/utils/dom-utils.js' %}"></script>
<script src="{% static 'js/utils/validators.js' %}"></script>
<script src="{% static 'js/services/datepicker-service.js' %}"></script>
<script src="{% static 'js/core/app.js' %}"></script>

<!-- Scripts existentes (sin cambios) -->
<script src="{% static 'js/cambio-turno/solicitar_doblada.js' %}"></script>
{% endblock %}
```

### 1.2 Repetir para otros templates

- `templates/solicitudes/solicitar_cambio_turno.html`
- `templates/solicitudes/solicitar_ct_permanente.html`
- `templates/turnos/mis_turnos.html`

### 1.3 Testing

1. Abrir cada formulario en el navegador
2. Verificar que todo funciona igual que antes
3. Abrir consola del navegador (F12)
4. Verificar que no hay errores
5. Probar funcionalidad básica (cargar página, seleccionar fechas, etc.)

**✅ Si todo funciona igual, continuar al Paso 2**

---

## Paso 2: Refactorizar Funciones Pequeñas (Riesgo: 🟡 Medio)

### 2.1 Elegir un archivo simple para empezar

**Recomendación**: Empezar con `solicitar_cambio_turno.js` (553 líneas, menos complejo)

### 2.2 Identificar funciones candidatas

Buscar funciones que:
- Hacen peticiones AJAX con `fetch()`
- Validan campos
- Manipulan DOM de forma simple
- No tienen dependencias complejas

### 2.3 Ejemplo: Refactorizar función `actualizarEmpleadosDisponibles`

**ANTES** (`solicitar_cambio_turno.js`, línea ~27):

```javascript
function actualizarEmpleadosDisponibles() {
    const fecha = fechaInput.value;
    if (!fecha) return;

    // ... código para construir URL ...
    
    fetch(url, {
        method: 'GET',
        headers: {
            'X-Requested-With': 'XMLHttpRequest',
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        // ... procesar datos ...
    })
    .catch(error => {
        console.error('Error al cargar empleados:', error);
        empleadoSelect.innerHTML = '<option value="">Error al cargar compañeros</option>';
        empleadoSelect.disabled = false;
    });
}
```

**DESPUÉS**:

```javascript
const actualizarEmpleadosDisponibles = async () => {
    const fecha = fechaInput?.value;
    if (!fecha) return;

    // Obtener tipo de solicitud
    const urlParams = new URLSearchParams(window.location.search);
    const tipoSolicitudId = urlParams.get('tipo_id') || 
                           DomUtils.$('#tipo_solicitud_id')?.value || 
                           window.tipoSolicitudId;

    // Mostrar indicador de carga
    if (empleadoSelect) {
        empleadoSelect.innerHTML = '<option value="">Cargando compañeros...</option>';
        empleadoSelect.disabled = true;
    }
    
    DomUtils.hide(turnoInfo);

    try {
        const params = { fecha };
        if (tipoSolicitudId) {
            params.tipo_solicitud_id = tipoSolicitudId;
        }

        const data = await ApiClient.get('/solicitudes/obtener-empleados-disponibles/', params);
        
        if (!empleadoSelect) return;
        
        empleadoSelect.innerHTML = '<option value="">Selecciona un compañero...</option>';
        
        if (data.success === false) {
            const mensajeError = data.error || 'Error al cargar compañeros disponibles';
            empleadoSelect.innerHTML = `<option value="">${mensajeError}</option>`;
        } else if (data.empleados && Array.isArray(data.empleados) && data.empleados.length > 0) {
            data.empleados.forEach(empleado => {
                const option = DomUtils.createElement('option', {
                    value: empleado.id
                }, `${empleado.nombre} ${empleado.apellido}`);
                empleadoSelect.appendChild(option);
            });
        } else {
            const mensaje = tipoSolicitudId && window.location.pathname.includes('cambio') 
                ? 'No hay compañeros de jornada contraria disponibles para esta fecha'
                : 'No hay compañeros disponibles para esta fecha';
            empleadoSelect.innerHTML = `<option value="">${mensaje}</option>`;
        }
        
        empleadoSelect.disabled = false;
    } catch (error) {
        console.error('Error al cargar empleados:', error);
        if (empleadoSelect) {
            empleadoSelect.innerHTML = '<option value="">Error al cargar compañeros</option>';
            empleadoSelect.disabled = false;
        }
        App.showError('Error al cargar empleados disponibles');
    }
};
```

### 2.4 Testing después del cambio

1. **Guardar el archivo**
2. **Recargar la página** (Ctrl+F5 para limpiar caché)
3. **Abrir consola** (F12) y verificar que no hay errores
4. **Probar la funcionalidad**:
   - Seleccionar una fecha
   - Verificar que se cargan los empleados
   - Verificar que se muestran correctamente
   - Verificar manejo de errores (desconectar internet temporalmente)

**✅ Si funciona correctamente, continuar con la siguiente función**

**❌ Si hay problemas, revertir el cambio y revisar**

---

## Paso 3: Refactorizar Validaciones

### 3.1 Buscar validaciones simples

**Ejemplo**:

```javascript
// ANTES
if (!fecha || fecha === '') {
    alert('La fecha es requerida');
    return false;
}

// DESPUÉS
const fechaValidation = Validators.required(fecha, 'La fecha');
if (!fechaValidation.valid) {
    App.showError(fechaValidation.message);
    return false;
}
```

### 3.2 Testing

Probar que las validaciones funcionan igual o mejor que antes.

---

## Paso 4: Refactorizar Manipulación DOM

### 4.1 Buscar código DOM repetitivo

**Ejemplo**:

```javascript
// ANTES
const elemento = document.getElementById('mi-elemento');
if (elemento) {
    elemento.classList.add('active');
    elemento.style.display = 'none';
}

// DESPUÉS
const elemento = DomUtils.$('#mi-elemento');
DomUtils.addClass(elemento, 'active');
DomUtils.hide(elemento);
```

---

## Paso 5: Refactorizar Archivos Complejos (Solo cuando tengas experiencia)

### 5.1 `solicitar_doblada.js` (2,237 líneas)

**Estrategia**:
1. Dividir en módulos más pequeños
2. Extraer funciones reutilizables
3. Crear clases para manejar estados complejos
4. Refactorizar sección por sección

**Ejemplo de estructura propuesta**:

```javascript
// Crear: static/js/components/doblada-form.js
class DobladaForm {
    constructor() {
        this.form = DomUtils.$('#dobladaForm');
        this.fechaCesionInput = DomUtils.$('#fecha_cesion');
        // ... inicializar elementos
    }
    
    async init() {
        await this.initializeDatepickers();
        this.setupEventListeners();
        await this.checkExistingDoblada();
    }
    
    // ... métodos organizados
}
```

---

## 🔍 Checklist de Verificación

Después de cada cambio, verificar:

### Funcionalidad
- [ ] El formulario carga correctamente
- [ ] Los campos se muestran
- [ ] Los datepickers funcionan
- [ ] Los selects se llenan
- [ ] Las validaciones funcionan
- [ ] El envío del formulario funciona

### Consola del Navegador
- [ ] No hay errores en consola
- [ ] No hay warnings relevantes
- [ ] Las peticiones AJAX se hacen correctamente

### UX
- [ ] Los mensajes de error se muestran
- [ ] Los mensajes de éxito se muestran
- [ ] Los indicadores visuales funcionan
- [ ] La navegación funciona

---

## 🚨 Si Algo Sale Mal

### Opción 1: Revertir con Git

```bash
# Ver qué archivos cambiaron
git status

# Revertir un archivo específico
git checkout HEAD -- static/js/cambio-turno/solicitar_cambio_turno.js

# O revertir todos los cambios
git checkout HEAD -- .
```

### Opción 2: Comentar código nuevo

```javascript
// Temporalmente comentado para debugging
// const data = await ApiClient.get('/api/endpoint');
// Usar código legacy mientras tanto
fetch('/api/endpoint')
    .then(response => response.json())
    .then(data => {
        // ...
    });
```

### Opción 3: Usar ambos (transición)

```javascript
// Usar ApiClient si está disponible, sino usar fetch
const fetchData = async (url, params) => {
    if (typeof ApiClient !== 'undefined') {
        return await ApiClient.get(url, params);
    } else {
        // Fallback a código legacy
        const response = await fetch(url);
        return await response.json();
    }
};
```

---

## 📊 Progreso Sugerido

### Semana 1
- [x] Cargar módulos en templates
- [ ] Testing básico

### Semana 2
- [ ] Refactorizar 2-3 funciones en `solicitar_cambio_turno.js`
- [ ] Testing exhaustivo

### Semana 3
- [ ] Refactorizar validaciones
- [ ] Refactorizar manipulación DOM simple

### Semana 4+
- [ ] Refactorizar archivos complejos (solo si todo va bien)

---

## 💡 Tips

1. **Hacer commits frecuentes**: Un commit por cada función refactorizada
2. **Probar inmediatamente**: No acumular cambios sin probar
3. **Documentar cambios**: Comentar qué cambió y por qué
4. **Pedir ayuda**: Si algo no funciona, revisar documentación o preguntar

---

## ✅ Listo para Empezar

1. ✅ Módulos creados y documentados
2. ✅ Estructura lista
3. ✅ Plan de migración definido
4. ✅ Estrategia de testing establecida

**Siguiente paso**: Empezar con Paso 1 (cargar módulos en templates) - **Riesgo mínimo** 🟢



