# 📧 Correo por Google Workspace — quitar la contraseña personal de en medio

**Fecha:** 2026-09-09
**Sustituye a:** la parte de Gmail de [SOLUCION_ENVIO_CORREOS.md](./SOLUCION_ENVIO_CORREOS.md)
**Relacionado:** [CHECKLIST_DESPLIEGUE_DOKPLOY.md](../01-dokploy/CHECKLIST_DESPLIEGUE_DOKPLOY.md) FASE 8 · [ADR 016](../../../03-arquitectura/adr/016-transporte-de-correo-y-fiabilidad.md)

---

## 1. El problema, tal cual está hoy

El envío sale por `smtp.gmail.com` con una **contraseña de aplicación de un buzón
personal**. Cada vez que se cambia la contraseña de ese correo, el App Password se
invalida y el envío se cae. Ya pasó: está documentado como un `SMTPAuthenticationError
(535)`.

**Y con el outbox en producción no se cae con estruendo, se cae así:**

```
Se aprueba una solicitud
   └─ el correo se encola en EmailOutbox (dentro de la transacción: nunca se pierde)
   └─ el envío inmediato falla:  535 Authentication failed
        └─ reintento a 1 min   → falla
        └─ reintento a 5 min   → falla
        └─ reintento a 15 min  → falla
        └─ reintento a 60 min  → falla
        └─ reintento a 180 min → falla
             └─ estado = 'fallido'.  Nadie lo vuelve a tocar.
                  └─ salta CORREOS_FALLIDOS
```

O sea: un cambio de contraseña personal deja a 300 empleados sin avisos de aprobación
durante horas, y la única señal es un marcador que hay que estar vigilando. La
información no se pierde —el outbox garantiza que la fila existe—, pero **la entrega sí**.

Y hay un problema de fondo, aparte del técnico: **los correos salen a nombre de una
persona.** Cuando esa persona se vaya de la empresa, el sistema de turnos se apaga con
ella.

---

## 2. Tres cosas se llaman "cuenta de servicio" y no son la misma

Conviene fijar el vocabulario antes de pedirle nada al administrador de Workspace, porque
pedir la equivocada cuesta semanas.

| | Qué es | ¿Sirve aquí? |
|---|---|---|
| **Relay SMTP de Workspace** | Un servicio del dominio que acepta correo de servidores autorizados: `smtp-relay.gmail.com:587` | **Sí, y es la mejor.** Puede autenticar **por IP**, con lo que la credencial desaparece del problema |
| **Buzón dedicado** (`no-reply@parqueexplora.org`) | Un usuario de Workspace normal, con licencia, 2FA y su propia contraseña de aplicación | **Sí, como plan B.** Sigue habiendo contraseña, pero deja de ser la tuya |
| **Service account de Google Cloud** (OAuth2, clave JSON, delegación en el dominio) | Lo que "cuenta de servicio" significa en Google **Cloud** | **No.** Exige una dependencia nueva (`google-auth`) y un backend de correo propio: cambio de código, y **innecesario** — las dos de arriba resuelven el problema entero |

> 🔴 **No pidas la tercera.** Es la que suena más profesional y la que más trabajo cuesta,
> y no compra nada que las otras dos no den. El ADR 016 ya descartó por el mismo motivo
> pasar a SES por API: "las credenciales SMTP tampoco caducan".

---

## 3. Opción recomendada — relay SMTP autenticado por IP

Es la única que **elimina la credencial** en vez de esconderla mejor.

### 3.1 Lo que hace el administrador de Workspace

Consola de administración → **Apps → Google Workspace → Gmail → Enrutamiento** →
sección **Servicio de retransmisión SMTP** → *Configurar / Añadir*.

- [ ] **Remitentes permitidos:** *Solo direcciones de los dominios registrados*.
- [ ] **Autenticación:** marcar **"Solo aceptar correo de las direcciones IP
      especificadas"** y añadir la **IP pública del servidor de Dokploy**.
- [ ] **Requerir cifrado TLS:** sí.
- [ ] Ponerle un nombre reconocible al ajuste, p. ej. `SWALP - servidor de turnos`.

> 📌 **La IP tiene que ser la de SALIDA del servidor**, que no siempre es la misma que la
> de entrada si hay NAT. Se comprueba desde el propio servidor con
> `curl -s https://ifconfig.io`. Si sale una IP distinta a la que apunta el DNS, es esa la
> que hay que autorizar.

> ⚠️ **Si la IP cambia, el correo se para en seco.** Es el precio de esta opción: se pasa
> de "la contraseña caduca sola" a "la IP se cambia rara vez y de forma deliberada". Es un
> intercambio bueno, pero hay que saberlo y anotar la IP autorizada donde se vea.

### 3.2 Lo que se pone en la aplicación

```env
EMAIL_HOST=smtp-relay.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL="SWALP <no-reply@parqueexplora.org>"
```

Dos detalles que hay que leer despacio:

- 🔴 **`EMAIL_HOST_USER` y `EMAIL_HOST_PASSWORD` tienen que EXISTIR aunque vayan vacías.**
  `config/settings.py` las lee sin `default`, así que si faltan la aplicación **no
  arranca** (`ImproperlyConfigured`). Vacías sí funciona: el backend SMTP de Django solo
  llama a `login()` si hay usuario **y** contraseña.
- 🔴 **`EMAIL_BACKEND` se deja sin definir.** Si alguien lo pone en `console`, los correos
  se escriben en el log, no los recibe nadie, y **no hay ningún error**. Es el fallo más
  silencioso de toda esta configuración.

### 3.3 Lo que se gana frente al plan de SES

| | Amazon SES (plan de AWS) | Relay de Workspace |
|---|---|---|
| Trámite previo | Salir del sandbox, ~24 h | Ninguno |
| Cambios de DNS | **6 CNAME** de Easy DKIM | **Ninguno** |
| SPF / DKIM / DMARC | Hay que montarlos | **Ya funcionan** para `parqueexplora.org` |
| Credencial | Usuario y contraseña SMTP | **Ninguna** (por IP) |
| Límite diario | 200 en sandbox / negociable fuera | **10.000 destinatarios/día por dominio** |
| Riesgo propio | Rebotes >5 % o quejas >0,1 % pausan el envío de toda la cuenta | La IP autorizada |

Contra los ~180 correos diarios reales (30 solicitudes × ~6), el límite sobra por dos
órdenes de magnitud.

---

## 4. Plan B — buzón dedicado con contraseña de aplicación

Si el administrador no quiere abrir el relay —algunos lo evitan porque autoriza a un
servidor a enviar como el dominio entero—, esta es la alternativa.

- [ ] **Crear el usuario `no-reply@parqueexplora.org`** en Workspace.

      🔴 **Tiene que ser un USUARIO con licencia.** Un **alias** y un **grupo** no pueden
      autenticarse por SMTP: no tienen contraseña propia. Es el error que hace perder la
      primera tarde.

- [ ] **Activar la verificación en dos pasos** en esa cuenta. Sin 2FA, Google no ofrece la
      opción de generar contraseñas de aplicación.
- [ ] **Generar la contraseña de aplicación** desde esa cuenta
      (`myaccount.google.com` → Seguridad → Contraseñas de aplicaciones).
- [ ] Ponerla en la aplicación:

```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=no-reply@parqueexplora.org
EMAIL_HOST_PASSWORD=<la contraseña de aplicación, 16 caracteres sin espacios>
DEFAULT_FROM_EMAIL="SWALP <no-reply@parqueexplora.org>"
```

- [ ] **Guardar la contraseña donde no dependa de una persona** (gestor de secretos del
      área, no un correo ni un post-it) y **anotar quién la custodia**.

Qué se arregla y qué no: cambiar **tu** contraseña deja de romper el envío, y el correo
deja de salir a tu nombre. Pero sigue habiendo una credencial que alguien puede revocar.
Límite de un buzón de Workspace: **2.000 destinatarios/día**, también de sobra.

---

## 5. Lo que **no** hay que pedir

> 🟡 **No pidas tocar el registro SPF del dominio.**
> El SPF del ápice es del que depende **todo el correo corporativo de Workspace**.
> Tocarlo tiene riesgo real y arrastra el límite de 10 consultas DNS. Con el relay o con
> un buzón del propio dominio, el correo sale **por la infraestructura de Google, que el
> SPF de `parqueexplora.org` ya autoriza**. No hay nada que añadir.

> 🟡 **No pidas MAIL FROM personalizado ni DKIM nuevo.**
> Workspace ya firma con DKIM en nombre del dominio. La firma alinea con el `From`, y con
> eso DMARC pasa.

---

## 6. Prueba de aceptación

La misma para las dos opciones. **Sin el punto 4, no sabemos si el problema original está
resuelto.**

- [ ] **1. Llega.** Enviar una solicitud real y confirmar que el correo llega, y que **no
      cae en spam**.

- [ ] **2. Está alineado.** En el mensaje recibido, *Mostrar original*:
      - `SPF: PASS`
      - `DKIM: PASS` **con el dominio del `From`**
      - `DMARC: PASS`

      🔴 **Que DKIM diga `PASS` no basta.** Si el dominio de la firma no es el del `From`,
      la alineación no existe y DMARC falla igual. Es el paso que casi todo el mundo se
      salta.

- [ ] **3. La cola queda limpia.**
      ```bash
      python manage.py procesar_email_outbox --resumen
      ```
      Debe decir `fallido=0`.

- [ ] **4. PRUEBA DE REGRESIÓN DEL PROBLEMA ORIGINAL.**
      **Cambiar la contraseña del buzón personal** y comprobar que el envío **sigue
      funcionando**.

      Este es el punto entero del ejercicio. Los tres anteriores solo dicen que el correo
      sale hoy; este dice que seguirá saliendo mañana. Un cambio que no se prueba contra
      el fallo que lo motivó no está terminado.

- [ ] **5. La alarma existe.** Con el vigilante ya programado:
      ```bash
      python manage.py alertar_crons --dry-run
      ```
      Debe redactar el correo sin errores. Es lo que avisará si esto vuelve a romperse.

---

## 7. Si algo falla

| Síntoma | Causa típica |
|---|---|
| `ImproperlyConfigured` al arrancar | Faltan `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD`. Tienen que existir **aunque vayan vacías** |
| Los correos no llegan y no hay ningún error | `EMAIL_BACKEND` quedó en `console`. Quítalo |
| `535 Authentication failed` | Plan B con la contraseña mal copiada (van 16 caracteres, sin espacios), o 2FA desactivada en la cuenta |
| `550 Relay denied` / `Mail relay denied` | Relay: la IP del servidor no está autorizada, o no es la de salida. `curl -s https://ifconfig.io` desde el servidor |
| `550-5.7.1 Invalid credentials for relay [IP]` **con la IP correcta y ya autorizada** en el mensaje | **Este error engaña: habla de la IP y del HELO, pero casi nunca es eso.** Empieza por descartar el remitente, que es la causa real la mayoría de las veces — ver la fila siguiente. Solo si esa prueba sale bien, mira el saludo HELO/EHLO: Google exige que se presente un dominio registrado de la cuenta, y el backend SMTP de Django, sin indicarle nada, usa `socket.getfqdn()`, que dentro de un contenedor Docker devuelve el hostname aleatorio del contenedor. Se fija con `EMAIL_LOCAL_HOSTNAME` en el `.env` (ver el bloque "Saludo HELO/EHLO propio", debajo de `EMAIL_TIMEOUT` en `settings.py`) |
| …y **la prueba que lo resuelve en 30 segundos** | Manda un correo poniendo como remitente una cuenta que sepas que existe: `python manage.py shell -c "from django.core.mail import send_mail; print(send_mail('x','x','TU.USUARIO@parqueexplora.org',['TU.USUARIO@parqueexplora.org']))"`. **Si devuelve `1`, el relay y la IP están bien y el problema es `DEFAULT_FROM_EMAIL`**: esa dirección no existe como usuario del directorio. Pasa cuando el apartado *Remitentes permitidos* del relay está en **"Solo los usuarios de apps registrados de mis dominios"** (más estricto que el que pide el punto 4) y la cuenta se creó con una errata, es un alias o es un grupo. En el despliegue de Dokploy (2026-09-18) la cuenta se había creado como `no-**replay**@` en vez de `no-**reply**@`, y el error no decía nada de eso |
| Llega pero cae en spam | Revisar la alineación del punto 6.2 antes de tocar nada más |
| `CORREOS_FALLIDOS` en el vigilante | Correos que agotaron los 5 reintentos: `/admin/solicitudes/emailoutbox/`, filtrar por *fallido*, revisar `ultimo_error`, y usar la acción **"Reintentar el envío ahora"** cuando la causa esté corregida |

---

## 8. Lo que NO cambia

El transporte cambia; **la fiabilidad se queda en casa**. Sigue igual, y es lo que hace
que un fallo de correo no pierda información:

- `EmailOutbox` escribe la fila **dentro de la misma transacción** que el cambio de
  negocio. Nunca hay una aprobación sin su correo encolado.
- El envío en lote sobre **una sola conexión SMTP** (`envio_agrupado`, ADR 015).
- **5 reintentos** con backoff de 1, 5, 15, 60 y 180 minutos.
- Las **claves de idempotencia** que impiden encolar dos veces el mismo correo lógico.
- El cron `procesar_email_outbox` cada 5 minutos, que es quien recoge lo que el envío
  inmediato no logró entregar.

Nada de eso depende del proveedor, y por eso cambiarlo es solo cambiar variables de
entorno: **cero líneas de código**.
