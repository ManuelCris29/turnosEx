"""
Tests para modelos de turnos
"""
from django.test import TestCase
from django.contrib.auth.models import User
from empleados.models import Empleado, Jornada
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from datetime import date, timedelta
from django.utils import timezone


class TurnoModelTest(TestCase):
    """Tests para el modelo Turno"""
    
    def setUp(self):
        # Crear jornada
        self.jornada = Jornada.objects.create(
            nombre='AM',
            hora_inicio='06:00:00',
            hora_fin='14:00:00'
        )
        
        # Crear sala
        self.sala = Sala.objects.create(
            nombre='Sala Test',
            activo=True
        )
        
        # Crear usuario y empleado
        user = User.objects.create_user(username='test', password='test123')
        self.empleado = Empleado.objects.create(
            user=user,
            nombre='Test',
            apellido='User',
            cedula='1234567890',
            activo=True
        )
        
        # Crear turno
        self.turno = Turno.objects.create(
            explorador=self.empleado,
            jornada=self.jornada,
            sala=self.sala,
            fecha=timezone.localdate()
        )
    
    def test_turno_creacion(self):
        """Test que se puede crear un turno"""
        self.assertIsNotNone(self.turno.id)
        self.assertEqual(self.turno.explorador, self.empleado)
        self.assertEqual(self.turno.jornada, self.jornada)
        self.assertEqual(self.turno.sala, self.sala)
    
    def test_turno_str(self):
        """Test del método __str__"""
        expected = f"{self.empleado.user.username} - {timezone.localdate()}"
        self.assertEqual(str(self.turno), expected)


class AsignarJornadaExploradorModelTest(TestCase):
    """Tests para el modelo AsignarJornadaExplorador"""
    
    def setUp(self):
        # Crear jornada
        self.jornada = Jornada.objects.create(
            nombre='AM',
            hora_inicio='06:00:00',
            hora_fin='14:00:00'
        )
        
        # Crear usuario y empleado
        user = User.objects.create_user(username='test', password='test123')
        self.empleado = Empleado.objects.create(
            user=user,
            nombre='Test',
            apellido='User',
            cedula='1234567890',
            activo=True
        )
        
        # Crear asignación
        self.asignacion = AsignarJornadaExplorador.objects.create(
            explorador=self.empleado,
            jornada=self.jornada,
            fecha_inicio=timezone.localdate() - timedelta(days=30)
        )
    
    def test_asignacion_creacion(self):
        """Test que se puede crear una asignación"""
        self.assertIsNotNone(self.asignacion.id)
        self.assertEqual(self.asignacion.explorador, self.empleado)
        self.assertEqual(self.asignacion.jornada, self.jornada)


