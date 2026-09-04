"""
Los bordes del endpoint de Mis Turnos por mes.

POR QUÉ ESTE ARCHIVO
--------------------
`MisTurnosPorMesView.get` son 345 líneas con 52 ramas: el tercer punto caliente que
señalaba la auditoría. Alimenta la pantalla que más miran los exploradores, así que un
fallo ahí lo ve todo el mundo.

Medida la cobertura sobre el artefacto del CI estaba al 81%, y lo que faltaba no era la
lógica de turnos —eso lo cubre `MisTurnosFuenteVerdadTest`— sino los BORDES: qué pasa
con una petición mal formada, qué pasa la segunda vez que se pide el mismo mes, y qué
pasa en diciembre.

Los dos que de verdad importan:

  - **El camino de la caché.** La vista guarda el mes calculado y lo devuelve tal cual en
    la siguiente petición. Esa segunda rama —la que sirve a casi todas las visitas
    reales— no la ejercitaba ningún test: todos veían siempre el cálculo en frío.
  - **Diciembre.** El rango del mes se calcula distinto en el último mes del año, porque
    hay que saltar al 1 de enero siguiente para restarle un día. Es una rama propia, y
    una que solo se ejecuta de verdad un mes al año.
"""
from datetime import date

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

from empleados.models import Empleado, Jornada
from turnos.models import AsignarJornadaExplorador

URL = '/turnos/api/mis-turnos-por-mes/'


@override_settings(AXES_ENABLED=False)
class MisTurnosMesBordesTest(TestCase):

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('bordes.mt', password='x')
        self.empleado = Empleado.objects.create(
            user=self.user, nombre='Bor', apellido='Des', cedula='9301', activo=True)
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00',
                                         hora_fin='14:00:00')
        Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        AsignarJornadaExplorador.objects.create(
            explorador=self.empleado, jornada=self.am, fecha_inicio=date(2026, 1, 1))
        self.client = Client()
        self.client.force_login(self.user)

    # ---------------------------------------------------- peticiones mal formadas

    def test_sin_mes_ni_anio_se_rechaza(self):
        r = self.client.get(URL)

        self.assertEqual(r.status_code, 400)
        self.assertIn('mes y anio', r.json()['error'])

    def test_un_mes_fuera_de_rango_se_rechaza(self):
        for mes in ('0', '13', '99'):
            with self.subTest(mes=mes):
                r = self.client.get(URL, {'mes': mes, 'anio': '2026'})

                self.assertEqual(r.status_code, 400)
                self.assertIn('Mes invalido', r.json()['error'])

    def test_un_mes_no_numerico_se_rechaza(self):
        """No revienta con un 500: contesta que el parámetro está mal."""
        r = self.client.get(URL, {'mes': 'agosto', 'anio': '2026'})

        self.assertEqual(r.status_code, 400)
        self.assertIn('numéricos', r.json()['error'])

    def test_un_usuario_sin_empleado_se_rechaza(self):
        """Un `User` de Django sin ficha de empleado —un superusuario recién creado, por
        ejemplo— no tiene turnos que enseñar."""
        suelto = User.objects.create_user('sin.empleado', password='x')
        c = Client()
        c.force_login(suelto)

        r = c.get(URL, {'mes': '8', 'anio': '2026'})

        self.assertEqual(r.status_code, 400)
        self.assertIn('no es empleado', r.json()['error'])

    # ---------------------------------------------------- normalización y caché

    def test_el_mes_se_normaliza_a_dos_digitos(self):
        """`?mes=8` y `?mes=08` son el mismo mes, y deben compartir la misma entrada de
        caché: si no, media aplicación calcularía en frío por escribir el cero."""
        primera = self.client.get(URL, {'mes': '8', 'anio': '2026'})
        segunda = self.client.get(URL, {'mes': '08', 'anio': '2026'})

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(primera.json(), segunda.json())

    def test_la_segunda_peticion_sale_de_la_cache(self):
        """
        El camino que sirve a casi todas las visitas reales, y que no ejercitaba ningún
        test. Se comprueba con el contenido, no con el número de consultas: lo que importa
        es que lo cacheado sea lo mismo que se calculó.
        """
        primera = self.client.get(URL, {'mes': '8', 'anio': '2026'})
        self.assertEqual(primera.status_code, 200)

        from core.services.cache_service import CacheService
        self.assertIsNotNone(CacheService.get(f'turnos_mes_{self.empleado.id}_2026_08'),
                             'la primera petición debe dejar el mes en caché')

        segunda = self.client.get(URL, {'mes': '8', 'anio': '2026'})

        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(segunda.json(), primera.json())

    # ---------------------------------------------------- frontera de año

    def test_diciembre_cubre_el_mes_entero(self):
        """
        Diciembre tiene su propia rama: para saber dónde acaba hay que saltar al 1 de enero
        del año siguiente y restarle un día. Si esa rama se rompe, el último mes del año
        sale corto —y solo se nota en diciembre—.
        """
        r = self.client.get(URL, {'mes': '12', 'anio': '2026'})

        self.assertEqual(r.status_code, 200)
        dias = r.json()
        self.assertIn('2026-12-01', dias)
        self.assertIn('2026-12-31', dias)
        self.assertEqual(len(dias), 31)
        self.assertNotIn('2027-01-01', dias, 'diciembre no puede invadir el año siguiente')

    def test_un_mes_normal_no_invade_el_siguiente(self):
        """CONTROL de la rama de arriba: el cálculo del resto de meses sigue intacto."""
        r = self.client.get(URL, {'mes': '11', 'anio': '2026'})

        dias = r.json()
        self.assertEqual(len(dias), 30)
        self.assertIn('2026-11-30', dias)
        self.assertNotIn('2026-12-01', dias)
