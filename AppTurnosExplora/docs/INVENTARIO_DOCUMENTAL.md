# Inventario documental — AppTurnos / SWALP

Auditoría de qué está documentado, qué está a medias y qué falta. Generado el
2026-07-25 con el skill `project-documentation-master` (Fase 0).

El criterio no es la fecha del archivo: un área se marca **desactualizada** solo si se
contrastó una afirmación concreta contra el código y no coincide. Cuando no se hizo esa
comprobación, el estado es **sin verificar**.

## Resumen

| Área | Estado | Dónde está | Qué falta |
|---|---|---|---|
| Arquitectura técnica | completo | [03-arquitectura/ARQUITECTURA.md](./03-arquitectura/ARQUITECTURA.md), [adr/](./03-arquitectura/adr/) | Nada crítico; ahora se enlaza desde el manual técnico |
| Decisiones técnicas (ADR) | completo | [adr/001](./03-arquitectura/adr/001-service-layer-y-orchestrator.md) a [005](./03-arquitectura/adr/005-pendientes-aws.md) | — |
| Reglas de negocio de solicitudes | parcial | [05-referencia/solicitudes/](./05-referencia/solicitudes/) | Cubre CT sencillo y dobladas a fondo; cambio de descanso, D FDS y CT permanente estaban dispersos |
| Dobladas | completo | [solicitudes/dobladas/](./05-referencia/solicitudes/dobladas/) (14 archivos) | Muy detallado, pero orientado a incidencias concretas, no a lectura de principio a fin |
| Turnos (fuente de verdad) | completo | [05-referencia/turnos/](./05-referencia/turnos/) | — |
| Despliegue | completo | [05-referencia/deployment/](./05-referencia/deployment/) | AWS EC2+RDS, Fargate y Docker local | 
| Pruebas | completo | [05-referencia/pruebas/INVENTARIO_TESTS.md](./05-referencia/pruebas/INVENTARIO_TESTS.md) | — |
| Patrones de protección | completo | `PROTECTION_PATTERNS.md` (raíz del repo) | Vive fuera de `docs/`; no está enlazado desde el índice |
| Mantenimiento anual | completo | [04-guias/mantenimiento-anual/](./04-guias/mantenimiento-anual/) | — |
| Festivos y calendario | completo | [04-guias/festivos/](./04-guias/festivos/) | — |
| Extensión del sistema | completo | [04-guias/GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md](./04-guias/GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md) | — |
| **Manual de usuario final** | **faltaba** | — | **Cubierto ahora**: [manual_usuario.md](./manual_usuario.md) |
| **Manual técnico de entrada** | **faltaba** | — | **Cubierto ahora**: [manual_tecnico.md](./manual_tecnico.md) |
| Roles y permisos | falta | — | No hay un documento que diga qué puede hacer cada rol; se deduce leyendo `AdminRequiredMixin` y las vistas |
| Glosario del dominio | falta | — | Términos como *cesión*, *doblada*, *alternancia*, *temporada*, *D FDS* no están definidos en un solo lugar |
| Permisos y PDH | falta | — | La app `permisos/` casi no aparece en `docs/` |
| Módulo empleados | falta | — | Salas, competencias, restricciones, sanciones e indicadores sin documentación funcional |
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
