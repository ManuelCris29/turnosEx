# Solución Precisa para Festivos de Colombia

## Problema Identificado

La lógica anterior aplicaba incorrectamente la **Ley Emiliani (Ley 51 de 1983)**:
- ❌ Solo movía festivos que caían en **domingo**
- ✅ Debe mover **TODOS** los festivos que NO caen en **lunes** al lunes siguiente

**Ejemplo:**
- 6 de enero de 2026 cae en **martes**
- Según Ley Emiliani, se traslada al **lunes 12 de enero de 2026**
- La lógica anterior lo dejaba como festivo el 6 de enero (incorrecto)

## Solución Implementada

### 1. Corrección de la Lógica JavaScript

**Archivo:** `static/js/festivos_colombia.js`

**Cambio principal:**
```javascript
// ANTES (INCORRECTO)
function moverALunesSiEsDomingo(fecha) {
    if (fecha.getDay() === 0) { // Solo domingo
        fecha.setDate(fecha.getDate() + 1);
    }
    return fecha;
}

// AHORA (CORRECTO)
function aplicarLeyEmiliani(fecha) {
    const diaSemana = fecha.getDay(); // 0=Domingo, 1=Lunes, ..., 6=Sábado
    
    // Si NO es lunes (1), mover al lunes siguiente
    if (diaSemana !== 1) {
        const diasHastaLunes = (8 - diaSemana) % 7 || 7;
        fecha.setDate(fecha.getDate() + diasHastaLunes);
    }
    
    return fecha;
}
```

### 2. Estrategia Híbrida para Máxima Precisión

#### Opción A: Biblioteca Python (RECOMENDADO)

**Biblioteca:** `calendario-colombiano`

**Instalación:**
```bash
pip install calendario-colombiano
```

**Uso en Backend:**
```python
from calendario_colombiano import CalendarioColombiano
from datetime import date

calendario = CalendarioColombiano()
fecha = date(2026, 1, 12)
es_festivo = calendario.es_festivo(fecha)  # True
```

**Ventajas:**
- ✅ Implementa correctamente la Ley Emiliani
- ✅ Mantenida por la comunidad
- ✅ Actualizada con cambios legislativos
- ✅ Precisión garantizada

**Integración:**
- El endpoint `/turnos/api/dias-festivos/` ahora intenta usar esta biblioteca
- Si está disponible, combina festivos calculados + festivos de BD
- Si no está disponible, usa solo festivos de BD (y el frontend usa su cálculo)

#### Opción B: API Externa (Alternativa)

**APIs disponibles:**
1. **PublicHolidays.co**: https://publicholidays.co/es/
2. **WebCal.Guru**: https://www.webcal.guru/es-CO/

**Ventajas:**
- ✅ Siempre actualizada
- ✅ No requiere mantenimiento local

**Desventajas:**
- ❌ Dependencia externa
- ❌ Requiere conexión a internet
- ❌ Posibles costos en uso intensivo

#### Opción C: Cálculo JavaScript Corregido (Respaldo)

**Archivo:** `static/js/festivos_colombia.js`

**Estado:**
- ✅ Lógica corregida para aplicar Ley Emiliani correctamente
- ✅ Funciona sin dependencias externas
- ✅ Cálculo rápido en el navegador

**Limitaciones:**
- ⚠️ Requiere mantenimiento manual si cambia la legislación
- ⚠️ No incluye festivos regionales o especiales

## Implementación Actual

### Flujo de Datos

```
┌─────────────────────────────────────────┐
│ 1. FRONTEND carga festivos              │
│    → Calcula festivos con JS corregido  │
│    → Llama API /turnos/api/dias-festivos/│
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 2. BACKEND procesa solicitud            │
│    → Intenta usar calendario-colombiano │
│    → Si no está, usa solo BD            │
│    → Combina festivos calculados + BD   │
└─────────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────┐
│ 3. FRONTEND recibe respuesta            │
│    → Combina festivos calculados + API  │
│    → Los de BD tienen prioridad         │
│    → Muestra en calendario Flatpickr    │
└─────────────────────────────────────────┘
```

### Verificación de Precisión

**Comando de verificación:**
```bash
python manage.py instalar_calendario_colombiano
```

Este comando:
1. Instala la biblioteca `calendario-colombiano`
2. Verifica que funcione correctamente
3. Prueba con fecha conocida (12 de enero de 2026)

## Recomendación Final

### Para Producción (RECOMENDADO):

1. **Instalar biblioteca Python:**
   ```bash
   pip install calendario-colombiano
   ```

2. **Verificar instalación:**
   ```bash
   python manage.py instalar_calendario_colombiano
   ```

3. **El sistema automáticamente:**
   - Usará la biblioteca para cálculos precisos
   - Combinará con festivos personalizados de BD
   - Mantendrá el cálculo JavaScript como respaldo

### Para Desarrollo:

- El cálculo JavaScript corregido funciona como respaldo
- Los festivos de BD siempre tienen prioridad
- Se puede agregar festivos personalizados desde el admin

## Próximos Pasos

1. ✅ Lógica JavaScript corregida
2. ✅ Endpoint backend preparado para biblioteca externa
3. ⏳ **Instalar biblioteca Python** (recomendado)
4. ⏳ Probar con fechas conocidas (ej: 12 de enero de 2026)
5. ⏳ Verificar que todos los festivos se muestren correctamente

## Referencias

- [Ley 51 de 1983 (Ley Emiliani)](https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=2785)
- [Biblioteca calendario-colombiano](https://pypi.org/project/calendario-colombiano/)
- [Calendario Colombia 2026](https://www.calendario-colombia.com/calendario-2026)


