# Test Manual: Cambio de Turno Sencillo (CT)

## 📋 Índice

1. [Preparación](#1-preparación)
2. [Validaciones de Empleados](#2-validaciones-de-empleados)
3. [Validaciones de Jornadas](#3-validaciones-de-jornadas)
4. [Validaciones de Fecha](#4-validaciones-de-fecha)
5. [Validaciones de Duplicidad](#5-validaciones-de-duplicidad)
6. [Validaciones de Dobladas](#6-validaciones-de-dobladas)
7. [Límite de Cambios](#7-límite-de-cambios)
8. [Flujo Completo - Creación](#8-flujo-completo---creación)
9. [Flujo Completo - Aprobación](#9-flujo-completo---aprobación)
10. [Flujo Completo - Rechazo](#10-flujo-completo---rechazo)
11. [Casos Especiales - Cambio sobre Cambio](#11-casos-especiales---cambio-sobre-cambio)
12. [Casos Especiales - First-Come, First-Served](#12-casos-especiales---first-come-first-served)
13. [Casos Especiales - Invalidación de Caché](#13-casos-especiales---invalidación-de-caché)
14. [Verificación de Integridad - Turnos](#14-verificación-de-integridad---turnos)
15. [Verificación de Integridad - Notificaciones](#15-verificación-de-integridad---notificaciones)

---

## 1. Preparación

### 1.1 Usuarios de Prueba Requeridos

| Usuario | Jornada Base | Rol | Estado | Notas |
|---------|--------------|-----|--------|-------|
| `jhon.areiza` | AM | Explorador | Activo | Para pruebas como solicitante AM |
| `usuario_pm_1` | PM | Explorador | Activo | Para pruebas como receptor PM |
| `usuario_am_2` | AM | Explorador | Activo | Para pruebas adicionales |
| `usuario_pm_2` | PM | Explorador | Activo | Para pruebas adicionales |
| `supervisor_1` | - | Supervisor | Activo | Para aprobaciones |
| `usuario_inactivo` | AM | Explorador | Inactivo | Para pruebas de validación |

**Nota**: Reemplazar con usuarios reales del sistema.

### 1.2 Datos de Prueba

| Tipo | Fecha | Descripción |
|------|-------|-------------|
| Fecha válida | `2026-02-15` (Lunes) | Fecha futura para pruebas normales |
| Fecha pasada | `2025-01-01` | Para validar rechazo de fechas pasadas |
| Domingo | `2026-02-14` | Para validar rechazo de domingos |
| Día festivo | `2026-01-01` | Para validar comportamiento en festivos |
| Día mantenimiento | Consultar BD | Para validar rechazo de mantenimiento |

### 1.3 Pre-requisitos

- [ ] Base de datos con usuarios de prueba configurados
- [ ] Usuarios con jornadas asignadas (AM/PM)
- [ ] Al menos un supervisor configurado
- [ ] Acceso a la aplicación web
- [ ] Acceso a la base de datos para verificación (opcional)

### 1.4 Consultas SQL Útiles

```sql
-- Verificar jornada de un usuario en una fecha
SELECT e.nombre, e.apellido, j.nombre as jornada
FROM empleados_empleado e
JOIN turnos_jornadaempleado je ON je.empleado_id = e.id
JOIN turnos_jornada j ON j.id = je.jornada_id
WHERE e.user_id = (SELECT id FROM auth_user WHERE username = 'usuario_am_1')
AND je.fecha_inicio <= '2026-02-15'
AND (je.fecha_fin IS NULL OR je.fecha_fin >= '2026-02-15');

-- Verificar turnos existentes
SELECT t.*, j.nombre as jornada, e.nombre as explorador
FROM turnos_turno t
JOIN turnos_jornada j ON j.id = t.jornada_id
JOIN empleados_empleado e ON e.id = t.explorador_id
WHERE t.fecha = '2026-02-15';

-- Verificar solicitudes pendientes
SELECT sc.*, ts.nombre as tipo
FROM solicitudes_solicitudcambio sc
JOIN solicitudes_tiposolicitudcambio ts ON ts.id = sc.tipo_cambio_id
WHERE sc.estado = 'pendiente'
AND sc.fecha_cambio_turno = '2026-02-15';
```

---

## 2. Validaciones de Empleados

### CT-001: Ambos empleados activos

| Campo | Valor |
|-------|-------|
| **ID** | CT-001 |
| **Descripción** | Verificar que ambos empleados (solicitante y receptor) deben estar activos |
| **Pre-requisitos** | Usuario inactivo configurado en el sistema |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1` (activo)<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Seleccionar fecha válida (ej: 2026-02-15)<br>4. Intentar seleccionar `usuario_inactivo` como receptor<br>5. Enviar solicitud |
| **Resultado Esperado** | ❌ Error: "El empleado no está activo" o el usuario inactivo no aparece en la lista |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-002: No mismo empleado

| Campo | Valor |
|-------|-------|
| **ID** | CT-002 |
| **Descripción** | Verificar que no se puede solicitar cambio con uno mismo |
| **Pre-requisitos** | Usuario activo con jornada asignada |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1`<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Seleccionar fecha válida<br>4. Intentar seleccionarse a sí mismo como receptor (si es posible)<br>5. Enviar solicitud |
| **Resultado Esperado** | ❌ Error: "No puedes solicitar cambio contigo mismo" o no aparece en la lista |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-003: Ambos tienen jornada asignada

| Campo | Valor |
|-------|-------|
| **ID** | CT-003 |
| **Descripción** | Verificar que ambos empleados deben tener jornada asignada para la fecha |
| **Pre-requisitos** | Usuario sin jornada asignada para la fecha de prueba |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1`<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Seleccionar fecha válida<br>4. Seleccionar receptor que NO tenga jornada asignada para esa fecha<br>5. Enviar solicitud |
| **Resultado Esperado** | ❌ Error: "El receptor no tiene jornada asignada para esa fecha" o no aparece en la lista |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 3. Validaciones de Jornadas

### CT-004: Jornadas contrarias obligatorias (AM ↔ PM)

| Campo | Valor |
|-------|-------|
| **ID** | CT-004 |
| **Descripción** | Verificar que solo se muestran exploradores con jornada contraria |
| **Pre-requisitos** | `usuario_am_1` con jornada AM, `usuario_pm_1` con jornada PM para la fecha |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1` (AM)<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Seleccionar fecha válida (ej: 2026-02-15)<br>4. Revisar lista de exploradores disponibles |
| **Resultado Esperado** | ✅ Solo aparecen exploradores con jornada PM en la lista<br>❌ No aparecen exploradores con jornada AM |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-005: Rechazo si misma jornada

| Campo | Valor |
|-------|-------|
| **ID** | CT-005 |
| **Descripción** | Verificar rechazo si se intenta cambiar con alguien de la misma jornada |
| **Pre-requisitos** | Dos usuarios con la misma jornada (AM) para la fecha |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1` (AM)<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Seleccionar fecha válida<br>4. Si aparece `usuario_am_2` (AM) en la lista, seleccionarlo<br>5. Enviar solicitud |
| **Resultado Esperado** | ❌ Error: "No se puede cambiar por la misma jornada. Los empleados deben tener jornadas contrarias"<br>O `usuario_am_2` no aparece en la lista |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-006: Verificación de jornadas en fecha específica

| Campo | Valor |
|-------|-------|
| **ID** | CT-006 |
| **Descripción** | Verificar que se consideran jornadas reales (incluyendo cambios previos) en la fecha específica |
| **Pre-requisitos** | `usuario_am_1` tiene cambio previo aprobado que le da jornada PM en la fecha de prueba |
| **Pasos** | 1. Verificar en BD que `usuario_am_1` tiene turno con jornada PM para 2026-02-15<br>2. Iniciar sesión como `usuario_pm_1` (PM)<br>3. Ir a "Solicitar Cambio de Turno"<br>4. Seleccionar fecha 2026-02-15<br>5. Revisar si `usuario_am_1` aparece en la lista |
| **Resultado Esperado** | ❌ `usuario_am_1` NO aparece en la lista (porque ya tiene jornada PM, no AM) |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 4. Validaciones de Fecha

### CT-007: No fecha pasada

| Campo | Valor |
|-------|-------|
| **ID** | CT-007 |
| **Descripción** | Verificar que no se puede seleccionar fecha pasada |
| **Pre-requisitos** | Fecha pasada conocida (ej: 2025-01-01) |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1`<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Intentar seleccionar fecha pasada (2025-01-01)<br>4. Verificar comportamiento del calendario |
| **Resultado Esperado** | ❌ No se puede seleccionar fecha pasada (calendario deshabilita o valida) |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-008: No domingo

| Campo | Valor |
|-------|-------|
| **ID** | CT-008 |
| **Descripción** | Verificar que no se puede cambiar domingo por día de semana |
| **Pre-requisitos** | Fecha que sea domingo (ej: 2026-02-14) |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1`<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Seleccionar fecha domingo (2026-02-14)<br>4. Intentar enviar solicitud |
| **Resultado Esperado** | ❌ Error: "No se puede cambiar domingo por día de semana" o el domingo no está disponible en el calendario |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-008B: No sábado

| Campo | Valor |
|-------|-------|
| **ID** | CT-008B |
| **Descripción** | Verificar que no se puede cambiar sábado por día de semana |
| **Pre-requisitos** | Fecha que sea sábado (ej: 2026-02-13) |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1`<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Seleccionar fecha sábado (2026-02-13)<br>4. Intentar enviar solicitud |
| **Resultado Esperado** | ❌ Error: "No se puede cambiar sábado por día de semana" o el sábado no está disponible en el calendario |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-009: No día de mantenimiento

| Campo | Valor |
|-------|-------|
| **ID** | CT-009 |
| **Descripción** | Verificar que no se puede cambiar en día de mantenimiento |
| **Pre-requisitos** | Día de mantenimiento configurado en el sistema |
| **Pasos** | 1. Consultar BD para encontrar día de mantenimiento<br>2. Iniciar sesión como `usuario_am_1`<br>3. Ir a "Solicitar Cambio de Turno"<br>4. Seleccionar fecha de mantenimiento<br>5. Intentar enviar solicitud |
| **Resultado Esperado** | ❌ Error: "No se puede realizar cambio en día de mantenimiento" o la fecha no está disponible |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-010: No día de temporada

| Campo | Valor |
|-------|-------|
| **ID** | CT-010 |
| **Descripción** | Verificar que no se puede cambiar en día de temporada (si aplica) |
| **Pre-requisitos** | Día de temporada configurado en el sistema |
| **Pasos** | 1. Consultar BD para encontrar día de temporada<br>2. Iniciar sesión como `usuario_am_1`<br>3. Ir a "Solicitar Cambio de Turno"<br>4. Seleccionar fecha de temporada<br>5. Intentar enviar solicitud |
| **Resultado Esperado** | ❌ Error relacionado con temporada o la fecha no está disponible |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-011: Festivos (permitido si ambos tienen jornada)

| Campo | Valor |
|-------|-------|
| **ID** | CT-011 |
| **Descripción** | Verificar que se permite cambio en festivos si ambos tienen jornada |
| **Pre-requisitos** | Día festivo configurado donde ambos usuarios tienen jornada |
| **Pasos** | 1. Consultar BD para encontrar día festivo<br>2. Verificar que `usuario_am_1` y `usuario_pm_1` tienen jornada ese día<br>3. Iniciar sesión como `usuario_am_1`<br>4. Ir a "Solicitar Cambio de Turno"<br>5. Seleccionar fecha festiva<br>6. Seleccionar `usuario_pm_1` como receptor<br>7. Enviar solicitud |
| **Resultado Esperado** | ✅ Solicitud creada exitosamente (si ambos tienen jornada) |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 5. Validaciones de Duplicidad

### CT-012: No solicitud pendiente del mismo par

| Campo | Valor |
|-------|-------|
| **ID** | CT-012 |
| **Descripción** | Verificar que no se puede crear solicitud duplicada (mismo solicitante-receptor-fecha) |
| **Pre-requisitos** | Solicitud pendiente existente de `usuario_am_1` a `usuario_pm_1` para 2026-02-15 |
| **Pasos** | 1. Crear solicitud pendiente de `usuario_am_1` a `usuario_pm_1` para 2026-02-15<br>2. Iniciar sesión como `usuario_am_1`<br>3. Ir a "Solicitar Cambio de Turno"<br>4. Seleccionar fecha 2026-02-15<br>5. Seleccionar `usuario_pm_1` como receptor<br>6. Intentar enviar solicitud |
| **Resultado Esperado** | ❌ Error: "Ya existe una solicitud pendiente tuya con este explorador para la misma fecha" |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-013: Múltiples solicitantes pueden solicitar al mismo receptor

| Campo | Valor |
|-------|-------|
| **ID** | CT-013 |
| **Descripción** | Verificar que múltiples solicitantes pueden enviar solicitudes al mismo receptor (First-Come, First-Served) |
| **Pre-requisitos** | Múltiples usuarios activos con jornadas contrarias al receptor |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1`<br>2. Crear solicitud a `usuario_pm_1` para 2026-02-15<br>3. Cerrar sesión<br>4. Iniciar sesión como `usuario_am_2`<br>5. Crear solicitud a `usuario_pm_1` para 2026-02-15<br>6. Verificar que ambas solicitudes existen |
| **Resultado Esperado** | ✅ Ambas solicitudes creadas exitosamente (estado: pendiente) |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | Esto valida el comportamiento First-Come, First-Served |

---

## 6. Validaciones de Dobladas

### CT-014: Solicitante no tiene doblada activa

| Campo | Valor |
|-------|-------|
| **ID** | CT-014 |
| **Descripción** | Verificar que el solicitante no puede tener doblada activa para la fecha |
| **Pre-requisitos** | `usuario_am_1` tiene doblada aprobada (AM+PM) para 2026-02-15 |
| **Pasos** | 1. Verificar en BD que `usuario_am_1` tiene doblada para 2026-02-15<br>2. Iniciar sesión como `usuario_am_1`<br>3. Ir a "Solicitar Cambio de Turno"<br>4. Seleccionar fecha 2026-02-15<br>5. Seleccionar receptor válido<br>6. Intentar enviar solicitud |
| **Resultado Esperado** | ❌ Error: "No se puede realizar cambio de turno. Tienes una doblada activa para esta fecha" |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-015: Receptor no tiene doblada activa

| Campo | Valor |
|-------|-------|
| **ID** | CT-015 |
| **Descripción** | Verificar que el receptor no puede tener doblada activa para la fecha |
| **Pre-requisitos** | `usuario_pm_1` tiene doblada aprobada (AM+PM) para 2026-02-15 |
| **Pasos** | 1. Verificar en BD que `usuario_pm_1` tiene doblada para 2026-02-15<br>2. Iniciar sesión como `usuario_am_1`<br>3. Ir a "Solicitar Cambio de Turno"<br>4. Seleccionar fecha 2026-02-15<br>5. Verificar si `usuario_pm_1` aparece en la lista<br>6. Si aparece, intentar enviar solicitud |
| **Resultado Esperado** | ❌ Error: "El receptor tiene una doblada activa para esta fecha" o no aparece en la lista |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 7. Límite de Cambios

### CT-016: Máximo 3 cambios aprobados por explorador/fecha

| Campo | Valor |
|-------|-------|
| **ID** | CT-016 |
| **Descripción** | Verificar que se aplica límite de 3 cambios aprobados por explorador por fecha |
| **Pre-requisitos** | `usuario_am_1` ya tiene 3 cambios aprobados para 2026-02-15 |
| **Pasos** | 1. Verificar en BD que `usuario_am_1` tiene 3 cambios aprobados para 2026-02-15<br>2. Iniciar sesión como `usuario_am_1`<br>3. Ir a "Solicitar Cambio de Turno"<br>4. Seleccionar fecha 2026-02-15<br>5. Seleccionar receptor válido<br>6. Enviar solicitud<br>7. Aprobar la solicitud (supervisor y receptor) |
| **Resultado Esperado** | ❌ Error al aprobar: "Se ha alcanzado el límite de cambios para esta fecha. El explorador ya tiene 3 cambio(s) aprobado(s). Límite máximo: 3 cambio(s) por fecha." |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-017: Validación para solicitante

| Campo | Valor |
|-------|-------|
| **ID** | CT-017 |
| **Descripción** | Verificar que el límite se valida para el solicitante |
| **Pre-requisitos** | `usuario_am_1` tiene 3 cambios aprobados como solicitante para 2026-02-15 |
| **Pasos** | 1. Verificar en BD el estado<br>2. Crear nueva solicitud de `usuario_am_1` a `usuario_pm_1` para 2026-02-15<br>3. Aprobar la solicitud |
| **Resultado Esperado** | ❌ Error al aplicar cambios: límite excedido para solicitante |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-018: Validación para receptor

| Campo | Valor |
|-------|-------|
| **ID** | CT-018 |
| **Descripción** | Verificar que el límite se valida para el receptor |
| **Pre-requisitos** | `usuario_pm_1` tiene 3 cambios aprobados como receptor para 2026-02-15 |
| **Pasos** | 1. Verificar en BD el estado<br>2. Crear nueva solicitud de `usuario_am_1` a `usuario_pm_1` para 2026-02-15<br>3. Aprobar la solicitud |
| **Resultado Esperado** | ❌ Error al aplicar cambios: límite excedido para receptor |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 8. Flujo Completo - Creación

### CT-FL-001: Creación exitosa con datos válidos

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-001 |
| **Descripción** | Verificar creación exitosa de solicitud con todos los datos válidos |
| **Pre-requisitos** | `usuario_am_1` (AM) y `usuario_pm_1` (PM) activos, sin conflictos |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1`<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Seleccionar fecha válida (2026-02-15)<br>4. Seleccionar `usuario_pm_1` como receptor<br>5. Agregar comentario opcional<br>6. Enviar solicitud |
| **Resultado Esperado** | ✅ Mensaje de éxito: "Solicitud creada exitosamente"<br>✅ Solicitud visible en "Mis Solicitudes" con estado "pendiente" |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-FL-002: Verificación de estado inicial (pendiente)

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-002 |
| **Descripción** | Verificar que la solicitud se crea con estado "pendiente" |
| **Pre-requisitos** | Solicitud creada en CT-FL-001 |
| **Pasos** | 1. Verificar en "Mis Solicitudes" el estado de la solicitud<br>2. Verificar en BD: `SELECT estado FROM solicitudes_solicitudcambio WHERE id = [ID]` |
| **Resultado Esperado** | ✅ Estado = "pendiente"<br>✅ `aprobado_receptor` = False<br>✅ `aprobado_supervisor` = False |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-FL-003: Verificación de notificaciones enviadas

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-003 |
| **Descripción** | Verificar que se envían notificaciones al receptor y supervisor |
| **Pre-requisitos** | Solicitud creada en CT-FL-001 |
| **Pasos** | 1. Iniciar sesión como `usuario_pm_1` (receptor)<br>2. Verificar notificaciones<br>3. Iniciar sesión como `supervisor_1`<br>4. Verificar notificaciones<br>5. Verificar en BD: `SELECT * FROM solicitudes_notificacion WHERE solicitud_id = [ID]` |
| **Resultado Esperado** | ✅ Notificación para receptor creada<br>✅ Notificación para supervisor creada<br>✅ Emails enviados (verificar bandeja de entrada si está configurado) |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 9. Flujo Completo - Aprobación

### CT-FL-004: Aprobación por supervisor

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-004 |
| **Descripción** | Verificar aprobación por supervisor |
| **Pre-requisitos** | Solicitud pendiente creada |
| **Pasos** | 1. Iniciar sesión como `supervisor_1`<br>2. Ir a "Solicitudes Pendientes"<br>3. Encontrar la solicitud<br>4. Aprobar la solicitud<br>5. Agregar comentario opcional |
| **Resultado Esperado** | ✅ Solicitud aprobada por supervisor<br>✅ Estado sigue "pendiente" (esperando receptor)<br>✅ `aprobado_supervisor` = True<br>✅ Notificación enviada al solicitante |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-FL-005: Aprobación por receptor

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-005 |
| **Descripción** | Verificar aprobación por receptor |
| **Pre-requisitos** | Solicitud pendiente creada |
| **Pasos** | 1. Iniciar sesión como `usuario_pm_1` (receptor)<br>2. Ir a "Mis Solicitudes" o notificaciones<br>3. Encontrar la solicitud<br>4. Aprobar la solicitud<br>5. Agregar comentario opcional |
| **Resultado Esperado** | ✅ Solicitud aprobada por receptor<br>✅ Estado sigue "pendiente" (esperando supervisor)<br>✅ `aprobado_receptor` = True<br>✅ Notificación enviada al solicitante |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-FL-006: Aprobación completa (ambos aprueban)

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-006 |
| **Descripción** | Verificar que cuando ambos aprueban, se aplican los cambios inmediatamente |
| **Pre-requisitos** | Solicitud pendiente, uno ya aprobó (supervisor o receptor) |
| **Pasos** | 1. Aprobar por el segundo aprobador (receptor o supervisor)<br>2. Verificar estado de la solicitud<br>3. Verificar turnos creados en BD<br>4. Verificar calendario de ambos usuarios |
| **Resultado Esperado** | ✅ Estado cambia a "aprobada"<br>✅ `fecha_resolucion` se establece<br>✅ Turnos creados/actualizados para ambos exploradores<br>✅ Jornadas intercambiadas correctamente |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-FL-007: Verificación de aplicación inmediata de cambios

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-007 |
| **Descripción** | Verificar que los cambios se aplican inmediatamente al aprobar (no quedan pendientes) |
| **Pre-requisitos** | Solicitud aprobada completamente |
| **Pasos** | 1. Verificar en BD los turnos:<br>   - `SELECT * FROM turnos_turno WHERE explorador_id = [solicitante_id] AND fecha = [fecha]`<br>   - `SELECT * FROM turnos_turno WHERE explorador_id = [receptor_id] AND fecha = [fecha]`<br>2. Verificar jornadas asignadas<br>3. Verificar salas asignadas |
| **Resultado Esperado** | ✅ Solicitante tiene jornada del receptor<br>✅ Receptor tiene jornada del solicitante<br>✅ Salas intercambiadas correctamente<br>✅ `tipo_cambio` = 'CT' en ambos turnos |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 10. Flujo Completo - Rechazo

### CT-FL-008: Rechazo por supervisor

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-008 |
| **Descripción** | Verificar rechazo por supervisor |
| **Pre-requisitos** | Solicitud pendiente creada |
| **Pasos** | 1. Iniciar sesión como `supervisor_1`<br>2. Ir a "Solicitudes Pendientes"<br>3. Encontrar la solicitud<br>4. Rechazar la solicitud<br>5. Agregar comentario de rechazo |
| **Resultado Esperado** | ✅ Estado cambia a "rechazada"<br>✅ `fecha_resolucion` se establece<br>✅ Notificación de rechazo enviada al solicitante<br>✅ No se crean turnos |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-FL-009: Rechazo por receptor

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-009 |
| **Descripción** | Verificar rechazo por receptor |
| **Pre-requisitos** | Solicitud pendiente creada |
| **Pasos** | 1. Iniciar sesión como `usuario_pm_1` (receptor)<br>2. Ir a "Mis Solicitudes" o notificaciones<br>3. Encontrar la solicitud<br>4. Rechazar la solicitud<br>5. Agregar comentario de rechazo |
| **Resultado Esperado** | ✅ Estado cambia a "rechazada"<br>✅ `fecha_resolucion` se establece<br>✅ Notificación de rechazo enviada al solicitante<br>✅ No se crean turnos |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-FL-010: Verificación de notificaciones de rechazo

| Campo | Valor |
|-------|-------|
| **ID** | CT-FL-010 |
| **Descripción** | Verificar que las notificaciones de rechazo se envían correctamente |
| **Pre-requisitos** | Solicitud rechazada |
| **Pasos** | 1. Iniciar sesión como solicitante<br>2. Verificar notificaciones<br>3. Verificar en BD: `SELECT * FROM solicitudes_notificacion WHERE solicitud_id = [ID] AND tipo = 'rechazo'`<br>4. Verificar email (si está configurado) |
| **Resultado Esperado** | ✅ Notificación de rechazo creada<br>✅ Contenido correcto (incluye comentario si se agregó)<br>✅ Email enviado |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 11. Casos Especiales - Cambio sobre Cambio

### CT-ESP-001: Actualización de turno existente cuando ya hay cambio previo

| Campo | Valor |
|-------|-------|
| **ID** | CT-ESP-001 |
| **Descripción** | Verificar que si ya existe un turno por cambio previo, se actualiza en lugar de crear nuevo |
| **Pre-requisitos** | `usuario_am_1` ya tiene turno con jornada PM (de cambio previo) para 2026-02-15 |
| **Pasos** | 1. Verificar en BD que existe turno para `usuario_am_1` en 2026-02-15<br>2. Crear nueva solicitud de `usuario_am_1` a `usuario_pm_2` para 2026-02-15<br>3. Aprobar la solicitud<br>4. Verificar en BD el turno |
| **Resultado Esperado** | ✅ El turno existente se actualiza (no se crea nuevo)<br>✅ Jornada actualizada a la del nuevo receptor<br>✅ Sala actualizada<br>✅ `tipo_cambio` sigue siendo 'CT' |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-ESP-002: Trazabilidad de solicitudes relacionadas

| Campo | Valor |
|-------|-------|
| **ID** | CT-ESP-002 |
| **Descripción** | Verificar que se relacionan solicitudes cuando hay cambio sobre cambio |
| **Pre-requisitos** | Solicitud previa aprobada que creó turno, nueva solicitud que actualiza ese turno |
| **Pasos** | 1. Verificar en BD: `SELECT solicitud_origen_id FROM solicitudes_solicitudcambio WHERE id = [nueva_solicitud_id]`<br>2. Verificar que `solicitud_origen` apunta a la solicitud anterior |
| **Resultado Esperado** | ✅ `solicitud_origen` está establecido<br>✅ Apunta a la solicitud anterior que creó el turno |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-ESP-003: Comentario de trazabilidad agregado correctamente

| Campo | Valor |
|-------|-------|
| **ID** | CT-ESP-003 |
| **Descripción** | Verificar que se agrega comentario de trazabilidad cuando hay cambio sobre cambio |
| **Pre-requisitos** | Solicitud que actualiza turno existente |
| **Pasos** | 1. Verificar comentario de la solicitud en BD o en la UI<br>2. Buscar texto de trazabilidad |
| **Resultado Esperado** | ✅ Comentario contiene: "Actualización: cambio previo reemplazado. Solicitud anterior ID: [ID] (aprobada el [fecha])" |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 12. Casos Especiales - First-Come, First-Served

### CT-ESP-004: Rechazo automático de otras solicitudes pendientes

| Campo | Valor |
|-------|-------|
| **ID** | CT-ESP-004 |
| **Descripción** | Verificar que al aprobar una solicitud, se rechazan automáticamente otras pendientes del mismo receptor |
| **Pre-requisitos** | Múltiples solicitudes pendientes del mismo receptor para la misma fecha |
| **Pasos** | 1. Crear 3 solicitudes pendientes de diferentes solicitantes al mismo receptor para la misma fecha<br>2. Aprobar la primera solicitud (ambos aprueban)<br>3. Verificar estado de las otras 2 solicitudes |
| **Resultado Esperado** | ✅ Las otras 2 solicitudes cambian a estado "rechazada"<br>✅ Comentario: "Rechazada automáticamente: otra solicitud fue aprobada primero (First-Come, First-Served)"<br>✅ `fecha_resolucion` establecida |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-ESP-005: Notificaciones a solicitantes afectados

| Campo | Valor |
|-------|-------|
| **ID** | CT-ESP-005 |
| **Descripción** | Verificar que se envían notificaciones a los solicitantes cuyas solicitudes fueron rechazadas automáticamente |
| **Pre-requisitos** | Solicitudes rechazadas automáticamente (de CT-ESP-004) |
| **Pasos** | 1. Iniciar sesión como cada solicitante afectado<br>2. Verificar notificaciones<br>3. Verificar en BD: `SELECT * FROM solicitudes_notificacion WHERE tipo = 'rechazo' AND solicitud_id IN ([ids_rechazadas])` |
| **Resultado Esperado** | ✅ Notificaciones creadas para cada solicitante afectado<br>✅ Contenido explica el rechazo automático<br>✅ Emails enviados |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-ESP-006: Mensaje de rechazo automático correcto

| Campo | Valor |
|-------|-------|
| **ID** | CT-ESP-006 |
| **Descripción** | Verificar que el mensaje de rechazo automático es claro y correcto |
| **Pre-requisitos** | Solicitud rechazada automáticamente |
| **Pasos** | 1. Verificar comentario de la solicitud rechazada<br>2. Verificar notificación recibida |
| **Resultado Esperado** | ✅ Mensaje: "Rechazada automáticamente: otra solicitud fue aprobada primero (First-Come, First-Served)" |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 13. Casos Especiales - Invalidación de Caché

### CT-ESP-007: Caché de turnos invalidado para ambos exploradores

| Campo | Valor |
|-------|-------|
| **ID** | CT-ESP-007 |
| **Descripción** | Verificar que se invalida el caché de turnos al aprobar solicitud |
| **Pre-requisitos** | Solicitud aprobada, caché configurado |
| **Pasos** | 1. Aprobar solicitud<br>2. Verificar en logs o código que se invalida caché<br>3. Verificar claves de caché: `turnos_mes_{explorador_id}_{año}_{mes}` |
| **Resultado Esperado** | ✅ Caché invalidado para solicitante<br>✅ Caché invalidado para receptor<br>✅ Claves correctas según formato |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | Puede requerir verificación en código o logs |

---

### CT-ESP-008: Verificación de actualización en calendario

| Campo | Valor |
|-------|-------|
| **ID** | CT-ESP-008 |
| **Descripción** | Verificar que el calendario muestra los cambios actualizados después de aprobar |
| **Pre-requisitos** | Solicitud aprobada |
| **Pasos** | 1. Iniciar sesión como solicitante<br>2. Ir a calendario/turnos<br>3. Verificar turno en la fecha de cambio<br>4. Iniciar sesión como receptor<br>5. Verificar turno en la fecha de cambio |
| **Resultado Esperado** | ✅ Calendario muestra jornada intercambiada para solicitante<br>✅ Calendario muestra jornada intercambiada para receptor<br>✅ Información actualizada (no cacheada) |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 14. Verificación de Integridad - Turnos

### CT-INT-001: Turnos creados correctamente para solicitante

| Campo | Valor |
|-------|-------|
| **ID** | CT-INT-001 |
| **Descripción** | Verificar que el turno del solicitante tiene la jornada del receptor |
| **Pre-requisitos** | Solicitud aprobada completamente |
| **Pasos** | 1. Consultar BD: `SELECT t.*, j.nombre as jornada FROM turnos_turno t JOIN turnos_jornada j ON j.id = t.jornada_id WHERE t.explorador_id = [solicitante_id] AND t.fecha = [fecha]`<br>2. Verificar jornada asignada |
| **Resultado Esperado** | ✅ Turno existe<br>✅ Jornada = jornada del receptor (PM si receptor es PM)<br>✅ Sala = sala del receptor |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-INT-002: Turnos creados correctamente para receptor

| Campo | Valor |
|-------|-------|
| **ID** | CT-INT-002 |
| **Descripción** | Verificar que el turno del receptor tiene la jornada del solicitante |
| **Pre-requisitos** | Solicitud aprobada completamente |
| **Pasos** | 1. Consultar BD: `SELECT t.*, j.nombre as jornada FROM turnos_turno t JOIN turnos_jornada j ON j.id = t.jornada_id WHERE t.explorador_id = [receptor_id] AND t.fecha = [fecha]`<br>2. Verificar jornada asignada |
| **Resultado Esperado** | ✅ Turno existe<br>✅ Jornada = jornada del solicitante (AM si solicitante es AM)<br>✅ Sala = sala del solicitante |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-INT-003: Salas asignadas correctamente

| Campo | Valor |
|-------|-------|
| **ID** | CT-INT-003 |
| **Descripción** | Verificar que las salas se intercambian correctamente |
| **Pre-requisitos** | Solicitud aprobada, ambos usuarios tienen salas asignadas |
| **Pasos** | 1. Consultar BD las salas de ambos usuarios<br>2. Verificar en los turnos creados que las salas están intercambiadas |
| **Resultado Esperado** | ✅ Solicitante tiene sala del receptor<br>✅ Receptor tiene sala del solicitante |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-INT-004: Tipo de cambio marcado como 'CT'

| Campo | Valor |
|-------|-------|
| **ID** | CT-INT-004 |
| **Descripción** | Verificar que los turnos tienen `tipo_cambio = 'CT'` |
| **Pre-requisitos** | Solicitud aprobada |
| **Pasos** | 1. Consultar BD: `SELECT tipo_cambio FROM turnos_turno WHERE explorador_id IN ([solicitante_id], [receptor_id]) AND fecha = [fecha]` |
| **Resultado Esperado** | ✅ Ambos turnos tienen `tipo_cambio = 'CT'` |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 15. Verificación de Integridad - Notificaciones

### CT-INT-005: Notificaciones creadas en base de datos

| Campo | Valor |
|-------|-------|
| **ID** | CT-INT-005 |
| **Descripción** | Verificar que todas las notificaciones se crean correctamente en BD |
| **Pre-requisitos** | Solicitud creada y/o aprobada/rechazada |
| **Pasos** | 1. Consultar BD: `SELECT * FROM solicitudes_notificacion WHERE solicitud_id = [ID] ORDER BY fecha_creacion`<br>2. Verificar destinatarios y tipos |
| **Resultado Esperado** | ✅ Notificación de creación para receptor<br>✅ Notificación de creación para supervisor<br>✅ Notificaciones de aprobación/rechazo según corresponda |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

### CT-INT-006: Emails enviados correctamente

| Campo | Valor |
|-------|-------|
| **ID** | CT-INT-006 |
| **Descripción** | Verificar que los emails se envían correctamente (si está configurado) |
| **Pre-requisitos** | Email configurado en el sistema |
| **Pasos** | 1. Verificar logs de email<br>2. Verificar bandejas de entrada de los usuarios<br>3. Verificar que no hay errores de envío |
| **Resultado Esperado** | ✅ Emails enviados a receptor<br>✅ Emails enviados a supervisor<br>✅ Emails de aprobación/rechazo enviados<br>✅ Sin errores de SMTP |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | Requiere configuración de email funcional |

---

### CT-INT-007: Contenido de notificaciones correcto

| Campo | Valor |
|-------|-------|
| **ID** | CT-INT-007 |
| **Descripción** | Verificar que el contenido de las notificaciones es correcto y completo |
| **Pre-requisitos** | Notificaciones creadas |
| **Pasos** | 1. Revisar notificaciones en la UI<br>2. Verificar título, mensaje, tipo<br>3. Verificar que incluyen información relevante (fecha, usuarios, etc.) |
| **Resultado Esperado** | ✅ Títulos descriptivos<br>✅ Mensajes claros y completos<br>✅ Información correcta (fechas, nombres, etc.)<br>✅ Tipos correctos |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

---

## 📊 Resumen de Ejecución

### Estadísticas

| Categoría | Total | ✅ PASS | ❌ FAIL | ⚠️ WARNING | ⬜ Sin Ejecutar |
|----------|-------|---------|---------|------------|-----------------|
| Validaciones de Empleados | 3 | | | | |
| Validaciones de Jornadas | 3 | | | | |
| Validaciones de Fecha | 6 | | | | |
| Validaciones de Duplicidad | 2 | | | | |
| Validaciones de Dobladas | 2 | | | | |
| Límite de Cambios | 3 | | | | |
| Flujo Completo - Creación | 3 | | | | |
| Flujo Completo - Aprobación | 4 | | | | |
| Flujo Completo - Rechazo | 3 | | | | |
| Casos Especiales | 6 | | | | |
| Verificación de Integridad | 7 | | | | |
| **TOTAL** | **42** | | | | |

### Notas Generales

**Fecha de creación del documento**: [Fecha]
**Versión**: 1.0
**Última actualización**: [Fecha]

**Observaciones generales**:
- [Agregar observaciones aquí]

**Problemas encontrados**:
- [Listar problemas encontrados]

**Mejoras sugeridas**:
- [Listar mejoras sugeridas]

---

## 🔍 Guía de Uso

### Cómo Usar Este Manual

Este documento está diseñado para realizar pruebas manuales sistemáticas del sistema de Cambio de Turno Sencillo. Sigue estos pasos:

1. **Preparación**: Completar la sección de preparación con usuarios y datos reales del sistema
2. **Ejecución sistemática**: Ejecutar casos de prueba en orden, marcando el estado de cada uno
3. **Registro detallado**: Completar "Resultado Real" y "Observaciones" para cada caso
4. **Análisis**: Revisar el resumen de ejecución para identificar áreas problemáticas
5. **Seguimiento**: Usar este documento para rastrear correcciones y mejoras

---

## 📖 Ejemplo Práctico: Cómo Ejecutar una Prueba

### Ejemplo: CT-004 - Jornadas Contrarias Obligatorias

Te muestro cómo ejecutar una prueba completa paso a paso:

#### **Paso 1: Preparar el Entorno**

Antes de empezar, necesitas:
- ✅ Usuarios reales del sistema (ej: `manuel.moreno` con jornada AM, `yesika.rodriguez` con jornada PM)
- ✅ Fecha válida para probar (ej: `2026-02-15`)
- ✅ Acceso a la aplicación web
- ✅ Acceso a base de datos (opcional, para verificar)

**Acción**: Actualiza la tabla de usuarios en la sección 1.1 con usuarios reales:
```
| Usuario | Jornada Base | Rol | Estado | Notas |
|---------|--------------|-----|--------|-------|
| `manuel.moreno` | AM | Explorador | Activo | Para pruebas como solicitante AM |
| `yesika.rodriguez` | PM | Explorador | Activo | Para pruebas como receptor PM |
```

#### **Paso 2: Leer el Caso de Prueba**

Busca el caso **CT-004** en la sección "3. Validaciones de Jornadas". Verás:

| Campo | Valor |
|-------|-------|
| **ID** | CT-004 |
| **Descripción** | Verificar que solo se muestran exploradores con jornada contraria |
| **Pre-requisitos** | `usuario_am_1` con jornada AM, `usuario_pm_1` con jornada PM para la fecha |
| **Pasos** | 1. Iniciar sesión como `usuario_am_1` (AM)<br>2. Ir a "Solicitar Cambio de Turno"<br>3. Seleccionar fecha válida (ej: 2026-02-15)<br>4. Revisar lista de exploradores disponibles |
| **Resultado Esperado** | ✅ Solo aparecen exploradores con jornada PM en la lista<br>❌ No aparecen exploradores con jornada AM |
| **Resultado Real** | |
| **Estado** | ⬜ Sin ejecutar / ✅ PASS / ❌ FAIL / ⚠️ WARNING |
| **Observaciones** | |

#### **Paso 3: Ejecutar los Pasos**

**3.1. Iniciar sesión**
- Abre el navegador
- Ve a la URL de la aplicación
- Inicia sesión como `manuel.moreno` (que tiene jornada AM)

**3.2. Navegar al formulario**
- Busca el menú "Solicitudes" o "Cambio de Turno"
- Haz clic en "Solicitar Cambio de Turno" o similar

**3.3. Seleccionar fecha**
- En el calendario, selecciona `2026-02-15` (o la fecha que preparaste)
- Verifica que la fecha se seleccionó correctamente

**3.4. Revisar lista de exploradores**
- Observa la lista desplegable o select de "Explorador Receptor"
- **Anota mentalmente o en papel**: ¿Qué usuarios aparecen?

#### **Paso 4: Comparar con Resultado Esperado**

**Resultado Esperado**:
- ✅ Solo deben aparecer usuarios con jornada **PM**
- ❌ NO deben aparecer usuarios con jornada **AM**

**Verificación**:
- Si `yesika.rodriguez` (PM) aparece → ✅ Correcto
- Si `manuel.moreno` (AM) aparece → ❌ Incorrecto
- Si otros usuarios AM aparecen → ❌ Incorrecto

#### **Paso 5: Registrar el Resultado**

Ahora llena la tabla en el documento:

**Si todo funcionó correctamente:**
```
| **Resultado Real** | Solo aparecieron usuarios con jornada PM. Manuel Moreno (AM) no apareció en la lista. |
| **Estado** | ✅ PASS |
| **Observaciones** | La validación funciona correctamente. El sistema filtra correctamente por jornada contraria. |
```

**Si hubo un problema:**
```
| **Resultado Real** | Aparecieron usuarios con jornada AM en la lista (Manuel Moreno apareció). Esto es incorrecto. |
| **Estado** | ❌ FAIL |
| **Observaciones** | El sistema no está filtrando correctamente por jornada contraria. Se debe revisar la lógica de `get_empleados_disponibles` en el backend. |
```

**Si funcionó parcialmente:**
```
| **Resultado Real** | La mayoría de usuarios PM aparecen, pero falta uno que debería aparecer. |
| **Estado** | ⚠️ WARNING |
| **Observaciones** | Funciona en general, pero hay un caso específico que no se está manejando correctamente. Revisar si ese usuario tiene alguna condición especial. |
```

#### **Paso 6: Continuar con el Siguiente Caso**

Una vez completado CT-004, pasa al siguiente caso (CT-005) y repite el proceso.

---

### 📝 Plantilla de Registro Rápido

Para agilizar el proceso, puedes usar esta plantilla mientras pruebas:

```
Caso: CT-XXX
Fecha de prueba: [Fecha]
Ejecutado por: [Tu nombre]

Pasos ejecutados:
1. [✓] Paso 1 completado
2. [✓] Paso 2 completado
3. [✓] Paso 3 completado

Resultado observado:
- [Descripción breve de lo que pasó]

Comparación:
- [✓] Cumple con resultado esperado
- [✗] No cumple con resultado esperado

Estado final: [PASS/FAIL/WARNING]

Notas: [Cualquier observación adicional]
```

---

### 🎯 Estrategia Recomendada de Ejecución

#### **Opción 1: Ejecución Completa (Recomendada para primera vez)**
1. Empieza desde CT-001 y ejecuta todos los casos en orden
2. Marca cada caso como completado
3. Al final, revisa el resumen de estadísticas

#### **Opción 2: Ejecución por Categorías (Recomendada para pruebas específicas)**
1. Si quieres probar solo validaciones → Ejecuta secciones 2-7
2. Si quieres probar el flujo completo → Ejecuta secciones 8-10
3. Si quieres probar casos especiales → Ejecuta secciones 11-13

#### **Opción 3: Ejecución por Prioridad**
1. Primero: Casos críticos (validaciones básicas) - Secciones 2-4
2. Segundo: Flujo completo - Secciones 8-10
3. Tercero: Casos especiales - Secciones 11-13
4. Cuarto: Verificación de integridad - Secciones 14-15

---

### 🔍 Verificación en Base de Datos (Opcional pero Recomendado)

Para casos que requieren verificar datos en BD, usa las consultas SQL de la sección 1.4:

**Ejemplo para CT-004:**
```sql
-- Verificar jornada de manuel.moreno en 2026-02-15
SELECT e.nombre, e.apellido, j.nombre as jornada
FROM empleados_empleado e
JOIN turnos_jornadaempleado je ON je.empleado_id = e.id
JOIN turnos_jornada j ON j.id = je.jornada_id
WHERE e.user_id = (SELECT id FROM auth_user WHERE username = 'manuel.moreno')
AND je.fecha_inicio <= '2026-02-15'
AND (je.fecha_fin IS NULL OR je.fecha_fin >= '2026-02-15');
```

Esto te confirmará que el usuario tiene jornada AM para esa fecha.

---

### ⚠️ Consejos Importantes

1. **Sé específico en "Resultado Real"**: No escribas solo "funcionó" o "no funcionó". Describe exactamente qué pasó.

2. **Toma capturas de pantalla**: Si encuentras un error, toma capturas para documentarlo mejor.

3. **Anota IDs de solicitudes**: Si creas solicitudes durante las pruebas, anota sus IDs para referencia futura.

4. **No modifiques datos mientras pruebas**: Si necesitas datos específicos, créalos antes de empezar.

5. **Actualiza el resumen al final**: Al terminar una sección, actualiza las estadísticas en la sección "Resumen de Ejecución".

---

### 📊 Ejemplo de Resumen Completado

Al final de ejecutar varios casos, tu resumen podría verse así:

```
| Categoría | Total | ✅ PASS | ❌ FAIL | ⚠️ WARNING | ⬜ Sin Ejecutar |
|----------|-------|---------|---------|------------|-----------------|
| Validaciones de Empleados | 3 | 2 | 1 | 0 | 0 |
| Validaciones de Jornadas | 3 | 3 | 0 | 0 | 0 |
| Validaciones de Fecha | 5 | 4 | 0 | 1 | 0 |
...
```

Esto te ayudará a identificar rápidamente qué áreas necesitan atención.

---

**Fin del Documento**

