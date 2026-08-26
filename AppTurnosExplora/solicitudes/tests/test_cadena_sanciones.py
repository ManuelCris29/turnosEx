"""
CAPA 1 — La cadena de sanciones por periodo mensual.

Aritmética pura, con fechas fijas y sin base de datos: qué duración corresponde a cada
mes incumplido, y cuándo empieza y acaba cada sanción. El servicio que graba estos
registros se prueba aparte; aquí se fija la REGLA, que es lo que no debe moverse sin que
alguien se entere.
"""
from datetime import date

from django.test import SimpleTestCase

from solicitudes.services.sancion_deuda_calculo import (
    DURACION_BASE_DIAS,
    Periodo,
    cadena_sanciones,
    fin_de_plazo,
    sancion_de,
)


class PeriodoTest(SimpleTestCase):

    def test_fin_de_plazo_es_el_ultimo_dia_del_mes(self):
        self.assertEqual(Periodo(2026, 8).fin_de_plazo(), date(2026, 8, 31))
        self.assertEqual(Periodo(2026, 9).fin_de_plazo(), date(2026, 9, 30))

    def test_diciembre_no_se_desborda_al_ano_siguiente(self):
        """El caso que rompe la fórmula ingenua `mes + 1`."""
        self.assertEqual(Periodo(2026, 12).fin_de_plazo(), date(2026, 12, 31))
        self.assertEqual(Periodo(2026, 12).primer_dia_vencida(), date(2027, 1, 1))

    def test_febrero_bisiesto(self):
        self.assertEqual(Periodo(2028, 2).fin_de_plazo(), date(2028, 2, 29))
        self.assertEqual(Periodo(2027, 2).fin_de_plazo(), date(2027, 2, 28))

    def test_vence_el_dia_siguiente_al_fin_de_plazo(self):
        self.assertEqual(Periodo(2026, 8).primer_dia_vencida(), date(2026, 9, 1))

    def test_los_periodos_se_ordenan_cronologicamente(self):
        """De esto depende que el nivel sea la posición en la cadena."""
        self.assertLess(Periodo(2026, 12), Periodo(2027, 1))
        self.assertLess(Periodo(2026, 8), Periodo(2026, 9))

    def test_el_envoltorio_por_fecha_coincide_con_el_periodo(self):
        self.assertEqual(fin_de_plazo(date(2026, 8, 14)), Periodo(2026, 8).fin_de_plazo())


class CadenaSancionesTest(SimpleTestCase):

    def test_un_solo_mes_incumplido_son_15_dias(self):
        (s,) = cadena_sanciones([Periodo(2026, 8)])

        self.assertEqual(s.nivel, 1)
        self.assertEqual(s.duracion_dias, DURACION_BASE_DIAS)
        self.assertEqual(s.inicio, date(2026, 9, 1))
        self.assertEqual(s.fin, date(2026, 9, 16))
        self.assertEqual(s.reincidencia, 0)

    def test_la_escalada_va_de_15_en_15(self):
        cadena = cadena_sanciones([Periodo(2026, 8), Periodo(2026, 9), Periodo(2026, 10)])

        self.assertEqual([s.duracion_dias for s in cadena], [15, 30, 45])
        self.assertEqual([s.reincidencia for s in cadena], [0, 1, 2])

    def test_una_cuarta_reincidencia_son_60_dias(self):
        cadena = cadena_sanciones([Periodo(2026, m) for m in (7, 8, 9, 10)])

        self.assertEqual(cadena[-1].duracion_dias, 60)

    def test_las_sanciones_no_se_solapan(self):
        """
        Una sanción de 45 días dura más que un mes: sin encadenar, la de septiembre
        empezaría antes de acabar la de agosto y un mismo día pertenecería a dos.
        """
        cadena = cadena_sanciones([Periodo(2026, m) for m in (8, 9, 10, 11)])

        for anterior, siguiente in zip(cadena, cadena[1:]):
            self.assertGreater(siguiente.inicio, anterior.fin,
                               f'{siguiente.periodo} empieza antes de acabar {anterior.periodo}')

    def test_encadenar_no_adelanta_nunca_una_sancion(self):
        """El encadenado solo puede RETRASAR: nadie se sanciona antes de que venza su mes."""
        cadena = cadena_sanciones([Periodo(2026, m) for m in (8, 9, 10)])

        for s in cadena:
            self.assertGreaterEqual(s.inicio, s.periodo.primer_dia_vencida())

    def test_meses_lejanos_no_se_encadenan(self):
        """Si el hueco es grande, cada sanción empieza cuando vence su propio mes."""
        cadena = cadena_sanciones([Periodo(2026, 1), Periodo(2026, 11)])

        self.assertEqual(cadena[0].inicio, date(2026, 2, 1))
        self.assertEqual(cadena[1].inicio, date(2026, 12, 1))

    def test_dos_meses_muy_separados_no_encadenan_la_reincidencia(self):
        """
        El antecedente PRESCRIBE. Entre marzo de 2024 y noviembre de 2026 pasaron años: la
        ventana se agotó hace mucho, así que la segunda vuelve a ser una primera sanción.

        Sin esta caducidad, un descuido aislado de hace dos años seguiría encareciendo la
        sanción de hoy, y el castigo por un tropiezo puntual acabaría siendo de meses.
        """
        cadena = cadena_sanciones([Periodo(2024, 3), Periodo(2026, 11)], ventana_dias=30)

        self.assertEqual([s.duracion_dias for s in cadena], [15, 15])
        self.assertEqual([s.nivel for s in cadena], [1, 1])

    def test_la_cadena_cruza_el_cambio_de_ano(self):
        cadena = cadena_sanciones([Periodo(2026, 12), Periodo(2027, 1)])

        self.assertEqual(cadena[0].inicio, date(2027, 1, 1))
        self.assertEqual(cadena[1].periodo, Periodo(2027, 1))
        self.assertGreater(cadena[1].inicio, cadena[0].fin)

    def test_no_hace_falta_pasarlos_ordenados(self):
        """Las dos fuentes de deuda aportan periodos por separado; ordenar es cosa nuestra."""
        desordenados = cadena_sanciones([Periodo(2026, 10), Periodo(2026, 8), Periodo(2026, 9)])

        self.assertEqual([s.periodo.mes for s in desordenados], [8, 9, 10])
        self.assertEqual([s.duracion_dias for s in desordenados], [15, 30, 45])

    def test_un_mes_repetido_cuenta_una_sola_vez(self):
        """
        Deber una doblada Y un permiso del mismo mes es UN incumplimiento, no dos: si
        contara doble, tener dos deudas el mismo mes duplicaría la sanción.
        """
        cadena = cadena_sanciones([Periodo(2026, 8), Periodo(2026, 8)])

        self.assertEqual(len(cadena), 1)
        self.assertEqual(cadena[0].duracion_dias, 15)

    def test_sin_incumplimientos_no_hay_sanciones(self):
        self.assertEqual(cadena_sanciones([]), [])

    def test_duracion_siguiente_anuncia_lo_que_viene(self):
        (s,) = cadena_sanciones([Periodo(2026, 8)])

        self.assertEqual(s.duracion_siguiente, 30)

    def test_sancion_de_busca_un_mes_concreto(self):
        periodos = [Periodo(2026, 8), Periodo(2026, 9)]

        self.assertEqual(sancion_de(periodos, Periodo(2026, 9)).duracion_dias, 30)
        self.assertIsNone(sancion_de(periodos, Periodo(2026, 10)))
