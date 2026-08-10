# Patrones de Protección, Idempotencia y Buenas Prácticas

Guía integral de técnicas aplicadas en este proyecto para evitar doble clic, corrupción de datos, 
race conditions, pérdida de integridad, y garantizar confiabilidad en operaciones críticas.

**Actualización:** Cada vez que se implemente un nuevo patrón o mejora, se documenta aquí con:
- Qué es
- Por qué se usa
- Dónde se aplicó
- Código de ejemplo

---

## 📋 Patrones Aplicados en el Proyecto

### 1. **Button Disable-On-Click** (Frontend)
**Qué es:** Deshabilitar el botón después del primer clic y mostrar "Procesando..." mientras se completa la petición.

**Por qué:** Previene que el usuario haga clic múltiples veces mientras la petición está en vuelo.

**Dónde:** Todo botón que dispara `fetch()` o `form.submit()`.

**Implementación:**
```javascript
button.disabled = true;
button.textContent = 'Procesando...';
// ... fetch ...
.finally(() => {
    button.disabled = false;
    button.textContent = textoOriginal;
});
```

**Estado:** ✅ **APLICADO**
- `solicitudes_pendientes_list.html` - botón `#confirmarAccion` (aprobar/rechazar)
- 7 formularios de "solicitar" (doblada, CT, D FDS, cambio descanso, etc.)
- `solicitar_cambio_descanso.js` - botón `#btnEnviarCd` (nuevamente implementado con LoadingUI)

---

### 2. **Select-For-Update + Transaction** (Backend)
**Qué es:** Bloqueo pesimista de fila con `select_for_update()` dentro de transacción atómica. Serializa peticiones concurrentes.

**Por qué:** Si dos peticiones llegan casi simultáneamente, la segunda espera a la primera, luego re-chequea el estado y se rechaza si ya cambió.

**Dónde:** Operaciones de estado crítico (aprobar, rechazar, cancelar).

**Implementación:**
```python
from django.db import transaction
with transaction.atomic():
    solicitud = SolicitudCambio.objects.select_for_update().get(id=id)
    if solicitud.estado != 'pendiente':
        return False, "Ya no está pendiente"
    solicitud.estado = 'aprobada'
    solicitud.save()
```

**Estado:** ✅ **APLICADO**
- `solicitud_aprobacion_service.py` - `aprobar_solicitud_receptor()`
- `solicitud_aprobacion_service.py` - `aprobar_solicitud_supervisor()`
- `aprobacion_views.py` - `CancelarSolicitudView.post()`

---

### 3. **Idempotent Guards / Snapshot-Once Pattern** (Backend)
**Qué es:** Guardar datos críticos (snapshot) solo la primera vez. Verificar que NO exista antes de sobrescribir.

**Por qué:** Evita corrupción de snapshot si la operación se re-aplica accidentalmente (doble clic a pesar de otras protecciones).

**Dónde:** Antes de capturar estado que se revertirá en cancellations (ventana de 30 min).

**Implementación:**
```python
if not getattr(detalle, 'snapshot_turnos_previos', None):
    snapshot = capturar_snapshot()
    Modelo.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snapshot)
    detalle.snapshot_turnos_previos = snapshot
```

**Estado:** ✅ **APLICADO**
- `doblada_strategy.py` - snapshot en `aplicar_cambios()`
- `d_fds_strategy.py` - snapshot en `aplicar_cambios()`
- `doblada_permanente_aplicacion_service.py` - snapshot en `aplicar()`
- `cambio_descanso_aplicacion_service.py` - snapshot en `aplicar()` y `aplicar_entre_semana()`

---

### 4. **SweetAlert Confirmation Modal** (Frontend)
**Qué es:** Diálogo de confirmación modal que solo permite una confirmación (no re-clickeable).

**Por qué:** Evita acciones accidentales y proporciona feedback visual claro.

**Dónde:** Operaciones destructivas (cancelar, rechazar).

**Implementación:**
```javascript
Swal.fire({ title: '¿Confirmar?', icon: 'warning', showCancelButton: true })
    .then(result => { if (result.isConfirmed) { fetch(...) } })
```

**Estado:** ✅ **APLICADO**
- `solicitudes_pendientes_list.html` - modal `#accionSolicitudModal`
- `mis_solicitudes_list.html` - `cancelarSolicitud()`, `cancelarSolicitudAprobada()`
- `solicitar_cambio_descanso.js` - función `mostrarConfirmacion()` (2026-06-26 - nuevo formulario cambio descanso)

---

### 5. **Form Submit Disable** (Frontend)
**Qué es:** Deshabilitar todos los campos (input, select, textarea) y botón submit mientras se procesa.

**Por qué:** Previene cambios de datos durante la petición y evita reenvíos accidentales.

**Dónde:** Todo formulario que crea/modifica solicitudes.

**Implementación:**
```javascript
submitBtn.disabled = true;
form.querySelectorAll('input, select, textarea').forEach(el => el.disabled = true);
```

**Estado:** ✅ **APLICADO**
- `solicitar_doblada.js`, `solicitar_doblada_permanente.js`, `solicitar_d_fds.js`, 
- `solicitar_cambio_descanso.js`, `solicitar_ct_permanente.js`, `solicitar_cambio_turno.js`

---

### 6. **Cache Invalidation** (Backend)
**Qué es:** Invalidar/eliminar caché cuando cambia estado de datos que otros usuarios leen.

**Por qué:** Sin esto, usuarios ven datos stale (desactualizados) en "Mis Turnos", contadores, etc.

**Dónde:** Después de aprobar, rechazar, cancelar, o aplicar cambios.

**Implementación:**
```python
from core.services.cache_service import CacheService
cache_keys = [
    f"solicitudes_count_mis_{solicitud.explorador_solicitante.id}",
    f"solicitudes_count_pend_{solicitud.explorador_receptor.id}",
]
CacheService.delete_many(cache_keys)
CacheService.invalidar_cache_turnos_empleado(empleado_id, mes, año)
```

**Estado:** ✅ **APLICADO**
- `solicitud_aprobacion_service.py` - invalidar contadores tras aprobar
- `aprobacion_views.py` - invalidar turnos tras cancelar
- Todas las strategies de cambios (`doblada_strategy.py`, `ct_permanente_strategy.py`, etc.)

---

### 7. **Transaction.atomic()** (Backend)
**Qué es:** Envolver operaciones de múltiples cambios en una transacción atómica. Si falla algo, TODO se revierte (rollback).

**Por qué:** Garantiza consistencia: o se aplican todos los cambios o ninguno.

**Dónde:** Crear solicitud, aplicar cambios, crear deudas, etc.

**Implementación:**
```python
from django.db import transaction
@transaction.atomic
def aplicar(solicitud, detalle):
    # Crear turno 1
    # Crear turno 2
    # Crear deuda
    # Si CUALQUIER cosa falla, TODO se revierte
```

**Estado:** ✅ **APLICADO**
- `doblada_aplicacion_service.py` - `aplicar()` (432 ocurrencias en total)
- Todas las strategies y servicios de aplicación
- `cambio_descanso_aplicacion_service.py` - `aplicar()`, `aplicar_entre_semana()`, `revertir()`
- `doblada_permanente_aplicacion_service.py` - `aplicar()`, `revertir()`

---

### 8. **Validación en Cliente Y Servidor** (Ambos)
**Qué es:** Validar datos tanto en JS (cliente) como en Python (servidor). Nunca confiar solo en cliente.

**Por qué:** Cliente valida para UX rápido. Servidor valida porque el cliente se puede hackear o saltear.

**Dónde:** Crear solicitud, cambiar fecha, seleccionar receptor, etc.

**Implementación:**
```javascript
// Cliente: validar rápido
if (!receptor) return Swal.fire('Error: Receptor requerido');
if (fecha < hoy) return Swal.fire('Error: Fecha pasada');

# Servidor: validar siempre
if not receptor: raise ValidationError('Receptor requerido')
if fecha < date.today(): raise ValidationError('Fecha pasada')
```

**Estado:** ✅ **APLICADO**
- Cliente: `solicitar_doblada.js`, `solicitar_doblada_permanente.js`, etc.
- Servidor: `solicitud_validator.py` - 82 validaciones centralizadas
  - `validar_empleado_activo()`, `validar_no_mismo_empleado()`, `validar_jornada_en_fecha()`,
  - `validar_duplicada_misma_fecha()`, `validar_fechas_cambio_permanente()`, `validar_jornada_contraria()`
  - `validar_no_dia_mantenimiento()`, `validar_fecha_pago_mismo_mes_cesion()`, etc.

---

### 9. **Autorización/Permisos** (Backend)
**Qué es:** Verificar que el usuario tiene derecho a realizar la acción (es receptor, es supervisor, etc.).

**Por qué:** Evita que A apruebe solicitud destinada a B, o que C cancele solicitud de D.

**Dónde:** Antes de cualquier acción que afecte a otros usuarios.

**Implementación:**
```python
if solicitud.explorador_receptor != request.user.empleado:
    return json_error('No tienes permisos', status=403)
if solicitud.explorador_solicitante.supervisor != request.user.empleado:
    return json_error('No eres supervisor de este explorador', status=403)
```

**Estado:** ✅ **APLICADO**
- `aprobacion_views.py` - `AprobarSolicitudReceptorView`, `AprobarSolicitudSupervisorView`
- `solicitud_aprobacion_service.py` - `aprobar_solicitud_receptor()`, `aprobar_solicitud_supervisor()`
- `mis_solicitudes_list.html` - Verificar permisos antes de mostrar botones

---

### 10. **Logging y Auditoría** (Backend)
**Qué es:** Registrar eventos importantes (aprobación, rechazo, aplicación, reversión) para debugging y auditoría.

**Por qué:** Permite rastrear quién hizo qué, cuándo y por qué. Crucial para debugging de bugs tipo #287.

**Dónde:** Operaciones críticas (aprobar, aplicar, revertir, etc.).

**Implementación:**
```python
logger.info(
    "Aprobando solicitud completamente - ID: %d, Tipo: %s, Receptor: %d, Solicitante: %d",
    solicitud.id, solicitud.tipo_cambio.nombre, receptor.id, solicitante.id
)
logger.exception("Error al aplicar cambios")  # incluye stack trace
```

**Estado:** ✅ **APLICADO**
- `solicitud_aprobacion_service.py` - logger en aprobar receptor/supervisor
- `doblada_aplicacion_service.py` - logger en aplicar/revertir (42 ocurrencias)
- `doblada_permanente_aplicacion_service.py`, `cambio_descanso_aplicacion_service.py`
- Todas las strategies y servicios

---

### 11. **Notificaciones a Usuarios** (Backend)
**Qué es:** Crear notificaciones en la BD cuando cambia estado (para que el usuario vea cambios en su dashboard).

**Por qué:** Los usuarios necesitan saber que se aprobó/rechazó/canceló su solicitud.

**Dónde:** Después de aprobar, rechazar, cancelar.

**Implementación:**
```python
NotificacionService.crear_notificacion_aprobacion_receptor(solicitud, receptor, comentario)
NotificacionService.crear_notificacion_rechazo_supervisor(solicitud, supervisor, comentario)
NotificacionService.crear_notificacion_cancelacion(solicitud)
```

**Estado:** ✅ **APLICADO**
- `solicitud_aprobacion_service.py` - crear notificaciones en aprobar/rechazar
- `aprobacion_views.py` - crear notificación en cancelar
- `notificacion_service.py` - 98 ocurrencias (servicio centralizado)

---

### 12. **Select_Related / Prefetch_Related** (Backend)
**Qué es:** Pre-cargar relaciones (FK, ManyToMany) en una sola query en vez de N queries.

**Por qué:** Evita el problema N+1: si iteras 100 solicitudes y accedes a `.tipo_cambio.nombre`, sin prefetch son 101 queries; con prefetch es 1.

**Dónde:** Todo `.get()` o `.filter()` que accede a datos relacionados.

**Implementación:**
```python
solicitudes = SolicitudCambio.objects\
    .select_related('explorador_solicitante', 'explorador_receptor', 'tipo_cambio')\
    .filter(estado='pendiente')

# Ahora acceder a solicitud.explorador_solicitante.nombre es O(1) en memoria
```

**Estado:** ✅ **APLICADO**
- `solicitud_aprobacion_service.py` - `select_related()` en todos los `.get()`
- `aprobacion_views.py` - pre-cargas en vistas
- `solicitud_consulta_service.py` - optimización de queries

---

### 13. **Snapshot para Rollback** (Backend)
**Qué es:** Capturar el estado ANTES de aplicar cambios, para poder revertirlo si se cancela dentro de 30 min.

**Por qué:** Los usuarios pueden cambiar de opinión. El snapshot es el "undo" de la operación.

**Dónde:** Antes de crear turnos, cambiar estado, etc.

**Implementación:**
```python
snapshot = { 
    f"{emp.id}:{fecha}": [{"jornada": "AM", "sala_id": 1, ...}, ...]
    for emp, fecha in [(solicitante, f1), (receptor, f2)]
}
DobladaDetalle.objects.filter(pk=detalle.pk).update(snapshot_turnos_previos=snapshot)

# Si se cancela:
DobladaAplicacionService.restaurar_turnos_desde_snapshot(snapshot)
```

**Estado:** ✅ **APLICADO**
- `doblada_aplicacion_service.py` - capturar y restaurar snapshot
- Todas las strategies de aplicación (doblada, D FDS, cambio descanso, permanentes)
- Ventana de 30 min: `aprobacion_views.py` - `VENTANA_CANCELACION_MINUTOS = 30`

---

### 14. **Refresh From DB** (Backend)
**Qué es:** Refrescar los datos del objeto desde la BD después de operaciones que pueden haber cambiadolos (especialmente en locks).

**Por qué:** En concurrencia, si la BD cambió el objeto, el objeto en memoria está stale. Refrescar lee los datos nuevos.

**Dónde:** Después de `select_for_update()` o antes de usar datos críticos.

**Implementación:**
```python
solicitud = SolicitudCambio.objects.select_for_update().get(id=id)
if solicitud.aprobado_receptor:
    solicitud.refresh_from_db()  # Lee desde BD nuevamente
    if not solicitud.aprobado_supervisor:  # Ahora es safe
        ...
```

**Estado:** ✅ **APLICADO**
- `aprobacion_views.py` - `AprobarSolicitudAmbosView` - `refresh_from_db()` después de cada aprobar paso

---

### 15. **Validación Centralizada** (Backend)
**Qué es:** Un módulo único (SolicitudValidator) que contiene todas las validaciones. Reutilizable en crear, editar, etc.

**Por qué:** Evita duplicar lógica de validación. Cambios en reglas se aplican en un solo lugar.

**Dónde:** Antes de crear solicitud, antes de aplicar.

**Implementación:**
```python
class SolicitudValidator:
    @staticmethod
    def validar_empleado_activo(empleado): ...
    @staticmethod
    def validar_jornada_contraria(sol, rec, fecha): ...
    @staticmethod
    def validar_fecha_pago_mismo_mes_cesion(pago, cesion): ...

# Usado en todas las strategies
valido, msg = SolicitudValidator.validar_empleado_activo(solicitante)
```

**Estado:** ✅ **APLICADO**
- `solicitud_validator.py` - 82+ validaciones centralizadas
- Reutilizada en: `doblada_strategy.py`, `d_fds_strategy.py`, `cambio_descanso_strategy.py`, etc.

---

### 16. **Strategy Pattern** (Backend)
**Qué es:** Cada tipo de solicitud (Doblada, D FDS, CT, etc.) tiene su propia clase Strategy con métodos: validar, crear, aplicar, revertir.

**Por qué:** Código limpio y mantenible. Agregar nuevo tipo de solicitud = nueva Strategy, sin tocar las antiguas.

**Dónde:** `solicitudes/services/strategies/`

**Implementación:**
```python
class DobladaStrategy(SolicitudStrategy):
    def validar_solicitud(self, datos): ...
    def crear_solicitud(self, datos): ...
    def aplicar_cambios(self, solicitud): ...
    
class DFDSStrategy(SolicitudStrategy):
    def validar_solicitud(self, datos): ...
    # Cada una con su lógica
```

**Estado:** ✅ **APLICADO**
- `solicitudes/services/strategies/base_strategy.py` - clase base
- 7 strategies: `doblada_strategy.py`, `d_fds_strategy.py`, `cambio_descanso_strategy.py`, 
  `cambio_turno_strategy.py`, `ct_permanente_strategy.py`, `doblada_permanente_strategy.py`
- Factory pattern: `solicitud_factory.py` - selecciona la strategy correcta según tipo

---

### 17. **Restricción de Ventana Temporal** (Backend)
**Qué es:** Solo se puede cancelar solicitud aprobada dentro de los primeros 30 minutos. Después, es final.

**Por qué:** Previene que los usuarios cancelen impulsivamente, pero les da tiempo si se arrepienten.

**Dónde:** `CancelarSolicitudView` en `aprobacion_views.py`

**Implementación:**
```python
VENTANA_CANCELACION_MINUTOS = 30
tiempo_transcurrido = timezone.now() - solicitud.fecha_resolucion
minutos = tiempo_transcurrido.total_seconds() / 60
if minutos > VENTANA_CANCELACION_MINUTOS:
    return json_error('Ya expiró la ventana de cancelación')
```

**Estado:** ✅ **APLICADO**
- `aprobacion_views.py` - `CancelarSolicitudView.VENTANA_CANCELACION_MINUTOS = 30`
- Validado en: `test_cancelacion_fuera_ventana.py` (si existe)

---

### 18. **Deduplicación de Solicitudes** (Backend)
**Qué es:** Evitar que el mismo solicitante envíe múltiples solicitudes al mismo receptor para la misma fecha y tipo.

**Por qué:** Previene spam y confusión (ej: Mariana envía 3 solicitudes de doblada a Jhon para el 15/12).

**Dónde:** Validación antes de crear.

**Implementación:**
```python
existe = SolicitudCambio.objects.filter(
    explorador_solicitante=solicitante,
    explorador_receptor=receptor,
    estado='pendiente',
    fecha_cambio_turno=fecha
).exists()
if existe:
    raise ValidationError('Ya existe una solicitud pendiente tuya con este explorador')
```

**Estado:** ✅ **APLICADO**
- `solicitud_validator.py` - `validar_duplicada_misma_fecha()`
- Todas las strategies

---

### 19. **Error Handling Robusto** (Backend)
**Qué es:** Try/except con logging en operaciones críticas. Retornar tuplas (success, message) en servicios.

**Por qué:** No dejar que errores desconocidos cuelguen la app. Loguear para debugging.

**Dónde:** Servicios, vistas, strategies.

**Implementación:**
```python
try:
    solicitud = SolicitudCambio.objects.get(id=id)
    # ... lógica ...
    return True, "Éxito"
except SolicitudCambio.DoesNotExist:
    return False, "Solicitud no encontrada"
except Exception as e:
    logger.exception("Error al aprobar solicitud")
    return False, f"Error: {str(e)}"
```

**Estado:** ✅ **APLICADO**
- `solicitud_aprobacion_service.py` - todo wrapped en try/except
- Todas las strategies - retornan (success, message) tuplas
- Vistas - catch exceptions y retornan json_error

---

### 20. **Modelo de Deuda Corporativa** (Backend)
**Qué es:** Registrar los 30 minutos que cada explorador debe cuando se dobla (Doblada, Doblada Permanente).

**Por qué:** Los usuarios ven su deuda en "Consolidado de Horas" y se paga vía PDH.

**Dónde:** Al aplicar dobladas.

**Implementación:**
```python
DeudaCorporativaService.crear_deuda_corporativa(
    explorador=quien_se_dobla,
    minutos=30,
    fecha_doblada=fecha,
    solicitud=solicitud,
    comentario='Doblada permanente — 2026-07-22'
)
```

**Estado:** ✅ **APLICADO**
- `deuda_corporativa_service.py` - crear y gestionar deudas
- Doblada simple: cada aplicación = 30 min
- Doblada Permanente: cada ocurrencia en el rango = 30 min
- Regla: solo de lunes a viernes (no sábado/domingo/festivo)

---

### 21. **Deuda Idempotente por (explorador, fecha)** (Backend)
**Qué es:** Antes de crear una `DeudaCorporativa`, verificar que no exista ya una ACTIVA para ese
explorador en esa fecha de doblada. **La clave es por DÍA, sin `solicitud_origen`.**

**Por qué:** Un día doblado = 30 min, siempre. Nadie puede doblar dos veces el mismo día, así que
dos deudas activas en la misma fecha son necesariamente un cobro doble. Los turnos toleran una
re-aplicación (se borran y se recrean, ver `_crear_doblada_dia`), pero la deuda NO: se sumaba
encima. Si `aplicar()` corría dos veces (reintento, re-aprobación manual, comando de mantenimiento),
el explorador terminaba debiendo 60 min por un solo día doblado. **Sin error, sin log de alarma, sin
nada visible** hasta que alguien mira el Consolidado de Horas y no le cuadra.

⚠️ **La clave NO puede incluir `solicitud_origen`** (así estaba la primera versión). Con la solicitud
en la clave, el guard solo veía re-aplicaciones de LA MISMA solicitud: dos solicitudes DISTINTAS que
tocaran el mismo día del mismo explorador creaban 30 min cada una y el cobro doble pasaba entero. La
vía real era la doblada permanente, que creaba sobre sus ocurrencias calculadas sin mirar el estado
del día.

**Solo se miran las ACTIVAS:** si la deuda del día está `cancelada` (solicitud revertida, o el día
dejó de ser doblada) se puede volver a crear — que es justo lo que debe pasar al re-aplicar. Sin ese
filtro, un registro cancelado en el historial del día serviría de coartada permanente: el guard
diría "ya existe" y el explorador doblaría gratis para siempre.

**El mismo filtro al CANCELAR.** Revertir una solicitud cancela sus deudas corporativas, pero solo
las `activa`. Una `pagada` es historia cerrada: revertir no des-paga lo ya pagado. Sin el filtro se
perdía el registro de la compensación **y** el `PDH` que la pagó quedaba apuntando (vía
`deudas_pagadas`) a una deuda que dice estar cancelada; al re-aplicar, el guard no veía nada activo
y volvía a cobrar un día ya pagado. Usa siempre:

```python
DeudaCorporativaService.cancelar_deudas_de_solicitud(solicitud, motivo='…')
```

⚠️ Esto vale solo para `DeudaCorporativa`. En `DeudaExplorador` el estado `pagada` significa otra
cosa —el par de favores está completo, y se marca al CREARLA— así que ahí sí se cancela al revertir
(`exclude(estado='cancelada')`). Copiar el filtro de un modelo al otro rompe uno de los dos.

⚠️ **NO BORRAR este guard.** Parece redundante ("si solo se aplica una vez, ¿para qué comprobar?"),
pero es la capa 3 del orden de defensa: las capas 1 y 2 previenen el doble clic, esta previene el
doble COBRO cuando las otras fallan. Quitarlo reintroduce el cobro doble en silencio.

**Dónde:** Al crear deuda corporativa dentro de un flujo que puede re-ejecutarse.

**Gatillo REAL (no hipotético):** `reaplicar_doblada` y `corregir_doblada_cesion_total` llaman a
`generar_deudas_doblada()` sobre solicitudes ya aplicadas. Se corren justo cuando algo salió mal,
y antes de este guard sumaban una segunda deuda encima de la existente.

**Implementación:** usa SIEMPRE las variantes idempotentes, no las crudas:
```python
DeudaCorporativaService.crear_deuda_corporativa_idempotente(...)  # clave: explorador+fecha_doblada
DeudaService.crear_deuda_idempotente(...)                          # clave: solicitud+deudor+acreedor+fecha_pago_pactada
# Ambas devuelven None si ya existía (útil para no loguear "creada" cuando no se creó).
```

**Las dos mitades del guard.** Crear idempotente evita cobrar dos veces; falta lo simétrico —
apagar cuando el día deja de ser doblada. Los 30 min son de quien REALMENTE dobla, así que hay dos
obligaciones en todo servicio de aplicación:

```python
# 1. Al crear: confirmar el estado REAL del día, no el tipo de solicitud.
if TurnoService.obtener_jornada_display(explorador, fecha) == 'DOBLADA':
    DeudaCorporativaService.crear_deuda_corporativa_idempotente(...)

# 2. Al quitarle una jornada a alguien: cancelar sus 30 min si dejó de doblar.
DeudaCorporativaService.sincronizar_deuda_corporativa(explorador, fecha, motivo='…')
```

Sin el punto 2, ceder una mitad de tu doblada dejaba tu deuda vieja activa mientras el nuevo
receptor —el que de verdad dobla— recibía la suya: 60 min cobrados por un día doblado una vez.
Aplicado en `DobladaDeudaService`, `DFDSAplicacionService`, `CambioDescansoAplicacionService`
(`_sincronizar_deuda_corp`) y `DobladaPermanenteAplicacionService`.

⚠️ **Excepción documentada:** `aplicar_semana_cambio_doblada` NO sincroniza. Es un swap — cada uno
sigue doblando un día de la semana, solo cambia cuál — y esa modalidad no genera deuda nueva, así
que cancelar la del día que sueltan los dejaría doblando gratis.

⚠️ **La clave NO puede usar `fecha_generacion`:** en ambos modelos de deuda ese campo es
`auto_now_add`, así que guarda la fecha de HOY. Un filtro por él nunca coincide y el guard queda
muerto sin dar señal (pasó en la primera versión de este patrón).

**Lección aplicada:** un parámetro que se acepta y se descarta es una trampa. `crear_deuda()` y
`crear_deuda_corporativa()` recibían `fecha_generacion` y lo tiraban en silencio; tres llamadores
le pasaban la fecha de cesión creyendo que se guardaba. **Se eliminó el parámetro de ambas firmas**
en vez de documentarlo: si no existe, nadie puede volver a confiar en él. La fecha del negocio vive
en `fecha_doblada` (corporativa) y `fecha_pago_pactada` / `solicitud_origen` (entre exploradores).

**Estado:** ✅ **APLICADO**
- `deuda_corporativa_service.py` - `crear_deuda_corporativa_idempotente()` ← guard compartido
- `deuda_service.py` - `crear_deuda_idempotente()` ← guard compartido
- `doblada_deuda_service.py` - DOBLADA (corporativa + entre exploradores)
- `d_fds_aplicacion_service.py` - D FDS (entre exploradores; la corporativa no aplica en finde)
- `doblada_permanente_aplicacion_service.py` - `_deuda()`
- `cambio_descanso_aplicacion_service.py` - `_deuda_30_si_doblo()`
- `reprogramacion_doblada_service.py` - `programar()` ← **era el último llamador que usaba la
  variante cruda** (auditoría 2026-07-26). Una excepción sin motivo a una regla declarada
  universal es exactamente donde vuelve a colarse el cobro doble: si el supervisor reprograma
  dos veces el mismo día de pago, se cobraban 60 min por un solo día doblado.
- Tests: `test_matriz_dobladas.py` - `test_regenerar_deudas_no_duplica`;
  `test_doblada_revalidacion.py` - `test_reaplicar_no_duplica_la_deuda`;
  `test_auditoria_huecos.py` - `TestReprogramacionUsaDeudaIdempotente` (incluye un guard de
  regresión que lee el propio fuente para que nadie reintroduzca la variante cruda)

---

### 22. **Reconciliación Completa: cubrir TODOS los modelos de detalle** (Backend)
**Qué es:** Cuando se cancela una solicitud y se restaura su snapshot, la reconciliación
(`reconciliar_dobladas_aprobadas`) re-materializa lo que seguía vigente en esas fechas. Debe
consultar TODOS los modelos de detalle, no solo uno.

**Por qué:** DOBLADA, D FDS y CAMBIO DESCANSO comparten `DobladaDetalle` (`solicitud.doblada`),
pero DOBLADA PERMANENTE vive en `DobladaPermanenteDetalle` (`solicitud.doblada_permanente`). La
consulta filtraba `doblada__isnull=False`, así que las permanentes quedaban fuera: restaurar un
snapshot pisaba su día `DOBLADA PERM` y **la deuda de 30 min quedaba viva sin doblada real**. Peor:
`cancelar_deudas_huerfanas` tampoco la detecta, porque busca deudas SIN solicitud de origen y esta
sí la tiene.

⚠️ **Al agregar un nuevo tipo de solicitud con su propio modelo de detalle**, hay que engancharlo
aquí. Si no, sus efectos se borran silenciosamente al cancelar cualquier solicitud vecina.

**Implementación:**
```python
# Los que comparten DobladaDetalle
candidatas = SolicitudCambio.objects.filter(estado='aprobada', doblada__isnull=False, ...)
# + los que NO lo comparten (cada modelo de detalle propio, su propia consulta)
permanentes = SolicitudCambio.objects.filter(estado='aprobada', doblada_permanente__isnull=False, ...)
for s in permanentes:
    DobladaPermanenteAplicacionService.reaplicar_fechas(s, s.doblada_permanente, fechas)
```

**Nota:** la re-materialización NO re-deriva la elegibilidad del estado en vivo (el día recién
pisado ya no parece "elegible"); usa las fechas del `snapshot_turnos_previos`, que son el registro
de lo que realmente se aplicó.

⚠️ **Y engancharlo en los DOS sentidos** (auditoría 2026-07-26). El patrón tiene dos mitades y
faltaban trozos de ambas:

1. **Qué se re-materializa.** CAMBIO TURNO y CT PERMANENTE no viven en `DobladaDetalle` ni en
   `DobladaPermanenteDetalle` (su snapshot está en la propia solicitud), así que no entraban en
   ninguna de las dos consultas. Restaurar cualquier snapshot que pisara su día los borraba y la
   persona volvía a su jornada base sin que nada avisara.
2. **Desde dónde se dispara.** La reconciliación solo se llamaba desde
   `revertir_doblada_aplicada` (DOBLADA). Los revert de D FDS, CAMBIO DESCANSO, DOBLADA
   PERMANENTE y CT restauraban su snapshot —que arrasa el día entero con un `delete()`— sin
   reconciliar nada después. **Todo `revertir()` que restaure un snapshot debe reconciliar.**

**Estado:** ✅ **APLICADO**
- `doblada_snapshot_service.py` - `reconciliar_dobladas_aprobadas()` y
  `_reconciliar_cambios_de_turno()` (CAMBIO TURNO + CT PERMANENTE)
- `doblada_permanente_aplicacion_service.py` - `reaplicar_fechas()`
- `cambio_turno_strategy.py` - `reaplicar_fechas()` (reconstruye el intercambio de jornadas base)
- `ct_permanente_strategy.py` - `reaplicar_fechas()` (usa las fechas del snapshot, que son
  exactamente las que esa gestión aplicó)
- Llamada a la reconciliación tras restaurar snapshot en: `doblada_aplicacion_service.py`,
  `d_fds_aplicacion_service.py`, `cambio_descanso_aplicacion_service.py`,
  `doblada_permanente_aplicacion_service.py`, `cambio_turno_strategy.py`
- Helpers compartidos: `core/utils/jornada_utils.py` - `obtener_jornada_base()`,
  `obtener_jornada_contraria()` (la re-materialización corre cuando los turnos del día acaban de
  borrarse, así que no puede consultarlos: necesita el estado virtual)
- Tests: `test_doblada_revalidacion.py` - `test_reconciliacion_rematerializa_la_doblada_permanente`;
  `test_auditoria_huecos.py` - `TestReconciliacionCubreTodosLosTipos`,
  `TestTodoRevertQueRestauraSnapshotReconcilia`

---

### 23. **Invariante de Estado por Señal (no solo en el flujo felíz)** (Backend)
**Qué es:** Las reglas que deben cumplirse SIEMPRE ("una solicitud cancelada no deja deudas vivas")
se refuerzan con una señal sobre el modelo, no solo dentro del use case que hace la operación bien.

**Por qué:** `CancelarSolicitudUseCase` cancela las deudas al revertir, pero el campo `estado` se
puede poner en `'cancelada'` por vías que NO pasan por ahí:
- el **admin de Django** (el campo es editable; solo las fechas son readonly),
- un **management command** (`corregir_doblada_cesion_total` lo hacía al unificar una cesión total),
- un **script** de mantenimiento.

Por esas vías la solicitud quedaba cancelada y el explorador seguía debiendo los 30 min. La lógica
que vive solo en el use case protege un camino; la señal protege el dato.

**Dónde:** `solicitudes/signals.py`

**Implementación:**
```python
@receiver(post_save, sender=SolicitudCambio)
def cancelar_deudas_al_cancelar_solicitud(sender, instance, **kwargs):
    if instance.estado != 'cancelada':
        return
    DeudaCorporativa.objects.filter(solicitud_origen=instance, estado='activa').update(estado='cancelada')
    DeudaExplorador.objects.filter(solicitud_origen=instance).exclude(estado='cancelada').update(estado='cancelada')
```
Idempotente: si el use case ya las canceló, el filtro no encuentra filas.

⚠️ **El predicado de la invariante debe cubrir TODOS los estados sin efecto vigente**, no solo el
que motivó el patrón (auditoría 2026-07-26). La señal filtraba `estado != 'cancelada'`, pero
`'reemplazada'` significa lo mismo en lo económico: una solicitud posterior pisó sus turnos
("lo último aprobado gana por día"), así que ya no hay doblada real detrás de esos 30 min.
`_marcar_reemplazadas()` la produce al aplicar un cambio de descanso. La constante
`ESTADOS_SIN_EFECTO_VIGENTE` existe para que al añadir un nuevo estado terminal se decida
explícitamente si entra.

**Estado:** ✅ **APLICADO**
- `signals.py` - `ESTADOS_SIN_EFECTO_VIGENTE = ('cancelada', 'reemplazada')`
- `signals.py` - `cancelar_deudas_al_cancelar_solicitud()` (post_save)
- `signals.py` - `cancelar_deudas_al_borrar_solicitud()` (pre_delete, ya existía)
- Tests: `test_matriz_dobladas.py` - `test_cancelar_por_fuera_del_use_case_cancela_las_deudas`;
  `test_auditoria_huecos.py` - `TestReemplazadaCancelaSusDeudas`

---

### 24. **Revert con Fallback sin Snapshot** (Backend)
**Qué es:** Todo `revertir()` necesita una rama `else` para cuando NO hay snapshot (solicitudes
anteriores a que se implementara el patrón #13): al menos borrar los turnos que esa gestión creó,
identificados por su `tipo_cambio`.

**Por qué:** Sin el `else`, cancelar una solicitud vieja cancelaba las deudas pero dejaba los turnos
aplicados. Es el peor cruce posible: la persona se queda **con la doblada puesta y sin deber los
30 min**. Estaba así en cambio de descanso; doblada, D FDS y la permanente ya lo tenían.

**Implementación:**
```python
if snap:
    DobladaAplicacionService.restaurar_turnos_desde_snapshot(snap)
else:
    Turno.objects.filter(explorador__in=[...], fecha__in=fechas, tipo_cambio='CAMBIO DESCANSO').delete()
```

**Estado:** ✅ **APLICADO**
- `doblada_aplicacion_service.py`, `d_fds_aplicacion_service.py`,
  `doblada_permanente_aplicacion_service.py`, `cambio_descanso_aplicacion_service.py`
- `cambio_turno_strategy.py` / `ct_permanente_strategy.py` - revert dirigido por `tipo_cambio`

---

### 25. **Guardias que Fallan CERRADO** (Backend)
**Qué es:** Cuando a una guardia de seguridad le falta el dato con el que decide, debe BLOQUEAR,
no dejar pasar. Si el dato preciso no está, se usa una aproximación conservadora que puede
sobre-estimar el riesgo (bloquea de más) pero nunca sub-estimarlo.

**Por qué:** La guardia LIFO decidía leyendo el snapshot:
```python
mios = self._pares_afectados(solicitud)
if mios:            # ← sin snapshot, conjunto vacío: la guardia entera se saltaba
    ...comprobar cambios posteriores...
```
Una solicitud sin snapshot —las anteriores al patrón #13, o cualquiera cuyo detalle quedara sin
capturar— se podía cancelar **por debajo de un cambio más reciente, pisándolo**. Es el peor tipo
de fallo: la protección parece estar puesta, no da error, y justamente en el caso raro (datos
viejos, el que nadie prueba) no protege nada.

Es el mismo razonamiento que el patrón #24 (`revertir()` necesita su rama `else` sin snapshot),
aplicado a la decisión en vez de a la ejecución. Si escribes uno, mira si te falta el otro.

**Dónde:** Toda guardia cuya condición dependa de un dato que puede faltar.

**Implementación:** derivar el dato de las fuentes que SÍ existen, y solo entonces decidir.
```python
if snap:
    return set(snap.keys())
return self._pares_derivados_de_fechas(solicitud)  # fechas propias de la solicitud
```

**Estado:** ✅ **APLICADO**
- `cancelar_solicitud.py` - `_pares_afectados()` + `_pares_derivados_de_fechas()`; la guardia LIFO
  ya no está envuelta en `if mios:`
- Test: `test_auditoria_huecos.py` - `TestLIFOFallaCerradoSinSnapshot` (incluye los dos controles:
  sin conflicto real SÍ se puede cancelar, y un cambio posterior en OTRO día no bloquea —
  "fallar cerrado" no puede degenerar en "bloquear siempre")

---

### 26. **Invariantes Estructurales en la BASE DE DATOS** (Backend)
**Qué es:** Cuando una regla del modelo de datos se sostiene solo por la disciplina de N sitios
del código, declararla como restricción en la base de datos.

**Por qué:** "Un día = un conjunto de jornadas sin repetir" dependía de que ~15 sitios
(strategies, servicios de aplicación, restauración de snapshot) recordaran hacer *delete* antes
de *create*. Cualquier ruta nueva que creara sin borrar duplicaba el turno **en silencio**:
ninguna de las tres capas de defensa lo nota, la persona aparece dos veces en la misma jornada y
el Consolidado de Horas cuenta doble. La migración que introdujo la restricción encontró un
duplicado real ya existente en la base de datos — la disciplina ya había fallado al menos una vez.

⚠️ **MySQL no soporta índices únicos parciales**, así que `UniqueConstraint(condition=...)` no
sirve para expresar "único entre los NO anulados". La vía portable es una columna discriminante
nullable: en un índice único los NULL no colisionan entre sí, de modo que muchos anulados
conviven y solo el activo queda restringido. La columna se mantiene sola en `save()` para que la
restricción no dependa de que cada llamador se acuerde de actualizarla.

**Implementación:**
```python
activo_key = models.PositiveSmallIntegerField(null=True, blank=True, default=1, editable=False)

constraints = [models.UniqueConstraint(
    fields=['explorador', 'fecha', 'jornada', 'activo_key'],
    name='turno_unico_activo_por_jornada')]

def save(self, *args, **kwargs):
    self.activo_key = None if self.anulado else 1   # derivada de `anulado`
    ...
```
La migración prepara los datos antes de crear el índice: pone `activo_key = NULL` en los anulados
y resuelve duplicados activos históricos **anulándolos** (no borrándolos: el soft-delete es el
mecanismo de auditoría del proyecto y estos casos hay que poder revisarlos).

**Estado:** ✅ **APLICADO**
- `turnos/models.py` - `Turno.activo_key`, `Meta.constraints`, `Turno.save()`
- `turnos/migrations/0011_turno_unico_activo_por_jornada.py` - `preparar_datos()` + `AddConstraint`
- Test: `test_auditoria_huecos.py` - `TestTurnoUnicoPorJornada` (incluye que doblar AM+PM sigue
  siendo legítimo y que un anulado no bloquea al turno activo que lo sustituye)

---

### 27. **Una sola noción de "hoy": `timezone.localdate()`** (Backend)
**Qué es:** El día de hoy se pide SIEMPRE con `timezone.localdate()`. Nunca con `date.today()`
ni con `timezone.now().date()`.

**Por qué:** El proyecto corre con `USE_TZ=True` y `TIME_ZONE='America/Bogota'` (UTC-5), y el
contenedor **no fija `TZ`**, así que el sistema operativo va en UTC. Con eso hay dos formas
distintas de equivocarse, y el código tenía las dos:

- `timezone.now()` devuelve UTC; pedirle `.date()` da **el día siguiente desde las 19:00 locales**.
- `date.today()` usa la zona del SO: correcta en un PC configurado en Bogotá, **UTC en producción
  y en el CI** (`ubuntu-latest`).

El efecto no es teórico. Medido a las 19:58 hora local:

```
timezone.localdate()  = 2026-07-27   ← el día real
timezone.now().date() = 2026-07-28   ← un día por delante
```

Con eso, **cada validación de "la fecha no puede ser pasada" corría un día adelantada de 19:00 a
medianoche, todos los días**: CT Permanente ofrecía como fecha mínima pasado mañana en vez de
mañana, y una solicitud legítima para el día siguiente se rechazaba con "debe ser posterior a
hoy". El turno PM trabaja de 14:00 a 22:00, o sea justo dentro de la ventana rota.

En los tests el mismo desajuste produce fallos **intermitentes según la hora**: un test que
calcula "ayer" con una noción y compara contra código que usa la otra pasa de día y falla de
noche. Así se descubrió.

**Dónde:** Todo el código de negocio y todos los tests. También en los tests: el CI corre en UTC,
así que mezclar nociones ahí genera fallos que no se reproducen en local.

**Implementación:**
```python
from django.utils import timezone

hoy = timezone.localdate()          # ✅ el día en la zona de la operación

hoy = timezone.now().date()         # ❌ fecha UTC: adelanta un día desde las 19:00
hoy = date.today()                  # ❌ zona del SO: UTC en el contenedor
```

⚠️ Al unificar, cuidado con dos trampas:
1. Hay alias como `_date.today()`; una sustitución de texto ingenua sobre `date.today()` los rompe.
   Usar límite de palabra: `\b_?date\.today\(\)`.
2. No basta con que el archivo contenga el import: tiene que estar **a nivel de módulo**. Varios
   archivos lo tenían dentro de una función y el uso a nivel de módulo reventaba con
   `NameError`. Peor aún, las strategies capturan `Exception` genérica y lo devolvían como
   mensaje de validación ("name 'timezone' is not defined"), así que el fallo de programación
   llegaba al usuario disfrazado de solicitud inválida en vez de dar un 500 visible.

**Estado:** ✅ **APLICADO** (27/07/2026)
- 137 sitios unificados en 62 archivos (`solicitudes`, `turnos`, `empleados`, `permisos`, `core`,
  `config`, `integration_tests`), incluidos los tests
- Quedan 0 usos de `date.today()` y `timezone.now().date()` en código de aplicación
- No se tocó `scripts/` (diagnósticos sueltos, fuera de las rutas de producción)

---

### 28. **El turno REAL (L1) manda sobre la atribución de descanso (L2)** (Backend)
**Qué es:** Cuando una solicitud aprobada dice que alguien descansa un día (cedió su jornada, le
pagan una doblada, doblada permanente), esa atribución se **anula si ese día hay un `Turno` real**.
La guarda vive en `DescansoPorSolicitudService.en_rango` como el set `con_turno_real`, y por ser la
fuente única la heredan `estado_dia`/`estado_mes`, Mis Turnos, los reportes y las validaciones que
usan `TurnoService.dia_comprometido_por_solicitud`.

**Por qué:** Es el corolario técnico de *la última aprobada gana por día*. Al aplicar una doblada se
**borran** los turnos de quien queda libre (el cedente en la cesión, el acreedor en el pago), así
que un turno presente en ese día **solo puede venir de algo aprobado DESPUÉS**. Sin la guarda, un
descanso viejo bloquea el día para siempre aunque la persona ya recuperó jornada real.

Caso que lo destapó (Marco, 30/07/2026): la solicitud #451 le pagaba una doblada el 30/07 (ese día
descansaba); más tarde se aprobó la #560, cuyo **pago cae el mismo 30/07**, así que ese día trabaja
la jornada del acreedor y tiene `Turno` real. Al intentar ceder ese día, la guarda L2 solo veía el
descanso viejo y respondía *"Ya tienes el 30/07/2026 comprometido en otra solicitud aprobada (paga
doblada); no puedes cederlo de nuevo"* — falso: ese día trabaja y sí puede cederlo.

**Dónde:** `solicitudes/services/descanso_solicitud_service.py` — **las CINCO ramas**, incluida
`cambio de día de descanso`.

**Implementación:**
```python
con_turno_real = set(Turno.objects.filter(
    explorador=empleado, fecha__range=(ini, fin)).values_list('fecha', flat=True))
...
for d, e in pago.items():
    if d in con_turno_real:   # ✅ L1 manda: ese día trabaja de verdad
        continue
```

⚠️ **No quitar la guarda** ni resolverla en el llamador: si cada validación decide por su cuenta
si el descanso sigue vigente, la atribución vuelve a divergir entre pantalla y validación — que es
exactamente el problema que este servicio existe para evitar.

⚠️ **CAMBIO DESCANSO ya NO está exento.** Lo estuvo, con el argumento de que "es un intercambio
puro con su propia fuente de verdad". El argumento no se sostenía: esa fuente propia
(`CambioDescansoAplicacionService._mapa_descanso_multi`) tampoco mira los turnos reales, así que
nadie aplicaba la guarda en esa rama. No se veía en las pantallas —todas resuelven L1 antes que
L2— pero sí en `dia_comprometido_por_solicitud`, que llama a `en_fecha` en crudo y alimenta 8
validaciones: producía falsos bloqueos ("ya tienes ese día comprometido en otra solicitud
aprobada") sobre días que la persona trabajaba de verdad. Si alguien vuelve a exceptuar una rama,
que sea porque esa rama comprueba los turnos ella misma.

**Estado:** ✅ **APLICADO** (29/07/2026) · rama CAMBIO DESCANSO incluida (07/08/2026)
- Test: `test_ceder_jornada_recibida.py` -
  `test_si_ese_dia_recupero_jornada_real_si_puede_cederla`
- La rama de doblada permanente ya tenía esta guarda por su cuenta; ahora las tres la comparten

---

### 29. **Un hueco en L2 no da error: da un dato FALSO** (Backend)
**Qué es (regla afilada, tras tres recaídas):**

> **Cada día que muta un aplicador tiene que tener su atribución en L2, y calculada con el campo
> que gobierna ESE día.**

Dos mitades, y las dos fallan solas:
1. **Cada día.** Si `aplicar_*` toca tres días (cesión, pago y `fecha_pago_semana`), los tres
   necesitan atribución. Un día mutado sin motivo es un día invisible.
2. **Con el campo de ese día.** `tipo_cesion` describe la **cesión**; `jornada_pago_sabado` y
   `jornada_cubre_en_pago`, el **pago**; `es_intercambio` manda sobre todos y significa día
   completo por los dos lados. Usar el campo de otro día es un **error de categoría**: da un
   número plausible y equivocado.

Y el corolario operativo: **la lógica de reparto de L2 tiene que espejar la del aplicador**, en el
mismo orden de prioridad. Si `DobladaPagoService` decide en cascada (sábado → `jcp` → resto),
`DescansoPorSolicitudService` decide igual. Cuando cambie una, cambia la otra.

**Por qué:** `estado_dia` resuelve el día por capas y su **último recurso es la jornada BASE**. Si
un día no tiene fila `Turno` (porque la aplicación la borró) **y** L2 no le pone motivo, no salta
ninguna excepción: se responde la jornada base y el sistema afirma que la persona trabaja un día
que tiene libre. El fallo es **silencioso y verosímil**, así que no lo detecta ningún guard — solo
alguien mirando su calendario.

Es el complemento del **#28**: allí L2 sobraba (un descanso viejo que ya no era cierto), aquí L2
faltaba. Los dos son el mismo requisito: **L1 y L2 tienen que contar la misma historia**, porque
donde ninguna habla, contesta la base.

**Los tres síntomas reales (mismo hueco, tres campos distintos).** Los tres se vieron igual — una
persona con el día libre mostrada trabajando su jornada base — y ninguno dio error:

| # | Solicitud | Campo mal leído | Qué mostraba |
|---|---|---|---|
| 1 | INTERCAMBIO mildrey ↔ arley (#565) | `es_intercambio` no se leía; se leía `tipo_cesion` (parcial, ruido del formulario) cuando un swap es día completo por los dos lados | `arley 06/08 → {'trabaja': True, 'jornada': 'AM', 'fuente': 'base'}` y `mildrey 12/08 → {…'PM', 'fuente': 'base'}` |
| 2 | El mismo #565, tras cancelar otra doblada (#566/#567) | La **reconciliación** post-revert no miraba `es_intercambio` y re-aplicaba el swap como cesión/pago | mildrey con una PM sola el 06/08; arley con una AM sola el 12/08 (perdieron la DOBLADA) |
| 3 | DOBLADA Mariana → arley (#568) | `tipo_cesion` (día de la CESIÓN) usado para decidir el día del **PAGO** | `arley 26/08 → {'trabaja': True, 'jornada': 'AM', 'fuente': 'base'}` cuando el deudor le cubría su única jornada |

Y de paso, un cuarto día que no se atribuía a NADIE: `fecha_pago_semana` (la devolución en semana
de un pago en sábado AMBAS). `aplicar_pago_residual_semana` lo muta —el solicitante descansa su
jornada— pero las dos ramas de la atribución solo miraban cesión y pago.

**Dónde:** `solicitudes/services/descanso_solicitud_service.py` (helpers `_full` y `_mitad_pago`,
ramas de cesión, de pago y de `fecha_pago_semana`), `doblada_snapshot_service.reconciliar_dobladas_
aprobadas`, la creación en `doblada_strategy.crear_solicitud` y el comando `reaplicar_doblada`.

**Implementación:**
```python
# 1) El flag manda sobre el tipo_cesion guardado (cesión: día completo por los dos lados)
def _full(det):
    return bool(getattr(det, 'es_intercambio', False))

# 2) El reparto del PAGO se lee de los campos del PAGO, espejando DobladaPagoService
def _mitad_pago(det, tipo):
    if det is None or tipo != 'DOBLADA' or getattr(det, 'es_intercambio', False):
        return 'FULL'                 # D FDS e intercambios: siempre día completo
    if det.fecha_pago.weekday() == 5 and jps in ('AM', 'PM'):
        return jps                    # sábado por mitades
    if jcp in ('AM', 'PM'):
        return jcp                    # el acreedor conserva la contraria
    return 'FULL'                     # parcial sin jcp, completa, AMBAS, fallback

# 3) Y al crear no se guardan datos que se contradicen con lo que se aplica
if datos.get('es_intercambio'):
    tipo_cesion = 'cesion_completa'
    jornada_cedida = None
```

⚠️ **Ningún subconjunto de las tres alcanza.** Solo la creación deja mal las filas ya aprobadas;
solo la atribución sigue guardando filas contradictorias que engañan a la siguiente lectura; y con
las dos pero sin la **reconciliación**, cualquier cancelación posterior vuelve a corromper los
turnos (síntoma 2). Un flag nuevo se despacha en los **tres** sitios: validar, aplicar **y
re-aplicar**.

El arreglo va en el **servicio compartido**, no en el llamador donde se notó: el mismo hueco
alimenta Mis Turnos, el calendario, los reportes y las validaciones.

**Checklist al agregar un sub-flujo, un flag o un día nuevo a un formulario:**
1. Listar **todos** los días que muta `aplicar_*` (¿hay un tercer día como `fecha_pago_semana`?).
2. Por cada día y cada una de las dos partes: *¿queda libre el día completo, media jornada, o nada?*
3. Comprobar que `DescansoPorSolicitudService` responde lo mismo, con el campo de **ese** día y en
   el mismo orden de prioridad que el aplicador.
4. Comprobar que la **reconciliación** despacha ese sub-flujo a su propio aplicador.
5. Señal de humo: si `estado_dia` contesta `'fuente': 'base'` en un día que una solicitud aprobada
   tocó, hay un hueco.

**Estado:** ✅ **APLICADO** (29/07/2026)
- Tests: `test_matriz_dobladas.py` — `TestIntercambioDobladas` (`…_atribuye_descanso_completo_a_los_
  dos_lados`, `…_se_guarda_como_cesion_completa`, `test_cancelar_otra_doblada_no_deshace_el_
  intercambio_vigente`) y `TestDescansoDelAcreedorEnElPago` (día completo en el pago, y la
  contraparte con `jornada_cubre_en_pago` donde sí conserva media jornada)
- Los tres tests se verificaron **fallando** con la lógica vieja antes de darlos por buenos
- Reparación de datos solo en el síntoma 2 (turnos ya escritos, `reaplicar_doblada 565`); 1 y 3 eran
  de lectura y se arreglaron sin tocar la BD
- ⚠️ Los arreglos de atribución/reconciliación viven en módulos ya cargados: **hay que reiniciar el
  servidor** o se sigue corrompiendo con el código viejo (pasó con #567)

---

### 30. **Un snapshot solo vale si NADIE tocó el día** (Backend)
**Qué es:** Restaurar un snapshot no es una operación segura por sí sola. Solo es correcta si el
estado actual sigue siendo el que dejó la solicitud. Por eso se guarda **también el estado
RESULTANTE** (lo que la solicitud dejó), y antes de revertir se compara contra la realidad.

**Por qué:** El patrón #13 guarda el estado PREVIO para poder deshacer. Pero deshacer asume algo
que nadie estaba comprobando: que entre la aprobación y la cancelación **nadie tocó esos días**.

El caso real: A y B hacen un CAMBIO TURNO. Antes de que A cancele, **B modifica su turno por otra
vía** (un permiso especial, una reprogramación, un ajuste manual). Si A cancela,
`restaurar_turnos_desde_snapshot` **borra todo el día de B y escribe el turno viejo del snapshot**
— que B ya no tiene. Resultado: conflicto de jornadas, y el cambio de B desaparecido sin rastro.

**La guardia LIFO (#25) no lo cubre, y es importante entender por qué.** Hace dos cosas que aquí
se quedan cortas:
1. Solo consulta `SolicitudCambio` aprobadas después. **No ve** `PermisoEspecial`, ni
   `ReprogramacionDiaDoblada`, ni el admin de Django, ni un script.
2. Compara **pares `persona:fecha`**, nunca el CONTENIDO del turno.

Comparar contenido cubre por construcción cualquier origen, incluidos los que aún no existen: no
hay que enseñarle una fuente nueva cada vez que aparece una.

**Dónde:** cualquier revert que restaure un estado guardado.

**Implementación:**
```python
# Al aplicar: guardar TAMBIÉN lo que se deja (mismo serializador que el previo, o divergen)
DobladaSnapshotService.capturar_snapshot_resultante(detalle)

# Al cancelar: ¿sigue siendo mío lo que hay ahí?
if esperado != actual:      # tuplas (jornada, sala, tipo_cambio), por conjuntos
    return 'No se puede cancelar: el turno de {quién} ({día}) ya fue modificado…'
```

Tres decisiones que no son obvias:

- **Un solo serializador.** Previo y resultante comparten `serializar_pares()`. Si divergieran, la
  comparación daría conflictos donde no los hay y bloquearía cancelaciones legítimas.
- **El resultante se REESCRIBE, el previo no.** El previo es snapshot-once (#13). El resultante se
  refresca tras cada aplicación **y tras la reconciliación** (`refrescar_resultantes`), que
  reescribe turnos de solicitudes ajenas: sin ese refresco quedarían marcadas como "tocadas por
  otro" y no se podrían cancelar.
- **Aquí el fallback va ABIERTO, al revés que el #25.** Sin resultante no se bloquea (solo se
  registra un warning). No es una excepción caprichosa: en el #25 sobre-estimar no cuesta nada
  (bloquea de más y el usuario cancela primero el reciente), pero aquí sobre-estimar volvería
  incancelable de golpe todo lo anterior al mecanismo. **La dirección en que falla una guardia se
  elige por su coste, no por costumbre.**

**Esta guardia solo cubre los días de LA solicitud que se cancela**, y ahí tiene un punto ciego: no
ve lo que la reconciliación posterior rompe **fuera** de esos días. Ese es el patrón #33, y el
comando `verificar_efecto_aplicado` es la auditoría que encuentra lo que se le escape.

**Y no existe "forzar".** Ni el explorador ni el supervisor desde Gestión. Un bypass reintroduce
exactamente el conflicto que la guardia evita, así que la solicitud se queda **aprobada y
vigente** y el mensaje señala la salida real: **solicitar un cambio de turno nuevo**. Una guardia
sin escapatoria necesita decir qué hacer a continuación, o el usuario la vive como un bloqueo.

**Estado:** ✅ **APLICADO** (30/07/2026)
- Modelos: `snapshot_turnos_resultantes` en `SolicitudCambio`, `DobladaDetalle`,
  `DobladaPermanenteDetalle` (migración `0031`)
- `doblada_snapshot_service.py` - `serializar_pares()`, `capturar_snapshot_resultante()`,
  `refrescar_resultantes()`
- `cancelar_solicitud.py` - `bloqueo_integridad()`, tras `bloqueo_lifo()` en **los dos** caminos
  (explorador y supervisor)
- Captura cableada en los 6 tipos; `test_cancelacion_integridad.py` lo verifica por inspección
  (si un tipo nuevo no la cablea, la guardia cae al fallback abierto **en silencio**)
- `reprogramacion_doblada_service._restaurar_turno_previo` - no recrea si esa jornada ya está
  puesta por otra vía (violaría `turno_unico_activo_por_jornada` y tumbaría la cancelación)
- El patrón hermano en `permisos`: `PermisoMediaJornadaService.puede_revertir_limpio` — de ahí
  salió la idea
- De paso: el JS de cancelación leía `data.message`, pero `json_error` responde en `data.error`.
  **Ningún** motivo de bloqueo llegaba al usuario (tampoco el de LIFO): se veía el texto genérico.

---

## 📊 Matriz Completa de Patrones por Flujo

| Flujo | Button Disable | Select-For-Update | Snapshot Guard | Swal Modal | Form Disable | Cache Invalid. | Validación | Autorización | Logging | Notificaciones | Transacción Atómica |
|-------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **Solicitar (Doblada, CT, etc.)** | ✅ | - | ✅ | - | ✅ | ✅ | ✅ | - | ✅ | - | ✅ |
| **Aprobar Receptor** | ✅ | ✅ | ✅ | ✅ | - | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Aprobar Supervisor** | ✅ | ✅ | ✅ | ✅ | - | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Aprobar Ambos** | ✅ | ✅ | ✅ | ✅ | - | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Rechazar** | ✅ | - | - | ✅ | - | ✅ | ✅ | ✅ | ✅ | ✅ | - |
| **Cancelar (Aprobada)** | ✅ | ✅ | ✅ | ✅ | - | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Aplicar Cambios (Aprobación completa)** | - | - | - | - | - | ✅ | - | - | ✅ | - | ✅ |

**Leyenda:**
- ✅ = Aplicado
- `-` = No aplica o no necesario
- Cada columna es un patrón de la lista anterior

---

### 31. **Un catálogo que gobierna permisos se compara EXACTO y se protege** (Backend)
**Qué es:** Cuando el código resuelve una decisión buscando una fila de catálogo **por nombre**
(el rol "Supervisor", las jornadas "AM"/"PM"), esa fila deja de ser un dato editable y pasa a ser
configuración estructural. Tres obligaciones, juntas o ninguna:

1. **Comparar exacto** (`iexact`), nunca por coincidencia parcial (`icontains`).
2. **Proteger la fila**: no se renombra ni se borra desde el CRUD.
3. **Impedir nombres que se confundan con ella**, y hacer el nombre único.

**Por qué:** `es_supervisor()` resolvía el permiso con `role__nombre__icontains='supervisor'`.
El CRUD de roles no validaba nada, así que **crear un rol llamado "Supervisor de sala" y
asignárselo a alguien concedía acceso total a la operación**: la pantalla de gestión de roles era
una vía de escalada de privilegios, sin explotar ningún bug — usándola como estaba diseñada.

La segunda mitad es simétrica y no se ve en la primera: `EmpleadoRole.role` era `CASCADE`, así que
**borrar el rol "Supervisor" borraba en silencio todas sus asignaciones** y dejaba la operación sin
supervisores. Quien lo borrara se autobloqueaba. Renombrarlo hacía lo mismo por otra puerta: el
permiso lo busca por nombre, así que "Supervisor" → "Coordinador" desactiva el acceso de todos sin
un solo error en el log.

⚠️ **La comparación exacta tiene que ser case-insensitive y la protección también.** En la base de
datos los roles están guardados como `'SUPERVISOR'` y `'EXPLORADOR'`, no en capitalización de
título. Un `nombre == 'Supervisor'` habría dejado a todos los supervisores sin acceso, y un
`es_protegido` exacto habría dejado desprotegida justo la fila que concede permisos. Comprobar el
dato real antes de elegir el operador, no asumir la forma canónica.

**Dónde:** Todo catálogo cuyo `nombre` se consulte desde código (`Role`, `Jornada`).

**Implementación:**
```python
class Role(models.Model):
    SUPERVISOR = 'Supervisor'
    NOMBRES_PROTEGIDOS = (SUPERVISOR, EXPLORADOR)
    nombre = models.CharField(max_length=50, unique=True)

    @property
    def es_protegido(self):
        return (self.nombre or '').strip().lower() in {n.lower() for n in self.NOMBRES_PROTEGIDOS}

class EmpleadoRole(models.Model):
    role = models.ForeignKey(Role, on_delete=models.PROTECT)   # nunca CASCADE

# El permiso, en un único sitio:
user.empleado.empleadorole_set.filter(role__nombre__iexact=Role.SUPERVISOR).exists()
```
Y el form rechaza cualquier nombre que **contenga** un protegido sin serlo, para que no vuelva a
existir un "Supervisor de sala" ambiguo.

**Una sola definición del permiso.** La regla estaba copiada en cinco sitios (`core/mixins.py`,
`core/middleware.py`, `empleados/admin.py`, `empleados/forms.py` ×2,
`empleado_repository.py`); arreglar uno solo habría dejado la escalada viva en los otros cuatro.
`middleware._es_admin()` ahora delega en `es_supervisor()`.

**Estado:** ✅ **APLICADO** (2026-08-01)
- `empleados/models.py` - `Role.NOMBRES_PROTEGIDOS`, `nombre` único, `EmpleadoRole.role` PROTECT
- `empleados/forms.py` - `RoleForm` (normaliza, unicidad case-insensitive, bloquea ambiguos y renombrado)
- `empleados/views/roles.py` - bloqueo de borrado de protegidos + `ProtectedError` con mensaje
- `core/mixins.py`, `core/middleware.py`, `empleados/admin.py`, `empleado_repository.py` - `iexact`
- `empleados/migrations/0006_role_nombre_unico_y_empleadorole_protect.py`
- Test: `empleados/tests/test_roles.py` - `RolePermisoTest.test_rol_parecido_no_concede_permisos`,
  `RoleBorradoTest.test_borrado_no_arrastra_asignaciones` (25 tests)
- Mismo patrón ya aplicado en `Jornada` (AM/PM): si tocas uno, mira el otro

---

### 32. **Un hecho que se registra no se borra, y su fin previsto no es su fin real** (Backend)
**Qué es:** Cuando una fila registra un **hecho** (una sanción, una amonestación, un pago), dos
reglas van juntas:

1. **No se borra**: se cierra con un estado propio que dice quién, cuándo y por qué.
2. **El fin PREVISTO y el fin REAL son campos distintos.** Nunca se pisa uno con el otro.

**Por qué:** La sanción tenía solo `fecha_fin`, haciendo los dos trabajos. Levantarla consistía en
moverla a `hoy - 1 día`. Eso rompía tres cosas a la vez:

- **Perdía la duración original.** Después ya no se podía distinguir "era de 15 días y se levantó a
  los 4" de "siempre fue de 4 días".
- **Producía rangos imposibles.** La sanción automática por deuda nace el día en que el explorador
  intenta solicitar algo, así que su `fecha_inicio` es siempre hoy. Si pagaba **ese mismo día**,
  `fecha_fin` quedaba en *ayer*: un día **antes** del inicio. El `clean()` del propio modelo ya
  prohibía ese rango — pero `save()` directo no lo ejecuta, así que el servicio se lo saltaba.
- **Castigaba justo la conducta que se quería premiar.** El contador de reincidencias buscaba
  sanciones con `fecha_fin < hoy` para agravar la siguiente. Una levantada por pago cumplía ese
  filtro, así que **quien pagaba empezaba la siguiente sanción en 30 días en vez de 15**. Nadie lo
  habría notado: no hay error, solo un número más grande.

⚠️ **El borrado no es solo el botón.** Quitar la vista y la URL deja abierto el admin de Django, y
`has_delete_permission` no cubre la acción masiva `delete_selected`. Hay que cerrar las tres.

⚠️ **Un "estado calculado" no se guarda: se deriva.** El último día que la sanción tuvo efecto
(`fecha_fin_efectiva`) puede quedar antes de `fecha_inicio` cuando se levanta el mismo día. Eso es
correcto como *cálculo* ("no rigió ni un día") y corrupto como *dato en la BD*.

**Dónde:** Todo modelo que registre un hecho con vigencia y pueda terminarse antes de tiempo:
`SancionEmpleado`, y el mismo criterio aplica a `RestriccionEmpleado` si algún día se levanta.

**Implementación:**
```python
class SancionEmpleado(models.Model):
    fecha_fin = models.DateField(null=True, blank=True)      # PREVISTO: no se toca nunca
    levantada_en = models.DateField(null=True, blank=True)   # REAL
    levantada_por = models.ForeignKey(Empleado, on_delete=models.PROTECT, null=True)
    levantada_motivo = models.TextField(blank=True, default='')

    def levantar(self, motivo, supervisor=None, fecha=None):
        if self.levantada_en:      # idempotente: un doble clic no reescribe quién la levantó
            return self
        ...

# Un ÚNICO filtro de "está vigente", reutilizado por todos los consumidores:
def vigentes_en(fecha=None):
    return (Q(fecha_inicio__lte=f)
            & (Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=f))
            & (Q(levantada_en__isnull=True) | Q(levantada_en__gt=f)))
```

**Un solo filtro, no la condición copiada.** El criterio estaba reescrito a mano en el reporte del
día, en Mis Turnos, en el listado y en el servicio de deuda. Añadir el levantamiento a uno solo
habría dejado a los otros mostrando como sancionado a alguien que ya no lo está.

**Estado:** ✅ **APLICADO** (2026-08-02)
- `empleados/models.py` - `levantada_en/_por/_motivo`, `levantar()`, `estado`, `fecha_fin_efectiva`
- `empleados/sancion_utils.py` - `vigentes_en()` como filtro único
- `solicitudes/services/deuda_corporativa_service.py` - levanta en vez de recortar; el contador de
  reincidencias excluye las levantadas
- `empleados/views/sanciones.py` - `SancionLevantarView` sustituye a `SancionDeleteView`
- `empleados/admin.py` - `has_delete_permission` + `delete_selected` fuera
- `turnos/services/reporte_dia_service.py`, `turnos/api/views/turnos_mes.py` - usan `vigentes_en`
- `empleados/migrations/0007_historicalsancionempleado_levantada_en_and_more.py`
- Tests: `empleados/tests/test_sanciones.py` (`SancionLevantarTest`),
  `solicitudes/tests/test_sancion_automatica_deuda.py` (7 tests, incluye la reincidencia)

---

### 33. **Al re-aplicar, el conjunto de días afectados se CIERRA antes de escribir** (Backend)
**Qué es:** Restaurar un snapshot arrasa el día entero, así que después hay que re-materializar lo
que sigue vigente ahí (#22). Pero **un re-aplicador no escribe solo el día por el que fue
seleccionado**: escribe TODO su efecto. Antes de re-aplicar nada, el conjunto de pares
`(persona, día)` se amplía con lo que esas re-aplicaciones van a escribir, hasta que deja de
crecer. Solo entonces se re-aplica, todo de una vez y en orden de `fecha_resolucion`.

**Por qué:** los días que un re-aplicador toca "de paso" quedaban fuera del conjunto, así que las
solicitudes que vivían en ellos —**vigentes, y posteriores**— se borraban sin que nada avisara.

El caso real (D FDS #584, agosto 2026): se cancela una D FDS que toca el 15/08 y el 08/08. La
reconciliación re-aplica un CAMBIO DESCANSO cuya cesión cae el 15/08 — correcto—, pero ese
re-aplicador **reescribe los dos findes completos** (sáb↔dom de cesión y de devolución), y de paso
pisó el 09/08 y el 16/08, donde vivía una D FDS **aprobada después** y aún vigente. Como esos dos
días nunca entraron en `afectados`, nadie la re-materializó: quedó aprobada, con su deuda viva y su
mensaje visible en Mis Turnos ("Mariana trabaja por ti, pagarás el 16/08"), pero **sin un solo turno
que la respaldara**. Los turnos decían justo lo contrario que las capas.

**Ninguna guardia lo detecta**, y por eso es un patrón y no un bug puntual: la de integridad (#30)
compara solo los días de la solicitud que se cancela, y la LIFO (#25) solo mira si hay algo más
reciente sobre esos mismos días. La víctima está **fuera del radar de ambas**.

**Dónde:** cualquier reconciliación o re-aplicación masiva posterior a un revert.

**Implementación:**
```python
# Cierre ANTES de escribir: recorrido de grafo sobre pares (persona, día).
for _ in range(MAX_VUELTAS_CIERRE):          # tope = red de seguridad, no límite de corrección
    nuevos = set()
    for s in _solicitudes_que_tocan(fechas, exploradores, excluir_id):
        nuevos |= _pares_que_reescribe(s, fechas)   # lo que ESA solicitud va a escribir
    if nuevos <= afectados:
        return afectados                     # convergió: nadie aporta días nuevos
    afectados |= nuevos                      # una vuelta más: puede haber descubierto solicitudes
                                             # alcanzables solo por los días recién añadidos
```

Cuatro decisiones que no son obvias:

- **Se cierra ANTES de aplicar, no en pasadas sucesivas de aplicación.** Si se aplicara en cada
  vuelta, una solicitud descubierta en la vuelta 2 se escribiría después de una de la vuelta 1
  aunque fuera **más antigua**, y ganaría el día quien no debe. Con el cierre primero, todas las
  vigentes se re-aplican **una vez** y en orden global de `fecha_resolucion`: sigue ganando el día
  la última aprobada, que es el principio del sistema.
- **Se pregunta qué se va a escribir REALMENTE, no todas las fechas de la solicitud.** Añadir un día
  que nadie va a tocar es igual de dañino por el otro lado: la reconciliación lo re-aplicaría y
  pisaría cambios ajenos en un día que estaba bien. De ahí que `_pares_que_reescribe` distinga por
  tipo: CAMBIO DESCANSO de finde → sus cuatro días; D FDS e intercambio → cesión **y** pago siempre;
  DOBLADA normal → **solo** el lado que coincide; CT y permanentes → nada (sus `reaplicar_fechas`
  ya vienen acotados a las fechas dadas y nunca escriben fuera).
- **`_pares_que_reescribe` es ESPEJO del dispatch de la reconciliación.** Son dos listas de casos
  por tipo que tienen que decir lo mismo. Si cambia lo que se re-aplica y no se cambia aquí, vuelve
  la pérdida silenciosa. Van comentadas la una a la otra.
- **UN solo orden global, no tres bloques.** Las candidatas viven en modelos distintos (`doblada`,
  `doblada_permanente`, snapshot en la propia solicitud) y por eso se consultan por separado — pero
  eso es un detalle de persistencia, **no un orden de aplicación**. Re-aplicarlas en tres bloques
  consecutivos hacía que una doblada permanente aprobada en junio se re-materializara **después**
  de una D FDS aprobada en julio y le ganara el día. Y la colisión es real: ceder un sábado que se
  trabaja por una permanente es legítimo, así que dos solicitudes vigentes pueden reclamar el mismo
  (persona, día); quien escribe última gana. Con el orden invertido, la persona volvía a trabajar el
  día que había cedido **mientras su sustituto también lo tenía asignado**: dos personas en un
  turno. Se juntan todas y se ordenan una sola vez por `fecha_resolucion`. *Regla general: cuando
  varias fuentes escriben el mismo dato, el orden lo decide el negocio, nunca el modelo de datos.*
- **El resultante solo se refresca a quien SÍ se re-aplicó.** `refrescar_resultantes` recorría todas
  las vigentes que compartían un día con el conjunto afectado. Para las re-aplicadas es correcto
  (su resultante es nuevo de verdad), pero para una que **no** se re-materializó es un desastre
  silencioso: su efecto está roto y refrescar graba el estado ROTO como "lo que esta solicitud
  dejó". Desde ese momento la discrepancia **deja de existir para el sistema**: `bloqueo_integridad`
  no la ve y la auditoría dice que todo está bien. Pasó con la D FDS #554, cuyo resultante acabó
  afirmando que había dejado un turno `CAMBIO DESCANSO` en el día que su dueño cedió — algo que una
  D FDS no puede dejar jamás. *Un mecanismo que "pone al día" un valor de referencia solo debe
  tocar lo que él mismo acaba de construir; si adopta lo que encuentra, deja de ser referencia.*
- **Re-aplicar reconstruye TURNOS, no estados.** `CambioDescansoAplicacionService.aplicar` marcaba
  como `reemplazada` la solicitud previa del día — correcto al aplicar de verdad, veneno al
  reconstruir: convertía en reemplazada una solicitud vigente. La reconciliación la llama con
  `marcar_reemplazos=False`. **Todo re-aplicador debe ser puro en turnos**; cualquier efecto
  secundario (estados, deudas, notificaciones) va fuera.

**El tope de vueltas.** La convergencia ya está garantizada por construcción (cada vuelta solo
**añade** pares y el universo es finito), así que el tope no es lo que hace terminar el bucle: es
protección contra un futuro `_pares_que_reescribe` no determinista o una cadena patológica. Sin él,
el bucle colgaría **dentro de la transacción y con los locks de `bloquear_partes` tomados**,
bloqueando las aprobaciones de todos — peor que un resultado incompleto. Al agotarse, se reconcilia
con lo alcanzado y queda un `WARNING` con el id de la solicitud, que es la señal para investigar. El
tope va holgado (8) porque las cadenas reales son de 2-3 saltos y una vuelta cuesta **dos consultas
de solo lectura**: las escrituras ocurren una sola vez, después del cierre.

**Corolario de auditoría:** que el sistema pueda perder el efecto de algo aprobado sin avisar es en
sí mismo un agujero. `verificar_efecto_aplicado` compara el `snapshot_turnos_resultantes` de **toda**
solicitud aprobada contra los turnos reales y lo repara vía reconciliación. Una guardia protege el
momento; una auditoría encuentra lo que ya se escapó.

Con un límite que conviene tener presente: **la auditoría se apoya en el resultante, así que un
resultante ya corrompido la deja ciega**. El origen de esa corrupción está cerrado (el punto del
refresco, arriba), pero lo grabado antes no se cura solo: por eso
`verificar_efecto_aplicado --solicitud N --reparar` reconcilia esa solicitud **aunque no detecte
nada**. Toda referencia que se compara contra la realidad necesita una vía de reparación que no
dependa de esa misma referencia.

**Estado:** ✅ **APLICADO** (2026-08-06)
- `doblada_snapshot_service.py` - `_cerrar_afectados()`, `_solicitudes_que_tocan()`,
  `_pares_que_reescribe()`, `MAX_VUELTAS_CIERRE`; llamado al entrar en
  `reconciliar_dobladas_aprobadas()`
- `doblada_snapshot_service.py` - `_candidatas_ordenadas()` + `_reaplicar_una()`: los tres bloques
  de re-aplicación pasan a ser **una pasada ordenada**. Sustituyen a `_reconciliar_cambios_de_turno()`
- `cambio_descanso_aplicacion_service.py` - `aplicar(..., marcar_reemplazos=True)`; la
  reconciliación lo pasa en `False`
- `solicitudes/management/commands/verificar_efecto_aplicado.py` - auditoría y `--reparar`
- Tests: `solicitudes/tests/test_reconciliacion_colateral.py` (8 tests: la regresión, el cierre, el
  no-reemplazo, que la DOBLADA normal **no** arrastre su otro lado, y que una permanente antigua no
  le gane el día a una D FDS reciente). Los tres que cubren un fallo real se verificaron **en rojo
  primero**, desactivando el arreglo

---

### 34. **Una caché de lectura declara QUÉ cubre, y lo que no cubre cae al camino lento** (Backend)
**Qué es:** Cuando se precarga estado en lote para acelerar un barrido, la tabla precargada **no
es "el estado"**: es el estado de un conjunto concreto de `(empleados, rango)` y calculado con un
conjunto concreto de parámetros. El accesor pregunta SIEMPRE si la celda que le piden está dentro
de esa cobertura; si no lo está, va a la base de datos como si no hubiera caché.

**Por qué:** una caché de lectura que sirve celdas que no calculó no da un error — da un **dato
falso** (mismo peligro que #29). Y como la precarga se hace por rendimiento, el que la escribe
está pensando en consultas, no en semántica: es fácil ampliar el `hit` "un poquito" y romper una
regla sin que ningún test lo note, porque el resultado sigue siendo un dict con la forma correcta.

El caso concreto: `precargar_ct_permanente` construye la tabla **sin exclusiones**. Pero
`_dia_libre_por_solicitud(emp, fecha, excluir_id)` existe precisamente para ignorar UNA solicitud
—la propia— al re-validar o re-aplicar algo ya aprobado. Si la caché atendiera también las
llamadas con `excluir_id`, esa solicitud **se auto-excluiría**: se vería a sí misma ocupando el
día y concluiría que el día no está libre. Por eso el `excluir_id is not None` corta el hit ANTES
de mirar la cobertura.

**Reglas:**
1. El contexto guarda su cobertura explícita (`emp_ids`, `ini`, `fin`) y expone `cubre()`.
2. Todo accesor empieza con `if ctx is not None and ctx.cubre(...)`; el `else` es el código
   original intacto. **Nunca** se borra el camino individual.
3. Un parámetro que cambia el resultado y NO entró en la precarga (aquí `excluir_id`) invalida el
   hit por sí solo.
4. Si la precarga falla, se sigue **sin caché** (correcto y lento), no con una tabla a medias.
5. Vida corta: se abre y se cierra dentro de una petición (`contextmanager` + `ContextVar`), así
   que no puede quedar obsoleta ni filtrarse entre hilos o peticiones.
6. Si ya hay una precarga activa que cubre lo pedido, se **reutiliza**; anidar otra la ocultaría y
   dejaría fuera de cobertura celdas que la de fuera sí tenía.

**Cómo se verifica (obligatorio):** ejecutar el camino con la caché ACTIVA y DESACTIVADA y comparar
los resultados, no solo los tiempos. Aquí se hizo en tres niveles: `estado_rango_multiple` contra
`estado_dia` celda a celda (1.236 celdas, 0 diferencias), cada endpoint con y sin precarga
(idéntico), y `obtener-jornadas-rango` contra una reimplementación de su lógica original día a día.

**Implementación:**
```python
def _dia_libre_por_solicitud(empleado, fecha, excluir_id=None):
    # Con `excluir_id` NO se usa la caché: la tabla precargada se construye sin exclusiones.
    ctx = _CTX_CT_PERMANENTE.get()
    if excluir_id is None and ctx is not None and ctx.cubre(empleado, fecha):
        return fecha in ctx.descansos.get(empleado.id, {})
    return TurnoService.dia_comprometido_por_solicitud(empleado, fecha, excluir_id=excluir_id) is not None
```

**Estado:** ✅ **APLICADO** (2026-08-06)
- `ct_permanente_helper.py` - `_ContextoCTPermanente`, `precargar_ct_permanente()`,
  `_CTX_CT_PERMANENTE`; accesores `_estado_ct`, `_dia_libre_por_solicitud`, `_tipo_cambio_previo`,
  `_es_festivo`, `_es_mantenimiento`, `_es_temporada`
- `turno_service.py` - `estado_rango_multiple()` (batch real, ~8 consultas fijas);
  `estado_mes`/`estado_rango` delegan ahí

⚠️ **NO tocar sin releer esto:** ampliar el `hit` de `_dia_libre_por_solicitud` a las llamadas con
`excluir_id` rompe la re-validación de solicitudes ya aprobadas, **en silencio y sin test rojo**.

---

### 35. **La regla se valida sobre el campo que MANDA al aplicar, no sobre el que la declara** (Backend)
**Qué es:** cuando dos campos describen la misma decisión —uno *declarativo* (`tipo_cesion`) y otro
*operativo* (`jornada_cedida`, el que el aplicador lee de verdad para decidir qué escribir en
`Turno`)— la validación tiene que mirar **el operativo**. Validar solo el declarativo deja la regla
sin dientes: basta que los dos se contradigan para que la validación diga "sí" y el aplicador haga
lo contrario.

**Por qué:** el caso concreto. La regla "un festivo se cede ENTERO" se comprobaba así:

```python
if es_cesion_festivo and tipo_cesion in ('cesion_parcial_am', 'cesion_parcial_pm'):
    return False, "...debes cederla entera..."
```

Pero `DobladaAplicacionService._aplicar_cesion` no consulta `tipo_cesion` para elegir la jornada:

```python
if detalle.jornada_cedida:            # <-- ESTE es el que manda
    jornada_cedida_nombre = detalle.jornada_cedida.upper()
else:
    jornada_cedida_nombre = jornada_solicitante.nombre.upper()
```

Así que `tipo_cesion='cesion_completa'` + `jornada_cedida='AM'` **pasaba la validación intacto** y
cedía media jornada del festivo. Y no era un POST artesanal: el formulario llegaba ahí solo
(el selector AM/PM reaparecía al salir del modo intercambio y el radio quedaba marcado).

**Reglas:**
1. Antes de escribir una validación, **abrir el aplicador** y ver qué campo lee para decidir. Ese es
   el que hay que validar.
2. Si dos campos pueden contradecirse, la regla los cubre a los dos (`tipo_cesion in (...) or
   jornada_cedida`), y además se **normalizan al crear** (mismo trato que el intercambio en #29).
3. La normalización al crear no sustituye a la validación: cubre los flujos que crean sin validar;
   la validación cubre la re-validación al aprobar de filas ya guardadas.

**Estado:** ✅ **APLICADO** (2026-08-06)
- `doblada_strategy.py` - `validar_solicitud()` (la regla mira también `jornada_cedida`);
  `crear_solicitud()` (normaliza `jornada_cedida=None` en festivo)
- Test: `test_cesion_festivo_con_jornada_cedida_suelta_rechazada`

---

### 36. **En un día de jornada VIRTUAL, el día completo no se deduce de la jornada base** (Backend)
**Qué es:** en festivo (y en finde) la doblada **no existe como filas `Turno`**: la calcula la
rotación. Quien deriva "qué jornada cede esta persona" leyendo su asignación base obtiene **una
sola** (AM o PM) — la base — cuando ese día realmente trabaja AM+PM. El día completo hay que
construirlo explícitamente, no inferirlo.

**Por qué:** este es el fallo que la regla #35 dejaba ver a medias. Con `jornada_cedida` vacío
(cesión completa, correcta), el aplicador caía en `jornada_solicitante.nombre` y le daba al receptor
**solo la PM**. El emisor sí quedaba sin turnos (día completo cedido) pero el receptor cubría media
jornada: **el festivo quedaba a medio cubrir y nadie protestaba** — la validación post-aplicación
daba ✅ ("receptor tiene 1 jornada(s): PM") porque solo comprobaba que tuviera *alguna*.

Es el mismo malentendido que ya costó el patrón de Mis Turnos ("un día de finde es DÍA COMPLETO, no
una DOBLADA"): en los días de jornada virtual, **la ausencia de `Turno` no significa media jornada
ni descanso**.

**Reglas:**
1. En festivo/finde, preguntar por la rotación (`TurnoService.dobla_en_festivo`), **no** por
   `AsignarJornadaExplorador` ni por la presencia de filas `Turno`.
2. Ceder un día completo virtual = crear **AM y PM** para el receptor, explícitamente.
3. Una validación post-aplicación que solo cuenta "≥1 jornada" no protege de esto: **quien aplica
   DECLARA el conjunto de jornadas esperado** y la guardia lo comprueba. `exists()` distingue "se
   escribió" de "no se escribió"; no distingue "se escribió bien" de "se escribió DE MENOS", que es
   justo la forma que tenía este bug.
4. El log de la guardia dice contra qué comparó (`esperadas: AM, PM`) o admite que no tenía valor
   esperado. Un ✅ junto al dato equivocado —`tiene 1 jornada(s): PM` en un festivo— es peor que no
   tener guardia: produce evidencia de que no hay fallo.

**Estado:** ✅ **APLICADO** (2026-08-06)
- `doblada_aplicacion_service.py` - `aplicar_doblada_cesion()`, rama `_cede_festivo_completo`;
  validación post-aplicación extraída a `_validar_post_aplicacion(..., jornadas_esperadas_receptor)`
  y propagada a `validar_turnos_doblada_cesion()` (festivo → `{AM, PM}`; resto → la jornada cedida)
- Tests: `test_aplicar_cesion_festivo_receptor_queda_con_dia_completo` (queda `{'PM'}` sin el fix) y
  `test_guardia_post_aplicacion_rechaza_festivo_a_medias` (la red ve el día a medias)

⚠️ **NO tocar sin releer esto:** derivar la jornada cedida desde la jornada base es correcto en día
ordinario y **falso** en festivo/finde. Cualquier `jornada_solicitante.nombre` en un flujo que
pueda caer en un día especial es sospechoso.

---

### 37. **Un desplegable de candidatos filtra por las MISMAS fechas que valida el envío** (Backend)
**Qué es:** casi toda operación de este sistema toca **dos fechas** (cesión y pago/devolución) y
**dos personas**. El endpoint que llena el desplegable de compañeros y la validación del envío son
**dos implementaciones de la misma regla**. Cuando el desplegable filtra por una sola de las dos
fechas, ofrece candidatos que el envío rechaza.

**Por qué:** el usuario no ve un bug, ve una **contradicción**: el sistema le propone a alguien y
acto seguido le dice que no puede. Peor, entre medias la ficha del candidato muestra texto
**calculado sobre la fecha equivocada** ("Marco trabaja libre → le cubres su PM"): no se puede
cubrir una jornada que no trabaja. El dato falso llega antes que el rechazo.

Este patrón se rompió **tres veces por sitios distintos** en el mismo formulario (Cambio de Día de
Descanso), lo que lo hace estructural y no un descuido puntual:

| Sub-flujo | El desplegable miraba | La validación mira además |
|---|---|---|
| Intercambiar el día / Jornadas partidas | mi día de descanso | el día de pago (`fecha_descanso_receptor`) |
| Que me cubran mi día | el día de cesión | que trabaje esa jornada el día de pago |
| Cambio de doblada | "¿tiene doblada esa semana?" | que esté LIBRE mi día completo |

**Reglas:**
1. Si la validación consulta N fechas, el endpoint de candidatos consulta **las mismas N**. La
   condición del desplegable debe poder leerse al lado de la del validador y decir lo mismo.
2. El endpoint recibe la segunda fecha **como parámetro explícito**; no la deduce ni la asume.
   Si no llega, o no filtra (y se documenta), o es error — nunca "filtra por una y ya".
3. Un candidato no seleccionable se devuelve **con su motivo**, no se oculta: "no trabaja PM el
   11/08" enseña la regla; una lista más corta, no.
4. El texto informativo de un candidato se calcula sobre la fecha a la que corresponde. Si la
   operación abarca dos fechas, la ficha las nombra por separado.
5. Antes de dar por bueno el filtro, **desactivarlo y ver caer el test**. Un test que pasa con y
   sin el filtro no prueba el filtro.

**Estado:** ✅ **APLICADO** (2026-08-07)
- `api_disponibles_ct_preview.py` - `_filtrar_por_descanso_receptor()` + param `fecha_descanso_receptor`
- `api_fin_semana.py` - `CoberturaCandidatosView`: `disponible` considera también `fecha_pago`
- `api_dobladas_consulta.py` - `DobladasSemanaView`: solo compañeros libres mi día de cesión
- Tests: `test_candidatos_excluye_a_quien_no_trabaja_esa_jornada_el_dia_de_pago`,
  `test_cambio_doblada_candidatos.py` (los 3 verificados por sabotaje)

⚠️ **NO tocar sin releer esto:** cualquier endpoint cuyo nombre sea "…disponibles", "…candidatos"
o "…semana" y que reciba UNA sola fecha mientras su validación usa dos es sospechoso. El
precedente correcto vive en `ExploradoresConDobladaView` (`api_dobladas_consulta.py`), que sí
filtra por el día A **y** el día B desde el principio.

---

### 38. **Una credencial que actúa SIN sesión se firma en un solo sitio, caduca y falla cerrada** (Backend / Seguridad)
**Qué es:** los correos de esta aplicación llevan enlaces que **aprueban o rechazan sin iniciar
sesión**. En un enlace así el token no es un identificador: es **la credencial completa**. Quien
sepa fabricarlo actúa en nombre de otro. La firma de esos tokens vive en **un único módulo**
(`solicitudes/services/tokens_aprobacion.py`) y todo el mundo delega en él.

**Por qué:** este patrón nació de un fallo real. La firma estaba duplicada en **seis** sitios, todos
con la clave escrita en el código (`b'secret_key_change_this'`, con el comentario "Cambiar en
producción" que nunca se atendió). Cualquiera con acceso al repositorio podía aprobar cualquier
solicitud. Y lo que lo convierte en patrón y no en anécdota: **la sexta copia estaba en OTRA app**
(`permisos/services.py`) y se pasó por alto en la primera revisión. Con la lógica duplicada, cerrar
cinco de seis agujeros equivale a no cerrar ninguno.

**Reglas:**
1. **Una sola implementación de la firma.** Si aparece un segundo `hmac.new(...)` o un segundo
   `signing.dumps(...)` para el mismo propósito, el patrón ya está roto.
2. **La clave sale de `SECRET_KEY`**, nunca de un literal. En AWS eso obliga a que todas las
   instancias compartan la MISMA `SECRET_KEY` (una entrada de Secrets Manager/SSM, no un valor por
   tarea): si no, los enlaces fallan de forma intermitente según a dónde encamine el ALB.
3. **Caduca.** `APPROVAL_LINK_MAX_AGE_DAYS` (30 por defecto). Una credencial sin caducidad es
   permanente por definición.
4. **Sal distinta por circuito.** Solicitudes de cambio y permisos especiales usan sales separadas,
   de modo que un token de un circuito no vale en el otro aunque los firme la misma clave.
5. **Falla cerrada.** Firma inválida, caducada o de otra persona → `False`. Nunca una excepción que
   alguien capture como "sigue adelante".
6. **Se ata a quien ocupa el rol HOY**, no a quien lo ocupaba al enviarse: si a un explorador le
   cambian de supervisor, el enlace del anterior deja de servir.
7. **El uso único se apoya en el estado del negocio**, no en una lista de tokens gastados:
   `_ya_resuelto_para()` consulta la base de datos, que es el almacén compartido entre instancias.
   Una lista propia añadiría dependencia de Redis sin ganar nada.

**Dónde vive:**
- `solicitudes/services/tokens_aprobacion.py` — fuente única (firma, caducidad, sales).
- Delegan: `solicitudes/services/email_service.py`, `solicitudes/views/aprobacion_email.py` (4
  vistas), `permisos/services.py`.
- Tests: `solicitudes/tests/test_tokens_aprobacion.py` (25), incluido uno que comprueba que un
  token firmado con la clave antigua ya **no** se acepta.

⚠️ **NO tocar sin releer esto:** antes de dar por cerrada una vulnerabilidad de credenciales,
busca la lógica duplicada **en todo el repositorio, no solo en la app donde la encontraste**
(`grep -rn "hmac.new\|signing.dumps" --include=*.py .`). Aquí la sexta copia vivía en otra app.

---

## 🛠️ Checklist para Nuevos Flujos o Cambios de Estado

Cuando crees un nuevo flujo que modifique estado, verifica TODOS estos puntos:

**Frontend (UI/UX):**
- [ ] **¿Hay un botón que dispara la acción?** → **Button Disable** (#1) - deshabilitar + "Procesando..."
- [ ] **¿Hay un formulario?** → **Form Disable** (#5) - deshabilitar campos mientras se procesa
- [ ] **¿Es una acción destructiva (rechazar, cancelar, eliminar)?** → **Swal Modal** (#4) - confirmación
- [ ] **¿Hay validaciones simples?** → **Validación Cliente** (#8) - feedback inmediato al usuario

**Backend (Lógica):**
- [ ] **¿Hay un cambio de estado crítico (pendiente → aprobada)?** → **Select-For-Update** (#2) - lock pessimista
- [ ] **¿Hay datos que se restaurarán si se cancela?** → **Snapshot Guard** (#3) - capturar ANTES de mutar
- [ ] **¿Hay múltiples cambios en la BD?** → **Transaction.atomic()** (#7) - todo o nada
- [ ] **¿Afecta datos que otros usuarios leen?** → **Cache Invalidation** (#6) - invalidar caché después
- [ ] **¿Hay reglas de negocio?** → **Validación Servidor** (#8) - SIEMPRE validar en servidor
- [ ] **¿Afecta a otros usuarios?** → **Autorización** (#9) - verificar permisos
- [ ] **¿Es operación importante?** → **Logging** (#10) - registrar en logs
- [ ] **¿Afecta al usuario?** → **Notificaciones** (#11) - notificar si cambió su estado
- [ ] **¿Hay relaciones FK/M2M?** → **Select_Related/Prefetch** (#12) - evitar N+1 queries

**Opcional (según contexto):**
- [ ] **¿Hay datos concurrentes que necesitan refrescarse?** → **Refresh From DB** (#14)
- [ ] **¿Es validación compleja?** → **Validación Centralizada** (#15) - usar módulo centralizado
- [ ] **¿Es un nuevo tipo de solicitud?** → **Strategy Pattern** (#16) - nueva clase Strategy
- [ ] **¿Hay límite de tiempo?** → **Ventana Temporal** (#17) - solo cierto tiempo
- [ ] **¿Hay deudas/pagos?** → **Deuda Corporativa** (#20) - registrar deuda en consolidado
- [ ] **¿Se crea una deuda que podría re-crearse?** → **Deuda Idempotente** (#21) - verificar antes de crear
- [ ] **¿El tipo nuevo tiene su propio modelo de detalle?** → **Reconciliación Completa** (#22) - engancharlo
- [ ] **¿Hay una regla que debe cumplirse SIEMPRE, no solo en el flujo feliz?** → **Invariante por Señal** (#23)
- [ ] **¿Escribiste un `revertir()`?** → **Fallback sin Snapshot** (#24) - la rama `else` para datos antiguos
- [ ] **¿Tu `revertir()` restaura un snapshot?** → **Reconciliación** (#22) - el restore arrasa el
      día entero: hay que reconstruir lo que siga vigente en esas fechas
- [ ] **¿Escribiste una guardia que decide con un dato que puede faltar?** → **Fallar Cerrado**
      (#25) - sin el dato, bloquear; nunca dejar pasar en silencio
- [ ] **¿La regla es estructural (unicidad, exclusión) y depende de la disciplina del código?** →
      **Invariante en la BD** (#26) - declararla como restricción
- [ ] **¿Alguna decisión (sobre todo de permisos) se resuelve buscando una fila de catálogo por
      nombre?** → **Catálogo que gobierna permisos** (#31) - comparar exacto, proteger la fila,
      impedir nombres ambiguos y FK `PROTECT`
- [ ] **¿Precargaste estado en lote para acelerar un barrido?** → **Caché que declara su cobertura**
      (#34) - `cubre()` explícito, el camino individual intacto, y todo parámetro que cambie el
      resultado (`excluir_id`) invalida el hit. Verificar con caché ON vs OFF, no solo el tiempo
- [ ] **¿Puede haber errores?** → **Error Handling** (#19) - try/except + logging

---

## 📝 Notas de Implementación

### Cuándo NO aplicar estos patrones
- **Filtros/búsquedas**: No modifican estado, no requieren protección
- **Navegación entre páginas**: No requiere protección
- **Lecturas/GET**: No requieren protección
- **Vistas públicas (sin login)**: Raramente requieren protección de doble clic

### Orden de defensa (capas independientes)
Si una falla, la otra resguarda:

1. **Frontend** (Button Disable, Form Disable, Swal) → previene 99% de dobles clics
2. **Backend Lock** (Select-For-Update) → serializa peticiones concurrentes que sí lleguen
3. **Idempotent Guards** (Snapshot Guard, Check estado) → evita corrupción si se re-aplica

**Ejemplo real (Bug #287):**
- Capa 1 falló: usuario hizo doble clic (frontend no lo detuvo)
- Capa 2 falló: no había select_for_update (backend no serializó)
- Capa 3 falló: no había snapshot guard (segunda aplicación sobrescribió el snapshot)
- **Resultado:** snapshot corrupto = revertir fue imposible

Con los 3 patrones: Bug #287 nunca habría ocurrido.

---

## 🆕 Cómo Agregar Nuevos Patrones

Cuando descubras/implemente un nuevo patrón o mejora:

1. **Documenta en este archivo** (al final de la lista, antes de "Notas de Implementación")
2. **Formato:**
   ```markdown
   ### 21. **Nombre del Patrón** (Frontend / Backend / Ambos)
   **Qué es:** Descripción breve
   
   **Por qué:** Problema que resuelve
   
   **Dónde:** Ubicaciones en el código
   
   **Implementación:**
   ```code ejemplo```
   
   **Estado:** ✅ **APLICADO** o ⏳ **PENDIENTE**
   - Archivo1.py - función/ubicación
   - Archivo2.html - ubicación
   ```

3. **Actualiza la matriz** - Agrega una columna con el número del nuevo patrón

4. **Actualiza el checklist** - Agrega checkbox en "Backend" u "Optional"

5. **Ejemplos de patrones para futuro:**
   - API rate limiting (evitar spam)
   - CSRF protection (Django ya lo hace, pero documéntalo)
   - Session timeout (logout automático)
   - Versioning de solicitudes (evitar editar versión vieja)
   - Soft delete (no borrar, marcar como inactivo)
   - Audit trail (historial completo de cambios)
   - Two-factor confirmation (para acciones muy críticas)
   - Queueing/Background jobs (operaciones largas)

---

## 🔗 Referencias en el Código

**Django:**
- Select-For-Update: https://docs.djangoproject.com/en/stable/ref/models/querysets/#select-for-update
- Transactions: https://docs.djangoproject.com/en/stable/topics/db/transactions/
- CSRF: https://docs.djangoproject.com/en/stable/middleware/csrf/

**Frontend:**
- SweetAlert2: https://sweetalert2.github.io/
- Fetch API: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API

**Conceptos:**
- Idempotency: https://en.wikipedia.org/wiki/Idempotence
- API Idempotency Keys (Stripe): https://stripe.com/docs/idempotent-requests
- Optimistic vs Pessimistic Locking: https://en.wikipedia.org/wiki/Optimistic_concurrency_control

---

## 📋 Registro de Cambios

| Fecha | Cambio | Patrones Afectados | Razón |
|-------|--------|-------------------|-------|
| **2026-06-25** | Agregados patrones #1-#20 (lista completa) | Todos | Sesión debugging - Bug #287 (snapshot corruption) |
| | Implementado Button Disable + Select-For-Update + Snapshot Guard | #1, #2, #3 | Prevenir doble aplicación de dobladas |
| | Implementado Cache Invalidation en todas las strategies | #6 | Evitar datos stale en MisTurnos y contadores |
| **2026-06-26** | Reescrito formulario "Cambio de Día de Descanso" | #1, #4, #5 | Lógica correcta: intercambio real sin dobladas |
| | Implementados patrones #4 (SweetAlert) + #5 (Form Disable) completo | #4, #5 | Confirmación modal + deshabilitar todos los inputs durante envío |
| | Aplicados patrones #2, #3, #6, #7, #10, #11 en strategies | #2, #3, #6, #7, #10, #11 | Transacciones, snapshot guard, invalidación caché, logging, notificaciones |
| **2026-07-25** | Agregado patrón #21 (Deuda Idempotente) | #21 | Auditoría de doblada permanente: re-aplicar duplicaba los 30 min en silencio |
| | Agregado patrón #22 (Reconciliación Completa) | #22 | Las permanentes quedaban fuera de la reconciliación: deuda viva sin doblada real |
| **2026-07-29** | #21: la clave idempotente pasa de (explorador, fecha, solicitud) a (explorador, fecha) | #21 | Dos solicitudes distintas sobre el mismo día cobraban 30 min cada una; el guard no las veía |
| | #21: agregada la mitad simétrica — `sincronizar_deuda_corporativa` en los 4 servicios de aplicación | #21 | Ceder media jornada de tu doblada dejaba tus 30 min vivos mientras el nuevo receptor recibía los suyos |
| | La doblada permanente ahora confirma el estado REAL del día antes de cobrar los 30 min | #21 | Creaba sobre ocurrencias calculadas: cobraba aunque el día no acabara en AM+PM |
| | #21: al revertir se cancelan solo las deudas ACTIVAS (`cancelar_deudas_de_solicitud`) | #21 | Revertir des-pagaba una deuda ya pagada: PDH huérfano y doble cobro al re-aplicar |
| | Auditoría de los otros 5 formularios: guards idempotentes compartidos | #21 | `reaplicar_doblada` y `corregir_doblada_cesion_total` duplicaban deuda de dobladas ya aplicadas |
| | Agregado patrón #23 (Invariante por Señal) | #23 | Cancelar desde el admin o un comando dejaba las deudas activas |
| | Agregado patrón #24 (Revert con Fallback) | #24 | Cambio de descanso sin snapshot cancelaba deudas pero dejaba los turnos puestos |
| **2026-07-26** | Auditoría completa del proyecto contra este documento: 5 huecos, todos con test que falla primero (`test_auditoria_huecos.py`) | #21, #22, #23, #25, #26 | Ver detalle abajo |
| | Reconciliación extendida a los SEIS tipos y disparada desde TODO revert que restaura snapshot | #22 | CAMBIO TURNO y CT PERMANENTE se borraban en silencio; solo DOBLADA reconciliaba |
| | Guardia LIFO ya no se salta sin snapshot | #25 (nuevo) | Se podía cancelar por debajo de un cambio más reciente y pisarlo |
| | `reprogramacion_doblada_service` pasa a la variante idempotente | #21 | Último llamador con la variante cruda: reprogramar dos veces cobraba 60 min |
| | La señal cubre también el estado 'reemplazada' | #23 | El predicado solo miraba 'cancelada': deuda viva sin doblada real |
| | Restricción de unicidad de turno activo en la BD | #26 (nuevo) | La migración encontró un duplicado real: la disciplina ya había fallado |
| **2026-07-29** | Agregado patrón #28 (el turno real L1 manda sobre el descanso L2) | #28 (nuevo) | Un descanso viejo bloqueaba para siempre un día en el que ya se recuperó jornada real (Marco, 30/07/2026) |
| | Agregado patrón #29 (un hueco en L2 no da error: da un dato falso) | #29 (nuevo) | El intercambio de dobladas no se atribuía como día completo: `estado_dia` caía a la jornada base y mostraba trabajando a quien tenía el día libre (mildrey ↔ arley, #565) |
| **2026-08-02** | Agregado patrón #32 (un hecho registrado no se borra; fin previsto ≠ fin real) | #32 (nuevo) | Levantar una sanción movía `fecha_fin` a ayer: perdía la duración original y, si se pagaba el mismo día en que nacía, dejaba `fecha_fin` ANTES de `fecha_inicio` (Mariana, Vanesa, jeison) |
| | Las sanciones ya no se pueden eliminar: se levantan con motivo obligatorio | #32 | Borrar destruía el registro del hecho disciplinario; editar la `fecha_fin` a mano dejaba el levantamiento indistinguible de una sanción corta |
| | El contador de reincidencias excluye las sanciones levantadas | #32 | Pagar agravaba la siguiente sanción (30 días en vez de 15): la levantada cumplía el filtro `fecha_fin < hoy` |
| | `vigentes_en()` como filtro único de sanción vigente (4 consumidores) | #32 | El criterio estaba reescrito a mano en el reporte del día, Mis Turnos, el listado y el servicio de deuda |
| | El intercambio se guarda con `tipo_cesion='cesion_completa'` (normalizado al crear) | #29 | El formulario arrastraba `cesion_parcial_am`, que contradice lo que `aplicar_intercambio` hace de verdad |
| **2026-08-06** | Agregado patrón #33 (la reconciliación cierra los días colaterales antes de re-aplicar) | #33 (nuevo), #22, #30 | Cancelar la D FDS #584 (15/08 + 08/08) re-aplicaba un CAMBIO DESCANSO de finde que reescribe los dos findes completos, y borró la D FDS #554 —aprobada después y vigente— del 09/08 y 16/08. Ninguna guardia lo veía: quedó aprobada, con deuda viva y mensaje en Mis Turnos, sin un turno que la respaldara |
| | Re-aplicar un CAMBIO DESCANSO ya no marca reemplazos (`marcar_reemplazos=False`) | #33 | La reconciliación convertía en 'reemplazada' una solicitud vigente: un re-aplicador debe ser puro en turnos |
| | Nuevo comando `verificar_efecto_aplicado` (auditoría + `--reparar`) | #33, #30 | Una guardia protege el momento; hacía falta encontrar lo que ya se escapó. Detectó y reparó la #554 |
| | La reconciliación re-aplica en UNA pasada ordenada por `fecha_resolucion`, no en tres bloques por modelo | #33 | Una doblada permanente aprobada en junio se re-materializaba después de una D FDS aprobada en julio y le ganaba el día cedido: la persona volvía a trabajarlo mientras su sustituto también lo tenía asignado |
| | `refrescar_resultantes` solo refresca las solicitudes que la reconciliación acaba de re-aplicar | #33, #30 | Refrescaba a toda vigente que compartiera un día: si su efecto estaba roto, grababa el estado roto como propio y cegaba a la guardia de integridad Y a la auditoría (la #554 llegó a afirmar que una D FDS había dejado un turno `CAMBIO DESCANSO`) |
| | `verificar_efecto_aplicado --solicitud N --reparar` repara aunque no detecte desajuste | #33 | Un resultante ya corrompido vuelve invisible el daño; la reparación no puede depender de la misma referencia que está mal |
| | En Mis Turnos, un día de FINDE trabajado dice `DÍA COMPLETO (AM + PM)`, no `DOBLADA` | — | En finde el día es AM+PM por definición: "doblada" afirmaba un esfuerzo extra inexistente, con deuda de 30 min asociada en la cabeza del explorador. Mismo vocabulario que el formulario de D FDS |
| | El detalle del día nombra el acuerdo real, el compañero y el papel de cada uno | — | Decía "Cambio de turno" para todos los tipos, y la rama que explicaba bien el caso era inalcanzable en findes por comparar `'DESCANSO'` contra el `'Descanso'` que devuelve `calcular_jornada_dia`. Además el compañero no se resolvía en un CAMBIO DESCANSO de finde (geometría distinta: el receptor trabaja la cesión, el solicitante los días opuestos) ni en una D FDS |
| | El formulario de D FDS deja de etiquetar los días con la alternancia teórica | — | Un día trabajado completo (AM+PM) salía como "AM" mientras Mis Turnos lo mostraba DOBLADA; y los textos hablaban de "doblarse" cuando las reglas 8/9 exigen que ambos tengan el día libre (por eso no hay 30 min) |
| | #29: la reconciliación post-revert despacha el intercambio a `aplicar_intercambio` (igual en `reaplicar_doblada`) | #29 | Al cancelar otra doblada, el swap vigente se re-aplicaba como cesión/pago y cada uno perdía su DOBLADA |
| | #29: el reparto de la fecha de PAGO se lee de `jornada_pago_sabado`/`jornada_cubre_en_pago`, no de `tipo_cesion` | #29 | `tipo_cesion` describe la cesión: en una parcial el acreedor queda libre el día COMPLETO y se atribuía medio (arley 26/08/2026) |
| | #29: atribución del tercer día, `fecha_pago_semana` (pago en sábado AMBAS) | #29 | Ese día lo muta `aplicar_pago_residual_semana` y no lo cubría ninguna rama: quedaba sin motivo |
| **2026-08-01** | Agregado patrón #31 (catálogo que gobierna permisos) tras auditar el CRUD de roles | #31 (nuevo) | Crear un rol "Supervisor de sala" concedía acceso total: el permiso se resolvía con `icontains` y el CRUD no validaba nada |
| | `EmpleadoRole.role` pasa de CASCADE a PROTECT + bloqueo de roles base | #31 | Borrar el rol "Supervisor" arrastraba en silencio todas las asignaciones y dejaba la operación sin supervisores |
| | La definición del permiso se unifica en `es_supervisor()` (el middleware la duplicaba) | #9, #31 | Estaba copiada en cinco sitios: arreglar uno dejaba la escalada viva en los otros cuatro |
| **2026-08-06** | Agregado patrón #34 (una caché de lectura declara qué cubre) tras optimizar CT PERMANENTE | #34 (nuevo), #12, #29 | Seleccionar un rango de 90 días en `/solicitudes/cambio-turno/solicitar/2/` tardaba ~35 s y lanzaba **13.163 consultas**: la matriz empleado×día resolvía cada celda con `estado_dia` (~13 consultas y ~17 ms), y el coste crecía linealmente con la plantilla |
| | `TurnoService.estado_rango_multiple()`: batch real de `estado_dia` para N empleados y un rango | #12, #34 | `en_fecha` delegaba en `en_rango_multiple`, o sea que **cada celda pagaba el arranque completo de la maquinaria batch** para una sola consulta. Ahora: 13.163 → 23 consultas, 39 s → 0,15 s. `estado_mes` delega ahí y deja de tener su propia copia del cálculo por capas |
| | La jornada base se resuelve POR FECHA, no con la asignación vigente al final del mes | #29 | `estado_mes` contradecía a `estado_dia` (que siempre miró `fecha_inicio__lte=fecha`): si alguien cambia de grupo a mitad de mes, Mis Turnos mostraba la jornada NUEVA también en los días anteriores al cambio. Un hueco de este tipo no da error, da un dato falso |
| | Eliminado el recálculo duplicado de `_estado_ct` en la matriz de compatibilidad | #12 | `_razones_exclusion_ct_permanente` ya resolvía el estado del candidato y la línea siguiente lo volvía a derivar con `_jornada_efectiva_ct`: el 40 % de las llamadas eran recálculo puro |
| **2026-08-06** | Agregados patrones #35 (validar por el campo que manda al aplicar) y #36 (día completo en jornada virtual) tras auditar DOBLADA en festivo | #35 (nuevo), #36 (nuevo), #29 | Un festivo se cede ENTERO, pero la UI reponía el selector AM/PM al deschulear "intercambiar", `cesion_completa` + `jornada_cedida='AM'` pasaba la validación, y —el fallo de fondo— al aprobar una cesión completa el receptor recibía **una sola jornada** (la base del emisor) en vez de AM+PM: el emisor descansaba el día entero y el festivo quedaba medio cubierto |
| | La cesión de festivo asigna al receptor AM **y** PM explícitamente | #36 | En festivo la doblada es virtual (sin filas `Turno`): `jornada_solicitante.nombre` da la base (una sola), no el día completo |
| | La regla "festivo todo-o-nada" mira `jornada_cedida`, no solo `tipo_cesion` | #35, #29 | Al aplicar manda `jornada_cedida`; validar solo el campo declarativo dejaba la regla sin dientes |
| | Precarga en los seis barridos de rango (compatibilidad, `evaluar_fechas_ct_permanente`, validador de jornada contraria, `obtener-jornadas-rango` y los dos endpoints de doblada permanente) | #34 | Tenían todos la misma forma N×M; la vista previa además barría el rango DOS veces (validación + evaluación) reconstruyendo el estado cada vez |
| **2026-08-07** | Agregado patrón #37 (el desplegable filtra por las mismas fechas que valida el envío) | #37 (nuevo) | Se rompió TRES veces por sitios distintos en el mismo formulario: el selector miraba una sola de las dos fechas de la operación y ofrecía compañeros que el envío rechazaba (Jhon 11/08, Marco en cobertura, Mariana en cambio de doblada) |
| | `CoberturaCandidatosView` marca no disponible a quien no trabaja esa jornada el día de pago | #37 | `jornada_pago` se calculaba solo para mostrarlo como texto; la ficha llegaba a decir "trabaja libre → le cubres su PM" |
| | `DobladasSemanaView` solo lista compañeros libres mi día completo de temporada | #37 | El cambio de doblada es mutuo (él toma mi día): tener doblada esa semana no basta. El endpoint gemelo `ExploradoresConDobladaView` ya lo hacía bien |
| | El formulario avisa si el día de pago de una cobertura es un día en que YA doblo | #37 | Pagar desde un día en que ya trabajas AM+PM es ficticio (y no genera los 30 min); el backend lo rechazaba, pero al final del formulario |
| **2026-08-09** | Agregado patrón #38 (credencial sin sesión: firma única, caducidad, fallo cerrado) tras cerrar la vulnerabilidad de los tokens de aprobación por correo | #38 (nuevo) | La firma estaba duplicada en **seis** sitios con la clave escrita en el código (`b'secret_key_change_this'`): cualquiera con acceso al repositorio podía aprobar cualquier solicitud sin iniciar sesión, y el token no caducaba. La sexta copia vivía en OTRA app (`permisos/services.py`) y se pasó por alto en la primera revisión — de ahí el patrón. Ver [ADR 006](AppTurnosExplora/docs/03-arquitectura/adr/006-tokens-firmados-para-aprobacion-por-correo.md) |
| | Los mensajes de error de las vistas ya no salen con los acentos rotos | — | 31 secuencias de mojibake por doble codificación UTF-8 en 5 archivos: el usuario leía literalmente "Token invÃ¡lido o expirado" en pantalla |
| | La página de error de token dice el plazo y qué hacer | — | El mismo mensaje cubre cuatro causas distintas (caducado, manipulado, ajeno, rol equivocado) y no decía ninguna; ahora nombra los 30 días y remite a resolver desde la aplicación. Contexto centralizado en `core/utils/error_token.py` para que las 15 llamadas no puedan olvidarlo |
| | `email_service.py` registra los fallos de envío con `logger.exception`, no con `print` | — | Un `print` no lleva nivel ni traza: en AWS ese texto no llega útil a CloudWatch |

---

## ⚠️ Deuda conocida — PENDIENTE DE DECISIÓN (no aplicar aún)

| Tema | Documento | Por qué está en pausa |
|---|---|---|
| **Punto ciego de TEMPORADA en `estado_dia`** — la fuente de verdad NO marca los días de temporada para quien conserva su jornada normal (`fuente='base'`, indistinguible de un día ordinario). Los formularios que deben rechazar temporada lo comprueban hoy por REGLA aparte (CT permanente y doblada permanente); los que leen `estado_dia` a secas son los que SÍ permiten temporada. Sin agujero explotable conocido hoy, pero la fuente de verdad miente por omisión y el próximo formulario volverá a olvidarlo. | [`docs/05-referencia/turnos/PUNTO_CIEGO_TEMPORADA_ESTADO_DIA.md`](AppTurnosExplora/docs/05-referencia/turnos/PUNTO_CIEGO_TEMPORADA_ESTADO_DIA.md) | Hay formularios en los que en temporada **sí** se pueden modificar jornadas y aún no está confirmado si todos o algunos. Arreglar la capa antes de saberlo puede romper casos legítimos. El documento trae la checklist a validar (§5). |

---

**Última actualización:** 2026-08-09  
**Mantenedor:** Equipo de AppTurnos  
**Próxima revisión:** Cuando se implemente nuevo patrón o cambio arquitectónico importante

--------------------------------------------------
**Loading Bloqueante**
**Que es:** Modal de carga con SweetAlert que bloquea toda la UI durante una petición

**Para que es:**Evita doble envío (doble clic) y da feedback de "procesando"
**Relación:**Es una versión más fuerte/consistente del patrón #1 (Button Disable).

