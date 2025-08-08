# Servicios de Solicitudes

Esta carpeta contiene los servicios que manejan la lógica de negocio de la aplicación de solicitudes.

## Estructura

```
services/
├── __init__.py
├── solicitud_service.py
├── permiso_service.py
└── README.md
```

## Servicios Disponibles

### SolicitudService

Maneja toda la lógica relacionada con las solicitudes de cambio de turno.

**Métodos principales:**
- `get_empleados_disponibles(fecha, usuario_actual)`: Obtiene empleados disponibles
- `get_turno_explorador(explorador_id, fecha)`: Obtiene turno de un explorador
- `get_salas_explorador(explorador_id)`: Obtiene salas asignadas a un explorador
- `get_tipos_solicitud_activos()`: Obtiene tipos de solicitud activos
- `crear_solicitud_cambio(...)`: Crea una nueva solicitud
- `validar_solicitud_cambio(...)`: Valida una solicitud
- `get_solicitudes_usuario(usuario)`: Obtiene solicitudes de un usuario
- `get_solicitudes_pendientes()`: Obtiene solicitudes pendientes

### PermisoService

Maneja la lógica relacionada con los permisos y detalles de permisos.

**Métodos principales:**
- `get_permisos_usuario(usuario)`: Obtiene permisos de un usuario
- `get_permisos_pendientes()`: Obtiene permisos pendientes
- `crear_permiso_detalle(solicitud, horas_solicitadas)`: Crea detalle de permiso
- `validar_permiso(empleado, fecha, horas_solicitadas)`: Valida un permiso
- `calcular_horas_acumuladas(empleado, fecha_inicio, fecha_fin)`: Calcula horas acumuladas

## Beneficios de usar Servicios

1. **Separación de responsabilidades**: La lógica de negocio está separada de las vistas
2. **Reutilización**: Los servicios pueden ser usados en múltiples vistas
3. **Testabilidad**: Es más fácil escribir tests para la lógica de negocio
4. **Mantenibilidad**: El código es más fácil de mantener y modificar
5. **Legibilidad**: Las vistas son más limpias y fáciles de leer

## Uso en Vistas

```python
from .services.solicitud_service import SolicitudService

# En una vista
empleados = SolicitudService.get_empleados_disponibles(fecha, request.user)
```

## Convenciones

- Todos los métodos son estáticos (`@staticmethod`)
- Los nombres de métodos son descriptivos y en snake_case
- Cada método tiene documentación clara
- Los servicios manejan la lógica de negocio, no la presentación 