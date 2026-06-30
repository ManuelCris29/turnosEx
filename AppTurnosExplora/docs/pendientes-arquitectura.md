# Pendientes de Arquitectura Limpia

## Refactorización de vistas con lógica de negocio inline

### ¿Por qué está pendiente?
Estas vistas tienen queries ORM y lógica de negocio directamente en el código de la vista,
lo cual viola la separación de capas. Se dejó pendiente porque el proyecto aún no está
terminado funcionalmente — refactorizar ahora podría introducir regresiones en flujos
que todavía están en desarrollo.

### ¿Cuándo conviene hacerlo?
Cuando el proyecto esté **funcionalmente completo** (todas las funcionalidades de solicitudes
implementadas y estables) y antes de subir a AWS. Es un prerequisito de calidad antes del
deploy a producción.

---

### Archivos a refactorizar

#### 1. `solicitudes/views/api_turno_jornada.py` — 855 líneas
**Problema**: 34 queries ORM directas en la vista. Hace lookups de `Empleado`,
`AsignarJornadaExplorador`, `Turno`, `DiaEspecial`, `SolicitudCambio` sin pasar
por repositorios ni servicios.

**Acción**: Extraer cada bloque de queries a métodos en `TurnoRepository` o crear
un nuevo `TurnoContextRepository`. Las clases de vista quedan como orquestadoras
delgadas que solo llaman al servicio y devuelven JSON.

---

#### 2. `solicitudes/views/api_disponibles_ct_preview.py` — 539 líneas
**Problema**: Queries inline de `Empleado` y lógica de disponibilidad mezclada con
la construcción de la respuesta HTTP.

**Acción**: Mover queries de disponibilidad a `EmpleadoDisponibilidadService` (ya existe)
y las de empleados a `EmpleadoRepository` (ya creado).

---

#### 3. `solicitudes/views/doblada_api.py` — 533 líneas
**Problema**: Queries de `Turno` y `DobladaDetalle` inline.

**Acción**: Mover a `TurnoRepository.tiene_doblada()` y métodos existentes de
`DobladaFiltroService`.

---

#### 4. `empleados/views.py` — 870 líneas
**Problema**: 29 queries ORM directas mezcladas con lógica de presentación.

**Acción**: `EmpleadoRepository` ya fue creado con los métodos principales.
Actualizar las vistas para llamar al repositorio en lugar del ORM directo.

---

### Impacto estimado en puntaje de arquitectura limpia
Al completar esto: **85% → ~97%**

El 3% restante sería inyección de dependencias formal (no crítico para este tipo de proyecto).

---

### Orden recomendado de refactorización
1. `empleados/views.py` — usa `EmpleadoRepository` que ya existe, cambios mecánicos
2. `doblada_api.py` — más pequeño, servicios ya disponibles
3. `api_disponibles_ct_preview.py` — conectar con `EmpleadoDisponibilidadService`
4. `api_turno_jornada.py` — el más grande, dejarlo para el final
