"""
Pago de Horas (PDH): registro, listado y borrado.

Cubre los huecos que tenía el flujo: errores que no se veían, tope de horas sin aplicar,
fechas incoherentes, IDs no numéricos y la fecha de pago desincronizada al editar.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse

from empleados.models import Empleado
from permisos.models import PDH, PermisoEspecial
from permisos.pago_horas_service import PagoHorasService
from solicitudes.models import DeudaCorporativa


class PagoHorasBase(TestCase):
    def setUp(self):
        jefe = User.objects.create_user('pdh.jefe', password='x', is_staff=True)
        self.supervisor = Empleado.objects.create(user=jefe, nombre='Jefa', apellido='Turno',
                                                  cedula='9001', activo=True)
        emp = User.objects.create_user('pdh.emp', password='x')
        self.explorador = Empleado.objects.create(user=emp, nombre='Explo', apellido='Rador',
                                                  cedula='9002', activo=True)
        self.client = Client()
        self.client.force_login(jefe)
        self.ayer = date.today() - timedelta(days=1)

    def _deuda(self, minutos=30, fecha=None):
        return DeudaCorporativa.objects.create(
            explorador=self.explorador, minutos=minutos,
            fecha_doblada=fecha or self.ayer, estado='activa',
        )


class AplicarPagoTest(PagoHorasBase):

    def test_pago_marca_la_deuda_y_la_vincula(self):
        d = self._deuda()
        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador,
            fecha=date.today(), keys=[f'doblada:{d.id}'],
        )
        self.assertIsNone(error)
        d.refresh_from_db()
        self.assertEqual(d.estado, 'pagada')
        self.assertEqual(d.fecha_pago, date.today())
        self.assertEqual(float(pdh.horas), 0.5)
        self.assertEqual(list(pdh.deudas_pagadas.all()), [d])

    def test_deuda_ya_pagada_no_se_cobra_dos_veces(self):
        """El check de 'sigue pendiente' es lo que impide el doble descuento."""
        d = self._deuda()
        PagoHorasService.aplicar_pago(supervisor=self.supervisor, explorador=self.explorador,
                                      fecha=date.today(), keys=[f'doblada:{d.id}'])
        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador,
            fecha=date.today(), keys=[f'doblada:{d.id}'],
        )
        self.assertIsNone(pdh)
        self.assertIn('ya no está pendiente', error)
        self.assertEqual(PDH.objects.count(), 1)

    def test_misma_deuda_repetida_en_el_post_cuenta_una_vez(self):
        d = self._deuda()
        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador, fecha=date.today(),
            keys=[f'doblada:{d.id}', f'doblada:{d.id}'],
        )
        self.assertIsNone(error)
        self.assertEqual(float(pdh.horas), 0.5)

    def test_tope_de_24_horas(self):
        """PDH.clean() limita a 24 h, pero solo se aplica si alguien lo ejecuta."""
        keys = []
        for i in range(50):  # 50 × 0.5 h = 25 h
            keys.append(f'doblada:{self._deuda(fecha=self.ayer - timedelta(days=i)).id}')
        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador, fecha=date.today(), keys=keys,
        )
        self.assertIsNone(pdh)
        self.assertIn('24', error)
        self.assertEqual(PDH.objects.count(), 0)
        self.assertEqual(DeudaCorporativa.objects.filter(estado='activa').count(), 50)

    def test_fecha_futura_rechazada(self):
        d = self._deuda()
        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador,
            fecha=date.today() + timedelta(days=3), keys=[f'doblada:{d.id}'],
        )
        self.assertIsNone(pdh)
        self.assertIn('futura', error)

    def test_fecha_anterior_a_la_deuda_rechazada(self):
        d = self._deuda(fecha=date.today() - timedelta(days=2))
        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador,
            fecha=date.today() - timedelta(days=5), keys=[f'doblada:{d.id}'],
        )
        self.assertIsNone(pdh)
        self.assertIn('anterior', error)

    def test_permiso_pagado_y_revertido(self):
        p = PermisoEspecial.objects.create(
            empleado=self.explorador, tipo='PERSONAL', fecha_inicio=self.ayer,
            fecha_fin=self.ayer, tiempo=2, motivo='x', estado='APROBADO',
        )
        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador,
            fecha=date.today(), keys=[f'permiso:{p.id}'],
        )
        self.assertIsNone(error)
        p.refresh_from_db()
        self.assertTrue(p.pagado)

        PagoHorasService.revertir_pago(pdh)
        p.refresh_from_db()
        self.assertFalse(p.pagado)
        self.assertIsNone(p.fecha_pago)


class PDHVistasTest(PagoHorasBase):

    def test_error_del_post_se_muestra_y_conserva_lo_escrito(self):
        """Antes se hacía redirect y el mensaje se perdía: la página volvía vacía y en silencio."""
        r = self.client.post(reverse('pdh_create'), {
            'explorador': str(self.explorador.id),
            'fecha': date.today().strftime('%Y-%m-%d'),
            'comentario': 'nota de prueba',
            'deudas': [],
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'al menos una deuda')
        self.assertContains(r, 'nota de prueba')

    def test_fecha_invalida_no_revienta(self):
        d = self._deuda()
        r = self.client.post(reverse('pdh_create'), {
            'explorador': str(self.explorador.id), 'fecha': 'no-es-fecha',
            'deudas': [f'doblada:{d.id}'],
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'no es válida')

    def test_explorador_no_numerico_no_revienta(self):
        r = self.client.get(reverse('pdh_deudas_pendientes'), {'explorador_id': 'abc'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['success'])

    def test_supervisor_sin_ficha_de_empleado_recibe_aviso(self):
        u = User.objects.create_user('staff.sin.ficha', password='x', is_staff=True)
        self.client.force_login(u)
        d = self._deuda()
        r = self.client.post(reverse('pdh_create'), {
            'explorador': str(self.explorador.id), 'fecha': date.today().strftime('%Y-%m-%d'),
            'deudas': [f'doblada:{d.id}'],
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'ficha de empleado')
        self.assertEqual(PDH.objects.count(), 0)

    def test_editar_la_fecha_sincroniza_las_deudas(self):
        d = self._deuda()
        pdh, _ = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador,
            fecha=date.today(), keys=[f'doblada:{d.id}'],
        )
        nueva = self.ayer
        r = self.client.post(reverse('pdh_edit', args=[pdh.id]),
                             {'fecha': nueva.strftime('%Y-%m-%d'), 'comentario': 'corregido'})
        self.assertEqual(r.status_code, 302)
        d.refresh_from_db()
        self.assertEqual(d.fecha_pago, nueva)

    def test_borrar_reactiva_la_deuda(self):
        d = self._deuda()
        pdh, _ = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador,
            fecha=date.today(), keys=[f'doblada:{d.id}'],
        )
        r = self.client.post(reverse('pdh_delete', args=[pdh.id]))
        self.assertEqual(r.status_code, 302)
        d.refresh_from_db()
        self.assertEqual(d.estado, 'activa')
        self.assertIsNone(d.fecha_pago)

    def test_listado_filtra_y_pagina(self):
        otro_u = User.objects.create_user('otro.explo', password='x')
        otro = Empleado.objects.create(user=otro_u, nombre='Otro', apellido='Uno',
                                       cedula='9003', activo=True)
        for emp in (self.explorador, otro):
            d = DeudaCorporativa.objects.create(explorador=emp, minutos=30,
                                                fecha_doblada=self.ayer, estado='activa')
            PagoHorasService.aplicar_pago(supervisor=self.supervisor, explorador=emp,
                                          fecha=date.today(), keys=[f'doblada:{d.id}'])
        r = self.client.get(reverse('pdh_list'), {'explorador': str(otro.id)})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p.explorador_id for p in r.context['pdhs']], [otro.id])
