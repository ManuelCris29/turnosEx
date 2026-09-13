"""
Una deuda vencida ya no se paga.

La deuda de un mes vence al cerrarse ese mes. A partir de ahí deja de ser cobrable: se
extingue cuando el explorador termina de cumplir la sanción que ese incumplimiento generó
(la sanción ES el pago). Aceptar además un PDH cobraría dos veces lo mismo, y le daría al
supervisor la impresión —falsa desde que la sanción se cumple entera— de que pagando
levanta el bloqueo.

La casilla deshabilitada en la pantalla es una cortesía; la defensa está en el servicio,
porque el POST se puede reenviar con la lista de meses de ayer.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from empleados.models import Empleado
from permisos.models import PDH, PermisoEspecial
from permisos.services.deuda_permiso_service import sincronizar
from permisos.services.pago_horas_service import PagoHorasService
from solicitudes.models import DeudaCorporativa
from solicitudes.services.sancion_deuda_calculo import Periodo


class PeriodoVencidoTest(TestCase):
    """El corte es puro: el mismo día decide aquí y en la sanción."""

    def test_el_mes_en_curso_no_esta_vencido(self):
        self.assertFalse(Periodo(2026, 8).esta_vencido(date(2026, 8, 26)))

    def test_el_ultimo_dia_del_mes_todavia_no_esta_vencido(self):
        self.assertFalse(Periodo(2026, 8).esta_vencido(date(2026, 8, 31)))

    def test_vence_el_dia_siguiente_al_cierre(self):
        self.assertTrue(Periodo(2026, 8).esta_vencido(date(2026, 9, 1)))

    def test_un_mes_futuro_nunca_esta_vencido(self):
        self.assertFalse(Periodo(2026, 12).esta_vencido(date(2026, 8, 26)))


class DeudaVencidaBase(TestCase):

    def setUp(self):
        jefe = User.objects.create_user('venc.jefe', password='x', is_staff=True)
        self.supervisor = Empleado.objects.create(
            user=jefe, nombre='Jefa', apellido='Turno', cedula='7001', activo=True)
        emp = User.objects.create_user('venc.emp', password='x')
        self.explorador = Empleado.objects.create(
            user=emp, nombre='Explo', apellido='Rador', cedula='7002', activo=True,
            supervisor=self.supervisor)
        self.client = Client()
        self.client.force_login(jefe)
        # Fechas relativas a un "hoy" inyectado: la prueba no depende del día real.
        self.hoy = date(2026, 8, 26)
        self.este_mes = date(2026, 8, 10)
        self.mes_pasado = date(2026, 7, 10)

    def _doblada(self, fecha, minutos=30):
        return DeudaCorporativa.objects.create(
            explorador=self.explorador, minutos=minutos, fecha_doblada=fecha, estado='activa')

    def _permiso_mes(self, fecha, horas='2'):
        permiso = PermisoEspecial.objects.create(
            empleado=self.explorador, tipo='PERSONAL', fecha_inicio=fecha, fecha_fin=fecha,
            tiempo=Decimal(horas), motivo='x', estado='APROBADO', supervisor=self.supervisor)
        sincronizar(permiso)
        return permiso.deudas_mes.get()

    def _pagar(self, keys):
        return PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador, fecha=self.hoy,
            keys=keys, comentario='pago', hoy=self.hoy)


class DeudasPendientesMarcanLoPagableTest(DeudaVencidaBase):

    def test_el_mes_en_curso_es_pagable(self):
        self._doblada(self.este_mes)

        (mes,) = PagoHorasService.deudas_pendientes(self.explorador, hoy=self.hoy)

        self.assertFalse(mes['vencido'])
        self.assertTrue(mes['pagable'])

    def test_el_mes_cerrado_no_es_pagable(self):
        self._doblada(self.mes_pasado)

        (mes,) = PagoHorasService.deudas_pendientes(self.explorador, hoy=self.hoy)

        self.assertTrue(mes['vencido'])
        self.assertFalse(mes['pagable'],
                         'un mes vencido se sigue viendo, pero con la casilla deshabilitada')

    def test_cada_mes_decide_por_separado(self):
        self._doblada(self.mes_pasado)
        self._doblada(self.este_mes)

        julio, agosto = PagoHorasService.deudas_pendientes(self.explorador, hoy=self.hoy)

        self.assertFalse(julio['pagable'])
        self.assertTrue(agosto['pagable'])


class AplicarPagoRechazaVencidasTest(DeudaVencidaBase):

    def test_no_se_puede_pagar_una_doblada_de_un_mes_cerrado(self):
        d = self._doblada(self.mes_pasado)

        pdh, error = self._pagar([f'doblada:{d.id}'])

        self.assertIsNone(pdh)
        self.assertIn('julio 2026', error)
        d.refresh_from_db()
        self.assertEqual(d.estado, 'activa', 'la deuda no se toca')
        self.assertFalse(PDH.objects.exists())

    def test_no_se_puede_pagar_un_permiso_de_un_mes_cerrado(self):
        deuda = self._permiso_mes(self.mes_pasado)

        pdh, error = self._pagar([f'permisomes:{deuda.id}'])

        self.assertIsNone(pdh)
        self.assertIn('julio 2026', error)
        deuda.refresh_from_db()
        self.assertEqual(deuda.minutos_pagados, 0)

    def test_una_sola_vencida_anula_el_pago_entero(self):
        """Nada de saldar la mitad en silencio: el supervisor corrige y reenvía."""
        vieja = self._doblada(self.mes_pasado)
        nueva = self._doblada(self.este_mes)

        pdh, error = self._pagar([f'doblada:{vieja.id}', f'doblada:{nueva.id}'])

        self.assertIsNone(pdh)
        nueva.refresh_from_db()
        self.assertEqual(nueva.estado, 'activa')

    def test_el_mes_en_curso_se_sigue_pagando(self):
        d = self._doblada(self.este_mes)

        pdh, error = self._pagar([f'doblada:{d.id}'])

        self.assertIsNone(error)
        d.refresh_from_db()
        self.assertEqual(d.estado, 'pagada')

    def test_el_ultimo_dia_del_mes_todavia_se_puede_pagar(self):
        d = self._doblada(date(2026, 8, 1))

        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador, fecha=date(2026, 8, 31),
            keys=[f'doblada:{d.id}'], comentario='in extremis', hoy=date(2026, 8, 31))

        self.assertIsNone(error)

    def test_la_vista_muestra_el_error_sin_perder_la_seleccion(self):
        """Con el reloj real: una deuda de hace dos meses está vencida cualquier día."""
        vieja = self._doblada((date.today().replace(day=1) - timedelta(days=1)).replace(day=1)
                              - timedelta(days=1))

        r = self.client.post(reverse('pdh_create'), {
            'explorador': str(self.explorador.id),
            'fecha': date.today().strftime('%Y-%m-%d'),
            'comentario': 'intento de pago tardío',
            'deudas': [f'doblada:{vieja.id}'],
        }, follow=True)

        self.assertContains(r, 'ya venció')
        self.assertFalse(PDH.objects.exists())
