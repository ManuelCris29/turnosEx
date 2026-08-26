"""
CAPA 2 — La revisión diaria: idempotencia, coordinación entre workers y convivencia con
las sanciones manuales del supervisor.

El comando `revisar_sanciones_por_deuda` corre a diario aunque la regla sea mensual. Eso
solo es seguro si repetirlo no hace daño, así que la mitad de esta suite se dedica a
comprobar que ejecutarlo dos veces, o tres días seguidos, no duplica nada.

La otra mitad protege un requisito explícito: **el proceso automático no puede tocar las
sanciones que el supervisor pone a mano**. Son dos vías paralelas.
"""
from datetime import timedelta
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, SancionEmpleado
from empleados.sancion_utils import sancion_activa
from solicitudes.models import DeudaCorporativa, RevisionSancionesDeuda
from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService


class RevisionDiariaTestBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-rev', password='x'),
            nombre='Supervisora', apellido='Test', cedula='sup-rev', activo=True)
        cls.moroso = Empleado.objects.create(
            user=User.objects.create_user(username='moroso-rev', password='x'),
            nombre='Moroso', apellido='Rev', cedula='moroso-rev', activo=True,
            supervisor=cls.sup)

    def setUp(self):
        self.hoy = timezone.localdate()
        mes_pasado = self.hoy.replace(day=1) - timedelta(days=1)
        self.deuda = DeudaCorporativa.objects.create(
            explorador=self.moroso, minutos=30, fecha_doblada=mes_pasado, estado='activa')

    def _correr(self, *args):
        salida = StringIO()
        call_command('revisar_sanciones_por_deuda', *args, stdout=salida)
        return salida.getvalue()

    def _autos(self):
        return SancionEmpleado.objects.filter(
            explorador=self.moroso,
            motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO)


class IdempotenciaTest(RevisionDiariaTestBase):

    def test_una_pasada_sanciona_al_moroso(self):
        self._correr()

        self.assertEqual(self._autos().count(), 1)
        self.assertIsNotNone(sancion_activa(self.moroso))

    def test_repetir_el_mismo_dia_no_duplica(self):
        """
        La defensa de verdad son las guardas del servicio, no el marcador: aunque se fuerce
        la re-ejecución, el resultado tiene que seguir siendo una sola sanción.
        """
        self._correr()
        self._correr('--force')
        self._correr('--force')

        self.assertEqual(self._autos().count(), 1)

    def test_el_marcador_evita_el_trabajo_repetido_del_dia(self):
        self._correr()
        salida = self._correr()

        self.assertIn('ya se ejecutó', salida)
        self.assertEqual(RevisionSancionesDeuda.objects.filter(fecha=self.hoy).count(), 1)

    def test_el_marcador_es_unico_por_dia(self):
        """
        Es el candado que coordina los 3 workers de gunicorn: la unicidad la impone la base
        de datos porque la caché (LocMem) es por proceso y no coordinaría nada.
        """
        self._correr()

        _, creada = RevisionSancionesDeuda.objects.get_or_create(fecha=self.hoy)
        self.assertFalse(creada, 'el segundo proceso NO debe poder tomar el candado')

    def test_el_marcador_deja_constancia_de_lo_que_hizo(self):
        self._correr()

        marca = RevisionSancionesDeuda.objects.get(fecha=self.hoy)
        self.assertEqual(marca.sanciones_creadas, 1)
        self.assertIn('Moroso', marca.detalle)

    def test_dry_run_no_escribe_ni_marca_el_dia(self):
        salida = self._correr('--dry-run')

        self.assertIn('DRY-RUN', salida)
        self.assertFalse(SancionEmpleado.objects.exists())
        self.assertFalse(RevisionSancionesDeuda.objects.exists(),
                         'un diagnóstico no puede consumir el turno del día')

    def test_dry_run_no_impide_la_ejecucion_posterior(self):
        self._correr('--dry-run')
        self._correr()

        self.assertEqual(self._autos().count(), 1)


class PagarNoLevantaTest(RevisionDiariaTestBase):
    """
    Antes, la revisión diaria levantaba la sanción de quien había pagado. Ya no: el castigo
    se cumple entero. Lo que la revisión cierra al final del ciclo es la DEUDA, saldada por
    la propia sanción cuando esta termina.
    """

    def test_pagar_no_levanta_la_sancion_en_la_revision(self):
        self._correr()
        self.deuda.estado = 'pagada'
        self.deuda.fecha_pago = self.hoy
        self.deuda.save(update_fields=['estado', 'fecha_pago'])

        self._correr('--force')

        self.assertEqual(self._autos().get().estado, 'activa')
        self.assertIsNotNone(sancion_activa(self.moroso), 'sigue bloqueado hasta cumplir')

    def test_al_cumplirse_la_sancion_la_revision_salda_la_deuda(self):
        self._correr()
        SancionEmpleado.objects.filter(id=self._autos().get().id).update(
            fecha_inicio=self.hoy - timedelta(days=20),
            fecha_fin=self.hoy - timedelta(days=1))

        self._correr('--force')

        self.deuda.refresh_from_db()
        self.assertEqual(self.deuda.estado, 'consumida_por_sancion')

    def test_lo_cuenta_en_el_marcador(self):
        """La bitácora operativa debe reflejar lo que de verdad hizo el proceso."""
        self._correr()
        SancionEmpleado.objects.filter(id=self._autos().get().id).update(
            fecha_inicio=self.hoy - timedelta(days=20),
            fecha_fin=self.hoy - timedelta(days=1))

        self._correr('--force')

        marca = RevisionSancionesDeuda.objects.get(fecha=self.hoy)
        self.assertEqual(marca.sanciones_levantadas, 1)


class SancionesManualesIntactasTest(RevisionDiariaTestBase):
    """
    Requisito explícito: el supervisor sigue pudiendo poner y levantar sanciones a mano, y
    el proceso automático no las toca. Se distinguen por el prefijo del motivo.
    """

    def _manual(self, **kwargs):
        datos = dict(
            explorador=self.moroso, supervisor=self.sup,
            fecha_inicio=self.hoy, fecha_fin=self.hoy + timedelta(days=5),
            motivo='Sanción manual del supervisor por llegar tarde')
        datos.update(kwargs)
        return SancionEmpleado.objects.create(**datos)

    def test_la_revision_no_levanta_una_sancion_manual_aunque_pague(self):
        manual = self._manual()
        self.deuda.estado = 'pagada'
        self.deuda.save(update_fields=['estado'])

        self._correr()

        manual.refresh_from_db()
        self.assertIsNone(manual.levantada_en, 'pagar la deuda no borra un castigo manual')
        self.assertIsNotNone(sancion_activa(self.moroso), 'sigue bloqueado por la manual')

    def test_la_revision_no_modifica_una_sancion_manual(self):
        manual = self._manual()
        antes = (manual.fecha_inicio, manual.fecha_fin, manual.motivo)

        self._correr()

        manual.refresh_from_db()
        self.assertEqual((manual.fecha_inicio, manual.fecha_fin, manual.motivo), antes)

    def test_una_manual_vigente_no_impide_crear_la_automatica(self):
        """
        Son hechos distintos con fechas distintas. Si la manual bloqueara la creación de la
        automática, al terminar la manual el moroso quedaría libre pese a seguir debiendo.
        """
        self._manual()

        self._correr()

        self.assertEqual(self._autos().count(), 1)
        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.moroso).count(), 2)

    def test_el_supervisor_sigue_pudiendo_levantar_a_mano(self):
        self._correr()
        auto = self._autos().get()

        auto.levantar(motivo='Acuerdo con el explorador', supervisor=self.sup)

        auto.refresh_from_db()
        self.assertEqual(auto.levantada_por, self.sup)
        self.assertIsNone(sancion_activa(self.moroso))

    def test_lo_que_levanta_el_supervisor_no_lo_recrea_la_revision_al_dia_siguiente(self):
        """El fallo más fácil de introducir: que el cron deshaga cada noche su decisión."""
        self._correr()
        self._autos().get().levantar(motivo='Acuerdo', supervisor=self.sup)

        self._correr('--force')
        self._correr('--force')

        self.assertEqual(self._autos().count(), 1)
        self.assertIsNone(sancion_activa(self.moroso))


class ResistenciaTest(RevisionDiariaTestBase):

    def test_sin_morosos_no_falla_ni_deja_el_dia_sin_marcar(self):
        self.deuda.estado = 'pagada'
        self.deuda.save(update_fields=['estado'])

        self._correr()

        self.assertTrue(RevisionSancionesDeuda.objects.filter(fecha=self.hoy).exists())
        self.assertFalse(SancionEmpleado.objects.exists())

    def test_un_explorador_que_falla_no_impide_revisar_al_resto(self):
        """
        Si una excepción subiera, todos los exploradores que van detrás se quedarían sin
        revisar hasta mañana por culpa de un dato raro de otra persona.
        """
        otro = Empleado.objects.create(
            user=User.objects.create_user(username='otro-rev', password='x'),
            nombre='Otro', apellido='Rev', cedula='otro-rev', activo=True, supervisor=self.sup)
        DeudaCorporativa.objects.create(
            explorador=otro, minutos=30,
            fecha_doblada=self.hoy.replace(day=1) - timedelta(days=1), estado='activa')

        original = DeudaCorporativaService._periodos_con_deuda
        fallados = []

        def _romper_para_uno(explorador):
            if explorador.id == self.moroso.id and not fallados:
                fallados.append(explorador.id)
                raise RuntimeError('dato corrupto simulado')
            return original(explorador)

        DeudaCorporativaService._periodos_con_deuda = staticmethod(_romper_para_uno)
        try:
            self._correr()
        finally:
            DeudaCorporativaService._periodos_con_deuda = staticmethod(original)

        self.assertIsNotNone(sancion_activa(otro), 'el segundo tenía que quedar sancionado')
