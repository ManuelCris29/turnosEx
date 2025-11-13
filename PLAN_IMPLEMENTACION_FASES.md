# PLAN DE IMPLEMENTACIÓN - CAMBIOS DE TURNO
## Guía Paso a Paso Completa

---

## 📋 FASE 1: FUNDAMENTOS (Prioridad Crítica)

### 🔍 FASE 1.1: Optimizar Consultas - Análisis
**Objetivo:** Analizar el código actual para entender el problema N+1

**Pasos:**
1. ✅ Revisar método `get_empleados_jornada_contraria` en `solicitud_service.py`
2. ✅ Identificar el loop que hace consultas individuales
3. ✅ Documentar cuántas consultas se hacen actualmente
4. ✅ Identificar qué datos necesitamos pre-cargar

**Archivos a revisar:**
- `AppTurnosExplora/solicitudes/services/solicitud_service.py` (líneas 42-102)

**Criterio de éxito:** Entender completamente el problema actual

---

### ⚡ FASE 1.2: Optimizar Consultas - Pre-cargar Turnos
**Objetivo:** Cargar todos los Turnos de una vez en lugar de uno por uno

**Pasos:**
1. ✅ Crear consulta batch para Turnos de la fecha específica
2. ✅ Usar `select_related('jornada')` para evitar consultas adicionales
3. ✅ Crear diccionario `turnos_por_explorador` para acceso rápido
4. ✅ Probar que la consulta funciona correctamente

**Código a modificar:**
- `AppTurnosExplora/solicitudes/services/solicitud_service.py`
- Método: `get_empleados_jornada_contraria`

**Criterio de éxito:** Consulta única trae todos los Turnos necesarios

---

### ⚡ FASE 1.3: Optimizar Consultas - Pre-cargar Asignaciones
**Objetivo:** Cargar todas las asignaciones de jornada de una vez

**Pasos:**
1. ✅ Crear consulta batch para AsignarJornadaExplorador
2. ✅ Filtrar por `fecha_inicio__lte=fecha_obj`
3. ✅ Usar `select_related('jornada')` para evitar consultas adicionales
4. ✅ Agrupar por explorador y tomar la más reciente (order_by('-fecha_inicio'))
5. ✅ Crear diccionario `asignaciones_por_explorador` para acceso rápido

**Código a modificar:**
- `AppTurnosExplora/solicitudes/services/solicitud_service.py`
- Método: `get_empleados_jornada_contraria`

**Criterio de éxito:** Consulta única trae todas las asignaciones necesarias

---

### ⚡ FASE 1.4: Optimizar Consultas - Refactorizar Método Principal
**Objetivo:** Reemplazar el loop con consultas batch

**Pasos:**
1. ✅ Obtener jornada del usuario actual (ya optimizado)
2. ✅ Determinar jornada contraria
3. ✅ Cargar todos los empleados activos (una consulta)
4. ✅ Pre-cargar todos los Turnos de la fecha (una consulta)
5. ✅ Pre-cargar todas las asignaciones relevantes (una consulta)
6. ✅ Crear diccionarios en memoria para acceso rápido
7. ✅ Iterar sobre empleados usando datos en memoria (sin consultas DB)
8. ✅ Filtrar por jornada contraria
9. ✅ Retornar lista de empleados

**Código a modificar:**
- `AppTurnosExplora/solicitudes/services/solicitud_service.py`
- Método: `get_empleados_jornada_contraria` (refactor completo)

**Criterio de éxito:** 
- De 200+ consultas → 4-5 consultas totales
- Funcionalidad idéntica, mejor rendimiento

---

### ✅ FASE 1.5: Optimizar Consultas - Pruebas
**Objetivo:** Verificar que todo funciona correctamente

**Pasos:**
1. ✅ Probar búsqueda de compañeros con fecha sin cambios
2. ✅ Probar búsqueda de compañeros con fecha con cambios aprobados
3. ✅ Verificar que se muestran solo jornadas contrarias
4. ✅ Verificar que se consideran Turnos antes que asignaciones
5. ✅ Medir tiempo de respuesta (debe ser <500ms)
6. ✅ Verificar en logs que solo se hacen 4-5 consultas

**Criterio de éxito:** Todo funciona igual, pero más rápido

---

### 🔒 FASE 1.6: Transacciones - Agregar transaction.atomic()
**Objetivo:** Garantizar que todas las operaciones se ejecuten o ninguna

**Pasos:**
1. ✅ Importar `transaction` de `django.db`
2. ✅ Envolver todo el método `aplicar_cambios` en `with transaction.atomic():`
3. ✅ Verificar que todas las operaciones están dentro del bloque
4. ✅ Probar que funciona correctamente

**Código a modificar:**
- `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py`
- Método: `aplicar_cambios`

**Criterio de éxito:** Método protegido con transacción atómica

---

### 🔒 FASE 1.7: Transacciones - Agregar select_for_update()
**Objetivo:** Bloquear la solicitud durante el procesamiento para evitar race conditions

**Pasos:**
1. ✅ Al inicio de `aplicar_cambios`, recargar solicitud con `select_for_update()`
2. ✅ Verificar que la solicitud sigue en estado 'aprobada'
3. ✅ Verificar que no tiene turnos ya creados
4. ✅ Continuar con el procesamiento normal
5. ✅ Probar que funciona correctamente

**Código a modificar:**
- `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py`
- Método: `aplicar_cambios`

**Criterio de éxito:** Solicitud bloqueada durante procesamiento

---

### 🔒 FASE 1.8: Transacciones - Verificar Rollback
**Objetivo:** Asegurar que los errores revierten todos los cambios

**Pasos:**
1. ✅ Probar escenario: error al crear primer Turno → verificar que no se crea nada
2. ✅ Probar escenario: error al crear segundo Turno → verificar que se revierte el primero
3. ✅ Probar escenario: error al actualizar solicitud → verificar que no se crean Turnos
4. ✅ Verificar en logs que se hace rollback correctamente

**Criterio de éxito:** Errores revierten todos los cambios automáticamente

---

### 📊 FASE 1.9: Índices BD - Índice en Turno
**Objetivo:** Acelerar búsquedas por explorador y fecha

**Pasos:**
1. ✅ Abrir `AppTurnosExplora/turnos/models.py`
2. ✅ Agregar clase `Meta` al modelo `Turno` (si no existe)
3. ✅ Agregar índice compuesto: `(explorador, fecha)`
4. ✅ Nombre del índice: `turno_explorador_fecha_idx`
5. ✅ Crear migración: `python manage.py makemigrations`
6. ✅ Revisar migración generada

**Código a modificar:**
- `AppTurnosExplora/turnos/models.py`
- Modelo: `Turno`

**Criterio de éxito:** Migración creada correctamente

---

### 📊 FASE 1.10: Índices BD - Índice en SolicitudCambio
**Objetivo:** Acelerar búsquedas de solicitudes por receptor y fecha

**Pasos:**
1. ✅ Abrir `AppTurnosExplora/solicitudes/models.py`
2. ✅ Agregar clase `Meta` al modelo `SolicitudCambio` (si no existe)
3. ✅ Agregar índice compuesto: `(explorador_receptor, fecha_cambio_turno, estado)`
4. ✅ Nombre del índice: `solicitud_receptor_fecha_estado_idx`
5. ✅ Crear migración: `python manage.py makemigrations`
6. ✅ Revisar migración generada

**Código a modificar:**
- `AppTurnosExplora/solicitudes/models.py`
- Modelo: `SolicitudCambio`

**Criterio de éxito:** Migración creada correctamente

---

### 📊 FASE 1.11: Índices BD - Índice en AsignarJornadaExplorador
**Objetivo:** Acelerar búsquedas de asignaciones por explorador y fecha

**Pasos:**
1. ✅ Abrir `AppTurnosExplora/turnos/models.py`
2. ✅ Agregar clase `Meta` al modelo `AsignarJornadaExplorador` (si no existe)
3. ✅ Agregar índice compuesto: `(explorador, fecha_inicio)`
4. ✅ Nombre del índice: `jornada_explorador_fecha_idx`
5. ✅ Crear migración: `python manage.py makemigrations`
6. ✅ Revisar migración generada

**Código a modificar:**
- `AppTurnosExplora/turnos/models.py`
- Modelo: `AsignarJornadaExplorador`

**Criterio de éxito:** Migración creada correctamente

---

### 📊 FASE 1.12: Índices BD - Ejecutar Migraciones
**Objetivo:** Aplicar los índices a la base de datos

**Pasos:**
1. ✅ Hacer backup de la base de datos (recomendado)
2. ✅ Ejecutar migraciones: `python manage.py migrate`
3. ✅ Verificar que no hay errores
4. ✅ Verificar en BD que los índices se crearon:
   - `turno_explorador_fecha_idx`
   - `solicitud_receptor_fecha_estado_idx`
   - `jornada_explorador_fecha_idx`
5. ✅ Probar que las consultas siguen funcionando

**Criterio de éxito:** Índices creados en BD, consultas funcionan

---

### 🎯 FASE 1.13: First-Come - Modificar Validación
**Objetivo:** Permitir múltiples solicitudes para mismo receptor/fecha

**Pasos:**
1. ✅ Abrir `AppTurnosExplora/solicitudes/services/solicitud_validator.py`
2. ✅ Revisar método `validar_duplicada_misma_fecha`
3. ✅ Modificar para que solo valide mismo par (solicitante-receptor-fecha)
4. ✅ NO validar si hay otros solicitantes para el mismo receptor
5. ✅ Probar que permite múltiples solicitudes

**Código a modificar:**
- `AppTurnosExplora/solicitudes/services/solicitud_validator.py`
- Método: `validar_duplicada_misma_fecha`

**Criterio de éxito:** Permite múltiples solicitudes para mismo receptor/fecha

---

### 🎯 FASE 1.14: First-Come - Rechazar Otras Solicitudes
**Objetivo:** Al aprobar una solicitud, rechazar automáticamente las demás

**Pasos:**
1. ✅ Abrir `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py`
2. ✅ En método `aplicar_cambios`, después de crear turnos exitosamente
3. ✅ Buscar otras solicitudes pendientes para mismo receptor/fecha:
   - `explorador_receptor = solicitud.explorador_receptor`
   - `fecha = solicitud.fecha_cambio_turno`
   - `estado = 'pendiente'`
   - Excluir la solicitud actual
4. ✅ Cambiar estado de esas solicitudes a 'rechazada'
5. ✅ Agregar comentario: "Rechazada automáticamente: otra solicitud fue aprobada primero"
6. ✅ Guardar cambios
7. ✅ Probar que funciona

**Código a modificar:**
- `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py`
- Método: `aplicar_cambios`

**Criterio de éxito:** Otras solicitudes se rechazan automáticamente

---

### 🎯 FASE 1.15: First-Come - Notificaciones
**Objetivo:** Notificar a solicitantes cuyas solicitudes fueron rechazadas

**Pasos:**
1. ✅ Después de rechazar solicitudes automáticamente
2. ✅ Para cada solicitud rechazada:
   - Obtener `explorador_solicitante`
   - Crear notificación: "Tu solicitud fue rechazada automáticamente porque otra solicitud para el mismo receptor/fecha fue aprobada primero"
   - Tipo: 'rechazo'
3. ✅ Usar `NotificacionService` para crear notificaciones
4. ✅ Probar que se crean notificaciones correctamente

**Código a modificar:**
- `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py`
- Método: `aplicar_cambios`

**Criterio de éxito:** Notificaciones creadas para solicitantes afectados

---

### ✅ FASE 1.16: First-Come - Pruebas Completas
**Objetivo:** Verificar todo el flujo First-Come, First-Served

**Pasos:**
1. ✅ Crear 3 solicitudes: A→X, B→X, C→X (misma fecha)
2. ✅ Aprobar primera solicitud (A→X)
3. ✅ Verificar que se crean turnos para A y X
4. ✅ Verificar que solicitudes B→X y C→X se rechazan automáticamente
5. ✅ Verificar que se crean notificaciones para B y C
6. ✅ Intentar aprobar B→X (debe fallar porque ya está rechazada)
7. ✅ Verificar que no se crean turnos duplicados

**Criterio de éxito:** Flujo completo funciona correctamente

---

## 📋 FASE 2: CAMBIO SOBRE CAMBIO (Prioridad Alta)

### 🔄 FASE 2.1: Actualizar Turno Existente - Modificar aplicar_cambios
**Objetivo:** Si ya existe Turno, actualizarlo en lugar de crear nuevo

**Pasos:**
1. ✅ Abrir `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py`
2. ✅ En método `aplicar_cambios`, antes de crear Turno para solicitante:
3. ✅ Buscar si ya existe Turno para `explorador + fecha`
4. ✅ Si existe:
   - Actualizar `jornada` y `sala`
   - Mantener `tipo_cambio='CT'`
   - NO crear nuevo registro
5. ✅ Si no existe:
   - Crear nuevo Turno (comportamiento actual)
6. ✅ Repetir para receptor
7. ✅ Probar que funciona

**Código a modificar:**
- `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py`
- Método: `aplicar_cambios`

**Criterio de éxito:** Turnos existentes se actualizan, no se duplican

---

### 🔄 FASE 2.2: Validación Jornada Actual - Verificar Lógica
**Objetivo:** Asegurar que validaciones usan jornada actual (Turno o asignación)

**Pasos:**
1. ✅ Verificar que `get_jornada_explorador_fecha` ya busca Turno primero
2. ✅ Verificar que `validar_jornada_en_fecha` usa este método
3. ✅ Verificar que `get_empleados_jornada_contraria` usa este método
4. ✅ Probar escenario: explorador con cambio aprobado puede cambiar de nuevo

**Criterio de éxito:** Todas las validaciones usan jornada actual correctamente

---

### 🔄 FASE 2.3: Límite de Cambios - Agregar Validación ✅
**Objetivo:** Limitar número de cambios por explorador/fecha

**Pasos:**
1. ✅ Crear método `contar_cambios_explorador_fecha(explorador_id, fecha)`
2. ✅ Contar solicitudes aprobadas para ese explorador/fecha
3. ✅ En `aplicar_cambios`, verificar límite (ej: máximo 2 cambios)
4. ✅ Si excede límite, retornar error
5. ✅ Agregar mensaje: "Se ha alcanzado el límite de cambios para esta fecha"
6. ⏳ Probar que funciona

**Código modificado:**
- `AppTurnosExplora/solicitudes/services/solicitud_service.py` - Método `contar_cambios_explorador_fecha` agregado (líneas 686-721)
- `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py` - Validación de límite agregada en `aplicar_cambios` (líneas 150-201)

**Criterio de éxito:** Límite de cambios funciona correctamente

---

### 🔄 FASE 2.4: Trazabilidad - Mejorar Historial ✅
**Objetivo:** Mantener registro de todos los cambios

**Pasos:**
1. ✅ Verificar que `SolicitudCambio` tiene campo `comentario`
2. ✅ Al actualizar Turno existente, agregar comentario:
   - "Actualización: cambio previo reemplazado"
   - Incluir referencia a solicitud anterior si es posible
3. ✅ Verificar que `HistoricalRecords` captura cambios
4. ⏳ Probar que se mantiene historial

**Código modificado:**
- `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py` - Lógica de trazabilidad agregada en `aplicar_cambios` (líneas 231-343)
  - Búsqueda de solicitud anterior que creó el turno existente
  - Agregado de comentarios de trazabilidad en la solicitud actual
  - Relación de solicitudes usando `solicitud_origen`

**Criterio de éxito:** Historial completo de cambios

---

### 🔄 FASE 2.5: Notificaciones UI - Advertencias ✅
**Objetivo:** Informar al usuario cuando ya tiene cambio aprobado

**Pasos:**
1. ✅ En vista de creación de solicitud, verificar si ya existe Turno
2. ✅ Si existe, mostrar advertencia:
   - "Ya tienes un cambio aprobado para esta fecha. Este nuevo cambio lo reemplazará."
3. ✅ Mostrar información del cambio actual (jornada, compañero)
4. ⏳ Probar que se muestra correctamente

**Código modificado:**
- `AppTurnosExplora/solicitudes/views.py` - Nueva vista `ObtenerCambioAprobadoView` (líneas 273-354)
- `AppTurnosExplora/solicitudes/urls.py` - Nueva ruta `obtener-cambio-aprobado/` (línea 44)
- `AppTurnosExplora/templates/solicitudes/solicitar_cambio_turno.html` - Div de advertencia agregado (líneas 42-56)
- `AppTurnosExplora/static/js/solicitar_cambio_turno.js` - Función `verificarCambioAprobado()` agregada (líneas 329-392)

**Criterio de éxito:** Usuario informado antes de crear solicitud

---

### ✅ FASE 2.6: Pruebas Cambio sobre Cambio ✅
**Objetivo:** Verificar todo el flujo de cambios múltiples

**Pasos:**
1. ✅ Crear solicitud A→B, aprobar
2. ✅ Verificar que se crea Turno para A (PM) y B (AM)
3. ✅ Crear solicitud A→C (mismo día)
4. ✅ Verificar que se actualiza Turno de A (vuelve a AM)
5. ✅ Verificar que se crea Turno para C (PM)
6. ✅ Verificar que Turno de B no cambia
7. ✅ Probar límite de cambios (si se implementó)

**Código creado:**
- `PRUEBAS_FASE2_6.md` - Documento detallado de casos de prueba
- `AppTurnosExplora/solicitudes/management/commands/test_cambio_sobre_cambio.py` - Comando automatizado de pruebas

**Criterio de éxito:** Cambios múltiples funcionan correctamente

---

## 📋 FASE 3: OPTIMIZACIÓN AVANZADA ✅

### ⚡ FASE 3.1: Índices Adicionales en SolicitudCambio ✅
**Objetivo:** Optimizar consultas por turno_origen, turno_destino y fecha_resolucion

**Pasos:**
1. ✅ Agregar índice `sol_turno_origen_estado_idx` en SolicitudCambio
2. ✅ Agregar índice `sol_turno_destino_estado_idx` en SolicitudCambio
3. ✅ Agregar índice `sol_fecha_resol_estado_idx` en SolicitudCambio
4. ✅ Crear y aplicar migraciones

**Código modificado:**
- `AppTurnosExplora/solicitudes/models.py` - Índices agregados (líneas 88-102)

**Criterio de éxito:** Índices creados, consultas optimizadas

---

### ⚡ FASE 3.2: Optimización de Consulta AsignarJornadaExplorador ✅
**Objetivo:** Evitar errores cuando hay múltiples registros y obtener siempre el más reciente

**Pasos:**
1. ✅ Cambiar `.get()` por `.first()` con `order_by('-fecha_inicio')`
2. ✅ Agregar `select_related('jornada')` para optimizar
3. ✅ Aplicar en `turnos/api/views.py` y `turnos/views.py`

**Código modificado:**
- `AppTurnosExplora/turnos/api/views.py` (líneas 90-96)
- `AppTurnosExplora/turnos/views.py` (líneas 59-65)

**Criterio de éxito:** Consultas más robustas y eficientes

---

### ⚡ FASE 3.3: Limitar Consulta de SolicitudCambio ✅
**Objetivo:** Evitar consultas lentas con miles de registros

**Pasos:**
1. ✅ Limitar consulta a 50 solicitudes más recientes
2. ✅ Aplicar en `turnos/api/views.py` y `turnos/views.py`

**Código modificado:**
- `AppTurnosExplora/turnos/api/views.py` (línea 167)
- `AppTurnosExplora/turnos/views.py` (línea 153)

**Criterio de éxito:** Consultas más rápidas, solo datos relevantes

---

### ⚡ FASE 3.4: Configuración de Caché Mejorada ✅
**Objetivo:** Mejorar rendimiento con más usuarios simultáneos

**Pasos:**
1. ✅ Aumentar `TIMEOUT` de 300s a 3600s (1 hora)
2. ✅ Aumentar `MAX_ENTRIES` de 1000 a 10000
3. ✅ Agregar configuración comentada para Redis (producción)

**Código modificado:**
- `AppTurnosExplora/config/settings.py` (líneas 179-195)

**Criterio de éxito:** Configuración de caché optimizada

---

### ⚡ FASE 3.5: Implementación de Caché en MisTurnosPorMesView ✅
**Objetivo:** Reducir tiempo de carga de 5s a <1s

**Pasos:**
1. ✅ Implementar caché en `MisTurnosPorMesView`
2. ✅ Clave única: `turnos_mes_{empleado_id}_{anio}_{mes}`
3. ✅ TTL: 1 hora (3600 segundos)
4. ✅ Invalidar caché al crear/modificar turnos

**Código modificado:**
- `AppTurnosExplora/turnos/api/views.py` - Caché implementado (líneas 56-205)
- `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py` - Invalidación de caché (líneas 371-386)

**Criterio de éxito:** Caché funciona, se invalida correctamente

---

### ⚡ FASE 3.6: Modelo TurnoArchivo ✅
**Objetivo:** Crear modelo para almacenar turnos antiguos

**Pasos:**
1. ✅ Crear modelo `TurnoArchivo` con misma estructura que `Turno`
2. ✅ Agregar campo `fecha_archivado` y `turno_original_id`
3. ✅ Agregar índices optimizados
4. ✅ Crear y aplicar migraciones

**Código modificado:**
- `AppTurnosExplora/turnos/models.py` - Modelo `TurnoArchivo` creado (líneas 69-92)

**Criterio de éxito:** Modelo creado, migraciones aplicadas

---

### ⚡ FASE 3.7: Comando para Archivar Turnos ✅
**Objetivo:** Archivar turnos antiguos automáticamente

**Pasos:**
1. ✅ Crear comando `archivar_turnos_antiguos`
2. ✅ Archivar en lotes de 100 para mejor rendimiento
3. ✅ Mantener trazabilidad con `turno_original_id`
4. ✅ Limpiar caché automáticamente después de archivar
5. ✅ Agregar opción `--dry-run` para simular

**Código creado:**
- `AppTurnosExplora/turnos/management/commands/archivar_turnos_antiguos.py`

**Criterio de éxito:** Comando funciona correctamente

---

### ⚡ FASE 3.8: Comando para Archivar Solicitudes ✅
**Objetivo:** Preparar comando para archivar solicitudes antiguas

**Pasos:**
1. ✅ Crear comando `archivar_solicitudes_antiguas`
2. ⏳ Nota: Actualmente solo informa. Para implementar completamente, se necesita:
   - Agregar campo `archivada` al modelo `SolicitudCambio`, O
   - Crear modelo `SolicitudCambioArchivo` similar a `TurnoArchivo`

**Código creado:**
- `AppTurnosExplora/solicitudes/management/commands/archivar_solicitudes_antiguas.py`

**Criterio de éxito:** Comando base creado (implementación completa pendiente)

---

## 📋 FASE 4: QA Y VALIDACIÓN FINAL

### ✅ FASE 4.1: Pruebas Unitarias
**Objetivo:** Crear tests automatizados

**Pasos:**
1. ✅ Test: optimización de consultas (verificar número de queries)
2. ✅ Test: transacciones (verificar rollback)
3. ✅ Test: First-Come, First-Served
4. ✅ Test: Cambio sobre cambio
5. ✅ Test: Límite de cambios
6. ✅ Ejecutar todos los tests

**Criterio de éxito:** Todos los tests pasan

---

### ✅ FASE 4.2: Pruebas Manuales
**Objetivo:** Verificar flujos completos

**Pasos:**
1. ✅ Escenario 1: Cambio simple (A→B)
2. ✅ Escenario 2: Múltiples solicitantes (A→X, B→X, C→X)
3. ✅ Escenario 3: Cambio sobre cambio (A→B, luego A→C)
4. ✅ Escenario 4: Error durante aprobación (verificar rollback)
5. ✅ Escenario 5: Límite de cambios
6. ✅ Verificar rendimiento (<500ms)

**Criterio de éxito:** Todos los escenarios funcionan

---

### ✅ FASE 4.3: Documentación
**Objetivo:** Documentar cambios y reglas de negocio

**Pasos:**
1. ✅ Documentar regla First-Come, First-Served
2. ✅ Documentar cambio sobre cambio
3. ✅ Documentar límite de cambios
4. ✅ Documentar optimizaciones realizadas
5. ✅ Actualizar README si es necesario

**Criterio de éxito:** Documentación completa

---

## ✅ CHECKLIST FINAL

Antes de considerar completado, verificar:

- [ ] Consultas optimizadas (4-5 queries máximo)
- [ ] Transacciones atómicas funcionando
- [ ] Índices creados en BD
- [ ] First-Come, First-Served implementado
- [ ] Cambio sobre cambio funcionando
- [ ] Notificaciones funcionando
- [ ] Pruebas pasando
- [ ] Rendimiento <500ms
- [ ] Sin errores en logs
- [ ] Documentación actualizada

---

## 📝 NOTAS IMPORTANTES

1. **No saltarse pasos:** Cada fase depende de la anterior
2. **Probar después de cada cambio:** No acumular cambios sin probar
3. **Backup antes de migraciones:** Siempre hacer backup de BD
4. **Revisar logs:** Verificar que no hay errores
5. **Comunicar problemas:** Si algo no funciona, detener y revisar

---

**Última actualización:** [Fecha]
**Estado:** Pendiente de inicio

