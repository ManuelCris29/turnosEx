#!/usr/bin/env python
"""
Script para probar la corrección de jornadas
"""

import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from solicitudes.models import SolicitudCambio
from turnos.models import AsignarJornadaExplorador
from django.db.models import Q
from datetime import date

def test_jornadas_corregidas():
    """Probar la corrección de jornadas"""
    
    # Obtener la solicitud CT PERMANENTE
    solicitud = SolicitudCambio.objects.filter(
        tipo_cambio__nombre='CT PERMANENTE',
        estado='aprobada'
    ).first()
    
    if not solicitud:
        print("❌ No se encontraron solicitudes CT PERMANENTE")
        return
    
    detalle = solicitud.cambio_permanente
    fecha_inicio = detalle.fecha_inicio
    
    print(f"Fecha inicio: {fecha_inicio}")
    print(f"Solicitante: {solicitud.explorador_solicitante.nombre}")
    print(f"Receptor: {solicitud.explorador_receptor.nombre}")
    
    # Probar la nueva lógica de búsqueda de jornadas
    print(f"\n🔍 PROBANDO NUEVA LÓGICA DE JORNADAS:")
    print("-" * 50)
    
    # Jornada del solicitante
    jornada_solicitante = AsignarJornadaExplorador.objects.filter(
        explorador=solicitud.explorador_solicitante,
        fecha_inicio__lte=fecha_inicio
    ).filter(
        Q(fecha_fin__gte=fecha_inicio) | Q(fecha_fin__isnull=True)
    ).order_by('-fecha_inicio').first()
    
    print(f"Jornada solicitante:")
    if jornada_solicitante:
        print(f"  ✅ {jornada_solicitante.fecha_inicio} a {jornada_solicitante.fecha_fin} | {jornada_solicitante.jornada.nombre}")
    else:
        print(f"  ❌ No encontrada")
    
    # Jornada del receptor
    jornada_receptor = AsignarJornadaExplorador.objects.filter(
        explorador=solicitud.explorador_receptor,
        fecha_inicio__lte=fecha_inicio
    ).filter(
        Q(fecha_fin__gte=fecha_inicio) | Q(fecha_fin__isnull=True)
    ).order_by('-fecha_inicio').first()
    
    print(f"Jornada receptor:")
    if jornada_receptor:
        print(f"  ✅ {jornada_receptor.fecha_inicio} a {jornada_receptor.fecha_fin} | {jornada_receptor.jornada.nombre}")
    else:
        print(f"  ❌ No encontrada")
    
    # Verificar si ambas jornadas se encontraron
    if jornada_solicitante and jornada_receptor:
        print(f"\n✅ AMBAS JORNADAS ENCONTRADAS - aplicar_cambios() debería funcionar")
        
        # Probar aplicar_cambios() directamente
        print(f"\n🔍 PROBANDO APLICAR_CAMBIOS():")
        print("-" * 50)
        
        from solicitudes.services.solicitud_factory import SolicitudFactory
        strategy = SolicitudFactory.get_strategy(solicitud.tipo_cambio)
        
        if strategy:
            try:
                success, message = strategy.aplicar_cambios(solicitud)
                print(f"Resultado: {success}")
                print(f"Mensaje: {message}")
                
                if success:
                    print("✅ aplicar_cambios() ejecutado correctamente")
                else:
                    print(f"❌ Error: {message}")
                    
            except Exception as e:
                print(f"❌ Excepción: {e}")
                import traceback
                traceback.print_exc()
        else:
            print("❌ No se encontró estrategia")
    else:
        print(f"\n❌ FALTAN JORNADAS - aplicar_cambios() fallará")

if __name__ == "__main__":
    test_jornadas_corregidas()
