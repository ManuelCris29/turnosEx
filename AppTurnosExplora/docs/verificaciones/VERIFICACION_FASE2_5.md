# VERIFICACIÓN FASE 2.5: Notificaciones UI - Advertencias

## Objetivo
Verificar que el sistema muestra advertencias en la UI cuando el usuario ya tiene un cambio aprobado para la fecha seleccionada, informándole que el nuevo cambio reemplazará el existente.

## Cambios Implementados

### 1. Nueva Vista: `ObtenerCambioAprobadoView`
**Archivo:** `AppTurnosExplora/solicitudes/views.py` (líneas 273-354)

**Funcionalidad:**
- Endpoint que verifica si el usuario logueado tiene un `Turno` para la fecha especificada
- Si existe turno, busca la `SolicitudCambio` aprobada que lo creó
- Devuelve información detallada sobre el cambio existente:
  - Jornada actual
  - Nombre del compañero con quien hizo el intercambio
  - Fecha de aprobación
  - ID de la solicitud
- Determina si el usuario es el solicitante o receptor del cambio anterior

**Respuesta JSON:**
```json
{
  "success": true,
  "data": {
    "tiene_cambio_aprobado": true,
    "mensaje": "Ya tienes un cambio aprobado para esta fecha. Tu jornada actual es PM (intercambio con Juan Pérez). Este nuevo cambio lo reemplazará.",
    "informacion_cambio": {
      "solicitud_id": 123,
      "jornada_actual": "PM",
      "companero_nombre": "Juan Pérez",
      "fecha_aprobacion": "20/11/2024 14:30",
      "es_solicitante": true
    }
  }
}
```

### 2. Nueva Ruta
**Archivo:** `AppTurnosExplora/solicitudes/urls.py` (línea 44)

**Ruta agregada:**
```python
path('obtener-cambio-aprobado/', ObtenerCambioAprobadoView.as_view(), name='obtener_cambio_aprobado'),
```

### 3. Template: Div de Advertencia
**Archivo:** `AppTurnosExplora/templates/solicitudes/solicitar_cambio_turno.html` (líneas 42-56)

**Funcionalidad:**
- Div oculto por defecto que muestra una alerta de advertencia
- Incluye:
  - Título: "Cambio Aprobado Existente"
  - Mensaje principal (dinámico)
  - Detalles del cambio actual (dinámico)
  - Botón para cerrar la advertencia

**HTML:**
```html
<div id="advertencia_cambio_aprobado" class="form-group" style="display: none;">
    <div class="alert alert-warning alert-dismissible fade show" role="alert">
        <h5 class="alert-heading">
            <i class="fas fa-exclamation-triangle mr-2"></i>Cambio Aprobado Existente
        </h5>
        <p id="mensaje_advertencia" class="mb-2"></p>
        <div id="detalles_cambio_aprobado" class="mt-2">
            <!-- Detalles dinámicos -->
        </div>
        <button type="button" class="close" data-dismiss="alert" aria-label="Close">
            <span aria-hidden="true">&times;</span>
        </button>
    </div>
</div>
```

### 4. JavaScript: Función de Verificación
**Archivo:** `AppTurnosExplora/static/js/solicitar_cambio_turno.js` (líneas 329-392)

**Funcionalidad:**
- Función `verificarCambioAprobado()` que:
  - Obtiene la fecha seleccionada
  - Hace una petición AJAX al endpoint `/solicitudes/obtener-cambio-aprobado/`
  - Si existe cambio aprobado:
    - Muestra el div de advertencia
    - Rellena el mensaje principal
    - Muestra detalles formateados del cambio actual
  - Si no existe, oculta la advertencia
- Event listener en el campo de fecha que llama a `verificarCambioAprobado()` cuando cambia
- Verificación automática al cargar la página si hay fecha seleccionada

**Detalles mostrados:**
- Jornada actual (AM/PM)
- Nombre del compañero
- Fecha de aprobación
- ID de la solicitud

## Casos de Prueba

### Caso 1: Sin Cambio Aprobado
**Escenario:**
- Usuario no tiene turno para fecha X
- Usuario selecciona fecha X en el formulario

**Resultado Esperado:**
- ✅ No se muestra advertencia
- ✅ El div `advertencia_cambio_aprobado` permanece oculto

### Caso 2: Con Cambio Aprobado (Usuario como Solicitante)
**Escenario:**
- Usuario tiene turno para fecha X (creado por solicitud aprobada donde fue solicitante)
- Usuario selecciona fecha X en el formulario

**Resultado Esperado:**
- ✅ Se muestra advertencia con estilo `alert-warning`
- ✅ Mensaje: "Ya tienes un cambio aprobado para esta fecha. Tu jornada actual es {jornada} (intercambio con {companero}). Este nuevo cambio lo reemplazará."
- ✅ Detalles muestran:
  - Jornada actual
  - Nombre del compañero
  - Fecha de aprobación
  - ID de la solicitud

### Caso 3: Con Cambio Aprobado (Usuario como Receptor)
**Escenario:**
- Usuario tiene turno para fecha X (creado por solicitud aprobada donde fue receptor)
- Usuario selecciona fecha X en el formulario

**Resultado Esperado:**
- ✅ Se muestra advertencia
- ✅ Mensaje correcto con información del compañero (solicitante original)
- ✅ Detalles completos

### Caso 4: Cambio de Fecha
**Escenario:**
- Usuario tiene cambio aprobado para fecha X
- Usuario selecciona fecha X → Se muestra advertencia
- Usuario cambia a fecha Y (sin cambio aprobado)

**Resultado Esperado:**
- ✅ Al cambiar a fecha Y, la advertencia se oculta automáticamente
- ✅ Al volver a fecha X, la advertencia se muestra nuevamente

### Caso 5: Turno Sin Solicitud Asociada (Caso Raro)
**Escenario:**
- Usuario tiene turno para fecha X pero no se encuentra la solicitud que lo creó

**Resultado Esperado:**
- ✅ Se muestra advertencia genérica
- ✅ Mensaje: "Ya tienes un turno asignado para esta fecha (jornada: {jornada}). Este nuevo cambio lo reemplazará."
- ✅ Detalles muestran solo la jornada actual

## Verificación Manual

### Paso 1: Verificar Endpoint
```bash
# Hacer petición GET al endpoint
curl -X GET "http://127.0.0.1:8000/solicitudes/obtener-cambio-aprobado/?fecha=2024-11-20" \
  -H "Cookie: sessionid=..."
```

**Respuesta esperada:**
```json
{
  "success": true,
  "data": {
    "tiene_cambio_aprobado": true,
    "mensaje": "...",
    "informacion_cambio": {...}
  }
}
```

### Paso 2: Verificar en UI
1. Iniciar sesión como usuario con cambio aprobado
2. Ir a `/solicitudes/cambio-turno/solicitar/{tipo_id}/`
3. Seleccionar la fecha del cambio aprobado
4. Verificar que aparece la advertencia

### Paso 3: Verificar Detalles
- Verificar que la jornada actual es correcta
- Verificar que el nombre del compañero es correcto
- Verificar que la fecha de aprobación es correcta
- Verificar que el ID de la solicitud es correcto

### Paso 4: Verificar Comportamiento Dinámico
1. Seleccionar fecha con cambio aprobado → Advertencia visible
2. Cambiar a fecha sin cambio aprobado → Advertencia oculta
3. Volver a fecha con cambio aprobado → Advertencia visible nuevamente

### Paso 5: Verificar Cierre de Advertencia
- Hacer clic en el botón "×" de la advertencia
- Verificar que la advertencia se cierra (Bootstrap alert dismiss)

## Notas Importantes

1. **Búsqueda de Solicitud:** El sistema busca la solicitud que creó el turno buscando en `turno_origen` Y `turno_destino`, ya que un turno puede ser el origen o destino de una solicitud.

2. **Orden de Búsqueda:** Se ordena por `fecha_resolucion` descendente para obtener la solicitud más reciente (en caso de múltiples solicitudes para el mismo turno, aunque esto no debería ocurrir).

3. **Determinación de Rol:** El sistema determina si el usuario es solicitante o receptor comparando el ID del empleado con `explorador_solicitante` y `explorador_receptor`.

4. **Manejo de Errores:** Si ocurre un error en la verificación, la advertencia se oculta para no confundir al usuario.

5. **Performance:** La verificación se hace solo cuando cambia la fecha, no en cada interacción del formulario.

6. **UX:** La advertencia es informativa, no bloquea la creación de la solicitud. El usuario puede cerrarla y continuar.

## Estado
✅ **IMPLEMENTADO** - Pendiente de pruebas manuales

