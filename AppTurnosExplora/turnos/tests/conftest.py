"""
Fixtures compartidas para tests de turnos
"""
import pytest
from django.contrib.auth.models import User
from empleados.models import Empleado, Jornada
from turnos.models import AsignarJornadaExplorador, Turno, Sala
from datetime import date, timedelta


@pytest.fixture
def jornada_am(db):
    """Fixture para jornada AM"""
    jornada, _ = Jornada.objects.get_or_create(
        nombre='AM',
        defaults={
            'hora_inicio': '06:00:00',
            'hora_fin': '14:00:00'
        }
    )
    return jornada


@pytest.fixture
def jornada_pm(db):
    """Fixture para jornada PM"""
    jornada, _ = Jornada.objects.get_or_create(
        nombre='PM',
        defaults={
            'hora_inicio': '14:00:00',
            'hora_fin': '22:00:00'
        }
    )
    return jornada


@pytest.fixture
def sala_test(db):
    """Fixture para sala de prueba"""
    sala, _ = Sala.objects.get_or_create(
        nombre='Sala Test',
        defaults={
            'activa': True
        }
    )
    return sala


@pytest.fixture
def empleado_con_jornada(db, jornada_am):
    """Fixture para empleado con jornada asignada"""
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
    AsignarJornadaExplorador.objects.create(
        explorador=empleado,
        jornada=jornada_am,
        fecha_inicio=date.today() - timedelta(days=30)
    )
    return empleado


