"""
Script para verificar el estado de una solicitud de doblada y los turnos creados.
Uso: python manage.py shell < scripts/verificar_solicitud_doblada.py
O ejecutar en shell: exec(open('scripts/verificar_solicitud_doblada.py').read())
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from solicitudes.models import SolicitudCambio
from turnos.models import Turno

# Cambiar este ID por el de la solicitud que quieres verificar
SOLICITUD_ID = None  # Cambiar aquí

if SOLICITUD_ID is None:
    print("⚠️  Por favor, edita el script y establece SOLICITUD_ID")
    print("   Ejemplo: SOLICITUD_ID = 123")
    sys.exit(1)

try:
    solicitud = SolicitudCambio.objects.select_related(
        'explorador_solicitante',
        'explorador_receptor',
        'tipo_cambio',
        'doblada'
    ).get(id=SOLICITUD_ID)
    
    print(f"\n{'='*60}")
    print(f"SOLICITUD ID: {solicitud.id}")
    print(f"{'='*60}\n")
    
    print(f"Estado: {solicitud.estado}")
    print(f"Aprobado por receptor: {solicitud.aprobado_receptor}")
    print(f"Aprobado por supervisor: {solicitud.aprobado_supervisor}")
    print(f"Tipo: {solicitud.tipo_cambio.nombre if solicitud.tipo_cambio else 'N/A'}")
    print()
    
    if solicitud.doblada:
        detalle = solicitud.doblada
        print(f"Fecha de cesión: {solicitud.fecha_cambio_turno}")
        print(f"Fecha de pago: {detalle.fecha_pago}")
        print(f"Tipo de cesión: {detalle.tipo_cesion}")
        print(f"Jornada cedida: {detalle.jornada_cedida}")
        print()
        
        solicitante = solicitud.explorador_solicitante
        receptor = solicitud.explorador_receptor
        fecha_cesion = solicitud.fecha_cambio_turno
        fecha_pago = detalle.fecha_pago
        
        print(f"{'='*60}")
        print(f"TURNOS EN FECHA DE CESIÓN ({fecha_cesion})")
        print(f"{'='*60}\n")
        
        turnos_cesion_receptor = Turno.objects.filter(
            explorador=receptor, fecha=fecha_cesion
        ).select_related('jornada')
        turnos_cesion_solicitante = Turno.objects.filter(
            explorador=solicitante, fecha=fecha_cesion
        ).select_related('jornada')
        
        print(f"Receptor ({receptor.nombre}):")
        if turnos_cesion_receptor.exists():
            for t in turnos_cesion_receptor:
                print(f"  - Turno ID {t.id}: {t.jornada.nombre} (tipo_cambio: {t.tipo_cambio})")
        else:
            print("  - Sin turnos")
        
        print(f"\nSolicitante ({solicitante.nombre}):")
        if turnos_cesion_solicitante.exists():
            for t in turnos_cesion_solicitante:
                print(f"  - Turno ID {t.id}: {t.jornada.nombre} (tipo_cambio: {t.tipo_cambio})")
        else:
            print("  - Sin turnos")
        
        print(f"\n{'='*60}")
        print(f"TURNOS EN FECHA DE PAGO ({fecha_pago})")
        print(f"{'='*60}\n")
        
        turnos_pago_solicitante = Turno.objects.filter(
            explorador=solicitante, fecha=fecha_pago
        ).select_related('jornada')
        turnos_pago_receptor = Turno.objects.filter(
            explorador=receptor, fecha=fecha_pago
        ).select_related('jornada')
        
        print(f"Solicitante ({solicitante.nombre}):")
        if turnos_pago_solicitante.exists():
            for t in turnos_pago_solicitante:
                print(f"  - Turno ID {t.id}: {t.jornada.nombre} (tipo_cambio: {t.tipo_cambio})")
        else:
            print("  - Sin turnos")
        
        print(f"\nReceptor ({receptor.nombre}):")
        if turnos_pago_receptor.exists():
            for t in turnos_pago_receptor:
                print(f"  - Turno ID {t.id}: {t.jornada.nombre} (tipo_cambio: {t.tipo_cambio})")
        else:
            print("  - Sin turnos")
        
        print(f"\n{'='*60}")
        print("DIAGNÓSTICO")
        print(f"{'='*60}\n")
        
        if solicitud.estado != 'aprobada':
            print(f"⚠️  La solicitud NO está aprobada (estado: {solicitud.estado})")
            print("   Los turnos NO se crean hasta que la solicitud esté completamente aprobada.")
            if not solicitud.aprobado_receptor:
                print("   - Falta aprobación del receptor")
            if not solicitud.aprobado_supervisor:
                print("   - Falta aprobación del supervisor")
        else:
            print("✅ La solicitud está aprobada")
            jornadas_cesion_receptor = [t.jornada.nombre.upper() for t in turnos_cesion_receptor]
            jornadas_pago_solicitante = [t.jornada.nombre.upper() for t in turnos_pago_solicitante]
            
            if detalle.tipo_cesion == 'cesion_completa':
                if 'AM' in jornadas_cesion_receptor and 'PM' in jornadas_cesion_receptor:
                    print("✅ Receptor tiene doblada en fecha de cesión")
                else:
                    print(f"⚠️  Receptor NO tiene doblada en fecha de cesión (tiene: {jornadas_cesion_receptor})")
                
                if turnos_cesion_solicitante.exists():
                    print(f"⚠️  Solicitante NO debería tener turnos en fecha de cesión (tiene: {[t.jornada.nombre for t in turnos_cesion_solicitante]})")
                else:
                    print("✅ Solicitante descansa en fecha de cesión")
                
                if 'AM' in jornadas_pago_solicitante and 'PM' in jornadas_pago_solicitante:
                    print("✅ Solicitante tiene doblada en fecha de pago")
                else:
                    print(f"⚠️  Solicitante NO tiene doblada en fecha de pago (tiene: {jornadas_pago_solicitante})")
                
                if turnos_pago_receptor.exists():
                    print(f"⚠️  Receptor NO debería tener turnos en fecha de pago (tiene: {[t.jornada.nombre for t in turnos_pago_receptor]})")
                else:
                    print("✅ Receptor descansa en fecha de pago")
            else:
                print("ℹ️  Cesión parcial - verificar manualmente según reglas de negocio")
        
    else:
        print("⚠️  Esta solicitud no tiene detalle de doblada")
        
except SolicitudCambio.DoesNotExist:
    print(f"❌ No se encontró solicitud con ID {SOLICITUD_ID}")
except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
