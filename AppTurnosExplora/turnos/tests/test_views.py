"""
Tests para vistas de turnos
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from empleados.models import Empleado


class MisTurnosViewTest(TestCase):
    """Tests para la vista Mis Turnos"""
    
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
    
    def test_mis_turnos_view_requiere_login(self):
        """Test que la vista requiere autenticación"""
        response = self.client.get(reverse('turnos:mis_turnos'))
        self.assertEqual(response.status_code, 302)  # Redirect a login
    
    def test_mis_turnos_view_con_login(self):
        """Test que la vista funciona con usuario autenticado"""
        self.client.login(username='testuser', password='test123')
        response = self.client.get(reverse('turnos:mis_turnos'))
        self.assertEqual(response.status_code, 200)


