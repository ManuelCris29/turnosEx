# Solución: Envío de Correos

## Problema Identificado

Los correos no se estaban enviando cuando se creaba una solicitud. El diagnóstico reveló que:

1. ✅ El código de notificaciones funciona correctamente
2. ✅ Los empleados tienen emails configurados
3. ✅ Los templates de email existen
4. ❌ **Las credenciales de Gmail son inválidas o han expirado**

## Error Específico

```
SMTPAuthenticationError: (535, b'5.7.8 Username and Password not accepted. 
For more information, go to https://support.google.com/mail/?p=BadCredentials')
```

## Solución

### Paso 1: Actualizar Contraseña de Aplicación de Gmail

1. Ir a [Google Account Security](https://myaccount.google.com/security)
2. Activar "Verificación en 2 pasos" si no está activada
3. Ir a "Contraseñas de aplicaciones"
4. Generar una nueva contraseña de aplicación para "Correo"
5. Copiar la contraseña generada (16 caracteres sin espacios)

### Paso 2: Actualizar settings.py

Editar `AppTurnosExplora/config/settings.py` y actualizar:

```python
EMAIL_HOST_PASSWORD = 'NUEVA_CONTRASEÑA_AQUI'  # Reemplazar con la nueva contraseña
```

### Paso 3: Verificar Configuración

Ejecutar el script de diagnóstico:

```bash
python scripts/test_envio_correos.py
```

Si todo está correcto, deberías ver:
- ✅ Email simple enviado exitosamente
- ✅ Emails de notificaciones enviados exitosamente

## Mejoras Implementadas

### 1. Logging Robusto
- Reemplazado `print()` con `logger` apropiado
- Logs detallados en todos los métodos de envío
- Identificación clara de errores con emojis (✅ éxito, ❌ error, ⚠️ advertencia)

### 2. Validaciones de Email
- Validación de emails antes de enviar (no None, no vacíos)
- Validación de `recipient_list` (no vacío, lista válida)
- Validación de `from_email` con fallback a `DEFAULT_FROM_EMAIL`
- Filtrado de emails inválidos en `recipient_list`

### 3. Manejo de Errores Mejorado
- Todos los métodos de envío retornan `True/False` explícitamente
- Errores se loguean con `logger.exception()` para stack traces completos
- Errores de renderizado de templates se capturan y loguean
- Errores no silencian el proceso completo

### 4. Corrección de `_cargar_solicitud_completa`
- Manejo de excepciones con fallback a solicitud original
- Agregado `select_related` para `user` de empleados
- Manejo correcto cuando `doblada` es None

## Archivos Modificados

1. `AppTurnosExplora/solicitudes/services/notificacion_service.py`
   - Agregado logging robusto
   - Validaciones de email antes de enviar
   - Mejor manejo de errores
   - Corrección de `_cargar_solicitud_completa`

2. `AppTurnosExplora/solicitudes/services/strategies/doblada_strategy.py`
   - Mejor logging de errores en notificaciones

3. `AppTurnosExplora/scripts/test_envio_correos.py` (NUEVO)
   - Script de diagnóstico para verificar configuración y envío de correos

## Verificación Post-Corrección

Después de actualizar las credenciales:

1. **Probar envío simple:**
   ```bash
   python scripts/test_envio_correos.py
   ```

2. **Crear una solicitud de prueba** y verificar:
   - Que los logs muestren "✅ Email enviado exitosamente"
   - Que los correos lleguen a los destinatarios

3. **Revisar logs del servidor Django** al crear solicitudes para ver:
   - Intentos de envío
   - Éxitos/fallos
   - Detalles de errores si los hay

## Notas Importantes

- Las contraseñas de aplicación de Gmail pueden expirar
- Si el error persiste después de actualizar, verificar:
  - Que la verificación en 2 pasos esté activada
  - Que la contraseña de aplicación sea correcta (16 caracteres, sin espacios)
  - Que el email `EMAIL_HOST_USER` sea el mismo que el de la cuenta de Google
  - Que no haya restricciones de seguridad en la cuenta de Google

## Alternativa: Backend de Consola (Solo Desarrollo)

Para desarrollo local, se puede usar el backend de consola que muestra los emails en la terminal:

```python
# En settings.py
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
```

Esto es útil para:
- Desarrollo local sin necesidad de credenciales SMTP
- Verificar que los templates de email se rendericen correctamente
- Debugging del contenido de los emails


