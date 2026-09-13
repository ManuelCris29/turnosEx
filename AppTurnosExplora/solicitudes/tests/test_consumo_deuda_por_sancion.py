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
from permisos.models import PermisoEspecial
from permisos.services.deuda_permiso_service import sincronizar
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

    def test_una_sancion_levantada_no_consume_la_deuda_la_condona(self):
        """
        Levantar y cumplir extinguen la deuda por vías distintas, y el estado lo distingue.

        La levantada NO puede quedar como 'consumida_por_sancion': eso diría que el castigo
        se pagó cumpliéndolo, que es justo lo que no pasó. Queda 'condonada', con la sanción
        y la fecha, para que un informe pueda separar lo que se cumplió de lo que se perdonó.

        Tampoco puede quedarse 'activa', que era el bug: el mes ya venció (no se puede
        pagar), esta sanción no la consumirá nunca (exige `levantada_en IS NULL`) y no nacerá
        otra que lo haga (el mes ya cuenta como juzgado). Se quedaba en el saldo para siempre.
        """
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = self._sancion()

        sancion.levantar(motivo='Excusa certificable', supervisor=self.sup)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'condonada')
        self.assertEqual(deuda.sancion_consumidora_id, sancion.id)
        self.assertEqual(deuda.fecha_consumo, sancion.levantada_en)

        # Y sigue así cuando pasa la fecha de fin planeada: ese día no ocurre nada.
        self._cumplir(sancion)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'condonada')

    def test_levantar_no_deja_deuda_pendiente_ni_reabre_sancion(self):
        """
        El cierre completo del limbo: tras levantar, ni queda saldo vencido que arrastrar
        ni el mes vuelve a sancionar. Se comprueban las dos salidas juntas porque arreglar
        una sin la otra deja el mismo problema con distinta cara.
        """
        self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = self._sancion()
        sancion.levantar(motivo='Excusa certificable', supervisor=self.sup)

        self.assertEqual(
            DeudaCorporativa.objects.filter(explorador=self.exp, estado='activa').count(), 0)

        antes = SancionEmpleado.objects.filter(explorador=self.exp).count()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.exp).count(), antes)

    def test_condonar_es_idempotente(self):
        """Un doble clic no condona dos veces ni reescribe la fecha del perdón."""
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = self._sancion()
        sancion.levantar(motivo='Excusa certificable', supervisor=self.sup)
        deuda.refresh_from_db()
        fecha = deuda.fecha_consumo

        n = DeudaCorporativaService.condonar_deudas_por_levantamiento(
            sancion, hoy=self.hoy + timedelta(days=5))

        self.assertEqual(n, 0)
        deuda.refresh_from_db()
        self.assertEqual(deuda.fecha_consumo, fecha)

    def test_levantar_no_toca_la_deuda_de_otros_meses(self):
        """Se condona el mes que originó la sanción, no el expediente entero."""
        del_mes = self._deuda()
        otro_mes = DeudaCorporativa.objects.create(
            explorador=self.exp, minutos=30, estado='activa',
            fecha_doblada=self.mes.fin_de_plazo() - timedelta(days=40))
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = SancionEmpleado.objects.filter(
            explorador=self.exp, periodo_anio=self.mes.anio,
            periodo_mes=self.mes.mes).first()

        sancion.levantar(motivo='Excusa certificable', supervisor=self.sup)

        del_mes.refresh_from_db()
        otro_mes.refresh_from_db()
        self.assertEqual(del_mes.estado, 'condonada')
        self.assertEqual(otro_mes.estado, 'activa')

    def test_una_sancion_manual_levantada_no_condona_nada(self):
        """Una sanción por llegar tarde no nació de un mes impagado: no hay qué perdonar."""
        deuda = self._deuda()
        manual = SancionEmpleado.objects.create(
            explorador=self.exp, supervisor=self.sup,
            fecha_inicio=self.hoy - timedelta(days=2),
            fecha_fin=self.hoy + timedelta(days=5),
            motivo='Sanción manual por llegar tarde')

        manual.levantar(motivo='Se aclaró', supervisor=self.sup)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'activa')

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

    def test_levantar_condona_tambien_la_deuda_mensual_de_un_permiso(self):
        """
        Las dos fuentes se perdonan igual, y el permiso se recalcula.

        El `pagado` del permiso es un agregado que vive aparte de sus meses: si no se
        rehace, el permiso sigue figurando como impagado en las pantallas que leen el
        agregado y el explorador ve reclamada una deuda que ya nadie puede cobrarle.
        """
        permiso = PermisoEspecial.objects.create(
            empleado=self.exp, tipo='PERSONAL', es_permanente=False,
            fecha_inicio=self.mes.fin_de_plazo(), fecha_fin=self.mes.fin_de_plazo(),
            tiempo=Decimal('2'), motivo='Cita', estado='APROBADO', supervisor=self.sup)
        sincronizar(permiso)
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self._sancion().levantar(motivo='Excusa certificable', supervisor=self.sup)

        permiso.refresh_from_db()
        self.assertEqual(permiso.deudas_mes.get().estado, 'condonada')
        self.assertTrue(permiso.pagado, 'ya no se le debe reclamar')

    def test_condona_aunque_se_haya_editado_el_motivo(self):
        """
        La auto-sanción se reconoce por su periodo, no por el texto del motivo.

        El motivo es editable desde la pantalla de sanciones. Si la detección dependiera de
        que empiece por el prefijo automático, bastaría con retocar la redacción para que la
        sanción dejara de reconocerse y sus horas volvieran al limbo: activas, no cobrables
        y sin sanción que las extinga.
        """
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = self._sancion()
        SancionEmpleado.objects.filter(id=sancion.id).update(
            motivo='Reescrito a mano por la supervisora')
        sancion.refresh_from_db()

        sancion.levantar(motivo='Excusa certificable', supervisor=self.sup)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'condonada')

    def test_editar_el_motivo_no_reabre_el_ciclo_de_sanciones(self):
        """
        Reescribir el motivo de una sanción automática no la vuelve invisible al sistema.

        Cuando el criterio era el prefijo del motivo, editarlo tenía dos efectos a la vez y
        ambos malos: la deuda no se consumía al cumplirse el castigo, y el mes dejaba de
        contar como juzgado, así que podía nacer una SEGUNDA sanción por el mismo mes ya
        castigado. Ahora el criterio es el periodo, que nadie edita.
        """
        deuda = self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        sancion = self._sancion()
        SancionEmpleado.objects.filter(id=sancion.id).update(
            motivo='Reescrito a mano por la supervisora')
        self._cumplir(sancion)

        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'consumida_por_sancion', 'el castigo cumplido la salda')
        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.exp).count(), 1,
                         'el mes ya juzgado no se sanciona dos veces')

    def test_al_levantar_se_avisa_al_explorador_por_la_campana(self):
        """
        El afectado tiene que enterarse de que le perdonaron las horas.

        Sin este aviso, toda la comunicación de la condonación vivía en la pantalla del
        supervisor y el explorador solo podía descubrirlo entrando por su cuenta al
        consolidado. Es un hecho irreversible que le cambia el saldo: se le dice.
        """
        from solicitudes.models import Notificacion

        self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)

        self._sancion().levantar(motivo='Excusa certificable', supervisor=self.sup)

        aviso = (Notificacion.objects
                 .filter(destinatario=self.exp, tipo='sancion_levantada')
                 .order_by('-id').first())
        self.assertIn('0.5 h', aviso.titulo)
        self.assertIn('condonar', aviso.mensaje)
        self.assertIn('antecedente', aviso.mensaje)
        self.assertIn('Excusa certificable', aviso.mensaje)

    def test_se_avisa_al_explorador_aunque_no_hubiera_horas_que_condonar(self):
        """Levantar sin deuda igual le interesa: recupera el derecho a solicitar."""
        from solicitudes.models import Notificacion

        manual = SancionEmpleado.objects.create(
            explorador=self.exp, supervisor=self.sup,
            fecha_inicio=self.hoy - timedelta(days=2),
            fecha_fin=self.hoy + timedelta(days=5),
            motivo='Sanción manual por llegar tarde')

        manual.levantar(motivo='Se aclaró', supervisor=self.sup)

        aviso = (Notificacion.objects
                 .filter(destinatario=self.exp, tipo='sancion_levantada')
                 .order_by('-id').first())
        self.assertEqual(aviso.titulo, '✅ Sanción levantada')
        self.assertIn('volver a realizar solicitudes', aviso.mensaje)

    def test_el_aviso_de_levantamiento_no_se_confunde_con_el_de_sancion(self):
        """
        Tipo propio, porque la campana elige el icono por el tipo.

        Compartiendo 'sancion', la buena noticia se pintaba con el mismo triángulo rojo de
        peligro que el castigo. Quien mira la campana de un vistazo lee el icono, no el
        título.
        """
        from solicitudes.models import Notificacion

        self._deuda()
        DeudaCorporativaService.gestionar_sancion_por_deuda(self.exp)
        self._sancion().levantar(motivo='Excusa certificable', supervisor=self.sup)

        tipos = list(Notificacion.objects.filter(destinatario=self.exp)
                     .order_by('id').values_list('tipo', flat=True))
        self.assertEqual(tipos, ['sancion', 'sancion_levantada'])
