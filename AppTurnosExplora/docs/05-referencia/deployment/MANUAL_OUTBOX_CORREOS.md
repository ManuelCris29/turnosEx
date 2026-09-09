# 📬 Outbox de correos — puesta en producción

> **Estado del proyecto:** el outbox ya está implementado y probado en desarrollo.
> Este documento es la checklist de **lo que falta hacer el día que se monte en
> producción**. Nada de aquí aplica al entorno local.

---

## 1. Qué es y por qué existe

Todos los correos de la app (solicitudes, permisos, reportes de integridad) pasan por
un único método: `EmailService._enviar_email_desde_usuario`. Ese método **no envía el
correo directamente**: lo escribe en la tabla `EmailOutbox` y solo después intenta
entregarlo.

**El problema que resuelve.** Antes, el envío se agendaba con `transaction.on_commit`
+ un hilo. Si el proceso moría entre el COMMIT y el callback, o si el SMTP estaba
caído, el correo se perdía **en silencio**: sin rastro, sin reintento y sin forma de
saber que existió. Para un supervisor, eso es una solicitud que "nunca le llegó".

**Cómo lo resuelve.** La fila se escribe *dentro de la misma transacción* que el cambio
de negocio: o commitan las dos cosas o ninguna. Nunca hay una aprobación sin su correo
encolado.

| | Código |
|---|---|
| Modelo | `solicitudes/models.py` → `EmailOutbox` |
| Servicio | `solicitudes/services/email_outbox_service.py` |
| Worker | `solicitudes/management/commands/procesar_email_outbox.py` |
| Tests | `solicitudes/tests/test_email_outbox.py` |

---

## 2. Cómo se entrega un correo (los dos caminos)

Entender esto es lo que explica por qué el cron es obligatorio.

```
Aprobar solicitud
      │
      ├─ 1. ENCOLAR ── fila en EmailOutbox, dentro de la transacción
      │                 (esto es lo que garantiza que el correo existe)
      │
      └─ 2. ENTREGAR ── tras el commit, un hilo intenta enviar el LOTE UNA VEZ
                          (todos los correos de la operación por una sola
                           conexión SMTP; ver `envio_agrupado`)
                          │
                          ├─ éxito → estado='enviado'   ✅ fin
                          │
                          └─ fallo → estado='pendiente', disponible_en = +1 min
                                      │
                                      └─ ⚠️ NADIE lo reintenta solo
                                            └─ solo lo recoge el CRON
```

**El paso 2 es un único intento.** Si falla, la fila queda marcada como lista para
reintentarse, pero *ningún proceso despierta a mirar la cola*. `disponible_en` es una
cita a la que nadie asiste.

**Sin el cron** ganas visibilidad (ves en el admin qué correos no salieron y por qué)
pero **no recuperación automática**: habría que entrar al admin y reintentar a mano.

**Con el cron**, un SMTP caído 20 minutos se resuelve solo.

Reintentos: **5 máximo**, con backoff de **1, 5, 15, 60 y 180 minutos**. Agotados los
5, la fila queda en estado `fallido` y ya nadie la recoge — esas son las únicas que
exigen intervención humana.

---

## 3. Checklist de despliegue

### Paso 1 — Migración

La tabla se crea con la migración `0032_emailoutbox`. Ya va incluida en el paso normal
de migraciones del despliegue (FASE 8 en ambos checklists), no requiere nada especial:

```bash
python manage.py migrate
```

- [ ] Verificar que la tabla existe: `python manage.py procesar_email_outbox --resumen`
      (debe responder `Estado de la cola: pendiente=0, enviando=0, enviado=0, fallido=0`).

### Paso 2 — Confirmar el modo asíncrono

En producción el envío debe ir fuera del request, para no bloquear la respuesta ~20 s
con el handshake SMTP.

```python
# config/settings.py:271 — ya está así, solo verificar
EMAIL_SEND_ASYNC = env.bool('EMAIL_SEND_ASYNC', default=IS_PRODUCTION)
```

- [ ] Confirmar que `IS_PRODUCTION` es `True` en el servidor (o fijar `EMAIL_SEND_ASYNC=True`
      explícitamente en el `.env`).

> En **tests** vale `False` a propósito: el envío es síncrono para que `mail.outbox`
> quede poblado dentro del propio test, y los que dependen de ello lo fijan con
> `override_settings`.
>
> En **desarrollo** conviene ponerlo a `True` en el `.env` (así está en
> `.env.example`). Con `False`, cada solicitud espera los handshakes SMTP dentro del
> request: medidos contra Gmail el 2026-09-07 fueron 6,3 s por solicitud, y los
> flujos que crean varias (cobertura con 2 compañeros, doblada permanente con N) los
> pagaban además con la transacción abierta. El explorador veía el modal "Enviando
> solicitud…" todo ese rato.

### Paso 3 — Programar el worker ⚠️ **este es el paso que no se puede omitir**

#### Si el despliegue es **EC2** (checklist AWS RDS)

```bash
# Crear el log
sudo mkdir -p /var/log/appturnos
sudo touch /var/log/appturnos/email_outbox.log
sudo chown -R ubuntu:ubuntu /var/log/appturnos

# Editar crontab
crontab -e
```

Agregar esta línea:

```cron
*/5 * * * * cd /home/ubuntu/appTurnos/AppTurnosExplora && /home/ubuntu/venvturnos/bin/python manage.py procesar_email_outbox >> /var/log/appturnos/email_outbox.log 2>&1
```

- [ ] Cron agregado y guardado.
- [ ] Verificar que quedó: `crontab -l | grep outbox`

**Por qué cada 5 minutos:** el backoff del primer reintento es de 1 minuto; barrer más
seguido no aporta nada, y más espaciado alarga la recuperación sin motivo.

**Es seguro que se solape consigo mismo.** Cada fila se reclama con un `UPDATE`
condicional, así que dos ejecuciones simultáneas nunca envían el mismo correo dos veces.

#### Si el despliegue es **Fargate** (checklist ECS)

En Fargate no hay crontab. Se necesita una **EventBridge Scheduled Rule** que lance una
tarea ECS con la misma Task Definition, sobrescribiendo el comando:

- [ ] Crear regla EventBridge con schedule `rate(5 minutes)`.
- [ ] Target: ECS Task (misma Task Definition que la app).
- [ ] Container override → command: `["python","manage.py","procesar_email_outbox"]`.
- [ ] Confirmar que la tarea usa la misma subnet/SG con salida a RDS y al SMTP.

### Paso 4 — Verificación post-despliegue

- [ ] Crear una solicitud real y confirmar que el correo llega.
- [ ] `python manage.py procesar_email_outbox --resumen` → debe mostrar `enviado=N`,
      `pendiente=0`, `fallido=0`.
- [ ] Abrir `/admin/solicitudes/emailoutbox/` y ver las filas con estado *Enviado*.
- [ ] Revisar el log del cron a los ~10 minutos: `tail /var/log/appturnos/email_outbox.log`
      (lo normal es `Cola vacía: no hay correos por reintentar.`).

---

## 4. Operación diaria

### Ver el estado de la cola (no envía nada)

```bash
python manage.py procesar_email_outbox --resumen
```

### Forzar una pasada manual

```bash
python manage.py procesar_email_outbox
python manage.py procesar_email_outbox --limite 100   # pasada más grande
```

### Desde el admin

`/admin/solicitudes/emailoutbox/` — filtrar por **estado**.

La cola es de **solo lectura** a propósito: editar a mano una fila solo puede provocar
un reenvío indebido o dejarla en un estado que el worker no sepa interpretar. Para
reintentar hay una acción dedicada: seleccionar filas → **"Reintentar el envío ahora"**
(los ya enviados se ignoran, para no duplicarlos).

### Qué mirar cuando algo falla

| Estado | Significado | Acción |
|---|---|---|
| `pendiente` | Esperando su turno o su backoff | Ninguna, se resuelve solo |
| `enviando` | Un worker lo tiene ahora mismo | Ninguna |
| `enviado` | Entregado al SMTP | Ninguna |
| **`fallido`** | **Agotó los 5 reintentos** | **Revisar `ultimo_error` y decidir** |

Solo `fallido` exige intervención humana. Causa típica: destinatario inválido o
credenciales SMTP mal configuradas — revisar `ultimo_error` en el admin.

---

## 5. Garantía real (importante, no sobreentender)

Esto es entrega **al menos una vez**, no exactamente-una-vez.

Si el proceso muere justo después de que el SMTP aceptó el mensaje pero antes de marcar
la fila como enviada, el reintento **reenviará ese correo**. Es el compromiso clásico e
inevitable sin transacciones distribuidas con el servidor de correo, y para este dominio
es el lado correcto: un supervisor prefiere un aviso repetido a no enterarse de una
solicitud.

Contra los duplicados *previsibles* sí hay protección: las **claves de idempotencia**
impiden encolar dos veces el mismo correo lógico.

| Clave | Correo |
|---|---|
| `aprob_sup_{id}` / `aprob_rec_{id}` | Aprobación por supervisor / receptor |
| `rech_sup_{id}` / `rech_rec_{id}` | Rechazo por supervisor / receptor |
| `creacion_permiso_{id}` / `resolucion_permiso_{id}` | Permisos |
| `reporte_integridad_{fecha}_{email}` | Reporte diario de integridad de dobladas |

Los correos sin clave (creación de solicitud, cancelación) encolan una fila por llamada:
ahí cada envío es un hecho distinto y duplicarlo no tendría sentido lógico que evitar.

---

## 6. Relación con otros documentos

- [CHECKLIST_DESPLIEGUE_AWS_RDS.md](./CHECKLIST_DESPLIEGUE_AWS_RDS.md) — FASE 10 (correo/SES).
- [CHECKLIST_DESPLIEGUE_AWS_RDS.md](./CHECKLIST_DESPLIEGUE_AWS_RDS.md) — FASE 8 (DNS) y FASE 10 (SES).
- [SOLUCION_ENVIO_CORREOS.md](./SOLUCION_ENVIO_CORREOS.md) — diagnóstico de credenciales
  SMTP. Sigue vigente: el outbox garantiza la *entrega*, pero si las credenciales están
  mal, los correos acumularán intentos y terminarán en `fallido`.
- `PLAN_CORREO_TRANSACCIONAL_Y_LATENCIA.docx` — plan de SES por API (Fase 2).
