"""
Análisis detallado de la lógica de festivos
Verificar cada cálculo paso a paso
"""
from datetime import date, timedelta

def analizar_fecha(fecha, nombre):
    """Analiza una fecha y muestra información detallada"""
    print(f"\n{'='*70}")
    print(f"ANÁLISIS: {nombre}")
    print(f"{'='*70}")
    print(f"Fecha: {fecha.strftime('%Y-%m-%d')} ({fecha.strftime('%A')})")
    print(f"weekday() (Python): {fecha.weekday()} (0=Lunes, 6=Domingo)")
    print(f"isoweekday() (Python): {fecha.isoweekday()} (1=Lunes, 7=Domingo)")
    
    # Simular lógica JavaScript getDay()
    # En JS: getDay() devuelve 0=Domingo, 1=Lunes, ..., 6=Sábado
    # En Python weekday(): 0=Lunes, 1=Martes, ..., 6=Domingo
    # Conversión: JS_day = (Python_weekday + 1) % 7
    python_weekday = fecha.weekday()
    js_day = (python_weekday + 1) % 7
    print(f"Equivalente JS getDay(): {js_day} (0=Domingo, 1=Lunes, ..., 6=Sábado)")
    
    return js_day

def aplicar_ley_emiliani_js(fecha):
    """Aplica Ley Emiliani usando lógica JavaScript"""
    python_weekday = fecha.weekday()
    js_day = (python_weekday + 1) % 7  # Convertir a formato JS
    
    print(f"\n  Aplicando Ley Emiliani:")
    print(f"  - Día de la semana (JS): {js_day}")
    
    if js_day != 1:  # Si NO es lunes
        dias_hasta_lunes = (8 - js_day) % 7
        print(f"  - Días hasta lunes: {dias_hasta_lunes}")
        nueva_fecha = fecha + timedelta(days=dias_hasta_lunes)
        print(f"  - Fecha trasladada: {nueva_fecha.strftime('%Y-%m-%d')} ({nueva_fecha.strftime('%A')})")
        return nueva_fecha
    else:
        print(f"  - Ya es lunes, no se traslada")
        return fecha

# Verificar fechas problemáticas
print("="*70)
print("ANÁLISIS DETALLADO DE FESTIVOS 2026")
print("="*70)

# Año Nuevo
fecha_ano_nuevo = date(2026, 1, 1)
js_day = analizar_fecha(fecha_ano_nuevo, "Año Nuevo")
fecha_trasladada = aplicar_ley_emiliani_js(fecha_ano_nuevo)
print(f"\n  RESULTADO: Año Nuevo se celebra el {fecha_trasladada.strftime('%Y-%m-%d')}")

# Verificar el 5 de enero
fecha_5_enero = date(2026, 1, 5)
print(f"\n  ¿El 5 de enero es lunes? {fecha_5_enero.strftime('%A')} (weekday={fecha_5_enero.weekday()})")

# Reyes Magos
fecha_reyes = date(2026, 1, 6)
js_day = analizar_fecha(fecha_reyes, "Reyes Magos")
fecha_trasladada = aplicar_ley_emiliani_js(fecha_reyes)
print(f"\n  RESULTADO: Reyes Magos se celebra el {fecha_trasladada.strftime('%Y-%m-%d')}")

# Todos los Santos
fecha_todos_santos = date(2026, 11, 1)
js_day = analizar_fecha(fecha_todos_santos, "Todos los Santos")
fecha_trasladada = aplicar_ley_emiliani_js(fecha_todos_santos)
print(f"\n  RESULTADO: Todos los Santos se celebra el {fecha_trasladada.strftime('%Y-%m-%d')}")

# Independencia Cartagena
fecha_cartagena = date(2026, 11, 11)
js_day = analizar_fecha(fecha_cartagena, "Independencia Cartagena")
fecha_trasladada = aplicar_ley_emiliani_js(fecha_cartagena)
print(f"\n  RESULTADO: Independencia Cartagena se celebra el {fecha_trasladada.strftime('%Y-%m-%d')}")

# Verificar TODOS los días de enero 2026 para ver qué está pasando
print("\n" + "="*70)
print("VERIFICACIÓN: Días de enero 2026 que son lunes")
print("="*70)
for dia in range(1, 32):
    try:
        fecha = date(2026, 1, dia)
        if fecha.weekday() == 0:  # Lunes
            print(f"  {fecha.strftime('%Y-%m-%d')} ({fecha.strftime('%A')}) - Es lunes")
    except ValueError:
        pass


