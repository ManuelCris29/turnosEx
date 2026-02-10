# INSTRUCCIONES PARA APLICAR OPTIMIZACIONES - FASE 3

## ✅ Cambios Implementados

### 1. Índices Adicionales en SolicitudCambio
- ✅ Agregados 3 índices nuevos para optimizar consultas
- **Archivo:** `solicitudes/models.py`

### 2. Optimización de Consultas
- ✅ Cambiado `.get()` por `.first()` en `AsignarJornadaExplorador`
- ✅ Limitado consulta de `SolicitudCambio` a 50 registros más recientes
- **Archivos:** `turnos/api/views.py`, `turnos/views.py`

### 3. Sistema de Caché
- ✅ Configuración mejorada de caché en `settings.py`
- ✅ Implementado caché en `MisTurnosPorMesView`
- ✅ Invalidación automática de caché al crear/modificar turnos
- **Archivos:** `config/settings.py`, `turnos/api/views.py`, `solicitudes/services/strategies/cambio_turno_strategy.py`

### 4. Sistema de Archivo
- ✅ Creado modelo `TurnoArchivo` para datos antiguos
- ✅ Creado comando `archivar_turnos_antiguos` para archivar turnos
- ✅ Creado comando `archivar_solicitudes_antiguas` (información)
- **Archivos:** `turnos/models.py`, `turnos/management/commands/archivar_turnos_antiguos.py`

## 📋 Pasos para Aplicar

### Paso 1: Crear Migraciones
```bash
cd AppTurnosExplora
python manage.py makemigrations
```

Esto creará migraciones para:
- Los nuevos índices en `SolicitudCambio`
- El nuevo modelo `TurnoArchivo`

### Paso 2: Aplicar Migraciones
```bash
python manage.py migrate
```

### Paso 3: Verificar que Todo Funciona
```bash
# Probar que el sistema funciona correctamente
python manage.py runserver
```

### Paso 4: Probar el Comando de Archivo (Opcional - Dry Run)
```bash
# Simular archivado sin hacer cambios reales
python manage.py archivar_turnos_antiguos --dry-run
```

## 🔄 Uso del Sistema de Archivo

### Archivar Turnos Antiguos

**Simular (recomendado primero):**
```bash
python manage.py archivar_turnos_antiguos --dry-run
```

**Archivar turnos de más de 1 año:**
```bash
python manage.py archivar_turnos_antiguos
```

**Archivar turnos de más de 2 años:**
```bash
python manage.py archivar_turnos_antiguos --dias 730
```

**Nota:** El comando:
- Archiva en lotes de 100 para mejor rendimiento
- Mantiene trazabilidad con `turno_original_id`
- Limpia el caché automáticamente después de archivar

### Programar Archivado Automático (Recomendado)

Agregar a crontab (Linux) o Task Scheduler (Windows) para ejecutar mensualmente:

**Linux:**
```bash
# Ejecutar el primer día de cada mes a las 2 AM
0 2 1 * * cd /ruta/al/proyecto/AppTurnosExplora && python manage.py archivar_turnos_antiguos
```

**Windows (Task Scheduler):**
- Crear tarea programada
- Ejecutar: `python manage.py archivar_turnos_antiguos`
- Frecuencia: Mensual, día 1, hora 2:00 AM

## 📊 Mejoras de Rendimiento Esperadas

### Antes de Optimizaciones:
- ⏱️ Tiempo de carga: **5 segundos**
- 👥 Con 300 usuarios: **15-20 segundos** (estimado)
- 📈 Con datos antiguos: **30+ segundos** (estimado)

### Después de Optimizaciones:
- ⚡ Tiempo de carga: **<1 segundo** (con caché)
- 👥 Con 300 usuarios: **<1 segundo** (caché compartido)
- 📈 Con datos antiguos: **<1 segundo** (solo últimos 2 años en tabla principal)

## ⚠️ Notas Importantes

1. **Caché:** Los datos se cachean por 1 hora. El caché se invalida automáticamente cuando se crean/modifican turnos.

2. **Archivo:** Los turnos antiguos se mueven a `TurnoArchivo`, pero siguen siendo accesibles para consultas históricas.

3. **Backup:** Antes de archivar por primera vez, hacer backup de la base de datos.

4. **Redis (Producción):** Para producción con muchos usuarios, se recomienda usar Redis. Ver configuración comentada en `settings.py`.

## 🔍 Verificación

Después de aplicar las migraciones, verificar:

1. ✅ Los índices se crearon correctamente:
   ```sql
   SHOW INDEX FROM solicitudes_solicitudcambio;
   ```

2. ✅ La tabla `TurnoArchivo` existe:
   ```sql
   DESCRIBE turnos_turnoarchivo;
   ```

3. ✅ El caché funciona (ver logs en consola del navegador)

4. ✅ Los tiempos de carga mejoraron (deberían ser <1s)

## 📝 Próximos Pasos (Opcional)

1. **Configurar Redis** para producción (ver `settings.py`)
2. **Monitorear rendimiento** con Django Debug Toolbar
3. **Configurar archivado automático** con cron/Task Scheduler
4. **Crear modelo SolicitudCambioArchivo** si se necesita archivar solicitudes

