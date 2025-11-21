# Guía de Tests - Proyecto AppTurnos

## Estructura de Tests

Los tests están organizados en la siguiente estructura:

```
AppTurnosExplora/
  {app}/
    tests/
      __init__.py
      conftest.py          # Fixtures específicas de la app
      test_models.py       # Tests de modelos
      test_services.py     # Tests de servicios
      test_views.py        # Tests de vistas
      test_*.py           # Tests específicos (factory, strategies, etc.)
      fixtures/           # Datos de prueba
        __init__.py

tests/                    # Tests globales
  __init__.py
  conftest.py            # Fixtures globales compartidas
  integration/           # Tests de integración end-to-end
    __init__.py
    test_*.py
```

---

## Cómo Ejecutar Tests

### Con Django TestCase (nativo):
```bash
cd AppTurnosExplora
python manage.py test
```

### Ejecutar tests de una app específica:
```bash
python manage.py test solicitudes
python manage.py test turnos
python manage.py test empleados
```

### Ejecutar un test específico:
```bash
python manage.py test solicitudes.tests.test_models.TipoSolicitudCambioModelTest
```

### Con pytest (recomendado):
```bash
cd AppTurnosExplora
pytest
```

### Ejecutar tests con cobertura:
```bash
pytest --cov=AppTurnosExplora --cov-report=html
```

---

## Cómo Agregar Nuevos Tests

### 1. Tests de Modelos
Crear o editar `{app}/tests/test_models.py`:

```python
from django.test import TestCase
from {app}.models import MiModelo

class MiModeloTest(TestCase):
    def setUp(self):
        # Preparar datos de prueba
        pass
    
    def test_creacion(self):
        # Test de creación
        pass
```

### 2. Tests de Servicios
Crear o editar `{app}/tests/test_services.py`:

```python
from django.test import TestCase
from {app}.services.mi_service import MiService

class MiServiceTest(TestCase):
    def setUp(self):
        # Preparar datos de prueba
        pass
    
    def test_metodo_del_servicio(self):
        # Test del método
        pass
```

### 3. Tests de Vistas
Crear o editar `{app}/tests/test_views.py`:

```python
from django.test import TestCase, Client
from django.urls import reverse

class MiViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        # Preparar usuario autenticado si es necesario
    
    def test_vista_requiere_login(self):
        # Test de autenticación
        pass
```

### 4. Tests de Integración
Crear o editar `tests/integration/test_*.py`:

```python
from django.test import TestCase

class MiFlujoE2ETest(TestCase):
    def test_flujo_completo(self):
        # Test del flujo completo
        pass
```

---

## Fixtures Compartidas

### Fixtures Globales (`tests/conftest.py`):
- `user_test` - Usuario de prueba
- `empleado_test` - Empleado de prueba

### Fixtures por App (`{app}/tests/conftest.py`):
- Fixtures específicas de cada app

### Uso de Fixtures:
```python
def test_con_fixture(self, empleado_test):
    # empleado_test está disponible automáticamente
    self.assertIsNotNone(empleado_test)
```

---

## Convenciones

1. **Nombres de archivos**: `test_*.py`
2. **Nombres de clases**: `*Test` o `*TestCase`
3. **Nombres de métodos**: `test_*`
4. **Organización**: Un archivo por tipo (models, services, views)
5. **Fixtures**: En `conftest.py` para reutilización

---

## Tests Migrados

Los siguientes tests fueron migrados desde `management/commands/`:

- `test_aprobar_solicitud.py` → `solicitudes/tests/test_integration.py` (pendiente)
- `test_cambio_sobre_cambio.py` → `solicitudes/tests/test_integration.py` (pendiente)
- `test_factory.py` → `solicitudes/tests/test_factory.py` (pendiente)

---

## Estado Actual

- [x] Estructura de tests creada
- [x] Tests base creados
- [x] Fixtures configuradas
- [ ] Tests de management commands migrados
- [ ] Tests sueltos de raíz migrados
- [ ] Cobertura de tests aumentada

---

## Próximos Pasos

1. Migrar tests de `management/commands/` a estructura de tests
2. Migrar tests sueltos de raíz
3. Aumentar cobertura de tests
4. Configurar CI/CD para ejecutar tests automáticamente

