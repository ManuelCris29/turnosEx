"""
Horas a favor del explorador (crédito corporativo).

El sistema de horas nació unidireccional. Estas pruebas cubren la dirección contraria: lo
que el supervisor o la corporación le deben AL explorador cuando le piden entrar antes de
su jornada, y cómo eso se descuenta de lo que él debe.

Las tres decisiones de negocio que blindan estas pruebas:
  1. Es una BOLSA: el remanente sobrevive al pago y queda para deudas futuras.
  2. Se consume en FIFO: primero el crédito más antiguo.
  3. NO toca la sanción: un mes vencido sigue sancionando aunque se salde con crédito.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from empleados.models import Empleado, SancionEmpleado
from permisos.credito_horas_service import CreditoHorasService
from permisos.deuda_permiso_service import sincronizar
from permisos.models import PDH, ConsumoCreditoHoras, CreditoHoras, PermisoEspecial
from permisos.pago_horas_service import PagoHorasService


class CreditoHorasBase(TestCase):

    def setUp(self):
        jefe = User.objects.create_user('credito.jefe', password='x', is_staff=True)
        self.supervisor = Empleado.objects.create(
            user=jefe, nombre='Jefa', apellido='Turno', cedula='9001', activo=True)
        emp = User.objects.create_user('credito.emp', password='x')
        self.explorador = Empleado.objects.create(
            user=emp, nombre='Explo', apellido='Rador', cedula='9002', activo=True,
            supervisor=self.supervisor)
        self.client = Client()
        self.client.force_login(jefe)

    def _credito(self, horas, fecha=None):
        """Reconoce `horas` a favor del explorador. Devuelve el crédito ya creado."""
        credito, error = CreditoHorasService.otorgar(
            explorador=self.explorador,
            fecha_hecho=fecha or date.today(),
            minutos=int(Decimal(str(horas)) * 60),
            motivo='Entró a las 07:00 en vez de las 08:00 por indicación del supervisor',
            otorgado_por=self.supervisor,
        )
        self.assertIsNone(error)
        return credito

    def _deuda_mes(self, horas='0.5', desplazamiento=0):
        """
        Una deuda de permiso de `horas` en el mes de hoy desplazado `n` meses.

        El mes se calcula desde hoy y no se escribe a mano: solo se puede pagar el mes en
        curso, así que un mes fijo dejaría de ser pagable al cambiar el calendario.
        """
        hoy = date.today()
        total = hoy.year * 12 + (hoy.month - 1) + desplazamiento
        dia = date(total // 12, total % 12 + 1, 10)
        permiso = PermisoEspecial.objects.create(
            empleado=self.explorador, tipo='PERSONAL', fecha_inicio=dia, fecha_fin=dia,
            tiempo=Decimal(str(horas)), motivo='x', estado='APROBADO',
            supervisor=self.supervisor)
        sincronizar(permiso)
        return permiso.deudas_mes.get()

    def _pagar(self, deuda, horas_credito=None):
        """Registra el PDH que salda `deuda`, aplicándole horas a favor si se indican."""
        pdh, error = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador, fecha=date.today(),
            keys=[f'permisomes:{deuda.id}'], comentario='pago')
        self.assertIsNone(error)
        if horas_credito is not None:
            _, error = CreditoHorasService.consumir(pdh, int(Decimal(str(horas_credito)) * 60))
            self.assertIsNone(error)
        return pdh


class OtorgarCreditoTests(CreditoHorasBase):

    def test_otorgar_deja_el_saldo_disponible(self):
        self._credito('1')
        self.assertEqual(CreditoHorasService.saldo_disponible(self.explorador), 60)
        self.assertEqual(CreditoHorasService.horas_disponibles(self.explorador), 1.0)

    def test_sin_motivo_no_se_otorga(self):
        credito, error = CreditoHorasService.otorgar(
            explorador=self.explorador, fecha_hecho=date.today(), minutos=60,
            motivo='   ', otorgado_por=self.supervisor)
        self.assertIsNone(credito)
        self.assertIn('motivo', error)
        self.assertFalse(CreditoHoras.objects.exists())

    def test_cero_horas_no_se_otorga(self):
        credito, error = CreditoHorasService.otorgar(
            explorador=self.explorador, fecha_hecho=date.today(), minutos=0,
            motivo='x', otorgado_por=self.supervisor)
        self.assertIsNone(credito)
        self.assertFalse(CreditoHoras.objects.exists())

    def test_un_credito_anulado_no_cuenta_en_el_saldo(self):
        credito = self._credito('1')
        _, error = CreditoHorasService.anular(credito, 'me equivoqué de explorador')
        self.assertIsNone(error)
        self.assertEqual(CreditoHorasService.saldo_disponible(self.explorador), 0)

    def test_un_credito_ya_consumido_no_se_puede_anular(self):
        credito = self._credito('0.5')
        self._pagar(self._deuda_mes('0.5'), horas_credito='0.5')
        credito.refresh_from_db()
        _, error = CreditoHorasService.anular(credito, 'error')
        self.assertIn('borra primero ese pago', error)


class ConsumoCreditoTests(CreditoHorasBase):

    def test_el_remanente_queda_a_favor_tras_saldar_una_deuda_menor(self):
        """
        El caso que motivó la funcionalidad: le deben 1 h y solo tiene 0.5 h por pagar.

        Antes esa media hora restante desaparecía —no había dónde anotarla—; ahora la
        deuda queda saldada y le siguen debiendo 30 min, disponibles para la próxima.
        """
        self._credito('1')
        deuda = self._deuda_mes('0.5')

        self._pagar(deuda, horas_credito='0.5')

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'pagada')
        self.assertEqual(CreditoHorasService.saldo_disponible(self.explorador), 30)

    def test_se_consume_primero_el_credito_mas_antiguo(self):
        hoy = date.today()
        viejo = self._credito('0.5', fecha=date(hoy.year - 1, 1, 15))
        nuevo = self._credito('0.5', fecha=hoy)

        self._pagar(self._deuda_mes('0.5'), horas_credito='0.5')

        viejo.refresh_from_db()
        nuevo.refresh_from_db()
        self.assertEqual(viejo.estado, 'consumido')
        self.assertEqual(viejo.minutos_pendientes, 0)
        self.assertEqual(nuevo.estado, 'activo')
        self.assertEqual(nuevo.minutos_pendientes, 30)

    def test_un_consumo_se_reparte_entre_varios_creditos(self):
        hoy = date.today()
        self._credito('0.5', fecha=date(hoy.year - 1, 1, 15))
        self._credito('0.5', fecha=hoy)

        self._pagar(self._deuda_mes('1'), horas_credito='1')

        self.assertEqual(ConsumoCreditoHoras.objects.count(), 2)
        self.assertEqual(CreditoHorasService.saldo_disponible(self.explorador), 0)

    def test_no_se_puede_consumir_mas_credito_del_disponible(self):
        self._credito('0.5')
        pdh, _ = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador, fecha=date.today(),
            keys=[f'permisomes:{self._deuda_mes("2").id}'], comentario='pago')

        consumos, error = CreditoHorasService.consumir(pdh, 120)

        self.assertIsNone(consumos)
        self.assertIn('0.5 h a favor disponibles', error)
        # Nada a medias: el crédito sigue intacto.
        self.assertEqual(CreditoHorasService.saldo_disponible(self.explorador), 30)
        self.assertFalse(ConsumoCreditoHoras.objects.exists())

    def test_el_credito_no_puede_superar_las_horas_del_pago(self):
        """El crédito es un medio de pago del PDH: cubrir más descontaría dos veces."""
        self._credito('5')
        pdh, _ = PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador, fecha=date.today(),
            keys=[f'permisomes:{self._deuda_mes("1").id}'], comentario='pago')

        consumos, error = CreditoHorasService.consumir(pdh, 300)

        self.assertIsNone(consumos)
        self.assertIn('no pueden superar', error)
        self.assertEqual(CreditoHorasService.saldo_disponible(self.explorador), 300)


class ReversionCreditoTests(CreditoHorasBase):

    def test_borrar_el_pago_devuelve_el_credito(self):
        credito = self._credito('0.5')
        pdh = self._pagar(self._deuda_mes('0.5'), horas_credito='0.5')
        credito.refresh_from_db()
        self.assertEqual(credito.estado, 'consumido')

        resp = self.client.post(reverse('pdh_delete', args=[pdh.id]))

        self.assertEqual(resp.status_code, 302)
        credito.refresh_from_db()
        self.assertEqual(credito.estado, 'activo')
        self.assertEqual(credito.minutos_pendientes, 30)
        self.assertFalse(ConsumoCreditoHoras.objects.exists())

    def test_un_credito_anulado_no_revive_al_borrar_el_pago(self):
        """
        Anular es una corrección administrativa: esas horas ya se decidió que no le
        correspondían, así que borrar el pago no puede devolvérselas.
        """
        credito = self._credito('0.5')
        pdh = self._pagar(self._deuda_mes('0.5'), horas_credito='0.5')
        CreditoHoras.objects.filter(id=credito.id).update(estado='anulado')

        CreditoHorasService.revertir_consumos(pdh)

        credito.refresh_from_db()
        self.assertEqual(credito.estado, 'anulado')
        self.assertEqual(credito.minutos_consumidos, 30)
        self.assertFalse(ConsumoCreditoHoras.objects.exists())


class CreditoYSancionTests(CreditoHorasBase):

    def test_el_credito_no_evita_la_sancion_de_un_mes_vencido(self):
        """
        Decisión de negocio deliberada: lo sancionable es haber dejado vencer el plazo, no
        el importe. Tener horas a favor de sobra no exime de la sanción del mes cerrado.
        """
        from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService

        self._credito('10')
        self._deuda_mes('2', desplazamiento=-1)  # mes pasado: ya vencido

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.explorador)

        self.assertTrue(
            SancionEmpleado.objects.filter(explorador=self.explorador).exists(),
            'El crédito no debe impedir la sanción por un mes vencido.')


class ConsolidadoConCreditoTests(CreditoHorasBase):

    def test_el_consolidado_separa_la_deuda_de_las_horas_a_favor(self):
        from turnos.services.consolidado_horas_service import ConsolidadoHorasService

        self._credito('1')
        self._deuda_mes('0.5')

        datos = ConsolidadoHorasService.get_consolidado(self.explorador)

        self.assertEqual(datos['total_horas'], 0.5)   # lo que él debe, intacto
        self.assertEqual(datos['total_credito'], 1.0)  # lo que le deben
        self.assertEqual(datos['saldo_neto'], -0.5)    # negativo = a su favor
        self.assertEqual(len(datos['creditos']), 1)

    def test_sin_creditos_el_neto_es_el_saldo(self):
        from turnos.services.consolidado_horas_service import ConsolidadoHorasService

        self._deuda_mes('0.5')
        datos = ConsolidadoHorasService.get_consolidado(self.explorador)

        self.assertEqual(datos['total_credito'], 0)
        self.assertEqual(datos['saldo_neto'], datos['total_horas'])


class PantallaPDHConCreditoTests(CreditoHorasBase):

    def test_el_ajax_informa_del_saldo_a_favor(self):
        self._credito('1')
        resp = self.client.get(reverse('pdh_deudas_pendientes'),
                               {'explorador_id': self.explorador.id})
        self.assertEqual(resp.json()['horas_credito'], 1.0)

    def test_registrar_un_pago_aplicando_horas_a_favor(self):
        self._credito('1')
        deuda = self._deuda_mes('0.5')

        resp = self.client.post(reverse('pdh_create'), {
            'explorador': self.explorador.id,
            'fecha': date.today().isoformat(),
            'comentario': 'pago con horas a favor',
            'deudas': [f'permisomes:{deuda.id}'],
            'horas_credito': '0.5',
        })

        self.assertEqual(resp.status_code, 302)
        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'pagada')
        self.assertEqual(CreditoHorasService.saldo_disponible(self.explorador), 30)

    def test_un_credito_excesivo_no_deja_el_pago_a_medias(self):
        """Si el crédito no se puede aplicar, el PDH entero se deshace."""
        self._credito('0.25')
        deuda = self._deuda_mes('0.5')

        resp = self.client.post(reverse('pdh_create'), {
            'explorador': self.explorador.id,
            'fecha': date.today().isoformat(),
            'comentario': 'pago',
            'deudas': [f'permisomes:{deuda.id}'],
            'horas_credito': '5',
        })

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PDH.objects.exists())
        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'activa')
        self.assertEqual(CreditoHorasService.saldo_disponible(self.explorador), 15)


class CreditoCRUDTests(CreditoHorasBase):

    def test_registrar_horas_a_favor_desde_la_pantalla(self):
        resp = self.client.post(reverse('credito_create'), {
            'explorador': self.explorador.id,
            'fecha_hecho': date.today().isoformat(),
            'horas': '1',
            'motivo': 'Entró a las 07:00 en vez de las 08:00',
        })

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(CreditoHorasService.saldo_disponible(self.explorador), 60)

    def test_el_minimo_del_campo_esta_alineado_con_el_paso(self):
        """
        En HTML5 los pasos de un `<input type=number>` se cuentan DESDE el mínimo, no desde
        cero. Con min=0.01 y step=0.25 las flechas del campo ofrecían 0.01, 0.26, 0.51… —
        valores que el propio formulario rechazaba después por no ser múltiplos de 0.25.
        """
        from empleados.forms import CreditoHorasForm
        campo = str(CreditoHorasForm()['horas'])
        self.assertIn('step="0.25"', campo)
        self.assertIn('min="0.25"', campo)

    def test_un_importe_invalido_da_un_solo_error(self):
        """
        El tope de «mayores a cero» vive en un validador del campo y no en `Model.clean()`.
        Estando en `clean()` corría aunque el formulario ya hubiera fallado en `horas`, y
        añadía un segundo error contradictorio encima del real.
        """
        from empleados.forms import CreditoHorasForm
        form = CreditoHorasForm({'explorador': self.explorador.id,
                                 'fecha_hecho': date.today().isoformat(),
                                 'horas': '0.51', 'motivo': 'x'})

        self.assertFalse(form.is_valid())
        self.assertEqual(list(form.errors), ['horas'])
        self.assertIn('múltiplos de 0.25', form.errors['horas'][0])

    def test_las_horas_deben_ir_en_cuartos_de_hora(self):
        resp = self.client.post(reverse('credito_create'), {
            'explorador': self.explorador.id,
            'fecha_hecho': date.today().isoformat(),
            'horas': '0.37',
            'motivo': 'x',
        })

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CreditoHoras.objects.exists())

    def test_el_listado_muestra_el_saldo_del_explorador_filtrado(self):
        self._credito('1')
        resp = self.client.get(reverse('credito_list'), {'explorador': self.explorador.id})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['saldo_horas'], 1.0)
