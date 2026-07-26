"""Tests de DiaEspecialService: los festivos se calculan (preview) sin persistir."""
from django.test import TestCase

from turnos.models import DiaEspecial
from turnos.services.dia_especial_service import DiaEspecialService


class CalcularFestivosAutomaticosTest(TestCase):
    def test_no_persiste_en_bd(self):
        """Calcular festivos NO debe crear registros (igual que mantenimiento)."""
        antes = DiaEspecial.objects.count()
        resultado = DiaEspecialService.calcular_festivos_automaticos(2035)
        despues = DiaEspecial.objects.count()

        self.assertEqual(antes, despues, "No debe crear filas en BD al previsualizar")
        self.assertGreater(len(resultado), 0, "Debe devolver festivos agrupados por mes")
        # Año Nuevo (1 de enero) siempre es festivo.
        self.assertIn(1, resultado)
        self.assertIn(1, resultado[1])

    def test_anio_invalido_lanza_error(self):
        with self.assertRaises(ValueError):
            DiaEspecialService.calcular_festivos_automaticos(1999)
