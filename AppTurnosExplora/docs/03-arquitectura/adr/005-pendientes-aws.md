# Pendientes para despliegue en AWS

## 1. Contenerización (Docker)

Crear `Dockerfile` y `docker-compose.yml` para desarrollo local con contenedores.

```dockerfile
# Dockerfile (referencia)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
```

Paquetes a agregar en `requirements.txt`:
- `gunicorn` — servidor WSGI para producción (reemplaza `runserver`)
- `mysqlclient` — driver MySQL nativo para Linux (en vez de pymysql)

---

## 2. Variables de entorno en AWS

En desarrollo usamos `.env`. En AWS las variables se inyectan de dos formas:

**Opción A — ECS Task Definition (valores simples):**
```json
"environment": [
  {"name": "ENVIRONMENT", "value": "production"},
  {"name": "DB_HOST", "value": "tu-rds-endpoint.amazonaws.com"}
]
```

**Opción B — SSM Parameter Store (secretos):**
```json
"secrets": [
  {"name": "SECRET_KEY", "valueFrom": "arn:aws:ssm:...:/appturnos/SECRET_KEY"},
  {"name": "DB_PASSWORD", "valueFrom": "arn:aws:ssm:...:/appturnos/DB_PASSWORD"},
  {"name": "EMAIL_HOST_PASSWORD", "valueFrom": "arn:aws:ssm:...:/appturnos/EMAIL_HOST_PASSWORD"}
]
```

Usar SSM para los secretos (SECRET_KEY, contraseñas). El resto puede ir en environment.

---

## 3. Base de datos — RDS MySQL en subred privada

- Crear RDS MySQL en subredes privadas (sin acceso público)
- Solo accesible desde el Security Group de ECS
- Actualizar en `.env` de producción / SSM:
  - `DB_HOST` → endpoint de RDS
  - `DB_NAME`, `DB_USER`, `DB_PASSWORD`
- Crear réplica de lectura si el tráfico lo justifica (reportes, consultas analíticas)

---

## 4. Archivos estáticos — S3 + CloudFront

Agregar a `requirements.txt`:
- `django-storages[s3]` — backend de S3 para archivos estáticos y media
- `boto3`

En `settings.py` (activar cuando `IS_PRODUCTION`):
```python
if IS_PRODUCTION:
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'
    AWS_STORAGE_BUCKET_NAME = env('AWS_S3_BUCKET')
    AWS_S3_REGION_NAME = env('AWS_REGION', default='us-east-1')
    STATIC_URL = f'https://{AWS_S3_BUCKET}.s3.amazonaws.com/static/'
```

Ejecutar `python manage.py collectstatic` en el pipeline antes del deploy.

---

## 5. Caché — ElastiCache Redis

Reemplazar `LocMemCache` por Redis en producción.

Agregar a `requirements.txt`:
- `django-redis`

En `settings.py`:
```python
if IS_PRODUCTION:
    CACHES = {
        'default': {
            'BACKEND': 'django_redis.cache.RedisCache',
            'LOCATION': env('REDIS_URL'),  # redis://tu-cluster.cache.amazonaws.com:6379/1
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
                'IGNORE_EXCEPTIONS': True,
            },
            'KEY_PREFIX': 'appturnos',
            'TIMEOUT': 3600,
        }
    }
```

Agregar `REDIS_URL` a SSM Parameter Store.

---

## 6. Notificaciones asíncronas — SQS (opcional / escalabilidad)

Actualmente las notificaciones de email van con `on_commit()` de forma síncrona.  
Si el volumen de emails crece o se necesitan reintentos automáticos:

1. Agregar `boto3` y configurar una cola SQS
2. En el `on_commit`, publicar a SQS en lugar de llamar a `NotificacionService` directamente
3. Un worker (Lambda o ECS task) consume la cola y envía los emails

No es urgente — `on_commit()` funciona bien para el volumen actual.

---

## 7. CI/CD — GitHub Actions

Crear `.github/workflows/deploy.yml`:

```yaml
name: Deploy
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install -r requirements-dev.txt
      - run: python manage.py test

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: Build Docker image
        run: docker build -t appturnos .
      - name: Push to ECR
        run: # aws ecr push ...
      - name: Deploy to ECS
        run: # aws ecs update-service ...
```

Los secretos de AWS (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`) van en  
GitHub → Settings → Secrets and variables → Actions.

---

## 8. Infraestructura como Código — Terraform (opcional)

Si se quiere reproducir el entorno desde cero:

```
infrastructure/
  main.tf        # VPC, subredes públicas/privadas
  rds.tf         # MySQL RDS en subred privada
  ecs.tf         # Cluster, Task Definition, Service
  alb.tf         # Application Load Balancer + certificado SSL
  s3.tf          # Bucket para estáticos
  elasticache.tf # Redis
  variables.tf
  outputs.tf
```

---

## 9. Monitoreo — CloudWatch

- Conectar los logs de Django a CloudWatch Logs (via `watchtower`):
  ```python
  # Agregar handler en LOGGING cuando IS_PRODUCTION
  'cloudwatch': {
      'class': 'watchtower.CloudWatchLogHandler',
      'log_group': '/appturnos/django',
  }
  ```
- Agregar `watchtower` a `requirements.txt`
- Crear alarmas en CloudWatch para errores 500 y latencia alta

---

## 10. Checklist antes del primer deploy

- [ ] Generar `SECRET_KEY` nueva y segura (no la del desarrollo)
- [ ] Subir todos los secretos a SSM Parameter Store
- [ ] RDS creada y accesible desde ECS
- [ ] `python manage.py migrate` ejecutado contra la BD de producción
- [ ] `python manage.py collectstatic` ejecutado y archivos en S3
- [ ] `ALLOWED_HOSTS` actualizado con el dominio real
- [ ] `CORS_ALLOWED_ORIGINS` actualizado con el dominio real
- [ ] `SITE_URL` actualizado con el dominio real (`https://`)
- [ ] Certificado SSL emitido (AWS Certificate Manager)
- [ ] `ENVIRONMENT=production` configurado en ECS Task Definition
- [ ] Verificar que `DEBUG=False` en producción
- [ ] Test de smoke: login, crear solicitud, aprobar solicitud
