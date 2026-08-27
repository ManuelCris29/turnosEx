"""
Tests para servicios de empleados
"""
from django.contrib.auth.models import User
from django.test import TestCase

from empleados.models import Empleado
from empleados.services.empleado_service import EmpleadoService


class EmpleadoServiceTest(TestCase):
    """Tests para EmpleadoService"""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='test123'
        )
        self.empleado = Empleado.objects.create(
            user=self.user,
            nombre='Test',
            apellido='User',
            cedula='1234567890',
            activo=True
        )
    
    def test_service_existe(self):
        """Test que el servicio existe y se puede importar"""
        self.assertIsNotNone(EmpleadoService)


