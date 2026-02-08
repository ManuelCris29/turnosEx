# Reglas de Negocio: Cambio de Turno Sencillo (CT)

## 📋 Descripción General

El **Cambio de Turno Sencillo (CT)** es una solicitud para intercambiar turnos con otro explorador en una **fecha específica**. Es un cambio puntual, de un solo día.

---

## 🔐 Reglas de Negocio

### 1. Validaciones de Empleados

#### 1.1 Ambos empleados deben estar activos
- ✅ **Regla**: El solicitante y el receptor deben tener estado `activo = True`
- ❌ **Rechazo si**: Cualquiera de los dos está inactivo
- 📝 **Mensaje de error**: "El empleado no está activo"

#### 1.2 No puede ser el mismo empleado
- ✅ **Regla**: El solicitante y el receptor deben ser personas diferentes
- ❌ **Rechazo si**: `solicitante.id == receptor.id`
- 📝 **Mensaje de error**: "No puedes solicitar cambio contigo mismo"

#### 1.3 Ambos deben tener jornada asignada
- ✅ **Regla**: Ambos empleados deben tener una jornada asignada para la fecha seleccionada
- ❌ **Rechazo si**: 
  - El solicitante no tiene jornada para esa fecha
  - El receptor no tiene jornada para esa fecha
- 📝 **Mensaje de error**: 
  - "El solicitante no tiene jornada asignada para esa fecha"
  - "El receptor no tiene jornada asignada para esa fecha"

---

### 2. Validaciones de Jornadas

#### 2.1 Jornadas contrarias obligatorias (AM ↔ PM)
- ✅ **Regla**: El solicitante y receptor deben tener jornadas **opuestas**
  - Si solicitante tiene **AM** → receptor debe tener **PM**
  - Si solicitante tiene **PM** → receptor debe tener **AM**
- ❌ **Rechazo si**: Ambos tienen la misma jornada (AM-AM o PM-PM)
- 📝 **Mensaje de error**: "No se puede cambiar por la misma jornada. Los empleados deben tener jornadas contrarias"
- 🔍 **Nota importante**: El sistema considera las jornadas **reales** en esa fecha, incluyendo cambios previos aprobados

#### 2.2 No se permite cambio por la misma jornada
- ✅ **Regla**: Es imposible crear un cambio entre dos personas con la misma jornada
- 🔍 **Implementación**: El frontend filtra automáticamente mostrando solo exploradores con jornada contraria

---

### 3. Validaciones de Fecha

#### 3.1 No puede ser fecha pasada
- ✅ **Regla**: La fecha del cambio debe ser **hoy o en el futuro**
- ❌ **Rechazo si**: `fecha_cambio_turno < fecha_actual`
- 📝 **Mensaje de error**: "La fecha no puede ser en el pasado"
- 🔍 **Implementación**: El calendario del frontend deshabilita fechas pasadas

#### 3.2 No puede ser domingo
- ✅ **Regla**: No se puede cambiar domingo por día de semana
- ❌ **Rechazo si**: `fecha.weekday() == 6` (domingo)
- 📝 **Mensaje de error**: "No se puede cambiar domingo por día de semana"
- 🔍 **Nota**: Los domingos no están disponibles en el calendario

#### 3.2.1 No puede ser sábado
- ✅ **Regla**: No se puede cambiar sábado por día de semana
- ❌ **Rechazo si**: `fecha.weekday() == 5` (sábado)
- 📝 **Mensaje de error**: "No se puede cambiar sábado por día de semana"
- 🔍 **Nota**: Los sábados no están disponibles en el calendario para CT Sencillo

#### 3.3 No puede ser día de mantenimiento
- ✅ **Regla**: No se puede realizar cambio en días de mantenimiento
- ❌ **Rechazo si**: La fecha está marcada como `tipo='mantenimiento'` en `DiaEspecial`
- 📝 **Mensaje de error**: "No se puede realizar cambio en día de mantenimiento"
- 🔍 **Implementación**: El sistema consulta la tabla `core_diaespecial` para validar

#### 3.4 No puede ser día de temporada
- ✅ **Regla**: No se puede realizar cambio en días de temporada (si aplica)
- ❌ **Rechazo si**: La fecha está marcada como temporada en `DiaEspecial`
- 📝 **Mensaje de error**: Error relacionado con temporada
- 🔍 **Nota**: Depende de la configuración del sistema

#### 3.5 Festivos (permitido si ambos tienen jornada)
- ✅ **Regla**: Se permite cambio en festivos **SI** ambos empleados tienen jornada asignada ese día
- ✅ **Permitido si**: 
  - La fecha es festivo (`tipo='festivo'` en `DiaEspecial`)
  - **Y** el solicitante tiene jornada
  - **Y** el receptor tiene jornada
- 🔍 **Nota**: El sistema permite solicitar en festivos si ambos tienen jornada, pero el frontend puede mostrar indicadores visuales

---

### 4. Validaciones de Duplicidad

#### 4.1 No puede haber solicitud pendiente del mismo par
- ✅ **Regla**: No puede existir una solicitud **pendiente** con el mismo:
  - Solicitante
  - Receptor
  - Fecha
- ❌ **Rechazo si**: Existe `SolicitudCambio` con:
  - `explorador_solicitante = solicitante`
  - `explorador_receptor = receptor`
  - `fecha_cambio_turno = fecha`
  - `estado = 'pendiente'`
- 📝 **Mensaje de error**: "Ya existe una solicitud pendiente tuya con este explorador para la misma fecha"
- 🔍 **Nota**: Esta validación previene que el mismo solicitante envíe múltiples solicitudes al mismo receptor para la misma fecha

#### 4.2 Múltiples solicitantes pueden solicitar al mismo receptor
- ✅ **Regla**: **Diferentes solicitantes** pueden enviar solicitudes al **mismo receptor** para la **misma fecha**
- ✅ **Permitido**: 
  - Solicitante A → Receptor X, fecha 15/02
  - Solicitante B → Receptor X, fecha 15/02
  - Solicitante C → Receptor X, fecha 15/02
- 🔍 **Comportamiento**: First-Come, First-Served (ver sección 11)

---

### 5. Validaciones de Dobladas

#### 5.1 El solicitante no puede tener doblada activa
- ✅ **Regla**: El solicitante no puede tener una doblada aprobada (AM+PM) para la fecha del cambio
- ❌ **Rechazo si**: El solicitante tiene turnos AM y PM en esa fecha (doblada)
- 📝 **Mensaje de error**: "No se puede realizar cambio de turno. Tienes una doblada activa para esta fecha"
- 🔍 **Verificación**: El sistema busca turnos del solicitante en esa fecha y verifica si tiene AM y PM

#### 5.2 El receptor no puede tener doblada activa
- ✅ **Regla**: El receptor no puede tener una doblada aprobada (AM+PM) para la fecha del cambio
- ❌ **Rechazo si**: El receptor tiene turnos AM y PM en esa fecha (doblada)
- 📝 **Mensaje de error**: "El receptor tiene una doblada activa para esta fecha"
- 🔍 **Verificación**: El sistema busca turnos del receptor en esa fecha y verifica si tiene AM y PM
- 🔍 **Nota**: El frontend puede filtrar automáticamente para no mostrar receptores con doblada

---

### 6. Límite de Cambios por Fecha

#### 6.1 Máximo 3 cambios aprobados por explorador/fecha
- ✅ **Regla**: Un explorador puede tener **máximo 3 cambios aprobados** para la misma fecha
- ❌ **Rechazo si**: 
  - El solicitante ya tiene 3 cambios aprobados para esa fecha
  - **O** el receptor ya tiene 3 cambios aprobados para esa fecha
- 📝 **Mensaje de error**: 
  - "Se ha alcanzado el límite de cambios para esta fecha. El explorador [nombre] ya tiene 3 cambio(s) aprobado(s) para el [fecha]. Límite máximo: 3 cambio(s) por fecha."
- 🔍 **Validación**: Se realiza **al aplicar los cambios** (cuando se aprueba), no al crear la solicitud
- 🔍 **Cálculo**: Se cuentan todas las solicitudes aprobadas donde el explorador es solicitante o receptor

#### 6.2 Validación para solicitante
- ✅ **Regla**: Se valida el límite para el solicitante
- 🔍 **Verificación**: `SolicitudConsultaService.contar_cambios_explorador_fecha(solicitante_id, fecha) >= 3`

#### 6.3 Validación para receptor
- ✅ **Regla**: Se valida el límite para el receptor
- 🔍 **Verificación**: `SolicitudConsultaService.contar_cambios_explorador_fecha(receptor_id, fecha) >= 3`

---

## 🔄 Proceso de Aplicación (Cuando se Aprueba)

### 7. Creación/Actualización de Turnos

#### 7.1 Si ya existe Turno para el explorador
- ✅ **Comportamiento**: Se **actualiza** el turno existente
- ✅ **Acciones**:
  - Se actualiza la `jornada` (se asigna la jornada del otro explorador)
  - Se actualiza la `sala` (se asigna la sala del otro explorador)
  - Se mantiene `tipo_cambio = 'CT'`
  - Se registra trazabilidad de la solicitud anterior
- 🔍 **Caso de uso**: Cambio sobre cambio (ver sección 11)

#### 7.2 Si no existe Turno
- ✅ **Comportamiento**: Se **crean** nuevos turnos
- ✅ **Acciones**:
  - Se crea turno para el **solicitante** con:
    - `jornada` = jornada del receptor
    - `sala` = sala del receptor
    - `tipo_cambio = 'CT'`
  - Se crea turno para el **receptor** con:
    - `jornada` = jornada del solicitante
    - `sala` = sala del solicitante
    - `tipo_cambio = 'CT'`

---

### 8. Trazabilidad

#### 8.1 Relación con solicitud anterior
- ✅ **Regla**: Si se actualiza un turno existente, se busca la solicitud anterior que lo creó
- ✅ **Acciones**:
  - Se busca `SolicitudCambio` donde `turno_origen = turno_existente` o `turno_destino = turno_existente`
  - Se relaciona la nueva solicitud con la anterior mediante `solicitud_origen`
  - Se agrega comentario de trazabilidad en el campo `comentario`

#### 8.2 Comentario de trazabilidad
- ✅ **Formato**: 
  ```
  "Actualización: cambio previo reemplazado. 
  Solicitud anterior ID: [ID] 
  (aprobada el [fecha_resolucion])"
  ```
- 🔍 **Nota**: Si no se encuentra la solicitud anterior, se agrega: "solicitud anterior no encontrada en el sistema"

---

### 9. First-Come, First-Served

#### 9.1 Rechazo automático de otras solicitudes pendientes
- ✅ **Regla**: Al aprobar una solicitud, se **rechazan automáticamente** todas las solicitudes pendientes del mismo receptor para la misma fecha
- ✅ **Comportamiento**:
  - Se buscan todas las `SolicitudCambio` con:
    - `explorador_receptor = receptor_aprobado`
    - `fecha_cambio_turno = fecha_aprobada`
    - `estado = 'pendiente'`
    - `id != solicitud_aprobada.id`
  - Se actualizan todas a `estado = 'rechazada'`
  - Se establece `fecha_resolucion = ahora`
  - Se agrega comentario de rechazo automático

#### 9.2 Notificaciones a solicitantes afectados
- ✅ **Regla**: Se crean notificaciones para cada solicitante cuya solicitud fue rechazada automáticamente
- ✅ **Acciones**:
  - Se crea `Notificacion` para cada solicitante afectado
  - Tipo: `'rechazo'`
  - Mensaje explica el rechazo automático
  - Se envía email (si está configurado)

#### 9.3 Mensaje de rechazo automático
- ✅ **Mensaje estándar**: 
  ```
  "Rechazada automáticamente: otra solicitud fue aprobada primero (First-Come, First-Served)"
  ```

---

### 10. Invalidación de Caché

#### 10.1 Caché de turnos invalidado
- ✅ **Regla**: Se invalida el caché de turnos para ambos exploradores del mes correspondiente
- ✅ **Acciones**:
  - Se elimina caché para el solicitante: `turnos_mes_{solicitante_id}_{año}_{mes}`
  - Se elimina caché para el receptor: `turnos_mes_{receptor_id}_{año}_{mes}`
- 🔍 **Propósito**: Asegurar que el calendario muestre los turnos actualizados inmediatamente

---

## 📊 Flujo de Aprobación

### 11. Doble Aprobación Requerida

#### 11.1 Aprobación por supervisor
- ✅ **Regla**: El supervisor debe aprobar la solicitud
- ✅ **Acciones**:
  - Se establece `aprobado_supervisor = True`
  - Se crea notificación para el solicitante
  - Si el receptor ya aprobó → estado cambia a `'aprobada'` y se aplican cambios
  - Si el receptor no ha aprobado → estado sigue `'pendiente'`

#### 11.2 Aprobación por receptor
- ✅ **Regla**: El receptor debe aprobar la solicitud
- ✅ **Acciones**:
  - Se establece `aprobado_receptor = True`
  - Se crea notificación para el solicitante
  - Si el supervisor ya aprobó → estado cambia a `'aprobada'` y se aplican cambios
  - Si el supervisor no ha aprobado → estado sigue `'pendiente'`

#### 11.3 Aplicación inmediata
- ✅ **Regla**: Cuando **ambos aprueban**, se aplican los cambios **inmediatamente**
- ✅ **Acciones**:
  - Estado cambia a `'aprobada'`
  - Se establece `fecha_resolucion = ahora`
  - Se ejecuta `CambioTurnoStrategy.aplicar_cambios()`
  - Se crean/actualizan turnos
  - Se rechazan otras solicitudes pendientes (First-Come, First-Served)
  - Se invalidan cachés

---

## 📝 Campos Requeridos

| Campo | Tipo | Descripción | Validación |
|-------|------|-------------|------------|
| `tipo_solicitud_id` | Integer | ID del tipo "CT" | ✅ Requerido |
| `empleado_receptor` | Integer | ID del explorador receptor | ✅ Requerido, activo, no mismo empleado |
| `fecha_solicitud` | Date | Fecha del cambio (YYYY-MM-DD) | ✅ Requerido, no pasado, formato válido |
| `comentario` | Text | Comentario opcional | ⚪ Opcional |

---

## 🔍 Casos Especiales

### 12. Cambio sobre Cambio

#### 12.1 Actualización de turno existente
- ✅ **Escenario**: Un explorador ya tiene un turno creado por un cambio previo
- ✅ **Comportamiento**: 
  - Si se aprueba un nuevo cambio, se **actualiza** el turno existente
  - No se crea un turno duplicado
  - Se mantiene la trazabilidad

#### 12.2 Trazabilidad de cambios múltiples
- ✅ **Regla**: Se puede rastrear la cadena de cambios mediante `solicitud_origen`
- 🔍 **Ejemplo**: 
  - Solicitud A crea turno para Juan
  - Solicitud B actualiza ese turno (tiene `solicitud_origen = A`)
  - Solicitud C actualiza ese turno (tiene `solicitud_origen = B`)

---

## ⚠️ Resumen de Validaciones

### Validaciones que se realizan al CREAR la solicitud:
1. ✅ Empleados activos
2. ✅ No mismo empleado
3. ✅ Ambos tienen jornada
4. ✅ Jornadas contrarias
5. ✅ No fecha pasada
6. ✅ No domingo
7. ✅ No día de mantenimiento
8. ✅ No día de temporada
9. ✅ No solicitud duplicada pendiente
10. ✅ No doblada activa (solicitante)
11. ✅ No doblada activa (receptor)

### Validaciones que se realizan al APROBAR la solicitud:
1. ✅ Límite de 3 cambios por fecha (solicitante)
2. ✅ Límite de 3 cambios por fecha (receptor)
3. ✅ Estado de la solicitud sigue siendo 'pendiente'
4. ✅ No tiene turnos ya creados (para evitar duplicados)

---

## 📌 Notas Importantes

1. **Jornadas Reales**: El sistema considera las jornadas **reales** en la fecha, incluyendo cambios previos aprobados, no solo la jornada base del empleado.

2. **First-Come, First-Served**: Si múltiples solicitantes envían solicitudes al mismo receptor para la misma fecha, solo la primera aprobada se aplica. Las demás se rechazan automáticamente.

3. **Cambio sobre Cambio**: Si un explorador ya tiene un turno por un cambio previo, un nuevo cambio **actualiza** ese turno en lugar de crear uno nuevo.

4. **Aplicación Inmediata**: Los cambios se aplican **inmediatamente** cuando ambos (supervisor y receptor) aprueban. No quedan pendientes.

5. **Límite de Cambios**: El límite de 3 cambios se valida **al aprobar**, no al crear la solicitud. Esto permite crear múltiples solicitudes, pero solo se pueden aprobar hasta 3.

---

**Última actualización**: Enero 2026  
**Versión**: 1.0

