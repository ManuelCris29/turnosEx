# Características de Solicitudes: Cambio de Turno (CT) y Cambio de Turno Permanente (CT PERMANENTE)

## 📋 Índice
1. [Cambio de Turno (CT) - Sencillo](#cambio-de-turno-ct---sencillo)
2. [Cambio de Turno Permanente (CT PERMANENTE)](#cambio-de-turno-permanente-ct-permanente)
3. [Comparación Rápida](#comparación-rápida)

---

## 🔄 Cambio de Turno (CT) - Sencillo

### **Descripción General**
Solicitud para intercambiar turnos con otro explorador en una **fecha específica**. Es un cambio puntual, de un solo día.

### **Campos Requeridos**
| Campo | Tipo | Descripción | Validación Frontend | Validación Backend |
|-------|------|-------------|---------------------|-------------------|
| `tipo_solicitud_id` | Integer (hidden) | ID del tipo de solicitud "CT" | ✅ Requerido | ✅ Verificado |
| `empleado_receptor` | Integer (select) | Compañero con quien intercambiar | ✅ Requerido | ✅ Activo, no mismo empleado |
| `fecha_solicitud` | Date | Fecha del cambio (YYYY-MM-DD) | ✅ Requerido, no pasado | ✅ No pasado, formato válido |

### **Reglas de Negocio**

#### **1. Validaciones de Empleados**
- ✅ **Ambos empleados deben estar activos**
- ✅ **No puede ser el mismo empleado** (solicitante ≠ receptor)
- ✅ **Ambos deben tener jornada asignada** para la fecha seleccionada

#### **2. Validaciones de Jornadas**
- ✅ **Jornadas contrarias obligatorias**: El solicitante y receptor deben tener jornadas opuestas (AM ↔ PM)
  - Si solicitante tiene AM → receptor debe tener PM
  - Si solicitante tiene PM → receptor debe tener AM
- ✅ **No se permite cambio por la misma jornada**

#### **3. Validaciones de Fecha**
- ✅ **No puede ser fecha pasada**
- ✅ **No puede ser domingo** (no se puede cambiar domingo por día de semana)
- ✅ **No puede ser día de mantenimiento**
- ✅ **No puede ser día de temporada** (si aplica)
- ✅ **No puede ser día festivo** (si aplica, aunque el sistema permite solicitar en festivos si ambos tienen jornada)

#### **4. Validaciones de Duplicidad**
- ✅ **No puede haber solicitud pendiente** del mismo solicitante para la misma fecha
- ✅ **No puede haber solicitud duplicada** (mismo solicitante, mismo receptor, misma fecha)

#### **5. Validaciones de Dobladas**
- ✅ **El solicitante no puede tener doblada activa** para esa fecha
- ✅ **El receptor no puede tener doblada activa** para esa fecha

#### **6. Límite de Cambios por Fecha**
- ✅ **Máximo 3 cambios aprobados** por explorador por fecha
- ✅ Se valida tanto para el solicitante como para el receptor
- ✅ Si se alcanza el límite, la solicitud se rechaza con mensaje explicativo

### **Proceso de Aplicación (cuando se aprueba)**

#### **1. Creación/Actualización de Turnos**
- **Si ya existe Turno** para el explorador en esa fecha:
  - Se **actualiza** el turno existente (jornada y sala)
  - Se mantiene `tipo_cambio='CT'`
  - Se registra trazabilidad de la solicitud anterior que creó ese turno
- **Si no existe Turno**:
  - Se **crea** nuevo turno para el solicitante (con jornada del receptor)
  - Se **crea** nuevo turno para el receptor (con jornada del solicitante)
  - Ambos turnos tienen `tipo_cambio='CT'`

#### **2. Trazabilidad**
- Si se actualiza un turno existente, se busca la solicitud anterior que lo creó
- Se relaciona la nueva solicitud con la anterior mediante `solicitud_origen`
- Se agrega comentario de trazabilidad en el campo `comentario`

#### **3. First-Come, First-Served**
- Al aprobar una solicitud, se **rechazan automáticamente** todas las solicitudes pendientes del mismo receptor para la misma fecha
- Se crean notificaciones para los solicitantes afectados
- Mensaje de rechazo: "Rechazada automáticamente: otra solicitud fue aprobada primero (First-Come, First-Served)"

#### **4. Invalidación de Caché**
- Se invalida el caché de turnos para ambos exploradores del mes correspondiente
- Claves de caché: `turnos_mes_{explorador_id}_{año}_{mes}`

### **Modelo de Datos**
```python
SolicitudCambio:
  - explorador_solicitante: ForeignKey(Empleado)
  - explorador_receptor: ForeignKey(Empleado)
  - tipo_cambio: ForeignKey(TipoSolicitudCambio)  # "CT"
  - fecha_cambio_turno: Date  # Fecha del cambio
  - estado: CharField  # pendiente, aprobada, rechazada, cancelada
  - turno_origen: ForeignKey(Turno)  # Turno del solicitante
  - turno_destino: ForeignKey(Turno)  # Turno del receptor
  - solicitud_origen: ForeignKey(Self)  # Para trazabilidad
```

### **Flujo de Usuario**
1. Usuario selecciona fecha en calendario (con indicadores de festivos/mantenimiento)
2. Sistema muestra solo exploradores con jornada contraria para esa fecha
3. Usuario selecciona compañero receptor
4. Sistema valida campos requeridos (frontend)
5. Usuario envía solicitud
6. Sistema valida reglas de negocio (backend)
7. Si es válida, se crea solicitud en estado "pendiente"
8. Supervisor aprueba/rechaza
9. Si se aprueba, se aplican cambios (crean/actualizan turnos)

---

## 🔁 Cambio de Turno Permanente (CT PERMANENTE)

### **Descripción General**
Solicitud para intercambiar turnos con otro explorador en un **rango de fechas** (múltiples días). Permite seleccionar días específicos o días de la semana dentro del rango.

### **Campos Requeridos**
| Campo | Tipo | Descripción | Validación Frontend | Validación Backend |
|-------|------|-------------|---------------------|-------------------|
| `tipo_solicitud_id` | Integer (hidden) | ID del tipo de solicitud "CT PERMANENTE" | ✅ Requerido | ✅ Verificado |
| `empleado_receptor` | Integer (select) | Compañero con quien intercambiar | ✅ Requerido | ✅ Activo, no mismo empleado |
| `fecha_inicio` | Date | Fecha de inicio del rango (YYYY-MM-DD) | ✅ Requerido, no pasado | ✅ No pasado, formato válido |
| `fecha_fin` | Date | Fecha de fin del rango (YYYY-MM-DD) | ✅ Requerido, posterior a inicio | ✅ Posterior a inicio, formato válido |
| `dias_seleccionados` | JSON (hidden) | Días seleccionados (días semana o fechas específicas) | ✅ Requerido, al menos 1 día | ✅ Al menos 1 día válido |

### **Tipos de Selección de Días**

#### **1. Días de Semana (dias_semana)**
- Selecciona todos los días de un tipo de semana dentro del rango
- Ejemplo: "Todos los martes y jueves del 1 al 31 de enero"
- Valores: `[0, 1, 2, 3, 4]` (Lunes=0, Martes=1, ..., Viernes=4)
- **Restricción**: Solo lunes-viernes (no sábados ni domingos)

#### **2. Fechas Específicas (fechas_especificas)**
- Selecciona días puntuales dentro del rango
- Ejemplo: "23 nov, 27 nov, 3 dic"
- Formato: `["2025-11-23", "2025-11-27", "2025-12-03"]`
- **Restricción**: Solo lunes-viernes (no sábados ni domingos)
- **Uso**: Permite compatibilidad parcial (días donde las jornadas son contrarias)

### **Reglas de Negocio**

#### **1. Validaciones de Empleados**
- ✅ **Ambos empleados deben estar activos**
- ✅ **No puede ser el mismo empleado** (solicitante ≠ receptor)

#### **2. Validaciones de Fechas**
- ✅ **fecha_inicio no puede ser en el pasado**
- ✅ **fecha_fin es obligatoria**
- ✅ **fecha_fin debe ser posterior a fecha_inicio**
- ✅ **Rango válido**: Al menos 1 día entre inicio y fin

#### **3. Validaciones de Días Seleccionados**
- ✅ **Debe haber al menos 1 día seleccionado** (dias_semana o fechas_especificas)
- ✅ **Solo lunes-viernes** (weekday 0-4)
- ✅ **Fechas específicas deben estar dentro del rango**
- ✅ **Si no hay días seleccionados**: Se usa rango completo (todos los lunes-viernes)

#### **4. Validaciones de Jornadas Contrarias**
- **Si hay fechas_especificas**:
  - Se evalúa día a día la compatibilidad
  - Solo se incluyen días donde las jornadas son contrarias
  - La validación se omite (ya se evaluó en `get_empleados_disponibles`)
- **Si NO hay fechas_especificas** (solo dias_semana o rango completo):
  - Debe haber **al menos 1 día** en el rango donde las jornadas sean contrarias
  - Se valida usando `validar_jornada_contraria_rango_permanente`

#### **5. Validaciones de Días Válidos**
El sistema **excluye automáticamente** días inválidos, pero requiere que haya **al menos 1 día válido**:

**Días excluidos automáticamente:**
- ❌ **Sábados y domingos** (solo lunes-viernes)
- ❌ **Días festivos** (registrados en `DiaEspecial` tipo='festivo')
- ❌ **Días de mantenimiento** (registrados en `DiaEspecial` tipo='mantenimiento')
- ❌ **Días de temporada** (registrados en `DiaEspecial` con `es_temporada=True`)
- ❌ **Días de descanso del solicitante** (según su jornada base)
- ❌ **Días de descanso del receptor** (según su jornada base)

**Prioridad de exclusión** (para mostrar razón principal):
1. **Mantenimiento** (más importante)
2. **Festivo**
3. **Temporada**
4. **Descanso Solicitante**
5. **Descanso Receptor**
6. **Fines de semana** (menos importante)

**Regla crítica**: Si **TODOS** los días del rango son inválidos, la solicitud se rechaza con mensaje: "No se encontraron días válidos en el rango seleccionado. Todos los días son festivos, de mantenimiento, temporada, o días de descanso."

#### **6. Validaciones de Superposición**
- ✅ **No puede haber cambio permanente superpuesto** entre los mismos empleados
- Se verifica que no exista otro cambio permanente aprobado o pendiente con:
  - Mismos empleados (solicitante y receptor)
  - Rango de fechas que se superponga

### **Sistema de Compatibilidad Parcial (Best Match)**

#### **Descripción**
Cuando el usuario selecciona un rango, el sistema evalúa día a día la compatibilidad de jornadas y muestra solo los días donde las jornadas son contrarias.

#### **Funcionamiento**
1. **Genera todas las fechas válidas** del rango (según días seleccionados)
2. **Evalúa cada fecha** para cada candidato:
   - Obtiene jornada del usuario actual
   - Determina jornada contraria necesaria
   - Verifica si el candidato tiene esa jornada contraria
3. **Calcula porcentaje de compatibilidad**:
   - `compatibilidad_percent = (días_compatibles / total_días) * 100`
4. **Filtra candidatos**:
   - Solo muestra candidatos con al menos 1 día compatible
   - Ordena por porcentaje de compatibilidad descendente
5. **Inyecta metadatos** en cada empleado:
   - `compatibilidad_percent`: Porcentaje de días compatibles
   - `dias_compatibles`: Lista de fechas compatibles
   - `dias_incompatibles`: Lista de fechas incompatibles
   - `total_dias_rango`: Total de días en el rango

#### **Uso de Fechas Específicas**
- Si el usuario selecciona un candidato con compatibilidad parcial, el sistema genera automáticamente `fechas_especificas` con solo los días compatibles
- Estas fechas se envían al backend en lugar de `dias_semana`
- El backend procesa solo esas fechas específicas

### **Proceso de Aplicación (cuando se aprueba)**

#### **1. Generación de Fechas Válidas**
- Se generan todas las fechas válidas según:
  - `fechas_especificas` (si existen, tienen prioridad)
  - `dias_semana` (si no hay fechas específicas)
  - Rango completo (si no hay días seleccionados)
- Se filtran días inválidos (festivos, mantenimiento, descansos, etc.)

#### **2. Creación de Turnos**
- Para cada fecha válida:
  - Se crea turno para el solicitante (con jornada contraria del receptor)
  - Se crea turno para el receptor (con jornada contraria del solicitante)
  - Ambos turnos tienen `tipo_cambio='CT PERMANENTE'`
- Se registran días omitidos con sus razones

#### **3. Actualización de Solicitud**
- Se relaciona la solicitud con el primer turno creado:
  - `turno_origen`: Primer turno del solicitante
  - `turno_destino`: Primer turno del receptor
- Se actualiza estado a "aprobada"
- Se registra `fecha_resolucion`

#### **4. Mensaje de Resultado**
- Muestra cantidad de días procesados
- Lista días omitidos con sus razones (si los hay)

### **Modelo de Datos**
```python
SolicitudCambio:
  - explorador_solicitante: ForeignKey(Empleado)
  - explorador_receptor: ForeignKey(Empleado)
  - tipo_cambio: ForeignKey(TipoSolicitudCambio)  # "CT PERMANENTE"
  - fecha_cambio_turno: Date  # Fecha de inicio (para compatibilidad)
  - estado: CharField
  - turno_origen: ForeignKey(Turno)  # Primer turno del solicitante
  - turno_destino: ForeignKey(Turno)  # Primer turno del receptor

CambioPermanenteDetalle:
  - solicitud: OneToOneField(SolicitudCambio)
  - fecha_inicio: Date
  - fecha_fin: Date (nullable)

CambioPermanenteDia:
  - cambio_permanente: ForeignKey(CambioPermanenteDetalle)
  - tipo: CharField  # 'fecha_especifica' o 'dia_semana'
  - fecha_especifica: Date (nullable, si tipo='fecha_especifica')
  - dia_semana: Integer (nullable, si tipo='dia_semana')
```

### **Vista Previa y Detalle**

#### **Vista Previa (en formulario)**
- Muestra **fechas aplicables** (días válidos donde se aplicará el cambio)
- Muestra **fechas excluidas** agrupadas por razón:
  - Mantenimiento
  - Festivo
  - Festivo, Temporada (combinado)
  - Temporada
  - Descanso Solicitante
  - Descanso Receptor
  - Fines de semana (resumen con toggle para ver detalle)
- Muestra **resumen del rango**:
  - Total de días en el rango
  - Total de fines de semana en el rango
  - Total de días aplicables
  - Total de días excluidos
  - Explicación de prioridad de exclusión

#### **Detalle (en Mis Solicitudes / Pendientes)**
- Muestra información completa de la solicitud
- Lista fechas aplicables y excluidas (igual que vista previa)
- Muestra resumen del rango con explicaciones

### **Flujo de Usuario**
1. Usuario selecciona rango de fechas (inicio y fin)
2. Usuario selecciona días de semana o fechas específicas (opcional)
3. Sistema muestra exploradores disponibles con compatibilidad parcial
4. Usuario selecciona compañero receptor
5. Sistema muestra vista previa (fechas aplicables y excluidas)
6. Usuario revisa y envía solicitud
7. Sistema valida campos requeridos (frontend)
8. Sistema valida reglas de negocio (backend)
9. Si es válida, se crea solicitud en estado "pendiente"
10. Supervisor aprueba/rechaza
11. Si se aprueba, se aplican cambios (crean turnos para cada fecha válida)

---

## 📊 Comparación Rápida

| Característica | CT (Sencillo) | CT PERMANENTE |
|----------------|---------------|---------------|
| **Alcance** | 1 día específico | Rango de fechas (múltiples días) |
| **Campos requeridos** | Fecha, Receptor | Fecha inicio, Fecha fin, Receptor, Días seleccionados |
| **Selección de días** | No aplica (1 día) | Días de semana o fechas específicas |
| **Jornadas contrarias** | Obligatorio en la fecha | Al menos 1 día en el rango |
| **Compatibilidad parcial** | No aplica | Sí (Best Match) |
| **Días válidos** | Lunes-sábado (no domingo) | Solo lunes-viernes |
| **Exclusión automática** | Festivos, mantenimiento, temporada | Festivos, mantenimiento, temporada, descansos, fines de semana |
| **Límite de cambios** | 3 por fecha | No aplica (es por rango) |
| **First-Come, First-Served** | Sí (rechaza otras solicitudes pendientes) | No aplica (rangos pueden superponerse parcialmente) |
| **Cambio sobre cambio** | Sí (actualiza turno existente) | Sí (crea múltiples turnos) |
| **Trazabilidad** | Sí (relaciona solicitudes) | Sí (relaciona solicitudes) |
| **Vista previa** | No (solo validación) | Sí (fechas aplicables y excluidas) |
| **Resumen de rango** | No aplica | Sí (total días, fines de semana, aplicables, excluidos) |

---

## 🔍 Archivos Clave

### **Estrategias**
- `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py`
- `AppTurnosExplora/solicitudes/services/strategies/ct_permanente_strategy.py`

### **Validadores**
- `AppTurnosExplora/solicitudes/services/solicitud_validator.py`

### **Helpers**
- `AppTurnosExplora/solicitudes/services/ct_permanente_helper.py`

### **Modelos**
- `AppTurnosExplora/solicitudes/models.py` (SolicitudCambio, CambioPermanenteDetalle, CambioPermanenteDia)

### **Vistas**
- `AppTurnosExplora/solicitudes/views.py` (ProcesarSolicitudView, PrevisualizarCTPermanenteView, ObtenerDetalleSolicitudView)

### **Templates**
- `AppTurnosExplora/templates/solicitudes/solicitar_cambio_turno.html`
- `AppTurnosExplora/templates/solicitudes/solicitar_ct_permanente.html`

### **JavaScript**
- `AppTurnosExplora/static/js/cambio-turno/solicitar_cambio_turno.js`
- `AppTurnosExplora/static/js/cambio-turno/solicitar_ct_permanente.js`
- `AppTurnosExplora/static/js/cambio-turno/validadores_solicitudes.js`

---

**Última actualización**: Enero 2025  
**Versión del documento**: 1.0

