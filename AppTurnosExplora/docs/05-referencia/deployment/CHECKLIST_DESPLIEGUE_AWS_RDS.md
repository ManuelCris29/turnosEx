# ✅ Checklist de despliegue — AppTurnos/SWALP en AWS (EC2 + RDS + SES)

**Fecha:** 2026-07-24
**Arquitectura:** ver [arquitectura-aws-rds-recomendada](./arquitectura-aws-rds-recomendada.md)
**Objetivo:** dejar la app **pública en internet** (acceso desde cualquier parte, con login) sobre:
`EC2 t4g.small (Nginx + Gunicorn) → RDS MySQL db.t4g.micro → Amazon SES`, HTTPS con Let's Encrypt.

> ⚠️ Este documento **reemplaza** al genérico [MANUAL_DESPLIEGUE_EC2.md](./MANUAL_DESPLIEGUE_EC2.md), que tiene nombres de variables `.env` desactualizados (`DJANGO_SECRET_KEY`, etc.) y asume `mysqlclient`. Este proyecto usa **PyMySQL** (no hay que compilar nada).

---

## FASE 0 — Ajustes de código previos (obligatorios, hacer ANTES de desplegar)

Sin estos tres puntos el despliegue **falla o entra en bucle de redirección**. Son cambios locales, se commitean y se despliegan con `git pull`.

### 0.1 Completar `requirements.txt` (faltan 2 paquetes instalados y en uso)
En `AppTurnosExplora/requirements.txt` **agregar**:
```
django-axes==7.0.1
django-cors-headers==4.9.0
gunicorn==23.0.0
```
> Sin `django-axes` y `django-cors-headers` Django no arranca (están en `INSTALLED_APPS`). `gunicorn` es el servidor de producción.

### 0.2 Evitar el bucle de redirección tras Nginx (TLS termina en Nginx)
En `config/settings.py`, dentro del bloque `if IS_PRODUCTION:` **agregar**:
```python
    # Nginx termina el TLS y reenvía por HTTP; sin esto, SECURE_SSL_REDIRECT
    # provoca un bucle de redirección infinito.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
```

### 0.3 Declarar `CSRF_TRUSTED_ORIGINS` (Django 5 lo exige para POST/AJAX por HTTPS)
En `config/settings.py`, cerca de `ALLOWED_HOSTS` **agregar**:
```python
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
```
> Sin esto, el login, el admin y los formularios AJAX dan error 403 CSRF en producción.

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
  - AMI: **Ubuntu Server 22.04 LTS (ARM64)** · Arquitectura **64-bit (Arm)**
  - Tipo: **`t4g.small`** (en pruebas puedes usar `t4g.micro`)
  - Storage: 20 GB gp3
  - Key pair: crear/usar uno para SSH
- [ ] **Security Group de EC2:**
  - `22` (SSH) → **solo tu IP**
  - `80` (HTTP) → `0.0.0.0/0`
  - `443` (HTTPS) → `0.0.0.0/0`  ← esto es lo que la hace pública desde cualquier parte
- [ ] **Elastic IP:** asignar y asociar a la EC2 (IP pública fija).
- [ ] Confirmar que el SG de la **RDS** referencia al SG de esta EC2 en el 3306 (Fase 1).

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

# Caché — OBLIGATORIA. Gunicorn corre con varios workers y con la caché en
# memoria cada uno tendría la suya: los exploradores verían turnos
# desactualizados de forma intermitente. Sin Redis, la tabla en RDS sirve
# (crearla una vez con: python manage.py createcachetable).
CACHE_URL=db://cache_appturnos
# CACHE_URL=redis://127.0.0.1:6379/1   # si instalas Redis en la propia EC2

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
python manage.py collectstatic --noinput     # genera staticfiles/ (los sirve Nginx)
python manage.py createsuperuser              # tu usuario admin
```

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

**Fase 1 (ahora, sin cambio de código) — SES por SMTP:**
- [ ] En SES: **verificar el dominio** `parqueexplora.org` (IT agrega los registros DKIM/SPF en DNS).
- [ ] **Solicitar acceso a producción** (salir del sandbox) para enviar a cualquier destinatario.
- [ ] Crear **credenciales SMTP de SES** → ponerlas en `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD` (Fase 4).
- [ ] Prueba: enviar una solicitud real y revisar cabeceras (`DKIM=pass`, `SPF=pass`) y que no caiga en spam.

**Fase 2 (posterior, mejora) — SES por API + IAM role:** elimina el secreto y baja la latencia; requiere `pip install django-ses boto3`, `EMAIL_BACKEND=django_ses.SESBackend` y un **IAM role** en la EC2. Ver el [plan de correo](./PLAN_CORREO_TRANSACCIONAL_Y_LATENCIA.docx). Junto con el envío **asíncrono** (outbox + hilo tras el commit) resuelve los ~20 s de latencia.

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
