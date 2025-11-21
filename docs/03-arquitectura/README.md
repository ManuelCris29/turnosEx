# 03. Arquitectura

## 📋 Contenido

Esta sección describe la arquitectura del proyecto después de la refactorización, incluyendo principios SOLID aplicados y estructura de servicios.

---

## 📚 Documentos Disponibles

### 1. [Arquitectura General](./arquitectura-general.md)
**Contenido**: Descripción completa de la arquitectura del proyecto
- Estructura del proyecto
- Organización por capas
- Servicios por dominio
- Dependencias entre módulos
- Patrones de diseño utilizados

**Leer primero** para entender la estructura general.

---

### 2. [Principios SOLID](./principios-solid.md)
**Contenido**: Análisis detallado de la aplicación de principios SOLID
- Single Responsibility Principle (SRP)
- Open/Closed Principle (OCP)
- Liskov Substitution Principle (LSP)
- Interface Segregation Principle (ISP)
- Dependency Inversion Principle (DIP)

**Leer** para entender cómo se aplicaron los principios.

---

## 🏗️ Arquitectura del Proyecto

### Estructura por Capas

```
Views (Presentación)
    ↓
Services (Lógica de Negocio)
    ↓
Models (Datos)
    ↓
Core Utils (Utilidades)
```

### Reglas de Dependencias:

1. **Views** solo llaman a **Services**
2. **Services** usan **Models** y **Core Utils**
3. **Core Utils** no depende de apps específicas
4. **Models** no depende de nada (excepto Django)

---

## 🎯 Servicios por Dominio

### Dominio: Solicitudes
- `SolicitudService` - Core (creación)
- `SolicitudFactory` - Factory Pattern
- `SolicitudValidator` - Validaciones
- `SolicitudConsultaService` - Consultas
- `SolicitudAprobacionService` - Aprobación/rechazo
- `EmpleadoDisponibilidadService` - Búsqueda de empleados
- `NotificacionService` - Notificaciones

### Dominio: Turnos
- `TurnoService` - Gestión de turnos
- `JornadaService` - Gestión de jornadas
- `TurnoContextService` - Contexto para views

### Dominio: Empleados
- `EmpleadoService` - Gestión de empleados

### Dominio: Core (Compartido)
- `CacheService` - Gestión de cache
- `JsonResponses` - Helpers JSON
- `AdminRequiredMixin` - Mixin de permisos
- `DateUtils` - Utilidades de fechas
- `JornadaUtils` - Utilidades de jornadas

---

## 🔄 Patrones de Diseño

### Strategy Pattern
- **Uso**: Diferentes tipos de solicitudes (CT, CT Permanente, Doblada, D FDS)
- **Implementación**: `SolicitudStrategy` base con estrategias específicas
- **Beneficio**: Extensible sin modificar código existente

### Factory Pattern
- **Uso**: Creación de estrategias según tipo de solicitud
- **Implementación**: `SolicitudFactory`
- **Beneficio**: Desacoplamiento de creación

### Service Layer Pattern
- **Uso**: Separación de lógica de negocio de views
- **Implementación**: Servicios por dominio
- **Beneficio**: Reutilización y testabilidad

---

## 📊 Principios SOLID Aplicados

### ✅ Single Responsibility Principle (SRP)
- Cada servicio tiene una única responsabilidad
- Views solo orquestan servicios
- Utilidades centralizadas

### ✅ Open/Closed Principle (OCP)
- Strategy Pattern permite extensión sin modificación
- Factory Pattern permite agregar nuevos tipos

### ✅ Liskov Substitution Principle (LSP)
- Estrategias son intercambiables
- Todas cumplen el contrato base

### ✅ Interface Segregation Principle (ISP)
- Servicios pequeños con interfaces específicas
- No hay servicios con métodos no usados

### ⚠️ Dependency Inversion Principle (DIP)
- Parcialmente cumplido (aceptable para Python)
- Interfaces creadas para documentación

---

## 🔗 Dependencias entre Módulos

```
Views → Services → Models
         ↓
      Core Utils
```

### Ejemplo de Flujo:

```
SolicitudesView
    ↓
SolicitudContextService
    ↓
SolicitudConsultaService
    ↓
SolicitudCambio (Model)
```

---

## ➡️ Próximos Pasos

Después de entender la arquitectura:

1. **Consulta las guías**: [04. Guías](../04-guias/README.md)
2. **Revisa referencias**: [05. Referencia](../05-referencia/README.md)

---

## 📝 Notas Importantes

- **Separación de responsabilidades**: Cada capa tiene su propósito claro
- **Reutilización**: Servicios pequeños y reutilizables
- **Testabilidad**: Servicios aislados fáciles de testear
- **Extensibilidad**: Fácil agregar nuevas funcionalidades


