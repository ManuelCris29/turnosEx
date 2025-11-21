from datetime import date, timedelta
from dateutil.easter import easter

class CalculadoraFestivos:
    """
    Calculadora de festivos de Colombia basada en la Ley 51 de 1983 (Ley Emiliani).
    """

    @staticmethod
    def calcular_festivos(anio):
        """
        Calcula todos los festivos para un año dado.
        Retorna una lista de diccionarios: [{'fecha': date, 'descripcion': str}]
        """
        festivos = []

        # 1. Festivos Fijos INAMOVIBLES (Se celebran el día exacto)
        festivos.append({'fecha': date(anio, 1, 1), 'descripcion': 'Año Nuevo'})
        festivos.append({'fecha': date(anio, 5, 1), 'descripcion': 'Día del Trabajo'})
        festivos.append({'fecha': date(anio, 7, 20), 'descripcion': 'Día de la Independencia'})
        festivos.append({'fecha': date(anio, 8, 7), 'descripcion': 'Batalla de Boyacá'})
        festivos.append({'fecha': date(anio, 12, 8), 'descripcion': 'Inmaculada Concepción'})
        festivos.append({'fecha': date(anio, 12, 25), 'descripcion': 'Navidad'})

        # 2. Festivos Fijos TRASLADABLES al lunes siguiente (Ley Emiliani)
        # Si caen en lunes, se quedan. Si no, van al siguiente lunes.
        trasladables_fijos = [
            (1, 6, 'Día de los Reyes Magos'),
            (3, 19, 'Día de San José'),
            (6, 29, 'San Pedro y San Pablo'),
            (8, 15, 'Asunción de la Virgen'),
            (10, 12, 'Día de la Raza'),
            (11, 1, 'Todos los Santos'),
            (11, 11, 'Independencia de Cartagena')
        ]

        for mes, dia, desc in trasladables_fijos:
            fecha_base = date(anio, mes, dia)
            fecha_final = CalculadoraFestivos._mover_a_lunes(fecha_base)
            festivos.append({'fecha': fecha_final, 'descripcion': desc})

        # 3. Festivos Móviles (Relativos a la Pascua)
        pascua = easter(anio)

        # Jueves Santo (Pascua - 3 días) - Fijo en la semana (siempre jueves)
        festivos.append({'fecha': pascua - timedelta(days=3), 'descripcion': 'Jueves Santo'})
        
        # Viernes Santo (Pascua - 2 días) - Fijo en la semana (siempre viernes)
        festivos.append({'fecha': pascua - timedelta(days=2), 'descripcion': 'Viernes Santo'})

        # Ascensión del Señor (Pascua + 43 días) -> Se traslada al lunes siguiente
        ascension = pascua + timedelta(days=43) # Cae en jueves
        festivos.append({'fecha': CalculadoraFestivos._mover_a_lunes(ascension), 'descripcion': 'Ascensión del Señor'})

        # Corpus Christi (Pascua + 64 días) -> Se traslada al lunes siguiente
        corpus = pascua + timedelta(days=64) # Cae en jueves
        festivos.append({'fecha': CalculadoraFestivos._mover_a_lunes(corpus), 'descripcion': 'Corpus Christi'})

        # Sagrado Corazón (Pascua + 71 días) -> Se traslada al lunes siguiente
        sagrado = pascua + timedelta(days=71) # Cae en viernes
        festivos.append({'fecha': CalculadoraFestivos._mover_a_lunes(sagrado), 'descripcion': 'Sagrado Corazón'})

        # Ordenar por fecha
        festivos.sort(key=lambda x: x['fecha'])
        return festivos

    @staticmethod
    def _mover_a_lunes(fecha):
        """
        Aplica la Ley Emiliani: Si la fecha no es lunes, se traslada al siguiente lunes.
        weekday(): 0=Lunes, 6=Domingo
        """
        dia_semana = fecha.weekday()
        if dia_semana != 0: # Si no es lunes
            dias_hasta_lunes = 7 - dia_semana
            return fecha + timedelta(days=dias_hasta_lunes)
        return fecha

