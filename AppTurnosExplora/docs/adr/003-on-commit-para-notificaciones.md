# ADR 003: transaction.on_commit() para desacoplar notificaciones

**Estado:** Implementado  
**Fecha:** 2026-06

## Contexto

Las notificaciones por email se enviaban dentro de `transaction.atomic()`. Si el envío fallaba, toda la transacción de aprobación revertía — la solicitud quedaba sin aprobar por un error de email. Además, los emails podían enviarse aunque la transacción luego fallara por otro motivo.

## Decisión

Las llamadas a `NotificacionService` se movieron a `transaction.on_commit(lambda: _notificar_*(...))`  con funciones helper que envuelven el envío en `try/except`. Los errores solo se loguean, no se propagan.

Se descartó SQS/Celery porque:
1. El proyecto no tiene workers ni infraestructura de colas
2. `on_commit()` da la garantía esencial: notificación solo si la transacción commit exitosamente
3. Las notificaciones son best-effort en este sistema — no es crítico reintentarlas

## Consecuencias

- Una aprobación nunca revierte por fallo de email
- Los emails nunca se envían por transacciones que luego fallan
- Si un email falla, queda en el log pero la operación siguió adelante
- Cuando se migre a AWS, cambiar a SQS es reemplazar el lambda dentro de `on_commit`
