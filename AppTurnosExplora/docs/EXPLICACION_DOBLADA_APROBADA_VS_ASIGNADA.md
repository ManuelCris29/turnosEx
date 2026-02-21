# Explicación: Doblada Aprobada vs Doblada Asignada

## Diferencia Conceptual

### 1. **Doblada Aprobada** (SolicitudCambio)
- Es una **solicitud** registrada en la tabla `SolicitudCambio`
- Tiene estado `'aprobada'`
- Cuando se aprueba, se **crean turnos** en la tabla `Turno`
- Ejemplo: Usuario A solicita doblada, Usuario B acepta, Supervisor aprueba → Se crea registro en `SolicitudCambio` con estado `'aprobada'` → Se crean turnos AM+PM para Usuario B

### 2. **Doblada Asignada** (Turnos AM+PM)
- Son **turnos reales** asignados en la tabla `Turno`
- El usuario tiene turnos con jornadas **AM** y **PM** en la misma fecha
- Estos turnos pueden venir de:
  - ✅ Una doblada aprobada (cuando se aprueba una solicitud)
  - ✅ Jornada fija del explorador (algunos exploradores tienen jornada doblada por defecto)
  - ✅ Cualquier otra razón (asignación manual, etc.)

## El Problema Anterior

### Lógica Original (INCORRECTA)
```python
# ❌ ANTES: Solo verificaba si había solicitud aprobada
if doblada_como_solicitante or doblada_como_receptor:
    # Mostrar opciones de cesión parcial
    return {'tiene_doblada': True, ...}
else:
    # NO mostrar opciones, aunque tuviera turnos AM+PM
    return {'tiene_doblada': False, ...}
```

**Problema**: Si el usuario tenía turnos AM+PM pero NO tenía una solicitud aprobada, el sistema NO mostraba las opciones de cesión parcial.

### Ejemplo del Problema

**Caso: jhon.areiza el 28 de febrero de 2026**
- ✅ Tiene turnos AM+PM asignados (Turno ID: 103 AM, Turno ID: 66 PM)
- ❌ NO tiene solicitud de doblada aprobada
- **Resultado anterior**: NO mostraba opciones de cesión parcial
- **Resultado esperado**: SÍ debe mostrar opciones de cesión parcial

## La Solución Actual

### Lógica Corregida (CORRECTA)
```python
# ✅ AHORA: Verifica AMBAS cosas
# 1. Si tiene solicitud aprobada
if doblada_como_solicitante or doblada_como_receptor:
    return {'tiene_doblada': True, ...}

# 2. Si tiene turnos AM+PM (aunque NO tenga solicitud aprobada)
es_doblada_turnos = 'AM' in jornadas and 'PM' in jornadas
if es_doblada_turnos:
    return {'tiene_doblada': True, ...}
```

**Solución**: Ahora el sistema verifica si tiene turnos AM+PM, independientemente de si tiene una solicitud aprobada o no.

## Flujo de Datos

### Cuando se aprueba una doblada:
```
1. Usuario solicita doblada
   ↓
2. Se crea SolicitudCambio (estado='pendiente')
   ↓
3. Receptor acepta → estado='aprobada_receptor'
   ↓
4. Supervisor aprueba → estado='aprobada'
   ↓
5. Se ejecuta aplicar_cambios()
   ↓
6. Se crean turnos AM+PM en tabla Turno
```

### Relación entre tablas:
```
SolicitudCambio (estado='aprobada')
    ↓ (cuando se aprueba)
Turno (jornada='AM', fecha=X)
Turno (jornada='PM', fecha=X)
```

## Casos de Uso

### Caso 1: Usuario con doblada aprobada
- ✅ Tiene `SolicitudCambio` con estado='aprobada'
- ✅ Tiene turnos AM+PM en `Turno`
- ✅ **Resultado**: Muestra opciones de cesión parcial

### Caso 2: Usuario con turnos AM+PM pero sin solicitud aprobada
- ❌ NO tiene `SolicitudCambio` con estado='aprobada'
- ✅ Tiene turnos AM+PM en `Turno` (por jornada fija u otra razón)
- ✅ **Resultado**: Ahora SÍ muestra opciones de cesión parcial (CORREGIDO)

### Caso 3: Usuario con solo una jornada
- ❌ NO tiene `SolicitudCambio` con estado='aprobada'
- ✅ Tiene solo turno AM o solo PM en `Turno`
- ✅ **Resultado**: NO muestra opciones de cesión parcial (correcto, no es doblada)

## Código Corregido

**Archivo**: `AppTurnosExplora/solicitudes/views.py`
**Método**: `VerificarDobladaExistenteView.get()`

```python
# Líneas 1999-2059
# ✅ CORRECCIÓN: Verificar si tiene turnos AM+PM (es doblada)
es_doblada_turnos = 'AM' in jornadas and 'PM' in jornadas

# Si tiene doblada aprobada (como solicitante o receptor)
if doblada_como_solicitante or doblada_como_receptor:
    return json_ok({
        'tiene_doblada': True,
        ...
    })

# ✅ NUEVO: Si tiene turnos AM+PM pero NO tiene doblada aprobada, también puede ceder parte
if es_doblada_turnos:
    return json_ok({
        'tiene_doblada': True,
        'mensaje': f'Tienes jornada doblada ({", ".join(jornadas)}). Puedes ceder una jornada (AM o PM) o ambas jornadas (cesión total).',
        ...
    })
```

## Resumen

**Antes**: Solo mostraba opciones si había solicitud aprobada
**Ahora**: Muestra opciones si tiene turnos AM+PM, independientemente de si tiene solicitud aprobada

**Beneficio**: Los usuarios pueden ceder parte de su jornada doblada incluso si no tienen una solicitud aprobada (por ejemplo, si tienen jornada fija doblada).



