# Guía: Exportar e Importar Chats de Cursor

## 📍 Ubicación del Historial de Chats de Cursor

Cursor almacena el historial de conversaciones en diferentes ubicaciones según el sistema operativo:

### Windows
```
%APPDATA%\Cursor\User\globalStorage\
o
%LOCALAPPDATA%\Cursor\User\globalStorage\
o
%USERPROFILE%\AppData\Roaming\Cursor\User\workspaceStorage\
```

**Rutas completas típicas:**
- `C:\Users\[TuUsuario]\AppData\Roaming\Cursor\User\globalStorage\`
- `C:\Users\[TuUsuario]\AppData\Local\Cursor\User\globalStorage\`
- `C:\Users\[TuUsuario]\AppData\Roaming\Cursor\User\workspaceStorage\`

### Linux
```
~/.config/Cursor/User/globalStorage/
o
~/.local/share/Cursor/User/globalStorage/
```

### macOS
```
~/Library/Application Support/Cursor/User/globalStorage/
```

---

## 🔍 Cómo Encontrar los Chats

### Método 1: Desde Cursor

1. **Abre Cursor**
2. **Ve a Configuración**: `Ctrl+,` (Windows/Linux) o `Cmd+,` (Mac)
3. **Busca "Storage" o "Chat History"** en la configuración
4. **Copia la ruta** que aparece

### Método 2: Explorador de Archivos (Windows)

1. Presiona `Windows + R`
2. Escribe: `%APPDATA%\Cursor` y presiona Enter
3. Navega a: `User\globalStorage\` o `User\workspaceStorage\`
4. Busca carpetas con nombres como:
   - `cursor.chat-history`
   - `cursor.conversations`
   - O carpetas con IDs de workspace

### Método 3: Buscar Archivos Manualmente

Ejecuta en PowerShell (como Administrador):

```powershell
# Buscar archivos relacionados con chats en Cursor
Get-ChildItem -Path "$env:APPDATA\Cursor" -Recurse -Filter "*chat*" -ErrorAction SilentlyContinue
Get-ChildItem -Path "$env:APPDATA\Cursor" -Recurse -Filter "*conversation*" -ErrorAction SilentlyContinue
Get-ChildItem -Path "$env:APPDATA\Cursor" -Recurse -Filter "*history*" -ErrorAction SilentlyContinue
```

---

## 💾 Exportar los Chats

### Opción 1: Exportar Carpeta Completa (Recomendado)

1. **Encuentra la carpeta** donde están los chats (ver sección anterior)
2. **Copia toda la carpeta** de Cursor:
   - En Windows: `%APPDATA%\Cursor` o `%LOCALAPPDATA%\Cursor`
   - En Linux: `~/.config/Cursor`
   - En macOS: `~/Library/Application Support/Cursor`

3. **Crea un backup**:
   ```powershell
   # Windows PowerShell
   Compress-Archive -Path "$env:APPDATA\Cursor" -DestinationPath "Cursor_Backup_$(Get-Date -Format 'yyyy-MM-dd').zip"
   ```

4. **Transfiere el ZIP** al otro equipo (USB, nube, email, etc.)

### Opción 2: Exportar Solo los Chats

Si identificas específicamente la carpeta de chats:

1. **Navega a la carpeta** de chats
2. **Selecciona todos los archivos** (Ctrl+A)
3. **Copia** (Ctrl+C)
4. **Pega** en una carpeta de respaldo
5. **Comprime** la carpeta

---

## 📥 Importar los Chats en Otro Equipo

### Pasos para Importar:

1. **Instala Cursor** en el otro equipo (si no está instalado)
2. **Cierra Cursor completamente** en el equipo destino
3. **Ubica la carpeta de Cursor** en el equipo destino (mismas rutas que arriba)
4. **Haz backup** de la configuración actual (por si acaso):
   ```powershell
   # Windows
   Copy-Item "$env:APPDATA\Cursor" "$env:APPDATA\Cursor_backup_$(Get-Date -Format 'yyyy-MM-dd')" -Recurse
   ```
5. **Restaura los archivos**:
   - Descomprime el ZIP que exportaste
   - Copia el contenido a la carpeta de Cursor del equipo destino
   - **Reemplaza** los archivos si te lo pide

6. **Abre Cursor** y verifica que los chats aparezcan

---

## ⚠️ Notas Importantes

### Limitaciones

1. **Los chats están vinculados al workspace**: Si los chats están en `workspaceStorage`, están asociados a rutas específicas del proyecto. Al moverlos, puede que no se muestren correctamente si las rutas del proyecto son diferentes.

2. **Formato de datos**: Cursor puede usar:
   - Base de datos SQLite (archivos `.db`)
   - Archivos JSON
   - Archivos binarios

3. **Sincronización de cuenta**: Si usas una cuenta de Cursor, algunos chats pueden estar en la nube y no en local.

### Alternativa: Exportar Conversaciones Específicas

Si exportar todo no funciona, puedes:

1. **Abrir cada conversación** en Cursor
2. **Copiar el contenido** del chat (seleccionar todo con Ctrl+A)
3. **Pegar en un archivo de texto** con el nombre del proyecto
4. **Guardar** todos en una carpeta `chats_exportados/`

---

## 🔄 Método Alternativo: Documentación Manual

Dado que exportar chats puede ser complicado, **recomiendo usar el documento `CONTEXTO_PROYECTO.md`** que ya creamos, ya que:

✅ Es más confiable  
✅ Está estructurado y organizado  
✅ No depende de versiones de Cursor  
✅ Es fácil de mantener actualizado  
✅ Puede incluirse en el repositorio Git  

---

## 📝 Script de Backup Automático (Windows)

Puedes crear un script para hacer backup automático. Crea un archivo `backup_cursor_chats.ps1`:

```powershell
# Script de backup de chats de Cursor
$fecha = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$destino = "Cursor_Backup_$fecha.zip"
$origen = "$env:APPDATA\Cursor"

if (Test-Path $origen) {
    Compress-Archive -Path $origen -DestinationPath $destino -Force
    Write-Host "Backup creado: $destino" -ForegroundColor Green
} else {
    Write-Host "No se encontró la carpeta de Cursor en: $origen" -ForegroundColor Red
}
```

Ejecuta con:
```powershell
powershell -ExecutionPolicy Bypass -File backup_cursor_chats.ps1
```

---

## 🔗 Ubicaciones Específicas por Tipo de Datos

### Chats por Workspace
```
%APPDATA%\Cursor\User\workspaceStorage\[WORKSPACE-ID]\state.vscdb
```

### Chats Globales
```
%APPDATA%\Cursor\User\globalStorage\[STORAGE-ID]\state.vscdb
```

### Historial General
```
%APPDATA%\Cursor\logs\
%APPDATA%\Cursor\storage\
```

---

## 💡 Recomendación Final

Para compartir el contexto del proyecto entre equipos, la mejor opción es:

1. ✅ **Usar `CONTEXTO_PROYECTO.md`** (ya creado)
2. ✅ **Incluir la carpeta `docs/`** completa
3. ✅ **Compartir el repositorio Git** con todo el código
4. ⚠️ **Exportar chats solo si es absolutamente necesario** (puede no funcionar perfectamente)

El documento de contexto es más valioso que los chats porque está:
- Organizado
- Actualizado
- Libre de información temporal/irrelevante
- Fácil de leer y mantener

---

## 📞 Si Necesitas Ayuda

Si no encuentras los chats o tienes problemas:
1. Revisa la documentación oficial de Cursor: https://cursor.sh/docs
2. Busca en la carpeta de logs: `%APPDATA%\Cursor\logs\`
3. Revisa la configuración de Cursor desde el menú Settings

---

**Última actualización**: Enero 2025



