"""
Script para verificar que la alternancia de fines de semana funciona correctamente
para el sábado 31 de enero de 2026.
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from datetime import date
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
from core.utils.jornada_utils import JornadaUtils

def test_alternancia():
    """Probar alternancia para varios fines de semana"""
    
    fechas_test = [
        date(2026, 1, 3),   # Sábado - debería trabajar AM
        date(2026, 1, 4),   # Domingo - debería trabajar PM
        date(2026, 1, 10),  # Sábado referencia - debería trabajar PM
        date(2026, 1, 11),  # Domingo - debería trabajar AM
        date(2026, 1, 17),  # Sábado - debería trabajar AM
        date(2026, 1, 18),  # Domingo - debería trabajar PM
        date(2026, 1, 24),  # Sábado - debería trabajar PM
        date(2026, 1, 25),  # Domingo - debería trabajar AM
        date(2026, 1, 31),  # Sábado - debería trabajar AM
        date(2026, 2, 1),   # Domingo - debería trabajar PM
        date(2026, 2, 7),   # Sábado - debería trabajar PM
        date(2026, 2, 8),   # Domingo - debería trabajar AM
    ]
    
    print("\n" + "="*80)
    print("PRUEBA DE ALTERNANCIA DE FINES DE SEMANA")
    print("="*80 + "\n")
    
    resultados_esperados = {
        date(2026, 1, 3): ("AM", "PM"),   # Sábado trabaja AM, Domingo trabaja PM
        date(2026, 1, 10): ("PM", "AM"),  # Sábado trabaja PM, Domingo trabaja AM
        date(2026, 1, 17): ("AM", "PM"),  # Sábado trabaja AM, Domingo trabaja PM
        date(2026, 1, 24): ("PM", "AM"),  # Sábado trabaja PM, Domingo trabaja AM
        date(2026, 1, 31): ("AM", "PM"),  # Sábado trabaja AM, Domingo trabaja PM
        date(2026, 2, 7): ("PM", "AM"),   # Sábado trabaja PM, Domingo trabaja AM
    }
    
    for fecha in fechas_test:
        es_sabado = fecha.weekday() == 5
        es_domingo = fecha.weekday() == 6
        
        if es_sabado:
            jornada_trabaja = AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha)
            jornada_descansa = AlternanciaFinesSemanaService.jornada_descansa_sabado(fecha)
            dia_nombre = "SÁBADO"
        elif es_domingo:
            jornada_trabaja = AlternanciaFinesSemanaService.jornada_trabaja_domingo(fecha)
            jornada_descansa = AlternanciaFinesSemanaService.jornada_descansa_domingo(fecha)
            dia_nombre = "DOMINGO"
        else:
            continue
        
        # Verificar con JornadaUtils
        jornada_am = JornadaUtils.calcular_jornada_dia("AM", fecha)
        jornada_pm = JornadaUtils.calcular_jornada_dia("PM", fecha)
        
        # Verificar resultado esperado
        if es_sabado:
            sabado_esperado, domingo_esperado = resultados_esperados.get(fecha, (None, None))
            if sabado_esperado:
                correcto = jornada_trabaja == sabado_esperado
                estado = "✅" if correcto else "❌"
            else:
                correcto = True
                estado = "✓"
        else:
            # Para domingo, verificar contra el sábado anterior
            sabado_anterior = fecha - timedelta(days=1)
            sabado_esperado, domingo_esperado = resultados_esperados.get(sabado_anterior, (None, None))
            if domingo_esperado:
                correcto = jornada_trabaja == domingo_esperado
                estado = "✅" if correcto else "❌"
            else:
                correcto = True
                estado = "✓"
        
        print(f"{estado} {dia_nombre} {fecha.strftime('%d/%m/%Y')}:")
        print(f"   Trabaja: {jornada_trabaja} | Descansa: {jornada_descansa}")
        print(f"   JornadaUtils - AM: {jornada_am} | PM: {jornada_pm}")
        
        if not correcto:
            if es_sabado:
                print(f"   ⚠️  ESPERADO: Trabaja {sabado_esperado}, pero obtuvo {jornada_trabaja}")
            else:
                print(f"   ⚠️  ESPERADO: Trabaja {domingo_esperado}, pero obtuvo {jornada_trabaja}")
        print()
    
    print("="*80)
    print("PRUEBA ESPECÍFICA: Sábado 31 de enero 2026")
    print("="*80 + "\n")
    
    fecha_31_enero = date(2026, 1, 31)
    fecha_1_febrero = date(2026, 2, 1)
    
    jornada_sabado = AlternanciaFinesSemanaService.jornada_trabaja_sabado(fecha_31_enero)
    jornada_domingo = AlternanciaFinesSemanaService.jornada_trabaja_domingo(fecha_1_febrero)
    
    print(f"Sábado 31/01/2026: Trabaja {jornada_sabado} (esperado: AM)")
    print(f"Domingo 01/02/2026: Trabaja {jornada_domingo} (esperado: PM)")
    
    # Verificar con JornadaUtils para usuario PM
    jornada_pm_31 = JornadaUtils.calcular_jornada_dia("PM", fecha_31_enero)
    jornada_am_31 = JornadaUtils.calcular_jornada_dia("AM", fecha_31_enero)
    
    print(f"\nJornadaUtils para 31/01/2026:")
    print(f"  Usuario AM: {jornada_am_31} (esperado: AM - trabaja)")
    print(f"  Usuario PM: {jornada_pm_31} (esperado: Descanso)")
    
    if jornada_sabado == "AM" and jornada_domingo == "PM" and jornada_pm_31 == "Descanso":
        print("\n✅ TODAS LAS PRUEBAS PASARON CORRECTAMENTE")
    else:
        print("\n❌ ALGUNAS PRUEBAS FALLARON")
        if jornada_sabado != "AM":
            print(f"   - Sábado debería trabajar AM, pero obtuvo {jornada_sabado}")
        if jornada_domingo != "PM":
            print(f"   - Domingo debería trabajar PM, pero obtuvo {jornada_domingo}")
        if jornada_pm_31 != "Descanso":
            print(f"   - Usuario PM debería estar en Descanso, pero obtuvo {jornada_pm_31}")

if __name__ == '__main__':
    from datetime import timedelta
    test_alternancia()


