"""
Pago parcial de una deuda mensual, y la pantalla de PDH desglosada por mes.

Antes la unidad mínima de pago era el permiso ENTERO, con dos consecuencias: no se podía
abonar una parte, y un permiso permanente largo resultaba directamente impagable porque su
total superaba el tope de 24 h de un solo registro y no había forma de trocearlo. Ahora la
unidad es el mes, y dentro del mes se puede abonar el importe que se acuerde.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from empleados.models import Empleado
from permisos.models import PDH, PagoDeudaPermisoMes, PermisoEspecial
from permisos.services.deuda_permiso_service import sincronizar
from permisos.services.pago_horas_service import PagoHorasService


class PagoParcialBase(TestCase):

    def setUp(self):
        jefe = User.objects.create_user('parcial.jefe', password='x', is_staff=True)
        self.supervisor = Empleado.objects.create(
            user=jefe, nombre='Jefa', apellido='Turno', cedula='8001', activo=True)
        emp = User.objects.create_user('parcial.emp', password='x')
        self.explorador = Empleado.objects.create(
            user=emp, nombre='Explo', apellido='Rador', cedula='8002', activo=True,
            supervisor=self.supervisor)
        self.client = Client()
        self.client.force_login(jefe)

    def _permiso_mes(self, horas='2', anio=None, mes=None):
        """Un permiso puntual de `horas` en el mes indicado, ya con su deuda mensual.

        Por defecto, el mes EN CURSO — y no puede volver a fijarse a un mes concreto.
        Este archivo se escribió con `2026-08` escrito a mano porque entonces era el mes
        abierto, y al llegar septiembre esos meses pasaron a estar vencidos: solo se puede
        pagar el mes en curso (ver `pago_horas_service`), así que 15 pruebas de PAGO PARCIAL
        empezaron a fallar por una regla que ninguna de ellas estaba probando.
        Quien sí prueba el vencimiento es `test_los_meses_ya_cerrados_se_marcan_como_vencidos`,
        que calcula el mes pasado a partir de hoy y por eso nunca caducó.
        """
        hoy = date.today()
        anio = hoy.year if anio is None else anio
        mes = hoy.month if mes is None else mes
        dia = date(anio, mes, 10)
        permiso = PermisoEspecial.objects.create(
            empleado=self.explorador, tipo='PERSONAL', fecha_inicio=dia, fecha_fin=dia,
            tiempo=Decimal(horas), motivo='x', estado='APROBADO', supervisor=self.supervisor)
        sincronizar(permiso)
        return permiso, permiso.deudas_mes.get()

    @staticmethod
    def _mes(desplazamiento):
        """Día 10 del mes de hoy desplazado `n` meses. Sin dependencias, y sin saltos raros
        por longitud de mes: el día 10 existe en todos."""
        hoy = date.today()
        total = (hoy.year * 12 + hoy.month - 1) + desplazamiento
        return date(total // 12, total % 12 + 1, 10)

    @staticmethod
    def _etiqueta_mes_actual():
        from permisos.services.pago_horas_service import _MESES
        hoy = date.today()
        return f'{_MESES[hoy.month - 1]} {hoy.year}'

    def _pagar(self, deuda, horas=None):
        importes = {f'permisomes:{deuda.id}': str(horas)} if horas is not None else None
        return PagoHorasService.aplicar_pago(
            supervisor=self.supervisor, explorador=self.explorador,
            fecha=date.today(), keys=[f'permisomes:{deuda.id}'],
            comentario='pago', importes=importes)


class PagoParcialTest(PagoParcialBase):

    def test_caso_8_pagar_una_parte_deja_el_resto_pendiente(self):
        _, deuda = self._permiso_mes(horas='2')

        pdh, error = self._pagar(deuda, horas='1')

        self.assertIsNone(error)
        deuda.refresh_from_db()
        self.assertEqual(deuda.minutos_pagados, 60)
        self.assertEqual(deuda.minutos_pendientes, 60)
        self.assertEqual(float(pdh.horas), 1.0)

    def test_un_mes_a_medias_sigue_estando_activo(self):
        """Si se marcara pagado, dejaría de reclamarse y de sancionar por lo que falta."""
        _, deuda = self._permiso_mes(horas='2')

        self._pagar(deuda, horas='1')

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'activa')
        self.assertIsNone(deuda.fecha_pago)

    def test_un_mes_a_medias_sigue_apareciendo_en_la_pantalla(self):
        _, deuda = self._permiso_mes(horas='2')
        self._pagar(deuda, horas='1')

        meses = PagoHorasService.deudas_pendientes(self.explorador)

        (agosto,) = meses
        self.assertEqual(agosto['horas_pendientes'], 1.0)
        self.assertEqual(agosto['horas_pagadas'], 1.0)

    def test_completar_el_pago_lo_salda(self):
        _, deuda = self._permiso_mes(horas='2')
        self._pagar(deuda, horas='1')
        deuda.refresh_from_db()

        self._pagar(deuda, horas='1')

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'pagada')
        self.assertEqual(deuda.minutos_pendientes, 0)

    def test_la_fecha_de_pago_es_la_del_abono_que_salda(self):
        """
        De ella depende si el periodo cuenta como cumplido. Hasta el último abono el
        explorador seguía debiendo, así que un pago a cuenta no puede fechar la deuda.
        """
        _, deuda = self._permiso_mes(horas='2')

        self._pagar(deuda, horas='1')
        deuda.refresh_from_db()
        self.assertIsNone(deuda.fecha_pago)

        self._pagar(deuda, horas='1')
        deuda.refresh_from_db()
        self.assertEqual(deuda.fecha_pago, date.today())

    def test_sin_importe_se_paga_el_mes_entero(self):
        """El caso corriente: marcar la casilla y no tocar nada más."""
        _, deuda = self._permiso_mes(horas='2')

        self._pagar(deuda)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'pagada')

    def test_no_se_puede_pagar_mas_de_lo_que_se_debe(self):
        """
        Se rechaza en vez de recortarlo: casi siempre es un error de tecleo, y aceptarlo
        dejaría el PDH afirmando que se abonó más de lo debido.
        """
        _, deuda = self._permiso_mes(horas='2')

        pdh, error = self._pagar(deuda, horas='5')

        self.assertIsNone(pdh)
        self.assertIn('pendientes', error)

    def test_no_se_puede_pagar_cero(self):
        _, deuda = self._permiso_mes(horas='2')

        pdh, error = self._pagar(deuda, horas='0')

        self.assertIsNone(pdh)
        self.assertIn('mayor que cero', error)

    def test_un_importe_no_numerico_no_revienta(self):
        _, deuda = self._permiso_mes(horas='2')

        pdh, error = self._pagar(deuda, horas='dos')

        self.assertIsNone(pdh)
        self.assertIn('no es un número válido', error)

    def test_un_permiso_largo_ya_no_es_impagable(self):
        """
        El efecto colateral que arregla el troceo: un permanente de 40 h superaba el tope de
        24 h de un solo registro y no había forma de dividirlo, así que no se podía pagar.
        """
        permiso = PermisoEspecial.objects.create(
            empleado=self.explorador, tipo='PERSONAL', es_permanente=True,
            fecha_inicio=self._mes(0).replace(day=1), fecha_fin=self._mes(3),
            dias_semana='0,1,2,3,4', tiempo=Decimal('1'), motivo='x',
            estado='APROBADO', supervisor=self.supervisor)
        sincronizar(permiso)
        self.assertGreater(permiso.horas_totales(), 24, 'el total no cabe en un solo PDH')

        for deuda in permiso.deudas_mes.all():
            pdh, error = PagoHorasService.aplicar_pago(
                supervisor=self.supervisor, explorador=self.explorador,
                fecha=date.today(), keys=[f'permisomes:{deuda.id}'], comentario='x')
            self.assertIsNone(error, f'no se pudo pagar {deuda.anio}-{deuda.mes}: {error}')

        permiso.refresh_from_db()
        self.assertTrue(permiso.pagado)


class RevertirPagoParcialTest(PagoParcialBase):

    def test_revertir_devuelve_el_importe_exacto(self):
        """
        Para esto existe la tabla intermedia: con un M2M plano no se sabría si el PDH pagó
        el mes entero o una parte, y al borrarlo el saldo quedaría mal.
        """
        _, deuda = self._permiso_mes(horas='2')
        pdh, _ = self._pagar(deuda, horas='1.5')

        PagoHorasService.revertir_pago(pdh)

        deuda.refresh_from_db()
        self.assertEqual(deuda.minutos_pagados, 0)
        self.assertEqual(deuda.estado, 'activa')

    def test_revertir_uno_de_dos_pagos_conserva_el_otro(self):
        _, deuda = self._permiso_mes(horas='2')
        primero, _ = self._pagar(deuda, horas='1')
        deuda.refresh_from_db()
        self._pagar(deuda, horas='1')

        PagoHorasService.revertir_pago(primero)

        deuda.refresh_from_db()
        self.assertEqual(deuda.minutos_pagados, 60, 'el segundo pago sigue en pie')
        self.assertEqual(deuda.estado, 'activa')

    def test_borrar_el_pdh_borra_sus_detalles(self):
        _, deuda = self._permiso_mes(horas='2')
        pdh, _ = self._pagar(deuda, horas='1')

        PagoHorasService.revertir_pago(pdh)

        self.assertEqual(PagoDeudaPermisoMes.objects.filter(pdh=pdh).count(), 0)

    def test_una_deuda_consumida_por_sancion_no_resucita(self):
        """
        Borrar un pago no puede devolver a la vida una deuda que una sanción cumplida ya
        extinguió: el explorador volvería a deber —y a poder ser sancionado— por algo que
        ya cumplió.
        """
        _, deuda = self._permiso_mes(horas='2')
        pdh, _ = self._pagar(deuda, horas='1')
        deuda.estado = 'consumida_por_sancion'
        deuda.save(update_fields=['estado'])

        PagoHorasService.revertir_pago(pdh)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'consumida_por_sancion')


class PantallaPorMesTest(PagoParcialBase):
    """Punto 7 del skill: la pantalla debe decir cuánto se debe en CADA mes."""

    def test_las_deudas_se_agrupan_por_mes(self):
        actual, siguiente = self._mes(0), self._mes(1)
        self._permiso_mes(horas='2', anio=actual.year, mes=actual.month)
        self._permiso_mes(horas='3', anio=siguiente.year, mes=siguiente.month)

        meses = PagoHorasService.deudas_pendientes(self.explorador)

        self.assertEqual([m['periodo'] for m in meses],
                         [actual.strftime('%Y-%m'), siguiente.strftime('%Y-%m')])
        self.assertEqual([m['horas_debidas'] for m in meses], [2.0, 3.0])

    def test_cada_mes_dice_debido_pagado_y_pendiente(self):
        _, deuda = self._permiso_mes(horas='2')
        self._pagar(deuda, horas='0.5')

        (agosto,) = PagoHorasService.deudas_pendientes(self.explorador)

        self.assertEqual(agosto['horas_debidas'], 2.0)
        self.assertEqual(agosto['horas_pagadas'], 0.5)
        self.assertEqual(agosto['horas_pendientes'], 1.5)

    def test_los_meses_ya_cerrados_se_marcan_como_vencidos(self):
        """Son los que sancionan: la pantalla tiene que poder destacarlos."""
        hoy = date.today()
        pasado = (hoy.replace(day=1) - timedelta(days=1))
        self._permiso_mes(horas='2', anio=pasado.year, mes=pasado.month)

        (mes,) = PagoHorasService.deudas_pendientes(self.explorador)

        self.assertTrue(mes['vencido'])

    def test_el_mes_abierto_avisa_de_cuando_cierra_el_plazo(self):
        """
        El hueco que esto cierra: la pantalla solo hablaba del plazo cuando YA se había
        perdido. El día 1 el mes anterior sale VENCIDO y bloqueado, pero el día 31 nada
        advertía de que cerraba esa noche — y perderlo no se arregla pagando después: el
        explorador queda sancionado y ya no puede evitarlo.
        """
        actual = self._mes(0)
        self._permiso_mes(horas='2', anio=actual.year, mes=actual.month)
        ultimo_dia = self._mes(1).replace(day=1) - timedelta(days=1)

        # A mitad de mes: hay plazo y no urge.
        (mes,) = PagoHorasService.deudas_pendientes(
            self.explorador, hoy=actual.replace(day=10))
        self.assertFalse(mes['vencido'])
        self.assertEqual(mes['fin_de_plazo'], ultimo_dia.strftime('%d/%m/%Y'))
        self.assertEqual(mes['dias_restantes'], (ultimo_dia - actual.replace(day=10)).days)
        self.assertFalse(mes['urgente'], 'a mitad de mes todavía hay margen')

    def test_el_ultimo_dia_del_plazo_avisa_y_todavia_se_puede_pagar(self):
        """`dias_restantes == 0` es HOY, no «ya pasó»: ese día el pago aún se acepta."""
        actual = self._mes(0)
        self._permiso_mes(horas='2', anio=actual.year, mes=actual.month)
        ultimo_dia = self._mes(1).replace(day=1) - timedelta(days=1)

        (mes,) = PagoHorasService.deudas_pendientes(self.explorador, hoy=ultimo_dia)

        self.assertEqual(mes['dias_restantes'], 0)
        self.assertTrue(mes['urgente'])
        self.assertTrue(mes['pagable'], 'el último día del plazo todavía se paga')
        self.assertFalse(mes['vencido'])

    def test_al_dia_siguiente_ya_esta_vencido_y_no_se_avisa_de_un_plazo_que_no_existe(self):
        actual = self._mes(0)
        self._permiso_mes(horas='2', anio=actual.year, mes=actual.month)
        primer_dia_siguiente = self._mes(1).replace(day=1)

        (mes,) = PagoHorasService.deudas_pendientes(
            self.explorador, hoy=primer_dia_siguiente)

        self.assertTrue(mes['vencido'])
        self.assertFalse(mes['pagable'])
        self.assertFalse(mes['urgente'], 'un mes vencido no es "urgente", es irrecuperable')
        self.assertLess(mes['dias_restantes'], 0)

    def test_caso_10_dos_permisos_del_mismo_mes_se_suman_sin_perder_su_origen(self):
        self._permiso_mes(horas='2')
        self._permiso_mes(horas='1')

        (agosto,) = PagoHorasService.deudas_pendientes(self.explorador)

        self.assertEqual(agosto['horas_debidas'], 3.0)
        self.assertEqual(len(agosto['items']), 2, 'cada obligación conserva su línea')

    def test_el_endpoint_ajax_devuelve_los_meses(self):
        self._permiso_mes(horas='2')

        r = self.client.get(reverse('pdh_deudas_pendientes'),
                            {'explorador_id': str(self.explorador.id)})

        datos = r.json()
        self.assertTrue(datos['success'])
        self.assertEqual(datos['meses'][0]['etiqueta'], self._etiqueta_mes_actual())
        self.assertEqual(datos['total_horas'], 2.0)

    def test_el_post_registra_un_pago_parcial(self):
        _, deuda = self._permiso_mes(horas='2')

        self.client.post(reverse('pdh_create'), {
            'explorador': str(self.explorador.id),
            'fecha': date.today().strftime('%Y-%m-%d'),
            'comentario': 'abono a cuenta',
            'deudas': [f'permisomes:{deuda.id}'],
            f'horas_permisomes:{deuda.id}': '1',
        })

        deuda.refresh_from_db()
        self.assertEqual(deuda.minutos_pagados, 60)
        self.assertEqual(float(PDH.objects.get().horas), 1.0)
