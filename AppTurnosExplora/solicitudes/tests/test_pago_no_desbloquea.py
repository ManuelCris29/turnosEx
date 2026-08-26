"""
¿Pagar la deuda levanta la sanción? No. Se cumple entera.

Esta suite existía antes afirmando lo CONTRARIO: pagar desbloqueaba en el acto. Se invirtió
al cambiar la regla de negocio, y el motivo del cambio importa: mientras el pago levantaba
el castigo, la sanción no era una consecuencia sino una fianza reembolsable —el moroso
elegía cuándo dejar de estar bloqueado—. Ahora el castigo corre por su cuenta y lo único
que cambia el pago es el estado de la deuda.

La respuesta depende de tres piezas separadas, y por eso se comprueba con pruebas y no
leyendo el código: que `gestionar_sancion_por_deuda` NO levante, que `vigentes_en` siga
contando la sanción, y que el orquestador de solicitudes siga bloqueando.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, SancionEmpleado
from empleados.sancion_utils import sancion_activa
from solicitudes.models import DeudaCorporativa
from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService


class PagarNoDesbloqueaTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-pago', password='x'),
            nombre='Supervisora', apellido='T', cedula='sup-pago', activo=True)
        cls.exp = Empleado.objects.create(
            user=User.objects.create_user(username='exp-pago', password='x'),
            nombre='Explorador', apellido='T', cedula='exp-pago', activo=True,
            supervisor=cls.sup)

    def setUp(self):
        self.hoy = timezone.localdate()
        mes_pasado = self.hoy.replace(day=1) - timedelta(days=1)
        self.deuda = DeudaCorporativa.objects.create(
            explorador=self.exp, minutos=30, fecha_doblada=mes_pasado, estado='activa')
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self.sancion = SancionEmpleado.objects.get(explorador=self.exp)

    def _pagar(self):
        self.deuda.estado = 'pagada'
        self.deuda.fecha_pago = self.hoy
        self.deuda.save(update_fields=['estado', 'fecha_pago'])
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

    def test_estaba_bloqueado_y_le_faltaban_dias(self):
        """Punto de partida: sancionado, y la sanción NO ha terminado por su cuenta."""
        self.assertIsNotNone(sancion_activa(self.exp))
        self.assertGreater(self.sancion.fecha_fin, self.hoy,
                           'si ya hubiera vencido, la prueba no demostraría nada')

    def test_pagar_no_desbloquea(self):
        self._pagar()

        self.assertIsNotNone(sancion_activa(self.exp),
                             'la sanción se cumple entera: pagar no la levanta')

    def test_pagar_no_levanta_la_sancion(self):
        self._pagar()

        self.sancion.refresh_from_db()
        self.assertIsNone(self.sancion.levantada_en)
        self.assertEqual(self.sancion.estado, 'activa')

    def test_pagar_no_acorta_la_sancion(self):
        """La fecha de fin es la que se comunicó al explorador y no se toca."""
        fin_original = self.sancion.fecha_fin

        self._pagar()

        self.sancion.refresh_from_db()
        self.assertEqual(self.sancion.fecha_fin, fin_original)

    def test_pagar_si_cambia_el_estado_de_la_deuda(self):
        """Lo que el pago SÍ hace: saldar el ledger. Las dos cosas dejan de ir juntas."""
        self._pagar()

        self.deuda.refresh_from_db()
        self.assertEqual(self.deuda.estado, 'pagada')

    def test_el_orquestador_de_solicitudes_lo_sigue_bloqueando(self):
        """
        El bloqueo real vive en el orquestador, no en la pantalla. Si aquí pasara, el
        explorador podría enviar solicitudes por mucho que la pantalla se lo negara.
        """
        from solicitudes.services.solicitud_orchestrator import SolicitudOrchestrator

        self._pagar()

        error = SolicitudOrchestrator.verificar_sancion(self.exp)
        self.assertIsNotNone(error, 'un sancionado no puede solicitar aunque haya pagado')

    def test_al_terminar_la_sancion_se_desbloquea_solo(self):
        """Lo que SÍ desbloquea: cumplir la duración. No hace falta que nadie intervenga."""
        futuro = self.sancion.fecha_fin + timedelta(days=1)

        self.assertIsNone(sancion_activa(self.exp, futuro))

    def test_una_sancion_manual_tampoco_se_levanta_por_pagar(self):
        """Ya era así, y debe seguir siéndolo: son vías disciplinarias independientes."""
        manual = SancionEmpleado.objects.create(
            explorador=self.exp, supervisor=self.sup,
            fecha_inicio=self.hoy, fecha_fin=self.hoy + timedelta(days=5),
            motivo='Sanción manual del supervisor por llegar tarde')

        self._pagar()

        manual.refresh_from_db()
        self.assertIsNone(manual.levantada_en)

    def test_el_supervisor_sigue_pudiendo_levantarla_a_mano(self):
        """
        La vía humana no desaparece: lo que se elimina es el levantamiento AUTOMÁTICO por
        pago, no la potestad del supervisor de perdonar un castigo concreto.
        """
        self._pagar()

        self.sancion.levantar(motivo='Acuerdo con el explorador', supervisor=self.sup)

        self.assertIsNone(sancion_activa(self.exp))
        self.assertEqual(self.sancion.levantada_por, self.sup)

    def test_si_le_quedan_otras_deudas_vencidas_sigue_bloqueado(self):
        """Pagar una cosa no salda las demás."""
        hace_dos_meses = self.hoy.replace(day=1) - timedelta(days=45)
        DeudaCorporativa.objects.create(
            explorador=self.exp, minutos=30,
            fecha_doblada=hace_dos_meses, estado='activa')

        self._pagar()

        self.assertIsNotNone(sancion_activa(self.exp))
