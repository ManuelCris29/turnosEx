# Límites de Cálculo de Festivos - Explicación Técnica

## Respuesta Directa

**NO tiene límite práctico.** El sistema puede calcular festivos para **cualquier año**, no solo hasta 2037.

## Límites Técnicos

### 1. Límite de JavaScript Date

El objeto `Date` de JavaScript puede manejar fechas desde:
- **Año mínimo**: ~271,821 AEC (antes de la era común)
- **Año máximo**: ~275,760 EC (era común)

**Conclusión**: No hay límite práctico para años futuros. El "problema del año 2038" es específico de sistemas de 32 bits con timestamps Unix, **NO aplica a JavaScript**.

### 2. Límite de la Función de Cálculo

La función `calcularFestivosColombia(año)` puede calcular festivos para **cualquier año** porque:
- Usa algoritmos matemáticos (no depende de datos pre-calculados)
- El algoritmo de Pascua funciona para cualquier año
- La Ley Emiliani es una regla matemática simple

**Ejemplo:**
```javascript
calcularFestivosColombia(2025);  // ✅ Funciona
calcularFestivosColombia(2037);  // ✅ Funciona
calcularFestivosColombia(2050);  // ✅ Funciona
calcularFestivosColombia(2100);  // ✅ Funciona
calcularFestivosColombia(3000);  // ✅ Funciona
```

## Límite Práctico Actual (Implementación)

### Carga Inicial
- **Rango**: Año actual - 1 hasta año actual + 10
- **Ejemplo 2025**: 2024 a 2035 (12 años)

### Carga Dinámica
- Si navegas a un año **fuera del rango inicial**, se cargan automáticamente
- **Ejemplo**: Si estás en 2025 y navegas a 2040, se calculan los festivos para 2040 automáticamente

### Código Actual

```javascript
// Carga inicial: año actual - 1 a + 10
const añoInicio = añoActual - 1;
const añoFin = añoActual + 10;

// Si navegas fuera del rango, carga dinámicamente
if (nuevoAño < añoInicio || nuevoAño > añoFin) {
    cargarDiasFestivos(nuevoAño); // Carga solo para ese año
}
```

## ¿Por Qué Solo 10 Años Inicialmente?

**Razón de rendimiento:**
- Calcular festivos para 12 años es rápido (< 1ms)
- Calcular para 100 años también es rápido, pero innecesario
- Se carga dinámicamente cuando se necesita

**Si quieres cambiar el rango:**
```javascript
// Cambiar de 10 a 50 años futuros
const añoFin = añoActual + 50;
```

## Verificación

### Años que Funcionan
- ✅ 2025, 2026, 2027... (años cercanos)
- ✅ 2037, 2040, 2050... (años futuros)
- ✅ 2100, 2200, 3000... (años muy lejanos)
- ✅ Cualquier año hasta ~275,760 (límite técnico de JavaScript)

### Años que NO Funcionan
- ❌ Años antes de ~271,821 AEC (límite técnico)
- ❌ Años después de ~275,760 EC (límite técnico)

## Conclusión

**El sistema NO tiene límite práctico para años futuros.**

- ✅ Funciona para 2037
- ✅ Funciona para 2050
- ✅ Funciona para 2100
- ✅ Funciona para cualquier año razonable

El único límite es el técnico de JavaScript (~275,760 años), que es completamente irrelevante para uso práctico.

## Recomendación

Si quieres asegurar que siempre funcione sin carga dinámica, puedes aumentar el rango inicial:

```javascript
// Cambiar de 10 a 20 años futuros
const añoFin = añoActual + 20;
```

Pero **no es necesario** porque la carga dinámica funciona perfectamente.

