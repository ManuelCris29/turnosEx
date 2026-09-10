# 02 · Correo

El sistema manda ~180 correos al día (30 solicitudes × ~6). Si esto se cae, los
supervisores dejan de enterarse de las solicitudes.

## Por dónde empezar

| Documento | Para qué |
|---|---|
| **[MANUAL_CORREO_GOOGLE_WORKSPACE.md](./MANUAL_CORREO_GOOGLE_WORKSPACE.md)** | **Empieza aquí.** Cómo configurar el transporte sin que dependa de la contraseña de un buzón personal |
| [MANUAL_OUTBOX_CORREOS.md](./MANUAL_OUTBOX_CORREOS.md) | Cómo funciona la cola: reintentos, backoff, idempotencia y el cron obligatorio |
| [SOLUCION_ENVIO_CORREOS.md](./SOLUCION_ENVIO_CORREOS.md) | Diagnóstico de credenciales SMTP. La parte de Gmail la sustituye el manual de Workspace |
| [MANUAL_RECUPERAR_CONTRASENA.md](./MANUAL_RECUPERAR_CONTRASENA.md) | El flujo de "olvidé mi contraseña", que va **fuera** del outbox a propósito |
| `PLAN_CORREO_TRANSACCIONAL_Y_LATENCIA.docx` | Plan de SES por API. Histórico: se abandonó con AWS |

## Lo que hay que saber sí o sí

- 🔴 `EMAIL_HOST_USER` y `EMAIL_HOST_PASSWORD` **tienen que existir aunque vayan vacías**.
  `settings.py` las lee sin `default`: si faltan, la aplicación **no arranca**.
- 🔴 `EMAIL_BACKEND` **se deja sin definir**. En `console`, los correos se escriben en el
  log, no los recibe nadie, y **no hay ningún error**.
- El transporte se cambia con variables de entorno: **cero líneas de código**. La
  fiabilidad (cola, 5 reintentos, idempotencia) no depende del proveedor.
