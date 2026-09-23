"""
Django settings para AppTurnos.

Lee configuración sensible desde .env (nunca hardcodeada aquí).
ENVIRONMENT=development → configuración local con debug toolbar.
ENVIRONMENT=production  → seguridad completa, sin debug.
"""
import os
from pathlib import Path

import environ
from whitenoise.compress import Compressor as _CompresorWhiteNoise

# ---------------------------------------------------------------------------
# Rutas base
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Leer .env
# ---------------------------------------------------------------------------
env = environ.Env(
    DEBUG=(bool, False),
    ENVIRONMENT=(str, 'development'),
)
environ.Env.read_env(BASE_DIR / '.env')

ENVIRONMENT = env('ENVIRONMENT')
IS_PRODUCTION = ENVIRONMENT == 'production'

# ---------------------------------------------------------------------------
# Seguridad
# ---------------------------------------------------------------------------
SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['127.0.0.1', 'localhost'])

# Orígenes de confianza para CSRF (Django 5 lo exige en POST/AJAX por HTTPS).
# En producción: https://tu-dominio. Vacío en desarrollo.
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

# ---------------------------------------------------------------------------
# Aplicaciones
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Terceros
    'corsheaders',
    'axes',
    'simple_history',
    'widget_tweaks',
    # Apps propias
    'core.login',
    'core.dashboard',
    'empleados',
    'solicitudes',
    'permisos',
    'turnos',
]

if not IS_PRODUCTION:
    INSTALLED_APPS += ['debug_toolbar']

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    'core.errors.RequestIDMiddleware',              # etiqueta la petición: debe ir arriba del todo
    'corsheaders.middleware.CorsMiddleware',       # debe ir primero
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',   # sirve estáticos sin Nginx (contenedores)
    # Comprime el HTML. Los estáticos ya iban comprimidos (WhiteNoise los sirve
    # pregenerados), pero la respuesta de gunicorn viajaba EN CRUDO: medido en
    # producción el 2026-09-20, ni un `Content-Encoding` en la respuesta de una
    # página. Y el HTML no se cachea nunca (`no-store`, lleva datos de sesión),
    # así que ese coste se paga ENTERO en cada navegación. En estas plantillas
    # pesa: el sidebar de base.html son ~300 líneas de menú que se repiten en
    # todas las páginas y comprimen muy bien.
    #
    # VA DEBAJO DE WHITENOISE A PROPÓSITO. WhiteNoise atiende las peticiones de
    # estáticos y devuelve ahí mismo, sin bajar más: así este middleware nunca
    # las ve. Puesto por encima, intentaría recomprimir lo ya comprimido y, peor,
    # gastaría CPU comprimiendo PNG y woff2, que no se comprimen más.
    #
    # SOBRE BREACH: es el motivo por el que la documentación de Django avisa
    # sobre este middleware. Desde Django 4.2 el propio framework aplica
    # «Heal The Breach», que añade bytes aleatorios a la respuesta comprimida
    # para romper la correlación tamaño↔contenido de la que vive ese ataque.
    # Además el token CSRF ya va enmascarado por petición. Con eso, el riesgo
    # residual no compensa servir el HTML sin comprimir a 300 empleados que
    # entran desde el celular.
    'django.middleware.gzip.GZipMiddleware',
    # `Cache-Control: no-store` en las respuestas que NO son HTML (las 81
    # JsonResponse del proyecto). Va aquí arriba a propósito: las respuestas
    # suben por la lista, así que este es de los últimos en mirarlas y ve el
    # `Cache-Control` que haya puesto cualquiera por debajo, incluido el
    # `@never_cache` de las vistas. Y va DEBAJO de WhiteNoise porque los
    # estáticos ni llegan hasta aquí: WhiteNoise los resuelve y devuelve arriba.
    # Ver el docstring en core/middleware.py, que explica por qué el HTML se
    # queda fuera (bfcache).
    'core.middleware.SinCacheEnDatosMiddleware',
    'csp.middleware.CSPMiddleware',                 # aplica Content-Security-Policy
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'simple_history.middleware.HistoryRequestMiddleware',
    'axes.middleware.AxesMiddleware',               # debe ir al final
    'core.middleware.AperturaAnioMiddleware',       # bloquea al supervisor si falta planificar el año
    'core.middleware.PermisoSesionMiddleware',      # niega la URL de una sesión deshabilitada
]

if not IS_PRODUCTION:
    # Va JUSTO DESPUES de GZipMiddleware, no al principio de la lista.
    # debug_toolbar inyecta su panel en el HTML de la respuesta, asi que necesita
    # verla SIN COMPRIMIR: por encima del gzip solo veria bytes comprimidos y no
    # podria insertar nada. El propio paquete lo comprueba y avisa (W003).
    # Se busca por nombre en vez de fijar un indice para que mover cualquier otro
    # middleware no vuelva a descolocarlo en silencio.
    _i_gzip = MIDDLEWARE.index('django.middleware.gzip.GZipMiddleware')
    MIDDLEWARE.insert(_i_gzip + 1, 'debug_toolbar.middleware.DebugToolbarMiddleware')

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates'),
            os.path.join(BASE_DIR, 'core', 'login', 'template'),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.permisos',
                'core.context_processors.sesiones_permitidas',
                'core.context_processors.mensajes_comentario',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
try:
    import MySQLdb  # noqa: F401
except ImportError:
    import pymysql
    pymysql.install_as_MySQLdb()

# --- Conexiones persistentes -----------------------------------------------
# Por defecto Django abre y cierra una conexión a la base EN CADA petición. Con
# RDS al otro lado de la red (y más aún con TLS, que añade su propio handshake)
# eso son decenas de milisegundos regalados por petición y presión innecesaria
# sobre `max_connections`. CONN_MAX_AGE reutiliza la conexión durante N segundos.
#
# En desarrollo el valor por defecto es 0 (comportamiento de siempre: runserver
# recarga código constantemente y las conexiones vivas estorban más que ayudan).
# En producción, 60 s.
#
# CONN_HEALTH_CHECKS es el acompañante OBLIGATORIO de lo anterior: una conexión
# reutilizada puede haber muerto por su cuenta (timeout de MySQL, failover de
# RDS, reinicio). Sin esta bandera, Django la usaría igualmente y la petición
# reventaría con un error de conexión; con ella la comprueba y la reabre si hace
# falta. Activar CONN_MAX_AGE sin esto cambia un coste de rendimiento por
# errores 500 intermitentes.
DB_CONN_MAX_AGE = env.int('DB_CONN_MAX_AGE', default=60 if IS_PRODUCTION else 0)

# --- TLS hacia la base de datos ---------------------------------------------
# Sin esto, el tráfico entre la aplicación y RDS viaja EN CLARO por la VPC:
# credenciales, turnos, datos personales de los empleados. Estar dentro de una
# VPC no es cifrado, solo aislamiento.
#
# Se activa indicando la ruta del certificado de la autoridad de Amazon:
#     DB_SSL_CA=/app/certs/rds-ca-global.pem
# El Dockerfile ya deja ese bundle en la imagen. Vacío (desarrollo) = sin TLS.
#
# `ssl_verify_cert` + `ssl_verify_identity` son lo que separa "cifrado" de
# "cifrado Y verificado": sin ellos se cifraría la conexión pero se aceptaría
# cualquier servidor que se hiciera pasar por la base. Parámetros de PyMySQL,
# que es el driver del proyecto.
DB_SSL_CA = env('DB_SSL_CA', default='')

DB_OPTIONS = {}
if DB_SSL_CA:
    DB_OPTIONS = {
        'ssl_ca': DB_SSL_CA,
        'ssl_verify_cert': True,
        'ssl_verify_identity': True,
    }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='3306'),
        'CONN_MAX_AGE': DB_CONN_MAX_AGE,
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': DB_OPTIONS,
        # Nombre de la base de TEST, configurable.
        #
        # Por defecto Django usa 'test_' + NAME, un nombre FIJO y compartido por toda corrida.
        # Combinado con `NoInputDiscoverRunner` (interactive=False → "borrar y recrear" sin
        # preguntar), dos ejecuciones simultáneas de la suite se destruyen mutuamente: la segunda
        # borra la base que la primera está usando y esta falla en masa, con errores que parecen
        # bugs del código y no lo son.
        #
        # Con TEST_DB_NAME cada corrida puede aislarse:
        #     TEST_DB_NAME=test_bdturnosex_2 python -m pytest ...
        # El valor por defecto reproduce el nombre de siempre, así que nada cambia si no se usa.
        # (Con pytest-xdist no hace falta: pytest-django le añade el sufijo _gwN a cada worker.)
        'TEST': {
            'NAME': env('TEST_DB_NAME', default=f"test_{env('DB_NAME')}"),
        },
    }
}

# Runner de tests: igual que el de Django pero sin preguntar nunca por consola. Evita que una
# base `test_*` huérfana (de una corrida que murió a medias) deje colgada la siguiente ejecución
# esperando un "yes" que nadie puede escribir. Ver `core/test_runner.py`.
TEST_RUNNER = 'core.test_runner.NoInputDiscoverRunner'

# ---------------------------------------------------------------------------
# Validación de contraseñas
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# ---------------------------------------------------------------------------
# Internacionalización
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Archivos estáticos
# ---------------------------------------------------------------------------
STATIC_URL = 'static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# WhiteNoise sirve los estáticos (no hay Nginx dentro del contenedor), pero su
# middleware por sí solo los entrega SIN COMPRIMIR y con caché débil. Medido en
# producción antes de este cambio: 2,3 MB por carga, `transferred` practicamente
# igual que `resources` (cero compresión) y estáticos respondiendo 200 en cada
# navegación, es decir, redescargados enteros en cada clic del menú.
#
# `CompressedManifestStaticFilesStorage` arregla las dos cosas en `collectstatic`:
#   - Pregenera versiones gzip/brotli: el CSS y el JS bajan a una fracción.
#   - Renombra cada archivo con un hash de su contenido, lo que permite servirlos
#     con caché inmutable: el navegador deja de preguntar por ellos. Importa
#     especialmente para los 300 empleados que entran desde el celular.
#
# POR QUE LA VARIANTE SIN `Manifest`
# Se probó primero `CompressedManifestStaticFilesStorage`, que además del gzip/brotli
# renombra cada archivo con un hash y permite servirlo con caché inmutable. Es la
# opción mejor, pero es ESTRICTA: verifica todas las referencias entre estáticos y
# `collectstatic` falla si alguna no resuelve. Con los plugins de terceros que trae
# `static/` aparecieron varias, y la última (jquery-ui) no es ni siquiera un archivo
# que falte —la imagen existe— sino el analizador de Django tragándose las comillas
# de `url("images/...")`. No compensa bloquear el despliegue por eso.
#
# Esta variante comprime igual (que era el problema medido: 2,3 MB por carga sin
# comprimir) y no toca las referencias.
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

# ---------------------------------------------------------------------------
# Caché de estáticos: un año — y por qué aquí SÍ se puede
# ---------------------------------------------------------------------------
# Sin nombres con hash, WhiteNoise aplica `max-age=60`. Es su criterio prudente y
# es el correcto por defecto: si no puede distinguir una versión de otra, no se
# atreve a dejar que el navegador se quede nada. Medido en producción el
# 2026-09-20, antes de este cambio:
#
#     $ curl -I https://swalp.parqueexplora.org/static/css/adminlte.min.css
#     Cache-Control: max-age=60, public
#     Content-Encoding: gzip
#
# La compresión ya estaba (commit e519771). Lo que quedaba era esto: al minuto de
# navegar, el navegador vuelve a preguntar por los ~14 estáticos de CADA página.
# Responden 304 y casi no gastan bytes, así que en una gráfica de tamaño no se
# ven — pero cada uno cuesta un viaje de ida y vuelta completo. Ahí está la
# diferencia que se reportó: en wifi un viaje son ~20 ms y nadie lo nota; en
# datos móviles son 100-200 ms, y catorce seguidos son segundos de espera en
# cada clic del menú. El problema nunca fue el ancho de banda: era la latencia
# multiplicada por el número de recursos.
#
# POR QUÉ UN AÑO NO ES TEMERARIO AQUÍ
# Normalmente, caché larga sin hash en el nombre es una forma segura de servir
# una versión vieja para siempre. Aquí no, porque el versionado ya existe por
# otra vía: `static_v` añade `?v=<mtime>` a la URL (ver
# solicitudes/templatetags/static_version.py). Si el archivo cambia, cambia su
# mtime, cambia la URL, y para el navegador es un recurso distinto que tiene que
# bajar. La caché larga no puede dejar servido nada viejo.
#
# 🔴 LA CONDICIÓN, Y ES ESTRICTA
# Esto solo se sostiene si TODA referencia a un estático pasa por `static_v`. Un
# `{% static %}` a secas, o un "/static/..." escrito a mano en el HTML, produce
# una URL fija que ahora se cachea un año: ese archivo se congela en el navegador
# de cada empleado y NO hay despliegue que lo actualice. Es el modo de fallo de
# este cambio, y es silencioso.
# Las 29 referencias que quedaban sueltas se convirtieron junto con este commit,
# y `core/tests/test_estaticos_versionados.py` falla si alguien reintroduce una.
#
# Subir a `CompressedManifestStaticFilesStorage` (hash en el nombre, que haría
# innecesaria esa disciplina) sigue siendo la opción de libro, y sigue bloqueada
# por lo mismo que la tumbó la vez pasada: las referencias rotas de los plugins
# vendorizados hacen fallar `collectstatic`. Esta ruta da el mismo resultado
# medible sin ese riesgo en el build.
WHITENOISE_MAX_AGE = 31536000  # 1 año

# ---------------------------------------------------------------------------
# No comprimir los source maps
# ---------------------------------------------------------------------------
# WhiteNoise se salta por defecto lo que ya viene comprimido (png, woff2, zip…).
# Los .map no están en esa lista, y hace bien en no asumirlo: son JSON y
# comprimen muy bien. Pero en ESTE proyecto son 64 MB de mapas de AdminLTE y
# pdfmake que ningún empleado descarga jamás — el navegador solo los pide con
# las herramientas de desarrollo abiertas.
#
# Comprimirlos cuesta, medido aquí el 2026-09-20: brotli en calidad 11 tarda
# ~73 s sobre esos 64 MB (gzip, ~1 s; brotli q11 es lento a propósito). Son 73 s
# añadidos a CADA build de la imagen, y a cambio nadie descarga el resultado.
# Antes no se notaba porque sin el paquete `brotli` esa compresión ni ocurría.
#
# Los .map SE SIGUEN SIRVIENDO, solo que sin versión pregenerada: si alguien
# depura en producción, los recibe igual (sin comprimir, y le da igual).
#
# Se parte de la lista de la propia librería en vez de copiarla, para heredar
# los formatos que añada en el futuro sin tener que enterarse.
WHITENOISE_SKIP_COMPRESS_EXTENSIONS = (
    *_CompresorWhiteNoise.SKIP_COMPRESS_EXTENSIONS,
    'map',
)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

# Vida del enlace de "olvidé mi contraseña". El valor por defecto de Django son
# TRES DÍAS: una llave de la cuenta viajando por correo y válida 72 horas. Si el
# buzón se ve comprometido en esa ventana, la cuenta cae detrás. Media hora es de
# sobra para ir a leer un correo, y el propio mensaje lo anuncia.
PASSWORD_RESET_TIMEOUT = env.int('PASSWORD_RESET_TIMEOUT', default=1800)

# Sesiones en base de datos (el valor por defecto de Django, explícito aquí a
# propósito). Con el backend de cookie firmada, cambiar la contraseña NO echaría
# a quien tenga la cuenta tomada desde otro dispositivo, que es justo lo que se
# espera de un cambio de contraseña: su sesión seguiría viva hasta caducar.
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
# Configurable para poder probar el flujo de recuperación de contraseña sin un
# SMTP delante: con `django.core.mail.backends.console.EmailBackend` el correo
# —enlace incluido— se imprime en la consola del runserver.
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')

# Timeout para que un SMTP colgado no congele el request (segundos).
EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=10)

# ---------------------------------------------------------------------------
# Saludo HELO/EHLO propio, para el relay SMTP de Google Workspace
# ---------------------------------------------------------------------------
# El relay autenticado por IP de Workspace exige ADEMÁS que el saludo
# HELO/EHLO presente uno de los dominios registrados de la cuenta. El backend
# SMTP de Django, si no se le indica nada, usa `socket.getfqdn()` para ese
# saludo — y dentro de un contenedor Docker eso devuelve el hostname
# aleatorio del contenedor (p. ej. '9e409ec3e672'), no un dominio de la
# empresa. Google lo rechaza con:
#
#   550-5.7.1 Invalid credentials for relay [IP]. [...] you must configure
#   your mail server [...] to present one of your domain names in the HELO
#   or EHLO command.
#
# `django.core.mail.utils.DNS_NAME` es el objeto que el backend SMTP consulta
# para ese saludo (cachea el resultado en `_fqdn` la primera vez que se pide).
# Fijarlo aquí, una sola vez al arrancar, evita escribir un backend SMTP
# propio solo para cambiar una línea del protocolo.
from django.core.mail.utils import DNS_NAME  # noqa: E402

DNS_NAME._fqdn = env('EMAIL_LOCAL_HOSTNAME', default='parqueexplora.org')

# Enviar los correos fuera del request (tras commit, en un hilo) para no
# bloquear la respuesta ~20 s con los handshakes SMTP. Se activa en producción;
# en desarrollo/tests se envía síncrono para que el comportamiento sea determinista.
EMAIL_SEND_ASYNC = env.bool('EMAIL_SEND_ASYNC', default=IS_PRODUCTION)

SITE_URL = env('SITE_URL', default='http://127.0.0.1:8000')

# Vida de los enlaces de aprobación/rechazo que viajan en el correo. Esos enlaces
# actúan SIN sesión iniciada: el token firmado es la única credencial, así que
# caduca. 30 días cubre de sobra el plazo real de respuesta a una solicitud.
#
# La firma usa SECRET_KEY (ver solicitudes/services/tokens_aprobacion.py). En AWS
# eso obliga a que TODAS las instancias compartan la misma SECRET_KEY, y rotarla
# invalida los enlaces ya enviados.
APPROVAL_LINK_MAX_AGE_DAYS = env.int('APPROVAL_LINK_MAX_AGE_DAYS', default=30)

# ---------------------------------------------------------------------------
# Caché — se elige con CACHE_URL
#
# POR QUÉ ESTO IMPORTA MÁS DE LO QUE PARECE
# LocMemCache vive en la memoria de UN proceso. Gunicorn arranca varios workers
# (--workers 3) y cada uno tendría su propia caché, invisible para los demás.
# Como aquí la caché no guarda adornos sino el estado de Mis Turnos
# (turnos/api/views/turnos_mes.py cachea `turnos_mes_<emp>_<año>_<mes>` 1 hora)
# y ese estado se invalida al aprobar solicitudes, levantar sanciones, etc.
# (CacheService.invalidar_cache_turnos_empleado), con varios procesos la
# invalidación solo limpiaría el worker que atendió esa petición. Los otros
# seguirían sirviendo el mes viejo hasta una hora: el explorador vería su turno
# corregido o sin corregir según a qué worker lo mande el balanceador, y al
# refrescar cambiaría. Con varias tareas en ECS, peor.
#
# Regla: en producción con más de un worker, la caché DEBE ser compartida.
#
# Valores de CACHE_URL:
#   (vacío)                     → LocMemCache. Solo desarrollo (runserver, 1 proceso).
#   db://cache_appturnos        → tabla en la propia MySQL/RDS. ← ELEGIDA en
#                                 producción (2026-09-04). Cuesta $0 y exige
#                                 crear la tabla una vez:
#                                     python manage.py createcachetable
#   redis://host:6379/1         → ElastiCache/Redis. Descartado: ~$12/mes se sale
#                                 del presupuesto del proyecto. Se reconsidera
#                                 solo con >=2 instancias web.
#   rediss://host:6379/1        → igual, con TLS (cifrado en tránsito).
#
# El backend de Redis es el nativo de Django 5 (no hace falta django-redis),
# pero sí el cliente `redis` — ya está en requirements.txt.
# ---------------------------------------------------------------------------
CACHE_URL = env('CACHE_URL', default='')

if CACHE_URL.startswith(('redis://', 'rediss://')):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': CACHE_URL,
            'TIMEOUT': 3600,
        }
    }
elif CACHE_URL.startswith('db://'):
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': CACHE_URL[len('db://'):] or 'cache_appturnos',
            'TIMEOUT': 3600,
            'OPTIONS': {
                'MAX_ENTRIES': 10000,
                'CULL_FREQUENCY': 3,
            },
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'appturnos',
            'TIMEOUT': 3600,
            'OPTIONS': {
                'MAX_ENTRIES': 10000,
                'CULL_FREQUENCY': 3,
            },
        }
    }

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list(
    'CORS_ALLOWED_ORIGINS',
    default=['http://localhost:8000', 'http://127.0.0.1:8000'],
)
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# django-axes: bloqueo por intentos fallidos de login
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1

# 🔴 EL BLOQUEO POR IP ES OPCIONAL Y VIENE APAGADO. NO SE ENCIENDE SIN MEDIRLO.
#
# Lista PLANA = cada criterio cuenta por separado (bloqueo por usuario O por IP).
# NO confundir con la anidada [['username', 'ip_address']], que cuenta la PAREJA:
# esa no frena a quien rota nombres de usuario desde la misma IP, que es
# justamente el ataque que se quiere cortar (credential stuffing).
#
# Añadir 'ip_address' solo protege si la aplicación ve IPs DISTINTAS para personas
# distintas. Si las ve iguales, ese criterio deja de discriminar y se convierte en
# su contrario: cinco fallos de cualquiera bloquean a TODA la plantilla una hora.
# Una denegación de servicio provocada por la propia protección.
#
# Medido en el despliegue de Dokploy el 2026-09-18: el cortafuegos corporativo
# enmascara el origen (NAT de origen) y no reenvía la IP real, así que Traefik pone
# en X-Forwarded-For la puerta de enlace `10.1.0.1` PARA TODO EL MUNDO. Ahí el
# criterio de IP no protegía de nada y solo podía hacer daño. Ver la nota de
# AXES_IPWARE_PROXY_COUNT, más abajo, para las dos causas que hubo que descartar
# antes de llegar a esta.
#
# Por eso el valor por defecto es APAGADO y no encendido: una protección que puede
# dejar fuera a los 300 empleados no se activa por inercia, se activa después de
# comprobar que distingue. El procedimiento está en:
#   python manage.py verificar_ip_cliente
# y lo único que cierra el asunto es entrar desde DOS REDES DISTINTAS y ver dos IPs
# públicas diferentes en /admin/axes/accesslog/.
#
# Para reactivarlo cuando IT deje de enmascarar el origen:  AXES_BLOQUEAR_POR_IP=True
AXES_BLOQUEAR_POR_IP = env.bool('AXES_BLOQUEAR_POR_IP', default=False)
AXES_LOCKOUT_PARAMETERS = (['username', 'ip_address'] if AXES_BLOQUEAR_POR_IP
                           else ['username'])

# ⚠ CRÍTICO cuando hay un intermediario delante (Nginx en EC2, ALB en Fargate).
#
# Sin esto, axes ve la IP DEL INTERMEDIARIO para todo el mundo: al quinto fallo de
# CUALQUIER empleado quedaría bloqueada la plantilla ENTERA durante una hora. Es
# el motivo por el que 'ip_address' no se había activado antes.
#
# El valor es 1 en las dos arquitecturas candidatas —Nginx en el camino EC2, ALB en
# el de Fargate— y ninguna contempla CloudFront. Si algún día se añade un segundo
# intermediario, este número SUBE o el bloqueo por IP vuelve a ser inservible.
# En desarrollo no hay proxy: 0.
#
# VERIFICAR EN STAGING antes de producción:
#   python manage.py verificar_ip_cliente
# debe decir que axes ve la IP real del cliente, no la del balanceador.
AXES_IPWARE_PROXY_COUNT = env.int('AXES_IPWARE_PROXY_COUNT', default=1 if IS_PRODUCTION else 0)

# Sin esto, lo de arriba NO SIRVE DE NADA, y es un fallo silencioso.
#
# El valor por defecto de axes es ("REMOTE_ADDR",) —solo la IP de la conexión—, así
# que aunque django-ipware esté instalado y el número de proxies sea correcto, axes
# nunca miraría X-Forwarded-For y seguiría viendo la IP del balanceador para todo el
# mundo. Se detectó al escribir `verificar_ip_cliente`: la configuración "correcta"
# resolvía la IP del ALB.
#
# Se activa SOLO cuando hay un intermediario delante, y el motivo es de seguridad, no
# de limpieza: si se confía en X-Forwarded-For sin proxy, cualquier cliente puede
# inventarse la cabecera y cambiar de "IP" en cada intento, con lo que el bloqueo por
# IP deja de existir. Con proxy, el balanceador reescribe la cabecera y el cliente no
# la controla.
#
# 🔴 ANTES ESTO COLGABA DE `AXES_IPWARE_PROXY_COUNT`, Y ERA UN ERROR.
# Son dos preguntas distintas y acoplarlas rompió el bloqueo por IP en producción:
#
#   ¿HAY un proxy delante?          -> decide si se mira X-Forwarded-For
#   ¿CUÁNTAS direcciones trae?      -> es `AXES_IPWARE_PROXY_COUNT`
#
# ipware valida en modo ESTRICTO con una igualdad exacta
# (`len(ips) - 1 == proxy_count`, python_ipware.py), y Traefik pone en la cabecera
# UNA sola dirección: la del cliente. O sea CERO proxies por delante del cliente
# dentro del propio encabezado, aunque físicamente haya un proxy. Medido en el
# despliegue de Dokploy el 2026-09-18:
#
#   PROXY_COUNT=1  -> ipware descarta la cabecera (1-1=0, esperaba 1) y también
#                     REMOTE_ADDR -> devuelve NULO. Todos los intentos quedaron con
#                     ip_address vacía, o sea TODOS en el mismo grupo.
#   PROXY_COUNT=0  -> con el acoplamiento viejo, esta línea no se ejecutaba y axes
#                     volvía a su valor por defecto ("REMOTE_ADDR",): la IP interna
#                     de Traefik (10.0.1.4) para toda la plantilla.
#
# Las dos ramas terminaban en el mismo desastre por caminos distintos: cinco fallos
# de cualquiera bloqueando a los 300. Por eso ahora depende de IS_PRODUCTION, que es
# la respuesta a "¿hay proxy delante?", y el conteo se ajusta aparte y SE MIDE.
AXES_LEER_IP_REENVIADA = env.bool('AXES_LEER_IP_REENVIADA', default=IS_PRODUCTION)
if AXES_LEER_IP_REENVIADA:
    AXES_IPWARE_META_PRECEDENCE_ORDER = ['HTTP_X_FORWARDED_FOR', 'REMOTE_ADDR']

AXES_RESET_ON_SUCCESS = True
AXES_VERBOSE = False

import sys as _sys

# Deshabilita axes durante los tests: con `manage.py test` ('test' en argv) y
# también bajo pytest (que NO pasa 'test' en argv). axes exige un `request` en
# authenticate(), que client.login() no provee en los tests.
if 'test' in _sys.argv or 'pytest' in _sys.modules:
    AXES_ENABLED = False

# ---------------------------------------------------------------------------
# Content Security Policy (CSP) — django-csp 4.0
#
# Qué hace: le dice al navegador desde qué orígenes puede ejecutar scripts,
# cargar estilos, fuentes, etc. Es la última defensa contra XSS: si alguien
# consigue inyectar un <script src="https://sitio-malicioso.com/..."> en una
# página, el navegador se NIEGA a ejecutarlo porque ese origen no está aquí.
# No sustituye al escapado de plantillas: lo respalda.
#
# MIGRACIÓN A ESTÁTICOS LOCALES: TERMINADA, Y AHORA SIN NINGÚN ORIGEN EXTERNO
# jsDelivr (flatpickr, chart.js, sweetalert2, fullcalendar), cdnjs (Font Awesome)
# e ionicons se autohospedan en static/plugins/ y ya no los referencia ninguna
# plantilla. La política estuvo en observación con una segunda cabecera
# REPORT-ONLY hasta confirmarlo; barridas las 116 plantillas, la report-only se
# borró y sus valores son ahora los que se aplican de verdad.
#
# El último que quedaba, Google Fonts, se retiró el 2026-09-20 —no se
# autohospedó: se eliminó—. AdminLTE ya declaraba la pila del sistema como
# reserva, así que no hacía falta descargar 58 KB de woff2 para que el texto se
# viera bien; se ahorran además los dos handshakes TLS que costaba. Por eso
# `style-src` y `font-src` ya no admiten nada de fuera.
#
# CONSECUENCIA: `default-src 'self'` es ahora literal. Ningún recurso de la
# aplicación sale del propio dominio. Si mañana algo necesita salir, hay que
# añadirlo aquí a mano y el test de abajo lo recordará.
#
# ---------------------------------------------------------------------------
# POR QUÉ SE QUEDA 'unsafe-inline' EN script-src (decisión, no pendiente)
#
# Debilita la CSP: permite ejecutar <script> escritos en el propio HTML y, sobre
# todo, manejadores en atributo (onclick, onerror). Quitarlo se evaluó a fondo y
# NO compensa:
#
#   * Los nonces solo cubren los 13 <script> inline. NO cubren los `onclick=` de
#     20 plantillas ni los `style="…"` de 72: para esos hay que reescribir el
#     marcado a addEventListener y a clases CSS. Son más de 90 plantillas
#     tocadas, con riesgo real de regresión visual y funcional.
#   * Y no cerraría ninguna amenaza viva. El renderizado en servidor está limpio
#     (2 usos de |safe, ambos sobre help_text de Django, que es una constante;
#     cero mark_safe), así que el XSS clásico de plantilla no existe aquí. El
#     único vector era el texto que llega sin escapar a los innerHTML del JS
#     propio, y ese se cerró por su origen: tras añadir AdminRequiredMixin a
#     EmpleadoEditView, ningún dato que un explorador controle llega ahí (los
#     nombres los escribe administración; `motivo` y `comentario` van a
#     textContent, que no interpreta HTML).
#
# Lo que la CSP SÍ aporta hoy, y por eso se mantiene: bloquea cargar scripts de
# cualquier origen externo, impide exfiltrar por fetch a otro dominio
# (connect-src 'self') y prohíbe que el sitio se embeba en un iframe ajeno
# (frame-ancestors 'none'). Son 15 líneas sin mantenimiento.
#
# Si algún día se rehace el frontend, ese es el momento de quitar 'unsafe-inline'
# y añadir nonces: hacerlo sobre el marcado actual es todo coste y ninguna
# ganancia.
#
# AL AÑADIR UN RECURSO EXTERNO NUEVO hay que incluir su origen aquí, o el
# navegador lo bloqueará SIN error de servidor (falla en silencio, solo se ve en
# la consola del navegador).
# ---------------------------------------------------------------------------
CONTENT_SECURITY_POLICY = {
    'DIRECTIVES': {
        'default-src': ["'self'"],
        'script-src': [
            "'self'", "'unsafe-inline'",
        ],
        'style-src': ["'self'", "'unsafe-inline'"],
        'font-src': ["'self'", 'data:'],
        'img-src': ["'self'", 'data:'],
        'connect-src': ["'self'"],
        'frame-ancestors': ["'none'"],
    }
}

# ---------------------------------------------------------------------------
# Cabeceras/cookies de seguridad — activas SIEMPRE (dev y prod)
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True          # X-Content-Type-Options: nosniff
X_FRAME_OPTIONS = 'DENY'                     # anti-clickjacking

# sessionid siempre HttpOnly (default de Django, explícito para el escáner).
# El csrftoken NO puede ser HttpOnly: api-client.js lo lee vía document.cookie
# para enviarlo en la cabecera X-CSRFToken de las llamadas AJAX.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'

# Vista propia para los fallos de CSRF. La de Django imprime el motivo exacto
# del rechazo; la nuestra lo registra en el log y al usuario le muestra un
# mensaje genérico de sesión expirada. Ver core/errors.py.
CSRF_FAILURE_VIEW = 'core.errors.csrf_failure'

# ---------------------------------------------------------------------------
# Seguridad adicional (requiere HTTPS)
# Activo por defecto en producción, pero desactivable con SECURE_HTTPS=False
# para poder probar la imagen de producción en local sobre HTTP.
# ---------------------------------------------------------------------------
SECURE_HTTPS = env.bool('SECURE_HTTPS', default=IS_PRODUCTION)
if SECURE_HTTPS:
    # El proxy (Nginx/ALB) termina el TLS y reenvía por HTTP; sin esto,
    # SECURE_SSL_REDIRECT provoca un bucle de redirección infinito.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True

    # Los health checks del ALB NO son tráfico de navegador: llegan por HTTP
    # directo al contenedor y sin la cabecera X-Forwarded-Proto. Sin esta
    # exención, SECURE_SSL_REDIRECT les responde 301 hacia https, el ALB lo lee
    # como "unhealthy", mata la tarea, arranca otra, y así indefinidamente: la
    # aplicación nunca llega a estar arriba. El patrón se compara contra la ruta
    # SIN la barra inicial. Ver core/health.py.
    SECURE_REDIRECT_EXEMPT = [r'^health/$', r'^health/ready/$']
    SECURE_HSTS_SECONDS = 31536000          # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# Logging estructurado
# ---------------------------------------------------------------------------
# Los errores NO se le muestran al usuario (ver core/errors.py y las plantillas
# 4xx/5xx): salen por aquí, y solo aquí. Dos destinos, a propósito:
#
#   consola  -> stdout. En ECS/Fargate el log driver `awslogs` recoge stdout y
#               lo publica en CloudWatch Logs sin ninguna dependencia extra.
#               Es la vía recomendada en AWS: si el contenedor muere, el driver
#               ya ha enviado lo que había.
#   fichero  -> logs/appturnos.log. SOLO EN DESARROLLO, por comodidad: poder
#               abrir el log sin depender de la consola donde corre runserver.
#               En producción NO se escribe fichero; el porqué está abajo, junto
#               a LOG_A_FICHERO.
#
# Cada línea lleva el request_id, así que buscar el código de referencia que el
# usuario ve en la página de error basta para reconstruir la petición entera:
#   aws logs filter-log-events --log-group-name /swalp/app \
#       --filter-pattern '"A3F91C2B"'
#
# RETENCIÓN: configúrala en el grupo de CloudWatch (no en el fichero). Estos
# logs contienen nombres de empleado y detalles de solicitudes, así que son
# datos personales: acótala y restringe el acceso al grupo por IAM.
# La ruta se puede reapuntar por entorno (p.ej. a un volumen montado que sí sea
# escribible cuando el contenedor arranca con el sistema de ficheros en solo
# lectura, que es lo recomendable en Fargate).
LOG_DIR = Path(env('LOG_DIR', default=str(BASE_DIR / 'logs')))

# EN PRODUCCIÓN NO SE ESCRIBE FICHERO. Tres razones, comprobadas sobre este
# despliegue y no heredadas de una costumbre:
#
#   1. No sobrevive. No hay ningún volumen montado para logs (ni en el Dockerfile
#      ni en los compose): el fichero vive en la capa efímera del contenedor y
#      desaparece entero cuando ECS reinicia la tarea. Un log que se borra solo
#      justo cuando ha pasado algo interesante no es un log.
#   2. No se puede leer. El `tail -f por SSH` que justificaba el fichero no existe
#      en Fargate: no hay máquina a la que entrar.
#   3. Y encima corrompe. Con `--workers 3` hay tres procesos con su propio
#      handler sobre el mismo fichero; al rotar, los tres renombran a la vez. En
#      Linux no da error: simplemente se pierden líneas y algún worker sigue
#      escribiendo en un fichero ya desenlazado, cuyo contenido no vuelve a
#      aparecer.
#
# O sea que se estaba pagando una condición de carrera por escribir en un disco
# que se borra solo. La información útil ya sale por stdout, que es de donde el
# log driver `awslogs` alimenta CloudWatch —y para lo que el Dockerfile ya fija
# PYTHONUNBUFFERED—.
#
# La aplicación emite eventos; DÓNDE se guardan es decisión de la plataforma. Por
# eso esto no se arregla con más configuración aquí, sino con menos.
if IS_PRODUCTION:
    LOG_A_FICHERO = False
else:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        LOG_A_FICHERO = os.access(LOG_DIR, os.W_OK)
    except OSError:
        # Sin permiso de escritura NO se cae la aplicación: se renuncia al fichero
        # y todo sale por stdout.
        LOG_A_FICHERO = False

_DESTINOS = ['console', 'file'] if LOG_A_FICHERO else ['console']

# SIN ROTACIÓN, en ningún entorno. No es un descuido:
#
# `RotatingFileHandler` no es seguro entre procesos, y aquí SIEMPRE hay varios
# escribiendo el mismo fichero: `runserver` levanta dos (el vigilante de cambios y
# el hijo que sirve) y `pytest -n 4` levanta cuatro. Al llegar a `maxBytes` cada uno
# intenta rotar con `os.rename`, y en Windows renombrar un fichero que otro proceso
# tiene abierto falla con `PermissionError: [WinError 32]`.
#
# No era un fallo aislado: con el fichero YA por encima del umbral, el intento se
# repetía en CADA línea de log y la consola quedaba inservible a base de
# tracebacks. En Linux no ocurre —ahí sí se puede renombrar un fichero abierto—, y
# por eso el CI nunca lo vio.
#
# Lo que falla es el RENAME, no la escritura: varios procesos pueden añadir al mismo
# fichero sin problema. Así que se usa un handler sin rotación y ya está. El fichero
# crece, pero son logs locales y desechables: si molesta, se borra la carpeta `logs/`
# (está en .gitignore).
#
# No se pone un nombre por PID —que también resolvería la contienda— porque crearía
# un fichero por cada ejecución de `manage.py`, y en una semana `logs/` sería un
# vertedero.
#

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'request_id': {
            '()': 'core.errors.RequestIDFilter',
        },
    },
    'formatters': {
        'json': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s',
        },
        'verbose': {
            'format': '[{asctime}] {levelname} {name} [{request_id}]: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
            'filters': ['request_id'],
        },
        'file': {
            # Sin rotación a propósito (ver arriba): este handler solo se usa en
            # desarrollo, donde el fichero es desechable, y `RotatingFileHandler`
            # no es seguro entre procesos.
            'class': 'logging.FileHandler',
            'filename': str(LOG_DIR / 'appturnos.log'),
            # `delay`: no abrir el fichero hasta que haya algo que escribir. Evita
            # crear un fichero vacío por cada proceso que solo importa settings.
            'delay': True,
            'encoding': 'utf-8',
            'formatter': 'verbose',
            'filters': ['request_id'],
        },
    },
    'root': {
        'handlers': _DESTINOS,
        'level': 'WARNING',
    },
    'loggers': {
        'solicitudes': {
            'handlers': _DESTINOS,
            'level': 'INFO',
            'propagate': False,
        },
        'turnos': {
            'handlers': _DESTINOS,
            'level': 'INFO',
            'propagate': False,
        },
        # Aquí aterrizan los 500 con su traceback completo. Es el logger que
        # sustituye a la pantalla de debug: mismo detalle, pero solo para el
        # equipo de desarrollo.
        'django.request': {
            'handlers': _DESTINOS,
            'level': 'ERROR',
            'propagate': False,
        },
        # Fallos de CSRF y peticiones rechazadas (Host no permitido, etc.).
        'django.security': {
            'handlers': _DESTINOS,
            'level': 'WARNING',
            'propagate': False,
        },
        'core.errors': {
            'handlers': _DESTINOS,
            'level': 'WARNING',
            'propagate': False,
        },
        # Eventos de contraseñas: solicitud de recuperación, enlace consumido,
        # cambio efectuado y límite de peticiones superado. En INFO a propósito:
        # sin estas líneas un ataque contra el reset no dejaría NINGUNA huella en
        # CloudWatch. Sobre ellas se puede montar después un metric filter, igual
        # que con REVISION_SANCIONES_NO_EJECUTADA.
        'core.seguridad': {
            'handlers': _DESTINOS,
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# ---------------------------------------------------------------------------
# Debug Toolbar (solo desarrollo)
# ---------------------------------------------------------------------------
if not IS_PRODUCTION:
    INTERNAL_IPS = ['127.0.0.1', 'localhost', '192.168.2.102']

    # El panel de perfilado usa cProfile, y solo puede haber un perfilador
    # activo a la vez. Como el runserver atiende peticiones en hilos y las
    # pantallas de solicitudes lanzan varias llamadas AJAX en paralelo, las
    # que coinciden revientan con "Another profiling tool is already active"
    # y devuelven 500. Se listan los paneles sin ProfilingPanel.
    DEBUG_TOOLBAR_PANELS = [
        'debug_toolbar.panels.history.HistoryPanel',
        'debug_toolbar.panels.versions.VersionsPanel',
        'debug_toolbar.panels.timer.TimerPanel',
        'debug_toolbar.panels.settings.SettingsPanel',
        'debug_toolbar.panels.headers.HeadersPanel',
        'debug_toolbar.panels.request.RequestPanel',
        'debug_toolbar.panels.sql.SQLPanel',
        'debug_toolbar.panels.staticfiles.StaticFilesPanel',
        'debug_toolbar.panels.templates.TemplatesPanel',
        'debug_toolbar.panels.alerts.AlertsPanel',
        'debug_toolbar.panels.cache.CachePanel',
        'debug_toolbar.panels.signals.SignalsPanel',
        'debug_toolbar.panels.redirects.RedirectsPanel',
    ]
