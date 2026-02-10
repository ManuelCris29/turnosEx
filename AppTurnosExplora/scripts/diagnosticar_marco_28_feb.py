#!/usr/bin/env python
"""
Script para diagnosticar con quién cedió la jornada Marco Castillo el 28 de febrero de 2026.
"""

import os
import sys
import django
from datetime import datetime

# Configurar Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from empleados.models import Empleado
from solicitudes.models import SolicitudCambio, DobladaDetalle
from turnos.models import Turno
from django.db.models import Q

def diagnosticar_marco_28_feb():
    """Diagnosticar con quién cedió la jornada Marco Castillo el 28 de febrero."""
    
    # Buscar Marco Castillo - intentar por username primero
    user = User.objects.filter(username__icontains='marco').first()
    if not user:
        # Si no se encuentra por username, buscar por nombre/apellido
        empleado_marco = Empleado.objects.filter(
            nombre__icontains='marco'
        ).first()
        if empleado_marco:
            marco = empleado_marco
            user = empleado_marco.user if hasattr(empleado_marco, 'user') else None
        else:
            print("❌ No se encontró usuario o empleado con 'marco'")
            print("\nBuscando todos los usuarios con 'marco'...")
            users = User.objects.filter(username__icontains='marco')[:5]
            for u in users:
                print(f"  - {u.username}")
            return
    else:
        marco = user.empleado if hasattr(user, 'empleado') else None
        if not marco:
            print(f"❌ El usuario {user.username} no tiene empleado asociado")
            return
        
        print(f"✅ Usuario encontrado: {marco.nombre} {marco.apellido} (ID: {marco.id})")
        print(f"   Username: {user.username}")
        print()
        
        # Fecha objetivo
        fecha_obj = datetime(2026, 2, 28).date()
        print(f"📅 Fecha a analizar: {fecha_obj.strftime('%d/%m/%Y')}")
        print()
        
        # Verificar si tiene turnos asignados
        turnos = Turno.objects.filter(
            explorador=marco,
            fecha=fecha_obj
        ).select_related('jornada')
        
        if turnos.exists():
            jornadas = [t.jornada.nombre for t in turnos if t.jornada]
            print(f"⚠️  Marco SÍ tiene turnos asignados el {fecha_obj.strftime('%d/%m/%Y')}: {', '.join(jornadas)}")
            print("   Esto significa que NO debería aparecer como descansando.")
            print()
        else:
            print(f"✅ Marco NO tiene turnos asignados el {fecha_obj.strftime('%d/%m/%Y')}")
            print("   Esto es consistente con que aparezca descansando.")
            print()
        
        # Buscar solicitudes donde Marco es SOLICITANTE (cedió su jornada)
        solicitudes_como_solicitante = SolicitudCambio.objects.filter(
            explorador_solicitante=marco,
            tipo_cambio__nombre='DOBLADA',
            fecha_cambio_turno=fecha_obj,
            estado='aprobada'
        ).select_related(
            'explorador_receptor',
            'tipo_cambio',
            'doblada'
        )
        
        print("=" * 80)
        print("🔍 SOLICITUDES DONDE MARCO ES SOLICITANTE (CEDIÓ SU JORNADA)")
        print("=" * 80)
        
        if solicitudes_como_solicitante.exists():
            for solicitud in solicitudes_como_solicitante:
                receptor = solicitud.explorador_receptor
                detalle = solicitud.doblada
                
                print(f"\n📋 Solicitud ID: {solicitud.id}")
                print(f"   Estado: {solicitud.estado}")
                print(f"   Fecha de solicitud: {solicitud.fecha_solicitud.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_solicitud else 'N/A'}")
                print(f"   Fecha de cesión: {solicitud.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud.fecha_cambio_turno else 'N/A'}")
                print()
                print(f"   👤 RECEPTOR (Quien cubrió a Marco):")
                print(f"      Nombre: {receptor.nombre} {receptor.apellido}")
                print(f"      ID: {receptor.id}")
                print(f"      Email: {receptor.email}")
                print()
                
                if detalle:
                    print(f"   📝 Detalles de la Doblada:")
                    print(f"      Tipo de cesión: {detalle.get_tipo_cesion_display()}")
                    print(f"      Jornada cedida: {detalle.jornada_cedida or 'N/A'}")
                    print(f"      Fecha de pago: {detalle.fecha_pago.strftime('%d/%m/%Y') if detalle.fecha_pago else 'N/A'}")
                    print(f"      Minutos de deuda: {detalle.minutos_deuda}")
                    if detalle.jornada_pago_sabado:
                        print(f"      Jornada pago sábado: {detalle.jornada_pago_sabado}")
                    print()
                
                # Verificar turnos del receptor en fecha de cesión
                turnos_receptor = Turno.objects.filter(
                    explorador=receptor,
                    fecha=fecha_obj
                ).select_related('jornada')
                
                if turnos_receptor.exists():
                    jornadas_receptor = [t.jornada.nombre for t in turnos_receptor if t.jornada]
                    print(f"   ✅ Receptor tiene turnos asignados el {fecha_obj.strftime('%d/%m/%Y')}: {', '.join(jornadas_receptor)}")
                else:
                    print(f"   ⚠️  Receptor NO tiene turnos asignados el {fecha_obj.strftime('%d/%m/%Y')}")
                print()
        else:
            print("❌ No se encontraron solicitudes donde Marco es solicitante (cedió su jornada)")
            print()
        
        # Buscar solicitudes donde Marco es RECEPTOR (cubrió a alguien) en fecha de pago
        solicitudes_como_receptor = SolicitudCambio.objects.filter(
            explorador_receptor=marco,
            tipo_cambio__nombre='DOBLADA',
            estado='aprobada',
            doblada__fecha_pago=fecha_obj
        ).select_related(
            'explorador_solicitante',
            'tipo_cambio',
            'doblada'
        )
        
        print("=" * 80)
        print("🔍 SOLICITUDES DONDE MARCO ES RECEPTOR (CUBRIÓ A ALGUIEN) EN FECHA DE PAGO")
        print("=" * 80)
        
        if solicitudes_como_receptor.exists():
            for solicitud in solicitudes_como_receptor:
                solicitante = solicitud.explorador_solicitante
                detalle = solicitud.doblada
                
                print(f"\n📋 Solicitud ID: {solicitud.id}")
                print(f"   Estado: {solicitud.estado}")
                print(f"   Fecha de solicitud: {solicitud.fecha_solicitud.strftime('%d/%m/%Y %H:%M') if solicitud.fecha_solicitud else 'N/A'}")
                print(f"   Fecha de cesión: {solicitud.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud.fecha_cambio_turno else 'N/A'}")
                print()
                print(f"   👤 SOLICITANTE (Quien cedió su jornada):")
                print(f"      Nombre: {solicitante.nombre} {solicitante.apellido}")
                print(f"      ID: {solicitante.id}")
                print(f"      Email: {solicitante.email}")
                print()
                
                if detalle:
                    print(f"   📝 Detalles de la Doblada:")
                    print(f"      Tipo de cesión: {detalle.get_tipo_cesion_display()}")
                    print(f"      Jornada cedida: {detalle.jornada_cedida or 'N/A'}")
                    print(f"      Fecha de pago: {detalle.fecha_pago.strftime('%d/%m/%Y') if detalle.fecha_pago else 'N/A'}")
                    print(f"      Minutos de deuda: {detalle.minutos_deuda}")
                    if detalle.jornada_pago_sabado:
                        print(f"      Jornada pago sábado: {detalle.jornada_pago_sabado}")
                    print()
                
                # Verificar turnos del solicitante en fecha de cesión
                if solicitud.fecha_cambio_turno:
                    turnos_solicitante = Turno.objects.filter(
                        explorador=solicitante,
                        fecha=solicitud.fecha_cambio_turno
                    ).select_related('jornada')
                    
                    if turnos_solicitante.exists():
                        jornadas_solicitante = [t.jornada.nombre for t in turnos_solicitante if t.jornada]
                        print(f"   ✅ Solicitante tiene turnos asignados el {solicitud.fecha_cambio_turno.strftime('%d/%m/%Y')}: {', '.join(jornadas_solicitante)}")
                    else:
                        print(f"   ⚠️  Solicitante NO tiene turnos asignados el {solicitud.fecha_cambio_turno.strftime('%d/%m/%Y')}")
                    print()
        else:
            print("❌ No se encontraron solicitudes donde Marco es receptor en fecha de pago")
            print()
        
        # Resumen
        print("=" * 80)
        print("📊 RESUMEN")
        print("=" * 80)
        
        if solicitudes_como_solicitante.exists():
            print(f"✅ Marco cedió su jornada el {fecha_obj.strftime('%d/%m/%Y')} a:")
            for solicitud in solicitudes_como_solicitante:
                receptor = solicitud.explorador_receptor
                print(f"   - {receptor.nombre} {receptor.apellido} (ID: {receptor.id})")
                print(f"     Solicitud ID: {solicitud.id}")
        else:
            print(f"❌ No se encontró solicitud donde Marco cedió su jornada el {fecha_obj.strftime('%d/%m/%Y')}")
        
        if solicitudes_como_receptor.exists():
            print(f"\n✅ Marco cubrió a alguien el {fecha_obj.strftime('%d/%m/%Y')} (fecha de pago):")
            for solicitud in solicitudes_como_receptor:
                solicitante = solicitud.explorador_solicitante
                print(f"   - {solicitante.nombre} {solicitante.apellido} (ID: {solicitante.id})")
                print(f"     Solicitud ID: {solicitud.id}")
                print(f"     Fecha de cesión original: {solicitud.fecha_cambio_turno.strftime('%d/%m/%Y') if solicitud.fecha_cambio_turno else 'N/A'}")
        
        print()

if __name__ == '__main__':
    diagnosticar_marco_28_feb()

