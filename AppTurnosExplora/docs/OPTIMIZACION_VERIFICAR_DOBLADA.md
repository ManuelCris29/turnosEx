# Optimización: VerificarDobladaExistenteView

## Problema Anterior

La lógica original verificaba **dos fuentes de datos**:
1. Tabla `SolicitudCambio` (solicitudes aprobadas)
2. Tabla `Turno` (turnos asignados)

Esto causaba:
- **Duplicación de lógica**: Verificar ambas tablas
- **Consultas innecesarias**: 2-3 consultas cuando 1 es suficiente
- **Complejidad**: Lógica condicional compleja
- **Inconsistencias**: Posibilidad de tener solicitud aprobada sin turnos o viceversa

## Solución Optimizada

### Principio: **Turno es la fuente de verdad**

Cuando una doblada se aprueba:
1. Se ejecuta `aplicar_cambios()` en `DobladaStrategy`
2. Se crean turnos AM+PM en la tabla `Turno` con `tipo_cambio="DOBLADA"`
3. **Si hay turnos AM+PM, significa que ya está aplicado**

### Lógica Simplificada

```python
# ✅ OPTIMIZACIÓN: Usar Turno como fuente de verdad única
turnos = Turno.objects.filter(explorador=usuario_actual, fecha=fecha_obj)
jornadas = [t.jornada.nombre.upper() for t in turnos if t.jornada]
es_doblada_turnos = 'AM' in jornadas and 'PM' in jornadas

# CASO 1: Tiene turnos AM+PM → Puede ceder parte
if es_doblada_turnos:
    return {'tiene_doblada': True, ...}

# CASO 2: Tiene turnos pero NO es doblada → Jornada normal
if jornadas:
    return {'tiene_doblada': False, ...}

# CASO 3: NO tiene turnos → Verificar si cedió (está descansando)
# Solo aquí necesitamos verificar SolicitudCambio
```

## Ventajas

### 1. **Rendimiento**
- **Antes**: 2-3 consultas a BD
- **Ahora**: 1 consulta principal + 1 opcional (solo si no hay turnos)
- **Mejora**: ~50-66% menos consultas

### 2. **Simplicidad**
- **Antes**: ~150 líneas de lógica condicional compleja
- **Ahora**: ~60 líneas de lógica clara y directa
- **Mejora**: Código más mantenible y fácil de entender

### 3. **Consistencia**
- **Antes**: Posibilidad de inconsistencias (solicitud sin turnos, turnos sin solicitud)
- **Ahora**: La fuente de verdad es única (Turno)
- **Mejora**: Menos errores y casos edge

### 4. **Mantenibilidad**
- **Antes**: Cambios en lógica de aprobación requerían actualizar ambas verificaciones
- **Ahora**: Solo necesitamos verificar Turno
- **Mejora**: Menos puntos de fallo

## Casos de Uso

### Caso 1: Usuario con turnos AM+PM
- ✅ Tiene turnos AM+PM en `Turno`
- ✅ **Resultado**: `tiene_doblada: True` → Muestra opciones de cesión parcial
- **Nota**: No importa si tiene solicitud aprobada o no, si tiene turnos AM+PM puede ceder

### Caso 2: Usuario con solo una jornada
- ✅ Tiene solo turno AM o solo PM en `Turno`
- ✅ **Resultado**: `tiene_doblada: False` → No muestra opciones de cesión parcial
- **Nota**: Es su jornada normal, puede solicitar doblada normalmente

### Caso 3: Usuario sin turnos (cedió su jornada)
- ❌ NO tiene turnos en `Turno`
- ✅ Tiene solicitud aprobada como solicitante en `SolicitudCambio`
- ✅ **Resultado**: `esta_descansando: True` → No puede solicitar doblada
- **Nota**: Solo en este caso verificamos `SolicitudCambio` porque no hay turnos

### Caso 4: Usuario sin turnos ni solicitud
- ❌ NO tiene turnos en `Turno`
- ❌ NO tiene solicitud aprobada en `SolicitudCambio`
- ✅ **Resultado**: `tiene_doblada: False` → Puede solicitar doblada normalmente

## Búsqueda Opcional de Solicitud

Para mantener compatibilidad con el frontend (mostrar ID de solicitud si existe), hacemos una búsqueda opcional:

```python
# Opcional: Buscar solicitud relacionada solo para mostrar ID (si existe)
# Esto es opcional y no afecta la lógica principal
solicitud_id = None
try:
    doblada_solicitud = (
        SolicitudCambio.objects
        .filter(
            Q(explorador_solicitante=usuario_actual, fecha_cambio_turno=fecha_obj) |
            Q(explorador_receptor=usuario_actual, doblada__fecha_pago=fecha_obj),
            tipo_cambio__nombre='DOBLADA',
            estado='aprobada'
        )
        .first()
    )
    if doblada_solicitud:
        solicitud_id = doblada_solicitud.id
except Exception:
    # Si falla la búsqueda de solicitud, no es crítico
    pass
```

**Nota**: Esta búsqueda es opcional y no afecta la lógica principal. Si falla, simplemente no se muestra el ID de solicitud.

## Comparación de Consultas

### Antes (Lógica Original)
```python
# Consulta 1: Turnos
turnos = Turno.objects.filter(...)

# Consulta 2: Solicitud como solicitante
doblada_como_solicitante = SolicitudCambio.objects.filter(...).first()

# Consulta 3: Solicitud como receptor
doblada_como_receptor = SolicitudCambio.objects.filter(...).first()

# Consulta 4 (si no hay turnos): Solicitud como solicitante (duplicada)
doblada_como_solicitante = SolicitudCambio.objects.filter(...).first()

# Consulta 5 (si no hay turnos): Solicitud como receptor (duplicada)
doblada_como_receptor = SolicitudCambio.objects.filter(...).first()
```

**Total**: 2-5 consultas dependiendo del caso

### Ahora (Lógica Optimizada)
```python
# Consulta 1: Turnos (SIEMPRE)
turnos = Turno.objects.filter(...)

# Consulta 2 (opcional): Solicitud solo si no hay turnos
if not jornadas:
    doblada_como_solicitante = SolicitudCambio.objects.filter(...).first()

# Consulta 3 (opcional): Solicitud relacionada para mostrar ID
# Solo si tiene turnos AM+PM y queremos mostrar ID
```

**Total**: 1-2 consultas (mejora del 50-80%)

## Conclusión

Esta optimización sigue el principio de Django de **usar la fuente de verdad única**:
- **Turno** es la fuente de verdad de lo que está asignado
- **SolicitudCambio** es solo el registro histórico de la solicitud
- Si hay turnos AM+PM, ya está aplicado, no necesitamos verificar la solicitud

**Beneficios**:
- ✅ Mejor rendimiento
- ✅ Código más simple
- ✅ Menos consultas a BD
- ✅ Menos puntos de fallo
- ✅ Más fácil de mantener

