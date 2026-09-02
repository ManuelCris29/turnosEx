"""
El orquestador de alta de solicitudes no habla HTTP.

QUÉ SE ARREGLÓ
--------------
`SolicitudOrchestrator.procesar()` devolvía `JsonResponse`. Todo el flujo de alta
—dedupe, sanción, cierre semanal, restricción médica, validación y creación— estaba
atado a la capa web: crear una solicitud desde un test de integración, un comando de
gestión o una tarea programada obligaba a fabricar un POST y a leer el resultado con
`json.loads(resp.content)`.

Ahora devuelve un `ResultadoSolicitud` y la conversión a JSON ocurre en un único
sitio: `solicitudes/views/resultado_http.py`.

POR QUÉ ESTE TEST
-----------------
La regresión es fácil y silenciosa: basta con que alguien añada un caso nuevo al
orquestador con un `return json_error(...)` copiado de otra rama. La respuesta HTTP
seguiría siendo correcta —el atajo funciona— y el flujo volvería a ser inejecutable
fuera de una petición sin que nada falle.
"""
import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from solicitudes.services.resultado import ResultadoSolicitud

ORQUESTADOR = Path(settings.BASE_DIR) / 'solicitudes' / 'services' / 'solicitud_orchestrator.py'
CASO_DE_USO = Path(settings.BASE_DIR) / 'solicitudes' / 'use_cases' / 'crear_solicitud.py'

# Construir una respuesta HTTP es exactamente lo que estas capas ya no deben hacer.
PROHIBIDOS = {'JsonResponse', 'HttpResponse', 'HttpResponseRedirect', 'json_ok', 'json_error',
              'json_error_inesperado', 'render', 'redirect'}


class OrquestadorSinHttpTestCase(SimpleTestCase):

    def _nombres_importados(self, py: Path) -> set:
        arbol = ast.parse(py.read_text(encoding='utf-8'))
        nombres = set()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.ImportFrom):
                nombres.update(a.asname or a.name for a in nodo.names)
            elif isinstance(nodo, ast.Import):
                nombres.update((a.asname or a.name).split('.')[0] for a in nodo.names)
        return nombres

    def test_el_orquestador_no_construye_respuestas_http(self):
        infractores = self._nombres_importados(ORQUESTADOR) & PROHIBIDOS
        self.assertEqual(
            infractores, set(),
            'El orquestador volvió a importar la capa HTTP: devuelve ResultadoSolicitud '
            'y deja que views/resultado_http.py lo traduzca.')

    def test_el_caso_de_uso_tampoco(self):
        infractores = self._nombres_importados(CASO_DE_USO) & PROHIBIDOS
        self.assertEqual(infractores, set())

    def test_el_cuerpo_json_no_cambia_respecto_a_los_helpers_antiguos(self):
        """El contrato que leen los seis formularios sigue siendo el mismo.

        Las claves están escritas a mano aquí a propósito: si alguien cambia
        `como_payload()`, este test debe fallar en vez de seguir a la implementación.
        """
        ok = ResultadoSolicitud.exito({'message': 'Creada', 'solicitud_id': 7}, status=201)
        self.assertEqual(ok.status, 201)
        self.assertEqual(ok.como_payload(),
                         {'success': True, 'message': 'Creada', 'solicitud_id': 7})

        err = ResultadoSolicitud.error('No puedes', status=403, code='sancionado')
        self.assertTrue(err.fallo)
        self.assertEqual(err.status, 403)
        self.assertEqual(err.como_payload(),
                         {'success': False, 'error': 'No puedes', 'code': 'sancionado'})

        con_extra = ResultadoSolicitud.error('Ups', status=500, code='internal_error',
                                             extra={'request_id': 'abc'})
        self.assertEqual(con_extra.como_payload()['extra'], {'request_id': 'abc'})

    def test_un_payload_del_dominio_viaja_intacto(self):
        """La advertencia de restricción médica y `RequiereCambioTurnoPrevio` definen su
        propio cuerpo; el resultado no debe reescribirlo."""
        from solicitudes.services.errores_validacion import RequiereCambioTurnoPrevio

        aviso = RequiereCambioTurnoPrevio('Necesitas un CT previo',
                                          fecha_pago='2026-09-10', jornada_comun='AM')
        res = ResultadoSolicitud.desde_payload(aviso.como_payload(), status=400)

        self.assertEqual(res.status, 400)
        self.assertTrue(res.fallo)
        self.assertEqual(res.como_payload(), aviso.como_payload())
        self.assertEqual(res.code, 'requiere_cambio_turno_previo')
