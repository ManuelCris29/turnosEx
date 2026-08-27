# Arquitectura del Proyecto AppTurnos

## Fecha: enero 2025 · **revisado el 26 ago 2026**

> ## ⚠ Estado: PARCIALMENTE DESACTUALIZADO — leer esto antes que nada
>
> Escrito en enero de 2025. Los **principios y patrones** (SOLID, Service Layer,
> Factory, Strategy, capas) siguen describiendo bien el proyecto. El **inventario
> de archivos concreto NO**: se ha quedado atrás en 19 meses.
>
> Comprobado el 26 ago 2026:
>
> | Este documento dice | Realidad |
> |---|---|
> | 9 servicios en `solicitudes/services/` | **32 módulos** |
> | `empleados/views.py`, `solicitudes/views.py` como ARCHIVOS | Son **paquetes** (`views/`) en `solicitudes`, `turnos` y `empleados` |
> | `SolicitudValidator` como servicio de 1 clase | Repartido en `services/validators/` (4 módulos); el archivo original tiene 20 líneas |
> | No menciona `email_service.py` | Existe desde ago-2026, extraído de `notificacion_service.py` |
> | No menciona `core/constants.py` | Existe, y es de lectura obligatoria: 4 vocabularios que comparten textos |
> | No menciona `repositories/`, `use_cases/`, `domain/` | Existen los tres |
>
> **Fuentes de verdad para lo que este documento no alcanza:**
> - Estado medido y línea base de calidad → [AUDITORIA_CALIDAD_2026-08.md](./AUDITORIA_CALIDAD_2026-08.md)
> - Decisiones y su porqué → [adr/](./adr/) (011 ADRs)
> - Qué falta y qué ya no → [pendientes-arquitectura.md](./pendientes-arquitectura.md)
> - Entrada para desarrolladores → [../manual_tecnico.md](../manual_tecnico.md)

## RESUMEN EJECUTIVO

Este documento describe la arquitectura del proyecto AppTurnos después de la refactorización siguiendo principios SOLID y mejores prácticas de desarrollo.

---

## ESTRUCTURA DEL PROYECTO

```
AppTurnosExplora/
├── config/                 # Configuración global de Django
│   ├── settings.py        # Configuración del proyecto
│   ├── urls.py            # URLs principales
│   └── ...
├── core/                   # Componentes transversales y compartidos
│   ├── constants.py       # ⚠ LOS 4 VOCABULARIOS DE DOMINIO. Leer su cabecera
│   ├── interfaces/        # Abstracciones para DIP (ITurnoService, …)
│   ├── mixins.py          # Mixins reutilizables (AdminRequiredMixin)
│   ├── checks.py          # System checks propios (p. ej. caché multiproceso)
│   ├── utils/             # Utilidades generales
│   │   ├── date_utils.py  # Utilidades de fechas
│   │   ├── jornada_utils.py # Utilidades de jornadas
│   │   ├── festivos_colombia.py
│   │   └── json_responses.py # Helpers JSON
│   ├── services/          # Servicios transversales
│   │   └── cache_service.py # Servicio de cache centralizado
│   ├── dashboard/         # App de dashboard
│   └── login/             # App de login
├── empleados/             # Módulo de empleados
│   ├── models.py
│   ├── services/
│   ├── views/             # PAQUETE, no un views.py
│   └── tests/
├── permisos/               # Módulo de permisos
│   ├── models.py
│   ├── services.py
│   ├── views.py
│   └── tests/
├── solicitudes/            # Módulo de solicitudes (dominio principal)
│   ├── models.py
│   ├── domain/            # Reglas puras, SIN ORM (vigilado por test)
│   │   └── estado_machine.py
│   ├── use_cases/         # crear / aprobar / cancelar solicitud
│   ├── repositories/      # Queries centralizadas (creado; POCO adoptado)
│   ├── services/          # 32 módulos — `ls` manda sobre esta lista
│   │   ├── solicitud_orchestrator.py   # Punto de entrada
│   │   ├── solicitud_factory.py        # Factory de estrategias
│   │   ├── notificacion_service.py
│   │   ├── email_service.py            # Extraído de notificacion_service
│   │   ├── validators/                 # Sustituye a solicitud_validator.py
│   │   └── strategies/                 # Una por tipo de solicitud
│   │       ├── base_strategy.py
│   │       ├── cambio_turno_strategy.py
│   │       ├── cambio_descanso_strategy.py
│   │       ├── ct_permanente_strategy.py
│   │       ├── doblada_strategy.py
│   │       ├── doblada_permanente_strategy.py
│   │       └── d_fds_strategy.py
│   ├── views/             # PAQUETE, no un views.py
│   └── tests/
├── turnos/                 # Módulo de turnos
│   ├── models.py
│   ├── services/
│   │   ├── jornada_service.py
│   │   ├── turno_context_service.py
│   │   └── turno_service.py
│   ├── api/                # API endpoints
│   │   └── views.py
│   ├── views.py
│   └── tests/
└── tests/                  # Tests de integración a nivel de proyecto
    └── integration/
```

---

## PRINCIPIOS ARQUITECTÓNICOS

### 1. Single Responsibility Principle (SRP)

Cada clase/módulo tiene una única responsabilidad:

- **Servicios**: Lógica de negocio específica de un dominio
- **Vistas**: Orquestación y presentación (delegando a servicios)
- **Modelos**: Persistencia de datos
- **Utilidades**: Funciones helper reutilizables

### 2. Separación de Capas

```
┌─────────────────────────────────────┐
│         Vistas (Views)              │  ← Capa de presentación
│  (Orquestación, validación HTTP)    │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│      Servicios (Services)           │  ← Capa de lógica de negocio
│  (Reglas de negocio, validaciones)  │
└──────────────┬──────────────────────┘
               │
               ▼
┌─────────────────────────────────────┐
│      Modelos (Models)                │  ← Capa de persistencia
│  (Datos, relaciones, validaciones)  │
└─────────────────────────────────────┘
```

### 3. Organización por Dominio

Los servicios se agrupan lógicamente dentro de sus respectivas aplicaciones:

- **`solicitudes/services/`**: Lógica relacionada con solicitudes
- **`turnos/services/`**: Lógica relacionada con turnos y jornadas
- **`empleados/services/`**: Lógica relacionada con empleados
- **`core/services/`**: Servicios transversales (cache)

---

## SERVICIOS Y SUS RESPONSABILIDADES

### Core Services (Transversales)

#### `CacheService` (`core/services/cache_service.py`)
- **Responsabilidad**: Gestión centralizada de cache
- **Métodos principales**:
  - `get(key)`: Obtener valor del cache
  - `set(key, value, ttl)`: Establecer valor en cache
  - `get_or_set(key, callback, ttl)`: Obtener o calcular y guardar
  - `delete(key)`: Eliminar del cache

### Solicitudes Services

#### `SolicitudService` (`solicitudes/services/solicitud_service.py`)
- **Responsabilidad**: Creación de solicitudes y cancelaciones automáticas
- **Métodos principales**:
  - `crear_solicitud_cambio()`: Crear nueva solicitud

#### `SolicitudConsultaService` (`solicitudes/services/solicitud_consulta_service.py`)
- **Responsabilidad**: Consulta y filtrado de solicitudes
- **Métodos principales**:
  - `get_solicitudes_usuario()`
  - `get_solicitudes_pendientes_para_empleado()`
  - `get_solicitudes_por_receptor()`
  - `get_solicitudes_por_supervisor()`
  - `get_estado_aprobacion_solicitud()`
  - `get_tipos_solicitud_activos()`
  - `contar_cambios_explorador_fecha()`

#### `SolicitudAprobacionService` (`solicitudes/services/solicitud_aprobacion_service.py`)
- **Responsabilidad**: Aprobación y rechazo de solicitudes
- **Métodos principales**:
  - `aprobar_solicitud_supervisor()`
  - `aprobar_solicitud_receptor()`
  - `rechazar_solicitud_supervisor()`
  - `rechazar_solicitud_receptor()`

#### `EmpleadoDisponibilidadService` (`solicitudes/services/empleado_disponibilidad_service.py`)
- **Responsabilidad**: Búsqueda y filtrado de empleados disponibles
- **Métodos principales**:
  - `get_empleados_disponibles()`
  - `get_empleados_jornada_contraria()`

#### `SolicitudContextService` (`solicitudes/services/solicitud_context_service.py`)
- **Responsabilidad**: Preparar contexto para vistas de solicitudes
- **Métodos principales**:
  - `get_context_data_for_solicitudes_view()`

#### `SolicitudFactory` (`solicitudes/services/solicitud_factory.py`)
- **Responsabilidad**: Factory Pattern para crear y validar solicitudes según tipo
- **Métodos principales**:
  - `crear_solicitud()`
  - `validar_solicitud()`
  - `aplicar_cambios()`

#### `SolicitudValidator` (`solicitudes/services/solicitud_validator.py`)
- **Responsabilidad**: Validaciones de negocio para solicitudes
- **Métodos principales**:
  - `validar_empleado_activo()`
  - `validar_no_mismo_empleado()`
  - `validar_jornada_en_fecha()`
  - `validar_duplicada_misma_fecha()`
  - Y otras validaciones específicas

### Turnos Services

#### `JornadaService` (`turnos/services/jornada_service.py`)
- **Responsabilidad**: Gestión de jornadas de exploradores
- **Métodos principales**:
  - `get_jornada_explorador_fecha()`
  - `get_jornada_predeterminada()`
  - `calcular_jornada_dia()` (deprecated, usar `JornadaUtils`)

#### `TurnoService` (`turnos/services/turno_service.py`)
- **Responsabilidad**: Gestión de turnos asignados
- **Métodos principales**:
  - `get_turno_explorador()`
  - `get_salas_explorador()`
  - `get_turnos_por_fecha()`
  - `get_exploradores_por_jornada()`

#### `TurnoContextService` (`turnos/services/turno_context_service.py`)
- **Responsabilidad**: Preparar contexto para vistas de turnos
- **Métodos principales**:
  - `get_context_data_for_mis_turnos_view()`

---

## UTILIDADES COMUNES

### `DateUtils` (`core/utils/date_utils.py`)
- **Responsabilidad**: Conversión y formateo de fechas
- **Métodos principales**:
  - `parse_date()`: Convertir string/date a date
  - `format_date()`: Formatear fecha a string
  - `format_date_display()`: Formatear para mostrar (DD/MM/YYYY)
  - `format_datetime_display()`: Formatear datetime para mostrar

### `JornadaUtils` (`core/utils/jornada_utils.py`)
- **Responsabilidad**: Cálculo de jornadas según reglas de negocio
- **Métodos principales**:
  - `calcular_jornada_dia()`: Calcular jornada considerando descansos

### `json_ok` / `json_error` (`core/utils/json_responses.py`)
- **Responsabilidad**: Respuestas JSON estandarizadas
- **Funciones**:
  - `json_ok()`: Respuesta exitosa
  - `json_error()`: Respuesta de error

---

## PATRONES DE DISEÑO UTILIZADOS

### 1. Factory Pattern
- **Implementación**: `SolicitudFactory`
- **Propósito**: Crear instancias de solicitudes según su tipo sin exponer la lógica de creación

### 2. Strategy Pattern
- **Implementación**: `SolicitudStrategy` y sus implementaciones
- **Propósito**: Diferentes tipos de solicitudes (CT, CT Permanente, Doblada, D FDS) tienen comportamientos específicos

### 3. Service Layer Pattern
- **Implementación**: Todos los servicios en `*/services/`
- **Propósito**: Separar lógica de negocio de las vistas y modelos

---

## FLUJO DE UNA SOLICITUD

```
1. Usuario envía solicitud
   └─> Vista (ProcesarSolicitudView)
       └─> SolicitudFactory.validar_solicitud()
           └─> Strategy específica.validar_solicitud()
       └─> SolicitudFactory.crear_solicitud()
           └─> SolicitudService.crear_solicitud_cambio()
               └─> NotificacionService (envía notificaciones)

2. Supervisor/Receptor aprueba
   └─> Vista (AprobarSolicitudView)
       └─> SolicitudAprobacionService.aprobar_solicitud_*()
           └─> Si ambos aprueban:
               └─> SolicitudFactory.aplicar_cambios()
                   └─> Strategy específica.aplicar_cambios()
                       └─> Crear/actualizar Turnos
```

---

## CONVENCIONES DE CÓDIGO

### Nombres de Servicios
- Formato: `{Dominio}Service` o `{Accion}Service`
- Ejemplos: `SolicitudService`, `TurnoService`, `CacheService`

### Nombres de Métodos
- Verbos en infinitivo: `get_*`, `create_*`, `update_*`, `delete_*`
- Claros y descriptivos

### Estructura de Servicios
- Métodos estáticos (`@staticmethod`)
- Documentación con docstrings
- Type hints cuando es posible

---

## TESTING

### Estructura de Tests
```
{app}/tests/
├── __init__.py
├── conftest.py          # Fixtures compartidas
├── test_models.py       # Tests de modelos
├── test_services.py     # Tests de servicios
├── test_views.py        # Tests de vistas
└── fixtures/            # Datos de prueba
```

### Tests de Integración
```
tests/integration/
└── test_solicitud_flow.py  # Flujos completos
```

---

## MEJORES PRÁCTICAS APLICADAS

1. ✅ **SRP**: Cada servicio tiene una responsabilidad única
2. ✅ **DRY**: Utilidades comunes centralizadas
3. ✅ **Separación de capas**: Vistas → Servicios → Modelos
4. ✅ **Cache centralizado**: `CacheService` con TTLs consistentes
5. ✅ **Validaciones centralizadas**: `SolicitudValidator`
6. ✅ **Factory Pattern**: Para creación de solicitudes
7. ✅ **Strategy Pattern**: Para diferentes tipos de solicitudes
8. ✅ **Type hints**: Donde es posible y útil
9. ✅ **Documentación**: Docstrings en servicios y métodos importantes

---

## PRÓXIMOS PASOS SUGERIDOS

1. **FASE 5**: Aplicar resto de principios SOLID (OCP, LSP, ISP, DIP)
2. **Mejoras de rendimiento**: Optimizar queries N+1 restantes
3. **Tests**: Aumentar cobertura de tests unitarios e integración
4. **Documentación**: Documentar APIs y endpoints
5. **Logging**: Estandarizar logging en servicios

---

## NOTAS

- Los servicios están diseñados para ser fácilmente testables
- La arquitectura permite agregar nuevos tipos de solicitudes sin modificar código existente (OCP)
- Las utilidades comunes facilitan el mantenimiento y consistencia


