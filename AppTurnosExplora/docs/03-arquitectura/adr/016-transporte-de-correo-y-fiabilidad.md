# ADR 016 — El transporte del correo es de un tercero; la fiabilidad no

- **Estado:** Decidido, pendiente de ejecución. El transporte sigue siendo Gmail hasta el
  despliegue; lo que cierra este ADR es **qué** se hace y **qué no**.
- **Fecha:** 2026-09
- **Ámbito:** transporte de correo (`EMAIL_*` en `config/settings.py:257-273`),
  `EmailOutboxService`, `EmailService`, la petición de DNS a IT y las alarmas de
  `infra/cloudformation/swalp-infra.yaml`.
- **Relación:** se apoya en el [ADR 015](./015-entrega-de-correo-en-lote.md) y en el
  [ADR 003](./003-on-commit-para-notificaciones.md); **no enmienda a ninguno**. Decide el
  *destino* del transporte, no el mecanismo del lote.

## Contexto

La pregunta que originó este ADR fue: *"¿mantenemos el envío de correo como está —código
propio— o usamos un servicio de terceros?"*.

Está mal planteada, y por eso tiene respuesta fácil. El correo de esta aplicación no es una
pieza, son **cuatro capas** que se deciden por separado — y en una de ellas ya se usa un
tercero sin haberlo llamado así:

| Capa | Qué resuelve | Quién la hace hoy | ¿Puede hacerla un tercero? |
|---|---|---|---|
| **Composición** | 9 plantillas, texto plano, tokens firmados, From fijo + Reply-To | `EmailService` (propio) | No: es dominio |
| **Fiabilidad** | Encolar dentro de la transacción, idempotencia, reintentos, multi-worker | `EmailOutboxService` (propio, 382 líneas) | **No. Ninguno** |
| **Transporte** | Quién acepta el SMTP y lo entrega al buzón | **Gmail** (tercero, ya) | **Sí, y hay que cambiarlo** |
| **Retroalimentación** | Rebotes, quejas, reputación de remitente | **Nadie** | **Sí, y es el hueco real** |

Datos con los que se decide: ~300 empleados, ~30 solicitudes/día, ~6 correos por solicitud →
**~6.000 correos/mes ≈ 180/día**. Remitente acordado `no-reply@parqueexplora.org`, sitio en
`swalp.parqueexplora.org`, y **Parque Explora ya usa Google Workspace sobre ese dominio** —
dato que la documentación de despliegue no tenía en cuenta.

## Decisión

### 1. La fiabilidad se queda en casa. Ningún proveedor la vende

`EmailOutboxService` no se sustituye, y no por apego: **SES, SendGrid, Resend y Celery empiezan
a trabajar cuando ya has decidido enviar**. El outbox existe para el instante anterior — escribe
la fila **dentro de la misma transacción** que la aprobación (`email_outbox_service.py:76`). Si
el proceso muere entre el COMMIT y la llamada al proveedor, ningún proveedor sabe que había un
correo; solo una fila ya commitada lo recuerda.

Eso es atomicidad con la base de datos, y no se compra. Lo que sí compran los proveedores es el
reintento de **la entrega al buzón del destinatario** — un tramo que ya funciona. El que falla
es el anterior.

Corolario que conviene no perder: **Celery/SQS no sería una alternativa, sería una capa más**.
Encolar una tarea dentro de una transacción tiene exactamente el problema que el outbox
resuelve — si hay rollback, la tarea ya está en la cola y se ejecuta igual. La solución canónica
a eso es `on_commit`, es decir, el ADR 003, sobre el que el outbox es la mejora. Se acabaría con
outbox **y** Celery.

### 2. El transporte sale de Gmail y va a Amazon SES por SMTP

Tres motivos, y la cuota es el menos importante de los tres:

**a. DKIM no puede alinear.** Enviar con `From: no-reply@parqueexplora.org` autenticando contra
`smtp.gmail.com` con una cuenta que no es de ese dominio produce una firma DKIM de `gmail.com`
que **no alinea** con el From: DMARC falla y el correo va a spam para las 300 personas. Es el
fallo más caro posible porque es silencioso — nadie reporta un correo que no llegó, simplemente
dejan de aprobar solicitudes.

**b. Ya se cayó por esto.** `SOLUCION_ENVIO_CORREOS.md` documenta un `SMTPAuthenticationError
(535)` real: caducó la contraseña de aplicación de Gmail y los correos dejaron de salir sin que
nadie se enterara hasta investigarlo a mano. **Las credenciales SMTP de SES no caducan solas**:
se derivan de una clave IAM y solo cambian si alguien las rota. Ese modo de fallo desaparece sin
escribir código.

**c. Cero retroalimentación.** Gmail no dice qué rebotó.

**El coste no es criterio de decisión.** SES son **0,60 USD/mes** (0,10 USD por millar), un
**1,9 %** de los 32,08 USD/mes de toda la factura AWS. Los planes gratuitos de SendGrid y Resend
(100/día) no cubren los 180/día; sus planes de pago cuestan ~20 USD, **33× SES**, y suben la
factura total un 62 %. La auditoría de costos del proyecto ya lo cerró: el volumen tendría que
multiplicarse por dieciséis para que el correo llegara a 10 USD.

**Cambiar el transporte cuesta cero líneas de código:** tres variables de entorno. El
acoplamiento real al proveedor es de **un solo fichero** (`email_outbox_service.py`), y la
prueba está en la suite — ver *Cobertura*.

### 3. Se pide a IT lo mínimo: tres CNAME, y ningún SPF

La documentación de despliegue pide a IT *"registros DKIM/SPF de SES"*
(`arquitectura-aws-rds-recomendada.md:243`, `:619`, `:697`, `:710`), y en `:243` llega a decir
*"ajustando SPF para no romper Workspace"*. **Eso pide de más y es el mayor riesgo de bloqueo
del proyecto.**

SES envía con un Return-Path propio (`@<región>.amazonses.com`) cuyo SPF publica Amazon y pasa.
DMARC exige que **uno** de los dos mecanismos alinee y pase, y **Easy DKIM firma con el dominio
del From**: alinea, y DMARC pasa. El SPF del ápice es del que depende **todo el correo
corporativo de Workspace** — tocarlo tiene riesgo real, arrastra el límite de 10 consultas DNS,
y es exactamente el cambio que un equipo de IT tarda semanas en aprobar.

Lo que hay que pedir son **3 CNAME de Easy DKIM**. Un CNAME nuevo no puede romper el correo
existente: convierte *"modifica el DNS del correo corporativo"* en *"añade tres alias"*.

Y se piden **dos identidades en el mismo ticket**: el ápice `parqueexplora.org` y el subdominio
`swalp.parqueexplora.org`. El subdominio deja todos los registros dentro de algo que IT puede
delegar entero y donde un error no toca el correo corporativo; además resuelve la incoherencia
entre `SITE_URL=https://swalp.parqueexplora.org` y
`DEFAULT_FROM_EMAIL=no-reply@parqueexplora.org`. Como `DEFAULT_FROM_EMAIL` **ya es variable de
entorno** (`config/settings.py:263`), elegir uno u otro **no cuesta una línea de código**: se usa
el que IT conceda primero. Una dependencia bloqueante se convierte así en dos caminos paralelos.

**No se pide MAIL FROM personalizado** en la primera vuelta: solo sirve para alinear también el
SPF, y con DKIM alineado DMARC ya pasa.

### 4. La retroalimentación es una capa nueva, y es el precio de entrada a SES

SES trae un modo de fallo que Gmail no tenía. `core/rate_limit.py:10-14` ya lo razona —*"SES
puede suspender el envío para TODA la aplicación"*— pero **hoy nadie procesa esos eventos**.

Los umbrales de AWS son **rebotes > 5 %** y **quejas > 0,1 %**. Con 300 empleados y rotación
normal hay buzones que mueren y siguen en nómina: **6 direcciones muertas sobre 180 correos
diarios ya son un 3,3 %**. Por debajo del umbral, pero en la trayectoria. Con Gmail eso rebotaba
y punto; con SES, la deriva silenciosa de la lista de correos puede **apagar el sistema de
aprobaciones entero**.

La alarma de rebotes no es madurez opcional: sin ella, SES es más frágil que Gmail. Y es barata
— SES publica `Reputation.BounceRate` y `Reputation.ComplaintRate` en CloudWatch sin configurar
nada, y `infra/cloudformation/swalp-infra.yaml:323` **ya tiene el `AlertTopic`** del que cuelgan
otras dos alarmas. Son dos bloques YAML. **Cero código Python y cero endpoint público.**

Umbrales propuestos **por debajo** de los de AWS —0,02 y 0,0005— para que la alarma suene
mientras todavía hay margen de maniobra.

### 5. La composición no se toca

Las 9 plantillas, el remitente fijo con Reply-To y los tokens firmados se quedan como están y
donde están: en el repositorio, versionados y probados.

## Consecuencias

- El cambio de transporte es **configuración, no despliegue de código**: tres variables en el
  `.env` de producción.
- Aparece una **dependencia externa nueva y bloqueante**: los CNAME de DKIM los publica IT de
  Parque Explora, y la **salida del sandbox de SES** tarda ~24 h y es **por región**. En sandbox
  solo se entrega a destinatarios verificados: los 180 correos diarios caben en la cuota de 200,
  pero son inservibles porque los ~300 empleados no estarán verificados. Es un fallo silencioso
  idéntico al de dejar `EMAIL_BACKEND` en `console`.
- El coste mensual sube **0,60 USD**.
- **El relay de Google Workspace queda degradado a alternativa, no a plan B gratis.** La
  documentación lo presenta como la salida si IT tarda
  (`arquitectura-aws-rds-recomendada.md:379-384`), pero autentica **por IP de origen**, que exige
  la Elastic IP, que exige la cuenta AWS: no está disponible antes que SES. Su variante con
  usuario y contraseña reintroduce el modo de fallo del `535`. En los dos casos hace falta que IT
  actúe en la consola de Workspace, y en los dos la reputación queda **compartida con el correo
  de toda la organización**: un bucle de notificaciones por un bug afectaría al correo de Parque
  Explora, no solo al de SWALP.

### Trabajo pendiente que este ADR deja registrado

1. **Corregir la petición a IT** en `arquitectura-aws-rds-recomendada.md` (§11.7, §11.8) y en el
   checklist: tres CNAME de Easy DKIM, sin tocar el SPF del ápice, con las dos identidades. Es la
   acción de mayor palanca y no depende de nadie.
2. ✅ **HECHO (2026-09-08).** *Nadie se entera de un correo definitivamente perdido.* Cerrado con
   un check propio, `_revisar_correos_fallidos`, y el marcador **`CORREOS_FALLIDOS`** —distinto
   de `CRON_NO_EJECUTADO`, que sigue significando solo "nadie ejecuta la tarea"—. La alarma mira
   los que agotaron los reintentos en las últimas **24 h** (`VENTANA_FALLIDOS_HORAS`), no el
   histórico: una alarma que no se puede apagar arreglando la causa se acaba ignorando, y un
   buzón muerto de verdad volvería a fallar en cada reintento manual dejando el check en rojo
   para siempre. El recuento total sigue saliendo en el detalle, sin dar la alarma. Umbral
   ajustable con `--umbral-fallidos`. 7 pruebas nuevas en `test_verificar_crons.py` (21 en total),
   incluida la que fija que reintentar desde el admin apaga la alarma.
   *Texto original del pendiente:* `verificar_crons.py:114-124` cuenta
   los correos en estado `fallido`, pero `ok` depende **solo** de la espera del pendiente más
   antiguo: mil correos agotados dan check verde y salida 0. La exclusión es deliberada y está
   razonada en su docstring —*"esas piden una persona, no un cron"*—; el problema no es esa
   semántica, es que **esa persona no tiene ningún aviso**, y detectarlo depende de que alguien
   abra el admin. Arreglo: umbral propio y **marcador distinto** (`CORREOS_FALLIDOS`). Reutilizar
   `CRON_NO_EJECUTADO` (`verificar_crons.py:45`, `:80`) ensuciaría el significado de la alarma
   que ya existe: "nadie ejecuta la tarea" y "hay correos que exigen una persona" piden
   respuestas distintas.
3. **Las alertas están escritas para Fargate y el despliegue es EC2.**
   `config/settings.py:536-540` justifica no escribir fichero de log porque *"en ECS/Fargate el
   log driver `awslogs` recoge stdout"*, pero el commit `dd4228c` eligió EC2 y descartó Fargate.
   Con gunicorn bajo systemd, stdout va a **journald**: sin el agente de CloudWatch instalado **no
   existe el grupo de logs `/swalp/app`** que el propio comentario manda consultar, y los *metric
   filters* sobre `CRON_NO_EJECUTADO` no tienen sobre qué montarse. No es un problema de correo,
   pero **es el que decide si te enteras de que un correo falló**: cualquier observabilidad
   construida encima sin resolver esto es teatro. Hay que elegir explícitamente entre instalar el
   agente (~0,50 USD/mes) o aceptar journald y reescribir esos comentarios.
4. **Las dos alarmas de reputación** en `swalp-infra.yaml`, colgando del `AlertTopic` existente.
5. ✅ **HECHO (2026-09-08).** *Borrar código muerto.* `EmailService._configurar_email_backend` y
   su import de `EmailBackend` eran el único sitio de la aplicación que instanciaba el backend
   SMTP a mano, y no los llamaba nadie. Borrados. **La propiedad que este ADR afirma ya es
   comprobable**, y esta es la comprobación:

   ```bash
   grep -rn "django\.core\.mail" --include=*.py . | grep -v "/tests/\|test_\|scripts/"
   ```

   Solo debe devolver `email_outbox_service.py:39` y la línea de `EMAIL_BACKEND` de
   `config/settings.py`. Si aparece un tercero, el cambio de proveedor ya no es solo
   configuración. La docstring del módulo lo dice ahora en primera persona, para que quien vaya
   a instanciar un backend sepa que va en `email_outbox_service.py` y no aquí.
   *Queda vivo* `EmailService._verificar_token` (`email_service.py:513`), un delegado de una
   línea a `tokens_aprobacion.verificar` que tampoco tiene llamadores —los de
   `views/aprobacion_email.py` son métodos propios de cada vista—. No ata a ningún proveedor, así
   que se deja como limpieza aparte.
6. **Ruta obsoleta:** `SOLUCION_ENVIO_CORREOS.md:57` manda ejecutar
   `scripts/test_envio_correos.py`; el script vive en `scripts/maintenance/`. Es justo la
   herramienta que se usará el día del cambio a SES, con el sistema caído.
7. **Medir el lote contra SES.** El ahorro del ADR 015 está medido contra Gmail desde desarrollo;
   SES tiene otra latencia y **otro límite de mensajes por conexión**, que es exactamente lo que
   dispara la renovación de canal a media tanda (`email_outbox_service.py:265-272`). Riesgo
   abierto nº 33 (`manual_tecnico.md:2844`). **Si el ahorro resulta despreciable, no se borra
   nada**: el código es correcto y está probado, y borrarlo sería riesgo sin retorno. Solo se
   actualiza el ADR 015 con el número real, para que nadie siga citando los 6,3-7,8 s de Gmail
   como si aplicaran.

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| **Quedarse en Gmail** | DKIM no alinea con el dominio propio → spam para 300 personas; la contraseña de aplicación ya caducó una vez y tumbó el envío en silencio; cero información de rebotes. La cuota (500 destinatarios/día) es lo de menos |
| **SendGrid / Resend** | El plan gratuito (100/día) no cubre 180/día: descartados **por volumen, no por precio**. De pago cuestan 33× SES y suben la factura total un 62 % para aportar un panel de rebotes que dos alarmas de CloudWatch dan gratis. Y meten un tercero **fuera del perímetro de AWS** que procesa datos de 300 empleados: otro encargado de tratamiento bajo la Ley 1581, con su contrato y su credencial |
| **Celery / SQS / Redis como broker** | No sustituye al outbox —encolar dentro de una transacción tiene el mismo problema que el outbox resuelve—, así que serían las dos cosas. Además, un worker más en una EC2 `t4g.micro` de 1 GB donde ya viven gunicorn, nginx y cron, y una segunda unidad systemd que puede morir en silencio: justo el fallo que `verificar_crons` existe para cazar |
| **SES por API (`django-ses` / `anymail`), ahora** | **No por lo que parece:** son *backends de Django*, siguen usando `EmailMultiAlternatives` y `get_connection()`, así que la suite **no se rompería**. Se aplaza por dos razones reales: no se meten dos variables a la vez en una primera salida a producción —con SMTP, si el correo falla, el problema es DNS, sandbox o credenciales, no una librería nueva—; y su ventaja principal, autenticar por rol IAM sin contraseña, pierde urgencia porque **las credenciales SMTP de SES tampoco caducan**. Lo que sí se degradaría es el ADR 015: sin handshake SMTP, el `open()` del lote deja de comprar nada. Ver *Vía de salida* |
| **Relay SMTP de Google Workspace** | Ver Consecuencias: no desbloquea antes que SES, tiene su propia dependencia de IT, y comparte la reputación con el correo corporativo |
| **Una capa de abstracción de proveedor propia** (interfaz `EmailSender`, adaptadores) | `EMAIL_BACKEND` de Django **ya es esa abstracción**, y el acoplamiento real es un fichero y tres símbolos. Una capa encima duplicaría lo que el framework da gratis |
| **Un webhook de rebotes de SNS** | Endpoint público sin autenticar que exige validar la firma de SNS y confirmar la suscripción: superficie de ataque nueva, para 300 destinatarios conocidos cuyo ciclo de vida ya gestiona `empleados/`. Dos alarmas de CloudWatch cubren el grueso del riesgo por cero código. Reevaluar solo si la métrica de rebotes lo pide |
| **Plantillas en la consola del proveedor** (SES templates, dinámicas de SendGrid) | Sacarlas del repositorio las saca del control de versiones y de las pruebas |
| **Configurar `ADMINS` / `mail_admins`** | Crearía un **segundo camino de correo fuera del outbox**, que es justo la propiedad que hace verificable todo lo anterior |
| **Mover el reset de contraseña al outbox** | Está fuera **a propósito** y `core/login/views.py:133-142` lo advierte por escrito: la persona espera delante de la pantalla, y con `EMAIL_SEND_ASYNC` más el cron el enlace podría tardar minutos. Un reset lo reintenta el propio usuario; el correo de una aprobación ocurre una sola vez. *"Si alguien 'arregla' esto metiéndolo en el outbox, romperá el flujo sin que ningún test de correo se queje."* Es la trampa más probable de este ADR, porque parece una incoherencia y es una decisión |

## Vía de salida (sin fecha)

Si algún día la gestión de las credenciales SMTP molesta, el camino está estudiado: `django-ses`
o `django-anymail` + rol IAM de la instancia, sin contraseña ninguna. Exige `boto3` en
`requirements.txt` (~15 MB, no despreciable en 1 GB de RAM) y una variable `EMAIL_BACKEND`. Queda
escrito aquí para que quien lo retome no repita el estudio.

## Cobertura

No añade pruebas: **este ADR se verifica por lo que NO hay que tocar.**

- 26 pruebas de correo —22 en `solicitudes/tests/test_email_outbox.py` (5 clases) y 4 en
  `test_email_service.py`— que se apoyan en `override_settings(EMAIL_BACKEND=...locmem...)`,
  `mail.outbox` y mocks de `EmailMultiAlternatives.send` y de
  `EmailOutboxService._abrir_conexion`. **Cambiar `EMAIL_BACKEND` a SES SMTP las deja verdes sin
  tocar una línea.**
- **La señal de alarma está definida:** si el cambio de transporte obligara a modificar
  `test_email_outbox.py`, el acoplamiento sería mayor del medido en este ADR y habría que
  revisarlo antes de seguir.
- Comprobación de acoplamiento, ejecutable: tras borrar el código muerto del punto 5,
  `grep -rn "django.core.mail" --include=*.py .` fuera de tests debe devolver **solo**
  `email_outbox_service.py` y la línea de `EMAIL_BACKEND` de `config/settings.py`.
- Comprobación de DKIM que casi todo el mundo se salta: en *Mostrar original* de Gmail debe
  leerse `DKIM: 'PASS' with domain <el dominio del From>`. **Si el dominio de la firma no es el
  del From, la alineación no existe aunque DKIM diga PASS.**
- Que el outbox aguanta un SES caído ya está cubierto por `OutboxUnaConexionPorLoteTest`: la
  conexión se abre **antes** de reclamar ninguna fila (`email_outbox_service.py:207`), así que
  una caída del proveedor cuesta **cero intentos**.
