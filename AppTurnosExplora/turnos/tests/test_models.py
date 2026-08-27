"""
Tests para modelos de turnos
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, Jornada
from turnos.models import AsignarJornadaExplorador, Sala, Turno


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




class TurnoTipoCambioConstraintTest(TestCase):
    """
    La CheckConstraint `turno_tipo_cambio_valido` es la unica garantia real de que
    no entre un valor inventado en `Turno.tipo_cambio`: los `choices` de Django
    solo se comprueban en `full_clean()`, y ningun servicio del proyecto lo llama
    antes de guardar.
    """

    def setUp(self):
        self.jornada = Jornada.objects.create(
            nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.sala = Sala.objects.create(nombre='Sala Test', activo=True)
        user = User.objects.create_user(username='tc_test', password='test123')
        self.empleado = Empleado.objects.create(
            user=user, nombre='Test', apellido='User', cedula='9876543210', activo=True)

    def _crear(self, tipo_cambio, dia_offset=0):
        return Turno.objects.create(
            explorador=self.empleado, jornada=self.jornada, sala=self.sala,
            fecha=timezone.localdate() + timedelta(days=dia_offset),
            tipo_cambio=tipo_cambio,
        )

    def test_acepta_todos_los_valores_del_vocabulario(self):
        from core.constants import TipoCambioTurno
        for i, valor in enumerate(TipoCambioTurno.TODOS):
            with self.subTest(tipo_cambio=valor):
                self.assertIsNotNone(self._crear(valor, dia_offset=i).id)

    def test_acepta_null(self):
        """Un turno normal, sin cambio de por medio."""
        self.assertIsNotNone(self._crear(None, dia_offset=50).id)

    def test_rechaza_un_valor_inventado(self):
        from django.db import IntegrityError, transaction
        # 'DOBLADA PERMANENTE' es el `nombre` de la maestra; en Turno se escribe
        # 'DOBLADA PERM'. Confundirlos era exactamente el fallo silencioso de antes.
        #
        # No se prueba con 'doblada' en minuscula: la colacion por defecto de MySQL
        # es case-insensitive, asi que la constraint lo acepta como 'DOBLADA'. Los
        # filtros del ORM comparan con esa misma colacion y tampoco lo notarian; lo
        # que si distinguiria mayusculas es un `t.tipo_cambio == 'DOBLADA'` en
        # Python. La constraint no cubre ese caso.
        for invalido in ('DOBLADA PERMANENTE', 'CAMBIO TURNO', 'TYPO', 'DOBLADA PERMA'):
            with self.subTest(tipo_cambio=invalido):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        self._crear(invalido, dia_offset=60)
