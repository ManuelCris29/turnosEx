# 🐳 Manual: dockerizar SWALP y probarlo en local

**Fecha:** 2026-07-25
**Qué cubre:** cómo se dockerizó la app y cómo correrla en local de **dos formas** —
con una base efímera propia, o **contra tu MySQL local con tus datos reales**.

> Requisitos: **Docker Desktop** instalado y corriendo. Todo lo de este manual ya
> está en el repo (`AppTurnosExplora/Dockerfile`, `.dockerignore`, y los dos
> `docker-compose.*.yml`).

---

## 0. Guía rápida (probar con tus datos reales)

Credenciales del usuario de base de datos para el contenedor:
**usuario `swalp` · contraseña la que pongas en tu `.env` · acceso solo a `bdturnosex`**.

> La contraseña ya NO se escribe en el compose ni aquí: sale de `DB_PASSWORD` en tu
> `.env`, que está en `.gitignore`. Y el usuario se crea acotado a `172.%` (el rango
> del puente de Docker) en vez de `%`: con `%` podía conectarse desde cualquier
> máquina de la red, y la contraseña estaba versionada. Si no conecta, mira tu rango
> con `docker network inspect bridge`.

```sql
-- (1) UNA SOLA VEZ: crear el usuario en tu MySQL local (Workbench o cliente mysql)
CREATE USER 'swalp'@'172.%' IDENTIFIED BY 'LA-QUE-PONGAS-EN-.env';
GRANT ALL PRIVILEGES ON bdturnosex.* TO 'swalp'@'172.%';
FLUSH PRIVILEGES;
```

```bash
# (2) ENCENDER el contenedor contra tu MySQL real (desde AppTurnosExplora/)
cd AppTurnosExplora
docker compose -f docker-compose.hostdb.yml up --build -d

# (3) ABRIR en el navegador → entra con tus usuarios reales de siempre
#     http://localhost:8000

# (4) APAGAR (no borra nada de tu base real)
docker compose -f docker-compose.hostdb.yml down
```

```sql
-- (5) Cuando ya NO lo necesites: eliminar el usuario
DROP USER 'swalp'@'172.%';
```

> Detalle de cada paso, la opción con base de datos vacía y el troubleshooting,
> más abajo.

---

## 1. Cómo se dockerizó (qué hace cada pieza)

### 1.1 `Dockerfile`
Empaqueta la app en una imagen de producción:

```dockerfile
FROM python:3.12-slim                     # base ligera con Python 3.12
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1   # sin .pyc; logs sin buffer
WORKDIR /app

COPY requirements.txt .                    # 1) dependencias primero (mejor caché)
RUN pip install -r requirements.txt        #    PyMySQL es puro Python: sin compiladores

COPY . .                                   # 2) código de la app

RUN ... collectstatic --noinput            # 3) recolecta estáticos EN EL BUILD
EXPOSE 8000
CMD migrate && gunicorn config.wsgi ...    # 4) arranque: migra + servidor WSGI
```

Puntos clave:
- **PyMySQL (puro Python)** → no hace falta instalar libs de MySQL ni `gcc` en la imagen.
- **`collectstatic` en el build** con `ENVIRONMENT=production` (para no cargar
  `debug_toolbar`, que solo está en `requirements-dev.txt`). Las variables de ese
  paso son ficticias y viven solo en esa capa (no se hornean secretos).
- **Gunicorn** es el servidor WSGI de producción (reemplaza a `runserver`).

### 1.2 WhiteNoise (estáticos sin Nginx)
En una EC2 los estáticos los sirve Nginx; **dentro de un contenedor no hay Nginx**.
Por eso se añadió **WhiteNoise**:
- `whitenoise` en `requirements.txt`.
- `whitenoise.middleware.WhiteNoiseMiddleware` en `settings.py`, justo después de
  `SecurityMiddleware`.

Así el propio Gunicorn sirve los 143 MB de `staticfiles/` que generó `collectstatic`.

### 1.3 Toggle `SECURE_HTTPS`
La imagen corre en **modo producción**, que fuerza HTTPS (redirección + cookies
seguras). Eso impediría navegar en HTTP local. Se añadió en `settings.py`:

```python
SECURE_HTTPS = env.bool('SECURE_HTTPS', default=IS_PRODUCTION)
if SECURE_HTTPS:
    SECURE_SSL_REDIRECT = True
    ...
```

- En **producción** sigue activo (default = producción) → sin cambios.
- En **local** se pasa `SECURE_HTTPS=False` para poder abrir `http://localhost:8000`.

### 1.4 `.dockerignore`
Evita meter en la imagen lo que no debe: `.env` (¡secretos!), `venvturnos/`,
`staticfiles/` (se regenera), `docs/`, `.git/`, los `docker-compose*.yml`, etc.

---

## 2. Opción A — Prueba autocontenida (base efímera propia)

No toca tu MySQL: levanta la app **+ su propia MySQL** vacía. Ideal para verificar
que la imagen funciona.

Archivo: **`docker-compose.local.yml`**.

> ### ⚠️ Aquí NO puedes entrar con tu usuario de siempre
>
> Esta base **está vacía: tiene cero usuarios**. Tu `manuel.moreno` vive en tu
> MySQL local (puerto 3306), y este contenedor levanta **otra** MySQL distinta
> (puerto 3307) que ni la ve.
>
> Si lo intentas, el mensaje será **«usuario o contraseña incorrectos»** — y es
> engañoso: la contraseña está bien, el usuario simplemente no existe ahí. Por eso
> el paso «crear un superusuario» de abajo **no es opcional**.
>
> 🚨 **Y ojo con insistir:** `django-axes` bloquea por **5 intentos fallidos**
> durante **una hora**. Si pruebas varias veces, acabarás bloqueado y seguirás
> viendo el mismo mensaje aunque ya hayas creado el usuario. Se arregla con
> `docker compose -f docker-compose.local.yml exec web python manage.py axes_reset`.
>
> ¿Quieres entrar con tus usuarios reales? Ese es el caso de la **Opción B** (§3).

```bash
cd AppTurnosExplora

# Levantar (build + app + mysql)
docker compose -f docker-compose.local.yml up --build -d

# (Primera vez) cargar zonas horarias en esa MySQL (para que el admin no falle)
docker compose -f docker-compose.local.yml exec -T db \
  sh -c "mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -uroot -plocalpw mysql"

# (Primera vez) crear un superusuario para entrar
docker compose -f docker-compose.local.yml exec -T \
  -e DJANGO_SUPERUSER_USERNAME=admin -e DJANGO_SUPERUSER_PASSWORD=admin12345 \
  -e DJANGO_SUPERUSER_EMAIL=admin@test.local \
  web python manage.py createsuperuser --noinput

# Abrir http://localhost:8000  (admin / admin12345)

# Apagar y BORRAR la base efímera
docker compose -f docker-compose.local.yml down -v
```

- La base es **nueva y vacía** (las migraciones crean el esquema; no hay datos).
- Su MySQL se publica en el host en el puerto **3307** para no chocar con tu MySQL (3306).

---

## 3. Opción B — Contra tu MySQL REAL (tus datos)

Levanta **solo el contenedor web** y lo conecta a tu MySQL local (`bdturnosex`).
**No corre migraciones** (para no modificar tu base real).

Archivo: **`docker-compose.hostdb.yml`**.

### 3.1 Requisito único: un usuario MySQL que acepte al contenedor
Tu `root` es `root@localhost` y **no acepta** conexiones desde el contenedor (que
llega por la red de Docker, no por `localhost`). Se crea un usuario dedicado **una
sola vez** (en tu MySQL local, con Workbench o el cliente `mysql`):

```sql
CREATE USER 'swalp'@'172.%' IDENTIFIED BY 'LA-QUE-PONGAS-EN-.env';
GRANT ALL PRIVILEGES ON bdturnosex.* TO 'swalp'@'172.%';
FLUSH PRIVILEGES;
```

> **Por qué `@'%'`:** permite la conexión desde la IP de la red de Docker. En una
> estación de trabajo (con el 3306 no expuesto a internet) es aceptable para
> desarrollo. Para restringir más, usa el rango de Docker en vez de `%`. Para
> quitarlo cuando termines: `DROP USER 'swalp'@'172.%';`.

También tu MySQL debe **escuchar en todas las interfaces** (`bind_address = *`, que
es el caso). Compruébalo con `SELECT @@bind_address;`.

### 3.2 Levantar
```bash
cd AppTurnosExplora

docker compose -f docker-compose.hostdb.yml up --build -d

# Abrir http://localhost:8000  → entra con TUS usuarios reales de siempre

# Apagar (no borra nada de tu base)
docker compose -f docker-compose.hostdb.yml down
```

**Cómo se conecta al host:** dentro del contenedor, `host.docker.internal` apunta a
tu máquina; por eso `DB_HOST=host.docker.internal` alcanza tu MySQL local en 3306.
El compose incluye `extra_hosts: "host.docker.internal:host-gateway"` por
compatibilidad.

### 3.3 Verificar que lee tus datos reales
```bash
docker compose -f docker-compose.hostdb.yml exec -T web \
  python manage.py shell -c "from solicitudes.models import SolicitudCambio; print(SolicitudCambio.objects.count())"
# → debe mostrar tu número real de solicitudes (p. ej. 341)
```

---

## 4. Comandos útiles (ambas opciones)

```bash
# Ver logs en vivo
docker compose -f docker-compose.hostdb.yml logs -f web

# Reconstruir tras cambiar código
docker compose -f docker-compose.hostdb.yml up --build -d

# Estado de contenedores
docker compose -f docker-compose.hostdb.yml ps

# Entrar a una shell dentro del contenedor
docker compose -f docker-compose.hostdb.yml exec web sh
```

---

## 5. Problemas típicos

| Síntoma | Causa / solución |
|---|---|
| `Access denied for user 'swalp'` | El usuario/clave no coincide, o falta el `GRANT`. Repite la Fase 3.1. |
| `Host '172.x.x.x' is not allowed to connect` | El usuario no es `@'%'` (o el rango correcto). Créalo como en 3.1. |
| `Can't connect to MySQL ... host.docker.internal` | Tu MySQL no escucha en todas las interfaces (`bind_address`) o un firewall bloquea el 3306. |
| El navegador redirige a `https://localhost` y no carga | Falta `SECURE_HTTPS=False` (ya está en los compose de local). |
| `Port 8000 already in use` | Ya hay un stack arriba. Bájalo con `down` antes de levantar el otro. |
| Admin: error de zona horaria | Solo en la opción A recién creada: carga las tablas TZ (ver §2). Tu MySQL real ya las tiene. *(Nota: la imagen `mysql:8.0` suele traerlas pobladas; comprueba antes con `SELECT COUNT(*) FROM mysql.time_zone_name;` — si devuelve ~1795, no hace falta.)* |
| **«Usuario o contraseña incorrectos» con mi usuario real** | **Opción A: esa base está vacía, tu usuario no existe ahí.** Crea el superusuario (§2) o usa la Opción B contra tu MySQL real. |
| Sigue sin dejarme entrar aunque el usuario exista | `django-axes` te bloqueó (5 fallos → 1 hora). Ejecuta `docker compose -f docker-compose.local.yml exec web python manage.py axes_reset`. |
| `/health/` da 404 | Imagen antigua. Reconstruye con `--build`. |

---

## 6. Relación con el despliegue en AWS

La **misma imagen** que probaste en local es la que se despliega en **ECS Fargate**
(el checklist de Fargate se borró al descartarse esa variante; ver
[arquitectura §7.1](./arquitectura-aws-rds-recomendada.md) para el papel que conserva Docker). La única
diferencia es de dónde salen las variables de entorno (aquí del compose; en AWS del
task definition + Secrets Manager) y que en producción `SECURE_HTTPS` queda activo
detrás del ALB. Dockerizar bien en local = casi todo el camino a Fargate hecho.
