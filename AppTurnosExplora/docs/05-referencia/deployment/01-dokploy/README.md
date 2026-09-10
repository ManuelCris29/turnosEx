# 01 · Dokploy — el despliegue vigente

## El documento

**[CHECKLIST_DESPLIEGUE_DOKPLOY.md](./CHECKLIST_DESPLIEGUE_DOKPLOY.md)** — FASES 0 a 13,
con casillas. Se sigue de arriba abajo.

| Fases | Qué se hace |
|---|---|
| 0 | Suite en verde, ensayo de estáticos, generar `SECRET_KEY` |
| 1 | Reconocimiento del servidor: **qué se puede reutilizar** de las otras apps |
| 2–3 | MySQL (⚠️ zonas horarias) y Redis |
| 4–6 | La Application, variables y primer arranque (⚠️ `verificar_ip_cliente`) |
| 7 | Dominio, DNS y certificado |
| 8 | Correo → [`02-correo/`](../02-correo/) |
| 9 | Las cinco tareas programadas |
| 10–11 | Backups y alarmas — **lo que AWS daba hecho** |
| 12–13 | GitHub, despliegue automático y verificación final |

## Lo que no está en este documento

| Dónde | Qué |
|---|---|
| [`infra/dokploy/`](../../../../infra/dokploy/) | Los scripts que se pegan en los Schedules de tipo Server |
| [`.env.dokploy.example`](../../../../.env.dokploy.example) | Las variables, con lo que rompe cada una si falta |
| [`.github/workflows/deploy.yml`](../../../../../.github/workflows/deploy.yml) | El despliegue disparado cuando el CI pasa |

## Antes de empezar, dos avisos

- **El contexto de build es `AppTurnosExplora`, no la raíz del repositorio.** Si se deja
  en la raíz, el `.dockerignore` no aplica y los `COPY` del `Dockerfile` no encuentran
  nada.
- **Auto Deploy va apagado.** Dokploy lo trae encendido por defecto y eso se salta el
  `manage.py check --deploy` del CI, que es la barrera contra los dos fallos que dejan la
  aplicación en pie pero rota.
