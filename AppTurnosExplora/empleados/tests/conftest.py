"""
Fixtures compartidas para tests de empleados
"""
import pytest
from django.contrib.auth.models import User
from empleados.models import Empleado


@pytest.fixture
def empleado_test(db):
    """Fixture para empleado de prueba"""
    user = User.objects.create_user(
        username='test_empleado',
        email='empleado@test.com',
        password='test123'
    )
    empleado = Empleado.objects.create(
        user=user,
        nombre='Test',
        apellido='Empleado',
        cedula='1234567890',
        activo=True
    )
    return empleado


