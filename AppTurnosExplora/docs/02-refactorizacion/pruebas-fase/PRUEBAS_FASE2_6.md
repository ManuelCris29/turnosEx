# PRUEBAS FASE 2.6: Cambio sobre Cambio - Escenario Completo

## Objetivo
Verificar que todo el flujo de cambios múltiples funciona correctamente, incluyendo:
- Creación de turnos iniciales
- Actualización de turnos existentes
- Límite de cambios
- Trazabilidad e historial
- Advertencias en UI

---

## Escenario Principal: Cambio sobre Cambio

### Configuración Inicial
- **Empleado A**: Jornada predeterminada AM
- **Empleado B**: Jornada predeterminada PM
- **Empleado C**: Jornada predeterminada PM
- **Fecha de prueba**: 2024-12-20

---

## Caso de Prueba 1: Primer Cambio (A→B)

### Paso 1: Crear Solicitud A→B
**Acción:**
1. Iniciar sesión como Empleado A
2. Crear solicitud de cambio de turno
3. Fecha: 2024-12-20
4. Receptor: Empleado B
5. Enviar solicitud

**Verificación:**
- ✅ Solicitud creada con estado "pendiente"
- ✅ No existe Turno para A en fecha 2024-12-20
- ✅ No existe Turno para B en fecha 2024-12-20

### Paso 2: Aprobar Solicitud A→B
**Acción:**
1. Aprobar como receptor (B)
2. Aprobar como supervisor (supervisor de A)

**Verificación:**
- ✅ Solicitud cambia a estado "aprobada"
- ✅ Se crea Turno para A:
  - `explorador`: A
  - `fecha`: 2024-12-20
  - `jornada`: PM (jornada de B)
  - `tipo_cambio`: 'CT'
- ✅ Se crea Turno para B:
  - `explorador`: B
  - `fecha`: 2024-12-20
  - `jornada`: AM (jornada de A)
  - `tipo_cambio`: 'CT'
- ✅ `solicitud.turno_origen` = Turno de A
- ✅ `solicitud.turno_destino` = Turno de B

**Consulta SQL:**
```sql
SELECT t.id, t.explorador_id, e.nombre, t.fecha, j.nombre as jornada, t.tipo_cambio
FROM turnos_turno t
JOIN empleados_empleado e ON t.explorador_id = e.id
JOIN turnos_jornada j ON t.jornada_id = j.id
WHERE t.fecha = '2024-12-20'
  AND t.explorador_id IN ([ID_A], [ID_B])
ORDER BY t.explorador_id;
```

---

## Caso de Prueba 2: Segundo Cambio (A→C) - Cambio sobre Cambio

### Paso 3: Verificar Jornada Actual de A
**Acción:**
- Consultar jornada de A para fecha 2024-12-20

**Verificación:**
- ✅ `get_jornada_explorador_fecha(A, '2024-12-20')` retorna PM (del Turno, no de asignación)

### Paso 4: Crear Solicitud A→C
**Acción:**
1. Iniciar sesión como Empleado A
2. Crear solicitud de cambio de turno
3. Fecha: 2024-12-20 (misma fecha)
4. Receptor: Empleado C
5. Enviar solicitud

**Verificación:**
- ✅ Solicitud creada con estado "pendiente"
- ✅ Sistema muestra compañeros con jornada contraria a PM (debe mostrar AM)
- ✅ Empleado C aparece en la lista (tiene PM, contraria a PM actual de A)

**Nota:** Esto verifica que `get_empleados_jornada_contraria` usa la jornada actual del Turno.

### Paso 5: Verificar Advertencia en UI
**Acción:**
- Al seleccionar fecha 2024-12-20 en el formulario

**Verificación:**
- ✅ Se muestra advertencia: "Ya tienes un cambio aprobado para esta fecha..."
- ✅ Detalles muestran:
  - Jornada actual: PM
  - Compañero: B
  - Fecha de aprobación
  - ID de solicitud anterior

### Paso 6: Aprobar Solicitud A→C
**Acción:**
1. Aprobar como receptor (C)
2. Aprobar como supervisor (supervisor de A)

**Verificación:**
- ✅ Solicitud cambia a estado "aprobada"
- ✅ **Turno de A se ACTUALIZA** (no se crea nuevo):
  - `explorador`: A
  - `fecha`: 2024-12-20
  - `jornada`: PM (jornada de C) - **ACTUALIZADO**
  - `tipo_cambio`: 'CT'
  - **Mismo ID de turno que antes**
- ✅ Se crea Turno para C:
  - `explorador`: C
  - `fecha`: 2024-12-20
  - `jornada`: PM (jornada actual de A, que era PM)
  - `tipo_cambio`: 'CT'
- ✅ **Turno de B NO cambia**:
  - `explorador`: B
  - `fecha`: 2024-12-20
  - `jornada`: AM (permanece igual)
- ✅ `solicitud.solicitud_origen` = Solicitud A→B (trazabilidad)
- ✅ `solicitud.comentario` contiene: "Actualización: cambio previo reemplazado. Solicitud anterior ID: {ID_A→B}..."

**Consulta SQL:**
```sql
-- Verificar que el turno de A tiene el mismo ID pero jornada actualizada
SELECT t.id, t.explorador_id, e.nombre, t.fecha, j.nombre as jornada, t.tipo_cambio
FROM turnos_turno t
JOIN empleados_empleado e ON t.explorador_id = e.id
JOIN turnos_jornada j ON t.jornada_id = j.id
WHERE t.fecha = '2024-12-20'
  AND t.explorador_id IN ([ID_A], [ID_B], [ID_C])
ORDER BY t.explorador_id;
```

**Verificación de Historial:**
```sql
-- Verificar historial del turno de A
SELECT history_date, history_type, jornada_id, tipo_cambio
FROM turnos_turno_history
WHERE id = [TURNO_A_ID]
ORDER BY history_date;
```

**Resultado Esperado:**
- 2 registros en historial:
  1. `history_type` = '+' (creación inicial con PM de B)
  2. `history_type` = '~' (actualización con PM de C)

---

## Caso de Prueba 3: Límite de Cambios

### Paso 7: Crear Tercer Cambio (A→D)
**Acción:**
1. Crear solicitud A→D para fecha 2024-12-20
2. Aprobar solicitud A→D

**Verificación:**
- ✅ Solicitud se aprueba correctamente
- ✅ Turno de A se actualiza nuevamente

### Paso 8: Intentar Cuarto Cambio (A→E) - Debe Fallar
**Acción:**
1. Crear solicitud A→E para fecha 2024-12-20
2. Intentar aprobar solicitud A→E

**Verificación:**
- ❌ Aprobación falla con error: "Se ha alcanzado el límite de cambios para esta fecha..."
- ✅ Solicitud permanece en estado "pendiente" o se rechaza
- ✅ No se crea/actualiza Turno para A

**Consulta:**
```python
from solicitudes.services.solicitud_service import SolicitudService
count = SolicitudService.contar_cambios_explorador_fecha([ID_A], '2024-12-20')
# Debe retornar 3 (A→B, A→C, A→D)
```

---

## Caso de Prueba 4: First-Come, First-Served

### Paso 9: Múltiples Solicitudes para Mismo Receptor
**Acción:**
1. Crear solicitud F→B para fecha 2024-12-20 (B ya tiene turno)
2. Crear solicitud G→B para fecha 2024-12-20
3. Aprobar solicitud F→B

**Verificación:**
- ✅ Solicitud F→B se aprueba
- ✅ Solicitud G→B se rechaza automáticamente
- ✅ Solicitud G→B tiene estado "rechazada"
- ✅ Solicitud G→B tiene comentario: "Rechazada automáticamente: otra solicitud fue aprobada primero (First-Come, First-Served)"
- ✅ Se crea notificación para G sobre el rechazo automático

---

## Verificaciones Adicionales

### Verificación 1: Integridad de Datos
- ✅ No hay turnos duplicados para mismo explorador/fecha
- ✅ Todas las solicitudes aprobadas tienen `turno_origen` y `turno_destino` asignados
- ✅ Las relaciones `solicitud_origen` están correctamente establecidas

### Verificación 2: Performance
- ✅ Las consultas usan índices (verificar con `EXPLAIN`)
- ✅ No hay N+1 queries en `get_empleados_jornada_contraria`
- ✅ Las transacciones son atómicas (no hay estados inconsistentes)

### Verificación 3: Logs
- ✅ Los logs muestran correctamente:
  - "FASE 2.1: Actualizando turno existente..."
  - "FASE 2.3: Validación de límite exitosa..."
  - "FASE 2.4: Solicitud anterior encontrada..."
  - "FASE 1.14: Rechazadas X solicitudes pendientes..."

---

## Comando de Prueba Automatizada

Ejecutar:
```bash
python manage.py test_cambio_sobre_cambio
```

Este comando ejecutará todos los casos de prueba y generará un reporte.

---

## Resultado Esperado Final

### Estado de Turnos para 2024-12-20:
- **A**: Turno con jornada PM (último cambio: A→C o A→D)
- **B**: Turno con jornada AM (del cambio A→B, no afectado por cambios posteriores)
- **C**: Turno con jornada PM (del cambio A→C)
- **D**: Turno con jornada PM (del cambio A→D, si se aprobó)

### Estado de Solicitudes:
- **A→B**: Aprobada, con turnos asignados
- **A→C**: Aprobada, con turnos asignados, `solicitud_origen` = A→B
- **A→D**: Aprobada (si límite permite), con turnos asignados, `solicitud_origen` = A→C
- **A→E**: Rechazada o pendiente (si límite excedido)
- **F→B**: Aprobada
- **G→B**: Rechazada automáticamente

---

## Criterios de Éxito

✅ Todos los casos de prueba pasan
✅ No hay errores en logs
✅ Integridad de datos verificada
✅ Performance aceptable (<500ms por operación)
✅ Trazabilidad completa
✅ Límite de cambios funciona
✅ First-Come, First-Served funciona
✅ Advertencias en UI funcionan

