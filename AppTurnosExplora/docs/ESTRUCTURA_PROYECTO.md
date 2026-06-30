# Estructura del Proyecto AppTurnosExplora

## 📋 Resumen

Este documento describe la estructura organizada del proyecto AppTurnosExplora después de la reorganización siguiendo las mejores prácticas de Django.

**Fecha de reorganización**: 2026-01-XX  
**Versión**: 2.0

---

## 🗂️ Estructura General

```
AppTurnosExplora/
├── config/                 # Configuración global de Django
│   ├── settings.py        # Configuración del proyecto
│   ├── urls.py            # URLs principales
│   ├── wsgi.py            # WSGI config
│   ├── asgi.py            # ASGI config
│   ├── db.py              # Configuración de base de datos
│   └── paths.py           # Rutas del proyecto
│
├── core/                   # Componentes transversales y compartidos
│   ├── mixins.py          # Mixins reutilizables (AdminRequiredMixin)
│   ├── utils/             # Utilidades generales
│   │   ├── date_utils.py
│   │   ├── jornada_utils.py
│   │   ├── json_responses.py
│   │   └── festivos_colombia.py
│   ├── services/           # Servicios transversales
│   │   └── cache_service.py
│   ├── interfaces/        # Interfaces para servicios
│   │   ├── empleado_disponibilidad_interface.py
│   │   └── turno_interface.py
│   ├── dashboard/         # App de dashboard
│   └── login/             # App de login
│
├── empleados/             # Módulo de empleados
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   ├── forms.py
│   ├── services/
│   │   └── empleado_service.py
│   ├── tests/             # Tests organizados
│   │   ├── test_models.py
│   │   ├── test_services.py
│   │   └── conftest.py
│   └── migrations/
│
├── turnos/                # Módulo de turnos
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   ├── forms.py
│   ├── api/               # API REST
│   │   ├── views.py
│   │   └── urls.py
│   ├── services/
│   │   ├── turno_service.py
│   │   ├── jornada_service.py
│   │   ├── alternancia_fines_semana_service.py
│   │   ├── dia_especial_service.py
│   │   ├── temporada_service.py
│   │   └── ...
│   ├── tests/
│   │   ├── test_models.py
│   │   ├── test_services.py
│   │   ├── test_views.py
│   │   ├── test_api.py
│   │   └── conftest.py
│   ├── management/
│   │   └── commands/
│   └── migrations/
│
├── permisos/              # Módulo de permisos
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   ├── tests/
│   │   ├── test_models.py
│   │   └── conftest.py
│   └── migrations/
│
├── solicitudes/           # Módulo de solicitudes (dominio principal)
│   ├── models.py
│   ├── views.py
│   ├── urls.py
│   ├── admin.py
│   ├── services/
│   │   ├── solicitud_service.py
│   │   ├── solicitud_factory.py
│   │   ├── solicitud_validator.py
│   │   ├── solicitud_aprobacion_service.py
│   │   ├── solicitud_consulta_service.py
│   │   ├── solicitud_context_service.py
│   │   ├── notificacion_service.py
│   │   ├── permiso_service.py
│   │   ├── empleado_disponibilidad_service.py
│   │   ├── strategies/    # Strategy Pattern
│   │   │   ├── base_strategy.py
│   │   │   ├── cambio_turno_strategy.py
│   │   │   ├── ct_permanente_strategy.py
│   │   │   ├── doblada_strategy.py
│   │   │   └── d_fds_strategy.py
│   │   └── ...
│   ├── tests/
│   │   ├── test_models.py
│   │   ├── test_services.py
│   │   ├── test_views.py
│   │   ├── test_strategies.py
│   │   ├── test_factory.py
│   │   ├── test_integration.py
│   │   ├── test_aprobacion.py
│   │   ├── test_cambio_sobre_cambio.py
│   │   └── conftest.py
│   ├── management/
│   │   └── commands/       # Management commands
│   │       ├── archivar_solicitudes_antiguas.py
│   │       ├── instalar_calendario_colombiano.py
│   │       ├── test_factory.py
│   │       ├── validar_jornadas.py
│   │       └── verificar_integridad_dobladas.py
│   └── migrations/
│
├── scripts/               # Scripts organizados por categoría
│   ├── tests/            # Scripts de prueba temporales
│   ├── debug/            # Scripts de debugging
│   ├── utils/            # Scripts de utilidad general
│   ├── migrations/       # Scripts de migraciones de BD
│   ├── data/             # Scripts de corrección de datos
│   ├── diagnostic/       # Scripts de diagnóstico
│   ├── maintenance/      # Scripts de mantenimiento
│   └── README.md         # Documentación de scripts
│
├── docs/                  # Documentación del proyecto
│   ├── test/             # Documentación de tests
│   │   ├── TEST_MANUAL_CAMBIO_TURNO_SENCILLO.md
│   │   └── REGLAS_NEGOCIO_CAMBIO_TURNO_SENCILLO.md
│   ├── deployment/       # Documentación de despliegue
│   │   └── MANUAL_DESPLIEGUE_EC2.md
│   └── ...               # Otra documentación
│
├── static/                # Archivos estáticos
│   ├── css/
│   ├── js/
│   ├── img/
│   └── plugins/
│
├── templates/             # Templates HTML
│   ├── base.html
│   ├── empleados/
│   ├── turnos/
│   ├── solicitudes/
│   └── ...
│
├── tests/                 # Tests de integración
│   ├── conftest.py
│   └── integration/
│
├── manage.py
├── requirements.txt
└── requirements-dev.txt
```

---

## 📦 Organización por Componente

### Apps Django

Cada app sigue la estructura estándar de Django:

```
app_name/
├── __init__.py
├── models.py          # Modelos de la app
├── views.py           # Vistas (FBV o CBV)
├── urls.py            # URLs de la app
├── admin.py           # Configuración de admin
├── apps.py            # Configuración de la app
├── services/          # Lógica de negocio (si aplica)
│   └── *.py
├── tests/             # Tests organizados
│   ├── test_models.py
│   ├── test_views.py
│   ├── test_services.py
│   └── conftest.py
└── migrations/        # Migraciones de BD
```

### Servicios

Los servicios contienen la lógica de negocio y están organizados por responsabilidad:

- **Servicios de dominio**: Lógica específica del dominio (ej: `solicitud_service.py`)
- **Servicios transversales**: Utilidades compartidas (ej: `cache_service.py`)
- **Servicios de aplicación**: Orquestación de operaciones complejas

### Tests

- **Tests unitarios**: En `tests/` de cada app
- **Tests de integración**: En `tests/integration/`
- **Tests de management commands**: En `tests/` de la app correspondiente
- **Scripts de prueba temporales**: En `scripts/tests/`

### Scripts

Organizados por propósito:

- **tests/**: Scripts de prueba temporales
- **debug/**: Scripts de debugging
- **utils/**: Scripts de utilidad general
- **migrations/**: Scripts relacionados con migraciones
- **data/**: Scripts de corrección de datos
- **diagnostic/**: Scripts de diagnóstico
- **maintenance/**: Scripts de mantenimiento

---

## ✅ Mejoras Aplicadas

1. ✅ **Raíz del proyecto limpia**: Solo archivos esenciales (manage.py, requirements.txt, etc.)
2. ✅ **Scripts organizados**: Categorizados por propósito en subcarpetas
3. ✅ **Tests organizados**: Todos en carpetas `tests/`, eliminados `tests.py` redundantes
4. ✅ **Documentación centralizada**: Todo en `docs/` con subcarpetas por tema
5. ✅ **Separación de responsabilidades**: Servicios, vistas, modelos bien separados
6. ✅ **Estructura escalable**: Fácil agregar nuevas funcionalidades

---

## 📝 Convenciones

### Nombres de Archivos

- **Modelos**: `models.py`
- **Vistas**: `views.py` o `views_*.py` si hay múltiples archivos
- **Servicios**: `*_service.py`
- **Tests**: `test_*.py`
- **Management commands**: `*.py` (sin prefijo)

### Estructura de Tests

```python
# tests/test_models.py
class ModelTestCase(TestCase):
    ...

# tests/test_views.py
class ViewTestCase(TestCase):
    ...

# tests/test_services.py
class ServiceTestCase(TestCase):
    ...
```

### Imports

```python
# Orden de imports:
# 1. Standard library
# 2. Third-party
# 3. Django
# 4. Local apps
from django.shortcuts import render
from core.utils import json_responses
from empleados.models import Empleado
from .models import SolicitudCambio
```

---

## 🔍 Búsqueda Rápida

- **Modelos**: `*/models.py`
- **Vistas**: `*/views.py`
- **Servicios**: `*/services/*.py`
- **Tests**: `*/tests/test_*.py`
- **URLs**: `*/urls.py`
- **Management commands**: `*/management/commands/*.py`
- **Scripts**: `scripts/*/`

---

**Última actualización**: 2026-01-XX




