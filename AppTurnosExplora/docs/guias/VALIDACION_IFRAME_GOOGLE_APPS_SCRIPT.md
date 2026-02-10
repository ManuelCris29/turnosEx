# Validación de Embedding para Google Apps Script

## 1. Validar que el Google Apps Script permita embedding

### Método 1: Prueba rápida con HTML local

Crea un archivo HTML de prueba y ábrelo en tu navegador:

```html
<!DOCTYPE html>
<html>
<head>
    <title>Prueba de Embedding</title>
</head>
<body>
    <h1>Prueba de iframe</h1>
    <iframe 
        src="https://script.google.com/a/macros/parqueexplora.org/s/AKfycbzEclLu4hB0BkDQ8d2wDgU3W4oFUFE_JbzTVl6k97o/dev"
        width="100%" 
        height="800px"
        frameborder="0"
        style="border: 1px solid #ccc;">
    </iframe>
</body>
</html>
```

**Resultados posibles:**
- ✅ **Si se carga correctamente**: El script permite embedding, puedes proceder.
- ❌ **Si aparece error "X-Frame-Options" o "Refused to display"**: El script NO permite embedding, necesitas configurarlo.

### Método 2: Verificar en la consola del navegador

1. Abre el URL del script directamente en el navegador:
   ```
   https://script.google.com/a/macros/parqueexplora.org/s/AKfycbzEclLu4hB0BkDQ8d2wDgU3W4oFUFE_JbzTVl6k97o/dev
   ```

2. Abre las herramientas de desarrollador (F12)

3. Ve a la pestaña "Console" (Consola)

4. Busca mensajes como:
   - `Refused to display '...' in a frame because it set 'X-Frame-Options' to 'deny'`
   - `Refused to display '...' in a frame because it set 'X-Frame-Options' to 'sameorigin'`

5. Ve a la pestaña "Network" (Red) y busca el header `X-Frame-Options` en la respuesta

**Si encuentras `X-Frame-Options: DENY` o `X-Frame-Options: SAMEORIGIN`**: Necesitas configurar el script.

### Método 3: Usar herramienta online

Puedes usar herramientas como:
- https://www.whatismybrowser.com/detect/is-iframe-allowed
- O simplemente intentar cargar el URL en un iframe de prueba

---

## 2. Configurar Google Apps Script para permitir embedding

Si el script NO permite embedding, necesitas configurarlo:

### Paso 1: Abrir el script en Google Apps Script

1. Ve a https://script.google.com
2. Encuentra tu script (el que genera el formulario de beneficios)
3. Abre el editor del script

### Paso 2: Configurar como Web App

1. En el menú, ve a **"Deploy" (Implementar)** → **"New deployment" (Nueva implementación)**
2. O si ya existe, haz clic en el ícono de engranaje ⚙️ junto a "Manage deployments"

### Paso 3: Configurar opciones de seguridad

En la configuración de deployment:

1. **"Execute as" (Ejecutar como)**: 
   - Selecciona "Me" (tu cuenta) o "User accessing the web app"

2. **"Who has access" (Quién tiene acceso)**:
   - Selecciona **"Anyone" (Cualquiera)** o **"Anyone with Google account"**
   - ⚠️ **IMPORTANTE**: Si seleccionas "Only myself", el iframe NO funcionará para otros usuarios

3. **Configuración adicional**:
   - Asegúrate de que el script esté configurado como "Web app"
   - No como "API executable"

### Paso 4: Verificar headers en el código (opcional)

Si tienes acceso al código del script, puedes agregar headers explícitos:

```javascript
function doGet(e) {
  // Tu código existente...
  
  // Crear HTML output
  var htmlOutput = HtmlService.createHtmlOutput(htmlContent);
  
  // IMPORTANTE: Permitir embedding en iframes
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  
  return htmlOutput;
}
```

O si usas `ContentService`:

```javascript
function doGet(e) {
  // Tu código...
  
  return ContentService
    .createTextOutput(htmlContent)
    .setMimeType(ContentService.MimeType.HTML);
}
```

### Paso 5: Redesplegar

Después de hacer cambios:
1. Haz clic en **"Deploy"** → **"Manage deployments"**
2. Haz clic en el ícono de edición (lápiz) junto a tu deployment
3. Selecciona **"New version"** si hiciste cambios en el código
4. Haz clic en **"Deploy"**

---

## 3. Validar que la autenticación funcione dentro del iframe

### Método 1: Prueba manual

1. Crea el archivo HTML de prueba (del Método 1 anterior)
2. Abre el archivo en tu navegador
3. Intenta usar el formulario dentro del iframe:
   - ¿Puedes seleccionar el beneficio?
   - ¿Puedes seleccionar la fecha?
   - ¿Puedes hacer clic en "Enviar"?
   - ¿Se envía correctamente?

### Método 2: Verificar en la consola

1. Abre el HTML de prueba
2. Abre las herramientas de desarrollador (F12)
3. Ve a la pestaña "Console"
4. Busca errores relacionados con:
   - `Blocked a frame with origin...`
   - `Permission denied`
   - `Cross-origin` errors

### Método 3: Verificar cookies/sesión

1. Abre el URL del script directamente (sin iframe)
2. Inicia sesión si es necesario
3. Luego abre el HTML de prueba con el iframe
4. Verifica si mantiene la sesión

**Si la autenticación NO funciona:**
- El script puede estar usando cookies de sesión que no se comparten con el iframe
- Puede requerir autenticación OAuth que no funciona en iframes
- Puede tener restricciones de SameSite en las cookies

---

## 4. Soluciones alternativas si no funciona

### Si el embedding está bloqueado:

**Opción A: Configurar el script** (recomendado)
- Sigue los pasos de la sección 2

**Opción B: Usar proxy en Django** (más complejo)
- Crear una vista en Django que haga proxy del contenido
- No recomendado por complejidad y posibles problemas de autenticación

**Opción C: Abrir en nueva ventana** (no cumple el requisito)
- Usar `target="_blank"` en lugar de iframe
- No es lo que quieres (salir de la app)

### Si la autenticación no funciona:

**Opción A: Configurar el script para acceso público**
- Si el formulario no requiere autenticación específica del usuario
- Configurar "Who has access" → "Anyone"

**Opción B: Usar autenticación basada en parámetros**
- Pasar información del usuario como parámetros en el URL del iframe
- El script puede recibir estos parámetros y autenticar internamente

**Opción C: Usar OAuth flow externo**
- Más complejo, requiere redirección fuera del iframe
- No es ideal para tu caso

---

## 5. Checklist de validación

Antes de implementar en Django, verifica:

- [ ] El iframe carga sin errores de X-Frame-Options
- [ ] El formulario se muestra correctamente dentro del iframe
- [ ] Puedo interactuar con todos los campos del formulario
- [ ] Puedo enviar el formulario y funciona correctamente
- [ ] La autenticación funciona (si es necesaria)
- [ ] No hay errores en la consola del navegador
- [ ] El formulario se ve bien en diferentes tamaños de pantalla

---

## 6. Comandos rápidos para probar

### Crear archivo de prueba HTML

Crea un archivo `test_iframe.html` en tu escritorio:

```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prueba de Embedding</title>
    <style>
        body {
            margin: 0;
            padding: 20px;
            font-family: Arial, sans-serif;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        iframe {
            width: 100%;
            height: 800px;
            border: 2px solid #ccc;
            border-radius: 5px;
        }
        .status {
            padding: 10px;
            margin-bottom: 10px;
            border-radius: 5px;
        }
        .success {
            background-color: #d4edda;
            color: #155724;
        }
        .error {
            background-color: #f8d7da;
            color: #721c24;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Prueba de Embedding - Google Apps Script</h1>
        <div id="status" class="status">Cargando...</div>
        <iframe 
            id="testIframe"
            src="https://script.google.com/a/macros/parqueexplora.org/s/AKfycbzEclLu4hB0BkDQ8d2wDgU3W4oFUFE_JbzTVl6k97o/dev"
            frameborder="0"
            allowfullscreen>
        </iframe>
    </div>
    
    <script>
        const iframe = document.getElementById('testIframe');
        const status = document.getElementById('status');
        
        iframe.onload = function() {
            status.textContent = '✅ Iframe cargado correctamente';
            status.className = 'status success';
        };
        
        iframe.onerror = function() {
            status.textContent = '❌ Error al cargar el iframe. Verifica la consola del navegador (F12)';
            status.className = 'status error';
        };
        
        // Verificar después de 5 segundos si no se cargó
        setTimeout(function() {
            if (status.textContent === 'Cargando...') {
                status.textContent = '⚠️ El iframe está tardando en cargar. Verifica la consola del navegador (F12)';
                status.className = 'status error';
            }
        }, 5000);
    </script>
</body>
</html>
```

Abre este archivo en tu navegador y verifica:
1. Si se carga correctamente
2. Si puedes interactuar con el formulario
3. Si hay errores en la consola (F12)

---

## 7. Resultado esperado

Si todo funciona correctamente, deberías ver:
- ✅ El formulario de beneficios cargándose dentro del iframe
- ✅ Los campos pre-llenados (Documento, Nombre, etc.)
- ✅ Poder seleccionar el beneficio del dropdown
- ✅ Poder seleccionar la fecha
- ✅ Poder hacer clic en "Enviar" y que funcione

Si ves esto, **puedes proceder con la implementación en Django** sin problemas.


