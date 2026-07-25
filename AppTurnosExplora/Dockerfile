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

# Código de la app.
COPY . .

# Recolectar estáticos en el build (los sirve WhiteNoise en runtime).
# Las variables son ficticias y viven SOLO en esta capa (no se hornean como
# secretos). ENVIRONMENT=production evita cargar debug_toolbar (que no está en
# requirements de producción).
RUN ENVIRONMENT=production SECRET_KEY=build-only \
    DB_NAME=build DB_USER=build DB_PASSWORD=build DB_HOST=localhost DB_PORT=3306 \
    EMAIL_HOST_USER=build EMAIL_HOST_PASSWORD=build DEFAULT_FROM_EMAIL=build@build.local \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Arranque. migrate en el CMD es cómodo con 1 task; con ≥2 tasks conviene
# ejecutar las migraciones en un task ECS aparte para evitar carreras.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60 --access-logfile - --error-logfile -"]
