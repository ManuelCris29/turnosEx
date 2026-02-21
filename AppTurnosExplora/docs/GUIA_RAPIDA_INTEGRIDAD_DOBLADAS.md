# Guía Rápida: Verificación de Integridad de Dobladas

**Referencia rápida para uso diario**

---

## 🚀 Comandos Más Usados

### Desarrollo Local (Windows)

```powershell
# Activar entorno virtual
cd C:\appTurnos\AppTurnosExplora
.\venvturnos\Scripts\Activate.ps1

# Verificar sin cambios
python manage.py verificar_integridad_dobladas

# Verificar y reparar
python manage.py verificar_integridad_dobladas --reparar

# Verificar últimos 7 días
python manage.py verificar_integridad_dobladas --dias 7 --reparar
```

### Producción (AWS EC2)

```bash
# Conectar al servidor
ssh -i "tu-llave.pem" ubuntu@tu-servidor-ec2.amazonaws.com

# Ir al proyecto
cd /home/ubuntu/appTurnos/AppTurnosExplora

# Verificar y reparar
/home/ubuntu/venvturnos/bin/python manage.py verificar_integridad_dobladas --reparar --email admin@tudominio.com

# Ver logs
tail -f /var/log/appturnos/integridad_dobladas.log

# Ver cron jobs
crontab -l
```

---

## ⚙️ Configuración Cron Job (Una Sola Vez)

```bash
# 1. Crear directorio de logs
sudo mkdir -p /var/log/appturnos
sudo touch /var/log/appturnos/integridad_dobladas.log
sudo chown -R ubuntu:ubuntu /var/log/appturnos

# 2. Editar crontab
crontab -e

# 3. Agregar esta línea (ejecutar diario a las 3:00 AM)
0 3 * * * cd /home/ubuntu/appTurnos/AppTurnosExplora && /home/ubuntu/venvturnos/bin/python manage.py verificar_integridad_dobladas --reparar --email admin@tudominio.com >> /var/log/appturnos/integridad_dobladas.log 2>&1

# 4. Guardar y salir (Ctrl+X, Y, Enter en nano)

# 5. Verificar
crontab -l
```

---

## 📋 Casos de Uso Comunes

### ✅ Post-Deploy

```bash
python manage.py verificar_integridad_dobladas --reparar
```

### ⚠️ Usuario Reporta Problema

```bash
# Diagnóstico específico
python scripts/diagnosticar_doblada_marco.py

# Verificar y reparar últimos 7 días
python manage.py verificar_integridad_dobladas --dias 7 --reparar
```

### 📊 Auditoría Mensual

```bash
python manage.py verificar_integridad_dobladas --dias 30 --email admin@tudominio.com
```

---

## 🔍 Ver Logs

```bash
# Tiempo real
tail -f /var/log/appturnos/integridad_dobladas.log

# Últimas 50 líneas
tail -n 50 /var/log/appturnos/integridad_dobladas.log

# Buscar errores
grep -i "error" /var/log/appturnos/integridad_dobladas.log

# Buscar inconsistencias
grep -i "inconsistencia" /var/log/appturnos/integridad_dobladas.log

# Contar ejecuciones
grep "VERIFICACIÓN DE INTEGRIDAD" /var/log/appturnos/integridad_dobladas.log | wc -l
```

---

## 🔧 Troubleshooting Rápido

### Error: "No module named 'solicitudes'"

```bash
cd C:\appTurnos\AppTurnosExplora  # o cd /home/ubuntu/appTurnos/AppTurnosExplora
.\venvturnos\Scripts\Activate.ps1  # o source /home/ubuntu/venvturnos/bin/activate
```

### Error: Email no se envía

```bash
# Probar email manualmente
python manage.py shell
```

```python
from django.core.mail import send_mail
send_mail('Test', 'Test', 'from@example.com', ['to@example.com'])
```

### Cron no se ejecuta

```bash
# Ver logs del cron
sudo tail -f /var/log/syslog | grep CRON

# Probar manualmente
cd /home/ubuntu/appTurnos/AppTurnosExplora && /home/ubuntu/venvturnos/bin/python manage.py verificar_integridad_dobladas --reparar 2>&1
```

---

## 📧 Configurar Email (Gmail)

**En `config/settings.py`:**

```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'tu-email@gmail.com'
EMAIL_HOST_PASSWORD = 'xxxx xxxx xxxx xxxx'  # App Password
DEFAULT_FROM_EMAIL = 'AppTurnos <no-reply@tudominio.com>'
```

**Obtener App Password:**
1. https://myaccount.google.com/apppasswords
2. Generar contraseña para "Django AppTurnos"
3. Copiar y pegar en `EMAIL_HOST_PASSWORD`

---

## 📊 Interpretación de Resultados

### ✅ Sin Problemas

```
✅ No se encontraron inconsistencias
```

**Acción:** Ninguna. Todo bien.

---

### ❌ Con Inconsistencias (Reparadas)

```
❌ Se encontraron 2 inconsistencia(s):

1. Solicitud ID: 111
   🔧 Intentando reparar...
      ✅ Solicitud reseteada a pendiente. Debe ser aprobada nuevamente.
```

**Acción:** Notificar a usuarios afectados para que re-aprueben.

---

## ⏰ Frecuencia Recomendada

| Escenario | Frecuencia | Comando |
|-----------|-----------|---------|
| **Automático (Cron)** | Diario 3:00 AM | `--reparar --email` |
| **Post-Deploy** | Cada deploy | `--reparar` |
| **Reporte Usuario** | Inmediato | `--dias 7 --reparar` |
| **Auditoría** | Mensual | `--dias 30 --email` |

---

## 📱 Contacto de Soporte

- **Manual completo:** `docs/MANUAL_VERIFICACION_INTEGRIDAD_DOBLADAS.md`
- **Documentación técnica:** `docs/SOLUCION_INTEGRIDAD_DOBLADAS.md`
- **Email:** soporte@tudominio.com

---

**Última actualización:** Enero 2026







