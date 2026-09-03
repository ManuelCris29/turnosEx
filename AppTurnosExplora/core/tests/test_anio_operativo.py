"""
Frontera del AÑO OPERATIVO (`core/utils/anio_operativo.py`).

La app opera sobre el año en curso y solo sobre él: cada 1 de enero arranca en limpio y el
año siguiente se prepara aparte en la apertura de año. Aquí se fija la definición de la
frontera; que cada formulario la aplique se comprueba en sus propias pruebas.
"""
from datetime import date

from django.test import TestCase

from core.utils.anio_operativo import (
    anio_operativo,
    fechas_fuera_del_anio_operativo,
    mensaje_fuera_del_anio_operativo,
)

HOY = date(2026, 12, 15)


class AnioOperativoTest(TestCase):

    def test_el_anio_operativo_es_el_anio_en_curso(self):
        self.assertEqual(anio_operativo(HOY), 2026)

    def test_ultimo_dia_del_anio_es_valido(self):
        self.assertEqual(fechas_fuera_del_anio_operativo([date(2026, 12, 31)], HOY), [])

    def test_primer_dia_del_anio_siguiente_esta_fuera(self):
        self.assertEqual(fechas_fuera_del_anio_operativo([date(2027, 1, 1)], HOY),
                         [date(2027, 1, 1)])

    def test_el_anio_anterior_tambien_esta_fuera(self):
        """La frontera es el año EN CURSO, no «de hoy en adelante»."""
        self.assertEqual(fechas_fuera_del_anio_operativo([date(2025, 12, 31)], HOY),
                         [date(2025, 12, 31)])

    def test_ignora_los_valores_vacios(self):
        """Los campos opcionales (fecha_pago, fecha_compensacion, fecha_fin) llegan a None."""
        self.assertEqual(fechas_fuera_del_anio_operativo([None, date(2026, 5, 1), None], HOY), [])

    def test_devuelve_las_infractoras_ordenadas_y_sin_repetir(self):
        fuera = fechas_fuera_del_anio_operativo(
            [date(2027, 3, 1), date(2026, 5, 1), date(2027, 1, 2), date(2027, 3, 1)], HOY)

        self.assertEqual(fuera, [date(2027, 1, 2), date(2027, 3, 1)])

    def test_sin_infractoras_no_hay_mensaje(self):
        self.assertIsNone(mensaje_fuera_del_anio_operativo([date(2026, 1, 1)], HOY))

    def test_el_mensaje_nombra_las_fechas_infractoras(self):
        """Con rangos largos, decir solo «hay fechas de otro año» obliga a adivinar cuál."""
        msg = mensaje_fuera_del_anio_operativo([date(2026, 12, 30), date(2027, 1, 4)], HOY)

        self.assertIn('2026', msg)
        self.assertIn('04/01/2027', msg)
        self.assertNotIn('30/12/2026', msg)
        self.assertIn('apertura de año', msg)

    def test_el_mensaje_dice_cuando_se_podra_no_una_accion_que_no_sirve(self):
        """
        El cierre decía «el año siguiente se habilita con la apertura de año», y eso manda a
        completar el checklist esperando que desbloquee la fecha. No lo hace: la apertura
        prepara el calendario del año siguiente, pero quien habilita operar sobre él es el 1
        de enero. El supervisor que seguía esa pista completaba los cinco ítems y se
        encontraba el mismo rechazo, sin nada más que intentar.
        """
        msg = mensaje_fuera_del_anio_operativo([date(2027, 1, 4)], HOY)

        self.assertIn('1 de enero', msg)
        self.assertNotIn('se habilita con la apertura', msg)
