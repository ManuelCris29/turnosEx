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

## 8. Alternativa de correo: Google Workspace SMTP relay (opción C)

Interino si IT no monta SES a tiempo: `smtp-relay.gmail.com`.
- **Ventaja:** incluido en Workspace ($0), solo variables de entorno, autentica por IP/dominio (no por contraseña humana).
- **Desventaja:** sigue siendo SMTP → **no baja tanto la latencia** (depende del async), y exige IP de salida fija (la Elastic IP la provee).
- **Recomendación:** ir directo a **SES**; dejar el relay como plan B temporal.

---

## 9. Resumen ejecutivo

> **Arquitectura:** 1× EC2 `t4g.small` (Nginx+Gunicorn+Django, HTTPS Let's Encrypt) + **RDS MySQL `db.t4g.micro` Single-AZ** + **Amazon SES** con IAM role. Sin Redis, sin NAT, sin balanceador, sin bucket de media. Escala vertical (micro→small→medium) según gatillos claros.
>
> **Costo:** **≈ $32/mes** on-demand · **≈ $22/mes** con compromiso a 1 año · **≈ $25/mes** en fase de pruebas (**≈ $5/mes** el 1.er año si aplica Free Tier). Multi-AZ opcional: **≈ $44/mes**.
>
> **RDS te quita la carga de seguridad/administración** (tu objetivo) ya en Single-AZ. **SES** arregla de paso los 20 s del correo.
