# Análisis de Violaciones SRP - Proyecto AppTurnos

## Fecha: 2025-01-XX

## RESUMEN EJECUTIVO

Se identificaron **violaciones críticas del Principio de Responsabilidad Única (SRP)** en:

1. **CRÍTICA**: `SolicitudService` con 15+ métodos y múltiples responsabilidades
2. **CRÍTICA**: Views con lógica de negocio mezclada
3. **MEDIA**: Algunos servicios con responsabilidades múltiples

---

## VIOLACIÓN 1: SolicitudService (CRÍTICA)

### Ubicación:
- `AppTurnosExplora/solicitudes/services/solicitud_service.py` (715 líneas)

### Responsabilidades Identificadas:

#### 1.1 Gestión de Empleados Disponibles
**Métodos**:
- `get_empleados_disponibles()` - línea 17
- `get_empleados_jornada_contraria()` - línea 43

**Responsabilidad**: Buscar y filtrar empleados según criterios

**Violación**: Esta responsabilidad debería estar en un servicio de empleados o disponibilidad

---

#### 1.2 Gestión de Jornadas
**Métodos**:
- `get_jornada_explorador_fecha()` - línea 154

**Responsabilidad**: Obtener jornada de un explorador para una fecha

**Violación**: Esta responsabilidad pertenece al dominio de `turnos`, no `solicitudes`

**Solución**: Mover a `turnos/services/jornada_service.py`

---

#### 1.3 Gestión de Turnos
**Métodos**:
- `get_turno_explorador()` - línea 186
- `get_salas_explorador()` - línea 260

**Responsabilidad**: Obtener información de turnos y salas

**Violación**: Esta responsabilidad pertenece al dominio de `turnos`

**Solución**: Mover a `turnos/services/turno_service.py`

---

#### 1.4 Gestión de Tipos de Solicitud
**Métodos**:
- `get_tipos_solicitud_activos()` - línea 269

**Responsabilidad**: Consultar tipos de solicitud

**Violación**: Responsabilidad simple pero podría estar en un servicio de consultas

**Solución**: Mover a `solicitudes/services/solicitud_consulta_service.py`

---

#### 1.5 Creación de Solicitudes
**Métodos**:
- `crear_solicitud_cambio()` - línea 276

**Responsabilidad**: Crear nuevas solicitudes y manejar cancelaciones automáticas

**Violación**: Mezcla creación, validación de duplicados y notificaciones

**Solución**: Mantener creación aquí, pero extraer lógica de cancelación y notificaciones

---

#### 1.6 Consultas de Solicitudes
**Métodos**:
- `get_solicitudes_usuario()` - línea 358
- `get_solicitudes_pendientes()` - línea 372
- `get_solicitudes_por_receptor()` - línea 623
- `get_solicitudes_por_supervisor()` - línea 639
- `get_estado_aprobacion_solicitud()` - línea 655
- `contar_cambios_explorador_fecha()` - línea 681

**Responsabilidad**: Consultar y filtrar solicitudes

**Violación**: Múltiples métodos de consulta mezclados con lógica de negocio

**Solución**: Extraer a `solicitudes/services/solicitud_consulta_service.py`

---

#### 1.7 Aprobación/Rechazo de Solicitudes
**Métodos**:
- `aprobar_solicitud_supervisor()` - línea 384
- `aprobar_solicitud_receptor()` - línea 458
- `rechazar_solicitud_supervisor()` - línea 531
- `rechazar_solicitud_receptor()` - línea 577

**Responsabilidad**: Procesar aprobaciones y rechazos, aplicar cambios, enviar notificaciones

**Violación**: Mezcla validación, cambio de estado, aplicación de cambios y notificaciones

**Solución**: Extraer a `solicitudes/services/solicitud_aprobacion_service.py`

---

### Resumen de Responsabilidades en SolicitudService:

1. ✅ **Búsqueda de empleados** → `EmpleadoDisponibilidadService`
2. ✅ **Gestión de jornadas** → `JornadaService` (en turnos)
3. ✅ **Gestión de turnos** → `TurnoService` (en turnos)
4. ✅ **Consultas de solicitudes** → `SolicitudConsultaService`
5. ✅ **Aprobación/rechazo** → `SolicitudAprobacionService`
6. ⚠️ **Creación de solicitudes** → Mantener en `SolicitudService` (core)

---

## VIOLACIÓN 2: Views con Lógica de Negocio (CRÍTICA)

### 2.1 SolicitudesView.get_context_data

**Ubicación**: `solicitudes/views.py` líneas 43-98

**Problemas**:
- Lógica de cache mezclada con lógica de negocio
- Queries complejas directamente en la view
- Cálculo de contadores en la view
- Debug prints en producción

**Responsabilidades mezcladas**:
1. Preparar contexto para template (responsabilidad de View)
2. Calcular contadores de solicitudes (lógica de negocio)
3. Gestionar cache (infraestructura)
4. Debugging (no debería estar en producción)

**Solución**:
- Extraer cálculo de contadores a `SolicitudConsultaService.get_contadores_usuario()`
- View solo llama al servicio y pasa datos al contexto

---

### 2.2 MisTurnosView.get_context_data

**Ubicación**: `turnos/views.py` líneas 16-282

**Problemas**:
- 266 líneas de lógica compleja en una view
- Cálculo de fechas y rangos
- Construcción de estructuras de datos complejas
- Lógica de jornadas predeterminadas
- Procesamiento de solicitudes aprobadas

**Responsabilidades mezcladas**:
1. Preparar contexto (responsabilidad de View)
2. Calcular rangos de fechas (utilidad)
3. Obtener y procesar turnos (lógica de negocio)
4. Calcular jornadas predeterminadas (lógica de negocio)
5. Construir estructuras de datos complejas (lógica de negocio)

**Solución**:
- Extraer cálculo de jornadas a `JornadaService.calcular_jornada_dia()`
- Extraer construcción de datos a `TurnoService.get_turnos_mes_dict()`
- Extraer procesamiento de solicitudes a `SolicitudConsultaService.get_solicitudes_por_turnos()`
- View solo orquesta llamadas a servicios

---

### 2.3 Otras Views con Lógica

**Archivos a revisar**:
- `turnos/api/views.py` - Lógica de cache y procesamiento
- `solicitudes/views.py` - Varias views con lógica mezclada

---

## VIOLACIÓN 3: Servicios con Responsabilidades Múltiples (MEDIA)

### 3.1 NotificacionService

**Ubicación**: `solicitudes/services/notificacion_service.py`

**Revisar**: Verificar si mezcla:
- Creación de notificaciones en BD
- Envío de emails
- Renderizado de templates

**Acción**: Si tiene múltiples responsabilidades, dividir en:
- `NotificacionService` - Gestión de notificaciones en BD
- `EmailService` - Envío de emails
- `TemplateService` - Renderizado de templates (opcional)

---

### 3.2 Otros Servicios

**Revisar**:
- `permiso_service.py`
- `empleado_service.py` (si existe)

---

## PLAN DE REFACTORIZACIÓN SRP

### FASE 3.1: Dividir SolicitudService

#### Servicio 1: EmpleadoDisponibilidadService
**Archivo**: `solicitudes/services/empleado_disponibilidad_service.py`
**Métodos**:
- `get_empleados_disponibles()`
- `get_empleados_jornada_contraria()`

**Dependencias**: `turnos.services.jornada_service` (para obtener jornadas)

---

#### Servicio 2: JornadaService
**Archivo**: `turnos/services/jornada_service.py`
**Métodos**:
- `get_jornada_explorador_fecha()`
- `calcular_jornada_dia()` (extraído de MisTurnosView)
- `get_jornada_predeterminada()`

**Responsabilidad única**: Gestión de jornadas de exploradores

---

#### Servicio 3: TurnoService
**Archivo**: `turnos/services/turno_service.py`
**Métodos**:
- `get_turno_explorador()`
- `get_salas_explorador()`
- `get_turnos_mes_dict()` (extraído de MisTurnosView)
- `get_turnos_por_fecha()`

**Responsabilidad única**: Gestión de turnos y salas

---

#### Servicio 4: SolicitudConsultaService
**Archivo**: `solicitudes/services/solicitud_consulta_service.py`
**Métodos**:
- `get_solicitudes_usuario()`
- `get_solicitudes_pendientes()`
- `get_solicitudes_por_receptor()`
- `get_solicitudes_por_supervisor()`
- `get_estado_aprobacion_solicitud()`
- `contar_cambios_explorador_fecha()`
- `get_contadores_usuario()` (extraído de SolicitudesView)
- `get_tipos_solicitud_activos()`

**Responsabilidad única**: Consultas y lecturas de solicitudes

---

#### Servicio 5: SolicitudAprobacionService
**Archivo**: `solicitudes/services/solicitud_aprobacion_service.py`
**Métodos**:
- `aprobar_solicitud_supervisor()`
- `aprobar_solicitud_receptor()`
- `rechazar_solicitud_supervisor()`
- `rechazar_solicitud_receptor()`

**Responsabilidad única**: Procesar aprobaciones y rechazos

**Nota**: Este servicio puede usar `SolicitudFactory` para aplicar cambios

---

#### SolicitudService (Refactorizado)
**Archivo**: `solicitudes/services/solicitud_service.py`
**Métodos restantes**:
- `crear_solicitud_cambio()` - Creación de solicitudes (core)

**Responsabilidad única**: Creación y gestión core de solicitudes

---

### FASE 3.2: Refactorizar Views

#### SolicitudesView
**Cambios**:
- Extraer lógica de contadores a `SolicitudConsultaService.get_contadores_usuario()`
- View solo prepara contexto

#### MisTurnosView
**Cambios**:
- Extraer cálculo de jornadas a `JornadaService`
- Extraer construcción de datos a `TurnoService`
- View solo orquesta servicios

---

## IMPACTO DE LAS VIOLACIONES

### Problemas Actuales:

1. **Mantenibilidad**: Cambios en una responsabilidad afectan otras
2. **Testabilidad**: Difícil testear responsabilidades aisladas
3. **Reutilización**: Código acoplado difícil de reutilizar
4. **Escalabilidad**: Agregar funcionalidad requiere modificar clases grandes
5. **Comprensión**: Difícil entender qué hace cada clase

### Beneficios Esperados:

1. ✅ **Mantenibilidad**: Cambios aislados por responsabilidad
2. ✅ **Testabilidad**: Tests más simples y enfocados
3. ✅ **Reutilización**: Servicios pequeños y reutilizables
4. ✅ **Escalabilidad**: Fácil agregar nuevas funcionalidades
5. ✅ **Comprensión**: Cada clase tiene un propósito claro

---

## ARCHIVOS A CREAR

1. `turnos/services/__init__.py`
2. `turnos/services/jornada_service.py`
3. `turnos/services/turno_service.py`
4. `solicitudes/services/empleado_disponibilidad_service.py`
5. `solicitudes/services/solicitud_consulta_service.py`
6. `solicitudes/services/solicitud_aprobacion_service.py`

## ARCHIVOS A MODIFICAR

1. `solicitudes/services/solicitud_service.py` - Refactorizar para usar nuevos servicios
2. `solicitudes/views.py` - Usar nuevos servicios
3. `turnos/views.py` - Usar nuevos servicios
4. Todos los archivos que importan `SolicitudService` - Actualizar imports

---

## ESTADO

- [x] Violaciones identificadas
- [x] Responsabilidades mapeadas
- [x] Plan de refactorización definido
- [ ] Implementación (FASE 3)

