# Manual de Usuario — AppTurnos / SWALP

Guía para exploradores y supervisores. Explica qué hace la aplicación, qué puede hacer
cada persona y cómo realizar paso a paso cada trámite.

No necesitas conocimientos técnicos para leer este manual. Si eres desarrollador, tu
documento es [manual_tecnico.md](./manual_tecnico.md).

---

## 1. ¿Qué es AppTurnos?

AppTurnos organiza la programación de turnos del equipo de exploradores y gestiona los
acuerdos entre compañeros para intercambiar jornadas.

Con la aplicación puedes:

- consultar tus turnos del mes;
- pedirle a un compañero que cubra tu jornada;
- intercambiar tu turno o tu día de descanso;
- aprobar o rechazar lo que otros te piden;
- llevar la cuenta de las jornadas que debes y las que te deben.

Todo acuerdo entre compañeros pasa por el sistema y necesita **dos aprobaciones**: la
del compañero implicado y la del supervisor. Así queda registro de lo pactado y nadie
depende de acuerdos verbales.

## 2. Acceso

**Requisitos.** Un navegador actualizado y tus credenciales de acceso, que entrega el
supervisor.

**Para entrar:**

1. Abre la dirección de la aplicación.
2. Escribe tu usuario y tu contraseña.
3. Pulsa **Iniciar sesión**.

Verás la pantalla de inicio con el menú lateral.

**Si fallas la contraseña varias veces**, el sistema bloquea el acceso por seguridad.
Contacta con tu supervisor para desbloquearlo.

**Para salir:** usa la opción de cerrar sesión del menú de usuario. Hazlo siempre que
uses un equipo compartido.

## 3. Roles: quién puede hacer qué

| Acción | Explorador | Supervisor |
|---|---|---|
| Consultar sus propios turnos | Sí | Sí |
| Crear solicitudes | Sí | Sí |
| Aprobar o rechazar como compañero | Sí, cuando lo eligen a él | Sí |
| Aprobar o rechazar como supervisor | No | Sí |
| Cancelar sus propias solicitudes | Sí | Sí |
| Ver y gestionar todas las solicitudes | No | Sí |
| Registrar inasistencias y reprogramar | No | Sí |
| Configurar el cierre semanal | No | Sí |
| Gestionar empleados, salas y sanciones | No | Sí |

Un supervisor que además sea el compañero de una solicitud puede resolver ambas
aprobaciones de una sola vez.

## 4. Navegación

El menú lateral organiza el trabajo diario:

| Opción | Para qué sirve |
|---|---|
| **Mis turnos** | Tu calendario del mes: qué días trabajas, en qué jornada y cuándo descansas |
| **Solicitudes** | Punto de partida para crear cualquier trámite |
| **Mis solicitudes** | Todo lo que has enviado y en qué estado está |
| **Solicitudes pendientes** | Lo que espera tu aprobación |
| **Notificaciones** | Avisos del sistema |

**Cómo leer "Mis turnos".** Cada día muestra tu jornada (AM o PM) o el descanso. Cuando
un cambio queda aprobado, el calendario se actualiza: es tu confirmación visual de que
el acuerdo surtió efecto.

## 5. Antes de solicitar: cuatro cosas que conviene saber

**5.1 Todo necesita dos aprobaciones.** Primero tu compañero, después el supervisor.
Hasta que ambas lleguen, nada cambia en el calendario.

**5.2 Si estás sancionado, no puedes participar.** Ni creando solicitudes ni como
compañero de otra persona. La sanción puede aparecer automáticamente si acumulas deuda
sin pagar.

**5.3 Hay un cierre semanal.** A partir del día y la hora que fije el supervisor, la
programación del fin de semana queda cerrada y ya no se aceptan solicitudes nuevas para
esos días. Si te aparece ese aviso, habla con tu supervisor.

**5.4 Puedes arrepentirte, pero con plazo.** Una solicitud pendiente se cancela cuando
quieras. Una ya aprobada, solo dentro de los **30 minutos** siguientes a su aprobación.

## 6. Los seis trámites, paso a paso

Todos empiezan igual: **Solicitudes → elige el tipo**. Todos piden un comentario
explicando el motivo, y en todos el sistema avisa por correo al compañero y al
supervisor.

### 6.1 Cambio de turno

**Objetivo.** Intercambiar tu jornada con un compañero durante un día.

**Antes de empezar.** Necesitas un compañero que ese día tenga la jornada contraria a
la tuya: si trabajas AM, él debe trabajar PM.

**Pasos:**

1. Entra en **Solicitudes** y elige **Cambio de turno**.
2. Selecciona la fecha del cambio.
3. Elige al compañero de la lista. El sistema solo muestra a quienes pueden hacerlo.
4. Escribe el motivo en el comentario.
5. Pulsa **Enviar solicitud**.

**Resultado esperado.** Mensaje de confirmación y aviso de que se notificó al compañero
y al supervisor.

**Cómo confirmar que quedó bien.** Entra en **Mis solicitudes**: debe aparecer como
*pendiente*. Cuando ambos aprueben, revisa **Mis turnos**: verás la jornada cambiada.

**Errores posibles:**

| Mensaje | Por qué pasa | Qué hacer |
|---|---|---|
| No se puede cambiar por la misma jornada | Ambos tienen AM, o ambos PM | Busca un compañero del grupo contrario |
| No se puede cambiar domingo por día de semana | Los domingos no admiten este trámite | Consulta con tu supervisor |
| No se puede cambiar sábado por día de semana | El fin de semana se rige por la alternancia | Usa **Cambio de descanso** o **D FDS** |
| Un sábado, domingo o festivo aparece «sin planificar» | El supervisor todavía no publicó la alternancia de ese año | Avísale: se publica en **Turnos → Fines de semana y festivos** |
| No se puede solicitar para una fecha pasada | La fecha ya pasó | Elige una fecha futura |
| No trabajas esa fecha | Ese día descansas: no hay jornada que intercambiar | Elige otro día |

### 6.2 Cambio de turno permanente

**Objetivo.** El mismo intercambio, repetido durante varias semanas.

**Antes de empezar.** Ten claros el rango de fechas y los días de la semana afectados.

**Pasos:**

1. **Solicitudes → Cambio de turno permanente**.
2. Indica fecha de inicio y fecha de fin (ambas obligatorias).
3. Marca los días de la semana que quieres cambiar.
4. Elige al compañero, del grupo contrario.
5. Usa la **previsualización** para revisar las fechas concretas que se verán afectadas.
6. Escribe el comentario y envía.

**Resultado esperado.** Confirmación, y en la previsualización la lista exacta de días
que cambiarán.

**Cómo confirmar que quedó bien.** Tras las dos aprobaciones, recorre **Mis turnos** por
el rango: los días marcados deben mostrar la jornada nueva.

**Errores posibles:**

| Mensaje | Por qué pasa | Qué hacer |
|---|---|---|
| Falta la fecha de fin | El rango está incompleto | Indica la fecha final |
| No se pueden realizar cambios permanentes en domingos | Los domingos quedan excluidos | Desmarca el domingo |
| No se encontraron jornadas contrarias | Tú y tu compañero tenéis la misma | Busca otro compañero |

### 6.3 Cambio de descanso

Este trámite funciona de **dos maneras distintas** según el día.

#### Modalidad fin de semana

**Objetivo.** Permutar con un compañero el día del fin de semana que trabajáis. Si tú
trabajas el sábado y él el domingo, os cambiáis; en otra semana del mismo mes se
devuelve.

**Importante.** No genera deudas ni dobladas: sigues trabajando un solo día por fin de
semana, solo cambia cuál.

**Pasos:**

1. **Solicitudes → Cambio de descanso**.
2. Selecciona el día del fin de semana que quieres cambiar.
3. Selecciona el fin de semana de la devolución (otro distinto, dentro del mes).
4. Elige al compañero.
5. Comenta y envía.

**Errores posibles:**

| Mensaje | Por qué pasa | Qué hacer |
|---|---|---|
| El día que cambias debe ser un fin de semana | Elegiste un día entre semana | Elige sábado o domingo |
| La devolución debe ser un fin de semana distinto | Ambas fechas caen en el mismo | Elige otro fin de semana |
| No se puede cambiar el descanso de un fin de semana pasado | La fecha ya pasó | Elige una futura |

#### Modalidad entre semana (temporada)

**Objetivo.** Intercambiar directamente el día de descanso que os asignó el supervisor
en temporada. **No hay devolución**: es un intercambio simple.

**Pasos:**

1. **Solicitudes → Cambio de descanso**, en su versión entre semana.
2. Selecciona tu día de descanso y el de tu compañero.
3. Indica la jornada correspondiente si el formulario la pide.
4. Comenta y envía.

**Errores posibles:**

| Mensaje | Por qué pasa | Qué hacer |
|---|---|---|
| El compañero solo puede descansar de lunes a viernes | Elegiste un fin de semana | Usa la modalidad de fin de semana |
| Los descansos deben estar en el mismo rango de temporada (máximo 45 días) | Las fechas están demasiado separadas | Acerca las fechas |
| El compañero debe ser del grupo contrario | Ambos sois del mismo grupo | Busca alguien del otro grupo |
| Esa semana no tiene descansos de temporada configurados | El supervisor aún no los cargó | Habla con tu supervisor |
| Ya enviaste este intercambio | Es un duplicado que sigue pendiente | Espera la respuesta |

### 6.4 Doblada

**Objetivo.** Que un compañero cubra tu jornada un día, doblándose él; tú se la
devuelves doblándote en otra fecha acordada.

**Antes de empezar.** Necesitas dos fechas claras: la de **cesión** (el día que no
trabajas) y la de **pago** (el día que devuelves el favor). Ambas deben caer en el
**mismo mes**.

**Pasos:**

1. **Solicitudes → Doblada**.
2. Indica la fecha de cesión.
3. Elige al compañero que te cubrirá, del grupo contrario.
4. Indica la fecha de pago. Puede ser antes o después de la cesión, pero **nunca el
   mismo día**.
5. Si el pago cae en sábado, indica qué jornada cubrirás: AM, PM o ambas.
6. Comenta y envía.

**Resultado esperado.** Confirmación de envío. Al aprobarse, tú descansas el día de la
cesión y quedas con una jornada pendiente de pagar.

**Cómo confirmar que quedó bien.** En **Mis turnos**, el día de la cesión aparece libre
y el de pago con la jornada doblada. La deuda queda registrada hasta que la pagues.

**Errores posibles:**

| Mensaje | Por qué pasa | Qué hacer |
|---|---|---|
| La fecha de pago es obligatoria | No existen dobladas abiertas: siempre se acuerda cuándo se devuelve | Acuerda la fecha con tu compañero |
| La fecha de pago no puede ser la misma que la de cesión | No puedes trabajar y descansar el mismo día | Elige otro día de pago |
| La fecha de pago debe estar en el mismo mes que la de cesión | Cruzaste el límite del mes | Elige una fecha del mismo mes |
| Para ceder jornada AM, el receptor debe tener jornada PM | Las jornadas no son contrarias | Busca otro compañero |
| El receptor no puede tener doblada el día de la cesión | Ya se dobla ese día; no puede triplicar | Busca otro compañero o cambia la fecha |
| No se puede realizar doblada en domingos | Los domingos quedan excluidos | Elige otro día |
| Los dos estáis descansando en la fecha de pago | Ninguno trabaja ese día | Elige otra fecha de pago |
| El receptor no trabaja en la fecha de pago | Ese día descansa; no hay jornada que cubrir | Elige una fecha en la que sí trabaje |
| Se requiere cambio de turno previo | Tú y tu compañero tenéis la misma jornada ese día y no puedes trabajarla dos veces | Haz primero un cambio de turno, o elige otra fecha |

### 6.5 Doblada permanente

**Objetivo.** Repetir el acuerdo de doblada durante un rango de fechas. Puedes repartir
la cobertura **entre varios compañeros**.

**Antes de empezar.** Ten claro el rango, qué días cede cada quién y qué días le
devuelves. La cuenta debe cuadrar.

**Pasos:**

1. **Solicitudes → Doblada permanente**.
2. Indica fecha de inicio y fecha de fin.
3. Añade cada día de cesión con el compañero que lo cubre.
4. Añade los días de devolución, con el mismo compañero.
5. Revisa la previsualización.
6. Comenta y envía.

**Resultado esperado.** Si repartes entre varios compañeros, el sistema crea **una
solicitud por compañero** y te indica cuántas creó.

**Reglas que conviene tener presentes:**

- A cada compañero le devuelves **exactamente** el mismo número de días que te cubre.
- Solo devuelves a quien te cubre.
- Una fecha se asigna a **un solo** compañero: dos personas no pueden cubrir ni pagar la
  misma jornada el mismo día.
- Si una sola de las solicitudes falla la validación, **no se crea ninguna**. Es todo o
  nada, para que no quedéis con acuerdos a medias.

**Errores posibles:**

| Mensaje | Por qué pasa | Qué hacer |
|---|---|---|
| A cada compañero debes devolverle la misma cantidad de días que te cubre | Las cuentas no cuadran | Ajusta los días de devolución |
| La fecha está asignada a dos compañeros | Repetiste una fecha | Deja un solo compañero por fecha |
| Solo puedes devolverle a un compañero que te cubra | Hay devolución a alguien que no te cubre | Corrige la asignación |
| El rango no puede iniciar en el pasado | La fecha de inicio ya pasó | Elige una fecha futura |

### 6.6 D FDS — doblada de fin de semana

**Objetivo.** Ceder tu día de fin de semana a un compañero del grupo contrario, que se
dobla ese fin de semana; tú devuelves el favor doblándote otro fin de semana del mismo
mes.

**Pasos:**

1. **Solicitudes → D FDS**.
2. Selecciona el fin de semana que cedes (sábado o domingo, según te toque).
3. Elige al compañero. El sistema muestra solo a quienes pueden cubrirte.
4. Selecciona el fin de semana de pago, dentro del mismo mes.
5. Comenta y envía.

**Errores posibles:**

| Mensaje | Por qué pasa | Qué hacer |
|---|---|---|
| La fecha de cesión debe ser un fin de semana | Elegiste un día entre semana | Elige sábado o domingo |
| La fecha de pago es obligatoria | Debes acordar cuándo devuelves | Elige otro fin de semana del mes |
| No se puede solicitar D FDS para un fin de semana pasado | La fecha ya pasó | Elige una futura |
| El compañero ya tiene una doblada en la fecha de cesión | No puede cubrirte ese día | Busca otro compañero |
| Ya tienes una doblada en la fecha de pago | No puedes doblarte dos veces | Elige otra fecha de pago |

## 7. Aprobar y rechazar

Cuando alguien te elige como compañero, recibes un aviso en la aplicación y un correo.

**Desde la aplicación:**

1. Entra en **Solicitudes pendientes**.
2. Abre la solicitud y revisa fechas, jornadas y comentario.
3. Pulsa **Aprobar** o **Rechazar**, añadiendo un comentario.

**Desde el correo.** El mensaje incluye enlaces directos para aprobar o rechazar sin
entrar en la aplicación. Son enlaces personales: no los reenvíes.

**Qué pasa después.** Con tu aprobación, la solicitud pasa al supervisor. Solo cuando
él también aprueba se modifican los turnos y ambos lo veis en **Mis turnos**.

**Consejo.** Antes de aprobar, comprueba que ese día realmente puedes: el sistema
revisa las reglas de nuevo en el momento de la aprobación, y si tu situación cambió
desde que se envió la solicitud, puede rechazarla entonces.

## 8. Cancelar una solicitud

**Si está pendiente.** Entra en **Mis solicitudes** y pulsa **Cancelar**. Sin límite de
tiempo.

**Si ya fue aprobada.** Solo puedes cancelarla dentro de los **30 minutos** siguientes a
su aprobación. Pasado ese plazo, habla con tu supervisor.

**Una restricción importante.** Si sobre ese mismo día hay otro cambio más reciente, el
sistema no te deja cancelar el antiguo: primero hay que cancelar el más reciente. Es lo
que evita que el calendario quede en un estado incoherente.

Solo puedes cancelar tus propias solicitudes.

## 9. Errores frecuentes y qué hacer

| Situación | Qué significa | Qué hacer |
|---|---|---|
| "Estás sancionado" | Tienes una sanción activa, quizá automática por deuda acumulada | Habla con tu supervisor; paga la deuda pendiente |
| "El compañero está sancionado" | La sanción de tu compañero le impide participar | Elige a otra persona |
| "Cierre de solicitudes activo" | La programación de ese fin de semana ya se cerró | Habla con tu supervisor |
| "Hay una restricción médica vigente" | Hay una recomendación médica en esas fechas | Léela y confirma si procede continuar |
| "No se pueden realizar cambios en días de mantenimiento" | Ese día no hay operación | Elige otro día |
| "Ya tienes una solicitud pendiente para esa fecha" | Hay otro trámite abierto para el mismo día | Espera su resolución o cancélalo |
| La lista de compañeros aparece vacía | Nadie cumple los requisitos ese día | Prueba otra fecha o consulta con tu supervisor |
| Enviaste la solicitud y no aparece | Puede que no llegara a enviarse | Revisa **Mis solicitudes**; si no está, vuelve a enviarla |

## 10. Preguntas frecuentes

**¿Por qué no aparece el compañero que quiero?**
Porque ese día no cumple las condiciones: puede estar descansando, tener la misma
jornada que tú, ya estar doblado o estar sancionado.

**¿Puedo pagar una doblada antes de cederla?**
Sí. El pago puede ir antes o después de la cesión, siempre que caiga en el mismo mes y
no sea el mismo día.

**¿Por qué me pide un cambio de turno antes de pagar?**
Porque tú y tu compañero tenéis la misma jornada ese día, y no puedes trabajar dos veces
la misma. Ajusta primero el turno o elige otra fecha.

**¿Qué pasa si mi compañero no responde?**
La solicitud queda pendiente. Recuérdaselo, o pide al supervisor que le reenvíe el aviso.

**¿Los cambios se acumulan?**
No. Si un día se modifica varias veces, vale **el último cambio aprobado**; el anterior
queda cancelado. Por eso, para deshacer, hay que empezar por el más reciente.

**¿Puedo cambiar el descanso de un fin de semana y no devolverlo?**
En la modalidad de fin de semana, no: se devuelve en otro fin de semana del mismo mes.
En la modalidad de temporada entre semana sí es un intercambio simple, sin devolución.

**¿Por qué mi calendario no muestra el cambio?**
Porque falta una aprobación. Comprueba el estado en **Mis solicitudes**.

## 11. Soporte

Ante cualquier duda o bloqueo, tu primer contacto es **tu supervisor**. Cuando reportes
un problema, indica: qué intentabas hacer, qué fechas, qué compañero y el mensaje exacto
que apareció en pantalla. Con eso se resuelve mucho más rápido.

---

*Generado con el skill `project-documentation-master`. La fuente de verdad es este
Markdown; el `.docx` es un artefacto derivado y no debe editarse a mano.*
