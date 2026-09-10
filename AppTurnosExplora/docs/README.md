# 📚 Documentación — AppTurnos / SWALP

Documentación única del proyecto, organizada por temas. (Se unificó aquí la
carpeta `docs/` que estaba en la raíz del repo; ya no existe una segunda copia.)

## Empezar por aquí

| Documento | Para quién |
|---|---|
| **[manual_usuario.md](./manual_usuario.md)** | Exploradores y supervisores: qué hace la app y cómo usar cada formulario. |
| **[manual_tecnico.md](./manual_tecnico.md)** | Desarrolladores: arquitectura, patrones aplicados, reglas de negocio con su cita en código, zonas frágiles. |
| **[INVENTARIO_DOCUMENTAL.md](./INVENTARIO_DOCUMENTAL.md)** | Qué está documentado, qué falta y qué está sin verificar. |

Versiones en Word de los dos manuales: [04-guias/manuales/](./04-guias/manuales/).
Versiones en **PDF**: [pdf/](./pdf/) — `Manual_Usuario.pdf` y `Manual_Tecnico.pdf`.

Ambos formatos son **artefactos generados**: se editan en el Markdown, nunca en el
`.docx` ni en el `.pdf`. Los mantienen los subagentes `subagen-user` y `subagen-dev`
(ver `.claude/agents/`), que regeneran el PDF con:

```bash
python .claude/skills/project-documentation-master/scripts/md_to_pdf.py \
  AppTurnosExplora/docs/manual_usuario.md \
  AppTurnosExplora/docs/pdf/Manual_Usuario.pdf \
  --titulo "Manual de Usuario" --subtitulo "AppTurnos / SWALP"
```

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
| **[deployment](./05-referencia/deployment/)** | **Despliegue y operación**, en cuatro carpetas ([índice](./05-referencia/deployment/README.md)): **[`01-dokploy/`](./05-referencia/deployment/01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md) — el plan VIGENTE, FASES 0–13** · [`02-correo/`](./05-referencia/deployment/02-correo/) (transporte por Google Workspace, outbox y su cron obligatorio) · [`03-operacion/`](./05-referencia/deployment/03-operacion/) ([**⚙️ configuración de producción**](./05-referencia/deployment/03-operacion/CONFIGURACION_PRODUCCION.md) — qué vale cada variable y qué se rompe si falta; [tests que caducan solos](./05-referencia/deployment/03-operacion/MANUAL_TESTS_QUE_CADUCAN.md); [Docker local](./05-referencia/deployment/03-operacion/MANUAL_DOCKER_LOCAL.md)) · [`99-aws/`](./05-referencia/deployment/99-aws/) ⚠️ histórico, **no vigente**: se conserva porque razona los invariantes. |
| **[solicitudes](./05-referencia/solicitudes/)** | Reglas de negocio de solicitudes, características CT, y **dobladas/** (flujo, integridad, casos). |
| **[turnos](./05-referencia/turnos/)** | Fuente de verdad de turnos, decisiones sobre jornada/pago sábado. |
| **[pruebas](./05-referencia/pruebas/)** | Inventario de tests, matriz de casos, guía de pruebas. |

## READMEs que viven junto al código

Estos no están en `docs/` a propósito: se leen desde la carpeta que documentan.

| README | Qué cubre |
|---|---|
| [`solicitudes/services/README.md`](../solicitudes/services/README.md) | Mapa de la capa de servicios de solicitudes: strategies, validadores, aplicación de turnos, deudas, correo. |
| [`static/js/README.md`](../static/js/README.md) | Módulos de JavaScript, `static_v` y qué se usa de verdad. |
| [`tests_js/README.md`](../tests_js/README.md) | Red de pruebas de JS (`node --test`, sin dependencias). |
| [`scripts/README.md`](../scripts/README.md) | Scripts de un solo uso y por qué casi siempre quieres un comando de gestión. |
| [`static/img/auth/README.md`](../static/img/auth/README.md) | El banner del login. |

---

> **Nota:** las dependencias del proyecto están en `AppTurnosExplora/requirements.txt`
> (producción) y `requirements-dev.txt` (desarrollo/tests). No hay copias en la raíz.
