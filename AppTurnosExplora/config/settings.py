"""
Django settings para AppTurnos.

Lee configuración sensible desde .env (nunca hardcodeada aquí).
ENVIRONMENT=development → configuración local con debug toolbar.
ENVIRONMENT=production  → seguridad completa, sin debug.
"""
import os
from pathlib import Path
import environ

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
]

if not IS_PRODUCTION:
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')

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

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL')

# Timeout para que un SMTP colgado no congele el request (segundos).
EMAIL_TIMEOUT = env.int('EMAIL_TIMEOUT', default=10)

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
#   redis://host:6379/1         → ElastiCache/Redis. Opción recomendada en AWS.
#   rediss://host:6379/1        → igual, con TLS (ElastiCache con cifrado en tránsito).
#   db://cache_appturnos        → tabla en la propia MySQL/RDS. Sin infraestructura
#                                 extra, pero exige crear la tabla una vez:
#                                     python manage.py createcachetable
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

# Lista PLANA = cada criterio cuenta por separado (bloqueo por usuario O por IP).
# NO confundir con la anidada [['username', 'ip_address']], que cuenta la PAREJA:
# esa no frena a quien rota nombres de usuario desde la misma IP, que es
# justamente el ataque que se quiere cortar (credential stuffing).
#
# Antes era solo ['username']. Esa opción está documentada por axes como elección
# válida por privacidad/GDPR —evita almacenar IPs—, pero deja la puerta abierta:
# con 5 intentos por usuario y una lista de nombres, no hay límite efectivo.
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']

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
# Se activa SOLO cuando hay un intermediario declarado, y el motivo es de seguridad,
# no de limpieza: si se confía en X-Forwarded-For sin proxy delante, cualquier cliente
# puede inventarse la cabecera y cambiar de "IP" en cada intento, con lo que el bloqueo
# por IP deja de existir. Con proxy, el balanceador reescribe la cabecera y el cliente
# no la controla.
if AXES_IPWARE_PROXY_COUNT:
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
# 'unsafe-inline' se mantiene por los scripts/estilos inline ya existentes.
# Debilita la protección (permite <script> escritos en el propio HTML) y
# eliminarlo exige migrar esos inline a archivos o usar nonces.
#
# ESTADO DE LA MIGRACIÓN A ESTÁTICOS LOCALES
# Todos los recursos de cdn.jsdelivr.net (flatpickr, chart.js, sweetalert2,
# fullcalendar) se autohospedan en static/plugins/. Igual que ionicons, que no
# se usa en ninguna plantilla. La política ESTRICTA de abajo elimina esas tres
# entradas y se publica en modo REPORT-ONLY: el navegador informa de las
# violaciones en consola SIN bloquear nada. Cuando se confirme que no aparece
# ninguna, basta con mover ese diccionario a CONTENT_SECURITY_POLICY y borrar
# el permisivo. Sigue haciendo falta cdnjs (Font Awesome 6 en mis_turnos.html)
# y Google Fonts (base.html y el login).
# ---------------------------------------------------------------------------
CONTENT_SECURITY_POLICY = {
    'DIRECTIVES': {
        'default-src': ["'self'"],
        'script-src': [
            "'self'", "'unsafe-inline'",
            'https://cdn.jsdelivr.net',
        ],
        'style-src': [
            "'self'", "'unsafe-inline'",
            'https://cdn.jsdelivr.net',
            'https://cdnjs.cloudflare.com',
            'https://fonts.googleapis.com',
            'https://code.ionicframework.com',
        ],
        'font-src': [
            "'self'", 'data:',
            'https://fonts.gstatic.com',
            'https://cdnjs.cloudflare.com',
            'https://code.ionicframework.com',
        ],
        'img-src': ["'self'", 'data:'],
        'connect-src': ["'self'"],
        'frame-ancestors': ["'none'"],
    }
}

# Política objetivo, en observación. Se envía como cabecera
# Content-Security-Policy-Report-Only: NO bloquea, solo reporta en la consola
# del navegador.
#
# Ya no aparecen jsDelivr, cdnjs ni ionicons: ninguna plantilla los usa. Font Awesome
# se sirve desde `static/plugins/fontawesome-free` (5.15.4) para TODO el sitio, así que
# también cayó el único uso de cdnjs. Lo único externo que queda es Google Fonts.
CONTENT_SECURITY_POLICY_REPORT_ONLY = {
    'DIRECTIVES': {
        'default-src': ["'self'"],
        'script-src': [
            "'self'", "'unsafe-inline'",
        ],
        'style-src': [
            "'self'", "'unsafe-inline'",
            'https://fonts.googleapis.com',
        ],
        'font-src': [
            "'self'", 'data:',
            'https://fonts.gstatic.com',
        ],
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
#   fichero  -> logs/appturnos.log con rotación. Sobrevive a un fallo de red
#               con CloudWatch y permite un `tail -f` inmediato por SSH. El
#               CloudWatch Agent puede además vigilar este fichero si se quiere
#               un segundo grupo de logs con retención distinta.
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
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_A_FICHERO = os.access(LOG_DIR, os.W_OK)
except OSError:
    # Sin permiso de escritura NO se cae la aplicación: se renuncia al fichero
    # y todo sale por stdout, que es de donde tira CloudWatch de todos modos.
    LOG_A_FICHERO = False

_DESTINOS = ['console', 'file'] if LOG_A_FICHERO else ['console']

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
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'appturnos.log'),
            'maxBytes': 10 * 1024 * 1024,   # 10 MB
            'backupCount': 5,               # ~50 MB como techo
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
    },
}

# ---------------------------------------------------------------------------
# Debug Toolbar (solo desarrollo)
# ---------------------------------------------------------------------------
if not IS_PRODUCTION:
    INTERNAL_IPS = ['127.0.0.1', 'localhost', '192.168.2.102']
