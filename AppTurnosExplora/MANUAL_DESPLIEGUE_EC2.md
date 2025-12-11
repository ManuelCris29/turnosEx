# Manual de Despliegue en AWS EC2

Este manual describe el proceso paso a paso para desplegar el proyecto AppTurnosExplora en una instancia AWS EC2.

---

## 1. Requisitos Previos

### Instancia EC2
- **Sistema Operativo:** Amazon Linux 2023 o Ubuntu 22.04 LTS
- **Tipo de instancia:** t2.micro (desarrollo) o t2.small+ (producción)
- **Almacenamiento:** Mínimo 20 GB
- **Grupos de seguridad:** Abrir puertos 22 (SSH), 80 (HTTP), 443 (HTTPS)

### Base de Datos
- MySQL 8.0+ o MariaDB 10.5+ (puede ser RDS o instalado en EC2)

---

## 2. Instalación de Dependencias del Sistema

### Amazon Linux 2023

```bash
# Actualizar sistema
sudo dnf update -y

# Instalar Python y herramientas de desarrollo
sudo dnf install python3.11 python3.11-pip python3.11-devel -y

# Instalar dependencias para mysqlclient
sudo dnf install mariadb105-devel gcc -y

# Instalar Nginx
sudo dnf install nginx -y
```

### Ubuntu 22.04

```bash
# Actualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Python y herramientas de desarrollo
sudo apt install python3 python3-pip python3-venv python3-dev -y

# Instalar dependencias para mysqlclient
sudo apt install default-libmysqlclient-dev build-essential pkg-config -y

# Instalar Nginx
sudo apt install nginx -y
```

---

## 3. Configuración del Proyecto

### 3.1 Crear usuario para la aplicación (opcional pero recomendado)

```bash
sudo useradd -m -s /bin/bash appuser
sudo su - appuser
```

### 3.2 Clonar el repositorio

```bash
cd /home/appuser  # o /var/www
git clone <URL_DEL_REPOSITORIO> appTurnos
cd appTurnos/AppTurnosExplora
```

### 3.3 Crear y activar entorno virtual

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3.4 Instalar dependencias

```bash
# Actualizar pip
pip install --upgrade pip

# Instalar dependencias de producción (incluye mysqlclient)
pip install -r requirements.txt

# Instalar Gunicorn (servidor WSGI)
pip install gunicorn
```

---

## 4. Configuración de Base de Datos

### 4.1 Crear archivo de variables de entorno

Crear archivo `.env` en la raíz del proyecto:

```bash
nano /home/appuser/appTurnos/AppTurnosExplora/.env
```

Contenido:

```env
# Base de datos
DB_NAME=bdturnosex
DB_USER=tu_usuario_mysql
DB_PASSWORD=tu_contraseña_segura
DB_HOST=localhost  # o endpoint de RDS
DB_PORT=3306

# Django
DJANGO_SECRET_KEY=tu-clave-secreta-muy-larga-y-segura
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=tu-dominio.com,IP_PUBLICA_EC2
```

### 4.2 Modificar config/db.py para usar variables de entorno

El archivo ya está configurado para detectar automáticamente `mysqlclient` o `pymysql`. 
Solo asegúrate de que las credenciales se lean desde variables de entorno en producción.

### 4.3 Crear la base de datos en MySQL

```bash
mysql -u root -p
```

```sql
CREATE DATABASE bdturnosex CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tu_usuario'@'localhost' IDENTIFIED BY 'tu_contraseña';
GRANT ALL PRIVILEGES ON bdturnosex.* TO 'tu_usuario'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

---

## 5. Migraciones y Archivos Estáticos

```bash
# Activar entorno virtual si no está activo
source venv/bin/activate

# Aplicar migraciones
python manage.py migrate

# Recolectar archivos estáticos
python manage.py collectstatic --noinput

# Crear superusuario (opcional)
python manage.py createsuperuser
```

---

## 6. Configuración de Gunicorn + Nginx

### 6.1 Crear archivo de servicio systemd para Gunicorn

```bash
sudo nano /etc/systemd/system/appturnosex.service
```

Contenido:

```ini
[Unit]
Description=Gunicorn daemon para AppTurnosExplora
After=network.target

[Service]
User=appuser
Group=appuser
WorkingDirectory=/home/appuser/appTurnos/AppTurnosExplora
Environment="PATH=/home/appuser/appTurnos/AppTurnosExplora/venv/bin"
EnvironmentFile=/home/appuser/appTurnos/AppTurnosExplora/.env
ExecStart=/home/appuser/appTurnos/AppTurnosExplora/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/home/appuser/appTurnos/AppTurnosExplora/gunicorn.sock \
    config.wsgi:application

[Install]
WantedBy=multi-user.target
```

### 6.2 Iniciar y habilitar Gunicorn

```bash
sudo systemctl start appturnosex
sudo systemctl enable appturnosex
sudo systemctl status appturnosex
```

### 6.3 Configurar Nginx

```bash
sudo nano /etc/nginx/conf.d/appturnosex.conf
```

Contenido:

```nginx
server {
    listen 80;
    server_name tu-dominio.com IP_PUBLICA_EC2;

    # Archivos estáticos
    location /static/ {
        alias /home/appuser/appTurnos/AppTurnosExplora/static/;
    }

    # Archivos media (si aplica)
    location /media/ {
        alias /home/appuser/appTurnos/AppTurnosExplora/media/;
    }

    # Proxy a Gunicorn
    location / {
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_pass http://unix:/home/appuser/appTurnos/AppTurnosExplora/gunicorn.sock;
    }
}
```

### 6.4 Verificar y reiniciar Nginx

```bash
# Verificar configuración
sudo nginx -t

# Reiniciar Nginx
sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

## 7. Comandos Útiles

### Servicios

```bash
# Reiniciar Gunicorn
sudo systemctl restart appturnosex

# Reiniciar Nginx
sudo systemctl restart nginx

# Ver estado de servicios
sudo systemctl status appturnosex
sudo systemctl status nginx
```

### Logs

```bash
# Logs de Gunicorn
sudo journalctl -u appturnosex -f

# Logs de Nginx
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Logs de Django (si están configurados)
tail -f /home/appuser/appTurnos/AppTurnosExplora/logs/django.log
```

### Actualizar aplicación

```bash
cd /home/appuser/appTurnos/AppTurnosExplora
source venv/bin/activate

# Obtener cambios
git pull origin main

# Instalar nuevas dependencias (si hay)
pip install -r requirements.txt

# Aplicar migraciones (si hay)
python manage.py migrate

# Recolectar estáticos (si hay cambios)
python manage.py collectstatic --noinput

# Reiniciar servicio
sudo systemctl restart appturnosex
```

---

## 8. Configuración HTTPS con Let's Encrypt (Opcional pero Recomendado)

```bash
# Instalar Certbot
sudo dnf install certbot python3-certbot-nginx -y  # Amazon Linux
# o
sudo apt install certbot python3-certbot-nginx -y  # Ubuntu

# Obtener certificado SSL
sudo certbot --nginx -d tu-dominio.com

# Renovación automática (ya configurada por Certbot)
sudo systemctl status certbot.timer
```

---

## 9. Checklist de Despliegue

- [ ] Instancia EC2 creada y configurada
- [ ] Grupos de seguridad configurados (puertos 22, 80, 443)
- [ ] Python y dependencias del sistema instaladas
- [ ] Proyecto clonado
- [ ] Entorno virtual creado
- [ ] `requirements.txt` instalado (con mysqlclient)
- [ ] Base de datos creada y configurada
- [ ] Archivo `.env` creado con credenciales
- [ ] Migraciones aplicadas
- [ ] Archivos estáticos recolectados
- [ ] Gunicorn configurado como servicio
- [ ] Nginx configurado como proxy reverso
- [ ] HTTPS habilitado (opcional)
- [ ] Probada la aplicación en el navegador

---

## Notas Importantes

1. **Nunca** uses `DEBUG=True` en producción
2. **Cambia** la `SECRET_KEY` de Django en producción
3. **Configura** `ALLOWED_HOSTS` correctamente
4. **Usa** variables de entorno para credenciales sensibles
5. **Haz** backups regulares de la base de datos
6. **Monitorea** los logs regularmente

---

*Última actualización: Diciembre 2025*


