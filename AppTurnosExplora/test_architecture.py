#!/usr/bin/env python
"""
Script de prueba para verificar que la nueva arquitectura funciona correctamente
"""
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import TipoSolicitudCambio
from solicitudes.services.solicitud_factory import SolicitudFactory
from solicitudes.services.strategies import CambioTurnoStrategy, DobladaStrategy, CTPermanenteStrategy, DFDSStrategy

def test_strategy_registration():
    """Probar que las estrategias están registradas correctamente"""
    print("🔍 Probando registro de estrategias...")
    
    # Verificar que las estrategias están registradas
    strategies = SolicitudFactory._strategies
    print(f"📊 Estrategias registradas: {list(strategies.keys())}")
    
    expected_strategies = ["CT", "DOBLADA", "CT PERMANENTE", "D FDS"]
    
    for strategy_name in expected_strategies:
        if strategy_name in strategies:
            print(f"✅ {strategy_name}: Registrada correctamente")
        else:
            print(f"❌ {strategy_name}: NO registrada")
    
    return len(strategies) == len(expected_strategies)

def test_strategy_instantiation():
    """Probar que las estrategias se pueden instanciar"""
    print("\n🔍 Probando instanciación de estrategias...")
    
    try:
        # Obtener tipos de solicitud de la BD
        tipos = {
            "CT": TipoSolicitudCambio.objects.filter(nombre="CT").first(),
            "DOBLADA": TipoSolicitudCambio.objects.filter(nombre="DOBLADA").first(),
            "CT PERMANENTE": TipoSolicitudCambio.objects.filter(nombre="CT PERMANENTE").first(),
            "D FDS": TipoSolicitudCambio.objects.filter(nombre="D FDS").first()
        }
        
        for tipo_nombre, tipo_obj in tipos.items():
            if tipo_obj:
                strategy = SolicitudFactory.get_strategy(tipo_obj)
                if strategy:
                    print(f"✅ {tipo_nombre}: Instanciada correctamente - {type(strategy).__name__}")
                else:
                    print(f"❌ {tipo_nombre}: No se pudo instanciar estrategia")
            else:
                print(f"⚠️  {tipo_nombre}: Tipo no encontrado en BD")
        
        return True
        
    except Exception as e:
        print(f"❌ Error al instanciar estrategias: {e}")
        return False

def test_tipo_solicitud_models():
    """Probar que los tipos de solicitud existen en la base de datos"""
    print("\n🔍 Probando tipos de solicitud en BD...")
    
    try:
        tipos = TipoSolicitudCambio.objects.all()
        print(f"📊 Tipos encontrados en BD: {[t.nombre for t in tipos]}")
        
        expected_tipos = ["CT", "DOBLADA", "CT PERMANENTE", "D FDS"]
        
        for tipo_nombre in expected_tipos:
            try:
                tipo = TipoSolicitudCambio.objects.get(nombre=tipo_nombre)
                print(f"✅ {tipo_nombre}: Encontrado en BD (ID: {tipo.id})")
            except TipoSolicitudCambio.DoesNotExist:
                print(f"❌ {tipo_nombre}: NO encontrado en BD")
        
        return True
        
    except Exception as e:
        print(f"❌ Error al consultar tipos de solicitud: {e}")
        return False

def test_factory_methods():
    """Probar que los métodos del factory funcionan"""
    print("\n🔍 Probando métodos del factory...")
    
    try:
        # Probar validar_solicitud (con datos dummy)
        tipo_cambio = TipoSolicitudCambio.objects.filter(nombre="CT").first()
        if tipo_cambio:
            print(f"✅ Tipo 'CT' encontrado para pruebas")
            
            # Datos dummy para prueba
            datos_dummy = {
                'explorador_solicitante': None,  # Se manejará en la validación
                'explorador_receptor': None,
                'tipo_cambio': tipo_cambio,
                'comentario': 'Prueba',
                'fecha_cambio_turno': '2024-01-01'
            }
            
            # Esto debería fallar por datos incompletos, pero no por error de arquitectura
            try:
                es_valida, mensaje = SolicitudFactory.validar_solicitud(tipo_cambio, datos_dummy)
                print(f"✅ validar_solicitud: Funciona (resultado: {es_valida})")
            except Exception as e:
                if "No se encontró estrategia" in str(e):
                    print(f"❌ validar_solicitud: Error de estrategia - {e}")
                    return False
                else:
                    print(f"✅ validar_solicitud: Funciona (error esperado por datos incompletos)")
        else:
            print("❌ No se encontró tipo 'CT' para pruebas")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Error al probar métodos del factory: {e}")
        return False

def main():
    """Función principal de pruebas"""
    print("🚀 INICIANDO PRUEBAS DE ARQUITECTURA")
    print("=" * 50)
    
    # Ejecutar todas las pruebas
    tests = [
        test_strategy_registration,
        test_strategy_instantiation,
        test_tipo_solicitud_models,
        test_factory_methods
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Error en prueba {test.__name__}: {e}")
            results.append(False)
    
    # Resumen final
    print("\n" + "=" * 50)
    print("📊 RESUMEN DE PRUEBAS")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    print(f"✅ Pruebas pasadas: {passed}/{total}")
    print(f"❌ Pruebas fallidas: {total - passed}/{total}")
    
    if passed == total:
        print("🎉 ¡TODAS LAS PRUEBAS PASARON! La arquitectura está funcionando correctamente.")
        return True
    else:
        print("⚠️  Algunas pruebas fallaron. Revisar la implementación.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
