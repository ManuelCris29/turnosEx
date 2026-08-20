"""
Comprobaciones propias del proyecto para `manage.py check --deploy`.

Se ejecutan SOLO con la bandera --deploy (deploy=True), nunca en el arranque
normal ni en `collectstatic`. Eso es deliberado: el build de la imagen corre
collectstatic con ENVIRONMENT=production y sin CACHE_URL, y no debe fallar por
ello; lo que no puede pasar desapercibido es un despliegue real mal configurado.
"""
from django.conf import settings
from django.core.checks import Error, Tags, Warning, register

LOCMEM = 'django.core.cache.backends.locmem.LocMemCache'


@register(Tags.caches, deploy=True)
def cache_compartida_en_produccion(app_configs, **kwargs):
    """
    En producción la caché no puede ser local al proceso.

    LocMemCache vive en la memoria de un único worker de Gunicorn. La aplicación
    cachea el estado de Mis Turnos y lo invalida cuando cambia (aprobaciones,
    sanciones, permisos). Con varios workers, esa invalidación limpiaría solo el
    proceso que atendió la petición y los demás seguirían sirviendo datos viejos
    hasta una hora. Ver el bloque de caché en config/settings.py.
    """
    if not getattr(settings, 'IS_PRODUCTION', False):
        return []

    if settings.CACHES.get('default', {}).get('BACKEND') != LOCMEM:
        return []

    return [
        Error(
            'La caché en producción es LocMemCache (memoria de un solo proceso).',
            hint=(
                'Gunicorn corre varios workers y cada uno tendría su propia caché, '
                'así que invalidarla solo afectaría a uno y los demás servirían '
                'Mis Turnos desactualizado hasta una hora. Define CACHE_URL: '
                'redis://host:6379/1 (ElastiCache) o db://cache_appturnos '
                '(tabla en RDS, requiere "manage.py createcachetable").'
            ),
            id='core.E001',
        )
    ]


@register(Tags.security, deploy=True)
def tls_hacia_la_base_en_produccion(app_configs, **kwargs):
    """
    En producción la conexión a la base debería ir cifrada y verificada.

    Es un aviso, no un error: hay topologías válidas donde el cifrado lo
    resuelve otra capa. Pero el caso por defecto —app en ECS y base en RDS— deja
    credenciales y datos personales viajando en claro por la VPC si nadie lo
    configura. Estar dentro de una VPC es aislamiento, no cifrado.
    """
    if not getattr(settings, 'IS_PRODUCTION', False):
        return []

    opciones = settings.DATABASES.get('default', {}).get('OPTIONS', {})
    if opciones.get('ssl_ca'):
        return []

    return [
        Warning(
            'La conexión a la base de datos no usa TLS en producción.',
            hint=(
                'El tráfico entre la aplicación y RDS viaja sin cifrar. Define '
                'DB_SSL_CA con la ruta del bundle de Amazon; la imagen ya lo trae '
                'en /app/certs/rds-ca-global.pem (ver Dockerfile).'
            ),
            id='core.W002',
        )
    ]


@register(Tags.security, deploy=True)
def axes_ve_la_ip_real_del_cliente(app_configs, **kwargs):
    """
    Si se bloquea por IP detrás de un proxy, axes tiene que ver la IP REAL.

    `AXES_LOCKOUT_PARAMETERS` incluye 'ip_address' para frenar el credential
    stuffing: sin él, un atacante rota nombres de usuario y los 5 intentos por
    usuario no suponen límite alguno.

    Pero cuando hay un intermediario delante (Nginx en el camino EC2, ALB en el de
    Fargate), la IP que Django ve por defecto es la DEL INTERMEDIARIO, idéntica
    para toda la plantilla. Con el bloqueo por IP activado, eso significa que al
    quinto fallo de CUALQUIER empleado quedarían bloqueados TODOS durante una hora:
    una denegación de servicio total provocada por la propia protección.

    `AXES_IPWARE_PROXY_COUNT` le dice a axes cuántos intermediarios saltar en la
    cabecera X-Forwarded-For. Este check impide desplegar con la combinación
    peligrosa: producción + proxy + bloqueo por IP + sin contar los proxies.

    Se detecta el proxy por `SECURE_PROXY_SSL_HEADER`, que solo se define cuando
    la app corre detrás de uno que termina el TLS.
    """
    if not getattr(settings, 'IS_PRODUCTION', False):
        return []

    bloquea_por_ip = 'ip_address' in _parametros_de_bloqueo()
    if not bloquea_por_ip:
        return []

    hay_proxy = bool(getattr(settings, 'SECURE_PROXY_SSL_HEADER', None))
    proxies_contados = getattr(settings, 'AXES_IPWARE_PROXY_COUNT', None)

    if not hay_proxy or proxies_contados:
        return []

    return [
        Error(
            'axes bloquea por IP detrás de un proxy sin contar los proxies: '
            'bloquearía a TODA la plantilla a la vez.',
            hint=(
                'SECURE_PROXY_SSL_HEADER está definido (hay un balanceador o Nginx '
                'delante), AXES_LOCKOUT_PARAMETERS incluye "ip_address" y '
                'AXES_IPWARE_PROXY_COUNT vale 0 o no está definido. Así axes ve la IP '
                'del intermediario para todos los usuarios y 5 fallos de cualquiera '
                'bloquean a todos. Define AXES_IPWARE_PROXY_COUNT=1 (un solo '
                'intermediario: Nginx o ALB) y verifica en staging que '
                'axes.helpers.get_client_ip_address devuelve la IP real del cliente.'
            ),
            id='core.E003',
        )
    ]


@register(deploy=True)
def axes_puede_leer_la_ip_reenviada(app_configs, **kwargs):
    """
    `AXES_IPWARE_PROXY_COUNT` puede estar puesto y NO HACER NADA. Dos motivos:

    1. django-ipware no está instalado. axes lo trae como EXTRA opcional
       (`django-axes[ipware]`); sin él, `get_client_ip_address` ignora todos los
       ajustes AXES_IPWARE_* y devuelve `REMOTE_ADDR` directamente
       (axes/helpers.py: `if use_ipware:` ... else fallback).
    2. `AXES_IPWARE_META_PRECEDENCE_ORDER` no incluye 'HTTP_X_FORWARDED_FOR'. Su
       valor por defecto en axes es `("REMOTE_ADDR",)`, así que ni con ipware
       instalado se llega a mirar la cabecera que trae la IP del cliente.

    En ambos casos axes ve la IP DEL BALANCEADOR para toda la plantilla, que es
    exactamente lo que `core.E003` pretende evitar. Sin este check, E003 da luz
    verde a una configuración inerte: el peor resultado posible, porque la
    protección parece puesta y no lo está. Se descubrió con
    `manage.py verificar_ip_cliente`, que ejecuta la resolución REAL en vez de
    leer los ajustes.

    Por eso este check exige que, si se declara que hay proxies, la resolución de
    IP funcione de verdad.
    """
    if not getattr(settings, 'IS_PRODUCTION', False):
        return []

    if 'ip_address' not in _parametros_de_bloqueo():
        return []

    if not getattr(settings, 'AXES_IPWARE_PROXY_COUNT', None):
        return []  # de esa combinación ya responde core.E003

    # Un AXES_CLIENT_IP_CALLABLE propio sustituye a ipware por completo.
    if getattr(settings, 'AXES_CLIENT_IP_CALLABLE', None):
        return []

    try:
        import ipware.ip  # noqa: F401
        ipware_ok = True
    except ImportError:
        ipware_ok = False

    cabeceras = getattr(settings, 'AXES_IPWARE_META_PRECEDENCE_ORDER', ('REMOTE_ADDR',))
    lee_reenviada = 'HTTP_X_FORWARDED_FOR' in tuple(cabeceras)

    if ipware_ok and lee_reenviada:
        return []

    if not ipware_ok:
        causa = ('django-ipware NO está instalado, así que axes ignora '
                 'AXES_IPWARE_PROXY_COUNT y usa REMOTE_ADDR.')
        arreglo = 'Instala el extra:  django-axes[ipware]==7.0.1  en requirements.txt.'
    else:
        causa = ("AXES_IPWARE_META_PRECEDENCE_ORDER no incluye 'HTTP_X_FORWARDED_FOR' "
                 "(por defecto axes solo mira REMOTE_ADDR).")
        arreglo = ("Define AXES_IPWARE_META_PRECEDENCE_ORDER = "
                   "['HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR'].")

    return [
        Error(
            'AXES_IPWARE_PROXY_COUNT está configurado pero axes NO puede leer la IP '
            'real del cliente: el bloqueo por IP alcanzaría a toda la plantilla.',
            hint=f'{causa} {arreglo} Comprueba el resultado con: '
                 f'python manage.py verificar_ip_cliente',
            id='core.E004',
        )
    ]


def _parametros_de_bloqueo():
    """
    Aplana AXES_LOCKOUT_PARAMETERS, que admite dos formas.

    Lista plana  ['username', 'ip_address']    -> cada criterio cuenta por separado.
    Lista anidada [['username', 'ip_address']] -> cuenta la PAREJA.

    Para saber si la IP participa en la decisión da igual la forma, así que se
    recorren ambas por igual.
    """
    parametros = getattr(settings, 'AXES_LOCKOUT_PARAMETERS', []) or []
    planos = []
    for parametro in parametros:
        if isinstance(parametro, str):
            planos.append(parametro)
        else:
            planos.extend(parametro)
    return planos
