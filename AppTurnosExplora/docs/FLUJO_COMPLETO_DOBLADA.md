# Flujo Completo de Solicitud de Doblada - Análisis Exhaustivo

## 📋 Índice
1. [Flujo Paso a Paso](#flujo-paso-a-paso)
2. [Tablas de Base de Datos](#tablas-de-base-de-datos)
3. [Reglas de Negocio](#reglas-de-negocio)
4. [Casos Especiales](#casos-especiales)
5. [Validaciones Implementadas](#validaciones-implementadas)

---

## 🔄 Flujo Paso a Paso

### FASE 1: Envío de la Solicitud (Frontend → Backend)

#### 1.1 Usuario Completa el Formulario
**Archivo**: `AppTurnosExplora/templates/solicitudes/solicitar_doblada.html`

**Campos del formulario**:
- `fecha_cesion`: Fecha en que el solicitante cede su jornada
- `empleado_receptor`: Explorador que cubrirá la doblada
- `fecha_pago`: Fecha en que el solicitante devolverá la doblada (OBLIGATORIO)
- `jornada_cedida`: 'AM' o 'PM' (opcional, solo si solicitante está en doblada)
- `tipo_cesion`: 'cesion_completa', 'cesion_parcial_am', 'cesion_parcial_pm'
- `comentarios`: Comentario opcional

#### 1.2 Validación Frontend
**Archivo**: `AppTurnosExplora/static/js/cambio-turno/solicitar_doblada.js`

**Validaciones realizadas**:
- ✅ Campos requeridos no vacíos
- ✅ `fecha_pago` posterior a `fecha_creacion_solicitud`
- ✅ `fecha_cesion` no es domingo, festivo ni día de mantenimiento
- ✅ `fecha_pago` no es domingo, festivo ni día de mantenimiento
- ✅ Verificación de doblada existente en fecha de cesión
- ✅ Detección de caso crítico (coincidencia de jornadas)

#### 1.3 Envío al Backend
**Endpoint**: `POST /solicitudes/procesar-solicitud/`
**Archivo**: `AppTurnosExplora/solicitudes/views.py` → `ProcesarSolicitudView.post()`

**Datos enviados**:
```python
{
    'tipo_solicitud_id': 3,  # ID de DOBLADA
    'empleado_receptor': receptor_id,
    'fecha_solicitud': fecha_cesion,  # Fecha de cesión
    'fecha_pago': fecha_pago,
    'jornada_cedida': 'AM' o 'PM' (opcional),
    'tipo_cesion': 'cesion_completa',
    'comentarios': comentario
}
```

---

### FASE 2: Validación Backend

#### 2.1 Validación de Campos Requeridos
**Archivo**: `AppTurnosExplora/solicitudes/views.py` (líneas 793-801)

**Validaciones**:
- ✅ `tipo_solicitud_id` existe
- ✅ `empleado_receptor` existe
- ✅ `fecha_solicitud` (fecha_cesion) existe
- ✅ `fecha_pago` existe (OBLIGATORIO: "No existen dobladas abiertas")

#### 2.2 Validación de Negocio
**Archivo**: `AppTurnosExplora/solicitudes/services/strategies/doblada_strategy.py` → `validar_solicitud()`

**Validaciones ejecutadas** (en orden):

1. **Validación de Empleados Activos**
   ```python
   SolicitudValidator.validar_empleado_activo(explorador_solicitante)
   SolicitudValidator.validar_empleado_activo(explorador_receptor)
   ```

2. **Validación: No Mismo Empleado**
   ```python
   SolicitudValidator.validar_no_mismo_empleado(explorador_solicitante, explorador_receptor)
   ```

3. **Validación: Acuerdo Previo Obligatorio**
   ```python
   SolicitudValidator.validar_acuerdo_previo_obligatorio(
       fecha_cesion, fecha_pago, fecha_creacion_solicitud
   )
   ```
   - ✅ `fecha_pago` debe ser posterior a `fecha_creacion_solicitud`
   - ✅ `fecha_pago` puede ser anterior a `fecha_cesion` (permitido)

4. **Validación: Días Especiales (Fecha Cesión)**
   ```python
   SolicitudValidator.validar_dias_especiales_doblada(fecha_cesion)
   ```
   - ❌ No se permite: Domingos, días festivos, días de mantenimiento

5. **Validación: Días Especiales (Fecha Pago)**
   ```python
   SolicitudValidator.validar_dias_especiales_doblada(fecha_pago)
   ```
   - ❌ No se permite: Domingos, días festivos, días de mantenimiento

6. **Validación: Jornadas Contrarias**
   ```python
   SolicitudValidator.validar_jornadas_contrarias_doblada(
       explorador_solicitante, explorador_receptor, fecha_cesion, jornada_cedida
   )
   ```
   - ✅ Solicitante AM → Receptor debe ser PM
   - ✅ Solicitante PM → Receptor debe ser AM
   - ✅ Si solicitante está en doblada → Receptor debe tener jornada contraria a la jornada cedida

7. **Validación: No Triple Turno (Receptor)**
   ```python
   SolicitudValidator.validar_no_triple_turno(explorador_receptor, fecha_cesion)
   SolicitudValidator.validar_no_triple_turno(explorador_receptor, fecha_pago)
   ```
   - ❌ Receptor no puede tener doblada activa en fecha de cesión
   - ❌ Receptor no puede tener doblada activa en fecha de pago

8. **Validación: No Doblada Activa (Solicitante)**
   ```python
   SolicitudValidator.validar_no_doblada_activa(explorador_solicitante, fecha_cesion)
   SolicitudValidator.validar_no_doblada_activa(explorador_solicitante, fecha_pago)
   ```
   - ❌ Solicitante no puede tener doblada activa en fecha de cesión (excepto si es cesión parcial)
   - ❌ Solicitante no puede tener doblada activa en fecha de pago

9. **Validación: Caso Crítico - Coincidencia de Jornadas**
   ```python
   SolicitudValidator.validar_coincidencia_jornadas_pago(
       explorador_solicitante, explorador_receptor, fecha_pago
   )
   ```
   - ❌ Si deudor y acreedor tienen la misma jornada en fecha de pago → **REQUIERE CAMBIO DE TURNO PREVIO**
   - ✅ Retorna código especial: `'requiere_cambio_turno_previo'`
   - ✅ Frontend redirige a formulario de CT Sencillo

---

### FASE 3: Creación de la Solicitud

#### 3.1 Creación del Registro Principal
**Archivo**: `AppTurnosExplora/solicitudes/services/strategies/doblada_strategy.py` → `crear_solicitud()`

**Tabla**: `solicitudes_solicitudcambio`

**Registro creado**:
```python
solicitud = SolicitudCambio.objects.create(
    explorador_solicitante=explorador_solicitante,  # FK a empleados_empleado
    explorador_receptor=explorador_receptor,         # FK a empleados_empleado
    tipo_cambio=tipo_cambio,                        # FK a solicitudes_tiposolicitudcambio
    comentario=comentario,
    fecha_cambio_turno=fecha_cesion,                # Fecha de cesión
    estado='pendiente'                              # Estado inicial
)
```

**Campos automáticos**:
- `fecha_solicitud`: `auto_now_add=True` (fecha/hora de creación)
- `aprobado_receptor`: `False` (por defecto)
- `aprobado_supervisor`: `False` (por defecto)
- `fecha_aprobacion_receptor`: `None` (inicialmente)
- `fecha_aprobacion_supervisor`: `None` (inicialmente)

#### 3.2 Creación del Detalle de Doblada
**Tabla**: `solicitudes_dobladadetalle`

**Registro creado**:
```python
DobladaDetalle.objects.create(
    solicitud=solicitud,                            # OneToOne con SolicitudCambio
    minutos_deuda=30,                               # Default 30 minutos
    fecha_pago=fecha_pago,                          # Fecha de pago (OBLIGATORIO)
    tipo_cesion=tipo_cesion,                        # 'cesion_completa', 'cesion_parcial_am', 'cesion_parcial_pm'
    jornada_cedida=jornada_cedida,                  # 'AM' o 'PM' (opcional)
    empleado_receptor=explorador_receptor           # FK redundante (útil para consultas)
)
```

---

### FASE 4: Creación de Notificaciones

#### 4.1 Notificaciones Creadas
**Archivo**: `AppTurnosExplora/solicitudes/services/notificacion_service.py` → `crear_notificacion_solicitud()`

**Tabla**: `solicitudes_notificacion`

**Notificaciones creadas**:

1. **Notificación para Supervisor** (si existe)
   ```python
   Notificacion.objects.create(
       destinatario=supervisor,
       tipo='solicitud_cambio',
       titulo='Nueva solicitud de cambio de turno',
       mensaje='...',
       solicitud=solicitud,
       leida=False
   )
   ```

2. **Notificación para Receptor**
   ```python
   Notificacion.objects.create(
       destinatario=explorador_receptor,
       tipo='solicitud_cambio',
       titulo='Solicitud de cambio de turno recibida',
       mensaje='...',
       solicitud=solicitud,
       leida=False
   )
   ```

3. **Notificación para Solicitante**
   ```python
   Notificacion.objects.create(
       destinatario=explorador_solicitante,
       tipo='solicitud_cambio',
       titulo='Solicitud de cambio de turno enviada',
       mensaje='...',
       solicitud=solicitud,
       leida=False
   )
   ```

**Caso Especial**: Si `supervisor == receptor`:
- Se crea una notificación combinada: "Rol Doble (Supervisor + Receptor)"

#### 4.2 Emails Enviados
**Archivos**: `AppTurnosExplora/solicitudes/services/notificacion_service.py`

**Emails enviados**:
1. ✅ Email al Supervisor (si existe y es diferente al receptor)
2. ✅ Email al Receptor
3. ✅ Email de confirmación al Solicitante

**Contenido de emails**:
- Enlaces de aprobación/rechazo (con tokens de seguridad)
- Detalles de la solicitud
- Fechas involucradas

---

### FASE 5: Estado Final - Solicitud Pendiente

#### 5.1 Estado en Base de Datos

**Tabla `solicitudes_solicitudcambio`**:
```sql
SELECT * FROM solicitudes_solicitudcambio WHERE id = [solicitud_id];

-- Resultado:
id: [auto_increment]
explorador_solicitante_id: [solicitante_id]
explorador_receptor_id: [receptor_id]
tipo_cambio_id: [tipo_doblada_id]
estado: 'pendiente'  ← ESTADO INICIAL
fecha_solicitud: [timestamp_actual]
fecha_cambio_turno: [fecha_cesion]
comentario: [comentario]
aprobado_receptor: FALSE
aprobado_supervisor: FALSE
fecha_aprobacion_receptor: NULL
fecha_aprobacion_supervisor: NULL
fecha_resolucion: NULL
```

**Tabla `solicitudes_dobladadetalle`**:
```sql
SELECT * FROM solicitudes_dobladadetalle WHERE solicitud_id = [solicitud_id];

-- Resultado:
id: [auto_increment]
solicitud_id: [solicitud_id]  ← OneToOne
minutos_deuda: 30
fecha_pago: [fecha_pago]
tipo_cesion: 'cesion_completa' | 'cesion_parcial_am' | 'cesion_parcial_pm'
jornada_cedida: 'AM' | 'PM' | NULL
empleado_receptor_id: [receptor_id]
```

**Tabla `solicitudes_notificacion`**:
```sql
SELECT * FROM solicitudes_notificacion WHERE solicitud_id = [solicitud_id];

-- Resultado: 3 registros (supervisor, receptor, solicitante)
-- Cada uno con:
id: [auto_increment]
destinatario_id: [empleado_id]
tipo: 'solicitud_cambio'
titulo: [título específico]
mensaje: [mensaje específico]
solicitud_id: [solicitud_id]
leida: FALSE
fecha_creacion: [timestamp_actual]
fecha_lectura: NULL
```

#### 5.2 Historial (django-simple-history)

**Tablas de historial creadas automáticamente**:
- `solicitudes_solicitudcambio_history`
- `solicitudes_dobladadetalle_history`

**Registros de historial**:
- Se crea un registro inicial en el historial con el estado inicial

---

## 🗄️ Tablas de Base de Datos

### Tablas Principales

#### 1. `solicitudes_solicitudcambio`
**Propósito**: Registro principal de la solicitud

**Campos relevantes para DOBLADA**:
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | INT (PK) | ID único de la solicitud |
| `explorador_solicitante_id` | INT (FK) | Explorador que solicita |
| `explorador_receptor_id` | INT (FK) | Explorador que cubre |
| `tipo_cambio_id` | INT (FK) | Tipo de solicitud (DOBLADA) |
| `estado` | VARCHAR(20) | 'pendiente', 'aprobada', 'rechazada', 'cancelada' |
| `fecha_solicitud` | DATETIME | Fecha/hora de creación |
| `fecha_cambio_turno` | DATE | Fecha de cesión |
| `comentario` | TEXT | Comentario opcional |
| `aprobado_receptor` | BOOLEAN | Aprobación del receptor |
| `aprobado_supervisor` | BOOLEAN | Aprobación del supervisor |
| `fecha_aprobacion_receptor` | DATETIME | Fecha de aprobación del receptor |
| `fecha_aprobacion_supervisor` | DATETIME | Fecha de aprobación del supervisor |
| `fecha_resolucion` | DATETIME | Fecha de resolución final |

**Índices**:
- `sol_receptor_fecha_estado_idx`: Optimiza búsquedas por receptor, fecha y estado

#### 2. `solicitudes_dobladadetalle`
**Propósito**: Detalles específicos de la doblada

**Campos**:
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | INT (PK) | ID único del detalle |
| `solicitud_id` | INT (FK, UNIQUE) | OneToOne con SolicitudCambio |
| `minutos_deuda` | INT | Minutos de deuda (default: 30) |
| `fecha_pago` | DATE | Fecha de pago (OBLIGATORIO) |
| `tipo_cesion` | VARCHAR(50) | 'cesion_completa', 'cesion_parcial_am', 'cesion_parcial_pm' |
| `jornada_cedida` | VARCHAR(2) | 'AM' o 'PM' (opcional) |
| `empleado_receptor_id` | INT (FK) | Receptor (redundante, útil para consultas) |

**Relación**: `OneToOne` con `SolicitudCambio`

#### 3. `solicitudes_notificacion`
**Propósito**: Notificaciones para usuarios

**Campos relevantes**:
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | INT (PK) | ID único de la notificación |
| `destinatario_id` | INT (FK) | Empleado destinatario |
| `tipo` | VARCHAR(50) | 'solicitud_cambio', 'aprobacion', 'rechazo' |
| `titulo` | VARCHAR(255) | Título de la notificación |
| `mensaje` | TEXT | Mensaje de la notificación |
| `solicitud_id` | INT (FK) | Solicitud relacionada |
| `leida` | BOOLEAN | Si fue leída |
| `fecha_creacion` | DATETIME | Fecha de creación |
| `fecha_lectura` | DATETIME | Fecha de lectura |

**Registros creados**: 3 (supervisor, receptor, solicitante)

#### 4. `solicitudes_deudaexplorador`
**Propósito**: Deudas entre exploradores (se crea cuando se aprueba)

**Campos**:
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | INT (PK) | ID único de la deuda |
| `deudor_id` | INT (FK) | Explorador deudor |
| `acreedor_id` | INT (FK) | Explorador acreedor |
| `solicitud_origen_id` | INT (FK) | Solicitud que generó la deuda |
| `fecha_generacion` | DATE | Fecha de generación |
| `fecha_pago_pactada` | DATE | Fecha acordada para pagar |
| `fecha_pago_real` | DATE | Fecha real de pago (NULL inicialmente) |
| `estado` | VARCHAR(20) | 'pendiente', 'pagada', 'cancelada' |
| `media_jornada` | BOOLEAN | True si es media jornada |
| `jornada_cedida` | VARCHAR(2) | 'AM' o 'PM' |

**Estado inicial**: Se crea con `estado='pagada'` cuando se aprueba (porque ambas dobladas se aplican inmediatamente)

#### 5. `solicitudes_deudacorporativa`
**Propósito**: Deudas corporativas acumuladas (se crea cuando se aprueba)

**Campos**:
| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | INT (PK) | ID único de la deuda |
| `explorador_id` | INT (FK) | Explorador que acumula la deuda |
| `solicitud_origen_id` | INT (FK) | Solicitud que generó la deuda |
| `minutos` | INT | Minutos de deuda (default: 30) |
| `fecha_generacion` | DATE | Fecha de generación |
| `fecha_doblada` | DATE | Fecha en que se realizó la doblada |
| `estado` | VARCHAR(20) | 'activa', 'cancelada' |
| `comentario` | TEXT | Comentario opcional |

**Estado inicial**: Se crea con `estado='activa'` cuando se aprueba (se acumula permanentemente)

### Tablas de Historial (django-simple-history)

#### 6. `solicitudes_solicitudcambio_history`
**Propósito**: Historial de cambios en SolicitudCambio

**Campos**: Todos los campos de `solicitudes_solicitudcambio` + `history_id`, `history_date`, `history_change_reason`, `history_type`

#### 7. `solicitudes_dobladadetalle_history`
**Propósito**: Historial de cambios en DobladaDetalle

**Campos**: Todos los campos de `solicitudes_dobladadetalle` + `history_id`, `history_date`, `history_change_reason`, `history_type`

---

## 📐 Reglas de Negocio

### Regla 1: Acuerdo Previo Obligatorio
**⛔ REGLA CRÍTICA**: No existen dobladas abiertas

**Requisitos**:
- ✅ `fecha_pago` es OBLIGATORIA
- ✅ `fecha_pago` debe ser posterior a `fecha_creacion_solicitud`
- ✅ `fecha_pago` puede ser anterior a `fecha_cesion` (permitido)

**Validación**: `SolicitudValidator.validar_acuerdo_previo_obligatorio()`

### Regla 2: Días Especiales
**No se permiten dobladas en**:
- ❌ Domingos
- ❌ Días festivos
- ❌ Días de mantenimiento

**Aplica a**:
- ✅ Fecha de cesión
- ✅ Fecha de pago

**Validación**: `SolicitudValidator.validar_dias_especiales_doblada()`

### Regla 3: Jornadas Contrarias
**Requisitos**:
- ✅ Solicitante AM → Receptor debe ser PM
- ✅ Solicitante PM → Receptor debe ser AM
- ✅ Si solicitante está en doblada → Receptor debe tener jornada contraria a la jornada cedida

**Validación**: `SolicitudValidator.validar_jornadas_contrarias_doblada()`

### Regla 4: No Triple Turno
**Restricción**:
- ❌ Receptor no puede tener doblada activa en fecha de cesión
- ❌ Receptor no puede tener doblada activa en fecha de pago

**Validación**: `SolicitudValidator.validar_no_triple_turno()`

### Regla 5: No Doblada Activa (Solicitante)
**Restricción**:
- ❌ Solicitante no puede tener doblada activa en fecha de cesión (excepto si es cesión parcial)
- ❌ Solicitante no puede tener doblada activa en fecha de pago

**Validación**: `SolicitudValidator.validar_no_doblada_activa()`

### Regla 6: Caso Crítico - Coincidencia de Jornadas
**Escenario**:
- Si deudor y acreedor tienen la misma jornada en fecha de pago → **REQUIERE CAMBIO DE TURNO PREVIO**

**Validación**: `SolicitudValidator.validar_coincidencia_jornadas_pago()`

**Acción**:
- ✅ Retorna código especial: `'requiere_cambio_turno_previo'`
- ✅ Frontend redirige a formulario de CT Sencillo
- ✅ Mensaje: "No se puede pagar trabajando dos veces la misma jornada. Debes primero realizar un cambio de turno sencillo para tener jornada contraria en la fecha de pago."

### Regla 7: Doble Aprobación
**Requisitos**:
- ✅ Receptor debe aprobar
- ✅ Supervisor debe aprobar
- ✅ Solo cuando AMBOS aprueban → se aplican los cambios

**Estado de aprobación**:
- `aprobado_receptor`: Boolean
- `aprobado_supervisor`: Boolean
- `estado`: 'pendiente' → 'aprobada' (cuando ambos aprueban)

### Regla 8: Aplicación Inmediata
**Cuando se aprueba** (ambos aprueban):
- ✅ **AMBAS dobladas se aplican INMEDIATAMENTE**:
  - Fecha de cesión: Receptor dobla, Solicitante descansa
  - Fecha de pago: Solicitante dobla, Receptor descansa
- ✅ Deuda entre exploradores: Se crea con `estado='pagada'` (porque ambas dobladas ya están aplicadas)
- ✅ Deuda corporativa: Se crea con `estado='activa'` para ambos (se acumula permanentemente)

**NO quedan dobladas pendientes**

---

## 🎯 Casos Especiales

### Caso 1: Solicitud Simple (1 a 1)
**Escenario**:
- Solicitante: AM
- Receptor: PM
- Fecha cesión: 2025-12-18
- Fecha pago: 2025-12-25

**Resultado**:
- Solicitud creada con `estado='pendiente'`
- Notificaciones enviadas a supervisor, receptor y solicitante
- Esperando aprobación de receptor y supervisor

### Caso 2: Cesión Parcial desde Doblada Existente
**Escenario**:
- Solicitante: Tiene doblada (AM+PM) el 2025-12-18
- Cede: Solo AM
- Receptor: PM (jornada contraria a AM)

**Resultado**:
- Solicitud creada con `tipo_cesion='cesion_parcial_am'`
- `jornada_cedida='AM'`
- Receptor cubre solo AM, Solicitante trabaja PM

### Caso 3: Cesión Total desde Doblada Existente
**Escenario**:
- Solicitante: Tiene doblada (AM+PM) el 2025-12-18
- Cede: Ambas jornadas (AM y PM)
- Necesita: 2 receptores (uno para AM, otro para PM)

**Resultado**:
- Se crean 2 solicitudes separadas:
  1. Cesión AM → Receptor PM
  2. Cesión PM → Receptor AM
- Cada una con su propia fecha de pago

### Caso 4: Caso Crítico - Coincidencia de Jornadas
**Escenario**:
- Solicitante: AM (jornada predeterminada)
- Receptor: AM (jornada predeterminada)
- Fecha pago: 2025-12-25 (ambos tienen AM)

**Resultado**:
- ❌ Validación falla
- ✅ Retorna código: `'requiere_cambio_turno_previo'`
- ✅ Frontend muestra mensaje y redirige a CT Sencillo
- ✅ Usuario debe hacer cambio de turno primero

### Caso 5: Supervisor = Receptor
**Escenario**:
- Supervisor del solicitante = Receptor de la solicitud

**Resultado**:
- Se crea notificación combinada: "Rol Doble (Supervisor + Receptor)"
- Email combinado con enlaces para ambos roles
- Debe aprobar en ambos roles

### Caso 6: Fecha de Pago Anterior a Fecha de Cesión
**Escenario**:
- Fecha cesión: 2025-12-18
- Fecha pago: 2025-12-15 (anterior a cesión)

**Resultado**:
- ✅ PERMITIDO (siempre que `fecha_pago > fecha_creacion_solicitud`)
- El receptor puede pagar antes de la cesión

---

## ✅ Validaciones Implementadas

### Validaciones Frontend
**Archivo**: `AppTurnosExplora/static/js/cambio-turno/solicitar_doblada.js`

1. ✅ Campos requeridos
2. ✅ Fecha de pago posterior a creación
3. ✅ Días especiales bloqueados en datepicker
4. ✅ Verificación de doblada existente
5. ✅ Detección de caso crítico

### Validaciones Backend
**Archivo**: `AppTurnosExplora/solicitudes/services/solicitud_validator.py`

1. ✅ `validar_empleado_activo()`
2. ✅ `validar_no_mismo_empleado()`
3. ✅ `validar_acuerdo_previo_obligatorio()`
4. ✅ `validar_dias_especiales_doblada()`
5. ✅ `validar_jornadas_contrarias_doblada()`
6. ✅ `validar_no_triple_turno()`
7. ✅ `validar_no_doblada_activa()`
8. ✅ `validar_coincidencia_jornadas_pago()`

---

## 📊 Resumen de Tablas y Estados

### Estado Inicial (Pendiente)

| Tabla | Registros Creados | Estado |
|-------|-------------------|--------|
| `solicitudes_solicitudcambio` | 1 | `estado='pendiente'` |
| `solicitudes_dobladadetalle` | 1 | - |
| `solicitudes_notificacion` | 3 | `leida=False` |
| `solicitudes_deudaexplorador` | 0 | (se crea al aprobar) |
| `solicitudes_deudacorporativa` | 0 | (se crea al aprobar) |
| `turnos_turno` | 0 | (se crea al aprobar) |

### Estado Final (Aprobada)

| Tabla | Registros Creados | Estado |
|-------|-------------------|--------|
| `solicitudes_solicitudcambio` | 1 | `estado='aprobada'` |
| `solicitudes_dobladadetalle` | 1 | - |
| `solicitudes_notificacion` | 3+ | (notificaciones de aprobación) |
| `solicitudes_deudaexplorador` | 1 | `estado='pagada'` |
| `solicitudes_deudacorporativa` | 2 | `estado='activa'` (ambos exploradores) |
| `turnos_turno` | 4 | (2 para cesión, 2 para pago) |

---

## 🔍 Consultas SQL Útiles

### Ver Solicitud de Doblada Pendiente
```sql
SELECT 
    sc.id,
    sc.estado,
    es.nombre AS solicitante,
    er.nombre AS receptor,
    sc.fecha_cambio_turno AS fecha_cesion,
    dd.fecha_pago,
    dd.tipo_cesion,
    dd.jornada_cedida,
    sc.fecha_solicitud,
    sc.aprobado_receptor,
    sc.aprobado_supervisor
FROM solicitudes_solicitudcambio sc
INNER JOIN empleados_empleado es ON sc.explorador_solicitante_id = es.id
INNER JOIN empleados_empleado er ON sc.explorador_receptor_id = er.id
INNER JOIN solicitudes_dobladadetalle dd ON dd.solicitud_id = sc.id
WHERE sc.estado = 'pendiente'
  AND sc.tipo_cambio_id = (SELECT id FROM solicitudes_tiposolicitudcambio WHERE nombre = 'DOBLADA')
ORDER BY sc.fecha_solicitud DESC;
```

### Ver Notificaciones de una Solicitud
```sql
SELECT 
    n.id,
    e.nombre AS destinatario,
    n.tipo,
    n.titulo,
    n.leida,
    n.fecha_creacion
FROM solicitudes_notificacion n
INNER JOIN empleados_empleado e ON n.destinatario_id = e.id
WHERE n.solicitud_id = [solicitud_id]
ORDER BY n.fecha_creacion DESC;
```

---

## 📝 Notas Finales

1. **No existen dobladas abiertas**: Toda solicitud debe tener `fecha_pago` definida
2. **Aplicación inmediata**: Cuando se aprueba, ambas dobladas se aplican inmediatamente
3. **Deuda corporativa permanente**: Se acumula permanentemente, no se cancela
4. **Doble aprobación**: Requiere aprobación de receptor Y supervisor
5. **Caso crítico**: Se valida al enviar la solicitud, no al aprobar

---

**Documento generado**: Análisis exhaustivo del flujo completo de solicitud de doblada
**Última actualización**: Basado en código actual del proyecto






