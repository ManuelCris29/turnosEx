# Configuración del Skill Django Expert

## ✅ Configuración Automática Activada

El skill `django-expert` está configurado para activarse **automáticamente** en todas las consultas relacionadas con Django en este proyecto.

## 📁 Archivos de Configuración

### `.cursorrules`
Archivo en la raíz del proyecto (`AppTurnosExplora/.cursorrules`) que instruye a Cursor para usar automáticamente el skill `django-expert`.

**Ubicación del skill**: `.cursor/skills/django-expert/SKILL.md`

## 🎯 ¿Cuándo se Activa Automáticamente?

El skill se activa automáticamente cuando trabajas con:

### 1. Modelos y ORM
- Crear o modificar modelos Django
- Optimizar queries (select_related, prefetch_related)
- Resolver problemas N+1
- Trabajar con migraciones

### 2. Vistas y APIs
- Desarrollar vistas (FBV, CBV)
- Crear endpoints con DRF
- Implementar serializers
- Configurar routers y viewsets

### 3. Base de Datos
- Optimizar consultas
- Crear índices
- Configurar relaciones (ForeignKey, ManyToMany)

### 4. Autenticación y Seguridad
- Implementar autenticación
- Crear permisos personalizados
- Aplicar medidas de seguridad (CSRF, XSS)

### 5. Testing
- Escribir tests unitarios
- Crear fixtures y factories
- Tests de integración

### 6. Performance
- Optimizar rendimiento
- Implementar caching
- Profiling de queries

### 7. Deployment
- Configurar settings de producción
- Configurar HTTPS/SSL
- Optimizar para producción

## 📚 Recursos del Skill

El skill incluye documentación de referencia en `.cursor/skills/django-expert/references/`:

- `models-and-orm.md` - Modelos y ORM
- `views-and-urls.md` - Vistas y URLs
- `drf-guidelines.md` - Django REST Framework
- `testing-strategies.md` - Estrategias de testing
- `security-checklist.md` - Checklist de seguridad
- `performance-optimization.md` - Optimización de rendimiento
- `production-deployment.md` - Deployment a producción
- `examples.md` - Ejemplos prácticos

## 🔧 Verificación

Para verificar que el skill está activo:

1. Abre Cursor en este proyecto
2. Haz una pregunta relacionada con Django (ej: "¿Cómo optimizo esta query?")
3. El asistente debería usar automáticamente las mejores prácticas de Django del skill

## 📝 Notas

- El archivo `.cursorrules` está en la raíz del proyecto
- No es necesario activar manualmente el skill
- El skill se aplica automáticamente a todas las consultas Django
- Las referencias del skill se cargan según el contexto de la tarea

## 🚀 Uso

Simplemente trabaja normalmente en el proyecto. Cuando hagas preguntas o solicites ayuda con código Django, el skill se activará automáticamente y te proporcionará:

- Mejores prácticas de Django
- Patrones recomendados
- Optimizaciones sugeridas
- Soluciones siguiendo estándares de Django

---

**Última actualización**: Configuración automática activada para todas las consultas Django en AppTurnosExplora.


