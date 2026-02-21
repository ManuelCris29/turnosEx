#!/usr/bin/env python
"""Script rápido para buscar usuarios con 'marco' en el username."""

import os
import sys
import django

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from empleados.models import Empleado

# Buscar todos los usuarios con 'marco'
users = User.objects.filter(username__icontains='marco')
print(f"Usuarios encontrados con 'marco': {users.count()}")
for user in users:
    print(f"  - {user.username} (ID: {user.id})")
    if hasattr(user, 'empleado'):
        print(f"    Empleado: {user.empleado.nombre} {user.empleado.apellido} (ID: {user.empleado.id})")
    else:
        print(f"    Sin empleado asociado")

# Buscar también por nombre/apellido
empleados = Empleado.objects.filter(nombre__icontains='marco') | Empleado.objects.filter(apellido__icontains='marco')
print(f"\nEmpleados encontrados con 'marco' en nombre/apellido: {empleados.count()}")
for emp in empleados:
    print(f"  - {emp.nombre} {emp.apellido} (ID: {emp.id})")
    if hasattr(emp, 'user'):
        print(f"    Username: {emp.user.username}")



