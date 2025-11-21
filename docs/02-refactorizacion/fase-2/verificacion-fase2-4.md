# VERIFICACIÓN FASE 2.4: Trazabilidad - Mejorar Historial

## Objetivo
Verificar que el sistema mantiene un registro completo de todos los cambios, incluyendo referencias a solicitudes anteriores cuando se actualiza un turno existente.

## Cambios Implementados

### 1. Búsqueda de Solicitud Anterior
**Archivo:** `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py` (líneas 240-244, 311-315)

**Funcionalidad:**
- Cuando se actualiza un turno existente, el sistema busca la solicitud anterior que creó ese turno
- Busca en `SolicitudCambio` donde `turno_origen` o `turno_destino` apuntan al turno existente
- Solo considera solicitudes con `estado='aprobada'`
- Ordena por `fecha_resolucion` descendente para obtener la más reciente

**Código:**
```python
solicitud_anterior_solicitante = SolicitudCambio.objects.filter(
    Q(turno_origen=turno_solicitante_existente) | Q(turno_destino=turno_solicitante_existente),
    estado='aprobada'
).order_by('-fecha_resolucion').first()
```

### 2. Comentarios de Trazabilidad
**Archivo:** `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py` (líneas 246-270, 320-341)

**Funcionalidad:**
- Si se encuentra una solicitud anterior, se agrega un comentario en la solicitud actual:
  - Formato: "Actualización: cambio previo reemplazado. Solicitud anterior ID: {id} (aprobada el {fecha})"
- Si no se encuentra, se agrega: "Actualización: cambio previo reemplazado (solicitud anterior no encontrada en el sistema)"
- Los comentarios se agregan tanto para el solicitante como para el receptor (si aplica)
- Los comentarios se concatenan con los comentarios existentes usando `\n\n` como separador

**Ejemplo de comentario:**
```
Actualización: cambio previo reemplazado. Solicitud anterior ID: 123 (aprobada el 20/11/2024 14:30)

Actualización (receptor): cambio previo reemplazado. Solicitud anterior ID: 124 (aprobada el 21/11/2024 10:15)
```

### 3. Relación de Solicitudes
**Archivo:** `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py` (línea 255)

**Funcionalidad:**
- Cuando se encuentra una solicitud anterior para el solicitante, se establece la relación usando `solicitud.solicitud_origen`
- Esto permite rastrear la cadena de cambios: solicitud nueva → solicitud anterior
- La relación se guarda junto con los demás campos de la solicitud

**Código:**
```python
if solicitud_anterior_solicitante:
    solicitud.solicitud_origen = solicitud_anterior_solicitante
```

### 4. HistoricalRecords
**Verificación:**
- ✅ `SolicitudCambio` tiene `historial = HistoricalRecords()` (línea 77 en `models.py`)
- ✅ `Turno` tiene `historial = HistoricalRecords()` (línea 41 en `turnos/models.py`)
- ✅ Los cambios en ambos modelos se capturan automáticamente por `django-simple-history`

## Casos de Prueba

### Caso 1: Primer Cambio (Sin Solicitud Anterior)
**Escenario:**
- Explorador A no tiene turno para fecha X
- Se aprueba solicitud A→B para fecha X

**Resultado Esperado:**
- ✅ Se crea nuevo turno (no hay actualización)
- ✅ No se agregan comentarios de trazabilidad
- ✅ `solicitud.solicitud_origen` permanece `None`

### Caso 2: Segundo Cambio (Con Solicitud Anterior)
**Escenario:**
- Explorador A ya tiene turno para fecha X (creado por solicitud ID 100)
- Se aprueba solicitud A→C para fecha X

**Resultado Esperado:**
- ✅ Se actualiza el turno existente
- ✅ Se encuentra solicitud anterior (ID 100)
- ✅ Se agrega comentario: "Actualización: cambio previo reemplazado. Solicitud anterior ID: 100 (aprobada el {fecha})"
- ✅ `solicitud.solicitud_origen = SolicitudCambio(id=100)`
- ✅ El historial de `Turno` captura el cambio (jornada, sala, tipo_cambio)

### Caso 3: Cambio en Receptor (Solicitud Anterior Diferente)
**Escenario:**
- Explorador B ya tiene turno para fecha X (creado por solicitud ID 200)
- Se aprueba solicitud A→B para fecha X (donde A no tenía turno previo)

**Resultado Esperado:**
- ✅ Se crea nuevo turno para A
- ✅ Se actualiza turno existente para B
- ✅ Se encuentra solicitud anterior para B (ID 200)
- ✅ Se agrega comentario: "Actualización (receptor): cambio previo reemplazado. Solicitud anterior ID: 200 (aprobada el {fecha})"
- ✅ `solicitud.solicitud_origen` puede ser `None` o apuntar a otra solicitud

### Caso 4: Cambio en Ambos (Misma Solicitud Anterior)
**Escenario:**
- Explorador A y B ya tienen turnos para fecha X (ambos creados por solicitud ID 300)
- Se aprueba solicitud A→B para fecha X

**Resultado Esperado:**
- ✅ Se actualizan ambos turnos
- ✅ Se encuentra la misma solicitud anterior (ID 300) para ambos
- ✅ Se agrega comentario una sola vez (evita duplicados)
- ✅ `solicitud.solicitud_origen = SolicitudCambio(id=300)`

### Caso 5: Cambio en Ambos (Solicitudes Anteriores Diferentes)
**Escenario:**
- Explorador A tiene turno para fecha X (creado por solicitud ID 400)
- Explorador B tiene turno para fecha X (creado por solicitud ID 500)
- Se aprueba solicitud A→B para fecha X

**Resultado Esperado:**
- ✅ Se actualizan ambos turnos
- ✅ Se encuentra solicitud anterior para A (ID 400)
- ✅ Se encuentra solicitud anterior diferente para B (ID 500)
- ✅ Se agregan ambos comentarios de trazabilidad
- ✅ `solicitud.solicitud_origen = SolicitudCambio(id=400)` (solicitante tiene prioridad)

## Verificación Manual

### Paso 1: Verificar Comentarios en Solicitud
```python
from solicitudes.models import SolicitudCambio

# Obtener solicitud que actualizó un turno existente
solicitud = SolicitudCambio.objects.get(id=XXX)
print(f"Comentario: {solicitud.comentario}")
print(f"Solicitud origen: {solicitud.solicitud_origen}")
```

### Paso 2: Verificar Historial de Turno
```python
from turnos.models import Turno
from simple_history.models import HistoricalRecords

# Obtener turno actualizado
turno = Turno.objects.get(id=XXX)

# Ver historial
historial = turno.historia.all()
for registro in historial:
    print(f"Fecha: {registro.history_date}, Jornada: {registro.jornada}, Tipo: {registro.history_type}")
```

### Paso 3: Verificar Relación de Solicitudes
```python
# Obtener solicitud nueva
solicitud_nueva = SolicitudCambio.objects.get(id=XXX)

# Verificar relación
if solicitud_nueva.solicitud_origen:
    print(f"Solicitud anterior: {solicitud_nueva.solicitud_origen.id}")
    print(f"Fecha aprobación anterior: {solicitud_nueva.solicitud_origen.fecha_resolucion}")
    
    # Verificar cadena de cambios
    solicitud_anterior = solicitud_nueva.solicitud_origen
    if solicitud_anterior.solicitud_origen:
        print(f"Cadena: Nueva ({solicitud_nueva.id}) → Anterior ({solicitud_anterior.id}) → ...")
```

## Notas Importantes

1. **Búsqueda de Solicitud Anterior:** El sistema busca en `turno_origen` Y `turno_destino` porque un turno puede ser el origen o destino de una solicitud anterior.

2. **Orden de Prioridad:** Si se encuentran solicitudes anteriores tanto para el solicitante como para el receptor, se establece `solicitud_origen` con la del solicitante (tiene prioridad).

3. **Evitar Duplicados:** Si la misma solicitud anterior se encuentra para ambos (solicitante y receptor), solo se agrega un comentario para evitar duplicación.

4. **HistoricalRecords:** Los cambios en `Turno` y `SolicitudCambio` se capturan automáticamente. Cada modificación crea un registro histórico con:
   - `history_date`: Fecha y hora del cambio
   - `history_type`: Tipo de cambio (+, ~, -)
   - `history_user`: Usuario que realizó el cambio
   - Todos los campos del modelo en ese momento

5. **Comentarios Preservados:** Los comentarios de trazabilidad se agregan a los comentarios existentes, no los reemplazan. Se usa `\n\n` como separador para mantener legibilidad.

## Estado
✅ **IMPLEMENTADO** - Pendiente de pruebas manuales

