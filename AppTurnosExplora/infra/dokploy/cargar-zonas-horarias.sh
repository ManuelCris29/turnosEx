#!/bin/sh
# =============================================================================
# Cargar las tablas de zona horaria de MySQL — SE EJECUTA UNA SOLA VEZ
# =============================================================================
#
# QUÉ ARREGLA
#   `TIME_ZONE='America/Bogota'` con `USE_TZ=True` hace que Django resuelva los
#   filtros por fecha con CONVERT_TZ, y CONVERT_TZ con NOMBRES de zona necesita
#   las tablas `mysql.time_zone*` pobladas.
#
#   RDS las trae pobladas. La imagen oficial de MySQL NO. Sin ellas CONVERT_TZ
#   devuelve NULL y el admin de Django revienta al filtrar por fecha — es el
#   mismo error que ya apareció en el MySQL local durante el desarrollo.
#
# POR QUÉ BASTA UNA VEZ
#   Esas tablas viven en el esquema `mysql`, dentro del directorio de datos, así
#   que PERSISTEN EN EL VOLUMEN del servicio. Sobreviven a reinicios y
#   redespliegues. Solo hay que repetirlo si se recrea el volumen desde cero.
#
#   OJO: restaurar un backup NO las trae. El dump contiene `bdturnosex`, no el
#   esquema `mysql`. Si algún día se levanta la base desde una copia, este script
#   vuelve a hacer falta.
#
# CÓMO SE USA
#   Dokploy → Schedules → tipo "Dokploy Server" (o "Server"), shell `sh`.
#   Pegar este contenido y ejecutar A MANO una vez. NO se programa: no es un cron.
#   Requiere la variable CONTENEDOR_MYSQL.
#
#   CONTENEDOR_MYSQL: nombre o id del contenedor de MySQL. Se ve con `docker ps`.
# =============================================================================
set -eu

: "${CONTENEDOR_MYSQL:?define CONTENEDOR_MYSQL con el nombre del contenedor de MySQL}"

echo "==> Cargando zonas horarias en ${CONTENEDOR_MYSQL}"

# Camino normal: la imagen trae /usr/share/zoneinfo.
if docker exec "$CONTENEDOR_MYSQL" test -d /usr/share/zoneinfo; then
    echo "    zoneinfo encontrado dentro del contenedor"
    docker exec "$CONTENEDOR_MYSQL" sh -c \
        'mysql_tzinfo_to_sql /usr/share/zoneinfo | mysql -uroot -p"$MYSQL_ROOT_PASSWORD" mysql'
else
    # Camino de respaldo: las imágenes oficiales de MySQL son Oracle Linux slim y
    # pueden venir SIN zoneinfo. Se le presta el del anfitrión, que sí lo tiene.
    echo "    sin zoneinfo en la imagen: se copia el del anfitrion"
    [ -d /usr/share/zoneinfo ] || {
        echo "ERROR: el anfitrion tampoco tiene /usr/share/zoneinfo." >&2
        echo "       Instala tzdata en el anfitrion y vuelve a lanzarlo." >&2
        exit 1
    }
    docker cp /usr/share/zoneinfo "${CONTENEDOR_MYSQL}:/tmp/zoneinfo"
    docker exec "$CONTENEDOR_MYSQL" sh -c \
        'mysql_tzinfo_to_sql /tmp/zoneinfo | mysql -uroot -p"$MYSQL_ROOT_PASSWORD" mysql'
    docker exec "$CONTENEDOR_MYSQL" rm -rf /tmp/zoneinfo
fi

# -----------------------------------------------------------------------------
# VERIFICACIÓN — esta parte no es opcional.
# Sin ella no se sabe si el paso de arriba sirvió de algo: `mysql_tzinfo_to_sql`
# puede terminar con código 0 habiendo cargado cero filas.
# -----------------------------------------------------------------------------
echo "==> Verificando"

FILAS=$(docker exec "$CONTENEDOR_MYSQL" sh -c \
    'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -B -e "SELECT COUNT(*) FROM mysql.time_zone_name;"')

echo "    mysql.time_zone_name: ${FILAS} filas (lo normal son ~1795)"

if [ "$FILAS" -lt 100 ]; then
    echo "ERROR: las tablas de zona horaria siguen vacias o casi." >&2
    echo "       El admin de Django fallara al filtrar por fecha." >&2
    exit 1
fi

CONVERSION=$(docker exec "$CONTENEDOR_MYSQL" sh -c \
    'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -N -B -e "SELECT CONVERT_TZ(NOW(),'"'"'UTC'"'"','"'"'America/Bogota'"'"');"')

echo "    CONVERT_TZ -> ${CONVERSION}"

if [ -z "$CONVERSION" ] || [ "$CONVERSION" = "NULL" ]; then
    echo "ERROR: CONVERT_TZ devuelve NULL. Las zonas no se cargaron bien." >&2
    exit 1
fi

echo "==> OK. La base ya entiende America/Bogota."
