# ¿Cómo Funcionan los Calendarios que Muestran Festivos Automáticamente?

## Explicación Técnica

Los calendarios como [calendario-colombia.com](https://www.calendario-colombia.com/calendario-2025) saben automáticamente qué días son festivos usando **algoritmos matemáticos** para calcular festivos móviles.

### 1. FESTIVOS FIJOS (Fáciles)

Estos son simples: siempre caen en la misma fecha cada año.

**Ejemplos:**
- **Año Nuevo**: 1 de enero
- **Día del Trabajo**: 1 de mayo
- **Independencia**: 20 de julio
- **Batalla de Boyacá**: 7 de agosto
- **Navidad**: 25 de diciembre

**Código:**
```javascript
festivos.push({ fecha: '2025-01-01', descripcion: 'Año Nuevo' });
festivos.push({ fecha: '2025-12-25', descripcion: 'Navidad' });
```

### 2. FESTIVOS MÓVILES (Complejos)

Estos varían cada año y se calculan usando algoritmos.

#### A. Semana Santa (Basada en Pascua)

**Pascua** (Domingo de Resurrección) se calcula usando el **Algoritmo de Meeus/Jones/Butcher**:

```javascript
function calcularPascua(año) {
    const a = año % 19;
    const b = Math.floor(año / 100);
    const c = año % 100;
    const d = Math.floor(b / 4);
    const e = b % 4;
    const f = Math.floor((b + 8) / 25);
    const g = Math.floor((b - f + 1) / 3);
    const h = (19 * a + b - d - g + 15) % 30;
    const i = Math.floor(c / 4);
    const k = c % 4;
    const l = (32 + 2 * e + 2 * i - h - k) % 7;
    const m = Math.floor((a + 11 * h + 22 * l) / 451);
    const mes = Math.floor((h + l - 7 * m + 114) / 31) - 1;
    const dia = ((h + l - 7 * m + 114) % 31) + 1;
    
    return new Date(año, mes, dia);
}
```

**Festivos relacionados:**
- **Domingo de Ramos**: 7 días antes de Pascua
- **Jueves Santo**: 3 días antes de Pascua
- **Viernes Santo**: 2 días antes de Pascua
- **Domingo de Pascua**: La fecha calculada

#### B. Festivos que Dependen de Pascua

- **Ascensión**: 43 días después de Pascua
- **Corpus Christi**: 64 días después de Pascua
- **Sagrado Corazón**: 71 días después de Pascua

### 3. REGLA DEL LUNES SIGUIENTE

En Colombia, algunos festivos se mueven al lunes siguiente si caen en domingo:

```javascript
function moverALunesSiEsDomingo(fecha) {
    if (fecha.getDay() === 0) { // Domingo = 0
        fecha.setDate(fecha.getDate() + 1); // Mover al lunes
    }
    return fecha;
}
```

**Festivos que aplican esta regla:**
- Reyes Magos (6 de enero)
- San José (19 de marzo)
- Ascensión
- Corpus Christi
- Sagrado Corazón
- Asunción de la Virgen (15 de agosto)

## Implementación en Nuestra Aplicación

### Archivo: `festivos_colombia.js`

Este archivo contiene:
1. **`calcularPascua(año)`**: Calcula Pascua para cualquier año
2. **`moverALunesSiEsDomingo(fecha)`**: Aplica regla del lunes
3. **`calcularFestivosColombia(año)`**: Calcula todos los festivos de un año
4. **`obtenerFestivosRango(añoInicio, añoFin)`**: Obtiene festivos para múltiples años

### Ventajas de Este Enfoque

✅ **No requiere BD**: Los festivos se calculan automáticamente
✅ **Siempre actualizado**: Funciona para cualquier año futuro
✅ **Preciso**: Usa algoritmos oficiales
✅ **Rápido**: Cálculo instantáneo en el navegador

### Combinación con BD

Nuestra aplicación combina:
1. **Festivos calculados** (Colombia oficial)
2. **Festivos de BD** (personalizados por la organización)

Los festivos de BD tienen prioridad y pueden:
- Sobrescribir festivos calculados
- Agregar festivos adicionales (ej: días de mantenimiento)

## Visualización en el Calendario

### Flatpickr Personalizado

Usamos **Flatpickr** para mostrar festivos directamente en el calendario:

```javascript
flatpickr(fechaInput, {
    onReady: function(selectedDates, dateStr, instance) {
        // Marcar días festivos con clase CSS
        fechasFestivos.forEach(fechaFestivo => {
            const day = instance.calendarContainer.querySelector(...);
            day.classList.add('festivo'); // Clase CSS roja
            day.title = descripcion; // Tooltip con descripción
        });
    }
});
```

**Estilos CSS:**
```css
.flatpickr-day.festivo {
    background-color: #ff6b6b !important;
    color: white !important;
    font-weight: bold;
}
```

## Resultado Final

Cuando el usuario abre el calendario:
1. ✅ Ve los festivos marcados en **rojo** directamente
2. ✅ Al hacer hover, ve la descripción del festivo
3. ✅ Al seleccionar un festivo, aparece un indicador adicional
4. ✅ Los festivos se calculan automáticamente para cualquier año

## Referencias

- [Calendario Colombia 2025](https://www.calendario-colombia.com/calendario-2025)
- [Algoritmo de Pascua (Wikipedia)](https://es.wikipedia.org/wiki/C%C3%A1lculo_de_la_fecha_de_Pascua)
- [Flatpickr Documentation](https://flatpickr.js.org/)

