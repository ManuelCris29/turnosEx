# ANÁLISIS FASE 1.1: Optimización de Consultas
## Problema N+1 Queries Identificado

---

## 📍 Ubicación del Código

**Archivo:** `AppTurnosExplora/solicitudes/services/solicitud_service.py`

**Método principal:** `get_empleados_jornada_contraria` (líneas 42-102)

**Método auxiliar:** `get_jornada_explorador_fecha` (líneas 104-134)

---

## 🔍 Análisis del Problema

### Flujo Actual:

1. **Línea 62-64:** Obtiene jornada del usuario actual
   - Llama a `get_jornada_explorador_fecha(empleado_actual.id, fecha)`
   - **Consultas:** 1-2 (busca Turno, si no encuentra busca AsignarJornadaExplorador)

2. **Línea 87-92:** Obtiene todos los empleados activos
   - **Consultas:** 1 (SELECT de Empleado)

3. **Línea 96-99:** Loop sobre cada empleado
   ```python
   for empleado in empleados_activos:  # Si hay 100 empleados
       jornada_empleado = SolicitudService.get_jornada_explorador_fecha(empleado.id, fecha)
       # ↑ ESTO SE EJECUTA 100 VECES
   ```

4. **Dentro de `get_jornada_explorador_fecha` (líneas 105-134):**
   - **Línea 112:** `Empleado.objects.get(id=explorador_id)` → **1 consulta**
   - **Línea 115-118:** `Turno.objects.filter(...).first()` → **1 consulta**
   - **Línea 125-128:** `AsignarJornadaExplorador.objects.filter(...).first()` → **1 consulta** (si no hay Turno)

### Cálculo de Consultas:

**Escenario con 100 empleados activos:**

- Consulta inicial usuario: 1-2 consultas
- Consulta empleados activos: 1 consulta
- Loop (100 empleados × 2-3 consultas cada uno): **200-300 consultas**

**TOTAL: 202-303 consultas a la base de datos** ❌

---

## 🎯 Problema Identificado: N+1 Queries

### ¿Qué es N+1?

El problema N+1 ocurre cuando:
- Haces 1 consulta para obtener N registros
- Luego haces N consultas adicionales (una por cada registro)

En nuestro caso:
- 1 consulta para obtener 100 empleados
- 100 consultas adicionales (una por cada empleado para obtener su jornada)

### Impacto:

1. **Rendimiento:** Muy lento con muchos empleados
2. **Carga en BD:** Satura la base de datos
3. **Escalabilidad:** Empeora con más empleados
4. **Experiencia de usuario:** Tiempos de respuesta largos

---

## 📊 Datos que Necesitamos Pre-cargar

### 1. Turnos para la Fecha Específica

**Qué necesitamos:**
- Todos los `Turno` donde `fecha = fecha_obj`
- Para todos los empleados activos
- Con la relación `jornada` cargada (select_related)

**Consulta optimizada:**
```python
turnos_fecha = Turno.objects.filter(
    fecha=fecha_obj,
    explorador__in=empleados_activos
).select_related('jornada')
```

**Resultado:** 1 consulta trae todos los Turnos necesarios

---

### 2. Asignaciones de Jornada

**Qué necesitamos:**
- Todas las `AsignarJornadaExplorador` para empleados activos
- Donde `fecha_inicio <= fecha_obj`
- Ordenadas por `fecha_inicio DESC` (la más reciente)
- Con la relación `jornada` cargada (select_related)

**Consulta optimizada:**
```python
asignaciones = AsignarJornadaExplorador.objects.filter(
    explorador__in=empleados_activos,
    fecha_inicio__lte=fecha_obj
).select_related('jornada').order_by('explorador', '-fecha_inicio')
```

**Resultado:** 1 consulta trae todas las asignaciones necesarias

**Nota:** Necesitamos agrupar por explorador y tomar la más reciente (puede requerir procesamiento en Python o usar Subquery)

---

## 🔄 Estrategia de Optimización

### Paso 1: Pre-cargar Turnos
- Consulta única para todos los Turnos de la fecha
- Crear diccionario: `{explorador_id: turno}`

### Paso 2: Pre-cargar Asignaciones
- Consulta única para todas las asignaciones relevantes
- Agrupar por explorador y tomar la más reciente
- Crear diccionario: `{explorador_id: asignacion}`

### Paso 3: Procesar en Memoria
- Iterar sobre empleados activos
- Para cada empleado:
  - Buscar en diccionario de Turnos (O(1))
  - Si no existe, buscar en diccionario de Asignaciones (O(1))
  - Comparar jornada con jornada contraria
  - Agregar a lista si coincide

### Resultado Esperado:

**Consultas totales:**
- 1 consulta: Empleados activos
- 1 consulta: Turnos de la fecha
- 1 consulta: Asignaciones relevantes
- 1 consulta: Jornada del usuario actual

**TOTAL: 4 consultas** ✅ (vs 200-300 actuales)

---

## 📝 Resumen del Análisis

### Problema Actual:
- ❌ 200-300 consultas para 100 empleados
- ❌ N+1 queries problem
- ❌ Lento y no escalable

### Solución Propuesta:
- ✅ 4 consultas totales
- ✅ Pre-carga de datos
- ✅ Procesamiento en memoria
- ✅ Escalable a cualquier número de empleados

### Archivos a Modificar:
- `AppTurnosExplora/solicitudes/services/solicitud_service.py`
  - Método: `get_empleados_jornada_contraria` (refactor completo)
  - Método: `get_jornada_explorador_fecha` (puede mantenerse para otros usos, pero no se usará en el loop)

---

## ✅ Criterio de Éxito para FASE 1.1

- [x] Código analizado completamente
- [x] Problema N+1 identificado
- [x] Consultas actuales contabilizadas (200-300)
- [x] Datos a pre-cargar identificados (Turnos y Asignaciones)
- [x] Estrategia de optimización definida
- [x] Archivos a modificar identificados

---

## 🚀 Próximo Paso: FASE 1.2

Pre-cargar Turnos con consulta batch usando `prefetch_related` o `select_related`.

---

**Fecha de análisis:** [Fecha actual]
**Estado:** ✅ COMPLETADO

