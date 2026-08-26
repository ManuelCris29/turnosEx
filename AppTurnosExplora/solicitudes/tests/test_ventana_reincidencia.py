"""
La reincidencia prescribe: la ventana configurable.

La escalada 15 → 30 → 45 era acumulativa para siempre. Eso significaba que un descuido
aislado de hace dos años seguía encareciendo la sanción de hoy, y que el castigo por un
tropiezo puntual acababa siendo de meses. Un antecedente disciplinario tiene que poder
prescribir.

Ahora, cuando una sanción termina arranca una ventana configurable (30 días por defecto).
Si dentro cae otra, es reincidencia; si la ventana se agota, el contador vuelve a cero.

Los escenarios de esta suite son los del enunciado de la regla, con sus fechas.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado, SancionEmpleado
from solicitudes.models import ConfiguracionSanciones, DeudaCorporativa
from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
from solicitudes.services.sancion_deuda_calculo import (
    Antecedente,
    Periodo,
    cadena_sanciones,
    nivel_siguiente,
)


class NivelSiguienteTest(SimpleTestCase):
    """La regla, aislada y con fechas fijas."""

    def test_sin_antecedente_es_la_primera(self):
        self.assertEqual(nivel_siguiente(None, date(2026, 8, 20), 30), 1)

    def test_escenario_1_dentro_de_la_ventana_es_reincidencia(self):
        """Sanción #1 termina el 15/08; la nueva llega el 20/08, dentro de los 30 días."""
        anterior = Antecedente(fin=date(2026, 8, 15), nivel=1)

        self.assertEqual(nivel_siguiente(anterior, date(2026, 8, 20), 30), 2)

    def test_escenario_2_pasada_la_ventana_el_contador_se_reinicia(self):
        """Termina el 15/08, la ventana muere el 14/09, la nueva llega el 20/09."""
        anterior = Antecedente(fin=date(2026, 8, 15), nivel=1)

        self.assertEqual(nivel_siguiente(anterior, date(2026, 9, 20), 30), 1)

    def test_escenario_3_la_escalada_continua_desde_el_nivel_anterior(self):
        """Sanción #2 (nivel 2) termina el 19/09; la #3 llega el 25/09 → nivel 3."""
        anterior = Antecedente(fin=date(2026, 9, 19), nivel=2)

        self.assertEqual(nivel_siguiente(anterior, date(2026, 9, 25), 30), 3)

    def test_el_ultimo_dia_de_la_ventana_todavia_cuenta(self):
        """Una ventana de 30 días abarca los 30 días siguientes, no 29."""
        anterior = Antecedente(fin=date(2026, 8, 15), nivel=1)

        self.assertEqual(nivel_siguiente(anterior, date(2026, 9, 14), 30), 2)

    def test_un_dia_despues_ya_prescribio(self):
        anterior = Antecedente(fin=date(2026, 8, 15), nivel=1)

        self.assertEqual(nivel_siguiente(anterior, date(2026, 9, 15), 30), 1)

    def test_la_ventana_se_mide_desde_el_FIN_no_desde_el_inicio(self):
        """
        Lo que abre el periodo de prueba es haber terminado de cumplir. Medir desde el
        inicio haría que una sanción larga se comiera su propia ventana.
        """
        anterior = Antecedente(fin=date(2026, 8, 15), nivel=1)   # empezó el 01/08

        # 20/09: a 36 días del INICIO, pero a 36 del fin -> prescrito con ventana de 30.
        self.assertEqual(nivel_siguiente(anterior, date(2026, 9, 20), 30), 1)
        # Con ventana de 60 sí entra.
        self.assertEqual(nivel_siguiente(anterior, date(2026, 9, 20), 60), 2)

    def test_una_ventana_mas_larga_mantiene_la_reincidencia(self):
        anterior = Antecedente(fin=date(2026, 8, 15), nivel=1)

        self.assertEqual(nivel_siguiente(anterior, date(2026, 10, 1), 90), 2)


class CadenaConAntecedenteTest(SimpleTestCase):

    def test_la_cadena_continua_la_escalada_de_lo_ya_existente(self):
        """Si ya cumplió una sanción reciente, el tramo nuevo no arranca de cero."""
        # Julio vence el 01/08; un antecedente que terminó el 20/07 queda a 12 días.
        anterior = Antecedente(fin=date(2026, 7, 20), nivel=1)

        (s,) = cadena_sanciones([Periodo(2026, 7)], 30, anterior)

        self.assertEqual(s.nivel, 2)
        self.assertEqual(s.duracion_dias, 30)

    def test_meses_consecutivos_escalan_con_la_ventana_por_defecto(self):
        """Es el caso corriente: incumplir tres meses seguidos da 15, 30 y 45."""
        cadena = cadena_sanciones([Periodo(2026, m) for m in (8, 9, 10)], ventana_dias=30)

        self.assertEqual([s.duracion_dias for s in cadena], [15, 30, 45])

    def test_una_ventana_muy_corta_impide_escalar_incluso_entre_meses_seguidos(self):
        """
        Consecuencia real de hacer la ventana configurable, y conviene tenerla presente al
        elegir el valor: entre el fin de una sanción y el vencimiento del mes siguiente
        pasan unos quince días. Con una ventana más corta que ese hueco, la reincidencia
        no llega a encadenarse nunca y todas las sanciones son de 15 días.
        """
        cadena = cadena_sanciones([Periodo(2026, m) for m in (8, 9, 10)], ventana_dias=3)

        self.assertEqual([s.duracion_dias for s in cadena], [15, 15, 15])

    def test_saltarse_un_mes_sigue_contando_como_reincidencia(self):
        """
        Incumplir enero, tener febrero limpio y volver a incumplir marzo SÍ escala. Es la
        razón de que la ventana por defecto sea 45 y no 30: el hueco entre el fin de la
        sanción de enero (16/02) y el vencimiento de marzo (01/04) es de 44 días, así que
        con 30 un solo mes limpio borraba el antecedente.
        """
        cadena = cadena_sanciones([Periodo(2026, 1), Periodo(2026, 3)], ventana_dias=45)

        self.assertEqual([s.duracion_dias for s in cadena], [15, 30])

    def test_saltarse_un_mes_escala_igual_venga_del_nivel_que_venga(self):
        """
        Con 30 días esto era desigual: quien venía de una sanción larga seguía escalando y
        quien venía de una corta no, porque la sanción larga acaba más cerca del siguiente
        vencimiento. Con 45 el hueco queda cubierto en todos los niveles.
        """
        desde_nivel_1 = cadena_sanciones([Periodo(2026, 1), Periodo(2026, 3)], 45)
        desde_nivel_3 = cadena_sanciones(
            [Periodo(2026, 1), Periodo(2026, 2), Periodo(2026, 3), Periodo(2026, 5)], 45)

        self.assertEqual(desde_nivel_1[-1].nivel, 2)
        self.assertEqual(desde_nivel_3[-1].nivel, 4, 'sigue la escalada tras el mes limpio')

    def test_saltarse_dos_meses_si_reinicia(self):
        """La ventana tiene que prescribir en algún momento: dos meses limpios bastan."""
        cadena = cadena_sanciones([Periodo(2026, 1), Periodo(2026, 4)], ventana_dias=45)

        self.assertEqual([s.duracion_dias for s in cadena], [15, 15])

    def test_un_antecedente_prescrito_no_arrastra_su_nivel(self):
        anterior = Antecedente(fin=date(2024, 1, 10), nivel=3)

        (s,) = cadena_sanciones([Periodo(2026, 7)], 30, anterior)

        self.assertEqual(s.nivel, 1)


class ConfiguracionSancionesTest(TestCase):

    def test_el_valor_por_defecto_son_45_dias(self):
        """
        45 y no 30: entre el fin de una sanción y el vencimiento del mes siguiente hay días
        muertos, y con 30 un solo mes limpio borraba el antecedente —de forma desigual,
        además—. Ver `test_saltarse_un_mes_sigue_contando_como_reincidencia`.
        """
        self.assertEqual(ConfiguracionSanciones.ventana_reincidencia(), 45)

    def test_obtener_es_un_singleton(self):
        primera = ConfiguracionSanciones.obtener()
        segunda = ConfiguracionSanciones.obtener()

        self.assertEqual(primera.pk, segunda.pk)
        self.assertEqual(ConfiguracionSanciones.objects.count(), 1)

    def test_el_supervisor_puede_cambiar_la_ventana(self):
        config = ConfiguracionSanciones.obtener()
        config.dias_ventana_reincidencia = 90
        config.save()

        self.assertEqual(ConfiguracionSanciones.ventana_reincidencia(), 90)

    def test_una_ventana_de_cero_dias_no_se_admite(self):
        from django.core.exceptions import ValidationError

        config = ConfiguracionSanciones.obtener()
        config.dias_ventana_reincidencia = 0

        with self.assertRaises(ValidationError):
            config.full_clean()


class VentanaEnElServicioTest(TestCase):
    """La regla aplicada de verdad, sobre sanciones grabadas."""

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-vent', password='x'),
            nombre='Sup', apellido='V', cedula='vt1', activo=True)
        cls.exp = Empleado.objects.create(
            user=User.objects.create_user(username='exp-vent', password='x'),
            nombre='Exp', apellido='V', cedula='vt2', activo=True, supervisor=cls.sup)

    def setUp(self):
        self.hoy = timezone.localdate()

    def _deuda(self, periodo):
        return DeudaCorporativa.objects.create(
            explorador=self.exp, minutos=30,
            fecha_doblada=periodo.fin_de_plazo(), estado='activa')

    def _sancion_cumplida(self, fin, nivel, motivo=None):
        """Una sanción ya terminada, como la que dejaría un incumplimiento anterior."""
        return SancionEmpleado.objects.create(
            explorador=self.exp, supervisor=self.sup,
            fecha_inicio=fin - timedelta(days=15), fecha_fin=fin,
            nivel_reincidencia=nivel,
            motivo=motivo or 'Sanción anterior ya cumplida')

    def test_la_sancion_guarda_su_nivel(self):
        """
        Se guarda y no se recalcula: si mañana cambia la ventana, lo que se le comunicó al
        explorador no puede reinterpretarse con la regla nueva.
        """
        self._deuda(Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=1)))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self.assertEqual(
            SancionEmpleado.objects.get(
                explorador=self.exp, periodo_anio__isnull=False
            ).nivel_reincidencia, 1)

    def test_con_un_antecedente_reciente_la_nueva_es_reincidencia(self):
        self._sancion_cumplida(fin=self.hoy - timedelta(days=5), nivel=1)
        self._deuda(Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=1)))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        nueva = SancionEmpleado.objects.filter(
            explorador=self.exp, periodo_anio__isnull=False).get()
        self.assertEqual(nueva.nivel_reincidencia, 2)
        self.assertEqual((nueva.fecha_fin - nueva.fecha_inicio).days, 30)

    def test_con_el_antecedente_prescrito_vuelve_a_ser_la_primera(self):
        self._sancion_cumplida(fin=self.hoy - timedelta(days=200), nivel=3)
        self._deuda(Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=1)))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        nueva = SancionEmpleado.objects.filter(
            explorador=self.exp, periodo_anio__isnull=False).get()
        self.assertEqual(nueva.nivel_reincidencia, 1)
        self.assertEqual((nueva.fecha_fin - nueva.fecha_inicio).days, 15)

    def test_una_sancion_manual_reciente_tambien_cuenta_como_antecedente(self):
        """
        Decisión de negocio: cualquier sanción es antecedente. Quien acaba de cumplir un
        castigo por otro motivo no está estrenando expediente.
        """
        self._sancion_cumplida(fin=self.hoy - timedelta(days=5), nivel=1,
                               motivo='Sanción manual por llegar tarde')
        self._deuda(Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=1)))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        nueva = SancionEmpleado.objects.filter(
            explorador=self.exp, periodo_anio__isnull=False).get()
        self.assertEqual(nueva.nivel_reincidencia, 2)

    def test_una_levantada_cuenta_y_la_ventana_corre_desde_que_se_levanto(self):
        """
        Levantar perdona ESE castigo, no borra que ocurrió — igual que tampoco condona la
        deuda. La ventana se mide desde el día en que dejó de aplicar.
        """
        anterior = self._sancion_cumplida(fin=self.hoy + timedelta(days=30), nivel=1)
        anterior.levantar(motivo='Acuerdo', supervisor=self.sup,
                          fecha=self.hoy - timedelta(days=3))
        self._deuda(Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=1)))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        nueva = SancionEmpleado.objects.filter(
            explorador=self.exp, periodo_anio__isnull=False).get()
        self.assertEqual(nueva.nivel_reincidencia, 2)

    def test_cambiar_la_ventana_no_recalcula_lo_ya_grabado(self):
        """Lo comunicado al explorador no cambia retroactivamente."""
        self._deuda(Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=1)))
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = SancionEmpleado.objects.filter(
            explorador=self.exp, periodo_anio__isnull=False).get()
        fin_original = sancion.fecha_fin

        config = ConfiguracionSanciones.obtener()
        config.dias_ventana_reincidencia = 90
        config.save()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sancion.refresh_from_db()
        self.assertEqual(sancion.fecha_fin, fin_original)

    def test_una_ventana_mas_larga_mantiene_viva_la_reincidencia(self):
        """La configuración cambia de verdad el resultado de lo que viene después."""
        self._sancion_cumplida(fin=self.hoy - timedelta(days=45), nivel=1)
        config = ConfiguracionSanciones.obtener()
        config.dias_ventana_reincidencia = 90
        config.save()
        self._deuda(Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=1)))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        nueva = SancionEmpleado.objects.filter(
            explorador=self.exp, periodo_anio__isnull=False).get()
        self.assertEqual(nueva.nivel_reincidencia, 2,
                         'con 90 días de ventana, lo de hace 45 sigue contando')

    def test_el_historial_de_sanciones_sobrevive_al_consumo_de_la_deuda(self):
        """
        La deuda se consume al cumplirse la sanción, pero el antecedente permanece: son
        conceptos independientes, y la reincidencia se mide sobre el historial.
        """
        mes = Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=1))
        deuda = self._deuda(mes)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = SancionEmpleado.objects.filter(
            explorador=self.exp, periodo_anio__isnull=False).get()
        SancionEmpleado.objects.filter(id=sancion.id).update(
            fecha_inicio=self.hoy - timedelta(days=20),
            fecha_fin=self.hoy - timedelta(days=1))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'consumida_por_sancion')
        self.assertTrue(SancionEmpleado.objects.filter(id=sancion.id).exists(),
                        'el antecedente no se borra con la deuda')


class PantallaDeConfiguracionTest(TestCase):
    """El supervisor cambia la ventana desde la pantalla de morosos."""

    def setUp(self):
        from django.test import Client

        jefe = User.objects.create_user('vent.jefe', password='x', is_staff=True)
        Empleado.objects.create(user=jefe, nombre='Jefa', apellido='V',
                                cedula='vt9', activo=True)
        self.client = Client()
        self.client.force_login(jefe)
        self.url = reverse('sanciones_morosos')

    def test_la_pantalla_muestra_el_valor_actual(self):
        r = self.client.get(self.url)

        self.assertEqual(r.context['config_sanciones'].dias_ventana_reincidencia, 45)
        self.assertContains(r, 'Ventana de reincidencia')

    def test_el_supervisor_la_cambia(self):
        self.client.post(self.url, {'accion': 'config',
                                    'dias_ventana_reincidencia': '60'})

        self.assertEqual(ConfiguracionSanciones.ventana_reincidencia(), 60)

    def test_queda_registrado_quien_la_cambio(self):
        """Es una decisión de política disciplinaria: debe poder rastrearse."""
        self.client.post(self.url, {'accion': 'config',
                                    'dias_ventana_reincidencia': '45'})

        self.assertEqual(ConfiguracionSanciones.obtener().actualizado_por.cedula, 'vt9')

    def test_un_valor_no_numerico_no_revienta_ni_guarda(self):
        self.client.post(self.url, {'accion': 'config',
                                    'dias_ventana_reincidencia': 'treinta'})

        self.assertEqual(ConfiguracionSanciones.ventana_reincidencia(), 45)

    def test_cero_dias_se_rechaza(self):
        r = self.client.post(self.url, {'accion': 'config',
                                        'dias_ventana_reincidencia': '0'}, follow=True)

        self.assertEqual(ConfiguracionSanciones.ventana_reincidencia(), 45)
        self.assertContains(r, 'al menos un día')

    def test_guardar_la_config_no_aplica_sanciones(self):
        """
        Los dos botones de la pantalla hacen cosas distintas. Cambiar un parámetro no puede
        tener, de paso, efectos disciplinarios sobre nadie.
        """
        sup = Empleado.objects.get(cedula='vt9')
        exp = Empleado.objects.create(
            user=User.objects.create_user('vent.moroso', password='x'),
            nombre='Moroso', apellido='V', cedula='vt8', activo=True, supervisor=sup)
        hoy = timezone.localdate()
        DeudaCorporativa.objects.create(
            explorador=exp, minutos=30, estado='activa',
            fecha_doblada=hoy.replace(day=1) - timedelta(days=1))

        self.client.post(self.url, {'accion': 'config',
                                    'dias_ventana_reincidencia': '45'})

        self.assertFalse(SancionEmpleado.objects.filter(explorador=exp).exists())


class ReglaFormalDelEnunciadoTest(TestCase):
    """
    Los tres escenarios del enunciado, extremo a extremo y con sus fechas exactas, para que
    la regla quede fijada tal y como se especificó.
    """

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-esc', password='x'),
            nombre='Sup', apellido='E', cedula='es1', activo=True)
        cls.exp = Empleado.objects.create(
            user=User.objects.create_user(username='exp-esc', password='x'),
            nombre='Exp', apellido='E', cedula='es2', activo=True, supervisor=cls.sup)

    def _nivel_tras(self, fin_anterior, nivel_anterior, inicio_nueva, ventana=30):
        return nivel_siguiente(Antecedente(fin=fin_anterior, nivel=nivel_anterior),
                               inicio_nueva, ventana)

    def test_escenario_1(self):
        """01/08 → sanción #1 (15 d) → 15/08 finaliza; 20/08 nueva → 30 días."""
        nivel = self._nivel_tras(date(2026, 8, 15), 1, date(2026, 8, 20))

        self.assertEqual(nivel, 2)
        self.assertEqual(nivel * 15, 30)

    def test_escenario_2(self):
        """15/08 finaliza; 15/09 vence la ventana; 20/09 nueva → vuelve a 15 días."""
        nivel = self._nivel_tras(date(2026, 8, 15), 1, date(2026, 9, 20))

        self.assertEqual(nivel, 1)
        self.assertEqual(nivel * 15, 15)

    def test_escenario_3(self):
        """#2 (nivel 2) finaliza el 19/09; #3 llega el 25/09 → 45 días."""
        nivel = self._nivel_tras(date(2026, 9, 19), 2, date(2026, 9, 25))

        self.assertEqual(nivel, 3)
        self.assertEqual(nivel * 15, 45)
