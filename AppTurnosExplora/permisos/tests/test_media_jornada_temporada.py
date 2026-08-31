"""
Permiso de MEDIA JORNADA TEMPORADA (sub-tipo del formulario de Cambio de Día de Descanso).

Este permiso llega por su propio endpoint, así que el gate del orquestador de solicitudes NO lo
cubre: las validaciones de días pasados y de cierre semanal tienen que estar aquí. Estos tests
cubren justo eso; el resto del flujo (día completo de temporada, compensación) vive en la vista.
"""
from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado
from solicitudes.models import CierreSolicitudesConfig


class MediaJornadaTemporadaGatesTest(TestCase):
    def setUp(self):
        u = User.objects.create_user('mj.temp', password='x')
        self.emp = Empleado.objects.create(user=u, nombre='Media', apellido='Jornada',
                                           cedula='7701', activo=True)
        self.client = Client()
        self.client.force_login(u)
        self.url = reverse('permisos_media_jornada_create')

    @staticmethod
    def _lunes_futuro(semanas=1):
        hoy = timezone.localdate()
        d = hoy + timedelta(days=1)
        while d.weekday() != 0:
            d += timedelta(days=1)
        return d + timedelta(days=7 * (semanas - 1))

    def _post(self, f_trabajo, f_comp):
        return self.client.post(self.url, {
            'fecha_trabajo': f_trabajo.strftime('%Y-%m-%d'),
            'fecha_compensacion': f_comp.strftime('%Y-%m-%d'),
            'jornada_trabaja': 'AM',
            'motivo': 'Prueba',
        })

    def test_dia_pasado_rechazado(self):
        """Antes no había ningún control contra `hoy`: se podía pedir un lunes ya pasado."""
        hoy = timezone.localdate()
        lunes_pasado = hoy - timedelta(days=hoy.weekday() + 7)
        r = self._post(lunes_pasado, lunes_pasado + timedelta(days=2))
        self.assertEqual(r.status_code, 400)
        self.assertIn('pasados', r.json().get('error', ''))

    def test_cierre_semanal_bloquea(self):
        """Con el cierre activo, este endpoint no puede ser una puerta trasera.

        Antes buscaba un día lun-vie que YA estuviera bloqueado y siguiera siendo futuro. Eso solo
        existe de jueves a domingo (las opciones de `dia_cierre` no incluyen lun-mié), así que la
        mitad de la semana el test se saltaba solo y la puerta trasera quedaba sin comprobar.

        Ahora se fija el reloj: se toma un lunes futuro, se pregunta al propio servicio cuál es su
        cutoff, y se sitúa `ahora` un minuto DESPUÉS. Así el día está bloqueado por construcción,
        corra la suite el día que corra.
        """
        from unittest import mock

        from solicitudes.services.cierre_solicitudes_service import CierreSolicitudesService as CS

        cfg = CierreSolicitudesConfig.obtener()
        cfg.habilitado = True
        cfg.dia_cierre = 'jueves'
        cfg.hora_cierre = time(0, 1)
        cfg.save()

        objetivo = self._lunes_futuro(semanas=2)
        cutoff = CS.cutoff_para_fecha(objetivo)
        self.assertIsNotNone(cutoff, 'con el cierre habilitado, un lunes debe tener cutoff')

        with mock.patch('django.utils.timezone.now', return_value=cutoff + timedelta(minutes=1)):
            r = self._post(objetivo, objetivo)

        self.assertEqual(r.status_code, 400)
        self.assertIn('Cierre de solicitudes', r.json().get('error', ''))

    def test_cierre_deshabilitado_no_bloquea_por_cierre(self):
        """Sin cierre activo, la petición avanza más allá del gate (falla luego por temporada)."""
        cfg = CierreSolicitudesConfig.obtener()
        cfg.habilitado = False
        cfg.save()
        lunes = self._lunes_futuro()
        r = self._post(lunes, lunes + timedelta(days=2))
        self.assertEqual(r.status_code, 400)
        self.assertNotIn('Cierre de solicitudes', r.json().get('error', ''))


class MediaJornadaVentanaDeFechasTest(MediaJornadaTemporadaGatesTest):
    """
    Las DOS reglas que delimitan el permiso: ambos días de LUNES A VIERNES y en la MISMA
    semana (mismo lunes). Son la esencia del sub-tipo —se parte un día completo de temporada
    y la otra media se trabaja en el día de descanso de ESA semana— y hasta ahora ningún test
    las sujetaba: se podían relajar en un refactor sin que la suite dijera nada.

    Ojo con el corolario: «misma semana» NO implica «mismo mes». Una semana de lunes a viernes
    cruza el cambio de mes varias veces al año (lunes 30/11 y martes 01/12 son la misma semana),
    y eso es un par VÁLIDO. Ver
    `ReflejoMisTurnosPermisosTest::test_compensacion_en_otro_mes_se_ve_al_consultar_ese_mes`.
    """

    def _mensaje(self, resp):
        return (resp.json() or {}).get('error') or ''

    def test_sabado_rechazado(self):
        lunes = self._lunes_futuro(2)
        resp = self._post(lunes, lunes + timedelta(days=5))  # sábado

        self.assertEqual(resp.status_code, 400)
        self.assertIn('lunes a viernes', self._mensaje(resp))

    def test_domingo_como_dia_de_trabajo_rechazado(self):
        lunes = self._lunes_futuro(2)
        resp = self._post(lunes - timedelta(days=1), lunes + timedelta(days=1))  # domingo previo

        self.assertEqual(resp.status_code, 400)
        self.assertIn('lunes a viernes', self._mensaje(resp))

    def test_semana_siguiente_rechazada(self):
        lunes = self._lunes_futuro(2)
        resp = self._post(lunes, lunes + timedelta(days=7))  # lunes de la semana siguiente

        self.assertEqual(resp.status_code, 400)
        self.assertIn('MISMA semana', self._mensaje(resp))

    def test_semana_anterior_rechazada(self):
        lunes = self._lunes_futuro(3)
        resp = self._post(lunes, lunes - timedelta(days=7))

        self.assertEqual(resp.status_code, 400)
        self.assertIn('MISMA semana', self._mensaje(resp))

    def test_viernes_y_lunes_siguiente_rechazados_aunque_sean_consecutivos(self):
        """Días laborables y casi pegados, pero de semanas distintas: la regla es el lunes común."""
        lunes = self._lunes_futuro(2)
        resp = self._post(lunes + timedelta(days=4), lunes + timedelta(days=7))

        self.assertEqual(resp.status_code, 400)
        self.assertIn('MISMA semana', self._mensaje(resp))

    def test_misma_semana_pasa_la_regla_de_fechas(self):
        """
        Lunes y miércoles de la misma semana: superan L-V y semana. Se detendrán más adelante
        (no es día completo de temporada), pero NO por estas dos reglas.
        """
        lunes = self._lunes_futuro(2)
        resp = self._post(lunes, lunes + timedelta(days=2))

        self.assertNotIn('lunes a viernes', self._mensaje(resp))
        self.assertNotIn('MISMA semana', self._mensaje(resp))
