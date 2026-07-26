# Manual del Desarrollador — AppTurnos / SWALP

Puerta de entrada técnica al proyecto. Explica qué es el sistema, cómo está construido,
qué patrones se aplicaron y por qué, y qué hay que saber antes de tocar nada.

Este documento **no reemplaza** la documentación existente en `docs/`: la ordena y la
enlaza. Cuando un tema ya está cubierto en profundidad, aquí se resume y se remite.

Toda regla de negocio afirmada lleva su origen entre paréntesis, en formato
`ruta/archivo.py:línea`, relativo a `AppTurnosExplora/`. La sección
[17. Por confirmar](#17-por-confirmar) recoge lo que no se pudo verificar.

---

## 1. Visión general técnica y stack

AppTurnos gestiona la programación de turnos de un equipo de **exploradores** y las
solicitudes con las que intercambian jornadas entre ellos. El núcleo del sistema no es
el calendario: es el **motor de solicitudes**, seis formularios que modifican turnos
propios y de terceros, generan deudas de jornada y requieren doble aprobación.

| Componente | Elección |
|---|---|
| Framework | Django 5.2.16 (sin Django REST Framework) |
| Lenguaje | Python 3.12 |
| Base de datos | MySQL (PyMySQL como respaldo del driver) |
| Frontend | AdminLTE 3.2 + JavaScript vanilla, **sin paso de build** |
| Historial de cambios | `django-simple-history` |
| Seguridad | `django-axes` (bloqueo por intentos), `django-csp`, `django-cors-headers` |
| Configuración | `django-environ` (ver [ADR 004](./03-arquitectura/adr/004-variables-de-entorno-django-environ.md)) |
| Estáticos | WhiteNoise |
| Servidor | Gunicorn |
| Exportación | openpyxl |

No hay API REST pública: los endpoints JSON existen para el propio frontend.

## 2. Estructura del repositorio

El detalle exhaustivo está en
[00-introduccion/ESTRUCTURA_PROYECTO.md](./00-introduccion/ESTRUCTURA_PROYECTO.md). Lo
mínimo para orientarse:

```
c:\appTurnos\                       raíz del repositorio
├── AppTurnosExplora\               ← raíz del proyecto Django (aquí está manage.py)
│   ├── config\                     settings.py, urls.py, wsgi.py, db.py, paths.py
│   ├── core\                       login, dashboard, utilidades compartidas
│   ├── empleados\                  personas, roles, salas, restricciones, sanciones
│   ├── turnos\                     turnos, jornadas, días especiales, descansos
│   ├── solicitudes\                el dominio central: los seis tipos de solicitud
│   ├── permisos\                   PDH y permisos especiales
│   ├── templates\                  plantillas HTML (incluye emails\)
│   ├── static\                     JS, CSS, AdminLTE
│   ├── docs\                       esta documentación
│   └── scripts\                    utilidades manuales (NO recogidas por pytest)
├── PROTECTION_PATTERNS.md          patrones de concurrencia e idempotencia
├── instructivos\                   fuentes de negocio en .docx / .mwb
└── docker-compose.yml              ⚠ solo SonarQube, NO la aplicación
```

**Dos trampas frecuentes de orientación:**

1. La raíz del proyecto Django es `AppTurnosExplora/`, no la raíz del repositorio.
2. El `docker-compose.yml` de la raíz levanta SonarQube. Los de la aplicación son
   `AppTurnosExplora/docker-compose.local.yml` y `docker-compose.hostdb.yml`.

## 3. Arquitectura

Arquitectura en capas con separación estricta entre HTTP, orquestación, reglas de
negocio y persistencia. La descripción completa está en
[03-arquitectura/ARQUITECTURA.md](./03-arquitectura/ARQUITECTURA.md); la justificación
de la capa de servicios, en
[ADR 001](./03-arquitectura/adr/001-service-layer-y-orchestrator.md).

### 3.1 El recorrido de una solicitud

Todo el motor de solicitudes pasa por un único camino. Entenderlo es entender el
sistema entero:

```
solicitudes/urls.py
  │
  ├─ views/cambio_turno_pages.py      renderiza el formulario según el tipo
  │
  └─ views/procesar_solicitud.py      endpoint POST único para los seis tipos
       │
       └─ services/solicitud_orchestrator.py
            │  1. sanción del solicitante          (solicitud_orchestrator.py:81)
            │  2. sanción del compañero            (solicitud_orchestrator.py:90)
            │  3. cierre semanal                   (solicitud_orchestrator.py:69)
            │  4. restricción médica               (solicitud_orchestrator.py:106)
            │  5. parseo del POST                  (services/solicitud_request_parser.py)
            │  6. validación                       (services/solicitud_factory.py:226)
            │  7. creación                         (services/solicitud_factory.py:205)
            │
            └─ services/solicitud_factory.py       elige la estrategia
                 └─ services/strategies/<tipo>.py  reglas propias del tipo
                      └─ services/validators/      validaciones reutilizables
                           └─ repositories/ → models
```

Al **aprobar**, el flujo vuelve a entrar por la estrategia: primero
`revalidar_para_aprobar` (`services/solicitud_factory.py:291`) y después
`aplicar_cambios` (`services/solicitud_factory.py:247`), que materializa los turnos.

### 3.2 Actores y límites del sistema

| Actor | Qué hace |
|---|---|
| Explorador | Crea solicitudes, aprueba o rechaza aquellas en las que es el compañero |
| Supervisor | Segunda aprobación, gestiona sanciones, reprogramaciones y cierre semanal |
| Administrador (`is_staff`) | Todo lo del supervisor, más el admin de Django |
| Correo saliente | Notificaciones y enlaces firmados de aprobación |

Fuera del sistema quedan la nómina y el registro de asistencia real: AppTurnos programa
y contabiliza deuda de jornada, no fichajes.

## 4. Patrones y refactorizaciones aplicadas

Esta sección responde a la pregunta "¿por qué está montado así?". Cada patrón se lista
con el problema concreto que resolvía.

### 4.1 Strategy — un archivo por tipo de solicitud

**Problema.** Los seis tipos comparten el 70 % del flujo pero difieren en reglas casi
incompatibles: una doblada genera deuda, un cambio de descanso no; un CT permanente
opera sobre un rango de fechas, un CT sencillo sobre un día. Resuelto con condicionales,
esto habría producido una vista de miles de líneas donde tocar un tipo rompe otro.

**Solución.** `SolicitudStrategy` (`services/strategies/base_strategy.py`) define el
contrato — `validar_solicitud`, `crear_solicitud`, `aplicar_cambios`,
`revalidar_para_aprobar`, `get_empleados_disponibles` — y cada tipo lo implementa a su
manera. El orquestador no sabe con qué tipo trabaja.

**Consecuencia práctica.** Añadir un séptimo tipo es escribir una clase y registrarla;
no se toca nada de lo existente. El procedimiento está en
[GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md](./04-guias/GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md).

### 4.2 Factory con búsqueda en cuatro niveles

**Problema.** Los tipos de solicitud viven en base de datos (`TipoSolicitudCambio`), y
sus nombres los escriben personas: "Cambio de Turno", "CAMBIO TURNO", "CT". Casar ese
texto libre con una clase Python es frágil.

**Solución.** `SolicitudFactory.get_strategy` (`services/solicitud_factory.py:123`)
busca en cascada:

1. Campo `codigo_estrategia`, coincidencia exacta — el control manual
   (`solicitud_factory.py:143`).
2. Nombre normalizado: mayúsculas, guiones a espacios, artículos eliminados
   (`solicitud_factory.py:46`).
3. Nombre directo, por compatibilidad con datos antiguos (`solicitud_factory.py:173`).
4. Estrategia por defecto — cambio de turno — con `warning` en el log
   (`solicitud_factory.py:182`).

La normalización tiene una sutileza deliberada: `'CT'` no debe capturar
`'CT PERMANENTE'`, por eso las coincidencias exactas se comprueban antes que las
parciales (`solicitud_factory.py:94-103`).

**Riesgo a vigilar.** El nivel 4 nunca falla ruidosamente: un tipo mal configurado se
procesa como cambio de turno. Ese `warning` del log es la única señal.

### 4.3 Validadores reutilizables

**Problema.** Reglas como "no en día de mantenimiento" o "no contigo mismo" aplican a
casi todos los tipos. Copiadas seis veces, se corrigen en cinco.

**Solución.** `BaseValidator` (`services/validators/base_validator.py`) concentra lo
transversal y los validadores específicos añaden lo suyo:
`ct_validator.py`, `ct_permanente_validator.py`, `doblada_validator.py`.

El método más importante es `_explorador_trabaja`
(`services/validators/base_validator.py:325`): responde "¿esta persona trabaja
realmente este día?" considerando **todos** los tipos de descanso — turnos explícitos,
descanso de fin de semana por alternancia, descanso de semana manual y mantenimiento.
Su docstring documenta el fallo que vino a cerrar: la jornada predeterminada no reflejaba
el descanso entre semana, lo que permitía ceder o pagar jornadas a alguien que ese día
descansaba.

**Regla derivada, y es la más importante del proyecto:** valida siempre contra el
estado real del día, nunca contra la jornada predeterminada.

### 4.4 Máquina de estados propia, sin librería

Los estados de una solicitud y sus transiciones legales están en un único mapa
(`domain/estado_machine.py:11`):

| Desde | Puede ir a |
|---|---|
| `pendiente` | `aprobada`, `rechazada`, `cancelada` |
| `aprobada` | `cancelada`, `reemplazada`, `pagada` |
| `rechazada`, `cancelada`, `reemplazada`, `pagada` | *(terminales)* |

`transicionar()` (`domain/estado_machine.py:28`) lanza `EstadoTransicionError` ante
cualquier salto ilegal. El motivo de no usar `django-fsm` está en
[ADR 002](./03-arquitectura/adr/002-fsm-sin-libreria-externa.md).

**Consecuencia.** Nunca asignes `solicitud.estado = '...'` a mano: se salta la
validación y es exactamente el tipo de bug que esta capa existe para impedir.

### 4.5 Casos de uso

`use_cases/` nombra la intención de negocio por encima de la implementación:
`CrearSolicitudUseCase`, `AprobarComoReceptorUseCase`, `AprobarComoSupervisorUseCase`,
`AprobarAmbosRolesUseCase`, `CancelarSolicitudUseCase`.

`AprobarAmbosRolesUseCase` (`use_cases/aprobar_solicitud.py:39`) resuelve un caso real:
cuando el supervisor es además el compañero de la solicitud, aprueba en ambos roles de
una sola acción — verificando primero que efectivamente ocupa los dos
(`use_cases/aprobar_solicitud.py:50-54`).

### 4.6 Repositorios

`repositories/solicitud_repository.py` y `turno_repository.py` aíslan las consultas del
ORM. Las estrategias piden datos sin escribir querysets, lo que mantiene las reglas de
negocio legibles y las consultas optimizables en un solo lugar.

### 4.7 Separación de vistas por archivo

`solicitudes/views/` es un paquete con ~18 módulos (páginas, procesamiento, aprobación,
gestión, reprogramación, endpoints JSON), reexportados desde `views/__init__.py`. El
diagnóstico que lo motivó está en
[01-analisis/ANALISIS_VIOLACIONES_SRP.md](./01-analisis/ANALISIS_VIOLACIONES_SRP.md).

### 4.8 Patrones de protección

Concurrencia, idempotencia y doble clic están documentados en detalle en
**`PROTECTION_PATTERNS.md`** (raíz del repositorio). Los que más aparecen en el motor de
solicitudes:

- **Bloqueo pesimista.** `select_for_update()` dentro de `transaction.atomic()` al
  cancelar (`use_cases/cancelar_solicitud.py:35-47`), para que dos peticiones casi
  simultáneas se serialicen y la segunda vea el estado ya cambiado.
- **Deshabilitar el botón al primer clic** en los siete formularios del frontend.
- **Snapshot antes de aplicar.** `snapshot_turnos_previos` (JSON) guarda el estado
  anterior de los turnos, lo que hace la reversión exacta y no reconstruida.
- **Fail-open deliberado en la revalidación.** Si `revalidar_para_aprobar` falla por un
  bug, se permite aprobar y se registra una ALERTA en el log
  (`services/solicitud_factory.py:307-317`). Es una red de seguridad *extra*: un fallo
  suyo no debe bloquear todas las aprobaciones del sistema.

## 5. Modelo de datos

El modelo completo está en [03-arquitectura/database/](./03-arquitectura/database/).
Las entidades con semántica no evidente:

### `turnos.Turno` — la entidad central

Un turno es una persona en una fecha con una jornada y una sala. Dos detalles críticos:

- Lleva `HistoricalRecords`: cada cambio queda registrado.
- Tiene **dos managers**: `objects` excluye los turnos anulados; `all_objects` los
  incluye. Un conteo que no cuadra con la interfaz casi siempre es esto.

### `solicitudes.SolicitudCambio` — la solicitud

Además de solicitante, receptor, tipo, estado y fecha, guarda la trazabilidad del
encadenamiento: `solicitud_origen`, `reemplazada_por` y `snapshot_turnos_previos`.

### Detalles por tipo

Una solicitud enlaza con el detalle que le corresponde: `CambioPermanenteDetalle` (+
`CambioPermanenteDia`), `DobladaDetalle`, `DobladaPermanenteDetalle`. **Cambio de
descanso y D FDS reutilizan `DobladaDetalle`**, aunque no generen deuda — al leer el
código, no asumas que `solicitud.doblada` implica una doblada.

### Deuda

`DeudaExplorador` y `DeudaCorporativa` registran jornadas debidas. La deuda corporativa
alimenta la **sanción automática**: antes de crear cualquier solicitud se recalcula y,
si procede, bloquea al empleado (`services/solicitud_orchestrator.py:32-43`).

### Calendario

`DiaEspecial` modela festivos, mantenimiento y temporada. Regla que atraviesa todo el
sistema: **la temporada manda**. Un día de mantenimiento que cae en temporada no cuenta
como mantenimiento (`services/validators/base_validator.py:65-67`).

## 6. Módulos y responsabilidades

| Módulo | Responsabilidad |
|---|---|
| `core` | Login, dashboard, utilidades de fecha, festivos de Colombia, caché, respuestas JSON |
| `empleados` | Personas, roles, salas, competencias, restricciones médicas, sanciones, indicadores |
| `turnos` | Turnos, jornadas, días especiales, alternancia de fines de semana, descansos, temporada, reportes |
| `solicitudes` | Los seis tipos, deudas, aprobaciones, notificaciones, cierre semanal, reprogramaciones |
| `permisos` | PDH y permisos especiales, pago de horas |

`turnos/services/` reúne ~12 servicios especializados; los más consultados desde
`solicitudes` son `turno_service`, `jornada_service`,
`alternancia_fines_semana_service` y `descanso_semana_service`.

## 7. Reglas de negocio transversales

Aplican a todos los tipos y se comprueban antes que cualquier regla específica.

**7.1 Sanción — solicitante y compañero.** Un sancionado no puede crear solicitudes
(`solicitud_orchestrator.py:81`) **ni participar como compañero**
(`solicitud_orchestrator.py:90`). El motivo está en el propio código: sin la segunda
comprobación bastaría con que otra persona enviara la solicitud en su nombre para
esquivar la sanción.

**7.2 Cierre semanal.** Cuando está habilitado, desde el día y hora de cierre no se
aceptan solicitudes nuevas cuyo objetivo caiga en la ventana `[día de cierre … primer
día hábil de la semana siguiente]` (`services/cierre_solicitudes_service.py:59-73`).
Hay configuración global (`CierreSolicitudesConfig`) y excepciones por semana
(`CierreSemanaOverride`). El primer día hábil salta festivos y mantenimientos, **pero no
la temporada**, que sí es día hábil (`cierre_solicitudes_service.py:31-34`). Solo afecta
a la creación: lo aprobado y las acciones del supervisor no pasan por aquí.

**7.3 Restricción médica.** No bloquea: advierte. Si hay una restricción vigente en el
rango, se devuelve `advertencia_restriccion` y el usuario debe confirmar
(`solicitud_orchestrator.py:106-148`).

**7.4 Día de mantenimiento.** Bloquea los cambios, salvo que la fecha esté en temporada
(`services/validators/base_validator.py:48-78`).

**7.5 Una solicitud pendiente por persona y fecha.** Ni el solicitante ni el compañero
pueden tener otra pendiente para la misma fecha
(`base_validator.py:227` y `base_validator.py:267`). Excepción deliberada: varias
personas **distintas** sí pueden solicitar al mismo compañero para la misma fecha —
primero en llegar, primero en ser servido (`base_validator.py:21-45`).

**7.6 Ventana de cancelación de 30 minutos.** Una solicitud pendiente se cancela sin
límite; una aprobada, solo dentro de los 30 minutos siguientes a su aprobación
(`use_cases/cancelar_solicitud.py:20` y `:80`).

**7.7 Guardia LIFO.** No se puede cancelar un cambio si existe otro más reciente sobre
el mismo día: hay que cancelar primero el más reciente
(`use_cases/cancelar_solicitud.py:87-106`). Esto sostiene el principio de que **el
estado efectivo de un día es lo último aprobado que lo modifica**; los cambios no se
encadenan, se cancelan.

**7.8 Doble aprobación.** Toda solicitud necesita al compañero y al supervisor. Si una
misma persona ocupa ambos roles, puede resolver los dos de una vez
(`use_cases/aprobar_solicitud.py:39`).

**7.9 Revalidación al aprobar.** Entre la creación y la aprobación el mundo cambia. Por
eso se revalida contra el estado actual antes de aplicar
(`services/solicitud_factory.py:291`).

## 8. Los seis tipos de solicitud

Reglas verificadas en código. Para el detalle operativo de dobladas, ver
[05-referencia/solicitudes/dobladas/](./05-referencia/solicitudes/dobladas/).

### 8.1 Cambio de turno (CT)

Intercambio de jornada entre dos exploradores en **un** día.

- Jornadas **contrarias** obligatorias: no se cambia AM por AM
  (`services/validators/ct_validator.py:36`).
- No se admiten fechas pasadas (`strategies/cambio_turno_strategy.py:72`).
- Ambos deben tener jornada ese día (`cambio_turno_strategy.py:88-90`).
- Si el solicitante descansa ese día, no hay nada que intercambiar
  (`cambio_turno_strategy.py:96`).
- Prohibido en domingo (`ct_validator.py:61`) y en sábado
  (`ct_validator.py:77`): el fin de semana lo gobierna la alternancia, no el
  intercambio directo.

Reglas ampliadas en
[REGLAS_NEGOCIO_CAMBIO_TURNO_SENCILLO.md](./05-referencia/solicitudes/REGLAS_NEGOCIO_CAMBIO_TURNO_SENCILLO.md).

### 8.2 Cambio de turno permanente (CT permanente)

El mismo intercambio, repetido en unos días de la semana durante un rango de fechas.

- `fecha_fin` es obligatoria (`strategies/ct_permanente_strategy.py:80`).
- Jornadas contrarias, igual que en CT (`ct_permanente_strategy.py:303`).
- **Nunca en domingo** (`services/validators/ct_validator.py:55-57`).
- El rango se expande a fechas concretas cruzando días de la semana con el intervalo
  (`services/solicitud_orchestrator.py:50-65`); los días no seleccionados se omiten.

### 8.3 Cambio de descanso

Tiene **dos modalidades distintas**, documentadas en la cabecera de
`strategies/cambio_descanso_strategy.py:1-16`.

**Modalidad fin de semana.** Intercambio de ida y vuelta de los días trabajados del fin
de semana. Si una persona trabaja el sábado y otra el domingo, se permutan; en otra
semana del mismo mes se revierte. **No genera dobladas ni deudas**: cada explorador
sigue trabajando un solo día por fin de semana, solo cambia cuál.

- Ambas fechas deben ser fin de semana (`cambio_descanso_strategy.py:243-245`).
- No se admite un fin de semana pasado (`:250`) y la devolución debe ser posterior a hoy
  (`:252`).
- La devolución debe caer en un fin de semana **distinto** (`:254`).

**Modalidad entre semana (temporada).** Intercambio directo de los descansos asignados
por el supervisor, **sin devolución**.

- Ambos días de lunes a viernes (`:383`, `:385`, `:459`).
- Ambos dentro del mismo rango de temporada, máximo 45 días (`:396`).
- El compañero debe ser del **grupo contrario** (`:410`).
- La semana debe tener descansos de temporada configurados (`:472`).
- Duplicado bloqueado: no se puede reenviar el mismo intercambio si ya está pendiente
  (`:402`).

Principio asociado: solo se cede el descanso de la temporada original; los intercambios
**no se encadenan**.

### 8.4 Doblada

Un explorador cede su jornada; el compañero la cubre doblándose, y esa jornada se
devuelve después. Es el tipo más complejo: la estrategia ocupa ~1.044 líneas.

Reglas centrales:

- La **fecha de pago es obligatoria**: no existen dobladas abiertas
  (`services/validators/doblada_validator.py:33`).
- Debe ser posterior a la fecha de creación de la solicitud (`doblada_validator.py:44`).
- **No puede coincidir con la fecha de cesión** — no se puede trabajar y descansar el
  mismo día (`doblada_validator.py:67`).
- Pago y cesión deben estar en el **mismo mes calendario**; el pago sí puede ser
  anticipado (`services/validators/base_validator.py:219`).
- Jornadas contrarias: quien cede AM necesita un compañero con PM y viceversa
  (`doblada_validator.py:143-150`).
- Sin triple turno: el receptor no puede tener ya una doblada el día de la cesión
  (`doblada_validator.py:165`).
- Ni domingo ni mantenimiento; festivos entre semana y temporada **sí** se permiten
  (`doblada_validator.py:194-199`).
- Si ambos descansan en la fecha de pago, no hay pago posible
  (`doblada_validator.py:269`).
- Si el receptor no trabaja ese día, no hay jornada que cubrir
  (`doblada_validator.py:294`).
- El receptor no puede pagar un día en que ya cedió su propia jornada
  (`doblada_validator.py:325`).

**Coincidencia de jornadas al pagar** (`doblada_validator.py:340`). Si deudor y acreedor
tienen la misma jornada en la fecha de pago, no se puede pagar trabajando dos veces lo
mismo; el sistema devuelve `requiere_cambio_turno_previo`
(`services/solicitud_orchestrator.py:162`). La regla tiene tres exenciones razonadas en
el propio código: pago en sábado, donde manda la alternancia (`:382`); deudor que
descansa ese día (`:401`); y acreedor que descansa ese día (`:420`). Las tres se
añadieron para eliminar falsos positivos del tipo "ambos tienen PM" cuando en realidad
uno de los dos no trabajaba.

**Submodalidades.** Pago en sábado con jornada elegible (AM, PM o ambas), pago en día de
semana dentro del mismo mes que el sábado (`strategies/doblada_strategy.py:685-694`), e
**intercambio de dobladas** entre un día A y un día B distintos (`:559-563`).

### 8.5 Doblada permanente

Doblada repetida sobre un rango de fechas, y el único tipo con **flujo propio
multi-compañero**: se puede repartir la cobertura entre varias personas y se crea una
solicitud independiente por cada una (`services/solicitud_orchestrator.py:179`).

- **Todo o nada:** se validan todas antes de crear ninguna
  (`solicitud_orchestrator.py:302-334`).
- **Balance obligatorio:** a cada compañero se le devuelve exactamente el mismo número
  de fechas que cubre (`solicitud_orchestrator.py:276-282`).
- **Una fecha, un compañero:** dos personas no pueden cubrir ni pagar la misma jornada
  el mismo día (`solicitud_orchestrator.py:209-233`). Esta comprobación vive en el
  orquestador precisamente porque es un cruce *entre* solicitudes que ninguna validación
  individual detectaría.
- Solo se devuelve a quien te cubre (`solicitud_orchestrator.py:272-275`).
- El rango no puede empezar en el pasado
  (`strategies/doblada_permanente_strategy.py:138`).

### 8.6 D FDS — doblada de fin de semana

Un explorador cede su día de fin de semana a un compañero del grupo contrario, que se
dobla ese fin de semana; el solicitante devuelve el favor doblándose otro fin de semana
del mismo mes (`strategies/d_fds_strategy.py:1-14`).

- Ambas fechas deben ser sábado o domingo (`d_fds_strategy.py:112-114`).
- Ni fines de semana pasados (`:120`) ni pago anterior a hoy (`:122`).
- Pago y cesión no pueden ser el mismo día (`:124`).
- El compañero no puede tener ya doblada en la fecha de cesión (`:246`), ni el
  solicitante en la fecha de pago (`:248`).
- La **alternancia** determina qué grupo trabaja cada día del fin de semana
  (`:175`, `:201`). Como en fin de semana quien trabaja lo hace AM+PM, el grupo se
  determina por la asignación base, no por el turno del día (`:49-59`).

## 9. Configuración local

```bash
cd AppTurnosExplora
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env          # y edita los valores
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

`ENVIRONMENT` (`development` | `production`) gobierna el comportamiento de
`config/settings.py`, que es un archivo único: no hay `settings/local.py`.

Con Docker: `docker compose -f docker-compose.local.yml up`. Guía completa en
[MANUAL_DOCKER_LOCAL.md](./05-referencia/deployment/MANUAL_DOCKER_LOCAL.md).

**Datos anuales.** Temporada, festivos y mantenimiento se cargan **manualmente cada
diciembre**. Que un año futuro no tenga datos es intencional, no un fallo. El
procedimiento está en
[04-guias/mantenimiento-anual/](./04-guias/mantenimiento-anual/).

**CSP.** El proyecto usa `django-csp` con lista blanca. Al añadir cualquier recurso
externo hay que registrarlo en `config/settings.py` o el navegador lo bloqueará sin
error visible en el servidor.

## 10. Pruebas

```bash
cd AppTurnosExplora
pytest                                    # todo
pytest solicitudes/tests -v               # el dominio central
pytest solicitudes/tests/test_matriz_dobladas.py
```

Configuración en `pytest.ini`; rutas recogidas: `integration_tests`,
`solicitudes/tests`, `turnos/tests`, `empleados/tests`, `permisos/tests`.

Los tests de `solicitudes/tests/` (~24 archivos) son la mejor documentación ejecutable de
las reglas: `test_matriz_dobladas`, `test_cancelacion_lifo`, `test_cambio_sobre_cambio`,
`test_ct_permanente_revert`, `test_reflejo_mis_turnos`. Inventario completo en
[INVENTARIO_TESTS.md](./05-referencia/pruebas/INVENTARIO_TESTS.md).

**Los scripts de `AppTurnosExplora/scripts/` no los recoge pytest**: son utilidades
manuales de diagnóstico y mantenimiento, aunque algunos se llamen `test_*`.

## 11. Despliegue

Cubierto por completo en
[05-referencia/deployment/](./05-referencia/deployment/): AWS EC2 + RDS + SES, ECS
Fargate, y la arquitectura recomendada. Pendientes de infraestructura en
[ADR 005](./03-arquitectura/adr/005-pendientes-aws.md).

## 12. Mantenimiento periódico

Comandos de gestión relevantes (`python manage.py <comando>`):

| Comando | Para qué |
|---|---|
| `verificar_integridad_dobladas` | Detecta dobladas aprobadas cuyos turnos no cuadran |
| `reaplicar_doblada` | Reaplica una doblada que quedó a medias |
| `cancelar_deudas_fin_semana` | Limpieza de deudas de fin de semana |
| `cancelar_deudas_huerfanas` | Deudas sin solicitud asociada |
| `archivar_solicitudes_antiguas` | Archivado histórico |
| `instalar_calendario_colombiano` | Carga de festivos |
| `actualizar_codigos_estrategia` | Sincroniza `codigo_estrategia` con las estrategias |
| `validar_jornadas` | Consistencia de jornadas |

## 13. Archivos críticos y zonas frágiles

Lo que hay que tratar con cuidado, y por qué:

| Archivo | Por qué es crítico |
|---|---|
| `solicitudes/services/solicitud_orchestrator.py` | Único punto de entrada de los seis tipos. Un fallo aquí los rompe todos |
| `solicitudes/services/strategies/doblada_strategy.py` | ~1.044 líneas, el mayor número de casos límite del sistema |
| `solicitudes/services/validators/base_validator.py` | `_explorador_trabaja` es la fuente de verdad de "¿trabaja este día?"; cambiarlo altera todas las validaciones |
| `solicitudes/domain/estado_machine.py` | Cualquier estado nuevo exige revisar el mapa de transiciones |
| `solicitudes/use_cases/cancelar_solicitud.py` | Ventana de 30 minutos, guardia LIFO y reversión por tipo, todo junto |
| `turnos/models.py` | Los dos managers (`objects` / `all_objects`) confunden a quien no lo sabe |
| `solicitudes/services/solicitud_factory.py` | La normalización de nombres es sensible al orden; ver `'CT'` vs `'CT PERMANENTE'` |

**Zonas propensas a error, por experiencia del propio código:**

1. **Jornada predeterminada vs. estado real.** Media docena de correcciones del
   repositorio nacen de este confusión. Usa siempre `_explorador_trabaja` o
   `TurnoService.estado_dia`.
2. **Fin de semana.** Quien trabaja lo hace AM+PM, así que el turno del día no indica el
   grupo: hay que mirar la asignación base.
3. **Fin de mes.** Varias reglas exigen "mismo mes calendario"; los tests deben evitar
   fechas que crucen el límite del mes.
4. **Temporada frente a mantenimiento.** La temporada manda, siempre.
5. **Reversión.** Borra y recrea turnos con identificadores nuevos; los FK en memoria
   quedan obsoletos y hay que refrescarlos
   (`use_cases/cancelar_solicitud.py:110-118`).

## 14. Puntos de extensión

- **Nuevo tipo de solicitud:** clase de estrategia + registro en el factory + validador +
  template + JS. Paso a paso en
  [GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md](./04-guias/GUIA_AGREGAR_NUEVO_TIPO_SOLICITUD.md).
- **Nueva validación transversal:** añádela a `BaseValidator` y llámala desde las
  estrategias que la necesiten.
- **Nuevo estado:** amplía el mapa de `domain/estado_machine.py` y revisa qué
  transiciones deben permitirse desde y hacia él.
- **Nuevo canal de notificación:** `services/notificacion_service.py` y
  `services/email_service.py` son el punto de enganche. El disparo va en `on_commit`
  ([ADR 003](./03-arquitectura/adr/003-on-commit-para-notificaciones.md)).

## 15. Seguridad

- **Autenticación:** login propio en `core/login/`, con `django-axes` bloqueando por
  intentos fallidos.
- **Autorización:** `AdminRequiredMixin` (`core/mixins.py:11`) admite `is_staff` o rol
  cuyo nombre contenga "supervisor" (`core/mixins.py:42-44`). **Falla cerrado**: ante
  cualquier excepción deniega y registra un `warning` (`core/mixins.py:47-54`).
- **Aprobación por correo:** enlaces con token firmado
  (`views/aprobacion_email.py`), que permiten aprobar sin iniciar sesión.
- **CSP y CORS:** `django-csp` y `django-cors-headers` configurados en
  `config/settings.py`.
- **Secretos:** vía `django-environ`; nunca en el código
  ([ADR 004](./03-arquitectura/adr/004-variables-de-entorno-django-environ.md)).

**Riesgo conocido.** La comprobación de rol de supervisor usa `icontains='supervisor'`
sobre el nombre del rol. Un rol llamado, por ejemplo, "ex-supervisor" concedería acceso.
Merece una revisión.

## 16. Glosario

| Término | Significado |
|---|---|
| **Explorador** | Empleado que cubre turnos; el usuario final del sistema |
| **Jornada** | Franja de trabajo, típicamente AM o PM |
| **Turno** | Un explorador, en una fecha, con una jornada y una sala |
| **Doblada** | Trabajar AM y PM el mismo día |
| **Cesión** | Entregar la propia jornada a un compañero, que la cubre |
| **Pago** | Devolver una jornada cedida, doblándose en la fecha acordada |
| **Deuda** | Jornada cedida y aún no devuelta |
| **Alternancia** | Rotación que determina qué grupo trabaja cada día del fin de semana |
| **Grupo AM / PM** | Conjunto de exploradores según su asignación base |
| **Temporada** | Periodo de alta demanda con reglas propias; prevalece sobre el mantenimiento |
| **Mantenimiento** | Día sin operación; bloquea los cambios salvo en temporada |
| **D FDS** | Doblada de fin de semana |
| **CT** | Cambio de turno |
| **PDH** | Pago de horas (módulo `permisos`) |
| **Cierre semanal** | Ventana a partir de la cual la programación del fin de semana queda cerrada |
| **Guardia LIFO** | Regla que obliga a cancelar primero el cambio más reciente sobre un día |

## 17. Por confirmar

| Afirmación pendiente | Dónde se buscó | Por qué no se pudo verificar |
|---|---|---|
| Reglas de negocio acordadas con el cliente | `instructivos/*.docx`, `*.mwb` | Formato binario, no legible en esta pasada. Es la fuente más probable de divergencias entre lo acordado y lo implementado |
| Especificación original de dobladas | `docs/04-guias/manuales/` — "requisito doblada.docx" (1,1 MB), "Proceso completo doblada.docx" (348 KB) | Formato binario. Contrastarlos con `doblada_strategy.py` y `doblada_validator.py` es la comprobación pendiente de mayor valor |
| Alcance funcional de `permisos/` (PDH, permisos especiales) | `permisos/services.py`, `pago_horas_service.py` | Fuera del alcance de esta pasada, centrada en el motor de solicitudes |
| Reglas de salas y competencias en la asignación | `empleados/models.py`, `turnos/services/` | No se rastreó el criterio de asignación de sala al materializar turnos |
| Contenido exacto de los 14 correos | `templates/solicitudes/emails/` | Se verificó su existencia, no su contenido |
| Comportamiento de los indicadores | `empleados/services/indicadores_service.py` | No revisado |
| Vigencia de `docs/02-refactorizacion/` | Esa carpeta | Documenta fases terminadas; no se contrastó cuánto sigue vigente |

---

*Generado con el skill `project-documentation-master`. La fuente de verdad es este
Markdown; el `.docx` es un artefacto derivado y no debe editarse a mano.*
