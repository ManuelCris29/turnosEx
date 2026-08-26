"""
La deuda de un permiso, repartida por mes.

Un permiso permanente de varios meses no es una deuda global: es una obligación por cada
mes, porque cada una vence al cerrar SU mes y se reclama por separado. Estos tests fijan
el reparto y su invariante con el total, que es lo que impide que la pantalla anuncie una
cifra y se cobre otra.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from empleados.models import Empleado
from permisos.deuda_permiso_service import (
    desglose_mensual,
    recalcular_roll_up,
    sincronizar,
)
from permisos.models import DeudaPermisoMes, PermisoEspecial


class DeudaPermisoMesTestBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-dpm', password='x'),
            nombre='Supervisora', apellido='D', cedula='sup-dpm', activo=True)
        cls.exp = Empleado.objects.create(
            user=User.objects.create_user(username='exp-dpm', password='x'),
            nombre='Explorador', apellido='D', cedula='exp-dpm', activo=True,
            supervisor=cls.sup)

    def _permanente(self, inicio, fin, dias='1', tiempo='0.5', estado='APROBADO', empleado=None):
        """Permiso permanente; por defecto los martes (weekday 1), media hora."""
        return PermisoEspecial.objects.create(
            empleado=empleado or self.exp, tipo='PERSONAL', es_permanente=True,
            fecha_inicio=inicio, fecha_fin=fin, dias_semana=dias,
            tiempo=Decimal(tiempo), motivo='Prueba', estado=estado, supervisor=self.sup)

    def _meses(self, permiso):
        return {(d.anio, d.mes): d for d in permiso.deudas_mes.all()}


class DesgloseMensualTest(DeudaPermisoMesTestBase):
    """Aritmética del reparto, sin tocar todavía la base de datos de deudas."""

    def test_caso_1_un_permiso_de_agosto_a_noviembre_da_cuatro_meses(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 11, 30))

        desglose = desglose_mensual(permiso)

        self.assertEqual([(d['anio'], d['mes']) for d in desglose],
                         [(2026, 8), (2026, 9), (2026, 10), (2026, 11)])

    def test_cada_mes_cuenta_sus_propios_martes(self):
        """
        Agosto de 2026 tiene 4 martes y septiembre 5. La deuda de cada mes debe reflejar
        SUS días, no un promedio: es lo que se le va a reclamar.
        """
        permiso = self._permanente(date(2026, 8, 1), date(2026, 9, 30))
        por_mes = {(d['anio'], d['mes']): d for d in desglose_mensual(permiso)}

        self.assertEqual(por_mes[(2026, 8)]['ocurrencias'], 4)
        self.assertEqual(por_mes[(2026, 8)]['minutos'], 120)
        self.assertEqual(por_mes[(2026, 9)]['ocurrencias'], 5)
        self.assertEqual(por_mes[(2026, 9)]['minutos'], 150)

    def test_el_reparto_suma_exactamente_el_total_del_permiso(self):
        """
        Invariante clave: si el desglose y `horas_totales()` divergieran, el consolidado
        mostraría una deuda distinta de la que se cobra en PDH.
        """
        permiso = self._permanente(date(2026, 8, 1), date(2026, 11, 30))

        total_desglose = sum(d['minutos'] for d in desglose_mensual(permiso))

        self.assertEqual(total_desglose, round(permiso.horas_totales() * 60))

    def test_caso_9_un_permiso_que_cruza_el_ano(self):
        permiso = self._permanente(date(2026, 11, 15), date(2027, 2, 10))
        desglose = desglose_mensual(permiso)

        self.assertEqual([(d['anio'], d['mes']) for d in desglose],
                         [(2026, 11), (2026, 12), (2027, 1), (2027, 2)])
        self.assertEqual(sum(d['minutos'] for d in desglose),
                         round(permiso.horas_totales() * 60))

    def test_caso_9_los_meses_de_los_extremos_solo_cuentan_dentro_del_rango(self):
        """Empezar a mitad de mes no debe cobrar los martes anteriores al permiso."""
        permiso = self._permanente(date(2026, 8, 20), date(2026, 9, 8))
        por_mes = {(d['anio'], d['mes']): d for d in desglose_mensual(permiso)}

        self.assertEqual(por_mes[(2026, 8)]['ocurrencias'], 1)   # solo el 25; el 18 queda fuera
        self.assertEqual(por_mes[(2026, 9)]['ocurrencias'], 2)   # 01/09 y 08/09, el límite incluido

    def test_varios_dias_de_la_semana_se_acumulan_en_el_mes(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 8, 31), dias='1,3')
        (agosto,) = desglose_mensual(permiso)

        self.assertEqual(agosto['ocurrencias'], 8)   # 4 martes + 4 jueves
        self.assertEqual(agosto['minutos'], 240)

    def test_un_permiso_puntual_es_un_solo_mes(self):
        puntual = PermisoEspecial.objects.create(
            empleado=self.exp, tipo='PERSONAL', es_permanente=False,
            fecha_inicio=date(2026, 8, 12), fecha_fin=date(2026, 8, 12),
            tiempo=Decimal('2'), motivo='Cita', estado='APROBADO', supervisor=self.sup)

        self.assertEqual(desglose_mensual(puntual),
                         [{'anio': 2026, 'mes': 8, 'ocurrencias': 1, 'minutos': 120}])

    def test_un_permanente_sin_dias_no_debe_nada(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 11, 30), dias='')

        self.assertEqual(desglose_mensual(permiso), [])
        self.assertEqual(permiso.horas_totales(), 0)


class SincronizarTest(DeudaPermisoMesTestBase):
    """Materialización de las obligaciones y su mantenimiento."""

    def test_aprobar_crea_una_deuda_por_mes(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 11, 30))

        resumen = sincronizar(permiso)

        self.assertEqual(resumen['creadas'], 4)
        self.assertEqual(permiso.deudas_mes.count(), 4)
        self.assertEqual(self._meses(permiso)[(2026, 9)].minutos_generados, 150)

    def test_el_explorador_queda_en_la_propia_deuda(self):
        """Desnormalizado a propósito: las consultas son 'qué debe esta persona'."""
        permiso = self._permanente(date(2026, 8, 1), date(2026, 8, 31))
        sincronizar(permiso)

        self.assertEqual(permiso.deudas_mes.get().explorador, self.exp)

    def test_repetir_la_sincronizacion_no_duplica(self):
        """Se llama desde varios sitios (aprobar, red de seguridad); debe ser idempotente."""
        permiso = self._permanente(date(2026, 8, 1), date(2026, 11, 30))
        sincronizar(permiso)

        resumen = sincronizar(permiso)

        self.assertEqual(resumen, {'creadas': 0, 'actualizadas': 0,
                                   'canceladas': 0, 'borradas': 0})
        self.assertEqual(permiso.deudas_mes.count(), 4)

    def test_un_permiso_pendiente_no_debe_nada_todavia(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 11, 30), estado='PENDIENTE')

        sincronizar(permiso)

        self.assertEqual(permiso.deudas_mes.count(), 0)

    def test_rechazar_retira_las_obligaciones_limpias(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 11, 30))
        sincronizar(permiso)

        permiso.estado = 'RECHAZADO'
        resumen = sincronizar(permiso)

        self.assertEqual(resumen['borradas'], 4)
        self.assertEqual(permiso.deudas_mes.count(), 0)

    def test_cancelar_conserva_lo_que_ya_tenia_pagos(self):
        """Un mes con dinero encima es historia: se cancela, no se borra."""
        permiso = self._permanente(date(2026, 8, 1), date(2026, 9, 30))
        sincronizar(permiso)
        agosto = self._meses(permiso)[(2026, 8)]
        agosto.minutos_pagados = 60
        agosto.save(update_fields=['minutos_pagados'])

        permiso.estado = 'CANCELADO'
        sincronizar(permiso)

        agosto.refresh_from_db()
        self.assertEqual(agosto.estado, 'cancelada')
        self.assertEqual(permiso.deudas_mes.count(), 1, 'el mes limpio sí se borra')

    def test_acortar_el_rango_retira_los_meses_sobrantes(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 11, 30))
        sincronizar(permiso)

        permiso.fecha_fin = date(2026, 9, 30)
        permiso.save(update_fields=['fecha_fin'])
        sincronizar(permiso)

        self.assertEqual(sorted(self._meses(permiso)), [(2026, 8), (2026, 9)])

    def test_un_mes_ya_pagado_no_se_recalcula_al_editar_el_permiso(self):
        """
        Cambiar el permiso no puede reescribir un mes que alguien ya pagó: el importe
        cobrado dejaría de cuadrar con la deuda registrada.
        """
        permiso = self._permanente(date(2026, 8, 1), date(2026, 8, 31))
        sincronizar(permiso)
        agosto = permiso.deudas_mes.get()
        agosto.minutos_pagados = 120
        agosto.estado = 'pagada'
        agosto.save(update_fields=['minutos_pagados', 'estado'])

        permiso.tiempo = Decimal('3')
        permiso.save(update_fields=['tiempo'])
        sincronizar(permiso)

        agosto.refresh_from_db()
        self.assertEqual(agosto.minutos_generados, 120)
        self.assertEqual(agosto.estado, 'pagada')

    def test_caso_10_dos_permisos_en_el_mismo_mes_no_se_fusionan(self):
        """
        La deuda del mes se suma para reclamarla, pero cada obligación conserva de qué
        permiso viene: sin eso no se podría explicar al explorador qué está pagando.
        """
        uno = self._permanente(date(2026, 8, 1), date(2026, 8, 31), dias='1')
        otro = self._permanente(date(2026, 8, 1), date(2026, 8, 31), dias='3', tiempo='1')
        sincronizar(uno)
        sincronizar(otro)

        deudas = DeudaPermisoMes.objects.filter(explorador=self.exp, anio=2026, mes=8)

        self.assertEqual(deudas.count(), 2)
        self.assertEqual({d.permiso_id for d in deudas}, {uno.id, otro.id})
        self.assertEqual(sum(d.minutos_generados for d in deudas), 120 + 240)


class MinutosPendientesTest(DeudaPermisoMesTestBase):

    def test_lo_pendiente_es_lo_generado_menos_lo_pagado(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 8, 31))
        sincronizar(permiso)
        agosto = permiso.deudas_mes.get()

        agosto.minutos_pagados = 45

        self.assertEqual(agosto.minutos_pendientes, 75)
        self.assertEqual(agosto.horas_pendientes, 1.25)

    def test_pagar_de_mas_no_genera_credito(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 8, 31))
        sincronizar(permiso)
        agosto = permiso.deudas_mes.get()

        agosto.minutos_pagados = 999

        self.assertEqual(agosto.minutos_pendientes, 0)


class RollUpTest(DeudaPermisoMesTestBase):
    """`PermisoEspecial.pagado` deja de ser la verdad y pasa a derivarse de los meses."""

    def test_mientras_quede_un_mes_con_saldo_el_permiso_no_esta_pagado(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 9, 30))
        sincronizar(permiso)
        agosto = self._meses(permiso)[(2026, 8)]
        agosto.minutos_pagados = agosto.minutos_generados
        agosto.estado = 'pagada'
        agosto.fecha_pago = date(2026, 9, 3)
        agosto.save()

        recalcular_roll_up(permiso)

        permiso.refresh_from_db()
        self.assertFalse(permiso.pagado)

    def test_con_todos_los_meses_saldados_el_permiso_queda_pagado(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 9, 30))
        sincronizar(permiso)
        for deuda in permiso.deudas_mes.all():
            deuda.minutos_pagados = deuda.minutos_generados
            deuda.estado = 'pagada'
            deuda.fecha_pago = date(2026, 10, 2)
            deuda.save()

        recalcular_roll_up(permiso)

        permiso.refresh_from_db()
        self.assertTrue(permiso.pagado)
        self.assertEqual(permiso.fecha_pago, date(2026, 10, 2))

    def test_un_mes_consumido_por_sancion_no_impide_dar_el_permiso_por_saldado(self):
        """La sanción cumplida extingue la deuda: ya no se debe, aunque no se pagara."""
        permiso = self._permanente(date(2026, 8, 1), date(2026, 8, 31))
        sincronizar(permiso)
        agosto = permiso.deudas_mes.get()
        agosto.estado = 'consumida_por_sancion'
        agosto.save(update_fields=['estado'])

        recalcular_roll_up(permiso)

        permiso.refresh_from_db()
        self.assertTrue(permiso.pagado)


class OcurrenciasHastaCorteTest(DeudaPermisoMesTestBase):
    """
    Corte por día: cuánto lleva devengado un permiso a mitad de mes.

    Lo necesita la consulta "a 25 de agosto, ¿quién debe?": el permiso se guarda agregado por
    mes, así que sin este corte se mostraría el mes entero y la cifra saldría inflada con
    ocurrencias que aún no han pasado.
    """

    def test_corta_en_el_dia_pedido(self):
        """Los martes de agosto de 2026 son 4, 11, 18 y 25: al día 20 solo han pasado tres."""
        permiso = self._permanente(date(2026, 8, 1), date(2026, 8, 31))

        self.assertEqual(permiso.ocurrencias_por_mes(hasta=date(2026, 8, 20)),
                         [(2026, 8, 3)])
        self.assertEqual(permiso.ocurrencias_por_mes(hasta=date(2026, 8, 25)),
                         [(2026, 8, 4)])

    def test_un_corte_anterior_al_inicio_no_devenga_nada(self):
        permiso = self._permanente(date(2026, 8, 1), date(2026, 8, 31))

        self.assertEqual(permiso.ocurrencias_por_mes(hasta=date(2026, 7, 31)), [])

    def test_sin_hasta_el_resultado_no_cambia(self):
        """El uso normal (`horas_totales`, `desglose_mensual`) no puede verse afectado."""
        permiso = self._permanente(date(2026, 8, 1), date(2026, 11, 30))

        self.assertEqual(permiso.ocurrencias_por_mes(),
                         permiso.ocurrencias_por_mes(hasta=date(2026, 11, 30)))

    def test_un_permiso_puntual_posterior_al_corte_no_cuenta(self):
        permiso = PermisoEspecial.objects.create(
            empleado=self.exp, tipo='PERSONAL', es_permanente=False,
            fecha_inicio=date(2026, 8, 27), fecha_fin=date(2026, 8, 27),
            tiempo=Decimal('1.0'), motivo='Prueba', estado='APROBADO', supervisor=self.sup)

        self.assertEqual(permiso.ocurrencias_por_mes(hasta=date(2026, 8, 25)), [])
        self.assertEqual(permiso.ocurrencias_por_mes(hasta=date(2026, 8, 27)),
                         [(2026, 8, 1)])

