"""
Red de caracterización de `SolicitudRequestParser`, previa a la Fase 2.

`solicitud_request_parser.py` contiene DOS cadenas `if tipo_nombre == ...`
—`validate_required` y `parse_datos`— que van a moverse a las strategies.

El estado de partida (medido el 2026-08-20): 52 % de cobertura. `test_request_parser.py`
cubre `validate_required` para CT, DOBLADA, D FDS y CT PERMANENTE, pero **no**
CAMBIO DESCANSO ni DOBLADA PERMANENTE, y **`parse_datos` no estaba cubierto en
absoluto**: justo la cadena más delicada, porque es la que decide qué claves
recibe cada strategy.

Aquí la caracterización puede ser EXACTA —no solo la forma, como en `detalle.py`—
porque `parse_datos` es prácticamente una función pura: transforma el POST en un
diccionario y no escribe nada. Se comparan los diccionarios completos. Si el
traslado pierde una clave o cambia un valor por defecto, la comparación lo dice.

Se cubren las seis ramas de cada cadena, incluida la `else` (CT y tipos genéricos).
"""
from django.http import QueryDict
from django.test import TestCase
from django.utils import timezone

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from solicitudes.services.solicitud_request_parser import SolicitudRequestParser as P


def post(**campos):
    """QueryDict a partir de pares simples; una lista se expande con appendlist."""
    q = QueryDict(mutable=True)
    for clave, valor in campos.items():
        if isinstance(valor, list):
            for v in valor:
                q.appendlist(clave, v)
        else:
            q[clave] = valor
    return q


class ParserTestCase(TestCase):
    def setUp(self):
        sala = crear_sala()
        jornada = crear_jornada('AM')
        self.solicitante = crear_empleado('Soli', 'Citante', jornada=jornada, sala=sala)
        self.receptor = crear_empleado('Recep', 'Tor', jornada=jornada, sala=sala)

    def _parse(self, tipo, **campos):
        return P.parse_datos(tipo, post(**campos), self.solicitante, self.receptor)


class TestValidateRequiredRamasSinCubrir(ParserTestCase):
    """
    Las dos ramas que `test_request_parser.py` no tocaba. Sin esto, moverlas a su
    strategy sería a ciegas.
    """

    CD_COMPLETO = dict(fecha_solicitud='2026-09-05', empleado_receptor='1',
                       fecha_pago='2026-09-13')

    def test_cambio_descanso_completo_pasa(self):
        ok, msg = P.validate_required('CAMBIO DESCANSO', post(**self.CD_COMPLETO))

        assert ok is True, msg

    def test_cambio_descanso_sin_finde_que_cambia(self):
        campos = {**self.CD_COMPLETO}
        del campos['fecha_solicitud']

        ok, msg = P.validate_required('CAMBIO DESCANSO', post(**campos))

        assert ok is False
        assert 'fin de semana que cambias' in msg

    def test_cambio_descanso_sin_receptor(self):
        campos = {**self.CD_COMPLETO}
        del campos['empleado_receptor']

        ok, msg = P.validate_required('CAMBIO DESCANSO', post(**campos))

        assert ok is False
        assert 'compañero' in msg

    def test_cambio_descanso_sin_devolucion(self):
        campos = {**self.CD_COMPLETO}
        del campos['fecha_pago']

        ok, msg = P.validate_required('CAMBIO DESCANSO', post(**campos))

        assert ok is False
        assert 'devolución' in msg

    DP_COMPLETO = dict(fecha_inicio='2026-09-01', fecha_fin='2026-09-30',
                       cesion_companero=['3'], devolucion_companero=['3'])

    def test_doblada_permanente_completa_pasa(self):
        ok, msg = P.validate_required('DOBLADA PERMANENTE', post(**self.DP_COMPLETO))

        assert ok is True, msg

    def test_doblada_permanente_sin_rango(self):
        campos = {**self.DP_COMPLETO}
        del campos['fecha_fin']

        ok, msg = P.validate_required('DOBLADA PERMANENTE', post(**campos))

        assert ok is False
        assert 'rango de fechas' in msg

    def test_doblada_permanente_sin_dias_de_cesion(self):
        """`cesion_companero` es una lista: se valida con getlist, no con get."""
        campos = {**self.DP_COMPLETO}
        del campos['cesion_companero']

        ok, msg = P.validate_required('DOBLADA PERMANENTE', post(**campos))

        assert ok is False
        assert 'cesión' in msg

    def test_doblada_permanente_sin_dias_de_devolucion(self):
        campos = {**self.DP_COMPLETO}
        del campos['devolucion_companero']

        ok, msg = P.validate_required('DOBLADA PERMANENTE', post(**campos))

        assert ok is False
        assert 'devolución' in msg


class TestParseDatosPorTipo(ParserTestCase):
    """
    La cadena que no estaba cubierta en absoluto. Se compara el diccionario
    COMPLETO: es lo que recibe la strategy, así que una clave perdida al mover
    equivale a un dato que deja de llegar.
    """

    def test_ct_permanente(self):
        datos = self._parse('CT PERMANENTE',
                            fecha_inicio='2026-09-01', fecha_fin='2026-09-30',
                            dias_seleccionados='{"0": "AM"}', comentarios='hola')

        assert datos == {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'comentario': 'hola',
            'fecha_cambio_turno': '2026-09-01',
            'fecha_inicio': '2026-09-01',
            'fecha_fin': '2026-09-30',
            'dias_seleccionados': {'0': 'AM'},
        }

    def test_ct_permanente_con_dias_seleccionados_ilegibles(self):
        """JSON corrupto no revienta: cae a diccionario vacío."""
        datos = self._parse('CT PERMANENTE', fecha_inicio='2026-09-01',
                            fecha_fin='2026-09-30', dias_seleccionados='{no es json')

        assert datos['dias_seleccionados'] == {}

    def test_doblada(self):
        datos = self._parse('DOBLADA', fecha_solicitud='2026-09-02',
                            fecha_pago='2026-09-09', jornada_cedida='AM',
                            comentarios='c')

        assert datos == {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'comentario': 'c',
            'fecha_cambio_turno': '2026-09-02',
            'fecha_pago': '2026-09-09',
            'jornada_cedida': 'AM',
            'jornada_pago_sabado': None,
            'jornada_cubre_en_pago': None,
            'fecha_pago_semana': None,
            'tipo_cesion': 'cesion_completa',
            'es_intercambio': False,
            'fecha_creacion_solicitud': timezone.localdate(),
        }

    def test_doblada_marca_el_intercambio_con_varios_formatos(self):
        """El formulario puede mandar '1', 'true', 'True' u 'on'."""
        for valor in ('1', 'true', 'True', 'on'):
            with self.subTest(valor=valor):
                datos = self._parse('DOBLADA', fecha_solicitud='2026-09-02',
                                    jornada_cedida='AM', intercambio_doblada=valor)
                assert datos['es_intercambio'] is True

    def test_doblada_no_marca_el_intercambio_con_otros_valores(self):
        for valor in ('', '0', 'false', 'no'):
            with self.subTest(valor=valor):
                datos = self._parse('DOBLADA', fecha_solicitud='2026-09-02',
                                    jornada_cedida='AM', intercambio_doblada=valor)
                assert datos['es_intercambio'] is False

    def test_doblada_infiere_la_jornada_cedida_si_no_viene(self):
        """
        Cesión desde jornada simple: el formulario no manda `jornada_cedida` y el
        parser la deduce de la jornada del solicitante en esa fecha.
        """
        datos = self._parse('DOBLADA', fecha_solicitud='2026-09-02')

        assert datos['jornada_cedida'] == 'AM'

    def test_d_fds_y_cambio_descanso_comparten_forma(self):
        """
        Hoy los atiende la MISMA rama (`elif tipo_nombre in ("D FDS", "CAMBIO
        DESCANSO")`). Al separarlos en dos strategies, los dos diccionarios deben
        seguir siendo idénticos salvo por lo que el tipo aporte.
        """
        comunes = dict(fecha_solicitud='2026-09-05', fecha_pago='2026-09-13',
                       tipo_cesion='cesion_completa', jornada_cedida='AM')

        esperado = {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'comentario': '',
            'fecha_cambio_turno': '2026-09-05',
            'fecha_pago': '2026-09-13',
            'submodalidad_semana': None,
            'tipo_cesion': 'cesion_completa',
            'jornada_cedida': 'AM',
            'jornada_cubre_en_pago': None,
            'fecha_creacion_solicitud': timezone.localdate(),
        }

        assert self._parse('D FDS', **comunes) == esperado
        assert self._parse('CAMBIO DESCANSO', **comunes) == esperado

    def test_cambio_descanso_arrastra_la_submodalidad(self):
        datos = self._parse('CAMBIO DESCANSO', fecha_solicitud='2026-09-02',
                            submodalidad_semana='jornadas_partidas')

        assert datos['submodalidad_semana'] == 'jornadas_partidas'

    def test_doblada_permanente_con_listas(self):
        datos = self._parse('DOBLADA PERMANENTE',
                            fecha_inicio='2026-09-01', fecha_fin='2026-09-30',
                            dias_cesion=['0', '1'], dias_devolucion=['3'])

        assert datos == {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'comentario': '',
            'fecha_inicio': '2026-09-01',
            'fecha_fin': '2026-09-30',
            'dias_cesion': ['0', '1'],
            'dias_devolucion': ['3'],
            'fecha_creacion_solicitud': timezone.localdate(),
        }

    def test_los_dias_separados_por_comas_NO_se_parten(self):
        """
        Caracteriza un comportamiento que SORPRENDE, y por eso queda fijado aquí.

        El código tiene un fallback aparente para el formato antiguo (un solo campo
        con '0,1,2' en vez de varios valores):

            dias_cesion = (post.getlist('dias_cesion')
                           or [d for d in post.get('dias_cesion', '').split(',') ...])

        Con un QueryDict real ese fallback NO SE EJECUTA NUNCA: `getlist` devuelve
        ['0,1'], que es una lista no vacía y por tanto verdadera, así que el `or`
        nunca llega a partir por comas. La rama solo correría si el campo faltara
        del todo, y entonces no habría nada que partir.

        No se corrige aquí: cambiarlo alteraría el comportamiento, y esta tanda es
        de refactor sin cambio de conducta. Queda anotado para decidirlo aparte.
        """
        datos = self._parse('DOBLADA PERMANENTE',
                            fecha_inicio='2026-09-01', fecha_fin='2026-09-30',
                            dias_cesion='0,1', dias_devolucion='3')

        assert datos['dias_cesion'] == ['0,1']
        assert datos['dias_devolucion'] == ['3']

    def test_ct_y_tipos_genericos(self):
        """La rama `else`, que atiende a CAMBIO TURNO y a cualquier tipo nuevo."""
        esperado = {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'comentario': 'x',
            'fecha_cambio_turno': '2026-09-02',
        }

        assert self._parse('CAMBIO TURNO', fecha_solicitud='2026-09-02',
                           comentarios='x') == esperado
        assert self._parse('TIPO QUE NO EXISTE', fecha_solicitud='2026-09-02',
                           comentarios='x') == esperado

    def test_sin_comentarios_queda_cadena_vacia(self):
        assert self._parse('CAMBIO TURNO', fecha_solicitud='2026-09-02')['comentario'] == ''
