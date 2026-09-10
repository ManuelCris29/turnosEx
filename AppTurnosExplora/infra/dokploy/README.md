# Scripts de apoyo para el despliegue en Dokploy

Estos tres scripts **no se ejecutan desde el repositorio**. Se copian y se pegan en
*Dokploy → Schedules*, en un trabajo de tipo **Server** o **Dokploy Server** (los que
corren en el anfitrión, no dentro del contenedor de la aplicación). Viven aquí para que
estén versionados, se revisen en un PR y no se pierdan si algún día se reinstala el
servidor.

> No hace falta acceso SSH. Un usuario **admin de Dokploy** puede crear Schedules de tipo
> Server desde el propio panel, y eso es suficiente para los tres.

El paso a paso completo está en
[`docs/05-referencia/deployment/01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md`](../../docs/05-referencia/deployment/01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md).

---

## `cargar-zonas-horarias.sh`

**Cuándo:** una sola vez, al crear el servicio MySQL (FASE 2). **No se programa.**

RDS traía las tablas `mysql.time_zone*` pobladas; la imagen oficial de MySQL no. Sin
ellas `CONVERT_TZ` devuelve `NULL` y el admin de Django revienta al filtrar por fecha.
Las tablas viven en el volumen, así que basta con cargarlas una vez.

| Variable | Qué es |
|---|---|
| `CONTENEDOR_MYSQL` | Nombre o id del contenedor de MySQL (`docker ps`) |

**Vuelve a hacer falta** si se recrea el volumen desde cero, incluido el caso de levantar
la base desde un backup: el dump trae `bdturnosex`, no el esquema `mysql`.

---

## `alerta-cierre-semanal.sh`

**Cuándo:** diario, `40 6 * * *`, timezone `America/Bogota`.

Vigila el marcador `CIERRE SEMANAL INOPERATIVO`. Es el único de los cuatro marcadores que
**solo existe en stdout** —`config/settings.py` fija `LOG_A_FICHERO = False` en
producción—, así que hay que leerlo con `docker logs` desde el anfitrión. Los otros tres
se deducen de la base de datos y los cubre `manage.py alertar_crons`, que corre dentro del
contenedor.

| Variable | Qué es |
|---|---|
| `CONTENEDOR_APP` | Nombre o id del contenedor de `swalp-web` |
| `ALERTAS_EMAIL` | Destinatario del aviso |
| `SMTP_HOST` / `SMTP_PORT` | `smtp-relay.gmail.com` / `587` |
| `SMTP_FROM` | `no-reply@parqueexplora.org` |
| `SMTP_USER` / `SMTP_PASSWORD` | Vacías si el relay autentica por IP |

Trae al final una alternativa con webhook (Teams, Slack, Google Chat, ntfy) por si se
prefiere el canal del equipo al correo.

---

## `backup-mysql.sh`

**Cuándo:** diario, `0 2 * * *` — **pero solo si no hay ningún destino S3 disponible.**

Es la peor de las tres opciones de backup y está escrito para el caso en que no haya otra.
Los destinos de backup de Dokploy son **exclusivamente S3-compatibles**, así que:

1. Si ya existe un destino S3 en *Settings → S3 Destinations* (puede haberlo para las
   otras aplicaciones del servidor), **reutilízalo** con un `prefix` propio y olvida este
   script.
2. Si no, monta uno: S3 corporativo, Backblaze B2 o un MinIO en el propio Dokploy.
3. Solo si nada de eso es posible, usa esto.

Lo que se pierde al usarlo: el botón **Test**, el **Restore** de un clic y la notificación
`databaseBackup` cuando el backup falla.

| Variable | Por defecto |
|---|---|
| `CONTENEDOR_MYSQL` | *(obligatoria)* |
| `BD` | `bdturnosex` |
| `DESTINO` | `/var/backups/swalp` |
| `RETENCION_DIAS` | `14` |

**Dos cosas que este script no hace y siguen siendo obligatorias:** sacar la copia del
servidor (un backup en el mismo disco que la base no es un backup) y **probar la
restauración** al menos una vez.

---

## Nota sobre los marcadores

`CRON_NO_EJECUTADO`, `CORREOS_FALLIDOS`, `REVISION_SANCIONES_NO_EJECUTADA` y
`CIERRE SEMANAL INOPERATIVO` van en mayúsculas, sin acentos y sin texto variable **a
propósito**: son el enganche de las alarmas y están protegidos por tests. No se traducen
ni se retocan — un cambio de redacción apaga la alarma sin que nadie lo note.
