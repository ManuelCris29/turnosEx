"""Capa de servicios de permisos.

Estos cuatro módulos vivían sueltos en la raíz de la app (`permisos/services.py`,
`permisos/credito_horas_service.py`, …) mientras `solicitudes/` y `turnos/` ya agrupaban los
suyos en un paquete `services/`. Misma responsabilidad, dos sitios distintos según la app:
quien llegaba nuevo no podía predecir dónde buscar la lógica de negocio.

`PermisoNotificacionService` y `PermisoMediaJornadaService` se re-exportan aquí porque estaban
en `permisos/services.py` y ese import (`from permisos.services import …`) es el que usan las
vistas y los tests; el paquete lo mantiene válido.
"""
from .permiso_service import PermisoMediaJornadaService, PermisoNotificacionService

__all__ = ['PermisoNotificacionService', 'PermisoMediaJornadaService']
