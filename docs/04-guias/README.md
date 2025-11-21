# 04. Guías

## 📋 Contenido

Esta sección contiene guías prácticas para trabajar con el proyecto.

---

## 📚 Documentos Disponibles

### [Guía de Testing](./testing.md)
**Contenido**: Guía completa para trabajar con tests en el proyecto
- Estructura de tests
- Cómo ejecutar tests
- Cómo agregar nuevos tests
- Fixtures compartidas
- Convenciones

**Leer** para entender cómo trabajar con tests.

---

### [Guía de Festivos y Calendarios](./festivos/festivos.md)
**Contenido**: Documentación completa sobre el manejo de festivos
- Cómo funcionan los calendarios festivos
- Explicación de festivos móviles y fijos
- Corrección Ley Emiliani
- Implementación y refactorización

---

### [Guía de Google Apps Script e Integraciones](./integraciones/google-apps-script.md)
**Contenido**: Documentación de integraciones con Google Apps Script
- Implementación de beneficios
- Manejo de iframes con autenticación
- Soluciones a problemas de X-Frame-Options

---

### [Guía: Agregar Nuevo Tipo de Solicitud](./guia-agregar-nuevo-tipo-solicitud.md)
**Contenido**: Guía paso a paso para agregar nuevos tipos de solicitud
- Creación de estrategias
- Registro automático
- Validaciones requeridas

---

### [Manual de GitHub](./manual-github.md)
**Contenido**: Guía completa para gestionar código en GitHub
- Configuración inicial
- Flujo de trabajo diario
- Comandos esenciales
- Buenas prácticas

---

### [Instrucciones de Optimización](./instrucciones-optimizacion.md)
**Contenido**: Guía de optimizaciones de rendimiento

---

## 🧪 Testing

### Estructura de Tests

```
{app}/
  tests/
    __init__.py
    conftest.py          # Fixtures específicas de la app
    test_models.py       # Tests de modelos
    test_services.py     # Tests de servicios
    test_views.py        # Tests de vistas
    test_*.py           # Tests específicos

tests/                  # Tests globales
  conftest.py          # Fixtures globales compartidas
  integration/         # Tests de integración end-to-end
    test_*.py
```

### Ejecutar Tests

```bash
# Con Django TestCase
python manage.py test

# Con pytest (recomendado)
pytest

# Con cobertura
pytest --cov=AppTurnosExplora --cov-report=html
```

### Agregar Nuevos Tests

1. Crear archivo `test_*.py` en la app correspondiente
2. Usar fixtures de `conftest.py` cuando sea posible
3. Seguir convenciones de nombres
4. Mantener tests pequeños y enfocados

---

## 💻 Desarrollo

### Convenciones de Código

1. **Servicios**: Un servicio por responsabilidad
2. **Views**: Solo orquestación, lógica en servicios
3. **Nombres**: Claros y descriptivos
4. **Imports**: Organizados y agrupados

### Agregar Nueva Funcionalidad

1. **Modelo**: Crear en `models.py`
2. **Servicio**: Crear en `services/`
3. **View**: Crear en `views.py`
4. **Tests**: Crear en `tests/`

### Agregar Nuevo Tipo de Solicitud

1. Crear estrategia en `solicitudes/services/strategies/`
2. Registrar en `SolicitudFactory` (automático si sigue convención)
3. Agregar validaciones en `SolicitudValidator`
4. Crear tests en `tests/test_strategies.py`

---

## 🔧 Utilidades Disponibles

### Core Utils

- `DateUtils.parse_date()` - Parsear fechas
- `DateUtils.format_date()` - Formatear fechas
- `JornadaUtils.calcular_jornada_dia()` - Calcular jornada
- `json_ok()` / `json_error()` - Respuestas JSON

### Core Services

- `CacheService.get_or_set()` - Cache con TTL
- `AdminRequiredMixin` - Mixin de permisos

---

## 📝 Documentación

### Documentar Código

- Usar docstrings en funciones y clases
- Documentar parámetros y retornos
- Incluir ejemplos cuando sea útil

### Actualizar Documentación

- Actualizar este README cuando agregues nuevas guías
- Mantener ejemplos actualizados
- Documentar decisiones importantes

---

## ➡️ Próximos Pasos

Después de leer las guías:

1. **Revisa referencias**: [05. Referencia](../05-referencia/README.md)
2. **Consulta arquitectura**: [03. Arquitectura](../03-arquitectura/README.md)

---

## 📝 Notas Importantes

- **Tests primero**: Escribe tests antes de implementar
- **Documentación**: Mantén la documentación actualizada
- **Convenciones**: Sigue las convenciones establecidas
- **Reutilización**: Usa servicios y utilidades existentes

