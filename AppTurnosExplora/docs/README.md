# 📚 Documentación — AppTurnos / SWALP

Documentación única del proyecto, organizada por temas. (Se unificó aquí la
carpeta `docs/` que estaba en la raíz del repo; ya no existe una segunda copia.)

## Estructura

| Carpeta | Contenido |
|---|---|
| **[00-introduccion](./00-introduccion/)** | Contexto y estructura general del proyecto. |
| **[01-analisis](./01-analisis/)** | Análisis técnico: duplicaciones, SOLID, SRP, modelos, migración AWS (histórico). |
| **[02-refactorizacion](./02-refactorizacion/)** | Refactorizaciones y migraciones: fases, planes, resúmenes, verificaciones, migración de JavaScript, optimizaciones. |
| **[03-arquitectura](./03-arquitectura/)** | Arquitectura, ADRs (decisiones técnicas), modelo de base de datos, tecnologías frontend, pendientes. |
| **[04-guias](./04-guias/)** | Guías operativas: festivos, integraciones (Google Apps Script, iframe), manuales, notas, **mantenimiento-anual**, CDN a estáticos. |
| **[05-referencia](./05-referencia/)** | Referencia de dominio y despliegue (ver abajo). |
| **[99-archivo](./99-archivo/)** | Documentos históricos de reorganización (se conservan por trazabilidad). |
| **[images](./images/)** | Diagramas e imágenes. |

## 05-referencia (lo más consultado)

| Subcarpeta | Contenido |
|---|---|
| **[deployment](./05-referencia/deployment/)** | **Despliegue en AWS**: [arquitectura recomendada](./05-referencia/deployment/arquitectura-aws-rds-recomendada.md) (EC2 y Fargate), checklists paso a paso [EC2+RDS+SES](./05-referencia/deployment/CHECKLIST_DESPLIEGUE_AWS_RDS.md) y [ECS Fargate](./05-referencia/deployment/CHECKLIST_DESPLIEGUE_FARGATE.md), manual EC2, plan de correo transaccional. |
| **[solicitudes](./05-referencia/solicitudes/)** | Reglas de negocio de solicitudes, características CT, y **dobladas/** (flujo, integridad, casos). |
| **[turnos](./05-referencia/turnos/)** | Fuente de verdad de turnos, decisiones sobre jornada/pago sábado. |
| **[pruebas](./05-referencia/pruebas/)** | Inventario de tests, matriz de casos, guía de pruebas. |

---

> **Nota:** las dependencias del proyecto están en `AppTurnosExplora/requirements.txt`
> (producción) y `requirements-dev.txt` (desarrollo/tests). No hay copias en la raíz.
