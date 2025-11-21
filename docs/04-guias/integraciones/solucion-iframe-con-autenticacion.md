# Solución: Google Apps Script con Autenticación en iframe

## 🔍 Situación Actual

Tu Google Apps Script:
- ✅ Es una Web App
- ✅ Requiere autenticación (carga información según el usuario logueado)
- ❌ No funciona en iframe (error 403 y X-Frame-Options)

## ⚠️ Desafío con Autenticación en iframes

Cuando un script requiere autenticación y se carga en un iframe, Google puede bloquearlo por seguridad. Hay varias soluciones:

---

## ✅ Solución 1: Configurar para "Anyone with Google account" + Permitir iframe

### Paso 1: Configurar el Deployment

1. Ve a https://script.google.com
2. Abre tu script
3. **Deploy** → **Manage deployments** → Edita el deployment existente o crea uno nuevo

### Paso 2: Configuración de Acceso

- **Execute as**: "User accessing the web app" (importante para que use la sesión del usuario)
- **Who has access**: **"Anyone with Google account"** (no "Only myself", pero tampoco "Anyone")
- Haz clic en **Deploy**

### Paso 3: Modificar el Código para Permitir iframe

En tu función `doGet()`, agrega:

```javascript
function doGet(e) {
  // Tu código existente para obtener información del usuario
  var userEmail = Session.getActiveUser().getEmail();
  // ... resto de tu código ...
  
  // Generar el HTML
  var htmlContent = generarHTML(userEmail, datosUsuario);
  
  // ⚠️ IMPORTANTE: Permitir embedding en iframes
  var htmlOutput = HtmlService.createHtmlOutput(htmlContent);
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  
  return htmlOutput;
}
```

### Paso 4: Usar URL `/exec`

Asegúrate de usar el URL que termina en `/exec`, no `/dev`.

---

## ✅ Solución 2: Pasar Información del Usuario desde Django (RECOMENDADO)

Si el script puede recibir parámetros, puedes pasarle información del usuario autenticado en Django:

### En Django (beneficios.html):

```html
<iframe 
    src="https://script.google.com/.../exec?email={{ request.user.email }}&nombre={{ request.user.get_full_name }}"
    width="100%" 
    height="800px"
    frameborder="0">
</iframe>
```

### En Google Apps Script:

```javascript
function doGet(e) {
  // Obtener parámetros del URL
  var email = e.parameter.email;
  var nombre = e.parameter.nombre;
  
  // Si no hay parámetros, usar sesión activa
  if (!email) {
    email = Session.getActiveUser().getEmail();
  }
  
  // Tu código para cargar información del usuario...
  var datosUsuario = obtenerDatosUsuario(email);
  
  // Generar HTML
  var htmlContent = generarHTML(email, datosUsuario, nombre);
  
  var htmlOutput = HtmlService.createHtmlOutput(htmlContent);
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  
  return htmlOutput;
}
```

**Ventajas:**
- No requiere autenticación OAuth en el iframe
- Más rápido (no hay flujo de login)
- Más control sobre qué información se pasa

**Desventajas:**
- Necesitas modificar el script para aceptar parámetros
- La información se pasa en el URL (considera seguridad)

---

## ✅ Solución 3: Autenticación Híbrida (Mejor Experiencia)

Combinar ambas: pasar información básica desde Django, pero permitir autenticación si es necesario:

### En Django:

```html
<iframe 
    src="https://script.google.com/.../exec?email={{ request.user.email }}&nombre={{ request.user.get_full_name }}&documento={{ request.user.empleado.numero_documento }}"
    width="100%" 
    height="800px"
    frameborder="0">
</iframe>
```

### En Google Apps Script:

```javascript
function doGet(e) {
  // Intentar obtener de parámetros primero
  var email = e.parameter.email;
  var nombre = e.parameter.nombre;
  var documento = e.parameter.documento;
  
  // Si no hay parámetros, intentar sesión activa
  if (!email) {
    try {
      email = Session.getActiveUser().getEmail();
    } catch (e) {
      // Si falla, mostrar mensaje de autenticación
      return HtmlService.createHtmlOutput(
        '<html><body><h2>Por favor, inicia sesión con tu cuenta de Google</h2>' +
        '<p>Este formulario requiere autenticación.</p></body></html>'
      );
    }
  }
  
  // Cargar datos del usuario
  var datosUsuario = obtenerDatosUsuario(email, documento);
  
  // Generar HTML
  var htmlContent = generarHTML(email, nombre, documento, datosUsuario);
  
  var htmlOutput = HtmlService.createHtmlOutput(htmlContent);
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  
  return htmlOutput;
}
```

---

## 🔒 Consideraciones de Seguridad

### Opción A: Validar en el Script

Si pasas información desde Django, valida en el script:

```javascript
function doGet(e) {
  var email = e.parameter.email;
  
  // Validar que el email coincida con la sesión activa (si existe)
  try {
    var activeEmail = Session.getActiveUser().getEmail();
    if (email !== activeEmail) {
      // Email no coincide, rechazar o usar el de la sesión
      email = activeEmail;
    }
  } catch (e) {
    // No hay sesión activa, usar el parámetro
  }
  
  // Continuar con el código...
}
```

### Opción B: Usar Tokens (Más Seguro)

1. Django genera un token temporal
2. Lo pasa al script
3. El script valida el token con Django (o con una base de datos compartida)

---

## 🎯 Recomendación Final

**Para tu caso específico, recomiendo la Solución 2 o 3:**

1. **Pasar información del usuario desde Django** al script como parámetros
2. **Configurar el script** para:
   - Aceptar parámetros del URL
   - Permitir iframe (`setXFrameOptionsMode(ALLOWALL)`)
   - Usar parámetros si están disponibles, o sesión activa como fallback

**Ventajas:**
- ✅ No requiere flujo OAuth en el iframe (que puede ser problemático)
- ✅ Más rápido (no hay login adicional)
- ✅ Funciona mejor en iframes
- ✅ Puedes pasar información adicional (documento, área, etc.)

---

## 📝 Pasos de Implementación

### 1. Modificar Google Apps Script

```javascript
function doGet(e) {
  // Obtener parámetros
  var email = e.parameter.email;
  var nombre = e.parameter.nombre;
  var documento = e.parameter.documento;
  var area = e.parameter.area;
  var jefe = e.parameter.jefe;
  
  // Si no hay parámetros, intentar sesión
  if (!email) {
    try {
      email = Session.getActiveUser().getEmail();
      // Cargar otros datos desde Google Sheets o donde los tengas
    } catch (e) {
      return HtmlService.createHtmlOutput(
        '<html><body><h2>Error: No se pudo obtener información del usuario</h2></body></html>'
      );
    }
  }
  
  // Tu código existente para generar el formulario
  var htmlContent = generarFormulario(email, nombre, documento, area, jefe);
  
  // Permitir iframe
  var htmlOutput = HtmlService.createHtmlOutput(htmlContent);
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  
  return htmlOutput;
}
```

### 2. Modificar Django Template

```html
{% extends 'base.html' %}
{% block title %}Beneficios{% endblock %}
{% block page_title %}Beneficios Utilizados{% endblock %}
{% block content %}
<div class="card">
    <div class="card-body p-0">
        <iframe 
            src="https://script.google.com/a/macros/parqueexplora.org/s/AKfycbzEclLu4hB0BkDQ8d2wDgU3W4oFUFE_JbzTVl6k97o/exec?email={{ request.user.email }}&nombre={{ request.user.get_full_name|urlencode }}&documento={{ request.user.empleado.numero_documento }}&area={{ request.user.empleado.area|urlencode }}&jefe={{ request.user.empleado.jefe_directo|urlencode }}"
            width="100%" 
            height="800px"
            frameborder="0"
            style="border: none; min-height: 600px;"
            title="Formulario de Beneficios Explora">
        </iframe>
    </div>
</div>
{% endblock %}
```

**Nota**: Usa `|urlencode` para codificar correctamente los parámetros en el URL.

---

## ⚠️ Limitaciones Conocidas

1. **Cookies de sesión**: Si el script usa cookies de Google, pueden no funcionar en iframe
2. **OAuth popups**: Si el script requiere OAuth, puede abrir popups fuera del iframe
3. **Tamaño del URL**: Si pasas mucha información, el URL puede ser muy largo

---

## ✅ Checklist

Antes de implementar en Django:

- [ ] El script acepta parámetros del URL
- [ ] El script tiene `setXFrameOptionsMode(ALLOWALL)`
- [ ] El deployment está configurado como "Web app"
- [ ] "Who has access" está en "Anyone with Google account" o "Anyone"
- [ ] Estás usando el URL que termina en `/exec`
- [ ] Has probado que funciona con parámetros en el URL

---

## 🧪 Prueba Rápida

Puedes probar pasando parámetros directamente en el navegador:

```
https://script.google.com/.../exec?email=tu.email@parqueexplora.org&nombre=Tu%20Nombre&documento=123456789
```

Si funciona, entonces puedes implementarlo en Django.

