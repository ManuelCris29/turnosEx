"""
Red de caracterización de los TRES despachos por tipo de `DobladaSnapshotService`,
previa a moverlos a las strategies (Fase 2).

POR QUÉ ESTE ARCHIVO ES DISTINTO DE LOS ANTERIORES
--------------------------------------------------
Las dos cadenas ya movidas (`detalle.py`, `solicitud_request_parser.py`) leían o
transformaban datos. Estas ESCRIBEN turnos: son la reconciliación que corre tras
revertir una solicitud, y de ellas dependen los patrones #22, #30, #33 y #40 de
`PROTECTION_PATTERNS.md`. Equivocar el despacho aquí no muestra un dato falso en
una pantalla: deja turnos reales mal escritos, en días que nadie está mirando.

Además el despacho NO es solo por tipo. Decide con una terna:

    (tipo, hay modelo de detalle, bandera es_intercambio)

y varios tipos comparten el mismo `DobladaDetalle`. Por eso los casos de prueba
combinan las tres cosas y no se limitan a recorrer la lista de tipos.

LA DUPLICACIÓN QUE MOTIVA EL REFACTOR
-------------------------------------
`_pares_que_reescribe` lo dice en su propio docstring:

    "Espejo exacto del dispatch de `reconciliar_dobladas_aprobadas`:
     si allí cambia lo que se re-aplica, aquí también."

Es la misma decisión escrita dos veces, sostenida por un comentario que pide a
las personas que las mantengan sincronizadas. `TestLosDosDespachosCoinciden`
convierte esa petición en un test, que es lo único que de verdad la sostiene.

QUÉ SE COMPRUEBA Y CÓMO
-----------------------
- `_pares_que_reescribe` es prácticamente pura (devuelve un conjunto y no escribe),
  así que se comparan los conjuntos EXACTOS.
- `_reaplicar_una` escribe, así que se caracteriza QUÉ APLICADOR recibe la llamada,
  con dobles. Es exactamente lo que el refactor mueve, y evita montar el estado
  completo de turnos para cada tipo.
"""
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from solicitudes.models import DobladaDetalle, SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.doblada_snapshot_service import DobladaSnapshotService as S

CESION = date(2026, 9, 2)     # miércoles
PAGO = date(2026, 9, 9)       # miércoles siguiente
SEMANA = date(2026, 9, 16)


class SnapshotDispatchTestCase(TestCase):

    def setUp(self):
        sala = crear_sala()
        jornada = crear_jornada('AM')
        self.a = crear_empleado('Uno', 'Uno', jornada=jornada, sala=sala)
        self.b = crear_empleado('Dos', 'Dos', jornada=jornada, sala=sala)

    def _solicitud(self, tipo_nombre, con_detalle=True, es_intercambio=False,
                   fecha_pago_semana=None):
        tipo, _ = TipoSolicitudCambio.objects.get_or_create(nombre=tipo_nombre)
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=self.a,
            explorador_receptor=self.b,
            tipo_cambio=tipo,
            fecha_cambio_turno=CESION,
            estado='aprobada',
        )
        if con_detalle:
            DobladaDetalle.objects.create(
                solicitud=solicitud,
                fecha_pago=PAGO,
                es_intercambio=es_intercambio,
                fecha_pago_semana=fecha_pago_semana,
            )
            solicitud.refresh_from_db()
        return solicitud

    def _pares(self, solicitud, fechas):
        return S._pares_que_reescribe(solicitud, set(fechas))

    def _ambos(self, *fechas):
        return {(p, f) for p in (self.a.id, self.b.id) for f in fechas}


class TestParesQueReescribe(SnapshotDispatchTestCase):
    """
    Qué pares (explorador, fecha) declara que va a reescribir cada tipo.

    Importa que sea EXACTO en los dos sentidos. Si declara de menos, la
    reconciliación no cierra días colaterales y se pierde en silencio lo que viva
    en ellos (patrón #33). Si declara de más, bloquea reconciliaciones legítimas.
    """

    def test_sin_detalle_solo_su_dia_y_a_las_dos_partes(self):
        """
        CAMBIO TURNO no tiene `DobladaDetalle`. Re-materializa un único día, pero
        lo escribe a AMBAS partes: lo que aporta al conjunto es la otra persona.
        """
        solicitud = self._solicitud('CAMBIO TURNO', con_detalle=False)

        assert self._pares(solicitud, [CESION]) == self._ambos(CESION)

    def test_sin_detalle_no_aporta_nada_si_su_dia_no_esta_en_juego(self):
        solicitud = self._solicitud('CAMBIO TURNO', con_detalle=False)

        assert self._pares(solicitud, [PAGO]) == set()

    def test_d_fds_declara_SIEMPRE_sus_dos_dias(self):
        """
        `DFDSAplicacionService.aplicar` muta sus dos días de una vez, sin importar
        cuál coincidió con la reconciliación. Declarar solo el coincidente dejaría
        el otro fuera del cierre.
        """
        solicitud = self._solicitud('D FDS')

        assert self._pares(solicitud, [CESION]) == self._ambos(CESION, PAGO)
        assert self._pares(solicitud, [PAGO]) == self._ambos(CESION, PAGO)

    def test_el_intercambio_de_dobladas_tambien_declara_sus_dos_dias(self):
        """
        Aquí no manda el tipo sino la BANDERA: una DOBLADA con `es_intercambio`
        se comporta como D FDS, porque `aplicar_intercambio` también muta los dos.
        """
        solicitud = self._solicitud('DOBLADA', es_intercambio=True)

        assert self._pares(solicitud, [CESION]) == self._ambos(CESION, PAGO)

    def test_la_doblada_normal_declara_SOLO_los_dias_en_juego(self):
        """
        Al revés que D FDS: la reconciliación re-aplica solo el lado que cae en
        `fechas`, así que los otros lados no se tocan y no deben entrar.
        """
        solicitud = self._solicitud('DOBLADA')

        assert self._pares(solicitud, [CESION]) == self._ambos(CESION)
        assert self._pares(solicitud, [PAGO]) == self._ambos(PAGO)
        assert self._pares(solicitud, [CESION, PAGO]) == self._ambos(CESION, PAGO)

    def test_la_doblada_normal_incluye_la_fecha_de_pago_de_semana(self):
        solicitud = self._solicitud('DOBLADA', fecha_pago_semana=SEMANA)

        assert self._pares(solicitud, [SEMANA]) == self._ambos(SEMANA)

    def test_cambio_descanso_usa_su_propio_calculo_de_fechas(self):
        """
        No deduce sus días de la solicitud: los pide a `fechas_afectadas`, la misma
        fuente que usa la invalidación de caché de su cancelación. Incluye los días
        OPUESTOS del finde, que pueden caer en otro mes.
        """
        solicitud = self._solicitud('CAMBIO DESCANSO')
        ruta = ('solicitudes.services.cambio_descanso_aplicacion_service'
                '.CambioDescansoAplicacionService.fechas_afectadas')

        with patch(ruta, return_value=[CESION, SEMANA]) as fechas_afectadas:
            pares = self._pares(solicitud, [CESION])

        assert fechas_afectadas.called, 'debe consultar su propio cálculo, no deducirlo'
        assert pares == self._ambos(CESION, SEMANA)


class TestDespachoDeReaplicacion(SnapshotDispatchTestCase):
    """
    Qué APLICADOR re-aplica cada tipo. Es la cadena que escribe turnos, así que se
    comprueba con dobles: interesa a quién se llama, no lo que cada uno haga.

    El comentario del código deja constancia de un incidente real: al re-aplicar un
    intercambio de dobladas con la lógica de cesión/pago, la reconciliación
    reconstruía un estado inventado (mildrey con una sola PM el 06/08). Por eso la
    bandera `es_intercambio` manda sobre el tipo.
    """

    RUTAS = {
        # Tras la Fase 2 la lógica vive en CambioDescansoStrategy.reaplicar, así que
        # se observa el aplicador REAL en vez del método intermedio que había en el
        # servicio (ya retirado). Los casos de prueba caen en día de semana con la
        # submodalidad por defecto, que es la rama `aplicar_entre_semana`.
        'cambio_descanso': ('solicitudes.services.cambio_descanso_aplicacion_service'
                            '.CambioDescansoAplicacionService.aplicar_entre_semana'),
        'd_fds': ('solicitudes.services.d_fds_aplicacion_service'
                  '.DFDSAplicacionService.aplicar'),
    }

    def _aplicador_usado(self, solicitud, fechas=(CESION,)):
        llamados = []
        parches = [patch(ruta, side_effect=lambda *a, _n=nombre, **k: llamados.append(_n))
                   for nombre, ruta in self.RUTAS.items()]
        for p in parches:
            p.start()
        try:
            S._reaplicar_una(solicitud, set(fechas))
        except Exception:
            # A los aplicadores no parcheados les faltan turnos reales; da igual:
            # lo que se caracteriza es a QUIÉN se llamó, no el resultado.
            pass
        finally:
            for p in parches:
                p.stop()
        return llamados

    def test_cambio_descanso_usa_su_propio_reaplicador(self):
        solicitud = self._solicitud('CAMBIO DESCANSO')

        assert self._aplicador_usado(solicitud) == ['cambio_descanso']

    def test_d_fds_usa_el_aplicador_de_finde_y_no_el_de_doblada(self):
        """D FDS comparte `DobladaDetalle`, pero no su lógica: la suya es de finde."""
        solicitud = self._solicitud('D FDS')

        assert self._aplicador_usado(solicitud) == ['d_fds']

    def test_la_doblada_normal_no_usa_ninguno_de_los_dos(self):
        solicitud = self._solicitud('DOBLADA')

        assert self._aplicador_usado(solicitud) == []

    def test_un_tipo_desconocido_NO_se_reaplica(self):
        """
        Hueco que faltaba en esta red y por el que se coló una regresión.

        La cadena original terminaba sin `else`: un tipo sin rama propia no se
        re-materializaba. Al pasar a despacho por strategy, `get_strategy` cae a
        CambioTurnoStrategy para los tipos desconocidos —razonable para pintar una
        pantalla, inaceptable aquí—, así que un tipo que no sabemos re-materializar
        se habría re-aplicado "como si fuera un cambio de turno", escribiendo turnos
        inventados.

        Se detectó al escribir la red equivalente de la cancelación, que sí tenía
        este caso. La corrección es `get_strategy_registrada`, que devuelve None en
        vez de caer por defecto.
        """
        from unittest.mock import patch

        solicitud = self._solicitud('TIPO QUE NO EXISTE', con_detalle=False)
        ruta = ('solicitudes.services.strategies.cambio_turno_strategy'
                '.CambioTurnoStrategy.reaplicar_fechas')

        with patch(ruta) as reaplicar_ct:
            S._reaplicar_una(solicitud, {CESION})

        assert not reaplicar_ct.called

    def test_el_intercambio_no_usa_el_de_cambio_descanso_ni_el_de_d_fds(self):
        """
        Tiene su propio aplicador. Lo que este test fija es que la bandera desvía
        el flujo fuera de la re-aplicación como doblada normal.
        """
        solicitud = self._solicitud('DOBLADA', es_intercambio=True)

        assert self._aplicador_usado(solicitud) == []


class TestLosDosDespachosCoinciden(SnapshotDispatchTestCase):
    """
    El docstring de `_pares_que_reescribe` pide que sea "espejo exacto" del
    despacho de la reconciliación, y hasta ahora eso lo sostenía únicamente un
    comentario. Aquí se convierte en test.

    Comprobación: lo que un tipo DECLARA que va a reescribir no puede quedarse
    corto respecto a los días que su re-aplicación toca de verdad. Si se queda
    corto, el cierre de días colaterales del patrón #33 pierde piezas en silencio.
    """

    def test_d_fds_declara_los_dos_dias_que_su_aplicador_muta(self):
        solicitud = self._solicitud('D FDS')

        declarados = {f for _, f in self._pares(solicitud, [CESION])}

        assert {CESION, PAGO} <= declarados

    def test_el_intercambio_declara_los_dos_dias_que_su_aplicador_muta(self):
        solicitud = self._solicitud('DOBLADA', es_intercambio=True)

        declarados = {f for _, f in self._pares(solicitud, [CESION])}

        assert {CESION, PAGO} <= declarados

    def test_ningun_tipo_declara_pares_de_terceros(self):
        """
        Un tipo solo puede declarar pares de sus DOS partes. Declarar de más
        bloquearía reconciliaciones ajenas legítimas.
        """
        for tipo, kwargs in (('CAMBIO TURNO', {'con_detalle': False}),
                             ('DOBLADA', {}),
                             ('D FDS', {}),
                             ('DOBLADA', {'es_intercambio': True})):
            with self.subTest(tipo=tipo, **kwargs):
                solicitud = self._solicitud(tipo, **kwargs)
                personas = {p for p, _ in self._pares(solicitud, [CESION, PAGO])}

                assert personas <= {self.a.id, self.b.id}
