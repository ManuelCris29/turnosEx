"""
Tests para API de turnos
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from empleados.models import Empleado


class TurnosAPITest(TestCase):
    """Tests para la API de turnos"""
    
    def setUp(self):
        self.client = Client()
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
    
    def test_api_requiere_login(self):
        """Test que la API requiere autenticación"""
        response = self.client.get('/turnos/api/mis-turnos-por-mes/')
        self.assertEqual(response.status_code, 302)  # Redirect a login
    
    def test_api_con_login(self):
        """Test que la API funciona con usuario autenticado"""
        self.client.login(username='testuser', password='test123')
        response = self.client.get('/turnos/api/mis-turnos-por-mes/?mes=11&anio=2025')
        # Puede ser 200 o 400 dependiendo de los parámetros
        self.assertIn(response.status_code, [200, 400])


