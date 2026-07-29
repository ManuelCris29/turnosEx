"""
Red de seguridad del PASO DE CORTE: congelar la alternancia no puede cambiar ningún día.

`materializar_alternancia` escribe en la base lo que la fórmula (ancla de findes + rotación
GLOBAL de festivos) devuelve hoy. Este test comprueba, fecha por fecha, que lo congelado
coincide exactamente con lo que la fórmula decía.

DEBE ESTAR EN VERDE ANTES DE ELIMINAR CUALQUIER FALLBACK. Si no, se está cambiando el
calendario de días ya vividos sin ninguna señal: no hay excepción ni log, simplemente
exploradores que ven otro turno.

El error concreto que atrapa: materializar los festivos con la siembra por año (que reinicia
en enero) en vez de con el índice global. Eso invierte TODOS los festivos del año.
"""
from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from turnos.models import AsignacionEspecialManual, DiaEspecial, Jornada
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
from turnos.services.asignacion_especial_service import AsignacionEspecialService
from turnos.services.festivos_rotacion_service import FestivosRotacionService


class EquivalenciaAlternanciaTest(TestCase):
    """El año de prueba lleva festivos en DOS años para que el índice global no sea trivial."""

    ANIO = 2031

    def setUp(self):
        Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        # Festivos del año ANTERIOR: desplazan el índice global. Si el congelado reiniciara
        # la rotación por año, estos harían que el resultado NO coincida y el test fallaría.
        self.festivos_previos = self._festivos_lunes(self.ANIO - 1, 3)
        self.festivos = self._festivos_lunes(self.ANIO, 5)

    def _festivos_lunes(self, anio, cuantos):
        """Lunes repartidos por el año, creados como festivo activo."""
        d = date(anio, 1, 1)
        while d.weekday() != 0:
            d += timedelta(days=1)
        creados = []
        for i in range(cuantos):
            f = d + timedelta(weeks=i * 7)
            if f.year != anio:
                break
            DiaEspecial.objects.create(fecha=f, tipo='festivo', activo=True)
            creados.append(f)
        return creados

    def _fechas_especiales(self):
        festivos = set(self.festivos)
        d, fin = date(self.ANIO, 1, 1), date(self.ANIO, 12, 31)
        while d <= fin:
            if d.weekday() >= 5 or d in festivos:
                yield d
            d += timedelta(days=1)

    def _formula(self, fecha):
        if fecha.weekday() >= 5:
            return AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(fecha)
        return FestivosRotacionService.get_grupo_que_dobla_en_festivo(fecha)

    def _materializar(self, **kwargs):
        out = StringIO()
        call_command('materializar_alternancia', anio=self.ANIO, stdout=out, **kwargs)
        return out.getvalue()

    def test_dry_run_no_escribe_nada(self):
        salida = self._materializar(dry_run=True)
        self.assertIn('DRY-RUN', salida)
        self.assertEqual(AsignacionEspecialManual.objects.count(), 0)

    def test_congelar_cubre_todos_los_findes_y_festivos(self):
        self._materializar()
        esperadas = set(self._fechas_especiales())
        guardadas = set(AsignacionEspecialManual.objects.filter(
            fecha__year=self.ANIO).values_list('fecha', flat=True))
        self.assertEqual(guardadas, esperadas)

    def test_lo_congelado_coincide_exactamente_con_la_formula(self):
        """El corazón del corte: ni un solo día puede cambiar de grupo."""
        antes = {f: self._formula(f) for f in self._fechas_especiales()}
        self._materializar()
        discrepancias = {
            f: (esperado, AsignacionEspecialService.grupo_trabaja(f))
            for f, esperado in antes.items()
            if AsignacionEspecialService.grupo_trabaja(f) != esperado
        }
        self.assertEqual(discrepancias, {}, f'{len(discrepancias)} día(s) cambiaron al congelar')

    def test_los_festivos_usan_el_indice_global_no_el_reinicio_anual(self):
        """
        Con 3 festivos en el año anterior, el primer festivo del año arranca en índice 3
        (impar → AM). Una siembra que reiniciara en enero daría PM: exactamente el fallo
        silencioso que este test existe para atrapar.
        """
        self.assertEqual(len(self.festivos_previos), 3)
        self._materializar()
        primer_festivo = min(self.festivos)
        self.assertEqual(
            AsignacionEspecialService.grupo_trabaja(primer_festivo),
            FestivosRotacionService.get_grupo_que_dobla_en_festivo(primer_festivo))

    def test_no_pisa_un_override_manual_existente(self):
        """Si el supervisor ya fijó un día a mano, el congelado lo respeta."""
        sabado = next(f for f in self._fechas_especiales() if f.weekday() == 5)
        contrario = 'AM' if self._formula(sabado) == 'PM' else 'PM'
        AsignacionEspecialService.guardar_anual(self.ANIO, {sabado.isoformat(): contrario})
        self._materializar()
        self.assertEqual(AsignacionEspecialService.grupo_trabaja(sabado), contrario)

    def test_es_idempotente(self):
        self._materializar()
        n = AsignacionEspecialManual.objects.count()
        salida = self._materializar()
        self.assertEqual(AsignacionEspecialManual.objects.count(), n)
        self.assertIn('ya está congelado', salida)
