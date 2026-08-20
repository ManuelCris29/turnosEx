"""
Tests para modelos de solicitudes
"""
from django.test import TestCase
from django.contrib.auth.models import User
from empleados.models import Empleado, Jornada
from solicitudes.models import TipoSolicitudCambio, SolicitudCambio
from turnos.models import AsignarJornadaExplorador
from datetime import timedelta
from django.utils import timezone


class TipoSolicitudCambioModelTest(TestCase):
    """Tests para el modelo TipoSolicitudCambio"""
    
    def setUp(self):
        self.tipo = TipoSolicitudCambio.objects.create(
            nombre='CT',
            codigo_estrategia='CT',
            activo=True,
            genera_deuda=False
        )
    
    def test_tipo_solicitud_creacion(self):
        """Test que se puede crear un tipo de solicitud"""
        self.assertIsNotNone(self.tipo.id)
        self.assertEqual(self.tipo.nombre, 'CT')
        self.assertEqual(self.tipo.codigo_estrategia, 'CT')
        self.assertTrue(self.tipo.activo)
    
    def test_tipo_solicitud_str(self):
        """Test del método __str__"""
        self.assertEqual(str(self.tipo), 'CT')


class SolicitudCambioModelTest(TestCase):
    """Tests para el modelo SolicitudCambio"""
    
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
        
        # Crear tipo de solicitud
        self.tipo = TipoSolicitudCambio.objects.create(
            nombre='CT',
            codigo_estrategia='CT',
            activo=True
        )
        
        # Crear solicitud
        self.solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=self.empleado1,
            explorador_receptor=self.empleado2,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=timezone.localdate() + timedelta(days=7),
            comentario='Test solicitud',
            estado='pendiente'
        )
    
    def test_solicitud_creacion(self):
        """Test que se puede crear una solicitud"""
        self.assertIsNotNone(self.solicitud.id)
        self.assertEqual(self.solicitud.estado, 'pendiente')
        self.assertEqual(self.solicitud.explorador_solicitante, self.empleado1)
        self.assertEqual(self.solicitud.explorador_receptor, self.empleado2)
    
    def test_solicitud_str(self):
        """Test del método __str__"""
        expected = (
            f"{self.tipo.nombre} - {self.empleado1} a {self.empleado2} "
            f"({self.solicitud.fecha_cambio_turno})"
        )
        self.assertEqual(str(self.solicitud), expected)
    
    def test_solicitud_estado_default(self):
        """Test que el estado por defecto es 'pendiente'"""
        nueva_solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=self.empleado1,
            explorador_receptor=self.empleado2,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=timezone.localdate() + timedelta(days=7)
        )
        self.assertEqual(nueva_solicitud.estado, 'pendiente')


