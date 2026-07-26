# PRUEBAS FASE 1.16: First-Come, First-Served - Escenario Completo
## Verificación del Flujo First-Come, First-Served

---

## 📋 Objetivo

Verificar que el sistema implementa correctamente la lógica First-Come, First-Served:
- Múltiples solicitantes pueden enviar solicitudes al mismo receptor para la misma fecha
- Cuando se aprueba la primera solicitud, las demás se **RECHAZAN automáticamente** (estado = 'rechazada')
- Se crean notificaciones para los solicitantes afectados
- No se pueden aprobar solicitudes ya rechazadas

**⚠️ DIFERENCIA IMPORTANTE:**
- **Rechazada** = El sistema o un usuario rechazó la solicitud (no se puede aprobar después)
- **Cancelada** = El solicitante canceló su propia solicitud (solo el solicitante puede cancelar)
- En First-Come, First-Served, las solicitudes se **RECHAZAN automáticamente**, no se cancelan

---

## ✅ Verificación de Código

### Revisión de Implementación
- [x] FASE 1.13: Validación permite múltiples solicitantes para mismo receptor/fecha
- [x] FASE 1.14: Lógica de rechazo automático implementada en `aplicar_cambios`
- [x] FASE 1.15: Notificaciones creadas para solicitantes afectados
- [x] Transacciones atómicas para garantizar integridad
- [x] Logging para debugging

---

## 🧪 Caso de Prueba Principal: Escenario First-Come, First-Served

### Preparación

**Requisitos:**
- 4 empleados activos: A, B, C, X
- A, B, C tienen jornada AM (o PM)
- X tiene jornada contraria (PM si A/B/C son AM, o AM si A/B/C son PM)
- Fecha de prueba: 2024-12-20 (o cualquier fecha futura)

**Configuración inicial:**
1. Verificar que A, B, C tienen jornada contraria a X
2. Verificar que no hay solicitudes pendientes para X en la fecha de prueba
3. Verificar que no hay turnos creados para A, B, C, X en la fecha de prueba

---

### Paso 1: Crear Múltiples Solicitudes

**Objetivo:** Verificar que se pueden crear múltiples solicitudes para el mismo receptor/fecha

**Pasos:**
1. Iniciar sesión como empleado A
2. Ir a "Crear Solicitud de Cambio de Turno"
3. Seleccionar tipo: "Cambio Turno"
4. Seleccionar fecha: 2024-12-20
5. Seleccionar receptor: X
6. Agregar comentario opcional: "Solicitud A→X"
7. Enviar solicitud
8. **Verificar:** Solicitud creada exitosamente con estado "pendiente"

9. Iniciar sesión como empleado B
10. Repetir pasos 2-7 con comentario: "Solicitud B→X"
11. **Verificar:** Solicitud creada exitosamente con estado "pendiente"

12. Iniciar sesión como empleado C
13. Repetir pasos 2-7 con comentario: "Solicitud C→X"
14. **Verificar:** Solicitud creada exitosamente con estado "pendiente"

**Resultado Esperado:**
- ✅ 3 solicitudes creadas: A→X, B→X, C→X
- ✅ Todas con estado "pendiente"
- ✅ Todas para la misma fecha: 2024-12-20
- ✅ Todas con el mismo receptor: X

**Verificación en Base de Datos:**
```sql
SELECT id, explorador_solicitante_id, explorador_receptor_id, 
       fecha_cambio_turno, estado, fecha_solicitud
FROM solicitudes_solicitudcambio
WHERE fecha_cambio_turno = '2024-12-20'
  AND explorador_receptor_id = [ID_DE_X]
ORDER BY fecha_solicitud;
```

**Resultado Esperado:**
- 3 registros con estado 'pendiente'
- Ordenados por fecha_solicitud (primera = A, segunda = B, tercera = C)

---

### Paso 2: Aprobar Primera Solicitud (A→X)

**Objetivo:** Verificar que al aprobar la primera solicitud, se crean los turnos y se rechazan las demás

**Pasos:**
1. Iniciar sesión como receptor X (o supervisor de A)
2. Ir a "Solicitudes Pendientes" o "Notificaciones"
3. Localizar la solicitud A→X (primera en orden cronológico)
4. Aprobar la solicitud A→X
   - Si es receptor: Aprobar como receptor
   - Si es supervisor: Aprobar como supervisor
   - Si ambos: Aprobar ambos
5. **Verificar:** Solicitud A→X cambia a estado "aprobada"

**Resultado Esperado:**
- ✅ Solicitud A→X cambia a estado "aprobada"
- ✅ Se crean 2 turnos en tabla `turnos_turno`:
  - Turno para A con jornada de X
  - Turno para X con jornada de A
- ✅ Solicitudes B→X y C→X cambian automáticamente a estado "rechazada"
- ✅ Comentario en B→X y C→X: "Rechazada automáticamente: otra solicitud fue aprobada primero (First-Come, First-Served)"

**Verificación en Base de Datos - Turnos:**
```sql
SELECT id, explorador_id, fecha, jornada_id, tipo_cambio
FROM turnos_turno
WHERE fecha = '2024-12-20'
  AND explorador_id IN ([ID_DE_A], [ID_DE_X])
ORDER BY explorador_id;
```

**Resultado Esperado:**
- 2 registros:
  - A con jornada de X
  - X con jornada de A
- Ambos con `tipo_cambio = 'CT'`

**Verificación en Base de Datos - Solicitudes:**
```sql
SELECT id, explorador_solicitante_id, estado, comentario, fecha_resolucion
FROM solicitudes_solicitudcambio
WHERE fecha_cambio_turno = '2024-12-20'
  AND explorador_receptor_id = [ID_DE_X]
ORDER BY fecha_solicitud;
```

**Resultado Esperado:**
- A→X: estado = 'aprobada', turno_origen y turno_destino no nulos
- B→X: estado = 'rechazada', comentario contiene "Rechazada automáticamente", fecha_resolucion no nula
- C→X: estado = 'rechazada', comentario contiene "Rechazada automáticamente", fecha_resolucion no nula

---

### Paso 3: Verificar Notificaciones

**Objetivo:** Verificar que se crean notificaciones para los solicitantes afectados

**Pasos:**
1. Iniciar sesión como empleado B
2. Ir a "Notificaciones" o "Mis Notificaciones"
3. **Verificar:** Existe notificación de rechazo automático

4. Iniciar sesión como empleado C
5. Ir a "Notificaciones" o "Mis Notificaciones"
6. **Verificar:** Existe notificación de rechazo automático

7. Iniciar sesión como supervisor de B (si existe)
8. Ir a "Notificaciones"
9. **Verificar:** Existe notificación sobre rechazo de solicitud de B

10. Iniciar sesión como supervisor de C (si existe)
11. Ir a "Notificaciones"
12. **Verificar:** Existe notificación sobre rechazo de solicitud de C

**Resultado Esperado:**
- ✅ Notificación para B con título: "Solicitud Rechazada Automáticamente - Cambio Turno"
- ✅ Notificación para C con título: "Solicitud Rechazada Automáticamente - Cambio Turno"
- ✅ Mensaje explica: "ha sido rechazada automáticamente porque otra solicitud para el mismo receptor y fecha fue aprobada primero (First-Come, First-Served)"
- ✅ Notificaciones para supervisores de B y C (si existen)

**Verificación en Base de Datos:**
```sql
SELECT id, destinatario_id, tipo, titulo, mensaje, solicitud_id
FROM solicitudes_notificacion
WHERE tipo = 'rechazo'
  AND solicitud_id IN (
    SELECT id FROM solicitudes_solicitudcambio
    WHERE fecha_cambio_turno = '2024-12-20'
      AND explorador_receptor_id = [ID_DE_X]
      AND estado = 'rechazada'
  )
ORDER BY destinatario_id;
```

**Resultado Esperado:**
- Notificaciones para B y C (solicitantes)
- Notificaciones para supervisores de B y C (si existen)
- Todas con tipo = 'rechazo'
- Título contiene "Rechazada Automáticamente"

---

### Paso 4: Intentar Aprobar Solicitud Rechazada

**Objetivo:** Verificar que no se puede aprobar una solicitud que ya fue rechazada automáticamente

**⚠️ ACLARACIÓN IMPORTANTE:**
- Cuando se aprueba la solicitud A→X (Paso 2), las otras solicitudes (B→X y C→X) se **RECHAZAN automáticamente** (estado = 'rechazada')
- **NO se cancelan** (cancelada es diferente: solo el solicitante puede cancelar su propia solicitud)
- Una vez rechazada, la solicitud NO puede ser aprobada después
- Este paso verifica que el sistema protege contra intentos de aprobar solicitudes ya rechazadas

**Pasos:**
1. Iniciar sesión como receptor X (o supervisor de B)
2. Ir a "Solicitudes Pendientes" o "Mis Solicitudes"
3. Intentar localizar la solicitud B→X
4. **Verificar:** La solicitud B→X NO aparece en "pendientes" (está rechazada automáticamente)
5. Si se puede acceder a la solicitud B→X (por ID directo o desde historial):
   - Intentar aprobar la solicitud
   - **Verificar:** Sistema rechaza la acción con mensaje apropiado

**Resultado Esperado:**
- ✅ Solicitud B→X no aparece en lista de pendientes (porque está 'rechazada', no 'pendiente')
- ✅ Si se intenta aprobar, sistema muestra error: "La solicitud no está pendiente" o "Esta solicitud ya fue rechazada"
- ✅ No se crean turnos adicionales
- ✅ Estado de B→X permanece como "rechazada"
- ✅ El receptor X ya no puede aprobar B→X porque ya está rechazada automáticamente

---

### Paso 5: Verificar Integridad de Datos

**Objetivo:** Verificar que no hay duplicados ni inconsistencias

**Verificaciones:**

1. **Turnos únicos por explorador/fecha:**
```sql
SELECT explorador_id, fecha, COUNT(*) as count
FROM turnos_turno
WHERE fecha = '2024-12-20'
  AND explorador_id IN ([ID_DE_A], [ID_DE_B], [ID_DE_C], [ID_DE_X])
GROUP BY explorador_id, fecha
HAVING COUNT(*) > 1;
```

**Resultado Esperado:**
- ✅ No hay duplicados (solo A y X tienen turnos, 1 cada uno)

2. **Solicitudes con estados consistentes:**
```sql
SELECT estado, COUNT(*) as count
FROM solicitudes_solicitudcambio
WHERE fecha_cambio_turno = '2024-12-20'
  AND explorador_receptor_id = [ID_DE_X]
GROUP BY estado;
```

**Resultado Esperado:**
- ✅ 1 solicitud con estado 'aprobada' (A→X)
- ✅ 2 solicitudes con estado 'rechazada' (B→X, C→X)
- ✅ 0 solicitudes con estado 'pendiente'

3. **Referencias de turnos:**
```sql
SELECT id, explorador_solicitante_id, turno_origen_id, turno_destino_id, estado
FROM solicitudes_solicitudcambio
WHERE fecha_cambio_turno = '2024-12-20'
  AND explorador_receptor_id = [ID_DE_X];
```

**Resultado Esperado:**
- ✅ A→X: turno_origen_id y turno_destino_id no nulos
- ✅ B→X y C→X: turno_origen_id y turno_destino_id nulos

---

## 🔍 Verificación de Logs

**Revisar logs de la aplicación para verificar:**

1. **Log de rechazo automático:**
```
FASE 1.14-1.15: Rechazadas 2 solicitudes pendientes para receptor [ID] en fecha 2024-12-20. Notificaciones creadas.
```

2. **Log de creación de turnos:**
- Verificar que se crearon 2 turnos (A y X)

3. **Log de creación de notificaciones:**
- Verificar que se crearon notificaciones para B y C

---

## ✅ Criterios de Éxito

- [x] Se pueden crear múltiples solicitudes para mismo receptor/fecha
- [x] Al aprobar primera solicitud, se crean turnos correctamente
- [x] Otras solicitudes se rechazan automáticamente
- [x] Se crean notificaciones para solicitantes afectados
- [x] No se pueden aprobar solicitudes ya rechazadas
- [x] No hay duplicados en turnos
- [x] Estados de solicitudes son consistentes
- [x] Logs registran las operaciones correctamente

---

## 📝 Notas Adicionales

### Casos Edge a Considerar

1. **Solicitudes creadas simultáneamente:**
   - Si A, B, C crean solicitudes al mismo tiempo, el orden se determina por `fecha_solicitud` (timestamp)
   - La primera en ser aprobada gana

2. **Aprobación simultánea:**
   - Gracias a `select_for_update()` y transacciones atómicas, no se pueden aprobar dos solicitudes simultáneamente
   - Solo la primera aprobación tendrá éxito

3. **Cancelación antes de aprobación:**
   - Si A cancela su solicitud antes de ser aprobada, B o C pueden ser aprobadas
   - El sistema sigue el principio First-Come, First-Served

---

## 🐛 Problemas Conocidos

Ninguno hasta el momento.

---

## 📅 Fecha de Prueba

**Fecha:** _______________

**Ejecutado por:** _______________

**Resultado:** [ ] ✅ Éxito  [ ] ❌ Fallo

**Observaciones:**
_________________________________________________
_________________________________________________
_________________________________________________

