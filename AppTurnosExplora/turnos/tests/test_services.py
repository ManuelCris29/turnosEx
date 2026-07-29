"""
Tests para servicios de turnos
"""
from django.test import TestCase
from django.contrib.auth.models import User
from empleados.models import Empleado, Jornada
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from turnos.services.turno_service import TurnoService
from datetime import date, timedelta
from django.utils import timezone


class TurnoServiceTest(TestCase):
    """Tests para TurnoService"""
    
    def setUp(self):
        # Crear jornadas
        self.jornada_am = Jornada.objects.create(
            nombre='AM',
            hora_inicio='06:00:00',
            hora_fin='14:00:00'
        )
        self.jornada_pm = Jornada.objects.create(
            nombre='PM',
            hora_inicio='14:00:00',
            hora_fin='22:00:00'
        )
        
        # Crear sala
        self.sala = Sala.objects.create(
            nombre='Sala Test',
            activo=True
        )
        
        # Crear usuarios y empleados
        user1 = User.objects.create_user(username='test1', password='test123')
        user2 = User.objects.create_user(username='test2', password='test123')
        
        self.empleado1 = Empleado.objects.create(
            user=user1,
            nombre='Test',
            apellido='Uno',
            cedula='1111111111',
            activo=True
        )
        self.empleado2 = Empleado.objects.create(
            user=user2,
            nombre='Test',
            apellido='Dos',
            cedula='2222222222',
            activo=True
        )
        
        # Asignar jornadas
        AsignarJornadaExplorador.objects.create(
            explorador=self.empleado1,
            jornada=self.jornada_am,
            fecha_inicio=timezone.localdate() - timedelta(days=30)
        )
        AsignarJornadaExplorador.objects.create(
            explorador=self.empleado2,
            jornada=self.jornada_pm,
            fecha_inicio=timezone.localdate() - timedelta(days=30)
        )
    
    def test_get_exploradores_por_jornada(self):
        """Test que se pueden obtener exploradores por jornada"""
        fecha = str(timezone.localdate())
        resultado = TurnoService.get_exploradores_por_jornada(fecha)
        
        self.assertIn('am', resultado)
        self.assertIn('pm', resultado)
        self.assertIsInstance(resultado['am'], list)
        self.assertIsInstance(resultado['pm'], list)
    
    def test_get_exploradores_por_jornada_rango(self):
        """Test que se pueden obtener exploradores por jornada en un rango"""
        fecha_inicio = str(timezone.localdate())
        fecha_fin = str(timezone.localdate() + timedelta(days=7))
        
        resultado = TurnoService.get_exploradores_por_jornada_rango(
            fecha_inicio,
            fecha_fin
        )
        
        self.assertIsInstance(resultado, dict)
        self.assertEqual(len(resultado), 8)  # 7 días + 1 día inicial


