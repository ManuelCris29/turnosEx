"""
Script para verificar todos los festivos de 2026 y detectar errores
"""
from datetime import date, timedelta

def aplicar_ley_emiliani(fecha):
    """Aplica la Ley Emiliani: mueve al lunes siguiente si no es lunes"""
    # En Python weekday(): 0=Lunes, 6=Domingo
    # Pero necesitamos convertir a formato JavaScript: 0=Domingo, 1=Lunes
    dia_semana_py = fecha.weekday()  # 0=Lunes, 6=Domingo
    dia_semana_js = (dia_semana_py + 1) % 7  # Convertir a formato JS: 0=Domingo, 1=Lunes
    
    if dia_semana_js != 1:  # Si NO es lunes (en formato JS)
        # Calcular días hasta el próximo lunes (usando fórmula JS)
        dias_hasta_lunes = (8 - dia_semana_js) % 7
        return fecha + timedelta(days=dias_hasta_lunes)
    return fecha

# Festivos fijos (fecha original)
festivos_fijos = [
    (1, 1, 'Año Nuevo'),
    (1, 6, 'Día de los Reyes Magos'),
    (3, 19, 'Día de San José'),
    (5, 1, 'Día del Trabajo'),
    (7, 20, 'Día de la Independencia'),
    (8, 7, 'Batalla de Boyacá'),
    (8, 15, 'Asunción de la Virgen'),
    (10, 12, 'Día de la Raza'),
    (11, 1, 'Día de Todos los Santos'),
    (11, 11, 'Independencia de Cartagena'),
    (12, 8, 'Inmaculada Concepción'),
    (12, 25, 'Navidad'),
]

print("=" * 70)
print("VERIFICACIÓN DE FESTIVOS 2026 - APLICANDO LEY EMILIANI")
print("=" * 70)
print(f"{'Festivo':<30} {'Fecha Original':<20} {'Fecha Trasladada':<20} {'Día'}")
print("-" * 70)

for mes, dia, nombre in festivos_fijos:
    fecha_original = date(2026, mes, dia)
    fecha_trasladada = aplicar_ley_emiliani(fecha_original)
    dia_semana = fecha_trasladada.strftime('%A')
    
    if fecha_original != fecha_trasladada:
        print(f"{nombre:<30} {fecha_original.strftime('%Y-%m-%d'):<20} {fecha_trasladada.strftime('%Y-%m-%d'):<20} {dia_semana}")
    else:
        print(f"{nombre:<30} {fecha_original.strftime('%Y-%m-%d'):<20} {fecha_trasladada.strftime('%Y-%m-%d'):<20} {dia_semana} (ya es lunes)")

print("\n" + "=" * 70)
print("VERIFICACIÓN ESPECÍFICA:")
print("=" * 70)
print(f"1 de noviembre de 2026: {date(2026, 11, 1).strftime('%A')} -> Trasladado a: {aplicar_ley_emiliani(date(2026, 11, 1))}")
print(f"11 de noviembre de 2026: {date(2026, 11, 11).strftime('%A')} -> Trasladado a: {aplicar_ley_emiliani(date(2026, 11, 11))}")

