"""
Un permiso tampoco cruza el 31 de diciembre (ver `core/utils/anio_operativo.py`).

Dos puertas de entrada distintas, y cada una tiene que cerrarla por su cuenta: el formulario
general de permisos y el endpoint propio de MEDIA JORNADA TEMPORADA.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado
from permisos.forms import PermisoEspecialForm, PermisoEspecialPermanenteForm

COMUNES = {'tipo': 'PERSONAL', 'tiempo': '1', 'motivo': 'Prueba'}


class PermisoPuntualAnioOperativoTest(TestCase):
    """Permiso de un día: el campo es `fecha`."""

    def setUp(self):
        self.hoy = timezone.localdate()

    def _form(self, f):
        return PermisoEspecialForm(data={'fecha': f.strftime('%Y-%m-%d'), **COMUNES})

    def test_dentro_del_anio_no_falla_por_la_frontera(self):
        form = self._form(date(self.hoy.year, 6, 15))
        form.is_valid()

        self.assertNotIn('apertura de año', str(form.errors))

    def test_en_el_anio_siguiente_se_rechaza(self):
        form = self._form(date(self.hoy.year + 1, 1, 4))

        self.assertFalse(form.is_valid())
        self.assertIn('apertura de año', str(form.errors['fecha']))


class PermisoPermanenteAnioOperativoTest(TestCase):
    """Permiso permanente: el rango `fecha_inicio`..`fecha_fin` tampoco cruza el año."""

    def setUp(self):
        self.hoy = timezone.localdate()

    def _form(self, fi, ff):
        return PermisoEspecialPermanenteForm(data={
            'fecha_inicio': fi.strftime('%Y-%m-%d'),
            'fecha_fin': ff.strftime('%Y-%m-%d'),
            'dias': ['0'], **COMUNES,
        })

    def test_dentro_del_anio_no_falla_por_la_frontera(self):
        form = self._form(date(self.hoy.year, 6, 1), date(self.hoy.year, 7, 1))
        form.is_valid()

        self.assertNotIn('apertura de año', str(form.errors))

    def test_rango_que_termina_el_anio_siguiente_se_rechaza(self):
        form = self._form(date(self.hoy.year, 12, 28), date(self.hoy.year + 1, 1, 4))

        self.assertFalse(form.is_valid())
        self.assertIn('fecha_fin', form.errors)
        self.assertIn('apertura de año', str(form.errors['fecha_fin']))

    def test_el_error_se_marca_en_cada_campo_infractor(self):
        form = self._form(date(self.hoy.year + 1, 1, 4), date(self.hoy.year + 1, 1, 5))
        form.is_valid()

        self.assertIn('fecha_inicio', form.errors)
        self.assertIn('fecha_fin', form.errors)


class MediaJornadaAnioOperativoTest(TestCase):
    """
    El caso que la regla de «misma semana» NO cubre: jueves 31/12 y viernes 01/01 son la misma
    semana, así que sin esta comprobación la compensación se colaba al año siguiente.
    """

    def setUp(self):
        u = User.objects.create_user('mj.anio', password='x')
        Empleado.objects.create(user=u, nombre='Media', apellido='Anio', cedula='7702', activo=True)
        self.client = Client()
        self.client.force_login(u)
        self.url = reverse('permisos_media_jornada_create')

    def test_compensacion_en_el_anio_siguiente_se_rechaza(self):
        # Último jueves/viernes del año que caen en la misma semana y cruzan el 1 de enero.
        anio = timezone.localdate().year
        d = date(anio, 12, 31)
        while d.weekday() >= 4:  # que quede al menos un día laborable por delante en su semana
            d -= timedelta(days=1)
        comp = d + timedelta(days=1)
        while comp.year == anio:
            d -= timedelta(days=1)
            comp = d + timedelta(days=1)
        # Si el 31/12 no deja un par L-V que cruce de año, este año no tiene el escenario.
        if not (d.weekday() < 5 and comp.weekday() < 5
                and d - timedelta(days=d.weekday()) == comp - timedelta(days=comp.weekday())):
            self.skipTest(f'{anio} no tiene un par L-V de la misma semana que cruce de año')

        resp = self.client.post(self.url, {
            'fecha_trabajo': d.strftime('%Y-%m-%d'),
            'fecha_compensacion': comp.strftime('%Y-%m-%d'),
            'jornada_trabaja': 'AM', 'motivo': 'Prueba',
        })

        self.assertEqual(resp.status_code, 400)
        self.assertEqual((resp.json() or {}).get('code'), 'fuera_anio_operativo')
