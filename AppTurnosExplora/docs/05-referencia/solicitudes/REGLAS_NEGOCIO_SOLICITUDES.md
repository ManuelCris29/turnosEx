# Reglas de Negocio y Casos Límite por Tipo de Solicitud

> **Documento vivo.** Actualizar siempre que se agregue, modifique o elimine una regla de negocio o validación.
> Última revisión: 2026-08-19 (comentario obligatorio en toda decisión; textos y contrato unificados en core)

---

## Regla transversal: el comentario es obligatorio

Toda acción que **resuelve** algo —aprobar, rechazar, cancelar o responder a una petición de
cancelación— exige un comentario o motivo con contenido. No es una regla por formulario, así que
no se repite en cada apartado de este documento: aplica a los seis tipos de solicitud y también a
permisos especiales, reprogramación de dobladas y pago de horas.

Se valida **en el servidor**, no solo en el formulario: el `required` del HTML es comodidad, no
defensa. Un texto vacío devuelve `400` con `code: 'comentario_requerido'` — en solicitudes siempre,
y en permisos para el cliente que pida JSON (el navegador conserva su mensaje y su redirect).

Los textos de aviso salen de `core/utils/comentarios.py` y llegan a las plantillas por el context
processor `core.context_processors.mensajes_comentario`, de forma que el navegador y el servidor
avisan con las mismas palabras para la misma falta.

Única excepción: la aprobación por enlace de correo electrónico, que es un GET de un clic y no
tiene dónde escribir.

Ver el manual técnico, § 8.2 principio **P6**, para los puntos de aplicación y los tests.

---

## Índice

- [CT Sencillo — Cambio de Turno Sencillo](#1-ct-sencillo--cambio-de-turno-sencillo)
- [Doblada](#2-doblada)
- [CT Permanente](#3-ct-permanente)
- [D-FDS — Doblada Fin de Semana](#4-d-fds--doblada-fin-de-semana)
- [Doblada Permanente](#5-doblada-permanente)
- [Cambio de Día de Descanso](#6-cambio-de-día-de-descanso)
- [Cancelar y eliminar desde gestión](#7-cancelar-y-eliminar-desde-gestión)
- [Validadores reutilizables (SolicitudValidator)](#8-validadores-reutilizables-solicitudvalidator)
- [Convenciones de nomenclatura de casos](#9-convenciones-de-nomenclatura-de-casos)

---

## 1. CT Sencillo — Cambio de Turno Sencillo

### Archivos clave

| Capa | Archivo |
|---|---|
| Strategy (backend) | `solicitudes/services/strategies/cambio_turno_strategy.py` |
| Validadores | `solicitudes/services/solicitud_validator.py` |
| Consultas | `solicitudes/services/solicitud_consulta_service.py` |
| Frontend | `static/js/cambio-turno/solicitar_cambio_turno.js` |
| Frontend validadores | `static/js/cambio-turno/validadores_solicitudes.js` |

### Reglas al crear — `validar_solicitud()`

| # | Caso | Regla | Mensaje de error | Capa |
|---|---|---|---|---|
| 1 | — | Datos requeridos presentes (solicitante, receptor, fecha) | "Faltan datos requeridos para la validación" | Backend |
| 2 | **A** | La fecha debe ser a partir de MAÑANA. El día en curso ya se está trabajando, así que no hay jornada que intercambiar. Al re-validar para aprobar solo se exige que no sea pasada (una solicitud enviada ayer para hoy sigue siendo aprobable: decide el supervisor) | "No se puede solicitar un cambio de turno para hoy: el día ya está en curso. Elige a partir de mañana." / "No se puede solicitar un cambio de turno para una fecha pasada." | Backend + Frontend (`fecha_minima = hoy + 1`) |
| 3 | — | Solicitante activo | "El empleado no está activo" | Backend |
| 4 | — | Receptor activo | "El empleado no está activo" | Backend |
| 5 | — | No mismo empleado | "No puedes solicitar cambio contigo mismo" | Backend |
| 6 | — | Comentario obligatorio | "Debes ingresar un comentario para la solicitud de cambio de turno." | Backend + Frontend |
| 7 | — | Solicitante con jornada asignada para la fecha | "El solicitante no tiene jornada asignada para esa fecha" | Backend |
| 8 | — | Receptor con jornada asignada para la fecha | "El receptor no tiene jornada asignada para esa fecha" | Backend |
| 9 | — | No duplicado del mismo par solicitante-receptor-fecha | "Ya existe una solicitud pendiente tuya con este explorador para la misma fecha" | Backend |
| 10 | **C** | Receptor sin ninguna solicitud pendiente para esa fecha (como solicitante o receptor) | "El compañero receptor ya tiene una solicitud pendiente para el DD/MM/YYYY. Debe esperar a que esa solicitud sea aprobada o cancelada..." | Backend |
| 11 | **C** | Solicitante sin ninguna solicitud pendiente para esa fecha (como solicitante o receptor) | "Ya tienes una solicitud pendiente para el DD/MM/YYYY. Debes esperar a que sea aprobada o cancelada..." | Backend |
| 12 | — | Jornadas contrarias obligatorias (AM ↔ PM) | "No se puede cambiar por la misma jornada. Los empleados deben tener jornadas contrarias" | Backend |
| 13 | — | No día de mantenimiento | "No se pueden realizar cambios de turno en días de mantenimiento. {descripcion}" | Backend + Frontend |
| 14 | — | No domingo | "No se puede cambiar domingo por día de semana" | Backend |
| 15 | — | No sábado (exclusivo de CT Sencillo) | "No se puede cambiar sábado por día de semana" | Backend |
| 16 | — | Rotación de festivos — informativo, no bloquea | — (solo logging) | Backend |
| 17 | — | Ninguno con doblada activa (AM+PM) — redirige a Solicitud de Dobladas | Ver mensajes diferenciados según quién tiene la doblada | Backend |
| 18 | — | **No hay tope de cambios por fecha** (eliminado). Lo que se puede hacer ese día ya lo gobiernan el estado real del día (trabaja, no está doblado, no está comprometido por otra solicitud aprobada) y el principio de "la última aprobada gana" | — | — |

### Reglas al aprobar — `aplicar_cambios()`

| Regla | Detalle |
|---|---|
| First-Come, First-Served | Al aprobar una solicitud, rechaza automáticamente todas las demás solicitudes pendientes del mismo receptor para la misma fecha. Notifica a cada solicitante afectado. |
| La sala no se intercambia | El CT intercambia la JORNADA. La sala es informativa (en qué es experto el explorador) y cada uno conserva la suya, igual que en las dobladas. |
| El cierre semanal NO se re-valida al aprobar | Es deliberado: el cierre limita a quién ENVÍA. Si el explorador envió el jueves y el cierre es el viernes, aprobar a tiempo es responsabilidad del supervisor. |

### Validaciones frontend

| Validación | Detalle |
|---|---|
| Datepicker bloquea sábados | `bloquearSabados: true` en configuración de Flatpickr |
| Datepicker bloquea domingos | Incluido en `bloquearDiasEspeciales: true` |
| Datepicker bloquea mantenimiento | `bloquearDiasEspeciales: true` — marcados en naranja |
| Festivos y temporada permitidos | `permitirFestivos: true`, `permitirTemporada: true` |
| Comentario obligatorio | Alerta SweetAlert si está vacío antes de enviar |
| Mantenimiento pre-envío | Verificación adicional con `cargarDiasMantenimiento()` antes de POST |
| Aviso si hay cambio aprobado | Advertencia informativa si ya existe CT aprobado para esa fecha |
| Estado "Descansando" | Si el solicitante está en descanso por doblada, muestra alert informativo y deshabilita el selector de compañeros |

### Casos especiales y excepciones

| Caso | Comportamiento |
|---|---|
| Temporada | Permitida. El supervisor recibe aviso en la notificación de nueva solicitud. |
| Festivos de semana | Permitidos. Solo se registra información de rotación (qué grupo debe doblar), no bloquea. |
| Solicitante descansando | El frontend muestra "Estás Descansando" con la razón y deshabilita el formulario. El backend bloqueará igual por jornada nula. |

### Pendientes / posibles mejoras

*(Agregar aquí si se identifican nuevas reglas faltantes)*

---

## 2. Doblada

### Archivos clave

| Capa | Archivo |
|---|---|
| Strategy (backend) | `solicitudes/services/strategies/doblada_strategy.py` |
| Validadores | `solicitudes/services/solicitud_validator.py` |
| Aplicación y reversión | `solicitudes/services/doblada_aplicacion_service.py` |
| Filtros | `solicitudes/services/doblada_filtro_service.py` |
| Detalles (modelo) | `solicitudes/models.py` → `DobladaDetalle` (`jornada_cubre_en_pago`: `AM` \| `PM` \| `AMBAS`) |
| Frontend | `static/js/cambio-turno/solicitar_doblada.js`, `templates/solicitudes/solicitar_doblada.html` |
| Vista POST | `solicitudes/views.py` → `jornada_cubre_en_pago` en `datos_solicitud` |

### Reglas al crear — `validar_solicitud()`

| # | Caso | Regla | Mensaje de error | Capa |
|---|---|---|---|---|
| 1 | — | Datos requeridos: solicitante, receptor, fecha_cesion, fecha_pago | Mensajes específicos por campo faltante | Backend |
| 2 | — | Comentario obligatorio | "Debes ingresar un comentario para la solicitud de doblada." | Backend + Frontend |
| 3 | — | fecha_cesion no puede ser pasada | "La fecha de cesión (DD/MM/YYYY) no puede ser en el pasado." | Backend |
| 4 | — | Solicitante y receptor activos | "El empleado no está activo" | Backend |
| 5 | — | No mismo empleado | "No puedes solicitar cambio contigo mismo" | Backend |
| 6 | — | Acuerdo previo: fecha_pago posterior a fecha_creacion_solicitud | "La fecha de pago (DD/MM/YYYY) debe ser posterior a la fecha de creación de la solicitud (DD/MM/YYYY)" | Backend + Frontend |
| 7 | **A** | fecha_pago en el mismo mes calendario que fecha_cesion | "La fecha de pago (DD/MM/YYYY) debe estar en el mismo mes que la fecha de cesión (DD/MM/YYYY). Ambas fechas deben pertenecer al mes MM/YYYY." | Backend + Frontend |
| 8 | **C** | Receptor sin solicitud pendiente en fecha_cesion (como solicitante o receptor) | "El compañero receptor ya tiene una solicitud pendiente para el DD/MM/YYYY. Debe esperar..." | Backend |
| 9 | **D** | Solicitante sin solicitud pendiente en fecha_cesion (como solicitante o receptor) | "Ya tienes una solicitud pendiente para el DD/MM/YYYY. Debes esperar..." | Backend |
| 10 | **F** | Receptor no descansa por doblada en fecha_pago (no puede ser solicitante con doblada aprobada ese día) | "El compañero receptor ya cedió su jornada el DD/MM/YYYY (tiene una doblada aprobada como solicitante en esa fecha) y estará descansando..." | Backend |
| 11 | — | fecha_pago diferente a fecha_cesion | "La fecha de pago (DD/MM/YYYY) no puede ser la misma que la fecha de cesión..." | Backend + Frontend |
| 12 | — | Días especiales de fecha_cesion: no domingo, no mantenimiento (festivos y temporada sí permitidos) | "No se puede realizar doblada en domingos" / "...en días de mantenimiento" | Backend + Frontend |
| 13 | — | Días especiales de fecha_pago: no domingo, no mantenimiento | Igual que anterior | Backend + Frontend |
| 14 | — | Si ambas fechas son festivos de semana, deben ser del mismo mes | "Los cambios y pagos de dobladas entre festivos solo se permiten cuando ambas fechas pertenecen al mismo mes." | Backend + Frontend |
| 15 | — | Pago en sábado: jornada_pago_sabado válida (AM o PM), receptor trabaja ese sábado según alternancia, sábado corresponde a jornada del receptor | Múltiples mensajes según la sub-regla incumplida | Backend + Frontend |
| 16 | — | Jornadas contrarias en fecha_cesion (solicitante vs receptor) | "Para ceder jornada AM, el receptor debe tener jornada PM..." | Backend |
| 17 | — | No triple turno: receptor sin doblada activa en fecha_cesion | Redirige a Solicitud de Dobladas | Backend |
| 18 | — | ~~No triple turno receptor en fecha_pago~~ **ELIMINADA**: en fecha de pago el receptor PIERDE una jornada (el deudor se la devuelve), no gana una. La protección real la da la regla 20. | — | — |
| 19 | — | Solicitante (deudor) sin doblada activa en fecha_pago | Redirige a Solicitud de Dobladas | Backend |
| 20 | — | Validación directa de jornada_cedida en fecha_pago: si el deudor ya tiene la misma jornada que cedió (jornada_cedida) en la fecha de pago, requiere CT previo. Es determinista y no depende de la jornada del receptor. Fallback: si no hay jornada_cedida, compara jornadas deudor vs acreedor. | "Ya tienes jornada X en la fecha de pago... Debes primero realizar un cambio de turno sencillo..." (retorna `code: 'requiere_cambio_turno_previo'`, `fecha_pago`, `jornada_comun`) | Backend + Frontend (Swal con redirección a CT Sencillo) |
| 21 | — | Si se envía `jornada_cubre_en_pago`, debe ser `AM`, `PM` o `AMBAS` | "Valor inválido para la jornada que cubrirás en la fecha de pago." | Backend |
| 22 | — | No combinar `jornada_cubre_en_pago` con pago en sábado que usa `jornada_pago_sabado` (regla especial de alternancia) | "No uses la opción AM/PM/toda la doblada junto con el pago en sábado; elige solo la jornada del sábado." | Backend |
| 23 | — | `jornada_cubre_en_pago` solo es coherente si el receptor tiene **doblada real** (turnos AM **y** PM) en `fecha_pago` | "La opción de cubrir AM, PM o toda la doblada solo aplica cuando el compañero tiene doblada (AM+PM) en la fecha de pago." | Backend |
| 24 | — | Si no se envía `jornada_cubre_en_pago`, el pago en cesión parcial sigue determinándose por `jornada_cedida` (comportamiento previo) | — | Backend |

### Reglas al aprobar — `aplicar_cambios()`

| Regla | Detalle |
|---|---|
| Ventana de cancelación de 30 minutos | Tras la aprobación, el solicitante puede cancelar la doblada dentro de los 30 minutos siguientes. El sistema elimina los turnos DOBLADA, restaura la jornada base de ambos empleados y cancela las deudas (DeudaExplorador y DeudaCorporativa). Pasada la ventana, ya no se puede cancelar. |
| Aviso de temporada al supervisor | Si fecha_cesion cae en temporada, la notificación al supervisor incluye un aviso visible para que evalúe antes de aprobar. |
| Pago en cesión parcial — `jornada_cubre_en_pago` (`aplicar_doblada_pago`) | **`AMBAS`:** se eliminan todos los turnos del receptor en `fecha_pago` y al deudor se le aseguran AM y PM (doblada completa de devolución; el acreedor descansa el día). **`AM` o `PM`:** se usa esa jornada como la que cubre el deudor (se quita al receptor esa media jornada y se le mantiene/asegura la contraria). Si el campo va vacío, se mantiene la lógica anterior basada en `jornada_cedida` / `tipo_cesion`. |

### Validaciones frontend

| Validación | Aplica a |
|---|---|
| Comentario obligatorio | Ambos tipos de cesión |
| fecha_cesion requerida | Ambos |
| Receptor(es) y fecha(s) de pago requeridos | Según tipo (total: AM+PM separados; parcial: uno solo) |
| fecha_pago posterior a fecha_creacion_solicitud | Ambos |
| fecha_pago diferente a fecha_cesion | Ambos |
| fecha_pago mismo mes que fecha_cesion | Ambos |
| No domingo ni mantenimiento en ninguna fecha | Ambos |
| Si alguna fecha es festivo, la otra debe serlo del mismo mes | Ambos |
| Sábado de pago debe corresponder al receptor según alternancia | Parcial (si fecha_pago es sábado) |
| Receptor en **doblada** en fecha de pago (día **no** sábado con regla especial): elegir **AM**, **PM** o **toda la doblada (AMBAS)** | Parcial; bloque `#opciones_cubre_pago_receptor_doblada`; obligatorio si el bloque está visible; valor por defecto alineado con `jornada_cedida` |
| Estado "Descansando" si el solicitante cedió su jornada | Informativo (no bloquea envío, pero deshabilita form) |

### Casos especiales y excepciones

| Caso | Comportamiento |
|---|---|
| Cesión total | El solicitante cede AM y PM a dos compañeros distintos. Requiere receptor_am, receptor_pm, fecha_pago_am, fecha_pago_pm. |
| Cesión parcial | El solicitante tiene jornada predeterminada y cede solo la mitad. Un solo receptor y fecha de pago. |
| Solicitante con doblada existente | Si ya tiene doblada activa (AM+PM), usa `jornada_cedida` en lugar de la jornada predeterminada. |
| Triple turno en sábado de pago | Se permite que el receptor "tenga doblada" en fecha_pago si es sábado, porque el sistema la divide en media jornada. |
| Receptor con doblada en fecha_pago | Permitido. El deudor indica explícitamente qué cubre: **solo AM**, **solo PM** o **AMBAS** (receptor sin turnos ese día y deudor con AM+PM). Si no se envía `jornada_cubre_en_pago`, el backend aplica la jornada de pago según `jornada_cedida` (una media jornada; el receptor conserva la otra). **No aplica** en fecha de pago **sábado** cuando rige `jornada_pago_sabado`. |
| Deudor con doblada (AM+PM) en fecha_pago | Puede pagar cualquier jornada de deuda porque ya trabaja las dos jornadas. |
| Temporada | Permitida para cesión. El supervisor recibe aviso en la notificación. |
| Festivos | Permitidos en ambas fechas. Si una es festivo, la otra también debe serlo del mismo mes. **También en el INTERCAMBIO de dobladas**: la regla se repite dentro de `_validar_intercambio`, que retorna antes del bloque de festivos del flujo normal. Sin ella se colaba cambiar un festivo por un día ordinario —en festivo el grupo que rota trabaja AM+PM, así que cuenta como DOBLADA y encajaba con cualquier otra— y el festivo se paga distinto. |

### Cobertura explícita en fecha de pago (`jornada_cubre_en_pago`)

**Modelo:** `DobladaDetalle.jornada_cubre_en_pago` — valores `AM`, `PM`, `AMBAS` (nulo si no aplica o si se confía en el comportamiento heredado vía `jornada_cedida`).

**Cuándo se ofrece en el formulario (cesión parcial):**

- El receptor tiene **doblada** (AM+PM) en la **fecha de pago** según `obtener-turno-explorador`.
- La fecha de pago **no** es **sábado** (en sábado continúa la regla de `jornada_pago_sabado` y no se muestra este bloque).

**Comportamiento:**

| Elección | Efecto al aprobar (`doblada_aplicacion_service.aplicar_doblada_pago`, rama cesión parcial) |
|---|---|
| `AM` o `PM` | El deudor cubre esa media jornada; al receptor se le quita esa jornada y se le deja la contraria. |
| `AMBAS` | Al receptor se le eliminan todos los turnos ese día; al deudor se le crean AM y PM si faltan. |
| *(vacío)* | Igual que antes: la jornada cubierta se toma de `jornada_cedida` (o del tipo de cesión parcial). |

**Validación:** `doblada_strategy.validar_solicitud` — coherencia del valor con turnos reales del receptor; prohibición de mezclar con pago sábado + `jornada_pago_sabado`.

**Frontend:** al cambiar fecha de pago o compañero se resetea el estado del receptor hasta recibir el nuevo fetch, para no mostrar opciones obsoletas.

### Matriz de fecha de pago — casos 2, 3.x, 4.x, 5 y 6.x

**Implementación:** `static/js/cambio-turno/solicitar_doblada.js` → `actualizarVistaPreviaAcuerdo()` (variables internas `casoNum` **5**, **7-9**, 1.2–1.10 y **3.9**).

**Cuándo aplica la matriz (`aplicaCasosPago`):**

1. **Emisor con una sola jornada** en fecha de cesión; receptor **sin** DOBLADA (AM+PM) ese día; y en cesión: **jornadas contrarias** (AM↔PM) **o** receptor **sin turno** (descanso/deuda).
2. **Emisor con DOBLADA** en fecha de cesión (**cesión parcial**): debe elegirse **jornada a ceder** (AM o PM); el receptor en cesión debe tener la **jornada contraria** a la cedida. Receptor **sin** DOBLADA en cesión.  
   - Las comparaciones «misma jornada que cediste» en fecha de pago usan **`jornada_cedida`**, no la jornada predeterminada del emisor (`jornadaEmisorReferencia` en código).
3. **Emisor con DOBLADA** (parcial) y receptor **descansando** en fecha de cesión (**serie 6.x**): con **jornada a ceder** elegida; la matriz de **fecha de pago** es la misma que en 3.x/4.x (`1.2`–`1.10`, `3.9`). Copy específico en **1.3** cuando aplica **6.1** / **6.4**.

**CASO 5 (inválido):** emisor **DOBLADA** y receptor **DOBLADA** el día de la cesión → **RECHAZADO** antes de la matriz de pago (`casoNum` **5**). El listado de exploradores ya excluye al receptor con doblada; el mensaje alineado con backend: `validar_no_triple_turno` → «El receptor no puede tener doblada el día de la cesión.»

**CASO 7–9 (inválido):** emisor **sin jornada cedible** en la fecha de cesión (descansando, sin turno AM/PM ni doblada real ni bloque «doblada existente» con jornada a ceder). Receptor con una jornada, doblada o descansando → **RECHAZADO** con el **mismo** mensaje (prevalece el emisor): «El solicitante no tiene jornada asignada para esa fecha». Frontend: `emisorSinJornadaParaCederEnCesion` + `solicitanteCesionTurnoFetchCompleto` en `solicitar_doblada.js` (`casoNum` **7-9**); aviso **Paso 2** `#aviso_sin_jornada_ceder_cesion` + validación en envío (`erroresValidacion`). Si `verificar-doblada-existente` indica `esta_descansando` sin doblada existente, se marca `solicitanteCesionTurnoFetchCompleto` sin llamar a `obtener-turno-explorador` (festivo con mensaje: misma lógica). Backend: `validar_jornadas_contrarias_doblada` (sin `jornada_solicitante` válida).

Si el receptor tiene **DOBLADA** en cesión en un flujo de **una sola jornada** emisor (**CASO 2**), no debe ofrecerse en el selector; `receptorCesionDoblada` evita aplicar la matriz en frontend.

| Caso negocio | Premisa cesión (Paso 1) | Estados en **fecha de pago** (Paso 2) | Resultado | Mensaje / acción (resumen) | Ref. código |
|---|---|---|---|---|---|
| **CASO 5** | Emisor **DOBLADA** (parcial); receptor **DOBLADA** (mismo día cesión) | — | **RECHAZADO** | «El receptor no puede tener doblada el día de la cesión.» | `5` + `validar_no_triple_turno` |
| **CASO 7** | Emisor **descansando** (sin turno cedible); receptor **1 jornada** | — | **RECHAZADO** | «El solicitante no tiene jornada asignada para esa fecha» | `7-9` + validador jornadas |
| **CASO 8** | Emisor **descansando**; receptor **DOBLADA** | — | **RECHAZADO** | Igual **CASO 7** (mensaje emisor prevalece) | `7-9` |
| **CASO 9** | Emisor **descansando**; receptor **descansando** | — | **RECHAZADO** | Igual **CASO 7** | `7-9` |
| **CASO 2** | Emisor 1 jornada; receptor **DOBLADA** | — | **Inválido** | No debe listarse como compañero (sin jornada libre). | Filtro exploradores + `receptorCesionDoblada` bloquea matriz |
| **CASO 3** | Emisor 1 jornada; receptor descansando (deuda) | Ambos **descansando** | **RECHAZADO** | «Los dos están descansando…» | `1.2` |
| **CASO 3.2** | Igual | Emisor descansando; receptor **una jornada** | **Válido** | «El emisor está descansando… reemplazas en AM o PM» | `1.3` |
| **CASO 3.4** | Igual | Emisor descansando; receptor **doblada** | **Válido** | Debe elegirse cobertura **AM**, **PM** o **AMBAS** (`jornada_cubre_en_pago`) si el formulario muestra el bloque; resumen y backend alineados | `1.4` |
| **CASO 3.5** | Igual | Emisor una jornada; receptor **descansando** | **RECHAZADO** | «El receptor se encuentra descansando…» | `1.5` / `1.8` |
| **CASO 3.6** | Igual | Ambos **una jornada** | **Válido** si contrarias en pago; si **misma** jornada en pago → **CT sencillo** antes | Misma jornada: bloqueo envío + enlace a CT sencillo | `1.6` |
| **CASO 3.7** | Igual | Emisor una jornada; receptor **doblada** | **Válido** (posible CT si misma jornada que cedió) | Texto informativo caso `1.7` | `1.7` |
| **CASO 3.8** | Igual que 3.5 | Emisor una jornada; receptor descansando | **RECHAZADO** | Igual 3.5 | `1.5` / `1.8` |
| **CASO 3.9** | Igual | Emisor **doblada**; receptor **descansando** | **RECHAZADO** | «El emisor tiene una doblada… el receptor descansando…» | `3.9` |
| **CASO 3.14** (primero) | Igual | Emisor **doblada**; receptor una jornada | **RECHAZADO** | Sin jornada libre para cubrir | `1.9` |
| **CASO 3.14** (ambos doblada) | Igual | Ambos **doblada** | **RECHAZADO** | «Ambos tienen doblada…» | `1.10` |
| **CASO 4.1** | Emisor **DOBLADA** (parcial); receptor 1 jornada **contraria a la cedida** | Ambos **descansando** (pago) | **RECHAZADO** | «Los dos están descansando…» | `1.2` |
| **CASO 4.2** | Igual | Emisor descansando; receptor **una jornada** | **Válido** | «El emisor está descansando…» | `1.3` |
| **CASO 4.2** (receptor doblada pago) | Igual | Emisor descansando; receptor **doblada** | **Válido** | Igual **3.4**: elección explícita AM / PM / AMBAS cuando aplica UI | `1.4` |
| **CASO 4.3** | Igual | Emisor una jornada; receptor **descansando** | **RECHAZADO** | «El receptor se encuentra descansando…» | `1.5` / `1.8` |
| **CASO 4.4** | Igual | Ambos **una jornada** (pago) | **Válido** / **CT** si misma jornada | Igual **3.6** (misma jornada → bloqueo + CT sencillo) | `1.6` |
| **CASO 4.5** | Igual | Emisor una jornada; receptor **doblada** | **Válido** (posible CT si coincide con lo cedido) | Igual **3.7** | `1.7` |
| **CASO 4.6** | Igual que 4.3 | Emisor una jornada; receptor descansando | **RECHAZADO** | Igual 4.3 | `1.5` / `1.8` |
| **CASO 4A.11** | Igual | Ambos misma jornada en pago (ej. PM–PM) | **CT obligatorio** antes de enviar | Mensaje específico emisor con doblada parcial + CT | `1.6` (rama misma jornada) |
| **CASO 4.7** | Igual | Emisor **doblada** (pago); receptor **descansando** | **RECHAZADO** | Igual **3.9** | `3.9` |
| **CASO 4.8** | Igual | Emisor **doblada** (pago); receptor una jornada | **RECHAZADO** | Sin cupo para cubrir | `1.9` |
| **CASO 4.9** | Igual | Ambos **doblada** (pago) | **RECHAZADO** | «Ambos tienen doblada…» | `1.10` |

**Serie 6.x** — misma matriz de **fecha de pago** que arriba; cambia solo la premisa de **cesión**: emisor **DOBLADA** (parcial), receptor **descansando**. Flags JS: `cesionValidaEmisorDobladaReceptorDescansa` + `emisorTieneDobladaParcialCesion`.

| Caso negocio | Estados en **fecha de pago** | Ref. código | Notas |
|---|---|---|---|
| **6.1** | Emisor descansando; receptor una jornada | `1.3` | Mensaje tipo «Se puede realizar el cambio…» (rama CASO 6) |
| **6.2** | Ambos descansando | `1.2` | |
| **6.3** | Emisor descansando; receptor doblada | `1.4` | Cobertura explícita `jornada_cubre_en_pago` si el bloque está visible |
| **6.4** | Igual **6.1** | `1.3` | Mismo código; variante de redacción en negocio |
| **6.5** | Emisor una jornada; receptor descansando | `1.5` / `1.8` | |
| **6.6** | Ambos una jornada | `1.6` | CT si misma jornada en pago |
| **6.7** | Emisor una jornada; receptor doblada | `1.7` | |
| **6.8** | Emisor doblada; receptor descansando | `3.9` | |
| **6.9** | Emisor doblada; receptor una jornada | `1.9` | |
| **6.10** | Ambos doblada | `1.10` | |

El **backend** acepta receptor sin jornada en cesión cuando el emisor cede AM/PM válido (`validar_jornadas_contrarias_doblada`, retorno temprano). Valida además coincidencias en pago (`validar_coincidencia_jornadas_pago`, etc.); la tabla alinea el copy del **Paso 3** con estas reglas.

### Pendientes / posibles mejoras

*(Agregar aquí si se identifican nuevas reglas faltantes)*

---

## 3. CT Permanente

### Archivos clave

| Capa | Archivo |
|---|---|
| Strategy (backend) | `solicitudes/services/strategies/ct_permanente_strategy.py` |
| **Evaluación de fechas (fuente única)** | `solicitudes/services/ct_permanente_helper.py` → `evaluar_fechas_ct_permanente` |
| Validadores | `solicitudes/services/validators/ct_permanente_validator.py` |
| Previsualización | `solicitudes/views/api_disponibles_ct_preview.py` → `PrevisualizarCTPermanenteView` |
| Frontend | `static/js/cambio-turno/solicitar_ct_permanente.js` |
| Frontend validadores | `static/js/cambio-turno/validadores_solicitudes.js` |

> **Fuente única de fechas.** Qué días entran en el cambio lo decide **solo**
> `evaluar_fechas_ct_permanente`. La validación, la vista previa y la aplicación llaman ahí, así
> que las tres responden lo mismo: lo que el usuario ve en el paso previo es exactamente lo que
> se materializa. No añadir copias de la expansión/filtrado de fechas.

### Reglas al crear — `validar_solicitud()`

| # | Caso | Regla | Mensaje de error | Capa |
|---|---|---|---|---|
| 1 | — | Datos requeridos: solicitante, receptor, fecha_inicio, fecha_fin (obligatoria) | "Faltan datos requeridos para la validación (fecha_fin es obligatoria)" | Backend |
| 2 | — | Solicitante y receptor activos | "El empleado no está activo" | Backend |
| 3 | — | No mismo empleado | "No puedes solicitar cambio contigo mismo" | Backend |
| 4 | — | Comentario obligatorio | "Debes ingresar un comentario para la solicitud de cambio de turno permanente." | Backend + Frontend |
| 5 | — | fecha_inicio no puede ser pasada (**solo al crear**; al re-validar para aprobar se omite y los días ya transcurridos se descartan uno a uno) | "La fecha de inicio no puede ser en el pasado" | Backend |
| 6 | — | fecha_fin obligatoria y posterior a fecha_inicio | "La fecha fin es obligatoria..." / "La fecha fin debe ser posterior a la fecha inicio" | Backend + Frontend |
| 7 | — | Solo lunes a viernes en el rango (no sábados ni domingos) | "No se pueden realizar cambios permanentes en sábados..." / "...en domingos" | Backend |
| 8 | — | No festivos en el rango | "No se pueden realizar cambios permanentes en días festivos" | Backend |
| 9 | — | No mantenimiento en el rango | "No se pueden realizar cambios de turno en días de mantenimiento. {descripcion}" | Backend |
| 10 | — | No temporada en el rango | "No se pueden realizar cambios permanentes en días de temporada. {descripcion}" | Backend |
| 11 | — | Al menos un día del rango con jornadas contrarias (AM ↔ PM), según el estado REAL (`estado_dia`). Se valida **siempre**, también con `fechas_especificas` | "No se puede realizar el cambio permanente. No se encontraron días en el rango donde los empleados tengan jornadas contrarias..." | Backend |
| 11b | — | **Por día**: un día en que ambos trabajan la MISMA jornada NO se aplica (no hay intercambio; aplicarlo dejaría a los dos en la contraria y la franja original sin cobertura) | Se excluye con razón "Sin jornada contraria" | Backend |
| 12 | — | Al menos un día APLICABLE en el rango (excluidos: fines de semana, festivos, mantenimiento, temporada, descansos reales, días ya comprometidos por otra solicitud, días ya cambiados y días sin jornada contraria) | "No se encontraron días válidos en el rango seleccionado..." | Backend |
| 13 | — | Sin superposición con otros cambios permanentes entre los mismos empleados (en ambas direcciones; solapamiento de intervalos completo, `fecha_fin` nula = indefinido) | "Ya existe un cambio permanente superpuesto entre estos empleados" | Backend |
| 15 | — | El solicitante no puede tener otra solicitud pendiente en **ninguno** de los días que el cambio tocaría | "Ya tienes una solicitud pendiente para el {fecha}, uno de los días que este cambio permanente afectaría..." | Backend |
| 14 | — | Si hay dias_seleccionados: al menos uno, todos dentro del rango, todos lunes-viernes | Mensajes específicos por sub-regla | Backend + Frontend |

### Reglas al aprobar

- Se **re-valida** con el estado actual (`revalidar_para_aprobar`): si entre el envío y la
  aprobación cambió una jornada, apareció un festivo o el día quedó comprometido, se bloquea.
- Se omite "no empezar en el pasado" (regla de creación) y, en su lugar, se descartan los días
  ya transcurridos: una aprobación tardía aplica solo los días futuros y no reescribe historia.
- **Si no queda ningún día aplicable, la aprobación falla** y la transacción revierte. Antes se
  aprobaba con "0 días", dejando la solicitud aprobada sin turnos ni snapshot.

### Aplicación

Por cada día aplicable, solicitante y receptor **intercambian** su jornada: cada uno recibe la
del otro (no "la contraria de la suya"). Los turnos se escriben con `delete()` + `create()`,
igual que el CT sencillo: crear sin borrar dejaba dos turnos el mismo día y "Mis Turnos" leía el
día como DOBLADA. El estado previo real se guarda en `snapshot_turnos_previos` y se restaura al
cancelar dentro de los 30 min (borrado dirigido: si otro cambio ya pisó el día, se respeta).

### Validaciones frontend

| Validación | Detalle |
|---|---|
| Comentario obligatorio | Alerta SweetAlert |
| Al menos un día de semana seleccionado | Valida checkboxes de días o fechas_especificas |
| fecha_fin posterior a fecha_inicio | Validación en `validadores_solicitudes.js` |
| Si hay fechas específicas, al menos una compatible con el compañero | Si `overrideDiasSeleccionados.fechas_especificas` vacío, bloquea |

### Casos especiales y excepciones

| Caso | Comportamiento |
|---|---|
| Selección de días completa vs fechas específicas | `dias_seleccionados` puede contener `dias_semana` (lunes a viernes como números 0-4) o `fechas_especificas` (listado de fechas puntuales). `fechas_especificas` tiene prioridad |
| Fechas específicas incompatibles | El JS precarga solo los días compatibles (`window.overrideDiasSeleccionados`), pero eso es **solo UX**: el backend re-evalúa cada día por su cuenta y descarta los que no tengan jornada contraria. Un POST con fechas fabricadas no salta el control |
| Compatibilidad (%) del compañero | Se calcula sobre los días realmente aplicables del solicitante, no sobre días de calendario, y usa la misma definición de "día aplicable" que la aplicación |

### Pendientes / posibles mejoras

*(Agregar aquí si se identifican nuevas reglas faltantes)*

---

## 4. D-FDS — Doblada Fin de Semana

> **Implementada** (reescrita). Antes era una auto-solicitud sin efecto al aprobar; ahora es una doblada entre dos exploradores en unidades de **día de finde completo** (no AM/PM).

### Concepto

El punto de partida es la **alternancia publicada** por el supervisor para el año (`AsignacionEspecialService.grupo_trabaja`, tabla `AsignacionEspecialManual`): un grupo trabaja un día completo del finde (AM+PM) y el otro grupo trabaja el otro día. Si el año no está publicado, esos días quedan *sin planificar* y no se puede solicitar sobre ellos. Pero esa es solo la programación por defecto — el estado real de cada persona lo da `TurnoService.estado_dia`, y ahí conviven quienes trabajan **los dos** días del finde (el propio más uno que cubren por un favor), quienes **descansan los dos** y quienes tienen **media jornada** por un cambio previo.

- **Favor (fecha de cesión):** el solicitante trabaja un día del finde a jornada completa y lo cede. El **receptor** —cualquiera que ESE día descanse, sin importar el grupo— pasa a trabajarlo completo (AM+PM).
- **Pago (fecha de pago, mismo mes y mismo día de la semana):** espejo. El solicitante cubre al compañero en un día que el compañero trabaja y él tiene libre. El receptor **descansa ese día**.

Unidad transferida = un día de finde completo. No hay medias jornadas, ni matriz de casos AM/PM.

**Traspaso de cobertura**: quien trabaja un día por un favor puede volver a cederlo. Se admite porque el sustituto trabaja el día completo, así que el acreedor original conserva su descanso y su acuerdo sigue vigente. Cada cesión crea su **propia** deuda con su fecha de pago —no se acumulan ni se traspasan— y para recibir hay que descansar ese día, así que nadie acumula dos coberturas en el mismo finde. La cadena solo se deshace en orden inverso, por la guardia LIFO de `use_cases/cancelar_solicitud.py`.

### Archivos clave

| Capa | Archivo |
|---|---|
| Strategy (backend) | `solicitudes/services/strategies/d_fds_strategy.py` |
| Aplicación (turnos + deudas) | `solicitudes/services/d_fds_aplicacion_service.py` |
| Validadores reutilizados | `solicitudes/services/solicitud_validator.py` (`validar_fecha_pago_mismo_mes_cesion`, etc.) |
| Alternancia | `turnos/services/alternancia_fines_semana_service.py` |
| Detalle (modelo) | `solicitudes/models.py` → `DobladaDetalle` (reusa `fecha_pago`, `minutos_deuda`) |
| Vista POST | `solicitudes/views/procesar_solicitud.py` (rama `D FDS`: receptor real + `fecha_pago`) |
| Routing/Form | `solicitudes/views/cambio_turno_pages.py` → `_render_d_fds`; `templates/solicitudes/solicitar_d_fds.html`; `static/js/cambio-turno/solicitar_d_fds.js` |

### Reglas al crear — `validar_solicitud()`

La elegibilidad se decide por el **estado real de cada día** (`TurnoService.estado_dia`, las mismas capas que Mis Turnos), **no** por el grupo AM/PM ni por la alternancia teórica: en la operación conviven quienes trabajan los dos días del finde (el propio más uno que cubren por un favor), quienes descansan los dos y quienes tienen media jornada por un cambio previo.

| # | Regla | Mensaje de error | Capa |
|---|---|---|---|
| 1 | Requeridos: solicitante, receptor, fecha de cesión, fecha de pago | Mensajes específicos por campo faltante | Backend + Frontend |
| 2 | Solicitante y receptor activos | "El empleado no está activo" | Backend |
| 3 | No mismo empleado | "No puedes solicitar cambio contigo mismo" | Backend |
| 4 | Comentario obligatorio | "Debes ingresar un comentario para la solicitud de D FDS." | Backend + Frontend |
| 5 | Cesión y pago deben ser fin de semana (sáb/dom) | "La fecha de cesión/pago debe ser un fin de semana (sábado o domingo)" | Backend + Frontend |
| 6 | Cesión y pago **posteriores a hoy**; pago ≠ cesión. Al re-validar para aprobar se admite la cesión del día en curso (no bloquear al supervisor) | Mensajes específicos | Backend + Frontend |
| 7 | Pago en el **mismo mes** que la cesión | "La fecha de pago (...) debe estar en el mismo mes que la fecha de cesión (...)" | Backend + Frontend |
| 8 | No mantenimiento en ninguna fecha | "No se pueden realizar cambios... en días de mantenimiento" | Backend |
| 9 | **Cesión**: el solicitante TRABAJA ese día a jornada completa (`estado_dia(...).jornada == 'DOBLADA'`) | "No tienes un turno que ceder el dd/mm/aaaa (...)" / "solo tienes media jornada (...) por un cambio previo" | Backend + Frontend |
| 10 | **Cesión**: el compañero tiene ese día LIBRE (es lo único que se le exige; el grupo AM/PM ya no interviene) | "Tu compañero ya trabaja el dd/mm/aaaa; no tiene ese día libre para cubrirte..." | Backend + Frontend |
| 11 | **Pago**: el compañero trabaja ese día completo y el solicitante lo tiene LIBRE | "Tu compañero no trabaja el dd/mm/aaaa..." / "No puedes pagar el dd/mm/aaaa: ese día ya trabajas..." | Backend + Frontend |
| 12 | No se puede pagar con un día **ya cedido** a otro compañero (él lo está cubriendo) | "No puedes pagar el dd/mm/aaaa: ese día ya se lo cediste a un compañero..." | Backend |
| 13 | El pago debe caer en el **mismo día de la semana** que la cesión (sáb→sáb, dom→dom), para conservar la misma cantidad de sábados/domingos al mes | "Cediste un domingo: la devolución también debe ser un domingo..." | Backend + Frontend |
| 14 | Ninguna de las dos fechas puede estar tomada por otra **solicitud pendiente** del solicitante o del receptor, cruzando tanto la cesión como el pago de esas solicitudes | "Ya tienes una solicitud pendiente que afecta el dd/mm/aaaa (como cesión o como pago)..." | Backend |
| 15 | **No importa POR QUÉ trabaja cada uno su día**, solo que el día quede cubierto. Vale ceder un día de cobertura, y vale pagar cubriendo un día que el compañero trabaja por un favor ajeno: un favor se mide en días trabajados, no en de quién es el día | — (no bloquea; el formulario lo señala como información) | Backend + Frontend |
| 16 | **Traspaso de cobertura**: al ceder un día que se trabaja por un favor, el sustituto lo cubre completo, el acreedor original conserva su descanso y su acuerdo sigue vigente; solo cambia quién cubre, y se le notifica | Aviso informativo en el resumen del formulario y notificación al acreedor | Backend + Frontend |

### Reglas al aprobar — `aplicar_cambios()` → `DFDSAplicacionService`

| Efecto | Detalle |
|---|---|
| Cesión | Receptor dobla AM+PM en la fecha de cesión; solicitante sin turnos (descansa el finde). |
| Pago | Solicitante dobla AM+PM en la fecha de pago; receptor sin turnos (descansa su día). |
| Deuda entre exploradores | `DeudaExplorador`: solicitante (deudor) → receptor (acreedor), saldada con la fecha de pago. |
| Deuda corporativa | **No aplica en D FDS**: los 30 min solo se generan de lunes a viernes y ambas fechas son de fin de semana (`aplica_deuda_doblada` lo garantiza). |
| Snapshot | Se captura snapshot de turnos previos (reutiliza el de doblada) para permitir reversión. |

### Display en Mis Turnos

La vista `turnos/api/views.py` incluye `D FDS` junto con `DOBLADA` en las consultas de descanso: el solicitante ve "descanso (cedió)" en la cesión y el receptor ve "descanso (pago)" en la fecha de pago.

El descanso se atribuye **solo a la fecha cedida/pagada**, no a los dos días del finde: el otro día ya se descansaba por alternancia (lo resuelve L6 con su propio motivo).

### Validaciones frontend

| Validación | Detalle |
|---|---|
| Selección por tarjetas de finde, día a día | `solicitar_d_fds.js` pinta un finde por tarjeta con el estado real de SUS DOS días; se toca el día concreto que se cede. Cada día es independiente: se puede trabajar sábado y domingo y ceder cualquiera de los dos. Los no cedibles quedan deshabilitados con su motivo |
| Compañeros | Se ofrece a quien DESCANSE el día que se cede, sin filtro de grupo AM/PM; los no disponibles se muestran igualmente con su motivo (`dfds-companeros` → `DFDSStrategy.disponibilidad_companero`) |
| Aviso de traspaso | Si el día que cedes lo trabajas por un favor, el resumen indica con quién era el acuerdo y quién pasará a cubrirlo |
| Días de pago que el compañero cubre | `alternancia-mes` marca por día `propio` (lo trabaja porque es SU día) y `cobertura` (a quién cubre). Si el compañero cubre a un tercero ese día, la fecha SÍ sirve, pero la tarjeta lo advierte: hay un tercero implicado y el día cambia de manos |
| Findes a caballo entre dos meses | `alternancia-mes` lista el finde cuyo sábado es del mes anterior si el domingo cae en el mes consultado, y solo permite elegirlo desde el mes al que pertenece el día trabajado (`del_mes`), porque el pago debe ser del mismo mes |
| Cierre semanal | Cada día trae `cerrado`; las tarjetas de findes ya cerrados no se pueden elegir (el POST también lo valida) |
| Pago restringido al mismo mes y día de semana | Los candidatos de pago se filtran por mes de la cesión, mismo día de la semana y fecha posterior a hoy |
| Campos requeridos + comentario | Validación previa al POST con SweetAlert |

### Reprogramación por inasistencia

Si alguien **no cumple su día** (el receptor en la cesión, o el solicitante en el pago), el
supervisor lo registra y le asigna otro día. Usa el mismo `ReprogramacionDobladaService` que
DOBLADA y DOBLADA PERMANENTE: se anula el día no cumplido (soft-delete + se resta su deuda) y se
programa uno nuevo, **sin tocar al otro explorador** — su descanso ya lo tuvo el día original, lo
que quedó sin cubrir es el turno.

Lo propio del fin de semana está en `_validar_dia_compensacion_finde`. El día de compensación:

| Regla | Motivo |
|---|---|
| Debe ser **sábado o domingo** | La unidad de D FDS es el día completo de finde |
| **Mismo día de la semana** que el que no se cumplió | Mantiene intacta su cantidad de sábados y domingos del mes |
| La persona debe **descansarlo** | Si ya trabaja, no puede doblarse de nuevo |
| No puede ser un día que **ella cedió** | Lo cubre un compañero como extra: quedarían dos personas en el turno |

No genera los 30 min: `aplica_deuda_doblada` los descarta en fin de semana. Al cancelar la
reprogramación la persona simplemente vuelve a descansar (no había jornada previa que restaurar).

### Pendientes / posibles mejoras

- Ventana de cancelación de 30 min (existe snapshot; falta exponer el botón/flujo para D FDS).
- La reprogramación **compensa** (la persona trabaja otro día de finde), no mueve la fecha pactada.
  Si avisa con antelación, hoy no hay forma de cambiar el día de pago para que el compañero vuelva
  a trabajar el original y la sala no quede corta.
- Mensaje de éxito compartido en `procesar_solicitud.py` tiene un mojibake heredado ("compañero").

---

## 5. Doblada Permanente

> Acuerdo **recurrente** dentro de un rango del mismo mes, entre el solicitante y uno o varios
> compañeros. El formulario es multi-compañero: el orquestador agrupa por compañero y crea **una
> solicitud independiente por cada uno**, todo o nada.

### Concepto

- **Días de cesión:** el compañero cubre; él dobla AM+PM y el solicitante descansa.
- **Días de devolución:** el solicitante devuelve el favor; él dobla y el compañero descansa.
- Cada doblada efectiva = **30 min de deuda corporativa** para quien dobla (Consolidado / PDH).

La elegibilidad se decide **día a día con la jornada REAL** (`_jornada_doblada_perm` sobre
`estado_dia`): ambos deben tener ese día una jornada única AM/PM y **contraria** entre sí. Los días
que no cumplen se **omiten** (no se rechaza el acuerdo entero), que es lo correcto para algo
recurrente. Al aplicar, cada lado se recorta al **mínimo común**: solo se aplican pares
cubrir↔devolver completos.

### Archivos clave

| Capa | Archivo |
|---|---|
| Strategy | `solicitudes/services/strategies/doblada_permanente_strategy.py` |
| Aplicación / reversión | `solicitudes/services/doblada_permanente_aplicacion_service.py` |
| Elegibilidad por día | `solicitudes/services/ct_permanente_helper.py` → `_jornada_doblada_perm` |
| Flujo multi-compañero | `solicitudes/services/solicitud_orchestrator.py` → `_procesar_doblada_permanente_multi` |
| Detalle (modelo) | `solicitudes/models.py` → `DobladaPermanenteDetalle` |
| Form | `templates/solicitudes/solicitar_doblada_permanente.html`; `static/js/cambio-turno/solicitar_doblada_permanente.js` |
| Tests | `solicitudes/tests/test_doblada_permanente.py` |

### Reglas al crear — `validar_solicitud()`

| # | Regla | Mensaje de error | Capa |
|---|---|---|---|
| 1 | Requeridos: solicitante, compañero, rango y al menos un día de cesión y uno de devolución | Mensajes específicos | Backend + Frontend |
| 2 | Empleados activos, no uno mismo, comentario obligatorio | Mensajes estándar | Backend + Frontend |
| 3 | Rango válido y no iniciado en el pasado | "El rango no puede iniciar en el pasado" | Backend + Frontend |
| 4 | Rango **dentro del mismo mes** | "El rango debe estar dentro del mismo mes..." | Backend + Frontend |
| 5 | Solo **lunes a viernes** (los findes se rigen por alternancia → D FDS) | "La doblada permanente es solo de lunes a viernes..." | Backend + Frontend |
| 6 | Un mismo día no puede ser de cesión y de devolución | "Un mismo día de la semana no puede ser de cesión y de devolución a la vez." | Backend + Frontend |
| 7 | **Balance**: misma cantidad de fechas (o días) cubiertas que devueltas | "Debes devolver la misma cantidad de fechas que te cubren..." | Backend + Frontend |
| 8 | Ni solicitante ni compañero pueden estar **sancionados** en el rango | "Estás sancionado en ese rango..." / "{compañero} está sancionado en ese rango." | Backend |
| 9 | El compañero no puede tener otra **doblada permanente** (pendiente o aprobada) que comparta alguna **fecha**. Se cruzan las fechas concretas de ambos acuerdos, no los días de la semana: dos acuerdos pueden usar el mismo weekday en fechas distintas y no chocar. Solo se compara por weekday si el otro acuerdo es legacy (sin `fechas_*`) | "{compañero} ya tiene una doblada permanente en esas fechas (dd/mm/aaaa)." | Backend |
| 10 | Jornadas **contrarias** por fecha real; deben quedar días válidos para cubrir **y** devolver | "No quedan fechas válidas para CUBRIR y DEVOLVER a la vez..." | Backend + Frontend |
| 11 | Ninguna de las **fechas afectadas** puede estar tomada por otra solicitud **pendiente**, ni del solicitante ni del compañero. Se cruzan las fechas que de verdad se aplicarían, no solo el inicio del rango | "Ya tienes una solicitud pendiente que afecta el dd/mm/aaaa..." | Backend |

### Reglas del flujo multi-compañero — `_procesar_doblada_permanente_multi`

| # | Regla | Mensaje de error |
|---|---|---|
| 1 | Una fecha solo la puede **cubrir** un compañero (ni **pagar** dos) | "La fecha dd/mm/aaaa está asignada a dos compañeros..." |
| 2 | Una fecha no puede ser **cesión de uno y devolución de otro**: ese día no se puede descansar y doblar a la vez | "El dd/mm/aaaa lo tienes como día que cedes y como día que devuelves a la vez..." |
| 3 | Solo se devuelve a quien te cubre, y **por compañero** la misma cantidad de fechas | "Solo puedes devolverle a un compañero que te cubra." / "A cada compañero debes devolverle la misma cantidad..." |
| 4 | **Cierre semanal** sobre todas las fechas (si la solicitud llega por el flujo antiguo de días de la semana, el rango se expande para poder comprobarlo) | Mensaje de cierre |
| 5 | Creación **todo o nada**: el lote va en una transacción; si una falla, ninguna queda creada | "Error creando la solicitud para {nombre}: ..." |

### Reglas al aprobar y aplicar

| Efecto | Detalle |
|---|---|
| Cesión | El receptor queda AM+PM (`tipo_cambio='DOBLADA PERM'`); el solicitante sin turnos. |
| Devolución | El solicitante queda AM+PM; el receptor sin turnos. |
| Deuda corporativa | 30 min por doblada efectiva, **idempotente** (aplicar dos veces no duplica) y solo lun-vie. |
| Snapshot | Se captura antes de mutar y **no se sobrescribe** en una segunda aplicación. |
| Reversión | Restaura el snapshot, cancela las deudas y **reconcilia** lo que siga vigente en esas fechas (patrón #22). |

### Pendientes / posibles mejoras

- El recorte al mínimo común descarta pares tomando los primeros por fecha; el usuario solo ve los
  conteos en el mensaje, no qué fechas quedaron fuera.

---

## 6. Cambio de Día de Descanso

> **Intercambio puro de días entre dos exploradores: no genera deuda.** Cada uno sigue trabajando
> lo mismo, solo cambia CUÁL día. Es lo que lo distingue de una doblada, donde alguien trabaja de
> más y hay que devolvérselo.

### Dos mundos distintos según el día

| | Fin de semana (sáb/dom) | Entre semana (lun-vie, temporada) |
|---|---|---|
| Qué se cambia | Cuál de los dos días del finde trabaja cada uno | El día de descanso de temporada |
| Devolución | Sí, en otro finde del mismo mes | No: el intercambio se salda en el acto |
| Día de la devolución | El **contrario** (cedes sábado → devuelves domingo) | — |
| Sub-modalidades | Una sola | Cuatro (ver abajo) |

### Archivos clave

| Capa | Archivo |
|---|---|
| Strategy | `solicitudes/services/strategies/cambio_descanso_strategy.py` |
| Aplicación / reversión | `solicitudes/services/cambio_descanso_aplicacion_service.py` |
| Compañeros (finde) | `solicitudes/views/api_fin_semana.py` → `DFDSCompanerosView` (compartida con D FDS) |
| Descansos de semana | `solicitudes/views/api_fin_semana.py` → `DescansosSemanaUsuarioView` |
| Form | `templates/solicitudes/solicitar_cambio_descanso.html`; `static/js/cambio-turno/solicitar_cambio_descanso.js` |

### Modalidad FIN DE SEMANA

Semana 1 (cesión): el solicitante trabaja el otro día del finde en lugar del que cede, y el
receptor al revés. Semana 2 (devolución): espejo. Cada uno sigue trabajando **un solo día por
finde**.

| # | Regla | Mensaje de error |
|---|---|---|
| 1 | Ambas fechas de fin de semana, futuras y distintas | Mensajes específicos |
| 2 | La devolución debe ser el **día contrario** (sáb↔dom) | "Cambiaste un sábado: la devolución debe ser un domingo (el día contrario), para mantener tu balance de domingos en el mes." |
| 3 | Mismo mes | "La fecha de pago debe estar en el mismo mes…" |
| 4 | Grupos **contrarios** | "El compañero debe ser del grupo contrario…" |
| 5 | Ambos con turno real en los días que ceden | "No tienes un turno válido el…" |
| 6 | Cada uno debe **descansar el día que recibe** (si ya trabaja los dos días del finde, no hay hueco donde encajarlo) | "Tu compañero ya trabaja el… (trabaja los dos días de ese fin de semana)." |
| 7 | Sin duplicado pendiente del mismo par de fechas, en cualquier orden | "Ya enviaste esta solicitud de cambio de descanso…" |

El **balance de domingos** se conserva por construcción: ganas un domingo en un finde y lo cedes
en el otro. En meses con 5 domingos el reparto puede quedar impar; el formulario lo advierte
(`validarBalanceDomingos`) pero **no bloquea**.

### Modalidad ENTRE SEMANA (temporada)

Cuatro sub-modalidades, todas con dos reglas duras comunes (`_validar_semana_comun`): días
**lunes a viernes**, futuros (hoy no vale al crear, porque ya se está trabajando) y **de la MISMA
semana** — un día de temporada modificado se compensa dentro de su propia semana, nunca en otra.

| Sub-modalidad | Qué hace | Deuda |
|---|---|---|
| `intercambio_dia` | Intercambio directo de descansos: yo descanso tu día y tú el mío | No |
| `jornadas_partidas` | Los dos días especiales se reparten por jornada: yo trabajo siempre AM y tú siempre PM (o al revés) | No |
| `cobertura_misma_semana` | Un compañero me cubre **AM o PM** de mi día completo de temporada, y le devuelvo esa jornada otro día de la misma semana | 30 min solo si quien cubre **ya tenía jornada** ese día y acabó doblado |
| `cambio_doblada` | El compañero tiene una doblada real ese día y yo mi día completo de temporada: se intercambian | No |

En `cobertura_misma_semana` **no se puede ceder el día completo a UNA sola persona** —eso es
"intercambiar el día"—; el día entero solo se reparte entre **dos** compañeros (una solicitud por
jornada).

### Reglas al aprobar y aplicar

| Efecto | Detalle |
|---|---|
| Finde | Cada uno pasa a trabajar el día del otro, ambos findes. Nadie dobla. |
| Entre semana | Depende de la sub-modalidad; solo `cobertura_misma_semana` puede dejar a alguien doblado (y ahí nacen los 30 min). |
| Reemplazo | Si un día ya cedido se vuelve a ceder a un tercero, la solicitud anterior pasa a `reemplazada` (`_marcar_reemplazadas`, **solo fin de semana**). |
| Snapshot | Se captura antes de mutar; al aprobarse la cancelación (acuerdo de dos pasos, 24 h por plazo) se restaura y se reconcilia. |

### Casos especiales

| Caso | Comportamiento |
|---|---|
| Día ya comprometido | En temporada no se reemplaza la solicitud previa: la **validación impide crear** la nueva mientras el día siga comprometido (`dia_comprometido_por_solicitud`). |
| Reintercambio del mismo día | `dia_bloqueado_para_nuevo_cambio` bloquea la fecha **solo** si hay un turno con `tipo_cambio` distinto de `CAMBIO DESCANSO` (DOBLADA, D FDS, CT…), y ese bloqueo es permanente. Un CAMBIO DESCANSO previo **no** bloquea: el día vuelve a estar disponible desde el primer minuto. El antiguo bloqueo de 30 min se retiró — ver [ADR 010](../../03-arquitectura/adr/010-dia-de-descanso-libre-tras-el-intercambio.md). |
| Permisos de temporada | Un permiso de media jornada de temporada consume el día de descanso; el formulario lo explica en vez de mostrar un error genérico. |

### Pendientes / posibles mejoras

- El descanso por intercambio no guarda `solicitud_id` en `DescansoPorSolicitudService`, así que
  los mensajes que lo citan no pueden enlazar a la solicitud que lo originó.

---

## 7. Cancelar y eliminar desde gestión

El supervisor cancela desde la pantalla de gestión. **No tiene la ventana de 30 minutos** —esa
limita al explorador— pero sí las guardas que protegen los datos. La lógica vive en
`CancelarSolicitudUseCase.execute_supervisor`; la vista solo muestra el resultado.

| Situación | Qué hace |
|---|---|
| **Pendiente** | Cancela. No hay nada aplicado que deshacer. |
| **Aprobada, ningún día ha pasado** | Revierte turnos y deudas, reconcilia lo que siga vigente, y cancela. |
| **Aprobada, todos los días ya pasaron** | Cancela **sin revertir**: la gente ya trabajó esos días y borrar sus turnos sería reescribir el historial. |
| **Aprobada, cumplida a medias** | **Bloquea.** Revertir borraría lo ya trabajado y no revertir dejaría el horario descuadrado. El mensaje nombra los días cumplidos y los pendientes, y remite a "Reprogramar" en las dobladas. |

Además se aplican dos guardias, ambas compartidas con la cancelación del explorador:

**1. Guardia LIFO** (`bloqueo_lifo`). Si hay un cambio aprobado más reciente sobre alguno de esos
días, revertir este pisaría aquel, así que se deshace en orden inverso.

**2. Guardia de integridad** (`bloqueo_integridad`). Revertir restaura el turno de *antes*, y eso
solo es correcto si **nadie tocó esos días** desde la aprobación. La guardia LIFO no basta: solo
mira otras solicitudes, así que no ve los permisos especiales, ni las reprogramaciones, ni los
ajustes manuales.

El caso típico: A y B hacen un cambio de turno; antes de que A cancele, **B cambia su turno por
otra vía**. Si A cancelara, se le escribiría a B el turno viejo —que ya no tiene— y quedarían dos
jornadas en conflicto. Por eso se compara el estado actual contra `snapshot_turnos_resultantes`
(lo que la solicitud dejó) y, si no coincide, **se bloquea**.

> **No se puede forzar** — tampoco desde gestión: forzar reintroduce exactamente el conflicto que
> se evita. La solicitud **sigue aprobada y vigente**, y la salida es que el explorador **solicite
> un cambio de turno nuevo** con alguien que le devuelva la jornada que quiere. El mensaje nombra
> a la persona y los días en conflicto, y lo dice.

Las solicitudes anteriores a este mecanismo no tienen estado resultante guardado: en ese caso la
guardia **no bloquea** (se queda con las guardias antiguas) y deja un aviso en el log. Bloquear
ahí las volvería incancelables en bloque.

**Eliminar** hace lo mismo antes de borrar la fila: revierte con idénticas guardas y solo
entonces elimina. Sin eso, borrar una solicitud aplicada dejaba los turnos puestos y sin ningún
registro que explicara de dónde salían.

---

## 8. Validadores reutilizables (SolicitudValidator)

Todos los tipos de solicitud comparten el mismo archivo de validadores. Los métodos relevantes y su reutilización:

| Método | Usado por |
|---|---|
| `validar_empleado_activo` | CT, Doblada, CT Permanente, D-FDS |
| `validar_no_mismo_empleado` | CT, Doblada, CT Permanente |
| `validar_comentario_obligatorio` | CT, Doblada, CT Permanente, D-FDS |
| `validar_jornada_en_fecha` | CT (indirectamente), D-FDS |
| `validar_duplicada_misma_fecha` | CT |
| `validar_receptor_sin_solicitud_pendiente_en_fecha` | CT (Caso C), Doblada (Caso C) |
| `validar_solicitante_sin_solicitud_pendiente_en_fecha` | CT (Caso C), Doblada (Caso D) |
| `validar_solicitante_sin_solicitud_pendiente_en_fechas` | CT Permanente (todos los días candidatos) |
| `validar_sin_pendiente_en_fechas` | D-FDS, Doblada Permanente. Cruza VARIAS fechas y mira las DOS fechas de las otras solicitudes (su cesión **y** su pago); sirve para solicitante y para compañero (`es_receptor`) |
| `validar_jornada_contraria` | CT |
| `validar_jornadas_contrarias_doblada` | Doblada |
| `validar_no_dia_mantenimiento` | CT, Doblada, CT Permanente, D-FDS |
| `validar_no_domingo_por_semana` | CT, Doblada |
| `validar_no_sabado_ct_sencillo` | CT (exclusivo) |
| `validar_no_doblada_activa` | CT, Doblada, D-FDS |
| `validar_fechas_cambio_permanente` | CT Permanente |
| `validar_jornada_contraria_rango_permanente` | CT Permanente |
| `validar_rango_completo_cambio_permanente` | CT Permanente |
| `validar_no_cambio_permanente_superpuesto` | CT Permanente |
| `validar_dias_seleccionados_permanente` | CT Permanente |
| `validar_acuerdo_previo_obligatorio` | Doblada |
| `validar_fecha_pago_diferente_cesion` | Doblada |
| `validar_fecha_pago_mismo_mes_cesion` | Doblada |
| `validar_receptor_no_descansa_por_doblada_en_pago` | Doblada (Caso F) |
| `validar_coincidencia_jornadas_pago` | Doblada |
| `validar_dias_especiales_doblada` | Doblada |
| `validar_no_triple_turno` | Doblada |
| `validar_festivos_mismo_mes` | Doblada |
| `validar_no_temporada` | CT Permanente |
| `es_festivo_semana` | CT (informativo), Doblada |
| `es_dia_temporada` | Notificaciones (aviso supervisor) |

---

## 9. Convenciones de nomenclatura de casos

Los casos implementados siguiendo el esquema Caso A, B, C... corresponden a:

| Caso | Descripción | Tipos afectados |
|---|---|---|
| **Caso A** | Validación de mes: fecha_pago/fecha_cesion en el mismo mes | Doblada; CT: fecha a partir de mañana |
| **Caso C** | Receptor sin solicitud pendiente para esa fecha | CT Sencillo, Doblada |
| **Caso D** | Solicitante sin solicitud pendiente para esa fecha | CT Sencillo (integrado en Caso C), Doblada |
| **Caso E** | Aviso de temporada al supervisor en la notificación | CT Sencillo, Doblada (implementado en `notificacion_service.py`) |
| **Caso F** | Receptor no puede descansar por doblada en fecha de pago | Doblada |
| **Caso G** | Ventana de cancelación de 30 min para dobladas aprobadas | Doblada |

---

*Cualquier nueva regla de negocio implementada debe registrarse en este documento antes o inmediatamente después de su implementación.*
