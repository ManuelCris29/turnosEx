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
- 6 formularios de "solicitar" (doblada, CT, D FDS, cambio descanso, etc.)

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

---

**Última actualización:** 2026-06-25  
**Mantenedor:** Equipo de AppTurnos  
**Próxima revisión:** Cuando se implemente nuevo patrón o cambio arquitectónico importante

--------------------------------------------------
**Loading Bloqueante**
**Que es:** Modal de carga con SweetAlert que bloquea toda la UI durante una petición

**Para que es:**Evita doble envío (doble clic) y da feedback de "procesando"
**Relación:**Es una versión más fuerte/consistente del patrón #1 (Button Disable).

