"""
Tests de integración para flujos completos de solicitudes
"""
from django.test import TestCase
from django.contrib.auth.models import User
from empleados.models import Empleado, Jornada
from solicitudes.models import TipoSolicitudCambio, SolicitudCambio
from solicitudes.services.solicitud_service import SolicitudService
from turnos.models import AsignarJornadaExplorador, Turno
from datetime import date, timedelta
from django.utils import timezone


class SolicitudFlowIntegrationTest(TestCase):
    """Tests de integración para el flujo completo de solicitudes"""
    
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
        user_supervisor = User.objects.create_user(username='supervisor', password='test123')
        
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
        self.supervisor = Empleado.objects.create(
            user=user_supervisor,
            nombre='Supervisor',
            apellido='Test',
            cedula='3333333333',
            activo=True
        )
        
        # Asignar supervisor
        self.empleado1.supervisor = self.supervisor
        self.empleado1.save()
        
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
        
        self.fecha_cambio = timezone.localdate() + timedelta(days=7)
    
    def test_flujo_completo_creacion_solicitud(self):
        """Test del flujo completo de creación de solicitud"""
        # Crear solicitud
        solicitud, mensaje = SolicitudService.crear_solicitud_cambio(
            explorador_solicitante=self.empleado1,
            explorador_receptor=self.empleado2,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=self.fecha_cambio,
            comentario='Test integración'
        )
        
        # Verificar que se creó
        self.assertIsNotNone(solicitud)
        self.assertEqual(solicitud.estado, 'pendiente')
        self.assertEqual(solicitud.explorador_solicitante, self.empleado1)
        self.assertEqual(solicitud.explorador_receptor, self.empleado2)
        
        # Verificar que existe en BD
        solicitud_db = SolicitudCambio.objects.get(id=solicitud.id)
        self.assertEqual(solicitud_db, solicitud)

    def test_creacion_solicitud_sin_comentario_falla(self):
        """No debe permitir crear una solicitud de cambio sin comentario."""
        solicitud, mensaje = SolicitudService.crear_solicitud_cambio(
            explorador_solicitante=self.empleado1,
            explorador_receptor=self.empleado2,
            tipo_cambio=self.tipo,
            fecha_cambio_turno=self.fecha_cambio,
            comentario=''  # comentario vacío
        )
        self.assertIsNone(solicitud)
        self.assertIsInstance(mensaje, str)
        self.assertNotEqual(mensaje, '')


