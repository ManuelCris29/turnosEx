/**
 * Cálculo de Festivos de Colombia
 * 
 * Este módulo calcula los festivos de Colombia, incluyendo:
 * - Festivos fijos (Navidad, Año Nuevo, etc.)
 * - Festivos móviles (Semana Santa, Ascensión, Corpus Christi, etc.)
 * - Regla de lunes siguiente (si caen en domingo, se mueven al lunes)
 * 
 * Basado en el calendario oficial de Colombia (Ley 51 de 1983).
 */

/**
 * Calcula la fecha de Pascua (Domingo de Resurrección) para un año dado
 * usando el algoritmo de Meeus/Jones/Butcher
 * 
 * @param {number} año - Año para calcular Pascua
 * @returns {Date} Fecha de Pascua
 */
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

/**
 * Aplica la Ley Emiliani (Ley 51 de 1983): Mueve una fecha al lunes siguiente 
 * si NO cae en lunes. Todos los festivos en Colombia se celebran en lunes.
 * 
 * @param {Date} fecha - Fecha a verificar
 * @returns {Date} Fecha trasladada al lunes siguiente si no es lunes
 */
function aplicarLeyEmiliani(fecha) {
    const nuevaFecha = new Date(fecha);
    const diaSemana = nuevaFecha.getDay(); // 0=Domingo, 1=Lunes, ..., 6=Sábado
    
    // Si NO es lunes (1), mover al lunes siguiente
    if (diaSemana !== 1) {
        // Calcular días hasta el próximo lunes
        // Domingo (0) -> +1, Martes (2) -> +6, Miércoles (3) -> +5, etc.
        const diasHastaLunes = (8 - diaSemana) % 7;
        nuevaFecha.setDate(nuevaFecha.getDate() + diasHastaLunes);
    }
    
    return nuevaFecha;
}

/**
 * Formatea una fecha a formato YYYY-MM-DD
 * 
 * @param {Date} fecha - Fecha a formatear
 * @returns {string} Fecha en formato YYYY-MM-DD
 */
function formatearFecha(fecha) {
    const año = fecha.getFullYear();
    const mes = String(fecha.getMonth() + 1).padStart(2, '0');
    const dia = String(fecha.getDate()).padStart(2, '0');
    return `${año}-${mes}-${dia}`;
}

/**
 * Calcula todos los festivos de Colombia para un año dado
 * 
 * @param {number} año - Año para calcular festivos
 * @returns {Array} Array de objetos con {fecha: 'YYYY-MM-DD', descripcion: string}
 */
function calcularFestivosColombia(año) {
    const festivos = [];
    
    // 1. FESTIVOS FIJOS INAMOVIBLES
    // Estos festivos se celebran el día exacto que caen.
    festivos.push({ fecha: formatearFecha(new Date(año, 0, 1)), descripcion: 'Año Nuevo' });
    festivos.push({ fecha: formatearFecha(new Date(año, 4, 1)), descripcion: 'Día del Trabajo' });
    festivos.push({ fecha: formatearFecha(new Date(año, 6, 20)), descripcion: 'Día de la Independencia' }); // CORREGIDO: Inamovible
    festivos.push({ fecha: formatearFecha(new Date(año, 7, 7)), descripcion: 'Batalla de Boyacá' });
    festivos.push({ fecha: formatearFecha(new Date(año, 11, 8)), descripcion: 'Inmaculada Concepción' });
    festivos.push({ fecha: formatearFecha(new Date(año, 11, 25)), descripcion: 'Navidad' });
    
    // 2. FESTIVOS FIJOS TRASLADABLES (Ley Emiliani)
    // Si no caen lunes, se mueven al siguiente lunes.
    
    // Reyes Magos (6 Enero)
    const reyesMagos = aplicarLeyEmiliani(new Date(año, 0, 6));
    festivos.push({ fecha: formatearFecha(reyesMagos), descripcion: 'Día de los Reyes Magos' });
    
    // San José (19 Marzo)
    const sanJose = aplicarLeyEmiliani(new Date(año, 2, 19));
    festivos.push({ fecha: formatearFecha(sanJose), descripcion: 'Día de San José' });
    
    // San Pedro y San Pablo (29 Junio) - AGREGADO
    const sanPedro = aplicarLeyEmiliani(new Date(año, 5, 29));
    festivos.push({ fecha: formatearFecha(sanPedro), descripcion: 'San Pedro y San Pablo' });
    
    // Asunción de la Virgen (15 Agosto)
    const asuncion = aplicarLeyEmiliani(new Date(año, 7, 15));
    festivos.push({ fecha: formatearFecha(asuncion), descripcion: 'Asunción de la Virgen' });
    
    // Día de la Raza (12 Octubre)
    const diaRaza = aplicarLeyEmiliani(new Date(año, 9, 12));
    festivos.push({ fecha: formatearFecha(diaRaza), descripcion: 'Día de la Raza' });
    
    // Todos los Santos (1 Noviembre)
    const todosSantos = aplicarLeyEmiliani(new Date(año, 10, 1));
    festivos.push({ fecha: formatearFecha(todosSantos), descripcion: 'Día de Todos los Santos' });
    
    // Independencia de Cartagena (11 Noviembre)
    const independenciaCartagena = aplicarLeyEmiliani(new Date(año, 10, 11));
    festivos.push({ fecha: formatearFecha(independenciaCartagena), descripcion: 'Independencia de Cartagena' });
    
    // 3. FESTIVOS MÓVILES (basados en Pascua)
    const pascua = calcularPascua(año);
    
    // Jueves Santo (3 días antes de Pascua) - Fijo en semana
    const juevesSanto = new Date(pascua);
    juevesSanto.setDate(pascua.getDate() - 3);
    festivos.push({ fecha: formatearFecha(juevesSanto), descripcion: 'Jueves Santo' });
    
    // Viernes Santo (2 días antes de Pascua) - Fijo en semana
    const viernesSanto = new Date(pascua);
    viernesSanto.setDate(pascua.getDate() - 2);
    festivos.push({ fecha: formatearFecha(viernesSanto), descripcion: 'Viernes Santo' });
    
    // Domingo de Pascua (ya calculado) - Opcional, usualmente no es festivo laboral oficial extra pero sí litúrgico
    // festivos.push({ fecha: formatearFecha(pascua), descripcion: 'Domingo de Pascua' });
    
    // Ascensión (43 días después de Pascua, se mueve al lunes siguiente - Ley Emiliani)
    const ascension = new Date(pascua);
    ascension.setDate(pascua.getDate() + 43);
    const ascensionLunes = aplicarLeyEmiliani(ascension);
    festivos.push({ fecha: formatearFecha(ascensionLunes), descripcion: 'Día de la Ascensión' });
    
    // Corpus Christi (64 días después de Pascua, se mueve al lunes siguiente - Ley Emiliani)
    const corpusChristi = new Date(pascua);
    corpusChristi.setDate(pascua.getDate() + 64);
    const corpusLunes = aplicarLeyEmiliani(corpusChristi);
    festivos.push({ fecha: formatearFecha(corpusLunes), descripcion: 'Corpus Christi' });
    
    // Sagrado Corazón (71 días después de Pascua, se mueve al lunes siguiente - Ley Emiliani)
    const sagradoCorazon = new Date(pascua);
    sagradoCorazon.setDate(pascua.getDate() + 71);
    const sagradoLunes = aplicarLeyEmiliani(sagradoCorazon);
    festivos.push({ fecha: formatearFecha(sagradoLunes), descripcion: 'Sagrado Corazón de Jesús' });
    
    return festivos;
}

/**
 * Obtiene festivos para un rango de años
 * 
 * @param {number} añoInicio - Año inicial
 * @param {number} añoFin - Año final
 * @returns {Map} Map con fecha como clave y descripción como valor
 */
function obtenerFestivosRango(añoInicio, añoFin) {
    const festivosMap = new Map();
    
    for (let año = añoInicio; año <= añoFin; año++) {
        const festivosAño = calcularFestivosColombia(año);
        festivosAño.forEach(festivo => {
            festivosMap.set(festivo.fecha, festivo.descripcion);
        });
    }
    
    return festivosMap;
}
