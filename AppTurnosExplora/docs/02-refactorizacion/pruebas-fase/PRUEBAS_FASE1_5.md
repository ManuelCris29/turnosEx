# PRUEBAS FASE 1.5: Verificación de Optimización de Consultas
## Casos de Prueba para get_empleados_jornada_contraria

---

## ✅ Verificación de Código

### Revisión de Sintaxis
- [x] Código sin errores de sintaxis
- [x] Imports correctos
- [x] Lógica de diccionarios implementada
- [x] Logging agregado

---

## 🧪 Casos de Prueba Manuales

### Caso 1: Búsqueda Básica (Sin Cambios Aprobados)

**Escenario:**
- Usuario tiene jornada AM (asignación fija)
- Busca compañeros para fecha: 2024-12-15
- No hay cambios aprobados (Turnos) para esa fecha

**Pasos:**
1. Iniciar sesión como usuario con jornada AM
2. Ir a crear solicitud de cambio de turno
3. Seleccionar fecha: 2024-12-15
4. Ver lista de compañeros disponibles

**Resultado Esperado:**
- ✅ Muestra solo empleados con jornada PM (asignación fija)
- ✅ No muestra empleados con jornada AM
- ✅ No muestra al usuario actual
- ✅ Tiempo de respuesta < 1 segundo

**Verificación en Logs:**
- `turnos_precargados_count: 0` (no hay turnos)
- `asignaciones_precargadas_count: X` (X = número de empleados activos)
- `empleados_contrarios_count: Y` (Y = empleados con PM)

---

### Caso 2: Búsqueda con Cambios Aprobados

**Escenario:**
- Usuario tiene jornada AM (asignación fija)
- Hay un cambio aprobado: Usuario A cambió de AM a PM para 2024-12-15
- Busca compañeros para fecha: 2024-12-15

**Pasos:**
1. Aprobar un cambio de turno: Usuario A (AM) ↔ Usuario B (PM) para 2024-12-15
2. Iniciar sesión como usuario con jornada AM
3. Ir a crear solicitud de cambio de turno
4. Seleccionar fecha: 2024-12-15
5. Ver lista de compañeros disponibles

**Resultado Esperado:**
- ✅ Muestra empleados con jornada PM (asignación fija)
- ✅ Muestra Usuario A (ahora tiene PM por cambio aprobado)
- ✅ NO muestra Usuario B (ahora tiene AM por cambio aprobado)
- ✅ Tiempo de respuesta < 1 segundo

**Verificación en Logs:**
- `turnos_precargados_count: 2` (turnos de A y B)
- `asignaciones_precargadas_count: X`
- `empleados_contrarios_count: Y+1` (incluye A con PM)

---

### Caso 3: Usuario con Cambio Aprobado Busca Compañeros

**Escenario:**
- Usuario tiene jornada AM (asignación fija)
- Usuario cambió a PM para 2024-12-15 (cambio aprobado)
- Busca compañeros para fecha: 2024-12-15

**Pasos:**
1. Aprobar cambio: Usuario (AM) ↔ Otro Usuario (PM) para 2024-12-15
2. Iniciar sesión como el Usuario
3. Ir a crear solicitud de cambio de turno
4. Seleccionar fecha: 2024-12-15
5. Ver lista de compañeros disponibles

**Resultado Esperado:**
- ✅ Muestra solo empleados con jornada AM (jornada contraria a PM actual del usuario)
- ✅ NO muestra empleados con jornada PM
- ✅ Considera el cambio aprobado (usuario tiene PM, busca AM)
- ✅ Tiempo de respuesta < 1 segundo

**Verificación en Logs:**
- `jornada_usuario: PM` (jornada del cambio, no la asignación fija)
- `jornada_contraria: AM`
- `empleados_contrarios_count: Y` (empleados con AM)

---

### Caso 4: Múltiples Empleados (Prueba de Rendimiento)

**Escenario:**
- Sistema con 100+ empleados activos
- Usuario busca compañeros disponibles

**Pasos:**
1. Iniciar sesión
2. Ir a crear solicitud de cambio de turno
3. Seleccionar fecha
4. Medir tiempo de respuesta

**Resultado Esperado:**
- ✅ Lista se carga en < 1 segundo
- ✅ Muestra solo compañeros con jornada contraria
- ✅ No hay errores en consola
- ✅ No hay timeouts

**Verificación en Logs:**
- `empleados_activos_count: 100+`
- `turnos_precargados_count: X`
- `asignaciones_precargadas_count: 100+`
- Tiempo total < 1 segundo

**Verificación de Consultas DB:**
- Abrir Django Debug Toolbar o logs de DB
- Verificar que solo se hacen 4-5 consultas SQL
- NO debe haber 100+ consultas

---

### Caso 5: Fecha sin Empleados Activos

**Escenario:**
- Fecha futura muy lejana
- Pocos o ningún empleado con asignación para esa fecha

**Pasos:**
1. Iniciar sesión
2. Ir a crear solicitud de cambio de turno
3. Seleccionar fecha futura (ej: 2025-12-31)
4. Ver lista de compañeros

**Resultado Esperado:**
- ✅ No muestra errores
- ✅ Lista vacía o con pocos empleados (si hay asignaciones)
- ✅ Tiempo de respuesta rápido

---

### Caso 6: Usuario sin Jornada Asignada

**Escenario:**
- Usuario no tiene jornada asignada (ni fija ni cambio)

**Pasos:**
1. Iniciar sesión como usuario sin jornada
2. Ir a crear solicitud de cambio de turno
3. Seleccionar fecha

**Resultado Esperado:**
- ✅ Retorna lista vacía
- ✅ No muestra errores
- ✅ Mensaje apropiado (si está implementado)

---

## 📊 Verificación de Rendimiento

### Métricas a Medir:

1. **Número de Consultas SQL:**
   - Antes: 200-300 consultas
   - Después: 4-5 consultas
   - Herramienta: Django Debug Toolbar o logs

2. **Tiempo de Respuesta:**
   - Antes: 2-3 segundos
   - Después: < 1 segundo
   - Herramienta: Network tab en DevTools

3. **Uso de Memoria:**
   - Verificar que no hay memory leaks
   - Diccionarios se crean y destruyen correctamente

---

## 🔍 Verificación de Logs

### Logs Esperados:

```
DEBUG: get_empleados_jornada_contraria fecha=2024-12-15 usuario_id=1
DEBUG: jornada_usuario jornada=AM
DEBUG: jornada_contraria jornada_contraria=PM
DEBUG: empleados_activos_count count=100
DEBUG: turnos_precargados_count count=5
DEBUG: asignaciones_precargadas_count count=100
DEBUG: empleados_contrarios_count count=45
```

### Verificar:
- ✅ Todos los logs aparecen
- ✅ Números son razonables
- ✅ No hay errores o warnings

---

## ✅ Checklist de Verificación

### Funcionalidad:
- [ ] Lista muestra solo compañeros con jornada contraria
- [ ] Considera cambios aprobados (Turnos)
- [ ] Considera asignaciones fijas si no hay Turnos
- [ ] No muestra al usuario actual
- [ ] Funciona con diferentes fechas
- [ ] Funciona con usuarios sin jornada

### Rendimiento:
- [ ] Tiempo de respuesta < 1 segundo
- [ ] Solo 4-5 consultas SQL (verificar con Debug Toolbar)
- [ ] No hay timeouts
- [ ] Escala bien con 100+ empleados

### Código:
- [ ] Sin errores en consola
- [ ] Logs aparecen correctamente
- [ ] No hay warnings críticos

---

## 🐛 Problemas Conocidos a Verificar

### Si la lista está vacía cuando debería tener empleados:
- Verificar que hay empleados activos
- Verificar que hay asignaciones de jornada
- Verificar que la fecha es correcta
- Revisar logs para ver qué está pasando

### Si muestra empleados incorrectos:
- Verificar lógica de jornada contraria
- Verificar que Turnos tienen prioridad sobre Asignaciones
- Revisar diccionarios en logs

### Si es lento:
- Verificar número de consultas SQL
- Verificar que se están usando los diccionarios
- Revisar si hay consultas N+1 todavía

---

## 📝 Notas de Prueba

**Fecha de Prueba:** [Fecha]
**Probado por:** [Nombre]
**Resultado:** [Pendiente/Exitoso/Con Errores]

**Observaciones:**
- [Anotar cualquier observación durante las pruebas]

---

## ✅ Criterio de Éxito

La FASE 1.5 se considera completada cuando:
- ✅ Todos los casos de prueba pasan
- ✅ Rendimiento mejorado (4-5 consultas, <1 segundo)
- ✅ Funcionalidad idéntica a antes
- ✅ Sin errores en producción

---

**Estado:** Pendiente de Pruebas

