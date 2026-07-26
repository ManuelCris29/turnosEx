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

### 21. **Deuda Idempotente por (explorador, fecha, solicitud)** (Backend)
**Qué es:** Antes de crear una `DeudaCorporativa`, verificar que no exista ya una ACTIVA para esa
misma combinación de explorador + fecha de doblada + solicitud de origen.

**Por qué:** Un día doblado = 30 min, siempre. Los turnos toleran una re-aplicación (se borran y se
recrean, ver `_crear_doblada_dia`), pero la deuda NO: se sumaba encima. Si `aplicar()` corría dos
veces (reintento, re-aprobación manual, comando de mantenimiento), el explorador terminaba debiendo
60 min por un solo día doblado. **Sin error, sin log de alarma, sin nada visible** hasta que alguien
mira el Consolidado de Horas y no le cuadra.

⚠️ **NO BORRAR este guard.** Parece redundante ("si solo se aplica una vez, ¿para qué comprobar?"),
pero es la capa 3 del orden de defensa: las capas 1 y 2 previenen el doble clic, esta previene el
doble COBRO cuando las otras fallan. Quitarlo reintroduce el cobro doble en silencio.

**Dónde:** Al crear deuda corporativa dentro de un flujo que puede re-ejecutarse.

**Gatillo REAL (no hipotético):** `reaplicar_doblada` y `corregir_doblada_cesion_total` llaman a
`generar_deudas_doblada()` sobre solicitudes ya aplicadas. Se corren justo cuando algo salió mal,
y antes de este guard sumaban una segunda deuda encima de la existente.

**Implementación:** usa SIEMPRE las variantes idempotentes, no las crudas:
```python
DeudaCorporativaService.crear_deuda_corporativa_idempotente(...)  # clave: explorador+fecha_doblada+solicitud
DeudaService.crear_deuda_idempotente(...)                          # clave: solicitud+deudor+acreedor+fecha_pago_pactada
# Ambas devuelven None si ya existía (útil para no loguear "creada" cuando no se creó).
```

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
| | Auditoría de los otros 5 formularios: guards idempotentes compartidos | #21 | `reaplicar_doblada` y `corregir_doblada_cesion_total` duplicaban deuda de dobladas ya aplicadas |
| | Agregado patrón #23 (Invariante por Señal) | #23 | Cancelar desde el admin o un comando dejaba las deudas activas |
| | Agregado patrón #24 (Revert con Fallback) | #24 | Cambio de descanso sin snapshot cancelaba deudas pero dejaba los turnos puestos |
| **2026-07-26** | Auditoría completa del proyecto contra este documento: 5 huecos, todos con test que falla primero (`test_auditoria_huecos.py`) | #21, #22, #23, #25, #26 | Ver detalle abajo |
| | Reconciliación extendida a los SEIS tipos y disparada desde TODO revert que restaura snapshot | #22 | CAMBIO TURNO y CT PERMANENTE se borraban en silencio; solo DOBLADA reconciliaba |
| | Guardia LIFO ya no se salta sin snapshot | #25 (nuevo) | Se podía cancelar por debajo de un cambio más reciente y pisarlo |
| | `reprogramacion_doblada_service` pasa a la variante idempotente | #21 | Último llamador con la variante cruda: reprogramar dos veces cobraba 60 min |
| | La señal cubre también el estado 'reemplazada' | #23 | El predicado solo miraba 'cancelada': deuda viva sin doblada real |
| | Restricción de unicidad de turno activo en la BD | #26 (nuevo) | La migración encontró un duplicado real: la disciplina ya había fallado |

---

**Última actualización:** 2026-07-26  
**Mantenedor:** Equipo de AppTurnos  
**Próxima revisión:** Cuando se implemente nuevo patrón o cambio arquitectónico importante

--------------------------------------------------
**Loading Bloqueante**
**Que es:** Modal de carga con SweetAlert que bloquea toda la UI durante una petición

**Para que es:**Evita doble envío (doble clic) y da feedback de "procesando"
**Relación:**Es una versión más fuerte/consistente del patrón #1 (Button Disable).

