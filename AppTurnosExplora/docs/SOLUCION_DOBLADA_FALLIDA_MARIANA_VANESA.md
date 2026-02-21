# Solución para Doblada Fallida (Mariana → Vanesa)

## 📋 Problema Identificado

### Contexto
Una solicitud de doblada entre **Mariana (ID: 13)** y **Vanesa (ID: 11)** se aprobó correctamente, pero hubo un error interno en `DobladaTurnoService` que provocó que **no se crearan los turnos AM+PM** en la base de datos.

### Síntomas
- ✅ La solicitud aparece como **aprobada**
- ✅ Los **descansos** se ven correctamente (se calculan por la solicitud)
- ❌ La **DOBLADA no aparece** en "Mis Turnos"
- ❌ **Falta en BD**: No existen registros de `Turno` con AM+PM para las exploradoras en las fechas correspondientes

### Causa Raíz
Error en `DobladaTurnoService` al momento de la aprobación que causó un rollback de la transacción. La solicitud quedó marcada como aprobada, pero los cambios en turnos se revirtieron.

---

## 🛠️ Solución Implementada

### Script de Reaplicación
Se creó un **management command de Django** que permite reaplicar manualmente una solicitud de doblada:

**Archivo**: `AppTurnosExplora/solicitudes/management/commands/reaplicar_doblada.py`

### Funcionalidad del Script
El script:
1. ✅ Verifica que la solicitud existe y está aprobada
2. ✅ Muestra el estado actual de los turnos (qué falta)
3. ✅ Reaplica la doblada de cesión (crea AM+PM para el receptor)
4. ✅ Reaplica la doblada de pago (crea AM+PM para el solicitante)
5. ✅ Regenera las deudas (DeudaExplorador y DeudaCorporativa)
6. ✅ Limpia el caché de turnos
7. ✅ Verifica que todo quedó correcto

---

## 🚀 Uso del Script

### 1. Activar el Entorno Virtual
```powershell
cd C:\appTurnos
.\venvturnos\Scripts\Activate.ps1
```

### 2. Identificar el ID de la Solicitud
Necesitas conocer el **ID de la solicitud** de doblada Mariana → Vanesa.

Puedes buscarlo en:
- Panel de administración de Django: `/admin/solicitudes/solicitudcambio/`
- O con una consulta SQL:

```sql
SELECT 
    sc.id,
    es.nombre AS solicitante,
    er.nombre AS receptor,
    sc.fecha_cambio_turno AS fecha_cesion,
    dd.fecha_pago,
    sc.estado
FROM solicitudes_solicitudcambio sc
JOIN empleados_empleado es ON sc.explorador_solicitante_id = es.id
JOIN empleados_empleado er ON sc.explorador_receptor_id = er.id
JOIN solicitudes_dobladadetalle dd ON dd.solicitud_id = sc.id
WHERE es.id = 13 AND er.id = 11  -- Mariana (13) → Vanesa (11)
    AND sc.estado = 'aprobada'
ORDER BY sc.fecha_solicitud DESC;
```

### 3. Ejecutar el Script (Modo Prueba)
**IMPORTANTE**: Primero ejecuta en modo `--dry-run` para ver qué cambios haría sin modificar la BD:

```powershell
python manage.py reaplicar_doblada <ID_SOLICITUD> --dry-run
```

**Ejemplo:**
```powershell
python manage.py reaplicar_doblada 456 --dry-run
```

Esto mostrará:
- ✅ Información de la solicitud
- ✅ Estado actual de los turnos
- ✅ Diagnóstico (qué falta)
- ✅ Qué cambios se aplicarían (SIN hacerlos)

### 4. Ejecutar el Script (Modo Real)
Si todo se ve correcto en el dry-run, ejecuta sin `--dry-run`:

```powershell
python manage.py reaplicar_doblada <ID_SOLICITUD>
```

**Ejemplo:**
```powershell
python manage.py reaplicar_doblada 456
```

### 5. Verificar en la UI
Después de ejecutar:
1. 🌐 Ingresa a la aplicación web
2. 👤 Inicia sesión como **Vanesa** (ID: 11)
3. 📅 Ve a **"Mis Turnos"**
4. 🔍 Busca la **fecha de cesión** → Debería mostrar **"DOBLADA (AM + PM)"**
5. 👤 Inicia sesión como **Mariana** (ID: 13)
6. 📅 Ve a **"Mis Turnos"**
7. 🔍 Busca la **fecha de pago** → Debería mostrar **"DOBLADA (AM + PM)"**

---

## 📝 Opciones Avanzadas del Script

### `--dry-run`
Simula la operación sin hacer cambios en la base de datos.

```powershell
python manage.py reaplicar_doblada 456 --dry-run
```

**Uso recomendado**: Siempre ejecuta primero con `--dry-run` para verificar.

### `--skip-deudas`
Reaplica solo los turnos, sin regenerar las deudas (DeudaExplorador y DeudaCorporativa).

```powershell
python manage.py reaplicar_doblada 456 --skip-deudas
```

**Uso recomendado**: Solo si las deudas ya existen y no quieres duplicarlas.

---

## 🧪 Flujo de Prueba Completo

### Paso 1: Reaplicar la Doblada Fallida (Mariana → Vanesa)

1. **Identificar el ID de la solicitud**:
   ```powershell
   # En el shell de Django
   python manage.py shell
   ```

   ```python
   from solicitudes.models import SolicitudCambio
   from empleados.models import Empleado
   
   mariana = Empleado.objects.get(id=13)
   vanesa = Empleado.objects.get(id=11)
   
   solicitudes = SolicitudCambio.objects.filter(
       explorador_solicitante=mariana,
       explorador_receptor=vanesa,
       tipo_solicitud__nombre='DOBLADA',
       estado='aprobada'
   ).order_by('-fecha_solicitud')
   
   for s in solicitudes:
       print(f"ID: {s.id}, Cesión: {s.fecha_cambio_turno}, Pago: {s.doblada.fecha_pago}")
   ```

2. **Ejecutar en modo dry-run**:
   ```powershell
   python manage.py reaplicar_doblada <ID_SOLICITUD> --dry-run
   ```

3. **Ejecutar en modo real**:
   ```powershell
   python manage.py reaplicar_doblada <ID_SOLICITUD>
   ```

4. **Verificar en la UI**:
   - Ingresar como Vanesa → Ver "Mis Turnos" → Buscar fecha de cesión → Debe mostrar "DOBLADA (AM + PM)"
   - Ingresar como Mariana → Ver "Mis Turnos" → Buscar fecha de pago → Debe mostrar "DOBLADA (AM + PM)"

### Paso 2: Crear y Probar una Nueva Doblada

Después de corregir el bug en `DobladaTurnoService`, probar con una nueva solicitud sencilla:

1. **Crear una nueva solicitud de doblada**:
   - Solicitante: Cualquier explorador (ej: Manuel)
   - Receptor: Cualquier explorador con jornada contraria (ej: Ronal)
   - Fecha de cesión: Fecha futura (ej: próxima semana)
   - Fecha de pago: Fecha posterior a la cesión
   - Tipo: Cesión completa

2. **Aprobar la solicitud**:
   - Receptor aprueba
   - Supervisor aprueba

3. **Verificar inmediatamente**:
   - ✅ En BD: Verificar que existan turnos AM+PM para receptor en fecha de cesión
   - ✅ En BD: Verificar que existan turnos AM+PM para solicitante en fecha de pago
   - ✅ En UI: "Mis Turnos" debe mostrar "DOBLADA (AM + PM)" en ambas fechas
   - ✅ En UI: Solo si es sábado/domingo con doblada completa → debe generar deuda corporativa

#### Verificación en BD (SQL):

```sql
-- Verificar turnos del RECEPTOR en fecha de CESIÓN
SELECT 
    e.nombre,
    t.fecha,
    j.nombre AS jornada,
    t.tipo_cambio
FROM turnos_turno t
JOIN empleados_empleado e ON t.explorador_id = e.id
JOIN turnos_jornada j ON t.jornada_id = j.id
WHERE t.explorador_id = <ID_RECEPTOR>
    AND t.fecha = '<FECHA_CESION>'
ORDER BY j.nombre;

-- Verificar turnos del SOLICITANTE en fecha de PAGO
SELECT 
    e.nombre,
    t.fecha,
    j.nombre AS jornada,
    t.tipo_cambio
FROM turnos_turno t
JOIN empleados_empleado e ON t.explorador_id = e.id
JOIN turnos_jornada j ON t.jornada_id = j.id
WHERE t.explorador_id = <ID_SOLICITANTE>
    AND t.fecha = '<FECHA_PAGO>'
ORDER BY j.nombre;
```

**Resultado esperado**: Ambas consultas deben retornar 2 filas (AM y PM).

#### Verificación en UI:

1. **Como Receptor**:
   - Ir a "Mis Turnos"
   - Buscar fecha de cesión
   - Debe mostrar: **"DOBLADA (AM + PM)"**
   - Color: Rojo (si es día que originalmente descansaba) o azul (si era su jornada base + adicional)

2. **Como Solicitante**:
   - Ir a "Mis Turnos"
   - Buscar fecha de pago
   - Debe mostrar: **"DOBLADA (AM + PM)"**
   - Color: Similar al receptor

3. **Deuda Corporativa** (solo si fecha es sábado o domingo):
   - Ir a "Mis Deudas Corporativas"
   - Debe aparecer: +30 minutos para receptor (fecha de cesión) y +30 minutos para solicitante (fecha de pago)
   - **IMPORTANTE**: Solo si en BD tienen AM+PM (doblada completa)

### Paso 3: Verificar el Criterio de Deuda Corporativa

**Regla de negocio**:
- La deuda corporativa (30 min) se genera **SOLO** si el explorador tiene **AM+PM en BD** (doblada completa)
- Si tiene solo AM o solo PM → NO se genera deuda (alguien más trabajó la otra media jornada)

**Prueba**:
1. Crear una solicitud de cesión parcial (solo AM o solo PM)
2. Aprobar
3. Verificar en BD: Receptor debe tener solo 1 jornada (no AM+PM completo)
4. Verificar en UI: "Mis Turnos" debe mostrar "AM" o "PM" (no DOBLADA)
5. Verificar en "Mis Deudas Corporativas": **NO debe haber deuda** para esa fecha

---

## 🔍 Diagnóstico y Troubleshooting

### Ver Logs del Script
El script genera logs detallados. Para verlos:

1. En la consola al ejecutar (output directo)
2. En el archivo de logs de Django (si está configurado)

### Verificar Turnos en BD
```sql
-- Ver turnos de un explorador en una fecha
SELECT 
    e.nombre,
    t.fecha,
    j.nombre AS jornada,
    t.tipo_cambio,
    s.nombre AS sala
FROM turnos_turno t
JOIN empleados_empleado e ON t.explorador_id = e.id
JOIN turnos_jornada j ON t.jornada_id = j.id
LEFT JOIN turnos_sala s ON t.sala_id = s.id
WHERE e.id = <ID_EXPLORADOR>
    AND t.fecha = '<FECHA>'
ORDER BY j.nombre;
```

### Verificar Deudas
```sql
-- DeudaExplorador
SELECT 
    de.id,
    ed.nombre AS deudor,
    ea.nombre AS acreedor,
    de.fecha_generacion,
    de.fecha_pago_pactada,
    de.estado,
    de.jornada_cedida
FROM solicitudes_deudaexplorador de
JOIN empleados_empleado ed ON de.deudor_id = ed.id
JOIN empleados_empleado ea ON de.acreedor_id = ea.id
WHERE de.solicitud_origen_id = <ID_SOLICITUD>;

-- DeudaCorporativa
SELECT 
    dc.id,
    e.nombre AS explorador,
    dc.minutos,
    dc.fecha_generacion,
    dc.fecha_doblada,
    dc.estado,
    dc.comentario
FROM solicitudes_deudacorporativa dc
JOIN empleados_empleado e ON dc.explorador_id = e.id
WHERE dc.solicitud_origen_id = <ID_SOLICITUD>
ORDER BY dc.fecha_doblada;
```

### Limpiar Caché Manualmente
Si después de reaplicar no se ven los cambios en la UI:

```powershell
python manage.py shell
```

```python
from core.services.cache_service import CacheService
from empleados.models import Empleado

# Limpiar caché para un explorador específico
explorador_id = 11  # Vanesa
mes = 2  # Febrero
año = 2026

CacheService.invalidar_cache_turnos_empleado(explorador_id, mes, año)

# O limpiar todo el caché
from django.core.cache import cache
cache.clear()
```

---

## ✅ Checklist Final

Después de reaplicar y probar:

### Para la Solicitud Mariana → Vanesa (Fallida)
- [ ] Script ejecutado sin errores
- [ ] Vanesa tiene AM+PM en BD (fecha de cesión)
- [ ] Mariana tiene AM+PM en BD (fecha de pago)
- [ ] Vanesa ve "DOBLADA (AM + PM)" en "Mis Turnos" (fecha de cesión)
- [ ] Mariana ve "DOBLADA (AM + PM)" en "Mis Turnos" (fecha de pago)
- [ ] Deudas generadas correctamente (DeudaExplorador y DeudaCorporativa)

### Para Nuevas Dobladas (Post-Corrección)
- [ ] Solicitud creada y aprobada sin errores
- [ ] Receptor tiene AM+PM en BD (fecha de cesión)
- [ ] Solicitante tiene AM+PM en BD (fecha de pago)
- [ ] "Mis Turnos" muestra "DOBLADA (AM + PM)" en ambas fechas
- [ ] Deuda corporativa generada **SOLO** si hay AM+PM completo
- [ ] NO se genera deuda corporativa si solo hay AM o PM (cesión parcial o media jornada)

---

## 📚 Referencias

### Archivos Relacionados
- `solicitudes/services/doblada_aplicacion_service.py`: Lógica de aplicación de dobladas
- `turnos/services/doblada_turno_service.py`: Gestión de turnos de dobladas
- `solicitudes/services/strategies/doblada_strategy.py`: Estrategia y validaciones
- `turnos/services/turno_service.py`: `obtener_jornada_display()` (fuente de verdad)
- `solicitudes/services/deuda_corporativa_service.py`: Generación de deudas corporativas

### Documentación
- `PLAN_DOBLADAS_COMPLETO.md`: Plan completo de implementación de dobladas
- `FLUJO_COMPLETO_DOBLADA.md`: Flujo detallado de solicitudes de doblada
- `RECOMENDACIONES_DOBLADA_FDS_Y_PERMANENTE.md`: Recomendaciones y casos especiales

---

## 🎯 Próximos Pasos

1. **Inmediato**: Reaplicar la solicitud Mariana → Vanesa con el script
2. **Corto plazo**: Verificar que el bug en `DobladaTurnoService` esté corregido
3. **Validación**: Crear una nueva doblada de prueba y verificar que funcione end-to-end
4. **Monitoreo**: Observar logs para detectar futuros errores similares

---

**Creado**: 2026-02-11  
**Autor**: AI Assistant  
**Propósito**: Solución para caso específico de doblada fallida + flujo de prueba  


