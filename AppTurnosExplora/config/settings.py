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

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': env('DB_NAME'),
        'USER': env('DB_USER'),
        'PASSWORD': env('DB_PASSWORD'),
        'HOST': env('DB_HOST', default='localhost'),
        'PORT': env('DB_PORT', default='3306'),
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

# ---------------------------------------------------------------------------
# Caché — LocMemCache en dev, Redis en prod (configurar CACHE_URL en .env)
# ---------------------------------------------------------------------------
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
AXES_LOCKOUT_PARAMETERS = ['username']
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
    SECURE_HSTS_SECONDS = 31536000          # 1 año
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# Logging estructurado
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'django.utils.log.ServerFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'solicitudes': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'turnos': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}

# ---------------------------------------------------------------------------
# Debug Toolbar (solo desarrollo)
# ---------------------------------------------------------------------------
if not IS_PRODUCTION:
    INTERNAL_IPS = ['127.0.0.1', 'localhost', '192.168.2.102']
