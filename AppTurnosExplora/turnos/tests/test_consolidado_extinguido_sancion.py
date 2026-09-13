"""
El consolidado explica también lo que se extinguió cumpliendo una sanción.

Una deuda consumida por sanción no está pendiente (ya no se cobra) ni pagada (no hubo
PDH). Sin una sección propia desaparecía del consolidado sin dejar rastro, y el explorador
—o su supervisor— no tenía dónde ver por qué dejó de deberla. Peor: el histórico acumulado
ENCOGÍA al cumplir el castigo, como si esas horas nunca hubieran existido.
"""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from empleados.models import Empleado, SancionEmpleado
from permisos.models import PermisoEspecial
from permisos.services.deuda_permiso_service import sincronizar
from solicitudes.models import DeudaCorporativa
from turnos.services.consolidado_horas_service import ConsolidadoHorasService


class ConsolidadoSaldadoPorSancionTest(TestCase):

    def setUp(self):
        jefe = User.objects.create_user('cons.jefe', password='x', is_staff=True)
        self.supervisor = Empleado.objects.create(
            user=jefe, nombre='Jefa', apellido='Turno', cedula='6001', activo=True)
        emp = User.objects.create_user('cons.emp', password='x')
        self.explorador = Empleado.objects.create(
            user=emp, nombre='Explo', apellido='Rador', cedula='6002', activo=True,
            supervisor=self.supervisor)

    def _sancion(self, anio=2026, mes=6):
        return SancionEmpleado.objects.create(
            explorador=self.explorador, supervisor=self.supervisor,
            fecha_inicio=date(anio, mes + 1, 1), fecha_fin=date(anio, mes + 1, 15),
            motivo='[AUTO-DEUDA] Sanción automática', periodo_anio=anio, periodo_mes=mes)

    def _doblada_consumida(self, sancion, minutos=30):
        return DeudaCorporativa.objects.create(
            explorador=self.explorador, minutos=minutos, fecha_doblada=date(2026, 6, 10),
            estado='consumida_por_sancion', sancion_consumidora=sancion,
            fecha_consumo=date(2026, 7, 16))

    def _permiso_consumido(self, sancion, horas='2'):
        permiso = PermisoEspecial.objects.create(
            empleado=self.explorador, tipo='PERSONAL',
            fecha_inicio=date(2026, 6, 10), fecha_fin=date(2026, 6, 10),
            tiempo=Decimal(horas), motivo='x', estado='APROBADO', supervisor=self.supervisor)
        sincronizar(permiso)
        deuda = permiso.deudas_mes.get()
        deuda.estado = 'consumida_por_sancion'
        deuda.sancion_consumidora = sancion
        deuda.fecha_consumo = date(2026, 7, 16)
        deuda.save()
        return deuda

    def test_sin_sanciones_la_seccion_va_vacia(self):
        datos = ConsolidadoHorasService.get_consolidado(self.explorador)

        self.assertEqual(datos['extinguidas_sancion'], [])
        self.assertEqual(datos['total_extinguido_sancion'], 0)

    def test_la_deuda_consumida_aparece_con_su_sancion(self):
        sancion = self._sancion()
        self._doblada_consumida(sancion)

        (fila,) = ConsolidadoHorasService.get_consolidado(self.explorador)['extinguidas_sancion']

        self.assertEqual(fila['periodo_str'], 'Junio 2026')
        self.assertEqual(fila['horas'], 0.5)
        self.assertEqual(len(fila['detalle_deudas']), 1)

    def test_suma_dobladas_y_permisos_de_la_misma_sancion(self):
        sancion = self._sancion()
        self._doblada_consumida(sancion)
        self._permiso_consumido(sancion, horas='2')

        datos = ConsolidadoHorasService.get_consolidado(self.explorador)

        (fila,) = datos['extinguidas_sancion']
        self.assertEqual(fila['horas'], 2.5)
        self.assertEqual(len(fila['detalle_deudas']), 2)
        self.assertEqual(datos['total_extinguido_sancion'], 2.5)

    def test_no_cuenta_como_pendiente_ni_como_pagado(self):
        sancion = self._sancion()
        self._doblada_consumida(sancion)

        datos = ConsolidadoHorasService.get_consolidado(self.explorador)

        self.assertEqual(datos['total_horas'], 0, 'ya no se le puede cobrar')
        self.assertEqual(datos['total_pagado'], 0, 'no hubo PDH: no fue un pago')

    def test_el_historico_acumulado_conserva_esas_horas(self):
        sancion = self._sancion()
        self._doblada_consumida(sancion)

        datos = ConsolidadoHorasService.get_consolidado(self.explorador)

        self.assertEqual(datos['total_acumulado'], 0.5,
                         'el histórico no puede encoger porque se cumplió el castigo')

    def test_una_sancion_sin_deudas_consumidas_no_ensucia_la_lista(self):
        """Las manuales del supervisor no extinguen nada y no tienen nada que explicar."""
        SancionEmpleado.objects.create(
            explorador=self.explorador, supervisor=self.supervisor,
            fecha_inicio=date(2026, 5, 1), fecha_fin=date(2026, 5, 10), motivo='llegada tarde')

        datos = ConsolidadoHorasService.get_consolidado(self.explorador)

        self.assertEqual(datos['extinguidas_sancion'], [])

class LineasNoCobrablesTest(TestCase):
    """
    Entre el vencimiento y el fin de la sanción hay una ventana en la que el explorador debe
    horas que YA NADIE puede cobrarle. Sin marcarlas, el consolidado enseña una deuda con
    pinta de normal y el bloqueo no se explica desde esta pantalla.
    """

    def setUp(self):
        jefe = User.objects.create_user('nocob.jefe', password='x', is_staff=True)
        self.supervisor = Empleado.objects.create(
            user=jefe, nombre='Jefa', apellido='Turno', cedula='6101', activo=True)
        emp = User.objects.create_user('nocob.emp', password='x')
        self.explorador = Empleado.objects.create(
            user=emp, nombre='Explo', apellido='Rador', cedula='6102', activo=True,
            supervisor=self.supervisor)
        self.hoy = date(2026, 8, 27)

    def _doblada(self, fecha):
        return DeudaCorporativa.objects.create(
            explorador=self.explorador, minutos=30, fecha_doblada=fecha, estado='activa')

    def _consolidado(self):
        return ConsolidadoHorasService.get_consolidado(self.explorador, hoy=self.hoy)

    def test_la_deuda_del_mes_en_curso_no_se_marca(self):
        self._doblada(date(2026, 8, 10))

        (fila,) = self._consolidado()['otras']

        self.assertFalse(fila['vencida'])

    def test_la_deuda_de_un_mes_cerrado_se_marca(self):
        self._doblada(date(2026, 7, 10))

        (fila,) = self._consolidado()['otras']

        self.assertTrue(fila['vencida'])

    def test_marcarla_no_la_saca_del_saldo(self):
        """Sigue debiéndola: lo que cambia es que ya no se puede cobrar."""
        self._doblada(date(2026, 7, 10))

        datos = self._consolidado()

        self.assertEqual(datos['total_horas'], 0.5)

    def test_el_permiso_de_un_mes_cerrado_tambien_se_marca(self):
        permiso = PermisoEspecial.objects.create(
            empleado=self.explorador, tipo='PERSONAL',
            fecha_inicio=date(2026, 7, 10), fecha_fin=date(2026, 7, 10),
            tiempo=Decimal('2'), motivo='x', estado='APROBADO', supervisor=self.supervisor)
        sincronizar(permiso)

        (fila,) = self._consolidado()['permisos']

        self.assertTrue(fila['vencida'])

    def test_el_historico_es_la_suma_de_los_tres_estados(self):
        """La cifra que enseña la cabecera: pendiente + pagado + saldado por sanción."""
        self._doblada(date(2026, 8, 10))

        datos = self._consolidado()

        self.assertEqual(
            datos['total_acumulado'],
            round(datos['total_horas'] + datos['total_pagado']
                  + datos['total_extinguido_sancion'], 2))


class FechaDeLosPermisosTest(TestCase):
    """
    La columna «Fecha» tiene que hablar el mismo idioma en todas las secciones.

    Decía «6 de noviembre de 2026» en las dobladas y «Junio 2026» en los permisos, porque
    la deuda de permiso se guarda por mes. Dos vocabularios en la misma columna hacen dudar
    de si falta el día o es que no lo hay.
    """

    def setUp(self):
        jefe = User.objects.create_user('fecha.jefe', password='x', is_staff=True)
        self.supervisor = Empleado.objects.create(
            user=jefe, nombre='Jefa', apellido='Turno', cedula='6201', activo=True)
        emp = User.objects.create_user('fecha.emp', password='x')
        self.explorador = Empleado.objects.create(
            user=emp, nombre='Explo', apellido='Rador', cedula='6202', activo=True,
            supervisor=self.supervisor)

    def _permiso(self, inicio, fin=None, permanente=False, dias=None):
        permiso = PermisoEspecial.objects.create(
            empleado=self.explorador, tipo='PERSONAL', fecha_inicio=inicio,
            fecha_fin=fin or inicio, tiempo=Decimal('1'), motivo='x',
            estado='APROBADO', supervisor=self.supervisor,
            es_permanente=permanente, dias_semana=dias or '')
        sincronizar(permiso)
        return permiso

    def _filas(self):
        return ConsolidadoHorasService.get_consolidado(
            self.explorador, hoy=date(2026, 8, 27))['permisos']

    def test_el_permiso_de_un_dia_muestra_ese_dia(self):
        self._permiso(date(2026, 6, 26))

        (fila,) = self._filas()

        self.assertEqual(fila['fecha_str'], '26 de junio de 2026')

    def test_el_permiso_de_varios_dias_muestra_el_rango(self):
        self._permiso(date(2026, 6, 10), date(2026, 6, 12))

        (fila,) = self._filas()

        self.assertEqual(fila['fecha_str'], '10 al 12 de junio de 2026')

    def test_un_puntual_a_caballo_entre_dos_meses_no_esconde_dias(self):
        """
        Un puntual genera UNA obligación, en el mes de su inicio, aunque el rango cruce de
        mes. Recortarla contra junio ocultaría los dos días de julio que también se deben.
        """
        self._permiso(date(2026, 6, 28), date(2026, 7, 2))

        (fila,) = self._filas()

        self.assertEqual(fila['fecha_str'], '28 de junio de 2026 al 2 de julio de 2026')

    def test_el_permanente_sigue_siendo_mensual(self):
        """No ocupa un tramo continuo: son días sueltos, y el mes es lo exacto."""
        self._permiso(date(2026, 6, 1), date(2026, 6, 30), permanente=True, dias='0,2')

        (fila,) = self._filas()

        self.assertEqual(fila['fecha_str'], 'Junio 2026')
        self.assertTrue(fila['es_permanente'])
        self.assertGreater(fila['ocurrencias'], 0, 'el día concreto se cuenta aparte')
