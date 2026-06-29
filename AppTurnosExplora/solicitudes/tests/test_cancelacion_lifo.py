"""
Test de la guardia de orden (LIFO) al cancelar.

Si hay dos cambios aprobados sobre el mismo (persona, día), cancelar el MÁS VIEJO debe
bloquearse (revertirlo pisaría al más nuevo). Hay que cancelar primero el más reciente.
"""
import json
from datetime import date, timedelta

from django.test import TestCase, RequestFactory
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from solicitudes.views.aprobacion_views import CancelarSolicitudView


class CancelacionLIFOTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.factory = RequestFactory()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala', activo=True)

        def _emp(username, ced, jor):
            u = User.objects.create_user(username=username, password='x')
            e = Empleado.objects.create(user=u, nombre=username, apellido='X', cedula=ced, activo=True)
            AsignarJornadaExplorador.objects.create(explorador=e, jornada=jor, fecha_inicio=date(2025, 1, 1))
            CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
            return e

        self.mariana = _emp('mariana', '1', self.am)
        self.jhon = _emp('jhon', '2', self.pm)
        self.carlos = _emp('carlos', '3', self.pm)

        d = timezone.now().date() + timedelta(days=3)
        while d.weekday() != 2:
            d += timedelta(days=1)
        self.x = d
        # Turnos reales en X (estado "ya aplicado").
        Turno.objects.create(explorador=self.mariana, fecha=self.x, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.jhon, fecha=self.x, jornada=self.pm, sala=self.sala)
        Turno.objects.create(explorador=self.carlos, fecha=self.x, jornada=self.pm, sala=self.sala)

        xi = self.x.isoformat()
        ahora = timezone.now()
        # A: Mariana↔Jhon, aprobada hace 10 min.
        self.A = SolicitudCambio.objects.create(
            explorador_solicitante=self.mariana, explorador_receptor=self.jhon,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.x, estado='aprobada',
            fecha_resolucion=ahora - timedelta(minutes=10), comentario='A',
            snapshot_turnos_previos={
                f"{self.mariana.id}:{xi}": [{'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
                f"{self.jhon.id}:{xi}": [{'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
            })
        # B: Mariana↔Carlos, aprobada hace 2 min (MÁS RECIENTE), comparte Mariana en X.
        self.B = SolicitudCambio.objects.create(
            explorador_solicitante=self.mariana, explorador_receptor=self.carlos,
            tipo_cambio=self.tipo, fecha_cambio_turno=self.x, estado='aprobada',
            fecha_resolucion=ahora - timedelta(minutes=2), comentario='B',
            snapshot_turnos_previos={
                f"{self.mariana.id}:{xi}": [{'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
                f"{self.carlos.id}:{xi}": [{'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': None}],
            })

    def _cancelar(self, solicitud, quien):
        req = self.factory.post(f'/solicitudes/cancelar/{solicitud.id}/')
        req.user = quien.user
        resp = CancelarSolicitudView.as_view()(req, solicitud_id=solicitud.id)
        return resp.status_code, json.loads(resp.content)

    def test_lifo(self):
        # Cancelar A (el viejo) → bloqueado por existir B más reciente sobre Mariana en X.
        code, body = self._cancelar(self.A, self.mariana)
        self.assertEqual(code, 400)
        self.assertEqual(body.get('code'), 'cambio_mas_reciente')
        self.A.refresh_from_db()
        self.assertEqual(self.A.estado, 'aprobada')  # sigue viva

        # Cancelar B (el más reciente) → permitido.
        code, body = self._cancelar(self.B, self.mariana)
        self.assertEqual(code, 200, body)
        self.B.refresh_from_db()
        self.assertEqual(self.B.estado, 'cancelada')

        # Ahora sí, cancelar A → permitido (ya no hay posteriores aprobadas).
        code, body = self._cancelar(self.A, self.mariana)
        self.assertEqual(code, 200, body)
        self.A.refresh_from_db()
        self.assertEqual(self.A.estado, 'cancelada')
