# Reglas de Negocio y Casos Límite por Tipo de Solicitud

> **Documento vivo.** Actualizar siempre que se agregue, modifique o elimine una regla de negocio o validación.
> Última revisión: 2026-04-01 (cobertura explícita AM/PM/AMBAS en pago con receptor doblada)

---

## Índice

- [CT Sencillo — Cambio de Turno Sencillo](#1-ct-sencillo--cambio-de-turno-sencillo)
- [Doblada](#2-doblada)
- [CT Permanente](#3-ct-permanente)
- [D-FDS — Doblada Fin de Semana](#4-d-fds--doblada-fin-de-semana)
- [Validadores reutilizables (SolicitudValidator)](#5-validadores-reutilizables-solicitudvalidator)
- [Convenciones de nomenclatura de casos](#6-convenciones-de-nomenclatura-de-casos)

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
| 2 | **A** | La fecha no puede ser pasada | "No se puede solicitar un cambio de turno para una fecha pasada." | Backend |
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
| 18 | **B** | Límite de 3 cambios aprobados por explorador/fecha al CREAR | "No puedes crear esta solicitud. Ya tienes {N} cambio(s) aprobado(s) para el DD/MM/YYYY. Límite máximo: 3." | Backend |

### Reglas al aprobar — `aplicar_cambios()`

| Regla | Detalle |
|---|---|
| Límite de 3 cambios (segunda línea de defensa) | Cubre condiciones de carrera: si dos solicitudes se aprueban casi simultáneamente, la segunda falla con el mismo mensaje del Caso B. |
| First-Come, First-Served | Al aprobar una solicitud, rechaza automáticamente todas las demás solicitudes pendientes del mismo receptor para la misma fecha. Notifica a cada solicitante afectado. |

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
| Festivos | Permitidos en ambas fechas. Si una es festivo, la otra también debe serlo del mismo mes. |

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
| Validadores | `solicitudes/services/solicitud_validator.py` |
| Frontend | `static/js/cambio-turno/solicitar_ct_permanente.js` |
| Frontend validadores | `static/js/cambio-turno/validadores_solicitudes.js` |

### Reglas al crear — `validar_solicitud()`

| # | Caso | Regla | Mensaje de error | Capa |
|---|---|---|---|---|
| 1 | — | Datos requeridos: solicitante, receptor, fecha_inicio, fecha_fin (obligatoria) | "Faltan datos requeridos para la validación (fecha_fin es obligatoria)" | Backend |
| 2 | — | Solicitante y receptor activos | "El empleado no está activo" | Backend |
| 3 | — | No mismo empleado | "No puedes solicitar cambio contigo mismo" | Backend |
| 4 | — | Comentario obligatorio | "Debes ingresar un comentario para la solicitud de cambio de turno permanente." | Backend + Frontend |
| 5 | — | fecha_inicio no puede ser pasada | "La fecha de inicio no puede ser en el pasado" | Backend |
| 6 | — | fecha_fin obligatoria y posterior a fecha_inicio | "La fecha fin es obligatoria..." / "La fecha fin debe ser posterior a la fecha inicio" | Backend + Frontend |
| 7 | — | Solo lunes a viernes en el rango (no sábados ni domingos) | "No se pueden realizar cambios permanentes en sábados..." / "...en domingos" | Backend |
| 8 | — | No festivos en el rango | "No se pueden realizar cambios permanentes en días festivos" | Backend |
| 9 | — | No mantenimiento en el rango | "No se pueden realizar cambios de turno en días de mantenimiento. {descripcion}" | Backend |
| 10 | — | No temporada en el rango | "No se pueden realizar cambios permanentes en días de temporada. {descripcion}" | Backend |
| 11 | — | Al menos un día del rango con jornadas contrarias (AM ↔ PM) | "No se puede realizar el cambio permanente. No se encontraron días en el rango donde los empleados tengan jornadas contrarias..." | Backend |
| 12 | — | Al menos un día válido en el rango (excluidos: domingos, sábados, festivos, mantenimiento, temporada, descansos) | "No se encontraron días válidos en el rango seleccionado. Todos los días son festivos, de mantenimiento, temporada, o días de descanso." | Backend |
| 13 | — | Sin superposición con otros cambios permanentes entre los mismos empleados (en ambas direcciones) | "Ya existe un cambio permanente superpuesto entre estos empleados" | Backend |
| 14 | — | Si hay dias_seleccionados: al menos uno, todos dentro del rango, todos lunes-viernes | Mensajes específicos por sub-regla | Backend + Frontend |

### Reglas al aprobar

*(No hay validaciones especiales adicionales documentadas fuera de las de creación)*

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
| Selección de días completa vs fechas específicas | `dias_seleccionados` puede contener `dias_semana` (lunes a viernes como números 0-4) o `fechas_especificas` (listado de fechas puntuales) |
| Fechas específicas incompatibles | Si ninguna de las fechas específicas tiene jornadas contrarias con el compañero, se bloquea |

### Pendientes / posibles mejoras

*(Agregar aquí si se identifican nuevas reglas faltantes)*

---

## 4. D-FDS — Doblada Fin de Semana

> **Implementada** (reescrita). Antes era una auto-solicitud sin efecto al aprobar; ahora es una doblada entre dos exploradores en unidades de **día de finde completo** (no AM/PM).

### Concepto

En un fin de semana, según la **alternancia** (`AlternanciaFinesSemanaService`), **un grupo trabaja un día completo (AM+PM)** y el otro grupo trabaja el otro día. Cada explorador trabaja un solo día del finde.

- **Favor (fecha de cesión):** el solicitante trabaja SU día del finde pero no puede asistir y lo cede. El **receptor** (grupo contrario, trabaja el otro día) **se dobla** ese finde: trabaja su día propio + el día cedido. El solicitante **descansa todo el finde**.
- **Pago (fecha de pago, mismo mes):** espejo. El solicitante cubre el día del receptor en otro finde del mismo mes: trabaja su día propio + el día del receptor. El receptor **descansa su día**.

Unidad transferida = un día de finde completo. No hay medias jornadas, ni matriz de casos AM/PM.

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

| # | Regla | Mensaje de error | Capa |
|---|---|---|---|
| 1 | Requeridos: solicitante, receptor, fecha de cesión, fecha de pago | Mensajes específicos por campo faltante | Backend + Frontend |
| 2 | Solicitante y receptor activos | "El empleado no está activo" | Backend |
| 3 | No mismo empleado | "No puedes solicitar cambio contigo mismo" | Backend |
| 4 | Comentario obligatorio | "Debes ingresar un comentario para la solicitud de D FDS." | Backend + Frontend |
| 5 | Cesión y pago deben ser fin de semana (sáb/dom) | "La fecha de cesión/pago debe ser un fin de semana (sábado o domingo)" | Backend + Frontend |
| 6 | Cesión no pasada; pago posterior a hoy; pago ≠ cesión | Mensajes específicos | Backend + Frontend |
| 7 | Pago en el **mismo mes** que la cesión | "La fecha de pago (...) debe estar en el mismo mes que la fecha de cesión (...)" | Backend + Frontend |
| 8 | No mantenimiento en ninguna fecha | "No se pueden realizar cambios... en días de mantenimiento" | Backend |
| 9 | Solicitante y receptor de **grupos contrarios** | "El compañero debe ser del grupo contrario..." | Backend |
| 10 | Al solicitante le corresponde trabajar SU día en la cesión (alternancia) | "Ese día no te corresponde trabajar por alternancia; no tienes un día que ceder..." | Backend |
| 11 | El día de pago debe ser el que trabaja el **receptor** (alternancia) | "En la fecha de pago debes cubrir el día que trabaja tu compañero (grupo X)..." | Backend |
| 12 | No triple turno: receptor sin doblada en cesión; solicitante sin doblada en pago | "El compañero ya tiene una doblada (AM+PM) en la fecha de cesión..." | Backend |

### Reglas al aprobar — `aplicar_cambios()` → `DFDSAplicacionService`

| Efecto | Detalle |
|---|---|
| Cesión | Receptor dobla AM+PM en la fecha de cesión; solicitante sin turnos (descansa el finde). |
| Pago | Solicitante dobla AM+PM en la fecha de pago; receptor sin turnos (descansa su día). |
| Deuda entre exploradores | `DeudaExplorador`: solicitante (deudor) → receptor (acreedor), saldada con la fecha de pago. |
| Deuda corporativa | **30 min por cada día con doblada efectiva AM+PM**: receptor en la cesión, solicitante en el pago. |
| Snapshot | Se captura snapshot de turnos previos (reutiliza el de doblada) para permitir reversión. |

### Display en Mis Turnos

La vista `turnos/api/views.py` incluye `D FDS` junto con `DOBLADA` en las consultas de descanso: el solicitante ve "descanso (cedió)" en la cesión y el receptor ve "descanso (pago)" en la fecha de pago.

### Validaciones frontend

| Validación | Detalle |
|---|---|
| Date pickers solo findes | `flatpickr` con `disable` de días entre semana en cesión y pago (`solicitar_d_fds.js`) |
| Pago restringido al mismo mes | El picker de pago se limita a `[primer..último día]` del mes de la cesión y excluye la fecha de cesión |
| Compañeros del grupo contrario | Se cargan vía `obtener-empleados-disponibles` (`DFDSStrategy.get_empleados_disponibles`) |
| Campos requeridos + comentario | Validación previa al POST con SweetAlert |

### Pendientes / posibles mejoras

- Ventana de cancelación de 30 min (existe snapshot; falta exponer el botón/flujo para D FDS).
- Mensaje de éxito compartido en `procesar_solicitud.py` tiene un mojibake heredado ("compañero").

---

## 5. Validadores reutilizables (SolicitudValidator)

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

## 6. Convenciones de nomenclatura de casos

Los casos implementados siguiendo el esquema Caso A, B, C... corresponden a:

| Caso | Descripción | Tipos afectados |
|---|---|---|
| **Caso A** | Validación de mes: fecha_pago/fecha_cesion en el mismo mes | Doblada; CT: fecha no pasada |
| **Caso B** | Límite de 3 cambios aprobados por explorador/fecha | CT Sencillo |
| **Caso C** | Receptor sin solicitud pendiente para esa fecha | CT Sencillo, Doblada |
| **Caso D** | Solicitante sin solicitud pendiente para esa fecha | CT Sencillo (integrado en Caso C), Doblada |
| **Caso E** | Aviso de temporada al supervisor en la notificación | CT Sencillo, Doblada (implementado en `notificacion_service.py`) |
| **Caso F** | Receptor no puede descansar por doblada en fecha de pago | Doblada |
| **Caso G** | Ventana de cancelación de 30 min para dobladas aprobadas | Doblada |

---

*Cualquier nueva regla de negocio implementada debe registrarse en este documento antes o inmediatamente después de su implementación.*
