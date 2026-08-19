"""Tokens firmados de los enlaces de aprobación/rechazo por correo.

FUENTE ÚNICA. Antes existían SEIS copias de la misma verificación —una en
`email_service.py`, cuatro en `views/aprobacion_email.py` y una sexta en otra app,
`permisos/services.py`—, todas firmando con una clave escrita en el código. La
sexta es la que explica esta regla: estaba fuera de `solicitudes/`, se pasó por
alto en la primera revisión, y bastaba olvidar una para dejar el agujero abierto.
Todo pasa ahora por aquí.

QUÉ PROTEGE
El correo de solicitud lleva enlaces que aprueban o rechazan SIN iniciar sesión.
El token es la única credencial: si se puede fabricar, se puede aprobar cualquier
solicitud en nombre de cualquier supervisor.

CÓMO
`django.core.signing` firma con `SECRET_KEY` (HMAC-SHA256) e incluye una marca de
tiempo, de modo que el enlace caduca. La firma es *stateless*: no consulta base de
datos ni caché, así que cualquier instancia detrás del balanceador verifica un
token emitido por otra sin estado compartido.

EN AWS, DOS CONDICIONES
1. `SECRET_KEY` debe ser LA MISMA en todas las instancias (una sola entrada en
   Secrets Manager / SSM, no un valor por tarea). Si cada instancia genera la suya,
   los enlaces fallan de forma intermitente según a cuál encamine el ALB.
2. Rotar `SECRET_KEY` invalida los enlaces ya enviados. Es el comportamiento
   correcto ante una filtración; tenlo en cuenta al planificar una rotación
   rutinaria (los pendientes se aprueban entrando a la aplicación).

UN SOLO USO
No se lleva lista de tokens gastados: el estado de la solicitud ya lo impide.
`_ya_resuelto_para()` (views/aprobacion_email.py) corta cuando la solicitud está
resuelta o ese rol ya respondió. Esa comprobación vive en la base de datos, que es
el almacén compartido en AWS, y además cubre el caso de que el cliente de correo
pre-cargue el enlace.
"""

import logging

from django.conf import settings
from django.core import signing

logger = logging.getLogger(__name__)

# Aísla estos tokens de cualquier otro uso de `signing` en el proyecto: una firma
# emitida para otra cosa no vale como token de aprobación aunque comparta clave.
SALT = 'solicitudes.aprobacion-email'

TIPOS_VALIDOS = ('supervisor', 'receptor')


def _max_age_segundos():
    """Vida del enlace en segundos (configurable con APPROVAL_LINK_MAX_AGE_DAYS)."""
    dias = getattr(settings, 'APPROVAL_LINK_MAX_AGE_DAYS', 30)
    return int(dias) * 24 * 60 * 60


def generar(solicitud_id, empleado_id, tipo):
    """Devuelve el token firmado que viaja en la URL del correo."""
    if tipo not in TIPOS_VALIDOS:
        raise ValueError("tipo de token no válido: %r" % (tipo,))
    return signing.dumps(
        {'s': int(solicitud_id), 'e': int(empleado_id), 't': tipo},
        salt=SALT,
    )


def _empleado_esperado(solicitud, tipo):
    """Quién es el único que puede usar un token de este tipo. None si no hay."""
    if tipo == 'supervisor':
        supervisor = solicitud.explorador_solicitante.supervisor
        return supervisor.id if supervisor else None
    receptor = solicitud.explorador_receptor
    return receptor.id if receptor else None


def verificar(solicitud, token, tipo):
    """True si `token` fue emitido por nosotros para esta solicitud, rol y persona.

    Devuelve False —nunca lanza— ante firma inválida, token caducado, token de
    otra solicitud o de otro rol. El llamador solo necesita saber si sigue.
    """
    if tipo not in TIPOS_VALIDOS or not token:
        return False

    try:
        datos = signing.loads(token, salt=SALT, max_age=_max_age_segundos())
    except signing.SignatureExpired:
        logger.info("Token de aprobación caducado (solicitud %s, %s)", solicitud.id, tipo)
        return False
    except signing.BadSignature:
        # Firma que no es nuestra: enlace manipulado o clave rotada.
        logger.warning("Token de aprobación inválido (solicitud %s, %s)", solicitud.id, tipo)
        return False

    if not isinstance(datos, dict):
        return False

    esperado = _empleado_esperado(solicitud, tipo)
    if esperado is None:
        return False

    # El token debe ser de ESTA solicitud, de ESTE rol y de la persona que hoy
    # ocupa ese rol: si a un explorador le cambian de supervisor, el enlace que
    # tenía el supervisor anterior deja de servir.
    return (
        datos.get('s') == solicitud.id
        and datos.get('t') == tipo
        and datos.get('e') == esperado
    )


# --------------------------------------------------------------- permisos especiales
#
# Los permisos especiales tienen su propio correo de aprobación con el mismo
# riesgo. Sal distinta a propósito: un token de permiso no debe valer como token
# de solicitud de cambio ni al revés, aunque los firme la misma SECRET_KEY.

SALT_PERMISO = 'permisos.aprobacion-email'


def generar_permiso(permiso_id, supervisor_id):
    """Token firmado del enlace de aprobación de un permiso especial."""
    return signing.dumps(
        {'p': int(permiso_id), 'e': int(supervisor_id)},
        salt=SALT_PERMISO,
    )


def verificar_permiso(permiso, token):
    """True si `token` es nuestro, vigente y del supervisor actual del empleado."""
    if not token:
        return False

    supervisor = permiso.empleado.supervisor
    if not supervisor:
        return False

    try:
        datos = signing.loads(token, salt=SALT_PERMISO, max_age=_max_age_segundos())
    except signing.SignatureExpired:
        logger.info("Token de permiso caducado (permiso %s)", permiso.id)
        return False
    except signing.BadSignature:
        logger.warning("Token de permiso inválido (permiso %s)", permiso.id)
        return False

    if not isinstance(datos, dict):
        return False

    return datos.get('p') == permiso.id and datos.get('e') == supervisor.id
