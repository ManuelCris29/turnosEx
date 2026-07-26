# Instrucciones para Modificar Google Apps Script

## Objetivo
Permitir que el formulario de Google Apps Script se cargue dentro de un iframe en la página de beneficios.

## Pasos a Seguir

### 1. Abrir el Google Apps Script
1. Ve a [script.google.com](https://script.google.com)
2. Abre el proyecto del formulario de beneficios
3. Busca el archivo que contiene la función que genera el HTML del formulario

### 2. Modificar el Código

Busca la función que crea el HTML (probablemente algo como `doGet()` o `doPost()`) y agrega la siguiente línea:

```javascript
function doGet(e) {
  // ... tu código existente ...
  
  // Crear el HTML del formulario
  var htmlOutput = HtmlService.createHtmlOutput(htmlContent);
  
  // ⬇️ AGREGAR ESTA LÍNEA ⬇️
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  
  // ... resto del código ...
  
  return htmlOutput;
}
```

### 3. Explicación de la Línea

```javascript
htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
```

Esta línea le dice al navegador que permita que el contenido se cargue en un iframe desde cualquier dominio. Las opciones disponibles son:

- `HtmlService.XFrameOptionsMode.ALLOWALL` - Permite embedding desde cualquier dominio (lo que necesitas)
- `HtmlService.XFrameOptionsMode.DENY` - Bloquea todo embedding (por defecto)
- `HtmlService.XFrameOptionsMode.SAMEORIGIN` - Solo permite embedding desde el mismo dominio

### 4. Ejemplo Completo

```javascript
function doGet(e) {
  // Tu código para obtener datos del usuario, etc.
  
  // Crear el HTML del formulario
  var template = HtmlService.createTemplate(`
    <!DOCTYPE html>
    <html>
      <head>
        <title>Formulario de Beneficios</title>
      </head>
      <body>
        <!-- Tu formulario aquí -->
        <form>
          <!-- Campos del formulario -->
        </form>
      </body>
    </html>
  `);
  
  // Evaluar el template
  var htmlContent = template.evaluate();
  
  // ⬇️ ESTA ES LA LÍNEA CLAVE ⬇️
  htmlContent.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  
  return htmlContent;
}
```

### 5. Guardar y Desplegar

1. Guarda los cambios en el script
2. Si ya tienes un despliegue, actualízalo:
   - Ve a "Desplegar" → "Gestionar despliegues"
   - Haz clic en el ícono de edición (lápiz)
   - Selecciona "Nueva versión"
   - Haz clic en "Desplegar"
3. Si no tienes un despliegue, créalo:
   - Ve a "Desplegar" → "Nuevo despliegue"
   - Selecciona "Tipo: Aplicación web"
   - Configura los permisos necesarios
   - Copia la URL de despliegue

### 6. Actualizar el Template de Django

Una vez que hayas modificado el script, actualiza el template `beneficios.html` para usar un iframe:

```html
<iframe 
    src="{{ google_script_url }}" 
    width="100%" 
    height="800px" 
    frameborder="0"
    style="border: none;">
</iframe>
```

## Notas Importantes

⚠️ **Seguridad**: `ALLOWALL` permite que cualquier sitio web embeba tu formulario. Si esto es un problema de seguridad, considera usar `SAMEORIGIN` y asegúrate de que tu aplicación Django esté en el mismo dominio que el script.

✅ **Ventajas**: Una vez configurado, el formulario se cargará directamente dentro de la página de beneficios sin necesidad de abrir una nueva ventana.

## Verificación

Después de hacer los cambios:
1. Recarga la página de beneficios en Django
2. El formulario debería cargarse dentro del iframe
3. Si aún ves errores de `X-Frame-Options`, verifica que:
   - Guardaste los cambios en el script
   - Actualizaste el despliegue
   - Estás usando la URL correcta del despliegue


