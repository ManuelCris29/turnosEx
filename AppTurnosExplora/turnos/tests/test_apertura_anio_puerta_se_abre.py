"""
La otra mitad de la puerta del 1 de diciembre: que se ABRE sola.

QUÉ FALTABA
-----------
`AperturaAnioMiddleware` estaba probado por el lado que cierra: el 1 de diciembre, con
el año siguiente sin planificar, cualquier administrador acaba en la pantalla de
apertura. Eso ya lo cubre `test_apertura_anio.AperturaAnioMiddlewareTest`, y se
comprobó de verdad al correr la suite entera con el reloj adelantado 90 días: 149
tests de vistas de administración se pusieron rojos, todos por esta puerta.

Nadie había probado el lado que abre. Y es el que de verdad importa el día que llegue
diciembre: si el supervisor completa el checklist y la puerta NO se abre sola, la
aplicación queda inutilizable para toda la administración con la única salida de que
alguien entre al admin de Django a apagar `bloqueo_duro`.

Lo que ya existía y NO es esto:
  - `test_si_el_anio_esta_listo_nunca_bloquea` prueba que el SERVICIO devuelve 'nada',
    con un `hoy` inyectado. No pasa por el middleware ni por una petición real.
  - `test_sin_bloqueo_duro_no_redirige` prueba la salida de emergencia —apagar el
    bloqueo—, que es lo contrario de lo que se quiere: que se abra por haber hecho el
    trabajo, no por desactivar el guardia.

POR QUÉ SE CONGELA EL RELOJ EN VEZ DE MOVER LA CONFIGURACIÓN
------------------------------------------------------------
Los tests del middleware existentes adelantan la fecha de bloqueo a hoy (`1/1`) para
provocar la situación. Sirve para probar la lógica, pero deja sin comprobar justo lo
que se quiere comprobar aquí: que con la configuración REAL —1 de diciembre, bloqueo
duro, ambos por defecto— y en la fecha REAL, la puerta se comporta como se espera.
Por eso aquí no se toca `AperturaAnioConfig`: si algún día cambian los valores por
defecto, este test debe enterarse.
"""
from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from freezegun import freeze_time

from empleados.models import Empleado, Jornada
from turnos.models import AperturaAnioConfig, DescansoSemanaManual, DiaEspecial
from turnos.services.apertura_anio_service import AperturaAnioService
from turnos.services.asignacion_especial_service import AsignacionEspecialService

# Un 1 de diciembre cualquiera, lejos del presente para que este test no dependa de
# cuándo se ejecute. El año siguiente (2032) es el que hay que dejar planificado.
PRIMERO_DE_DICIEMBRE = '2031-12-01'
ANIO_A_PLANIFICAR = 2032


@override_settings(AXES_ENABLED=False)
class LaPuertaDeDiciembreSeAbreSolaTest(TestCase):

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00',
                                         hora_fin='14:00:00')
        Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')

        # Configuración POR DEFECTO, sin tocar: bloqueo el 1-dic y bloqueo duro activo.
        cfg = AperturaAnioConfig.obtener()
        self.assertEqual((cfg.inicio_bloqueo_dia, cfg.inicio_bloqueo_mes), (1, 12),
                         'este test se apoya en que el bloqueo por defecto es el 1-dic')
        self.assertTrue(cfg.bloqueo_duro, 'y en que por defecto es duro')

        self.admin = User.objects.create_user('sup_dic', password='x', is_staff=True)
        Empleado.objects.create(user=self.admin, nombre='Sup', apellido='Dic',
                                cedula='7101', activo=True)

    def _planificar_el_anio(self, anio=ANIO_A_PLANIFICAR):
        """Deja los cinco ítems del checklist completos, como los dejaría el supervisor."""
        DiaEspecial.objects.create(fecha=date(anio, 1, 1), tipo='festivo', activo=True)
        DiaEspecial.objects.create(fecha=date(anio, 2, 2), tipo='mantenimiento', activo=True)
        DiaEspecial.objects.create(fecha=date(anio, 3, 3), tipo='temporada',
                                   es_temporada=True, activo=True)
        DescansoSemanaManual.objects.create(
            fecha=date(anio, 3, 3), jornada=self.am, motivo='temporada', activo=True)
        AsignacionEspecialService.sembrar_anio(anio, 'AM', 'PM')

    def _navegar(self):
        c = Client()
        c.force_login(self.admin)
        return c.get('/turnos/')

    # ------------------------------------------------------------------

    @freeze_time(PRIMERO_DE_DICIEMBRE)
    def test_control_el_1_de_diciembre_sin_planificar_la_puerta_esta_cerrada(self):
        """
        CONTROL. Sin esto, el test de abajo podría pasar porque la puerta nunca llegó a
        cerrarse —por ejemplo si el reloj no se congeló—, y estaría probando nada.
        """
        r = self._navegar()

        self.assertEqual(r.status_code, 302)
        self.assertIn('/turnos/apertura-anio/', r['Location'])

    @freeze_time(PRIMERO_DE_DICIEMBRE)
    def test_con_el_anio_planificado_el_admin_navega_con_normalidad(self):
        """El caso que nadie había probado: se hizo el trabajo, la puerta se abre sola."""
        self._planificar_el_anio()

        r = self._navegar()

        self.assertNotIn('/turnos/apertura-anio/', r.get('Location', ''),
                         'el checklist está completo: no hay nada que reclamar')
        self.assertNotEqual(r.status_code, 302)

    @freeze_time(PRIMERO_DE_DICIEMBRE)
    def test_se_abre_sin_tocar_la_configuracion(self):
        """
        No hace falta que nadie entre al admin a apagar `bloqueo_duro`. Es la diferencia
        entre una puerta y un muro con una llave escondida: el supervisor solo tiene que
        hacer su trabajo, y el bloqueo sigue armado para el año siguiente.
        """
        self._planificar_el_anio()
        self._navegar()

        cfg = AperturaAnioConfig.obtener()
        self.assertTrue(cfg.bloqueo_duro)
        self.assertEqual((cfg.inicio_bloqueo_dia, cfg.inicio_bloqueo_mes), (1, 12))

    @freeze_time(PRIMERO_DE_DICIEMBRE)
    def test_el_ultimo_item_que_falta_es_el_que_abre(self):
        """
        La apertura no ocurre a medias. Con cuatro de cinco ítems la puerta sigue cerrada;
        se abre en el momento en que se completa el quinto —aquí la alternancia, el único
        que exige el año COMPLETO y por tanto el que más fácil se queda a medias—.
        """
        anio = ANIO_A_PLANIFICAR
        DiaEspecial.objects.create(fecha=date(anio, 1, 1), tipo='festivo', activo=True)
        DiaEspecial.objects.create(fecha=date(anio, 2, 2), tipo='mantenimiento', activo=True)
        DiaEspecial.objects.create(fecha=date(anio, 3, 3), tipo='temporada',
                                   es_temporada=True, activo=True)
        DescansoSemanaManual.objects.create(
            fecha=date(anio, 3, 3), jornada=self.am, motivo='temporada', activo=True)

        self.assertEqual(self._navegar().status_code, 302, 'falta la alternancia')

        AsignacionEspecialService.sembrar_anio(anio, 'AM', 'PM')

        self.assertNotIn('/turnos/apertura-anio/', self._navegar().get('Location', ''))

    @freeze_time(PRIMERO_DE_DICIEMBRE)
    def test_el_anio_que_se_reclama_es_el_siguiente_no_el_corriente(self):
        """
        Planificar 2031 —el año que está corriendo— no abre nada: lo que se reclama en
        diciembre de 2031 es 2032. Un despiste aquí dejaría al supervisor completando el
        año equivocado sin entender por qué la puerta no cede.
        """
        self._planificar_el_anio(anio=2031)

        self.assertEqual(AperturaAnioService.anio_objetivo(), ANIO_A_PLANIFICAR)
        self.assertEqual(self._navegar().status_code, 302)

    @freeze_time('2031-11-30')
    def test_el_dia_anterior_todavia_no_bloquea(self):
        """La frontera exacta: el 30 de noviembre se avisa, no se bloquea."""
        r = self._navegar()

        self.assertNotIn('/turnos/apertura-anio/', r.get('Location', ''))
