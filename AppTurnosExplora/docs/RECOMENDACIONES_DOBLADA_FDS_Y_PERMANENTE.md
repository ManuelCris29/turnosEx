# Recomendaciones Arquitectónicas: Doblada Fines de Semana y Doblada Permanente

## 📋 Resumen Ejecutivo

Este documento presenta recomendaciones arquitectónicas para implementar dos nuevos tipos de dobladas:
1. **Doblada Fines de Semana (D FDS)**: Intercambio de sábado por domingo dentro del mismo fin de semana
2. **Doblada Permanente**: Dobladas recurrentes en días específicos de la semana durante un rango de fechas

**Principio clave**: Reutilizar al máximo la infraestructura existente (`CambioPermanenteDetalle`, `DobladaDetalle`, `DeudaCorporativa`) para minimizar complejidad y tiempo de desarrollo.

---

## 🏗️ Análisis de Infraestructura Existente

### ✅ Componentes Reutilizables

#### 1. **Modelo `DobladaDetalle`** (Actual)
```python
# Ya existe y funciona bien para dobladas simples
- solicitud: OneToOne(SolicitudCambio)
- fecha_pago: Date (obligatorio)
- tipo_cesion: CharField (cesion_completa, cesion_parcial_am, cesion_parcial_pm)
- jornada_cedida: CharField (AM/PM)
- minutos_deuda: Integer (default=30)
- empleado_receptor: ForeignKey(Empleado)
```

**✅ Ventajas**:
- Estructura base sólida
- Ya maneja deuda corporativa (30 min)
- Relación OneToOne con SolicitudCambio

**⚠️ Limitaciones actuales**:
- Solo maneja una fecha de cesión (`fecha_cambio_turno` en `SolicitudCambio`)
- No soporta rangos de fechas
- No diferencia tipos de dobladas (simple, FDS, permanente)

#### 2. **Modelo `CambioPermanenteDetalle` + `CambioPermanenteDia`** (Reutilizable)
```python
# Estructura perfecta para doblada permanente
CambioPermanenteDetalle:
  - solicitud: OneToOne(SolicitudCambio)
  - fecha_inicio: Date
  - fecha_fin: Date (nullable)

CambioPermanenteDia:
  - cambio_permanente: ForeignKey(CambioPermanenteDetalle)
  - tipo: CharField ('fecha_especifica' | 'dia_semana')
  - fecha_especifica: Date (nullable)
  - dia_semana: Integer (0-6, nullable)
```

**✅ Ventajas**:
- Ya maneja rangos de fechas
- Soporta días específicos o días de semana
- Validaciones de lunes-viernes ya implementadas
- Helper `calcular_fechas_aplicables_ct_permanente()` reutilizable

**⚠️ Adaptación necesaria**:
- Actualmente restringe sábados/domingos (línea 231-234)
- Para doblada permanente, necesitamos permitir sábados/domingos según reglas de negocio

#### 3. **Sistema de Deuda Corporativa** (Completo)
```python
DeudaCorporativa:
  - explorador: ForeignKey(Empleado)
  - minutos: Integer (default=30)
  - fecha_doblada: Date
  - estado: CharField ('activa' | 'cancelada')
  - solicitud_origen: ForeignKey(SolicitudCambio, nullable)
```

**✅ Ventajas**:
- Ya acumula minutos permanentemente
- Integrado con PDH para supervisores
- Servicio `DeudaCorporativaService` completo

#### 4. **Sistema de Deuda entre Exploradores** (Parcial)
```python
DeudaExplorador:
  - deudor: ForeignKey(Empleado)
  - acreedor: ForeignKey(Empleado)
  - fecha_pago_pactada: Date
  - estado: CharField ('pendiente' | 'pagada' | 'cancelada')
```

**✅ Ventajas**:
- Estructura base correcta
- Maneja estado de pago

**⚠️ Limitaciones**:
- No tiene campo `fecha_limite_pago` (30 días)
- No tiene sistema de multas

---

## 🎯 Recomendaciones por Tipo de Doblada

### 1. DOBLADA FINES DE SEMANA (D FDS)

#### 1.1 Modelo de Datos

**Opción A: Extender `DobladaDetalle` (RECOMENDADO)**
```python
# Agregar campos a DobladaDetalle existente
class DobladaDetalle(models.Model):
    # ... campos existentes ...
    
    # NUEVO: Tipo de doblada
    tipo_doblada = models.CharField(
        max_length=20,
        choices=[
            ('simple', 'Doblada Simple'),  # Actual
            ('fines_semana', 'Doblada Fines de Semana'),  # Nuevo
            ('permanente', 'Doblada Permanente'),  # Nuevo
        ],
        default='simple'
    )
    
    # NUEVO: Para D FDS - fecha del domingo (receptor trabaja sábado+domingo)
    fecha_domingo = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha del domingo (solo para D FDS)'
    )
    
    # NUEVO: Para D FDS - fecha de pago (fin de semana completo)
    fecha_pago_fin_semana = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha del sábado del fin de semana de pago (solo para D FDS)'
    )
```

**Ventajas**:
- ✅ Reutiliza toda la estructura existente
- ✅ No requiere nueva tabla
- ✅ Compatible con dobladas simples actuales
- ✅ Migración simple (agregar campos nullable)

**Desventajas**:
- ⚠️ `DobladaDetalle` se vuelve más complejo
- ⚠️ Validaciones condicionales según `tipo_doblada`

#### 1.2 Lógica de Negocio

**Flujo D FDS**:
1. **Solicitud**: Solicitante trabaja sábado, no puede asistir
2. **Receptor**: Trabaja sábado (su jornada) + domingo (jornada del solicitante) = doblada completa fin de semana
3. **Pago**: Solicitante debe devolver el favor trabajando un fin de semana completo (sábado+domingo) cuando el receptor lo solicite

**Validaciones específicas**:
```python
def validar_doblada_fds(datos):
    fecha_sabado = datos['fecha_cambio_turno']  # Sábado original
    fecha_domingo = datos['fecha_domingo']  # Domingo del mismo fin de semana
    
    # Validar que fecha_domingo es el domingo siguiente al sábado
    assert fecha_domingo == fecha_sabado + timedelta(days=1)
    assert fecha_sabado.weekday() == 5  # Sábado
    assert fecha_domingo.weekday() == 6  # Domingo
    
    # Validar que receptor puede trabajar ambos días
    # (no tiene turnos asignados, no es festivo, etc.)
    
    # Validar que fecha_pago_fin_semana es un sábado futuro
    fecha_pago_sabado = datos['fecha_pago_fin_semana']
    assert fecha_pago_sabado.weekday() == 5
    assert fecha_pago_sabado > fecha_sabado
```

**Aplicación al aprobar**:
- **Fecha sábado**: Solicitante descansa, Receptor trabaja AM+PM (doblada)
- **Fecha domingo**: Solicitante descansa, Receptor trabaja AM+PM (doblada)
- **Deuda corporativa**: Receptor acumula 60 minutos (30 min × 2 días)
- **Deuda entre exploradores**: Solicitante debe a Receptor (fin de semana completo)

**Pago de deuda**:
- Receptor solicita que Solicitante trabaje un fin de semana completo
- **Fecha pago sábado**: Solicitante trabaja AM+PM, Receptor descansa
- **Fecha pago domingo**: Solicitante trabaja AM+PM, Receptor descansa
- **Deuda corporativa**: Solicitante acumula 60 minutos (30 min × 2 días)
- **Deuda entre exploradores**: Estado → 'pagada'

#### 1.3 Estrategia de Implementación

**Archivo**: `solicitudes/services/strategies/doblada_fds_strategy.py`

```python
class DobladaFDSStrategy(SolicitudStrategy):
    """
    Strategy para Doblada Fines de Semana.
    Reutiliza DobladaStrategy base pero con validaciones específicas.
    """
    
    def validar_solicitud(self, datos):
        # Validar que es fin de semana
        # Validar que receptor puede trabajar ambos días
        # Validar fecha_pago_fin_semana es sábado futuro
        pass
    
    def crear_solicitud(self, datos):
        # Crear SolicitudCambio
        # Crear DobladaDetalle con tipo_doblada='fines_semana'
        # Crear turnos para sábado y domingo
        pass
```

**Reutilización**:
- ✅ `DobladaAplicacionService` puede extenderse con método `aplicar_doblada_fds()`
- ✅ `DeudaCorporativaService` ya maneja acumulación (solo llamar 2 veces: 30 min × 2 días)

---

### 2. DOBLADA PERMANENTE

#### 2.1 Modelo de Datos

**Opción A: Reutilizar `CambioPermanenteDetalle` + Extender `DobladaDetalle` (RECOMENDADO)**

```python
# Extender DobladaDetalle
class DobladaDetalle(models.Model):
    # ... campos existentes ...
    tipo_doblada = models.CharField(...)  # Agregado arriba
    
    # NUEVO: Relación con CambioPermanenteDetalle (solo para doblada permanente)
    cambio_permanente = models.OneToOneField(
        CambioPermanenteDetalle,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='doblada_permanente',
        help_text='Solo para dobladas permanentes'
    )
    
    # NUEVO: Fecha límite para que receptor especifique días de pago
    fecha_limite_pago = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha límite para que receptor especifique días de pago mutuo'
    )
```

**Ventajas**:
- ✅ Reutiliza 100% la estructura de `CambioPermanenteDetalle` y `CambioPermanenteDia`
- ✅ Ya tiene lógica de rangos, días específicos, días de semana
- ✅ Helper `calcular_fechas_aplicables_ct_permanente()` reutilizable
- ✅ Validaciones de festivos/mantenimiento ya implementadas

**Adaptaciones necesarias**:
- ⚠️ Modificar `CambioPermanenteDia.save()` para permitir sábados/domingos cuando `tipo_doblada='permanente'`
- ⚠️ Crear helper `calcular_fechas_aplicables_doblada_permanente()` basado en el de CT permanente

#### 2.2 Lógica de Negocio

**Flujo Doblada Permanente**:
1. **Solicitud**: Solicitante no puede asistir días específicos de la semana (ej: todos los martes) durante un rango
2. **Receptor**: Acepta cubrir esos días (hace doblada completa AM+PM cada día)
3. **Acuerdo mutuo**: Receptor especifica días en que Solicitante debe doblarse (dentro de fecha límite)
4. **Aplicación**: Se aplican turnos semana tras semana hasta cumplir rango

**Validaciones específicas**:
```python
def validar_doblada_permanente(datos):
    fecha_inicio = datos['fecha_inicio']
    fecha_fin = datos['fecha_fin']
    dias_seleccionados = datos['dias_seleccionados']  # Similar a CT permanente
    
    # Validar rango de fechas
    assert fecha_fin > fecha_inicio
    
    # Validar días seleccionados (pueden ser sábados/domingos para doblada)
    # NO restringir a lunes-viernes como CT permanente
    
    # Validar que receptor puede trabajar en todos los días seleccionados
    # (no tiene turnos, no es festivo, etc.)
    
    # Validar fecha_limite_pago es posterior a fecha_inicio
    fecha_limite_pago = datos['fecha_limite_pago']
    assert fecha_limite_pago > fecha_inicio
```

**Aplicación al aprobar**:
- **Para cada día seleccionado en el rango**:
  - Solicitante descansa
  - Receptor trabaja AM+PM (doblada completa)
  - Receptor acumula 30 minutos de deuda corporativa por día
- **Deuda entre exploradores**: Solicitante debe a Receptor (días trabajados)
- **Estado**: 'aprobada' pero con `fecha_limite_pago` pendiente

**Acuerdo mutuo (receptor especifica días de pago)**:
- Receptor crea `CambioPermanenteDia` adicionales vinculados a la misma solicitud
- Estos días son cuando Solicitante debe doblarse
- Validar que están dentro de `fecha_limite_pago`
- Aplicar turnos para esos días (Solicitante dobla, Receptor descansa)

**Aplicación semanal**:
- Similar a CT permanente, usar helper para calcular fechas aplicables
- Excluir festivos, mantenimiento, temporadas
- Aplicar turnos semana tras semana hasta `fecha_fin`

#### 2.3 Estrategia de Implementación

**Archivo**: `solicitudes/services/strategies/doblada_permanente_strategy.py`

```python
class DobladaPermanenteStrategy(SolicitudStrategy):
    """
    Strategy para Doblada Permanente.
    Reutiliza CTPermanenteStrategy pero adaptado para dobladas.
    """
    
    def validar_solicitud(self, datos):
        # Reutilizar validaciones de CT permanente
        # PERO permitir sábados/domingos
        # Validar fecha_limite_pago
        pass
    
    def crear_solicitud(self, datos):
        # Crear SolicitudCambio
        # Crear CambioPermanenteDetalle (reutilizar)
        # Crear CambioPermanenteDia (reutilizar, permitir sábados/domingos)
        # Crear DobladaDetalle con tipo_doblada='permanente'
        pass
    
    def aplicar_solicitud(self, solicitud):
        # Usar helper calcular_fechas_aplicables_doblada_permanente()
        # Para cada fecha aplicable:
        #   - Receptor trabaja AM+PM
        #   - Solicitante descansa
        #   - Acumular 30 min deuda corporativa por día
        pass
```

**Reutilización**:
- ✅ `CTPermanenteStrategy` como base (copiar y adaptar)
- ✅ `calcular_fechas_aplicables_ct_permanente()` como base para nuevo helper
- ✅ Templates de CT permanente como base para UI

---

## ⏰ Sistema de Plazos y Multas

### 3.1 Extender `DeudaExplorador`

```python
class DeudaExplorador(models.Model):
    # ... campos existentes ...
    
    # NUEVO: Fecha límite de pago (30 días desde fecha_generacion)
    fecha_limite_pago = models.DateField(
        help_text='Fecha límite para pagar (30 días desde generación)'
    )
    
    # NUEVO: Fecha en que se aplicó multa
    fecha_aplicacion_multa = models.DateField(
        null=True,
        blank=True,
        help_text='Fecha en que se aplicó la multa por no pagar a tiempo'
    )
    
    # NUEVO: Estado de multa
    tiene_multa = models.BooleanField(
        default=False,
        help_text='True si tiene multa activa por no pagar a tiempo'
    )
```

### 3.2 Modelo de Multa

```python
class MultaExplorador(models.Model):
    """
    Modelo para registrar multas por no pagar deudas a tiempo.
    """
    ESTADO_CHOICES = [
        ('activa', 'Activa'),
        ('pagada', 'Pagada'),
        ('cancelada', 'Cancelada'),
    ]
    
    explorador = models.ForeignKey(
        Empleado,
        on_delete=models.CASCADE,
        related_name='multas'
    )
    deuda_origen = models.ForeignKey(
        DeudaExplorador,
        on_delete=models.CASCADE,
        related_name='multa_generada'
    )
    fecha_aplicacion = models.DateField(
        auto_now_add=True,
        help_text='Fecha en que se aplicó la multa'
    )
    fecha_fin_restriccion = models.DateField(
        help_text='Fecha hasta la cual el explorador tiene restricciones (30 días desde multa)'
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='activa'
    )
    comentario = models.TextField(
        null=True,
        blank=True,
        help_text='Comentario sobre la multa'
    )
    historial = HistoricalRecords()
    
    class Meta:
        indexes = [
            models.Index(fields=['explorador', 'estado'], name='multa_exp_estado_idx'),
            models.Index(fields=['fecha_fin_restriccion', 'estado'], name='multa_fecha_fin_estado_idx'),
        ]
```

### 3.3 Servicio de Validación de Plazos

```python
# solicitudes/services/plazo_multas_service.py

class PlazoMultasService:
    """
    Servicio para gestionar plazos de pago y multas.
    """
    
    @staticmethod
    def calcular_fecha_limite_pago(fecha_generacion: date) -> date:
        """Calcula fecha límite (30 días desde generación)."""
        return fecha_generacion + timedelta(days=30)
    
    @staticmethod
    def verificar_vencimientos():
        """
        Tarea periódica (cron) para verificar deudas vencidas.
        Debe ejecutarse diariamente.
        """
        hoy = date.today()
        deudas_vencidas = DeudaExplorador.objects.filter(
            estado='pendiente',
            fecha_limite_pago__lt=hoy,
            tiene_multa=False
        )
        
        for deuda in deudas_vencidas:
            MultaExplorador.objects.create(
                explorador=deuda.deudor,
                deuda_origen=deuda,
                fecha_fin_restriccion=hoy + timedelta(days=30),
                estado='activa',
                comentario=f'Multa por no pagar deuda a tiempo (venció {deuda.fecha_limite_pago})'
            )
            deuda.tiene_multa = True
            deuda.fecha_aplicacion_multa = hoy
            deuda.save()
    
    @staticmethod
    def tiene_restricciones(explorador: Empleado) -> bool:
        """
        Verifica si un explorador tiene restricciones activas por multa.
        """
        hoy = date.today()
        return MultaExplorador.objects.filter(
            explorador=explorador,
            estado='activa',
            fecha_fin_restriccion__gte=hoy
        ).exists()
    
    @staticmethod
    def validar_puede_solicitar_cambio(explorador: Empleado) -> Tuple[bool, str]:
        """
        Valida si un explorador puede realizar solicitudes de cambio.
        Retorna (puede_solicitar, mensaje_error)
        """
        if PlazoMultasService.tiene_restricciones(explorador):
            multa = MultaExplorador.objects.filter(
                explorador=explorador,
                estado='activa',
                fecha_fin_restriccion__gte=date.today()
            ).first()
            
            return False, (
                f"No puedes realizar solicitudes de cambio de turno hasta "
                f"{multa.fecha_fin_restriccion.strftime('%d/%m/%Y')} "
                f"debido a una multa por no pagar deudas a tiempo."
            )
        return True, ""
```

### 3.4 Integración en Validaciones

**Archivo**: `solicitudes/services/solicitud_validator.py`

```python
def validar_explorador_puede_solicitar(explorador: Empleado):
    """
    Valida que el explorador no tenga restricciones por multa.
    """
    puede, mensaje = PlazoMultasService.validar_puede_solicitar_cambio(explorador)
    if not puede:
        raise ValidationError(mensaje)
```

**Llamar en**:
- `DobladaStrategy.validar_solicitud()`
- `CTStrategy.validar_solicitud()`
- `CTPermanenteStrategy.validar_solicitud()`
- Cualquier estrategia de solicitud

---

## 🔄 Flujo de Pago de Deuda con Plazo

### 4.1 Al Crear Deuda

```python
# En DobladaAplicacionService o similar
deuda = DeudaExplorador.objects.create(
    deudor=solicitante,
    acreedor=receptor,
    fecha_pago_pactada=fecha_pago,
    fecha_limite_pago=PlazoMultasService.calcular_fecha_limite_pago(date.today()),
    # ... otros campos ...
)
```

### 4.2 Al Pagar Deuda

```python
# Si paga antes de fecha_limite_pago → OK
# Si paga después de fecha_limite_pago pero antes de multa → OK pero registrar retraso
# Si ya tiene multa → Debe pagar deuda primero, luego esperar fin de restricción
```

---

## 📊 Resumen de Recomendaciones

### ✅ Reutilización Máxima

1. **Doblada FDS**:
   - ✅ Extender `DobladaDetalle` con campos `tipo_doblada`, `fecha_domingo`, `fecha_pago_fin_semana`
   - ✅ Reutilizar `DobladaStrategy` base
   - ✅ Reutilizar `DeudaCorporativaService` (llamar 2 veces: 30 min × 2 días)

2. **Doblada Permanente**:
   - ✅ Reutilizar `CambioPermanenteDetalle` + `CambioPermanenteDia` al 100%
   - ✅ Extender `DobladaDetalle` con relación a `CambioPermanenteDetalle`
   - ✅ Adaptar `CTPermanenteStrategy` como base
   - ✅ Adaptar helper `calcular_fechas_aplicables_ct_permanente()`

3. **Sistema de Plazos/Multas**:
   - ✅ Extender `DeudaExplorador` con `fecha_limite_pago`, `tiene_multa`
   - ✅ Crear `MultaExplorador` nuevo (estructura simple)
   - ✅ Crear `PlazoMultasService` nuevo
   - ✅ Integrar validaciones en `SolicitudValidator`

### ⚠️ Consideraciones Importantes

1. **Migraciones**:
   - Agregar campos nullable a `DobladaDetalle` (backward compatible)
   - Crear `MultaExplorador` (nueva tabla)
   - Agregar campos a `DeudaExplorador` (backward compatible)

2. **Compatibilidad**:
   - Dobladas simples actuales siguen funcionando (`tipo_doblada='simple'` por defecto)
   - CT permanente actual no se afecta (solo se reutiliza estructura)

3. **Validaciones**:
   - D FDS: Validar que domingo es siguiente al sábado
   - D Permanente: Permitir sábados/domingos (modificar `CambioPermanenteDia.save()`)
   - Plazos: Validar en todas las estrategias de solicitud

4. **Tareas Periódicas**:
   - Crear tarea cron/django-celery para `PlazoMultasService.verificar_vencimientos()`
   - Ejecutar diariamente a medianoche

5. **UI/UX**:
   - Reutilizar templates de CT permanente para Doblada Permanente
   - Crear template específico para D FDS (más simple)
   - Agregar indicadores visuales de multas/restricciones

---

## 🎯 Priorización de Implementación

### Fase 1: Sistema de Plazos y Multas (Base)
1. Extender `DeudaExplorador`
2. Crear `MultaExplorador`
3. Crear `PlazoMultasService`
4. Integrar validaciones
5. Crear tarea periódica

### Fase 2: Doblada Fines de Semana
1. Extender `DobladaDetalle`
2. Crear `DobladaFDSStrategy`
3. Adaptar `DobladaAplicacionService`
4. Crear templates/UI

### Fase 3: Doblada Permanente
1. Adaptar `CambioPermanenteDia` para permitir sábados/domingos
2. Extender `DobladaDetalle` con relación a `CambioPermanenteDetalle`
3. Crear `DobladaPermanenteStrategy`
4. Crear helper `calcular_fechas_aplicables_doblada_permanente()`
5. Adaptar templates de CT permanente

---

## 📝 Notas Finales

- **Principio DRY**: Máxima reutilización de código existente
- **Backward Compatibility**: No romper funcionalidad actual
- **Escalabilidad**: Estructura preparada para futuros tipos de dobladas
- **Mantenibilidad**: Separación clara de responsabilidades por estrategia

**Estimación de esfuerzo**:
- Fase 1: 2-3 días
- Fase 2: 3-4 días
- Fase 3: 5-7 días
- **Total**: ~10-14 días de desarrollo

---

## 🔧 SOLUCIÓN: Script de Reaplicación de Dobladas Fallidas

### Problema Identificado (Caso: Mariana → Vanesa)
Una solicitud de doblada se aprobó correctamente, pero debido a un error en `DobladaTurnoService`, los turnos AM+PM no se crearon en la base de datos. Por eso:
- ✅ La solicitud aparece como aprobada
- ✅ Los descansos se ven correctamente
- ❌ **Las dobladas NO aparecen en "Mis Turnos"** (falta AM+PM en BD)

### Solución Implementada
Se crearon **dos management commands de Django** para diagnosticar y corregir este tipo de errores:

#### 1. `verificar_doblada` - Diagnóstico Completo
Verifica el estado de una doblada (turnos, deudas, visualización).

```bash
python manage.py verificar_doblada <ID_SOLICITUD>
```

#### 2. `reaplicar_doblada` - Corrección Automática
Reaplica una doblada que no se aplicó correctamente, recreando los turnos faltantes.

```bash
# Ver qué haría (sin hacer cambios)
python manage.py reaplicar_doblada <ID_SOLICITUD> --dry-run

# Aplicar corrección
python manage.py reaplicar_doblada <ID_SOLICITUD>
```

### Documentación Completa
Para instrucciones detalladas de uso, consulta:
- **📖 Guía Rápida**: `GUIA_RAPIDA_REAPLICAR_DOBLADA.md` (5 minutos de lectura)
- **📚 Documentación Completa**: `SOLUCION_DOBLADA_FALLIDA_MARIANA_VANESA.md` (referencia completa con SQL, troubleshooting, etc.)

### Ubicación de los Scripts
- `AppTurnosExplora/solicitudes/management/commands/verificar_doblada.py`
- `AppTurnosExplora/solicitudes/management/commands/reaplicar_doblada.py`

---


