# Diagrama de flujo completo – Solicitud Doblada

Documento de referencia con todos los casos del flujo de solicitud doblada (creación, validaciones, aprobación, rechazo, cancelación y aplicación) para revisar fallos o verificar que el comportamiento sea el esperado.

**Archivos principales:** `solicitudes/views.py`, `solicitudes/services/strategies/doblada_strategy.py`, `solicitudes/services/solicitud_validator.py`, `solicitudes/services/solicitud_aprobacion_service.py`, `solicitudes/services/doblada_aplicacion_service.py`, `static/js/cambio-turno/solicitar_doblada.js`.

---

## 1. Diagrama de flujo principal (creación)

Desde que el usuario abre el formulario hasta que la solicitud queda creada en estado `pendiente` o se devuelve un error con código/mensaje. Incluye la rama de **cesión total** (2 solicitudes AM y PM) y la de **cesión parcial/completa normal** (1 solicitud).

```mermaid
flowchart TD
    Inicio[Usuario abre formulario doblada]
    Inicio --> SeleccionaCesion[Selecciona tipo cesión y datos]
    SeleccionaCesion --> EsCesionTotal{Es cesión total?}
    
    EsCesionTotal -->|Sí| ValidaCamposTotal[Backend: validar receptor AM, PM, fecha_pago_am, fecha_pago_pm]
    ValidaCamposTotal --> ValidarAM[SolicitudFactory.validar_solicitud datos AM]
    ValidarAM --> ValAMOk{AM válida?}
    ValAMOk -->|No| ErrorAM[Error: code/mensaje AM]
    ErrorAM --> RespuestaError[Respuesta 400 con code y mensaje]
    ValAMOk -->|Sí| ValidarPM[SolicitudFactory.validar_solicitud datos PM]
    ValidarPM --> ValPMOk{PM válida?}
    ValPMOk -->|No| ErrorPM[Error: code/mensaje PM]
    ErrorPM --> RespuestaError
    ValPMOk -->|Sí| CrearDos[Crear 2 solicitudes AM y PM]
    CrearDos --> NotifDos[Notificaciones para cada una]
    NotifDos --> SuccessDos[Solicitud creada - 2 registros]
    
    EsCesionTotal -->|No| ValidaCamposNormal[Backend: validar empleado_receptor, fecha_pago]
    ValidaCamposNormal --> ValidarUna[SolicitudFactory.validar_solicitud datos]
    ValidarUna --> ValidaBackend[DobladaStrategy.validar_solicitud]
    
    ValidaBackend --> V1[explorador_solicitante existe?]
    V1 -->|No| E1[Error: Explorador solicitante requerido]
    V1 -->|Sí| V2[explorador_receptor existe?]
    V2 -->|No| E2[Error: Explorador receptor requerido]
    V2 -->|Sí| V3[fecha_cesion existe?]
    V3 -->|No| E3[Error: Fecha cesión requerida]
    V3 -->|Sí| V4[fecha_pago existe?]
    V4 -->|No| E4[Error: Fecha pago obligatoria]
    V4 -->|Sí| V5[fecha_cesion no pasado?]
    V5 -->|No| E5[Error: Fecha cesión no puede ser pasado]
    V5 -->|Sí| V6[validar_empleado_activo ambos]
    V6 -->|Falla| E6[Error: Empleado no activo]
    V6 -->|Ok| V7[validar_no_mismo_empleado]
    V7 -->|Falla| E7[Error: No mismo empleado]
    V7 -->|Ok| V8[validar_acuerdo_previo_obligatorio]
    V8 -->|Falla| E8[Error: Fecha pago debe ser posterior a creación]
    V8 -->|Ok| V9[validar_dias_especiales_doblada fecha_cesion]
    V9 -->|Falla| E9[Error: Domingo/festivo/mantenimiento cesión]
    V9 -->|Ok| V10[validar_dias_especiales_doblada fecha_pago]
    V10 -->|Falla| E10[Error: Domingo/festivo/mantenimiento pago]
    V10 -->|Ok| V11{Pago sábado y jornada_pago_sabado?}
    V11 -->|Sí| V11a[Alternancia y jornada receptor válida]
    V11a -->|Falla| E11a[Error: Sábado inválido o receptor no trabaja]
    V11a -->|Ok| V12
    V11 -->|No| V12[validar_jornadas_contrarias_doblada]
    V12 -->|Falla| E12[Error: Jornadas no contrarias]
    V12 -->|Ok| V13[validar_no_triple_turno receptor fecha_cesion]
    V13 -->|Falla| E13[Error: Receptor ya doblada cesión]
    V13 -->|Ok| V14{Es pago sábado?}
    V14 -->|No| V15[validar_no_triple_turno receptor fecha_pago]
    V14 -->|Sí| V16
    V15 -->|Falla| E15[Error: Receptor ya doblada pago]
    V15 -->|Ok| V16[validar_no_doblada_activa solicitante fecha_pago]
    V16 -->|Falla| E16[Error: Solicitante ya doblada en fecha pago]
    V16 -->|Ok| V17[validar_coincidencia_jornadas_pago]
    V17 -->|requiere_cambio_turno| E17[code: requiere_cambio_turno_previo]
    V17 -->|Ok| CrearUna[DobladaStrategy.crear_solicitud]
    
    E1 --> RespuestaError
    E2 --> RespuestaError
    E3 --> RespuestaError
    E4 --> RespuestaError
    E5 --> RespuestaError
    E6 --> RespuestaError
    E7 --> RespuestaError
    E8 --> RespuestaError
    E9 --> RespuestaError
    E10 --> RespuestaError
    E11a --> RespuestaError
    E12 --> RespuestaError
    E13 --> RespuestaError
    E15 --> RespuestaError
    E16 --> RespuestaError
    E17 --> RespuestaError
    
    CrearUna --> CrearSC[SolicitudCambio.create]
    CrearSC --> CrearDD[DobladaDetalle.create]
    CrearDD --> NotifUna[NotificacionService.crear_notificacion_solicitud]
    NotifUna --> SuccessUna[Solicitud creada - estado pendiente]
```

---

## 2. Diagrama de estados de la solicitud

Estados posibles y transiciones al aprobar, rechazar o cancelar.

```mermaid
stateDiagram-v2
    [*] --> pendiente: Creación solicitud
    
    pendiente --> aprobada: Receptor Y Supervisor aprueban
    pendiente --> rechazada: Receptor rechaza
    pendiente --> rechazada: Supervisor rechaza
    pendiente --> cancelada: Solicitante cancela
    
    aprobada --> [*]: Final
    rechazada --> [*]: Final
    cancelada --> [*]: Final
    
    note right of pendiente: aprobado_receptor = False\naprobado_supervisor = False
    note right of aprobada: aplicar_cambios ejecutado\nTurnos y deudas creados
```

**Condiciones al intentar aprobar o rechazar de nuevo:**

| Estado actual   | Acción intentada | Resultado |
|-----------------|-------------------|-----------|
| `pendiente`    | Aprobar/Rechazar  | Se procesa (receptor o supervisor según identidad). |
| `aprobada`     | Aprobar/Rechazar  | Mensaje: "Esta solicitud ya fue aprobada". |
| `rechazada`    | Aprobar/Rechazar  | Mensaje: "Esta solicitud ya fue rechazada". |
| `cancelada`    | Aprobar/Rechazar  | Mensaje: "Esta solicitud fue cancelada y ya no puede ser aprobada/rechazada". |

---

## 3. Diagrama de flujo de aprobación y rechazo

Flujo para receptor y supervisor (desde app o desde email). Incluye comprobación de identidad, estado pendiente y, al aprobar, aplicación de cambios cuando ambos han aprobado.

```mermaid
flowchart TD
    Entrada[Usuario hace clic Aprobar o Rechazar]
    Entrada --> Origen{Origen: App o Email?}
    Origen --> App[Vista App: AprobarSolicitudView / AprobarSolicitudReceptorView]
    Origen --> Email[Vista Email: token en URL]
    App --> ObtenerSolicitud[Obtener solicitud por ID]
    Email --> ValidarToken[Validar token]
    ValidarToken --> ObtenerSolicitud
    
    ObtenerSolicitud --> Rol{Quién aprueba/rechaza?}
    Rol --> Receptor[Receptor]
    Rol --> Supervisor[Supervisor]
    Rol --> Ambos[Supervisor = Receptor - AprobarSolicitudAmbosView]
    
    Receptor --> CheckReceptor[¿Usuario = explorador_receptor?]
    CheckReceptor -->|No| ErrPermiso[403: No tienes permisos]
    CheckReceptor -->|Sí| CheckEstado
    Supervisor --> CheckSupervisor[¿Usuario = supervisor del solicitante?]
    CheckSupervisor -->|No| ErrPermiso
    CheckSupervisor -->|Sí| CheckEstado
    
    Ambos --> CheckAmbos[¿Usuario = receptor Y supervisor?]
    CheckAmbos -->|No| ErrPermiso
    CheckAmbos -->|Sí| AprobarReceptorPrimero[Si no aprobado_receptor: aprobar como receptor]
    AprobarReceptorPrimero --> AprobarSupervisorDespues[Si no aprobado_supervisor: aprobar como supervisor]
    AprobarSupervisorDespues --> CheckEstado
    
    CheckEstado{estado == pendiente?}
    CheckEstado -->|No| MsgEstado[Según estado: ya aprobada, ya rechazada, cancelada]
    CheckEstado -->|Sí| Accion{Acción?}
    
    Accion --> Aprobar[Aprobar]
    Accion --> Rechazar[Rechazar]
    
    Aprobar --> MarcarFlag[Marcar aprobado_receptor o aprobado_supervisor]
    MarcarFlag --> OtroYaAprobo{El otro ya aprobó?}
    OtroYaAprobo -->|No| GuardarParcial[Guardar solicitud]
    GuardarParcial --> NotifAprobacion[Notificación aprobación parcial]
    OtroYaAprobo -->|Sí| EstadoAprobada[estado = aprobada, fecha_resolucion]
    EstadoAprobada --> GuardarAprobada[Guardar]
    GuardarAprobada --> AplicarCambios[SolicitudFactory.aplicar_cambios]
    AplicarCambios --> DobladaAplicacion[DobladaStrategy.aplicar_cambios: cesión, pago, deudas]
    DobladaAplicacion --> LimpiarCache[Limpiar caché turnos]
    LimpiarCache --> NotifAprobacion
    NotifAprobacion --> InvalidarCacheContadores[Invalidar caché contadores]
    InvalidarCacheContadores --> OkAprobacion[200: Solicitud aprobada]
    
    Rechazar --> EstadoRechazada[estado = rechazada, fecha_resolucion]
    EstadoRechazada --> GuardarRechazo[Guardar]
    GuardarRechazo --> NotifRechazo[NotificacionService.crear_notificacion_rechazo_*]
    NotifRechazo --> InvalidarCacheContadoresR[Invalidar caché contadores]
    InvalidarCacheContadoresR --> OkRechazo[200: Solicitud rechazada]
    
    MsgEstado --> RespuestaErrorEstado[400 con mensaje]
```

---

## 4. Diagrama de aplicación de la doblada (al aprobar)

Cuando la solicitud pasa a `aprobada`, se ejecuta `DobladaStrategy.aplicar_cambios`, que delega en `DobladaAplicacionService`.

```mermaid
flowchart TD
    AplicarCambios[DobladaStrategy.aplicar_cambios]
    AplicarCambios --> Transaccion[transaction.atomic]
    Transaccion --> Cesion[DobladaAplicacionService.aplicar_doblada_cesion]
    Cesion --> CesionDetalle[Receptor dobla en fecha_cesion]
    CesionDetalle --> CesionSolicitante{Solicitante: cesión completa o parcial?}
    CesionSolicitante -->|Completa| QuitarTodos[Eliminar todos los turnos solicitante fecha_cesion]
    CesionSolicitante -->|Parcial AM| QuitarAM[Eliminar solo turno AM solicitante]
    CesionSolicitante -->|Parcial PM| QuitarPM[Eliminar solo turno PM solicitante]
    QuitarTodos --> ValidarCesion[validar_turnos_doblada_cesion]
    QuitarAM --> ValidarCesion
    QuitarPM --> ValidarCesion
    
    ValidarCesion --> Pago[DobladaAplicacionService.aplicar_doblada_pago]
    Pago --> EsSabado{fecha_pago es sábado y jornada_pago_sabado?}
    EsSabado -->|Sí| SabadoLogic[Solicitante: solo jornada elegida. Receptor: solo jornada contraria]
    EsSabado -->|No| NormalLogic[Deudor dobla en fecha_pago. Acreedor descansa]
    SabadoLogic --> Deudas[generar_deudas_doblada]
    NormalLogic --> Deudas
    
    Deudas --> DeudaExplorador[DeudaService.crear_deuda estado pagada]
    Deudas --> DeudaCorpReceptor[DeudaCorporativaService receptor +30 min]
    Deudas --> DeudaCorpSolicitante[DeudaCorporativaService solicitante +30 min]
    DeudaExplorador --> FinTransaccion[Fin transacción]
    DeudaCorpReceptor --> FinTransaccion
    DeudaCorpSolicitante --> FinTransaccion
    
    FinTransaccion --> LimpiarCache[Limpiar caché turnos solicitante y receptor]
    LimpiarCache --> Retorno[return True mensaje]
```

---

## 5. Tabla de validaciones (salidas de error)

Para cada validación se indica la condición de fallo, el mensaje o código devuelto y la acción en frontend cuando aplica.

| Validación | Dónde | Condición de fallo | Mensaje/código devuelto | Acción en frontend |
|------------|--------|--------------------|--------------------------|--------------------|
| Campos requeridos (fecha_cesion, empleado_receptor, fecha_pago) | Backend `ProcesarSolicitudView` | Falta algún campo según tipo (normal vs cesión total) | `missing_fields`, mensaje específico | Swal / mensaje de error |
| Explorador solicitante requerido | `DobladaStrategy.validar_solicitud` | No se envía solicitante | "Explorador solicitante es requerido" | Error genérico |
| Explorador receptor requerido | Idem | No se envía receptor | "Explorador receptor es requerido" | Error genérico |
| Fecha cesión requerida | Idem | `fecha_cesion` vacía | "Fecha de cesión es requerida" | Error genérico |
| Fecha pago obligatoria | Idem | `fecha_pago` vacía | "Fecha de pago es obligatoria. No existen dobladas abiertas." | Error genérico |
| Fecha cesión en pasado | Idem | `fecha_cesion` < hoy | "La fecha de cesión (...) no puede ser en el pasado." | Error genérico |
| Empleado no activo | `validar_empleado_activo` | Solicitante o receptor no activo | "El empleado no está activo" | Error genérico |
| Mismo empleado | `validar_no_mismo_empleado` | Solicitante id = Receptor id | "No puedes solicitar cambio contigo mismo" | Error genérico |
| Acuerdo previo | `validar_acuerdo_previo_obligatorio` | `fecha_pago` <= fecha_creacion_solicitud | "La fecha de pago es obligatoria..." / ValidationError | Datepicker pago: mínimo hoy |
| Días especiales cesión | `validar_dias_especiales_doblada` | Domingo, festivo o mantenimiento en fecha_cesion | "No se puede realizar doblada en domingos" / festivo / mantenimiento | Datepicker cesión: deshabilitar esos días |
| Días especiales pago | Idem | Domingo, festivo o mantenimiento en fecha_pago | Idem | Datepicker pago: deshabilitar esos días |
| Pago sábado (jornada inválida) | `DobladaStrategy.validar_solicitud` | `jornada_pago_sabado` no AM/PM | "Para pagar en sábado debes seleccionar una jornada válida (AM o PM)." | Mostrar opciones AM/PM sábado |
| Pago sábado (alternancia) | Idem | No se determina alternancia sábado | "No se pudo determinar la alternancia para el sábado seleccionado." | Error genérico |
| Pago sábado (receptor sin jornada) | Idem | Receptor sin jornada en fecha_pago | "El receptor no tiene jornada asignada para la fecha de pago (sábado)." | Error genérico |
| Pago sábado (receptor grupo distinto) | Idem | Receptor no es del grupo que trabaja ese sábado | "Para pagar el sábado ..., el receptor debe ser del grupo ..." | Error genérico |
| Jornadas contrarias | `validar_jornadas_contrarias_doblada` | Solicitante y receptor misma jornada en fecha_cesion (o jornada_cedida no contraria) | ValidationError jornadas no contrarias | Filtro empleados disponibles por jornada contraria |
| No triple turno (receptor cesión) | `validar_no_triple_turno` | Receptor ya tiene doblada en fecha_cesion | ValidationError doblada activa | Excluir de lista disponibles |
| No triple turno (receptor pago) | Idem | Receptor ya tiene doblada en fecha_pago (excepto si pago sábado) | Idem | Excluir de lista disponibles |
| No doblada activa (solicitante pago) | `validar_no_doblada_activa` | Solicitante tiene doblada en fecha_pago | ValidationError | Mensaje / deshabilitar esa fecha pago |
| Coincidencia jornadas pago | `validar_coincidencia_jornadas_pago` | Deudor y acreedor misma jornada en fecha_pago | `code: requiere_cambio_turno_previo` + mensaje | Redirigir a CT sencillo con fecha_pago |
| Doblada existente (solicitante fecha pago) | Backend (mensaje contiene "ya tiene una doblada") | Solicitante con doblada en fecha de pago | `code: doblada_existente` | Swal + mensaje fecha conflicto |
| Usuario descansando en fecha cesión | Frontend / API turno | Solicitante sin turno en fecha_cesion | `esta_descansando` / no puede ceder | Deshabilitar envío o mostrar aviso |

---

## 6. Tabla de códigos de error y acción en frontend

Códigos que puede devolver el backend (o que el frontend interpreta) y cómo se comporta la interfaz.

| Código | Mensaje típico | Acción en frontend |
|--------|----------------|--------------------|
| `requiere_cambio_turno_previo` | "No se puede pagar trabajando dos veces la misma jornada. Debes primero realizar un cambio de turno sencillo para tener jornada contraria en la fecha de pago." | Swal con mensaje; botón para redirigir a `/solicitudes/cambio-turno/solicitar/?tipo_id=1&fecha_solicitud={fecha_pago}` |
| `doblada_existente` | "No se puede crear la solicitud porque ya tienes una doblada en la fecha de pago seleccionada." (+ `fecha_conflicto`, `jornada_afectada`) | Swal con mensaje y fecha/jornada afectada |
| `missing_fields` | Mensaje específico según campo (ej. "La fecha de pago es obligatoria...") | Swal / mensaje junto al formulario |
| `invalid_type` | "Tipo de solicitud no válido" | Error genérico |
| `forbidden` | "No tienes permisos para aprobar/rechazar esta solicitud" | Mensaje 403 |
| Estado no pendiente al aprobar/rechazar | "Esta solicitud ya fue aprobada/rechazada" o "fue cancelada" | Mensaje en vista de aprobación/rechazo o en email |
| Error al aplicar cambios | "Error aplicando cambios: {mensaje}" | Mensaje de error tras segunda aprobación |

---

## Referencia rápida de archivos

| Componente | Archivo |
|------------|--------|
| Formulario y submit | `templates/solicitudes/solicitar_doblada.html`, `static/js/cambio-turno/solicitar_doblada.js` |
| Procesar POST | `solicitudes/views.py` → `ProcesarSolicitudView.post` |
| Validar / crear doblada | `solicitudes/services/strategies/doblada_strategy.py` → `validar_solicitud`, `crear_solicitud` |
| Validaciones de negocio | `solicitudes/services/solicitud_validator.py` |
| Aprobar / rechazar | `solicitudes/services/solicitud_aprobacion_service.py` |
| Aplicar doblada (cesión, pago, deudas) | `solicitudes/services/doblada_aplicacion_service.py` |
| Notificaciones y emails | `solicitudes/services/notificacion_service.py` |

Documento generado según el plan de diagrama de flujo completo de la solicitud doblada.
