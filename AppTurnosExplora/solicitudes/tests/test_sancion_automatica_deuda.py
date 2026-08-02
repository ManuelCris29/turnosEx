"""
Sanción automática por deuda corporativa vencida y su levantamiento al pagar.

El caso que motivó estos tests: la sanción se crea en el momento en que el
explorador intenta solicitar algo, así que su primer día es SIEMPRE hoy. Si pagaba
ese mismo día, el levantamiento —que consistía en dejar `fecha_fin` en ayer— la
dejaba con la fecha de fin ANTES de la de inicio, un rango que el propio `clean()`
del modelo prohíbe, y de paso borraba la duración original.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, SancionEmpleado
from empleados.sancion_utils import sancion_activa
from solicitudes.models import DeudaCorporativa
from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService


class SancionAutomaticaPorDeudaTest(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-auto', password='x'),
            nombre='Supervisora', apellido='Test', cedula='sup-auto', activo=True)
        cls.exp = Empleado.objects.create(
            user=User.objects.create_user(username='exp-auto', password='x'),
            nombre='Explorador', apellido='Test', cedula='exp-auto',
            activo=True, supervisor=cls.sup)

    def setUp(self):
        self.hoy = timezone.localdate()

    def _deuda_vencida(self, explorador=None):
        """Deuda de un mes anterior al actual y sin pagar: la que dispara la sanción."""
        primero = self.hoy.replace(day=1)
        mes_pasado = primero - timedelta(days=1)
        return DeudaCorporativa.objects.create(
            explorador=explorador or self.exp, minutos=30,
            fecha_doblada=mes_pasado, estado='activa',
        )

    def _sancion(self):
        return SancionEmpleado.objects.filter(explorador=self.exp).order_by('-id').first()

    # ------------------------------------------------------------------ crear
    def test_deuda_vencida_crea_sancion(self):
        self._deuda_vencida()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sancion = self._sancion()
        self.assertIsNotNone(sancion)
        self.assertEqual(sancion.fecha_inicio, self.hoy)
        self.assertEqual(sancion.fecha_fin, self.hoy + timedelta(days=15))
        self.assertIsNotNone(sancion_activa(self.exp))

    def test_no_duplica_mientras_siga_vigente(self):
        self._deuda_vencida()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.exp).count(), 1)

    # -------------------------------------------------------------- levantar
    def test_pagar_el_mismo_dia_no_invierte_el_rango(self):
        """El bug original: nace y se levanta hoy → fecha_fin quedaba antes que fecha_inicio."""
        deuda = self._deuda_vencida()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        fin_original = self._sancion().fecha_fin

        deuda.estado = 'pagada'
        deuda.save(update_fields=['estado'])
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sancion = self._sancion()
        self.assertGreaterEqual(sancion.fecha_fin, sancion.fecha_inicio)
        self.assertEqual(sancion.fecha_fin, fin_original, 'la duración planeada no se toca')
        sancion.full_clean(exclude=['explorador', 'supervisor'])   # no lanza

    def test_pagar_levanta_la_sancion_y_deja_constancia(self):
        deuda = self._deuda_vencida()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self.assertIsNotNone(sancion_activa(self.exp))

        deuda.estado = 'pagada'
        deuda.save(update_fields=['estado'])
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sancion = self._sancion()
        self.assertEqual(sancion.levantada_en, self.hoy)
        self.assertIsNone(sancion.levantada_por, 'la levantó el sistema, no una persona')
        self.assertIn('pagada', sancion.levantada_motivo.lower())
        self.assertIsNone(sancion_activa(self.exp), 'ya no debe bloquear')

    def test_la_sancion_levantada_no_deja_de_existir(self):
        """Se levanta, no se borra: el hecho disciplinario sigue en el historial."""
        deuda = self._deuda_vencida()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        deuda.estado = 'pagada'
        deuda.save(update_fields=['estado'])
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.exp).count(), 1)
        self.assertEqual(self._sancion().estado, 'levantada')

    # ---------------------------------------------------------- reincidencia
    def test_una_sancion_levantada_no_cuenta_como_reincidencia(self):
        """
        Pagar no puede agravar la siguiente sanción. Antes sí lo hacía: levantar dejaba
        la fecha_fin en el pasado y el contador de reincidencias la veía como vencida,
        así que quien pagaba empezaba la siguiente en 30 días en vez de 15.
        """
        deuda = self._deuda_vencida()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        deuda.estado = 'pagada'
        deuda.save(update_fields=['estado'])
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self.assertEqual(self._sancion().estado, 'levantada')

        # Vuelve a deber: la nueva sanción debe ser de 15 días, no de 30.
        self._deuda_vencida()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        nueva = self._sancion()
        self.assertIsNone(nueva.levantada_en)
        self.assertEqual(nueva.fecha_fin, self.hoy + timedelta(days=15))

    def test_sancion_vencida_sin_pagar_si_agrava_la_siguiente(self):
        """El agravante sigue existiendo para quien deja vencer la sanción sin pagar."""
        self._deuda_vencida()
        vencida_desde = self.hoy.replace(day=1)
        SancionEmpleado.objects.create(
            explorador=self.exp, supervisor=self.sup,
            fecha_inicio=vencida_desde,
            fecha_fin=self.hoy - timedelta(days=1),
            motivo=f'{DeudaCorporativaService.AUTO_SANCION_PREFIJO} anterior sin pagar',
        )

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        nueva = self._sancion()
        self.assertEqual(nueva.fecha_fin, self.hoy + timedelta(days=30),
                         'reincidencia #1 → 30 días')
