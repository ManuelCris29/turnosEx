# Solución: Error 403 y X-Frame-Options

## 🔴 Problema Identificado

Los errores que estás viendo indican:

1. **403 Forbidden**: El script no está configurado para acceso público o requiere autenticación
2. **X-Frame-Options**: El script está bloqueando el embedding en iframes

## ✅ Solución: Configurar Google Apps Script

### Paso 1: Acceder al Script

1. Ve a https://script.google.com
2. Inicia sesión con tu cuenta de `parqueexplora.org`
3. Busca el script que genera el formulario de beneficios
4. Haz clic para abrirlo

### Paso 2: Verificar que sea una Web App

1. En el editor del script, verifica que tenga una función `doGet()` o `doPost()`
2. Si no la tiene, el script no está configurado como Web App

### Paso 3: Configurar como Web App (NUEVA IMPLEMENTACIÓN)

1. En el menú superior, haz clic en **"Deploy" (Implementar)**
2. Selecciona **"New deployment" (Nueva implementación)**
3. O si ya existe una, haz clic en el ícono de engranaje ⚙️ junto a "Manage deployments"

### Paso 4: Configurar Opciones de Acceso

En la ventana de configuración:

#### A. Tipo de implementación
- Selecciona **"Web app"** (no "API executable")

#### B. Configuración
- **Description (Descripción)**: Opcional, puedes poner "Formulario de Beneficios"
- **Execute as (Ejecutar como)**: 
  - Selecciona **"Me"** (tu cuenta) si el script necesita acceso a tus datos
  - O **"User accessing the web app"** si cada usuario debe acceder con sus credenciales

#### C. Who has access (Quién tiene acceso) ⚠️ **CRÍTICO**
- **DEBES seleccionar**: **"Anyone" (Cualquiera)** o **"Anyone with Google account"**
- ❌ **NO seleccionar**: "Only myself" (esto causa el error 403)

#### D. Haz clic en **"Deploy"**

### Paso 5: Copiar el URL de la Web App

Después de hacer deploy:
1. Se mostrará un URL como: `https://script.google.com/a/macros/parqueexplora.org/s/.../exec`
2. **IMPORTANTE**: Usa el URL que termina en `/exec` (no `/dev`)
3. Copia este URL

### Paso 6: Modificar el Código del Script (OPCIONAL pero RECOMENDADO)

Si tienes acceso al código del script, agrega esta línea para permitir explícitamente el embedding:

```javascript
function doGet(e) {
  // Tu código existente para generar el HTML...
  var htmlOutput = HtmlService.createHtmlOutput(htmlContent);
  
  // ⚠️ IMPORTANTE: Permitir embedding en iframes
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  
  return htmlOutput;
}
```

O si usas `ContentService`:

```javascript
function doGet(e) {
  // Tu código existente...
  
  return ContentService
    .createTextOutput(htmlContent)
    .setMimeType(ContentService.MimeType.HTML);
}
```

**Nota**: `ContentService` por defecto permite embedding, pero `HtmlService` necesita configuración explícita.

### Paso 7: Redesplegar (si modificaste el código)

1. Si modificaste el código, ve a **"Deploy"** → **"Manage deployments"**
2. Haz clic en el ícono de edición (lápiz) junto a tu deployment
3. Selecciona **"New version"**
4. Haz clic en **"Deploy"**

### Paso 8: Actualizar el URL

1. Copia el **nuevo URL** que termina en `/exec` (no `/dev`)
2. Actualiza el archivo `test_iframe_beneficios.html` con el nuevo URL
3. Vuelve a probar

---

## 🔍 Verificación

Después de configurar, verifica:

1. **El URL debe terminar en `/exec`**, no `/dev`
2. **El acceso debe ser "Anyone"** o "Anyone with Google account"
3. **El código debe tener `setXFrameOptionsMode(ALLOWALL)`** si usas `HtmlService`

---

## 📝 Nota sobre `/dev` vs `/exec`

- **`/dev`**: URL de desarrollo, puede tener restricciones adicionales
- **`/exec`**: URL de producción, es el que debes usar en producción

---

## 🆘 Si aún no funciona

### Opción A: Verificar permisos del script

1. Ve a https://script.google.com
2. Abre tu script
3. Ve a **"Deploy"** → **"Manage deployments"**
4. Verifica que el deployment tenga:
   - ✅ Tipo: "Web app"
   - ✅ Execute as: "Me" o "User accessing..."
   - ✅ Who has access: **"Anyone"** o "Anyone with Google account"

### Opción B: Verificar el código

Asegúrate de que el código tenga:

```javascript
function doGet(e) {
  // Tu código...
  var htmlOutput = HtmlService.createHtmlOutput(htmlContent);
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  return htmlOutput;
}
```

### Opción C: Probar con URL `/exec`

El URL que estás usando termina en `/dev`. Prueba cambiándolo a `/exec`:

```
https://script.google.com/a/macros/parqueexplora.org/s/AKfycbzEclLu4hB0BkDQ8d2wDgU3W4oFUFE_JbzTVl6k97o/exec
```

---

## ✅ Checklist Final

Antes de probar de nuevo, verifica:

- [ ] El script está configurado como "Web app"
- [ ] "Who has access" está en "Anyone" o "Anyone with Google account"
- [ ] El código tiene `setXFrameOptionsMode(ALLOWALL)` (si usa HtmlService)
- [ ] Estás usando el URL que termina en `/exec` (no `/dev`)
- [ ] Has hecho "Deploy" después de cualquier cambio

---

## 🎯 Resultado Esperado

Después de configurar correctamente:

- ✅ El iframe carga sin error 403
- ✅ No hay errores de X-Frame-Options
- ✅ El formulario se muestra correctamente
- ✅ Puedes interactuar con todos los campos

