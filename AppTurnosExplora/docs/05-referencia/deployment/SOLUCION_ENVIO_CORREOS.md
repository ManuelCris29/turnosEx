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

### Paso 2: Actualizar el `.env` (NO `settings.py`)

Editar `AppTurnosExplora/.env`:

```ini
EMAIL_HOST_PASSWORD=NUEVA_CONTRASEÑA_AQUI
```

> Este paso decía antes "editar `config/settings.py`". **No lo hagas**: `settings.py`
> lee la clave del `.env` (`EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')`) y está
> bajo control de versiones, así que escribir ahí la contraseña la publicaría en el
> repositorio. El `.env` está en `.gitignore` justamente para esto.
>
> En producción la credencial no vive en ningún fichero del repositorio: ver
> `CONFIGURACION_PRODUCCION.md`.

### Paso 3: Verificar Configuración

> ✅ **Corregido (2026-09-08):** el script sí existe, pero en `scripts/maintenance/`, no en la
> raíz de `scripts/`. El aviso anterior decía que se había perdido. Es justo la herramienta que
> se usa el día que se cambia el transporte de correo —con el sistema caído—, así que la ruta
> importa.

Ejecutar el script de diagnóstico:

```bash
python scripts/maintenance/test_envio_correos.py
```

O, si solo quieres comprobar el SMTP y el estado de la cola:

```bash
python manage.py shell -c "from django.core.mail import send_mail; send_mail('Prueba SWALP','cuerpo',None,['tu-correo@parqueexplora.org'])"
python manage.py procesar_email_outbox --resumen
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

```ini
# En el .env (settings.py ya lo lee de ahí; no edites settings.py)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

Esto es útil para:
- Desarrollo local sin necesidad de credenciales SMTP
- Verificar que los templates de email se rendericen correctamente
- Debugging del contenido de los emails


