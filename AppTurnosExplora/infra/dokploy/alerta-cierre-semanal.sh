#!/bin/sh
# =============================================================================
# Vigilante del marcador CIERRE SEMANAL INOPERATIVO
# =============================================================================
#
# QUÉ VIGILA
#   La comprobación del cierre semanal falla ABIERTA a propósito
#   (`solicitudes/services/solicitud_orchestrator.py`): si se rompe, la solicitud
#   se acepta SIN VALIDAR y lo único que queda es un CRITICAL en el log con el
#   texto `CIERRE SEMANAL INOPERATIVO`. Sin un aviso, el cierre queda desactivado
#   de hecho y nadie se entera.
#
# POR QUÉ ESTE MARCADOR NECESITA UN SCRIPT Y LOS OTROS TRES NO
#   Los otros tres (`CRON_NO_EJECUTADO`, `CORREOS_FALLIDOS`,
#   `REVISION_SANCIONES_NO_EJECUTADA`) se deducen de la BASE DE DATOS, así que los
#   cubre `manage.py alertar_crons` desde dentro del contenedor.
#
#   Este NO. Solo existe en stdout: `config/settings.py` fija
#   `if IS_PRODUCTION: LOG_A_FICHERO = False`, sin variable de entorno que lo
#   cambie. Desde dentro del contenedor no hay nada que leer, así que hace falta
#   `docker logs` — y eso solo se puede hacer desde el anfitrión.
#
# CÓMO SE USA
#   Dokploy → Schedules → tipo "Dokploy Server" (o "Server"), shell `sh`,
#   timezone America/Bogota, cron `40 6 * * *` (después del vigilante de crons).
#
#   Variables necesarias:
#     CONTENEDOR_APP   nombre o id del contenedor de swalp-web (`docker ps`)
#     ALERTAS_EMAIL    destinatario del aviso
#     SMTP_HOST        p.ej. smtp-relay.gmail.com
#     SMTP_PORT        587
#     SMTP_FROM        no-reply@parqueexplora.org
#     SMTP_USER        vacío si el relay autentica por IP
#     SMTP_PASSWORD    vacío si el relay autentica por IP
#
#   Si la empresa usa Teams/Slack, sustituir `enviar_correo` por un `curl` al
#   webhook del canal: ver el final del fichero.
#
# VENTANA
#   Mira solo las últimas 24 h, igual que hace `verificar_crons` con los correos
#   agotados y por el mismo motivo: una alarma que no se puede apagar arreglando
#   la causa se acaba ignorando.
# =============================================================================
set -eu

: "${CONTENEDOR_APP:?define CONTENEDOR_APP con el nombre del contenedor de la app}"
: "${ALERTAS_EMAIL:?define ALERTAS_EMAIL con el destinatario del aviso}"

VENTANA="${VENTANA:-24h}"
# El marcador va literal y en mayúsculas. NO se traduce ni se retoca: es un
# contrato con la infraestructura, y cualquier cambio de redacción apagaría esta
# alarma sin que se note. Está protegido por tests en el repositorio.
MARCADOR="CIERRE SEMANAL INOPERATIVO"

enviar_correo() {
    asunto="$1"
    cuerpo="$2"
    tmp=$(mktemp)
    {
        echo "From: ${SMTP_FROM}"
        echo "To: ${ALERTAS_EMAIL}"
        echo "Subject: ${asunto}"
        echo ""
        echo "${cuerpo}"
    } > "$tmp"

    # curl habla SMTP: no hace falta un MTA instalado en el anfitrion.
    # --ssl-reqd fuerza STARTTLS; sin el, la contrasena viajaria en claro.
    if [ -n "${SMTP_USER:-}" ] && [ -n "${SMTP_PASSWORD:-}" ]; then
        curl --silent --show-error --ssl-reqd \
             --url "smtp://${SMTP_HOST}:${SMTP_PORT}" \
             --user "${SMTP_USER}:${SMTP_PASSWORD}" \
             --mail-from "${SMTP_FROM}" \
             --mail-rcpt "${ALERTAS_EMAIL}" \
             --upload-file "$tmp"
    else
        # Relay autenticado POR IP: sin credenciales, que es justo el objetivo.
        curl --silent --show-error --ssl-reqd \
             --url "smtp://${SMTP_HOST}:${SMTP_PORT}" \
             --mail-from "${SMTP_FROM}" \
             --mail-rcpt "${ALERTAS_EMAIL}" \
             --upload-file "$tmp"
    fi

    rm -f "$tmp"
}

# `grep -c` devuelve 1 cuando no encuentra nada, y con `set -e` eso abortaria el
# script haciendo pasar "todo bien" por un fallo. El `|| true` lo evita.
OCURRENCIAS=$(docker logs --since "$VENTANA" "$CONTENEDOR_APP" 2>&1 \
              | grep -c "$MARCADOR" || true)

if [ "${OCURRENCIAS:-0}" -eq 0 ]; then
    echo "[ok] Sin rastro de '${MARCADOR}' en las ultimas ${VENTANA}."
    exit 0
fi

MUESTRA=$(docker logs --since "$VENTANA" "$CONTENEDOR_APP" 2>&1 \
          | grep "$MARCADOR" | tail -n 5)

CUERPO=$(cat <<FIN
La comprobacion del cierre semanal fallo ${OCURRENCIAS} vez/veces en las ultimas ${VENTANA}.

QUE SIGNIFICA
  Esa validacion falla ABIERTA a proposito: cuando se rompe, la solicitud se
  ACEPTA SIN VALIDAR el cierre. O sea que durante ese rato el cierre semanal
  estuvo desactivado de hecho.

QUE HACER
  1. Revisar solicitudes/services/solicitud_orchestrator.py y el log completo:
     docker logs --since ${VENTANA} ${CONTENEDOR_APP} | grep "${MARCADOR}"
  2. Comprobar que las solicitudes aceptadas en esa franja son legitimas.

ULTIMAS LINEAS:
${MUESTRA}
FIN
)

echo "$CUERPO"
enviar_correo "SWALP: cierre semanal inoperativo" "$CUERPO"

# Codigo 1 para que el Schedule quede tambien en rojo en el panel, no solo avisado.
exit 1

# -----------------------------------------------------------------------------
# ALTERNATIVA CON WEBHOOK (Teams, Slack, Google Chat, ntfy)
# Sustituir la llamada a `enviar_correo` por:
#
#   curl --silent --show-error -X POST -H 'Content-Type: application/json' \
#        -d "{\"text\": \"SWALP: cierre semanal inoperativo (${OCURRENCIAS} en ${VENTANA})\"}" \
#        "$WEBHOOK_URL"
# -----------------------------------------------------------------------------
