# 🏗️ Arquitectura AWS recomendada (con RDS) — AppTurnos / SWALP

**Fecha:** 2026-07-24 · **Precios revalidados:** 2026-09-04
**Decisión del cliente:** usar **RDS** para **quitarse la carga de seguridad/administración/backups** (no por precio).
**Escala objetivo (revisada 2026-09-04):** ~**300 usuarios** registrados · ~**30 solicitudes/día** (permisos + cambios de turno) · patrón **lectura intensiva** (dashboard, aceptar pendientes) por emisor y receptor · BD de **7,4 MB** · **sin uploads de usuario**.
**Estado actual:** en pruebas (pocos usuarios reales todavía).
**Presupuesto:** ≤ **150.000 COP/mes** (≈ $37 USD a 4.050 COP/USD). Es un techo duro y condiciona el dimensionamiento de §3.

> La versión original dimensionaba para 1.000 usuarios / 100 solicitudes-día. El alcance real de
> la primera producción es **300 usuarios / 30 solicitudes-día**, una tercera parte. Las cifras de
> §3, §4 y §5 están recalculadas para esa escala; los objetivos de 1.000 usuarios se conservan
> como camino de crecimiento.

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
| Caché | `LocMemCache` en desarrollo; en producción **`CACHE_URL=db://cache_appturnos`** (tabla en la propia RDS) | Con varios workers de Gunicorn la caché DEBE ser compartida. La tabla cuesta **$0**; **ElastiCache (~$12/mes) queda descartado por presupuesto**. Exige `createcachetable` una vez |
| Driver MySQL | `PyMySQL` puro | Conecta a RDS sin compilar |
| Correo | 3 `send_mail` SMTP síncronos por solicitud | Causa los **~20 s**; SES + async lo resuelve |
| Zona horaria | `USE_TZ`, `America/Bogota` | RDS ya trae tablas TZ pobladas (ver [[mysql-tz-tables-local-vs-rds]]) |

**Conclusión:** app interna, monolítica, **read-heavy** y de escritura ligera. Arquitectura de **una instancia con escalado vertical** + RDS gestionado + SES. Simple, barata y suficiente para 1.000 usuarios; con camino claro a crecer si hiciera falta.

---

## 2. Arquitectura recomendada

```
                 ~300 empleados Parque Explora (lectura intensiva)
                        (crece a ~1.000; ver §3)
                               │
                    swalp.parqueexplora.org  (DNS que agrega IT)
                               │
                     ┌─────────▼──────────┐
                     │  EC2  t4g.micro     │  ← 1 instancia (2 vCPU / 1 GB)
                     │  (público, EIP)     │     sube a small/medium si crece
                     │  ┌───────────────┐  │
                     │  │ Nginx (HTTPS) │  │ ← TLS Let's Encrypt (gratis)
                     │  │  + estáticos  │  │ ← sirve 143 MB directo
                     │  └──────┬────────┘  │
                     │  ┌──────▼────────┐  │
                     │  │ Gunicorn ×2-3 │  │ ← workers para lectura concurrente
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

## 3. Dimensionamiento: prueba (ahora) vs producción (300 → 1.000 usuarios)

| Pieza | En pruebas (ahora) | Producción (300 usuarios, decidido 2026-09-04) | Por qué |
|---|---|---|---|
| **EC2 (web)** | `t4g.micro` (1 GB) | **`t4g.micro` (1 GB)** para los 300 iniciales; `t4g.small` al crecer | Con 300 usuarios y 30 solicitudes/día, `micro` sostiene 2-3 workers de Gunicorn. Se decidió arrancar en `micro` **para medir antes de comprometerse**: hacia los 1.000 usuarios sí hará falta `small` (~4 workers). Cambiar micro→small es **1 clic**. Añadir **1-2 GB de swap**: con 1 GB de RAM, el swap evita que el OOM killer tumbe la app en un pico |
| **RDS (BD)** | `db.t4g.micro` | **`db.t4g.micro`** (se mantiene) | La BD son 7,4 MB: cabe entera en el buffer pool → micro sirve incluso read-heavy. Se sube a `small` **solo si** los créditos de CPU se agotan sostenidamente |
| **Alta disponibilidad** | Single-AZ | Single-AZ (Multi-AZ opcional) | Multi-AZ da failover automático (+~$12/mes). Opcional; ver §4 |

> **Regla de escalado (gatillos claros):**
> - CPU de EC2 sostenida >70 % o respuestas lentas → EC2 a `t4g.medium`.
> - `CPUCreditBalance` de RDS cayendo a 0 sostenido → RDS a `db.t4g.small`.
> - Necesitas ≥2 instancias web (mucha más carga) → recién ahí entran **ALB + ElastiCache** (caché compartida). No antes.

---

## 4. Servicio por servicio: qué, por qué y cuánto (us-east-1, on-demand)

### 4.1 EC2 `t4g.micro` — servidor web · **~$6,13/mes** ($0,008/h)
- **Qué:** 2 vCPU (burst) ARM Graviton, 1 GB RAM. Nginx + Gunicorn (2-3 workers) + Django.
- **Por qué micro para 300 usuarios:** el uso es **lectura concurrente** (dashboard y pendientes), pero con 300 usuarios y 30 solicitudes/día la concurrencia de pico ronda las decenas de peticiones, no los cientos. `small` (2 GB, ~$12,26/mes) es el escalón siguiente y hace falta hacia los 1.000 usuarios; subir es 1 clic y no exige reinstalar nada.
- **Por qué ARM (t4g):** ~20 % más barato que x86 con igual rendimiento; Python corre nativo.
- **⚠️ Poner la instancia en modo `standard`, no `unlimited`.** Las clases T arrancan por defecto en **Unlimited**, que **no frena la instancia al agotar los créditos de CPU: factura el excedente** por vCPU-hora ([docs EC2, *unlimited mode*](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-performance-instances-unlimited-mode.html)). Con un presupuesto tope eso es un costo sin techo. En EC2 **sí se puede** desactivar:

  ```bash
  aws ec2 modify-instance-credit-specification \
      --instance-credit-specification "InstanceId=i-XXXX,CpuCredits=standard"
  ```

  En modo `standard` la instancia se limita en vez de cobrar. Si notas lentitud sostenida, subir a `small` es una decisión tuya, no una sorpresa en la factura.

### 4.2 RDS MySQL `db.t4g.micro` Single-AZ, 20 GB gp3 · **~$11,7 + ~$2,3/mes**
- **Qué:** MySQL gestionado, 1 GB RAM, 20 GB (mínimo; la BD usa 7,4 MB).
- **Por qué RDS (tu razón, confirmada):** te **quita la carga de seguridad y administración**: parches automáticos, backups y snapshots, cifrado en reposo, hardening, y **tablas de zona horaria ya pobladas** (evita el error del admin que vimos en local). Ese es justo su valor.
- **Por qué micro alcanza:** con 7,4 MB, **toda la base vive en memoria**; las lecturas del dashboard no tocan disco. Subir a `small` es un clic si hiciera falta.
- **⚠️ En RDS el modo Unlimited NO se puede desactivar.** La documentación es explícita: *"All burstable instances are configured for Unlimited mode, allowing them to exceed their baseline performance for an additional charge"* ([Concepts.DBInstanceClass.Types](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Concepts.DBInstanceClass.Types.html)). A diferencia de EC2, aquí **no hay modo `standard`**: si se agotan los créditos, AWS cobra el excedente y la factura de RDS queda con techo abierto.

  Una versión anterior de este documento afirmaba que el burst estaba *"cubierto por los créditos"*. **Es falso.** Con 7,4 MB de BD y 30 solicitudes/día es improbable superar el baseline de forma sostenida, pero hay que **vigilarlo**, no darlo por imposible:

  - Alarma de CloudWatch sobre **`CPUSurplusCreditsCharged` > 0** — es el único aviso de que la BD empezó a cobrar extra.
  - **AWS Budget con alerta a $30**, el techo real del proyecto.
- **Por qué RDS estándar y no Aurora:** Aurora arranca en ~$43/mes (Serverless v2 mín. 0,5 ACU). A esta escala es carísimo de más → **RDS estándar es lo económico**, como intuías.

### 4.3 Amazon SES — correo transaccional · **~$2/mes**
- **Qué:** conteo real del flujo (`NotificacionService` → `EmailService`): por solicitud se encolan **1-3** correos al crearla (supervisor, receptor, solicitante — o el combinado `_enviar_email_supervisor_receptor`) y **2-4** al responder receptor y supervisor (`notificacion_service.py:391-512`). Son **~6 correos por solicitud**.
- **Volumen a 30 solicitudes/día:** 30 × 6 × 30 días = **5.400/mes**, más recuperación de contraseña y avisos de seguridad ≈ **6.000/mes** × $0,10/1.000 ≈ **$0,60/mes**. (A 100 solicitudes/día serían ~18.000/mes ≈ $1,80.)
- **Por qué SES (opción B del plan de correo):**
  - **Sin secreto que rotar:** la EC2 usa **IAM role**; adiós al App Password de Gmail que caduca.
  - **Arregla los 20 s:** 1 llamada HTTPS (~0,3 s) vs handshake SMTP (~5 s); con envío **asíncrono** la respuesta baja a **<1 s percibido**.
  - **Entregabilidad:** DKIM/SPF/DMARC sobre `parqueexplora.org` → no cae en spam.
- **Dependencia:** IT verifica el dominio en SES y hay que **salir del sandbox** (§6).

### 4.4 Disco de la EC2 (EBS gp3, 20 GB) · **~$1,60/mes**
- **Qué:** el volumen raíz de la instancia, a $0,08/GB-mes. Es **independiente** de los 20 GB de RDS (§4.2) y **faltaba por completo en la versión anterior de este presupuesto**.
- 20 GB alcanzan de sobra: SO + Python + la app + los 143 MB de estáticos + logs.

### 4.5 IPv4 pública (Elastic IP) · **~$3,65/mes**
- Desde 2024 AWS cobra toda IPv4 pública ($0,005/h). Inevitable con una instancia pública. Al mantener la EC2 en subred pública **evitamos el NAT gateway (~$32/mes)**.
- **Se cobra aunque esté ociosa:** *"Fees apply regardless of whether the Elastic IP address is currently in use by a resource or is idle in your account"* ([docs EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/elastic-ip-addresses-eip.html)). No la reserves antes de necesitarla.

### 4.6 SSL · **$0** — Let's Encrypt en Nginx
- ACM solo sirve con balanceador/CloudFront (~$16/mes). Con una EC2, **Certbot** da HTTPS gratis y auto-renovado.

### 4.7 DNS · **$0** — lo gestiona IT
- `parqueexplora.org` lo administra IT. Basta un registro `A` (`swalp.parqueexplora.org` → Elastic IP). Route 53 solo si quisieras DNS en AWS ($0,50/mes/zona).

### 4.8 Estáticos · **$0** — Nginx/WhiteNoise
- 1.000 usuarios internos no necesitan CDN. S3 (~$0,10) + CloudFront quedan como opción futura.

### 4.9 Monitoreo y backups · **$0** — incluidos
- CloudWatch básico (free tier). Backups de RDS incluidos: el *free tier* de backup cubre **hasta el tamaño del volumen asignado** (los 20 GB), no solo el tamaño de la BD — con 7,4 MB de datos sobra muchísimo. Código en Git → la EC2 es reemplazable.

---

## 5. Costo total mensual

**Precios unitarios verificados el 2026-09-04** (us-east-1, on-demand). Fuentes al final de la sección.

| Recurso | Precio verificado |
|---|---|
| EC2 `t4g.micro` (2 vCPU, 1 GiB) | $0,008/h · RI 1 año sin anticipo: $0,005/h |
| EC2 `t4g.small` (2 vCPU, 2 GiB) | $0,017/h · RI 1 año sin anticipo: $0,011/h |
| RDS `db.t4g.micro` MySQL **Single-AZ** | $0,016/h · RI 1 año: $0,0116/h (−28 %) |
| Almacenamiento RDS gp3 | $0,115/GB-mes |
| EBS gp3 (disco de la EC2) | $0,08/GB-mes |
| IPv4 pública / Elastic IP | $0,005/h = $3,65/mes |
| Amazon SES | $0,10 / 1.000 correos |
| **IVA Colombia** | **19 %** (ver nota fiscal abajo) |

> ⚠️ **Cuidado con las comparativas de terceros.** Algunas publican `db.t4g.micro` a **$0,03/h**: es el
> precio **Multi-AZ** (exactamente el doble) mal etiquetado. Single-AZ, que es lo que usa este plan,
> son **$0,016/h**.

### 5.1 Opción DECIDIDA (2026-09-04) — `t4g.micro`, 300 usuarios

| Servicio | Config | On-demand | Con compromiso 1 año* |
|---|---|---:|---:|
| EC2 web | `t4g.micro` | $6,13 | $3,65 |
| Disco EC2 | 20 GB gp3 (EBS) | $1,60 | $1,60 |
| RDS instancia | `db.t4g.micro` Single-AZ | $11,68 | $8,47 |
| RDS almacenamiento | 20 GB gp3 | $2,30 | $2,30 |
| IPv4 pública | 1 Elastic IP | $3,65 | $3,65 |
| Amazon SES | ~6.000 correos/mes | $0,60 | $0,60 |
| CloudWatch + transferencia de salida | | $1,00 | $1,00 |
| SSL / DNS / estáticos | Let's Encrypt + IT + Nginx | $0 | $0 |
| **Subtotal** | | **$26,96** | **$21,27** |
| **+ IVA 19 %** | | **$32,08** | **$25,31** |
| **En pesos @ 4.050 COP/USD** | | **≈ 130.000 COP** ✅ | **≈ 102.500 COP** ✅ |

\* *Savings Plan (EC2) + Reserved Instance (RDS), 1 año sin pago inicial.*

### 5.2 Comparativa con `t4g.small` (el escalón siguiente)

| | `t4g.micro` | `t4g.small` |
|---|---:|---:|
| Subtotal on-demand | $26,96 | $33,09 |
| + IVA 19 % | $32,08 | **$39,38** |
| COP @ 4.050 | ≈ 130.000 ✅ | **≈ 159.500** ❌ |
| Subtotal con RI 1 año | $21,27 | $25,65 |
| + IVA 19 % | $25,31 | $30,52 |
| COP @ 4.050 | ≈ 102.500 ✅ | ≈ 123.600 ✅ |

**`t4g.small` en on-demand se pasa del techo de 150.000 COP** por ~9.500 COP: solo cabría con el dólar
por debajo de **3.809 COP**, y está en ~4.050. **Con RI a 1 año sí cabe** (~123.600 COP) y sale más
barato que `micro` en on-demand — pero comprometerse a un año antes de medir la carga real es apostar.
De ahí la decisión de §5.1.

### 5.3 Nota fiscal: el IVA puede no ser costo real

AWS factura **19 % de IVA** a clientes en Colombia, y **ninguno de los precios de este documento lo
incluye salvo donde se indica**. Pero si Parque Explora es responsable de IVA (lo es, como entidad
jurídica), ese 19 % es **descontable como crédito fiscal ante la DIAN**: el costo real para la
institución sería el **subtotal sin IVA**.

**Confirmar con contabilidad antes de decidir**, porque cambia el resultado: si el IVA se recupera,
`t4g.small` on-demand son $33,09 ≈ **134.000 COP** y también cabría en el presupuesto.

### 5.4 Riesgo cambiario

Todo lo anterior asume **4.050 COP/USD**. A **4.400 COP/USD**: `micro` on-demand sube a ~141.000 COP
(aguanta) y `small` con RI a ~134.000 COP (aguanta); `small` on-demand se dispara a ~173.000 COP.
El plan elegido tiene margen; el descartado no.

### 5.5 Free Tier y alta disponibilidad

| Escenario | Efecto |
|---|---|
| **Cuenta AWS con <12 meses (Free Tier)** | EC2 + RDS micro + 20 GB gratis el 1.er año → pagas **solo IPv4 + SES ≈ $5/mes**. **Verificarlo antes de lanzar.** |
| RDS a **Multi-AZ** (`db.t4g.micro`) | +~$12/mes → **fuera de presupuesto**. Da failover automático. Descartado por ahora; Single-AZ ya cubre el objetivo de quitarse la administración |

### 5.6 Controles de costo obligatorios

Ninguno es opcional con un techo de 150.000 COP:

1. **EC2 en modo `standard`** (§4.1) — convierte el burst de costo variable en costo fijo.
2. **Alarma CloudWatch sobre `CPUSurplusCreditsCharged` de RDS > 0** (§4.2) — el único aviso de que
   la BD empezó a cobrar excedente, que en RDS **no se puede desactivar**.
3. **AWS Budget con alerta a $30.**
4. **No reservar la Elastic IP antes de necesitarla** (§4.5) — se cobra ociosa.

**Fuentes de precios (consultadas 2026-09-04):**
[t4g.micro](https://instances.vantage.sh/aws/ec2/t4g.micro) ·
[t4g.small](https://instances.vantage.sh/aws/ec2/t4g.small) ·
[db.t4g.micro](https://calculator.holori.com/aws/rds/db.t4g.micro) ·
[almacenamiento RDS gp3](https://www.usage.ai/blogs/aws/reserved-instances/rds/storage-cost/) ·
[EBS gp3](https://www.cloudzero.com/blog/ebs-pricing/) ·
[IPv4 pública](https://www.doit.com/blog/aws-public-ipv4-price-increase-the-complete-guide) ·
[IVA SaaS Colombia](https://payproglobal.com/saas-sales-tax/colombia/)

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
4. **Archivado anual (pendiente, sin fecha):** dump anual a S3 cada diciembre. Se
   analizó purgar los años pasados y se **descartó**: el almacenamiento sobra para
   >150 años sobre el mínimo de 20 GB ya pagado. Ver
   [MANUAL_ARCHIVADO_ANUAL.md](./MANUAL_ARCHIVADO_ANUAL.md).
5. **Django prod:** `.env` con `ENVIRONMENT=production`, `DEBUG=False`, `ALLOWED_HOSTS`, `SECRET_KEY`, `CSRF_TRUSTED_ORIGINS`, conexión a RDS.

---

## 7. CI/CD — integración y despliegue continuos

**CI (integración continua) — ✅ implementado.** Workflow `.github/workflows/ci.yml` (en la **raíz del
repositorio**, no dentro de `AppTurnosExplora/`; Actions solo lee esa ruta). Dos jobs:

- **`test`** (bloqueante): levanta MySQL 8.0, **carga las tablas de zona horaria** (la imagen no las trae y sin ellas `CONVERT_TZ` devuelve `NULL`), corre `manage.py check`, `manage.py check --deploy` con entorno de producción simulado —así `core.E001` impide desplegar con LocMemCache— y la suite `pytest -n auto` con gate de cobertura al 64 %. Sobre **Python 3.12**, la versión del Dockerfile: el desarrollo local va en 3.14 y este job detecta lo que funcione allí y no en producción.
- **`lint`** (informativo, `continue-on-error`, añadido 2026-08-19): `ruff --statistics`, `bandit` y `pip-audit`. No bloquea todavía: el baseline de ruff ronda los 1.000-1.500 avisos y se endurecerá por familias de reglas.

Ampliado el 2026-08-19: antes solo corría en `main`, ahora en **cualquier rama**, para que sirva de red
durante la refactorización y no solo al abrir el PR.

**CD (despliegue continuo) — ⏳ pendiente, se hace al montar AWS.** Un segundo workflow `deploy.yml` que, al mergear a `main`, entre por SSH al EC2 y ejecute la actualización:
`git pull → pip install -r requirements.txt → migrate → collectstatic → systemctl restart appturnosex`.

- **Bloqueado por infraestructura:** necesita que la EC2 exista (host, usuario, clave SSH). Por eso **no se crea todavía** — un workflow apuntando a un servidor inexistente sería código muerto.
- **Al montar AWS, requiere estos GitHub Secrets:** `SSH_HOST` (Elastic IP), `SSH_USER` (ej. `appuser`), `SSH_KEY` (clave privada de despliegue). Se usaría una action tipo `appleboy/ssh-action`.
- **Interino (sin CD):** la actualización manual del Anexo del [checklist](./CHECKLIST_DESPLIEGUE_AWS_RDS.md) (`git pull` + `systemctl restart`) es suficiente para una sola instancia.
- **Docker:** no interviene en el despliegue a EC2 — la app corre con systemd + Gunicorn, no en
  contenedor. Pero **el `Dockerfile` y los dos `docker-compose` se conservan**; ver §7.1.

### 7.1 ¿Sigue haciendo falta Docker si descartamos Fargate?

**Sí, pero cambia de papel:** deja de ser un camino de despliegue y pasa a ser **herramienta de
prueba local**. Qué usa realmente cada pieza hoy:

| Fichero | Quién lo usa | ¿Se conserva? |
|---|---|---|
| `Dockerfile` | Solo los dos compose. **El CI NO lo usa**: `ci.yml` instala Python 3.12 con `setup-python`, no construye la imagen | ✅ Sí |
| `docker-compose.local.yml` | Prueba local con la config de **producción** (`ENVIRONMENT=production`, `DEBUG=False`, sin debug-toolbar) contra una BD efímera | ✅ Sí |
| `docker-compose.hostdb.yml` | Igual pero contra el MySQL real del host, sin migraciones | ✅ Sí (uso marginal) |

**Por qué conservarlos aunque no se use Fargate:**

1. **Cuestan $0.** No son infraestructura desplegada; son ficheros en el repo. Borrarlos no ahorra
   un peso del presupuesto de §5.
2. **Es la única forma de probar la configuración de producción antes de desplegar.** `runserver`
   corre con `DEBUG=True` y la debug-toolbar; `docker-compose.local.yml` levanta exactamente el
   `ENVIRONMENT=production` que va a correr en la EC2. Ese *smoke test* es justo lo que atrapa los
   fallos de `DEBUG=False` (estáticos, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`) **antes** de que los
   vea un usuario.
3. **El `Dockerfile` documenta el entorno de producción.** Fija Python 3.12 y las dependencias de
   sistema; es la referencia al aprovisionar la EC2 y lo que mantiene alineado el `python-version`
   del CI.
4. **Es la puerta de salida.** Si mañana el presupuesto crece o cansa mantener el SO, migrar a
   Fargate o App Runner es *build + push*, no empezar de cero.

**⚠️ Salvedad importante:** con el plan EC2, el contenedor **ya no refleja producción al 100 %**. En
la EC2 los estáticos los sirve **Nginx** y el proceso lo gestiona **systemd**; en el contenedor los
sirve **WhiteNoise** con el `CMD` del `Dockerfile`. Sirve para validar Django y su configuración, **no**
para validar Nginx, TLS ni el arranque por systemd. Eso se prueba en la propia EC2.

---

## 8. Variante sin gestión de servidores: ECS Fargate — ❌ DESCARTADA (2026-09-04)

> **Decisión:** descartada **por presupuesto**. Con los crons contabilizados sale en **~$60/mes + IVA
> ≈ 290.000 COP**, casi el doble del techo de 150.000 COP. Se conserva esta sección como referencia
> y como camino si el presupuesto cambia.

Si el objetivo es **no gestionar el SO** (parches, actualizaciones, Nginx/systemd) y concentrarse solo en la app, se sustituye la EC2 por **ECS Fargate**: AWS corre el contenedor y **no hay servidor que mantener**. Requiere **dockerizar** (ya incluido: `AppTurnosExplora/Dockerfile` + `.dockerignore`, imagen validada).

> 📋 El checklist paso a paso de Fargate **se borró el 2026-09-04** al descartarse esta variante.
> Sigue en el historial de git si algún día hiciera falta:
> `git show e0e4388:AppTurnosExplora/docs/05-referencia/deployment/CHECKLIST_DESPLIEGUE_FARGATE.md`

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
| **EventBridge: crons como tasks ECS** (ver abajo) | **~3,60** |
| Amazon SES | 0,60 |
| ECR + CloudWatch | ~1,00 |
| ACM (SSL) | 0 |
| **Subtotal (1 task)** | **≈ $54/mes** |
| **+ IVA 19 %** | **≈ $64/mes ≈ 260.000 COP** |
| Alta disponibilidad (2 tasks), con IVA | **≈ $85/mes ≈ 345.000 COP** |

**El costo de los crons faltaba en la versión anterior de esta tabla.** En Fargate no hay `crontab`:
`procesar_email_outbox` debe correr **cada 5 minutos** como task ECS lanzada por EventBridge.
Son **8.640 lanzamientos/mes**, cada uno
facturado con **mínimo 1 minuto** de Fargate = 144 h/mes ≈ **$3,60**. En EC2 esas mismas líneas de
`crontab` cuestan **$0**.

Con **Compute Savings Plan** (Fargate, 1 año) el cómputo baja, pero el ALB no tiene descuento por
compromiso y el suelo se queda en ~$45 + IVA ≈ 220.000 COP: **sigue fuera de presupuesto**.

### Trade-off vs plan EC2 (~$32/mes con IVA)
- **+~$32/mes** (≈ +100 %). El grueso: el premium de cómputo de Fargate, el **ALB obligatorio (~$18)**
  y los crons por EventBridge.
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

> **DECISIÓN (2026-09-04): plan A con `t4g.micro`.**
>
> **A) EC2 — ≈ $32/mes con IVA (≈ 130.000 COP)** on-demand · ≈ 102.500 COP con compromiso a 1 año ·
> ≈ $5/mes el 1.er año si aplica Free Tier. 1× EC2 **`t4g.micro`** (Nginx + Gunicorn + Django, HTTPS
> Let's Encrypt) + RDS `db.t4g.micro` Single-AZ + SES. Tú mantienes el SO (parches, Nginx).
>
> **B) ECS Fargate — ❌ descartada.** ≈ $64/mes con IVA (≈ 260.000 COP) contando los crons por
> EventBridge. Casi el doble del techo de 150.000 COP. Ver §8.
>
> **Por qué `micro` y no `small`:** `small` on-demand se pasa del techo (≈ 159.500 COP) y con RI a 1
> año sí cabe, pero comprometerse a un año **antes de medir** la carga real es apostar. Se arranca en
> `micro`, se mide un mes con CloudWatch y entonces se decide: RI en `micro` (≈ 102.500 COP) si va
> holgado, o `small` con RI (≈ 123.600 COP) si va apretado. Ambos caminos caben.
>
> **Común a ambos:** **RDS `db.t4g.micro`** quita la administración de la BD, y **SES** (con el
> refactor From/Reply-To + async ya hecho) arregla los 20 s del correo. Sin Redis ni bucket de media.
>
> **No opcional:** los cuatro controles de costo de §5.6. Sin el modo `standard` en la EC2, el
> excedente de créditos puede comerse justo el margen que da haber elegido la opción barata.

---

## 11. La URL, la IP y la configuración de la app — paso a paso

Esta sección responde a la pregunta práctica: **¿qué escribe un empleado en el navegador, y qué hay
que configurar para que eso funcione?** El checklist
([CHECKLIST_DESPLIEGUE_AWS_RDS.md](./CHECKLIST_DESPLIEGUE_AWS_RDS.md)) tiene los comandos; aquí está
**el porqué y en qué orden**, que es lo que se pierde entre fases.

### 11.1 La cadena completa, de un vistazo

```
  Empleado escribe:  https://swalp.parqueexplora.org
                              │
                     (1) DNS: registro A que agrega IT
                              │  swalp.parqueexplora.org → 52.x.x.x
                              ▼
                     (2) Elastic IP  52.x.x.x   ← IP FIJA de AWS, tuya
                              │
                     (3) Security Group: deja pasar 80 y 443
                              ▼
                     (4) Nginx en la EC2
                         · termina el TLS (certificado Let's Encrypt)
                         · sirve /static/ directo desde disco
                         · lo demás lo pasa a Gunicorn por socket Unix
                         · reescribe X-Forwarded-For / X-Forwarded-Proto
                              ▼
                     (5) Gunicorn + Django
                         · valida el dominio contra ALLOWED_HOSTS
                         · valida el origen contra CSRF_TRUSTED_ORIGINS
                         · construye enlaces de correo con SITE_URL
                         · axes lee la IP real desde X-Forwarded-For
```

**Las cinco piezas se configuran en tres sitios distintos** y ese es el lío habitual:

| Pieza | Dónde se configura | Quién lo hace |
|---|---|---|
| (1) DNS | Panel de DNS de `parqueexplora.org` | **IT de Parque Explora** |
| (2) Elastic IP · (3) Security Group | Consola AWS | Tú |
| (4) Nginx + certificado | Ficheros en la EC2 | Tú (checklist FASE 7 y 9) |
| (5) Variables de Django | `.env` en la EC2 | Tú (checklist FASE 4) |

### 11.2 ¿Qué URL van a usar los empleados?

**`https://swalp.parqueexplora.org`** — un subdominio del dominio que ya tiene Parque Explora.

**Por qué un dominio y no la IP pelada:**

1. **HTTPS necesita un dominio.** Let's Encrypt **no emite certificados para direcciones IP**. Sin
   dominio no hay candado, y sin candado `SECURE_HTTPS=True` (que activa cookies `Secure` y HSTS,
   `settings.py:508-526`) deja la app inaccesible.
2. **La IP puede cambiar.** Si algún día recreas la instancia, con dominio solo cambia un registro
   DNS; con IP hay que avisar a 300 personas.
3. **`ALLOWED_HOSTS` y `CSRF_TRUSTED_ORIGINS` se fijan al dominio.** Cambiar de IP obligaría a tocar
   el `.env` y reiniciar.

> **Tú no controlas el DNS.** `parqueexplora.org` lo administra IT. Tu entregable es la **Elastic IP**;
> lo que pides es un registro **A**: `swalp.parqueexplora.org → <TU_ELASTIC_IP>`. Es la dependencia
> externa del proyecto: **pídela con antelación**, porque bloquea HTTPS (FASE 9) y SES (FASE 10).

### 11.3 El orden importa, y es contraintuitivo

El error clásico es intentar sacar el certificado antes de que el DNS resuelva. Certbot **verifica el
dominio conectándose a él**: si `swalp.parqueexplora.org` todavía no apunta a tu IP, falla.

```
FASE 2  Lanzar EC2 + asociar Elastic IP        →  ya tienes la IP
FASE 8  IT crea el registro A hacia esa IP     →  ⏳ esperar propagación
        Verificar:  nslookup swalp.parqueexplora.org
FASE 9  certbot --nginx -d swalp.parqueexplora.org   ← solo funciona DESPUÉS
```

**Mientras esperas el DNS puedes avanzar en todo lo demás** (FASES 3-7): servidor, base de datos,
Gunicorn, Nginx por HTTP. Se prueba con `http://<ELASTIC_IP>` añadiendo temporalmente la IP a
`ALLOWED_HOSTS` y dejando `SECURE_HTTPS=False`. **Ambas cosas se revierten en FASE 9**, cuando ya haya
certificado.

### 11.4 Qué va exactamente en el `.env` — y qué se rompe si falta

Cinco variables dependen del dominio. La tabla completa está en
[CONFIGURACION_PRODUCCION.md §2](./CONFIGURACION_PRODUCCION.md); aquí solo las relacionadas con la URL:

```bash
# El dominio final. SIN esquema (sin https://), separado por comas.
# Django rechaza con 400 Bad Request cualquier petición cuyo Host no esté aquí.
ALLOWED_HOSTS=swalp.parqueexplora.org

# CON esquema. Django 5 lo EXIGE para aceptar cualquier POST por HTTPS.
# Si falta: el login devuelve "CSRF verification failed" y NADIE puede entrar.
CSRF_TRUSTED_ORIGINS=https://swalp.parqueexplora.org

# Con esquema y sin barra final. Es la base de los enlaces de los CORREOS.
# Si falta: los correos salen con enlaces a http://127.0.0.1:8000 (settings.py:273)
# y los botones de aprobar/rechazar no funcionan para nadie.
SITE_URL=https://swalp.parqueexplora.org

# Activa HSTS, cookies Secure y la redirección HTTP→HTTPS.
# Ponlo en False HASTA tener certificado (FASE 9), o la app queda inaccesible.
SECURE_HTTPS=True

# Cuántos proxies hay entre el usuario y Django. Con Nginx en la EC2: 1.
# Ya vale 1 por defecto en producción; declararlo explícito documenta la decisión. Ver 11.5.
AXES_IPWARE_PROXY_COUNT=1
```

**El fallo más común y más confuso** es mezclar los formatos: `ALLOWED_HOSTS` va **sin** `https://` y
`CSRF_TRUSTED_ORIGINS` y `SITE_URL` van **con**. Poner el esquema en `ALLOWED_HOSTS` no da error al
arrancar: da 400 en cada petición, lo que parece un problema de red y no de configuración.

### 11.5 ⚠️ `AXES_IPWARE_PROXY_COUNT`: el que puede dejar fuera a los 300

Es el ajuste más peligroso del despliegue, y merece su propio apartado.

`django-axes` bloquea tras 5 intentos fallidos **por usuario Y por IP** (`settings.py:370`). Con Nginx
delante, Django ve por defecto la IP de **Nginx** —siempre la misma— para todo el mundo. Consecuencia:
**al quinto fallo de cualquier empleado, queda bloqueada la plantilla entera durante una hora.**

La configuración ya está resuelta en el código y encaja con el plan EC2:

- `AXES_IPWARE_PROXY_COUNT` vale **1** por defecto en producción (`settings.py:386`) — exactamente el
  número de intermediarios que hay con Nginx en la propia instancia.
- Con ese valor, `settings.py:401-402` activa `AXES_IPWARE_META_PRECEDENCE_ORDER` para que axes mire
  `X-Forwarded-For`. **Sin esa segunda línea la primera no sirve de nada, y falla en silencio.**
- Nginx debe **escribir** esa cabecera. El bloque de la FASE 7 ya lo hace:
  `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`. La documentación de Nginx es
  explícita en que **no se envía nada por defecto**: si esa línea no está, no hay cabecera que leer.

**Verificación obligatoria antes de dar la URL a nadie:**

```bash
python manage.py verificar_ip_cliente   # core/login/management/commands/
```

Debe reportar la IP **real del cliente**, no la de Nginx (`127.0.0.1`). Si reporta la de Nginx, el
bloqueo por IP es una bomba: **no publiques la URL hasta arreglarlo.**

> Si algún día se añade un segundo intermediario (CloudFront, un ALB), este número **sube a 2**. Con
> el valor viejo, axes vuelve a ver una sola IP para todos.

### 11.6 Los estáticos: por qué Nginx y no Django

Son **143 MB** (§1). Django con `DEBUG=False` **no los sirve**, y WhiteNoise los serviría a través de
los workers de Gunicorn, gastando en imágenes y CSS los 2-3 workers que tienes en `t4g.micro`.

El bloque `location /static/` de la FASE 7 los sirve **desde disco, sin tocar Python**. Requiere:

1. `python manage.py collectstatic` los junta en `staticfiles/` (`settings.py:224`).
2. El `alias` de Nginx apunta a esa ruta **absoluta**.
3. `sudo usermod -aG appuser www-data` — sin esto Nginx no puede leerlos y da **403 en todos los CSS**:
   la app carga "sin estilos" y parece rota.

Coste: **$0**. No hacen falta S3 ni CloudFront a esta escala.

### 11.7 Correo: la URL también depende de SES

Los correos llevan enlaces construidos con `SITE_URL` (11.4) y salen desde el dominio, así que SES
también depende del DNS.

**⚠️ El límite del sandbox está justo en tu volumen.** Una cuenta SES nueva arranca en sandbox con
`Max24HourSend = 200` correos/día y **solo puede escribir a direcciones verificadas**. Tu flujo son
**~180 correos/día** (§4.3): cabría por los pelos en la cuota, pero **es inservible igualmente**,
porque los 300 empleados no están verificados uno a uno.

```bash
# Ver la cuota actual
aws ses get-send-quota

# Pedir acceso de producción (saca del sandbox)
aws sesv2 put-account-details \
    --production-access-enabled \
    --mail-type TRANSACTIONAL \
    --website-url https://swalp.parqueexplora.org \
    --contact-language ES
```

Dos trampas documentadas por AWS:

1. **El sandbox es por región.** Salir del sandbox en una región **no** aplica a las demás. Pídelo en
   **la misma región del despliegue** (`us-east-1`).
2. **La aprobación no es inmediata** (suele tardar ~24 h). Es la segunda dependencia externa junto al
   DNS: **pídela pronto**, porque sin ella no sale un solo correo a los empleados y el flujo de
   aprobaciones —que es la app entera— no funciona.

### 11.8 Resumen: el camino crítico

Dos cosas no dependen de ti y bloquean el despliegue. **Pídelas el primer día:**

| # | Dependencia | A quién | Bloquea |
|---|---|---|---|
| 1 | Registro **A** `swalp.parqueexplora.org` → Elastic IP | IT Parque Explora | HTTPS (FASE 9) y la URL final |
| 2 | Registros **DKIM/SPF** de SES en `parqueexplora.org` | IT Parque Explora | Entregabilidad del correo |
| 3 | **Salida del sandbox de SES** en us-east-1 | AWS (~24 h) | Todo el flujo de aprobaciones |

Todo lo demás (FASES 1-7) se puede hacer en paralelo mientras esas tres avanzan.

---

## 12. ¿Se puede hacer todo esto en YAML? — Infraestructura como código

**Sí, la mitad. Y esa mitad conviene hacerla en YAML; la otra mitad no.**

La plantilla está escrita y validada: **[`infra/cloudformation/swalp-infra.yaml`](../../../infra/cloudformation/swalp-infra.yaml)**.

### 12.1 La división: infraestructura sí, configuración del servidor no

| Capa | Ejemplo | ¿YAML? | Dónde |
|---|---|---|---|
| **Infraestructura AWS** | VPC, security groups, EC2, RDS, Elastic IP, alarmas | ✅ **Sí** | `swalp-infra.yaml` (CloudFormation) |
| **Config dentro del servidor** | Nginx, certbot, gunicorn/systemd, crontab, `.env` | ❌ **No** | A mano, checklist FASES 3-9 |
| **Despliegue de código** | `git pull`, `migrate`, `collectstatic`, restart | ✅ **Sí** | `deploy.yml` (GitHub Actions) |

**Por qué la configuración del servidor NO va en YAML:** CloudFormation puede lanzarla por `UserData`,
pero entonces **un error de Nginx se depura recreando la pila entera** — un ciclo de 15 minutos para
arreglar una línea mal puesta. Se hace una vez, a mano, siguiendo el checklist. Si algún día hay más
de un servidor, la respuesta es Ansible, no `UserData`.

Lo que la plantilla **sí** deja resuelto en el arranque es lo que no se depura: paquetes base, el
**swap de 2 GB** y el certificado de RDS.

### 12.2 Qué gana el YAML aquí (y no es "quedar bien")

1. **Los controles de costo dejan de ser un post-it.** `CreditSpecification: CPUCredits: standard`
   está *dentro* del recurso EC2. Es imposible olvidarlo, que es exactamente el fallo que puede
   reventar el presupuesto (§4.1). Lo mismo con la alarma de `CPUSurplusCreditsCharged` y la de
   facturación a $30.
2. **`DeletionPolicy: Snapshot` en la RDS.** Si alguien borra la pila, los datos sobreviven en un
   snapshot. Es la red de seguridad que justifica pagar RDS.
3. **Escalar es editar un parámetro.** El "1 clic" de `micro` → `small` (§3) es cambiar
   `InstanceType` y re-desplegar, con el cambio versionado en git.
4. **Se puede borrar todo.** `aws cloudformation delete-stack` no deja recursos huérfanos cobrando
   —una Elastic IP olvidada son $3,65/mes— que es el error de costo más común al probar.
5. **La segunda vez es gratis.** Levantar un entorno de pruebas idéntico es re-desplegar con otro
   `--stack-name`.

### 12.3 Cómo se usa

```bash
# Crear (o actualizar) toda la infraestructura
aws cloudformation deploy \
    --template-file infra/cloudformation/swalp-infra.yaml \
    --stack-name swalp-prod \
    --parameter-overrides \
        VpcId=vpc-xxxx \
        SubnetIds=subnet-aaaa,subnet-bbbb \
        EC2SubnetId=subnet-aaaa \
        SSHLocation=<TU_IP>/32 \
        KeyName=<tu-key-pair> \
        DBPassword=<LA-QUE-PONGAS> \
        AlertEmail=tu@correo.com \
    --capabilities CAPABILITY_IAM \
    --region us-east-1

# Leer lo que creó: la IP para IT y el endpoint para el .env
aws cloudformation describe-stacks --stack-name swalp-prod \
    --query 'Stacks[0].Outputs' --output table
```

> 🔴 **La contraseña de RDS NO se escribe en el YAML.** El parámetro `DBPassword` es `NoEcho`, así
> que no aparece en la consola ni en los eventos de la pila. El fichero se versiona en git; la
> contraseña se pasa por `--parameter-overrides` y vive solo en el `.env` de la instancia.

### 12.4 Qué NO puede hacer el YAML, por mucho que quieras

Tres cosas del despliegue **no son recursos de AWS** y ninguna herramienta de IaC las resuelve:

| Cosa | Por qué no | Quién la hace |
|---|---|---|
| El registro DNS `swalp.parqueexplora.org` | El dominio lo administra **IT**, no esta cuenta AWS | IT Parque Explora |
| Los registros DKIM/SPF de SES | Van en ese mismo DNS ajeno | IT Parque Explora |
| La **salida del sandbox de SES** | Es una **solicitud a AWS** que revisa una persona (~24 h), no un recurso | Tú → AWS |

Son las tres dependencias del camino crítico (§11.8). **Pídelas el primer día**, porque el YAML se
despliega en 15 minutos y luego te quedas esperándolas.

### 12.5 Orden completo de despliegue

```
DÍA 1 — lo que depende de otros (pedirlo YA)
  □ Solicitar salida del sandbox de SES en us-east-1        (~24 h)  §11.7
  □ Desplegar la pila YAML → obtienes la Elastic IP                  §12.3
  □ Pedir a IT el registro A hacia esa IP                            §11.2
  □ Pedir a IT los registros DKIM/SPF de SES                         FASE 10

MIENTRAS ESPERAS — no depende de nadie
  □ FASE 0.4  Correr la suite, también con --dias-en-el-futuro=45
  □ FASE 3    Entrar por SSH, clonar el código, venv
  □ FASE 4    Escribir el .env  (DB_HOST = output DBEndpoint)
              ⚠️ De momento: ALLOWED_HOSTS con la IP y SECURE_HTTPS=False
  □ FASE 5    migrate, createcachetable, collectstatic, crear admin
  □ FASE 6    Gunicorn como servicio systemd
  □ FASE 7    Nginx (proxy + estáticos + X-Forwarded-For)
              Probar por http://<ELASTIC_IP>

CUANDO EL DNS YA RESUELVE  (nslookup swalp.parqueexplora.org)
  □ FASE 9    certbot --nginx -d swalp.parqueexplora.org
  □ Revertir  ALLOWED_HOSTS al dominio · SECURE_HTTPS=True · reiniciar
  □ FASE 4    SITE_URL y CSRF_TRUSTED_ORIGINS con https://

CUANDO SES YA ESTÁ FUERA DEL SANDBOX
  □ FASE 10   Configurar el correo y enviar uno de prueba real

ANTES DE DAR LA URL A NADIE — no negociable
  □ python manage.py verificar_ip_cliente   → ¿IP real, no la de Nginx?   §11.5
  □ Los crons en crontab: procesar_email_outbox (5 min) + sanciones (diario)
  □ python manage.py verificar_crons
  □ manage.py check --deploy  sin errores  (core.E001 = falta la caché)
  □ Alarma de facturación a $30 activa y suscripción de correo confirmada
```

### 12.6 El CD también es YAML, y ya está diseñado

`deploy.yml` (GitHub Actions, §7) entra por SSH y ejecuta
`git pull → pip install → migrate → collectstatic → systemctl restart`. Sigue **pendiente a
propósito**: necesita que la EC2 exista para tener `SSH_HOST`, `SSH_USER` y `SSH_KEY`. Se crea
justo después de la FASE 6, cuando el servicio ya arranca a mano.
