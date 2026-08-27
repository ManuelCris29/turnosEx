"""
Tests de la APERTURA DE AÑO: el checklist obligatorio y el bloqueo del supervisor.

Lo que se protege aquí:
  1. La completitud se DERIVA del dato: nada se marca a mano.
  2. La alternancia exige cobertura COMPLETA, no "al menos un registro". Es lo que impide
     que un explorador vea días `sin_planificar`.
  3. El bloqueo afecta SOLO al admin, y nunca a las rutas que hacen falta para desbloquearse
     (si no, el supervisor queda encerrado sin poder ni completar el checklist ni salir).
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from empleados.models import Empleado, Jornada
from turnos.models import (
    AperturaAnioConfig,
    AsignacionEspecialManual,
    DescansoSemanaManual,
    DiaEspecial,
)
from turnos.services.apertura_anio_service import AperturaAnioService
from turnos.services.asignacion_especial_service import AsignacionEspecialService


class AperturaAnioChecklistTest(TestCase):

    ANIO = 2032

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')

    def _claves_completas(self, anio=None):
        return {i.clave for i in AperturaAnioService.estado(anio or self.ANIO) if i.completo}

    def test_anio_vacio_no_tiene_nada_completo(self):
        self.assertEqual(self._claves_completas(), set())
        self.assertFalse(AperturaAnioService.completo(self.ANIO))
        self.assertEqual(len(AperturaAnioService.pendientes(self.ANIO)), 5)

    def test_cada_item_se_completa_con_su_dato(self):
        DiaEspecial.objects.create(fecha=date(self.ANIO, 1, 1), tipo='festivo', activo=True)
        self.assertIn('festivos', self._claves_completas())

        DiaEspecial.objects.create(fecha=date(self.ANIO, 2, 2), tipo='mantenimiento', activo=True)
        self.assertIn('mantenimiento', self._claves_completas())

        DiaEspecial.objects.create(fecha=date(self.ANIO, 3, 3), tipo='temporada',
                                   es_temporada=True, activo=True)
        self.assertIn('temporadas', self._claves_completas())

        DescansoSemanaManual.objects.create(fecha=date(self.ANIO, 3, 3), jornada=self.am,
                                            motivo='temporada', activo=True)
        self.assertIn('descansos_semana', self._claves_completas())

    def test_la_alternancia_exige_el_anio_completo(self):
        """Con un solo día publicado NO basta: cualquier hueco deja días sin planificar."""
        sabado = date(self.ANIO, 1, 1)
        while sabado.weekday() != 5:
            sabado += timedelta(days=1)
        AsignacionEspecialManual.objects.create(
            fecha=sabado, jornada_trabaja=self.am, tipo='finde', activo=True)
        self.assertNotIn('alternancia', self._claves_completas())

        AsignacionEspecialService.sembrar_anio(self.ANIO, 'AM', 'PM')
        self.assertIn('alternancia', self._claves_completas())

    def test_anio_completo_cuando_estan_los_cinco(self):
        DiaEspecial.objects.create(fecha=date(self.ANIO, 1, 1), tipo='festivo', activo=True)
        DiaEspecial.objects.create(fecha=date(self.ANIO, 2, 2), tipo='mantenimiento', activo=True)
        DiaEspecial.objects.create(fecha=date(self.ANIO, 3, 3), tipo='temporada',
                                   es_temporada=True, activo=True)
        DescansoSemanaManual.objects.create(fecha=date(self.ANIO, 3, 3), jornada=self.am,
                                            motivo='temporada', activo=True)
        AsignacionEspecialService.sembrar_anio(self.ANIO, 'AM', 'PM')
        self.assertTrue(AperturaAnioService.completo(self.ANIO))

    def test_el_anio_objetivo_es_siempre_el_siguiente(self):
        self.assertEqual(AperturaAnioService.anio_objetivo(date(2031, 3, 5)), 2032)
        self.assertEqual(AperturaAnioService.anio_objetivo(date(2031, 12, 31)), 2032)


class AperturaAnioSituacionTest(TestCase):
    """La situación depende de las fechas configuradas y de si falta algo."""

    def setUp(self):
        Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.cfg = AperturaAnioConfig.obtener()

    def test_antes_del_recordatorio_no_pasa_nada(self):
        situacion, _ = AperturaAnioService.situacion(hoy=date(2031, 6, 1), cfg=self.cfg)
        self.assertEqual(situacion, 'nada')

    def test_entre_recordatorio_y_bloqueo_solo_avisa(self):
        situacion, anio = AperturaAnioService.situacion(hoy=date(2031, 11, 15), cfg=self.cfg)
        self.assertEqual(situacion, 'aviso')
        self.assertEqual(anio, 2032)

    def test_desde_el_bloqueo_se_bloquea(self):
        situacion, _ = AperturaAnioService.situacion(hoy=date(2031, 12, 5), cfg=self.cfg)
        self.assertEqual(situacion, 'bloqueo')

    def test_con_bloqueo_duro_apagado_solo_avisa(self):
        self.cfg.bloqueo_duro = False
        self.cfg.save()
        situacion, _ = AperturaAnioService.situacion(hoy=date(2031, 12, 5), cfg=self.cfg)
        self.assertEqual(situacion, 'aviso')

    def test_si_el_anio_esta_listo_nunca_bloquea(self):
        anio = 2032
        DiaEspecial.objects.create(fecha=date(anio, 1, 1), tipo='festivo', activo=True)
        DiaEspecial.objects.create(fecha=date(anio, 2, 2), tipo='mantenimiento', activo=True)
        DiaEspecial.objects.create(fecha=date(anio, 3, 3), tipo='temporada',
                                   es_temporada=True, activo=True)
        DescansoSemanaManual.objects.create(
            fecha=date(anio, 3, 3), jornada=Jornada.objects.get(nombre='AM'),
            motivo='temporada', activo=True)
        AsignacionEspecialService.sembrar_anio(anio, 'AM', 'PM')
        situacion, _ = AperturaAnioService.situacion(hoy=date(2031, 12, 31), cfg=self.cfg)
        self.assertEqual(situacion, 'nada')


@override_settings(AXES_ENABLED=False)
class AperturaAnioMiddlewareTest(TestCase):
    """El bloqueo no puede dejar encerrado al supervisor ni molestar al explorador."""

    def setUp(self):
        Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        # Configuración que bloquea HOY: el año siguiente está vacío.
        cfg = AperturaAnioConfig.obtener()
        _hoy = date.today()
        cfg.inicio_bloqueo_dia, cfg.inicio_bloqueo_mes = 1, 1
        cfg.inicio_recordatorio_dia, cfg.inicio_recordatorio_mes = 1, 1
        cfg.save()

        self.admin_user = User.objects.create_user('sup_ap', password='x', is_staff=True)
        Empleado.objects.create(user=self.admin_user, nombre='Sup', apellido='X',
                                cedula='7001', activo=True)
        self.explorador_user = User.objects.create_user('exp_ap', password='x')
        Empleado.objects.create(user=self.explorador_user, nombre='Exp', apellido='X',
                                cedula='7002', activo=True)

    def _get(self, user, url):
        c = Client()
        c.force_login(user)
        return c.get(url)

    def test_el_admin_es_redirigido_al_checklist(self):
        r = self._get(self.admin_user, '/turnos/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/turnos/apertura-anio/', r['Location'])

    def test_el_explorador_no_se_bloquea(self):
        """La planificación no es su trabajo: dejarlo fuera sería peor que el problema."""
        r = self._get(self.explorador_user, '/turnos/')
        self.assertNotIn('/turnos/apertura-anio/', r.get('Location', ''))

    def test_las_pantallas_del_checklist_no_se_bloquean(self):
        """Sin estas exenciones el supervisor no podría completar el checklist."""
        anio = AperturaAnioService.anio_objetivo()
        for url in (f'/turnos/apertura-anio/{anio}/',
                    '/turnos/dias-especiales/festivos-mantenimiento-anual/',
                    '/turnos/dias-especiales/temporadas-anual/',
                    '/turnos/descanso-semana/anual/',
                    '/turnos/asignacion-especial/anual/'):
            with self.subTest(url=url):
                r = self._get(self.admin_user, url)
                self.assertNotIn('/turnos/apertura-anio/', r.get('Location', ''),
                                 f'{url} no puede redirigir al checklist')

    def test_el_admin_puede_cerrar_sesion(self):
        r = self._get(self.admin_user, '/logout/')
        self.assertNotIn('/turnos/apertura-anio/', r.get('Location', ''))

    def test_sin_bloqueo_duro_no_redirige(self):
        cfg = AperturaAnioConfig.obtener()
        cfg.bloqueo_duro = False
        cfg.save()
        r = self._get(self.admin_user, '/turnos/')
        self.assertNotIn('/turnos/apertura-anio/', r.get('Location', ''))

    def test_las_peticiones_ajax_no_se_redirigen(self):
        """Redirigir un endpoint JSON rompería el front con un error de parseo."""
        c = Client()
        c.force_login(self.admin_user)
        r = c.get('/turnos/', HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertNotIn('/turnos/apertura-anio/', r.get('Location', ''))


class AperturaAnioVistaTest(TestCase):

    def setUp(self):
        Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.user = User.objects.create_user('sup_v', password='x', is_staff=True)
        Empleado.objects.create(user=self.user, nombre='Sup', apellido='V',
                                cedula='7003', activo=True)

    def test_la_ruta_sin_anio_usa_el_siguiente(self):
        """Es la que enlaza el menú, que no conoce el año."""
        c = Client()
        c.force_login(self.user)
        r = c.get('/turnos/apertura-anio/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['anio'], AperturaAnioService.anio_objetivo())

    def test_la_pantalla_lista_los_cinco_items(self):
        c = Client()
        c.force_login(self.user)
        r = c.get('/turnos/apertura-anio/2032/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total'], 5)
        self.assertEqual(r.context['completados'], 0)
        self.assertEqual(r.context['pendientes'], 5)
        self.assertFalse(r.context['todo_listo'])
