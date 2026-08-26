"""
Las PANTALLAS deben bloquear al sancionado, no solo el POST.

El caso real: un explorador con deudas de julio sin pagar seguía entrando a los formularios
en agosto. La regla de sanción existía y era correcta, pero la sanción nace PEREZOSA —solo
cuando algo llama a `gestionar_sancion_por_deuda`— y las pantallas consultaban
`sancion_activa()` a secas. Como nadie la había disparado, la sanción no existía todavía y la
consulta respondía "no sancionado": las tarjetas se ofrecían, el formulario se abría y el
bloqueo aparecía recién al enviar.

Estos tests parten del estado que producía el fallo: deuda vencida y CERO sanciones en BD.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado, SancionEmpleado
from solicitudes.models import DeudaCorporativa, TipoSolicitudCambio


class BloqueoPantallasPorSancionTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-pant', password='x'),
            nombre='Supervisora', apellido='Test', cedula='sup-pant', activo=True)
        cls.exp = Empleado.objects.create(
            user=User.objects.create_user(username='exp-pant', password='x'),
            nombre='Explorador', apellido='Test', cedula='exp-pant',
            activo=True, supervisor=cls.sup)
        cls.tipo = TipoSolicitudCambio.objects.create(
            nombre='CAMBIO DE TURNO', codigo_estrategia='CT', activo=True)

    def setUp(self):
        self.hoy = timezone.localdate()
        self.client.force_login(self.exp.user)

    def _deuda_vencida(self):
        """Deuda de un mes anterior sin pagar: la que debe sancionar. Nadie la ha evaluado aún."""
        mes_pasado = self.hoy.replace(day=1) - timedelta(days=1)
        DeudaCorporativa.objects.create(
            explorador=self.exp, minutos=30, fecha_doblada=mes_pasado, estado='activa')
        assert not SancionEmpleado.objects.filter(explorador=self.exp).exists()

    # ------------------------------------------------------- listado de tipos
    def test_el_listado_avisa_y_no_ofrece_iniciar(self):
        self._deuda_vencida()

        resp = self.client.get(reverse('solicitudes:cambio_turno_inicio'))

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context['sancion_msg'], 'la pantalla debe explicar el bloqueo')
        self.assertContains(resp, 'Bloqueado por sanción')
        self.assertNotContains(resp, reverse(
            'solicitudes:solicitar_cambio_turno', args=[self.tipo.id]))

    def test_el_listado_crea_la_sancion_que_nadie_habia_disparado(self):
        """Entrar a la pantalla es suficiente para que la sanción exista: ese era el agujero."""
        self._deuda_vencida()

        self.client.get(reverse('solicitudes:cambio_turno_inicio'))

        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.exp).count(), 1)

    # ----------------------------------------------------------- formulario
    def test_el_formulario_redirige_en_vez_de_abrirse(self):
        self._deuda_vencida()

        resp = self.client.get(
            reverse('solicitudes:solicitar_cambio_turno', args=[self.tipo.id]), follow=True)

        self.assertRedirects(resp, reverse('solicitudes:cambio_turno_inicio'))
        mensajes = [str(m) for m in resp.context['messages']]
        self.assertTrue(any('sancionado' in m.lower() for m in mensajes), mensajes)

    def test_entrar_por_la_url_directa_tampoco_abre_el_formulario(self):
        """Sin pasar por el listado: la comprobación no puede depender de la pantalla anterior."""
        self._deuda_vencida()

        resp = self.client.get(
            reverse('solicitudes:solicitar_cambio_turno', args=[self.tipo.id]))

        self.assertEqual(resp.status_code, 302)

    # -------------------------------------------------------- sin sanción
    def test_sin_deuda_vencida_todo_sigue_abierto(self):
        """La deuda del mes EN CURSO aún está en plazo: no sanciona ni estorba."""
        DeudaCorporativa.objects.create(
            explorador=self.exp, minutos=30, fecha_doblada=self.hoy, estado='activa')

        listado = self.client.get(reverse('solicitudes:cambio_turno_inicio'))
        form = self.client.get(
            reverse('solicitudes:solicitar_cambio_turno', args=[self.tipo.id]))

        self.assertFalse(listado.context.get('sancion_msg'))
        self.assertContains(listado, 'Iniciar Solicitud')
        self.assertEqual(form.status_code, 200)
        self.assertFalse(SancionEmpleado.objects.filter(explorador=self.exp).exists())

    def test_pagar_no_reabre_las_pantallas(self):
        """
        Pagar salda la deuda pero no levanta el castigo, así que la pantalla sigue cerrada.
        Antes se reabría en el acto: la sanción duraba lo que el moroso quisiera.
        """
        self._deuda_vencida()
        self.client.get(reverse('solicitudes:cambio_turno_inicio'))   # nace la sanción

        DeudaCorporativa.objects.filter(explorador=self.exp).update(estado='pagada')

        resp = self.client.get(reverse('solicitudes:cambio_turno_inicio'))
        self.assertTrue(resp.context.get('sancion_msg'))
        self.assertEqual(
            self.client.get(reverse('solicitudes:solicitar_cambio_turno',
                                    args=[self.tipo.id])).status_code, 302,
            'el formulario sigue redirigiendo')

    def test_cumplir_la_sancion_reabre_las_pantallas(self):
        """Lo que SÍ reabre: que termine el castigo. Es la única salida."""
        from empleados.models import SancionEmpleado

        self._deuda_vencida()
        self.client.get(reverse('solicitudes:cambio_turno_inicio'))   # nace la sanción
        SancionEmpleado.objects.filter(explorador=self.exp).update(
            fecha_inicio=self.hoy - timedelta(days=20),
            fecha_fin=self.hoy - timedelta(days=1))

        resp = self.client.get(reverse('solicitudes:cambio_turno_inicio'))

        self.assertFalse(resp.context.get('sancion_msg'))
        self.assertEqual(
            self.client.get(reverse('solicitudes:solicitar_cambio_turno',
                                    args=[self.tipo.id])).status_code, 200)
