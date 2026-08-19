"""
Las APIs JSON tampoco pueden devolver el texto de una excepción.

Ocho `except Exception` de `turnos/api/views/` y `solicitudes/views/` metían
`str(e)` en la respuesta 500. No pasan por ningún handler de Django —son
respuestas normales de una vista—, así que quedaron fuera del arreglo de las
páginas de error. Un `str(e)` de MySQL puede ser
`(1054, "Unknown column 'turnos_diaespecial.descripcion' in 'field list'")` o
`(2003, "Can't connect to MySQL server on 'swalp-prod.xxxx.rds.amazonaws.com'")`.

Estos tests fijan las dos mitades del arreglo: que el detalle NO salga, y que
SÍ quede en el log. Sin la segunda, el cambio solo escondería el problema.
"""
import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.test import RequestFactory

from core.utils.json_responses import json_error_inesperado

# Los ocho puntos corregidos, con el módulo donde viven.
MODULOS = [
    'turnos/api/views/dias_especiales.py',
    'turnos/api/views/calculo_automatico.py',
    'turnos/api/views/turnos_mes.py',
    'solicitudes/views/api_turno_jornada.py',
    'solicitudes/views/gestion_solicitudes.py',
]

ERROR_MYSQL = (
    '(2003, "Can\'t connect to MySQL server on '
    '\'swalp-prod.abc123.us-east-1.rds.amazonaws.com\' (115)")'
)


@pytest.fixture
def peticion():
    request = RequestFactory().get('/turnos/api/festivos/')
    request.request_id = 'A3F91C2B7D01'
    return request


class TestNoSeFiltraElDetalle:

    def test_el_endpoint_de_rds_no_llega_al_cliente(self, peticion):
        """El caso más serio: un fallo de conexión expone el host de RDS."""
        respuesta = json_error_inesperado(
            peticion, RuntimeError(ERROR_MYSQL), 'No pudimos cargar los festivos.'
        )

        cuerpo = respuesta.content.decode('utf-8')
        assert 'rds.amazonaws.com' not in cuerpo
        assert 'MySQL' not in cuerpo
        assert respuesta.status_code == 500

    def test_los_nombres_de_tabla_y_columna_no_llegan(self, peticion):
        error = RuntimeError(
            '(1054, "Unknown column \'turnos_diaespecial.descripcion\' in \'field list\'")'
        )

        cuerpo = json_error_inesperado(
            peticion, error, 'No pudimos cargar los festivos.'
        ).content.decode('utf-8')

        assert 'turnos_diaespecial' not in cuerpo
        assert 'Unknown column' not in cuerpo

    def test_el_mensaje_propio_si_se_muestra(self, peticion):
        """Se conserva un mensaje por endpoint: un genérico único degradaría
        la experiencia más de lo necesario."""
        respuesta = json_error_inesperado(
            peticion, RuntimeError('boom'), 'No pudimos cargar los festivos.'
        )

        datos = json.loads(respuesta.content)
        assert datos['error'] == 'No pudimos cargar los festivos.'
        assert datos['success'] is False
        assert datos['code'] == 'internal_error'


class TestElDetalleSiQuedaEnElLog:

    def test_se_registra_con_traza(self, peticion, caplog):
        with caplog.at_level('ERROR', logger='core.utils.json_responses'):
            json_error_inesperado(peticion, RuntimeError(ERROR_MYSQL), 'No pudimos cargar los festivos.')

        registro = caplog.records[-1]
        assert registro.exc_info is not None, 'Sin traza el arreglo solo esconde el fallo'

    def test_el_codigo_de_referencia_viaja_al_cliente(self, peticion):
        """Es lo que permite cruzar lo que reporta el usuario con el log."""
        datos = json.loads(
            json_error_inesperado(peticion, RuntimeError('boom'), 'Fallo.').content
        )

        assert datos['extra']['request_id'] == 'A3F91C2B7D01'

    def test_sin_identificador_no_se_inventa_nada(self):
        request = RequestFactory().get('/x/')   # sin request_id

        datos = json.loads(
            json_error_inesperado(request, RuntimeError('boom'), 'Fallo.').content
        )

        assert 'extra' not in datos


def _sin_comentarios(fuente: str) -> str:
    """Quita los comentarios para no analizarlos como si fueran código.

    Hace falta porque los propios comentarios que explican una fuga ya
    corregida citan el patrón que se persigue, y el test los daba por
    reincidencias. Se usa `tokenize` en vez de cortar por `#`, que rompería
    con una almohadilla dentro de una cadena.
    """
    import io
    import tokenize

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(fuente).readline))
    except tokenize.TokenError:
        return fuente   # Ante la duda, analizar de más y no de menos.

    lineas = fuente.splitlines()
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        fila, columna = token.start
        lineas[fila - 1] = lineas[fila - 1][:columna]
    return '\n'.join(lineas)


class TestNoReaparece:
    """Barrera para que el patrón no vuelva a colarse en estos módulos."""

    @pytest.mark.parametrize('modulo', MODULOS)
    def test_ningun_except_exception_devuelve_str_de_la_excepcion(self, modulo):
        """
        Se analiza el BLOQUE completo del `except`, no cada línea suelta.

        La primera versión de este test comparaba línea a línea y por eso dejó
        pasar una fuga real en `MisTurnosPorMesView`, donde el `JsonResponse(`
        y el `str(e)` estaban en líneas distintas:

            return JsonResponse({
                'error': f'Error al procesar fechas: {str(e)}',
                'traceback': error_trace if request.user.is_staff else None
            }, status=400)

        Ese bloque además publicaba el traceback entero a cualquier `is_staff`.
        """
        fuente = _sin_comentarios(
            (Path(settings.BASE_DIR) / modulo).read_text(encoding='utf-8'))
        lineas = fuente.splitlines()

        fugas = []
        for i, linea in enumerate(lineas):
            if not re.search(r'except\s+(Exception|BaseException)\b', linea):
                continue

            sangria = len(linea) - len(linea.lstrip())
            bloque = []
            for siguiente in lineas[i + 1:]:
                if siguiente.strip() and (len(siguiente) - len(siguiente.lstrip())) <= sangria:
                    break
                bloque.append(siguiente)
            texto = '\n'.join(bloque)

            devuelve = re.search(r'(JsonResponse|json_error\(|messages\.error|HttpResponse)', texto)
            interpola = re.search(r'(str\(e\)|\{e\}|\{str\(e\)\}|format_exc)', texto)
            if devuelve and interpola:
                fugas.append(f'{modulo}:{i + 1}')

        assert not fugas, f'Vuelve a filtrarse la excepción en {fugas}'

    @pytest.mark.parametrize('modulo', MODULOS)
    def test_no_se_publica_ningun_traceback(self, modulo):
        """`traceback.format_exc()` no puede acabar en una respuesta, ni
        siquiera detrás de un `if request.user.is_staff`: un supervisor es
        `is_staff` y no tiene por qué ver rutas de fichero ni código."""
        fuente = _sin_comentarios(
            (Path(settings.BASE_DIR) / modulo).read_text(encoding='utf-8'))

        assert "'traceback':" not in fuente
        assert '"traceback":' not in fuente
