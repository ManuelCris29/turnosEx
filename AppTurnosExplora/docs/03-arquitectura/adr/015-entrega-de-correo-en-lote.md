# ADR 015 — El correo se entrega en lote sobre una conexión, y el lote se declara a mano

- **Estado:** Implementado
- **Fecha:** 2026-09
- **Ámbito:** `solicitudes` (`EmailOutboxService`, `EmailService`, `NotificacionService`,
  `SolicitudOrchestrator`), configuración de correo (`EMAIL_SEND_ASYNC`)
- **Relación:** **no enmienda** al [ADR 003](./003-on-commit-para-notificaciones.md); lo
  reinterpreta. `transaction.on_commit` sigue en su sitio, pero después del patrón outbox ya
  no es lo que garantiza que el correo no se pierda: hoy solo decide **cuándo** se intenta la
  entrega. Ver "Qué queda del ADR 003", más abajo.

## Contexto

Crear una solicitud tardaba entre **6,3 y 7,8 segundos** en responder. Medido en
`logs/appturnos.log` el 2026-09-07, con el detalle de una solicitud real:

```
23:49:45,738  Encolando email  → supervisor
23:49:47,910  enviada                        (2,17 s)
23:49:47,922  Encolando email  → receptor
23:49:49,951  enviada                        (2,03 s)
23:49:49,964  Encolando email  → solicitante
23:49:52,044  enviada                        (2,08 s)
```

Todo ese tiempo era SMTP, y no por el tamaño de los mensajes: **el coste de un correo es el
saludo**. Cada envío abría su propia conexión —handshake TLS + `AUTH` contra Gmail, ~2 s— para
mandar unos kilobytes y colgar. Tres correos por solicitud, tres saludos.

Los flujos que crean varias solicitudes de golpe multiplican la cuenta: cobertura con dos
compañeros son 6 correos, doblada permanente con tres son 9. Con `EMAIL_SEND_ASYNC=False`
—como estaba el entorno de desarrollo— esos 19 segundos los esperaba el explorador con el
modal "Enviando solicitud…" en pantalla, y además **con la transacción abierta**, porque el
envío ocurría dentro del `atomic()` del bucle.

El patrón outbox ya resolvía la parte difícil (que el correo no se pierda). Lo que quedaba era
puramente de transporte.

## Decisión

### 1. Una conexión por lote, con `open()` explícito

`enviar_lote(ids)` (`solicitudes/services/email_outbox_service.py:234`) es **el único camino
de envío**. `intentar_enviar` sigue existiendo con su contrato de siempre, pero como envoltorio
de `_intentar` (`:151`); un correo suelto es simplemente un lote de uno, de modo que el ahorro
lo aprovecha todo el mundo sin que cada llamador tenga que acordarse.

La pieza que hace que funcione es una línea fácil de borrar por descuido: el `open()`
**explícito** de `_abrir_conexion` (`:207`), antes del bucle. `send_messages` de Django cierra
la conexión **solo si fue él quien la abrió**; compartir el objeto de conexión sin abrirlo
antes no ahorra nada, porque cada mensaje volvería a abrir y cerrar. Quien quite ese `open()`
no romperá ninguna prueba de entrega —los correos seguirán saliendo— pero devolverá el
handshake por mensaje sin que nada avise.

### 2. El lote se declara a mano, no se deduce de la transacción

`envio_agrupado()` (`:329`) es un *context manager* reentrante: los correos encolados dentro
del bloque se apuntan y se despachan juntos al salir.

**Se descartó derivar la agrupación de `transaction.on_commit`**, que era la opción obvia
—acumular las filas y despachar en un único callback—. No funciona: fuera de un `atomic()`,
Django ejecuta el callback de `on_commit` **en el acto**, y en este proyecto hay estrategias que
crean sin transacción a propósito (`doblada_strategy`, por el comportamiento de MySQL ante
reintentos tras error SQL). En esas rutas cada correo formaría su propio grupo de uno y la
agrupación sería silenciosamente inútil justo en el formulario más usado. El bloque explícito
marca el límite del lote **haya transacción o no**.

La reentrancia no es un adorno: el orquestador abre un grupo alrededor del bucle y cada
`crear_notificacion_solicitud` abre el suyo. Si el interior despachara, volveríamos a una
conexión por solicitud.

### 3. El grupo se abre POR FUERA del `atomic()` — invariante

En `_procesar_cobertura_dos` (`solicitudes/services/solicitud_orchestrator.py:278`) y
`_procesar_multiples_companeros` (`:530`), el `with envio_agrupado()` envuelve al
`with atomic()`, nunca al revés. Tiene dos consecuencias y **la segunda no es rendimiento**:

- Nada se entrega con la transacción abierta.
- Nada se entrega hasta que el bloque termina, **ya commitado**.

Eso cierra un agujero que el propio código documentaba como limitación asumida: *"el rollback
deshace las filas, pero un email ya enviado por la primera no se puede desenviar"*. Si la
segunda creación falla, el rollback se lleva también las filas del outbox y el lote se queda
vacío por sí solo — la atomicidad la sigue dando la base de datos, no una lista en memoria.
Es el hallazgo **B5** del manual técnico (§ 16.4), hoy cerrado.

Invertir ese anidamiento reabre B5 y devuelve el SMTP al interior de la transacción. No hay
ninguna prueba que lo impida por su forma; lo que hay es esta decisión escrita.

### 4. El fallo de conexión ocurre antes de reclamar ninguna fila

`_abrir_conexion` devuelve `None` si el SMTP no responde, y `enviar_lote` sale sin tocar la
cola. Antes, con una conexión por correo, cada fila se reclamaba —incrementando `intentos`— y
**después** descubría que el servidor no estaba: cinco caídas seguidas y un correo perfectamente
válido quedaba en `fallido` para siempre, agotado por indisponibilidad ajena. Ahora una caída
del SMTP cuesta **cero intentos** y las filas se quedan pendientes, intactas, para el barrido.

Mover ese `open()` después del `_reclamar`, o contar el fallo como intento, restaura el
comportamiento viejo.

### 5. Si una fila falla a media tanda, se renueva el canal

Un fallo puede ser del mensaje (un destinatario malo) o del canal (SMTP que corta por
inactividad o por límite de mensajes). No se distinguen desde fuera, así que se asume lo
segundo: se cierra y se reabre antes de seguir. Con un canal muerto, no hacerlo condenaría al
resto del lote. Si la reapertura no prospera, el lote **se corta ahí**: las filas restantes se
quedan sin reclamar y las recoge el cron, en vez de quemarles un intento a todas contra un
servidor que ya sabemos que no está.

Por eso `_intentar` devuelve tres estados y no un booleano: `omitido` —la fila la tiene otro
worker, o ya salió— **no dice nada del canal** y no debe provocar una reconexión.

### 6. Sigue sin haber cola de tareas

Se vuelve a descartar Celery/SQS, y por la misma razón que en el ADR 003 más una nueva: el
único trabajo diferido de este sistema son los correos, la garantía de entrega ya la da la
tabla `EmailOutbox` con su cron de reintentos, y **el problema medido no era de concurrencia
sino de handshakes**. Un broker habría añadido un servicio que operar, monitorizar y pagar para
resolver algo que costaba abrir la conexión una vez.

## Consecuencias

- Doblada permanente con tres compañeros pasa de **9 saludos TLS+AUTH a 1**.
- Con `EMAIL_SEND_ASYNC=True` la respuesta ya no espera al correo en absoluto. El flag pasa a
  recomendarse también en desarrollo (`.env.example`); su valor por omisión —
  `default=IS_PRODUCTION`— **no cambió**, para que los tests sigan siendo síncronos y
  `mail.outbox` se pueble dentro de cada prueba.
- B5 cerrado (§ 16.4 del manual técnico).
- Efecto colateral que hubo que arreglar aparte: mientras el envío tardaba 13-19 s, el candado
  anti doble-submit del orquestador **caducaba a mitad del propio request que protegía** (TTL de
  10 s). Se subió a 30 s en `_DEDUPE_TTL_SEGUNDOS` (`solicitud_orchestrator.py:34`). De ahí sale
  una regla general que conviene no perder: **un TTL de deduplicación debe durar más que el
  request más lento que protege**.
- El barrido del cron (`procesar_pendientes`) también va en una sola conexión.

## Qué queda del ADR 003

El ADR 003 movió las notificaciones a `transaction.on_commit` para que una aprobación no
revirtiera por un fallo de correo. Esa decisión sigue siendo correcta y su mecanismo sigue en
pie, pero su **justificación** ya no es la que era: cuando llegó el patrón outbox, la garantía
de "no se pierde" pasó a la tabla y sus reintentos.

Hoy `on_commit` cumple un papel más modesto y perfectamente definido: es el **temporizador** que
decide en qué momento se lanza el hilo de entrega (`enviar_tras_commit`, `:303`). Quien lea el
ADR 003 buscando la garantía de entrega debe venir aquí y al `MANUAL_OUTBOX_CORREOS.md`.

Las tres piezas que hoy responden a "cuándo se entrega" están separadas a propósito:

| Pieza | Responde a |
|---|---|
| `despachar(fila_id)` (`:370`) | punto único de salida tras encolar |
| `envio_agrupado()` (`:329`) | con qué otras filas viaja |
| `enviar_tras_commit(ids)` (`:303`) | en qué instante, y en qué hilo |

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Celery / SQS | Ver punto 6: el problema era el handshake, no la concurrencia |
| Agrupar con `on_commit` | Fuera de `atomic()` el callback corre en el acto: grupos de uno, en silencio, justo en las rutas sin transacción |
| Compartir el objeto de conexión sin `open()` explícito | Django la abre y cierra en cada `send_messages`: no ahorra nada |
| Una conexión SMTP persistente a nivel de proceso | Un canal de larga vida hay que vigilarlo (cortes por inactividad, límites de mensajes por conexión, un lock por worker de Gunicorn). El lote acota la vida de la conexión a la operación que la necesita |
| Reintentar el lote entero cuando falla una fila | Reenviaría correos ya entregados: la garantía es *al menos una vez*, y duplicar avisos de aprobación tiene coste real para el supervisor |

## Cobertura

15 pruebas en `solicitudes/tests/test_email_outbox.py`, clases
`OutboxUnaConexionPorLoteTest` y `OutboxEnvioAgrupadoTest`: que un lote de tres abre una sola
conexión, que el barrido también, que una caída del SMTP no gasta intentos, que un fallo a
media tanda renueva el canal y continúa, que una fila omitida **no** provoca reconexión, que el
grupo es reentrante, que despacha aunque el bloque termine con excepción y que no queda abierto
después.
