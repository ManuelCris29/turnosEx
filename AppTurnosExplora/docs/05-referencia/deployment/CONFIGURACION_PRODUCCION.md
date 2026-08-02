# ⚙️ Configuración de producción — variables, trampas y verificación

**Última revisión:** 2026-08-02
**Ámbito:** qué tiene que valer cada variable de entorno al desplegar, **qué se rompe si no**, y cómo comprobarlo **antes** de que lo descubran los usuarios.

> Este documento explica el **porqué**. Los pasos de infraestructura están en los checklists:
> [ECS Fargate](./CHECKLIST_DESPLIEGUE_FARGATE.md) · [EC2 + RDS](./CHECKLIST_DESPLIEGUE_AWS_RDS.md).
> Si solo quieres la receta, ve allí; si algo falla y no entiendes por qué, vuelve aquí.

---

## 1. Idea que evita el 90% de los líos

**Todo se configura con variables de entorno. No se edita código para desplegar.**

`settings.py` está escrito para que el valor por defecto sea el correcto en cada
entorno: en desarrollo se comporta como siempre sin que configures nada, y en
producción (`ENVIRONMENT=production`) sube solo la seguridad, las conexiones
persistentes y la exigencia de HTTPS.

Consecuencia práctica: **si algo va mal en AWS, el problema está en una variable,
no en el código.** Empieza siempre por listar las variables del contenedor.

---

## 2. Variables — tabla completa

### 2.1 Obligatorias (la app no arranca sin ellas)

| Variable | Valor en producción | Si falta o está mal |
|---|---|---|
| `ENVIRONMENT` | `production` | Con otro valor se carga `debug_toolbar` (que **no está** en la imagen) y no se activan HTTPS, HSTS ni cookies seguras. |
| `SECRET_KEY` | Cadena larga y única (≥50 caracteres) | Se invalidan firmas de sesión y CSRF. **Nunca** reutilices la de desarrollo. |
| `DEBUG` | `False` | Con `True` expones trazas completas con configuración y consultas SQL a cualquiera que provoque un error. |
| `ALLOWED_HOSTS` | `swalp.parqueexplora.org` | **400 Bad Request** en todas las peticiones. Ver la trampa nº 3. |
| `DB_NAME` `DB_USER` `DB_PASSWORD` `DB_HOST` `DB_PORT` | Datos de RDS | No arranca. `DB_HOST` es el *endpoint* de RDS, no una IP. |
| `EMAIL_HOST_USER` `EMAIL_HOST_PASSWORD` `DEFAULT_FROM_EMAIL` | Según SES | No arranca (se leen sin valor por defecto). |

### 2.2 Críticas para que funcione BIEN (arranca sin ellas, pero con fallos)

Estas son las peligrosas: **la aplicación levanta igual y parece sana**, y el
problema aparece después, en forma de datos incorrectos o caídas intermitentes.

| Variable | Valor en producción | Si falta |
|---|---|---|
| `CACHE_URL` | `redis://<endpoint>:6379/1` o `db://cache_appturnos` | 🔴 **Trampa nº 1.** Los usuarios ven turnos desactualizados. `check --deploy` lo bloquea (`core.E001`). |
| `CSRF_TRUSTED_ORIGINS` | `https://swalp.parqueexplora.org` | Todos los formularios y llamadas AJAX fallan con **403 CSRF** tras el ALB. |
| `SITE_URL` | `https://swalp.parqueexplora.org` | Los enlaces de los correos apuntan a `127.0.0.1:8000` y no sirven a nadie. |
| `DB_SSL_CA` | `/app/certs/rds-ca-global.pem` | Credenciales y datos personales viajan **sin cifrar** por la VPC. Avisa `core.W002`. |

### 2.3 Opcionales (el valor por defecto ya es correcto)

| Variable | Por defecto | Cuándo tocarla |
|---|---|---|
| `DB_CONN_MAX_AGE` | `60` en producción, `0` en desarrollo | Casi nunca. Bájalo si RDS se queda sin conexiones. |
| `SECURE_HTTPS` | `True` en producción | Solo `False` para probar la imagen de producción en HTTP local. **Nunca en AWS.** |
| `EMAIL_SEND_ASYNC` | `True` en producción | Solo para depurar el envío de correo. |
| `CORS_ALLOWED_ORIGINS` | localhost | Ponle el dominio real si algo externo consume la API. |

---

## 3. Las cuatro trampas

Estas son las que cuestan una tarde entera si no las conoces de antemano. Las
tres primeras ya están resueltas en el código; la cuarta es una **decisión
pendiente** que solo puedes tomar al desplegar.

### 🔴 Trampa 1 — La caché en memoria sirve datos viejos

**Síntoma:** un supervisor aprueba una solicitud o levanta una sanción, y el
explorador sigue viendo su turno anterior. Refresca y a veces aparece bien, a
veces mal. Es intermitente e imposible de reproducir a mano.

**Causa:** `LocMemCache` vive en la memoria de **un** proceso. Gunicorn arranca
con `--workers 3`, así que hay tres cachés que no se ven entre sí. La app cachea
el estado de Mis Turnos durante **una hora**
(`turnos/api/views/turnos_mes.py` → clave `turnos_mes_<emp>_<año>_<mes>`) y lo
invalida cuando cambia (`CacheService.invalidar_cache_turnos_empleado`). Con
varios procesos, esa invalidación **solo limpia el worker que atendió la
petición**; los otros dos siguen sirviendo el mes viejo. Con varias tareas ECS,
peor todavía.

**Solución:** define `CACHE_URL`. Dos caminos válidos:

| Opción | `CACHE_URL` | Coste | Requisito extra |
|---|---|---|---|
| **ElastiCache Redis** (recomendada) | `redis://<endpoint>:6379/1` | ~$12/mes | Crear el clúster y abrir el puerto 6379 desde el SG de los tasks |
| **Tabla en RDS** (sin infra nueva) | `db://cache_appturnos` | $0 | Ejecutar **una vez**: `python manage.py createcachetable` |

> Si el presupuesto manda, `db://` es perfectamente aceptable para este volumen
> (~300 usuarios). Lo inaceptable es dejarlo sin configurar.

**Red de seguridad:** `manage.py check --deploy` **falla** con `core.E001` si
detecta caché local en producción. El CI lo ejecuta en cada push.

---

### 🔴 Trampa 2 — El ALB mata las tareas en bucle (redirección HTTPS)

**Síntoma:** el target group nunca pasa a *healthy*. ECS arranca una tarea, el
ALB la marca como muerta, la mata, arranca otra… indefinidamente. La aplicación
nunca llega a estar disponible y los logs no muestran ningún error.

**Causa:** los health checks del ALB **no son tráfico de navegador**: llegan por
HTTP directo al contenedor y **sin** la cabecera `X-Forwarded-Proto`. Con
`SECURE_SSL_REDIRECT=True`, Django les responde **301 hacia https**. El ALB
espera 200 y lee el 301 como fallo.

**Solución (ya aplicada):** `SECURE_REDIRECT_EXEMPT` exime a las rutas de salud.
Comprobado en el contenedor real:

```
/health/         -> HTTP 200   (sin redirección)
/health/ready/   -> HTTP 200   (sin redirección)
/                -> HTTP 301   Location: https://...
```

**Lo que debes hacer al desplegar:** apuntar el health check del target group a
**`/health/`**, no a `/`. Ver §4.

---

### 🔴 Trampa 3 — `ALLOWED_HOSTS` rechaza al propio ALB *(decisión pendiente)*

⚠️ **Esta es la única pieza que queda por decidir. No está resuelta en el código.**

**Síntoma:** igual que la trampa 2 —el target group no pasa a *healthy*— pero por
otra causa. En los logs verás `DisallowedHost` y **400**.

**Causa:** el ALB envía sus health checks usando la **IP privada de la tarea**
como cabecera `Host` (por ejemplo `10.0.1.23`). Esa IP cambia en cada despliegue
y obviamente no está en `ALLOWED_HOSTS`, así que Django rechaza la petición antes
de que llegue a la vista de salud.

**Opciones (elige una al desplegar):**

| Opción | Cómo | Valoración |
|---|---|---|
| **A. Añadir la IP de la tarea al arrancar** | Leer `ECS_CONTAINER_METADATA_URI_V4` en `settings.py` y añadir la IP a `ALLOWED_HOSTS` | La más correcta. Requiere ~10 líneas de código. |
| **B. `ALLOWED_HOSTS=*`** | Variable de entorno | Aceptable **solo** si el ALB es la única entrada al contenedor (SG del task que únicamente admite al SG del ALB, como indica el checklist). La protección real pasa a ser la red. |
| **C. Health check por TCP** | Configurar el target group en modo TCP | Deja de comprobar que la app responde; solo que el puerto está abierto. **No recomendada.** |

**Recomendación:** empieza con **B** (el SG ya te protege y desbloquea el
despliegue), y pasa a **A** cuando tengas el sistema estable. Si eliges A,
avísame y lo implemento con sus tests.

---

### 🟡 Trampa 4 — Conexiones persistentes que ya murieron

**Síntoma:** errores 500 intermitentes con fallos de conexión a la base, sobre
todo tras periodos de poca actividad o después de un failover de RDS.

**Causa:** `CONN_MAX_AGE=60` reutiliza la conexión durante un minuto, pero esa
conexión puede haber muerto por su cuenta (timeout de MySQL, failover, reinicio).
Sin comprobarla, Django la usaría igualmente y la petición revienta.

**Solución (ya aplicada):** `CONN_HEALTH_CHECKS = True` acompaña siempre a
`CONN_MAX_AGE`. Django comprueba la conexión y la reabre si hace falta.

> ⚠️ **Nunca actives `CONN_MAX_AGE` sin `CONN_HEALTH_CHECKS`.** Cambiarías un
> coste de rendimiento por errores intermitentes, que es mucho peor. Hay un test
> que fija esta relación (`core/tests/test_config_base_datos.py`).

---

## 4. Endpoints de salud

La aplicación expone **dos**, y usar el que no toca tiene consecuencias:

| Ruta | Qué comprueba | Uso |
|---|---|---|
| `/health/` | Que el proceso responde. **No toca la base.** | ✅ **El health check del ALB va aquí** |
| `/health/ready/` | Además, que alcanza la base (503 si no) | Verificar despliegues a mano o desde un script |

**Por qué el ALB no debe usar `/health/ready/`:** si el health check consultara
RDS y la base tuviera un problema de 30 segundos, el ALB daría por muertas
**todas** las tareas y las reemplazaría. Las nuevas encontrarían la misma base
enferma y el ciclo se repetiría. Convertirías un incidente recuperable de base de
datos en **una caída total de la aplicación**.

Configuración del target group:

```
Health check path:      /health/
Success codes:          200
Interval:               30 s
Healthy threshold:      2
Unhealthy threshold:    3
```

---

## 5. Verificación antes de desplegar

### 5.1 El guardián automático

```bash
python manage.py check --deploy
```

Además de las comprobaciones de Django, ejecuta las propias del proyecto
(`core/checks.py`):

| Código | Nivel | Significa |
|---|---|---|
| `core.E001` | 🔴 **Error** (falla) | Caché local en producción → trampa nº 1 |
| `core.W002` | 🟡 Aviso | Sin TLS hacia la base |

Con la configuración de producción completa debe salir:
`System check identified no issues`.

> El CI lo ejecuta en cada push con una configuración de producción simulada, así
> que un despliegue con la caché mal configurada **no llega a `main` en silencio**.

### 5.2 Prueba manual de la imagen (recomendado antes de subir a ECR)

```bash
cd AppTurnosExplora
docker compose -f docker-compose.local.yml up --build -d

# Endpoints de salud
curl -s http://localhost:8000/health/          # {"status": "ok"}
curl -s http://localhost:8000/health/ready/    # {"status": "ok", "database": "ok"}

# El certificado de RDS está en la imagen (debe dar 108 certificados)
docker compose -f docker-compose.local.yml exec web \
  grep -c "BEGIN CERTIFICATE" /app/certs/rds-ca-global.pem

# Apagar y borrar la base efímera
docker compose -f docker-compose.local.yml down -v
```

> ℹ️ Esa base es **efímera y vacía**: no tiene usuarios. Si quieres entrar,
> necesitas crear uno — ver [MANUAL_DOCKER_LOCAL.md](./MANUAL_DOCKER_LOCAL.md) §5.

### 5.3 Después de desplegar

```bash
# Los endpoints responden a través del ALB
curl -s https://swalp.parqueexplora.org/health/

# Configuración efectiva dentro de la tarea (ECS Exec)
aws ecs execute-command --cluster swalp-cluster --task <task-id> \
  --container web --interactive --command "python manage.py check --deploy"
```

---

## 6. Resumen para el día del despliegue

Bloque de variables listo para copiar al *task definition* (los valores entre
`<>` son tuyos):

```bash
# --- Obligatorias ---
ENVIRONMENT=production
DEBUG=False
SECRET_KEY=<desde Secrets Manager>
ALLOWED_HOSTS=swalp.parqueexplora.org        # ver trampa nº 3
CSRF_TRUSTED_ORIGINS=https://swalp.parqueexplora.org
SITE_URL=https://swalp.parqueexplora.org
CORS_ALLOWED_ORIGINS=https://swalp.parqueexplora.org

# --- Base de datos ---
DB_NAME=bdturnosex
DB_USER=admin
DB_PASSWORD=<desde Secrets Manager>
DB_HOST=<endpoint-rds>
DB_PORT=3306
DB_SSL_CA=/app/certs/rds-ca-global.pem       # TLS verificado

# --- Caché: OBLIGATORIA, elige una ---
CACHE_URL=redis://<endpoint-elasticache>:6379/1
# CACHE_URL=db://cache_appturnos             # alternativa sin infra nueva

# --- Correo ---
EMAIL_HOST_USER=<...>
EMAIL_HOST_PASSWORD=<desde Secrets Manager>
DEFAULT_FROM_EMAIL=SWALP <no-reply@parqueexplora.org>
```

**Las tres cosas que no puedes olvidar:**

1. `CACHE_URL` definida (si no, los usuarios verán turnos incorrectos).
2. Health check del ALB apuntando a **`/health/`** (si no, no arranca nunca).
3. Decidir la trampa nº 3 (`ALLOWED_HOSTS` frente al ALB).

---

## 7. Dónde está cada cosa en el código

| Qué | Archivo |
|---|---|
| Toda la configuración por entorno | `config/settings.py` |
| Endpoints de salud | `core/health.py` |
| Rutas de salud | `config/urls.py` |
| Comprobaciones de despliegue | `core/checks.py` |
| Certificado de RDS en la imagen | `Dockerfile` |
| Plantilla de variables | `.env.example` |
| Tests de esta configuración | `core/tests/` |

---

## 8. Pendiente (no bloquea el despliegue)

- **Sentry** — ahora mismo un error 500 solo deja rastro en CloudWatch, entre el
  resto de logs. Requiere cuenta y `SENTRY_DSN`.
- **Secretos en SSM / Secrets Manager** — la app ya lee todo de variables de
  entorno, así que es puro trabajo de infraestructura en el *task definition*.
- **Promover la CSP a estricta** — la política objetivo ya está en observación en
  `settings.py` (`CONTENT_SECURITY_POLICY_REPORT_ONLY`); falta confirmar que no
  reporta violaciones y moverla.
- **Alinear PyMySQL** — `requirements.txt` fija `1.1.2` y el entorno local tiene
  `1.4.6`: se desarrolla contra una versión distinta de la que se despliega.
