# Estructura Objetivo - Proyecto AppTurnos

## Fecha: enero 2025 · **revisado el 26 ago 2026**

> ## ⚠ Estado: DOCUMENTO HISTÓRICO — su "objetivo" ya se alcanzó en su mayor parte
>
> Es el plan de enero de 2025, no una descripción del proyecto de hoy. Se conserva
> por trazabilidad: explica **por qué** la estructura actual es como es.
>
> **No lo uses como lista de tareas.** Casi todo lo que pide ya existe, y su
> sección «ESTRUCTURA ACTUAL» describe un proyecto que dejó de existir hace más
> de un año. Comprobado el 26 ago 2026:
>
> | Este documento dice | Realidad |
> |---|---|
> | `empleados/tests.py (vacío)`, `permisos/tests.py (vacío)` | Ambos tienen carpeta `tests/` poblada. **1 439 tests** en el proyecto, todos en verde |
> | `solicitud_service.py ⚠️ Múltiples responsabilidades` | Ya descompuesto: `orchestrator`, `factory`, `strategies/`, `validators/`, servicios de aplicación |
> | «ARCHIVOS A CREAR»: interfaces, repositorios, casos de uso | Creados: `core/interfaces/`, `solicitudes/repositories/`, `solicitudes/use_cases/`, `solicitudes/domain/` |
> | Estructura por capas como meta futura | Es la estructura actual |
>
> Lo que SÍ sigue abierto de este plan —adoptar los repositorios que ya existen,
> partir las funciones gigantes— está medido y priorizado en
> [pendientes-arquitectura.md](./pendientes-arquitectura.md), que es el documento
> vivo. Este no lo es.

## RESUMEN EJECUTIVO

Este documento describe la estructura objetivo del proyecto después de aplicar principios SOLID y mejores prácticas de organización.

---

## ESTRUCTURA ACTUAL

```
AppTurnosExplora/
  config/                    # Configuración Django
  core/                      # Apps core
    dashboard/
    login/
  empleados/                 # App empleados
    services/
      empleado_service.py
    models.py
    views.py
    tests.py (vacío)
  permisos/                  # App permisos
    models.py
    views.py
    tests.py (vacío)
  solicitudes/               # App solicitudes
    management/
      commands/              # Tests y utilidades
    services/
      strategies/            # Strategy Pattern
      solicitud_service.py   # ⚠️ Múltiples responsabilidades
      notificacion_service.py
      permiso_service.py
      solicitud_factory.py
      solicitud_validator.py
    models.py
    views.py
    tests.py (vacío)
  turnos/                    # App turnos
    api/
    services/
      turno_service.py      # ⚠️ Servicio pequeño, podría expandirse
    models.py
    views.py
    tests.py (vacío)
  test_*.py                  # ⚠️ Tests sueltos en raíz
```

### Problemas Identificados:

1. **Falta `core/utils/`** - Utilidades compartidas mezcladas
2. **Falta `core/mixins/`** - Mixins duplicados
3. **Servicios con responsabilidades múltiples** - `SolicitudService` hace demasiado
4. **Tests desorganizados** - Tests en commands y raíz
5. **Falta estructura de tests** - Tests.py vacíos

---

## ESTRUCTURA OBJETIVO

```
AppTurnosExplora/
  config/                    # Configuración Django
    settings.py
    urls.py
    wsgi.py
    asgi.py
  
  core/                      # Módulo core compartido
    __init__.py
    mixins.py                # ✅ Mixins compartidos (AdminRequiredMixin)
    utils/                   # ✅ Utilidades compartidas
      __init__.py
      json_responses.py      # ✅ Helpers JSON (json_ok, json_error)
    services/                # ✅ Servicios compartidos
      __init__.py
      cache_service.py       # ✅ Servicio de cache centralizado
  
  empleados/                 # App empleados
    __init__.py
    models.py
    views.py
    urls.py
    admin.py
    services/
      __init__.py
      empleado_service.py
    tests/                   # ✅ Estructura de tests
      __init__.py
      test_models.py
      test_services.py
      test_views.py
      conftest.py
      fixtures/
        __init__.py
  
  permisos/                  # App permisos
    __init__.py
    models.py
    views.py
    urls.py
    admin.py
    tests/                   # ✅ Estructura de tests
      __init__.py
      test_models.py
      test_views.py
      conftest.py
  
  solicitudes/               # App solicitudes
    __init__.py
    models.py
    views.py
    urls.py
    admin.py
    management/
      commands/
        archivar_solicitudes_antiguas.py
        actualizar_codigos_estrategia.py
        instalar_calendario_colombiano.py
        validar_jornadas.py  # Herramienta de diagnóstico
    services/
      __init__.py
      # ✅ Servicios divididos por responsabilidad
      solicitud_service.py           # Core: creación de solicitudes
      solicitud_factory.py           # Factory Pattern
      solicitud_validator.py         # Validaciones
      empleado_disponibilidad_service.py  # ✅ Nueva: búsqueda de empleados
      solicitud_consulta_service.py      # ✅ Nueva: consultas de solicitudes
      solicitud_aprobacion_service.py    # ✅ Nueva: aprobación/rechazo
      notificacion_service.py
      permiso_service.py
      strategies/                     # Strategy Pattern
        __init__.py
        base_strategy.py
        cambio_turno_strategy.py
        ct_permanente_strategy.py
        doblada_strategy.py
        d_fds_strategy.py
    tests/                   # ✅ Estructura de tests organizada
      __init__.py
      test_models.py
      test_services.py
      test_views.py
      test_factory.py
      test_strategies.py
      test_integration.py
      conftest.py
      fixtures/
        __init__.py
  
  turnos/                    # App turnos
    __init__.py
    models.py
    views.py
    urls.py
    admin.py
    api/                     # API REST
      __init__.py
      urls.py
      views.py
    services/
      __init__.py
      turno_service.py       # ✅ Expandido: gestión de turnos
      jornada_service.py     # ✅ Nueva: gestión de jornadas
    management/
      commands/
        archivar_turnos_antiguos.py
    tests/                   # ✅ Estructura de tests
      __init__.py
      test_models.py
      test_services.py
      test_views.py
      test_api.py
      conftest.py
      fixtures/
        __init__.py
  
  tests/                    # ✅ Tests de integración globales
    __init__.py
    conftest.py             # Fixtures globales compartidas
    integration/
      __init__.py
      test_solicitud_flow.py
      test_turno_flow.py
  
  # Archivos de configuración
  manage.py
  requirements.txt
  pytest.ini                 # ✅ Configuración de pytest
  .coveragerc                # ✅ Configuración de coverage (opcional)
```

---

## PRINCIPIOS APLICADOS

### 1. Single Responsibility Principle (SRP)

#### Antes:
- `SolicitudService` con 15+ métodos y múltiples responsabilidades

#### Después:
- `SolicitudService` - Solo creación de solicitudes (core)
- `EmpleadoDisponibilidadService` - Búsqueda de empleados
- `JornadaService` - Gestión de jornadas
- `TurnoService` - Gestión de turnos
- `SolicitudConsultaService` - Consultas de solicitudes
- `SolicitudAprobacionService` - Aprobación/rechazo

---

### 2. Open/Closed Principle (OCP)

#### Ya implementado:
- Strategy Pattern permite agregar nuevos tipos sin modificar código existente
- Factory Pattern permite extensión sin modificación

#### Mejoras:
- Servicios pequeños y extensibles
- Interfaces claras para extensión

---

### 3. Liskov Substitution Principle (LSP)

#### Ya implementado:
- Estrategias son intercambiables
- `SolicitudStrategy` base permite sustitución

#### Verificar:
- Todas las estrategias cumplen el contrato base

---

### 4. Interface Segregation Principle (ISP)

#### Mejoras:
- Servicios pequeños con interfaces específicas
- No hay servicios con métodos no usados

---

### 5. Dependency Inversion Principle (DIP)

#### Mejoras:
- Views dependen de servicios (abstracciones)
- Servicios dependen de modelos (abstracciones de Django ORM)
- Factory Pattern para creación de estrategias

---

## ORGANIZACIÓN POR CAPAS

### Capa 1: Models (Datos)
- `{app}/models.py` - Modelos de Django
- Responsabilidad: Definir estructura de datos

### Capa 2: Services (Lógica de Negocio)
- `{app}/services/` - Servicios de dominio
- Responsabilidad: Lógica de negocio pura
- Sin dependencias de Django (excepto ORM)

### Capa 3: Views (Presentación)
- `{app}/views.py` - Vistas Django
- `{app}/api/views.py` - API REST
- Responsabilidad: Preparar datos para templates/API
- Depende de Services, no de Models directamente

### Capa 4: Templates (UI)
- `{app}/templates/` - Templates HTML
- Responsabilidad: Presentación visual

---

## DEPENDENCIAS ENTRE MÓDULOS

```
Views → Services → Models
         ↓
      Core Utils
```

### Reglas:
1. **Views** solo llaman a **Services**
2. **Services** usan **Models** y **Core Utils**
3. **Core Utils** no depende de apps específicas
4. **Models** no depende de nada (excepto Django)

---

## SERVICIOS POR DOMINIO

### Dominio: Solicitudes
- `SolicitudService` - Core
- `SolicitudFactory` - Factory
- `SolicitudValidator` - Validaciones
- `SolicitudConsultaService` - Consultas
- `SolicitudAprobacionService` - Aprobación/rechazo
- `EmpleadoDisponibilidadService` - Búsqueda de empleados
- `NotificacionService` - Notificaciones

### Dominio: Turnos
- `TurnoService` - Gestión de turnos
- `JornadaService` - Gestión de jornadas

### Dominio: Empleados
- `EmpleadoService` - Gestión de empleados

### Dominio: Core (Compartido)
- `CacheService` - Gestión de cache
- `JsonResponses` - Helpers JSON
- `AdminRequiredMixin` - Mixin de permisos

---

## TESTS POR CAPA

### Unit Tests:
- `test_models.py` - Tests de modelos
- `test_services.py` - Tests de servicios
- `test_utils.py` - Tests de utilidades

### Integration Tests:
- `test_views.py` - Tests de vistas
- `test_integration.py` - Tests de flujos completos

### E2E Tests:
- `tests/integration/` - Tests end-to-end

---

## ARCHIVOS A CREAR

### Core:
1. `core/mixins.py`
2. `core/utils/__init__.py`
3. `core/utils/json_responses.py`
4. `core/services/__init__.py`
5. `core/services/cache_service.py`

### Solicitudes:
6. `solicitudes/services/empleado_disponibilidad_service.py`
7. `solicitudes/services/solicitud_consulta_service.py`
8. `solicitudes/services/solicitud_aprobacion_service.py`
9. `solicitudes/tests/__init__.py`
10. `solicitudes/tests/test_models.py`
11. `solicitudes/tests/test_services.py`
12. `solicitudes/tests/test_views.py`
13. `solicitudes/tests/test_factory.py`
14. `solicitudes/tests/test_strategies.py`
15. `solicitudes/tests/test_integration.py`
16. `solicitudes/tests/conftest.py`

### Turnos:
17. `turnos/services/jornada_service.py`
18. `turnos/tests/__init__.py`
19. `turnos/tests/test_models.py`
20. `turnos/tests/test_services.py`
21. `turnos/tests/test_views.py`
22. `turnos/tests/test_api.py`
23. `turnos/tests/conftest.py`

### Tests Globales:
24. `tests/__init__.py`
25. `tests/conftest.py`
26. `tests/integration/__init__.py`
27. `tests/integration/test_solicitud_flow.py`

### Configuración:
28. `pytest.ini`

---

## ARCHIVOS A MODIFICAR

### Core:
- Ninguno (nuevo módulo)

### Solicitudes:
- `solicitudes/services/solicitud_service.py` - Refactorizar para usar nuevos servicios
- `solicitudes/views.py` - Usar nuevos servicios y core utils

### Turnos:
- `turnos/views.py` - Usar nuevos servicios
- `turnos/services/turno_service.py` - Expandir funcionalidad

### Empleados:
- `empleados/views.py` - Usar core mixins

### Permisos:
- `permisos/views.py` - Usar core mixins

---

## MIGRACIÓN GRADUAL

### Paso 1: Crear estructura base
- Crear directorios y archivos vacíos
- No romper funcionalidad existente

### Paso 2: Mover código existente
- Extraer código a nuevos servicios
- Mantener compatibilidad temporal

### Paso 3: Actualizar referencias
- Actualizar imports gradualmente
- Validar después de cada cambio

### Paso 4: Eliminar código antiguo
- Eliminar código duplicado
- Limpiar imports no usados

---

## BENEFICIOS ESPERADOS

1. ✅ **Mantenibilidad**: Código organizado y fácil de encontrar
2. ✅ **Testabilidad**: Tests organizados y fáciles de ejecutar
3. ✅ **Escalabilidad**: Fácil agregar nuevas funcionalidades
4. ✅ **Comprensión**: Estructura clara y documentada
5. ✅ **Reutilización**: Servicios pequeños y reutilizables
6. ✅ **Calidad**: Principios SOLID aplicados

---

## ESTADO

- [x] Estructura actual analizada
- [x] Estructura objetivo diseñada
- [x] Principios SOLID aplicados
- [x] Plan de migración definido
- [ ] Implementación (FASES 1-6)


