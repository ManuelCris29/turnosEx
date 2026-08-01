# ✅ Checklist de despliegue — AppTurnos/SWALP en AWS (ECS Fargate)

**Fecha:** 2026-07-25
**Arquitectura:** ver §8 de [arquitectura-aws-rds-recomendada](./arquitectura-aws-rds-recomendada.md)
**Objetivo:** dejar la app **pública en internet, sin gestionar servidores** sobre:
`ALB (HTTPS/ACM) → ECS Fargate (contenedor) → RDS MySQL + Amazon SES`.

> Alternativa al [checklist EC2](./CHECKLIST_DESPLIEGUE_AWS_RDS.md). Elige **uno de los dos** caminos. Aquí AWS gestiona el SO; tú solo publicas imágenes.
> Variables usadas de ejemplo: región `us-east-1`, cuenta `<ACCOUNT_ID>`, dominio `swalp.parqueexplora.org`.

---

## FASE 0 — Código (✅ ya está listo en el repo)

Lo necesario para contenedor **ya se hizo**; solo repásalo:
- [x] **Dockerfile** + **.dockerignore** (`AppTurnosExplora/`). Imagen validada.
- [x] **WhiteNoise** sirve los estáticos dentro del contenedor (no hay Nginx).
- [x] **SECURE_PROXY_SSL_HEADER** + **CSRF_TRUSTED_ORIGINS** (para HTTPS tras el ALB).
- [x] `requirements.txt` completo (incluye `django-environ`, `gunicorn`, `whitenoise`).
- [ ] *(Opcional, recomendado)* endpoint de salud sin login para el health check del ALB (ver Fase 6).

---

## FASE 1 — Base de datos RDS

**Idéntica al camino EC2** → sigue la [Fase 1 del checklist EC2](./CHECKLIST_DESPLIEGUE_AWS_RDS.md#fase-1--base-de-datos-rds):
- [ ] RDS **MySQL 8.0**, `db.t4g.micro`, Single-AZ, 20 GB gp3, **Public access: No**.
- [ ] Anotar el **endpoint** → será `DB_HOST`.
- El Security Group de RDS se ajusta en la Fase 4 (permitir el SG de los tasks).

> ✅ RDS ya trae las tablas de zona horaria pobladas (sin el error del admin visto en local).

---

## FASE 2 — Imagen en ECR (registro de contenedores)

```bash
AWS_REGION=us-east-1
ACCOUNT_ID=<ACCOUNT_ID>
REPO=swalp-app
ECR=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# 2.1 Crear el repositorio
aws ecr create-repository --repository-name $REPO --region $AWS_REGION

# 2.2 Autenticar docker contra ECR
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR

# 2.3 Construir, etiquetar y subir (desde AppTurnosExplora/)
cd AppTurnosExplora
docker build -t $REPO:latest .
docker tag $REPO:latest $ECR/$REPO:latest
docker push $ECR/$REPO:latest
```

- [ ] Repo ECR creado y **primera imagen subida**.

---

## FASE 3 — Secretos y parámetros

Guardar los valores sensibles en **AWS Secrets Manager** (o SSM Parameter Store):
- [ ] `swalp/SECRET_KEY`, `swalp/DB_PASSWORD` (mínimo). Opcional: agrupar todo el `.env` en un secreto JSON.
- Los **no sensibles** (`ENVIRONMENT=production`, `ALLOWED_HOSTS`, `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PORT`, `SITE_URL`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS`) van como **env vars** normales en el task definition.

```bash
aws secretsmanager create-secret --name swalp/SECRET_KEY --secret-string "<clave-larga>"
aws secretsmanager create-secret --name swalp/DB_PASSWORD --secret-string "<password-rds>"
```

---

## FASE 4 — Red y Security Groups

Usando la **VPC por defecto** y **subredes públicas** (evita el NAT gateway ~$32/mes):
- [ ] **SG del ALB** (`swalp-alb-sg`): entrada `80` y `443` desde `0.0.0.0/0`.
- [ ] **SG de los tasks** (`swalp-task-sg`): entrada `8000` **solo desde `swalp-alb-sg`**.
- [ ] **SG de RDS**: entrada `3306` **solo desde `swalp-task-sg`**.

---

## FASE 5 — Roles IAM

- [ ] **Task execution role** (`swalp-exec-role`): permite a ECS **descargar de ECR**, escribir **logs en CloudWatch** y leer los **secretos** (política `AmazonECSTaskExecutionRolePolicy` + acceso a los secretos de la Fase 3).
- [ ] **Task role** (`swalp-task-role`): permisos de la **app en runtime**. Para enviar correo con **SES por API** (recomendado en AWS): `ses:SendEmail` y `ses:SendRawEmail`. Así **no hay credenciales SMTP** que rotar.

---

## FASE 6 — ALB + Target Group + Certificado

- [ ] **ACM:** solicitar/validar certificado para `swalp.parqueexplora.org` (validación DNS; IT agrega el registro).
- [ ] **Target Group** (`swalp-tg`): tipo **IP**, protocolo HTTP, puerto **8000**.
  - **Health check:** path `/` con **códigos de éxito `200-399`** (la app redirige a HTTPS y devuelve 301; el 3xx cuenta como sano). *Mejor aún:* un endpoint `/healthz/` sin login exento de redirección.
- [ ] **ALB** (`swalp-alb`): internet-facing, en las **subredes públicas**, SG `swalp-alb-sg`.
  - Listener **443** (HTTPS, cert ACM) → reenvía a `swalp-tg`.
  - Listener **80** → **redirige a 443**.

---

## FASE 7 — ECS: Cluster, Task Definition y Service

### 7.1 Cluster
```bash
aws ecs create-cluster --cluster-name swalp-cluster
```

### 7.2 Task Definition (Fargate)
Registrar una task definition con:
- **Launch type:** Fargate · **CPU/mem:** `0.5 vCPU` / `1 GB` (`cpu: 512`, `memory: 1024`).
- **Execution role:** `swalp-exec-role` · **Task role:** `swalp-task-role`.
- **Contenedor** `web`: imagen `<ECR>/swalp-app:latest`, puerto **8000**.
  - **environment:** `ENVIRONMENT=production`, `DEBUG=False`, `ALLOWED_HOSTS=swalp.parqueexplora.org`, `CSRF_TRUSTED_ORIGINS=https://swalp.parqueexplora.org`, `CORS_ALLOWED_ORIGINS=https://swalp.parqueexplora.org`, `SITE_URL=https://swalp.parqueexplora.org`, `DB_HOST=<endpoint-rds>`, `DB_NAME=bdturnosex`, `DB_USER=admin`, `DB_PORT=3306`. Para correo por API: `EMAIL_BACKEND=django_ses.SESBackend`, `AWS_SES_REGION_NAME=us-east-1`.
  - **secrets:** `SECRET_KEY` y `DB_PASSWORD` desde Secrets Manager.
  - **logConfiguration:** `awslogs` → grupo `/ecs/swalp` en CloudWatch.

> **Correo:** en Fargate lo natural es **SES por API + IAM task role** (`django-ses`): `pip install django-ses boto3` (agrégalo a `requirements.txt`) y `EMAIL_BACKEND=django_ses.SESBackend`. Sin secretos SMTP. Alternativa: mantener SMTP con credenciales SES en un secreto.

### 7.3 Service
```bash
aws ecs create-service \
  --cluster swalp-cluster --service-name swalp-svc \
  --task-definition swalp-web --desired-count 1 --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-pub-1>,<subnet-pub-2>],securityGroups=[<swalp-task-sg>],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=<arn-swalp-tg>,containerName=web,containerPort=8000"
```
- [ ] Service creado y el task pasa a **RUNNING** y **healthy** en el target group.

---

## FASE 8 — Migraciones

El `CMD` del Dockerfile corre `migrate` al arrancar (bien con **1 task**). Con **≥2 tasks** conviene una migración controlada:
```bash
aws ecs run-task --cluster swalp-cluster --task-definition swalp-web --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[<subnet-pub-1>],securityGroups=[<swalp-task-sg>],assignPublicIp=ENABLED}" \
  --overrides '{"containerOverrides":[{"name":"web","command":["python","manage.py","migrate","--noinput"]}]}'
```
- [ ] Migraciones aplicadas. *(Opcional: quitar `migrate` del CMD y dejarlo solo como task puntual.)*

---

## FASE 9 — DNS + SES

- [ ] **DNS (IT):** `swalp.parqueexplora.org` → **DNS del ALB** (registro **CNAME**, o **Alias** si el dominio está en Route 53).
- [ ] **SES:** verificar dominio `parqueexplora.org` (DKIM/SPF), **salir del sandbox**. Con el **task role** (`ses:SendEmail`) no hacen falta credenciales.

**Outbox de correos — ⚠️ paso obligatorio:**
- [ ] Crear una **EventBridge Scheduled Rule** (`rate(5 minutes)`) que lance una tarea ECS con la misma Task Definition, sobrescribiendo el comando a `["python","manage.py","procesar_email_outbox"]`. En Fargate no hay crontab.
- [ ] **Sin esto, un correo que falle queda guardado pero no se reintenta nunca.** Paso a paso en **[MANUAL_OUTBOX_CORREOS.md](./MANUAL_OUTBOX_CORREOS.md)**.

---

## FASE 10 — Verificación

- [ ] `https://swalp.parqueexplora.org` carga desde **fuera de la red** (celular con datos) con candado.
- [ ] Target group **healthy**; ALB enruta al task.
- [ ] Login (django-axes activo), dashboard, crear solicitud, aceptar pendiente (emisor y receptor) → OK.
- [ ] Llega el correo desde `no-reply@parqueexplora.org` (DKIM=pass, SPF=pass).
- [ ] `/admin/` sin el error de zona horaria (RDS ya trae las tablas TZ).
- [ ] Logs visibles en CloudWatch (`/ecs/swalp`).

---

## FASE 11 — CD (despliegue continuo, opcional)

Reemplaza al CD por SSH: al mergear a `main`, un workflow construye y publica la imagen y fuerza un nuevo despliegue.

```yaml
# .github/workflows/deploy.yml (esbozo)
name: Deploy
on:
  push:
    branches: [ main ]
jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # OIDC hacia AWS (sin llaves estáticas)
      contents: read
    steps:
      - uses: actions/checkout@v5
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<ACCOUNT_ID>:role/<gh-oidc-deploy-role>
          aws-region: us-east-1
      - uses: aws-actions/amazon-ecr-login@v2
        id: ecr
      - name: Build & push
        run: |
          IMG=${{ steps.ecr.outputs.registry }}/swalp-app:${{ github.sha }}
          docker build -t $IMG AppTurnosExplora
          docker push $IMG
      - name: Actualizar servicio ECS
        run: aws ecs update-service --cluster swalp-cluster --service swalp-svc --force-new-deployment
```
- [ ] **Secrets/OIDC:** rol IAM con confianza a GitHub OIDC (evita llaves estáticas en GitHub).

---

## Anexo — Operación

```bash
# Nuevo despliegue manual (build → push → rolling update)
cd AppTurnosExplora
docker build -t $ECR/swalp-app:latest .
docker push $ECR/swalp-app:latest
aws ecs update-service --cluster swalp-cluster --service swalp-svc --force-new-deployment

# Logs
aws logs tail /ecs/swalp --follow

# Escalar (nº de tasks)
aws ecs update-service --cluster swalp-cluster --service swalp-svc --desired-count 2
```

**Backups:** RDS automáticos (sin cambios). **Sin SO que parchear** — AWS gestiona la plataforma del contenedor.
**Escalado:** subir `--desired-count` (horizontal) o la CPU/mem del task definition (vertical).

---

## Diferencias clave vs el checklist EC2

| | EC2 | **Fargate (este)** |
|---|---|---|
| Servir HTTP/HTTPS | Nginx + Certbot (tú) | **ALB + ACM** (gestionado) |
| Estáticos | Nginx | **WhiteNoise** en el contenedor |
| Publicar cambios | `git pull` + restart | **build + push imagen** |
| Gestión de SO | Tú | **AWS (ninguna)** |
| Correo | SES SMTP | **SES API + task role** (sin secretos) |
| Costo aprox. | ~$32/mes | ~$56/mes |
