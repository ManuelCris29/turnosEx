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

### La base de datos de tests

Django no usa la base real: crea `test_<DB_NAME>` (por ejemplo `test_bdturnosex`), corre las
migraciones ahí, ejecuta los tests y al terminar la borra. La base real **nunca se toca**.

Si una corrida muere a medias (se cancela, se cierra la terminal, se mata el proceso), esa base
queda huérfana. Django, por defecto, pregunta por consola si puede borrarla:

```
Type 'yes' if you would like to try deleting the test database, or 'no' to cancel:
```

En una terminal basta con escribir `yes`. Pero si nadie puede responder —CI, un script, una
herramienta— el proceso se queda esperando o revienta con `EOFError: EOF when reading a line`, y
como la base huérfana sigue ahí, el intento siguiente se atasca igual.

**Este proyecto ya no pregunta**: `TEST_RUNNER` apunta a `core.test_runner.NoInputDiscoverRunner`
(ver `config/settings.py`), que fuerza `interactive=False`. Equivale a pasar `--noinput` siempre,
sin depender de acordarse. `pytest` tampoco pregunta (pytest-django ya corre en modo no
interactivo).

Banderas útiles:

| Bandera | Para qué |
|---|---|
| `--keepdb` | Reutiliza la base de test en vez de recrearla: ahorra el minuto de migraciones al iterar. **Evítala si hay migraciones nuevas**: puede quedarse con un esquema viejo y dar fallos falsos. |
| `--parallel` | Reparte los tests en varios procesos. Ojo con los tests que dependen de datos compartidos. |
| `-v2` | Muestra el nombre de cada test según va corriendo. |

Si la suite falla en bloque y los archivos aislados pasan, casi siempre es **otro proceso usando
la base de test**. Comprobar que no quede un `manage.py test` colgado antes de tocar código.

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


