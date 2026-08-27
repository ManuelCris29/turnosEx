"""
Tests para modelos de empleados
"""
from django.contrib.auth.models import User
from django.test import TestCase

from empleados.models import Empleado


class EmpleadoModelTest(TestCase):
    """Tests para el modelo Empleado"""
    
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
    
    def test_empleado_creacion(self):
        """Test que se puede crear un empleado"""
        self.assertIsNotNone(self.empleado.id)
        self.assertEqual(self.empleado.nombre, 'Test')
        self.assertEqual(self.empleado.apellido, 'User')
        self.assertTrue(self.empleado.activo)
    
    def test_empleado_str(self):
        """Test del método __str__"""
        expected = f"{self.empleado.nombre} {self.empleado.apellido} ({self.user.username})"
        self.assertEqual(str(self.empleado), expected)


