#!/usr/bin/env python
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from empleados.models import Empleado
from solicitudes.models import SolicitudCambio
from django.db import models

# Buscar Luisa
luisa = Empleado.objects.filter(user__username='luisa.perez').first()
print(f"=== LUISA PEREZ ===")
print(f"ID: {luisa.id if luisa else None}")
print(f"Nombre: {luisa.nombre if luisa else None} {luisa.apellido if luisa else None}")
print(f"Supervisor: {luisa.supervisor.nombre if luisa and luisa.supervisor else None}")

if not luisa:
    print("Luisa no encontrada")
    sys.exit(1)

print("\n=== SOLICITUDES PENDIENTES COMO RECEPTOR ===")
receptor_pendientes = SolicitudCambio.objects.filter(
    explorador_receptor=luisa, 
    estado='pendiente', 
    aprobado_receptor=False
)
print(f"Count: {receptor_pendientes.count()}")
for s in receptor_pendientes:
    print(f"ID: {s.id}, Solicitante: {s.explorador_solicitante.nombre}, Fecha: {s.fecha_cambio_turno}, Aprobado Receptor: {s.aprobado_receptor}")

print("\n=== SOLICITUDES PENDIENTES COMO SUPERVISOR ===")
supervisor_pendientes = SolicitudCambio.objects.filter(
    explorador_solicitante__supervisor=luisa, 
    estado='pendiente', 
    aprobado_supervisor=False
)
print(f"Count: {supervisor_pendientes.count()}")
for s in supervisor_pendientes:
    print(f"ID: {s.id}, Solicitante: {s.explorador_solicitante.nombre}, Receptor: {s.explorador_receptor.nombre}, Fecha: {s.fecha_cambio_turno}, Aprobado Supervisor: {s.aprobado_supervisor}")

print("\n=== TODAS LAS SOLICITUDES DE LUISA (CUALQUIER ESTADO) ===")
todas_solicitudes = SolicitudCambio.objects.filter(
    models.Q(explorador_receptor=luisa) | models.Q(explorador_solicitante=luisa)
).order_by('-fecha_solicitud')
print(f"Count: {todas_solicitudes.count()}")
for s in todas_solicitudes:
    rol = "RECEPTOR" if s.explorador_receptor == luisa else "SOLICITANTE"
    print(f"ID: {s.id}, Rol: {rol}, Estado: {s.estado}, Fecha: {s.fecha_cambio_turno}, Aprobado Receptor: {s.aprobado_receptor}, Aprobado Supervisor: {s.aprobado_supervisor}")

print("\n=== SOLICITUDES PENDIENTES EN GENERAL ===")
todas_pendientes = SolicitudCambio.objects.filter(estado='pendiente')
print(f"Count total pendientes: {todas_pendientes.count()}")
for s in todas_pendientes:
    print(f"ID: {s.id}, Solicitante: {s.explorador_solicitante.nombre}, Receptor: {s.explorador_receptor.nombre}, Fecha: {s.fecha_cambio_turno}")
