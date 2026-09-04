"""
El selector de compañeros de fin de semana pertenece a dos estrategias, no a las seis.

QUÉ SE ARREGLÓ
--------------
`disponibilidad_companero` y `etiqueta_companero` vivían en `SolicitudStrategy`, la base
de las SEIS estrategias, con la regla del INTERCAMBIO como comportamiento por defecto.

Dos consecuencias, y la segunda es un fallo de verdad:

  - D FDS, cuya regla es la de la CESIÓN, tenía que sobrescribir a su propia base. Quien
    leía la base no podía saber que ese "por defecto" era la regla de otro formulario.
  - El endpoint acepta `?tipo_solicitud_id=` de cualquier tipo. Pidiéndole los compañeros
    de un sábado con el id de DOBLADA, contestaba aplicando la regla del intercambio: una
    lista verosímil y sin sentido, sin error y sin aviso.

Ahora el contrato es `EstrategiaFinDeSemana`, lo implementan solo CAMBIO DESCANSO y
D FDS, y el endpoint comprueba antes de preguntar.
"""
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from empleados.models import Empleado, Jornada
from solicitudes.models import TipoSolicitudCambio
from solicitudes.services.solicitud_factory import SolicitudFactory
from solicitudes.services.strategies.base_strategy import SolicitudStrategy
from solicitudes.services.strategies.estrategia_fin_de_semana import EstrategiaFinDeSemana

TIPOS_DE_FINDE = {'CAMBIO DESCANSO', 'D FDS'}
TIPOS_SIN_FINDE = {'CAMBIO TURNO', 'DOBLADA', 'CT PERMANENTE', 'DOBLADA PERMANENTE'}


class ContratoDelSelectorTest(TestCase):
    """Quién puede contestar, y quién ya no."""

    def setUp(self):
        for nombre in TIPOS_DE_FINDE | TIPOS_SIN_FINDE:
            TipoSolicitudCambio.objects.get_or_create(
                nombre=nombre, defaults={'activo': True})

    def _strategy(self, nombre):
        return SolicitudFactory.get_strategy(TipoSolicitudCambio.objects.get(nombre=nombre))

    def test_solo_los_dos_formularios_de_finde_implementan_el_contrato(self):
        for nombre in TIPOS_DE_FINDE:
            with self.subTest(tipo=nombre):
                self.assertIsInstance(self._strategy(nombre), EstrategiaFinDeSemana)

        for nombre in TIPOS_SIN_FINDE:
            with self.subTest(tipo=nombre):
                self.assertNotIsInstance(self._strategy(nombre), EstrategiaFinDeSemana)

    def test_la_base_ya_no_responde_por_nadie(self):
        """
        La comprobación que impide que la regla vuelva a colarse ahí: mientras
        `SolicitudStrategy` tenga estos métodos, las cuatro estrategias que no son de finde
        contestan a una pregunta que no les corresponde.
        """
        self.assertFalse(hasattr(SolicitudStrategy, 'disponibilidad_companero'))
        self.assertFalse(hasattr(SolicitudStrategy, 'etiqueta_companero'))

    def test_cada_formulario_conserva_su_propia_regla(self):
        """
        No basta con que ambos implementen: tienen que implementar cosas DISTINTAS. Si el
        día de mañana alguien las unifica «para no repetir código», el intercambio y la
        cesión volverían a compartir criterio, que es justo de lo que se venía.
        """
        cd = type(self._strategy('CAMBIO DESCANSO')).disponibilidad_companero
        fds = type(self._strategy('D FDS')).disponibilidad_companero

        self.assertIsNot(cd, fds)
        self.assertIsNot(cd, EstrategiaFinDeSemana.disponibilidad_companero)
        self.assertIsNot(fds, EstrategiaFinDeSemana.disponibilidad_companero)


@override_settings(AXES_ENABLED=False)
class EndpointFinDeSemanaTest(TestCase):
    """El endpoint no contesta por un tipo que no sabe de findes."""

    URL = '/solicitudes/dfds-companeros/'

    def setUp(self):
        Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        u = User.objects.create_user('exp.finde', password='x')
        Empleado.objects.create(user=u, nombre='Exp', apellido='Finde',
                                cedula='9101', activo=True)
        self.client = Client()
        self.client.force_login(u)
        for nombre in ('D FDS', 'DOBLADA'):
            TipoSolicitudCambio.objects.get_or_create(
                nombre=nombre, defaults={'activo': True})
        # Un sábado cualquiera, futuro: la fecha solo tiene que ser de finde.
        from datetime import timedelta

        from django.utils import timezone
        d = timezone.localdate() + timedelta(days=7)
        while d.weekday() != 5:
            d += timedelta(days=1)
        self.sabado = d.strftime('%Y-%m-%d')

    def _pedir(self, tipo_nombre=None):
        params = {'fecha': self.sabado}
        if tipo_nombre:
            params['tipo_solicitud_id'] = str(
                TipoSolicitudCambio.objects.get(nombre=tipo_nombre).id)
        return self.client.get(self.URL, params, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

    def test_un_tipo_de_finde_contesta(self):
        """CONTROL: sin esto, el test de abajo pasaría aunque el endpoint estuviera roto."""
        r = self._pedir('D FDS')

        self.assertEqual(r.status_code, 200)
        self.assertIn('companeros', r.json())

    def test_un_tipo_que_no_es_de_finde_se_rechaza_en_vez_de_inventar(self):
        """
        Antes devolvía 200 con una lista calculada con la regla del intercambio. Un error
        explícito es mejor que una respuesta plausible: la lista mala nadie la habría
        mirado dos veces.
        """
        r = self._pedir('DOBLADA')

        self.assertEqual(r.status_code, 400)
        cuerpo = r.json()
        self.assertEqual(cuerpo['code'], 'tipo_sin_selector_finde')
        self.assertIn('DOBLADA', cuerpo['error'])
