# ✅ Checklist de despliegue — AppTurnos/SWALP en Dokploy

**Fecha:** 2026-09-09
**Objetivo:** dejar la aplicación **pública en internet** en `https://swalp.parqueexplora.org`, sobre el servidor de Dokploy de Parque Explora.

> Este documento **sustituye** a [CHECKLIST_DESPLIEGUE_AWS_RDS.md](../99-aws/CHECKLIST_DESPLIEGUE_AWS_RDS.md) como plan de despliegue vigente. Aquel **no se borra**: sigue siendo el registro de por qué cada invariante existe, y varias de sus fases se heredan palabra por palabra.

---

## Qué cambia respecto al plan de AWS

Dokploy borra media lista: no hay factura variable, ni sandbox de SES, ni Elastic IP, ni
alarmas de presupuesto, ni CloudFormation. Pero **traslada a nosotros tres cosas que AWS
regalaba, y las tres fallan en silencio**:

| | AWS lo daba hecho | Aquí |
|---|---|---|
| **Backups** | RDS: automáticos, 7 días, cifrados, snapshot al borrar | **FASE 10** — hay que montarlos y **probar la restauración** |
| **Zonas horarias de MySQL** | RDS trae las tablas pobladas | **FASE 2** — la imagen oficial NO. Sin ellas el admin revienta |
| **Alarmas de los marcadores** | CloudWatch con metric filters | **FASE 11** — Dokploy **no notifica cuando un Schedule falla** |

| Pieza | AWS | Dokploy |
|---|---|---|
| Servidor | EC2 `t4g.micro` + Nginx + systemd | Application, con el `Dockerfile` del repo |
| TLS | certbot | Traefik + Let's Encrypt, en un formulario |
| Base | RDS MySQL 8.4 | Servicio MySQL de Dokploy + volumen |
| Caché | `db://cache_appturnos` (ElastiCache costaba $12/mes) | **Redis**, que autohospedado cuesta 0 |
| Correo | Amazon SES por SMTP | **Google Workspace** ([manual](../02-correo/MANUAL_CORREO_GOOGLE_WORKSPACE.md)) |
| Crons | `crontab` / EventBridge | **Schedules**, con `timezone` propio |
| Despliegue | `deploy.yml` por SSH (nunca escrito) | `.github/workflows/deploy.yml` → API de Dokploy |

---

## FASE 0 — Antes de tocar nada

### 0.1 La suite, y también con el reloj adelantado

```bash
cd AppTurnosExplora
pytest -n 4                          # debe estar en verde
pytest -n 4 --dias-en-el-futuro=45   # ¿algo se pondrá rojo solo dentro de mes y medio?
```

- [ ] Las dos corridas salen en verde.
- [ ] **Si la segunda sale roja, eso es el hallazgo, no un error de la corrida.** Contexto
      en [MANUAL_TESTS_QUE_CADUCAN.md](../03-operacion/MANUAL_TESTS_QUE_CADUCAN.md).

### 0.2 Ensayo local de los estáticos con `DEBUG=False`

Se hereda íntegra la FASE 0.5 del checklist de AWS y sigue siendo válida palabra por
palabra: es la única forma barata de descubrir un estático que falta antes de que la
página salga sin estilos ya publicada.

```bash
# 1) En .env, temporalmente:  DEBUG=False
python manage.py collectstatic --noinput
python manage.py runserver
```

- [ ] Login, dashboard, Mis Turnos y los 6 formularios **se ven con estilos**.
- [ ] Consola del navegador: **ningún 404** de CSS/JS y **ningún bloqueo de CSP**.
- [ ] Volver a dejar `DEBUG=True`.

### 0.3 Generar la `SECRET_KEY`

```bash
python -c "import secrets; print(secrets.token_hex(50))"
```

- [ ] Guardada donde no dependa de una persona.

> Se usa `token_hex` y no el `get_random_secret_key()` de Django a propósito: aquel puede
> incluir `$`, `%` y `(`, y ese mismo valor acaba pegado en ficheros compose y en shells
> donde `$` sí muerde. Hexadecimal no da problemas en ningún sitio.

> ⚠️ **Firma los enlaces de aprobación de los correos.** Rotarla invalida todos los
> enlaces ya enviados (viven hasta 30 días). No se cambia por rutina.

---

## FASE 1 — Reconocimiento del servidor

Dokploy **ya está instalado** y con otras aplicaciones desplegadas. Esta fase sustituye a
la instalación, y no es trámite: el servidor es **compartido**, así que lo que hagamos mal
se lo lleva puesto a las demás aplicaciones.

### 1.1 Qué se puede reutilizar

Antes de crear nada, mirar en el panel:

- [ ] **Settings → S3 Destinations** — ¿ya hay un destino para los backups de las otras
      apps? Si lo hay, **la FASE 10 se resuelve en cinco minutos** con un `prefix` propio.
- [ ] **Settings → Notifications** — ¿ya hay un canal (correo, Slack, Teams)? Añadirse a
      él en vez de montar otro.
- [ ] **Git Sources** — ¿ya hay una GitHub App instalada? Entonces basta con darle acceso
      al repositorio nuevo.
- [ ] **Registry** — ¿hay un registro de Docker? Decide si el rollback será rápido o por
      reconstrucción (ver FASE 12.4).

### 1.2 Recursos

- [ ] **Disco libre.** El build hace `pip install` + `collectstatic` de **143 MB** de
      estáticos, y las imágenes viejas se acumulan. Quedarse sin disco **tumba también a
      las otras aplicaciones**.
- [ ] **Docker Cleanup activado** en Dokploy.
- [ ] **RAM libre** suficiente para MySQL (~400 MB–1 GB) + Redis (~100 MB) + 3 workers de
      gunicorn (~450 MB).

### 1.3 La pregunta para IT que conviene hacer hoy

- [ ] **¿Qué hay por debajo del Windows Server: una VM Linux o WSL2?**

      No cambia nada de este plan —Dokploy corre y eso significa que hay un Linux
      debajo—, pero sí cambia el riesgo operativo: **sobre WSL2, Docker no arranca solo
      tras reiniciar el Windows** y la IP interna cambia. Es información que hay que tener
      **antes** del día en que reinicien el servidor, no después.

---

## FASE 2 — MySQL

### 2.1 Crear el servicio

- [ ] *Databases → Create → MySQL*, versión **8.4**.
- [ ] Base `bdturnosex`, charset `utf8mb4`.
- [ ] Anotar de *Internal Credentials*: **host interno**, usuario y contraseña. El host es
      un nombre de la red overlay — **no** una IP y **no** `localhost`.

> **Por qué 8.4 y no 8.0:** el soporte comunitario de MySQL 8.0 terminó en abril de 2026.
> El CI todavía usa 8.0; subirlo queda como tarea de seguimiento, porque toca `ci.yml`.

### 2.2 🔴 Cargar las tablas de zona horaria — PASO OBLIGATORIO

**Este es el paso que RDS hacía por nosotros y que aquí no hace nadie.**

`TIME_ZONE='America/Bogota'` con `USE_TZ=True` hace que Django resuelva los filtros por
fecha con `CONVERT_TZ`, y `CONVERT_TZ` con **nombres** de zona necesita las tablas
`mysql.time_zone*` pobladas. **La imagen oficial de MySQL no las trae.** Sin ellas
`CONVERT_TZ` devuelve `NULL` y **el admin de Django revienta al filtrar por fecha** — el
mismo error que ya apareció en el MySQL local durante el desarrollo.

- [ ] Crear un Schedule de tipo **Dokploy Server**, pegar
      [`infra/dokploy/cargar-zonas-horarias.sh`](../../../../infra/dokploy/cargar-zonas-horarias.sh),
      definir `CONTENEDOR_MYSQL` y **ejecutarlo a mano una vez**. No se programa: no es un
      cron.

- [ ] **Verificar.** El script lo hace solo, pero conviene verlo:

      ```sql
      SELECT COUNT(*) FROM mysql.time_zone_name;        -- ≈ 1795, nunca 0
      SELECT CONVERT_TZ(NOW(),'UTC','America/Bogota');  -- una fecha, nunca NULL
      ```

> 📌 **Basta una vez**, porque esas tablas viven en el esquema `mysql`, dentro del
> directorio de datos: **persisten en el volumen**. Solo hay que repetirlo si se recrea el
> volumen desde cero — **incluido el caso de levantar la base desde un backup**, porque el
> dump trae `bdturnosex`, no el esquema `mysql`. Está anotado en el guion de la FASE 10.

---

## FASE 3 — Redis

- [ ] *Databases → Create → Redis*.
- [ ] Anotar host interno y contraseña.
- [ ] `CACHE_URL=redis://:LA-CONTRASEÑA@host-interno:6379/1`

> **Por qué Redis ahora sí.** En AWS se eligió `db://cache_appturnos` porque ElastiCache
> costaba ~$12/mes y meter Redis en la EC2 se comía 200–400 MB del único GB de RAM.
> Autohospedado no existe ninguna de las dos restricciones: `redis==5.2.1` ya está en
> `requirements.txt`, `settings.py` ya sabe leer `redis://`, y **desaparece la trampa del
> `createcachetable`**.

> 🔴 **La caché compartida no es opcional.** Gunicorn corre con 3 workers; con
> `LocMemCache` cada uno tendría la suya, así que invalidar "Mis Turnos" al aprobar una
> solicitud limpiaría solo el worker que atendió esa petición. El explorador vería su
> turno corregido o sin corregir según a qué worker cayera. `core.E001` bloquea el
> despliegue si `CACHE_URL` queda vacío, y el CI lo comprueba.

> 📌 **Nota operativa:** `core/rate_limit.py` se apoya en la caché, así que reiniciar
> Redis reinicia los contadores anti-abuso del "olvidé mi contraseña". Es aceptable a esta
> escala y conviene saberlo.

---

## FASE 4 — La Application

### 4.1 Origen

- [ ] *Create → Application*. Provider **GitHub**, repositorio `ManuelCris29/turnosEx`,
      rama `main`.
- [ ] **Auto Deploy: OFF.** Ver FASE 12.
- [ ] Build Type: **Dockerfile**
      - **Dockerfile Path:** `AppTurnosExplora/Dockerfile`
      - **Docker Context Path:** `AppTurnosExplora`

> 🔴 **El contexto tiene que ser la subcarpeta.** La raíz del repositorio es `appTurnos/`
> y el proyecto Django vive en `AppTurnosExplora/`. Si el contexto se deja en la raíz:
> el `.dockerignore` (que está dentro de `AppTurnosExplora/`) **no aplica**, se le manda a
> Docker el `venvturnos/` entero, y los `COPY` del `Dockerfile` no encuentran
> `requirements.txt`.

> ⚠️ **En la raíz del repositorio hay un `docker-compose.yml` que es de SonarQube**, no de
> la aplicación. No elegir Compose por error.

### 4.2 Recursos y arranque

- [ ] **Replicas: 1.** El `CMD` del `Dockerfile` corre `migrate --noinput` al arrancar;
      con 2+ réplicas migrarían dos a la vez. Si algún día hace falta escalar, las
      migraciones salen antes a un job aparte.

- [ ] **Límite de memoria** en *Advanced → Resources*. En servidor compartido no es
      opcional: sin límite, un pico de la aplicación se lleva a las demás.

      ```json
      {"TaskTemplate":{"Resources":{
         "Limits":{"MemoryBytes":1073741824},
         "Reservations":{"MemoryBytes":536870912}}}}
      ```

- [ ] **Update config** en *Swarm Settings*, para que un despliegue no deje la app abajo:

      ```json
      {"Parallelism":1,"Delay":10000000000,"FailureAction":"rollback","Order":"start-first"}
      ```

> El health check lo aporta ya el `Dockerfile` (contra `/health/`, que a propósito no toca
> la base). No hace falta duplicarlo en *Swarm Settings*; si se duplica, recordar que la
> imagen `slim` **no trae `curl`**.

> 📌 **El build necesita salida a internet.** Además de `pip install`, el `Dockerfile`
> trae un `ADD` del bundle CA de RDS. Aquí ya no sirve para nada, pero si el servidor
> construye sin internet **el build falla**.

---

## FASE 5 — Variables de entorno (tanda de humo)

- [ ] Pegar en *Environment* el bloque de
      [`.env.dokploy.example`](../../../../.env.dokploy.example), con los valores marcados
      **[HUMO]**:
      - `SECURE_HTTPS=False`
      - `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` y `SITE_URL` con
        el dominio `*.traefik.me` que Dokploy asigna solo.

> **Por qué en dos tandas y no de una.** Con `SECURE_HTTPS=True`, `settings.py` activa
> HSTS con **un año, `includeSubDomains` y `preload`**. En cuanto un navegador ve esa
> cabecera, ese host queda comprometido a HTTPS durante un año **para esa persona**, y no
> hay forma de apagarlo desde el servidor: no es una configuración, es una promesa que el
> navegador recuerda. Probando sobre el dominio temporal, si algo sale mal se quema un
> nombre desechable y no el dominio real.

---

## FASE 6 — Primer despliegue y arranque en frío

- [ ] Pulsar **Deploy** y seguir el log de build.

> Es normal que el contenedor reinicie una vez: el `CMD` corre `migrate` y si MySQL aún no
> acepta conexiones, falla y Swarm lo reintenta. A la segunda entra.

Desde la terminal del contenedor:

- [ ] `python manage.py createsuperuser`

- [ ] `python manage.py check --deploy` → **sin errores**.

      `core.W002` (sin TLS hacia la base) **sí aparece, y es correcto**: la app y MySQL
      hablan por la red overlay dentro del mismo servidor, no hay tráfico saliendo a
      internet que cifrar.

      🔴 **No lo "arregles" apuntando `DB_SSL_CA` a `/app/certs/rds-ca-global.pem`.** Ese
      fichero sigue en la imagen porque el `Dockerfile` lo trae de los tiempos de RDS,
      pero aquí no hay ningún RDS y la verificación de identidad fallaría.

- [ ] 🔴 **`python manage.py verificar_ip_cliente`** — **el paso que no se salta.**

      Debe imprimir la IP pública de quien navega, **no** una `10.x`/`172.x` del proxy.

      **Por qué importa tanto:** axes bloquea también por IP. Si `AXES_IPWARE_PROXY_COUNT`
      es menor que los proxies reales, axes ve la IP del proxy para **todo el mundo** y
      **5 contraseñas falladas de cualquiera bloquean a los 300 empleados**. Con solo
      Traefik delante el valor es `1`; si IT tiene otro proxy corporativo, `2`. Los checks
      `core.E003`/`core.E004` cubren el caso obvio, no este.

- [ ] Datos iniciales, a mano: calendario del año, los 6 `TipoSolicitudCambio`, los roles
      `Supervisor`/`Explorador` y las jornadas `AM`/`PM`.

> 📌 **No hay migración de datos.** Producción arranca limpia, solo con `manuel.moreno`.

---

## FASE 7 — Dominio, DNS y certificado

### 7.1 La decisión, ya tomada

**`swalp.parqueexplora.org`**, subdominio del dominio que la empresa ya tiene. **No hay
nada que comprar: costo $0.** Se descartó registrar `swalparqueexplora.org` por tres
razones, en orden de peso:

1. 🔴 **Los enlaces de aprobación actúan sin iniciar sesión.** Van firmados y caducan a
   los 30 días, pero el empleado hace clic y aprueba. Un correo que sale de
   `@parqueexplora.org` con un botón que apunta a `swalparqueexplora.org` tiene
   **exactamente la forma de un ataque de suplantación**: dominio parecido, en un correo,
   con una acción detrás. Es justo lo que se entrena a la gente a no pulsar.
2. **El correo ya está alineado.** SPF y DKIM de `parqueexplora.org` funcionan hoy: cero
   cambios de DNS de correo.
3. **No hay renovación que olvidar.** Un dominio caducado no es solo la app caída: es una
   dirección que 300 empleados reconocen quedando libre para que la compre cualquiera.

### 7.2 Lo que hay que pedirle a IT, de una sola vez

- [ ] **Registro A:** `swalp.parqueexplora.org` → **IP pública del servidor**. Con **TTL
      de 300 s** mientras dura el despliegue; se sube después.
- [ ] **Si el servidor está detrás de NAT:** el registro apunta a la IP pública del
      cortafuegos, y hace falta **redirección de los puertos 80 y 443**.
- [ ] 🔴 **Confirmar que el 80 está abierto desde internet**, aunque el sitio vaya por
      HTTPS: **Let's Encrypt valida por HTTP-01 y sin el 80 no hay certificado.**
- [ ] **Preguntar si hay algún proxy corporativo delante.** No es curiosidad: es el dato
      de `AXES_IPWARE_PROXY_COUNT` (FASE 6).
- [ ] **De correo, nada.** El subdominio hereda SPF, DKIM y DMARC.

### 7.3 Verificar antes de tocar Dokploy

```bash
nslookup swalp.parqueexplora.org        # debe devolver la IP del servidor
curl -I http://swalp.parqueexplora.org  # debe responder Traefik
```

- [ ] Un **404 de Traefik es buena señal**: el DNS resuelve y el puerto llega, solo falta
      dar de alta el router. Un **timeout** es otra cosa: puerto cerrado o NAT sin
      redirección.

### 7.4 En Dokploy

- [ ] *Domains → Add*: Host `swalp.parqueexplora.org`, Path `/`, **Container Port 8000**,
      HTTPS **ON**, Certificate **Let's Encrypt**.
- [ ] Comprobar que el certificado se emitió. Si falla, casi siempre es el 80 cerrado o el
      DNS sin propagar.

### 7.5 Y solo después, la tanda [FINAL]

```env
SECURE_HTTPS=True
ALLOWED_HOSTS=swalp.parqueexplora.org                    # SIN esquema
CSRF_TRUSTED_ORIGINS=https://swalp.parqueexplora.org     # CON esquema
CORS_ALLOWED_ORIGINS=https://swalp.parqueexplora.org     # CON esquema
SITE_URL=https://swalp.parqueexplora.org                 # CON esquema, SIN barra final
```

- [ ] Redesplegar.

> 🔴 **Los formatos son el error más repetido.** Si `ALLOWED_HOSTS` lleva `https://`,
> Django responde 400 a todo el mundo y el mensaje no dice por qué.

---

## FASE 8 — Correo

**Paso a paso completo en [MANUAL_CORREO_GOOGLE_WORKSPACE.md](../02-correo/MANUAL_CORREO_GOOGLE_WORKSPACE.md).**

Resumen de lo que hay que decidir con el administrador de Workspace:

- [ ] **Recomendado — relay SMTP autenticado por IP.** Autoriza la IP del servidor y la
      aplicación envía **sin credenciales**. Es la única opción que *elimina* la
      contraseña en vez de esconderla mejor, y arregla de raíz que hoy el envío dependa de
      la contraseña de aplicación de un buzón personal.
- [ ] **Plan B — buzón dedicado** `no-reply@parqueexplora.org` con su propia contraseña de
      aplicación. Tiene que ser un **usuario con licencia**: un alias o un grupo no pueden
      autenticarse por SMTP.

Y los dos detalles que tumban el arranque si se pasan por alto:

- [ ] 🔴 `EMAIL_HOST_USER` y `EMAIL_HOST_PASSWORD` **tienen que existir aunque vayan
      vacías**: `settings.py` las lee sin `default` y sin ellas la aplicación **no
      arranca**.
- [ ] 🔴 `EMAIL_BACKEND` **se deja sin definir**. En `console`, los correos se escriben en
      el log, no los recibe nadie, y **no hay ningún error**.

---

## FASE 9 — Las tareas programadas

Cinco Schedules. Timezone **`America/Bogota`** en todos — se acabó la conversión a UTC que
exigía EventBridge.

| Nombre | Tipo | Cron | Comando |
|---|---|---|---|
| `swalp-outbox` | Application | `*/5 * * * *` | `python manage.py procesar_email_outbox` |
| `swalp-sanciones` | Application | `15 5 * * *` | `python manage.py revisar_sanciones_por_deuda` |
| `swalp-integridad-dobladas` | Application | `0 3 * * *` | `python manage.py verificar_integridad_dobladas --reparar --email <supervisor>` |
| `swalp-alerta-crons` | Application | `30 6 * * *` | `python manage.py alertar_crons` |
| `swalp-cierre-semanal` | Dokploy Server | `40 6 * * *` | [`alerta-cierre-semanal.sh`](../../../../infra/dokploy/alerta-cierre-semanal.sh) |

### 9.1 Los dos obligatorios

- [ ] **`swalp-outbox`** — sin él, **un correo que falla no se reintenta nunca**. El envío
      inmediato es un único intento; si no prospera, la fila queda marcada como lista para
      reintentarse pero *ningún proceso despierta a mirar la cola*. Detalle completo en
      [MANUAL_OUTBOX_CORREOS.md](../02-correo/MANUAL_OUTBOX_CORREOS.md).

      Cada 5 minutos porque el primer backoff es de 1 minuto: barrer más seguido no aporta
      nada. **Es seguro que se solape consigo mismo**: cada fila se reclama con un `UPDATE`
      condicional.

- [ ] **`swalp-sanciones`** — sin él, **la sanción de un moroso solo nace cuando esa misma
      persona abre la aplicación**, así que quien no entra no aparece bloqueado en ningún
      informe del supervisor. De madrugada, para que la sanción esté puesta antes de que
      nadie empiece a trabajar.

      **Correr antes `--dry-run`**: la primera ejecución puede sancionar con fechas
      retroactivas. Ver [MANUAL_SANCIONES_DEUDA.md](../03-operacion/MANUAL_SANCIONES_DEUDA.md).

### 9.2 Comprobar que existen de verdad

```bash
python manage.py verificar_crons        # termina con código 1 si algo va mal
```

- [ ] Sale **`[ok]`** en las tres líneas.
- [ ] **Volver a lanzarlo 24 h después.** El día 1 la revisión de sanciones puede no haber
      corrido aún; lo que no es normal es que siga saliendo al día siguiente.

> **Por qué hace falta si el propio comando de sanciones ya se autodenuncia:** ese aviso
> solo puede sonar **cuando alguien lo ejecuta**. Contra el fallo que de verdad ocurre —que
> nadie programó la tarea— un proceso no puede avisar de su propia ausencia.
> `verificar_crons` mira desde fuera lo que las tareas dejan en la base.

> ⚠️ Los jobs de tipo Application usan `docker exec`: **el contenedor tiene que estar
> arriba** para que corran.

### 9.3 Periódicos, documentados pero sin programar de entrada

| Comando | Cuándo |
|---|---|
| `verificar_apertura_anio` | Mensual de octubre a diciembre. Sale != 0 si falta planificar el año siguiente |
| `materializar_alternancia --anio <N>` | Anual, con el mantenimiento de diciembre |
| `archivar_turnos_antiguos` / `archivar_solicitudes_antiguas` | Anual, **con `--dry-run` primero** |

---

## FASE 10 — Backups (lo que ya no hace RDS)

RDS hacía backup automático con 7 días de retención, cifrado en reposo y snapshot al
borrar. **Nada de eso existe en un contenedor MySQL.**

### 10.1 El destino

🔴 **Los destinos de backup de Dokploy son exclusivamente S3-compatibles**: piden
`accessKey`, `secretAccessKey`, `bucket`, `region` y `endpoint`. **No hay destino de disco
local.** Eso obliga a elegir:

| | Cuándo | Qué se gana / se pierde |
|---|---|---|
| **Reutilizar el destino existente** | Si la FASE 1.1 encontró uno | Se resuelve en cinco minutos con un `prefix` propio |
| **A. S3 corporativo** (AWS S3, Backblaze B2, MinIO de la empresa) | IT tiene almacenamiento de objetos | Todo nativo, **y la copia ya nace fuera del servidor** |
| **B. MinIO en el propio Dokploy + réplica fuera** | No hay S3 corporativo | Conserva Test, Restore y notificación, pero **obliga** a copiar el bucket a un NAS cada noche |
| **C. [`backup-mysql.sh`](../../../../infra/dokploy/backup-mysql.sh)** | Último recurso | Cero interfaz, cero notificación, restauración a mano |

- [ ] Destino configurado.
- [ ] *Backup* del servicio MySQL: base `bdturnosex`, cron `0 2 * * *`, retención ≥ 14
      días.
- [ ] **Pulsar el botón `Test`** y confirmar que el fichero aparece en el bucket.
- [ ] **Activar la notificación `databaseBackup`.** Es lo único que convierte un backup
      silencioso en uno vigilado.

### 10.2 🔴 El simulacro de restauración

**Un backup que nunca se restauró es una hipótesis.** La auditoría de costos ya lo
recomendaba teniendo RDS; sin RDS deja de ser una recomendación.

- [ ] Crear una base vacía de prueba y restaurar sobre ella la última copia
      (*Backup → Restore*, con autocompletado del fichero).
- [ ] Comprobar que los datos están.
- [ ] **Volver a cargar las tablas de zona horaria** (FASE 2.2): el dump trae
      `bdturnosex`, **no** el esquema `mysql`. Si esto se olvida en una restauración real,
      el admin volverá a fallar al filtrar por fecha y nadie sabrá por qué.
- [ ] Anotar cuánto tardó. Ese número es el RTO real, y es el dato que hay que dar cuando
      alguien pregunte "¿cuánto tardaríamos en volver?".

### 10.3 Las dos condiciones no negociables

- [ ] **La copia sale del servidor.** Un backup en el mismo disco que la base no es un
      backup: el incendio que se lleva la base se lleva las copias.
- [ ] **Backup antes de cada despliegue con migraciones.** Varias migraciones crean
      `UniqueConstraint`/`CheckConstraint` **no reversibles**, así que revertir la imagen
      no deshace el esquema.

---

## FASE 11 — Alarmas

### 11.1 El hueco que hay que tapar

El código emite cuatro marcadores a propósito, y en AWS colgaban de un metric filter de
CloudWatch:

| Marcador | Significa | Dónde vive | Quién lo arregla |
|---|---|---|---|
| `CRON_NO_EJECUTADO` | Nadie ejecuta una tarea programada | Base de datos | Programar el job |
| `CORREOS_FALLIDOS` | Correos que agotaron los 5 reintentos | Base de datos | **Una persona**, en el admin |
| `REVISION_SANCIONES_NO_EJECUTADA` | La revisión diaria lleva días sin correr | Base de datos | Programar / revisar el job |
| `CIERRE SEMANAL INOPERATIVO` | La validación del cierre falló **abierta**: la solicitud se aceptó sin validar | **Solo stdout** | Revisar el orquestador |

🔴 **Dokploy no notifica cuando un Schedule falla.** Sus disparadores son `appBuildError`,
`appDeploy`, `databaseBackup`, `dokployBackup`, `volumeBackup`, `dockerCleanup`,
`dokployRestart` y `serverThreshold` — ninguno cubre un trabajo programado que revienta.
Un cron caído se queda en rojo dentro de un log que nadie abre, que es **peor** que el
`crontab` de Linux, donde un código de salida distinto de cero al menos generaba correo.

### 11.2 `alertar_crons` — los tres marcadores de base

- [ ] Definir `ALERTAS_CRON_EMAIL` en las variables de la Application.
- [ ] Schedule `swalp-alerta-crons` (FASE 9) programado.
- [ ] **Probarlo antes de darlo por bueno:**

      ```bash
      python manage.py alertar_crons --dry-run
      ```

      **Un aviso sin probar no es un aviso.**

> El comando envía con `smtplib` directamente, **no** con `django.core.mail`, y eso es
> deliberado: todo correo de la aplicación pasa por el outbox, así que si lo averiado es
> justamente el worker del outbox, una alerta encolada ahí se quedaría esperando junto a
> los correos que denuncia. **El vigilante no puede compartir maquinaria con lo que
> vigila.** (Además, el ADR 016 exige que `django.core.mail` solo aparezca en
> `email_outbox_service.py`.)

> **El latido semanal.** Los lunes el comando avisa aunque todo esté bien. Es la única
> defensa contra que deje de correr *él*: un vigilante mudo y uno muerto se ven igual
> desde fuera. Semanal y no diario porque un aviso diario de que no pasa nada se deja de
> leer en dos semanas.

### 11.3 `alerta-cierre-semanal.sh` — el marcador que vive en el log

- [ ] Schedule `swalp-cierre-semanal` (FASE 9) con las variables que pide el script.
- [ ] **Probarlo**: forzar una línea con ese texto en el log del contenedor y comprobar
      que **llega el correo**.

> Este marcador es el único que no se puede ver desde dentro del contenedor:
> `config/settings.py` fija `if IS_PRODUCTION: LOG_A_FICHERO = False`, sin variable de
> entorno que lo cambie. Solo existe en stdout, así que hace falta `docker logs` — y eso
> solo desde el anfitrión. **No hace falta SSH**: un admin de Dokploy puede crear
> Schedules de tipo Server desde el panel.

### 11.4 Lo que sí cubre Dokploy

- [ ] `serverThreshold` — disco, RAM y CPU. **En servidor compartido no es opcional**: es
      lo que evita que nuestro build deje sin espacio a las demás aplicaciones.
- [ ] `databaseBackup` — el backup falló.
- [ ] `appBuildError` / `appDeploy`.

> 🔴 **Los cuatro marcadores no se traducen ni se retocan.** Van en mayúsculas, sin
> acentos y sin texto variable porque son el enganche de las alarmas, y están protegidos
> por tests (`test_verificar_crons.py`, `test_alertar_crons.py`,
> `test_alerta_cron_sanciones.py`). Cualquier retoque de redacción apaga la alarma sin que
> nadie lo note.

---

## FASE 12 — GitHub y el ciclo de vida

### 12.1 Conectar

- [ ] *Git Sources → GitHub*. Si la FASE 1.1 encontró una GitHub App ya instalada, basta
      con **darle acceso al repositorio**. Si no, crear una (nombre único, p. ej.
      `Dokploy-ParqueExplora`), instalarla y autorizarla con acceso **solo** a
      `ManuelCris29/turnosEx`.

> La GitHub App es preferible a una clave de despliegue: los permisos son revocables por
> repositorio y el token rota solo.

### 12.2 🔴 Auto Deploy: OFF

Dokploy lo trae **encendido por defecto para GitHub: despliega en cada push**. Aquí eso es
un error, y por un motivo concreto: el job `test` del CI corre `manage.py check --deploy`,
que es la barrera que impide desplegar con `LocMemCache` (`core.E001`) o con axes mal
configurado (`core.E003`/`core.E004`). **Desplegar en el push crudo se salta esa barrera
justo en los dos fallos que dejan la aplicación en pie pero rota:** turnos
desactualizados, o los 300 empleados bloqueados al quinto intento fallido de cualquiera.

- [ ] Auto Deploy desactivado.
- [ ] Configurar [`.github/workflows/deploy.yml`](../../../../../.github/workflows/deploy.yml)
      (ya está en el repositorio) con tres secretos en GitHub:
      `DOKPLOY_URL`, `DOKPLOY_API_KEY` (*Settings → API Keys*) y `DOKPLOY_APP_ID`.

> ⚠️ El panel tiene que ser alcanzable desde GitHub Actions. Si hoy solo responde en el
> `:3000`, **pídele a quien administre el servidor que le ponga dominio propio con TLS
> antes** de meter ahí una API key: esa clave puede desplegar y leer configuración de
> **todas** las aplicaciones del servidor.

### 12.3 Qué pasa en cada actualización

```
git push a main
   └─► CI: test + lint + tests_js + seguridad          ¿verde?
          └─► deploy.yml llama a la API de Dokploy
                 └─► Dokploy clona, construye (pip install + collectstatic)
                        └─► arranca el contenedor nuevo
                              CMD: migrate --noinput && gunicorn
                                 └─► start-first: Traefik pasa al nuevo, cae el viejo
```

`start-first` levanta el nuevo antes de matar el viejo, y **solo el nuevo corre
`migrate`**.

### 12.4 Volver atrás

El rollback de Dokploy es **basado en registro**: descarga del registro la imagen de un
despliegue anterior. Sin registro configurado, volver atrás es redesplegar un commit
anterior, que **reconstruye** la imagen (varios minutos). Con 300 usuarios internos eso es
tolerable; si se quiere rollback rápido, hace falta configurar un Docker Registry.

- [ ] 🔴 **Recordar que revertir la imagen NO deshace las migraciones.** De ahí el backup
      previo (FASE 10.3).

Dokploy guarda el historial de los **últimos 10 despliegues** con su log de build.

---

## FASE 13 — Verificación final

### Acceso y seguridad
- [ ] `https://swalp.parqueexplora.org` accesible **desde fuera de la red** (celular con
      datos).
- [ ] `curl -I http://swalp.parqueexplora.org` redirige a `https`.
- [ ] Login funciona; **axes bloquea tras 5 intentos fallidos**… y **desbloquea solo a esa
      persona**, no a todas (si bloquea a todas, `AXES_IPWARE_PROXY_COUNT` está mal).
- [ ] `/admin/` abre **sin el error de zona horaria** y se puede filtrar por fecha.

### Funcional
- [ ] Dashboard, crear solicitud, aceptar pendiente (emisor y receptor).
- [ ] Los 6 formularios de solicitudes.
- [ ] **Mis Turnos refleja el turno aplicado** tras aprobar.
- [ ] Llega el correo de notificación desde `no-reply@parqueexplora.org`, y en *Mostrar
      original*: `SPF`, `DKIM` **alineado con el `From`** y `DMARC` en `PASS`.

### Tareas de fondo
- [ ] A las 24 h: `python manage.py verificar_crons` → `[ok]` en las tres líneas.
- [ ] `/admin/solicitudes/revisionsancionesdeuda/` tiene **una fila con la fecha de ayer**.
- [ ] `python manage.py procesar_email_outbox --resumen` → `pendiente=0`, `fallido=0`.
- [ ] Las dos alarmas **probadas de verdad** (FASE 11.2 y 11.3).

### Backups
- [ ] Backup automático ejecutado, visible en el bucket.
- [ ] **Restauración probada** y el tiempo anotado (FASE 10.2).

### Ciclo de vida
- [ ] Un cambio trivial: `git push` → CI verde → despliegue automático → **la aplicación
      sigue arriba durante el cambio**.

---

## Anexo — Operación diaria

```bash
# Estado de la cola de correos
python manage.py procesar_email_outbox --resumen

# Diagnóstico de las tareas de fondo
python manage.py verificar_crons
python manage.py alertar_crons --dry-run

# Forzar una pasada del outbox
python manage.py procesar_email_outbox --limite 100
```

| Dónde mirar | Para qué |
|---|---|
| Dokploy → Application → **Logs** | Qué está haciendo la aplicación ahora |
| Dokploy → Application → **Deployments** | Los últimos 10 despliegues y su log de build |
| Dokploy → Schedules → *(cada job)* | Si el cron corrió y qué imprimió |
| `/admin/solicitudes/emailoutbox/` | Correos en `fallido` — **los únicos que exigen una persona** |
| `/admin/solicitudes/revisionsancionesdeuda/` | Una fila por día que corrió la revisión |

---

## Documentos relacionados

- [MANUAL_CORREO_GOOGLE_WORKSPACE.md](../02-correo/MANUAL_CORREO_GOOGLE_WORKSPACE.md) — FASE 8 al detalle
- [MANUAL_OUTBOX_CORREOS.md](../02-correo/MANUAL_OUTBOX_CORREOS.md) — cómo funciona la cola de correos
- [MANUAL_SANCIONES_DEUDA.md](../03-operacion/MANUAL_SANCIONES_DEUDA.md) — el cron diario de sanciones
- [CONFIGURACION_PRODUCCION.md](../03-operacion/CONFIGURACION_PRODUCCION.md) — qué hace cada variable y qué se rompe si falta
- [`infra/dokploy/README.md`](../../../../infra/dokploy/README.md) — los scripts de los Schedules de tipo Server
- [CHECKLIST_DESPLIEGUE_AWS_RDS.md](../99-aws/CHECKLIST_DESPLIEGUE_AWS_RDS.md) — el plan que este sustituye; se conserva como registro de los invariantes
