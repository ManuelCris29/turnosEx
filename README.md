# turnosEx — AppTurnos / SWALP

Aplicación web para la gestión de turnos, solicitudes (cambios de turno, dobladas,
permisos, descansos) y reportes del personal.

## Estructura del repositorio

| Ruta | Contenido |
|---|---|
| **[AppTurnosExplora/](./AppTurnosExplora/)** | Código de la aplicación (Django) **y toda su documentación**. |
| `docker-compose.yml` | Orquestación local. |
| `PROTECTION_PATTERNS.md` | Patrones de protección aplicados en el código. |

## Documentación

> **La documentación del proyecto está dentro de [`AppTurnosExplora/docs/`](./AppTurnosExplora/docs/).**

Punto de entrada: [`AppTurnosExplora/docs/README.md`](./AppTurnosExplora/docs/README.md).

| Documento | Para quién |
|---|---|
| [Manual de usuario](./AppTurnosExplora/docs/manual_usuario.md) | Exploradores y supervisores: qué hace la app y cómo usar cada formulario. |
| [Manual técnico](./AppTurnosExplora/docs/manual_tecnico.md) | Desarrolladores: arquitectura, reglas de negocio, zonas frágiles. |
| [Inventario documental](./AppTurnosExplora/docs/INVENTARIO_DOCUMENTAL.md) | Qué está documentado y qué falta. |
| [Despliegue (Dokploy)](./AppTurnosExplora/docs/05-referencia/deployment/) | Guías y checklist de despliegue y operación. |

Versiones en PDF de los manuales: [`AppTurnosExplora/docs/pdf/`](./AppTurnosExplora/docs/pdf/).
