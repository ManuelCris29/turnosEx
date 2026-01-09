# Manual de Usuario: Verificación de Integridad de Dobladas

**Sistema:** AppTurnosExplora  
**Versión:** 1.0  
**Fecha:** Enero 2026  
**Autor:** Equipo de Desarrollo

---

## 📑 Tabla de Contenidos

1. [Introducción](#introducción)
2. [Requisitos Previos](#requisitos-previos)
3. [Configuración Inicial](#configuración-inicial)
4. [Uso del Comando](#uso-del-comando)
5. [Configuración en Producción (AWS EC2)](#configuración-en-producción-aws-ec2)
6. [Casos de Uso Prácticos](#casos-de-uso-prácticos)
7. [Interpretación de Resultados](#interpretación-de-resultados)
8. [Troubleshooting](#troubleshooting)
9. [Mantenimiento](#mantenimiento)

---

## 🎯 Introducción

### ¿Qué hace este comando?

El comando `verificar_integridad_dobladas` es una herramienta de monitoreo que:

- ✅ Detecta solicitudes de doblada aprobadas sin turnos generados
- ✅ Identifica inconsistencias en la base de datos
- ✅ Repara automáticamente problemas de datos
- ✅ Envía alertas por email al administrador
- ✅ Genera logs para auditoría

### ¿Por qué es importante?

Previene y corrige situaciones donde:
- Una doblada se aprueba pero los turnos no se crean
- Los usuarios ven mensajes confusos ("Doblada Existente Detectada" sin turnos)
- El sistema queda en estado inconsistente

---

## 📋 Requisitos Previos

### Software Necesario

- ✅ Python 3.10+
- ✅ Django 5.1+
- ✅ Entorno virtual `venvturnos` activado
- ✅ Acceso a la base de datos del proyecto
- ✅ Permisos de administrador (para producción)

### Verificar Instalación

```bash
# 1. Activar entorno virtual (Windows)
cd C:\appTurnos\AppTurnosExplora
.\venvturnos\Scripts\Activate.ps1

# 2. Verificar que el comando existe
python manage.py verificar_integridad_dobladas --help
```

**Salida esperada:**
```
usage: manage.py verificar_integridad_dobladas [-h] [--reparar] [--email EMAIL] [--dias DIAS]

Verifica la integridad de solicitudes de doblada aprobadas

optional arguments:
  -h, --help     show this help message and exit
  --reparar      Intenta reparar automáticamente las inconsistencias detectadas
  --email EMAIL  Envía un reporte por email a la dirección especificada
  --dias DIAS    Número de días hacia atrás para verificar (default: 90)
```

---

## ⚙️ Configuración Inicial

### 1. Configurar Email (Para Alertas)

**Archivo:** `AppTurnosExplora/config/settings.py`

```python
# ========================================
# CONFIGURACIÓN DE EMAIL
# ========================================

# Para Gmail
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'tu-email@gmail.com'
EMAIL_HOST_PASSWORD = 'xxxx xxxx xxxx xxxx'  # App Password de Gmail
DEFAULT_FROM_EMAIL = 'AppTurnos <no-reply@tudominio.com>'

# Para Outlook/Office365
# EMAIL_HOST = 'smtp.office365.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True

# Para servidor SMTP personalizado
# EMAIL_HOST = 'smtp.tudominio.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
```

#### Obtener App Password de Gmail

1. Ve a https://myaccount.google.com/security
2. Activa "Verificación en 2 pasos"
3. Ve a "Contraseñas de aplicaciones"
4. Genera una contraseña para "Django AppTurnos"
5. Copia la contraseña (16 caracteres)
6. Pégala en `EMAIL_HOST_PASSWORD`

### 2. Probar Configuración de Email

```bash
# Crear script de prueba
python manage.py shell
```

```python
from django.core.mail import send_mail
from django.conf import settings

send_mail(
    'Prueba de Email - AppTurnos',
    'Si recibes este email, la configuración es correcta.',
    settings.DEFAULT_FROM_EMAIL,
    ['tu-email@gmail.com'],
    fail_silently=False,
)
```

Si recibes el email: ✅ **Configuración correcta**

---

## 💻 Uso del Comando

### Sintaxis Básica

```bash
python manage.py verificar_integridad_dobladas [OPCIONES]
```

### Opciones Disponibles

| Opción | Descripción | Ejemplo |
|--------|-------------|---------|
| `--reparar` | Repara automáticamente las inconsistencias | `--reparar` |
| `--email EMAIL` | Envía reporte por email | `--email admin@tudominio.com` |
| `--dias DIAS` | Días hacia atrás para verificar (default: 90) | `--dias 30` |

### Ejemplos de Uso

#### 1. **Verificación Simple (Solo Reporte)**

```bash
python manage.py verificar_integridad_dobladas
```

**Cuándo usar:** Para revisar el estado actual sin hacer cambios.

**Salida:**
```
================================================================================
VERIFICACIÓN DE INTEGRIDAD DE DOBLADAS
================================================================================

📅 Verificando solicitudes desde: 2025-10-09
🔧 Modo reparación: NO

📊 Total de solicitudes aprobadas: 15

================================================================================
RESULTADOS
================================================================================

✅ No se encontraron inconsistencias
================================================================================
```

---

#### 2. **Verificación con Reparación Automática**

```bash
python manage.py verificar_integridad_dobladas --reparar
```

**Cuándo usar:** Después de deploy o cuando detectes problemas.

**Salida:**
```
================================================================================
VERIFICACIÓN DE INTEGRIDAD DE DOBLADAS
================================================================================

📅 Verificando solicitudes desde: 2025-10-09
🔧 Modo reparación: SÍ

📊 Total de solicitudes aprobadas: 15

================================================================================
RESULTADOS
================================================================================

❌ Se encontraron 1 inconsistencia(s):

1. Solicitud ID: 111
   Solicitante: Jhon
   Receptor: Marco
   Fecha cesión: 2026-01-14
   Problema: Receptor Marco no tiene turnos para 2026-01-14 (debería tener doblada)
   🔧 Intentando reparar...
      ✅ Solicitud reseteada a pendiente. Debe ser aprobada nuevamente.

================================================================================
```

**⚠️ IMPORTANTE:** Después de reparar, los usuarios afectados deben re-aprobar las solicitudes.

---

#### 3. **Verificación con Email**

```bash
python manage.py verificar_integridad_dobladas --reparar --email admin@tudominio.com
```

**Cuándo usar:** Para monitoreo automático con notificaciones.

**Comportamiento:**
- Si NO hay inconsistencias: ✅ No envía email
- Si hay inconsistencias: 📧 Envía email con reporte detallado

---

#### 4. **Verificación de Rango de Fechas Específico**

```bash
# Verificar últimos 7 días
python manage.py verificar_integridad_dobladas --dias 7 --reparar

# Verificar último mes
python manage.py verificar_integridad_dobladas --dias 30 --reparar

# Verificar últimos 3 meses
python manage.py verificar_integridad_dobladas --dias 90 --reparar
```

**Cuándo usar:** Para auditorías periódicas o investigación de problemas.

---

## 🚀 Configuración en Producción (AWS EC2)

### Paso 1: Conectarse al Servidor

```bash
# Desde tu computadora local
ssh -i "tu-llave.pem" ubuntu@tu-servidor-ec2.amazonaws.com
```

### Paso 2: Verificar Rutas

```bash
# 1. Ubicar el proyecto
cd /home/ubuntu/appTurnos/AppTurnosExplora
pwd
# Salida: /home/ubuntu/appTurnos/AppTurnosExplora

# 2. Ubicar el entorno virtual
ls /home/ubuntu/venvturnos/bin/python
# Salida: /home/ubuntu/venvturnos/bin/python

# 3. Probar el comando manualmente
/home/ubuntu/venvturnos/bin/python manage.py verificar_integridad_dobladas
```

### Paso 3: Crear Directorio de Logs

```bash
# Crear directorio si no existe
sudo mkdir -p /var/log/appturnos

# Crear archivo de log
sudo touch /var/log/appturnos/integridad_dobladas.log

# Dar permisos al usuario ubuntu
sudo chown -R ubuntu:ubuntu /var/log/appturnos

# Verificar permisos
ls -la /var/log/appturnos/
```

### Paso 4: Configurar Cron Job

```bash
# Editar crontab
crontab -e

# Si es la primera vez, elegir editor (recomendado: nano)
# Presionar 1 y Enter
```

**Agregar esta línea al final del archivo:**

```bash
# Verificación de integridad de dobladas - Diaria a las 3:00 AM
0 3 * * * cd /home/ubuntu/appTurnos/AppTurnosExplora && /home/ubuntu/venvturnos/bin/python manage.py verificar_integridad_dobladas --reparar --email admin@tudominio.com >> /var/log/appturnos/integridad_dobladas.log 2>&1
```

**Guardar y salir:**
- En nano: `Ctrl + X`, luego `Y`, luego `Enter`
- En vim: `Esc`, luego `:wq`, luego `Enter`

### Paso 5: Verificar Configuración del Cron

```bash
# Listar cron jobs activos
crontab -l

# Verificar que el servicio cron esté activo
sudo systemctl status cron
```

**Salida esperada:**
```
● cron.service - Regular background program processing daemon
   Loaded: loaded (/lib/systemd/system/cron.service; enabled; vendor preset: enabled)
   Active: active (running) since Mon 2026-01-06 10:00:00 UTC; 2 days ago
```

### Paso 6: Probar Manualmente (Simulación)

```bash
# Ejecutar el comando exacto que ejecutará el cron
cd /home/ubuntu/appTurnos/AppTurnosExplora && /home/ubuntu/venvturnos/bin/python manage.py verificar_integridad_dobladas --reparar --email admin@tudominio.com >> /var/log/appturnos/integridad_dobladas.log 2>&1

# Ver el log generado
cat /var/log/appturnos/integridad_dobladas.log
```

### Paso 7: Monitorear Logs

```bash
# Ver logs en tiempo real
tail -f /var/log/appturnos/integridad_dobladas.log

# Ver últimas 50 líneas
tail -n 50 /var/log/appturnos/integridad_dobladas.log

# Buscar errores
grep -i "error" /var/log/appturnos/integridad_dobladas.log

# Buscar inconsistencias detectadas
grep -i "inconsistencia" /var/log/appturnos/integridad_dobladas.log
```

---

## 📚 Casos de Uso Prácticos

### Caso 1: Post-Deploy (Después de Actualizar Código)

**Escenario:** Acabas de hacer deploy de nuevos cambios en producción.

**Procedimiento:**

```bash
# 1. Conectarse al servidor
ssh -i "tu-llave.pem" ubuntu@tu-servidor-ec2.amazonaws.com

# 2. Ir al directorio del proyecto
cd /home/ubuntu/appTurnos/AppTurnosExplora

# 3. Activar entorno virtual
source /home/ubuntu/venvturnos/bin/activate

# 4. Verificar integridad
python manage.py verificar_integridad_dobladas --reparar

# 5. Si hay problemas, revisar logs
tail -f /var/log/appturnos/integridad_dobladas.log
```

---

### Caso 2: Usuario Reporta Problema

**Escenario:** Marco reporta que ve "Doblada Existente Detectada" pero sin turnos.

**Procedimiento:**

```bash
# 1. Diagnosticar usuario específico (local o servidor)
python scripts/diagnosticar_doblada_marco.py

# 2. Verificar inconsistencias recientes (últimos 7 días)
python manage.py verificar_integridad_dobladas --dias 7 --reparar

# 3. Si se repara, notificar al usuario
# "Marco, tu solicitud fue reseteada. Por favor, apruébala nuevamente."

# 4. Verificar que el problema no se repita
tail -f /var/log/appturnos/integridad_dobladas.log
```

---

### Caso 3: Auditoría Mensual

**Escenario:** Primer día de cada mes, quieres verificar el mes anterior.

**Procedimiento:**

```bash
# Verificar último mes y enviar reporte
python manage.py verificar_integridad_dobladas --dias 30 --email admin@tudominio.com
```

**Email que recibirás (si hay problemas):**

```
Asunto: ⚠️ Reporte de Integridad de Dobladas - 3 problema(s)

Reporte de Verificación de Integridad de Dobladas
=================================================

Se detectaron 3 inconsistencia(s) en el sistema:

1. Solicitud ID: 111
   Solicitante: Jhon
   Receptor: Marco
   Fecha cesión: 2026-01-14
   Problema: Receptor Marco no tiene turnos para 2026-01-14 (debería tener doblada)
   
[... más detalles ...]

Acción recomendada:
- Ejecutar: python manage.py verificar_integridad_dobladas --reparar
- O resetear manualmente las solicitudes afectadas
```

---

### Caso 4: Investigación de Problema Específico

**Escenario:** Quieres investigar una solicitud específica que sospechas tiene problemas.

**Procedimiento:**

```bash
# 1. Diagnosticar la solicitud (ejemplo: ID 111)
python scripts/diagnosticar_solicitud_111.py

# 2. Si confirma el problema, resetear manualmente
python scripts/resetear_solicitud_111.py

# 3. Verificar que el sistema global esté OK
python manage.py verificar_integridad_dobladas
```

---

## 📊 Interpretación de Resultados

### Resultado 1: ✅ Sin Inconsistencias

```
================================================================================
VERIFICACIÓN DE INTEGRIDAD DE DOBLADAS
================================================================================

📅 Verificando solicitudes desde: 2025-10-09
🔧 Modo reparación: SÍ

📊 Total de solicitudes aprobadas: 25

================================================================================
RESULTADOS
================================================================================

✅ No se encontraron inconsistencias
================================================================================
```

**Significado:**
- ✅ Todas las solicitudes aprobadas tienen sus turnos correctamente generados
- ✅ No se requiere acción
- ✅ El sistema está funcionando correctamente

**Acción:** Ninguna. Todo está bien.

---

### Resultado 2: ⚠️ Con Inconsistencias (Sin Reparar)

```
================================================================================
VERIFICACIÓN DE INTEGRIDAD DE DOBLADAS
================================================================================

📅 Verificando solicitudes desde: 2025-10-09
🔧 Modo reparación: NO

📊 Total de solicitudes aprobadas: 25

================================================================================
RESULTADOS
================================================================================

❌ Se encontraron 2 inconsistencia(s):

1. Solicitud ID: 111
   Solicitante: Jhon
   Receptor: Marco
   Fecha cesión: 2026-01-14
   Problema: Receptor Marco no tiene turnos para 2026-01-14 (debería tener doblada)

2. Solicitud ID: 115
   Solicitante: Pedro
   Receptor: Ana
   Fecha cesión: 2026-01-20
   Problema: Receptor Ana no tiene turnos para 2026-01-20 (debería tener doblada)

================================================================================
```

**Significado:**
- ❌ Se detectaron 2 solicitudes con problemas
- ⚠️ No se repararon porque no usaste `--reparar`
- 📋 Los problemas persisten en la base de datos

**Acción Recomendada:**

```bash
# Ejecutar nuevamente con --reparar
python manage.py verificar_integridad_dobladas --reparar
```

---

### Resultado 3: ✅ Con Inconsistencias (Reparadas)

```
================================================================================
VERIFICACIÓN DE INTEGRIDAD DE DOBLADAS
================================================================================

📅 Verificando solicitudes desde: 2025-10-09
🔧 Modo reparación: SÍ

📊 Total de solicitudes aprobadas: 25

================================================================================
RESULTADOS
================================================================================

❌ Se encontraron 2 inconsistencia(s):

1. Solicitud ID: 111
   Solicitante: Jhon
   Receptor: Marco
   Fecha cesión: 2026-01-14
   Problema: Receptor Marco no tiene turnos para 2026-01-14 (debería tener doblada)
   🔧 Intentando reparar...
      ✅ Solicitud reseteada a pendiente. Debe ser aprobada nuevamente.

2. Solicitud ID: 115
   Solicitante: Pedro
   Receptor: Ana
   Fecha cesión: 2026-01-20
   Problema: Receptor Ana no tiene turnos para 2026-01-20 (debería tener doblada)
   🔧 Intentando reparar...
      ✅ Solicitud reseteada a pendiente. Debe ser aprobada nuevamente.

📧 Reporte enviado a admin@tudominio.com
================================================================================
```

**Significado:**
- ✅ Se detectaron y repararon 2 solicitudes
- ✅ Las solicitudes volvieron a estado `pendiente`
- 📧 Se envió email al administrador
- ⚠️ Los usuarios deben re-aprobar las solicitudes

**Acción Recomendada:**

1. **Notificar a los usuarios afectados:**
   - Jhon y Marco (Solicitud 111)
   - Pedro y Ana (Solicitud 115)

2. **Mensaje a enviar:**
   ```
   Hola [Nombre],
   
   Tu solicitud de doblada #[ID] fue reseteada automáticamente 
   por el sistema debido a un problema técnico que ya fue resuelto.
   
   Por favor, aprueba nuevamente la solicitud desde:
   http://tudominio.com/solicitudes/pendientes/
   
   Disculpa las molestias.
   ```

3. **Investigar la causa raíz:**
   ```bash
   # Revisar logs de Django para entender por qué falló
   tail -f /var/log/django/application.log
   
   # Buscar errores relacionados con la fecha
   grep "2026-01-14" /var/log/django/application.log
   ```

---

## 🔧 Troubleshooting

### Problema 1: "No module named 'solicitudes'"

**Error:**
```
ModuleNotFoundError: No module named 'solicitudes'
```

**Causa:** No estás en el directorio correcto o el entorno virtual no está activado.

**Solución:**

```bash
# Windows
cd C:\appTurnos\AppTurnosExplora
.\venvturnos\Scripts\Activate.ps1
python manage.py verificar_integridad_dobladas

# Linux/Mac (AWS EC2)
cd /home/ubuntu/appTurnos/AppTurnosExplora
source /home/ubuntu/venvturnos/bin/activate
python manage.py verificar_integridad_dobladas
```

---

### Problema 2: "SMTPAuthenticationError"

**Error:**
```
SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted')
```

**Causa:** Credenciales de email incorrectas o App Password no configurado.

**Solución:**

1. **Verificar configuración en `settings.py`:**
   ```python
   EMAIL_HOST_USER = 'tu-email@gmail.com'  # ✅ Correcto
   EMAIL_HOST_PASSWORD = 'xxxx xxxx xxxx xxxx'  # ✅ App Password
   ```

2. **Generar nuevo App Password:**
   - Ve a https://myaccount.google.com/apppasswords
   - Genera nueva contraseña
   - Actualiza `settings.py`

3. **Probar email manualmente:**
   ```bash
   python manage.py shell
   ```
   ```python
   from django.core.mail import send_mail
   send_mail('Test', 'Test', 'from@example.com', ['to@example.com'])
   ```

---

### Problema 3: Cron Job No Se Ejecuta

**Síntoma:** No aparecen nuevos logs en `/var/log/appturnos/integridad_dobladas.log`

**Diagnóstico:**

```bash
# 1. Verificar que el cron job está configurado
crontab -l

# 2. Verificar servicio cron
sudo systemctl status cron

# 3. Ver logs del cron
sudo tail -f /var/log/syslog | grep CRON

# 4. Ejecutar manualmente para ver errores
cd /home/ubuntu/appTurnos/AppTurnosExplora && /home/ubuntu/venvturnos/bin/python manage.py verificar_integridad_dobladas --reparar 2>&1
```

**Soluciones Comunes:**

1. **Rutas incorrectas:**
   ```bash
   # Verificar que las rutas existan
   ls /home/ubuntu/appTurnos/AppTurnosExplora/manage.py
   ls /home/ubuntu/venvturnos/bin/python
   ```

2. **Permisos de archivo:**
   ```bash
   sudo chmod +x /home/ubuntu/venvturnos/bin/python
   sudo chown -R ubuntu:ubuntu /var/log/appturnos/
   ```

3. **Variables de entorno:**
   ```bash
   # Agregar al crontab ANTES de la línea del comando
   SHELL=/bin/bash
   PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
   ```

---

### Problema 4: "django.db.utils.OperationalError: no such table"

**Error:**
```
django.db.utils.OperationalError: no such table: solicitudes_solicitudcambio
```

**Causa:** Migraciones no aplicadas.

**Solución:**

```bash
python manage.py migrate
python manage.py verificar_integridad_dobladas
```

---

### Problema 5: Email No Se Envía (Sin Errores)

**Síntoma:** El comando termina sin errores pero no recibes email.

**Causa:** Solo se envía email si hay inconsistencias.

**Solución:**

```bash
# Verificar si hubo inconsistencias
python manage.py verificar_integridad_dobladas --email admin@tudominio.com

# Si dice "✅ No se encontraron inconsistencias" → No se envía email (comportamiento correcto)

# Para probar el email, forzar un envío con el shell
python manage.py shell
```

```python
from django.core.mail import send_mail
from django.conf import settings

send_mail(
    'Prueba Manual',
    'Este es un email de prueba',
    settings.DEFAULT_FROM_EMAIL,
    ['admin@tudominio.com'],
)
```

---

## 🔄 Mantenimiento

### Rotación de Logs

**Crear archivo de configuración:**

```bash
sudo nano /etc/logrotate.d/appturnos
```

**Contenido:**

```
/var/log/appturnos/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0640 ubuntu ubuntu
    sharedscripts
}
```

**Probar configuración:**

```bash
sudo logrotate -d /etc/logrotate.d/appturnos
```

---

### Monitoreo de Rendimiento

```bash
# Ver tamaño de logs
du -h /var/log/appturnos/integridad_dobladas.log

# Ver número de ejecuciones
grep "VERIFICACIÓN DE INTEGRIDAD" /var/log/appturnos/integridad_dobladas.log | wc -l

# Ver inconsistencias encontradas
grep "inconsistencia(s)" /var/log/appturnos/integridad_dobladas.log

# Ver reparaciones exitosas
grep "Solicitud reseteada" /var/log/appturnos/integridad_dobladas.log
```

---

### Backup de Configuración

```bash
# Exportar crontab
crontab -l > crontab_backup_$(date +%Y%m%d).txt

# Copiar configuración de email
cp /home/ubuntu/appTurnos/AppTurnosExplora/config/settings.py \
   /home/ubuntu/backups/settings_$(date +%Y%m%d).py
```

---

## 📞 Soporte

### Comandos Rápidos de Referencia

```bash
# Verificar solo (sin cambios)
python manage.py verificar_integridad_dobladas

# Verificar y reparar
python manage.py verificar_integridad_dobladas --reparar

# Verificar, reparar y enviar email
python manage.py verificar_integridad_dobladas --reparar --email admin@tudominio.com

# Verificar últimos 7 días
python manage.py verificar_integridad_dobladas --dias 7 --reparar

# Ver logs en tiempo real
tail -f /var/log/appturnos/integridad_dobladas.log

# Ver cron jobs
crontab -l

# Editar cron jobs
crontab -e
```

---

### Contacto

- **Email:** soporte@tudominio.com
- **Documentación:** `/docs/SOLUCION_INTEGRIDAD_DOBLADAS.md`
- **Logs:** `/var/log/appturnos/integridad_dobladas.log`

---

## ✅ Checklist de Implementación

### Desarrollo Local

- [ ] Comando funciona correctamente
- [ ] Email de prueba se envía y recibe
- [ ] Logs se generan correctamente
- [ ] Reparación automática funciona

### Producción (AWS EC2)

- [ ] SSH configurado y funcional
- [ ] Rutas del proyecto verificadas
- [ ] Directorio de logs creado
- [ ] Cron job configurado
- [ ] Cron job probado manualmente
- [ ] Email configurado y probado
- [ ] Rotación de logs configurada
- [ ] Primera ejecución exitosa
- [ ] Monitoreo activo (revisar logs diariamente)
- [ ] Documentación actualizada

---

**Fin del Manual**

_Última actualización: Enero 2026_  
_Versión: 1.0_

