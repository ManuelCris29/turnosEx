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
