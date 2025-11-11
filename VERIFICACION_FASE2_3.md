# VERIFICACIÓN FASE 2.3: Límite de Cambios por Explorador/Fecha

## Objetivo
Verificar que la validación de límite de cambios funciona correctamente, impidiendo que un explorador exceda el límite máximo de cambios aprobados para una fecha específica.

## Cambios Implementados

### 1. Método `contar_cambios_explorador_fecha`
**Archivo:** `AppTurnosExplora/solicitudes/services/solicitud_service.py` (líneas 686-721)

**Funcionalidad:**
- Cuenta el número de solicitudes aprobadas donde el explorador participa (como solicitante o receptor) para una fecha específica
- Usa `Q` para buscar en ambos roles (solicitante o receptor)
- Retorna el conteo total de cambios aprobados

**Código:**
```python
@staticmethod
def contar_cambios_explorador_fecha(explorador_id: int, fecha) -> int:
    # Convierte fecha a objeto date si es string
    # Cuenta solicitudes aprobadas donde explorador es solicitante o receptor
    # Retorna el conteo
```

### 2. Validación de Límite en `aplicar_cambios`
**Archivo:** `AppTurnosExplora/solicitudes/services/strategies/cambio_turno_strategy.py` (líneas 150-201)

**Funcionalidad:**
- Verifica el límite de cambios ANTES de aplicar los cambios
- Límite configurable: `LIMITE_CAMBIOS_POR_FECHA = 2` (por defecto)
- Valida tanto para el solicitante como para el receptor
- Si alguno excede el límite, retorna error con mensaje descriptivo
- Registra logs de advertencia cuando se excede el límite

**Flujo:**
1. Obtener conteo de cambios aprobados para el solicitante
2. Si `cambios_solicitante >= LIMITE_CAMBIOS_POR_FECHA` → Error
3. Obtener conteo de cambios aprobados para el receptor
4. Si `cambios_receptor >= LIMITE_CAMBIOS_POR_FECHA` → Error
5. Si ambos están dentro del límite → Continuar con la aplicación de cambios

## Casos de Prueba

### Caso 1: Primer Cambio (Dentro del Límite)
**Escenario:**
- Explorador A tiene 0 cambios aprobados para fecha X
- Se intenta aprobar solicitud A→B para fecha X

**Resultado Esperado:**
- ✅ Validación pasa (0 < 2)
- ✅ Cambio se aplica correctamente

### Caso 2: Segundo Cambio (Dentro del Límite)
**Escenario:**
- Explorador A tiene 1 cambio aprobado para fecha X
- Se intenta aprobar solicitud A→C para fecha X

**Resultado Esperado:**
- ✅ Validación pasa (1 < 2)
- ✅ Cambio se aplica correctamente

### Caso 3: Tercer Cambio (Excede el Límite)
**Escenario:**
- Explorador A tiene 2 cambios aprobados para fecha X
- Se intenta aprobar solicitud A→D para fecha X

**Resultado Esperado:**
- ❌ Validación falla (2 >= 2)
- ❌ Error: "Se ha alcanzado el límite de cambios para esta fecha..."
- ❌ Cambio NO se aplica

### Caso 4: Límite en Receptor
**Escenario:**
- Explorador B tiene 2 cambios aprobados para fecha X
- Se intenta aprobar solicitud A→B para fecha X

**Resultado Esperado:**
- ❌ Validación falla para el receptor (2 >= 2)
- ❌ Error: "Se ha alcanzado el límite de cambios para esta fecha..."
- ❌ Cambio NO se aplica

### Caso 5: Cambios en Fechas Diferentes
**Escenario:**
- Explorador A tiene 2 cambios aprobados para fecha X
- Se intenta aprobar solicitud A→B para fecha Y (diferente)

**Resultado Esperado:**
- ✅ Validación pasa (los cambios de fecha X no cuentan para fecha Y)
- ✅ Cambio se aplica correctamente

## Verificación Manual

### Paso 1: Verificar Método de Conteo
```python
from solicitudes.services.solicitud_service import SolicitudService
from datetime import date

# Contar cambios para un explorador en una fecha
count = SolicitudService.contar_cambios_explorador_fecha(
    explorador_id=1,
    fecha=date(2024, 11, 20)
)
print(f"Cambios aprobados: {count}")
```

### Paso 2: Crear Solicitudes de Prueba
1. Crear solicitud A→B para fecha X → Aprobar
2. Crear solicitud A→C para fecha X → Aprobar
3. Crear solicitud A→D para fecha X → Intentar aprobar

### Paso 3: Verificar Logs
Revisar logs para mensajes:
- `"FASE 2.3: Validación de límite exitosa"` cuando pasa
- `"FASE 2.3: Límite de cambios excedido"` cuando falla

### Paso 4: Verificar Mensaje de Error
Cuando se excede el límite, el mensaje debe incluir:
- Nombre del explorador
- Número de cambios aprobados
- Fecha del cambio
- Límite máximo

## Notas Importantes

1. **Límite Configurable:** El límite está definido como constante `LIMITE_CAMBIOS_POR_FECHA = 2` en `aplicar_cambios`. Se puede modificar según necesidades del negocio.

2. **Conteo Incluye Ambos Roles:** El método cuenta cambios donde el explorador es solicitante O receptor, ya que ambos roles representan un cambio de turno para ese explorador.

3. **Validación Temprana:** La validación se realiza ANTES de aplicar los cambios, dentro de la transacción atómica, garantizando que no se apliquen cambios que excedan el límite.

4. **Logs Detallados:** Se registran logs informativos cuando la validación pasa y logs de advertencia cuando se excede el límite, facilitando el debugging.

## Estado
✅ **IMPLEMENTADO** - Pendiente de pruebas manuales

