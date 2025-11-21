"""
Fixtures compartidas para tests de solicitudes
"""
import pytest
from django.contrib.auth.models import User
from empleados.models import Empleado, Jornada
from solicitudes.models import TipoSolicitudCambio, SolicitudCambio
from turnos.models import AsignarJornadaExplorador
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
def tipo_cambio_ct(db):
    """Fixture para tipo de cambio CT"""
    tipo, _ = TipoSolicitudCambio.objects.get_or_create(
        nombre='CT',
        defaults={
            'codigo_estrategia': 'CT',
            'activo': True,
            'genera_deuda': False
        }
    )
    return tipo


@pytest.fixture
def empleado_solicitante(db, jornada_am):
    """Fixture para empleado solicitante"""
    user = User.objects.create_user(
        username='test_solicitante',
        email='solicitante@test.com',
        password='test123'
    )
    empleado = Empleado.objects.create(
        user=user,
        nombre='Test',
        apellido='Solicitante',
        cedula='1234567890',
        activo=True
    )
    # Asignar jornada AM
    AsignarJornadaExplorador.objects.create(
        explorador=empleado,
        jornada=jornada_am,
        fecha_inicio=date.today() - timedelta(days=30)
    )
    return empleado


@pytest.fixture
def empleado_receptor(db, jornada_pm):
    """Fixture para empleado receptor"""
    user = User.objects.create_user(
        username='test_receptor',
        email='receptor@test.com',
        password='test123'
    )
    empleado = Empleado.objects.create(
        user=user,
        nombre='Test',
        apellido='Receptor',
        cedula='0987654321',
        activo=True
    )
    # Asignar jornada PM
    AsignarJornadaExplorador.objects.create(
        explorador=empleado,
        jornada=jornada_pm,
        fecha_inicio=date.today() - timedelta(days=30)
    )
    return empleado


@pytest.fixture
def fecha_futura():
    """Fixture para fecha futura de prueba"""
    return date.today() + timedelta(days=7)


