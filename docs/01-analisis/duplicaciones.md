# Análisis de Duplicaciones - Proyecto AppTurnos

## Fecha: 2025-01-XX

## RESUMEN EJECUTIVO

Se identificaron **4 tipos principales de duplicaciones** en el proyecto:

1. **CRÍTICA**: `AdminRequiredMixin` duplicado en 2 archivos
2. **MEDIA**: Funciones `json_ok` y `json_error` duplicadas
3. **MEDIA**: Lógica de cache duplicada en múltiples lugares
4. **BAJA**: Queries similares repetidas (algunas ya optimizadas)

---

## DUPLICACIÓN 1: AdminRequiredMixin (CRÍTICA)

### Ubicación:
- `AppTurnosExplora/empleados/views.py` líneas 21-41
- `AppTurnosExplora/permisos/views.py` líneas 8-28

### Código Duplicado:
```python
class AdminRequiredMixin:
    def dispatch(self, request, *args, **kwargs):
        # Verificar si el usuario es staff o tiene rol de Supervisor
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        
        # Si es staff, permitir acceso
        if request.user.is_staff:
            return super().dispatch(request, *args, **kwargs)
        
        # Verificar si tiene rol de Supervisor
        try:
            empleado = request.user.empleado
            tiene_rol_supervisor = empleado.empleadorole_set.filter(role__nombre__icontains='supervisor').exists()
            if tiene_rol_supervisor:
                return super().dispatch(request, *args, **kwargs)
        except:
            pass
        
        # Si no cumple ninguna condición, denegar acceso
        raise PermissionDenied("No tienes permisos de administrador.")
```

### Impacto:
- **Mantenibilidad**: Si cambia la lógica de permisos, hay que actualizar 2 lugares
- **Consistencia**: Riesgo de que las implementaciones divergan
- **Tamaño**: ~20 líneas duplicadas

### Solución:
- Crear `core/mixins.py` con `AdminRequiredMixin` centralizado
- Actualizar imports en `empleados/views.py` y `permisos/views.py`

---

## DUPLICACIÓN 2: Funciones JSON (MEDIA)

### Ubicación:
- `AppTurnosExplora/solicitudes/views.py` líneas 24-36

### Código Duplicado:
```python
def json_ok(payload=None, status=200):
    data = {'success': True}
    if isinstance(payload, dict):
        data.update(payload)
    return JsonResponse(data, status=status)

def json_error(message, *, status=400, code=None, extra=None):
    data = {'success': False, 'error': str(message)}
    if code:
        data['code'] = code
    if isinstance(extra, dict):
        data['extra'] = extra
    return JsonResponse(data, status=status)
```

### Impacto:
- **Reutilización**: Estas funciones podrían usarse en otras apps
- **Consistencia**: Asegura formato uniforme de respuestas JSON
- **Mantenibilidad**: Cambios en formato JSON requieren un solo lugar

### Solución:
- Crear `core/utils/json_responses.py` con estas funciones
- Actualizar imports en `solicitudes/views.py`
- Buscar otros lugares donde se puedan usar

---

## DUPLICACIÓN 3: Lógica de Cache (MEDIA)

### Ubicaciones Identificadas:

#### 3.1 Cache en SolicitudesView
**Archivo**: `solicitudes/views.py` líneas 48-66
```python
cache_key_mis = f"solicitudes_count_mis_{empleado.id}"
cache_key_pend = f"solicitudes_count_pend_{empleado.id}"

mis_solicitudes_count = cache.get(cache_key_mis)
if mis_solicitudes_count is None:
    mis_solicitudes_count = SolicitudCambio.objects.filter(...).count()
    cache.set(cache_key_mis, mis_solicitudes_count, 300)
```

#### 3.2 Cache en ObtenerEmpleadosDisponiblesView
**Archivo**: `solicitudes/views.py` líneas 231-239
```python
cache_key = f"empleados_disponibles_{fecha}_{usuario_id}"
empleados_disponibles = cache.get(cache_key)
if empleados_disponibles is None:
    empleados_disponibles = SolicitudService.get_empleados_disponibles(...)
    cache.set(cache_key, empleados_disponibles, 1800)
```

#### 3.3 Cache en MisTurnosPorMesView
**Archivo**: `turnos/api/views.py` líneas 60, 207
```python
cached_data = cache.get(cache_key)
if cached_data is None:
    # ... lógica ...
    cache.set(cache_key, turnos_mes_dict, 3600)
```

#### 3.4 Cache en DiasFestivosView
**Archivo**: `turnos/api/views.py` líneas 301, 381
```python
cached_data = cache.get(cache_key)
if cached_data is None:
    # ... lógica ...
    cache.set(cache_key, response_data, 3600)
```

#### 3.5 Cache en SolicitudService
**Archivo**: `solicitudes/services/solicitud_service.py` líneas 213-219
```python
cache_key = f"jornada_pred_{explorador.id}_{fecha_obj}"
asignacion_jornada = cache.get(cache_key)
if asignacion_jornada is None:
    asignacion_jornada = AsignarJornadaExplorador.objects.filter(...).first()
    cache.set(cache_key, asignacion_jornada, 3600)
```

### Patrón Repetido:
```python
cache_key = f"{prefix}_{id}_{params}"
cached_value = cache.get(cache_key)
if cached_value is None:
    cached_value = expensive_operation()
    cache.set(cache_key, cached_value, ttl)
```

### Impacto:
- **Consistencia**: Diferentes TTLs (300, 1800, 3600 segundos) sin documentación
- **Mantenibilidad**: Patrón repetido en múltiples lugares
- **Testabilidad**: Difícil mockear cache en tests

### Solución:
- Crear `core/services/cache_service.py` con métodos helper:
  - `get_or_set(key, callable, ttl)` - Patrón común
  - `invalidate_pattern(pattern)` - Para invalidar múltiples keys
  - Constantes para TTLs comunes

---

## DUPLICACIÓN 4: Queries Similares (BAJA)

### Queries Identificadas:

#### 4.1 Obtener Empleados Activos
**Patrón repetido en múltiples lugares:**
```python
Empleado.objects.filter(activo=True).select_related('supervisor')
```
**Ubicaciones**:
- `solicitudes/services/solicitud_service.py` líneas 30-34, 88-93
- Posiblemente en otras partes

#### 4.2 Obtener Solicitudes Pendientes
**Patrón similar:**
```python
SolicitudCambio.objects.filter(estado='pendiente').select_related(...)
```
**Ubicaciones**:
- `solicitudes/services/solicitud_service.py` línea 378
- `solicitudes/views.py` líneas 62-65
- Variaciones en múltiples métodos

#### 4.3 Obtener Jornada de Explorador
**Ya optimizado pero usado en múltiples lugares:**
- `get_jornada_explorador_fecha` en `solicitud_service.py`
- Lógica similar en `turnos/views.py`

### Impacto:
- **BAJO**: La mayoría ya están optimizadas o son queries simples
- **Oportunidad**: Algunas podrían extraerse a métodos reutilizables

### Solución:
- Evaluar si vale la pena crear métodos helper para queries muy simples
- Prioridad baja, enfocarse en duplicaciones más críticas primero

---

## RESUMEN DE PRIORIDADES

### Prioridad ALTA:
1. ✅ **Extraer AdminRequiredMixin** - 2 archivos afectados, fácil de hacer

### Prioridad MEDIA:
2. ✅ **Extraer funciones JSON** - Reutilizables, mejoran consistencia
3. ✅ **Crear servicio de cache** - Mejora mantenibilidad y testabilidad

### Prioridad BAJA:
4. ⚠️ **Queries similares** - Evaluar caso por caso, mayoría ya optimizadas

---

## ARCHIVOS A CREAR

1. `core/mixins.py` - Mixins compartidos
2. `core/utils/json_responses.py` - Helpers JSON
3. `core/services/cache_service.py` - Servicio de cache

## ARCHIVOS A MODIFICAR

1. `empleados/views.py` - Usar mixin común
2. `permisos/views.py` - Usar mixin común
3. `solicitudes/views.py` - Usar helpers JSON y cache service
4. `turnos/api/views.py` - Usar cache service
5. `solicitudes/services/solicitud_service.py` - Usar cache service

---

## ESTADO

- [x] Duplicaciones identificadas
- [x] Impacto evaluado
- [x] Soluciones propuestas
- [ ] Implementación (FASE 2)

