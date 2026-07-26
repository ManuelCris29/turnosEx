# Modificación del Google Apps Script para Permitir iframe

## Ubicación de la Modificación

Debes modificar la función `doGet()` en dos lugares:

### 1. Flujo Principal (Línea ~47)

**ANTES:**
```javascript
// Carga la plantilla HTML y pasa los datos dinámicos
const template = HtmlService.createTemplateFromFile('datosUser');
template.userData = userData; // Pasa los datos del usuario al HTML
return template.evaluate().setTitle('Formulario Beneficio').setWidth(800).setHeight(600); // Evalúa y retorna el HTML renderizado
```

**DESPUÉS:**
```javascript
// Carga la plantilla HTML y pasa los datos dinámicos
const template = HtmlService.createTemplateFromFile('datosUser');
template.userData = userData; // Pasa los datos del usuario al HTML
const htmlOutput = template.evaluate().setTitle('Formulario Beneficio').setWidth(800).setHeight(600);
htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); // ⬅️ AGREGAR ESTA LÍNEA
return htmlOutput;
```

### 2. Caso de Error - Usuario no encontrado (Línea ~40)

**ANTES:**
```javascript
if(!userData){
  const errorTemplate = HtmlService.createHtmlOutput('<h3>Usuario no encontrado. Verifica tu correo electrónico.</h3>');
  return errorTemplate.setWidth(400).setHeight(200);
}
```

**DESPUÉS:**
```javascript
if(!userData){
  const errorTemplate = HtmlService.createHtmlOutput('<h3>Usuario no encontrado. Verifica tu correo electrónico.</h3>');
  errorTemplate.setWidth(400).setHeight(200);
  errorTemplate.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); // ⬅️ AGREGAR ESTA LÍNEA
  return errorTemplate;
}
```

### 3. Caso de Error General (Línea ~55)

**ANTES:**
```javascript
}catch (e) {
  Logger.log(`Error en doGet: ${e.message}`);
  return HtmlService.createHtmlOutput(
    `<h3>Error: ${e.message}</h3>`
  ).setWidth(400).setHeight(200);
}
```

**DESPUÉS:**
```javascript
}catch (e) {
  Logger.log(`Error en doGet: ${e.message}`);
  const errorOutput = HtmlService.createHtmlOutput(
    `<h3>Error: ${e.message}</h3>`
  ).setWidth(400).setHeight(200);
  errorOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); // ⬅️ AGREGAR ESTA LÍNEA
  return errorOutput;
}
```

## Código Completo Modificado de doGet()

```javascript
function doGet(e) {
  try{
    validateSpreadsheet();
    console.log("VALIDATE", e.parameter)

    // Si vienen parámetros en la solicitud, procesamos la aprobación/rechazo
    if (e && e?.parameter && e?.parameter?.id && e?.parameter?.beneficio && e?.parameter?.aprobado) {
      return handleApprovalOrRejection(e.parameter);
    }

   // Flujo normal para cargar el formulario del usuario
  const email = Session.getActiveUser().getEmail(); // Obtiene el correo del usuario autenticado
  const userData = getUserData(email); // Busca los datos del usuario en la hoja
  Logger.log(userData); // Registra los datos obtenidos para revisarlos en el registro de Apps Script

  
  if(!userData){
    const errorTemplate = HtmlService.createHtmlOutput('<h3>Usuario no encontrado. Verifica tu correo electrónico.</h3>');
    errorTemplate.setWidth(400).setHeight(200);
    errorTemplate.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); // ⬅️ AGREGAR ESTA LÍNEA
    return errorTemplate;
  }

   // Carga la plantilla HTML y pasa los datos dinámicos
  const template = HtmlService.createTemplateFromFile('datosUser');
  template.userData = userData; // Pasa los datos del usuario al HTML
  const htmlOutput = template.evaluate().setTitle('Formulario Beneficio').setWidth(800).setHeight(600);
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); // ⬅️ AGREGAR ESTA LÍNEA
  return htmlOutput;
  
  }catch (e) {
    Logger.log(`Error en doGet: ${e.message}`);
    const errorOutput = HtmlService.createHtmlOutput(
      `<h3>Error: ${e.message}</h3>`
    ).setWidth(400).setHeight(200);
    errorOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL); // ⬅️ AGREGAR ESTA LÍNEA
    return errorOutput;
  }
}
```

## Pasos a Seguir

1. Abre tu Google Apps Script
2. Busca la función `doGet()`
3. Realiza las 3 modificaciones indicadas arriba
4. Guarda los cambios (Ctrl+S o Cmd+S)
5. Actualiza el despliegue:
   - Ve a "Desplegar" → "Gestionar despliegues"
   - Haz clic en el ícono de edición (lápiz) junto a tu despliegue
   - Selecciona "Nueva versión"
   - Haz clic en "Desplegar"
6. Prueba cargando la página de beneficios en Django

## Nota Importante

La función `handleApprovalOrRejection()` también retorna HTML, pero como esa función se llama desde enlaces de correo (no desde el iframe), no es necesario modificarla. Sin embargo, si quieres que también funcione en iframe, puedes agregar la misma línea en todos los `return HtmlService.createHtmlOutput(...)` dentro de esa función.


