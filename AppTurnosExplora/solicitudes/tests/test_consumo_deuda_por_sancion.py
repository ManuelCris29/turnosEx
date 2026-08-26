"""
Cumplir la sanción salda la deuda que la originó.

Es la pieza que cierra el ciclo. Como pagar ya no levanta el castigo, hacía falta decidir
qué pasa con la deuda cuando el castigo termina: si siguiera viva, el explorador saldría
de sus 15 días con el mismo saldo vencido que lo metió en ellos y volvería a ser
sancionado por lo mismo, en un bucle del que no se sale. La sanción cumplida ES el pago.

La distinción crítica que se prueba aquí: solo consume la sanción CUMPLIDA. Una levantada
a mano por el supervisor perdona el castigo, no la deuda.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, SancionEmpleado
from empleados.sancion_utils import sancion_activa
from permisos.deuda_permiso_service import sincronizar
from permisos.models import PermisoEspecial
from solicitudes.models import DeudaCorporativa
from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
from solicitudes.services.sancion_deuda_calculo import Periodo


class ConsumoDeudaPorSancionTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-consumo', password='x'),
            nombre='Supervisora', apellido='C', cedula='sup-cons', activo=True)
        cls.exp = Empleado.objects.create(
            user=User.objects.create_user(username='exp-consumo', password='x'),
            nombre='Explorador', apellido='C', cedula='exp-cons', activo=True,
            supervisor=cls.sup)

    def setUp(self):
        self.hoy = timezone.localdate()
        self.mes = Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=1))

    def _deuda(self):
        return DeudaCorporativa.objects.create(
            explorador=self.exp, minutos=30,
            fecha_doblada=self.mes.fin_de_plazo(), estado='activa')

    def _sancion(self):
        return SancionEmpleado.objects.filter(explorador=self.exp).order_by('-id').first()

    def _cumplir(self, sancion):
        """Adelanta el final de la sanción al pasado, como si ya se hubiera cumplido."""
        SancionEmpleado.objects.filter(id=sancion.id).update(
            fecha_inicio=self.hoy - timedelta(days=20),
            fecha_fin=self.hoy - timedelta(days=1))

    def test_al_cumplirse_la_sancion_la_deuda_queda_saldada(self):
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self._cumplir(self._sancion())

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'consumida_por_sancion')

    def test_queda_constancia_de_que_sancion_la_consumio(self):
        """
        La deuda deja de cobrarse pero no de explicarse: hay que poder responder por qué
        desapareció sin que nadie la pagara.
        """
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = self._sancion()
        self._cumplir(sancion)

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertEqual(deuda.sancion_consumidora_id, sancion.id)
        self.assertEqual(deuda.fecha_consumo, self.hoy)

    def test_criterio_15_la_misma_deuda_no_vuelve_a_sancionar(self):
        """
        Sin esto, terminar la sanción devolvía al explorador a la casilla de salida: mismo
        saldo vencido, nueva sanción, y así indefinidamente.
        """
        self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self._cumplir(self._sancion())

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.exp).count(), 1)
        self.assertIsNone(sancion_activa(self.exp), 'ya cumplió: vuelve a estar habilitado')

    def test_consumir_la_deuda_no_borra_el_antecedente(self):
        """
        La deuda y el historial de sanciones son cosas distintas: la primera se extingue,
        el segundo permanece. Si el antecedente desapareciera con ella, cada sanción
        cumplida devolvería al explorador a "primera vez" y nunca se llegaría a los 30 días.
        """
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = self._sancion()
        self._cumplir(sancion)

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'consumida_por_sancion')
        self.assertEqual(DeudaCorporativaService._antecedente(self.exp).nivel, 1,
                         'la sanción sigue siendo antecedente para la siguiente')

    def test_tras_consumir_un_mes_el_siguiente_incumplido_ya_es_reincidencia(self):
        """La consecuencia práctica de lo anterior: la segunda sanción son 30 días."""
        primero = Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=70))
        DeudaCorporativa.objects.create(
            explorador=self.exp, minutos=30,
            fecha_doblada=primero.fin_de_plazo(), estado='activa')
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        for sancion in SancionEmpleado.objects.filter(explorador=self.exp):
            self._cumplir(sancion)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self._deuda()   # ahora incumple también el mes pasado
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        nueva = self._sancion()
        self.assertEqual((nueva.periodo_anio, nueva.periodo_mes), (self.mes.anio, self.mes.mes))
        self.assertEqual((nueva.fecha_fin - nueva.fecha_inicio).days, 30)

    def test_una_sancion_todavia_en_curso_no_consume_nada(self):
        """El castigo salda la deuda al TERMINAR, no al empezar."""
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'activa')

    def test_una_sancion_levantada_a_mano_no_consume_la_deuda(self):
        """
        La distinción que sostiene la regla: levantar perdona UN castigo, no las horas.
        Si consumiera, cada levantamiento sería una condonación silenciosa de deuda.
        """
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = self._sancion()
        sancion.levantar(motivo='Acuerdo con el explorador', supervisor=self.sup)
        self._cumplir(sancion)

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'activa', 'sigue debiendo esas horas')

    def test_una_sancion_manual_cumplida_no_consume_deuda(self):
        """Una sanción por llegar tarde no salda horas: no viene de ninguna deuda."""
        deuda = self._deuda()
        SancionEmpleado.objects.create(
            explorador=self.exp, supervisor=self.sup,
            fecha_inicio=self.hoy - timedelta(days=20),
            fecha_fin=self.hoy - timedelta(days=1),
            motivo='Sanción manual por llegar tarde')

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertNotEqual(deuda.estado, 'consumida_por_sancion')

    def test_consumir_es_idempotente(self):
        """Se llama desde cinco disparadores distintos; repetirlo no puede alterar nada."""
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self._cumplir(self._sancion())
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        deuda.refresh_from_db()
        consumo = deuda.fecha_consumo

        resultado = DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertEqual(resultado['consumidas'], 0)
        self.assertEqual(deuda.fecha_consumo, consumo)

    def test_tambien_consume_la_deuda_mensual_de_un_permiso(self):
        """Las dos fuentes se saldan igual: la sanción no distingue de dónde venía el saldo."""
        permiso = PermisoEspecial.objects.create(
            empleado=self.exp, tipo='PERSONAL', es_permanente=False,
            fecha_inicio=self.mes.fin_de_plazo(), fecha_fin=self.mes.fin_de_plazo(),
            tiempo=Decimal('2'), motivo='Cita', estado='APROBADO', supervisor=self.sup)
        sincronizar(permiso)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self._cumplir(self._sancion())

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self.assertEqual(permiso.deudas_mes.get().estado, 'consumida_por_sancion')

    def test_al_consumir_la_deuda_del_permiso_se_actualiza_el_permiso(self):
        permiso = PermisoEspecial.objects.create(
            empleado=self.exp, tipo='PERSONAL', es_permanente=False,
            fecha_inicio=self.mes.fin_de_plazo(), fecha_fin=self.mes.fin_de_plazo(),
            tiempo=Decimal('2'), motivo='Cita', estado='APROBADO', supervisor=self.sup)
        sincronizar(permiso)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self._cumplir(self._sancion())

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        permiso.refresh_from_db()
        self.assertTrue(permiso.pagado, 'ya no se le debe reclamar')
