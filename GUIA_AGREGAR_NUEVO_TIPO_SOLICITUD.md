# GUÍA: Cómo Agregar un Nuevo Tipo de Solicitud de Cambio

## 📋 Resumen

Esta guía explica paso a paso cómo agregar un nuevo tipo de solicitud de cambio al sistema. El sistema está diseñado para ser **escalable** y **dinámico**, permitiendo agregar nuevos tipos sin modificar código existente.

**IMPORTANTE:** Después de implementar esta guía, el sistema registrará automáticamente el nuevo tipo desde la base de datos. **NO es necesario modificar `views.py`** (ese código ya fue eliminado).

---

## 🎯 Pasos para Agregar un Nuevo Tipo

### **PASO 1: Crear la Clase de Estrategia**

**Ubicación:** `AppTurnosExplora/solicitudes/services/strategies/`

**Archivo a crear:** `nuevo_tipo_strategy.py` (ejemplo: `cambio_especial_strategy.py`)

**Estructura básica:**

```python
"""
Estrategia para [Nombre del Tipo de Solicitud]
"""
from .base_strategy import SolicitudStrategy
from solicitudes.models import SolicitudCambio
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class NuevoTipoStrategy(SolicitudStrategy):
    """
    Estrategia para manejar solicitudes de tipo [Nombre del Tipo]
    """
    
    def __init__(self):
        """
        Inicializa la estrategia con el código del tipo.
        """
        super().__init__("NUEVO TIPO")  # Usar el código normalizado
    
    def validar_solicitud(self, datos: Dict[str, Any]) -> tuple:
        """
        Valida los datos de la solicitud.
        
        Args:
            datos: Diccionario con los datos de la solicitud
            
        Returns:
            Tuple (es_valido: bool, mensaje: str)
        """
        # Implementar validaciones específicas del tipo
        # Ejemplo:
        if not datos.get('campo_requerido'):
            return False, "El campo 'campo_requerido' es obligatorio"
        
        return True, "Validación exitosa"
    
    def crear_solicitud(self, datos: Dict[str, Any]) -> tuple:
        """
        Crea una nueva solicitud.
        
        Args:
            datos: Diccionario con los datos de la solicitud
            
        Returns:
            Tuple (solicitud: SolicitudCambio, mensaje: str)
        """
        from solicitudes.services.solicitud_service import SolicitudService
        
        # Implementar lógica de creación específica
        solicitud = SolicitudService.crear_solicitud_cambio(
            explorador_solicitante=datos['explorador_solicitante'],
            explorador_receptor=datos['explorador_receptor'],
            tipo_cambio=datos['tipo_cambio'],
            fecha_cambio_turno=datos.get('fecha_cambio_turno'),
            comentario=datos.get('comentario')
        )
        
        return solicitud, "Solicitud creada exitosamente"
    
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> tuple:
        """
        Aplica los cambios cuando la solicitud es aprobada.
        
        Args:
            solicitud: Instancia de SolicitudCambio aprobada
            
        Returns:
            Tuple (exito: bool, mensaje: str)
        """
        # Implementar lógica específica para aplicar cambios
        # Ejemplo: crear turnos, actualizar asignaciones, etc.
        
        try:
            # Tu lógica aquí
            return True, "Cambios aplicados exitosamente"
        except Exception as e:
            logger.error(f"Error aplicando cambios: {e}")
            return False, f"Error al aplicar cambios: {str(e)}"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual) -> List:
        """
        Obtiene la lista de empleados disponibles para este tipo de solicitud.
        
        Args:
            fecha: Fecha en formato YYYY-MM-DD
            usuario_actual: Instancia de Empleado del usuario actual
            
        Returns:
            Lista de empleados disponibles
        """
        from solicitudes.services.solicitud_service import SolicitudService
        
        # Implementar lógica específica para obtener empleados disponibles
        # Ejemplo: filtrar por jornada contraria, disponibilidad, etc.
        
        return SolicitudService.get_empleados_disponibles(
            fecha=fecha,
            usuario_actual=usuario_actual,
            solo_jornada_contraria=True  # Ajustar según necesidades
        )
    
    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        """
        Obtiene información del turno de un explorador para una fecha.
        
        Args:
            explorador_id: ID del empleado
            fecha: Fecha en formato YYYY-MM-DD
            
        Returns:
            Diccionario con información del turno
        """
        from solicitudes.services.solicitud_service import SolicitudService
        
        return SolicitudService.get_turno_explorador(explorador_id, fecha)
```

**Nota:** Puedes copiar `cambio_turno_strategy.py` como base y modificarlo según tus necesidades.

---

### **PASO 2: Exportar la Estrategia**

**Archivo:** `AppTurnosExplora/solicitudes/services/strategies/__init__.py`

**Agregar la importación y al __all__:**

```python
from .base_strategy import SolicitudStrategy
from .cambio_turno_strategy import CambioTurnoStrategy
from .doblada_strategy import DobladaStrategy
from .ct_permanente_strategy import CTPermanenteStrategy
from .d_fds_strategy import DFDSStrategy
from .nuevo_tipo_strategy import NuevoTipoStrategy  # Agregar esta línea

__all__ = [
    'SolicitudStrategy',
    'CambioTurnoStrategy', 
    'DobladaStrategy',
    'CTPermanenteStrategy',
    'DFDSStrategy',
    'NuevoTipoStrategy',  # Agregar esta línea
]
```

---

### **PASO 3: Agregar al Mapeo de Códigos**

**Archivo:** `AppTurnosExplora/solicitudes/services/solicitud_factory.py`

**Función a modificar:** `_find_strategy_by_code()` (líneas ~388-416)

**Agregar al mapeo:**

```python
def _find_strategy_by_code(codigo: str):
    """
    Find strategy class by normalized code.
    """
    try:
        from .strategies import (
            CambioTurnoStrategy, DobladaStrategy, 
            CTPermanenteStrategy, DFDSStrategy,
            NuevoTipoStrategy  # Agregar importación
        )
        
        # Mapping of codes to strategy classes
        code_mapping = {
            'CT': CambioTurnoStrategy,
            'DOBLADA': DobladaStrategy,
            'CT PERMANENTE': CTPermanenteStrategy,
            'CAMBIO PERMANENTE': CTPermanenteStrategy,
            'D FDS': DFDSStrategy,
            'DIA FIN DE SEMANA': DFDSStrategy,
            'NUEVO TIPO': NuevoTipoStrategy,  # Agregar mapeo
            'NUEVO_TIPO': NuevoTipoStrategy,  # Variante con guión bajo
        }
        
        return code_mapping.get(codigo)
    except ImportError:
        return None
```

**También agregar al registro manual (líneas ~358-364):**

```python
# Step 1: Manual registration (backward compatibility)
from .strategies import (
    CambioTurnoStrategy, DobladaStrategy, 
    CTPermanenteStrategy, DFDSStrategy,
    NuevoTipoStrategy  # Agregar importación
)

SolicitudFactory.register_strategy("CT", CambioTurnoStrategy)
SolicitudFactory.register_strategy("DOBLADA", DobladaStrategy)
SolicitudFactory.register_strategy("CT PERMANENTE", CTPermanenteStrategy)
SolicitudFactory.register_strategy("D FDS", DFDSStrategy)
SolicitudFactory.register_strategy("NUEVO TIPO", NuevoTipoStrategy)  # Agregar registro
```

---

### **PASO 4: Agregar Normalización (Opcional pero Recomendado)**

**Archivo:** `AppTurnosExplora/solicitudes/services/solicitud_factory.py`

**Función a modificar:** `normalize_name()` (líneas ~72-82)

**Agregar al diccionario de mapeos:**

```python
mappings = {
    'CT PERMANENTE': 'CT PERMANENTE',
    'CAMBIO PERMANENTE': 'CT PERMANENTE',
    'CAMBIO TURNO': 'CT',
    'CAMBIO': 'CT',
    'CT': 'CT',
    'DOBLADA': 'DOBLADA',
    'D FDS': 'D FDS',
    'DIA FIN DE SEMANA': 'D FDS',
    'NUEVO TIPO': 'NUEVO TIPO',  # Agregar mapeo
    'NUEVO_TIPO': 'NUEVO TIPO',  # Variante
}
```

---

### **PASO 5: Crear el Tipo en la Base de Datos**

**Opción A: Desde la Interfaz Web (Recomendado)**

1. Ir a: `http://127.0.0.1:8000/solicitudes/tipos-solicitud/`
2. Clic en "Nuevo Tipo de Solicitud"
3. Llenar el formulario:
   - **Nombre:** "Nuevo Tipo" (o el nombre que desees)
   - **Código de Estrategia:** "NUEVO TIPO" (debe coincidir con el código en el mapeo)
   - **Activo:** ✓ (marcado)
   - **Genera deuda de horas:** (según corresponda)
4. Guardar

**Opción B: Desde el Shell de Django**

```python
from solicitudes.models import TipoSolicitudCambio

tipo = TipoSolicitudCambio.objects.create(
    nombre="Nuevo Tipo",
    codigo_estrategia="NUEVO TIPO",
    activo=True,
    genera_deuda=False
)
```

---

### **PASO 6: Verificar que Funciona**

**Comando de prueba:**

```bash
python manage.py test_factory
```

**O desde el shell:**

```python
from solicitudes.models import TipoSolicitudCambio
from solicitudes.services.solicitud_factory import SolicitudFactory

tipo = TipoSolicitudCambio.objects.get(nombre="Nuevo Tipo")
strategy = SolicitudFactory.get_strategy(tipo)
print(f"Estrategia encontrada: {strategy.__class__.__name__}")
# Debe imprimir: NuevoTipoStrategy
```

---

## 📝 Ejemplo Completo: Agregar "CAMBIO ESPECIAL"

### 1. Crear `cambio_especial_strategy.py`:

```python
from .base_strategy import SolicitudStrategy
from solicitudes.models import SolicitudCambio
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)


class CambioEspecialStrategy(SolicitudStrategy):
    """Estrategia para Cambio Especial"""
    
    def validar_solicitud(self, datos: Dict[str, Any]) -> tuple:
        # Validaciones específicas
        return True, "Validación exitosa"
    
    def crear_solicitud(self, datos: Dict[str, Any]) -> tuple:
        from solicitudes.services.solicitud_service import SolicitudService
        solicitud = SolicitudService.crear_solicitud_cambio(...)
        return solicitud, "Solicitud creada"
    
    def aplicar_cambios(self, solicitud: SolicitudCambio) -> tuple:
        # Lógica específica
        return True, "Cambios aplicados"
    
    def get_empleados_disponibles(self, fecha: str, usuario_actual) -> List:
        from solicitudes.services.solicitud_service import SolicitudService
        return SolicitudService.get_empleados_disponibles(fecha, usuario_actual)
    
    def get_turno_explorador(self, explorador_id: int, fecha: str) -> Dict[str, Any]:
        from solicitudes.services.solicitud_service import SolicitudService
        return SolicitudService.get_turno_explorador(explorador_id, fecha)
```

### 2. Actualizar `__init__.py`:

```python
from .cambio_especial_strategy import CambioEspecialStrategy
```

### 3. Actualizar `solicitud_factory.py`:

```python
# En _find_strategy_by_code():
from .strategies import (
    ..., CambioEspecialStrategy
)

code_mapping = {
    ...,
    'CAMBIO ESPECIAL': CambioEspecialStrategy,
    'CE': CambioEspecialStrategy,  # Abreviación
}

# En _auto_register_strategies():
from .strategies import (
    ..., CambioEspecialStrategy
)

SolicitudFactory.register_strategy("CAMBIO ESPECIAL", CambioEspecialStrategy)
```

### 4. Crear en BD:

- **Nombre:** "Cambio Especial"
- **Código de Estrategia:** "CAMBIO ESPECIAL" o "CE"

---

## ✅ Checklist Final

Antes de considerar completado, verificar:

- [ ] Clase de estrategia creada e implementa todos los métodos requeridos
- [ ] Estrategia exportada en `__init__.py`
- [ ] Agregada al mapeo en `_find_strategy_by_code()`
- [ ] Agregada al registro manual en `_auto_register_strategies()`
- [ ] Agregada normalización en `normalize_name()` (opcional)
- [ ] Tipo creado en BD con `codigo_estrategia` correcto
- [ ] Pruebas realizadas y funcionando
- [ ] Logs verificados (no hay warnings sobre estrategia no encontrada)

---

## 🔍 Troubleshooting

### Problema: "No se encontró estrategia para el tipo"

**Solución:**
1. Verificar que el `codigo_estrategia` en BD coincide con el mapeo
2. Verificar que la estrategia está registrada en `_auto_register_strategies()`
3. Verificar que está en el mapeo de `_find_strategy_by_code()`
4. Reiniciar el servidor Django (para que se ejecute el auto-registro)

### Problema: "ModuleNotFoundError: No module named 'strategies.nuevo_tipo_strategy'"

**Solución:**
1. Verificar que el archivo existe en `strategies/`
2. Verificar que está exportado en `__init__.py`
3. Verificar que el nombre de la clase coincide

### Problema: La estrategia no se registra automáticamente

**Solución:**
1. Verificar que el tipo en BD tiene `activo=True`
2. Verificar que `codigo_estrategia` está correcto
3. Verificar que la normalización funciona: `SolicitudFactory.normalize_name("TU_CODIGO")`

---

## 📚 Archivos a Modificar (Resumen)

1. ✅ `solicitudes/services/strategies/nuevo_tipo_strategy.py` - **CREAR**
2. ✅ `solicitudes/services/strategies/__init__.py` - **MODIFICAR** (agregar import)
3. ✅ `solicitudes/services/solicitud_factory.py` - **MODIFICAR** (2 lugares)
4. ✅ Base de datos - **CREAR** tipo con código correcto

**NO es necesario modificar:**
- ❌ `views.py` (ya no tiene código hardcodeado)
- ❌ Templates (funcionan automáticamente)
- ❌ URLs (funcionan automáticamente)

---

## 🎯 Ventajas del Sistema Actual

1. **Escalable:** Agregar nuevos tipos sin tocar código existente
2. **Dinámico:** El sistema registra automáticamente desde BD
3. **Flexible:** Permite override manual con `codigo_estrategia`
4. **Mantenible:** Código centralizado y organizado
5. **Seguro:** Fallback garantiza que siempre hay estrategia

---

**Última actualización:** 2025-11-11
**Versión del sistema:** 2.0 (con registro dinámico)

