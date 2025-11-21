# Inventario de Tests - Proyecto AppTurnos

## Fecha: 2025-01-XX

## RESUMEN EJECUTIVO

**Estado actual**: Tests dispersos e incompletos
- **Tests en management commands**: 3 archivos
- **Tests sueltos en raíz**: 8 archivos
- **Tests.py en apps**: 6 archivos (todos vacíos o con código comentado)
- **Cobertura**: Desconocida (no hay reportes)

---

## TESTS EN MANAGEMENT COMMANDS

### Ubicación: `AppTurnosExplora/solicitudes/management/commands/`

#### 1. test_aprobar_solicitud.py
**Tipo**: Management Command
**Propósito**: Probar proceso de aprobación de solicitudes
**Estado**: ✅ Funcional
**Cobertura**:
- Creación de solicitudes
- Aprobación por supervisor
- Aprobación por receptor
- Verificación de turnos creados

**Acción**: Mover a `solicitudes/tests/test_services.py` o `test_integration.py`

---

#### 2. test_cambio_sobre_cambio.py
**Tipo**: Management Command
**Propósito**: FASE 2.6 - Probar escenario completo de cambio sobre cambio
**Estado**: ✅ Funcional
**Cobertura**:
- Cambios secuenciales de turno
- Validación de límites
- Verificación de integridad de datos

**Acción**: Mover a `solicitudes/tests/test_integration.py`

---

#### 3. test_factory.py
**Tipo**: Management Command
**Propósito**: Probar el factory de estrategias
**Estado**: ✅ Funcional
**Cobertura**:
- Registro de estrategias
- Instanciación de estrategias
- Mapeo de tipos a estrategias

**Acción**: Mover a `solicitudes/tests/test_factory.py`

---

#### 4. validar_jornadas.py
**Tipo**: Management Command
**Propósito**: Validar jornadas después de cambios
**Estado**: ✅ Funcional (herramienta de diagnóstico)
**Cobertura**: Validación de datos

**Acción**: Mantener como command (no es test unitario)

---

## TESTS SUELTOS EN RAÍZ

### Ubicación: `AppTurnosExplora/`

#### 1. test_architecture.py
**Tipo**: Script standalone
**Propósito**: Verificar que la nueva arquitectura funciona correctamente
**Estado**: ✅ Funcional
**Cobertura**:
- Registro de estrategias
- Instanciación de estrategias
- Tipos de solicitud en BD
- Métodos del factory

**Acción**: Mover a `solicitudes/tests/test_factory.py` o `test_architecture.py`

---

#### 2. test_cancelacion_solicitudes.py
**Tipo**: Script standalone
**Propósito**: Probar cancelación de solicitudes
**Estado**: ❓ Desconocido (no revisado en detalle)
**Acción**: Revisar y mover a `solicitudes/tests/test_services.py`

---

#### 3. test_counter.py
**Tipo**: Script standalone
**Propósito**: Probar contadores de solicitudes
**Estado**: ❓ Desconocido
**Acción**: Revisar y mover a `solicitudes/tests/test_views.py` o `test_services.py`

---

#### 4. test_ct_permanente.py
**Tipo**: Script standalone
**Propósito**: Probar cambio de turno permanente
**Estado**: ❓ Desconocido
**Acción**: Revisar y mover a `solicitudes/tests/test_strategies.py` o `test_integration.py`

---

#### 5. test_email_from_user.py
**Tipo**: Script standalone
**Propósito**: Probar envío de emails
**Estado**: ❓ Desconocido
**Acción**: Revisar y mover a `solicitudes/tests/test_services.py` (notificacion_service)

---

#### 6. test_jornadas_corregidas.py
**Tipo**: Script standalone
**Propósito**: Probar jornadas corregidas
**Estado**: ❓ Desconocido
**Acción**: Revisar y mover a `turnos/tests/test_services.py` o `test_models.py`

---

#### 7. test_manual_request.py
**Tipo**: Script standalone
**Propósito**: Crear solicitud manualmente para pruebas
**Estado**: ❓ Desconocido
**Acción**: Revisar y mover a `solicitudes/tests/fixtures/` o mantener como utilidad

---

#### 8. test_new_notification.py
**Tipo**: Script standalone
**Propósito**: Probar creación de notificaciones
**Estado**: ❓ Desconocido
**Acción**: Revisar y mover a `solicitudes/tests/test_services.py` (notificacion_service)

---

## TESTS.PY EN APPS (Vacíos o Comentados)

### 1. solicitudes/tests.py
**Estado**: Vacío
**Acción**: Crear estructura de tests organizada

---

### 2. turnos/tests.py
**Estado**: Vacío
**Acción**: Crear estructura de tests organizada

---

### 3. empleados/tests.py
**Estado**: Código comentado (ejemplo de RoleTestCase)
**Acción**: Descomentar y organizar, crear estructura completa

---

### 4. permisos/tests.py
**Estado**: Vacío
**Acción**: Crear estructura de tests organizada

---

### 5. core/login/tests.py
**Estado**: Vacío
**Acción**: Crear tests de autenticación

---

### 6. core/dashboard/tests.py
**Estado**: Vacío
**Acción**: Crear tests de dashboard

---

## ESTRUCTURA PROPUESTA DE TESTS

### Estructura por App:

```
{app}/
  tests/
    __init__.py
    test_models.py          # Tests de modelos
    test_services.py        # Tests de servicios
    test_views.py           # Tests de vistas
    test_utils.py           # Tests de utilidades (si aplica)
    fixtures/               # Datos de prueba
      __init__.py
      factories.py          # Factory Boy factories (opcional)
      sample_data.json      # Datos de ejemplo
    conftest.py             # Fixtures compartidas (pytest)
```

### Estructura Global:

```
tests/
  conftest.py              # Fixtures globales compartidas
  integration/             # Tests de integración
    test_solicitud_flow.py
    test_turno_flow.py
  utils/                   # Utilidades de testing
    test_helpers.py
```

---

## PLAN DE REORGANIZACIÓN

### FASE 1.1: Crear Estructura Base

1. Crear `tests/` en cada app:
   - `solicitudes/tests/`
   - `turnos/tests/`
   - `empleados/tests/`
   - `permisos/tests/`
   - `core/login/tests/`
   - `core/dashboard/tests/`

2. Crear `tests/` global para tests de integración

### FASE 1.2: Mover Tests Existentes

1. **Management Commands → Tests**:
   - `test_aprobar_solicitud.py` → `solicitudes/tests/test_integration.py`
   - `test_cambio_sobre_cambio.py` → `solicitudes/tests/test_integration.py`
   - `test_factory.py` → `solicitudes/tests/test_factory.py`

2. **Raíz → Tests**:
   - `test_architecture.py` → `solicitudes/tests/test_factory.py` (integrar)
   - `test_cancelacion_solicitudes.py` → `solicitudes/tests/test_services.py`
   - `test_counter.py` → `solicitudes/tests/test_views.py`
   - `test_ct_permanente.py` → `solicitudes/tests/test_strategies.py`
   - `test_email_from_user.py` → `solicitudes/tests/test_services.py`
   - `test_jornadas_corregidas.py` → `turnos/tests/test_services.py`
   - `test_manual_request.py` → `solicitudes/tests/fixtures/` o mantener como utilidad
   - `test_new_notification.py` → `solicitudes/tests/test_services.py`

### FASE 1.3: Crear Tests Base

1. **Smoke Tests** para funcionalidades críticas:
   - Crear solicitud
   - Aprobar solicitud
   - Obtener empleados disponibles
   - Obtener turnos

2. **Tests de Integración** para flujos principales:
   - Flujo completo de cambio de turno
   - Flujo de aprobación
   - Flujo de cambio sobre cambio

### FASE 1.4: Configurar Testing

1. Verificar si `pytest-django` está instalado
2. Crear `pytest.ini` o `setup.cfg` con configuración
3. Crear `conftest.py` global con fixtures compartidas

---

## TESTS CRÍTICOS FALTANTES

### Solicitudes:
- [ ] Test de creación de solicitud
- [ ] Test de validación de solicitud
- [ ] Test de aprobación completa
- [ ] Test de rechazo
- [ ] Test de cancelación
- [ ] Test de FCFS (First-Come, First-Served)
- [ ] Test de cambio sobre cambio
- [ ] Test de límite de cambios

### Turnos:
- [ ] Test de obtención de jornada
- [ ] Test de cálculo de jornada por día
- [ ] Test de obtención de turnos
- [ ] Test de construcción de datos mensuales

### Empleados:
- [ ] Test de obtención de empleados disponibles
- [ ] Test de filtrado por jornada contraria

### Servicios:
- [ ] Test de cache
- [ ] Test de notificaciones
- [ ] Test de emails

---

## COBERTURA ACTUAL

### Estimación:
- **Modelos**: ~0% (no hay tests)
- **Servicios**: ~20% (algunos tests en commands)
- **Views**: ~0% (no hay tests)
- **Integración**: ~30% (tests en commands y scripts)

### Objetivo:
- **Modelos**: 80%+
- **Servicios**: 90%+
- **Views**: 70%+
- **Integración**: 80%+

---

## HERRAMIENTAS DE TESTING

### Actual:
- Django TestCase (disponible)
- Management commands (usado actualmente)

### Recomendado:
- **pytest-django**: Framework más moderno y flexible
- **factory_boy**: Para crear fixtures de datos
- **coverage**: Para medir cobertura
- **mock**: Para mockear dependencias (ya incluido en Python 3.3+)

---

## ARCHIVOS A CREAR

1. `solicitudes/tests/__init__.py`
2. `solicitudes/tests/test_models.py`
3. `solicitudes/tests/test_services.py`
4. `solicitudes/tests/test_views.py`
5. `solicitudes/tests/test_factory.py`
6. `solicitudes/tests/test_strategies.py`
7. `solicitudes/tests/test_integration.py`
8. `solicitudes/tests/conftest.py`
9. `turnos/tests/__init__.py`
10. `turnos/tests/test_models.py`
11. `turnos/tests/test_services.py`
12. `turnos/tests/test_views.py`
13. `turnos/tests/conftest.py`
14. `empleados/tests/__init__.py`
15. `empleados/tests/test_models.py`
16. `empleados/tests/test_services.py`
17. `tests/conftest.py` (global)
18. `pytest.ini` o `setup.cfg`

---

## ARCHIVOS A MOVER/ELIMINAR

### Mover:
- `solicitudes/management/commands/test_*.py` → `solicitudes/tests/`
- `test_*.py` (raíz) → `{app}/tests/`

### Eliminar después de mover:
- Tests duplicados
- Scripts de prueba obsoletos

---

## ESTADO

- [x] Tests existentes mapeados
- [x] Estructura propuesta definida
- [x] Plan de reorganización creado
- [ ] Implementación (FASE 1)

