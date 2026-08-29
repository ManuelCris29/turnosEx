# Manual — Recuperar contraseña (autoservicio) en producción

**Qué resuelve:** que una persona que olvidó su contraseña la recupere sola, sin que un
administrador tenga que reponérsela a mano.

**A quién le sirve:** a quien despliega (secciones 3 a 6). Las secciones 1 y 2 explican
el flujo y por qué el fallo típico es silencioso.

> ⚠️ **Este manual es obligatorio antes de anunciar la función.** Si no se hace, la
> pantalla de recuperación **parece funcionar** —dice "revisa tu correo"— pero no llega
> nada. Ver sección 2.

---

## 1. Qué hay en la aplicación

Dos pantallas nuevas, ambas con las vistas estándar de Django:

| Pantalla | Ruta | Quién entra |
|---|---|---|
| Cambiar mi contraseña | `/password/cambiar/` | Con sesión iniciada, desde el menú de usuario |
| ¿Olvidaste tu contraseña? | `/password/recuperar/` | **Público**, enlace en el login |

El código está en `core/login/views.py` y `core/login/urls.py`. Los límites de peticiones
en `core/rate_limit.py`, y el aviso de "tu contraseña ha cambiado" en
`core/services/aviso_seguridad_service.py`.

**Solo la segunda depende de AWS.** "Cambiar mi contraseña" funciona sin tocar nada
(salvo el aviso por correo, que se encola y sale cuando el SMTP esté disponible).

---

## 2. El fallo silencioso (lee esto antes de nada)

La pantalla de recuperación responde **exactamente lo mismo** haya cuenta o no la haya,
y también cuando se supera el límite de peticiones. Es deliberado: si dijera "ese correo
no existe", cualquiera podría averiguar quién tiene cuenta probando direcciones.

El efecto secundario es que **un correo mal configurado no se nota**: el usuario ve
"revisa tu correo" y no llega nada. Por eso la verificación de la sección 6 no es
opcional — es la única forma de saber que funciona.

**Las tres causas de que no llegue nada:**

1. SES está en **sandbox** (sección 3.2). La más habitual con diferencia.
2. La cuenta **no tiene email registrado**. Desde ahora el email es obligatorio al crear
   un usuario nuevo (`empleados/forms.py`), pero una cuenta creada antes puede no tenerlo.
   Se comprueba en `/admin/auth/user/` filtrando por email vacío.

**Y una causa que NO es un fallo:** una persona **dada de baja** no recibe el enlace.
`PasswordResetForm` filtra por `is_active=True`, y dar de baja desactiva la cuenta. Es el
comportamiento correcto: quien no puede entrar tampoco debe poder recuperar su acceso.
Si se trata de un reingreso, primero hay que reingresarlo desde la lista de empleados.
3. El grupo de seguridad **bloquea la salida al puerto 587** (sección 4).

---

## 3. SES, paso a paso

### 3.1 Verificar la identidad del remitente

1. Consola de AWS → **Amazon SES** → región del despliegue → **Identities** →
   *Create identity*.
2. Elegir **Domain** y escribir `parqueexplora.org` (verificar el dominio, no solo una
   dirección: es lo que permite enviar desde cualquier `@parqueexplora.org` y lo que
   mejora la entregabilidad).
3. Dejar marcado **Easy DKIM** con clave RSA_2048.
4. SES muestra **3 registros CNAME**. Pasárselos a IT para que los cree en el DNS del
   dominio.
5. Añadir también el **SPF**: un registro TXT en el dominio con
   `v=spf1 include:amazonses.com ~all` (si ya existe un SPF, se le añade el `include`,
   **no se crea un segundo**: dos registros SPF invalidan los dos).
6. Esperar a que la identidad pase a **Verified**. Suele tardar minutos; puede llegar a
   72 horas si el DNS propaga lento.

> Si hay prisa y el dominio aún no está listo, se puede verificar solo la dirección
> `no-reply@parqueexplora.org` (*Create identity* → **Email address**). Sirve para
> probar, pero los correos tienen más papeletas de acabar en spam sin DKIM del dominio.

### 3.2 Salir del sandbox — **paso bloqueante**

Una cuenta nueva de SES está en *sandbox*: **solo entrega a direcciones verificadas a
mano**. Con la recuperación de contraseña eso significa que **no funciona para nadie**.

1. SES → **Account dashboard** → *Request production access*.
2. Tipo de correo: **Transactional**.
3. URL del sitio web: la URL de la aplicación.
4. Caso de uso: describir en dos líneas que es una aplicación interna de gestión de
   turnos y que los correos son avisos de solicitudes y recuperación de contraseña,
   dirigidos únicamente a empleados de la organización. Mencionar que no hay listas de
   distribución ni correo comercial.
5. Volumen diario esperado: una estimación honesta (decenas, no miles).
6. **Plazo típico: 24 horas hábiles.** Pedirlo con antelación, no el día del despliegue.

Confirmar después en *Account dashboard* que dice **Production access: Enabled**.

### 3.3 Credenciales SMTP

⚠️ **No son las claves IAM normales.** Una *access key* de IAM no sirve como contraseña
SMTP; hay que generar credenciales específicas.

1. SES → **SMTP settings** → *Create SMTP credentials*.
2. Anotar el **SMTP endpoint** que muestra esa misma página:
   `email-smtp.<region>.amazonaws.com`.
3. AWS crea un usuario IAM y entrega **usuario y contraseña SMTP**. Se muestran **una
   sola vez**: descargarlos.
4. Guardarlos en **Secrets Manager** (no en la task definition en claro):
   ```bash
   aws secretsmanager create-secret --name swalp/ses-smtp \
     --secret-string '{"EMAIL_HOST_USER":"AKIA...","EMAIL_HOST_PASSWORD":"..."}'
   ```
5. Referenciarlos en la task definition con `secrets` (no con `environment`), y dar al
   **execution role** permiso `secretsmanager:GetSecretValue` sobre ese secreto.

---

## 4. Variables de entorno y red

En la task definition:

```bash
EMAIL_HOST=email-smtp.us-east-1.amazonaws.com   # el endpoint de la seccion 3.3
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=<desde Secrets Manager>
EMAIL_HOST_PASSWORD=<desde Secrets Manager>
DEFAULT_FROM_EMAIL=no-reply@parqueexplora.org  # debe ser del dominio verificado

# Vida del enlace de recuperacion, en segundos. Por defecto 1800 (30 min).
# El valor por defecto de DJANGO son 3 dias: no lo subas sin una razon.
PASSWORD_RESET_TIMEOUT=1800
```

**Red — se olvida a menudo:** el grupo de seguridad de las tareas ECS debe permitir
**salida (egress) al puerto 587**. Si no, el envío se queda colgado hasta agotar
`EMAIL_TIMEOUT` (10 s) y el usuario ve un error genérico sin pista de la causa.

> Si el VPC no tiene salida a internet, hace falta un **VPC endpoint de SES** o un NAT
> Gateway. Con subredes privadas sin NAT, esto no funciona.

---

## 5. El enlace del correo: dominio y HTTPS

El enlace se construye con el **host de la petición**, no con `SITE_URL`. Si esto está
mal, el correo llega pero el enlace no sirve:

- **`ALLOWED_HOSTS`** debe incluir el dominio público (`swalp.parqueexplora.org`). Ver la
  trampa 3 de [CONFIGURACION_PRODUCCION.md](./CONFIGURACION_PRODUCCION.md).
- **`SECURE_PROXY_SSL_HEADER`** ya se activa con `SECURE_HTTPS=True`. Sin él, Django cree
  que la petición llegó por HTTP y **manda enlaces `http://`** que el ALB rebota.

**Señal de que esto está mal:** el enlace del correo apunta al DNS interno del ALB
(`swalp-alb-123456.us-east-1.elb.amazonaws.com`) en vez de al dominio, o empieza por
`http://`.

---

## 6. Verificación de extremo a extremo

Después de desplegar, con una cuenta real (no la de un admin):

- [ ] `https://swalp.parqueexplora.org/` muestra el enlace **"¿Olvidaste tu contraseña?"**.
- [ ] Pedir el enlace con el correo de esa cuenta → la pantalla dice "Revisa tu correo".
- [ ] **El correo llega** en menos de un minuto, desde `no-reply@parqueexplora.org`.
- [ ] En la cabecera del correo: **DKIM=pass** y **SPF=pass** (en Gmail, "Mostrar
      original"). Si fallan, acabará en spam para todo el mundo.
- [ ] El enlace empieza por **`https://swalp.parqueexplora.org/password/recuperar/`**
      (sección 5).
- [ ] El enlace abre el formulario, la contraseña nueva se guarda, y **se puede entrar
      con ella**.
- [ ] **Abrir el mismo enlace por segunda vez** → "El enlace ha caducado, ya se usó...".
      Si vuelve a dejar cambiar la contraseña, hay un problema serio.
- [ ] Llega el correo **"Tu contraseña ha cambiado"** (este va por el outbox, así que
      puede tardar hasta 5 minutos si el cron es quien lo entrega).
- [ ] Con sesión iniciada, el menú de usuario muestra **"Cambiar mi contraseña"** y el
      flujo completo funciona.
- [ ] En CloudWatch (`/ecs/swalp`) aparecen las líneas `PASSWORD_RESET_SOLICITADO` y
      `PASSWORD_RESET_CONSUMIDO`.

---

## 7. Diagnóstico

| Síntoma | Causa más probable | Comprobación |
|---|---|---|
| No llega ningún correo | SES en **sandbox** | *Account dashboard* → Production access |
| No llega, y SES está en producción | La cuenta **no tiene email** | `/admin/auth/user/` → ver el campo email |
| No llega, y la cuenta sí tiene email | **Puerto 587 cerrado** | Logs: error de timeout SMTP al enviar |
| Llega a **spam** | DKIM/SPF sin verificar | Cabeceras del correo: `dkim=pass`, `spf=pass` |
| Enlace "caducado" al primer intento | El enlace **ya se usó**, o `PASSWORD_RESET_TIMEOUT` demasiado bajo | Pedir uno nuevo; revisar la variable |
| Enlace apunta a `http://` o al DNS del ALB | `SECURE_PROXY_SSL_HEADER` / `ALLOWED_HOSTS` | Sección 5 |
| Deja de enviarse de golpe para todos | **Reputación de SES** dañada | SES → *Reputation metrics*; revisar bounces y quejas |
| Llega a alguien que ya no trabaja aquí | Fue **eliminado** con la versión antigua, que dejaba viva la cuenta | Buscar cuentas sin ficha: `User.objects.filter(empleado__isnull=True)`. Ya no deberían aparecer: hoy se da de baja, no se elimina |

**Un fallo que NO es un fallo:** decirle a alguien "pedí el enlace y no me llegó nada"
cuando ha pedido más de 3 en la última hora. Es el límite de peticiones haciendo su
trabajo (`core/rate_limit.py`); se levanta solo pasada la hora. En CloudWatch aparece
como `LIMITE_PETICIONES_SUPERADO`.

---

## 8. Coste

**Prácticamente nulo.** No se añade ningún servicio: SES ya estaba previsto para los
avisos de solicitudes. SES cobra del orden de **$0,10 por cada 1.000 correos**, y el
volumen de esta función son unas pocas recuperaciones al mes. No hace falta ECS extra,
Lambda, cola ni base de datos.

---

## 9. Documentos relacionados

- [CHECKLIST_DESPLIEGUE_FARGATE.md](./CHECKLIST_DESPLIEGUE_FARGATE.md) — FASE 9 (SES) y FASE 10 (verificación).
- [CONFIGURACION_PRODUCCION.md](./CONFIGURACION_PRODUCCION.md) — tabla de variables y las cuatro trampas.
- [MANUAL_OUTBOX_CORREOS.md](./MANUAL_OUTBOX_CORREOS.md) — por dónde sale el aviso de "contraseña cambiada".
  **Ojo:** el enlace de recuperación NO pasa por el outbox, y es deliberado (ver el
  docstring de `PasswordResetSWALPView`).
