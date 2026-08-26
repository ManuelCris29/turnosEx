"""
CAPA 3 — Materialización de la sanción automática por deuda.

Estos tests cubren el SERVICIO: que grabe en la base de datos exactamente la sanción que
la capa de cálculo dice, que no duplique y que respete las decisiones del supervisor. La
aritmética de la escalada (cuánto dura cada nivel, cómo se encadenan) NO se re-comprueba
aquí: vive en `test_cadena_sanciones.py`, con fechas fijas. Por eso lo esperado se pide a
`cadena_sanciones()` en vez de recalcularlo a mano — si se recalculara, esta suite podría
pasar con una aritmética distinta de la real y no nos enteraríamos.

Nota histórica: la sanción nació primero con `fecha_inicio = hoy`, el día en que el
explorador casualmente abría la aplicación, lo que hacía que quien evitaba la app se
sancionara más tarde Y más barato. Después la unidad pasó a ser la doblada, y hoy es el
PERIODO MENSUAL, que es lo que permite tratar igual las dobladas y los permisos.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, SancionEmpleado
from empleados.sancion_utils import sancion_activa
from solicitudes.models import DeudaCorporativa
from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
from solicitudes.services.sancion_deuda_calculo import Periodo, cadena_sanciones


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

    def _deuda_de(self, periodo: Periodo, explorador=None):
        """Deuda de una doblada del mes indicado, sin pagar."""
        return DeudaCorporativa.objects.create(
            explorador=explorador or self.exp, minutos=30,
            fecha_doblada=periodo.fin_de_plazo(), estado='activa')

    def _mes_pasado(self) -> Periodo:
        primero = self.hoy.replace(day=1)
        return Periodo.de_fecha(primero - timedelta(days=1))

    def _deuda_vencida(self, explorador=None):
        """Deuda de un mes anterior al actual y sin pagar: la que dispara la sanción."""
        return self._deuda_de(self._mes_pasado(), explorador)

    def _sancion(self):
        return SancionEmpleado.objects.filter(explorador=self.exp).order_by('-id').first()

    def _sancion_esperada(self, *periodos):
        """Lo que la capa de cálculo dice que corresponde a esos meses incumplidos."""
        return cadena_sanciones(periodos)[-1]

    # ------------------------------------------------------------------ crear
    def test_deuda_vencida_crea_sancion(self):
        self._deuda_vencida()

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sancion = self._sancion()
        self.assertIsNotNone(sancion)
        self.assertEqual((sancion.fecha_fin - sancion.fecha_inicio).days, 15)
        self.assertIsNotNone(sancion_activa(self.exp), 'tiene que bloquear hoy')

    def test_la_sancion_guarda_de_que_mes_viene(self):
        """
        De este dato depende QUÉ deuda extingue al cumplirse. Deducirlo del texto del
        motivo haría que un retoque de redacción cambiara en silencio qué se condona.
        """
        mes = self._mes_pasado()
        self._deuda_de(mes)

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sancion = self._sancion()
        self.assertEqual((sancion.periodo_anio, sancion.periodo_mes), (mes.anio, mes.mes))

    def test_la_primera_sancion_dura_15_dias(self):
        self._deuda_vencida()

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sancion = self._sancion()
        self.assertEqual((sancion.fecha_fin - sancion.fecha_inicio).days, 15)

    def test_una_deuda_del_mes_en_curso_no_sanciona(self):
        """Todavía está en plazo: el mes no ha cerrado."""
        DeudaCorporativa.objects.create(
            explorador=self.exp, minutos=30, fecha_doblada=self.hoy, estado='activa')

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self.assertIsNone(self._sancion())

    def test_no_duplica_mientras_siga_vigente(self):
        self._deuda_vencida()

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.exp).count(), 1)

    def test_el_rango_grabado_nunca_esta_invertido(self):
        """`clean()` prohíbe fecha_fin < fecha_inicio; el servicio no puede producirlo."""
        self._deuda_vencida()

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sancion = self._sancion()
        self.assertGreaterEqual(sancion.fecha_fin, sancion.fecha_inicio)
        sancion.full_clean(exclude=['explorador', 'supervisor'])   # no lanza

    def test_el_castigo_nunca_nace_ya_cumplido(self):
        """
        La ventana teórica de un mes lejano ya expiró. Grabarla tal cual daría un castigo
        nacido muerto: se consumiría en el acto, extinguiendo la deuda sin haber bloqueado
        ni un día. Se desplaza al presente conservando su duración.
        """
        antiguo = Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=200))
        self._deuda_de(antiguo)

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sancion = self._sancion()
        self.assertGreaterEqual(sancion.fecha_fin, self.hoy)
        self.assertIsNotNone(sancion_activa(self.exp), 'debe bloquear de verdad')

    def test_una_deuda_aprobada_tarde_nace_vencida_y_aun_asi_bloquea(self):
        """
        El caso que motiva el desplazamiento, y que NO es un cron caído: un permiso
        pendiente desde hace meses que el supervisor aprueba hoy. Su deuda es de aquel mes,
        pero hasta este momento no existía, así que ninguna revisión diaria podría haberla
        materializado antes. La sanción tiene que bloquear de todos modos.
        """
        from decimal import Decimal

        from permisos.deuda_permiso_service import sincronizar
        from permisos.models import PermisoEspecial

        viejo = Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=40))
        dia = date(viejo.anio, viejo.mes, 10)
        permiso = PermisoEspecial.objects.create(
            empleado=self.exp, tipo='PERSONAL', es_permanente=False,
            fecha_inicio=dia, fecha_fin=dia, tiempo=Decimal('2'),
            motivo='pendiente desde hace meses', estado='PENDIENTE', supervisor=self.sup)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self.assertIsNone(self._sancion(), 'sin aprobar todavía no debe nada')

        permiso.estado = 'APROBADO'
        permiso.save(update_fields=['estado'])
        sincronizar(permiso)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self.assertIsNotNone(sancion_activa(self.exp),
                             'la deuda nació vencida, pero el castigo debe cumplirse')

    def test_enterarse_tarde_no_abarata_la_sancion(self):
        """
        La otra mitad de lo anterior, y la garantía que no se puede perder: el retraso mueve
        las fechas, pero la DURACIÓN sale del ledger y no cambia. Dos meses incumplidos son
        30 días tanto si se miran a tiempo como si se miran medio año después.
        """
        base = self.hoy.replace(day=1) - timedelta(days=200)
        self._deuda_de(Periodo.de_fecha(base))
        self._deuda_de(Periodo.de_fecha(base.replace(day=1) + timedelta(days=32)))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        duraciones = sorted(
            (s.fecha_fin - s.fecha_inicio).days
            for s in SancionEmpleado.objects.filter(explorador=self.exp))
        self.assertEqual(duraciones, [15, 30])

    # ---------------------------------------------------------- reincidencia
    def test_dos_meses_incumplidos_dan_15_y_30(self):
        primero = Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=70))
        segundo = Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=35))
        self._deuda_de(primero)
        self._deuda_de(segundo)

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sanciones = SancionEmpleado.objects.filter(explorador=self.exp).order_by('fecha_inicio')
        self.assertEqual([(s.fecha_fin - s.fecha_inicio).days for s in sanciones], [15, 30])

    def test_las_sanciones_encadenadas_no_se_solapan(self):
        """Dos castigos vigentes a la vez harían ambiguo cuándo termina el bloqueo."""
        for dias in (70, 35):
            self._deuda_de(Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=dias)))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        sanciones = list(SancionEmpleado.objects.filter(explorador=self.exp)
                         .order_by('fecha_inicio'))
        for anterior, siguiente in zip(sanciones, sanciones[1:]):
            self.assertGreater(siguiente.fecha_inicio, anterior.fecha_fin)

    def test_la_escalada_no_depende_de_que_existan_las_sanciones_anteriores(self):
        """
        El nivel sale del LEDGER, no de cuántos registros haya. Si se contaran las
        `SancionEmpleado` previas, borrarlas —o que un supervisor las levantara— abarataría
        la siguiente.
        """
        primero = Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=70))
        segundo = Periodo.de_fecha(self.hoy.replace(day=1) - timedelta(days=35))
        self._deuda_de(primero)
        self._deuda_de(segundo)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        esperado = {(s.periodo_anio, s.periodo_mes): (s.fecha_fin - s.fecha_inicio).days
                    for s in SancionEmpleado.objects.filter(explorador=self.exp)}

        SancionEmpleado.objects.filter(explorador=self.exp).delete()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        recalculado = {(s.periodo_anio, s.periodo_mes): (s.fecha_fin - s.fecha_inicio).days
                       for s in SancionEmpleado.objects.filter(explorador=self.exp)}
        self.assertEqual(recalculado, esperado)

    def test_sin_antecedente_previo_la_sancion_es_la_primera(self):
        """
        El nivel arranca en 1 cuando no hay historial: la reincidencia se mide sobre las
        sanciones anteriores, no sobre cuántas veces se haya debido algo.
        """
        self._deuda_vencida()

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self.assertEqual(self._sancion().nivel_reincidencia, 1)

    # ------------------------------------------------- decisiones del supervisor
    def test_una_sancion_levantada_por_el_supervisor_no_renace(self):
        """
        Si un SUPERVISOR la levantó (decisión humana), el proceso automático no puede
        recrearla en la siguiente pasada. Deshacer su decisión en silencio sería peor que
        dejar pasar a un moroso.
        """
        self._deuda_vencida()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self._sancion().levantar(motivo='Acuerdo con el explorador', supervisor=self.sup)

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.exp).count(), 1)
        self.assertIsNone(sancion_activa(self.exp))

    def test_una_sancion_levantada_a_mano_no_condona_la_deuda(self):
        """
        Levantar perdona el CASTIGO, no la deuda. Confundirlas convertiría cada
        levantamiento en una condonación silenciosa de horas.
        """
        deuda = self._deuda_vencida()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = self._sancion()
        sancion.levantar(motivo='Acuerdo', supervisor=self.sup)
        SancionEmpleado.objects.filter(id=sancion.id).update(
            fecha_fin=self.hoy - timedelta(days=1))

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'activa', 'sigue debiendo esas horas')

    def test_una_sancion_manual_no_impide_crear_la_automatica(self):
        """Son hechos disciplinarios distintos, con fechas distintas."""
        SancionEmpleado.objects.create(
            explorador=self.exp, supervisor=self.sup,
            fecha_inicio=self.hoy, fecha_fin=self.hoy + timedelta(days=3),
            motivo='Sanción manual por llegar tarde')
        self._deuda_vencida()

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        automaticas = SancionEmpleado.objects.filter(
            explorador=self.exp,
            motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO)
        self.assertEqual(automaticas.count(), 1)
