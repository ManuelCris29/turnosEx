# 99 · AWS — histórico, NO vigente

> ⚠️ **No sigas estos documentos para desplegar.**
> El plan vigente es
> [`01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md`](../01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md).

## Por qué se conservan

Este plan estaba terminado y nunca se ejecutó: en 2026-09 se decidió desplegar en el
servidor de Dokploy de la empresa. Se conserva porque **razona por qué cada invariante
existe**, y esas razones siguen valiendo aunque la plataforma haya cambiado: por qué la
caché tiene que ser compartida, por qué `AXES_IPWARE_PROXY_COUNT` es el ajuste más
peligroso del despliegue, por qué los correos van por una cola, por qué la base necesita
las tablas de zona horaria.

Varias fases se heredaron palabra por palabra en el checklist de Dokploy.

| Documento | Qué contiene |
|---|---|
| [arquitectura-aws-rds-recomendada.md](./arquitectura-aws-rds-recomendada.md) | El documento maestro: dimensionamiento, costos verificados, qué se descartó y por qué |
| [CHECKLIST_DESPLIEGUE_AWS_RDS.md](./CHECKLIST_DESPLIEGUE_AWS_RDS.md) | FASES 0–11 sobre EC2 + RDS + SES |
| [MANUAL_DESPLIEGUE_EC2.md](./MANUAL_DESPLIEGUE_EC2.md) | Manual genérico, ya reemplazado por el anterior. Asume `mysqlclient`, y este proyecto usa PyMySQL |

También sigue en el repositorio
[`infra/cloudformation/swalp-infra.yaml`](../../../../infra/cloudformation/swalp-infra.yaml),
con el mismo criterio.

## Lo que cambió al pasar a Dokploy

| | AWS | Dokploy |
|---|---|---|
| Servidor | EC2 `t4g.micro` + Nginx + systemd | Application con el `Dockerfile` del repo |
| Base | RDS MySQL 8.4 (backups y zonas horarias incluidos) | Servicio MySQL — **ambas cosas pasan a ser nuestras** |
| Caché | `db://cache_appturnos` (ElastiCache costaba ~$12/mes) | Redis, que autohospedado cuesta 0 |
| Correo | Amazon SES: sandbox + 6 CNAME de DKIM | Google Workspace: **cero cambios de DNS** |
| Crons | `crontab` / EventBridge en UTC | Schedules con `timezone` propio |
| Alarmas | CloudWatch con metric filters | Comando propio: Dokploy **no notifica Schedules fallidos** |
