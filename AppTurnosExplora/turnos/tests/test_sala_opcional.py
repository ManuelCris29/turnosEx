"""
Tests para la sala OPCIONAL en los turnos.

La sala es informativa: dice en qué espacio tiene competencia el explorador, pero NO
condiciona el turno. Antes `obtener_sala_explorador_fecha` lanzaba ValidationError cuando el
explorador no tenía `CompetenciaEmpleado`, y eso hacía fallar la aprobación de solicitudes
legítimas (caso real: quien pasa de supervisor a explorador conserva jornada pero no
competencia, y el supervisor veía "no tiene sala asignada" al aprobar).
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import CompetenciaEmpleado, Empleado, Jornada, Sala
from turnos.models import Turno
from turnos.services.doblada_turno_service import DobladaTurnoService
from turnos.services.turno_service import TurnoService


class SalaOpcionalTest(TestCase):
    """La ausencia de sala no bloquea el turno y se muestra como 'Por asignar'."""

    def setUp(self):
        self.jornada_am = Jornada.objects.create(
            nombre='AM', hora_inicio='08:00:00', hora_fin='13:00:00'
        )
        self.jornada_pm = Jornada.objects.create(
            nombre='PM', hora_inicio='12:30:00', hora_fin='17:30:00'
        )
        self.sala = Sala.objects.create(nombre='Sala Test', activo=True)

        # Explorador SIN competencia: reproduce el caso que fallaba.
        self.sin_sala = Empleado.objects.create(
            user=User.objects.create_user(username='sin_sala', password='x'),
            nombre='Sin', apellido='Sala', cedula='9000001', activo=True,
        )
        # Explorador CON competencia: control, debe seguir viendo su sala.
        self.con_sala = Empleado.objects.create(
            user=User.objects.create_user(username='con_sala', password='x'),
            nombre='Con', apellido='Sala', cedula='9000002', activo=True,
        )
        CompetenciaEmpleado.objects.create(empleado=self.con_sala, sala=self.sala)

        self.fecha = timezone.localdate() + timedelta(days=7)

    def test_sin_competencia_devuelve_none_en_vez_de_lanzar_error(self):
        """El corazón del arreglo: sin sala NO es un error, es None."""
        self.assertIsNone(
            DobladaTurnoService.obtener_sala_explorador_fecha(self.sin_sala, self.fecha)
        )

    def test_con_competencia_sigue_devolviendo_su_sala(self):
        """El arreglo no debe degradar a quien sí tiene la competencia cargada."""
        self.assertEqual(
            DobladaTurnoService.obtener_sala_explorador_fecha(self.con_sala, self.fecha),
            self.sala,
        )

    def test_turno_del_dia_tiene_prioridad_sobre_la_competencia(self):
        """La prioridad 1 (sala del turno existente) se mantiene intacta."""
        otra = Sala.objects.create(nombre='Otra Sala', activo=True)
        Turno.objects.create(
            explorador=self.con_sala, fecha=self.fecha, jornada=self.jornada_am, sala=otra
        )
        self.assertEqual(
            DobladaTurnoService.obtener_sala_explorador_fecha(self.con_sala, self.fecha),
            otra,
        )

    def test_se_puede_crear_un_turno_sin_sala(self):
        """Lo que la BD prohibía antes (columna NOT NULL)."""
        turno = Turno.objects.create(
            explorador=self.sin_sala, fecha=self.fecha, jornada=self.jornada_am, sala=None
        )
        self.assertIsNone(turno.sala)

    def test_doblada_completa_se_crea_sin_sala(self):
        """La ruta que fallaba al aprobar (D FDS / doblada) ahora sí aplica."""
        base, adicional = DobladaTurnoService.crear_doblada_completa(
            self.sin_sala, self.fecha, self.jornada_am, self.jornada_pm
        )
        self.assertIsNone(base.sala)
        self.assertIsNone(adicional.sala)
        self.assertEqual(
            Turno.objects.filter(explorador=self.sin_sala, fecha=self.fecha).count(), 2
        )

    def test_mis_turnos_muestra_por_asignar_y_no_revienta(self):
        """La UI degrada a 'Por asignar' en vez de fallar con AttributeError."""
        Turno.objects.create(
            explorador=self.sin_sala, fecha=self.fecha, jornada=self.jornada_am, sala=None
        )
        datos = TurnoService.get_turno_explorador(self.sin_sala.id, self.fecha)
        self.assertEqual(datos['sala'], 'Por asignar')
        self.assertIsNone(datos['sala_id'])
        # La jornada, que es lo que sí importa para la operación, no se ve afectada.
        self.assertEqual(datos['jornada'], 'AM')

    def test_mis_turnos_sigue_mostrando_la_sala_cuando_existe(self):
        """Control: asignada la competencia, el calendario muestra la sala real."""
        Turno.objects.create(
            explorador=self.con_sala, fecha=self.fecha, jornada=self.jornada_am, sala=self.sala
        )
        datos = TurnoService.get_turno_explorador(self.con_sala.id, self.fecha)
        self.assertEqual(datos['sala'], 'Sala Test')
        self.assertEqual(datos['sala_id'], self.sala.id)

    def test_estado_dia_no_depende_de_la_sala(self):
        """La sala es informativa: el estado real del día se calcula igual sin ella."""
        Turno.objects.create(
            explorador=self.sin_sala, fecha=self.fecha, jornada=self.jornada_am, sala=None
        )
        estado = TurnoService.estado_dia(self.sin_sala.id, self.fecha)
        self.assertTrue(estado['trabaja'])
        self.assertEqual(estado['jornada'], 'AM')


class RevertSinSalaTest(TestCase):
    """El revert de los 30 min debe restaurar el turno aunque no haya sala.

    La restauración descartaba la fila (`continue`) cuando no lograba resolver una sala. Con
    la sala ya opcional eso habría hecho desaparecer en silencio el turno previo de un
    explorador sin competencia: al cancelar una solicitud, en vez de recuperar su turno se
    quedaba sin ninguno.
    """

    def setUp(self):
        self.jornada_am = Jornada.objects.create(
            nombre='AM', hora_inicio='08:00:00', hora_fin='13:00:00'
        )
        self.sin_sala = Empleado.objects.create(
            user=User.objects.create_user(username='revert_sin_sala', password='x'),
            nombre='Sin', apellido='Sala', cedula='9000003', activo=True,
        )
        self.fecha = timezone.localdate() + timedelta(days=7)

    def test_restaurar_snapshot_recupera_el_turno_sin_sala(self):
        from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService

        snapshot = {
            f'{self.sin_sala.id}:{self.fecha.isoformat()}': [
                {'jornada_nombre': 'AM', 'sala_id': None, 'tipo_cambio': None}
            ]
        }
        DobladaSnapshotService.restaurar_turnos_desde_snapshot(snapshot)

        turnos = Turno.objects.filter(explorador=self.sin_sala, fecha=self.fecha)
        self.assertEqual(turnos.count(), 1, 'el turno previo se perdió al revertir')
        self.assertEqual(turnos.first().jornada, self.jornada_am)
        self.assertIsNone(turnos.first().sala)
