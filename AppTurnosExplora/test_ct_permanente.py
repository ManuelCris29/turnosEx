#!/usr/bin/env python
"""
Script de prueba para verificar que CT PERMANENTE funciona correctamente
"""
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import TipoSolicitudCambio
from solicitudes.services.solicitud_factory import SolicitudFactory
from empleados.models import Empleado
from datetime import datetime, date

def test_ct_permanente_functionality():
    """Probar funcionalidad de CT PERMANENTE"""
    print("🔍 Probando funcionalidad de CT PERMANENTE...")
    
    try:
        # Obtener tipo de solicitud CT PERMANENTE
        tipo_ct_permanente = TipoSolicitudCambio.objects.get(nombre="CT PERMANENTE")
        print(f"✅ Tipo CT PERMANENTE encontrado: ID {tipo_ct_permanente.id}")
        
        # Obtener un empleado de prueba
        empleado = Empleado.objects.filter(activo=True).first()
        if not empleado:
            print("❌ No hay empleados activos para probar")
            return False
        
        print(f"✅ Empleado de prueba: {empleado.nombre} {empleado.apellido}")
        
        # Probar obtener empleados disponibles
        fecha_prueba = "2024-12-20"  # Fecha futura
        print(f"📅 Probando con fecha: {fecha_prueba}")
        
        empleados_disponibles = SolicitudFactory.get_empleados_disponibles(
            tipo_ct_permanente, 
            fecha_prueba, 
            empleado
        )
        
        print(f"👥 Empleados disponibles: {len(empleados_disponibles)}")
        for emp in empleados_disponibles:
            print(f"   - {emp.nombre} {emp.apellido} (ID: {emp.id})")
        
        # Probar obtener turno del empleado
        turno_info = SolicitudFactory.get_turno_explorador(
            tipo_ct_permanente,
            empleado.id,
            fecha_prueba
        )
        
        print(f"🔄 Información de turno:")
        print(f"   - Tiene turno: {turno_info.get('tiene_turno', False)}")
        if turno_info.get('turno'):
            turno = turno_info['turno']
            print(f"   - Jornada: {turno.get('jornada', 'No asignada')}")
            print(f"   - Horario: {turno.get('horario', 'No definido')}")
            print(f"   - Turno: {turno.get('turno', 'No asignado')}")
            print(f"   - Salas: {turno.get('salas', [])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en la prueba: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_strategy_instantiation():
    """Probar que la estrategia se puede instanciar"""
    print("\n🔍 Probando instanciación de estrategia...")
    
    try:
        tipo_ct_permanente = TipoSolicitudCambio.objects.get(nombre="CT PERMANENTE")
        strategy = SolicitudFactory.get_strategy(tipo_ct_permanente)
        
        if strategy:
            print(f"✅ Estrategia instanciada: {type(strategy).__name__}")
            print(f"   - Tipo: {strategy.tipo_solicitud}")
            return True
        else:
            print("❌ No se pudo instanciar la estrategia")
            return False
            
    except Exception as e:
        print(f"❌ Error instanciando estrategia: {e}")
        return False

def main():
    """Función principal de pruebas"""
    print("🚀 INICIANDO PRUEBAS DE CT PERMANENTE")
    print("=" * 50)
    
    tests = [
        test_strategy_instantiation,
        test_ct_permanente_functionality
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
        print("🎉 ¡TODAS LAS PRUEBAS PASARON! CT PERMANENTE está funcionando correctamente.")
        return True
    else:
        print("⚠️  Algunas pruebas fallaron. Revisar la implementación.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

