"""
Que se note cuando la revisión diaria deja de ejecutarse.

Un cron caído no produce ningún error que alguien vea: simplemente deja de ocurrir. El
síntoma —morosos que siguen pudiendo solicitar— tarda semanas en aparecer y nadie lo
atribuye a esto. Estas pruebas cubren las dos vías por las que ahora se entera alguien:
el log de nivel CRITICAL (que es lo que engancha una alerta) y el aviso en el dashboard.
"""
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado
from solicitudes.management.commands.revisar_sanciones_por_deuda import MARCADOR_ALERTA
from solicitudes.models import RevisionSancionesDeuda


class DiasSinEjecutarTest(TestCase):

    def setUp(self):
        self.hoy = timezone.localdate()

    def test_si_corrio_hoy_no_hay_hueco(self):
        RevisionSancionesDeuda.objects.create(fecha=self.hoy)

        self.assertEqual(RevisionSancionesDeuda.dias_sin_ejecutar(self.hoy), 0)
        self.assertFalse(RevisionSancionesDeuda.hay_hueco(self.hoy))

    def test_un_dia_de_retraso_no_es_noticia(self):
        """El proceso se autocura; un día solo atrasa el aviso, no rompe nada."""
        RevisionSancionesDeuda.objects.create(fecha=self.hoy - timedelta(days=1))

        self.assertFalse(RevisionSancionesDeuda.hay_hueco(self.hoy))

    def test_varios_dias_seguidos_si_lo_son(self):
        RevisionSancionesDeuda.objects.create(fecha=self.hoy - timedelta(days=5))

        self.assertEqual(RevisionSancionesDeuda.dias_sin_ejecutar(self.hoy), 5)
        self.assertTrue(RevisionSancionesDeuda.hay_hueco(self.hoy))

    def test_no_haber_corrido_nunca_cuenta_como_hueco(self):
        """
        Es el caso más probable en un despliegue nuevo: que la tarea programada no se
        llegara a configurar. Tratarlo como "sin datos, no opino" lo dejaría invisible
        justo cuando más falta hace verlo.
        """
        self.assertTrue(RevisionSancionesDeuda.hay_hueco(self.hoy))

    def test_manda_la_ejecucion_mas_reciente(self):
        """Que haya huecos antiguos da igual si el proceso volvió a la normalidad."""
        RevisionSancionesDeuda.objects.create(fecha=self.hoy - timedelta(days=40))
        RevisionSancionesDeuda.objects.create(fecha=self.hoy)

        self.assertFalse(RevisionSancionesDeuda.hay_hueco(self.hoy))


class AlertaDelComandoTest(TestCase):

    def _correr(self, *args):
        out, err = StringIO(), StringIO()
        call_command('revisar_sanciones_por_deuda', *args, stdout=out, stderr=err)
        return out.getvalue(), err.getvalue()

    def test_avisa_por_stderr_y_por_log_critical(self):
        """
        CRITICAL y no WARNING a propósito: es el nivel al que se enganchan las alertas, y
        un aviso que nadie recibe no sirve de nada.
        """
        RevisionSancionesDeuda.objects.create(
            fecha=timezone.localdate() - timedelta(days=10))

        with self.assertLogs(
                'solicitudes.management.commands.revisar_sanciones_por_deuda',
                level='CRITICAL') as registro:
            _, err = self._correr('--dry-run')

        self.assertIn(MARCADOR_ALERTA, err)
        self.assertIn('10 días sin ejecutarse', err)
        self.assertIn(MARCADOR_ALERTA, registro.output[0])

    def test_lo_dice_tambien_si_nunca_corrio(self):
        with self.assertLogs(
                'solicitudes.management.commands.revisar_sanciones_por_deuda',
                level='CRITICAL'):
            _, err = self._correr('--dry-run')

        self.assertIn(MARCADOR_ALERTA, err)
        self.assertIn('NUNCA', err)

    def test_en_marcha_normal_no_molesta(self):
        """Una alerta que salta todos los días deja de leerse."""
        RevisionSancionesDeuda.objects.create(fecha=timezone.localdate())

        _, err = self._correr('--dry-run')

        self.assertNotIn(MARCADOR_ALERTA, err)

    def test_la_alerta_no_impide_que_la_revision_haga_su_trabajo(self):
        """Denunciar el hueco y recuperarse son cosas distintas: hay que hacer las dos."""
        _, err = self._correr()

        self.assertIn(MARCADOR_ALERTA, err)
        self.assertTrue(
            RevisionSancionesDeuda.objects.filter(fecha=timezone.localdate()).exists(),
            'la pasada de hoy debe quedar registrada igualmente')


class AvisoEnDashboardTest(TestCase):

    def setUp(self):
        jefe = User.objects.create_user('cron.jefe', password='x', is_staff=True)
        Empleado.objects.create(user=jefe, nombre='Jefa', apellido='C',
                                cedula='7001', activo=True)
        self.client.force_login(jefe)

    def test_el_supervisor_ve_el_aviso(self):
        r = self.client.get(reverse('dashboard'))

        self.assertTrue(r.context['revision_dias_sin_correr'])
        self.assertContains(r, 'no se está ejecutando')

    def test_no_aparece_cuando_el_proceso_va_al_dia(self):
        RevisionSancionesDeuda.objects.create(fecha=timezone.localdate())

        r = self.client.get(reverse('dashboard'))

        self.assertFalse(r.context['revision_dias_sin_correr'])
        self.assertNotContains(r, 'no se está ejecutando')

    def test_un_explorador_normal_no_lo_ve(self):
        """Es un aviso operativo: al explorador no le dice nada y solo le preocupa."""
        emp = User.objects.create_user('cron.exp', password='x')
        Empleado.objects.create(user=emp, nombre='Explo', apellido='C',
                                cedula='7002', activo=True)
        self.client.force_login(emp)

        r = self.client.get(reverse('dashboard'))

        self.assertFalse(r.context['revision_dias_sin_correr'])


class MarcadorDeAlertaTest(TestCase):
    """
    El marcador es un CONTRATO con la infraestructura: las alarmas de producción filtran
    por esta cadena exacta. Si alguien la cambia, las alertas dejan de dispararse sin que
    falle nada visible, y nadie se entera hasta que hace falta.
    """

    def test_el_marcador_no_cambia(self):
        self.assertEqual(MARCADOR_ALERTA, 'REVISION_SANCIONES_NO_EJECUTADA')

    def test_no_lleva_acentos_ni_espacios(self):
        """Tiene que sobrevivir a un grep y a un metric filter sin escapes raros."""
        self.assertTrue(MARCADOR_ALERTA.isascii())
        self.assertNotIn(' ', MARCADOR_ALERTA)

    def test_sale_al_principio_del_mensaje(self):
        from io import StringIO

        from django.core.management import call_command

        err = StringIO()
        call_command('revisar_sanciones_por_deuda', '--dry-run', stderr=err)

        self.assertTrue(err.getvalue().lstrip().startswith(MARCADOR_ALERTA))
