"""
Fixtures globales compartidas para todos los tests
"""
import pytest
from django.contrib.auth.models import User
from empleados.models import Empleado


@pytest.fixture
def user_test(db):
    """Fixture global para usuario de prueba"""
    return User.objects.create_user(
        username='testuser',
        email='test@test.com',
        password='test123'
    )


@pytest.fixture
def empleado_test(db, user_test):
    """Fixture global para empleado de prueba"""
    return Empleado.objects.create(
        user=user_test,
        nombre='Test',
        apellido='User',
        cedula='1234567890',
        activo=True
    )


