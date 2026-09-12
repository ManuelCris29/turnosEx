"""
`DFDSCompanerosView` precarga en lote el estado del finde para todo el pool de
candidatos (api_fin_semana.py + estrategia_fin_de_semana.py::estado_de), en vez
de pagar `estado_dia` 1-2 veces por candidato. Fija que el coste no crezca con
el tamaño del pool.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from empleados.models import Empleado, Jornada
from solicitudes.models import TipoSolicitudCambio


@override_settings(AXES_ENABLED=False)
class DFDSCompanerosCosteConstanteTest(TestCase):

    URL = '/solicitudes/dfds-companeros/'

    def setUp(self):
        Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        u = User.objects.create_user('exp.finde.batch', password='x')
        self.yo = Empleado.objects.create(user=u, nombre='Exp', apellido='Batch',
                                          cedula='9201', activo=True)
        self.client = Client()
        self.client.force_login(u)
        TipoSolicitudCambio.objects.get_or_create(nombre='D FDS', defaults={'activo': True})

        d = timezone.localdate() + timedelta(days=7)
        while d.weekday() != 5:
            d += timedelta(days=1)
        self.sabado = d.strftime('%Y-%m-%d')

    _contador = 0

    def _crear_candidatos(self, n):
        for _ in range(n):
            i = DFDSCompanerosCosteConstanteTest._contador
            DFDSCompanerosCosteConstanteTest._contador += 1
            u = User.objects.create_user(username=f'finde_batch_{i}', password='x')
            Empleado.objects.create(user=u, nombre=f'C{i}', apellido='Batch',
                                    cedula=f'921{i:04d}', activo=True)

    def _consultas(self):
        params = {'fecha': self.sabado}
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(self.URL, params, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        return len(ctx), resp.json()

    def test_el_numero_de_consultas_no_crece_con_el_pool_de_candidatos(self):
        """
        Antes del batch (`estados_precargados`), cada candidato pagaba 1-2 consultas propias
        de `estado_dia`: con 15 candidatos más eso habría sido +15-30 consultas. Se admite un
        margen de 2 (alguna consulta puede variar por el CONTENIDO de los datos, no por la
        CANTIDAD de candidatos) para no acoplar el test a un número exacto y frágil.
        """
        self._crear_candidatos(2)
        pocas, _ = self._consultas()

        self._crear_candidatos(15)
        muchas, data = self._consultas()

        self.assertGreaterEqual(len(data['companeros']), 15)
        self.assertLessEqual(
            muchas, pocas + 2,
            f'{pocas} consultas con pocos candidatos y {muchas} con muchos: con 15 candidatos '
            f'más, el selector no debería crecer de forma proporcional (antes del batch de '
            f'estado_dia, esto habría sido +15 a +30 consultas).',
        )
