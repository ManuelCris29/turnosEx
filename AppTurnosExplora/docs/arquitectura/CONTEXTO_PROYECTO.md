# Contexto del Proyecto AppTurnos

## 📋 Resumen Ejecutivo

**AppTurnos** es una aplicación web Django para la gestión de turnos de empleados, específicamente diseñada para el manejo de solicitudes de cambio de turno, turnos permanentes, dobladas y descansos fines de semana (D-FDS).

### Propósito Principal
- Gestión de solicitudes de cambio de turno entre empleados
- Aprobación por supervisor y receptor
- Notificaciones automáticas por email
- Sistema de calendario con festivos colombianos (Ley Emiliani)
- Gestión de jornadas y turnos de exploradores

---

## 🛠️ Stack Tecnológico

### Backend
- **Framework**: Django 5.2.2
- **Base de Datos**: MySQL (usando mysqlclient)
- **Lenguaje**: Python 3.x
- **Cache**: LocMemCache (desarrollo) / Redis (producción, configurado pero no activo)

### Librerías Principales
- `django-simple-history`: Historial de cambios en modelos
- `django-widget-tweaks`: Mejoras en formularios
- `mysqlclient`: Driver para MySQL

### Frontend
- Templates Django (HTML)
- JavaScript vanilla (sin framework)
- CSS personalizado

---

## 📁 Estructura del Proyecto

```
AppTurnosExplora/
├── config/                    # Configuración Django
│   ├── settings.py           # Settings principales
│   ├── db.py                 # Configuración de BD
│   └── urls.py               # URLs principales
│
├── core/                      # Componentes transversales
│   ├── login/                # App de autenticación
│   ├── dashboard/            # Dashboard principal
│   ├── mixins.py             # Mixins reutilizables
│   ├── utils/                # Utilidades generales
│   │   ├── date_utils.py     # Manejo de fechas
│   │   ├── jornada_utils.py  # Cálculo de jornadas
│   │   └── json_responses.py # Respuestas JSON
│   └── services/
│       └── cache_service.py  # Servicio de cache
│
├── empleados/                 # Módulo de empleados
│   ├── models.py
│   ├── services/
│   │   └── empleado_service.py
│   └── views.py
│
├── solicitudes/               # Módulo principal ⭐
│   ├── models.py             # Modelo Solicitud y relacionados
│   ├── services/             # Lógica de negocio
│   │   ├── solicitud_service.py           # Creación de solicitudes
│   │   ├── solicitud_factory.py           # Factory Pattern
│   │   ├── solicitud_validator.py         # Validaciones
│   │   ├── solicitud_consulta_service.py  # Consultas
│   │   ├── solicitud_aprobacion_service.py # Aprobaciones
│   │   ├── notificacion_service.py        # Envío de emails
│   │   ├── empleado_disponibilidad_service.py
│   │   ├── solicitud_context_service.py
│   │   └── strategies/       # Strategy Pattern por tipo
│   │       ├── base_strategy.py
│   │       ├── cambio_turno_strategy.py
│   │       ├── ct_permanente_strategy.py
│   │       ├── doblada_strategy.py
│   │       └── d_fds_strategy.py
│   └── views.py
│
├── turnos/                    # Módulo de turnos
│   ├── models.py             # Modelos Turno, Jornada
│   ├── services/
│   │   ├── turno_service.py
│   │   ├── jornada_service.py
│   │   └── turno_context_service.py
│   └── views.py
│
├── permisos/                  # Módulo de permisos
│   └── ...
│
└── templates/                 # Templates HTML
    └── solicitudes/          # Templates de solicitudes
```

---

## 🏗️ Arquitectura

### Principios Aplicados

#### 1. **Single Responsibility Principle (SRP)**
- Cada servicio tiene una única responsabilidad
- Separación clara entre servicios, vistas y modelos

#### 2. **Separación en Capas**
```
Views (Presentación)
    ↓
Services (Lógica de Negocio)
    ↓
Models (Persistencia)
```

#### 3. **Patrones de Diseño**
- **Factory Pattern**: `SolicitudFactory` para crear solicitudes por tipo
- **Strategy Pattern**: Diferentes estrategias por tipo de solicitud (CT, CT Permanente, Doblada, D-FDS)
- **Service Layer Pattern**: Lógica de negocio en servicios, no en vistas

### Flujo de una Solicitud

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

## 🎯 Funcionalidades Principales

### 1. Tipos de Solicitudes

#### Cambio de Turno (CT)
- Solicitud temporal de cambio de turno entre dos empleados
- Requiere aprobación de supervisor y receptor
- Solo en la misma fecha

#### Cambio de Turno Permanente (CT Permanente)
- Cambio permanente de turno
- Aplica a múltiples fechas futuras

#### Doblada
- Un empleado cubre el turno de otro
- Sin intercambio, solo un empleado trabaja ambos turnos

#### Descanso Fin de Semana (D-FDS)
- Solicitud para descansar en fin de semana
- Requiere que otro empleado cubra

### 2. Sistema de Aprobaciones
- Doble aprobación: Supervisor + Receptor
- Notificaciones automáticas por email
- Historial de cambios (django-simple-history)

### 3. Sistema de Festivos
- Calendario con festivos colombianos
- Ley Emiliani aplicada
- Cálculo automático de jornadas considerando festivos

### 4. Gestión de Jornadas
- Cálculo automático de jornadas
- Considera descansos y festivos
- Soporte para jornadas diurnas y nocturnas

---

## 💾 Base de Datos

### Modelos Principales

#### `Empleado`
- Información de empleados
- Relación con usuarios Django
- Estado activo/inactivo

#### `Solicitud`
- Tipo de solicitud (CT, CT Permanente, Doblada, D-FDS)
- Empleado solicitante y receptor
- Fecha(s) afectada(s)
- Estado (pendiente, aprobada, rechazada)
- Aprobaciones de supervisor y receptor

#### `Turno`
- Turnos asignados a empleados
- Relación con Jornada

#### `Jornada`
- Jornadas de exploradores
- Fecha y tipo de jornada
- Relación con empleados

---

## 📧 Sistema de Notificaciones

- **Backend**: SMTP Gmail
- **Email de envío**: manuel.moreno@parqueexplora.org
- **Notificaciones automáticas**:
  - Al crear solicitud (para receptor)
  - Al aprobar/rechazar (para solicitante y receptor)
  - Al aplicar cambios (confirmación)

---

## 🧪 Testing

### Estructura
```
{app}/tests/
├── __init__.py
├── conftest.py          # Fixtures compartidas
├── test_models.py       # Tests de modelos
├── test_services.py     # Tests de servicios
└── test_views.py        # Tests de vistas
```

### Tests de Integración
```
tests/integration/
└── test_solicitud_flow.py  # Flujos completos
```

**Nota**: El proyecto tiene estructura de tests creada, pero la cobertura puede variar.

---

## 📚 Documentación Disponible

### Ubicación Principal
Toda la documentación está organizada en la carpeta `docs/`:

```
docs/
├── README.md                    # Índice general
├── 00-introduccion/            # Visión general
├── 01-analisis/                # Análisis inicial
├── 02-refactorizacion/         # Proceso de refactorización
├── 03-arquitectura/            # Arquitectura detallada
├── 04-guias/                   # Guías de desarrollo
└── 05-referencia/              # Referencia técnica
```

### Documentos Clave en Raíz
- `ARQUITECTURA.md`: Arquitectura completa del proyecto
- `RESUMEN_REFACTORIZACION.md`: Resumen del proceso de refactorización
- `GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md`: Cómo agregar nuevos tipos de solicitud
- `COMO_FUNCIONAN_CALENDARIOS_FESTIVOS.md`: Explicación del sistema de festivos

---

## 🚀 Cómo Empezar

### 1. Configuración del Entorno

```bash
# Crear entorno virtual
python -m venv venvturnos

# Activar entorno virtual
# Windows:
venvturnos\Scripts\activate
# Linux/Mac:
source venvturnos/bin/activate

# Instalar dependencias
pip install -r AppTurnosExplora/requirements.txt
```

### 2. Configuración de Base de Datos

El proyecto usa MySQL. La configuración está en `AppTurnosExplora/config/db.py`.

**Archivo de ejemplo** (`config/db.py`):
```python
DATABASESMYSQL = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'nombre_bd',
        'USER': 'usuario',
        'PASSWORD': 'contraseña',
        'HOST': 'localhost',
        'PORT': '3306',
    }
}
```

### 3. Variables de Entorno / Configuración

- **Email**: Configurado en `settings.py` (líneas 164-170)
- **Secret Key**: En `settings.py` (línea 27) - **⚠️ Cambiar en producción**
- **Debug**: `True` en desarrollo (línea 30)

### 4. Migraciones

```bash
cd AppTurnosExplora
python manage.py makemigrations
python manage.py migrate
```

### 5. Crear Superusuario

```bash
python manage.py createsuperuser
```

### 6. Ejecutar Servidor

```bash
python manage.py runserver
```

---

## ⚙️ Configuraciones Importantes

### Cache
- **Desarrollo**: `LocMemCache` (configurado en `settings.py`)
- **Producción**: Redis (configuración comentada, lista para activar)

### Email
- **SMTP**: Gmail configurado
- **Email de envío**: manuel.moreno@parqueexplora.org
- **Backend de desarrollo**: Puede cambiarse a consola (comentado en settings)

### Seguridad
- ⚠️ `DEBUG = True` en desarrollo
- ⚠️ `SECRET_KEY` debe cambiarse en producción
- ⚠️ `ALLOWED_HOSTS` incluye `'*'` - ajustar en producción

---

## 🔍 Servicios Clave y sus Responsabilidades

### Solicitudes

| Servicio | Responsabilidad |
|----------|----------------|
| `SolicitudService` | Creación de solicitudes y cancelaciones |
| `SolicitudFactory` | Factory Pattern - Crear solicitudes por tipo |
| `SolicitudValidator` | Validaciones de negocio |
| `SolicitudConsultaService` | Consultas y filtrado |
| `SolicitudAprobacionService` | Aprobación/rechazo |
| `NotificacionService` | Envío de emails |
| `EmpleadoDisponibilidadService` | Búsqueda de empleados disponibles |

### Turnos

| Servicio | Responsabilidad |
|----------|----------------|
| `TurnoService` | Gestión de turnos asignados |
| `JornadaService` | Gestión de jornadas |
| `TurnoContextService` | Preparar contexto para vistas |

### Core

| Servicio | Responsabilidad |
|----------|----------------|
| `CacheService` | Gestión centralizada de cache |

---

## 📝 Convenciones de Código

### Nombres de Servicios
- Formato: `{Dominio}Service` o `{Accion}Service`
- Ejemplos: `SolicitudService`, `TurnoService`

### Métodos
- Verbos en infinitivo: `get_*`, `create_*`, `update_*`, `delete_*`
- Métodos estáticos (`@staticmethod`)
- Documentación con docstrings

### Estructura de Archivos
- Servicios en `{app}/services/`
- Utilidades en `core/utils/`
- Templates en `templates/{app}/`

---

## 🐛 Debugging y Troubleshooting

### Scripts de Debug
El proyecto incluye varios scripts de debug:
- `debug_luisa.py`
- `debug_manuel_notifications.py`
- `check_recent_requests.py`
- `test_manual_request.py`

### Logs
- Django logs en consola (cuando `DEBUG=True`)
- Historial de cambios en modelos (django-simple-history)

---

## 🔄 Estado Actual del Proyecto

### ✅ Completado
- Refactorización siguiendo principios SOLID
- Separación en servicios
- Factory y Strategy patterns implementados
- Sistema de notificaciones funcionando
- Documentación organizada

### 📋 Mejoras Futuras Sugeridas
- Aumentar cobertura de tests
- Optimizar queries N+1 restantes
- Configurar Redis para producción
- Documentar APIs REST (si se agregan)
- Estandarizar logging en servicios

---

## 📖 Referencias Rápidas

### Documentación Externa
- [Django 5.2 Docs](https://docs.djangoproject.com/en/5.2/)
- [django-simple-history](https://django-simple-history.readthedocs.io/)

### Documentación Interna
- Ver `docs/README.md` para índice completo
- `ARQUITECTURA.md` para arquitectura detallada
- `GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md` para extender funcionalidad

---

## 💡 Puntos Importantes para Nuevos Desarrolladores

1. **Siempre usar servicios, no lógica en vistas**: Las vistas solo orquestan, la lógica está en servicios
2. **Validar antes de crear**: Usar `SolicitudValidator` o el Factory para validaciones
3. **Cache cuando sea posible**: Usar `CacheService` para datos frecuentemente consultados
4. **Notificaciones automáticas**: El `NotificacionService` se encarga de enviar emails
5. **Nuevos tipos de solicitud**: Seguir el patrón Strategy (ver `strategies/`)

---

## 📞 Contacto y Soporte

- **Email configurado**: manuel.moreno@parqueexplora.org
- **Proyecto**: Parque Explora - Sistema de Gestión de Turnos

---

**Última actualización**: Enero 2025  
**Versión Django**: 5.2.2  
**Estado**: En desarrollo activo ✅



