"""
Script temporal para validar jornadas predeterminadas y turnos creados
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'AppTurnosExplora.config.settings')
django.setup()

from django.contrib.auth.models import User
from empleados.models import Empleado
from turnos.models import Turno, AsignarJornadaExplorador
from solicitudes.models import SolicitudCambio
from solicitudes.services.solicitud_service import SolicitudService
from datetime import date

fecha = date(2025, 11, 17)

print("=" * 60)
print("VALIDACION DE JORNADAS Y TURNOS")
print("=" * 60)

# Obtener empleados
mariana = User.objects.get(username='mariana.villa').empleado
jhon = User.objects.get(username='jhon.areiza').empleado
manuel = User.objects.get(username='manuel.moreno').empleado

print("\n1. JORNADAS PREDETERMINADAS (AsignarJornadaExplorador):")
print("-" * 60)
asign_mariana = AsignarJornadaExplorador.objects.filter(
    explorador=mariana, 
    fecha_inicio__lte=fecha
).order_by('-fecha_inicio').first()
print(f"Mariana (ID: {mariana.id}): {asign_mariana.jornada.nombre if asign_mariana else 'N/A'}")

asign_jhon = AsignarJornadaExplorador.objects.filter(
    explorador=jhon, 
    fecha_inicio__lte=fecha
).order_by('-fecha_inicio').first()
print(f"Jhon (ID: {jhon.id}): {asign_jhon.jornada.nombre if asign_jhon else 'N/A'}")

asign_manuel = AsignarJornadaExplorador.objects.filter(
    explorador=manuel, 
    fecha_inicio__lte=fecha
).order_by('-fecha_inicio').first()
print(f"Manuel (ID: {manuel.id}): {asign_manuel.jornada.nombre if asign_manuel else 'N/A'}")

print("\n2. TURNOS CREADOS EN LA PRUEBA:")
print("-" * 60)
turno_mariana = Turno.objects.filter(explorador=mariana, fecha=fecha).first()
turno_jhon = Turno.objects.filter(explorador=jhon, fecha=fecha).first()
turno_manuel = Turno.objects.filter(explorador=manuel, fecha=fecha).first()

print(f"Mariana - Turno ID: {turno_mariana.id if turno_mariana else 'N/A'}, Jornada: {turno_mariana.jornada.nombre if turno_mariana else 'N/A'}")
print(f"Jhon - Turno ID: {turno_jhon.id if turno_jhon else 'N/A'}, Jornada: {turno_jhon.jornada.nombre if turno_jhon else 'N/A'}")
print(f"Manuel - Turno ID: {turno_manuel.id if turno_manuel else 'N/A'}, Jornada: {turno_manuel.jornada.nombre if turno_manuel else 'N/A'}")

print("\n3. JORNADAS OBTENIDAS POR get_jornada_explorador_fecha:")
print("-" * 60)
jornada_mariana = SolicitudService.get_jornada_explorador_fecha(mariana.id, fecha.strftime('%Y-%m-%d'))
jornada_jhon = SolicitudService.get_jornada_explorador_fecha(jhon.id, fecha.strftime('%Y-%m-%d'))
jornada_manuel = SolicitudService.get_jornada_explorador_fecha(manuel.id, fecha.strftime('%Y-%m-%d'))

print(f"Mariana: {jornada_mariana.nombre if jornada_mariana else 'N/A'}")
print(f"Jhon: {jornada_jhon.nombre if jornada_jhon else 'N/A'}")
print(f"Manuel: {jornada_manuel.nombre if jornada_manuel else 'N/A'}")

print("\n4. SOLICITUDES DE LA PRUEBA:")
print("-" * 60)
solicitudes = SolicitudCambio.objects.filter(fecha_cambio_turno=fecha).order_by('id')
for s in solicitudes:
    print(f"ID: {s.id}")
    print(f"  Solicitante: {s.explorador_solicitante.nombre} (ID: {s.explorador_solicitante.id})")
    print(f"  Receptor: {s.explorador_receptor.nombre} (ID: {s.explorador_receptor.id})")
    print(f"  Estado: {s.estado}")
    print(f"  Turno origen: {s.turno_origen.id if s.turno_origen else 'N/A'}")
    print(f"  Turno destino: {s.turno_destino.id if s.turno_destino else 'N/A'}")
    print(f"  Solicitud origen: {s.solicitud_origen.id if s.solicitud_origen else 'N/A'}")
    print()

print("\n5. ANALISIS:")
print("-" * 60)
print("Primer cambio (Mariana->Jhon):")
print(f"  - Mariana deberia recibir jornada de Jhon: {asign_jhon.jornada.nombre if asign_jhon else 'N/A'}")
print(f"  - Jhon deberia recibir jornada de Mariana: {asign_mariana.jornada.nombre if asign_mariana else 'N/A'}")
print(f"  - Turno Mariana tiene: {turno_mariana.jornada.nombre if turno_mariana else 'N/A'}")
print(f"  - Turno Jhon tiene: {turno_jhon.jornada.nombre if turno_jhon else 'N/A'}")

if turno_mariana and turno_jhon:
    if turno_mariana.jornada.nombre == (asign_jhon.jornada.nombre if asign_jhon else None):
        print("  [OK] Turno de Mariana tiene la jornada correcta")
    else:
        print("  [ERROR] Turno de Mariana NO tiene la jornada correcta")
    
    if turno_jhon.jornada.nombre == (asign_mariana.jornada.nombre if asign_mariana else None):
        print("  [OK] Turno de Jhon tiene la jornada correcta")
    else:
        print("  [ERROR] Turno de Jhon NO tiene la jornada correcta")

print("\n" + "=" * 60)

