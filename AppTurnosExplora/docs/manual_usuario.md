# Manual de Usuario — AppTurnos / SWALP

Guía para exploradores y supervisores. No necesitas conocimientos técnicos para leerla.

Si buscas la documentación para desarrolladores, tu documento es
[manual_tecnico.md](./manual_tecnico.md). El índice general de la documentación está en
[README.md](./README.md).

---

## 1. Qué es AppTurnos y qué problema resuelve

AppTurnos —también llamada SWALP— organiza la programación de turnos del equipo de
exploradores y registra los acuerdos entre compañeros para intercambiar jornadas.
<!-- fuente: core/login/template/login.html (rótulo "SWALP · Gestión de turnos del equipo · Parque Explora") -->

El problema que resuelve es sencillo de enunciar: antes, los cambios se pactaban de
palabra y nadie tenía un registro fiable de quién debía qué a quién. Aquí todo acuerdo
queda escrito, aprobado y reflejado en el calendario.

Con la aplicación puedes consultar tus turnos, pedir un cambio, aprobar lo que otros te
piden y ver quién te cubrió y a quién debes cubrir.
<!-- fuente: templates/solicitudes/list.html; templates/solicitudes/mis_favores.html -->

Todo acuerdo entre dos personas necesita **dos aprobaciones**: la del compañero implicado
y la del supervisor. Hasta que ambas llegan, el calendario no cambia.
<!-- fuente: solicitudes/services/solicitud_aprobacion_service.py (aprobar_solicitud_receptor / aprobar_solicitud_supervisor) -->

### 1.1 A quién sirve

| Acción | Explorador | Supervisor | Administrador |
|---|---|---|---|
| Consultar sus propios turnos | Sí | Sí | Sí |
| Crear solicitudes | Sí | Sí | Sí |
| Aprobar o rechazar como compañero | Sí, cuando lo eligen a él | Sí | Sí |
| Aprobar o rechazar como supervisor | No | Sí | Sí |
| Cancelar sus propias solicitudes | Sí | Sí | Sí |
| Ver y gestionar todas las solicitudes | No | Sí | Sí |
| Registrar inasistencias y reprogramar | No | Sí | Sí |
| Configurar el cierre semanal | No | Sí | Sí |
| Gestionar personas, salas, sanciones y restricciones | No | Sí | Sí |
| Publicar el calendario del año, festivos y descansos de temporada | No | Sí | Sí |

<!-- fuente: core/mixins.py (es_supervisor: staff o rol Supervisor exacto) -->
<!-- fuente: templates/base.html (bloque {% if puede_administrar %} del menú lateral) -->

"Supervisor" y "administrador" ven exactamente el mismo menú: la aplicación distingue a
quien tiene el rol **Supervisor** o es administrador del sistema, y a todos los demás.
El rol se compara de forma exacta: un rol llamado "supervisor de sala", por ejemplo, no
concede esos permisos.
<!-- fuente: core/mixins.py (comparación __iexact contra Role.SUPERVISOR) -->

Un supervisor que además sea el compañero de una solicitud puede resolver las dos
aprobaciones de una vez con la **Acción combinada**.
<!-- fuente: templates/solicitudes/solicitudes_pendientes_list.html:140 -->

### 1.2 Qué NO hace el sistema

- **No recupera contraseñas por tu cuenta.** No existe una pantalla de "olvidé mi
  contraseña": el cambio lo hace el administrador.
  <!-- fuente: core/login/urls.py (solo rutas de inicio y cierre de sesión) -->
- **No permite acuerdos verbales.** Si no hay solicitud aprobada, el turno no cambia.
- **No inventa la programación del año.** Los fines de semana, los festivos y los días de
  descanso de temporada los publica el supervisor; si no están cargados, los formularios
  que dependen de ellos no ofrecen opciones.
  <!-- fuente: solicitudes/services/strategies/doblada_strategy.py ("El año {…} aún no tiene publicada la alternancia de fines de semana") -->
- **No deja doblar un domingo.** Ni con doblada ni con cambio de turno permanente.
  <!-- fuente: solicitudes/services/validators/doblada_validator.py:191; ct_validator.py:57 -->
- **No reescribe el pasado.** Una vez trabajado un día, ni tú ni el supervisor pueden
  borrarlo cancelando la solicitud.
  <!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (execute_supervisor, casos 3 y 4) -->
- **No avisa por mensaje de texto.** Los avisos llegan dentro de la aplicación y por
  correo electrónico.
  <!-- fuente: solicitudes/views/aprobacion_email.py; templates/solicitudes/emails/ -->

### 1.3 Glosario mínimo

| Término | Qué significa |
|---|---|
| **Turno** | El trabajo que te corresponde un día concreto. |
| **Jornada** | La mitad del día que trabajas: **AM** (mañana) o **PM** (tarde). |
| **Jornada contraria** | La otra mitad. Si tú eres AM, tu compañero contrario es PM. Casi todos los acuerdos exigen jornadas contrarias. |
| **Doblada** | Trabajar las dos jornadas del mismo día (AM + PM). En un fin de semana ese mismo esfuerzo se llama **día completo**, porque es lo normal ese día. <!-- fuente: static/js/mis_turnos.js:742 --> |
| **Cesión** | El día que tú no trabajas porque un compañero te cubre. |
| **Pago o devolución** | El día en que le devuelves el favor a ese compañero. |
| **Descanso** | Día que no trabajas por programación (temporada, alternancia de fin de semana o mantenimiento). Se marca con 😴. <!-- fuente: static/js/mis_turnos.js:459 --> |
| **Día libre** | Día que te queda libre porque cediste tu jornada en una doblada. Se marca con ☕. <!-- fuente: static/js/mis_turnos.js:459 --> |
| **Temporada** | Semana de alta operación en la que el supervisor fija días de descanso concretos entre semana. |
| **Alternancia** | El reparto publicado de quién trabaja sábado y quién domingo. |
| **Cobertura** | Que un compañero trabaje una jornada tuya sin que tú dejes de existir en el calendario. |
| **Deuda** | Jornada que te cubrieron y todavía no has devuelto. |
| **Sesión** | El periodo en que la aplicación te reconoce tras iniciar sesión. Al cerrar sesión termina. |
| **Sanción** | Periodo en el que no puedes participar en ninguna solicitud. Se marca con ⚖️. <!-- fuente: static/js/mis_turnos.js:553 --> |
| **Restricción** | Recomendación médica vigente en unas fechas. Se marca con 🚫. <!-- fuente: static/js/mis_turnos.js:525 --> |
| **Código de referencia** | Cadena de 12 caracteres, del estilo `A3F91C2B7D01`, que aparece en tres sitios: al pie de las pantallas de error; dentro del aviso de fallo al enviar una solicitud, cuando el servidor alcanza a responder; y en el recuadro **Detalles del Error** de la página "No se pudo procesar la solicitud", la que sale al abrir un enlace del correo que ya no sirve. Identifica tu caso concreto para el equipo de desarrollo. <!-- fuente: core/errors.py:68 (uuid4().hex[:12].upper()); static/js/utils/codigo-referencia.js:70-79; templates/solicitudes/error_token.html:47-55 --> |

---

## 2. Primeros pasos

Este apartado es un recorrido guiado. Síguelo en orden la primera vez.

### 2.1 Cómo ingresar

Necesitas un navegador actualizado y las credenciales que te entrega el supervisor.

1. Abre la dirección de la aplicación que te hayan indicado. Verás la pantalla
   **Bienvenido**, con el rótulo **SWALP** y el texto *Ingresa tus credenciales para
   continuar*.
   <!-- fuente: core/login/template/login.html -->
2. Escribe tu usuario y tu contraseña.
3. Pulsa **Iniciar sesión**.

Si los datos son correctos, entras directamente en el **Dashboard**.
<!-- fuente: config/settings.py:227 (LOGIN_REDIRECT_URL = 'dashboard') -->

Si te equivocas, la pantalla muestra: *"Usuario o contraseña incorrectos. Verifica tus
datos e inténtalo de nuevo."*
<!-- fuente: core/login/template/login.html -->

Tras **5 intentos fallidos** el sistema bloquea el acceso a ese usuario durante **1
hora**. Un inicio de sesión correcto reinicia la cuenta de intentos.
<!-- fuente: config/settings.py:330-333 (AXES_FAILURE_LIMIT=5, AXES_COOLOFF_TIME=1, AXES_RESET_ON_SUCCESS=True) -->

### 2.2 Qué ves al entrar

La pantalla tiene un menú lateral fijo a la izquierda y el contenido a la derecha.

Como explorador, tu menú tiene estas opciones:
<!-- fuente: templates/base.html -->

1. **Dashboard** — la portada.
2. **Mis Turnos / Mi Calendario** — tu calendario.
3. **Notificaciones / Solicitudes** — el centro de trámites. Cuando tienes avisos sin
   leer, aparece un contador junto al nombre.
   <!-- fuente: templates/base.html (notificaciones_no_leidas_count) -->
4. **Cambios de Turno** — atajo directo a la lista de tipos de solicitud.
5. **Consolidado de Horas**, **Permisos Especiales**, **Beneficios Utilizados**,
   **Sanciones**, **Restricciones**, **Días Especiales**, **Indicadores** — consulta.

Si eres supervisor, además ves **Empleados/Exploradores**, **Gestión de Solicitudes**,
**Reprogramaciones**, **Cierre de solicitudes**, **Apertura de Año**, **Descansos de
Semana**, **Fines de Semana / Festivos**, **Tipos de Solicitud**, **Salas**, **Turnos**,
**Jornadas**, **PDH** y **Roles y Permisos**.
<!-- fuente: templates/base.html (bloque {% if puede_administrar %}) -->

Entra ahora en **Notificaciones / Solicitudes**. Verás cuatro accesos: **Mis
Solicitudes**, **Solicitudes Pendientes**, **Mis Favores** y **Notificaciones**, más el
botón **Solicitar Cambio de Turno**.
<!-- fuente: templates/solicitudes/list.html -->

Pulsa **Solicitar Cambio de Turno**: llegas a la pantalla *Selecciona el tipo de
solicitud que deseas iniciar*, con una tarjeta por cada tipo y un botón **Iniciar
Solicitud** en cada una. Esa es la puerta de entrada de los seis formularios.
<!-- fuente: templates/solicitudes/cambio_turno_inicio.html -->

Si esa pantalla aparece con el mensaje *"En este momento no hay tipos de solicitud
configurados en el sistema."*, avisa a tu supervisor: falta cargar los tipos.
<!-- fuente: templates/solicitudes/cambio_turno_inicio.html -->

### 2.3 Recuperar o cambiar la contraseña

No hay autoservicio. Si olvidaste tu contraseña o quieres cambiarla, pídeselo a tu
supervisor o al administrador del sistema.
<!-- fuente: core/login/urls.py (no hay rutas de restablecimiento de contraseña) -->

Lo mismo si quedaste bloqueado tras cinco intentos fallidos y no quieres esperar la hora
de espera.

### 2.4 Cerrar sesión y qué pasa si se vence

Para salir, usa la opción de cerrar sesión. Vuelves a la pantalla de inicio de sesión.
<!-- fuente: core/login/views.py (LogoutUserView, next_page='login') -->

Hazlo siempre en equipos compartidos.

Si tu sesión caduca —por inactividad prolongada o porque cerraste el navegador— y pulsas
cualquier opción del menú, la aplicación te devuelve a la pantalla de inicio de sesión.
Vuelve a entrar y continúa: no se pierde nada de lo ya enviado.
<!-- fuente: config/settings.py:226 (LOGIN_URL) -->

Caso aparte: si dejaste un formulario abierto mucho tiempo y pulsas enviar, puede aparecer
la pantalla "Tu sesión expiró antes de enviar el formulario". No se guarda nada; se explica
en el apartado 7.2.
<!-- fuente: templates/403_csrf.html; core/errors.py:154-164 -->

---

## 3. Mapa de la aplicación

### 3.1 Menú y secciones

| Sección | Para qué sirve | Quién la ve |
|---|---|---|
| **Dashboard** | Portada de entrada | Todos |
| **Mis Turnos / Mi Calendario** | Tu calendario del mes y el resumen de la semana | Todos |
| **Notificaciones / Solicitudes** | Centro de trámites: crear, consultar y aprobar | Todos |
| **Cambios de Turno** | Lista de los tipos de solicitud disponibles | Todos |
| **Mis Solicitudes** | Historial de todo lo que has enviado, con su estado | Todos |
| **Solicitudes Pendientes** | Lo que espera tu aprobación | Todos |
| **Mis Favores** | Quién te cubrió en fin de semana y a quién cubriste tú | Todos |
| **Notificaciones** | Avisos del sistema | Todos |
| **Consolidado de Horas** | Recuento de horas | Todos |
| **Permisos Especiales**, **Beneficios Utilizados** | Consulta de permisos y beneficios | Todos |
| **Sanciones**, **Restricciones**, **Días Especiales** | Consulta de tu situación y del calendario | Todos |
| **Indicadores** | Cuadro de indicadores | Todos |
| **Gestión de Solicitudes** | Ver, reenviar, cancelar o eliminar cualquier solicitud | Supervisor |
| **Reprogramaciones** | Registrar una inasistencia y reasignar el día de doblada | Supervisor |
| **Cierre de solicitudes** | Configurar a partir de cuándo se cierra el fin de semana | Supervisor |
| **Apertura de Año**, **Descansos de Semana**, **Fines de Semana / Festivos** | Publicar el calendario anual | Supervisor |
| **Empleados/Exploradores**, **Salas**, **Jornadas**, **Turnos**, **PDH**, **Roles y Permisos**, **Tipos de Solicitud** | Configuración | Supervisor |

<!-- fuente: templates/base.html; templates/solicitudes/list.html; solicitudes/urls.py -->

### 3.2 Mis Turnos: cómo leer el calendario

La pantalla tiene dos partes.

Arriba, el **Resumen Semanal de Turnos**: una tarjeta por día con el rango de fechas de la
semana. Cada tarjeta muestra tu jornada del día —**AM**, **PM**, **DOBLADA** o
**DESCANSO**— y debajo si es *Asignado* (viene de un acuerdo) o *Predeterminado* (es tu
programación normal).
<!-- fuente: templates/turnos/mis_turnos.html -->

Abajo, el **Calendario de Jornadas** del mes. Toca un día y se despliega **Detalles del
día** con tu jornada y, si procede, la explicación del acuerdo que la cambió.
<!-- fuente: templates/turnos/mis_turnos.html; static/js/mis_turnos.js -->

Los símbolos de las casillas del calendario:

| Símbolo | Significado |
|---|---|
| 😴 | Día de descanso: temporada, mantenimiento, fin de semana o intercambio de descanso |
| ☕ | Día libre porque cediste tu jornada en una doblada |
| 📋 | Permiso aprobado |
| ⏳ | Permiso pendiente |
| 🚫 | Restricción médica en esa fecha |
| ⚖️ | Estás sancionado ese día: no puedes hacer solicitudes |

<!-- fuente: static/js/mis_turnos.js:455-560 -->

En el detalle del día, el nombre del acuerdo que modificó la jornada se muestra con su
nombre real: *Cambio de turno*, *Cambio de turno permanente*, *Cambio de día de
descanso*, *Doblada*, *Doblada permanente* o *Doblada de fin de semana*.
<!-- fuente: static/js/mis_turnos.js:590-597 -->

Un detalle de vocabulario: entre semana, trabajar AM y PM el mismo día se muestra como
**DOBLADA (AM + PM)**; en sábado o domingo, como **DÍA COMPLETO (AM + PM)**, porque en fin
de semana lo habitual es trabajar el día entero y no es un esfuerzo extra.
<!-- fuente: static/js/mis_turnos.js:742 -->

### 3.3 Estado de una solicitud

En **Mis Solicitudes** cada fila tiene un estado.

| Estado | Qué significa | Qué puedes hacer |
|---|---|---|
| **Pendiente** | Falta al menos una de las dos aprobaciones | Cancelar, sin límite de tiempo |
| **Aprobada** | Compañero y supervisor aprobaron; el calendario ya cambió | Cancelar solo dentro de los 30 minutos siguientes |
| **Rechazada** | Alguien la rechazó; nada cambia | Nada; envía otra si procede |
| **Cancelada** | Se dio de baja | Nada |

<!-- fuente: templates/solicitudes/mis_solicitudes_list.html (filtros Pendiente/Aprobada/Rechazada/Cancelada) -->
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (VENTANA_CANCELACION_MINUTOS = 30) -->

En las filas aprobadas, el botón de cancelar muestra una cuenta atrás con el tiempo que te
queda, y su descripción es *"Cancelar (solo disponible 30 min tras aprobación)"*.
<!-- fuente: templates/solicitudes/mis_solicitudes_list.html:125-127 -->

---

## 4. Los formularios de solicitud

Los seis formularios comparten el mismo camino de entrada, las mismas comprobaciones
previas y el mismo comportamiento al enviar. Cada ficha sigue la misma plantilla de 14
puntos para que puedas compararlos.

Antes de las fichas, tres cosas que valen para todos:

- **Comentario obligatorio.** Los seis exigen explicar el motivo.
  <!-- fuente: solicitudes/services/validators/base_validator.py:190 -->
- **Sanción bloqueante.** Ni tú ni tu compañero podéis participar si alguno está
  sancionado.
  <!-- fuente: solicitudes/services/solicitud_orchestrator.py:164-187 -->
- **Nada del día en curso.** El calendario de los formularios empieza en **mañana**.
  <!-- fuente: solicitudes/views/cambio_turno_pages.py (fecha_minima = hoy + 1 día en los cinco formularios que la fijan) -->

---

### 4.1 Cambio de turno

**1. Nombre y cómo se llega.**
Pantalla **Solicitud de Cambio de Turno**.
Menú lateral → **Cambios de Turno** → tarjeta *Cambio de turno* → **Iniciar Solicitud**.
También desde **Notificaciones / Solicitudes** → **Solicitar Cambio de Turno**.
<!-- fuente: solicitudes/urls.py (cambio_turno_inicio, solicitar_cambio_turno); templates/solicitudes/solicitar_cambio_turno.html -->

**2. Para qué sirve.**
Intercambiar tu jornada con un compañero durante un solo día: tú pasas a su horario y él
al tuyo.

**3. Quién puede usarlo.**
Cualquier explorador activo y sin sanción vigente, con un compañero también activo y sin
sanción.
<!-- fuente: solicitudes/services/validators/base_validator.py:13; solicitud_orchestrator.py:164-187 -->

**4. Cuándo se puede usar.**
A partir de mañana. Nunca para hoy ni para una fecha pasada. Tampoco si esa fecha ya está
dentro de una ventana de cierre semanal.
<!-- fuente: solicitudes/services/strategies/cambio_turno_strategy.py (fecha pasada y día en curso) -->
<!-- fuente: solicitudes/services/cierre_solicitudes_service.py -->

**5. Qué necesitas antes de empezar.**
La fecha y un compañero que ese día tenga la **jornada contraria** a la tuya. Conviene
haberlo hablado con él: será quien apruebe.

**6. Pasos numerados.**

1. Entra en la pantalla **Solicitud de Cambio de Turno**.
2. Selecciona la **Fecha del Cambio** en el calendario. Los días festivos aparecen
   marcados en rojo y los de mantenimiento en naranja.
   <!-- fuente: templates/solicitudes/solicitar_cambio_turno.html -->
3. Abre **Compañero para Intercambiar**. La lista se rellena sola con quienes pueden
   hacerlo esa fecha, y junto a cada nombre aparece su jornada.
   <!-- fuente: templates/solicitudes/solicitar_cambio_turno.html; static/js/cambio-turno/solicitar_cambio_turno.js -->
4. Si ya hay un cambio aprobado sobre esa fecha, se despliega el aviso **Cambio Aprobado
   Existente** con lo que ya está pactado.
   <!-- fuente: templates/solicitudes/solicitar_cambio_turno.html -->
5. Escribe el motivo en **Comentarios**.
6. Pulsa **Enviar Solicitud**. Aparece *"Enviando solicitud..."* y después la
   confirmación.
   <!-- fuente: static/js/cambio-turno/solicitar_cambio_turno.js -->

**7. Cada campo del formulario.**

| Campo visible | Qué se pone | ¿Obligatorio? | Valor por defecto | Qué cambia según elijas |
|---|---|---|---|---|
| **Fecha del Cambio** | Un día del calendario, desde mañana | Sí | Vacío | Determina qué compañeros aparecen |
| **Compañero para Intercambiar** | Un nombre de la lista | Sí | *Selecciona un compañero...* | Nada más; es el último dato |
| **Comentarios** | El motivo, hasta el límite del cuadro | Sí | Vacío | Nada |

<!-- fuente: templates/solicitudes/solicitar_cambio_turno.html -->

**8. Opciones y qué implica cada una.**

| Opción | Qué implica |
|---|---|
| Compañero con jornada PM (si tú eres AM) | Ese día tú trabajas PM y él AM |
| Compañero con jornada AM (si tú eres PM) | Ese día tú trabajas AM y él PM |
| Fecha festiva | No se acepta: en festivo una jornada trabaja completa y la otra descansa |

<!-- fuente: solicitudes/services/strategies/cambio_turno_strategy.py (rechazo de festivo) -->

**9. Qué valida la pantalla al momento.**

- El calendario no deja seleccionar fechas anteriores a mañana.
  <!-- fuente: solicitudes/views/cambio_turno_pages.py (_render_cambio_turno_normal) -->
- Al tocar un día de mantenimiento avisa: *"No se pueden realizar cambios de turno en días
  de mantenimiento. Por favor, selecciona otra fecha."*
  <!-- fuente: static/js/cambio-turno/solicitar_cambio_turno.js -->
- Si es tu descanso, el calendario lo dice: *"Es tu día de descanso por mantenimiento."* o
  *"Es tu día de descanso de la semana (temporada)."*
  <!-- fuente: static/js/cambio-turno/solicitar_cambio_turno.js -->
- Sin comentario no deja enviar: *"Debes ingresar un comentario para enviar la
  solicitud."*
  <!-- fuente: static/js/cambio-turno/solicitar_cambio_turno.js -->
- La lista de compañeros solo muestra a los disponibles para esa fecha.
  <!-- fuente: templates/solicitudes/solicitar_cambio_turno.html ("Solo se muestran compañeros disponibles para la fecha seleccionada") -->

**10. Qué valida el sistema al enviar.**

- Que no seas tú mismo y que ambos estéis activos.
  <!-- fuente: solicitudes/services/validators/base_validator.py:13,18 -->
- Que ninguno de los dos esté sancionado.
  <!-- fuente: solicitudes/services/solicitud_orchestrator.py:164-187 -->
- Que las jornadas sean contrarias ese día, mirando el estado **real** del día y no la
  jornada de la programación base.
  <!-- fuente: solicitudes/services/validators/ct_validator.py:37 -->
- Que la fecha no sea pasada ni el día en curso.
  <!-- fuente: solicitudes/services/strategies/cambio_turno_strategy.py -->
- Que ninguno de los dos tenga doblada ese día.
  <!-- fuente: solicitudes/services/strategies/cambio_turno_strategy.py -->
- Que no sea domingo intercambiado por día de semana, ni sábado por día de semana.
  <!-- fuente: solicitudes/services/validators/ct_validator.py:62,78 -->
- Que no sea día de mantenimiento.
  <!-- fuente: solicitudes/services/validators/base_validator.py:78 -->
- Que no exista ya otra solicitud pendiente tuya con esa persona para esa fecha.
  <!-- fuente: solicitudes/services/validators/base_validator.py:45 -->
- Que la fecha no caiga en una ventana de cierre semanal ya activa.
  <!-- fuente: solicitudes/services/cierre_solicitudes_service.py:148-166 -->
- Si hay una recomendación médica vigente, se muestra antes de continuar y hay que
  confirmar.
  <!-- fuente: solicitudes/services/solicitud_orchestrator.py:292-335 -->

**11. Qué pasa después de enviar.**
La solicitud queda **pendiente**. El sistema avisa al compañero y al supervisor dentro de
la aplicación y por correo. El mensaje de confirmación es: *"Solicitud enviada
correctamente. Se han enviado notificaciones al supervisor y al compañero."*
<!-- fuente: solicitudes/services/solicitud_orchestrator.py:674-677 -->

El turno no cambia hasta que las dos aprobaciones llegan. El tiempo depende de las
personas: el sistema no fija plazo.

**12. Cómo confirmar que quedó bien.**
Entra en **Mis Solicitudes**: debe aparecer la fila con estado **Pendiente**. Cuando pase
a **Aprobada**, ve a **Mis Turnos**: ese día mostrará la jornada nueva con la etiqueta
*Asignado* y, al tocarlo, el detalle dirá *Cambio de turno*.
<!-- fuente: templates/solicitudes/mis_solicitudes_list.html; static/js/mis_turnos.js:590-597 -->

**13. Cómo cancelar o deshacer.**
Mientras esté **Pendiente**, botón **Cancelar** en **Mis Solicitudes**, sin plazo. Ya
**Aprobada**, solo dentro de los **30 minutos** siguientes a la aprobación. Al cancelar,
las jornadas de ambos vuelven a como estaban.
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py -->

**14. Errores posibles.**

| Mensaje literal | Causa | Solución |
|---|---|---|
| "No se puede cambiar por la misma jornada. Los empleados deben tener jornadas contrarias" | Ambos tenéis AM, o ambos PM | Elige un compañero de la jornada contraria |
| "No se puede solicitar un cambio de turno para una fecha pasada." | La fecha ya pasó | Elige una futura |
| "No se puede solicitar un cambio de turno para hoy: el día ya está en curso. Elige a partir de mañana." | Seleccionaste hoy | Elige a partir de mañana |
| "No trabajas esa fecha (ese día descansas): no hay jornada para intercambiar. Elige otra fecha." | Ese día descansas | Elige otro día |
| "No se puede cambiar domingo por día de semana" | Mezclaste domingo con día de semana | Usa el formulario adecuado al fin de semana |
| "No se puede cambiar sábado por día de semana" | Mezclaste sábado con día de semana | Usa **Cambio de Día de Descanso** o **Doblada de Fin de Semana** |
| "No se puede hacer un cambio de turno en un día festivo. En festivo una jornada trabaja completa (AM+PM) y la otra descansa. Si necesitas intercambiar un festivo, hazlo con una Doblada (festivo por festivo)." | La fecha es festiva | Usa **Solicitud de Doblada** con festivo por festivo |
| "Tienes jornada doblada (AM + PM) en esta fecha. Este tipo de cambio no se puede realizar como Cambio de Turno Sencillo; debes usar la Solicitud de Dobladas." | Ese día ya doblas | Usa **Solicitud de Doblada** |
| "El compañero seleccionado tiene jornada doblada (AM + PM) en esta fecha. Este cambio no se puede hacer como Cambio de Turno Sencillo; debe gestionarse mediante la Solicitud de Dobladas." | El compañero dobla ese día | Elige otro compañero o usa **Solicitud de Doblada** |
| "No se pueden realizar cambios de turno en días de mantenimiento." | Ese día no hay operación | Elige otro día |
| "Ya existe una solicitud pendiente tuya con este explorador para la misma fecha" | Duplicado | Espera la resolución o cancélala |
| "No puedes solicitar cambio contigo mismo" | Te elegiste a ti | Elige a otra persona |
| "El empleado no está activo" | Tú o el compañero estáis inactivos | Habla con tu supervisor |

<!-- fuente: solicitudes/services/validators/ct_validator.py; base_validator.py; strategies/cambio_turno_strategy.py -->

**Ejemplo.**
María trabaja AM el martes 14/03 y necesita la tarde libre por una cita. Juan trabaja PM
ese mismo día. María entra en **Solicitud de Cambio de Turno**, elige el 14/03, selecciona
a *Juan (PM)*, escribe "cita médica en la tarde" y envía. Juan aprueba desde el correo esa
misma tarde y la supervisora aprueba al día siguiente. En **Mis Turnos** del 14/03, María
ve **PM** y Juan **AM**.

---

### 4.2 Cambio de turno permanente

**1. Nombre y cómo se llega.**
Pantalla **Solicitud de Cambio de Turno Permanente**.
Menú lateral → **Cambios de Turno** → tarjeta del cambio permanente → **Iniciar
Solicitud**.
<!-- fuente: templates/solicitudes/solicitar_ct_permanente.html; solicitudes/views/cambio_turno_pages.py (_render_ct_permanente) -->

**2. Para qué sirve.**
Repetir el mismo intercambio de jornada con un compañero varios días de la semana durante
un rango de fechas.

**3. Quién puede usarlo.**
Cualquier explorador activo y sin sanción, con un compañero de **jornada contraria**.
<!-- fuente: templates/solicitudes/solicitar_ct_permanente.html ("Solo se muestran compañeros con jornada contraria a la tuya") -->

**4. Cuándo se puede usar.**
A partir de mañana. El rango no puede empezar en el pasado y no puede durar **más de un
año**.
<!-- fuente: solicitudes/services/validators/ct_permanente_validator.py:51,65 -->

**5. Qué necesitas antes de empezar.**
La fecha de inicio, la de fin, los días de la semana afectados y el compañero. Solo se
puede de **lunes a viernes**.
<!-- fuente: templates/solicitudes/solicitar_ct_permanente.html -->

**6. Pasos numerados.**

1. Abre la pantalla **Solicitud de Cambio de Turno Permanente**.
2. Selecciona la **Fecha de Inicio**. En el calendario, los festivos van en rojo, los de
   mantenimiento en naranja y tus descansos en gris.
   <!-- fuente: templates/solicitudes/solicitar_ct_permanente.html -->
3. Selecciona la **Fecha de Fin**.
4. En **Seleccionar Días para el Cambio**, marca **Lunes**, **Martes**, **Miércoles**,
   **Jueves** o **Viernes**. Debajo se actualiza el **Total de días seleccionados**.
5. Elige el **Compañero para Intercambio Permanente**.
6. Revisa la vista previa: muestra las fechas concretas que quedarán afectadas.
   <!-- fuente: solicitudes/urls.py (previsualizar_ct_permanente); static/js/cambio-turno/solicitar_ct_permanente.js -->
7. Escribe **Comentarios**.
8. Pulsa **Enviar Solicitud de Cambio Permanente** y confirma en el aviso *"¿Estás seguro
   de que deseas enviar esta solicitud de cambio permanente?"*.
   <!-- fuente: static/js/cambio-turno/solicitar_ct_permanente.js -->

**7. Cada campo del formulario.**

| Campo visible | Qué se pone | ¿Obligatorio? | Valor por defecto | Qué cambia según elijas |
|---|---|---|---|---|
| **Fecha de Inicio** | Primer día del rango | Sí | Vacío | Habilita el resto del formulario |
| **Fecha de Fin** | Último día del rango | Sí | Vacío | Define cuántas fechas se generan |
| **Seleccionar Días para el Cambio** | Casillas de lunes a viernes | Sí, al menos una | Ninguna marcada | Determina las fechas concretas |
| **Compañero para Intercambio Permanente** | Un nombre de la lista | Sí | *Selecciona un compañero con jornada contraria...* | La vista previa se recalcula con sus días compatibles |
| **Comentarios** | El motivo | Sí | Vacío | Nada |

<!-- fuente: templates/solicitudes/solicitar_ct_permanente.html -->

**8. Opciones y qué implica cada una.**

| Opción | Qué implica |
|---|---|
| Marcar un día de la semana | Ese día se intercambia en todas las semanas del rango |
| Marcar varios días | Se acumulan; el total se muestra en pantalla |
| Rango que cruza festivos, mantenimientos, temporada o descansos | Esas fechas quedan excluidas automáticamente del cambio |
| Sábado o domingo | No están permitidos |

<!-- fuente: solicitudes/views/api_disponibles_ct_preview.py:331 (motivos de exclusión) -->
<!-- fuente: solicitudes/tests/test_politica_temporada.py (CT PERMANENTE no permite temporada) -->

**9. Qué valida la pantalla al momento.**

- Sin comentario: *"Debes ingresar un comentario para enviar la solicitud de cambio
  permanente."*
- Sin días marcados: *"Debe seleccionar al menos un día de la semana (lunes a viernes)
  para el cambio permanente."*
- Si el compañero elegido no sirve para ninguna fecha: *"No hay días compatibles con el
  compañero seleccionado. Por favor, selecciona otro compañero o ajusta el rango de
  fechas."*
- Si no hay nadie con jornada contraria: *"No hay compañeros disponibles con jornada
  contraria"*.
- La nota fija recuerda: *"Nota: Los cambios permanentes solo se pueden realizar de lunes a
  viernes. Sábados y domingos no están permitidos."*

<!-- fuente: static/js/cambio-turno/solicitar_ct_permanente.js; templates/solicitudes/solicitar_ct_permanente.html -->

**10. Qué valida el sistema al enviar.**

- Que la fecha de inicio no esté en el pasado y que exista fecha de fin posterior.
  <!-- fuente: solicitudes/services/validators/ct_permanente_validator.py:51-59 -->
- Que el rango no supere un año.
  <!-- fuente: solicitudes/services/validators/ct_permanente_validator.py:65 -->
- Que haya al menos un día marcado, y que todos sean de lunes a viernes.
  <!-- fuente: solicitudes/services/validators/ct_permanente_validator.py:142,149 -->
- Que en al menos una fecha del rango tengáis jornadas contrarias.
  <!-- fuente: solicitudes/services/validators/ct_permanente_validator.py:101 -->
- Que no exista ya otro cambio permanente solapado entre vosotros dos.
  <!-- fuente: solicitudes/services/validators/ct_permanente_validator.py:278 -->
- Que ninguna de las fechas caiga en una ventana de cierre semanal activa. El sistema
  calcula las fechas exactas del rango, no el rango entero.
  <!-- fuente: solicitudes/services/solicitud_orchestrator.py:82-111 -->
- Sanción, restricción médica y comentario, como en todos los formularios.

**11. Qué pasa después de enviar.**
Queda **pendiente**, con aviso al compañero y al supervisor. Al aprobarse, el cambio se
aplica día a día sobre las fechas válidas y el sistema informa de cuántas procesó:
*"Cambio permanente aplicado para N días"*.
<!-- fuente: solicitudes/services/strategies/ct_permanente_strategy.py:532 -->

**12. Cómo confirmar que quedó bien.**
En **Mis Solicitudes** verás una sola fila para todo el rango. Cuando esté **Aprobada**,
recorre **Mis Turnos** por los meses del rango: los días marcados mostrarán la jornada
nueva.

**13. Cómo cancelar o deshacer.**
Pendiente: **Cancelar** sin plazo. Aprobada: **30 minutos**. Al cancelar se revierten
todos los días del rango que aún no hayan pasado. Si algunos días ya se trabajaron y otros
no, la cancelación queda bloqueada y hay que hablar con el supervisor.
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (execute_supervisor, caso 4) -->

**14. Errores posibles.**

| Mensaje literal | Causa | Solución |
|---|---|---|
| "La fecha de inicio no puede ser en el pasado" | Empezaste antes de hoy | Elige una fecha futura |
| "La fecha fin es obligatoria para cambios permanentes" | Falta el final del rango | Indica la fecha de fin |
| "La fecha fin debe ser posterior a la fecha inicio" | El rango está invertido | Corrige las fechas |
| "El cambio permanente no puede durar más de un año." | Rango demasiado largo | Acorta el rango |
| "Debe seleccionar al menos un día de la semana (lunes a viernes) para el cambio permanente." | No marcaste ningún día | Marca al menos uno |
| "Los cambios permanentes solo se pueden realizar de lunes a viernes (0=Lunes, 4=Viernes)." | Hay un día de fin de semana | Desmárcalo |
| "No se pueden realizar cambios permanentes en domingos" | La fecha cae en domingo | Elige días de semana |
| "No se puede realizar el cambio permanente. No se encontraron días en el rango donde los empleados tengan jornadas contrarias. Los empleados deben tener jornadas opuestas (AM ↔ PM) en al menos un día del rango." | Tenéis la misma jornada todo el rango | Cambia de compañero o de fechas |
| "Ya existe un cambio permanente superpuesto entre estos empleados" | Duplicado con otro acuerdo vuestro | Ajusta el rango o cancela el anterior |
| "No se encontraron días válidos en el rango seleccionado. Todos los días quedan excluidos (fin de semana, festivo, mantenimiento, temporada, descanso, día ya comprometido o sin jornada contraria)." | Todas las fechas quedan fuera | Amplía o desplaza el rango |
| "No queda ningún día válido para aplicar el cambio permanente." | Igual que el anterior, detectado al aplicar | Vuelve a solicitarlo con otras fechas |

<!-- fuente: solicitudes/services/validators/ct_permanente_validator.py; strategies/ct_permanente_strategy.py; views/api_disponibles_ct_preview.py:331 -->

**Ejemplo.**
Carlos (AM) estudia los martes y jueves por la mañana entre el 01/04 y el 30/06. Elige ese
rango, marca **Martes** y **Jueves**, selecciona a *Lucía (PM)* y ve en la vista previa 26
fechas. Envía. Con las dos aprobaciones, todos esos martes y jueves Carlos trabaja PM y
Lucía AM; los festivos del rango quedan fuera automáticamente.

---

### 4.3 Cambio de día de descanso

**1. Nombre y cómo se llega.**
Pantalla **Cambio de Día de Descanso**, con el subtítulo *Intercambia tu descanso con un
compañero del grupo contrario*.
Menú lateral → **Cambios de Turno** → tarjeta del cambio de descanso → **Iniciar
Solicitud**.
<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html -->

**2. Para qué sirve.**
Intercambiar el día que descansas con un compañero. Funciona de dos maneras según el
selector **Modalidad**: **Fin de semana** y **Entre semana**.
<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html:39-49 -->

**3. Quién puede usarlo.**
Explorador activo y sin sanción. El compañero debe ser del **grupo contrario**: el que
descansa el día que tú trabajas.
<!-- fuente: solicitudes/services/strategies/cambio_descanso_strategy.py ("El compañero debe ser del grupo contrario…") -->

**4. Cuándo se puede usar.**

- Modalidad **Fin de semana**: siempre que la alternancia del mes esté publicada. La ida y
  la vuelta deben ser dos fines de semana **distintos del mismo mes**.
  <!-- fuente: solicitudes/services/strategies/cambio_descanso_strategy.py -->
- Modalidad **Entre semana**: solo en semanas con **descansos de temporada** cargados, y
  la compensación tiene que ser **en la misma semana**.
  <!-- fuente: solicitudes/services/strategies/cambio_descanso_strategy.py ("El intercambio de descansos de temporada debe ser en la MISMA semana…"; "El día de temporada modificado debe compensarse EN LA MISMA SEMANA. No se puede pagar en otra semana.") -->

En ambos casos, desde mañana en adelante.

**5. Qué necesitas antes de empezar.**
El mes, el día que quieres cambiar, el compañero y —en fin de semana— la semana de
devolución. En **Entre semana**, además, decidir cuál de las cinco opciones quieres.

**6. Pasos numerados.**

*Modalidad Fin de semana:*

1. Deja la **Modalidad** en **Fin de semana** (viene marcada por defecto).
2. Elige el **Mes**: verás todos sus fines de semana.
3. En **Semana que Cambias**, toca la semana donde trabajas y quieres intercambiar tu día.
4. Elige el **Compañero con quien intercambias**. La lista muestra compañeros del grupo
   contrario que trabajan el otro día de ese fin de semana.
5. En **Semana de Devolución**, elige otra semana del mismo mes donde trabajas el día
   contrario.
6. Escribe **Comentarios** y pulsa **Enviar Solicitud**.

<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html:52-79 -->

*Modalidad Entre semana:*

1. Pulsa **Entre semana** en **Modalidad**.
2. Elige el **Mes**: verás tus días de descanso de temporada.
3. En **Tu Descanso**, toca el día que quieres intercambiar. Debajo aparece el descanso
   del grupo contrario de esa misma semana.
4. En **¿Qué quieres hacer?**, elige una de las cinco opciones (ver punto 8).
5. Rellena el bloque que aparece según la opción elegida.
6. Elige el **Compañero**.
7. Escribe **Comentarios** y pulsa **Enviar Solicitud**.

<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html:82-224 -->

**7. Cada campo del formulario.**

| Campo visible | Qué se pone | ¿Obligatorio? | Valor por defecto | Qué cambia según elijas |
|---|---|---|---|---|
| **Modalidad** | **Fin de semana** o **Entre semana** | Sí | Fin de semana | Cambia todo el formulario |
| **Mes** | Un mes del desplegable | Sí | Mes en curso | Carga las semanas o los descansos |
| **Semana que Cambias** | Una semana (solo fin de semana) | Sí en esa modalidad | Ninguna | Habilita la lista de compañeros |
| **Compañero con quien intercambias** | Un nombre | Sí en fin de semana | *Selecciona un compañero…* | Habilita la devolución |
| **Semana de Devolución** | Otra semana del mismo mes | Sí en fin de semana | Ninguna | Puede mostrar el aviso de domingos impares |
| **Tu Descanso** | Un día de descanso de temporada | Sí en entre semana | Ninguno | Fija la semana del intercambio |
| **¿Qué quieres hacer?** | Una de las cinco opciones | Sí en entre semana | Ninguna | Muestra un bloque distinto |
| **¿Qué jornada trabajas TÚ los dos días?** | **AM (mañana)** o **PM (tarde)** | Solo en *Jornadas partidas* | Ninguna | Tu compañero trabaja la contraria |
| **¿Qué te cubren de tu día completo?** | **Solo AM**, **Solo PM** o **Día completo (2 compañeros)** | Solo en *Que me cubran mi día* | Ninguna | Determina cuántos compañeros hacen falta |
| **Día de pago (misma semana)** | Un día de la misma semana | Solo en *Que me cubran mi día* | Ninguno | Debe ser de la misma semana |
| **¿Con qué jornada pagas ese día?** | **AM** o **PM** | Solo si estás libre ese día y él trabaja las dos | Ninguna | Define qué le cubres |
| **Compañero que te cubre** / **Compañero que cubre la PM** | Nombres | Sí en cobertura | *Selecciona un compañero…* | Con dos compañeros se crean dos solicitudes |
| **Doblada de la semana que tomas** | Una doblada del desplegable | Solo en *Cambio de doblada* | *Cargando dobladas de la semana…* | Define quién toma tu día |
| **¿Qué media jornada trabajas tu día completo?** | **AM (mañana)** o **PM (tarde)** | Solo en *Permiso media jornada* | Ninguna | La otra media la trabajas en tu descanso |
| **Compañero** | Un nombre | Sí, salvo en permiso | *Selecciona un compañero…* | Es quien aprueba |
| **Comentarios** | El motivo | Sí | Vacío | Nada |

<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html -->

**8. Opciones y qué implica cada una.**

| Opción de **¿Qué quieres hacer?** | Qué implica |
|---|---|
| 🔁 **Intercambiar el día** | Cambias tu descanso por el del compañero: él toma tu día completo y tú el suyo. Sin deuda. |
| 🌗 **Jornadas partidas** | Uno va los 2 días en la mañana (AM) y el otro los 2 días en la tarde (PM). Sin deuda. |
| 🤝 **Que me cubran mi día** | Te cubren 1 jornada o las 2 de tu día completo y pagas en la **misma semana**. Deuda de 30 minutos solo para quien doble sobre su propia jornada. |
| ♻️ **Cambio de doblada** | Tomas la doblada que un compañero ya tiene esa semana y él toma tu día completo. Sin deuda, porque ambos ya doblaban. |
| 📋 **Permiso media jornada** | Trabajas media jornada tu día completo y la otra media tu día de descanso. Se aprueba como **PERMISO** por tu supervisor, sin pasar por un compañero. Sin deuda. |

<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html:116-135 -->

| Opción de cobertura | Qué implica |
|---|---|
| **Solo AM** | Un compañero cubre tu mañana |
| **Solo PM** | Un compañero cubre tu tarde |
| **Día completo (2 compañeros)** | Se crean **dos** solicitudes en un solo envío: o se crean las dos o ninguna. Después cada una se aprueba por separado. |

<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html:153-155,187-188 -->
<!-- fuente: solicitudes/services/solicitud_orchestrator.py:190-290 -->

**9. Qué valida la pantalla al momento.**

Avisos inmediatos, tal como aparecen:

- *"Selecciona la semana que cambias."*, *"Selecciona el compañero."*, *"Selecciona la
  semana de devolución."*
- *"Selecciona tu descanso (define la semana)."*, *"Elige qué quieres hacer esa semana."*
- *"Elige qué jornada trabajarás tú."*
- *"Elige qué te cubren (Solo AM, Solo PM o día completo con 2 compañeros)."*
- *"Elige el día de pago (misma semana)."*, *"Selecciona el compañero que te cubre."*,
  *"Selecciona el segundo compañero (cubre PM)."*
- *"Los dos compañeros deben ser personas distintas."*
- *"El día de pago ya trabajas AM+PM (doblada): no te queda jornada con la que pagar. Elige
  otro día."*
- *"En el día de pago tienes la misma jornada que el compañero: primero haz un Cambio de
  Turno sencillo."*
- *"Selecciona la doblada que tomas."*, *"Elige qué media jornada trabajas tu día."*
- *"Ingresa un comentario."*
- Si el mes tiene 5 domingos: *"Uno trabajará 3 domingos y el otro 2. Confirmen ambos antes
  de continuar."*
- Si no hay descanso contrario esa semana: *"Esta semana no hay un descanso del grupo
  contrario para intercambiar."*
- Si el mes no sirve: *"En este mes descansas todos los fines de semana o ya pasaron.
  Prueba con otro mes."*

<!-- fuente: static/js/cambio-turno/solicitar_cambio_descanso.js -->
<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html:105 -->

**10. Qué valida el sistema al enviar.**

En modalidad **Fin de semana**:

- Que el día que cambias y el de devolución sean fines de semana, distintos, futuros y del
  mismo tipo de día (sábado por sábado, domingo por domingo), para mantener el balance de
  domingos del mes.
  <!-- fuente: solicitudes/services/strategies/cambio_descanso_strategy.py -->
- Que el compañero sea del grupo contrario y que ninguno de los dos trabaje ya el día que
  va a recibir.
- Que no haya un cambio ya aplicado ese día ni un intercambio idéntico pendiente.

En modalidad **Entre semana**:

- Que ambos días sean de lunes a viernes, distintos y futuros.
- Que el descanso del compañero sea de la **misma semana** que el tuyo.
- Que esa semana tenga descansos de temporada configurados.
- Que la compensación sea en la misma semana.
- Que el compañero sea del grupo contrario y que ambos tengáis realmente ese descanso
  asignado.

<!-- fuente: solicitudes/services/strategies/cambio_descanso_strategy.py -->

Y en todos los casos: sanción, restricción médica, comentario y cierre semanal.

**11. Qué pasa después de enviar.**
Queda **pendiente** y se avisa al compañero y al supervisor. En la opción **Permiso media
jornada** el aviso va solo a tu supervisor y la confirmación dice *"Permiso enviado a tu
supervisor."*. Con dos compañeros, la confirmación es *"Se crearon las 2 solicitudes de
cobertura (AM y PM). Cada compañero la aprueba por separado."*
<!-- fuente: static/js/cambio-turno/solicitar_cambio_descanso.js; solicitudes/services/solicitud_orchestrator.py:286-290 -->

**12. Cómo confirmar que quedó bien.**
En **Mis Solicitudes**, la fila aparece con estado **Pendiente**. Con las dos aprobaciones,
en **Mis Turnos** los dos días afectados cambian y el detalle del día dice *Cambio de día
de descanso*. El día que pasa a ser descanso se marca con 😴, no con ☕: es un intercambio,
no una doblada.
<!-- fuente: static/js/mis_turnos.js:455,675-682 -->

**13. Cómo cancelar o deshacer.**
Pendiente: sin plazo. Aprobada: **30 minutos**. Al cancelar se revierten los dos días.
Este formulario tiene una regla propia: si sobre ese día hay un cambio de descanso
aprobado hace menos de 30 minutos, hay que cancelarlo primero.
<!-- fuente: solicitudes/services/strategies/cambio_descanso_strategy.py ("Ese día tiene un cambio de descanso reciente (dentro de los 30 min de aprobado)…") -->

Los intercambios **no se encadenan**: solo se cede el descanso de temporada original. Para
cambiar de nuevo, se cancela el anterior.

**14. Errores posibles.**

| Mensaje literal | Causa | Solución |
|---|---|---|
| "El día que cambias debe ser un fin de semana (sábado o domingo)" | Elegiste un día de semana en modalidad fin de semana | Cambia de día o de modalidad |
| "La devolución debe ser un fin de semana distinto al que cambias" | Ida y vuelta en el mismo fin de semana | Elige otra semana del mes |
| "El fin de semana que cambias debe ser posterior a hoy: el día en curso ya se está trabajando." | La fecha ya pasó o es hoy | Elige una futura |
| "El compañero debe ser del grupo contrario (el que descansa el otro día del fin de semana). No puedes intercambiar con alguien de tu mismo grupo." | Mismo grupo | Elige del otro grupo |
| "El día que cambias debe ser de lunes a viernes." | Elegiste fin de semana en modalidad entre semana | Cambia de modalidad |
| "El compañero solo puede descansar de lunes a viernes." | El descanso del compañero cae en fin de semana | Elige otro compañero |
| "El intercambio de descansos de temporada debe ser en la MISMA semana. Elige el descanso del grupo contrario de esa misma semana." | Los descansos son de semanas distintas | Elige el de la misma semana |
| "Esa semana no tiene descansos de temporada configurados." | El supervisor aún no los cargó | Habla con tu supervisor |
| "El día de temporada modificado debe compensarse EN LA MISMA SEMANA. No se puede pagar en otra semana." | El día de pago es de otra semana | Elige uno de la misma semana |
| "Los días deben ser distintos." | Elegiste el mismo día dos veces | Corrige |
| "Ya enviaste este intercambio de descanso (mismos días). Está pendiente de aprobación." | Duplicado | Espera la respuesta |
| "Ese día tiene un cambio de descanso reciente (dentro de los 30 min de aprobado). Cancélalo primero, o espera a que pase la ventana de cancelación para volver a intentar el intercambio." | Hay un cambio muy reciente | Cancélalo o espera |
| "Tu compañero ya tiene el día completo ocupado; no puede cubrirte." | El compañero ya trabaja AM y PM | Elige otro compañero |
| "Debes indicar qué jornada trabajarás tú ambos días (AM o PM)." | Falta el dato en jornadas partidas | Elige AM o PM |
| "Para que una sola persona tome tu día completo usa «Intercambiar el día». En «Que me cubran mi día» elige Solo AM, Solo PM, o día completo con 2 compañeros." | Opción incompatible | Cambia de opción |
| "Ya tienes una solicitud de cobertura pendiente para esa jornada de ese día." | Duplicado de cobertura | Espera la respuesta |
| "Selecciona el compañero que te cubre la jornada AM." | Falta el primer compañero en el modo de dos | Selecciónalo |
| "No se pudo crear la cobertura completa, no se creó ninguna solicitud." | Una de las dos coberturas falló la validación | Corrige y vuelve a enviar; no quedó nada a medias |

<!-- fuente: solicitudes/services/strategies/cambio_descanso_strategy.py; solicitud_orchestrator.py:190-290 -->

**Ejemplo.**
Ana trabaja el sábado 07/03 y descansa el domingo. Pedro, del grupo contrario, trabaja el
domingo 08/03. Ana entra en **Cambio de Día de Descanso**, deja la modalidad en **Fin de
semana**, elige marzo, toca la semana del 07/03, selecciona a *Pedro*, elige como **Semana
de Devolución** la del 21/03 y comenta "compromiso familiar". Con las dos aprobaciones,
Ana trabaja el domingo 08 y el sábado 21, y Pedro al revés. Ninguno de los dos gana ni
pierde domingos en el mes.

---

### 4.4 Doblada

**1. Nombre y cómo se llega.**
Pantalla **Solicitud de Doblada**.
Menú lateral → **Cambios de Turno** → tarjeta *Doblada* → **Iniciar Solicitud**.
<!-- fuente: templates/solicitudes/solicitar_doblada.html; solicitudes/views/cambio_turno_pages.py (_render_doblada) -->

**2. Para qué sirve.**
Que un compañero cubra tu jornada un día —doblándose él— y devolverle el favor doblándote
tú en otra fecha acordada.

**3. Quién puede usarlo.**
Explorador activo y sin sanción, con un compañero de **jornada contraria** ese día y
también sin sanción.
<!-- fuente: solicitudes/services/validators/doblada_validator.py:141,145 -->

**4. Cuándo se puede usar.**
Desde mañana. **Nunca en domingo** ni en día de mantenimiento. La fecha de pago es
obligatoria: no existen dobladas abiertas. Cesión y pago deben caer en el **mismo mes** y
no pueden ser el mismo día.
<!-- fuente: solicitudes/services/validators/doblada_validator.py:32,191,195 -->

**5. Qué necesitas antes de empezar.**
Las dos fechas acordadas —cesión y pago— y el compañero. Si el pago cae en sábado,
decidir qué mitad del sábado cubrirás.

**6. Pasos numerados.**

1. Abre la pantalla **Solicitud de Doblada**.
2. Selecciona la **Fecha de Cesión**: el día que no trabajarás.
3. Si ese día ya tienes doblada, aparece el bloque **Jornada a Ceder**: elige **Jornada AM
   (él conserva PM)** o **Jornada PM (él conserva AM)**.
   <!-- fuente: templates/solicitudes/solicitar_doblada.html -->
4. Elige el **Compañero que te Cubrirá**. Solo aparecen compañeros con jornada contraria
   disponibles para esa fecha. Se esconde a quien ese día ya queda trabajando la mañana y
   la tarde —pedirle la doblada sería un triple turno—, pero sí aparece quien ese día
   descansa por haber cedido su jornada en otra doblada, incluido quien descansa
   precisamente porque te cedió el día a ti.
   <!-- fuente: solicitudes/services/doblada_filtro_service.py:54-66,94-113 -->
5. Selecciona la **Fecha de Pago**: el día que devuelves el favor.
6. Si el pago cae en sábado y ese día tú estás libre pero tu compañero sí trabaja, aparece
   el aviso **Pago en Sábado** y debes indicar en **¿Qué mitad del sábado cubrirás tú?** la
   jornada que asumes: él trabaja la otra mitad. Si tu compañero también descansa ese
   sábado, ni el aviso ni esa pregunta aparecen, porque no hay ninguna jornada suya que
   cubrir; la **Vista Previa del Acuerdo** te dirá que esa fecha de pago no sirve.
   <!-- fuente: static/js/cambio-turno/solicitar_doblada.js (sincronizarSelectorPagoSabado) -->
7. Revisa la **Vista Previa del Acuerdo** antes de enviar: si el recuadro es azul
   (**Resumen del Acuerdo**), el acuerdo es válido; si es rojo (**No se puede enviar la
   solicitud**), corrige lo que indique el motivo.
   <!-- fuente: static/js/cambio-turno/solicitar_doblada.js (verificarCoincidenciaPago) -->
8. Si el compañero tiene doblada ese día, indica en **¿Qué jornada le cubres?** qué parte
   asumes.
9. Escribe **Comentarios** y pulsa **Enviar Solicitud**.

<!-- fuente: templates/solicitudes/solicitar_doblada.html; static/js/cambio-turno/solicitar_doblada.js -->

**7. Cada campo del formulario.**

| Campo visible | Qué se pone | ¿Obligatorio? | Valor por defecto | Qué cambia según elijas |
|---|---|---|---|---|
| **Fecha de Cesión** | Día que cedes, desde mañana | Sí | Vacío | Filtra la lista de compañeros |
| **Jornada a Ceder** | **Jornada AM (él conserva PM)** o **Jornada PM (él conserva AM)** | Solo si ese día doblas | Ninguna | Define qué mitad cedes |
| **Compañero que te Cubrirá** | Un nombre de la lista | Sí | *Selecciona un compañero...* | Determina qué fechas de pago son válidas |
| **Fecha de Pago** | Día en que devuelves, mismo mes | Sí | Vacío | Puede abrir los selectores de jornada |
| **¿Qué mitad del sábado cubrirás tú?** | **AM (Mañana)** o **PM (Tarde)** | Solo si el pago es sábado, tú estás libre ese día y el compañero sí trabaja | Ninguna | Define tu carga ese sábado <!-- fuente: static/js/cambio-turno/solicitar_doblada.js (sincronizarSelectorPagoSabado) --> |
| **¿Qué jornada le cubres?** | AM, PM o toda la doblada | Solo si él dobla ese día | Ninguna | Define cuánto asumes |
| **Comentarios** | El motivo | Sí | Vacío | Nada |

<!-- fuente: templates/solicitudes/solicitar_doblada.html -->

**8. Opciones y qué implica cada una.**

| Opción | Qué implica |
|---|---|
| Pago **antes** de la cesión | Permitido, siempre que sea el mismo mes |
| Pago **después** de la cesión | Permitido, mismo mes |
| Pago el **mismo día** que la cesión | No permitido |
| **Intercambiar mi doblada por la de un compañero** | Eliges como fecha de pago el día de la doblada de él. No se cede jornada: cada uno toma la doblada del otro. <!-- fuente: templates/solicitudes/solicitar_doblada.html --> |
| Cesión y pago en **festivo** | Solo si ambas fechas son festivos del mismo mes <!-- fuente: solicitudes/services/validators/doblada_validator.py:240 --> |
| Pago en **sábado** | Debes elegir qué mitad cubres; si cubres las dos, hay que fijar además un día de la semana de devolución <!-- fuente: solicitudes/services/strategies/doblada_strategy.py --> |
| Pago en **sábado en el que el compañero descansa** | No sirve como fecha de pago: no hay jornada suya que cubrir. No se te pide la mitad del sábado y la vista previa lo rechaza <!-- fuente: static/js/cambio-turno/solicitar_doblada.js; solicitudes/services/doblada_pago_service.py:100 --> |
| Cesión y pago **sábado por sábado** | No permitido: para eso está la doblada de fin de semana |
| Compañero que ese día **trabaja mañana y tarde** | No aparece en la lista: ya está doblado y no puede asumir otra jornada <!-- fuente: solicitudes/services/doblada_filtro_service.py:94-113 --> |
| Compañero que ese día **descansa por haber cedido su jornada** | Sí aparece: tiene el día libre y puede cubrirte <!-- fuente: solicitudes/services/doblada_filtro_service.py:54-66 --> |

**9. Qué valida la pantalla al momento.**

- Marca los días imposibles y explica por qué: *"Es tu día de descanso por
  mantenimiento."*, *"Es tu día de descanso de la semana (temporada)."*, *"Descansas este
  día por una solicitud aprobada."*, *"Ese día cediste tu jornada a un compañero, así que
  estás libre."*
- *"Trabajarías dos veces la misma jornada ese día. Haz un cambio de turno primero."*
- *"El receptor se encuentra descansando ese día. No puedes pagarle en esta fecha. Debes
  elegir otra fecha de pago."*
- *"Los dos están descansando. No se puede realizar el pago en esa fecha."*
- *"Ya tienes una doblada (AM + PM) en la fecha de pago; no te queda jornada libre para
  pagar ahí. Elige otra fecha."*
- *"Ese sábado ya está comprometido como pago por otra doblada tuya. Elige otro día de
  pago."*
- *"La fecha de pago es un festivo. La fecha de cesión también debe ser un festivo del
  mismo mes."*
- *"El comentario es obligatorio. Explica el motivo de la doblada."*
- *"Indica qué jornada (AM o PM) del compañero cubres en la fecha de pago."*
- En el modo de intercambio: *"Solo aparecen compañeros que tienen una doblada (AM + PM)
  ese día."* y *"El día de la doblada del compañero debe ser distinto al de la tuya."*

En cuanto completas **Fecha de Pago** y **Compañero que te Cubrirá**, la **Vista Previa del
Acuerdo** se pronuncia: si el acuerdo es válido verás el recuadro azul **Resumen del
Acuerdo**; si el sistema ya sabe que lo rechazará, verás en su lugar un recuadro rojo **No
se puede enviar la solicitud** con el motivo, sin tener que pulsar **Enviar Solicitud** para
enterarte. Ocurre, por ejemplo, cuando los dos descansan en la fecha de pago, cuando el
compañero descansa ese día o cuando ese día ambos tenéis la misma jornada.
<!-- fuente: static/js/cambio-turno/solicitar_doblada.js (verificarCoincidenciaPago) -->

Si el pago cae en sábado, el aviso **Pago en Sábado** y la pregunta por la mitad solo
aparecen cuando el compañero sí trabaja ese sábado. Si él descansa, no aparecen: no existe
mitad que repartir.
<!-- fuente: static/js/cambio-turno/solicitar_doblada.js (sincronizarSelectorPagoSabado) -->

<!-- fuente: static/js/cambio-turno/solicitar_doblada.js -->

**10. Qué valida el sistema al enviar.**

- Que exista fecha de pago, distinta de la de cesión y del mismo mes.
  <!-- fuente: solicitudes/services/validators/doblada_validator.py:32; base_validator.py:220 -->
- Que ambos tengáis jornada asignada esas fechas y que sean contrarias.
  <!-- fuente: solicitudes/services/validators/doblada_validator.py:120,134,141,145 -->
- Que el compañero no tenga ya doblada el día de la cesión.
  <!-- fuente: solicitudes/services/validators/doblada_validator.py:164 -->
- Que la fecha no sea domingo ni día de mantenimiento.
  <!-- fuente: solicitudes/services/validators/doblada_validator.py:191,195 -->
- Que no estéis los dos descansando el día de pago y que él sí trabaje ese día.
  <!-- fuente: solicitudes/services/validators/doblada_validator.py:265,288 -->
- Que él no haya cedido ya su jornada ese día.
  <!-- fuente: solicitudes/services/validators/doblada_validator.py:330 -->
- Que ninguno de los dos tenga otra solicitud pendiente que afecte a esos días.
  <!-- fuente: solicitudes/services/validators/base_validator.py:259,298,345,350 -->
- Que el año del sábado de pago tenga publicada la alternancia de fines de semana.
  <!-- fuente: solicitudes/services/strategies/doblada_strategy.py -->
- Sanción, restricción médica, comentario y cierre semanal.

**11. Qué pasa después de enviar.**
Queda **pendiente**, con aviso al compañero y al supervisor: *"Solicitud enviada
correctamente. Se han enviado notificaciones al supervisor y al compañero."*
<!-- fuente: solicitudes/services/solicitud_orchestrator.py:674-677 -->

Al aprobarse, el día de la cesión te queda libre y el de pago queda registrado como tu
devolución. Las condiciones se vuelven a comprobar en ese momento: si entre el envío y la
aprobación el compañero dejó de trabajar el sábado de pago, la solicitud no se aplica y se
avisa con *"&lt;Nombre&gt; no trabaja el sábado DD/MM/AAAA: ese día descansa, así que no hay
jornada suya que cubrir y no se le puede pagar la doblada. La doblada debe rehacerse con otra
fecha de pago."* Ese aviso lo ve quien aprueba, no tú: por eso no pide elegir una fecha, sino
que deja constancia de que la solicitud debe volver a enviarse con otra fecha de pago.
<!-- fuente: solicitudes/services/doblada_pago_service.py:144 -->

La misma comprobación se aplica cuando el pago cae **entre semana**. Si al aplicarse la
doblada resulta que el compañero descansa ese día, el sistema se detiene y avisa con
*"&lt;Nombre&gt; &lt;Apellido&gt; no trabaja el DD/MM/AAAA: ese día descansa, así que no
tiene una jornada que cubrirle para pagar la doblada. La doblada debe rehacerse con otra
fecha de pago."* Antes, en algunos casos, la doblada seguía adelante y le dejaba a esa
persona un turno en un día libre sin que nadie se enterara.
<!-- fuente: solicitudes/services/doblada_pago_service.py:302,536 -->

Rellenando el formulario no deberías toparte con este aviso: al enviar ya se comprueba que
el compañero trabaje la fecha de pago. Aparece sobre todo cuando ese día cambió entre el
envío y la aprobación, o cuando un administrador rehace una doblada por su cuenta.

**12. Cómo confirmar que quedó bien.**
En **Mis Solicitudes**, estado **Pendiente** y luego **Aprobada**. En **Mis Turnos**, el
día de la cesión aparece con ☕ (día libre) y el de pago como **DOBLADA (AM + PM)** entre
semana o **DÍA COMPLETO (AM + PM)** en fin de semana.
<!-- fuente: static/js/mis_turnos.js:459,742 -->

**13. Cómo cancelar o deshacer.**
Pendiente: sin plazo. Aprobada: **30 minutos**. Si uno de los dos días ya se trabajó y el
otro no, la cancelación se bloquea; en ese caso el supervisor puede usar **Reprogramar**
para reasignar el día que falta.
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (execute_supervisor, caso 4) -->

**14. Errores posibles.**

| Mensaje literal | Causa | Solución |
|---|---|---|
| "La fecha de pago es obligatoria. No existen dobladas abiertas." | No indicaste cuándo devuelves | Acuerda la fecha y ponla |
| "Para ceder jornada AM, el receptor debe tener jornada PM." | Jornadas iguales | Busca un compañero contrario |
| "Para ceder jornada PM, el receptor debe tener jornada AM." | Jornadas iguales | Busca un compañero contrario |
| "El receptor no puede tener doblada el día de la cesión." | Ya se dobla ese día | Otro compañero u otra fecha |
| "No se puede realizar doblada en domingos" | La fecha es domingo | Elige otro día |
| "No se puede realizar doblada en días de mantenimiento" | Ese día no hay operación | Elige otro día |
| "Los dos están descansando en la fecha de pago. No se puede realizar el pago en esa fecha. Elige otra fecha de pago." | Ninguno trabaja ese día | Cambia la fecha de pago |
| "El solicitante no tiene jornada asignada para esa fecha" | Falta tu programación | Avisa al supervisor |
| "El receptor no tiene jornada asignada para esa fecha" | Falta su programación | Avisa al supervisor |
| "No puedes hacer una doblada de sábado por sábado. Para intercambiar sábados usa una Doblada de Fin de Semana (D FDS)." | Ambas fechas son sábado | Usa **Doblada de Fin de Semana** |
| "Los cambios y pagos de dobladas entre festivos solo se permiten cuando ambas fechas pertenecen al mismo mes." | Festivos de meses distintos | Elige festivos del mismo mes |
| "Para intercambiar, debes tener una DOBLADA (AM+PM) el …" | Intentaste el intercambio sin tener doblada | Usa el modo normal de cesión |
| "Para intercambiar dobladas, el día A y el día B deben ser distintos." | Misma fecha en ambos lados | Cambia una |
| "El año … aún no tiene publicada la alternancia de fines de semana, así que no se puede saber quién trabaja ese sábado. Pídele al supervisor que la publique." | Falta la programación anual | Avisa al supervisor |
| "Para pagar en sábado debes seleccionar una jornada válida (AM, PM o ambas)." | Falta la mitad del sábado | Elige AM, PM o ambas |
| "Al cubrir ambas jornadas el sábado, debes elegir el día de la semana en que el compañero te devolverá la jornada." | Falta el día de devolución en semana | Selecciónalo |
| "&lt;Nombre&gt; no trabaja el sábado DD/MM/AAAA: ese día descansa, así que no hay jornada suya que cubrir y no se le puede pagar la doblada. La doblada debe rehacerse con otra fecha de pago." | Al aprobarse, el compañero ya no trabaja ese sábado (cambió su programación o cedió el día). Lo ve quien aprueba | Envía la solicitud de nuevo con otra fecha de pago |
| "&lt;Nombre&gt; &lt;Apellido&gt; no trabaja el DD/MM/AAAA: ese día descansa, así que no tiene una jornada que cubrirle para pagar la doblada. La doblada debe rehacerse con otra fecha de pago." | Al aplicarse la doblada, el compañero ya no trabaja esa fecha de pago entre semana. Lo ve quien aprueba | Envía la solicitud de nuevo con otra fecha de pago |
| "El día de pago en semana debe ser de lunes a viernes." | Elegiste fin de semana | Corrige |
| "El día de pago en semana no puede ser festivo ni de mantenimiento." | Fecha no operativa | Elige otra |
| "Ya tienes una solicitud pendiente que afecta el … (como cesión o como pago). Debes esperar a que sea aprobada o cancelada antes de enviar otra que use ese día." | Solapamiento con otra solicitud tuya | Espera o cancela la anterior |
| "El compañero ya tiene una solicitud pendiente que afecta el … Debe esperar a que sea aprobada o cancelada antes de enviar una nueva que use ese día." | Solapamiento del compañero | Espera o elige a otro |

<!-- fuente: solicitudes/services/validators/doblada_validator.py; base_validator.py; strategies/doblada_strategy.py -->

**Ejemplo.**
Diego (AM) necesita el jueves 12/03 libre. Sofía trabaja PM ese día. Diego abre
**Solicitud de Doblada**, pone como **Fecha de Cesión** el 12/03, elige a *Sofía* y como
**Fecha de Pago** el lunes 23/03, cuando ella trabaja AM y él PM. Comenta "viaje
familiar". Aprobado todo, el 12/03 Diego tiene ☕ y Sofía **DOBLADA (AM + PM)**; el 23/03,
al revés.

---

### 4.5 Doblada permanente

**1. Nombre y cómo se llega.**
Pantalla **Doblada Permanente**.
Menú lateral → **Cambios de Turno** → tarjeta de doblada permanente → **Iniciar
Solicitud**.
<!-- fuente: templates/solicitudes/solicitar_doblada_permanente.html -->

**2. Para qué sirve.**
Repetir el acuerdo de doblada durante un rango de fechas, pudiendo repartir la cobertura
entre varios compañeros.

**3. Quién puede usarlo.**
Explorador activo y sin sanción, con uno o varios compañeros de jornada contraria y
también sin sanción en ese rango.
<!-- fuente: solicitudes/services/strategies/doblada_permanente_strategy.py -->

**4. Cuándo se puede usar.**
El rango no puede empezar en el pasado y debe estar **dentro del mismo mes**. Solo de
**lunes a viernes**.
<!-- fuente: solicitudes/services/strategies/doblada_permanente_strategy.py -->

**5. Qué necesitas antes de empezar.**
El rango de fechas, qué días cede cada compañero y qué días le devuelves a cada uno. Por
cada compañero, la cuenta debe cuadrar exactamente.

**6. Pasos numerados.**

1. Abre la pantalla **Doblada Permanente**.
2. Indica **Desde** y **Hasta**. Hasta que no pongas la fecha de inicio, la lista de
   compañeros muestra *"Primero elige la fecha de inicio para cargar los compañeros."*
   <!-- fuente: templates/solicitudes/solicitar_doblada_permanente.html -->
3. En **Días que cedes — te cubre un compañero**, pulsa **Agregar día de cesión** por cada
   día y asigna su compañero.
4. En **Días en que devuelves — tú te doblas**, pulsa **Agregar día de devolución** y
   asigna el mismo compañero que te cubre.
5. Marca las fechas concretas dentro de cada día.
6. Revisa la vista previa de fechas.
   <!-- fuente: solicitudes/urls.py (previsualizar_doblada_permanente, dias_disponibles_doblada_permanente) -->
7. Escribe el **Comentario** y pulsa **Enviar Solicitud**.

**7. Cada campo del formulario.**

| Campo visible | Qué se pone | ¿Obligatorio? | Valor por defecto | Qué cambia según elijas |
|---|---|---|---|---|
| **Desde** | Primer día del rango | Sí | Vacío | Carga la lista de compañeros |
| **Hasta** | Último día del rango, mismo mes | Sí | Vacío | Define las fechas disponibles |
| **Días que cedes — te cubre un compañero** | Filas de día + compañero | Sí, al menos una | Ninguna | Define quién te cubre |
| **Días en que devuelves — tú te doblas** | Filas de día + compañero | Sí | Ninguna | Debe cuadrar con la cesión |
| Fechas concretas de cada fila | Casillas de las fechas del rango | Sí | Ninguna marcada | El recuento debe coincidir por compañero |
| **Comentario** | El motivo | Sí | Vacío | Nada |

<!-- fuente: templates/solicitudes/solicitar_doblada_permanente.html -->

**8. Opciones y qué implica cada una.**

| Opción | Qué implica |
|---|---|
| Un solo compañero | Se crea **una** solicitud |
| Varios compañeros | Se crea **una solicitud por compañero**, y todas se validan antes de crear ninguna: o se crean todas o ninguna |
| Una fecha asignada a dos compañeros | No permitido, ni en cesión ni en devolución |
| Una fecha como cesión y como devolución a la vez | No permitido: ese día no puedes descansar y doblarte |
| Fechas en fin de semana | No permitidas; para eso está la doblada de fin de semana |

<!-- fuente: solicitudes/services/solicitud_orchestrator.py:396-439,547-572 -->

**9. Qué valida la pantalla al momento.**

- *"Selecciona el rango de fechas (Desde y Hasta)."*
- *"Agrega al menos un día de cesión con su compañero."*
- *"Cada día de cesión debe tener un compañero."*
- *"Agrega al menos un día de devolución."* y *"Cada día de devolución debe tener un
  compañero."*
- *"Un día no puede ser de cesión y de devolución a la vez."*
- *"Tienes dos filas con el mismo día y el mismo compañero. Usa compañeros distintos para
  el mismo día, o quita la fila repetida."*
- *"Marca al menos una fecha en los días que cedes."* y *"Marca al menos una fecha en los
  días que devuelves."*
- *"Ajusta las fechas: por cada compañero, las que te cubre y las que devuelves deben ser
  iguales."*
- *"Solo puedes devolverle a un compañero que te cubra."*
- *"Ingresa un comentario."*
- Si hay recomendación médica: *"Hay una restricción médica vigente. ¿Continuar de todos
  modos?"*

<!-- fuente: static/js/cambio-turno/solicitar_doblada_permanente.js -->

**10. Qué valida el sistema al enviar.**

- Que exista rango completo, que el fin sea posterior al inicio, que no empiece en el
  pasado y que ambas fechas sean del mismo mes.
  <!-- fuente: solicitudes/services/strategies/doblada_permanente_strategy.py -->
- Que solo haya días de lunes a viernes.
- Que ningún día sea a la vez de cesión y de devolución.
- Que por cada compañero el número de fechas cedidas y devueltas sea idéntico.
  <!-- fuente: solicitudes/services/solicitud_orchestrator.py:487-493 -->
- Que una misma fecha no esté asignada a dos compañeros.
  <!-- fuente: solicitudes/services/solicitud_orchestrator.py:396-420 -->
- Que solo devuelvas a quien te cubre.
  <!-- fuente: solicitudes/services/solicitud_orchestrator.py:483-486 -->
- Que ni tú ni ningún compañero estéis sancionados en el rango.
- Que en cada fecha tengáis jornadas contrarias según el estado real del día, y que no
  caiga en festivo, fin de semana, mantenimiento, temporada, descanso, día libre ni un día
  ya doblado.
  <!-- fuente: solicitudes/services/strategies/doblada_permanente_strategy.py -->
- Que el compañero no tenga ya otra doblada permanente en esas fechas.
- Que ninguna fecha caiga en una ventana de cierre semanal activa.
  <!-- fuente: solicitudes/services/solicitud_orchestrator.py:441-455 -->

**11. Qué pasa después de enviar.**
Con un solo compañero: *"Doblada permanente solicitada. Se notificó al compañero y al
supervisor."* Con varios: *"Se crearon N solicitudes de doblada permanente (una por
compañero). Se notificó a cada uno y al supervisor."*
<!-- fuente: solicitudes/services/solicitud_orchestrator.py:566-572 -->

Cada solicitud se aprueba por separado, con sus dos aprobaciones.

**12. Cómo confirmar que quedó bien.**
En **Mis Solicitudes** verás una fila por compañero. Al aprobarse, recorre **Mis Turnos**
por el rango: los días cedidos aparecen con ☕ y los de devolución como **DOBLADA (AM +
PM)**.

**13. Cómo cancelar o deshacer.**
Pendiente: sin plazo. Aprobada: **30 minutos**, y se revierte el rango completo. Si ya se
trabajó parte del rango, la cancelación se bloquea y el supervisor debe usar
**Reprogramar** para los días que faltan.
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py -->

Cancelar la solicitud de un compañero no cancela las de los demás: son solicitudes
independientes.

**14. Errores posibles.**

| Mensaje literal | Causa | Solución |
|---|---|---|
| "El rango de fechas (inicio y fin) es obligatorio" | Falta una fecha | Complétalas |
| "La fecha de fin debe ser posterior a la fecha de inicio" | Rango invertido | Corrige |
| "El rango no puede iniciar en el pasado" | Empieza antes de hoy | Elige fechas futuras |
| "El rango debe estar dentro del mismo mes: la fecha de inicio y la de fin deben caer en el mismo mes." | Rango a caballo entre meses | Divídelo en dos solicitudes |
| "La doblada permanente es solo de lunes a viernes (no aplica fines de semana). Para intercambiar un sábado usa una Doblada de Fin de Semana." | Hay fines de semana | Quítalos |
| "Un mismo día de la semana no puede ser de cesión y de devolución a la vez. Revisa los días seleccionados." | Día duplicado en los dos lados | Reasigna |
| "Debes devolver la misma cantidad de fechas que te cubren…" | Las cuentas no cuadran | Ajusta las fechas |
| "A cada compañero debes devolverle la misma cantidad de fechas que te cubre." | Desbalance por compañero | Ajusta ese compañero |
| "Solo puedes devolverle a un compañero que te cubra." | Devolución a quien no te cubre | Corrige la asignación |
| "La fecha … está asignada a dos compañeros; una fecha solo puede cubrirla un compañero (no puedes cubrir ni pagar la misma jornada el mismo día con dos personas)." | Fecha repetida entre compañeros | Deja un solo compañero por fecha |
| "El … lo tienes como día que cedes y como día que devuelves a la vez. Ese día no puedes descansar y doblarte al mismo tiempo, aunque sean compañeros distintos." | Cruce entre cesión y devolución | Reasigna la fecha |
| "Estás sancionado en ese rango de fechas; no puedes crear la solicitud." | Tienes sanción | Habla con tu supervisor |
| "… está sancionado en ese rango. Elige otro compañero o ajusta las fechas." | El compañero está sancionado | Cambia de compañero |
| "… ya tiene una doblada permanente en esas fechas. Elige otras fechas u otro compañero." | Solapamiento | Ajusta |
| "Estas fechas ya no son válidas para la doblada: … Ese día tú y el compañero deben tener jornadas CONTRARIAS (AM↔PM) según su jornada real, y no puede caer en festivo, fin de semana, mantenimiento, temporada, descanso, día libre ni un día ya doblado." | Fechas no aptas | Ajusta las fechas o el compañero |
| "Agrega al menos un día de cesión con su compañero" | Formulario vacío | Añade filas |
| "Compañero no válido." | El compañero seleccionado ya no existe | Recarga y vuelve a elegir |

<!-- fuente: solicitudes/services/strategies/doblada_permanente_strategy.py; solicitud_orchestrator.py -->

**Ejemplo.**
Laura necesita libres los lunes y miércoles de mayo. Pone **Desde** 04/05 y **Hasta**
29/05, agrega *lunes → Andrés* y *miércoles → Beatriz* en la cesión, y en la devolución
agrega *martes → Andrés* y *jueves → Beatriz*, marcando cuatro fechas en cada fila para
que las cuentas cuadren. Envía y el sistema crea **2 solicitudes**, una para Andrés y otra
para Beatriz.

---

### 4.6 Doblada de fin de semana

**1. Nombre y cómo se llega.**
Pantalla **Doblada de Fin de Semana**, abreviada **D FDS**.
Menú lateral → **Cambios de Turno** → tarjeta correspondiente → **Iniciar Solicitud**.
<!-- fuente: templates/solicitudes/solicitar_d_fds.html; solicitudes/views/cambio_turno_pages.py (_render_d_fds) -->

**2. Para qué sirve.**
Ceder tu día de fin de semana a un compañero que ese día descansa, y devolverle el favor
otro fin de semana del mismo mes trabajando el día que a él le toca.

**3. Quién puede usarlo.**
Explorador activo y sin sanción. El compañero debe **descansar** el día que cedes: por eso
puede trabajarlo.
<!-- fuente: templates/solicitudes/solicitar_d_fds.html ("Compañeros que descansan el día que cedes (por eso pueden trabajarlo).") -->

**4. Cuándo se puede usar.**
Desde mañana. Ida y devolución deben ser **fines de semana distintos del mismo mes** y del
**mismo día de la semana**: sábado por sábado, domingo por domingo.
<!-- fuente: solicitudes/services/strategies/d_fds_strategy.py -->

**5. Qué necesitas antes de empezar.**
El mes, el día de fin de semana que cedes, el compañero y el fin de semana de devolución.

**6. Pasos numerados.**

1. Abre la pantalla **Doblada de Fin de Semana**.
2. Elige el mes: verás todos sus fines de semana.
3. En **Fin de Semana que Cedes**, toca el día que trabajas y quieres ceder. Si trabajas
   los dos días del fin de semana, puedes ceder cualquiera de ellos.
   <!-- fuente: templates/solicitudes/solicitar_d_fds.html -->
4. Elige el **Compañero que Trabajará tu Día**. Cada tarjeta indica si sirve y, si no, por
   qué.
5. En **Fin de Semana de Devolución (Pago)**, elige otro fin de semana del mismo mes,
   mismo día, donde cubres a tu compañero.
6. Escribe **Comentarios** y pulsa **Enviar Solicitud**.

**7. Cada campo del formulario.**

| Campo visible | Qué se pone | ¿Obligatorio? | Valor por defecto | Qué cambia según elijas |
|---|---|---|---|---|
| Mes | Un mes del desplegable | Sí | Mes en curso | Carga los fines de semana |
| **Fin de Semana que Cedes** | Un sábado o domingo que trabajas | Sí | Ninguno | Filtra los compañeros posibles |
| **Compañero que Trabajará tu Día** | Un nombre de la lista | Sí | *Selecciona un compañero…* | Filtra los fines de semana de pago |
| **Fin de Semana de Devolución (Pago)** | Otro fin de semana del mes, mismo día | Sí | Ninguno | Define cuándo doblas tú |
| **Comentarios** | El motivo | Sí | Vacío | Nada |

<!-- fuente: templates/solicitudes/solicitar_d_fds.html -->

**8. Opciones y qué implica cada una.**

| Opción | Qué implica |
|---|---|
| Ceder un sábado | La devolución debe ser otro sábado del mismo mes |
| Ceder un domingo | La devolución debe ser otro domingo del mismo mes |
| Trabajar los dos días del fin de semana | Puedes ceder cualquiera de los dos |
| Mes con 5 sábados o 5 domingos | El reparto puede no quedar exactamente igual; la pantalla lo advierte <!-- fuente: templates/solicitudes/solicitar_d_fds.html --> |

**9. Qué valida la pantalla al momento.**

- *"Selecciona el fin de semana que cedes."*
- *"Selecciona el compañero que trabajará tu día."*
- *"Selecciona el fin de semana de devolución (pago)."*
- *"Ingresa un comentario."*
- Si el mes no sirve: *"En este mes no hay ningún día de fin de semana que puedas ceder.
  Prueba otro mes."*
- Si ese compañero no encaja en ningún fin de semana: *"Ningún finde de este mes sirve para
  pagarle a este compañero."* y *"Prueba con otro compañero o revisa los motivos en cada
  tarjeta."*
- En cada tarjeta descartada, el motivo: *"ya trabaja los dos días de ese finde"*, *"ya
  trabaja ese sábado"* o *"solo tiene media jornada"*.

<!-- fuente: static/js/cambio-turno/solicitar_d_fds.js; solicitudes/services/strategies/base_strategy.py -->

**10. Qué valida el sistema al enviar.**

- Que ambas fechas sean fines de semana, distintas, futuras y del mismo día de la semana.
  <!-- fuente: solicitudes/services/strategies/d_fds_strategy.py -->
- Que tengas realmente un turno que ceder ese día y no solo media jornada.
- Que el compañero no trabaje ya ese día: debe estar libre para cubrirte.
- Que en la fecha de pago el compañero sí trabaje, y con jornada completa.
- Que tú no trabajes ya la fecha de pago ni la hayas cedido a otro.
- Sanción, restricción médica, comentario y cierre semanal.

**11. Qué pasa después de enviar.**
Queda **pendiente**, con aviso al compañero y al supervisor. La confirmación es *"Solicitud
de doblada de fin de semana enviada correctamente."*
<!-- fuente: static/js/cambio-turno/solicitar_d_fds.js -->

**12. Cómo confirmar que quedó bien.**
En **Mis Solicitudes**, la fila cambia a **Aprobada**. En **Mis Turnos**, el día cedido
aparece libre y el de pago como **DÍA COMPLETO (AM + PM)**. Además, este trámite se refleja
en **Mis Favores**, que lleva la cuenta de los días de fin de semana que te cubrieron y los
que cubriste tú.
<!-- fuente: templates/solicitudes/mis_favores.html; static/js/mis_turnos.js:742 -->

**13. Cómo cancelar o deshacer.**
Pendiente: sin plazo. Aprobada: **30 minutos**. Si el fin de semana cedido ya pasó y el de
pago no, la cancelación se bloquea y el supervisor puede **Reprogramar**.
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py -->

**14. Errores posibles.**

| Mensaje literal | Causa | Solución |
|---|---|---|
| "La fecha de fin de semana es requerida" | No elegiste el día que cedes | Selecciónalo |
| "La fecha de pago es obligatoria (otro fin de semana del mismo mes)" | Falta la devolución | Elige otro fin de semana |
| "La fecha de cesión debe ser un fin de semana (sábado o domingo)" | Elegiste un día de semana | Corrige |
| "La fecha de cesión debe ser posterior a hoy: no se puede ceder un fin de semana pasado ni el día en curso." | Fecha pasada o de hoy | Elige una futura |
| "La fecha de pago no puede ser la misma que la fecha de cesión" | Misma fecha en ambos lados | Cambia una |
| "Cediste un sábado: la devolución (pago) también debe ser un sábado, para que ambos conserven la misma cantidad de sábados en el mes." | Mezclaste sábado y domingo | Empareja el mismo día |
| "No tienes un turno que ceder el …" | Ese día no trabajas | Elige otro |
| "Tu compañero ya trabaja el …; no tiene ese día libre para cubrirte. Elige a alguien que descanse ese día." | El compañero ya trabaja | Elige a otro |
| "Tu compañero no trabaja el … ; no hay día que cubrir." | Ese día él descansa | Cambia la fecha de pago |
| "No puedes pagar el …: ese día ya trabajas y no puedes doblarte de nuevo. Elige un fin de semana en el que ese mismo día descanses." | Ya trabajas la fecha de pago | Elige otra |
| "No puedes pagar el …: ese día ya se lo cediste a un compañero y él lo está cubriendo. Elige otro fin de semana." | Fecha ya comprometida | Elige otra |
| "Debe seleccionar el compañero que se doblará el fin de semana" | Falta el compañero | Selecciónalo |

<!-- fuente: solicitudes/services/strategies/d_fds_strategy.py -->

**Ejemplo.**
Marta trabaja el sábado 07/03 y quiere ese día libre. Raúl descansa ese sábado. Marta abre
**Doblada de Fin de Semana**, elige marzo, toca el sábado 07, selecciona a *Raúl* y como
devolución el sábado 21/03, día que él trabaja y ella descansa. Comenta "matrimonio de un
familiar". Aprobado, Raúl trabaja el 07 y Marta el 21; ambos conservan el mismo número de
sábados del mes.

---

## 5. Diccionario de opciones

Referencia rápida de los valores que aparecen en los formularios.

| Campo o etiqueta | Valor | Qué significa elegirlo |
|---|---|---|
| Jornada | **AM (Mañana)** | Trabajas la mañana |
| Jornada | **PM (Tarde)** | Trabajas la tarde |
| Jornada mostrada en el calendario | **DOBLADA** | Trabajas AM y PM el mismo día entre semana |
| Jornada mostrada en el calendario | **DÍA COMPLETO (AM + PM)** | Lo mismo, pero en sábado o domingo |
| Jornada mostrada en el calendario | **DESCANSO** | No trabajas por programación |
| Jornada mostrada en el calendario | **DÍA LIBRE** | No trabajas porque cediste tu jornada en una doblada |
| Etiqueta bajo la jornada | **Asignado** | La jornada viene de un acuerdo aprobado |
| Etiqueta bajo la jornada | **Predeterminado** | Es tu programación normal |
| Modalidad de cambio de descanso | **Fin de semana** | Intercambias el día del fin de semana que trabajas, con devolución en otro fin de semana del mismo mes |
| Modalidad de cambio de descanso | **Entre semana** | Intercambias un día de descanso de temporada, compensando en la misma semana |
| ¿Qué quieres hacer? | **Intercambiar el día** | Él toma tu día completo y tú el suyo. Sin deuda |
| ¿Qué quieres hacer? | **Jornadas partidas** | Uno hace AM los dos días y el otro PM los dos días. Sin deuda |
| ¿Qué quieres hacer? | **Que me cubran mi día** | Te cubren una o las dos jornadas y pagas en la misma semana |
| ¿Qué quieres hacer? | **Cambio de doblada** | Tomas la doblada que él ya tenía y él toma tu día. Sin deuda |
| ¿Qué quieres hacer? | **Permiso media jornada** | Media jornada tu día completo y media tu descanso; lo aprueba solo el supervisor |
| ¿Qué te cubren? | **Solo AM** / **Solo PM** | Un compañero cubre esa mitad |
| ¿Qué te cubren? | **Día completo (2 compañeros)** | Dos solicitudes en un solo envío, todo o nada |
| Jornada a ceder en doblada | **Jornada AM (él conserva PM)** | Cedes tu mañana |
| Jornada a ceder en doblada | **Jornada PM (él conserva AM)** | Cedes tu tarde |
| Estado de solicitud | **Pendiente** | Falta al menos una aprobación |
| Estado de solicitud | **Aprobada** | Ya se aplicó al calendario |
| Estado de solicitud | **Rechazada** | Alguien la rechazó |
| Estado de solicitud | **Cancelada** | Se dio de baja |
| Filtro de Mis Favores | **Te cubrieron** / **Se lo devolviste** | Días de fin de semana que otro trabajó por ti y los que devolviste |
| Filtro de Mis Favores | **Cubriste a** / **Te lo devolvió** | Días que trabajaste por otro y los que él te devolvió |

<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html; solicitar_doblada.html; templates/turnos/mis_turnos.html; templates/solicitudes/mis_favores.html; templates/solicitudes/mis_solicitudes_list.html -->

Marcas en el calendario mensual: 😴 descanso · ☕ día libre por doblada · 📋 permiso
aprobado · ⏳ permiso pendiente · 🚫 restricción · ⚖️ sanción.
<!-- fuente: static/js/mis_turnos.js:455-560 -->

Colores del calendario de los formularios: **rojo** día festivo, **naranja** día de
mantenimiento, **gris** día de descanso.
<!-- fuente: templates/solicitudes/solicitar_cambio_turno.html; solicitar_ct_permanente.html -->

---

## 6. Sobre cómo el sistema entiende tus turnos

Este apartado explica el porqué. No hay pasos que seguir.

### 6.1 Última aprobada gana por día

El estado de un día es siempre **el último acuerdo aprobado que lo modifica**. Los cambios
no se encadenan ni se acumulan: cuando se aprueba uno nuevo sobre el mismo día, el
anterior deja de estar vigente.
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (bloqueo_lifo) -->

De ahí sale una consecuencia práctica que sorprende a mucha gente: para deshacer, hay que
empezar por el más reciente. Si intentas cancelar un cambio antiguo teniendo otro más nuevo
encima, el sistema lo impide, porque revertirlo pisaría el reciente y dejaría el calendario
en un estado que no corresponde a ningún acuerdo real.

Hay una segunda protección. Aunque no exista otra solicitud posterior, el sistema compara
el estado actual del día con el que dejó la solicitud que quieres cancelar. Si alguien lo
modificó por otra vía —un permiso, una reprogramación, un ajuste del supervisor—, la
cancelación se bloquea y la solicitud sigue vigente. La salida es solicitar un cambio
nuevo, no forzar la marcha atrás.
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (bloqueo_integridad) -->

### 6.2 Sobre los días de descanso de temporada

En temporada el supervisor fija días de descanso concretos entre semana. Esos días tienen
una protección especial: **solo el formulario Cambio de Día de Descanso puede tocarlos**.
Ningún otro trámite los modifica, ni siquiera los que sí pueden operar durante una semana
de temporada.
<!-- fuente: solicitudes/tests/test_politica_temporada.py -->

La razón es la compensación. Cuando se mueve un descanso de temporada, la devolución tiene
que ocurrir **en la misma semana**; una doblada, que puede pagar en cualquier fecha del
mes, no lo garantiza.
<!-- fuente: solicitudes/services/strategies/cambio_descanso_strategy.py -->

El alcance de esta protección es acotado: veta dos fechas por semana, no la temporada
entera. Durante una semana de temporada puedes seguir haciendo dobladas y cambios de turno
sencillos en el resto de los días.

Dos formularios no funcionan en absoluto durante la temporada: el **cambio de turno
permanente** y la **doblada permanente**.
<!-- fuente: solicitudes/tests/test_politica_temporada.py -->

### 6.3 Qué se revierte al cancelar y en qué plazo

Los seis formularios revierten lo que hicieron cuando se cancelan. Revertir significa
devolver los turnos de las dos personas al estado exacto que tenían antes, y deshacer
también las deudas y coberturas que el acuerdo hubiera generado.

Los plazos son dos y no se mezclan:

- **Pendiente**: puedes cancelar cuando quieras. Nada se había aplicado, así que no hay
  nada que revertir.
- **Aprobada**: solo dentro de los **30 minutos** siguientes a la aprobación. Pasado ese
  margen, el turno se considera comunicado y en firme.

<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (VENTANA_CANCELACION_MINUTOS = 30) -->

El supervisor no tiene esa ventana de 30 minutos, pero sí las mismas protecciones sobre
los datos. Si todos los días de un acuerdo ya se trabajaron, puede cerrarlo sin revertir:
el historial se conserva tal cual. Si unos días ya pasaron y otros no, no puede hacer
ninguna de las dos cosas y la salida es reprogramar el día que falta.
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (execute_supervisor) -->

### 6.4 Sobre el cierre semanal

El supervisor puede fijar un día y una hora a partir de los cuales la programación de un
fin de semana queda cerrada. Desde ese momento no se aceptan solicitudes nuevas cuyas
fechas caigan dentro de la ventana cerrada, que va desde el día de cierre hasta el primer
día hábil de la semana siguiente.
<!-- fuente: solicitudes/services/cierre_solicitudes_service.py -->

El cierre solo afecta a la **creación** de solicitudes. Lo ya aprobado sigue su curso y las
acciones del supervisor no pasan por esta comprobación.
<!-- fuente: solicitudes/services/cierre_solicitudes_service.py:11 -->

### 6.5 Sobre las dos aprobaciones y la revalidación

Una solicitud pasa primero por el compañero y después por el supervisor. En el momento de
cada aprobación el sistema vuelve a comprobar las reglas: si la situación cambió desde que
se envió —una sanción nueva, un turno modificado— la aprobación no se realiza y verás el
motivo.
<!-- fuente: solicitudes/services/solicitud_aprobacion_service.py ("No se puede aprobar: …") -->

Cuando eso ocurre, el aviso que lees empieza por "No se puede aprobar: la solicitud ya no
es válida con el estado actual." y a continuación cita el motivo entre la palabra
**Motivo:** y la aclaración "(instrucciones dirigidas a quien la envió)".
<!-- fuente: solicitudes/services/solicitud_aprobacion_service.py:130-134 -->

Ese motivo está redactado para quien envió la solicitud, no para ti. Por eso suena a orden
—"Elige otra fecha de pago.", "Elige otro día de la semana."— y por eso va entre
paréntesis la aclaración: tú no puedes cambiar nada de una solicitud ya enviada.
<!-- fuente: solicitudes/services/solicitud_aprobacion_service.py:123-129 -->

Lo que te toca hacer es **rechazar** la solicitud. Al rechazarla, tu compañero recibe el
aviso y puede volver a enviarla corrigiendo lo que indica el motivo. El propio texto
termina diciéndotelo: "Recházala para que pueda rehacerse."
<!-- fuente: solicitudes/services/solicitud_aprobacion_service.py:130-134 -->

Por eso conviene aprobar pronto y no dejar solicitudes semanas pendientes.

Los enlaces de **Aprobar** y **Rechazar** que llegan por correo caducan a los 30 días desde
que se envió el correo. Pasado ese plazo el enlace deja de funcionar y muestra una página de
error; la solicitud sigue existiendo y se resuelve entrando a la aplicación.
<!-- fuente: solicitudes/services/tokens_aprobacion.py (_max_age_segundos); config/settings.py:262 (APPROVAL_LINK_MAX_AGE_DAYS, por defecto 30) -->

---

## 7. Mensajes de error y qué hacer

Hay dos cosas distintas que se parecen. Un **aviso dentro de un formulario** aparece sin
salir de la pantalla en la que estás. Una **pantalla de error a página completa** sustituye
todo lo que había: solo se ve un título grande, una explicación y dos botones.

### 7.1 Avisos dentro de los formularios

Los mensajes propios de cada formulario están en su ficha, punto 14. Aquí van los que
pueden aparecer en cualquiera de los seis.

| Mensaje literal | Qué significa | Qué hacer |
|---|---|---|
| "Estás sancionado del dd/mm/aaaa al dd/mm/aaaa. Durante la sanción no puedes realizar solicitudes de cambio de turno ni de permisos." | Tienes una sanción vigente | Habla con tu supervisor <!-- fuente: empleados/sancion_utils.py (mensaje_sancion) --> |
| "El compañero … está sancionado y no puede participar en la solicitud. Elige otro compañero o espera a que termine su sanción." | La sanción de tu compañero le impide participar | Elige a otra persona <!-- fuente: solicitudes/services/solicitud_orchestrator.py:183-186 --> |
| "Cierre de solicitudes activo: desde el … a las hh:mm la programación del fin de semana ya está cerrada; no se pueden enviar solicitudes para el dd/mm/aaaa." | La ventana de cierre ya se activó | Habla con tu supervisor <!-- fuente: solicitudes/services/cierre_solicitudes_service.py:159-164 --> |
| "Hay una restricción médica vigente en las fechas. Revisa la nota antes de continuar." | Hay una recomendación médica en esas fechas | Lee la nota y confirma si procede <!-- fuente: solicitudes/services/solicitud_orchestrator.py:332 --> |
| "Hay una restricción médica vigente en el rango. Revisa la nota antes de continuar." | Lo mismo, en un trámite con rango de fechas | Igual que el anterior <!-- fuente: solicitudes/services/solicitud_orchestrator.py:510 --> |
| "Ya se está procesando esta solicitud. Espera unos segundos antes de reintentar." | Pulsaste enviar dos veces | Espera unos segundos y revisa **Mis Solicitudes** <!-- fuente: solicitudes/services/solicitud_orchestrator.py:77-79 --> |
| "Debe seleccionar un compañero para el intercambio" | Falta el compañero | Selecciónalo <!-- fuente: solicitudes/services/solicitud_orchestrator.py:643 --> |
| "El compañero seleccionado no existe." | La persona ya no está disponible | Recarga la página y vuelve a elegir <!-- fuente: solicitudes/services/solicitud_orchestrator.py:648 --> |
| "Ingresa un comentario." | Falta el motivo | Escríbelo <!-- fuente: solicitudes/services/solicitud_orchestrator.py:372 --> |
| "Debes ingresar un comentario para …" | Lo mismo, con el nombre del trámite | Escríbelo <!-- fuente: solicitudes/services/validators/base_validator.py:190 --> |
| "Error al procesar la solicitud" | Fallo interno; no es culpa de tus datos | Reinténtalo; si persiste, avisa a tu supervisor <!-- fuente: solicitudes/services/solicitud_orchestrator.py:25 --> |
| "Ocurrió un error de red. Intenta de nuevo." | El envío no llegó a completarse | Comprueba **Mis Solicitudes** antes de reenviar. Si el aviso incluye un **Código de referencia**, apúntalo: ver el apartado 7.3 <!-- fuente: static/js/cambio-turno/solicitar_d_fds.js:442; solicitar_doblada_permanente.js:705 --> |
| "Intenta de nuevo." bajo el título *Error de red* | Lo mismo, en **Cambio de Día de Descanso** | Igual que el anterior <!-- fuente: static/js/cambio-turno/solicitar_cambio_descanso.js:1328,1362,1382 --> |
| "Ocurrió un error de red." | Lo mismo, en **Cambio de Turno Permanente** y en **Doblada** | Igual que el anterior <!-- fuente: static/js/cambio-turno/solicitar_ct_permanente.js:1748; solicitar_doblada.js:2862 --> |
| "Ocurrió un error al procesar la solicitud" | El envío de **Cambio de Turno** falló y el sistema no devolvió un motivo concreto | Comprueba **Mis Solicitudes** antes de reenviar <!-- fuente: static/js/cambio-turno/solicitar_cambio_turno.js:421 --> |
| "Ya no es posible cancelar esta solicitud. Solo se puede cancelar dentro de los 30 minutos posteriores a su aprobación (han pasado N minutos)." | Se acabó la ventana | Habla con tu supervisor <!-- fuente: solicitudes/use_cases/cancelar_solicitud.py --> |
| "No puedes cancelar este cambio: hay otro más reciente sobre el mismo día (dd/mm). Cancela primero el cambio más reciente." | Los cambios se deshacen en orden inverso | Cancela primero el más nuevo <!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (bloqueo_lifo) --> |
| "No se puede cancelar: el turno de … ya fue modificado por otro cambio posterior a esta aprobación. Cancelar ahora dejaría un conflicto de jornadas, así que esta solicitud se mantiene vigente. Si necesitas volver a tu turno original, solicita un nuevo cambio de turno." | Alguien tocó ese día por otra vía | Solicita un cambio nuevo <!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (_mensaje_conflicto) --> |
| "Solo puedes cancelar tus propias solicitudes" | Intentaste cancelar la de otra persona | Pídeselo a quien la creó <!-- fuente: solicitudes/use_cases/cancelar_solicitud.py --> |
| "Solicitud no encontrada" | La solicitud ya no existe | Recarga **Mis Solicitudes** <!-- fuente: solicitudes/use_cases/cancelar_solicitud.py --> |
| "Esta solicitud fue cancelada y ya no puede ser aprobada" | Se canceló antes de que aprobaras | Nada que hacer <!-- fuente: solicitudes/services/solicitud_aprobacion_service.py --> |
| "Esta solicitud ya fue aprobada" / "Esta solicitud ya fue rechazada" | Alguien se te adelantó | Nada que hacer <!-- fuente: solicitudes/services/solicitud_aprobacion_service.py --> |
| "Ya habías aprobado esta solicitud como compañero." | Doble clic en aprobar | Ninguna acción <!-- fuente: solicitudes/services/solicitud_aprobacion_service.py --> |
| "No tienes permisos para aprobar esta solicitud" | No eres ni el compañero ni el supervisor | Avisa a quien corresponda <!-- fuente: solicitudes/services/solicitud_aprobacion_service.py --> |
| "Estás sancionado y no puedes aceptar ni participar en solicitudes de cambio de turno." | Te sancionaron mientras la solicitud estaba pendiente | Habla con tu supervisor <!-- fuente: solicitudes/services/solicitud_aprobacion_service.py --> |
| "No se puede aprobar: la solicitud ya no es válida con el estado actual. Motivo: … (instrucciones dirigidas a quien la envió). Recházala para que pueda rehacerse." | Lo ves al aprobar: la situación cambió desde que se envió la solicitud y ya no cumple las reglas. El motivo citado está escrito para quien la envió, no para ti | Recházala; tu compañero podrá enviarla de nuevo corregida. Ver el apartado 6.5 <!-- fuente: solicitudes/services/solicitud_aprobacion_service.py:130-134 --> |
| "No se puede aprobar: … está sancionado y no puede participar en la solicitud." | Uno de los dos fue sancionado después de enviarla | Se resuelve al levantar la sanción <!-- fuente: solicitudes/services/solicitud_aprobacion_service.py --> |
| "Token inválido o expirado" | El enlace de **Aprobar** o **Rechazar** del correo ya no sirve. La propia página lista las cuatro causas posibles: han pasado más de 30 días desde que recibiste el correo, el enlace se copió mal o fue modificado, el enlace no era para ti (o te cambiaron de supervisor después de enviarse), o la solicitud ya fue procesada. La página se titula "No se pudo procesar la solicitud" | Entra a la aplicación y resuelve la solicitud desde **Notificaciones** o **Gestión de Solicitudes**: el enlace del correo no es la única forma de aprobar o rechazar. La propia página te lo indica y te ofrece los botones **Ir al Dashboard** y **Ver Notificaciones**. Si en el recuadro **Detalles del Error** ves un **Código de referencia**, apúntalo antes de salir: ver el apartado 7.3 <!-- fuente: solicitudes/views/aprobacion_email.py:102,161,220,272; templates/solicitudes/error_token.html:41-72; core/utils/error_token.py (dias_validez, request_id) --> |
| "No pudimos completar la operación por un fallo interno. El equipo de desarrollo ya tiene el registro del error." | En la misma página "No se pudo procesar la solicitud": el enlace del correo era válido, pero algo falló por dentro al procesarlo | Resuelve la solicitud desde **Notificaciones** o **Gestión de Solicitudes**. Apunta el **Código de referencia** del recuadro y repórtalo <!-- fuente: core/utils/error_token.py:32-35 (MENSAJE_INESPERADO) --> |
| "No se encontró supervisor para esta solicitud" | En la misma página: la solicitud no tiene supervisor asignado a quien atribuir la decisión | Avisa a tu supervisor o al administrador <!-- fuente: solicitudes/views/aprobacion_email.py:108,159 --> |
| "Usuario o contraseña incorrectos. Verifica tus datos e inténtalo de nuevo." | Credenciales erróneas | Reintenta; tras 5 fallos hay bloqueo de 1 hora <!-- fuente: core/login/template/login.html; config/settings.py:330-331 --> |
| "Tu usuario no está vinculado a un explorador." | Tu cuenta no tiene ficha de persona asociada | Avisa al administrador <!-- fuente: templates/solicitudes/mis_favores.html --> |
| "En este momento no hay tipos de solicitud configurados en el sistema." | Falta configurar los tipos | Avisa a tu supervisor <!-- fuente: templates/solicitudes/cambio_turno_inicio.html --> |

**Cuando falla la consulta de datos de una pantalla.** Estos avisos no hablan de tus datos:
salen cuando la aplicación intenta traer información y algo se rompe de forma inesperada.
Los avisos de validación normales de esas mismas pantallas (por ejemplo "Formato de fecha
inválido" o "Debe seleccionar una fecha") no cambian y siguen apareciendo igual.
<!-- fuente: core/utils/json_responses.py:67-100 (json_error_inesperado) -->

| Mensaje literal | Cuándo sale | Qué hacer |
|---|---|---|
| "No pudimos cargar los festivos. Inténtalo de nuevo." | Al cargar los festivos del año en los calendarios y selectores de fecha | Reinténtalo. Si persiste, reporta la hora y la pantalla <!-- fuente: turnos/api/views/dias_especiales.py:188 --> |
| "No pudimos cargar los días de temporada. Inténtalo de nuevo." | Al consultar los días de temporada | Igual que el anterior <!-- fuente: turnos/api/views/dias_especiales.py:265 --> |
| "No pudimos cargar los días especiales. Inténtalo de nuevo." | Al consultar los días especiales de un tipo concreto | Igual que el anterior <!-- fuente: turnos/api/views/dias_especiales.py:354 --> |
| "No pudimos cargar los turnos de ese día. Inténtalo de nuevo." | Al elegir una fecha para ver quién trabaja en la mañana o en la tarde | Elige la fecha otra vez; si persiste, reinténtalo más tarde <!-- fuente: turnos/api/views/turnos_mes.py:24 --> |
| "No pudimos calcular las jornadas de ese rango. Inténtalo de nuevo." | Al previsualizar un rango de fechas en **Cambio de Turno Permanente** y **Doblada Permanente** | Vuelve a fijar el rango. No se envió nada, así que no hay solicitud a medias <!-- fuente: solicitudes/views/api_turno_jornada.py:555 --> |
| "No pudimos calcular los días de mantenimiento. Inténtalo de nuevo." | Solo supervisores, en el mantenimiento anual | Reinténtalo; si persiste, reporta la hora <!-- fuente: turnos/api/views/calculo_automatico.py:80 --> |
| "No pudimos calcular los festivos del año. Inténtalo de nuevo." | Solo supervisores, al generar los festivos del año | Igual que el anterior <!-- fuente: turnos/api/views/calculo_automatico.py:132 --> |
| "No se pudo reenviar la notificación. Código de referencia: …" | Solo supervisores, en **Gestión de Solicitudes**, al reenviar una notificación | La solicitud sigue pendiente y no se duplicó nada. Apunta el código y reinténtalo pasados unos segundos <!-- fuente: solicitudes/views/gestion_solicitudes.py:183-184 --> |

En los siete primeros, el código de referencia viaja junto con la respuesta; que llegue a
verse en pantalla depende de cómo presente el aviso cada formulario. En el último, el
código va escrito dentro del propio mensaje rojo.
<!-- fuente: core/utils/json_responses.py:96-100 (extra.request_id); solicitudes/views/gestion_solicitudes.py:183-184 -->

### 7.2 Pantallas de error a página completa

Cuando algo impide seguir, la aplicación ya no te deja en una página en blanco ni te
enseña una pantalla técnica en inglés. Ves una de estas cinco pantallas, escritas en
español y con el aspecto de SWALP.
<!-- fuente: templates/errors/_base_error.html; core/errors.py:114-164 (handlers 400/403/404/500 y csrf_failure) -->

Todas comparten la misma estructura: una etiqueta con el tipo de error, el título en
grande, un párrafo que explica qué pasó, un recuadro con la recomendación, los botones
**Ir al inicio** y **Volver atrás**, y al pie el **Código de referencia**.
<!-- fuente: templates/errors/_base_error.html (bloques eyebrow, heading, lede, hint, actions, meta) -->

**Ir al inicio** te lleva al panel de entrada. **Volver atrás** te devuelve a la pantalla
anterior; si llegaste directamente, sin haber visitado antes otra página, ese botón no se
muestra porque no tendría a dónde volver.
<!-- fuente: templates/errors/_base_error.html (href="/dashboard/"; window.history.length <= 1 → back.hidden) -->

Las pantallas se adaptan solas a modo claro y modo oscuro según la configuración de tu
equipo o tu teléfono, y se ven bien en pantalla pequeña. Si has pedido reducir las
animaciones, no se mueve nada.
<!-- fuente: templates/errors/_base_error.html (prefers-color-scheme, prefers-reduced-motion, @media min-width:840px) -->

#### "Esta página no está en la grilla"

Etiqueta: *Error 404 · No encontrado*. Aparece cuando la dirección a la que has llegado no
corresponde a ninguna sección: el enlace está mal escrito, la página se movió, o el
registro que buscabas ya no existe.
<!-- fuente: templates/404.html (heading, lede) -->

Texto que verás: *"La dirección a la que has llegado no corresponde a ninguna sección de
SWALP. Puede que el enlace esté mal escrito, que la página se haya movido o que el registro
que buscabas ya no exista."*

Qué hacer:

1. Pulsa **Ir al inicio** y navega hasta la sección desde el menú, o pulsa **Volver atrás**.
2. Si llegaste desde un enlace de la propia aplicación o de un correo, avisa al equipo de
   desarrollo indicando desde dónde hiciste clic, para que puedan corregir ese enlace.
   Incluye el código de referencia.
   <!-- fuente: templates/404.html (bloque hint) -->

#### "No tienes permiso para entrar aquí"

Etiqueta: *Error 403 · Acceso denegado*. Tu usuario está bien identificado, pero su rol no
incluye el acceso a esa sección. **No es un fallo del sistema**: es la configuración de
permisos haciendo su trabajo.
<!-- fuente: templates/403.html (heading, lede) -->

Qué hacer: si crees que deberías tener acceso, habla con tu supervisor para que revise los
permisos asignados a tu rol en **Administración → Roles y Permisos**.
<!-- fuente: templates/403.html (bloque hint) -->

#### "Tu sesión expiró antes de enviar el formulario"

Etiqueta: *Error 403 · Verificación fallida*. Aparece al enviar un formulario desde una
pestaña que llevaba demasiado tiempo abierta. Por seguridad, la aplicación comprueba que
cada envío venga de una sesión activa y de la propia aplicación.
<!-- fuente: templates/403_csrf.html (heading, lede); core/errors.py:154-164 (csrf_failure) -->

Lo primero que debes saber: **no se guardó nada**. La solicitud no se creó a medias.
<!-- fuente: templates/403_csrf.html ("Esa comprobación no ha pasado, así que no se guardó nada") -->

Qué hacer:

1. Inicia sesión de nuevo.
2. Repite el envío desde el principio.
3. Comprueba que tu navegador acepte cookies para este sitio: sin ellas la verificación
   fallará siempre.
   <!-- fuente: templates/403_csrf.html (bloque hint) -->

#### "Algo se rompió por nuestro lado"

Etiqueta: *Error 500 · Fallo interno*. Se produjo un fallo inesperado del servidor al
procesar tu petición. No es culpa tuya ni de los datos que escribiste.
<!-- fuente: templates/500.html (heading, lede) -->

**Antes de repetir nada: si estabas registrando una solicitud, entra en Mis Solicitudes y
comprueba si llegó a guardarse.** Puede haberse creado justo antes del fallo, y repetirla
te dejaría dos solicitudes iguales.
<!-- fuente: templates/500.html (bloque hint) -->

Si no aparece, vuelve a enviarla. Si el fallo se repite, reporta el código de referencia.

#### "No pudimos interpretar esta petición"

Etiqueta: *Error 400 · Petición incorrecta*. Los datos que llegaron al servidor no tienen
el formato esperado, así que la petición se descartó sin procesarla. Suele pasar con
enlaces manipulados o con formularios que quedaron abiertos demasiado tiempo.
<!-- fuente: templates/400.html (heading, lede) -->

Qué hacer: empieza de nuevo desde el menú. Vuelve al inicio y navega hasta la sección que
necesitas en lugar de reutilizar el enlace anterior.
<!-- fuente: templates/400.html (bloque hint) -->

### 7.3 El código de referencia: lo único que necesitas apuntar

El código aparece en tres sitios: al pie de las pantallas de error a página completa,
dentro de los avisos emergentes que salen al enviar una solicitud, y en la página que ves
al abrir un enlace de **Aprobar** o **Rechazar** del correo que ya no sirve.

#### En las pantallas a página completa

Al pie de cada una de esas cinco pantallas verás **Código de referencia** seguido de una
cadena de 12 caracteres, por ejemplo `A3F91C2B7D01`, y un botón **Copiar**. Al pulsarlo, el
botón cambia a **Copiado** durante un par de segundos.
<!-- fuente: templates/errors/_base_error.html (bloque meta, botón data-copy, texto 'Copiado'); core/errors.py:68 -->

**Cuando reportes una incidencia al equipo de desarrollo, incluye ese código.** Es la
información más útil que puedes dar: con él, el equipo localiza exactamente qué falló en tu
caso concreto, entre todas las peticiones que atiende el sistema. Sin el código, investigar
el reporte es mucho más difícil.
<!-- fuente: core/errors.py:18-29 (el identificador se adjunta a todas las líneas de registro de esa petición) -->

Cada caso tiene su propio código: es distinto cada vez, aunque el error sea el mismo, así
que cópialo antes de cerrar la pantalla o de volver atrás.
<!-- fuente: core/errors.py:68 (se genera uno nuevo por petición, aleatorio) -->

Estas pantallas **no muestran detalles técnicos a propósito**. No es que se haya perdido
información: el detalle completo del fallo se envía de forma automática al equipo de
desarrollo en el mismo momento en que ocurre. Por eso no tienes que copiar mensajes raros,
ni hacer capturas de pantallas llenas de texto en inglés, ni describir con precisión qué
estabas haciendo. Con el código de referencia basta.
<!-- fuente: core/errors.py:12-26; templates/errors/_base_error.html (comentario: no se muestra ruta, excepción ni nombres internos) -->

Si el botón **Copiar** no aparece, apunta el código a mano: ocurre en navegadores que no
permiten copiar al portapapeles.
<!-- fuente: templates/errors/_base_error.html (copy.hidden = true si no hay navigator.clipboard) -->

#### En los avisos al enviar una solicitud

Cuando falla el envío de una solicitud, el aviso emergente ya no se queda solo en "Ocurrió
un error de red. Intenta de nuevo.": debajo de ese texto aparece un recuadro con el código,
en letra de máquina de escribir. Lo verás así: **Código de referencia:** `A3F91C2B7D01`, y
justo debajo, en letra pequeña, "Indícaselo al equipo de desarrollo si reportas la
incidencia."
<!-- fuente: static/js/utils/codigo-referencia.js:70-79 (htmlMensaje) y :53-58 (mensaje) -->

Es el mismo tipo de código que el de las pantallas completas: 12 caracteres, distinto en
cada caso. Vale para los seis formularios de solicitud de cambio de turno.
<!-- fuente: static/js/utils/codigo-referencia.js:73 (filtro [A-Za-z0-9]); core/errors.py:68; static/js/cambio-turno/solicitar_cambio_turno.js:421, solicitar_ct_permanente.js:1748, solicitar_doblada.js:2862, solicitar_doblada_permanente.js:705, solicitar_d_fds.js:442, solicitar_cambio_descanso.js:1328,1362,1382 -->

**No siempre habrá código, y eso es normal.** El código solo existe si el servidor llegó a
responder. Si se te cayó la conexión del todo y la petición nunca llegó, el aviso sale
igual que antes, sin recuadro: no hay nada registrado que el equipo pueda buscar. En ese
caso, reporta simplemente qué estabas haciendo y a qué hora.
<!-- fuente: static/js/utils/codigo-referencia.js:71-72 (sin código se devuelve el aviso tal cual) y :103-106 (un fallo de red no deja cabecera que leer) -->

El código de un aviso caduca al minuto: pasado ese tiempo, un fallo posterior no reutiliza
el código del anterior. Por eso, si vas a reportarlo, apúntalo en el momento.
<!-- fuente: static/js/utils/codigo-referencia.js:36 (VIGENCIA_MS = 60000) -->

En estos avisos no hay botón **Copiar**: selecciona el código con el ratón y cópialo, o
apúntalo a mano.
<!-- fuente: static/js/utils/codigo-referencia.js:70-79 (el bloque solo contiene texto) -->

#### En la página del enlace del correo que ya no sirve

Es la página titulada "No se pudo procesar la solicitud". Dentro del recuadro amarillo
**Detalles del Error**, debajo del mensaje y separado por una línea horizontal, aparece en
letra pequeña "Código de referencia:" seguido del código, y justo debajo "Indícaselo al
equipo de desarrollo si reportas la incidencia."
<!-- fuente: templates/solicitudes/error_token.html:41-55 -->

Solo se muestra cuando hay código; si no lo hay, el recuadro enseña únicamente el mensaje.
Tampoco hay aquí botón **Copiar**: selecciónalo con el ratón o apúntalo a mano.
<!-- fuente: templates/solicitudes/error_token.html:47 ({% if request_id %}) -->

Este código es especialmente útil cuando el mensaje del recuadro es "No pudimos completar
la operación por un fallo interno. El equipo de desarrollo ya tiene el registro del error.":
ese texto no describe la causa a propósito, y el código es lo que permite localizarla.
<!-- fuente: core/utils/error_token.py:30-35 y :57-70 -->

#### Cuando falla la consulta de datos de una pantalla

Son los avisos del final del apartado 7.1, los que empiezan por "No pudimos cargar…" o
"No pudimos calcular…". El código de referencia acompaña siempre a la respuesta del
servidor, pero no todas las pantallas lo pintan: puede que solo veas la frase. No es un
problema; en ese caso indica qué pantalla usabas y a qué hora.
<!-- fuente: core/utils/json_responses.py:96-100 (el request_id viaja en extra) -->

La excepción es el aviso de **Gestión de Solicitudes** al reenviar una notificación: ahí el
código va escrito dentro del propio mensaje, después del punto, como "Código de referencia:"
seguido del código. Si el servidor no pudo generar ninguno, el mensaje aparece solo.
<!-- fuente: solicitudes/views/gestion_solicitudes.py:183-184 -->

---

## 8. Preguntas frecuentes

**¿Por qué no aparece el compañero que quiero?**
Porque ese día no cumple las condiciones: descansa, tiene tu misma jornada, ya está
doblado, ya cedió su jornada o está sancionado. En los formularios de fin de semana, cada
tarjeta descartada muestra el motivo concreto.
<!-- fuente: solicitudes/services/strategies/base_strategy.py (motivos: "ya trabaja los dos días de ese finde", "ya trabaja ese …", "solo tiene media jornada") -->

**¿Puedo pagar una doblada antes de cederla?**
Sí. El pago puede ir antes o después de la cesión, siempre que caiga en el mismo mes y no
sea el mismo día.
<!-- fuente: solicitudes/services/validators/base_validator.py:220 -->

**¿Por qué me pide un cambio de turno antes de pagar?**
Porque tú y tu compañero tenéis la misma jornada ese día y no puedes trabajarla dos veces.
Haz primero un cambio de turno sencillo o elige otra fecha.
<!-- fuente: static/js/cambio-turno/solicitar_doblada.js ("Para pagar la doblada deben quedar en jornadas contrarias…") -->

**¿Qué pasa si mi compañero no responde?**
La solicitud queda pendiente indefinidamente. Recuérdaselo o pide al supervisor que le
reenvíe el aviso desde **Gestión de Solicitudes**.
<!-- fuente: solicitudes/urls.py (gestion_reenviar_solicitud) -->

**¿Los cambios se acumulan?**
No. Si un día se modifica varias veces, vale el último cambio aprobado. Por eso, para
deshacer, hay que empezar por el más reciente.
<!-- fuente: solicitudes/use_cases/cancelar_solicitud.py (bloqueo_lifo) -->

**¿Puedo cambiar el descanso de un fin de semana y no devolverlo?**
No en la modalidad de fin de semana: la devolución es obligatoria y va en otro fin de
semana del mismo mes. En la modalidad entre semana, la opción **Intercambiar el día** es un
cambio simple sin deuda, pero sigue siendo un intercambio dentro de la misma semana.
<!-- fuente: solicitudes/services/strategies/cambio_descanso_strategy.py -->

**¿Por qué mi calendario no muestra el cambio?**
Porque falta una aprobación. Comprueba el estado en **Mis Solicitudes**.

**¿Puedo aprobar desde el correo?**
Sí. El correo incluye enlaces directos para aprobar o rechazar. Son personales: no los
reenvíes. Caducan a los 30 días; después hay que resolver la solicitud entrando a la
aplicación.
<!-- fuente: solicitudes/urls.py (aprobar_solicitud_email, rechazar_solicitud_email, aprobar_solicitud_receptor_email) -->

**¿Qué es la deuda de 30 minutos que menciona la cobertura?**
Cuando alguien cubre una jornada tuya y ese día acaba trabajando AM y PM, el sistema le
calcula esa diferencia. Solo aplica a quien dobla sobre su propia jornada.
<!-- fuente: templates/solicitudes/solicitar_cambio_descanso.html:126; static/js/cambio-turno/solicitar_cambio_descanso.js -->

**¿Dónde veo a quién le debo un fin de semana?**
En **Mis Favores**, con las columnas *Te cubrieron*, *Se lo devolviste*, *Cubriste a* y
*Te lo devolvió*. Las dobladas entre semana no salen ahí: se ven en el **Consolidado de
Horas**.
<!-- fuente: templates/solicitudes/mis_favores.html -->

**Me salió una pantalla de error. ¿Qué apunto para reportarla?**
El **Código de referencia** que aparece al pie, de 12 caracteres. Púlsalo con el botón
**Copiar** y pégalo en tu reporte. Es lo único que el equipo necesita para encontrar tu
caso; el detalle técnico les llega solo.
<!-- fuente: templates/errors/_base_error.html (bloque meta); core/errors.py:18-29 -->

**Me falló el envío de una solicitud y salió un aviso, no una pantalla completa. ¿Qué apunto?**
Ese aviso también trae el **Código de referencia** cuando el servidor alcanzó a responder:
está en el recuadro del final. Apúntalo tal cual. Si no aparece ninguno, es que la conexión
se cayó antes de llegar al servidor: indica entonces qué formulario usabas y a qué hora.
<!-- fuente: static/js/utils/codigo-referencia.js:70-79; :103-106 -->

**Me salió "No pudimos cargar los festivos. Inténtalo de nuevo." y no veo ningún código. ¿Está incompleto el aviso?**
No. En estos avisos el código viaja con la respuesta, pero no todas las pantallas lo
muestran. Reinténtalo; si vuelve a fallar, indica qué pantalla usabas y a qué hora. Lo
mismo vale para los demás avisos que empiezan por "No pudimos cargar…" o "No pudimos
calcular…".
<!-- fuente: turnos/api/views/dias_especiales.py:188; core/utils/json_responses.py:96-100 -->

**Pulsé el enlace del correo y salió "No se pudo procesar la solicitud". ¿Qué apunto?**
Mira el recuadro **Detalles del Error**: si trae un **Código de referencia**, apúntalo antes
de salir de la página. Después entra a la aplicación y resuelve la solicitud desde
**Notificaciones** o **Gestión de Solicitudes**.
<!-- fuente: templates/solicitudes/error_token.html:41-72 -->

**Me apareció "Algo se rompió por nuestro lado" al enviar una solicitud. ¿La reenvío?**
No de inmediato. Entra primero en **Mis Solicitudes** y comprueba si quedó registrada. Si
no está, envíala otra vez.
<!-- fuente: templates/500.html (bloque hint) -->

**Me apareció "Tu sesión expiró antes de enviar el formulario". ¿Perdí la solicitud?**
No se guardó nada, así que no hay nada a medias. Inicia sesión de nuevo y repite el envío.
<!-- fuente: templates/403_csrf.html (lede, hint) -->

**"No tienes permiso para entrar aquí": ¿está roto el sistema?**
No. Tu usuario es válido, pero tu rol no incluye esa sección. Pídele a tu supervisor que
revise los permisos de tu rol.
<!-- fuente: templates/403.html (lede, hint) -->

**¿Por qué el año que viene aparece sin días de mantenimiento?**
Porque el calendario anual se carga a mano cada diciembre. Que un año futuro esté vacío es
lo esperado, no un fallo.
<!-- fuente: docs/04-guias/mantenimiento-anual/ -->

---

## 9. Ejemplos de uso resueltos

**Caso 1 — Necesito la mañana libre un día concreto.**
María trabaja AM el 14/03 y tiene cita médica esa mañana. Hace un **cambio de turno** con
Juan, que ese día trabaja PM: María pasa a PM y deja la mañana libre. Envía, Juan aprueba
desde el correo, la supervisora aprueba después, y el 14/03 el calendario de María muestra
**PM · Asignado**.

**Caso 2 — Necesito el día entero libre y puedo devolverlo.**
Diego cede el jueves 12/03 mediante una **doblada**: Sofía trabaja ese día AM y PM, y él
devuelve el favor el lunes 23/03. Ambas fechas son de marzo y ninguna cae en domingo. En
**Mis Turnos**, Diego ve ☕ el 12 y **DOBLADA (AM + PM)** el 23.

**Caso 3 — Quiero cambiar mi fin de semana de trabajo.**
Ana trabaja el sábado 07/03. Usa **Cambio de Día de Descanso** en modalidad **Fin de
semana**: cambia con Pedro, que trabaja el domingo 08, y devuelve el fin de semana del
21/03. Nadie gana ni pierde domingos en el mes, y no se genera deuda.

**Caso 4 — Quiero un fin de semana entero libre.**
Marta cede su sábado 07/03 con **Doblada de Fin de Semana**: Raúl, que ese sábado descansa,
lo trabaja por ella, y ella trabaja el sábado 21/03 por él. El movimiento queda registrado
en **Mis Favores**.

**Caso 5 — Estudio los martes durante tres meses.**
Carlos pide un **cambio de turno permanente** del 01/04 al 30/06, marcando **Martes** y
**Jueves**, con Lucía. Los festivos del rango quedan excluidos automáticamente. Una sola
solicitud cubre las 26 fechas.

**Caso 6 — Semana de temporada y tengo un compromiso el día que trabajo completo.**
En temporada, el supervisor fijó el descanso de Ana el martes y el de Beatriz el viernes.
Ana usa **Cambio de Día de Descanso**, modalidad **Entre semana**, opción **Intercambiar el
día**: Beatriz toma el día completo de Ana y Ana el de Beatriz. Todo ocurre dentro de la
misma semana y no genera deuda.

**Caso 7 — Me arrepentí cinco minutos después de que aprobaran.**
Diego entra en **Mis Solicitudes**, ve la cuenta atrás en el botón de cancelar y pulsa
**Cancelar**. Los turnos suyos y de Sofía vuelven al estado anterior. Si hubiera esperado
más de 30 minutos, el botón ya no funcionaría y tendría que hablar con su supervisora.

**Caso 8 — Quiero cancelar un cambio antiguo.**
Laura pactó un cambio para el 10/04 y después otro sobre el mismo día. Al intentar cancelar
el primero recibe: *"No puedes cancelar este cambio: hay otro más reciente sobre el mismo
día (10/04). Cancela primero el cambio más reciente."* Cancela el segundo y luego el
primero.

---

## 10. Cambios funcionales relevantes

Cambios recientes que afectan a lo que ves en pantalla.

| Cambio | Qué significa para ti |
|---|---|
| Cinco pantallas de error propias, en español | Cuando algo falla ya no ves una pantalla técnica en inglés ni una página en blanco, sino una explicación clara con botones **Ir al inicio** y **Volver atrás**. Ver el apartado 7.2 <!-- fuente: templates/400.html, 403.html, 403_csrf.html, 404.html, 500.html; core/errors.py --> |
| Cada pantalla de error muestra un **Código de referencia** con botón **Copiar** | Es lo único que tienes que incluir al reportar una incidencia; el detalle técnico llega solo al equipo. Ver el apartado 7.3 <!-- fuente: templates/errors/_base_error.html (bloque meta); core/errors.py:51-76 --> |
| Los avisos de fallo al enviar una solicitud también muestran el **Código de referencia** | Antes el código solo salía en las pantallas de error a página completa. Ahora, si el envío falla y el servidor alcanzó a responder, el propio aviso trae el código en un recuadro. Afecta a los seis formularios. Ver el apartado 7.3 <!-- fuente: static/js/utils/codigo-referencia.js; templates/base.html:297 --> |
| La página "No se pudo procesar la solicitud" también muestra el **Código de referencia** | Antes esta pantalla no mostraba ninguno. Ahora, cuando lo hay, aparece dentro del recuadro **Detalles del Error**. Además, si el fallo es interno, el recuadro dice "No pudimos completar la operación por un fallo interno. El equipo de desarrollo ya tiene el registro del error." en lugar del texto técnico de antes. Ver el apartado 7.3 <!-- fuente: templates/solicitudes/error_token.html:41-55; core/utils/error_token.py:32-35 --> |
| Los fallos al cargar o calcular datos de una pantalla se explican en español | Antes, si algo se rompía al traer festivos, días de temporada, días especiales, los turnos de un día o las jornadas de un rango, veías un texto técnico incomprensible. Ahora ves una frase clara del estilo "No pudimos cargar los festivos. Inténtalo de nuevo." y el código de referencia acompaña a la respuesta. Los avisos de validación normales no cambiaron. Ver los apartados 7.1 y 7.3 <!-- fuente: turnos/api/views/dias_especiales.py:188,265,354; turnos/api/views/turnos_mes.py:24; solicitudes/views/api_turno_jornada.py:555; core/utils/json_responses.py:67-100 --> |
| Lo mismo en las pantallas de supervisor | En el mantenimiento anual y en la generación de festivos del año verás "No pudimos calcular los días de mantenimiento. Inténtalo de nuevo." y "No pudimos calcular los festivos del año. Inténtalo de nuevo.". Al reenviar una notificación desde **Gestión de Solicitudes**, el aviso es "No se pudo reenviar la notificación." con el código de referencia escrito a continuación <!-- fuente: turnos/api/views/calculo_automatico.py:80,132; solicitudes/views/gestion_solicitudes.py:183-184 --> |
| Los enlaces de **Aprobar** y **Rechazar** del correo caducan a los 30 días | Antes no caducaban. Si abres un correo antiguo y pulsas el enlace, verás la página de error del enlace; resuelve la solicitud entrando a la aplicación <!-- fuente: solicitudes/services/tokens_aprobacion.py; config/settings.py:262 --> |
| Los días de descanso de temporada solo se modifican desde **Cambio de Día de Descanso** | Ningún otro trámite puede tocar esos dos días de la semana <!-- fuente: commit 4bddab7 --> |
| En **Cambio de Día de Descanso**, el compañero que manda es el del desplegable | Si cambias de compañero después de elegir la fecha, la validación usa el nuevo <!-- fuente: commit 5bd991c --> |
| El desplegable y la validación miran la misma fecha | Ya no aparecen compañeros que luego el sistema rechaza <!-- fuente: commit 9c429e3 --> |
| En **Doblada Permanente**, el choque con el compañero se mide por fecha | Los avisos de solapamiento son más precisos <!-- fuente: commit a7607d7 --> |
| Ceder un festivo entero en **Doblada** cubre el día completo (AM + PM) | Al ceder un festivo, el compañero asume las dos jornadas <!-- fuente: commit 56eb793 --> |
| En **Mis Turnos**, un día de fin de semana se llama **DÍA COMPLETO**, no **DOBLADA** | El texto ya no sugiere un esfuerzo extra donde no lo hay <!-- fuente: commit 0c3ccc8 --> |
| Se registra la hora real de la cancelación | La cuenta atrás de los 30 minutos es exacta <!-- fuente: commit a437c41 --> |
| En **Doblada Permanente** se explica por qué un compañero no cubre una fecha | Los motivos aparecen junto a cada fecha descartada <!-- fuente: commit 4dd6cd6 --> |
| Un rol parecido a "Supervisor" ya no concede permisos de supervisor | Solo el rol exacto **Supervisor** ve el menú de administración <!-- fuente: commits f9e82e3, 727f1f8 --> |
| Las sanciones se levantan, no se borran | Queda el registro de la sanción y de cuándo se levantó <!-- fuente: commit 0e541c1 --> |
| En **Doblada**, la lista de compañeros esconde a quien ya trabaja mañana y tarde | Antes se escondía por error a quien ese día descansaba por haber cedido su jornada. Ahora aparecen en el desplegable compañeros libres que antes no se mostraban, incluido quien descansa porque te cedió el día a ti <!-- fuente: solicitudes/services/doblada_filtro_service.py:54-66 --> |
| En **PDH**, la fecha de pago la decide el supervisor | Se retiró una validación que rechazaba fechas legítimas <!-- fuente: commit 9bf81f8 --> |

<!-- fuente: git log del repositorio, commits 0e541c1 … 40a7ed8 -->

---

## 11. Por confirmar

Afirmaciones que no pudieron verificarse contra el código y que, por tanto, **no** se
incluyeron como hechos en el manual.

| Afirmación pendiente | Dónde se buscó | Por qué no se pudo verificar |
|---|---|---|
| Duración exacta de la sesión antes de caducar por inactividad | Configuración general del proyecto | No hay un valor explícito configurado; se aplica el comportamiento por defecto del sistema, que no está declarado en el proyecto |
| Cuánto tarda en llegar el correo de aviso al compañero | Servicio de correo y su cola de envío | El envío es diferido y depende de una tarea programada del servidor; no hay un plazo garantizado escrito en el código |
| Texto exacto de los correos de aprobación y rechazo | Plantillas de correo del módulo de solicitudes (14 archivos) | No se abrieron una por una en esta revisión; el manual solo cita los mensajes de pantalla |
| Qué muestra exactamente el **Dashboard** al entrar | Plantilla del panel de inicio | No se revisó su contenido en esta revisión; el recorrido del apartado 2.2 se limita al menú |
| Contenido y reglas de **Consolidado de Horas**, **Indicadores** y **Beneficios Utilizados** | Módulos de turnos y personas | Quedan fuera del alcance de esta revisión, centrada en los seis formularios de solicitud |
| Reglas del módulo de **Permisos Especiales** y **PDH** | Módulo de permisos | El inventario documental lo marca como área sin documentación funcional; no se abordó aquí |
| Reglas de **Salas**, **Competencias** y asignación de sala | Módulo de personas | Igual que el anterior: marcado como pendiente en el inventario documental |
| Si el mensaje de bloqueo tras 5 intentos fallidos se muestra al usuario y con qué texto | Pantalla de inicio de sesión y configuración de bloqueo | El límite y la hora de espera sí están configurados, pero no se localizó una pantalla propia con el texto del bloqueo |
| Contenido de los documentos de negocio en formato Word de la carpeta de instructivos | Carpeta de instructivos del proyecto | Formato binario; su contenido no se pudo contrastar con lo implementado |
| Si el usuario recibe alguna confirmación de que su incidencia fue registrada al reportar el código de referencia | Pantallas de error y avisos del sistema | No existe un canal de reporte dentro de la aplicación: el aviso al equipo se hace por fuera |
| Si existe algún aviso automático cuando una solicitud lleva mucho tiempo pendiente | Servicio de notificaciones | No se encontró; el supervisor puede reenviar el aviso manualmente |

---

*La fuente de verdad de este manual es este archivo Markdown. Las versiones en PDF y Word
son artefactos generados y no deben editarse a mano.*
