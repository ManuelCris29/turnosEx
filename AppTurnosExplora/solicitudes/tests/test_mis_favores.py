"""
Pantalla "Mis Favores": el registro de días de finde cubiertos entre exploradores.

`DeudaExplorador` existía desde el principio pero solo se veía por el admin de Django: un
explorador no podía saber quién le cubrió un día ni a quién se lo devolvió.

Ojo con los estados: como la fecha de pago se pacta en la MISMA solicitud, la deuda nace ya
'pagada'. Por eso la pantalla muestra el historial y no una lista de "lo que debes", que estaría
siempre vacía.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado
from solicitudes.models import (
    DeudaExplorador, DobladaDetalle, SolicitudCambio, TipoSolicitudCambio,
)
from solicitudes.views.favores import LIMITE_POR_TARJETA

URL = '/solicitudes/mis-favores/'


class FavoresBase(TestCase):
    """Escenario común: yo, un compañero y un tercero ajeno. Sin tests propios."""

    def setUp(self):
        self.tipo = TipoSolicitudCambio.objects.create(nombre='D FDS')
        self.yo = self._emp('favor.yo', '7001')
        self.otro = self._emp('favor.otro', '7002')
        self.ajeno = self._emp('favor.ajeno', '7003')
        self.hoy = timezone.localdate()

    def _emp(self, username, cedula):
        u = User.objects.create_user(username=username, password='x')
        return Empleado.objects.create(user=u, nombre=username.split('.')[1],
                                       apellido='T', cedula=cedula, activo=True)

    def _favor(self, deudor, acreedor, dia_cubierto, estado='pagada', pagada_el=None):
        s = SolicitudCambio.objects.create(
            explorador_solicitante=deudor, explorador_receptor=acreedor,
            tipo_cambio=self.tipo, comentario='x', fecha_cambio_turno=dia_cubierto,
            estado='aprobada', fecha_resolucion=timezone.now())
        return DeudaExplorador.objects.create(
            deudor=deudor, acreedor=acreedor, solicitud_origen=s,
            fecha_pago_pactada=dia_cubierto + timedelta(days=7),
            fecha_pago_real=pagada_el, estado=estado, jornada_cedida='AM')


class MisFavoresTest(FavoresBase):
    def test_muestra_los_favores_recibidos_y_hechos(self):
        cubierto = self.hoy + timedelta(days=10)
        self._favor(self.yo, self.otro, cubierto,
                    pagada_el=cubierto + timedelta(days=7))     # me cubrió `otro`
        self._favor(self.otro, self.yo, cubierto + timedelta(days=1),
                    pagada_el=cubierto + timedelta(days=8))     # yo cubrí a `otro`

        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['recibidos']), 1)
        self.assertEqual(len(r.context['hechos']), 1)
        self.assertEqual(r.context['recibidos'][0]['companero'].id, self.otro.id)
        self.assertEqual(r.context['hechos'][0]['companero'].id, self.otro.id)

    def test_no_muestra_favores_de_otras_personas(self):
        self._favor(self.otro, self.ajeno, self.hoy + timedelta(days=10),
                    pagada_el=self.hoy + timedelta(days=17))
        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual(r.context['recibidos'], [])
        self.assertEqual(r.context['hechos'], [])

    def test_las_canceladas_no_se_listan(self):
        """Un acuerdo deshecho no es un favor."""
        self._favor(self.yo, self.otro, self.hoy + timedelta(days=10), estado='cancelada')
        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual(r.context['recibidos'], [])

    def test_distingue_lo_ya_devuelto_de_lo_pendiente(self):
        cubierto = self.hoy + timedelta(days=10)
        self._favor(self.yo, self.otro, cubierto, estado='pendiente')      # sin devolver
        self._favor(self.yo, self.ajeno, cubierto + timedelta(days=1),
                    pagada_el=cubierto + timedelta(days=8))                # devuelto

        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual(r.context['pendientes_de_devolver'], 1)
        devueltos = [f for f in r.context['recibidos'] if f['devuelto']]
        self.assertEqual(len(devueltos), 1)

    def test_muestra_el_dia_que_se_cubrio_no_solo_el_de_pago(self):
        """Lo que importa saber es QUÉ día trabajó por ti, que es la fecha de cesión."""
        cubierto = self.hoy + timedelta(days=10)
        self._favor(self.yo, self.otro, cubierto, pagada_el=cubierto + timedelta(days=7))
        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual(r.context['recibidos'][0]['fecha_cubierta'], cubierto)

    def test_requiere_sesion(self):
        r = self.client.get(URL)
        self.assertIn(r.status_code, (301, 302))

    def test_cuenta_los_favores_hechos_sin_cobrar(self):
        """El contador de la tarjeta 'Cubriste a' tenía tabla pero no test."""
        cubierto = self.hoy + timedelta(days=10)
        self._favor(self.otro, self.yo, cubierto, estado='pendiente')      # no me lo han devuelto
        self._favor(self.ajeno, self.yo, cubierto + timedelta(days=1),
                    pagada_el=cubierto + timedelta(days=8))                # ya me lo devolvieron

        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual(r.context['pendientes_de_cobrar'], 1)
        self.assertEqual(r.context['pendientes_de_devolver'], 0)

    def test_ordena_por_el_dia_cubierto_que_es_el_que_se_muestra(self):
        """Ordenar por la fecha de pago hacía que el listado visible pareciera arbitrario."""
        viejo = self.hoy + timedelta(days=5)
        nuevo = self.hoy + timedelta(days=40)
        # El favor MÁS RECIENTE se pacta con la devolución más lejana en el tiempo,
        # así que ordenar por una u otra fecha da resultados distintos.
        self._favor(self.yo, self.otro, viejo, pagada_el=viejo + timedelta(days=90))
        self._favor(self.yo, self.ajeno, nuevo, pagada_el=nuevo + timedelta(days=1))

        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual([f['fecha_cubierta'] for f in r.context['recibidos']], [nuevo, viejo])

    def test_distingue_dia_completo_de_media_jornada(self):
        """D FDS cede un finde entero; la doblada, media jornada. Se veían iguales."""
        cubierto = self.hoy + timedelta(days=10)
        d = self._favor(self.yo, self.otro, cubierto, pagada_el=cubierto + timedelta(days=7))
        DeudaExplorador.objects.filter(pk=d.pk).update(media_jornada=False)

        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual(r.context['recibidos'][0]['jornada'], 'Día completo')

    def test_recorta_el_historial_largo_pero_no_los_contadores(self):
        cubierto = self.hoy
        for i in range(LIMITE_POR_TARJETA + 3):
            self._favor(self.yo, self.otro, cubierto + timedelta(days=i), estado='pendiente')

        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual(len(r.context['recibidos']), LIMITE_POR_TARJETA)
        self.assertTrue(r.context['recortados'])
        # El contador habla del total, no de lo que cabe en pantalla.
        self.assertEqual(r.context['pendientes_de_devolver'], LIMITE_POR_TARJETA + 3)

        completo = self.client.get(URL, {'todo': '1'})
        self.assertEqual(len(completo.context['recibidos']), LIMITE_POR_TARJETA + 3)
        self.assertFalse(completo.context['recortados'])


class DeudaResidualSabadoTest(FavoresBase):
    """
    Pago en sábado cubriendo AMBAS jornadas: `DobladaDeudaService` crea una SEGUNDA deuda
    con deudor y acreedor invertidos sobre la MISMA solicitud. Su favor no ocurrió el día
    de la cesión sino el sábado del pago, y la pantalla mostraba la fecha de la cesión.
    """

    def test_la_residual_muestra_el_sabado_del_pago_no_la_cesion(self):
        cesion = self.hoy + timedelta(days=10)
        sabado = cesion + timedelta(days=7)
        semana = sabado + timedelta(days=3)

        # `_favor` deja al solicitante como deudor: esa es la deuda principal.
        principal = self._favor(self.yo, self.otro, cesion, pagada_el=sabado)
        solicitud = principal.solicitud_origen
        DobladaDetalle.objects.create(
            solicitud=solicitud, fecha_pago=sabado,
            jornada_pago_sabado='AMBAS', fecha_pago_semana=semana)
        # Residual: el receptor queda debiendo media jornada, a devolver en semana.
        DeudaExplorador.objects.create(
            deudor=self.otro, acreedor=self.yo, solicitud_origen=solicitud,
            fecha_pago_pactada=semana, fecha_pago_real=semana,
            estado='pagada', jornada_cedida='AM')

        self.client.force_login(self.yo.user)
        r = self.client.get(URL)

        # Yo recibí el favor de la cesión; yo hice el favor del sábado.
        self.assertEqual([f['fecha_cubierta'] for f in r.context['recibidos']], [cesion])
        self.assertEqual([f['fecha_cubierta'] for f in r.context['hechos']], [sabado])

    def test_sin_detalle_la_residual_cae_a_la_fecha_de_cesion(self):
        """Sin `DobladaDetalle` no hay sábado que mostrar: no debe reventar."""
        cesion = self.hoy + timedelta(days=10)
        principal = self._favor(self.yo, self.otro, cesion, pagada_el=cesion + timedelta(days=7))
        DeudaExplorador.objects.create(
            deudor=self.otro, acreedor=self.yo, solicitud_origen=principal.solicitud_origen,
            fecha_pago_pactada=cesion + timedelta(days=10), estado='pendiente',
            jornada_cedida='AM')

        self.client.force_login(self.yo.user)
        r = self.client.get(URL)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['hechos'][0]['fecha_cubierta'], cesion)
