# Inventario documental — AppTurnos / SWALP

Auditoría de qué está documentado, qué está a medias y qué falta. Generado el
2026-07-25 con el skill `project-documentation-master` (Fase 0) y **actualizado el 2026-08-09**
tras la reconstrucción completa de los dos manuales
([manual_usuario.md](./manual_usuario.md), 1.579 líneas;
[manual_tecnico.md](./manual_tecnico.md), 1.496 líneas).

El criterio no es la fecha del archivo: un área se marca **desactualizada** solo si se
contrastó una afirmación concreta contra el código y no coincide. Cuando no se hizo esa
comprobación, el estado es **sin verificar**.

## Resumen

| Área | Estado | Dónde está | Qué falta |
|---|---|---|---|
| Arquitectura técnica | completo | [03-arquitectura/ARQUITECTURA.md](./03-arquitectura/ARQUITECTURA.md), [adr/](./03-arquitectura/adr/) | Nada crítico; ahora se enlaza desde el manual técnico |
| Decisiones técnicas (ADR) | completo | [adr/001](./03-arquitectura/adr/001-service-layer-y-orchestrator.md) a [010](./03-arquitectura/adr/010-dia-de-descanso-libre-tras-el-intercambio.md) | — |
| **Auditoría de calidad (SOLID / arquitectura / código limpio)** | **completo** | [03-arquitectura/AUDITORIA_CALIDAD_2026-08.md](./03-arquitectura/AUDITORIA_CALIDAD_2026-08.md) | Línea base del 2026-08-19: 52 % de adherencia, 5 fases de refactor priorizadas. Contrastado con doc oficial de Django 5.2, django-axes y Gunicorn vía Context7. Incluye §9: comparativa EC2 vs Fargate y su interacción con los hallazgos. Pendiente: verificar nonces de django-csp (no indexado) |
| Reglas de negocio de solicitudes | parcial | [05-referencia/solicitudes/](./05-referencia/solicitudes/) | Cubre CT sencillo y dobladas a fondo; cambio de descanso, D FDS y CT permanente estaban dispersos |
| Dobladas | completo | [solicitudes/dobladas/](./05-referencia/solicitudes/dobladas/) (14 archivos) | Muy detallado, pero orientado a incidencias concretas, no a lectura de principio a fin |
| Turnos (fuente de verdad) | completo | [05-referencia/turnos/](./05-referencia/turnos/) | — |
| Despliegue | completo | [05-referencia/deployment/](./05-referencia/deployment/) | AWS EC2+RDS, Fargate y Docker local | 
| Pruebas | completo | [05-referencia/pruebas/INVENTARIO_TESTS.md](./05-referencia/pruebas/INVENTARIO_TESTS.md) | — |
| Patrones de protección | completo | `PROTECTION_PATTERNS.md` (raíz del repo) | Vive fuera de `docs/`; no está enlazado desde el índice |
| Mantenimiento anual | completo | [04-guias/mantenimiento-anual/](./04-guias/mantenimiento-anual/) | — |
| Festivos y calendario | completo | [04-guias/festivos/](./04-guias/festivos/) | — |
| Extensión del sistema | completo | [04-guias/GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md](./04-guias/GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md) | — |
| **Manual de usuario final** | **completo** | [manual_usuario.md](./manual_usuario.md) + [pdf/Manual_Usuario.pdf](./pdf/Manual_Usuario.pdf) | Reconstruido el 2026-08-08. Organizado por rol, con glosario |
| **Manual técnico de entrada** | **completo** | [manual_tecnico.md](./manual_tecnico.md) + [pdf/Manual_Tecnico.pdf](./pdf/Manual_Tecnico.pdf) | Reconstruido el 2026-08-09: 18 secciones, ficha por modelo, 5 endpoints con los 12 campos, 5 diagramas Mermaid |
| Roles y permisos | **cubierto** | [manual_usuario.md](./manual_usuario.md) (qué puede hacer cada rol) y [manual_tecnico.md § 9.2](./manual_tecnico.md) (dónde se comprueba: `core/mixins.py`) | Falta la lista vista por vista de `turnos/`, `empleados/` y `permisos/` — anotado en "Por confirmar" nº 8 |
| Glosario del dominio | **cubierto** | [manual_usuario.md](./manual_usuario.md) § 1.3, referenciado desde el manual técnico | Fuente única; no se duplica en el manual técnico |
| Modelos y base de datos | **completo** | [manual_tecnico.md § 5](./manual_tecnico.md) | Ficha de los 4 grupos de modelos + `erDiagram` + migraciones delicadas |
| Endpoints y URLs | **parcial** | [manual_tecnico.md § 6](./manual_tecnico.md) | Tabla completa de rutas de `solicitudes/`; fichas de 12 campos solo para los 5 endpoints no triviales. `turnos/`, `empleados/` y `permisos/` solo a nivel de grupo |
| Configuración y variables de entorno | **completo** | [manual_tecnico.md § 10](./manual_tecnico.md) | 26 variables con obligatoriedad, tipo, default y línea donde se leen. Sin valores reales |
| Seguridad | **completo, con hallazgos** | [manual_tecnico.md § 9 y § 16.3](./manual_tecnico.md) | Documenta 3 riesgos abiertos: clave HMAC en el código (B1), tokens sin caducidad (B2), sin recuperación de contraseña (B3) |
| Permisos y PDH | parcial | `permisos/models.py` documentado en [manual_tecnico.md § 5.2](./manual_tecnico.md); flujo funcional en el manual de usuario | Sigue sin ficha propia de los flujos de aprobación de permisos, al nivel de los seis formularios |
| Módulo empleados | parcial | Modelos en [manual_tecnico.md § 5.2](./manual_tecnico.md) | Salas, competencias, restricciones e indicadores siguen sin documentación funcional detallada |
| Reglas en `.docx` | sin verificar | `instructivos/` (raíz del repo) | Formato binario; su contenido no se pudo contrastar con el código |
| Requisitos de doblada en Word | sin verificar | [04-guias/manuales/](./04-guias/manuales/) — "requisito doblada.docx" (1,1 MB), "Proceso completo doblada.docx" (348 KB), "estrucutra sql.docx" | Formato binario. Por tamaño y título parecen la especificación original de dobladas: la fuente más valiosa sin contrastar |

## Huecos que este trabajo cierra

1. **Puerta de entrada para desarrolladores nuevos.** Había 100+ documentos técnicos,
   pero ninguno que sirviera de punto de partida. `manual_tecnico.md` es ese índice
   narrado; los documentos existentes siguen siendo la referencia profunda.
2. **Manual para el usuario final.** No existía documentación en lenguaje llano para
   exploradores y supervisores. `manual_usuario.md` la aporta, organizada por rol.
3. **Roles y permisos.** Se documentan por primera vez a partir del código.
4. **Glosario.** Incluido en ambos manuales.

## Huecos que quedan abiertos

- **`instructivos/*.docx` y `*.mwb`.** Contienen las reglas dictadas por el negocio
  ("regla de negocios de cada solicitud", "Matriz de combinación doblada", "Casos de
  dobladas"). Al ser binarios no se pudieron contrastar con el código. Conviene
  exportarlos a Markdown y confrontarlos con lo implementado: es la vía más probable de
  encontrar divergencias reales entre lo acordado y lo construido.
- **App `permisos/` y app `empleados/`.** Este trabajo las cubre a nivel funcional
  básico. Merecen fichas propias con el mismo detalle que los seis formularios.
- **`PROTECTION_PATTERNS.md` vive fuera de `docs/`.** Funciona, pero rompe el "una sola
  fuente de verdad": conviene moverlo a `docs/03-arquitectura/` o enlazarlo desde el
  índice.
- **La carpeta `02-refactorizacion/`** documenta fases ya terminadas. Es historia útil,
  pero un lector nuevo puede confundirla con el estado actual. Convendría marcarla como
  histórica o moverla a `99-archivo/`.

## Pendientes heredados de "Por confirmar" del manual técnico (2026-08-09)

Las 13 filas de [manual_tecnico.md § 18](./manual_tecnico.md) son deuda documental viva. Las
que afectan al inventario:

| Tema | Qué falta | Coste estimado |
|---|---|---|
| Outbox y rollback (B5) | Confirmar si `crear_solicitud` encola el correo dentro de la misma `transaction.atomic()`; de ello depende que el bug del correo irretirable exista o no | Leer las 6 estrategias + `EmailOutboxService` |
| Cobertura de tests | Ejecutar `pytest --cov` y publicar el porcentaje real por app | Requiere MySQL levantado |
| Recuento de migraciones | Contar las de `turnos`, `empleados` y `permisos`; el dato de la § 1.3 del manual técnico procede de una pasada anterior y el de `solicitudes` ya no coincide (35, no 33) | Minutos |
| Permisos vista por vista | Listar qué vistas de `turnos/`, `empleados/` y `permisos/` exigen rol supervisor | Medio |
| `Dockerfile` | Documentar imagen base, usuario, `HEALTHCHECK` y `ENTRYPOINT` | Bajo |
| Cron del outbox | Documentar la frecuencia real en producción (es configuración de infraestructura, no está en el código) | Bajo |
| CSP report-only | Confirmar si ha generado violaciones y promover la política estricta | Requiere entorno desplegado |
| ADR que faltan | Registrar como ADR tres decisiones ya tomadas y solo documentadas en comentarios: el patrón outbox, la `UniqueConstraint` con columna discriminante `activo_key`, y `core/constants.py` como fuente única de vocabularios | Bajo |
| Documentos `.docx` sin contrastar | `instructivos/*.docx`, `04-guias/manuales/*.docx` y `PLAN_CORREO_TRANSACCIONAL_Y_LATENCIA.docx` | Alto; es la vía más probable de encontrar divergencias reales |
