"""Límite de peticiones para los formularios sensibles de contraseña.

POR QUÉ EXISTE ESTO
-------------------
`django-axes` vigila UNA sola puerta: los intentos fallidos de *login*. Las
pantallas de "olvidé mi contraseña" y "cambiar mi contraseña" son puertas
distintas y axes no las mira, así que sin este módulo quedarían como endpoints
sin ningún freno:

* En el reset, cualquiera puede pedir correos en bucle contra un email conocido.
  No revienta ninguna cuenta —el token es de un solo uso y de vida corta—, pero
  quema la **reputación de remitente del dominio**: si esos correos se marcan
  como spam, SES puede suspender el envío para TODA la aplicación, no solo para
  el reset.
* En el cambio de contraseña, con una sesión robada (portátil sin bloquear,
  cookie filtrada) se podría probar la contraseña actual sin límite hasta
  apoderarse de la cuenta.

Se apoya en la caché que ya es obligatoria en producción (`CACHE_URL`), así que
no añade infraestructura. Contrapartida asumida: con varias tareas y caché
compartida el conteo es global (correcto); con `LocMemCache` cada proceso cuenta
por su cuenta (aceptable, es el caso de desarrollo y tests).
"""
import hashlib
import logging

from django.core.cache import cache

logger = logging.getLogger('core.seguridad')

# Ventana común a todos los límites. Una hora es larga para molestar a alguien
# legítimo (que reintenta una o dos veces) y corta para que un bloqueo no
# parezca permanente.
VENTANA_SEGUNDOS = 3600

# Los tres límites del plan de seguridad, juntos para poder revisarlos de un
# vistazo en vez de repartidos por las vistas.
LIMITE_RESET_POR_IP = 5      # frena el abuso masivo desde un origen
LIMITE_RESET_POR_EMAIL = 3   # impide bombardear a UNA persona rotando de IP
LIMITE_CAMBIO_POR_USUARIO = 5


def _clave(ambito: str, identificador: str) -> str:
    """Construye la clave de caché.

    El identificador se guarda **hasheado**: en la cola de la caché pueden
    acabar correos y nombres de usuario, y esa caché es compartida y volcable.
    Un hash basta porque solo necesitamos comparar, nunca leer el original.
    """
    digest = hashlib.sha256(identificador.strip().lower().encode('utf-8')).hexdigest()
    return f'rl:{ambito}:{digest}'


def consumir(ambito: str, identificador: str, limite: int) -> bool:
    """Registra un intento y dice si TODAVÍA está permitido.

    Devuelve True si el intento cabe dentro del límite, False si ya lo superó.

    El contador se incrementa siempre, también cuando ya está bloqueado: así una
    ráfaga no "descansa" sola mientras siga golpeando. Ojo con el patrón
    `add` + `incr`: es el único que fija el TTL una vez y no lo renueva en cada
    intento (con `set` la ventana se estiraría indefinidamente y el bloqueo sería
    perpetuo).
    """
    if not identificador:
        return True

    clave = _clave(ambito, identificador)
    # `add` solo escribe si la clave no existía: ahí es donde nace la ventana.
    if cache.add(clave, 1, VENTANA_SEGUNDOS):
        return True

    try:
        intentos = cache.incr(clave)
    except ValueError:
        # La clave caducó entre el `add` y el `incr`. Es el comienzo de una
        # ventana nueva, no un error.
        cache.add(clave, 1, VENTANA_SEGUNDOS)
        return True

    if intentos > limite:
        # Se registra el bloqueo, nunca el identificador: este log va a
        # CloudWatch y no debe filtrar correos ni nombres de usuario.
        logger.warning('LIMITE_PETICIONES_SUPERADO ambito=%s intentos=%s', ambito, intentos)
        return False
    return True


def limpiar(ambito: str, identificador: str) -> None:
    """Borra el contador. Se llama tras un éxito legítimo.

    Sin esto, alguien que se equivoca cuatro veces al escribir su contraseña
    actual, acierta a la quinta, y más tarde vuelve a equivocarse, se
    encontraría bloqueado por unos fallos que ya había resuelto.
    """
    if identificador:
        cache.delete(_clave(ambito, identificador))
