"""
`solicitudes/services/fechas_helper.py`: estaba al 0 % de cobertura.

No es código muerto —lo llama la rama de CAMBIO TURNO de `views/detalle.py:429`—,
pero ninguno de los 991 tests de la suite lo pisaba. Alimenta el análisis de fecha
que ve el supervisor en el detalle de una solicitud: si dice que un día es válido
cuando no lo es, se aprueba sobre información falsa.

Lo que estos tests fijan es la MATRIZ POR TIPO, que es la parte con reglas de
negocio de verdad: qué motivo de exclusión invalida qué tipo de solicitud.

    motivo          CT          CT PERMANENTE   DOBLADA / D FDS
    Festivo         INVALIDA    INVALIDA        permitido
    Mantenimiento   INVALIDA    INVALIDA        INVALIDA
    Temporada       INVALIDA    INVALIDA        INVALIDA
    Domingo         INVALIDA    INVALIDA        permitido
    Sábado          INVALIDA    INVALIDA        permitido

Las dos primeras columnas coinciden hoy, y no es casualidad: un cambio de turno
—sencillo o permanente— intercambia AM por PM, y todos esos días o no tienen dos
jornadas que intercambiar o están cerrados. La DOBLADA es otra cosa: no
intercambia, cubre el turno de otro, y por eso admite festivos y fines de semana.

Nota: el módulo envuelve cada comprobación en `except Exception` + warning, así que
ante un fallo de base de datos informa "no es festivo / no es mantenimiento" en vez
de fallar. Es un *fail-open* como los del patrón #25, pero aquí solo alimenta una
pantalla de CONSULTA y no escribe nada, así que se deja documentado y no se cambia.
"""
from datetime import date

from django.test import TestCase

from core.tests.factories import crear_empleado, crear_jornada, crear_par_contrario
from solicitudes.services.fechas_helper import (
    analizar_fecha_solicitud,
    obtener_informacion_fecha_para_detalle,
)
from turnos.models import DiaEspecial

# Fechas fijas de 2026 elegidas por su día de la semana, para que los tests no
# dependan de cuándo se ejecutan.
MIERCOLES = date(2026, 9, 2)
SABADO = date(2026, 9, 5)
DOMINGO = date(2026, 9, 6)


class FechasHelperTestCase(TestCase):
    def setUp(self):
        self.solicitante, self.receptor, self.sala = crear_par_contrario()

    def _analizar(self, fecha=MIERCOLES, tipo='CT', con_empleados=True):
        return analizar_fecha_solicitud(
            fecha,
            solicitante=self.solicitante if con_empleados else None,
            receptor=self.receptor if con_empleados else None,
            tipo_solicitud=tipo,
        )


class TestDiasEspeciales(FechasHelperTestCase):

    def test_festivo_se_detecta_y_se_lista(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='festivo', activo=True)

        r = self._analizar()

        assert r['es_festivo'] is True
        assert 'Festivo' in r['razones_exclusion']

    def test_festivo_inactivo_no_cuenta(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='festivo', activo=False)

        assert self._analizar()['es_festivo'] is False

    def test_mantenimiento_se_detecta(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='mantenimiento', activo=True)

        r = self._analizar()

        assert r['es_mantenimiento'] is True
        assert 'Mantenimiento' in r['razones_exclusion']

    def test_la_temporada_manda_sobre_el_mantenimiento(self):
        """
        Regla de negocio del proyecto: un día marcado como mantenimiento que cae en
        temporada NO se considera mantenimiento. Aquí se comprueba a través del
        helper, que delega en `DiaEspecial.es_mantenimiento_efectivo`.
        """
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='mantenimiento', activo=True)
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='temporada',
                                   es_temporada=True, activo=True)

        r = self._analizar()

        assert r['es_mantenimiento'] is False
        assert r['es_temporada'] is True
        assert 'Mantenimiento' not in r['razones_exclusion']
        assert 'Temporada' in r['razones_exclusion']

    def test_dia_normal_no_marca_nada(self):
        r = self._analizar()

        assert r['razones_exclusion'] == []
        assert r['valida'] is True


class TestDiaDeLaSemana(FechasHelperTestCase):

    def test_domingo_excluye_en_ct(self):
        r = self._analizar(DOMINGO, tipo='CT')

        assert r['es_domingo'] is True
        assert 'Domingo' in r['razones_exclusion']
        assert r['valida'] is False

    def test_domingo_no_excluye_en_doblada(self):
        """Una DOBLADA sí puede caer en domingo: se cubre el turno de otro."""
        r = self._analizar(DOMINGO, tipo='DOBLADA')

        assert r['es_domingo'] is True
        assert r['valida'] is True

    def test_el_sabado_excluye_en_los_dos_tipos_de_cambio_de_turno(self):
        """
        `cambio_turno_strategy.py:179` llama a `validar_no_sabado_ct_sencillo()` en
        TODO cambio de turno, no solo en el permanente. Antes esta pantalla solo
        marcaba el sábado para CT PERMANENTE.
        """
        assert 'Sábado' in self._analizar(SABADO, tipo='CT')['razones_exclusion']
        assert 'Sábado' in self._analizar(SABADO, tipo='CT PERMANENTE')['razones_exclusion']

    def test_el_sabado_no_excluye_en_doblada(self):
        """Una DOBLADA sí puede caer en sábado: se cubre el turno de otro."""
        assert self._analizar(SABADO, tipo='DOBLADA')['valida'] is True

    def test_un_miercoles_no_es_ni_sabado_ni_domingo(self):
        r = self._analizar(MIERCOLES)

        assert r['es_sabado'] is False
        assert r['es_domingo'] is False


class TestMatrizDeValidezPorTipo(FechasHelperTestCase):
    """
    La parte con verdadera regla de negocio: el MISMO motivo de exclusión
    invalida unos tipos y otros no.
    """

    def test_el_festivo_invalida_los_dos_tipos_de_cambio_de_turno(self):
        """
        Los festivos NO se cambian con un CT: se cambian con una DOBLADA, festivo
        por festivo. En festivo una jornada trabaja el día completo (AM+PM) por
        rotación, así que no hay un AM y un PM que intercambiar.

        Es la regla que aplica `cambio_turno_strategy.py:185`. Hasta el 2026-08-20
        esta pantalla decía lo contrario y marcaba la fecha como válida.
        """
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='festivo', activo=True)

        assert self._analizar(tipo='CT')['valida'] is False
        assert self._analizar(tipo='CT PERMANENTE')['valida'] is False

    def test_festivo_se_permite_en_doblada(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='festivo', activo=True)

        assert self._analizar(tipo='DOBLADA')['valida'] is True
        assert self._analizar(tipo='D FDS')['valida'] is True

    def test_el_mantenimiento_invalida_todos_los_tipos(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='mantenimiento', activo=True)

        for tipo in ('CT', 'CT PERMANENTE', 'DOBLADA', 'D FDS', 'CAMBIO DESCANSO'):
            assert self._analizar(tipo=tipo)['valida'] is False, tipo

    def test_el_festivo_entre_semana_invalida_el_cambio_descanso(self):
        """
        Un festivo de lunes a viernes tiene su PROPIA alternancia: un grupo dobla
        (AM+PM) y el otro descansa. Ese descanso no es el de la rotación ordinaria,
        así que no se puede intercambiar.
        """
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='festivo', activo=True)

        assert self._analizar(MIERCOLES, tipo='CAMBIO DESCANSO')['valida'] is False

    def test_el_festivo_en_fin_de_semana_SI_permite_el_cambio_descanso(self):
        """
        El matiz que hace la regla no trivial: un festivo que cae en sábado o domingo
        SIGUE SIENDO fin de semana. Ahí manda la alternancia de findes, que sí admite
        el intercambio de descanso. Confirmado con el usuario el 2026-08-20.

        Sin este control, "bloquear el festivo" degeneraría en bloquear de más — el
        mismo riesgo que avisa el patrón #25 al cerrar una guardia.
        """
        DiaEspecial.objects.create(fecha=SABADO, tipo='festivo', activo=True)
        DiaEspecial.objects.create(fecha=DOMINGO, tipo='festivo', activo=True)

        assert self._analizar(SABADO, tipo='CAMBIO DESCANSO')['valida'] is True
        assert self._analizar(DOMINGO, tipo='CAMBIO DESCANSO')['valida'] is True

    def test_la_temporada_invalida_todos_los_tipos(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='temporada',
                                   es_temporada=True, activo=True)

        for tipo in ('CT', 'CT PERMANENTE', 'DOBLADA', 'D FDS', 'CAMBIO DESCANSO'):
            assert self._analizar(tipo=tipo)['valida'] is False, tipo


class TestTipoNoContemplado(FechasHelperTestCase):
    """
    La rama `else`, y el caso que mas facil se rompe al pasar a despacho por
    strategy.

    Aqui el `else` es el GENERICO PERMISIVO —solo mantenimiento y temporada
    invalidan— y NO el de CAMBIO TURNO. Es al reves que en `views/detalle.py` y en
    `solicitud_request_parser.py`, donde el `else` si mandaba a CT.

    Despachar con una caida por defecto a CambioTurnoStrategy, como se hizo alli,
    convertiria un tipo desconocido de permisivo en estricto sin que nadie lo note.
    Estos tests estan escritos ANTES del refactor precisamente para impedirlo.
    """

    def test_un_tipo_desconocido_permite_festivo_sabado_y_domingo(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='festivo', activo=True)

        assert self._analizar(MIERCOLES, tipo='TIPO QUE NO EXISTE')['valida'] is True
        assert self._analizar(SABADO, tipo='TIPO QUE NO EXISTE')['valida'] is True
        assert self._analizar(DOMINGO, tipo='TIPO QUE NO EXISTE')['valida'] is True

    def test_un_tipo_desconocido_SI_se_bloquea_por_mantenimiento(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='mantenimiento', activo=True)

        assert self._analizar(MIERCOLES, tipo='TIPO QUE NO EXISTE')['valida'] is False

    def test_un_tipo_desconocido_SI_se_bloquea_por_temporada(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='temporada',
                                   es_temporada=True, activo=True)

        assert self._analizar(MIERCOLES, tipo='TIPO QUE NO EXISTE')['valida'] is False

    def test_una_cadena_vacia_se_trata_como_tipo_no_contemplado(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='festivo', activo=True)

        assert self._analizar(MIERCOLES, tipo='')['valida'] is True

    def test_el_tipo_desconocido_NO_hereda_las_reglas_de_cambio_turno(self):
        """
        El control explicito contra el error que se cometio dos veces en esta fase:
        reusar la caida por defecto de una cadena en otra cuyo `else` era distinto.
        Un domingo invalida un CT, pero NO un tipo no contemplado.
        """
        assert self._analizar(DOMINGO, tipo='CT')['valida'] is False
        assert self._analizar(DOMINGO, tipo='TIPO QUE NO EXISTE')['valida'] is True


class TestJornadaYDescanso(FechasHelperTestCase):

    def test_detecta_que_ambos_tienen_jornada(self):
        r = self._analizar()

        assert r['tiene_jornada_solicitante'] is True
        assert r['tiene_jornada_receptor'] is True

    def test_sin_jornada_asignada_no_marca_jornada(self):
        """Un empleado recién creado, sin AsignarJornadaExplorador."""
        sin_jornada = crear_empleado('Sin', 'Jornada')

        r = analizar_fecha_solicitud(MIERCOLES, solicitante=sin_jornada,
                                     receptor=self.receptor, tipo_solicitud='CT')

        assert r['tiene_jornada_solicitante'] is False
        assert r['tiene_jornada_receptor'] is True

    def test_sin_empleados_no_revienta(self):
        """
        Los dos empleados son opcionales en la firma. Con None debe devolver el
        análisis del día (festivo, domingo…) sin tocar jornadas.
        """
        r = self._analizar(con_empleados=False)

        assert r['tiene_jornada_solicitante'] is False
        assert r['es_descanso_solicitante'] is False
        assert r['valida'] is True


class TestInformacionParaElDetalle(FechasHelperTestCase):
    """La función que consume `views/detalle.py`: formato de salida."""

    def test_formatea_la_fecha_para_el_frontend(self):
        info = obtener_informacion_fecha_para_detalle(
            MIERCOLES, self.solicitante, self.receptor, 'CT')

        assert info['fecha'] == '02/09/2026'

    def test_expone_las_claves_que_espera_la_vista(self):
        """
        `detalle.py` lee `razones_exclusion` directamente; si desaparece o cambia
        de nombre, la vista falla en producción y no en los tests.
        """
        info = obtener_informacion_fecha_para_detalle(
            MIERCOLES, self.solicitante, self.receptor, 'CT')

        assert set(info) == {'fecha', 'valida', 'razones_exclusion', 'informacion'}
        assert set(info['informacion']) == {
            'es_festivo', 'es_mantenimiento', 'es_temporada', 'es_domingo', 'es_sabado',
            'es_descanso_solicitante', 'es_descanso_receptor',
            'tiene_doblada_solicitante', 'tiene_doblada_receptor',
            'tiene_jornada_solicitante', 'tiene_jornada_receptor',
        }

    def test_traslada_el_motivo_de_exclusion(self):
        DiaEspecial.objects.create(fecha=MIERCOLES, tipo='mantenimiento', activo=True)

        info = obtener_informacion_fecha_para_detalle(
            MIERCOLES, self.solicitante, self.receptor, 'CT')

        assert info['valida'] is False
        assert 'Mantenimiento' in info['razones_exclusion']
        assert info['informacion']['es_mantenimiento'] is True


class TestFactoriesCompartidas(TestCase):
    """
    Control de las factories nuevas (`core/tests/factories.py`): si generaran
    identificadores repetidos, los fallos aparecerían dispersos por toda la suite
    y costaría relacionarlos con su causa.
    """

    def test_las_cedulas_y_usuarios_no_se_repiten(self):
        empleados = [crear_empleado() for _ in range(5)]

        assert len({e.cedula for e in empleados}) == 5
        assert len({e.user.username for e in empleados}) == 5

    def test_crear_jornada_reutiliza_la_existente(self):
        """`Jornada.nombre` es ÚNICO: pedir 'AM' dos veces no puede reventar."""
        assert crear_jornada('AM').pk == crear_jornada('AM').pk

    def test_el_par_contrario_tiene_jornadas_opuestas(self):
        am, pm, sala = crear_par_contrario()

        assert am.asignarjornadaexplorador_set.first().jornada.nombre == 'AM'
        assert pm.asignarjornadaexplorador_set.first().jornada.nombre == 'PM'
