# 🏗️ Arquitectura AWS recomendada (con RDS) — AppTurnos / SWALP

**Fecha:** 2026-07-24
**Decisión del cliente:** usar **RDS** para **quitarse la carga de seguridad/administración/backups** (no por precio).
**Escala objetivo:** ~**1.000 usuarios** registrados · ~**100 solicitudes/día** (permisos + cambios de turno) · patrón **lectura intensiva** (dashboard, aceptar pendientes) por emisor y receptor · BD de **7,4 MB** · **sin uploads de usuario**.
**Estado actual:** en pruebas (pocos usuarios reales todavía).

> Sustituye a [ANALISIS_MIGRACION_AWS.md](../../01-analisis/ANALISIS_MIGRACION_AWS.md) (que evitaba RDS). Integra el [PLAN_CORREO_TRANSACCIONAL_Y_LATENCIA](./PLAN_CORREO_TRANSACCIONAL_Y_LATENCIA.docx).

---

## 1. Hallazgos del análisis del proyecto (medidos)

| Aspecto | Valor real | Consecuencia |
|---|---|---|
| Tamaño de la BD | **7,4 MB** | El dataset **entero cabe en RAM** incluso en la RDS más chica → los datos no son el cuello de botella |
| Patrón de uso | **Lectura intensiva** (dashboard, pendientes) + escritura ligera (~100 solicitudes/día) | El cuello de botella es **CPU/workers de la app**, no la BD → se escala el **compute (EC2)** |
| Aprobación 2 partes | Emisor **y** receptor entran a aceptar → más sesiones + más correo | Sube concurrencia y volumen de emails |
| Uploads de usuario | **0** (no hay `FileField`/`ImageField`) | **No se necesita bucket S3 de media** |
| Archivos estáticos | 143 MB | Los sirve Nginx/WhiteNoise **gratis**; S3+CloudFront opcional |
| Caché | `LocMemCache` (no hay `django-redis`) | En 1 instancia funciona; **Redis/ElastiCache NO necesario aún** |
| Driver MySQL | `PyMySQL` puro | Conecta a RDS sin compilar |
| Correo | 3 `send_mail` SMTP síncronos por solicitud | Causa los **~20 s**; SES + async lo resuelve |
| Zona horaria | `USE_TZ`, `America/Bogota` | RDS ya trae tablas TZ pobladas (ver [[mysql-tz-tables-local-vs-rds]]) |

**Conclusión:** app interna, monolítica, **read-heavy** y de escritura ligera. Arquitectura de **una instancia con escalado vertical** + RDS gestionado + SES. Simple, barata y suficiente para 1.000 usuarios; con camino claro a crecer si hiciera falta.

---

## 2. Arquitectura recomendada

```
                 ~1.000 empleados Parque Explora (lectura intensiva)
                               │
                    swalp.parqueexplora.org  (DNS que agrega IT)
                               │
                     ┌─────────▼──────────┐
                     │  EC2  t4g.small     │  ← 1 instancia (2 vCPU / 2 GB)
                     │  (público, EIP)     │     escala vertical a medium si crece
                     │  ┌───────────────┐  │
                     │  │ Nginx (HTTPS) │  │ ← TLS Let's Encrypt (gratis)
                     │  │  + estáticos  │  │ ← sirve 143 MB directo
                     │  └──────┬────────┘  │
                     │  ┌──────▼────────┐  │
                     │  │ Gunicorn ×4   │  │ ← workers para lectura concurrente
                     │  │ Django (SWALP)│  │
                     │  └──┬────────┬───┘  │
                     └─────│────────│──────┘
                           │        │  IAM role (sin secreto)
                  ┌────────▼───┐  ┌─▼──────────────┐
                  │ RDS MySQL   │  │  Amazon SES     │ → correo transaccional
                  │ db.t4g.micro│  │ (dominio DKIM)  │
                  │ Single-AZ   │  └─────────────────┘
                  │ 20 GB gp3   │
                  └─────────────┘
```

**Filosofía:** una EC2 pública (web) + RDS gestionado + SES. Sin NAT gateway, sin balanceador, sin Redis, sin bucket de media. Cada pieza eliminada es costo que a esta escala no aporta valor.

---

## 3. Dimensionamiento: prueba (ahora) vs producción (1.000 usuarios)

| Pieza | En pruebas (ahora) | Producción (~1.000 usuarios) | Por qué |
|---|---|---|---|
| **EC2 (web)** | `t4g.micro` (1 GB) | **`t4g.small` (2 GB)** | La lectura concurrente del dashboard consume CPU/RAM de los workers de Gunicorn. `small` corre ~4 workers cómodos. Cambiar micro→small es **1 clic** |
| **RDS (BD)** | `db.t4g.micro` | **`db.t4g.micro`** (se mantiene) | La BD son 7,4 MB: cabe entera en el buffer pool → micro sirve incluso read-heavy. Se sube a `small` **solo si** los créditos de CPU se agotan sostenidamente |
| **Alta disponibilidad** | Single-AZ | Single-AZ (Multi-AZ opcional) | Multi-AZ da failover automático (+~$12/mes). Opcional; ver §4 |

> **Regla de escalado (gatillos claros):**
> - CPU de EC2 sostenida >70 % o respuestas lentas → EC2 a `t4g.medium`.
> - `CPUCreditBalance` de RDS cayendo a 0 sostenido → RDS a `db.t4g.small`.
> - Necesitas ≥2 instancias web (mucha más carga) → recién ahí entran **ALB + ElastiCache** (caché compartida). No antes.

---

## 4. Servicio por servicio: qué, por qué y cuánto (us-east-1, on-demand)

### 4.1 EC2 `t4g.small` — servidor web · **~$12,3/mes**
- **Qué:** 2 vCPU (burst) ARM Graviton, 2 GB RAM. Nginx + Gunicorn (~4 workers) + Django.
- **Por qué small y no micro:** el uso real es **lectura concurrente** (todos entran al dashboard y a aceptar pendientes). 2 GB permiten varios workers sin quedarse sin RAM. En pruebas puedes arrancar en `micro` y subir sin reinstalar nada.
- **Por qué ARM (t4g):** ~20 % más barato que x86 con igual rendimiento; Python corre nativo.

### 4.2 RDS MySQL `db.t4g.micro` Single-AZ, 20 GB gp3 · **~$11,7 + ~$2,3/mes**
- **Qué:** MySQL gestionado, 1 GB RAM, 20 GB (mínimo; la BD usa 7,4 MB).
- **Por qué RDS (tu razón, confirmada):** te **quita la carga de seguridad y administración**: parches automáticos, backups y snapshots, cifrado en reposo, hardening, y **tablas de zona horaria ya pobladas** (evita el error del admin que vimos en local). Ese es justo su valor.
- **Por qué micro alcanza para 1.000 usuarios:** con 7,4 MB, **toda la base vive en memoria**; las lecturas del dashboard no tocan disco. El límite sería CPU en burst, cubierto por los créditos de la clase `t4g`. Subir a `small` es un clic si hiciera falta.
- **Por qué RDS estándar y no Aurora:** Aurora arranca en ~$43/mes (Serverless v2 mín. 0,5 ACU). A esta escala es carísimo de más → **RDS estándar es lo económico**, como intuías.

### 4.3 Amazon SES — correo transaccional · **~$2/mes**
- **Qué:** con aprobación de 2 partes + notificaciones, ~100 solicitudes/día generan del orden de **~15–20 mil emails/mes** × $0,10/1.000 ≈ **$1,5–2**.
- **Por qué SES (opción B del plan de correo):**
  - **Sin secreto que rotar:** la EC2 usa **IAM role**; adiós al App Password de Gmail que caduca.
  - **Arregla los 20 s:** 1 llamada HTTPS (~0,3 s) vs handshake SMTP (~5 s); con envío **asíncrono** la respuesta baja a **<1 s percibido**.
  - **Entregabilidad:** DKIM/SPF/DMARC sobre `parqueexplora.org` → no cae en spam.
- **Dependencia:** IT verifica el dominio en SES y hay que **salir del sandbox** (§6).

### 4.4 IPv4 pública (Elastic IP) · **~$3,65/mes**
- Desde 2024 AWS cobra toda IPv4 pública (~$0,005/h). Inevitable con una instancia pública. Al mantener la EC2 en subred pública **evitamos el NAT gateway (~$32/mes)**.

### 4.5 SSL · **$0** — Let's Encrypt en Nginx
- ACM solo sirve con balanceador/CloudFront (~$16/mes). Con una EC2, **Certbot** da HTTPS gratis y auto-renovado.

### 4.6 DNS · **$0** — lo gestiona IT
- `parqueexplora.org` lo administra IT. Basta un registro `A` (`swalp.parqueexplora.org` → Elastic IP). Route 53 solo si quisieras DNS en AWS ($0,50/mes/zona).

### 4.7 Estáticos · **$0** — Nginx/WhiteNoise
- 1.000 usuarios internos no necesitan CDN. S3 (~$0,10) + CloudFront quedan como opción futura.

### 4.8 Monitoreo y backups · **$0** — incluidos
- CloudWatch básico (free tier). Backups de RDS incluidos (gratis hasta el tamaño de la BD). Código en Git → la EC2 es reemplazable.

---

## 5. Costo total mensual

### Opción recomendada — Producción 1.000 usuarios (Single-AZ)

| Servicio | Config | On-demand | Con compromiso 1 año* |
|---|---|---:|---:|
| EC2 web | `t4g.small` | $12,30 | ~$7,40 |
| RDS instancia | `db.t4g.micro` Single-AZ | $11,70 | ~$7,00 |
| RDS almacenamiento | 20 GB gp3 | $2,30 | $2,30 |
| IPv4 pública | 1 Elastic IP | $3,65 | $3,65 |
| Amazon SES | ~15–20k emails/mes | $2,00 | $2,00 |
| SSL / DNS / CloudWatch / estáticos | Let's Encrypt + IT + free tier + Nginx | $0 | $0 |
| **TOTAL** | | **≈ $32 / mes** | **≈ $22 / mes** |

\* *Savings Plan (EC2) + Reserved Instance (RDS), 1 año sin pago inicial, ~40 % de ahorro.*

### Fase de pruebas (ahora, pocos usuarios)

| Cambio | Efecto |
|---|---|
| EC2 a `t4g.micro` | −$6,2/mes → **≈ $25/mes** on-demand |
| **Si la cuenta AWS tiene <12 meses (Free Tier)** | EC2 + RDS micro + 20 GB + 5 GB S3 gratis el 1.er año → pagas **solo IPv4 + SES ≈ $5/mes** |

### Opción con alta disponibilidad (si más adelante quieres failover automático)

| Cambio | Efecto |
|---|---|
| RDS a **Multi-AZ** (`db.t4g.micro`) | +~$12/mes → **≈ $44/mes** on-demand. Da conmutación automática ante caída de la BD. **Opcional**; Single-AZ ya cubre tu objetivo de quitarte la administración |

---

## 6. Dependencias y pendientes antes de desplegar

1. **IT de Parque Explora** (controlan DNS y Workspace):
   - Crear `no-reply@parqueexplora.org`.
   - Agregar registros **DKIM/SPF** de SES (ajustando SPF para no romper Workspace).
   - Crear `swalp.parqueexplora.org` → Elastic IP.
2. **SES:** verificar dominio y **solicitar salida del sandbox**.
3. **Código:**
   - ✅ **Hecho** — Refactor **From/Reply-To** (envío desde `DEFAULT_FROM_EMAIL`, persona en `Reply-To`).
   - ✅ **Hecho** — **Async** de correo (`transaction.on_commit` + hilo, `EMAIL_TIMEOUT`) → arregla los 20 s; controlado por `EMAIL_SEND_ASYNC`.
   - ⏳ Al montar AWS: `EMAIL_BACKEND=django_ses.SESBackend` + IAM role.
   - ⏳ **Cachear consultas del dashboard** (read-heavy) con `LocMemCache` → menos carga a RDS.
4. **Django prod:** `.env` con `ENVIRONMENT=production`, `DEBUG=False`, `ALLOWED_HOSTS`, `SECRET_KEY`, `CSRF_TRUSTED_ORIGINS`, conexión a RDS.

---

## 7. CI/CD — integración y despliegue continuos

**CI (integración continua) — ✅ implementado.** Workflow `.github/workflows/ci.yml`: en cada push/PR a `main` levanta MySQL, carga las tablas de zona horaria, corre `manage.py check` y la suite `pytest`. Evita subir código roto a `main`.

**CD (despliegue continuo) — ⏳ pendiente, se hace al montar AWS.** Un segundo workflow `deploy.yml` que, al mergear a `main`, entre por SSH al EC2 y ejecute la actualización:
`git pull → pip install -r requirements.txt → migrate → collectstatic → systemctl restart appturnosex`.

- **Bloqueado por infraestructura:** necesita que la EC2 exista (host, usuario, clave SSH). Por eso **no se crea todavía** — un workflow apuntando a un servidor inexistente sería código muerto.
- **Al montar AWS, requiere estos GitHub Secrets:** `SSH_HOST` (Elastic IP), `SSH_USER` (ej. `appuser`), `SSH_KEY` (clave privada de despliegue). Se usaría una action tipo `appleboy/ssh-action`.
- **Interino (sin CD):** la actualización manual del Anexo del [checklist](./CHECKLIST_DESPLIEGUE_AWS_RDS.md) (`git pull` + `systemctl restart`) es suficiente para una sola instancia.
- **Docker:** no se contempla para una sola EC2; solo tendría sentido al migrar a ECS/Fargate o multi-instancia.

---

## 8. Variante sin gestión de servidores: ECS Fargate

Si el objetivo es **no gestionar el SO** (parches, actualizaciones, Nginx/systemd) y concentrarse solo en la app, se sustituye la EC2 por **ECS Fargate**: AWS corre el contenedor y **no hay servidor que mantener**. Requiere **dockerizar** (ya incluido: `AppTurnosExplora/Dockerfile` + `.dockerignore`, imagen validada).

### Qué cambia respecto al plan EC2
- **EC2 + Nginx + Certbot** → **Fargate (contenedor) + ALB + ACM**. Los estáticos los sirve **WhiteNoise** dentro del contenedor (no hay Nginx). Ya está configurado (`whitenoise` en requirements + middleware).
- **RDS y SES NO cambian.**
- Sin NAT gateway: los tasks corren en **subred pública con IP pública** (alcanzan ECR/SES/RDS) → se evita el NAT de ~$32/mes.

### Diagrama
```
  Internet
     │
   ALB (HTTPS con ACM, gratis)
     │
  ECS Fargate task(s)   [Gunicorn + Django + WhiteNoise]
     ├── RDS MySQL db.t4g.micro   (sin cambios)
     └── Amazon SES (IAM task role, sin cambios)

  Imagen:  docker build → ECR → ECS despliega (rolling)
```

### Costo (us-east-1, on-demand)
| Concepto | $/mes |
|---|---:|
| Fargate 0.5 vCPU / 1 GB (1 task) | ~18,00 |
| Application Load Balancer (obligatorio) | ~16–18 |
| RDS db.t4g.micro + 20 GB | 14,00 |
| Amazon SES | 2,00 |
| ECR + CloudWatch | ~1,00 |
| ACM (SSL) | 0 |
| **TOTAL (1 task)** | **≈ $56/mes** |
| Alta disponibilidad (2 tasks) | **≈ $74/mes** |

Con **Compute Savings Plan** (Fargate, 1 año) baja a **≈ $40/mes**. El ALB no tiene descuento por compromiso.

### Trade-off vs plan EC2 (~$32/mes)
- **+~$24/mes** (~70%). El grueso: el premium de cómputo de Fargate y el **ALB obligatorio (~$18)**.
- A cambio: **cero gestión de SO/servidor**, deploy = build+push de imagen (**CD sin SSH**), escalado por número de tasks.
- **Migraciones:** con 1 task se ejecutan en el arranque (CMD del Dockerfile); con ≥2 tasks conviene moverlas a un **task ECS aparte** para evitar carreras.

### CD con Fargate (reemplaza al CD por SSH de §7)
`docker build → push a ECR → aws ecs update-service --force-new-deployment` (rolling). Más robusto y sin servidor que tocar. Secrets en GitHub: credenciales AWS (o rol OIDC) en vez de SSH.

### Alternativa aún más simple: AWS App Runner
Le das la imagen y gestiona balanceo + HTTPS + autoscaling **sin ALB ni ECS**. Precio similar o algo mayor; para llegar a RDS necesita un *VPC connector* (algo más de setup). Opción válida si se quiere el mínimo de configuración.

---

## 9. Alternativa de correo: Google Workspace SMTP relay (opción C)

Interino si IT no monta SES a tiempo: `smtp-relay.gmail.com`.
- **Ventaja:** incluido en Workspace ($0), solo variables de entorno, autentica por IP/dominio (no por contraseña humana).
- **Desventaja:** sigue siendo SMTP → **no baja tanto la latencia** (depende del async), y exige IP de salida fija (la Elastic IP la provee).
- **Recomendación:** ir directo a **SES**; dejar el relay como plan B temporal.

---

## 10. Resumen ejecutivo

> **Dos caminos según cuánta infraestructura quieras gestionar:**
>
> **A) EC2 (más barato) — ≈ $32/mes** on-demand (≈ $22 con compromiso; ≈ $5 el 1.er año con Free Tier). 1× EC2 `t4g.small` (Nginx+Gunicorn+Django, HTTPS Let's Encrypt) + RDS + SES. Tú mantienes el SO (parches, Nginx). Multi-AZ opcional: ≈ $44/mes.
>
> **B) ECS Fargate (cero gestión de SO) — ≈ $56/mes** on-demand (≈ $40 con compromiso; ≈ $74 con 2 tasks HA). Contenedor + ALB + ACM + RDS + SES. AWS gestiona todo bajo la app; deploy = push de imagen. **+~$24/mes** por no tocar servidores.
>
> **Común a ambos:** **RDS `db.t4g.micro`** te quita la administración de la BD, y **SES** (con el refactor From/Reply-To + async ya hecho) arregla los 20 s del correo. Sin Redis ni bucket de media.
>
> **Recomendación:** si el presupuesto es lo primero → **A**. Si "solo concentrarme en la app / no gestionar servidores" es lo primero → **B**.
