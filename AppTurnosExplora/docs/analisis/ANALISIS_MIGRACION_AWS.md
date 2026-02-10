# 📊 ANÁLISIS DE MIGRACIÓN A AWS - PROYECTO APPTURNOS
## Evaluación Técnica y Económica por Ingeniero Senior

**Fecha:** 2025-11-11  
**Proyecto:** AppTurnos - Sistema de Gestión de Cambios de Turno  
**Objetivo:** Migración a AWS con costos mínimos, evitando RDS

---

## 🔍 ANÁLISIS DEL PROYECTO ACTUAL

### **Stack Tecnológico Identificado:**

1. **Backend:**
   - Django 5.2.2
   - Python 3.12 (inferido del venv)
   - MySQL (mysqlclient 2.2.7)
   - WSGI/ASGI ready

2. **Dependencias Principales:**
   - django-simple-history (auditoría)
   - django-widget-tweaks (formularios)
   - Cache: LocMemCache (desarrollo) / Redis preparado (producción)

3. **Frontend:**
   - AdminLTE 3.2.0
   - FullCalendar
   - SweetAlert2
   - Font Awesome
   - JavaScript vanilla (sin framework pesado)

4. **Características:**
   - Sistema de autenticación Django
   - Envío de emails (SMTP Gmail)
   - Archivos estáticos (CSS, JS, imágenes)
   - API REST (JSON responses)

### **Escala Esperada:**

- **Usuarios simultáneos:** 300 exploradores
- **Solicitudes diarias:** 100+ cambios de turno
- **Base de datos:** MySQL con índices optimizados
- **Caché:** Implementado para optimización

---

## 📈 NIVEL DE DIFICULTAD: **MEDIO-BAJO (35%)**

### **Justificación:**

#### ✅ **Factores que REDUCEN la dificultad (60%):**

1. **Django está bien preparado para producción:**
   - WSGI/ASGI incluidos
   - `collectstatic` para archivos estáticos
   - Configuración de producción estándar
   - Middleware de seguridad incluido

2. **Base de datos MySQL:**
   - Compatible con múltiples opciones AWS
   - Migraciones Django funcionan igual
   - Sin dependencias propietarias

3. **Arquitectura simple:**
   - Monolito Django (no microservicios)
   - Sin dependencias complejas
   - Cache ya implementado

4. **Sin servicios externos críticos:**
   - Email SMTP (Gmail) funciona igual
   - No hay integraciones complejas

#### ⚠️ **Factores que AUMENTAN la dificultad (40%):**

1. **Configuración de producción:**
   - Variables de entorno
   - SECRET_KEY en producción
   - DEBUG=False
   - ALLOWED_HOSTS
   - Configuración de base de datos

2. **Archivos estáticos:**
   - Necesita S3 + CloudFront (o similar)
   - Configuración de `STATIC_ROOT` y `STATIC_URL`

3. **Base de datos MySQL:**
   - Si no usas RDS, necesitas EC2 con MySQL
   - Backups manuales o automatizados
   - Mantenimiento del servidor

4. **SSL/HTTPS:**
   - Certificado SSL (Let's Encrypt o ACM)
   - Configuración de dominio

---

## 💰 ARQUITECTURA ECONÓMICA PROPUESTA

### **Opción 1: MÁS ECONÓMICA (Recomendada)**
**Costo estimado: $15-25 USD/mes**

#### **Componentes:**

1. **EC2 t3.micro (1 vCPU, 1GB RAM) - $8.50/mes**
   - Ubuntu 22.04 LTS
   - Django + Gunicorn
   - MySQL Server (mismo servidor)
   - Nginx como reverse proxy

2. **S3 Standard (archivos estáticos) - $1-2/mes**
   - ~500MB de archivos estáticos
   - Transferencia mínima

3. **CloudFront (CDN opcional) - $0-1/mes**
   - Solo si necesitas mejor rendimiento global
   - Puede omitirse inicialmente

4. **Elastic IP (gratis si en uso) - $0/mes**
   - IP estática para el servidor

5. **Route 53 (DNS) - $0.50/mes**
   - Solo si usas dominio propio
   - Alternativa: usar DNS gratuito (Cloudflare)

6. **ACM (SSL Certificate) - $0/mes**
   - Certificado SSL gratuito

**Total: ~$10-15 USD/mes** (sin dominio) o **~$15-25 USD/mes** (con dominio)

---

### **Opción 2: ESCALABLE (Si creces)**
**Costo estimado: $30-50 USD/mes**

#### **Componentes:**

1. **EC2 t3.small (2 vCPU, 2GB RAM) - $15/mes**
   - Mejor rendimiento para 300 usuarios
   - MySQL en servidor separado (opcional)

2. **RDS MySQL db.t3.micro (OPCIONAL) - $15/mes**
   - Solo si quieres separar BD (no recomendado por costos)
   - **Alternativa:** Mantener MySQL en EC2

3. **S3 + CloudFront - $2-3/mes**

4. **Elastic IP + Route 53 - $0.50/mes**

**Total: ~$30-50 USD/mes**

---

### **Opción 3: SERVERLESS (Más complejo, pero escalable)**
**Costo estimado: $20-40 USD/mes (puede variar)**

#### **Componentes:**

1. **Elastic Beanstalk (Django) - $0 + EC2 costs**
   - Auto-scaling
   - Gestión simplificada
   - EC2 t3.micro: $8.50/mes

2. **RDS MySQL db.t3.micro - $15/mes**
   - **NO RECOMENDADO** (vas a evitar RDS)

3. **S3 + CloudFront - $2-3/mes**

**Total: ~$25-30 USD/mes** (sin RDS)

---

## 🛠️ HERRAMIENTAS Y SERVICIOS NECESARIOS

### **Servicios AWS Requeridos:**

1. **EC2 (Elastic Compute Cloud)**
   - Servidor virtual
   - Ubuntu 22.04 LTS
   - Tipo: t3.micro o t3.small

2. **S3 (Simple Storage Service)**
   - Almacenamiento de archivos estáticos
   - Bucket para `STATIC_ROOT` y `MEDIA_ROOT`

3. **CloudFront (Opcional)**
   - CDN para archivos estáticos
   - Mejora rendimiento global

4. **ACM (AWS Certificate Manager)**
   - Certificado SSL gratuito
   - Para HTTPS

5. **Route 53 (Opcional)**
   - DNS si usas dominio propio
   - Alternativa: Cloudflare (gratis)

6. **Elastic IP**
   - IP estática (gratis si asociada a instancia)

### **Software a Instalar en EC2:**

1. **Python 3.12**
   ```bash
   sudo apt update
   sudo apt install python3.12 python3.12-venv python3-pip
   ```

2. **MySQL Server**
   ```bash
   sudo apt install mysql-server
   ```

3. **Nginx**
   ```bash
   sudo apt install nginx
   ```

4. **Gunicorn**
   ```bash
   pip install gunicorn
   ```

5. **Supervisor (opcional, para gestión de procesos)**
   ```bash
   sudo apt install supervisor
   ```

---

## 📋 PASOS DE MIGRACIÓN (Checklist)

### **FASE 1: Preparación Local (2-3 horas)**

- [ ] Actualizar `settings.py` para producción:
  - `DEBUG = False`
  - `ALLOWED_HOSTS = ['tu-dominio.com', 'www.tu-dominio.com']`
  - Variables de entorno para `SECRET_KEY`
  - Configuración de base de datos con variables de entorno
  - `STATIC_ROOT` y `MEDIA_ROOT` configurados
  - `STATIC_URL` apuntando a S3

- [ ] Crear `requirements.txt` completo (ya existe, verificar)
- [ ] Probar `collectstatic` localmente
- [ ] Crear archivo `.env.example` con variables necesarias
- [ ] Documentar configuración de email (SMTP)

### **FASE 2: Configuración AWS (1-2 horas)**

- [ ] Crear cuenta AWS (si no existe)
- [ ] Crear instancia EC2 (t3.micro, Ubuntu 22.04)
- [ ] Configurar Security Groups:
  - Puerto 22 (SSH)
  - Puerto 80 (HTTP)
  - Puerto 443 (HTTPS)
  - Puerto 3306 (MySQL, solo desde EC2)
- [ ] Asociar Elastic IP
- [ ] Crear bucket S3 para archivos estáticos
- [ ] Configurar IAM user con permisos S3
- [ ] Configurar CloudFront (opcional)

### **FASE 3: Instalación en EC2 (2-3 horas)**

- [ ] Conectar por SSH
- [ ] Actualizar sistema: `sudo apt update && sudo apt upgrade -y`
- [ ] Instalar Python, MySQL, Nginx
- [ ] Crear usuario para Django
- [ ] Clonar repositorio Git
- [ ] Crear virtual environment
- [ ] Instalar dependencias (`pip install -r requirements.txt`)
- [ ] Configurar MySQL:
  - Crear base de datos
  - Crear usuario
  - Importar datos (si hay)
- [ ] Ejecutar migraciones: `python manage.py migrate`
- [ ] Crear superusuario: `python manage.py createsuperuser`
- [ ] Configurar variables de entorno (`.env`)

### **FASE 4: Configuración Django (1-2 horas)**

- [ ] Configurar `settings.py` para producción
- [ ] Instalar `django-storages` para S3:
  ```bash
  pip install django-storages boto3
  ```
- [ ] Configurar S3 en `settings.py`:
  ```python
  INSTALLED_APPS = [
      ...
      'storages',
  ]
  
  AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID')
  AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
  AWS_STORAGE_BUCKET_NAME = 'tu-bucket-s3'
  AWS_S3_REGION_NAME = 'us-east-1'
  STATICFILES_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
  ```
- [ ] Ejecutar `collectstatic` (sube a S3)
- [ ] Configurar Gunicorn
- [ ] Configurar Nginx como reverse proxy
- [ ] Probar aplicación localmente en EC2

### **FASE 5: SSL y Dominio (1 hora)**

- [ ] Configurar dominio (Route 53 o Cloudflare)
- [ ] Solicitar certificado SSL en ACM
- [ ] Configurar Nginx con SSL
- [ ] Redirigir HTTP a HTTPS

### **FASE 6: Monitoreo y Backups (1 hora)**

- [ ] Configurar backups de MySQL (cron job)
- [ ] Configurar CloudWatch (monitoreo básico)
- [ ] Configurar alertas (opcional)
- [ ] Documentar proceso de backup/restore

### **FASE 7: Pruebas (2-3 horas)**

- [ ] Probar todas las funcionalidades
- [ ] Probar con múltiples usuarios simultáneos
- [ ] Verificar rendimiento
- [ ] Probar emails
- [ ] Verificar archivos estáticos desde S3

---

## ⚠️ CONSIDERACIONES IMPORTANTES

### **1. Base de Datos MySQL en EC2 (No RDS)**

**Ventajas:**
- ✅ Costo $0 adicional (incluido en EC2)
- ✅ Control total
- ✅ Sin límites de conexiones

**Desventajas:**
- ⚠️ Tú eres responsable de backups
- ⚠️ Tú eres responsable de actualizaciones
- ⚠️ Tú eres responsable de seguridad

**Recomendación:**
- Script de backup diario a S3 (cron job)
- Actualizaciones de seguridad regulares
- Firewall MySQL (solo desde localhost)

### **2. Escalabilidad**

**Con 300 usuarios simultáneos:**
- **t3.micro:** Puede funcionar, pero justo
- **t3.small:** Recomendado para mejor rendimiento
- **t3.medium:** Si creces más (50-100 USD/mes)

**Auto-scaling:**
- No necesario inicialmente
- Puedes escalar manualmente cuando sea necesario

### **3. Archivos Estáticos**

**Opciones:**
1. **S3 + CloudFront:** Mejor rendimiento, ~$2-3/mes
2. **S3 solo:** Funciona, ~$1/mes
3. **Nginx serve static:** Más simple, pero menos escalable

**Recomendación:** S3 + CloudFront (opcional inicialmente)

### **4. Email SMTP**

**Actual:** Gmail SMTP
- Funciona igual en producción
- Sin cambios necesarios
- Considerar límites de Gmail (500 emails/día)

**Alternativa:** AWS SES (Simple Email Service)
- Más económico si envías muchos emails
- ~$0.10 por 1000 emails
- Requiere verificación de dominio

---

## 💡 OPTIMIZACIONES ADICIONALES

### **1. Cache Redis (Opcional)**

**Costo:** ElastiCache t3.micro ~$15/mes

**Alternativa:** Redis en EC2 mismo servidor
- ✅ Costo $0 adicional
- ⚠️ Compite por recursos con Django/MySQL
- ✅ Funciona bien para 300 usuarios

**Recomendación:** Redis en EC2 (no ElastiCache)

### **2. CDN CloudFront**

**Costo:** ~$1-2/mes (primeros 10GB gratis)

**Beneficio:** Mejor rendimiento global

**Recomendación:** Opcional inicialmente, agregar si es necesario

### **3. Load Balancer (Solo si escalas)**

**Costo:** ~$16/mes

**Cuándo:** Solo si necesitas múltiples instancias EC2

**Recomendación:** No necesario inicialmente

---

## 📊 COMPARACIÓN DE COSTOS

| Componente | Opción Económica | Opción Escalable | Opción Serverless |
|------------|------------------|------------------|-------------------|
| **EC2** | t3.micro ($8.50) | t3.small ($15) | t3.micro ($8.50) |
| **MySQL** | En EC2 ($0) | En EC2 ($0) | En EC2 ($0) |
| **S3** | $1-2 | $2-3 | $2-3 |
| **CloudFront** | $0-1 (opcional) | $1-2 | $1-2 |
| **Route 53** | $0.50 | $0.50 | $0.50 |
| **Elastic IP** | $0 | $0 | $0 |
| **TOTAL** | **$10-12/mes** | **$18-20/mes** | **$12-14/mes** |

**Nota:** Costos en USD, región us-east-1. Pueden variar según región y uso.

---

## 🎯 RECOMENDACIÓN FINAL

### **Arquitectura Recomendada (Costo: $10-15 USD/mes):**

```
┌─────────────────────────────────────────┐
│           Internet / Usuarios            │
└─────────────────┬───────────────────────┘
                  │
         ┌────────▼────────┐
         │   CloudFront    │ (Opcional, $0-1/mes)
         │      (CDN)       │
         └────────┬────────┘
                  │
         ┌────────▼────────┐
         │   Route 53      │ ($0.50/mes)
         │     (DNS)       │
         └────────┬────────┘
                  │
         ┌────────▼────────────────────────┐
         │         EC2 t3.micro             │
         │  ┌──────────────────────────┐   │
         │  │  Nginx (Reverse Proxy)    │   │
         │  └──────────┬───────────────┘   │
         │             │                    │
         │  ┌──────────▼───────────────┐   │
         │  │  Gunicorn + Django       │   │
         │  └──────────┬───────────────┘   │
         │             │                    │
         │  ┌──────────▼───────────────┐   │
         │  │  MySQL Server            │   │
         │  └──────────────────────────┘   │
         │  ┌──────────────────────────┐   │
         │  │  Redis (Cache)           │   │
         │  └──────────────────────────┘   │
         └──────────────────────────────────┘
                  │
         ┌────────▼────────┐
         │   S3 Bucket      │ ($1-2/mes)
         │  (Static Files) │
         └──────────────────┘
```

### **Ventajas de esta arquitectura:**

1. ✅ **Costo mínimo:** $10-15 USD/mes
2. ✅ **Escalable:** Puedes cambiar a t3.small/medium cuando crezcas
3. ✅ **Simple:** Todo en un servidor (fácil de mantener)
4. ✅ **Sin RDS:** MySQL en EC2 (ahorro de $15/mes)
5. ✅ **Rendimiento:** Suficiente para 300 usuarios

### **Desventajas:**

1. ⚠️ **Single Point of Failure:** Si EC2 cae, todo cae
   - **Mitigación:** Backups automáticos a S3
   - **Mitigación:** Puedes crear AMI (imagen) para recuperación rápida

2. ⚠️ **Mantenimiento manual:** Tú gestionas MySQL
   - **Mitigación:** Scripts automatizados de backup
   - **Mitigación:** Actualizaciones de seguridad regulares

---

## 🚀 TIEMPO ESTIMADO DE IMPLEMENTACIÓN

### **Para un desarrollador con experiencia en AWS:**

- **Preparación local:** 2-3 horas
- **Configuración AWS:** 1-2 horas
- **Instalación EC2:** 2-3 horas
- **Configuración Django:** 1-2 horas
- **SSL y dominio:** 1 hora
- **Monitoreo y backups:** 1 hora
- **Pruebas:** 2-3 horas

**TOTAL: 10-15 horas** (1.5-2 días de trabajo)

### **Para un desarrollador sin experiencia en AWS:**

- **Aprendizaje básico AWS:** +5-10 horas
- **Troubleshooting:** +3-5 horas

**TOTAL: 18-30 horas** (3-4 días de trabajo)

---

## 📚 RECURSOS Y DOCUMENTACIÓN

### **Guías útiles:**

1. **Django Deployment:**
   - https://docs.djangoproject.com/en/5.2/howto/deployment/

2. **Gunicorn:**
   - https://docs.gunicorn.org/

3. **Nginx + Django:**
   - https://uwsgi-docs.readthedocs.io/en/latest/tutorials/Django_and_nginx.html

4. **django-storages (S3):**
   - https://django-storages.readthedocs.io/

5. **AWS EC2:**
   - https://docs.aws.amazon.com/ec2/

---

## ✅ CONCLUSIÓN

### **Nivel de Dificultad: 35% (MEDIO-BAJO)**

**Razones:**
- Django está bien preparado para producción
- Arquitectura simple (monolito)
- Sin dependencias complejas
- Documentación abundante

### **Costo Estimado: $10-15 USD/mes**

**Componentes:**
- EC2 t3.micro: $8.50/mes
- S3: $1-2/mes
- Route 53: $0.50/mes
- Otros: $0-2/mes

### **Tiempo Estimado: 10-15 horas**

**Para desarrollador con experiencia AWS**

### **Recomendación:**

✅ **SÍ, es factible y económico**

La migración es **relativamente sencilla** y el costo es **muy bajo** comparado con otras opciones. El proyecto está bien estructurado y Django facilita el despliegue en producción.

**Próximos pasos sugeridos:**
1. Crear cuenta AWS (si no existe)
2. Probar con instancia EC2 de prueba (t2.micro free tier si calificas)
3. Seguir checklist de migración paso a paso
4. Monitorear costos durante primer mes

---

**Última actualización:** 2025-11-11  
**Autor:** Análisis Técnico - Ingeniero Senior

