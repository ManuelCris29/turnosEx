# Manual de Creación del Entorno Virtual

Este manual te guiará paso a paso para crear y configurar el entorno virtual del proyecto **AppTurnosExplora** desde cero.

---

## 📋 Tabla de Contenidos

1. [Requisitos Previos](#requisitos-previos)
2. [Creación del Entorno Virtual](#creación-del-entorno-virtual)
3. [Activación del Entorno Virtual](#activación-del-entorno-virtual)
4. [Instalación de Dependencias](#instalación-de-dependencias)
5. [Configuración de Base de Datos](#configuración-de-base-de-datos)
6. [Configuración Inicial de Django](#configuración-inicial-de-django)
7. [Verificación de la Instalación](#verificación-de-la-instalación)
8. [Desactivación del Entorno Virtual](#desactivación-del-entorno-virtual)
9. [Solución de Problemas Comunes](#solución-de-problemas-comunes)

---

## 🔧 Requisitos Previos

### 1. Python 3.12.4 o superior

El proyecto requiere **Python 3.12.4** o una versión compatible (3.12.x).

#### Verificar instalación de Python

**Windows (PowerShell o CMD):**
```powershell
python --version
```

**Linux/macOS:**
```bash
python3 --version
```

Si no tienes Python instalado o tienes una versión anterior:
- **Windows**: Descarga desde [python.org](https://www.python.org/downloads/)
- **Linux**: `sudo apt update && sudo apt install python3.12 python3.12-venv python3-pip`
- **macOS**: `brew install python@3.12` (requiere Homebrew)

### 2. pip (Gestor de paquetes de Python)

#### Verificar instalación de pip

**Windows:**
```powershell
python -m pip --version
```

**Linux/macOS:**
```bash
python3 -m pip --version
```

Si pip no está instalado, instálalo con:
```bash
python -m ensurepip --upgrade
```

### 3. MySQL (Base de datos)

El proyecto utiliza MySQL como base de datos. Asegúrate de tener MySQL instalado y configurado.

**Windows:**
- Descarga MySQL desde [mysql.com](https://dev.mysql.com/downloads/installer/)
- O instala XAMPP que incluye MySQL

**Linux:**
```bash
sudo apt update
sudo apt install mysql-server
```

**macOS:**
```bash
brew install mysql
```

---

## 🚀 Creación del Entorno Virtual

### Windows

#### Opción 1: PowerShell

1. Abre PowerShell en la raíz del proyecto (`C:\appTurnos`)
2. Ejecuta el siguiente comando:

```powershell
python -m venv venvturnos
```

#### Opción 2: CMD (Símbolo del sistema)

1. Abre CMD en la raíz del proyecto (`C:\appTurnos`)
2. Ejecuta el siguiente comando:

```cmd
python -m venv venvturnos
```

### Linux/macOS

1. Abre la terminal en la raíz del proyecto
2. Ejecuta el siguiente comando:

```bash
python3 -m venv venvturnos
```

### Verificación

Después de ejecutar el comando, deberías ver una nueva carpeta llamada `venvturnos` en la raíz del proyecto. Esta carpeta contiene el entorno virtual aislado.

**Estructura esperada:**
```
appTurnos/
├── venvturnos/          ← Entorno virtual creado
├── AppTurnosExplora/
│   ├── requirements.txt
│   ├── manage.py
│   └── ...
└── ...
```

---

## ✅ Activación del Entorno Virtual

**IMPORTANTE**: Siempre debes activar el entorno virtual antes de trabajar en el proyecto.

### Windows

#### PowerShell

```powershell
.\venvturnos\Scripts\Activate.ps1
```

Si obtienes un error de política de ejecución, ejecuta primero:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### CMD (Símbolo del sistema)

```cmd
venvturnos\Scripts\activate.bat
```

### Linux/macOS

```bash
source venvturnos/bin/activate
```

### Verificación de Activación

Cuando el entorno virtual esté activado, verás el prefijo `(venvturnos)` al inicio de tu línea de comandos:

**Windows:**
```
(venvturnos) PS C:\appTurnos>
```

**Linux/macOS:**
```
(venvturnos) usuario@maquina:~/appTurnos$
```

---

## 📦 Instalación de Dependencias

Una vez activado el entorno virtual, instala todas las dependencias del proyecto.

### 1. Navegar a la carpeta del proyecto

**Windows:**
```powershell
cd AppTurnosExplora
```

**Linux/macOS:**
```bash
cd AppTurnosExplora
```

### 2. Actualizar pip (recomendado)

```bash
python -m pip install --upgrade pip
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

Este comando instalará todas las dependencias listadas en `requirements.txt`:
- Django 5.2.2
- django-simple-history 3.8.0
- django-widget-tweaks 1.5.0
- mysqlclient 2.2.7
- Y otras dependencias necesarias

### 4. Verificar instalación

Verifica que Django se instaló correctamente:

```bash
python manage.py --version
```

Deberías ver: `5.2.2`

---

## 🗄️ Configuración de Base de Datos

### 1. Crear la base de datos en MySQL

Conéctate a MySQL y crea la base de datos:

```sql
CREATE DATABASE bdturnosex CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. Configurar credenciales

Edita el archivo `AppTurnosExplora/config/db.py` y actualiza las credenciales de MySQL según tu configuración:

```python
DATABASESMYSQL = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'bdturnosex',           # Nombre de tu base de datos
        'USER': 'root',                 # Tu usuario de MySQL
        'PASSWORD': 'tu_contraseña',    # Tu contraseña de MySQL
        'HOST': 'localhost',
        'PORT': '3306',
    }
}
```

**⚠️ IMPORTANTE**: No subas este archivo con credenciales reales a Git. Usa variables de entorno en producción.

---

## ⚙️ Configuración Inicial de Django

### 1. Ejecutar migraciones

Aplica las migraciones para crear las tablas en la base de datos:

```bash
python manage.py migrate
```

Este comando creará todas las tablas necesarias en la base de datos `bdturnosex`.

### 2. Crear superusuario (opcional)

Crea un usuario administrador para acceder al panel de administración de Django:

```bash
python manage.py createsuperuser
```

Sigue las instrucciones para ingresar:
- Nombre de usuario
- Correo electrónico
- Contraseña

### 3. Recopilar archivos estáticos (si es necesario)

```bash
python manage.py collectstatic
```

---

## 🧪 Verificación de la Instalación

### 1. Verificar que Django funciona

Ejecuta el servidor de desarrollo:

```bash
python manage.py runserver
```

Deberías ver un mensaje similar a:

```
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

### 2. Acceder a la aplicación

Abre tu navegador y visita:
- **Aplicación**: http://127.0.0.1:8000/
- **Admin de Django**: http://127.0.0.1:8000/admin/

### 3. Verificar dependencias instaladas

Lista todas las dependencias instaladas:

```bash
pip list
```

Deberías ver Django y todas las demás dependencias del proyecto.

---

## 🚪 Desactivación del Entorno Virtual

Cuando termines de trabajar en el proyecto, puedes desactivar el entorno virtual ejecutando:

```bash
deactivate
```

El prefijo `(venvturnos)` desaparecerá de tu línea de comandos.

---

## 🔧 Solución de Problemas Comunes

### Error: "python no se reconoce como comando"

**Solución:**
- En Windows, usa `py` en lugar de `python`: `py -m venv venvturnos`
- O agrega Python al PATH del sistema
- En Linux/macOS, usa `python3` en lugar de `python`

### Error: "No se puede cargar el archivo porque la ejecución de scripts está deshabilitada" (PowerShell)

**Solución:**
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Luego intenta activar el entorno virtual nuevamente.

### Error al instalar mysqlclient

**Windows:**
1. Instala Microsoft Visual C++ Build Tools desde [visualstudio.com](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. O descarga los binarios precompilados de mysqlclient

**Linux:**
```bash
sudo apt-get install python3-dev default-libmysqlclient-dev build-essential
pip install mysqlclient
```

**macOS:**
```bash
brew install mysql-client
export PATH="/usr/local/opt/mysql-client/bin:$PATH"
pip install mysqlclient
```

### Error: "ModuleNotFoundError: No module named 'django'"

**Solución:**
- Asegúrate de que el entorno virtual esté activado (debe aparecer `(venvturnos)` en tu terminal)
- Verifica que instalaste las dependencias: `pip install -r requirements.txt`

### Error de conexión a MySQL

**Solución:**
1. Verifica que MySQL esté ejecutándose:
   - **Windows**: Revisa los servicios de Windows
   - **Linux**: `sudo systemctl status mysql`
   - **macOS**: `brew services list`

2. Verifica las credenciales en `AppTurnosExplora/config/db.py`

3. Prueba la conexión manualmente:
   ```bash
   mysql -u root -p
   ```

### Error: "django.db.utils.OperationalError: (1045, 'Access denied')"

**Solución:**
- Verifica el usuario y contraseña en `config/db.py`
- Asegúrate de que el usuario tenga permisos sobre la base de datos:
  ```sql
  GRANT ALL PRIVILEGES ON bdturnosex.* TO 'root'@'localhost';
  FLUSH PRIVILEGES;
  ```

### El entorno virtual no se activa

**Solución:**
- Verifica que estés en la carpeta correcta (raíz del proyecto)
- Verifica que la carpeta `venvturnos` existe
- En Windows, asegúrate de usar la ruta correcta: `.\venvturnos\Scripts\Activate.ps1` (PowerShell) o `venvturnos\Scripts\activate.bat` (CMD)

---

## 📝 Resumen de Comandos Rápidos

### Crear y configurar el entorno virtual (primera vez)

**Windows (PowerShell):**
```powershell
# Crear entorno virtual
python -m venv venvturnos

# Activar entorno virtual
.\venvturnos\Scripts\Activate.ps1

# Navegar al proyecto
cd AppTurnosExplora

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar migraciones
python manage.py migrate

# Crear superusuario (opcional)
python manage.py createsuperuser

# Iniciar servidor
python manage.py runserver
```

**Linux/macOS:**
```bash
# Crear entorno virtual
python3 -m venv venvturnos

# Activar entorno virtual
source venvturnos/bin/activate

# Navegar al proyecto
cd AppTurnosExplora

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar migraciones
python manage.py migrate

# Crear superusuario (opcional)
python manage.py createsuperuser

# Iniciar servidor
python manage.py runserver
```

### Comandos para sesiones futuras

```bash
# 1. Activar entorno virtual
# Windows PowerShell: .\venvturnos\Scripts\Activate.ps1
# Windows CMD: venvturnos\Scripts\activate.bat
# Linux/macOS: source venvturnos/bin/activate

# 2. Navegar al proyecto
cd AppTurnosExplora

# 3. Iniciar servidor
python manage.py runserver

# 4. Al terminar, desactivar entorno virtual
deactivate
```

---

## 📚 Recursos Adicionales

- [Documentación oficial de Django](https://docs.djangoproject.com/)
- [Documentación de Python venv](https://docs.python.org/3/library/venv.html)
- [Documentación de MySQL](https://dev.mysql.com/doc/)

---

## ✅ Checklist de Instalación

Usa este checklist para asegurarte de que todo esté configurado correctamente:

- [ ] Python 3.12.4 o superior instalado
- [ ] pip instalado y actualizado
- [ ] MySQL instalado y ejecutándose
- [ ] Entorno virtual `venvturnos` creado
- [ ] Entorno virtual activado (se ve `(venvturnos)` en la terminal)
- [ ] Dependencias instaladas (`pip install -r requirements.txt`)
- [ ] Base de datos `bdturnosex` creada en MySQL
- [ ] Credenciales de MySQL configuradas en `config/db.py`
- [ ] Migraciones ejecutadas (`python manage.py migrate`)
- [ ] Superusuario creado (opcional)
- [ ] Servidor de desarrollo ejecutándose correctamente

---

## 📞 Soporte

Si encuentras problemas que no están cubiertos en este manual:

1. Revisa la sección [Solución de Problemas Comunes](#solución-de-problemas-comunes)
2. Consulta la documentación del proyecto en la carpeta `docs/`
3. Contacta al equipo de desarrollo

---

**Última actualización**: Enero 2025  
**Versión del proyecto**: Django 5.2.2  
**Python requerido**: 3.12.4+



