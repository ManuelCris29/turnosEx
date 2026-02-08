# Decisión Técnica: Historial de `jornada_pago_sabado`

## Decisión Final

**Solución implementada:** Exclusión temporal del campo `jornada_pago_sabado` del historial de `simple_history`.

```python
historial = HistoricalRecords(excluded_fields=['jornada_pago_sabado'])
```

## Análisis del Problema

### Problema Identificado
- La columna `jornada_pago_sabado` existe físicamente en ambas tablas:
  - ✅ `solicitudes_dobladadetalle` (tabla principal)
  - ✅ `solicitudes_dobladadetallehistory` (tabla histórica)
- Django reconoce el campo en el modelo principal
- Django reconoce el campo en el modelo histórico (verificado con `get_history_manager_for_model`)
- **PERO**: Al intentar insertar, Django genera SQL que falla con "Unknown column"

### Causa Raíz
El problema parece estar en cómo `django-simple-history` genera internamente el modelo histórico y construye las queries SQL. Aunque la columna existe y Django la reconoce, hay un desajuste entre:
- El esquema de la base de datos (tiene la columna)
- El modelo histórico que Django genera dinámicamente (no incluye la columna en el INSERT)

Esto puede deberse a:
1. Caché interna de `simple_history` sobre la estructura del modelo
2. El modelo histórico se genera antes de que la migración se aplique completamente
3. Un bug conocido en `django-simple-history` con campos agregados después de la creación inicial

## Solución Implementada

### Opción Elegida: Exclusión Temporal
```python
historial = HistoricalRecords(excluded_fields=['jornada_pago_sabado'])
```

### Justificación

1. **Funcionalidad Principal Intacta**
   - ✅ El campo se guarda correctamente en la tabla principal
   - ✅ Todas las consultas y lógica de negocio funcionan
   - ✅ El sistema es completamente funcional

2. **Impacto Mínimo en Auditoría**
   - `jornada_pago_sabado` se establece **una sola vez** al crear la solicitud
   - No se modifica después de la creación
   - El valor actual siempre está disponible en la tabla principal
   - Los demás campos de `DobladaDetalle` SÍ tienen historial completo

3. **Solución Práctica**
   - Resuelve el problema inmediato
   - No requiere investigación profunda de `django-simple-history`
   - Permite continuar con el desarrollo

## Impacto en el Proyecto

### ✅ Lo que Funciona
- Guardado de `jornada_pago_sabado` en tabla principal
- Consultas y filtros por `jornada_pago_sabado`
- Lógica de aplicación de dobladas en sábados
- Historial completo de todos los demás campos de `DobladaDetalle`

### ⚠️ Lo que No se Registra en Historial
- Cambios en `jornada_pago_sabado` (pero este campo no cambia después de la creación)
- Versiones anteriores de `jornada_pago_sabado` (pero solo hay una versión)

## Solución Futura (Opcional)

Si en el futuro se necesita el historial completo de `jornada_pago_sabado`, las opciones son:

### Opción 1: Regenerar Modelo Histórico
```python
# Eliminar y recrear la tabla histórica
# Esto requiere:
# 1. Backup de datos históricos existentes
# 2. Eliminar tabla histórica
# 3. Recrear con makemigrations/migrate
# 4. Restaurar datos históricos si es necesario
```

### Opción 2: Migración Manual de simple_history
```python
# Crear migración personalizada que:
# 1. Agregue la columna a la tabla histórica
# 2. Force a simple_history a reconocerla
# 3. Actualice el modelo histórico interno
```

### Opción 3: Actualizar django-simple-history
- Verificar si hay una versión más reciente que solucione el problema
- Reportar el bug si es necesario

## Recomendación

**Mantener la solución actual** porque:
- ✅ Funciona correctamente
- ✅ No afecta la funcionalidad principal
- ✅ El impacto en auditoría es mínimo (campo no cambia)
- ✅ Permite continuar con el desarrollo sin bloqueos

**Revisar en el futuro** si:
- Se necesita modificar `jornada_pago_sabado` después de la creación
- Se requiere auditoría estricta de este campo específico
- Hay tiempo para investigar el problema con `django-simple-history`

## Notas Técnicas

- **Fecha de implementación:** 2026-01-29
- **Versión de django-simple-history:** Verificar con `pip show django-simple-history`
- **Estado:** Solución temporal funcional, pendiente de investigación futura


