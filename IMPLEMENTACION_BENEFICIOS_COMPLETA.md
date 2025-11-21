# Implementación Completa: Beneficios con Google Apps Script

## ✅ Lo que se implementó en Django

### 1. Vista actualizada (`permisos/views.py`)

La vista `BeneficiosView` ahora:
- Obtiene información del empleado autenticado
- Pasa los siguientes parámetros al Google Apps Script:
  - `email`: Email del empleado
  - `nombre`: Nombre completo
  - `documento`: Cédula del empleado
  - `tipo_usuario`: Tipo de usuario (actualmente "Operativo")
  - `jefe`: Nombre del jefe directo (si existe)

### 2. Template actualizado (`templates/permisos/beneficios.html`)

El template ahora:
- Muestra un iframe con el Google Apps Script
- Pasa los parámetros del usuario en el URL
- Incluye estilos CSS para que se vea bien
- Maneja errores si no hay información del empleado

### 3. URL del Script

Se está usando el URL que termina en `/exec`:
```
https://script.google.com/a/macros/parqueexplora.org/s/AKfycbzEclLu4hB0BkDQ8d2wDgU3W4oFUFE_JbzTVl6k97o/exec
```

---

## ⚠️ Lo que DEBES hacer en Google Apps Script

Para que funcione correctamente, necesitas modificar tu Google Apps Script:

### Paso 1: Modificar la función `doGet()`

Tu función debe aceptar parámetros del URL y permitir embedding:

```javascript
function doGet(e) {
  // Obtener parámetros del URL (pasados desde Django)
  var email = e.parameter.email;
  var nombre = e.parameter.nombre;
  var documento = e.parameter.documento;
  var tipoUsuario = e.parameter.tipo_usuario;
  var jefe = e.parameter.jefe;
  
  // Si no hay parámetros, intentar obtener de la sesión activa (fallback)
  if (!email) {
    try {
      email = Session.getActiveUser().getEmail();
      // Aquí puedes cargar otros datos desde Google Sheets o donde los tengas
    } catch (e) {
      // Si falla, mostrar mensaje de error
      return HtmlService.createHtmlOutput(
        '<html><body><h2>Error: No se pudo obtener información del usuario</h2></body></html>'
      );
    }
  }
  
  // Tu código existente para generar el formulario
  // Usa las variables: email, nombre, documento, tipoUsuario, jefe
  var htmlContent = generarFormulario(email, nombre, documento, tipoUsuario, jefe);
  
  // ⚠️ IMPORTANTE: Permitir embedding en iframes
  var htmlOutput = HtmlService.createHtmlOutput(htmlContent);
  htmlOutput.setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
  
  return htmlOutput;
}
```

### Paso 2: Actualizar tu función de generación de HTML

Modifica tu función que genera el HTML del formulario para usar los parámetros:

```javascript
function generarFormulario(email, nombre, documento, tipoUsuario, jefe) {
  // Tu código existente, pero ahora usa los parámetros en lugar de Session.getActiveUser()
  
  var html = `
    <!DOCTYPE html>
    <html>
    <head>
      <!-- Tus estilos CSS -->
    </head>
    <body>
      <form>
        <input type="text" name="documento" value="${documento}" readonly>
        <input type="text" name="nombre" value="${nombre}" readonly>
        <input type="email" name="email" value="${email}" readonly>
        <input type="text" name="tipo_usuario" value="${tipoUsuario}" readonly>
        <input type="text" name="jefe" value="${jefe || ''}" readonly>
        <!-- Resto de tu formulario -->
      </form>
    </body>
    </html>
  `;
  
  return html;
}
```

### Paso 3: Configurar el Deployment

1. Ve a https://script.google.com
2. Abre tu script
3. **Deploy** → **Manage deployments**
4. Edita el deployment existente o crea uno nuevo:
   - **Type**: Web app
   - **Execute as**: "User accessing the web app" (para que use la sesión del usuario si es necesario)
   - **Who has access**: **"Anyone with Google account"** o **"Anyone"**
5. Haz clic en **Deploy**
6. Copia el URL que termina en `/exec`

### Paso 4: Verificar que funciona

1. Prueba el URL directamente en el navegador con parámetros:
   ```
   https://script.google.com/.../exec?email=test@parqueexplora.org&nombre=Test%20User&documento=123456789&tipo_usuario=Operativo
   ```

2. Si funciona, prueba desde Django:
   - Ve a `http://127.0.0.1:8000/permisos/beneficios/`
   - Debe cargar el formulario con los datos pre-llenados

---

## 🔍 Parámetros que se pasan desde Django

| Parámetro | Valor | Descripción |
|-----------|-------|-------------|
| `email` | `request.user.email` o `empleado.email` | Email del usuario |
| `nombre` | `empleado.nombre + " " + empleado.apellido` | Nombre completo |
| `documento` | `empleado.cedula` | Cédula del empleado |
| `tipo_usuario` | `"Operativo"` | Tipo de usuario (puedes ajustar la lógica) |
| `jefe` | `empleado.supervisor.nombre + " " + empleado.supervisor.apellido` | Jefe directo (si existe) |

---

## 🎯 Ventajas de esta solución

1. ✅ **No requiere autenticación OAuth en el iframe** (más rápido)
2. ✅ **Funciona mejor en iframes** (no hay problemas de cookies)
3. ✅ **Información pre-llenada** desde Django
4. ✅ **Más control** sobre qué información se pasa
5. ✅ **Mejor experiencia de usuario** (no hay popups de login)

---

## ⚠️ Consideraciones de Seguridad

### Validación en el Script (Recomendado)

Si quieres validar que el email coincida con la sesión activa:

```javascript
function doGet(e) {
  var email = e.parameter.email;
  
  // Validar que el email coincida con la sesión activa (si existe)
  try {
    var activeEmail = Session.getActiveUser().getEmail();
    if (email && email !== activeEmail) {
      // Email no coincide, usar el de la sesión activa
      email = activeEmail;
      // Recargar otros datos desde tu fuente de datos
    }
  } catch (e) {
    // No hay sesión activa, usar el parámetro
  }
  
  // Continuar con el código...
}
```

---

## 🧪 Prueba Rápida

### 1. Probar desde Django

1. Inicia el servidor Django: `python manage.py runserver`
2. Inicia sesión en la aplicación
3. Ve a: `http://127.0.0.1:8000/permisos/beneficios/`
4. Verifica que:
   - El iframe carga correctamente
   - Los campos están pre-llenados
   - Puedes interactuar con el formulario
   - Puedes enviar el formulario

### 2. Verificar en la consola

Abre las herramientas de desarrollador (F12) y verifica:
- ✅ No hay errores de X-Frame-Options
- ✅ No hay errores 403
- ✅ El iframe carga correctamente

---

## 📝 Checklist Final

Antes de considerar que está completo:

- [ ] El Google Apps Script acepta parámetros del URL
- [ ] El script tiene `setXFrameOptionsMode(ALLOWALL)`
- [ ] El deployment está configurado como "Web app"
- [ ] "Who has access" está en "Anyone with Google account" o "Anyone"
- [ ] Estás usando el URL que termina en `/exec`
- [ ] Has probado que funciona desde Django
- [ ] Los campos se pre-llenan correctamente
- [ ] Puedes enviar el formulario

---

## 🆘 Si aún no funciona

### Error 403 Forbidden
- Verifica que "Who has access" esté en "Anyone" o "Anyone with Google account"
- Verifica que estés usando el URL `/exec` (no `/dev`)

### Error X-Frame-Options
- Verifica que el código tenga `setXFrameOptionsMode(ALLOWALL)`
- Verifica que estés usando `HtmlService.createHtmlOutput()` (no `ContentService`)

### Campos no se pre-llenan
- Verifica que el script esté recibiendo los parámetros: `e.parameter.email`, etc.
- Verifica que estés usando los parámetros en lugar de `Session.getActiveUser()`

### El formulario no se envía
- Verifica que la función `doPost()` esté configurada correctamente
- Verifica que no haya errores de JavaScript en la consola

---

## ✅ Estado Actual

- ✅ **Django**: Implementado y listo
- ⚠️ **Google Apps Script**: Necesita modificaciones (ver arriba)

Una vez que modifiques el Google Apps Script siguiendo los pasos anteriores, todo debería funcionar correctamente.


