# ✅ Checklist de despliegue — AppTurnos/SWALP en AWS (EC2 + RDS + SES)

**Fecha:** 2026-07-24
**Arquitectura:** ver [arquitectura-aws-rds-recomendada](./arquitectura-aws-rds-recomendada.md)
**Objetivo:** dejar la app **pública en internet** (acceso desde cualquier parte, con login) sobre:
`EC2 t4g.small (Nginx + Gunicorn) → RDS MySQL db.t4g.micro → Amazon SES`, HTTPS con Let's Encrypt.

> ⚠️ Este documento **reemplaza** al genérico [MANUAL_DESPLIEGUE_EC2.md](./MANUAL_DESPLIEGUE_EC2.md), que es genérico y asume `mysqlclient`. Este proyecto usa **PyMySQL** (no hay que compilar nada). Los nombres de variables `.env` de aquel manual ya están corregidos (van sin prefijo `DJANGO_`), pero este checklist sigue siendo el documento de referencia.

---

## FASE 0 — Ajustes de código previos

> ✅ **Auditado el 2026-09-04: los puntos 0.1, 0.2 y 0.3 YA ESTÁN HECHOS en el código.**
> Se conservan como registro de por qué cada uno importa, pero **no hay nada que cambiar**.
> Solo queda pendiente **0.4** (correr la suite), que es una verificación, no una edición.

### 0.1 Paquetes de producción — ✅ HECHO
Ya están en `requirements.txt`: `django-axes[ipware]==7.0.1`, `django-cors-headers==4.9.0`,
`gunicorn==23.0.0`.

> 🔴 **La versión anterior de este checklist pedía instalar `django-axes==7.0.1`, SIN el extra
> `[ipware]`. Seguirla al pie de la letra ROMPERÍA el despliegue de forma silenciosa.**
> Sin `django-ipware`, axes ignora los ajustes `AXES_IPWARE_*` y resuelve siempre `REMOTE_ADDR`
> —la IP de Nginx— para todo el mundo: al quinto fallo de cualquier empleado quedaría bloqueada la
> plantilla entera. El propio `requirements.txt` lo avisa en un comentario. **No toques esa línea.**

### 0.2 Bucle de redirección tras Nginx — ✅ HECHO
`SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` ya está en `config/settings.py:512`,
dentro del bloque `if SECURE_HTTPS:`. Sin esto, Nginx termina el TLS y reenvía por HTTP, con lo que
`SECURE_SSL_REDIRECT` redirige en bucle infinito.

### 0.3 `CSRF_TRUSTED_ORIGINS` — ✅ HECHO
Ya está en `config/settings.py:39`, leído del entorno. **Lo que sí falta es darle valor en el `.env`**
(FASE 4): la variable existe pero por defecto es una lista vacía, y sin valor el login da 403 CSRF.

### 0.4 Correr la suite, y correrla tambien con el reloj adelantado

```bash
cd AppTurnosExplora
pytest -n auto                          # debe estar en verde
pytest -n auto --dias-en-el-futuro=45   # ¿algo se pondrá rojo solo dentro de mes y medio?
```
- [ ] Las dos corridas salen en verde.
- [ ] **Si la segunda sale roja, eso es el hallazgo, no un error de la corrida:** ese test va a
      fallar solo dentro de unas semanas, sin que nadie toque el código. Decide si lo arreglas
      ahora o lo anotas, pero no despliegues sin saber qué es.
- [ ] **Por qué el segundo comando:** la suite normal siempre corre con el reloj de hoy, así que
      de esta clase de fallo solo se entera el día que ya es tarde. El 2026-09-02 aparecieron 17
      tests en rojo de golpe, sin que nadie hubiera tocado nada, y costó una hora de auditoría
      averiguar que no era un bug sino tres fechas que habían caducado. Esta comprobación lo
      habría dicho semanas antes, en diez minutos y sin nada a medias por en medio.
- [ ] Contexto completo, cómo leer el resultado y la decisión pendiente de si esto debe ir al CI:
      **[MANUAL_TESTS_QUE_CADUCAN.md](./MANUAL_TESTS_QUE_CADUCAN.md)**.

### 0.5 Ensayo en local de los estáticos con `DEBUG=False`

Antes de subir nada, comprueba **en tu máquina** que el sitio se ve bien tal como lo servirá
producción. Es la única forma barata de descubrir un estático que falta: en el servidor el mismo
fallo se manifiesta como una página sin estilos y ya con la app publicada.

```bash
cd AppTurnosExplora
# 1) En .env, temporalmente:  DEBUG=False
python manage.py collectstatic --noinput   # genera staticfiles/
python manage.py runserver
```

- [ ] Recorre las pantallas principales (login, dashboard, Mis Turnos, los 6 formularios de
      solicitudes) y confirma que **se ven con estilos**.
- [ ] Abre la consola del navegador: **ningún 404** de CSS/JS y **ningún bloqueo de CSP**.
- [ ] Al terminar, **vuelve a dejar `DEBUG=True` en tu `.env`**.

> 🔴 **Por qué esta prueba existe.** Con `DEBUG=True`, `runserver` sirve `static/` él mismo. Al
> pasar a `False` eso se apaga y el relevo lo toma **WhiteNoise**, que sirve desde `STATIC_ROOT`
> (`staticfiles/`) — un directorio que **no existe hasta que corres `collectstatic`**. Si no está,
> todos los CSS y JS dan 404 y sale el HTML crudo. Le pasó a este proyecto en dev el 2026-09-07.

> ⚠️ **Dos trampas mientras dure el ensayo:**
> 1. **Los cambios en CSS/JS dejan de verse.** WhiteNoise sirve la copia congelada de
>    `staticfiles/`, no tu original: hay que volver a correr `collectstatic` tras cada edición.
>    Por eso este modo es una prueba puntual, nunca tu entorno de trabajo.
> 2. **Pierdes la página de error con el traceback.** Cualquier bug aparece como un
>    `Server Error (500)` mudo. Si algo se rompe durante el ensayo, vuelve a `DEBUG=True` para
>    diagnosticarlo.

> 📌 **CSP:** si alguna vez añades un recurso externo nuevo (un CDN, una fuente), tiene que estar
> en la allowlist CSP de `config/settings.py` o el navegador lo bloqueará **sin error visible en
> el servidor**. Este ensayo es el momento de detectarlo. Ver también la migración de CDN a
> estáticos locales en `static/`.

> 📌 **`staticfiles/` no entra al repo.** Es una copia generada que se rehace en cada despliegue.
> Ya está en `.gitignore` (`AppTurnosExplora/staticfiles/`), así que el `git add -A` con el que
> cierra esta Fase 0 no se lleva los cientos de archivos del ensayo. No quites esa línea.

**Al terminar la Fase 0:** `git add -A && git commit -m "prod: completar requirements + proxy SSL + CSRF origins" && git push`

---

## FASE 1 — Base de datos RDS

- [ ] **Crear RDS** (consola AWS → RDS → Create database):
  - Engine: **MySQL 8.0**
  - Template: **Free tier** (si aplica) o **Dev/Test**
  - Clase: **`db.t4g.micro`** · Single-AZ · Storage **20 GB gp3**
  - **Public access: No** (solo la EC2 la alcanza)
  - DB name inicial: `bdturnosex`
  - Usuario maestro: `admin` (o el que prefieras) + contraseña fuerte
- [ ] **Security Group de RDS:** permitir entrada **3306** SOLO desde el Security Group de la EC2 (no desde `0.0.0.0/0`).
- [ ] Anotar el **endpoint** (ej. `bdturnosex.xxxx.us-east-1.rds.amazonaws.com`) → será `DB_HOST`.

> ✅ RDS MySQL ya trae **pobladas las tablas de zona horaria**, así que el error de datetime del admin que vimos en local **no aparece aquí** (ver [[mysql-tz-tables-local-vs-rds]]).

---

## FASE 2 — Instancia EC2

- [ ] **Lanzar EC2:**
  - AMI: **Ubuntu Server 24.04 LTS (ARM64)** · Arquitectura **64-bit (Arm)**
    (24.04 tiene soporte hasta 2029; 22.04 se acaba en 2027. Trae **Python 3.12**,
    la misma versión que fija el CI)
  - ⚠️ **ARM64 no es opcional:** `t4g` es Graviton; una AMI x86 ni siquiera arranca
  - Tipo: **`t4g.micro`** ← decidido el 2026-09-04 por presupuesto
    ([arquitectura §5.1](./arquitectura-aws-rds-recomendada.md)). `t4g.small` es el escalón
    siguiente, necesario hacia los 1.000 usuarios; subir es 1 clic
  - Storage: 20 GB gp3 (**~$1,60/mes**, aparte de los 20 GB de RDS)
  - Key pair: crear/usar uno para SSH
- [ ] **Security Group de EC2:**
  - `22` (SSH) → **solo tu IP**
  - `80` (HTTP) → `0.0.0.0/0`
  - `443` (HTTPS) → `0.0.0.0/0`  ← esto es lo que la hace pública desde cualquier parte
- [ ] **Elastic IP:** asignar y asociar a la EC2 (IP pública fija).
      ⚠️ Se cobra ($3,65/mes) **aunque esté sin asociar**: no la reserves antes de necesitarla.
      Anótala: es lo que hay que darle a IT para el registro DNS (FASE 8).
- [ ] Confirmar que el SG de la **RDS** referencia al SG de esta EC2 en el 3306 (Fase 1).

- [ ] 🔴 **Poner la instancia en modo `standard` (control de costo, no opcional):**

      ```bash
      aws ec2 modify-instance-credit-specification \
          --instance-credit-specification "InstanceId=i-XXXX,CpuCredits=standard"
      ```

      Las clases T arrancan en modo **`unlimited`**, que **no frena la instancia al agotar los
      créditos de CPU: factura el excedente** por vCPU-hora. Con un techo de 150.000 COP/mes eso es
      un costo sin límite superior. En `standard` la instancia se limita en vez de cobrar.

- [ ] **Añadir 1-2 GB de swap.** Con 1 GB de RAM y 2-3 workers de Gunicorn el margen es estrecho;
      el swap evita que el OOM killer mate la app en un pico.

      ```bash
      sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
      sudo mkswap /swapfile && sudo swapon /swapfile
      echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
      ```

- [ ] **Alarma de costo:** crear un **AWS Budget con alerta a $30/mes**, y una alarma de CloudWatch
      sobre **`CPUSurplusCreditsCharged` > 0** de la RDS — en RDS el modo `unlimited` **no se puede
      desactivar**, así que esa métrica es el único aviso de que la BD empezó a cobrar excedente.

---

## FASE 3 — Preparar el servidor (por SSH)

```bash
ssh -i tu-clave.pem ubuntu@<ELASTIC_IP>

# Sistema
sudo apt update && sudo apt upgrade -y

# Python + Nginx + cliente MySQL (para pruebas). NO se necesita compilar
# mysqlclient: el proyecto usa PyMySQL (puro Python).
sudo apt install -y python3 python3-venv python3-pip nginx git mysql-client

# Usuario de la app
sudo useradd -m -s /bin/bash appuser
sudo su - appuser

# Código
git clone <URL_DEL_REPOSITORIO> appTurnos
cd appTurnos/AppTurnosExplora
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt      # ya incluye gunicorn tras Fase 0
```

- [ ] Probar conexión a RDS: `mysql -h <ENDPOINT_RDS> -u admin -p` (desde la EC2 debe conectar).

---

## FASE 4 — Variables de entorno de producción

Crear `/home/appuser/appTurnos/AppTurnosExplora/.env` (nombres **exactos** que lee `settings.py`):

```env
ENVIRONMENT=production
DEBUG=False
SECRET_KEY=<genera-una-clave-larga-y-unica>

ALLOWED_HOSTS=swalp.parqueexplora.org
CSRF_TRUSTED_ORIGINS=https://swalp.parqueexplora.org
CORS_ALLOWED_ORIGINS=https://swalp.parqueexplora.org
SITE_URL=https://swalp.parqueexplora.org

# Base de datos → RDS
DB_NAME=bdturnosex
DB_USER=admin
DB_PASSWORD=<password-del-maestro-rds>
DB_HOST=<ENDPOINT_RDS>
DB_PORT=3306

# TLS hacia RDS: cifra Y verifica la identidad del servidor.
# En EC2 (a diferencia del contenedor) hay que bajar el certificado a la máquina:
#   sudo mkdir -p /etc/ssl/rds && sudo curl -o /etc/ssl/rds/global-bundle.pem \
#     https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
DB_SSL_CA=/etc/ssl/rds/global-bundle.pem

# Caché — OBLIGATORIA, y para este presupuesto la opción es db://
#
# Gunicorn corre con varios workers y con LocMemCache cada uno tendría la suya.
# Como la caché guarda el estado de Mis Turnos (turnos_mes_<emp>_<año>_<mes>, 1 h)
# y se invalida al aprobar solicitudes, con varios procesos la invalidación solo
# limpiaría el worker que atendió esa petición: el explorador vería su turno
# corregido o sin corregir según a qué worker caiga, y al refrescar cambiaría.
#
# ⚠️ ElastiCache/Redis cuesta ~$12/mes y SE SALE DEL PRESUPUESTO (150.000 COP).
# La tabla en la propia RDS cuesta $0 y es suficiente a esta escala. Crearla una
# vez con: python manage.py createcachetable
#
# `manage.py check --deploy` FALLA con core.E001 si esto queda vacío en
# producción, así que el CI ya impide desplegar sin caché compartida.
CACHE_URL=db://cache_appturnos
#
# Redis queda DESCARTADO, no pendiente:
#   · ElastiCache          ~$12/mes → fuera de presupuesto.
#   · Redis en la propia EC2 → gratis en dinero, pero se come 200-400 MB del
#     único GB de RAM de la t4g.micro, compitiendo con los workers de Gunicorn.
#     Cambiar un problema de presupuesto por uno de memoria no es un arreglo.
# Se reconsidera solo si se pasa a >=2 instancias web (ver §3 de la arquitectura).

# Correo — Fase 1: SES por SMTP (solo variables, sin cambio de código)
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<SES_SMTP_USERNAME>
EMAIL_HOST_PASSWORD=<SES_SMTP_PASSWORD>
DEFAULT_FROM_EMAIL=SWALP <no-reply@parqueexplora.org>
```

> Generar `SECRET_KEY`: `python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`

> 📖 **Qué hace cada variable y qué se rompe si falta:** [CONFIGURACION_PRODUCCION.md](./CONFIGURACION_PRODUCCION.md).
> Antes de dar por terminado el despliegue, ejecuta `python manage.py check --deploy`:
> debe decir *"no issues"*. Si sale `core.E001`, falta `CACHE_URL` y los usuarios
> verán turnos desactualizados.
>
> En EC2, Nginx puede comprobar la salud de la app en **`/health/`** (responde sin
> tocar la base). `/health/ready/` sí consulta la base y sirve para verificar a mano.

---

## FASE 5 — Migraciones, estáticos y admin

```bash
cd /home/appuser/appTurnos/AppTurnosExplora
source venv/bin/activate

python manage.py migrate

# 🔴 OBLIGATORIO con CACHE_URL=db:// — crea la tabla que usa la caché.
# Sin esto la app arranca, pero PETA en la primera lectura o escritura de caché
# (que es cada carga de Mis Turnos): la tabla cache_appturnos no existe.
# `migrate` NO la crea: no sale de ninguna migración, es un comando aparte.
python manage.py createcachetable

python manage.py collectstatic --noinput     # genera staticfiles/ (los sirve Nginx)
# (el ensayo previo de este mismo paso en local es el 0.5 de la FASE 0)
python manage.py createsuperuser              # tu usuario admin
```

- [ ] `createcachetable` ejecutado (o la app fallará al cargar Mis Turnos).
- [ ] Comprobar que la tabla existe:
      `python manage.py shell -c "from django.core.cache import cache; cache.set('x',1); print(cache.get('x'))"`
      debe imprimir `1`. Si lanza `ProgrammingError`, falta el `createcachetable`.
- [ ] Prueba rápida: `python manage.py check --deploy` (revisa avisos de seguridad).

---

## FASE 6 — Gunicorn como servicio (systemd)

`sudo nano /etc/systemd/system/appturnosex.service`:

```ini
[Unit]
Description=Gunicorn AppTurnosExplora
After=network.target

[Service]
User=appuser
Group=www-data
WorkingDirectory=/home/appuser/appTurnos/AppTurnosExplora
EnvironmentFile=/home/appuser/appTurnos/AppTurnosExplora/.env
ExecStart=/home/appuser/appTurnos/AppTurnosExplora/venv/bin/gunicorn \
    --workers 4 \
    --bind unix:/home/appuser/appTurnos/AppTurnosExplora/gunicorn.sock \
    config.wsgi:application

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now appturnosex
sudo systemctl status appturnosex     # debe estar "active (running)"
```

---

## FASE 7 — Nginx (proxy inverso + estáticos)

`sudo nano /etc/nginx/sites-available/appturnosex`:

```nginx
server {
    listen 80;
    server_name swalp.parqueexplora.org;

    client_max_body_size 10M;

    location /static/ {
        alias /home/appuser/appTurnos/AppTurnosExplora/staticfiles/;
        expires 30d;
    }

    location / {
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;   # requerido por Fase 0.2
        proxy_pass http://unix:/home/appuser/appTurnos/AppTurnosExplora/gunicorn.sock;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/appturnosex /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo usermod -aG appuser www-data      # Nginx debe leer el socket/estáticos
sudo nginx -t && sudo systemctl restart nginx
```

- [ ] Probar por HTTP: `http://<ELASTIC_IP>` (con `ALLOWED_HOSTS` puede requerir el dominio; ver Fase 8/9).

---

## FASE 8 — DNS (lo agrega IT de Parque Explora)

- [ ] Pedir a IT un registro **A**: `swalp.parqueexplora.org` → `<ELASTIC_IP>`.
- [ ] Esperar propagación (`nslookup swalp.parqueexplora.org`).

---

## FASE 9 — HTTPS con Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d swalp.parqueexplora.org
# Elegir redirección HTTP→HTTPS cuando lo pregunte.
sudo systemctl status certbot.timer     # renovación automática
```

- [ ] Verificar: `https://swalp.parqueexplora.org` carga con candado y login.

---

## FASE 10 — Correo (Amazon SES)

> 🔴 **El sandbox de SES bloquea el proyecto entero.** Una cuenta nueva arranca con
> `Max24HourSend = 200` correos/día y **solo puede escribir a direcciones verificadas una a una**.
> El flujo real son **~180 correos/día** (30 solicitudes × ~6): entra en la cuota por los pelos, pero
> es inservible igual, porque los 300 empleados no están verificados. **Pídelo el primer día:**
> la aprobación suele tardar ~24 h. Ver [arquitectura §11.7](./arquitectura-aws-rds-recomendada.md).
>
> ```bash
> aws ses get-send-quota          # ver la cuota actual
> aws sesv2 put-account-details \
>     --production-access-enabled \
>     --mail-type TRANSACTIONAL \
>     --website-url https://swalp.parqueexplora.org \
>     --contact-language ES
> ```
>
> ⚠️ **El sandbox es por región:** salir en una no aplica a las demás. Pídelo en la **misma región
> del despliegue** (`us-east-1`).

**Fase 1 (ahora, sin cambio de código) — SES por SMTP:**
- [ ] **Solicitar la salida del sandbox** (comando de arriba) — hacerlo YA, tarda ~24 h.
- [ ] En SES: **verificar las dos identidades**, `parqueexplora.org` **y** `swalp.parqueexplora.org`, y activar **Easy DKIM** en ambas.
- [ ] Pedirle a IT los **3 CNAME de Easy DKIM** de cada identidad (seis en total). **NO se pide tocar el registro SPF** — ver el recuadro de abajo.
- [ ] Crear **credenciales SMTP de SES** → ponerlas en `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` (Fase 4). No son una access key de IAM.
- [ ] `EMAIL_HOST=email-smtp.us-east-1.amazonaws.com`, `EMAIL_PORT=587`. **`EMAIL_BACKEND` se deja sin definir**: si queda en `console`, los correos se escriben en el log y no los recibe nadie, sin ningún error.
- [ ] Prueba: enviar una solicitud real y revisar en *Mostrar original* que diga `DKIM: 'PASS' with domain <el dominio del From>` y `DMARC: 'PASS'`, y que no caiga en spam.

> 🟡 **No pidas a IT que ajuste el SPF, y no pidas MAIL FROM personalizado.**
> SES envía con su propio Return-Path (`@<región>.amazonses.com`), cuyo SPF publica Amazon y pasa.
> DMARC exige que **uno** de los dos mecanismos alinee y pase, y **Easy DKIM firma con el dominio
> del From**: alinea, y DMARC pasa. El SPF del ápice es del que depende **todo el correo
> corporativo de Workspace** — tocarlo tiene riesgo real, arrastra el límite de 10 consultas DNS
> y convierte un trámite de días en uno de semanas. Un CNAME nuevo, en cambio, no puede romper
> nada de lo que ya funciona. Razonado en el
> [ADR 016](../../03-arquitectura/adr/016-transporte-de-correo-y-fiabilidad.md).
>
> **Ojo con la comprobación:** que DKIM diga `PASS` no basta. Si el dominio de la firma no es el
> del `From`, **la alineación no existe** y DMARC falla igual. Es el paso que casi todo el mundo
> se salta.

> 🟡 **Alarmas de reputación — no son opcionales con SES.** AWS pone la cuenta bajo revisión con
> **rebotes > 5 %** o **quejas > 0,1 %**, y luego pausa el envío **de toda la aplicación**. Con 300
> empleados y rotación normal, **6 buzones muertos sobre 180 correos diarios ya son un 3,3 %**.
> Con Gmail eso rebotaba y punto; con SES puede apagar el flujo de aprobaciones entero. SES publica
> `Reputation.BounceRate` y `Reputation.ComplaintRate` en CloudWatch sin configurar nada: cuelga
> dos `AWS::CloudWatch::Alarm` del `AlertTopic` que ya existe en
> [`swalp-infra.yaml`](../../../infra/cloudformation/swalp-infra.yaml), con umbrales **por debajo**
> de los de AWS (0,02 y 0,0005) para que suenen mientras aún hay margen.

**Fase 2 (posterior, sin fecha) — SES por API + IAM role:** elimina el secreto de la ecuación; requiere `pip install django-ses boto3`, `EMAIL_BACKEND=django_ses.SESBackend` y un **IAM role** en la EC2. **No se hace en la misma ventana que el cambio de transporte**: dos variables a la vez en una primera salida a producción convierten cualquier fallo en un problema de diagnóstico. Y pierde urgencia porque **las credenciales SMTP de SES tampoco caducan**. Los ~20 s de latencia ya los resuelven el envío asíncrono y el lote sobre una conexión ([ADR 015](../../03-arquitectura/adr/015-entrega-de-correo-en-lote.md)); con backend HTTP, de hecho, ese lote deja de comprar nada. Ver [ADR 016](../../03-arquitectura/adr/016-transporte-de-correo-y-fiabilidad.md).

**Outbox de correos — ⚠️ paso obligatorio:**
- [ ] Programar el cron `procesar_email_outbox` (cada 5 min). **Sin él, un correo que falle queda guardado pero no se reintenta nunca.**
- [ ] Ver el paso a paso completo en **[MANUAL_OUTBOX_CORREOS.md](./MANUAL_OUTBOX_CORREOS.md)**.

**Sanciones por deuda de horas — ⚠️ paso obligatorio:**
- [ ] Programar el cron `revisar_sanciones_por_deuda` (una vez al día, de madrugada).
- [ ] **Sin él, la sanción de un moroso solo nace cuando esa misma persona abre la aplicación**, así que quien no entra no aparece bloqueado en ningún informe del supervisor.
- [ ] Correr antes `--dry-run` para ver a quién afectaría la primera ejecución (puede sancionar con fechas retroactivas).
- [ ] **Aviso de que el cron dejó de correr.** El comando emite `REVISION_SANCIONES_NO_EJECUTADA`
      en nivel `CRITICAL` cuando lleva días sin ejecutarse. Un cron que deja de dispararse no da
      ningún error —simplemente deja de ocurrir—, así que hay que vigilarlo desde fuera. Mismo
      patrón que el aviso del cierre semanal (FASE 11):
      ```bash
      # /etc/cron.daily/swalp-alerta-sanciones  (chmod +x)
      #!/bin/sh
      # Solo el final del log: una linea vieja puede ser de un problema ya resuelto.
      tail -n 200 /var/log/appturnos/sanciones_deuda.log \
        | grep -q "REVISION_SANCIONES_NO_EJECUTADA" \
        && echo "La revision de sanciones por deuda no se esta ejecutando. Revisar crontab -l." \
           | mail -s "SWALP: revision de sanciones caida" <tu-correo>
      ```
- [ ] Probado el aviso: fuerza la condición (renombra temporalmente la fila de hoy en
      `/admin/solicitudes/revisionsancionesdeuda/`, o espera 3 días) y comprueba que **llega el
      correo**. Un aviso sin probar no es un aviso.
- [ ] Paso a paso en **[MANUAL_SANCIONES_DEUDA.md](./MANUAL_SANCIONES_DEUDA.md)**.

**Comprobar que las dos tareas de arriba existen de verdad — ⚠️ paso obligatorio:**
```bash
cd /srv/swalp/AppTurnosExplora && source venv/bin/activate
python manage.py verificar_crons        # termina con codigo 1 si algo va mal
```
- [ ] Sale **`[ok]`** en las dos líneas.
- [ ] **Por qué hace falta si ya está el aviso de arriba:** ese aviso lo emite el propio
      comando de sanciones, así que solo puede sonar **cuando alguien lo ejecuta**. Contra el
      fallo que de verdad ocurre —que la línea del `crontab` nunca se llegó a añadir— un
      proceso no puede avisar de su propia ausencia. `verificar_crons` mira desde fuera lo que
      las dos tareas dejan en la base: la espera del correo pendiente más antiguo y el día de
      la última revisión. Antes, la única defensa contra "nadie programó el cron" era que una
      persona leyera esta lista.
- [ ] **Vuelve a lanzarlo 24 h después.** El día 1 la revisión de sanciones puede no haber
      corrido aún y el aviso de "NUNCA se ha ejecutado" es esperable; lo que no es normal es
      que siga saliendo al día siguiente.
- [ ] Recomendado: añadirlo al `crontab` una vez al día. Su código de salida 1 hace que cron
      envíe el correo de error automáticamente, sin montar nada más. El marcador para un
      `grep` propio es **`CRON_NO_EJECUTADO`**.

---

## FASE 11 — Verificación final

- [ ] `https://swalp.parqueexplora.org` accesible **desde fuera de la red** (celular con datos) → confirma acceso "desde cualquier parte".
- [ ] Login funciona; `django-axes` bloquea tras 5 intentos fallidos.
- [ ] Dashboard, crear solicitud, aceptar pendiente (emisor y receptor) → OK.
- [ ] Llega el correo de notificación desde `no-reply@parqueexplora.org`.
- [ ] Admin `/admin/` abre sin el error de zona horaria (RDS ya trae las tablas TZ).
- [ ] `curl -I http://swalp.parqueexplora.org` redirige a `https`.
- [ ] **Aviso del cierre semanal.** La comprobación del cierre falla **ABIERTA** a propósito: si se
      rompe, la solicitud se acepta sin validar y lo único que queda es un `CRITICAL` en el log
      (`solicitudes/services/solicitud_orchestrator.py:154-162`). Sin aviso, el cierre queda
      desactivado de hecho y nadie se entera. En una sola EC2, sin CloudWatch agent, basta un cron
      diario:
      ```bash
      # /etc/cron.daily/swalp-alerta-cierre  (chmod +x)
      #!/bin/sh
      journalctl -u appturnosex --since "24 hours ago" \
        | grep -q "CIERRE SEMANAL INOPERATIVO" \
        && echo "Cierre semanal inoperativo en las ultimas 24 h. Revisar journalctl -u appturnosex." \
           | mail -s "SWALP: cierre semanal caido" <tu-correo>
      ```
      Alternativa mejor si ya usas CloudWatch: instalar el agent sobre el journal de la unidad y
      crear el metric filter + alarma descritos en el
      [manual técnico § 13.6](../../manual_tecnico.md).
- [ ] Probado el aviso: fuerza una línea con ese texto en el journal y comprueba que llega el
      correo. **Un aviso sin probar no es un aviso.**
- [ ] **Revisión de sanciones: confirmar que corrió.** Al día siguiente del despliegue,
      `/admin/solicitudes/revisionsancionesdeuda/` debe tener **una fila con la fecha de ayer**.
      Si no la hay, el cron no está funcionando. El supervisor también lo verá como un banner
      rojo en el dashboard a los tres días.

---

## Anexo — Operación y actualizaciones

```bash
# Actualizar la app tras un push
sudo su - appuser
cd appTurnos/AppTurnosExplora && source venv/bin/activate
git pull origin main
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
exit
sudo systemctl restart appturnosex

# Logs
sudo journalctl -u appturnosex -f
sudo tail -f /var/log/nginx/error.log
```

**Backups:** RDS los hace automáticos (retención configurable). Nada manual que mantener.
**Escalado:** si la CPU de la EC2 se satura → cambiar el tipo de instancia a `t4g.medium` (Stop → Change instance type → Start). Si los créditos de CPU de RDS se agotan → subir a `db.t4g.small`.

---

## Resumen de bloqueos corregidos en Fase 0

| # | Problema detectado | Efecto si no se corrige |
|---|---|---|
| 0.1 | `requirements.txt` sin `django-axes` ni `django-cors-headers` | Django no arranca en el servidor |
| 0.2 | Falta `SECURE_PROXY_SSL_HEADER` tras Nginx | Bucle de redirección HTTPS infinito |
| 0.3 | Falta `CSRF_TRUSTED_ORIGINS` | Error 403 CSRF en login/formularios |
