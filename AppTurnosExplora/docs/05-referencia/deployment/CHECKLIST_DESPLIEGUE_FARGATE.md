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
- [x] `requirements.txt` completo (incluye `django-environ`, `gunicorn`, `whitenoise`, `redis`).
- [x] **Endpoints de salud** `/health/` y `/health/ready/` sin login (`core/health.py`), **exentos de la redirección a HTTPS** — sin esa exención el ALB entra en bucle de arranque. Ver Fase 6.
- [x] **Caché configurable** por `CACHE_URL` y **TLS a RDS** por `DB_SSL_CA` (el certificado de Amazon ya viaja en la imagen).
- [x] **Conexiones persistentes** (`CONN_MAX_AGE=60` + `CONN_HEALTH_CHECKS`) automáticas en producción.

> 📖 **Antes de seguir, lee [CONFIGURACION_PRODUCCION.md](./CONFIGURACION_PRODUCCION.md).**
> Explica qué vale cada variable, **qué se rompe si falta**, y las trampas del ALB.
> Este checklist es el "cómo"; ese documento es el "por qué".

**Comprobación opcional antes de empaquetar (10 min, en local):**
```bash
cd AppTurnosExplora
pytest -n auto                       # la suite normal: debe estar en verde
pytest -n auto --dias-en-el-futuro=45   # ¿algo se pondrá rojo solo dentro de mes y medio?
```
- [ ] La segunda corrida sale en verde. **Si sale algo en rojo, eso es el hallazgo, no un
      error de la corrida:** ese test va a fallar solo dentro de unas semanas, sin que nadie
      toque el código. Se decide si se arregla ahora o se anota, pero no se despliega sin
      saber qué es.
- [ ] Por qué aquí: la suite normal siempre corre con el reloj de hoy, así que de esto solo
      se entera el día que ya es tarde. Pasó el 2026-09-02 con 17 tests en rojo de golpe y
      nada tocado. **Contexto, cómo leerlo y la decisión de si esto debe ir al CI:
      [MANUAL_TESTS_QUE_CADUCAN.md](./MANUAL_TESTS_QUE_CADUCAN.md).**

---

## FASE 1 — Base de datos RDS

**Idéntica al camino EC2** → sigue la [Fase 1 del checklist EC2](./CHECKLIST_DESPLIEGUE_AWS_RDS.md#fase-1--base-de-datos-rds):
- [ ] RDS **MySQL 8.0**, `db.t4g.micro`, Single-AZ, 20 GB gp3, **Public access: No**.
- [ ] Anotar el **endpoint** → será `DB_HOST`.
- El Security Group de RDS se ajusta en la Fase 4 (permitir el SG de los tasks).

> ✅ RDS ya trae las tablas de zona horaria pobladas (sin el error del admin visto en local).

---

## FASE 1.5 — Caché compartida ⚠️ **obligatoria, no la saltes**

La app cachea el estado de **Mis Turnos** una hora y lo invalida cuando cambia.
Gunicorn corre con **3 workers**: con la caché en memoria (la de desarrollo) cada
worker tendría la suya, la invalidación limpiaría solo uno, y **los exploradores
verían turnos desactualizados de forma intermitente**. Detalle completo en
[CONFIGURACION_PRODUCCION.md §3, trampa nº 1](./CONFIGURACION_PRODUCCION.md#-trampa-1--la-caché-en-memoria-sirve-datos-viejos).

Elige **una** de las dos:

**Opción A — ElastiCache Redis** (recomendada, ~$12/mes)
- [ ] Clúster **Redis**, `cache.t4g.micro`, 1 nodo, en las mismas subredes que los tasks.
- [ ] **SG de ElastiCache**: entrada `6379` **solo desde `swalp-task-sg`**.
- [ ] Anotar el endpoint → `CACHE_URL=redis://<endpoint>:6379/1` (usa `rediss://` si activas cifrado en tránsito).

**Opción B — Tabla en la propia RDS** (sin infraestructura nueva, $0)
- [ ] `CACHE_URL=db://cache_appturnos`
- [ ] Crear la tabla **una sola vez** (igual que las migraciones de la Fase 8):
  ```bash
  aws ecs run-task --cluster swalp-cluster --task-definition swalp-web --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[<subnet-pub-1>],securityGroups=[<swalp-task-sg>],assignPublicIp=ENABLED}" \
    --overrides '{"containerOverrides":[{"name":"web","command":["python","manage.py","createcachetable"]}]}'
  ```

> `manage.py check --deploy` **falla** (`core.E001`) si despliegas sin `CACHE_URL`. Es a propósito.

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
  - **Health check:** path **`/health/`**, códigos de éxito **`200`**, intervalo 30 s, umbral sano 2 / insano 3.
  - ⚠️ **No uses `/`**: los health checks del ALB llegan sin `X-Forwarded-Proto`, así que la app les respondería **301** hacia HTTPS. `/health/` está exento de esa redirección precisamente por eso.
  - ⚠️ **No uses `/health/ready/`**: consulta la base. Si RDS tuviera un problema pasajero, el ALB daría por muertas *todas* las tareas a la vez y convertiría un incidente recuperable en una caída total. `/health/ready/` es para verificar a mano.
  - ⚠️ **`ALLOWED_HOSTS`:** el ALB manda sus health checks con la **IP privada de la tarea** como cabecera `Host`, y Django la rechazaría con **400 DisallowedHost**. Decide antes cómo resolverlo → [trampa nº 3](./CONFIGURACION_PRODUCCION.md#-trampa-3--allowed_hosts-rechaza-al-propio-alb-decisión-pendiente).
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
  - **environment:** `ENVIRONMENT=production`, `DEBUG=False`, `ALLOWED_HOSTS=swalp.parqueexplora.org`, `CSRF_TRUSTED_ORIGINS=https://swalp.parqueexplora.org`, `CORS_ALLOWED_ORIGINS=https://swalp.parqueexplora.org`, `SITE_URL=https://swalp.parqueexplora.org`, `DB_HOST=<endpoint-rds>`, `DB_NAME=bdturnosex`, `DB_USER=admin`, `DB_PORT=3306`.
    - ⚠️ **`CACHE_URL=redis://<endpoint>:6379/1`** (o `db://cache_appturnos`) — **sin esto el despliegue falla el check**. Ver Fase 1.5.
    - ⚠️ **`DB_SSL_CA=/app/certs/rds-ca-global.pem`** — cifra y **verifica** la conexión a RDS. La imagen ya trae el certificado de Amazon.
    - Para correo por API: `EMAIL_BACKEND=django_ses.SESBackend`, `AWS_SES_REGION_NAME=us-east-1`.
    - No hace falta tocar `CONN_MAX_AGE`: en producción vale 60 s automáticamente, con comprobación de conexión.

> 📋 Bloque completo de variables listo para copiar: [CONFIGURACION_PRODUCCION.md §6](./CONFIGURACION_PRODUCCION.md#6-resumen-para-el-día-del-despliegue).
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
- [ ] **⚠️ Salir del sandbox es BLOQUEANTE desde que existe "olvidé mi contraseña":** en sandbox, SES solo entrega a direcciones verificadas a mano, así que **nadie** puede recuperar su contraseña — y el fallo es silencioso (la pantalla dice "revisa tu correo" igualmente). **Se pide con 24 h hábiles de antelación**, no el día del despliegue. Paso a paso en **[MANUAL_RECUPERAR_CONTRASENA.md](./MANUAL_RECUPERAR_CONTRASENA.md)**.
- [ ] **Salida al puerto 587** permitida en el grupo de seguridad de las tareas. Sin esto el envío se cuelga hasta agotar `EMAIL_TIMEOUT` y el usuario ve un error sin pista de la causa.

**Outbox de correos — ⚠️ paso obligatorio:**
- [ ] Crear una **EventBridge Scheduled Rule** (`rate(5 minutes)`) que lance una tarea ECS con la misma Task Definition, sobrescribiendo el comando a `["python","manage.py","procesar_email_outbox"]`. En Fargate no hay crontab.
- [ ] **Sin esto, un correo que falle queda guardado pero no se reintenta nunca.** Paso a paso en **[MANUAL_OUTBOX_CORREOS.md](./MANUAL_OUTBOX_CORREOS.md)**.

**Sanciones por deuda de horas — ⚠️ paso obligatorio:**
- [ ] Crear una **EventBridge Scheduled Rule** con schedule `cron(15 10 * * ? *)` (**UTC** → 05:15 en Colombia) que lance una tarea ECS con la misma Task Definition, sobrescribiendo el comando a `["python","manage.py","revisar_sanciones_por_deuda"]`.
- [ ] Retry attempts: **2**. Un fallo transitorio (RDS que aún no acepta conexiones, una tarea que no arranca) se arregla reintentando; sin reintentos ese día se pierde entero. La ejecución es idempotente —el candado de `RevisionSancionesDeuda` garantiza que solo una haga el trabajo—, así que reintentar es seguro.
- [ ] **Sin esto, la sanción de un moroso solo nace cuando esa misma persona abre la aplicación**, así que quien no entra no aparece bloqueado en ningún informe del supervisor.
- [ ] **Alarma de que la tarea dejó de correr.** Crear un *metric filter* sobre el log group del contenedor con el patrón **`REVISION_SANCIONES_NO_EJECUTADA`** y una alarma que notifique a un SNS. El comando emite esa cadena en nivel `CRITICAL` cuando detecta que lleva días sin ejecutarse. **Es la única forma de enterarse sin mirar:** una tarea programada que deja de dispararse no da ningún error, simplemente deja de ocurrir.
- [ ] Probada la alarma: lanzar la tarea a mano con la base sin ninguna fila en `RevisionSancionesDeuda` (o esperar 3 días) y comprobar que **llega la notificación**. Un aviso sin probar no es un aviso.
- [ ] Paso a paso en **[MANUAL_SANCIONES_DEUDA.md](./MANUAL_SANCIONES_DEUDA.md)**.

**Comprobar que las dos tareas de arriba existen de verdad — ⚠️ paso obligatorio:**
```bash
# Dentro de la tarea, con ECS Exec. Termina con codigo 1 si algo va mal.
aws ecs execute-command --cluster swalp-cluster --task <task-id>   --container web --interactive --command "python manage.py verificar_crons"
```
- [ ] Sale **`[ok]`** en las dos líneas.
- [ ] **Por qué hace falta si ya está la alarma de arriba:** esa alarma la emite el propio
      comando de sanciones, así que solo puede sonar **cuando alguien lo ejecuta**. Contra el
      fallo que de verdad ocurre —que la Scheduled Rule nunca se llegó a crear— un proceso no
      puede avisar de su propia ausencia. `verificar_crons` mira desde fuera lo que las dos
      tareas dejan en la base: la espera del correo pendiente más antiguo y el día de la
      última revisión. Antes, la única defensa contra "nadie programó el cron" era que una
      persona leyera esta lista.
- [ ] **Vuelve a lanzarlo 24 h después del despliegue.** El día 1 la revisión de sanciones
      puede no haber corrido todavía y el aviso de "NUNCA se ha ejecutado" es esperable; lo que
      no es normal es que siga saliendo al día siguiente.
- [ ] Recomendado: la **misma** Scheduled Rule diaria puede lanzar `verificar_crons` con
      `--json`; su código de salida 1 marca la ejecución como fallida y eso ya es visible en
      EventBridge sin montar nada más. El marcador para un *metric filter* propio es
      **`CRON_NO_EJECUTADO`**.

---

## FASE 10 — Verificación

**Antes de dar por buena la salida (comprobación automática):**
```bash
# Dentro de la tarea, con ECS Exec. Debe decir "no issues".
aws ecs execute-command --cluster swalp-cluster --task <task-id> \
  --container web --interactive --command "python manage.py check --deploy"
```
- [ ] Sale **`System check identified no issues`**.
  - Si sale **`core.E001`** → falta `CACHE_URL` (Fase 1.5). **No lo ignores:** significa que los usuarios verán turnos desactualizados.
  - Si sale **`core.W002`** → falta `DB_SSL_CA`: el tráfico a RDS va sin cifrar.
- [ ] `curl https://swalp.parqueexplora.org/health/` → `{"status": "ok"}`.
- [ ] `curl https://swalp.parqueexplora.org/health/ready/` → `{"status": "ok", "database": "ok"}`.

**Funcional:**
- [ ] `https://swalp.parqueexplora.org` carga desde **fuera de la red** (celular con datos) con candado.
- [ ] Target group **healthy**; ALB enruta al task.
- [ ] **Prueba de la caché compartida** (la que valida la trampa nº 1): con **≥2 tasks**, aprobar una solicitud y refrescar Mis Turnos varias veces. El resultado debe ser **siempre el mismo**; si alterna entre el dato viejo y el nuevo, la caché no es compartida.
- [ ] Login (django-axes activo), dashboard, crear solicitud, aceptar pendiente (emisor y receptor) → OK.
- [ ] Llega el correo desde `no-reply@parqueexplora.org` (DKIM=pass, SPF=pass).
- [ ] **Recuperar contraseña de extremo a extremo:** pedir el enlace desde el login, comprobar que llega, que apunta a `https://swalp.parqueexplora.org/...` (no a `http://` ni al DNS interno del ALB), fijar la contraseña, entrar con ella, y verificar que **el mismo enlace ya no vale una segunda vez**. Casillas completas en **[MANUAL_RECUPERAR_CONTRASENA.md](./MANUAL_RECUPERAR_CONTRASENA.md)** §6. **Sin esta prueba no se sabe si funciona:** la pantalla responde lo mismo aunque no salga ningún correo.
- [ ] Con sesión iniciada, el menú de usuario ofrece **Cambiar mi contraseña** y el flujo termina bien.
- [ ] **Ninguna cuenta sin ficha de empleado.** Son cuentas fantasma: pueden entrar y recibir enlaces de recuperación, pero no aparecen en la pantalla de empleados, así que nadie las ve. Las generaba la versión antigua de "eliminar empleado" (hoy se da de baja, que no las crea) y también crearlas a mano desde `/admin/`.
  ```bash
  aws ecs execute-command --cluster swalp-cluster --task <task-id> \
    --container web --interactive --command \
    "python manage.py shell -c \"from django.contrib.auth.models import User; print(list(User.objects.filter(empleado__isnull=True).values_list('username', flat=True)))\""
  ```
  Debe salir `[]` (salvo cuentas de administración creadas a propósito con `createsuperuser`).
- [ ] `/admin/` sin el error de zona horaria (RDS ya trae las tablas TZ).
- [ ] Logs visibles en CloudWatch (`/ecs/swalp`).

**Alertas (no dejar para después):**
- [ ] **Alarma del cierre semanal.** La comprobación del cierre falla **ABIERTA** a propósito: si se
      rompe, la solicitud se acepta sin validar y lo único que queda es un `CRITICAL` en el log
      (`solicitudes/services/solicitud_orchestrator.py:154-162`). Sin alarma, el cierre queda
      desactivado de hecho y **nadie se entera** — no hay error visible, solo empiezan a colarse
      solicitudes fuera de plazo.
      ```bash
      aws sns create-topic --name swalp-alertas
      aws sns subscribe --topic-arn <arn> --protocol email --notification-endpoint <correo>

      aws logs put-metric-filter --log-group-name /ecs/swalp \
        --filter-name swalp-cierre-inoperativo \
        --filter-pattern '"CIERRE SEMANAL INOPERATIVO"' \
        --metric-transformations metricName=CierreSemanalInoperativo,metricNamespace=SWALP,metricValue=1,defaultValue=0

      aws cloudwatch put-metric-alarm --alarm-name swalp-cierre-semanal-inoperativo \
        --namespace SWALP --metric-name CierreSemanalInoperativo \
        --statistic Sum --period 300 --evaluation-periods 1 --threshold 1 \
        --comparison-operator GreaterThanOrEqualToThreshold \
        --treat-missing-data notBreaching --alarm-actions <arn>
      ```
      Umbral **1**: una sola aparición ya significa que el cierre no protege nada.
      Detalle y la variante para EC2: [manual técnico § 13.6](../../manual_tecnico.md).
- [ ] **Alarma genérica** con el patrón `?ERROR ?CRITICAL` sobre el mismo grupo de logs, para no
      depender de haber previsto cada texto concreto.
- [ ] Prueba de que la alarma funciona: publica una línea de prueba en el grupo de logs
      (`aws logs put-log-events` con el texto `CIERRE SEMANAL INOPERATIVO`) y comprueba que
      llega el correo. **Una alarma sin probar no es una alarma.**

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
