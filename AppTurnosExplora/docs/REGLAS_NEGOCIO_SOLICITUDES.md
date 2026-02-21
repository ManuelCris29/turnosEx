# Reglas de Negocio y Casos Límite por Tipo de Solicitud

> **Documento vivo.** Actualizar siempre que se agregue, modifique o elimine una regla de negocio o validación.
> Última revisión: 2026-02-12

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
| Detalles (modelo) | `solicitudes/models.py` → `DobladaDetalle` |
| Frontend | `static/js/cambio-turno/solicitar_doblada.js` |

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
| 18 | — | No triple turno: receptor sin doblada activa en fecha_pago — **excepción si es sábado** (el sistema divide en media jornada) | Redirige a Solicitud de Dobladas | Backend |
| 19 | — | Solicitante (deudor) sin doblada activa en fecha_pago | Redirige a Solicitud de Dobladas | Backend |
| 20 | — | Coincidencia de jornadas en fecha_pago: si deudor y acreedor tienen la misma jornada, requiere CT previo | "No se puede pagar trabajando dos veces la misma jornada. Debes primero realizar un cambio de turno sencillo..." | Backend |

### Reglas al aprobar — `aplicar_cambios()`

| Regla | Detalle |
|---|---|
| Ventana de cancelación de 30 minutos | Tras la aprobación, el solicitante puede cancelar la doblada dentro de los 30 minutos siguientes. El sistema elimina los turnos DOBLADA, restaura la jornada base de ambos empleados y cancela las deudas (DeudaExplorador y DeudaCorporativa). Pasada la ventana, ya no se puede cancelar. |
| Aviso de temporada al supervisor | Si fecha_cesion cae en temporada, la notificación al supervisor incluye un aviso visible para que evalúe antes de aprobar. |

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
| Estado "Descansando" si el solicitante cedió su jornada | Informativo (no bloquea envío, pero deshabilita form) |

### Casos especiales y excepciones

| Caso | Comportamiento |
|---|---|
| Cesión total | El solicitante cede AM y PM a dos compañeros distintos. Requiere receptor_am, receptor_pm, fecha_pago_am, fecha_pago_pm. |
| Cesión parcial | El solicitante tiene jornada predeterminada y cede solo la mitad. Un solo receptor y fecha de pago. |
| Solicitante con doblada existente | Si ya tiene doblada activa (AM+PM), usa `jornada_cedida` en lugar de la jornada predeterminada. |
| Triple turno en sábado de pago | Se permite que el receptor "tenga doblada" en fecha_pago si es sábado, porque el sistema la divide en media jornada. |
| Deudor con doblada (AM+PM) en fecha_pago | Puede pagar cualquier jornada de deuda porque ya trabaja las dos jornadas. |
| Temporada | Permitida para cesión. El supervisor recibe aviso en la notificación. |
| Festivos | Permitidos en ambas fechas. Si una es festivo, la otra también debe serlo del mismo mes. |

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

### Archivos clave

| Capa | Archivo |
|---|---|
| Strategy (backend) | `solicitudes/services/strategies/d_fds_strategy.py` |
| Validadores | `solicitudes/services/solicitud_validator.py` |

### Reglas al crear — `validar_solicitud()`

| # | Caso | Regla | Mensaje de error | Capa |
|---|---|---|---|---|
| 1 | — | Datos requeridos: solicitante, fecha, minutos_deuda (entero positivo) | "Explorador solicitante es requerido" / "Fecha es requerida" / "Minutos de deuda debe ser un número positivo" | Backend |
| 2 | — | Solicitante activo | "El empleado no está activo" | Backend |
| 3 | — | Comentario obligatorio | "Debes ingresar un comentario para la solicitud de D FDS." | Backend |
| 4 | — | La fecha debe ser sábado o domingo | "D FDS solo se puede solicitar para fines de semana (sábado o domingo)" | Backend + Frontend |
| 5 | — | No día de mantenimiento | "No se pueden realizar cambios de turno en días de mantenimiento. {descripcion}" | Backend |
| 6 | — | Solicitante con jornada asignada para esa fecha | "El empleado no tiene jornada asignada para esa fecha" | Backend |
| 7 | — | Solicitante sin doblada activa (AM+PM) para esa fecha | "No se puede realizar un Cambio de Turno Sencillo porque el explorador ya tiene una jornada doblada (AM + PM)..." | Backend |

### Validaciones frontend

| Validación | Detalle |
|---|---|
| Fecha debe ser sábado o domingo | Validación en `validadores_solicitudes.js` (`fecha_fin_de_semana`) |
| Fecha no puede ser pasada | Validación en `validadores_solicitudes.js` (`fecha_no_pasado`) |

### Casos especiales y excepciones

*(Ninguno documentado actualmente)*

### Pendientes / posibles mejoras

*(Agregar aquí si se identifican nuevas reglas faltantes)*

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
