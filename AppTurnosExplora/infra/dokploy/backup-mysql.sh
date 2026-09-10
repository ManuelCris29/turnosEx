#!/bin/sh
# =============================================================================
# Backup de la base por mysqldump — SOLO SI NO HAY DESTINO S3
# =============================================================================
#
# ⚠️ LEE ESTO ANTES DE USARLO: esta es la OPCIÓN C, la peor de las tres.
#
#   A. Destino S3 corporativo  → usa la pestaña Backup del servicio MySQL en
#      Dokploy. Trae botón Test, Restore de un clic, retención y —lo que más
#      importa— la notificación `databaseBackup` cuando el backup falla.
#   B. MinIO en el propio Dokploy + réplica a un NAS → mismas ventajas que A.
#   C. Este script → cero interfaz, cero notificación, restauración a mano.
#
#   Los destinos de backup de Dokploy son EXCLUSIVAMENTE S3-compatibles: piden
#   accessKey, secretAccessKey, bucket, region y endpoint. No existe destino de
#   disco local. Por eso este script existe: para cuando no hay ningún S3 al
#   alcance. En cuanto lo haya, se tira.
#
# LO QUE ESTE SCRIPT **NO** HACE, Y HAY QUE HACER APARTE
#   1. SACAR LA COPIA DEL SERVIDOR. Un backup en el mismo disco que la base no es
#      un backup: el incendio que se lleva la base se lleva las copias. Añade un
#      rsync/rclone a un NAS o a otra máquina, o esto no protege de nada.
#   2. PROBAR LA RESTAURACIÓN. Un backup que nunca se restauró es una hipótesis.
#      Ver el manual de despliegue, FASE 10.
#
# CÓMO SE USA
#   Dokploy → Schedules → tipo "Dokploy Server" (o "Server"), shell `sh`,
#   timezone America/Bogota, cron `0 2 * * *`.
#
#   Variables:
#     CONTENEDOR_MYSQL  nombre o id del contenedor de MySQL (`docker ps`)
#     BD                nombre de la base (bdturnosex)
#     DESTINO           carpeta del anfitrión donde se dejan los .sql.gz
#     RETENCION_DIAS    días que se conservan (por defecto 14)
# =============================================================================
set -eu

: "${CONTENEDOR_MYSQL:?define CONTENEDOR_MYSQL}"
BD="${BD:-bdturnosex}"
DESTINO="${DESTINO:-/var/backups/swalp}"
RETENCION_DIAS="${RETENCION_DIAS:-14}"

mkdir -p "$DESTINO"
ARCHIVO="${DESTINO}/${BD}-$(date +%Y%m%d-%H%M%S).sql.gz"

echo "==> Volcando ${BD} a ${ARCHIVO}"

# --single-transaction: la copia sale consistente SIN bloquear la aplicación
#   (InnoDB). Sin esto, un backup a las 2 de la mañana podría capturar una
#   solicitud a medio aprobar.
# --routines --triggers --events: el esquema no es solo tablas.
docker exec "$CONTENEDOR_MYSQL" sh -c \
    "exec mysqldump -uroot -p\"\$MYSQL_ROOT_PASSWORD\" \
        --single-transaction --routines --triggers --events \
        --default-character-set=utf8mb4 ${BD}" \
    | gzip -9 > "$ARCHIVO"

# -----------------------------------------------------------------------------
# VERIFICACIÓN — sin esto, el modo de fallo típico pasa desapercibido.
# `mysqldump` puede terminar en 0 y escribir un fichero vacío o truncado (una
# credencial mal puesta, el contenedor arrancando). Un .gz de 20 bytes rotando en
# la carpeta durante meses parece un backup y no lo es.
# -----------------------------------------------------------------------------
TAMANO=$(wc -c < "$ARCHIVO")
echo "    ${TAMANO} bytes"

if [ "$TAMANO" -lt 1024 ]; then
    echo "ERROR: el volcado esta practicamente vacio (${TAMANO} bytes)." >&2
    echo "       Se borra para que nadie lo confunda con una copia buena." >&2
    rm -f "$ARCHIVO"
    exit 1
fi

# Que el gzip se pueda descomprimir es lo minimo exigible para llamarlo copia.
if ! gzip -t "$ARCHIVO"; then
    echo "ERROR: el fichero comprimido esta corrupto." >&2
    rm -f "$ARCHIVO"
    exit 1
fi

echo "==> Rotando copias de mas de ${RETENCION_DIAS} dias"
find "$DESTINO" -name "${BD}-*.sql.gz" -mtime "+${RETENCION_DIAS}" -print -delete

echo "==> OK: ${ARCHIVO}"
echo ""
echo "RECORDATORIO: esta copia sigue en el MISMO servidor que la base."
echo "Si no hay un rsync/rclone que la lleve fuera, no protege de nada."
