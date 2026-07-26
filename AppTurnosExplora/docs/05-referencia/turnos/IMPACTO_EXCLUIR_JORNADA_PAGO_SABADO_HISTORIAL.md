# Impacto de Excluir `jornada_pago_sabado` del Historial

## ¿Qué es `simple_history`?

`django-simple-history` es una librería que crea automáticamente un registro histórico cada vez que se guarda o actualiza un modelo. Esto permite:

1. **Auditoría**: Ver quién hizo qué cambio y cuándo
2. **Trazabilidad**: Rastrear el historial completo de cambios en un registro
3. **Recuperación**: Ver estados anteriores de un registro

## Estado Actual

**Campo excluido:** `jornada_pago_sabado` en el modelo `DobladaDetalle`

**Código actual:**
```python
historial = HistoricalRecords(excluded_fields=['jornada_pago_sabado'])
```

## Efectos en el Proyecto

### ✅ **Lo que SÍ funciona (sin problemas):**

1. **Guardado normal**: El campo `jornada_pago_sabado` se guarda correctamente en la tabla principal `solicitudes_dobladadetalle`
2. **Consultas normales**: Puedes consultar y usar `jornada_pago_sabado` normalmente:
   ```python
   detalle = DobladaDetalle.objects.get(id=1)
   print(detalle.jornada_pago_sabado)  # ✅ Funciona
   ```
3. **Filtros y búsquedas**: Puedes filtrar por este campo:
   ```python
   DobladaDetalle.objects.filter(jornada_pago_sabado='AM')  # ✅ Funciona
   ```
4. **Aplicación de dobladas**: El campo se usa correctamente en la lógica de negocio

### ⚠️ **Lo que NO se guarda en el historial:**

1. **Cambios en `jornada_pago_sabado`**: Si alguien modifica este campo, el cambio NO quedará registrado en el historial
2. **Versiones anteriores**: No podrás ver qué valor tenía `jornada_pago_sabado` en versiones anteriores del registro
3. **Auditoría de este campo**: No habrá registro de quién cambió este campo y cuándo

### 📊 **Ejemplo Práctico:**

**Escenario:** Un `DobladaDetalle` se crea con `jornada_pago_sabado='AM'` y luego se actualiza a `jornada_pago_sabado='PM'`

**Con historial completo:**
```python
detalle = DobladaDetalle.objects.get(id=1)
historial = detalle.historial.all()
# Verías:
# - Versión 1: jornada_pago_sabado='AM' (creado el 2026-01-28)
# - Versión 2: jornada_pago_sabado='PM' (actualizado el 2026-01-29)
```

**Con campo excluido (estado actual):**
```python
detalle = DobladaDetalle.objects.get(id=1)
historial = detalle.historial.all()
# Verías:
# - Versión 1: (sin jornada_pago_sabado en el historial)
# - Versión 2: (sin jornada_pago_sabado en el historial)
# Pero el valor actual en detalle.jornada_pago_sabado sigue siendo 'PM' ✅
```

## ¿Es un Problema Crítico?

### ❌ **NO es crítico si:**

- `jornada_pago_sabado` se establece **una sola vez** al crear la solicitud
- No se modifica después de la creación
- No necesitas auditoría de cambios en este campo específico
- El valor actual siempre está disponible en la tabla principal

### ⚠️ **SÍ podría ser un problema si:**

- Necesitas rastrear cambios en `jornada_pago_sabado` para auditoría
- El campo se modifica después de la creación
- Requieres cumplir con normativas de auditoría estrictas
- Necesitas recuperar valores anteriores de este campo

## Solución Alternativa (Si se Necesita Historial Completo)

Si en el futuro necesitas el historial completo, puedes:

1. **Agregar la columna a la tabla histórica manualmente:**
   ```sql
   ALTER TABLE solicitudes_dobladadetallehistory
   ADD COLUMN jornada_pago_sabado VARCHAR(2) NULL;
   ```

2. **Quitar la exclusión del modelo:**
   ```python
   historial = HistoricalRecords()  # Sin excluded_fields
   ```

3. **Regenerar la tabla histórica** (si es necesario)

## Recomendación

**Para el caso actual:** La exclusión es **aceptable** porque:
- `jornada_pago_sabado` es un campo que se establece al crear la solicitud
- No se modifica después (es parte de la solicitud original)
- El valor siempre está disponible en la tabla principal
- Resuelve el problema técnico inmediato

**Para el futuro:** Si necesitas auditoría completa, puedes implementar la solución alternativa cuando sea necesario.





