"""
DOBLADA — el filtro «sin doblada activa» distingue QUIÉN se dobla de QUIÉN se libera.

En una DOBLADA los dos roles hacen cosas opuestas ese día:
- `explorador_solicitante`: CEDE su jornada y DESCANSA  -> sigue disponible para otras solicitudes.
- `explorador_receptor`:    RECIBE la jornada y se DOBLA -> no se le puede pedir otra (triple turno).

El filtro miraba `explorador_solicitante_id`, así que excluía justo a la gente libre: quien te
había cedido a TI no aparecía en el selector de compañeros pese a estar descansando.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, Jornada
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.doblada_filtro_service import DobladaFiltroService
from turnos.models import AsignarJornadaExplorador, Sala, Turno


class FiltroDobladaActivaRolTest(TestCase):
    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Filtro', activo=True)

        self.cede = self._empleado('cede.filtro', 'Cede', '9401', self.pm)
        self.dobla = self._empleado('dobla.filtro', 'Dobla', '9402', self.am)

        self.fecha = timezone.localdate() + timedelta(days=10)

        self.tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA', activo=True)
        SolicitudCambio.objects.create(
            tipo_cambio=self.tipo,
            explorador_solicitante=self.cede,
            explorador_receptor=self.dobla,
            fecha_cambio_turno=self.fecha,
            estado='aprobada',
        )

    def _empleado(self, username, nombre, cedula, jornada):
        u = User.objects.create_user(username, password='x')
        e = Empleado.objects.create(user=u, nombre=nombre, apellido='Filtro',
                                    cedula=cedula, activo=True)
        AsignarJornadaExplorador.objects.create(explorador=e, jornada=jornada,
                                                fecha_inicio=date(2025, 1, 1))
        return e

    def test_quien_cedio_su_jornada_sigue_disponible(self):
        """El solicitante descansa ese día: no está doblado, no debe filtrarse."""
        disponibles = DobladaFiltroService.filtrar_empleados_sin_doblada_activa(
            [self.cede, self.dobla], self.fecha
        )
        self.assertIn(self.cede, disponibles)

    def test_quien_recibio_la_jornada_queda_excluido(self):
        """El receptor trabaja AM+PM: pedirle otra doblada sería un triple turno."""
        disponibles = DobladaFiltroService.filtrar_empleados_sin_doblada_activa(
            [self.cede, self.dobla], self.fecha
        )
        self.assertNotIn(self.dobla, disponibles)

    def test_doblada_ya_materializada_en_turnos_tambien_excluye(self):
        """La otra fuente del filtro (AM+PM reales en Turno) sigue vigente."""
        otro = self._empleado('otro.filtro', 'Otro', '9403', self.am)
        for jornada in (self.am, self.pm):
            Turno.objects.create(explorador=otro, fecha=self.fecha,
                                 jornada=jornada, sala=self.sala)

        disponibles = DobladaFiltroService.filtrar_empleados_sin_doblada_activa(
            [self.cede, otro], self.fecha
        )
        self.assertNotIn(otro, disponibles)
        self.assertIn(self.cede, disponibles)
