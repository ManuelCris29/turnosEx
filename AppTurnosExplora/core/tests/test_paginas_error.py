"""
Las páginas de error no pueden filtrar información interna.

Estos tests son una barrera de regresión: el día que alguien haga que una
plantilla de error herede de base.html, o que un handler pase el `request` al
renderizar, o que se despliegue con DEBUG=True, estos tests se ponen rojos.

El fallo que evitan es real: con DEBUG=True una simple URL inexistente
(/solicitudes/cambio-turno/loquesea) devolvía el URLconf completo de la
aplicación, con todos los endpoints de aprobación y rechazo de solicitudes.
"""
import pytest
from django.test import Client, override_settings

# Cadenas que jamás deben aparecer en una respuesta de error.
FUGAS = [
    'config.urls',          # nombre del módulo de URLs
    'URLconf',
    'Traceback',
    'aprobar-solicitud',    # cualquier endpoint del mapa de rutas
    'Django tried these',
    'DJANGO_SETTINGS_MODULE',
]


@pytest.fixture
def cliente_produccion():
    """Cliente que se comporta como producción: sin DEBUG."""
    with override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver']):
        yield Client()


class TestSinFugaDeInformacion:

    def test_404_no_revela_el_urlconf(self, cliente_produccion):
        respuesta = cliente_produccion.get('/solicitudes/cambio-turno/loquesea')

        assert respuesta.status_code == 404
        cuerpo = respuesta.content.decode('utf-8')
        for fuga in FUGAS:
            assert fuga not in cuerpo, f'La página 404 filtra «{fuga}»'

    def test_404_no_refleja_la_ruta_pedida(self, cliente_produccion):
        """
        No devolver la entrada del usuario evita usar la página de error como
        soporte para un mensaje falso ("su sesión ha caducado, llame al...").
        """
        respuesta = cliente_produccion.get('/ruta-inventada-xyz123/')

        assert 'ruta-inventada-xyz123' not in respuesta.content.decode('utf-8')

    def test_404_usa_la_plantilla_propia(self, cliente_produccion):
        respuesta = cliente_produccion.get('/no-existe/')

        cuerpo = respuesta.content.decode('utf-8')
        assert 'Esta página no está en la grilla' in cuerpo
        assert 'SWALP' in cuerpo


class TestCodigoDeReferencia:

    def test_toda_respuesta_lleva_la_cabecera(self, cliente_produccion):
        respuesta = cliente_produccion.get('/no-existe/')

        rid = respuesta.headers.get('X-Request-ID')
        assert rid and len(rid) == 12

    def test_el_codigo_visible_coincide_con_la_cabecera(self, cliente_produccion):
        """
        Es la razón de ser del código: lo que el usuario reporta tiene que ser
        exactamente lo que el equipo busca en CloudWatch.
        """
        respuesta = cliente_produccion.get('/no-existe/')

        rid = respuesta.headers['X-Request-ID']
        assert rid in respuesta.content.decode('utf-8')

    def test_cada_peticion_recibe_un_codigo_distinto(self, cliente_produccion):
        primera = cliente_produccion.get('/no-existe/').headers['X-Request-ID']
        segunda = cliente_produccion.get('/no-existe/').headers['X-Request-ID']

        assert primera != segunda

    def test_no_se_acepta_el_codigo_que_envia_el_cliente(self, cliente_produccion):
        """Un ID controlado por el cliente acabaría escrito en los logs."""
        respuesta = cliente_produccion.get(
            '/no-existe/', headers={'x-request-id': 'INYECTADO123'}
        )

        assert respuesta.headers['X-Request-ID'] != 'INYECTADO123'
        assert 'INYECTADO123' not in respuesta.content.decode('utf-8')


class TestCodigoReferenciaEnFormularios:
    """
    Los formularios envían por fetch y no recargan, así que no pasan por las
    plantillas de error: el código lo aporta `static/js/utils/codigo-referencia.js`.
    """

    def _base_html(self):
        from django.template import loader
        return loader.get_template('base.html').template.source

    def test_el_stub_se_define_antes_de_cargar_el_script(self):
        """
        Sin el stub, si el fichero no cargara, los `.catch()` de los formularios
        lanzarían ReferenceError: el usuario se quedaría sin aviso **y** sin que
        se rehabilitara el botón, con el formulario bloqueado. El orden importa:
        el stub primero, el fichero real después para sobrescribirlo.
        """
        fuente = self._base_html()

        stub = fuente.find('window.CodigoReferencia = {')
        script = fuente.find('js/utils/codigo-referencia.js')

        assert stub != -1, 'Falta el stub de CodigoReferencia en base.html'
        assert script != -1, 'Falta la carga de codigo-referencia.js en base.html'
        assert stub < script, 'El stub debe definirse ANTES de cargar el fichero'

    def test_el_script_se_carga_antes_que_los_demas(self):
        """Si se cargara después, no envolvería el fetch de los formularios."""
        fuente = self._base_html()

        assert (fuente.find('js/utils/codigo-referencia.js')
                < fuente.find('jquery.min.js'))


class TestPlantillasAutocontenidas:
    """
    Una página de error no puede depender de nada que pueda estar caído justo
    cuando se necesita: ni CDN, ni hoja de estilos externa, ni la BD.
    """

    @pytest.mark.parametrize('plantilla', [
        '400.html', '403.html', '403_csrf.html', '404.html', '500.html',
    ])
    def test_no_carga_recursos_externos(self, plantilla):
        from django.template import loader

        html = loader.get_template(plantilla).render({'request_id': 'ABC123'})
        # xmlns no es una descarga: es el identificador del espacio de nombres
        # SVG. El navegador nunca lo resuelve por red.
        html = html.replace('http://www.w3.org/2000/svg', '')

        assert 'http://' not in html
        assert 'https://' not in html

    @pytest.mark.parametrize('plantilla', [
        '400.html', '403.html', '403_csrf.html', '404.html', '500.html',
    ])
    def test_renderiza_sin_request_ni_contexto(self, plantilla):
        """
        handler500 renderiza con un contexto VACÍO. Si la plantilla necesitara
        `user` o `request`, la página de error reventaría precisamente en el
        escenario para el que existe.
        """
        from django.template import loader

        html = loader.get_template(plantilla).render({})

        assert '<!DOCTYPE html>' in html
        assert 'Código de referencia' not in html  # se omite si no hay id
