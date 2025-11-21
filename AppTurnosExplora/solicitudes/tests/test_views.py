"""
Tests para vistas de solicitudes
"""
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from empleados.models import Empleado


class SolicitudesViewTest(TestCase):
    """Tests para la vista de solicitudes"""
    
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
    
    def test_solicitudes_view_requiere_login(self):
        """Test que la vista requiere autenticación"""
        response = self.client.get(reverse('solicitudes:list'))
        self.assertEqual(response.status_code, 302)  # Redirect a login
    
    def test_solicitudes_view_con_login(self):
        """Test que la vista funciona con usuario autenticado"""
        self.client.login(username='testuser', password='test123')
        response = self.client.get(reverse('solicitudes:list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'solicitudes')


