# Despliegue y operación — índice

Todo lo que hace falta para poner SWALP en producción y mantenerlo funcionando.
Las carpetas van numeradas en el orden en que se necesitan.

---

## 🚀 Si vas a desplegar, empieza aquí

**[`01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md`](./01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md)**

Es el plan vigente, de la FASE 0 a la FASE 13, con casillas. Te va mandando a las otras
carpetas cuando toca: al correo en la FASE 8, a la operación cuando necesitas la
referencia de una variable.

---

## Las cuatro carpetas

| | Qué hay | Cuándo se abre |
|---|---|---|
| **[`01-dokploy/`](./01-dokploy/)** | El plan de despliegue vigente | Al montar producción, y en cada cambio de infraestructura |
| **[`02-correo/`](./02-correo/)** | Transporte, cola de salida y recuperación de contraseña | FASE 8, y cada vez que un correo no llega |
| **[`03-operacion/`](./03-operacion/)** | Tareas recurrentes y referencia de configuración | Después del despliegue, en el día a día |
| **[`99-aws/`](./99-aws/)** | ⚠️ El plan de AWS, **no vigente** | Solo para consultar por qué se decidió algo |

---

## Fuera de esta carpeta, pero parte del despliegue

| Dónde | Qué es |
|---|---|
| [`infra/dokploy/`](../../../infra/dokploy/) | Los scripts que se pegan en los Schedules de Dokploy |
| [`.env.dokploy.example`](../../../.env.dokploy.example) | Las variables de entorno, comentadas |
| [`.github/workflows/deploy.yml`](../../../../.github/workflows/deploy.yml) | El despliegue automático cuando el CI pasa |
| [`infra/cloudformation/swalp-infra.yaml`](../../../infra/cloudformation/swalp-infra.yaml) | ⚠️ IaC de AWS, **no vigente**. Se conserva como registro de invariantes |

---

## Las tres cosas que fallan en silencio

Si solo vas a leer tres avisos de todo esto, que sean estos. Son lo que AWS daba hecho y
aquí es responsabilidad nuestra:

1. **Los backups.** Dokploy solo escribe a destinos S3-compatibles, no a disco local. Y un
   backup que nunca se restauró es una hipótesis → [FASE 10](./01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md).
2. **Las tablas de zona horaria de MySQL.** La imagen oficial no las trae; sin ellas el
   admin de Django revienta al filtrar por fecha → [FASE 2](./01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md).
3. **Las alarmas.** Dokploy **no notifica cuando un Schedule falla** → [FASE 11](./01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md).

---

## Y el que bloquea a los 300 empleados

`AXES_IPWARE_PROXY_COUNT`. Si el número de proxies está mal, django-axes ve la IP del
proxy para todo el mundo y **cinco contraseñas falladas de cualquiera dejan fuera a la
plantilla entera**. No se adivina, se mide con `python manage.py verificar_ip_cliente`, y
antes de dar la URL a nadie. Detalle en
[`03-operacion/CONFIGURACION_PRODUCCION.md`](./03-operacion/CONFIGURACION_PRODUCCION.md).
