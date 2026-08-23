# Servicios de Solicitudes

Capa de lógica de negocio de la app `solicitudes`. Las vistas (`solicitudes/views/`) no
contienen reglas: parsean el request, llaman a un servicio o caso de uso y devuelven JSON.

> **Auditado contra el código el 2026-08-23.** Si añades o quitas un módulo, actualiza
> también la tabla de abajo: es el índice que se consulta antes de tocar esta carpeta.

## Dónde encaja esta carpeta

```
views/            → HTTP: parseo del POST y respuesta
use_cases/        → crear / aprobar / cancelar (entrada de alto nivel)
services/         → ESTA CARPETA: reglas de negocio y aplicación de turnos
  strategies/     → una clase por tipo de solicitud (validar + aplicar)
  validators/     → validaciones por dominio, reutilizadas por las strategies
repositories/     → consultas encapsuladas (SolicitudRepository, TurnoRepository)
domain/           → máquina de estados de la solicitud
```

Flujo de creación:

```
views/…  →  use_cases/crear_solicitud.py
             → SolicitudRequestParser   (normaliza el POST)
             → SolicitudOrchestrator    (sanción, restricción médica, transacción)
               → SolicitudFactory       (elige la strategy por tipo)
                 → strategies/*         (valida y crea)
```

Flujo de aprobación: `views/aprobacion_email.py` o las vistas de listado →
`SolicitudAprobacionService` → `bloquear_partes()` → strategy / servicio de aplicación
correspondiente → deudas → `NotificacionService` + `EmailOutboxService`.

## Módulos

### Entrada y orquestación

| Módulo | Qué hace |
|---|---|
| `solicitud_request_parser.py` | Normaliza y valida la forma del POST antes de tocar negocio. |
| `solicitud_orchestrator.py` | Orquesta la creación completa (sanción → restricción médica → parseo → validación → creación) dentro de una transacción. `_CreacionAbortada` existe porque un `return` dentro de `atomic()` no deshace lo ya creado. |
| `solicitud_factory.py` | Factory que resuelve el tipo de solicitud a su strategy (por `codigo_estrategia`, por normalización del nombre, por registro dinámico, o fallback). |
| `solicitud_service.py` | Creación core de `SolicitudCambio` y cancelación automática de solicitudes previas de la misma fecha. **Es una fachada delgada**: casi todo lo demás se movió a los servicios específicos (ver su docstring). |
| `solicitud_context_service.py` | Contexto para las plantillas de solicitudes. |

### Consulta y disponibilidad

| Módulo | Qué hace |
|---|---|
| `solicitud_consulta_service.py` | Consultar y filtrar solicitudes (usuario, pendientes, por receptor/supervisor). |
| `empleado_disponibilidad_service.py` | Buscar y filtrar empleados disponibles para una fecha/jornada. |
| `doblada_filtro_service.py` | Filtros de negocio específicos de dobladas sobre los empleados candidatos. |
| `fechas_helper.py` | `analizar_fecha_solicitud()` / `obtener_informacion_fecha_para_detalle()`. |

### Aprobación y aplicación de turnos

| Módulo | Qué hace |
|---|---|
| `solicitud_aprobacion_service.py` | Aprobar/rechazar por supervisor y por receptor; punto único de re-validación al aprobar. |
| `bloqueo_partes.py` | `bloquear_partes(solicitud)`: bloqueo de fila de las dos partes para que la lectura del estado y la escritura de turnos no se pisen entre solicitudes concurrentes. |
| `doblada_aplicacion_service.py` | Aplica una doblada aprobada (turnos + deudas). Delega el caso de pago en `doblada_pago_service`. |
| `doblada_pago_service.py` | El caso más complejo: la doblada en la fecha de **pago** (reparto de sábado, cobertura AM/PM/AMBAS, cesión parcial, pago residual en semana). |
| `doblada_permanente_aplicacion_service.py` | Doblada permanente: recorre el rango y aplica cesión/devolución por ocurrencia válida. |
| `d_fds_aplicacion_service.py` | Doblada de fin de semana (D FDS). |
| `cambio_descanso_aplicacion_service.py` | Cambio de día de descanso (fin de semana y entre semana), incluidos `revertir()` y el marcado de reemplazos. |
| `doblada_snapshot_service.py` | Captura/restaura el estado de turnos antes y después de una doblada, y reconcilia las vigentes tras una cancelación. |
| `reprogramacion_doblada_service.py` | Una de las partes no puede cumplir **su** día de una doblada ya aprobada: anula ese día y ajusta su deuda, sin afectar a la otra parte. |
| `descanso_solicitud_service.py` | Fuente **única** de "qué día descansa este empleado por una solicitud aprobada, y con quién". Antes estaba reimplementado en 3-4 sitios que divergían. |
| `ct_permanente_helper.py` | Cálculo de fechas aplicables/excluidas de los cambios permanentes, reutilizable fuera de la strategy. |
| `cierre_solicitudes_service.py` | Cierre semanal: a partir del día/hora de cierre no se admiten solicitudes nuevas cuyo objetivo caiga en la ventana cerrada. |

### Deudas

| Módulo | Qué hace |
|---|---|
| `deuda_service.py` | Deudas **entre exploradores** generadas por dobladas. |
| `deuda_corporativa_service.py` | Deudas **corporativas** acumuladas al doblar. |
| `doblada_deuda_service.py` | Genera ambas deudas al aprobarse una doblada. No toca turnos. |

### Notificación y correo

| Módulo | Qué hace |
|---|---|
| `notificacion_service.py` | Notificaciones in-app de todo el ciclo de la solicitud. |
| `email_service.py` | Composición y envío de los correos de solicitudes. |
| `email_outbox_service.py` | Patrón *outbox*: encolar es transaccional, enviar es reintentable y va fuera de la transacción. Lo consume el comando `procesar_email_outbox` (cron obligatorio en producción). |
| `tokens_aprobacion.py` | Tokens firmados de los enlaces de aprobar/rechazar por correo (`generar`/`verificar`, y su variante `_permiso`). |

### Strategies (`strategies/`)

Una clase por tipo de solicitud, todas derivadas de `SolicitudStrategy`
(`base_strategy.py`) y exportadas en `strategies/__init__.py`:

| Strategy | Tipo |
|---|---|
| `CambioTurnoStrategy` | Cambio de turno sencillo |
| `DobladaStrategy` | Doblada |
| `DobladaPermanenteStrategy` | Doblada permanente |
| `DFDSStrategy` | Doblada de fin de semana |
| `CTPermanenteStrategy` | Cambio de turno permanente |
| `CambioDescansoStrategy` | Cambio de día de descanso |

La strategy es responsable de **validar** la solicitud y de **aplicarla** al aprobarse.
No se instancian a mano: se piden a `SolicitudFactory`.

### Validadores (`validators/`)

`BaseValidator`, `CTValidator`, `CTPermanenteValidator` y `DobladaValidator`.
`solicitud_validator.py` (módulo hermano) es solo una **fachada de compatibilidad** que
los combina para los callers antiguos: en código nuevo importa el validador concreto.

### Errores

`errores_validacion.py` define errores que **llevan datos**, no solo texto —
p. ej. `RequiereCambioTurnoPrevio`, que el frontend usa para ofrecer el paso que falta.

### `steps/`

Paquete **vacío** (solo el `__init__.py`). No lo importa nadie; se conserva como sitio
previsto para descomponer el orquestador en pasos. No añadas nada ahí sin cablearlo.

## Convenciones

- Los servicios exponen `@staticmethod` (o funciones de módulo en los helpers: `bloqueo_partes`,
  `fechas_helper`, `ct_permanente_helper`, `tokens_aprobacion`).
- Devuelven `(objeto, mensaje)` o `(bool, mensaje)`; los mensajes son los que ve el usuario.
- Ningún servicio construye `HttpResponse` salvo `SolicitudOrchestrator`, que devuelve
  `JsonResponse` por ser el borde del flujo de creación.
- Todo lo que escriba turnos al aprobar pasa antes por `bloquear_partes()`.
- El detalle de un error 500 va al log, nunca a la respuesta.

## Uso

```python
from solicitudes.services.solicitud_consulta_service import SolicitudConsultaService
from solicitudes.services.solicitud_factory import SolicitudFactory

pendientes = SolicitudConsultaService.get_solicitudes_pendientes()
strategy = SolicitudFactory.get_strategy(tipo_solicitud)
```

## Ojo

- **`PermisoService` ya no vive aquí.** Los permisos son otra app: `permisos/services.py`
  y `permisos/pago_horas_service.py`.
- Las reglas de negocio con su cita en código están en
  [`docs/manual_tecnico.md`](../../docs/manual_tecnico.md) y en
  [`docs/05-referencia/solicitudes/`](../../docs/05-referencia/solicitudes/).
