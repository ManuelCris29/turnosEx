# syntax=docker/dockerfile:1
# Imagen de la app SWALP/AppTurnos para contenedores (ECS Fargate, App Runner
# o pruebas locales). Sirve estáticos con WhiteNoise (no hay Nginx dentro).
FROM python:3.12-slim

# Sin .pyc y salida sin buffer (logs inmediatos en CloudWatch).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias primero para aprovechar la caché de capas.
# PyMySQL es puro Python: no hacen falta compiladores ni libs de MySQL del sistema.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Certificados de las autoridades de RDS/Aurora (todas las regiones).
# Necesarios para que la conexión a la base no solo vaya cifrada, sino
# VERIFICADA: sin el CA no se puede comprobar que el servidor al otro lado es
# de verdad tu RDS. Se activa apuntando DB_SSL_CA a esta ruta (ver settings.py):
#     DB_SSL_CA=/app/certs/rds-ca-global.pem
# Si la variable no se define, el fichero simplemente no se usa.
#
# OJO: esta línea hace que el build necesite acceso a Internet. El bundle es
# público y lo publica Amazon; si algún día quieres un build hermético, baja el
# .pem al repositorio y cámbialo por un COPY.
ADD https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
    /app/certs/rds-ca-global.pem
RUN chmod 644 /app/certs/rds-ca-global.pem

# Código de la app.
COPY . .

# Recolectar estáticos en el build (los sirve WhiteNoise en runtime) y crear el
# usuario sin privilegios, todo en una sola capa.
# - Las variables son ficticias y viven SOLO en esta capa (no se hornean como
#   secretos). ENVIRONMENT=production evita cargar debug_toolbar (que no está en
#   requirements de producción).
# - `appuser`: si alguien logra ejecutar código dentro del contenedor, no lo hace
#   como root. El chown va al final, cuando collectstatic ya escribió en /app.
RUN ENVIRONMENT=production SECRET_KEY=build-only \
    DB_NAME=build DB_USER=build DB_PASSWORD=build DB_HOST=localhost DB_PORT=3306 \
    EMAIL_HOST_USER=build EMAIL_HOST_PASSWORD=build DEFAULT_FROM_EMAIL=build@build.local \
    python manage.py collectstatic --noinput && \
    useradd --create-home --shell /usr/sbin/nologin appuser && \
    chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# LIVENESS del contenedor: "¿el proceso responde?". Se apoya en /health/, que a
# propósito NO toca la base de datos (ver core/health.py).
#
# Se usa python y no curl porque la imagen slim no lo trae y no compensa instalarlo.
#
# OJO con el criterio: se acepta CUALQUIER respuesta HTTP < 500, no solo un 200.
# Motivo: en producción ALLOWED_HOSTS lleva el dominio público, así que una
# petición a 127.0.0.1 responde 400 (DisallowedHost). Ese 400 demuestra que
# Django está vivo y sirviendo, que es justo lo que mide un liveness; exigir 200
# marcaría el contenedor como enfermo y ECS lo mataría en bucle. Si quieres el
# chequeo estricto, añade 127.0.0.1 a ALLOWED_HOSTS.
# De la readiness (¿puede además trabajar?) responde el ALB con /health/ready/.
# Se usa http.client y no urllib a propósito: urllib lanza excepción ante un 4xx,
# lo que obligaría a un try/except imposible de escribir en una sola línea. Con
# http.client el código de estado se lee tal cual, y si el proceso no acepta la
# conexión la excepción sale sola y el chequeo falla, que es lo correcto.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import sys, http.client as h; c = h.HTTPConnection('127.0.0.1', 8000, timeout=4); c.request('GET', '/health/'); sys.exit(0 if c.getresponse().status < 500 else 1)"

# Arranque. migrate en el CMD es cómodo con 1 task; con ≥2 tasks conviene
# ejecutar las migraciones en un task ECS aparte para evitar carreras.
#
# Workers: la fórmula recomendada por Gunicorn es 2 × núcleos + 1, pero NO se
# calcula aquí con `nproc`, y el motivo importa: dentro de un contenedor `nproc`
# devuelve los núcleos del ANFITRIÓN, no los que el task tiene asignados. Fargate
# limita la CPU por cuota de cgroup, que nproc no ve, así que un task de 0,5 vCPU
# arrancaría con tantos workers como núcleos tenga la máquina física —se comprobó
# en una de 14 núcleos: la fórmula daba 29—. Se queda el valor conocido (3) y la
# perilla explícita: en ECS, define GUNICORN_WORKERS según el tamaño del task
#     0,5 vCPU -> 2      1 vCPU -> 3      2 vCPU -> 5
#
# --max-requests recicla cada worker tras N peticiones: acota el efecto de
# cualquier fuga de memoria. El jitter evita que todos se reinicien a la vez y
# dejen un hueco sin capacidad.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS:-3} --timeout 60 --max-requests 1000 --max-requests-jitter 100 --access-logfile - --error-logfile -"]
