"""
Script de diagnóstico para verificar la doblada de jhon.areiza el 14 de febrero de 2026
"""
import os
import sys
import django

# Configurar Django
# El script está en AppTurnosExplora/scripts/, necesitamos ir al directorio padre (AppTurnosExplora)
script_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.dirname(script_dir)  # AppTurnosExplora
base_dir = os.path.dirname(app_dir)  # C:\appTurnos

# Agregar ambos directorios al path
sys.path.insert(0, base_dir)
sys.path.insert(0, app_dir)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AppTurnosExplora.config.settings')
django.setup()

from datetime import date
from turnos.models import Turno
from solicitudes.models import SolicitudCambio
from empleados.models import Empleado
from django.contrib.auth.models import User

def diagnosticar_doblada_jhon_14_feb():
    """Diagnosticar la situación de jhon.areiza el 14 de febrero de 2026"""
    
    fecha = date(2026, 2, 14)
    
def diagnosticar_doblada_jhon_28_feb():
    """Diagnosticar la situación de jhon.areiza el 28 de febrero de 2026"""
    
    fecha = date(2026, 2, 28)
    # Buscar por user.username
    user = User.objects.filter(username='jhon.areiza').first()
    if user:
        usuario = user.empleado if hasattr(user, 'empleado') else None
    else:
        usuario = None
    
    if not usuario:
        print("❌ ERROR: No se encontró el usuario jhon.areiza")
        return
    
    print(f"\n{'='*80}")
    print(f"DIAGNÓSTICO: jhon.areiza - {fecha}")
    print(f"{'='*80}\n")
    
    print(f"Usuario: {usuario.nombre} {usuario.apellido} (ID: {usuario.id})")
    print(f"Fecha: {fecha}\n")
    
    # 1. Verificar turnos en esa fecha
    print("1️⃣ TURNOS EN LA FECHA:")
    print("-" * 80)
    turnos = Turno.objects.filter(explorador=usuario, fecha=fecha).select_related('jornada')
    if turnos.exists():
        jornadas = []
        for turno in turnos:
            jornada_nombre = turno.jornada.nombre if turno.jornada else 'Sin jornada'
            jornadas.append(jornada_nombre)
            print(f"   ✅ Turno ID: {turno.id} - Jornada: {jornada_nombre}")
            print(f"      Horario: {turno.hora_inicio} - {turno.hora_fin}")
            print(f"      Es turno virtual: {turno.es_turno_virtual}")
        
        es_doblada = 'AM' in jornadas and 'PM' in jornadas
        print(f"\n   📊 Resumen: {len(jornadas)} turno(s) - {', '.join(jornadas)}")
        print(f"   {'✅ ES DOBLADA (AM + PM)' if es_doblada else '❌ NO ES DOBLADA (solo una jornada)'}")
    else:
        print("   ❌ No tiene turnos asignados en esta fecha")
    
    # 2. Verificar doblada como solicitante
    print("\n2️⃣ DOBLADA COMO SOLICITANTE:")
    print("-" * 80)
    doblada_solicitante = SolicitudCambio.objects.filter(
        explorador_solicitante=usuario,
        tipo_cambio__nombre='DOBLADA',
        fecha_cambio_turno=fecha,
        estado='aprobada'
    ).select_related('tipo_cambio', 'explorador_receptor', 'doblada').first()
    
    if doblada_solicitante:
        print(f"   ✅ Tiene doblada como SOLICITANTE")
        print(f"      Solicitud ID: {doblada_solicitante.id}")
        print(f"      Estado: {doblada_solicitante.estado}")
        print(f"      Receptor: {doblada_solicitante.explorador_receptor.nombre} {doblada_solicitante.explorador_receptor.apellido}")
        if doblada_solicitante.doblada:
            print(f"      Fecha de pago: {doblada_solicitante.doblada.fecha_pago}")
            print(f"      Minutos deuda: {doblada_solicitante.doblada.minutos_deuda}")
    else:
        print("   ❌ No tiene doblada como solicitante")
    
    # 3. Verificar doblada como receptor
    print("\n3️⃣ DOBLADA COMO RECEPTOR:")
    print("-" * 80)
    doblada_receptor = SolicitudCambio.objects.filter(
        explorador_receptor=usuario,
        tipo_cambio__nombre='DOBLADA',
        doblada__fecha_pago=fecha,
        estado='aprobada'
    ).select_related('tipo_cambio', 'explorador_solicitante', 'doblada').first()
    
    if doblada_receptor:
        print(f"   ✅ Tiene doblada como RECEPTOR")
        print(f"      Solicitud ID: {doblada_receptor.id}")
        print(f"      Estado: {doblada_receptor.estado}")
        print(f"      Solicitante: {doblada_receptor.explorador_solicitante.nombre} {doblada_receptor.explorador_solicitante.apellido}")
        print(f"      Fecha de cesión: {doblada_receptor.fecha_cambio_turno}")
        if doblada_receptor.doblada:
            print(f"      Fecha de pago: {doblada_receptor.doblada.fecha_pago}")
            print(f"      Minutos deuda: {doblada_receptor.doblada.minutos_deuda}")
    else:
        print("   ❌ No tiene doblada como receptor")
    
    # 4. Verificar todas las solicitudes relacionadas (cualquier estado)
    print("\n4️⃣ TODAS LAS SOLICITUDES RELACIONADAS (cualquier estado):")
    print("-" * 80)
    todas_solicitudes = SolicitudCambio.objects.filter(
        tipo_cambio__nombre='DOBLADA'
    ).filter(
        (Q(explorador_solicitante=usuario, fecha_cambio_turno=fecha) |
         Q(explorador_receptor=usuario, doblada__fecha_pago=fecha))
    ).select_related('tipo_cambio', 'explorador_solicitante', 'explorador_receptor', 'doblada')
    
    if todas_solicitudes.exists():
        for solicitud in todas_solicitudes:
            rol = "SOLICITANTE" if solicitud.explorador_solicitante == usuario else "RECEPTOR"
            print(f"   📋 Solicitud ID: {solicitud.id} - Rol: {rol}")
            print(f"      Estado: {solicitud.estado}")
            print(f"      Fecha cesión: {solicitud.fecha_cambio_turno}")
            if solicitud.doblada:
                print(f"      Fecha pago: {solicitud.doblada.fecha_pago}")
    else:
        print("   ❌ No hay solicitudes relacionadas")
    
    # 5. Análisis y recomendación
    print("\n5️⃣ ANÁLISIS Y RECOMENDACIÓN:")
    print("-" * 80)
    
    tiene_turnos = turnos.exists()
    tiene_doblada_solicitante = doblada_solicitante is not None
    tiene_doblada_receptor = doblada_receptor is not None
    
    if tiene_turnos and (tiene_doblada_solicitante or tiene_doblada_receptor):
        print("   ✅ CORRECTO: Tiene turnos Y tiene doblada aprobada")
        print("      → El sistema DEBE mostrar 'Doblada Existente Detectada'")
        print("      → Debe mostrar opciones de cesión parcial/total")
    elif tiene_turnos and not tiene_doblada_solicitante and not tiene_doblada_receptor:
        print("   ⚠️ INCONSISTENCIA: Tiene turnos pero NO tiene doblada aprobada")
        print("      → Es su jornada normal (no doblada)")
        print("      → El sistema NO debe mostrar 'Doblada Existente Detectada'")
    elif not tiene_turnos and tiene_doblada_receptor:
        print("   ❌ ERROR CRÍTICO: Tiene doblada como receptor pero NO tiene turnos")
        print("      → Inconsistencia de datos - falta generar turnos")
    elif not tiene_turnos and tiene_doblada_solicitante:
        print("   ✅ CORRECTO: Tiene doblada como solicitante (cedió su jornada)")
        print("      → Está descansando - no debe tener turnos")
    else:
        print("   ✅ CORRECTO: No tiene turnos ni doblada")
        print("      → Puede solicitar doblada normalmente")
    
    print(f"\n{'='*80}\n")

if __name__ == '__main__':
    from django.db.models import Q
    diagnosticar_doblada_jhon_14_feb()

