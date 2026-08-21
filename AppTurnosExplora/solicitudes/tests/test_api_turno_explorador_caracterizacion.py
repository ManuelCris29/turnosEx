"""
Red de caracterizacion de `ObtenerTurnoExploradorView` (api_turno_jornada.py:16).

POR QUE ESTA RED EXISTE
La medicion del punto 16 del informe dio el peor numero de todo el proyecto:
`api_turno_jornada.py` figuraba al 5 %, pero al mirar QUE lineas cubria el CI
resulto que eran los imports y las lineas de `class` y `def`. Ni una sola linea de
cuerpo se ejecutaba en ningun test. La cobertura funcional era CERO.

Y no es codigo secundario: `obtener-turno-explorador` lo llaman TRES formularios
(cambio de turno, CT permanente y doblada), y las ocho claves de su respuesta se
leen en el JS (`data.turno` en 32 sitios).

Un `get()` de 310 lineas sin una sola prueba no se puede refactorizar: cualquier
corte seria a ciegas. Estos tests NO especifican como deberia comportarse el
endpoint; FIJAN lo que hace hoy, para que al trocearlo se note si algo cambia.
Donde el comportamiento actual parece discutible, se marca como tal en vez de
"corregirlo" — cambiarlo ahora mezclaria dos cosas y sin red que lo respalde.

LO QUE DESCUBRIO LA PRUEBA DE MUTACION (y es el hallazgo de fondo del punto 16)
Escrita la red, se comprobo que mordiera rompiendo el codigo a proposito. Dos de
tres mutaciones NO la hicieron fallar, y la causa no era la red: era que ese codigo
esta DUPLICADO. Medido ejecutando el servicio directamente:

  * `TurnoService.get_turno_explorador` YA devuelve None cuando el explorador cedio
    ese dia en una DOBLADA aprobada. Las ~60 lineas de la vista que vuelven a
    detectar el descanso pueden quitar `turno_dict = None` sin que nada cambie: lo
    unico que aportan de verdad es `descanso_info` (nombre del companero, fechas),
    que el servicio no da.
  * `TurnoService` YA responde `jornada: 'DOBLADA'` y `es_doblada: True` con dos
    turnos AM+PM reales. El calculo manual `len(turnos_en_fecha) >= 2 and 'AM' in
    ... and 'PM' in ...` es redundante: el bloque siguiente vuelve a poner
    `es_doblada = True` a partir de la senal del servicio.

Por eso esta vista tiene 310 lineas — reimplementa a mano lo que la fuente de
verdad ya resuelve. Ese es el material del refactor, y ahora esta medido en vez de
supuesto. Los tests se dejan igualmente: fijan la RESPUESTA, que es lo que el
frontend consume, sea cual sea la capa que la produzca.

QUE NO CUBRE
El bloque de festivos entre semana depende de la alternancia publicada del anio
(`AsignacionEspecialService.grupo_trabaja`), que en la base de test no esta
sembrada. Se cubre el camino de fin de semana, que usa el mismo servicio y si se
puede montar. Queda anotado como hueco consciente.
"""
import json
from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from empleados.models import Empleado
from solicitudes.models import DobladaDetalle, SolicitudCambio, TipoSolicitudCambio
from turnos.models import AsignarJornadaExplorador, Turno


class BaseApiTurno(TestCase):
    URL = None

    def setUp(self):
        self.URL = reverse('solicitudes:obtener_turno_explorador')
        self.sala = crear_sala()
        self.am = crear_jornada('AM')
        self.pm = crear_jornada('PM')
        self.emp = crear_empleado('Ana', 'Uno', jornada=self.am, sala=self.sala)
        self.otro = crear_empleado('Ben', 'Dos', jornada=self.pm, sala=self.sala)
        self.client.force_login(self.emp.user)

    def pedir(self, **params):
        r = self.client.get(self.URL, params)
        return r, json.loads(r.content)

    def _turno(self, empleado, fecha, jornada):
        return Turno.objects.create(explorador=empleado, fecha=fecha,
                                    jornada=jornada, sala=self.sala)

    def _un_martes(self):
        """Un dia de semana futuro, para no chocar con reglas de fin de semana."""
        d = date.today() + timedelta(days=14)
        while d.weekday() != 1:
            d += timedelta(days=1)
        return d


class ParametrosTestCase(BaseApiTurno):
    def test_sin_fecha_ni_explorador_responde_400(self):
        r, cuerpo = self.pedir()

        self.assertEqual(r.status_code, 400)
        self.assertEqual(cuerpo.get('code'), 'missing_params')

    def test_falta_solo_la_fecha_y_tambien_responde_400(self):
        r, cuerpo = self.pedir(explorador_id=self.emp.id)

        self.assertEqual(r.status_code, 400)
        self.assertEqual(cuerpo.get('code'), 'missing_params')

    def test_sin_sesion_no_se_responde(self):
        self.client.logout()

        r = self.client.get(self.URL, {'fecha': '2026-03-10', 'explorador_id': self.emp.id})

        self.assertIn(r.status_code, (302, 403))

    def test_un_explorador_inexistente_da_404_y_no_un_turno_vacio(self):
        """
        Un id que no existe es un error del CLIENTE. Antes la peticion llegaba
        hasta la estrategia, que capturaba el DoesNotExist y devolvia `{}`, y la
        respuesta era `200` con `turno: {}, tiene_turno: true` — "si tiene turno",
        con un objeto vacio. Ahora se comprueba antes de nada.
        """
        r, cuerpo = self.pedir(fecha=str(self._un_martes()), explorador_id=999999)

        self.assertEqual(r.status_code, 404)
        self.assertEqual(cuerpo.get('code'), 'explorador_no_encontrado')

    def test_un_fallo_real_sale_como_500_sin_filtrar_la_traza(self):
        """La otra mitad: una averia de verdad no se disfraza de dia sin turno."""
        with patch('turnos.services.turno_service.TurnoService.get_turno_explorador',
                   side_effect=RuntimeError('boom')):
            r, cuerpo = self.pedir(fecha=str(self._un_martes()),
                                   explorador_id=self.emp.id)

        self.assertEqual(r.status_code, 500)
        self.assertEqual(cuerpo.get('code'), 'internal_error')
        self.assertNotIn('Traceback', str(cuerpo))
        self.assertNotIn('boom', str(cuerpo))


class ContratoDeRespuestaTestCase(BaseApiTurno):
    """
    Las ocho claves que lee el JS. Es el contrato que un refactor no puede tocar
    sin romper pantallas, y ninguna estaba vigilada.
    """

    CLAVES = {'turno', 'tiene_turno', 'es_doblada', 'jornadas',
              'esta_descansando', 'descanso_info'}

    def test_la_respuesta_siempre_trae_las_claves_que_lee_el_formulario(self):
        martes = self._un_martes()
        self._turno(self.emp, martes, self.am)

        _, cuerpo = self.pedir(fecha=str(martes), explorador_id=self.emp.id)

        self.assertTrue(self.CLAVES.issubset(set(cuerpo)),
                        f'faltan claves: {self.CLAVES - set(cuerpo)}')

    def test_un_sabado_anade_las_dos_claves_propias_del_sabado(self):
        """
        `jornada_trabaja_sabado` y `corresponde_trabajar_sabado` solo aparecen en
        sabado. El formulario de doblada las usa para decidir si muestra el selector
        de media jornada.
        """
        sabado = date.today() + timedelta(days=14)
        while sabado.weekday() != 5:
            sabado += timedelta(days=1)

        _, cuerpo = self.pedir(fecha=str(sabado), explorador_id=self.emp.id)

        self.assertIn('jornada_trabaja_sabado', cuerpo)
        self.assertIn('corresponde_trabajar_sabado', cuerpo)
        self.assertIsInstance(cuerpo['corresponde_trabajar_sabado'], bool)

    def test_entre_semana_no_aparecen_las_claves_de_sabado(self):
        martes = self._un_martes()

        _, cuerpo = self.pedir(fecha=str(martes), explorador_id=self.emp.id)

        self.assertNotIn('jornada_trabaja_sabado', cuerpo)
        self.assertNotIn('corresponde_trabajar_sabado', cuerpo)


class JornadaBaseTestCase(BaseApiTurno):
    """
    `jornada_base=true` es una rama COMPLETA y aparte: sale por su propio `return`
    en las primeras 45 lineas y no ejecuta nada del resto del metodo. La usa
    `solicitar_ct_permanente.js`.
    """

    def test_devuelve_un_turno_virtual_desde_la_jornada_asignada(self):
        martes = self._un_martes()

        _, cuerpo = self.pedir(fecha=str(martes), explorador_id=self.emp.id,
                               jornada_base='true')

        self.assertTrue(cuerpo['tiene_turno'])
        turno = cuerpo['turno']
        self.assertTrue(turno['es_turno_virtual'])
        self.assertTrue(turno['es_jornada_base'])
        self.assertIsNone(turno['id'], 'no corresponde a ninguna fila Turno real')
        self.assertEqual(turno['jornada'], 'AM')

    def test_ignora_los_turnos_reales_del_dia(self):
        """
        Lo que hace util a esta rama: responde la jornada BASE aunque ese dia haya
        turnos que digan otra cosa. Si algun refactor la unificara con la rama
        general, CT permanente empezaria a ver el estado del dia en vez de la base.
        """
        martes = self._un_martes()
        self._turno(self.emp, martes, self.pm)

        _, cuerpo = self.pedir(fecha=str(martes), explorador_id=self.emp.id,
                               jornada_base='true')

        self.assertEqual(cuerpo['turno']['jornada'], 'AM')

    def test_sin_jornada_asignada_responde_que_no_hay_turno(self):
        martes = self._un_martes()
        suelto = Empleado.objects.create(
            user=User.objects.create_user(username='suelto', password='x'),
            nombre='Sin', apellido='Jornada', cedula='99999999', activo=True)

        _, cuerpo = self.pedir(fecha=str(martes), explorador_id=suelto.id,
                               jornada_base='true')

        self.assertFalse(cuerpo['tiene_turno'])
        self.assertIsNone(cuerpo['turno'])


class DobladaRealTestCase(BaseApiTurno):
    def test_dos_turnos_am_y_pm_el_mismo_dia_son_doblada(self):
        martes = self._un_martes()
        self._turno(self.emp, martes, self.am)
        self._turno(self.emp, martes, self.pm)

        _, cuerpo = self.pedir(fecha=str(martes), explorador_id=self.emp.id)

        self.assertTrue(cuerpo['es_doblada'])
        self.assertEqual(sorted(cuerpo['jornadas']), ['AM', 'PM'])

    def test_un_solo_turno_no_es_doblada(self):
        """
        La regla que el comentario del codigo subraya: doblada exige TURNOS
        asignados AM+PM, no basta la jornada predeterminada.
        """
        martes = self._un_martes()
        self._turno(self.emp, martes, self.am)

        _, cuerpo = self.pedir(fecha=str(martes), explorador_id=self.emp.id)

        self.assertFalse(cuerpo['es_doblada'])

    def test_la_base_impide_repetir_jornada_el_mismo_dia(self):
        """
        Se intento caracterizar "AM+AM no es doblada" y resulto ser un escenario
        IMPOSIBLE: la restriccion `turno_unico_activo_por_jornada` lo rechaza en la
        base de datos. Es decir, la condicion `'AM' in lista and 'PM' in lista` de
        la vista tiene detras una garantia real, no solo una convencion.

        Se deja como test para que, si algun dia se relaja esa restriccion, alguien
        vuelva a mirar la deteccion de doblada de esta vista.
        """
        from django.db.utils import IntegrityError

        martes = self._un_martes()
        self._turno(self.emp, martes, self.am)

        with self.assertRaises(IntegrityError):
            self._turno(self.emp, martes, self.am)


class DescansoPorDobladaTestCase(BaseApiTurno):
    """
    Sin turnos en la fecha, el endpoint busca si el descanso viene de una DOBLADA
    aprobada y devuelve `descanso_info` para que el formulario lo explique.
    """

    def setUp(self):
        super().setUp()
        self.tipo, _ = TipoSolicitudCambio.objects.get_or_create(nombre='DOBLADA')

    def _doblada(self, solicitante, receptor, fecha_cesion, fecha_pago):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=solicitante, explorador_receptor=receptor,
            tipo_cambio=self.tipo, estado='aprobada',
            fecha_cambio_turno=fecha_cesion, comentario='x')
        DobladaDetalle.objects.create(solicitud=sol, fecha_pago=fecha_pago)
        return sol

    def test_quien_cedio_su_jornada_aparece_descansando(self):
        cesion = self._un_martes()
        pago = cesion + timedelta(days=7)
        self._doblada(self.emp, self.otro, cesion, pago)

        _, cuerpo = self.pedir(fecha=str(cesion), explorador_id=self.emp.id)

        self.assertTrue(cuerpo['esta_descansando'])
        self.assertEqual(cuerpo['descanso_info']['tipo'], 'cedio')
        self.assertEqual(cuerpo['descanso_info']['companero_id'], self.otro.id)
        self.assertIsNone(cuerpo['turno'], 'descansando no se muestra jornada base')
        self.assertEqual(cuerpo['jornadas'], [])

    def test_quien_cobra_el_favor_descansa_el_dia_de_pago(self):
        cesion = self._un_martes()
        pago = cesion + timedelta(days=7)
        self._doblada(self.otro, self.emp, cesion, pago)

        _, cuerpo = self.pedir(fecha=str(pago), explorador_id=self.emp.id)

        self.assertTrue(cuerpo['esta_descansando'])
        self.assertEqual(cuerpo['descanso_info']['tipo'], 'pago')
        self.assertEqual(cuerpo['descanso_info']['companero_id'], self.otro.id)

    def test_el_descanso_solo_se_busca_si_no_hay_turnos_reales(self):
        """
        Guarda de la condicion `if not turnos_en_fecha`: con un turno real en la
        fecha, la doblada aprobada NO se consulta. Si un refactor moviera este
        bloque fuera del `if`, el dia empezaria a mostrarse como descanso teniendo
        turno.
        """
        cesion = self._un_martes()
        self._doblada(self.emp, self.otro, cesion, cesion + timedelta(days=7))
        self._turno(self.emp, cesion, self.am)

        _, cuerpo = self.pedir(fecha=str(cesion), explorador_id=self.emp.id)

        self.assertFalse(cuerpo['esta_descansando'])
        self.assertIsNotNone(cuerpo['turno'])

    def test_una_doblada_no_aprobada_no_produce_descanso(self):
        cesion = self._un_martes()
        sol = self._doblada(self.emp, self.otro, cesion, cesion + timedelta(days=7))
        sol.estado = 'pendiente'
        sol.save()

        _, cuerpo = self.pedir(fecha=str(cesion), explorador_id=self.emp.id)

        self.assertFalse(cuerpo['esta_descansando'])


class TipoSolicitudTestCase(BaseApiTurno):
    def test_un_tipo_inexistente_no_da_error_sino_otra_rama(self):
        """
        RAREZA CARACTERIZADA, no aprobada. El propio codigo lo admite en un
        comentario: un `tipo_solicitud_id` que no existe no responde 400 — se sigue
        con `tipo_solicitud=None`, que toma una rama de calculo DISTINTA de la que
        el formulario pidio, y solo queda un warning en el log.

        Se fija aqui para que el refactor no lo cambie sin querer. Si algun dia se
        decide devolver 400, este test debe cambiarse a proposito y con su motivo.
        """
        martes = self._un_martes()
        self._turno(self.emp, martes, self.am)

        r, cuerpo = self.pedir(fecha=str(martes), explorador_id=self.emp.id,
                               tipo_solicitud_id=999999)

        self.assertEqual(r.status_code, 200)
        self.assertIn('turno', cuerpo)


class FinDeSemanaTestCase(BaseApiTurno):
    def test_en_sabado_se_informa_que_grupo_trabaja(self):
        sabado = date.today() + timedelta(days=14)
        while sabado.weekday() != 5:
            sabado += timedelta(days=1)

        _, cuerpo = self.pedir(fecha=str(sabado), explorador_id=self.emp.id)

        # El valor concreto depende de la alternancia sembrada; lo que se fija es
        # que la clave viaja y que el booleano es coherente con ella.
        grupo = cuerpo['jornada_trabaja_sabado']
        if grupo:
            asignacion = (AsignarJornadaExplorador.objects
                          .filter(explorador=self.emp, fecha_inicio__lte=sabado)
                          .order_by('-fecha_inicio').first())
            base = asignacion.jornada.nombre.upper() if asignacion else None
            self.assertEqual(cuerpo['corresponde_trabajar_sabado'],
                             base == str(grupo).upper())
        else:
            self.assertFalse(cuerpo['corresponde_trabajar_sabado'])


class ErroresQueYaNoSeDisfrazanTestCase(BaseApiTurno):
    """
    El `{}` que las estrategias devolvian al tragarse una excepcion, y por que se
    quito.

    HISTORIA, porque explica dos decisiones seguidas y opuestas.

    Primero se propuso borrar dos bloques de esta vista por parecer duplicados de
    `TurnoService`. La auditoria lo impidio: tres estrategias hacian
    `except Exception: return {}`, y ese `{}` es *falsy* en Python pero
    `{} is not None` es cierto —y en JavaScript es *truthy*—, asi que los dos
    bloques no eran duplicados: sostenian la respuesta cuando el servicio fallaba.

    Medido despues, ese `{}` resulto ser el problema de fondo. Creaba un TERCER
    valor de retorno que no declaraba nadie (dict / None / `{}`), era alcanzable
    desde la URL con un `explorador_id` inexistente, y producia `200` con
    `turno: {}, tiene_turno: true`. Ademas anulaba una decision explicita de
    `DobladaStrategy`, que renunciaba al `except` a proposito: el envoltorio de
    `SolicitudFactory` lo capturaba igual una capa mas arriba.

    Ahora los errores no se disfrazan: un id inexistente da 404 y una averia real
    da 500 con traza en el log. Un bug que se hace pasar por "hoy no trabaja" no se
    encuentra en el log; se encuentra meses despues, por la queja de alguien que se
    quedo sin turno.
    """

    RUTA_SERVICIO = 'turnos.services.turno_service.TurnoService.get_turno_explorador'

    def _tipo_ct(self):
        t, _ = TipoSolicitudCambio.objects.get_or_create(nombre='CT')
        return t

    def test_nadie_devuelve_ya_un_diccionario_vacio_como_turno(self):
        """
        Control directo: si alguien reintroduce el `return {}`, vuelve el tercer
        valor y con el toda la ambiguedad.

        Se analiza con AST y no buscando el texto `return {}`, porque los propios
        docstrings de esos modulos lo MENCIONAN al explicar por que se quito: una
        busqueda literal se caza a si misma. El AST distingue codigo de prosa.
        """
        import ast
        import inspect

        from solicitudes.services import solicitud_factory as factory_mod
        from solicitudes.services.strategies import base_strategy as base_mod
        from solicitudes.services.strategies import (
            cambio_turno_strategy, d_fds_strategy, doblada_permanente_strategy,
            doblada_strategy,
        )

        modulos = (factory_mod, base_mod, cambio_turno_strategy, d_fds_strategy,
                   doblada_permanente_strategy, doblada_strategy)
        infractores = []
        for modulo in modulos:
            arbol = ast.parse(inspect.getsource(modulo))
            for nodo in ast.walk(arbol):
                if (isinstance(nodo, ast.Return)
                        and isinstance(nodo.value, ast.Dict)
                        and not nodo.value.keys):
                    infractores.append(f'{modulo.__name__}:{nodo.lineno}')

        self.assertEqual(infractores, [],
                         f'volvieron a fabricar un dict vacio: {infractores}')

    def test_las_cuatro_sobrescrituras_identicas_siguen_borradas(self):
        """
        Cuatro estrategias sobrescribian `get_turno_explorador` con el MISMO cuerpo
        que la base; tres de ellas solo anadian el `except` danino. Heredar de la
        base es lo correcto, y este test evita que alguien vuelva a copiarlo.
        """
        from solicitudes.services.strategies.base_strategy import SolicitudStrategy
        from solicitudes.services.strategies.cambio_turno_strategy import CambioTurnoStrategy
        from solicitudes.services.strategies.d_fds_strategy import DFDSStrategy
        from solicitudes.services.strategies.doblada_permanente_strategy import DobladaPermanenteStrategy
        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy

        for clase in (CambioTurnoStrategy, DobladaStrategy, DFDSStrategy,
                      DobladaPermanenteStrategy):
            with self.subTest(estrategia=clase.__name__):
                self.assertIs(
                    clase.get_turno_explorador, SolicitudStrategy.get_turno_explorador,
                    'volvio a sobrescribir un metodo identico al de la base')

    def test_con_el_servicio_caido_la_peticion_falla_de_forma_visible(self):
        """Antes: 200 con datos vacios. Ahora: 500, que es lo que hay que ver."""
        martes = self._un_martes()
        self._turno(self.emp, martes, self.am)
        self._turno(self.emp, martes, self.pm)

        with patch(self.RUTA_SERVICIO, side_effect=RuntimeError('boom')):
            r, _ = self.pedir(fecha=str(martes), explorador_id=self.emp.id,
                              tipo_solicitud_id=self._tipo_ct().id)

        self.assertEqual(r.status_code, 500)

    def test_un_tipo_inactivo_sigue_devolviendo_el_turno_real(self):
        """
        `activo` significa "se pueden CREAR solicitudes nuevas de este tipo"; no
        dice nada sobre consultar que turno tiene alguien un dia. Antes esto
        devolvia `{}` con `tiene_turno: true` y sin jornada.
        """
        martes = self._un_martes()
        self._turno(self.emp, martes, self.am)
        tipo = self._tipo_ct()
        tipo.activo = False
        tipo.save()

        r, cuerpo = self.pedir(fecha=str(martes), explorador_id=self.emp.id,
                               tipo_solicitud_id=tipo.id)

        self.assertEqual(r.status_code, 200)
        self.assertTrue(cuerpo['tiene_turno'])
        self.assertEqual(cuerpo['turno']['jornada'], 'AM')
