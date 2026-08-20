# ADR 009 — Cancelar una solicitud aprobada exige el acuerdo de la contraparte

- **Estado:** Implementado
- **Fecha:** 2026-08
- **Ámbito:** `solicitudes` (los seis formularios) y `permisos` (media jornada de temporada)

## Contexto

Hasta ahora, cancelar era un acto **unilateral del solicitante**: pulsaba un botón y, si estaba
dentro de una ventana de 30 minutos desde la aprobación y las dos guardias lo permitían, los
turnos volvían atrás en el acto.

El problema no era técnico. Una solicitud `aprobada` es un **acuerdo entre dos personas**: el
receptor ya dijo que sí y ya reorganizó su semana en consecuencia. Que una sola de las partes
pudiera deshacerlo sin avisar convierte el turno del otro en algo revocable por sorpresa.

La ventana de 30 minutos tampoco encajaba con pedir permiso a nadie: es un plazo pensado para
"me equivoqué al enviar", no para que otra persona lea una notificación y conteste.

## Decisión

**Cancelar deshace un acuerdo, y quién puede deshacerlo depende de si ese acuerdo llegó a
existir.**

| Situación | Quién cancela | Por qué |
|---|---|---|
| `pendiente` | El solicitante, solo | Nadie aceptó nada y nada se aplicó al calendario |
| `aprobada` | El solicitante **pide** y el **receptor** aprueba o rechaza | El receptor ya aceptó y los turnos se movieron |
| Gestión | El supervisor, directo | Es intervención administrativa, no parte del acuerdo |

Dos plazos de 24 horas: el solicitante tiene 24 h desde `fecha_resolucion` para pedirla
(`VENTANA_PEDIR_CANCELACION_HORAS`), y la contraparte 24 h desde `cancelacion_solicitada_en` para
responder (`VENTANA_RESPONDER_CANCELACION_HORAS`), ambas en `core/constants.py:160,165`.

Tres desenlaces terminales y definitivos —`aprobada`, `rechazada`, `caducada`
(`EstadoCancelacion.TERMINALES`, `core/constants.py:154`)—: **no se vuelve a pedir**. Si el
receptor se niega o deja pasar el plazo, el cambio queda **firme**, y la salida es un cambio nuevo
o que un supervisor lo cancele desde Gestión. Nadie pierde su turno por el silencio del otro.

### El invariante que sostiene todo lo demás

Mientras `cancelacion_estado == 'pendiente'`, el `estado` de la solicitud sigue siendo
`'aprobada'` **a propósito**. Los turnos continúan aplicados y todo lo que filtra por
`'aprobada'` —guardia LIFO, Mis Turnos, reconciliación— la sigue viendo vigente. La cancelación
solo se materializa cuando el receptor aprueba (`solicitudes/models.py:166-170`).

Consecuencia directa: las guardias LIFO e integridad corren **dos veces**, al pedir
(`solicitudes/use_cases/cancelar_solicitud.py:272`) y al aprobar (`:359`). La primera evita
molestar al receptor con algo que ya es irreversible; la segunda es obligatoria porque entre
ambas pueden pasar 24 horas y entrar otro cambio sobre los mismos días.

En **permisos** la contraparte es el **supervisor**, porque el permiso no tiene receptor: es
quien lo aprobó y quien responde por la cobertura del día (`permisos/models.py:114-118`). Tres
consecuencias, todas deliberadas y ya implementadas:

- El plazo de 24 h cuelga de un campo propio, `PermisoEspecial.fecha_aprobacion`
  (`permisos/models.py:94-97`, migración `permisos/0009`), no de `actualizado_en` (`auto_now`).
  El cálculo es `fecha_aprobacion or actualizado_en` (`permisos/views.py:443`): el respaldo es
  **permanente**, porque sin él los permisos aprobados antes del campo serían incancelables.
- Sobre el permiso **propio** siempre se PIDE, aunque quien pulse tenga rol de supervisor
  (`permisos/views.py:424`), y el dueño tampoco puede responderse a sí mismo (`:585`). La
  pregunta que decide es de quién es el permiso, no qué rol tiene quien actúa.
- Responde **el** supervisor del permiso, resuelto por una fuente única,
  `_supervisor_del_permiso` (`:561`), que comparten la autorización (`:588`) y la notificación
  (`:611`): decide y avisa la misma persona. Si el permiso no tiene ninguno resoluble vale
  cualquier supervisor (`:588-591`); de lo contrario la petición sería incontestable y
  caducaría siempre.

## Alternativas descartadas

| Alternativa | Por qué no |
|---|---|
| Poner `estado='cancelada'` al pedir y revertirlo si el receptor rechaza | El cambio dejaría de verse vigente mientras se decide: la guardia LIFO no lo contaría, Mis Turnos mostraría el turno viejo y la reconciliación podría deshacerlo. Un estado transitorio visible es peor que ninguno |
| Un estado nuevo de solicitud, `cancelacion_pendiente` | Obligaría a revisar **todas** las consultas que hoy filtran por `'aprobada'`. El coste no está en el modelo, está en no haberlas encontrado todas |
| Caducar con un proceso de fondo (cron o Celery) | Una petición vencida **no tiene ningún efecto pendiente que aplicar**: el cambio simplemente sigue vigente. Reconocerla al leerla o al responderla da el mismo resultado sin infraestructura nueva |
| Mantener los 30 minutos | No dan tiempo a que la otra persona lea la notificación y conteste. Un plazo que nadie puede cumplir es un rechazo automático disfrazado |
| Dejar que el supervisor apruebe también las de solicitudes | Confunde dos cosas distintas: el acuerdo entre pares y la intervención administrativa. `execute_supervisor` sigue existiendo, aparte y sin cambios (`cancelar_solicitud.py:105`) |

## Consecuencias

**A favor.** Nadie deshace por su cuenta un turno que otro ya organizó. El rechazo y la caducidad
dan un desenlace claro en vez de dejar el asunto abierto.

**En contra, asumido.**

- Un flujo de un paso pasa a ser de dos, con dos actores y dos plazos. El frontend debe leer
  `cancelada` en la respuesta: un 200 ya no significa cancelada.
- El receptor puede recibir un error de guardia causado por un tercero que tocó esos días
  mientras él decidía.
- `SolicitudCambio` y `PermisoEspecial` llevan el mismo bloque de seis campos **sin abstracción
  común**: cualquier cambio hay que hacerlo dos veces.
- Si nadie mira una petición vencida, se queda en `pendiente` en base de datos aunque a efectos
  de negocio esté caducada.

## Referencias

- Regla completa: manual técnico § 8.2 (P0) y § 8.1 (los dos diagramas de estado).
- Fichas de los endpoints: § 6.2.
- Zonas frágiles asociadas: § 16.2. B9-B13 (los tres defectos de permisos, el mensaje inejecutable y
  la constante `VENTANA_CANCELACION_MINUTOS` duplicada) están **cerrados**: § 16.4.
- Hilo derivado de este ADR: [ADR 010](./010-dia-de-descanso-libre-tras-el-intercambio.md) — al pasar
  la cancelación a 24 h se retiró el bloqueo temporal del día para un nuevo cambio de descanso, que
  estaba calcado de la ventana de 30 min. Ahí se eliminó `VENTANA_CANCELACION_MINUTOS`, que en este
  archivo había quedado como código muerto.
- Hermano de este ADR en el dominio: "la última aprobada gana por día" (§ 8.2, P1).
