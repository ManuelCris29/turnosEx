# ADR 002: Máquina de Estados sin librería externa (django-fsm)

**Estado:** Implementado  
**Fecha:** 2026-06

## Contexto

Los estados de `SolicitudCambio` (pendiente, aprobada, rechazada, cancelada, pagada, reemplazada) se asignaban directamente con `solicitud.estado = '...'` en 3 archivos distintos sin validar si la transición era legal. Era posible pasar de `rechazada` a `aprobada` sin que el código lo detectara.

## Decisión

Se implementó `solicitudes/domain/estado_machine.py` con un diccionario `_TRANSICIONES` y la función `transicionar(solicitud, nuevo_estado)` que lanza `EstadoTransicionError` si la transición no está permitida.

Se descartó `django-fsm` porque:
1. Agrega una dependencia externa para un problema que se resuelve con ~50 líneas propias
2. Requiere decoradores en el modelo, mezclando dominio con infraestructura Django
3. La FSM de este proyecto tiene 6 estados y 8 transiciones — no justifica una librería

## Consecuencias

- Cualquier intento de transición ilegal falla con excepción clara
- Los estados terminales (rechazada, cancelada, pagada, reemplazada) son irrompibles
- Fácil de extender: agregar un estado nuevo es una línea en `_TRANSICIONES`
