"""
`DobladaStrategy.get_empleados_disponibles`: 206 líneas y solo 10 % cubierto.

Es el agujero de cobertura más grande de la clase, medido el 2026-08-20 al
empezar la Fase 3. Alimenta el desplegable de "¿quién te cubre?" del formulario
de doblada, así que un fallo aquí no lanza ningún error: simplemente ofrece a la
persona equivocada, o no ofrece a nadie.

Estos tests se escriben ANTES de tocar el método, para poder descomponerlo
después con red. Cubren las cinco ramas de decisión, que no son por tipo sino por
la combinación (día de la semana, festivo, jornada cedida, si el solicitante
descansa):

    sábado + sin alternancia definida   -> lista vacía
    sábado + jornada_cedida             -> el grupo que DESCANSA ese sábado
    sábado + sin jornada_cedida         -> el grupo que TRABAJA ese sábado
    entre semana + festivo              -> el grupo CONTRARIO al que dobla
    entre semana normal                 -> jornada contraria

`AsignacionEspecialService.grupo_trabaja` se dobla en los casos de sábado y
festivo: es una planificación anual que se carga a mano, y montarla entera en
cada test ataría estas pruebas a datos de calendario en vez de a la regla.
"""
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from solicitudes.services.errores_validacion import RequiereCambioTurnoPrevio
from solicitudes.services.strategies.doblada_strategy import DobladaStrategy

# Fechas fijas de 2026, elegidas por su día de la semana.
MIERCOLES = date(2026, 9, 2)
SABADO = date(2026, 9, 5)

GRUPO_TRABAJA = ('turnos.services.asignacion_especial_service'
                 '.AsignacionEspecialService.grupo_trabaja')
ES_FESTIVO_SEMANA = ('solicitudes.services.solicitud_validator'
                     '.SolicitudValidator.es_festivo_semana')


class EmpleadosDisponiblesTestCase(TestCase):

    def setUp(self):
        self.sala = crear_sala()
        self.am = crear_jornada('AM')
        self.pm = crear_jornada('PM')
        self.estrategia = DobladaStrategy()

        # Solicitante del grupo AM y un companero de cada grupo.
        self.solicitante = crear_empleado('Soli', 'AM', jornada=self.am, sala=self.sala)
        self.companero_am = crear_empleado('Comp', 'AM', jornada=self.am, sala=self.sala)
        self.companero_pm = crear_empleado('Comp', 'PM', jornada=self.pm, sala=self.sala)

    def _disponibles(self, fecha=MIERCOLES, **kwargs):
        return self.estrategia.get_empleados_disponibles(
            fecha.strftime('%Y-%m-%d'), self.solicitante, **kwargs)

    def _ids(self, resultado):
        return {e['id'] for e in resultado}


class TestSabado(EmpleadosDisponiblesTestCase):
    """
    En sábado manda la alternancia de fines de semana, no la jornada base del día.
    """

    def test_sin_alternancia_definida_no_ofrece_a_nadie(self):
        """
        Si nadie ha planificado quién trabaja ese sábado, la lista va vacía. Es un
        vacío LEGÍTIMO —"no hay a quién ofrecer"— distinto del que produciría un
        fallo, que este método propaga como excepción a propósito.
        """
        with patch(GRUPO_TRABAJA, return_value=None):
            assert self._disponibles(SABADO) == []

    def test_con_jornada_cedida_ofrece_el_grupo_que_DESCANSA(self):
        """
        Regla especial de los sábados: el grupo que TRABAJA hace la doblada, así que
        quien puede recibir la cesión es el que DESCANSA. Si trabajan los AM, los
        compañeros ofrecidos son PM — y da igual si se cede AM o PM.
        """
        with patch(GRUPO_TRABAJA, return_value='AM'):
            ids = self._ids(self._disponibles(SABADO, jornada_cedida='AM'))

        assert self.companero_pm.id in ids
        assert self.companero_am.id not in ids

    def test_con_jornada_cedida_el_grupo_ofrecido_no_depende_de_la_que_se_cede(self):
        """El control de la regla anterior: ceder PM ofrece los mismos que ceder AM."""
        with patch(GRUPO_TRABAJA, return_value='AM'):
            cediendo_am = self._ids(self._disponibles(SABADO, jornada_cedida='AM'))
            cediendo_pm = self._ids(self._disponibles(SABADO, jornada_cedida='PM'))

        assert cediendo_am == cediendo_pm

    def test_se_invierte_si_el_sabado_lo_trabaja_el_otro_grupo(self):
        with patch(GRUPO_TRABAJA, return_value='PM'):
            ids = self._ids(self._disponibles(SABADO, jornada_cedida='AM'))

        assert self.companero_am.id in ids
        assert self.companero_pm.id not in ids

    def test_nunca_se_ofrece_a_uno_mismo(self):
        with patch(GRUPO_TRABAJA, return_value='PM'):
            ids = self._ids(self._disponibles(SABADO, jornada_cedida='AM'))

        assert self.solicitante.id not in ids


class TestEntreSemana(EmpleadosDisponiblesTestCase):
    """Sin festivo de por medio: manda la jornada contraria."""

    def test_ofrece_la_jornada_contraria_a_la_del_solicitante(self):
        """El solicitante es AM, así que quien puede cubrirlo es PM."""
        with patch(ES_FESTIVO_SEMANA, return_value=False):
            ids = self._ids(self._disponibles(MIERCOLES))

        assert self.companero_pm.id in ids
        assert self.companero_am.id not in ids

    def test_nunca_se_ofrece_a_uno_mismo(self):
        with patch(ES_FESTIVO_SEMANA, return_value=False):
            assert self.solicitante.id not in self._ids(self._disponibles(MIERCOLES))

    def test_no_ofrece_empleados_inactivos(self):
        self.companero_pm.activo = False
        self.companero_pm.save()

        with patch(ES_FESTIVO_SEMANA, return_value=False):
            assert self.companero_pm.id not in self._ids(self._disponibles(MIERCOLES))

    def test_si_el_solicitante_descansa_puede_elegir_a_quien_trabaje(self):
        """
        Caso especial: quien descansa ese día no tiene jornada propia que ceder, así
        que la regla de "jornada contraria" no aplica y puede escoger a cualquiera
        que trabaje.
        """
        with patch(ES_FESTIVO_SEMANA, return_value=False):
            normal = self._ids(self._disponibles(MIERCOLES))
            descansando = self._ids(self._disponibles(MIERCOLES, solicitante_descansa=True))

        assert descansando >= normal, 'descansando no puede ofrecer MENOS opciones'


class TestFestivoEntreSemana(EmpleadosDisponiblesTestCase):
    """
    En un festivo de lunes a viernes un grupo dobla (AM+PM) y el otro descansa.
    Quien puede cubrir es el grupo CONTRARIO al que dobla, ceda lo que ceda.
    """

    def test_ofrece_el_grupo_contrario_al_que_dobla(self):
        with patch(ES_FESTIVO_SEMANA, return_value=True), \
             patch(GRUPO_TRABAJA, return_value='AM'):
            ids = self._ids(self._disponibles(MIERCOLES, jornada_cedida='AM'))

        assert self.companero_pm.id in ids
        assert self.companero_am.id not in ids

    def test_se_invierte_si_dobla_el_otro_grupo(self):
        with patch(ES_FESTIVO_SEMANA, return_value=True), \
             patch(GRUPO_TRABAJA, return_value='PM'):
            ids = self._ids(self._disponibles(MIERCOLES, jornada_cedida='AM'))

        assert self.companero_am.id in ids
        assert self.companero_pm.id not in ids

    def test_sin_grupo_planificado_cae_a_la_regla_normal(self):
        """
        Si el festivo no tiene alternancia cargada, `grupo_que_dobla` queda a None y
        la rama especial no aplica: se usa la regla de jornada contraria de siempre.
        """
        with patch(ES_FESTIVO_SEMANA, return_value=True), \
             patch(GRUPO_TRABAJA, return_value=None):
            ids = self._ids(self._disponibles(MIERCOLES))

        assert self.companero_pm.id in ids


class TestFormatoDeSalida(EmpleadosDisponiblesTestCase):

    def test_cada_empleado_trae_las_claves_que_espera_el_formulario(self):
        with patch(ES_FESTIVO_SEMANA, return_value=False):
            resultado = self._disponibles(MIERCOLES)

        assert resultado, 'el caso base debe ofrecer al menos un companero'
        assert set(resultado[0]) == {'id', 'nombre', 'apellido', 'jornada'}


class TestUnFalloNoSeDisfrazaDeListaVacia(EmpleadosDisponiblesTestCase):
    """
    El metodo propaga las excepciones a proposito, y conviene que siga haciendolo.

    La lista vacia YA SIGNIFICA otra cosa: "ese dia no hay ningun companero que
    cumpla las condiciones". Devolver lo mismo ante un bug hacia que el
    desplegable saliera vacio y la persona concluyera "hoy no hay nadie", sin
    ninguna señal de que el codigo habia reventado.
    """

    def test_propaga_en_vez_de_devolver_lista_vacia(self):
        with patch(ES_FESTIVO_SEMANA, side_effect=RuntimeError('fallo simulado')):
            with self.assertRaises(RuntimeError):
                self._disponibles(MIERCOLES)

    def test_una_fecha_ilegible_tambien_propaga(self):
        with self.assertRaises((ValueError, TypeError)):
            self.estrategia.get_empleados_disponibles('no-es-fecha', self.solicitante)


class TestContratoJsonConElFrontend(TestCase):
    """
    Las claves del JSON de `requiere_cambio_turno_previo`, que lee el formulario.

    No es celo excesivo: durante la Fase 3, un reemplazo automatico de variables
    por `entrada.x` alcanzo tambien a los literales de cadena y renombro la clave
    'fecha_pago' en las DOS respuestas que la llevan.
    `solicitar_doblada.js:2913` lee `data.fecha_pago || fechaPagoInput.value`, asi
    que el `||` tapaba la averia: mostraba la fecha del formulario en vez de la que
    devuelve el servidor. Paso el CI sin que saltara nada, porque ningun test
    miraba esas claves.

    ESTOS TESTS MEJORARON al desaparecer el JSON-dentro-del-mensaje. Antes tenian
    que inspeccionar el CODIGO FUENTE contando apariciones literales, porque la
    forma del diccionario estaba escrita tres veces y no habia ningun objeto que
    interrogar. Ahora la define `RequiereCambioTurnoPrevio` en un solo sitio, asi
    que se comprueba el comportamiento real.
    """

    CLAVES = {'success', 'code', 'message', 'fecha_pago', 'jornada_comun'}

    def _error(self):
        return RequiereCambioTurnoPrevio(
            'Necesitas un cambio de turno previo.',
            fecha_pago=date(2026, 2, 14),
            jornada_comun='AM',
        )

    def test_el_payload_lleva_exactamente_las_claves_que_lee_el_formulario(self):
        payload = self._error().como_payload()

        self.assertEqual(set(payload), self.CLAVES)
        self.assertEqual(payload['code'], 'requiere_cambio_turno_previo')
        self.assertFalse(payload['success'])

    def test_la_fecha_de_pago_viaja_como_texto(self):
        """
        La clave concreta que se rompio. El frontend la mete en un input, asi que
        un `date` serializado de otra forma —o ausente— vuelve a activar el
        respaldo silencioso del `||`.
        """
        payload = self._error().como_payload()

        self.assertEqual(payload['fecha_pago'], '2026-02-14')
        self.assertIsInstance(payload['fecha_pago'], str)

    def test_sigue_siendo_utilizable_como_mensaje_de_texto(self):
        """
        Hereda de `str` a proposito: el mensaje pasa por sitios que lo concatenan,
        lo registran en el log o inspeccionan su contenido. Si dejara de ser texto,
        esos sitios romperian sin que nada mas lo avisara.
        """
        error = self._error()

        self.assertIsInstance(error, str)
        self.assertEqual(str(error), 'Necesitas un cambio de turno previo.')
        self.assertEqual(f'Ana Perez: {error}',
                         'Ana Perez: Necesitas un cambio de turno previo.')

    def test_la_estrategia_ya_no_construye_el_json_a_mano(self):
        """
        Guarda contra la vuelta atras: si alguien vuelve a escribir las claves
        dentro de la estrategia, la forma queda otra vez duplicada y sin un sitio
        unico que proteger.
        """
        import inspect

        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy

        fuente = inspect.getsource(DobladaStrategy)

        self.assertNotIn("'code': 'requiere_cambio_turno_previo'", fuente)
        self.assertNotIn("json.dumps", fuente)

    def test_ninguna_clave_quedo_prefijada_por_el_refactor(self):
        """Control directo del fallo concreto: nada de 'entrada.' dentro de un literal."""
        import inspect

        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy

        fuente = inspect.getsource(DobladaStrategy)

        assert "'entrada." not in fuente
        assert '"entrada.' not in fuente
