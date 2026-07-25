# Plan de Reorganización del Proyecto AppTurnosExplora

## 📋 Análisis de la Estructura Actual

### ✅ Aspectos Bien Organizados

1. **Apps Django bien estructuradas**: `empleados`, `turnos`, `solicitudes`, `permisos`
2. **Separación de servicios**: Cada app tiene su carpeta `services/`
3. **Tests organizados**: Mayoría de apps tienen carpeta `tests/`
4. **Core bien estructurado**: `core/utils/`, `core/services/`, `core/interfaces/`
5. **Strategy Pattern implementado**: `solicitudes/services/strategies/`

### ⚠️ Problemas Identificados

#### 1. Scripts de Prueba y Debug en la Raíz
**Archivos problemáticos:**
- `test_*.py` (8 archivos en raíz)
- `debug_*.py` (4 archivos en raíz)
- `create_*.py`, `fix_*.py`, `validar_*.py`, `verificar_*.py` (varios archivos)

**Problema**: Contaminan la raíz del proyecto y dificultan la navegación.

#### 2. Scripts de Utilidad Mezclados
**Archivos:**
- `check_recent_requests.py`
- `clean_corrupt_data.py`
- `validar_jornadas.py`
- `verificar_cambios_permanentes.py`

**Problema**: Deberían estar en `scripts/` o como management commands.

#### 3. Tests en Management Commands
**Archivos:**
- `solicitudes/management/commands/test_*.py` (3 archivos)

**Problema**: Los tests deben estar en `tests/`, no en `management/commands/`.

#### 4. Archivos de Documentación en Raíz
**Archivos:**
- `MANUAL_DESPLIEGUE_EC2.md`

**Problema**: Debería estar en `docs/`.

#### 5. Duplicación de tests.py y tests/
**Problema**: Algunas apps tienen ambos `tests.py` y carpeta `tests/`, lo cual es redundante.

---

## 🎯 Plan de Reorganización

### Fase 1: Limpieza de la Raíz del Proyecto

#### 1.1 Mover Scripts de Prueba a `scripts/tests/`

**Crear estructura:**
```
scripts/
├── tests/              # Scripts de prueba temporales
│   ├── test_architecture.py
│   ├── test_cancelacion_solicitudes.py
│   ├── test_counter.py
│   ├── test_ct_permanente.py
│   ├── test_email_from_user.py
│   ├── test_jornadas_corregidas.py
│   ├── test_manual_request.py
│   └── test_new_notification.py
```

**Archivos a mover:**
- `test_architecture.py` → `scripts/tests/`
- `test_cancelacion_solicitudes.py` → `scripts/tests/`
- `test_counter.py` → `scripts/tests/`
- `test_ct_permanente.py` → `scripts/tests/`
- `test_email_from_user.py` → `scripts/tests/`
- `test_jornadas_corregidas.py` → `scripts/tests/`
- `test_manual_request.py` → `scripts/tests/`
- `test_new_notification.py` → `scripts/tests/`

#### 1.2 Mover Scripts de Debug a `scripts/debug/`

**Crear estructura:**
```
scripts/
├── debug/              # Scripts de debugging
│   ├── debug_luisa_notifications.py
│   ├── debug_manuel_notifications.py
│   └── debug_solicitud.py
```

**Archivos a mover:**
- `debug_luisa_notifications.py` → `scripts/debug/`
- `debug_manuel_notifications.py` → `scripts/debug/`
- `debug_solicitud.py` → `scripts/debug/`

#### 1.3 Mover Scripts de Utilidad a `scripts/utils/`

**Crear estructura:**
```
scripts/
├── utils/              # Scripts de utilidad
│   ├── check_recent_requests.py
│   ├── clean_corrupt_data.py
│   ├── create_luisa_request.py
│   ├── fix_solicitud_10.py
│   ├── validar_jornadas.py
│   └── verificar_cambios_permanentes.py
```

**Archivos a mover:**
- `check_recent_requests.py` → `scripts/utils/`
- `clean_corrupt_data.py` → `scripts/utils/`
- `create_luisa_request.py` → `scripts/utils/`
- `fix_solicitud_10.py` → `scripts/utils/`
- `validar_jornadas.py` → `scripts/utils/`
- `verificar_cambios_permanentes.py` → `scripts/utils/`

#### 1.4 Mover Documentación a `docs/`

**Archivos a mover:**
- `MANUAL_DESPLIEGUE_EC2.md` → `docs/deployment/`

---

### Fase 2: Reorganización de Tests

#### 2.1 Mover Tests de Management Commands

**Archivos a mover:**
- `solicitudes/management/commands/test_aprobar_solicitud.py` → `solicitudes/tests/test_aprobacion.py`
- `solicitudes/management/commands/test_cambio_sobre_cambio.py` → `solicitudes/tests/test_cambio_sobre_cambio.py`
- `solicitudes/management/commands/test_factory.py` → `solicitudes/tests/test_factory.py` (ya existe, consolidar)

#### 2.2 Eliminar tests.py Redundantes

**Verificar y eliminar si están vacíos o duplicados:**
- `solicitudes/tests.py` (si está vacío o solo importa de tests/)
- `turnos/tests.py` (si está vacío o solo importa de tests/)
- `empleados/tests.py` (si está vacío o solo importa de tests/)
- `permisos/tests.py` (si está vacío o solo importa de tests/)
- `core/dashboard/tests.py` (si está vacío)
- `core/login/tests.py` (si está vacío)

---

### Fase 3: Organización de Scripts Existentes

#### 3.1 Categorizar Scripts en `scripts/`

**Estructura propuesta:**
```
scripts/
├── __init__.py
├── tests/              # Scripts de prueba temporales
├── debug/              # Scripts de debugging
├── utils/              # Scripts de utilidad
├── migrations/         # Scripts relacionados con migraciones
│   ├── agregar_columna_historica_jornada_pago_sabado.py
│   ├── agregar_columna_jornada_pago_sabado.py
│   ├── corregir_tabla_historica_jornada_pago_sabado.py
│   ├── crear_tabla_historica_completa.py
│   ├── forzar_reconocimiento_columna_historica.py
│   └── verificar_y_corregir_tabla_historica.py
├── data/               # Scripts de corrección de datos
│   ├── corregir_dobladas_existentes.py
│   ├── corregir_solicitud_110.py
│   ├── resetear_aprobaciones_110.py
│   ├── resetear_solicitud_108.py
│   ├── resetear_solicitud_111.py
│   └── verificar_solicitud_110.py
├── diagnostic/         # Scripts de diagnóstico
│   ├── diagnosticar_doblada_28_29.py
│   ├── diagnosticar_doblada_marco.py
│   └── diagnosticar_solicitud_111.py
└── maintenance/        # Scripts de mantenimiento
    ├── debug_sql_historico.py
    ├── limpiar_cache_turnos.py
    ├── test_alternancia_31_enero.py
    ├── test_crear_doblada_detalle.py
    ├── test_envio_correos.py
    └── verificar_columna_jornada_pago_sabado.py
```

---

### Fase 4: Mejoras Adicionales

#### 4.1 Crear README.md en scripts/

**Archivo:** `scripts/README.md`
```markdown
# Scripts del Proyecto

Este directorio contiene scripts de utilidad, pruebas, debugging y mantenimiento.

## Estructura

- `tests/` - Scripts de prueba temporales
- `debug/` - Scripts de debugging
- `utils/` - Scripts de utilidad general
- `migrations/` - Scripts relacionados con migraciones de BD
- `data/` - Scripts de corrección de datos
- `diagnostic/` - Scripts de diagnóstico
- `maintenance/` - Scripts de mantenimiento

## Uso

Los scripts deben ejecutarse desde la raíz del proyecto con el entorno virtual activado.
```

#### 4.2 Crear .gitignore para scripts temporales

**Agregar a `.gitignore`:**
```
# Scripts temporales (opcional, si no quieres versionarlos)
scripts/tests/
scripts/debug/
```

#### 4.3 Documentar estructura en docs/

**Crear:** `docs/ESTRUCTURA_PROYECTO.md` con la estructura final organizada.

---

## 📊 Resumen de Cambios

### Archivos a Mover

**De raíz a scripts/:**
- 8 archivos `test_*.py` → `scripts/tests/`
- 3 archivos `debug_*.py` → `scripts/debug/`
- 6 archivos de utilidad → `scripts/utils/`
- 1 archivo de documentación → `docs/deployment/`

**De management/commands a tests/:**
- 3 archivos `test_*.py` → `solicitudes/tests/`

**Reorganizar en scripts/:**
- 20+ archivos existentes en `scripts/` → categorizar en subcarpetas

### Archivos a Eliminar

- `tests.py` redundantes (si están vacíos o solo importan)

---

## ✅ Checklist de Ejecución

- [ ] Crear estructura de carpetas en `scripts/`
- [ ] Mover archivos de prueba de raíz a `scripts/tests/`
- [ ] Mover archivos de debug de raíz a `scripts/debug/`
- [ ] Mover archivos de utilidad de raíz a `scripts/utils/`
- [ ] Mover documentación a `docs/deployment/`
- [ ] Mover tests de management/commands a tests/
- [ ] Reorganizar scripts existentes en subcarpetas
- [ ] Eliminar tests.py redundantes
- [ ] Crear README.md en scripts/
- [ ] Actualizar .gitignore si es necesario
- [ ] Verificar que todos los imports sigan funcionando
- [ ] Actualizar documentación de estructura

---

## 🔍 Verificación Post-Reorganización

1. **Ejecutar tests**: Verificar que todos los tests siguen funcionando
2. **Verificar imports**: Asegurar que no hay imports rotos
3. **Revisar paths**: Verificar que los scripts siguen funcionando desde sus nuevas ubicaciones
4. **Actualizar documentación**: Actualizar cualquier referencia a rutas antiguas

---

**Fecha de creación**: 2026-01-XX  
**Versión**: 1.0




