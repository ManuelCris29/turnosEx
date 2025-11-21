"""
Tests para servicios de solicitudes
"""
from django.test import TestCase
from django.contrib.auth.models import User
from empleados.models import Empleado, Jornada
from solicitudes.models import TipoSolicitudCambio, SolicitudCambio
from solicitudes.services.solicitud_service import SolicitudService
from turnos.models import AsignarJornadaExplorador
from datetime import date, timedelta


class SolicitudServiceTest(TestCase):
    """Tests para SolicitudService"""
    
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
            fecha_inicio=date.today() - timedelta(days=30)
        )
        AsignarJornadaExplorador.objects.create(
            explorador=self.empleado2,
            jornada=self.jornada_pm,
            fecha_inicio=date.today() - timedelta(days=30)
        )
        
        # Crear tipo de solicitud
        self.tipo = TipoSolicitudCambio.objects.create(
            nombre='CT',
            codigo_estrategia='CT',
            activo=True
        )
    
    def test_get_tipos_solicitud_activos(self):
        """Test que se pueden obtener tipos de solicitud activos"""
        tipos = SolicitudService.get_tipos_solicitud_activos()
        self.assertGreater(tipos.count(), 0)
        self.assertTrue(all(t.activo for t in tipos))
    
    def test_get_solicitudes_usuario(self):
        """Test que se pueden obtener solicitudes de un usuario"""
        # Crear solicitud
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=self.empleado1,
            explorador_receptor=self.empleado2,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=date.today() + timedelta(days=7)
        )
        
        # Obtener solicitudes del usuario
        user = self.empleado1.user
        solicitudes = SolicitudService.get_solicitudes_usuario(user)
        
        self.assertEqual(solicitudes.count(), 1)
        self.assertEqual(solicitudes.first(), solicitud)
    
    def test_get_solicitudes_pendientes(self):
        """Test que se pueden obtener solicitudes pendientes"""
        # Crear solicitud pendiente
        solicitud_pendiente = SolicitudCambio.objects.create(
            explorador_solicitante=self.empleado1,
            explorador_receptor=self.empleado2,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=date.today() + timedelta(days=7),
            estado='pendiente'
        )
        
        # Crear solicitud aprobada (no debe aparecer)
        solicitud_aprobada = SolicitudCambio.objects.create(
            explorador_solicitante=self.empleado1,
            explorador_receptor=self.empleado2,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=date.today() + timedelta(days=8),
            estado='aprobada'
        )
        
        # Obtener solicitudes pendientes
        pendientes = SolicitudService.get_solicitudes_pendientes()
        
        self.assertIn(solicitud_pendiente, pendientes)
        self.assertNotIn(solicitud_aprobada, pendientes)


