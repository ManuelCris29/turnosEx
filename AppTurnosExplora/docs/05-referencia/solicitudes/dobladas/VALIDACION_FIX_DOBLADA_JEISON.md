# Validación del Fix: Doblada Existente Detectada para Jeison 14/02/2026

## Problema Original

Cuando Jeison Mora tiene una DOBLADA aprobada el 14 de febrero de 2026 (sábado) donde cede su jornada a Marco Castillo, el sistema mostraba incorrectamente "Doblada Existente Detectada" en lugar de detectar que está descansando.

**Causa raíz**: El orden de verificación en `VerificarDobladaExistenteView` aplicaba la regla de doblada por sábado (alternancia) ANTES de verificar si el usuario ya tenía una DOBLADA aprobada.

## Solución Implementada

Se reordenó la lógica de verificación en `VerificarDobladaExistenteView` para que:

1. **PRIMERO** verifique si está descansando por DOBLADA aprobada (PRIORIDAD ABSOLUTA)
2. **SEGUNDO** verifique si tiene CT aprobado
3. **TERCERO** verifique la regla de doblada por sábado (solo si no hay DOBLADA ni CT)

## Archivos Modificados

1. **`AppTurnosExplora/solicitudes/views.py`**
   - `VerificarDobladaExistenteView.get()`: Reordenamiento de casos de verificación (líneas ~2175-2268)

2. **`AppTurnosExplora/static/js/cambio-turno/solicitar_doblada.js`**
   - Manejo del caso cuando `puede_ceder: false` pero no está descansando (líneas ~1273-1292)

## Validación Manual

### Paso 1: Verificar Estado en Base de Datos

Ejecutar el script de diagnóstico:

```bash
python manage.py test_verificar_doblada_jeison
```

O ejecutar el script de validación:

```bash
python manage.py validar_fix_doblada_jeison
```

### Paso 2: Validación en el Navegador

1. **Iniciar sesión como Jeison Mora** (`jeison.mora`)

2. **Navegar al formulario de doblada**

3. **Seleccionar la fecha 14 de febrero de 2026**

4. **Resultado Esperado**:
   - ✅ NO debe aparecer "Doblada Existente Detectada"
   - ✅ Debe aparecer un mensaje indicando "Estás Descansando" o "Ya cediste tu jornada"
   - ✅ El formulario debe estar deshabilitado
   - ✅ NO debe mostrar opciones de "Cesión Parcial" o "Cesión Total"

### Paso 3: Validación del Endpoint Directamente

Abrir la consola del navegador (F12) y ejecutar:

```javascript
fetch('/solicitudes/verificar-doblada-existente/?fecha=2026-02-14')
  .then(r => r.json())
  .then(data => {
    console.log('Respuesta:', data);
    console.log('¿Está descansando?', data.esta_descansando);
    console.log('¿Tiene doblada?', data.tiene_doblada);
    console.log('¿Puede ceder?', data.puede_ceder);
  });
```

**Resultado Esperado**:
```json
{
  "success": true,
  "tiene_doblada": false,
  "esta_descansando": true,
  "puede_ceder": false,
  "jornadas": [],
  "mensaje": "Ya cediste tu jornada para esta fecha. Estás descansando este día.",
  "solicitud_id": <id_de_la_doblada>
}
```

### Paso 4: Validación de Casos Adicionales

#### Caso A: Usuario sin DOBLADA en sábado
- Seleccionar un sábado donde el usuario NO tenga DOBLADA aprobada
- **Resultado Esperado**: Debe mostrar "Doblada Existente Detectada" si corresponde por regla de negocio

#### Caso B: Usuario con CT aprobado
- Seleccionar una fecha donde el usuario tenga un CT aprobado
- **Resultado Esperado**: Debe mostrar mensaje de que no puede solicitar doblada

#### Caso C: Usuario con turnos AM+PM
- Seleccionar una fecha donde el usuario tenga turnos AM+PM en BD
- **Resultado Esperado**: Debe mostrar "Doblada Existente Detectada" con opciones de cesión

## Orden de Prioridad Final

La lógica de verificación sigue este orden (de mayor a menor prioridad):

1. **Descanso por DOBLADA aprobada** (PRIORIDAD ABSOLUTA)
   - Verifica como solicitante: `tipo_cambio='DOBLADA'`, `fecha_cambio_turno=fecha`, `estado='aprobada'`
   - Verifica como receptor: `tipo_cambio='DOBLADA'`, `doblada__fecha_pago=fecha`, `estado='aprobada'`

2. **Bloqueo por CT aprobado**
   - Verifica si tiene turnos relacionados con un CT donde es solicitante
   - O si tiene un CT aprobado sin turnos

3. **Doblada por regla de negocio (sábados)**
   - Solo se aplica si NO está descansando por DOBLADA y NO tiene CT
   - Verifica alternancia de fines de semana

## Tests Unitarios

Se creó un test unitario en:
- `AppTurnosExplora/solicitudes/tests/test_verificar_doblada_existente.py`

Para ejecutar:
```bash
python manage.py test solicitudes.tests.test_verificar_doblada_existente
```

## Scripts de Diagnóstico

1. **`test_verificar_doblada_jeison.py`**: Diagnóstico completo del estado de Jeison
2. **`validar_fix_doblada_jeison.py`**: Validación automatizada del fix

## Checklist de Validación

- [ ] Script de diagnóstico ejecutado sin errores
- [ ] Endpoint retorna `esta_descansando: true` para Jeison el 14/02/2026
- [ ] Endpoint retorna `tiene_doblada: false` para Jeison el 14/02/2026
- [ ] Endpoint retorna `puede_ceder: false` para Jeison el 14/02/2026
- [ ] Frontend NO muestra "Doblada Existente Detectada"
- [ ] Frontend muestra mensaje de "Estás Descansando"
- [ ] Formulario está deshabilitado
- [ ] Test unitario pasa correctamente

## Notas Técnicas

- El fix asegura que la verificación de DOBLADA aprobada se ejecute ANTES de la regla de sábado
- Se mantiene compatibilidad con todos los demás casos (CT, turnos normales, etc.)
- El frontend maneja correctamente todos los casos de respuesta del backend


