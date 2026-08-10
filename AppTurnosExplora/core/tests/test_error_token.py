"""
La página de los enlaces de aprobación por correo no puede filtrar excepciones.

Cuatro `except Exception` de `solicitudes/views/aprobacion_email.py` hacían
`render_error_token(request, f'Error al procesar la solicitud: {str(e)}')`. El
texto de una excepción de base de datos lleva fragmentos de SQL, nombres de
tabla y de columna o el nombre de la restricción violada, y esta página la ve
quien llega desde un correo, posiblemente sin sesión iniciada (CWE-209).

Es la misma clase de fuga que se cerró en las páginas 4xx/5xx; esta se quedó
fuera porque no pasa por los handlers de Django, al ser una respuesta normal de
una vista.
"""
import pytest
from django.test import RequestFactory, override_settings

from core.utils.error_token import (
    MENSAJE_INESPERADO,
    render_error_token,
    render_error_token_inesperado,
)


@pytest.fixture
def peticion():
    request = RequestFactory().get('/solicitudes/aprobar-email/1/tok/')
    request.request_id = 'A3F91C2B7D01'
    return request


class TestNoSeFiltraLaExcepcion:

    def test_el_texto_de_la_excepcion_no_llega_al_usuario(self, peticion):
        error = ValueError(
            "(1054, \"Unknown column 'solicitudes_solicitudcambio.secreto' in 'field list'\")"
        )

        respuesta = render_error_token_inesperado(peticion, error)

        cuerpo = respuesta.content.decode('utf-8')
        assert 'Unknown column' not in cuerpo
        assert 'solicitudes_solicitudcambio' not in cuerpo
        assert 'ValueError' not in cuerpo
        assert MENSAJE_INESPERADO in cuerpo

    def test_un_fallo_inesperado_responde_500(self, peticion):
        respuesta = render_error_token_inesperado(peticion, RuntimeError('boom'))

        assert respuesta.status_code == 500

    def test_la_traza_si_queda_en_el_log(self, peticion, caplog):
        """Lo que se le oculta al usuario tiene que estar en el log, o el
        cambio solo habría escondido el problema."""
        with caplog.at_level('ERROR', logger='core.utils.error_token'):
            render_error_token_inesperado(peticion, RuntimeError('boom'), 'aprobar supervisor')

        registro = caplog.records[-1]
        assert registro.exc_info is not None
        assert 'aprobar supervisor' in registro.getMessage()


class TestCodigoDeReferencia:

    def test_se_muestra_para_poder_reportarlo(self, peticion):
        respuesta = render_error_token_inesperado(peticion, RuntimeError('boom'))

        assert 'A3F91C2B7D01' in respuesta.content.decode('utf-8')

    def test_sin_identificador_no_se_inventa_nada(self):
        request = RequestFactory().get('/x/')   # sin request_id

        respuesta = render_error_token(request, 'Token inválido o expirado', status=403)

        # Se busca el marcado que se pinta, no el texto suelto: base.html lleva
        # un comentario HTML que también contiene esas palabras.
        assert 'Código de referencia: <code>' not in respuesta.content.decode('utf-8')


class TestEstadosHttp:
    """
    Un 200 en un enlace rechazado miente al navegador y, sobre todo, hace el
    fallo invisible para cualquier alarma que vigile códigos de error.
    """

    @override_settings(APPROVAL_LINK_MAX_AGE_DAYS=30)
    def test_el_mensaje_propio_se_muestra_tal_cual(self, peticion):
        respuesta = render_error_token(peticion, 'Token inválido o expirado', status=403)

        assert respuesta.status_code == 403
        assert 'Token inválido o expirado' in respuesta.content.decode('utf-8')

    def test_las_vistas_de_correo_no_devuelven_200_en_los_fallos(self):
        """Fija el resultado de la corrección sobre las cuatro vistas."""
        import re
        from pathlib import Path
        from django.conf import settings

        fuente = (Path(settings.BASE_DIR) / 'solicitudes' / 'views' /
                  'aprobacion_email.py').read_text(encoding='utf-8')

        llamadas = re.findall(r'render_error_token\((.*?)\)\n', fuente)
        sin_status = [c for c in llamadas if 'status=' not in c]

        assert not sin_status, f'Llamadas sin status explícito: {sin_status}'

    def test_no_queda_ninguna_interpolacion_de_excepcion(self):
        from pathlib import Path
        from django.conf import settings

        fuente = (Path(settings.BASE_DIR) / 'solicitudes' / 'views' /
                  'aprobacion_email.py').read_text(encoding='utf-8')

        assert 'str(e)' not in fuente
        assert '{e}' not in fuente
