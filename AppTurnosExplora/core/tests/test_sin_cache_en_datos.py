"""
`Cache-Control: no-store` en las respuestas de datos, y SOLO en ellas.

Las tres reglas de `SinCacheEnDatosMiddleware` son fáciles de romper sin querer
—basta con invertir una condición— y ninguna de las tres se nota al usar la
aplicación: no hay pantalla que se vea mal ni error de servidor. Lo que pasa es
peor y más tarde: o un explorador ve turnos viejos, o el botón «atrás» deja de
ser instantáneo en el celular. Por eso están fijadas aquí.

Se prueba el middleware DIRECTAMENTE, con respuestas fabricadas, en vez de a
través de una vista real. Así cada regla se comprueba aislada y sin base de
datos, y el test dice exactamente qué se rompió.
"""
from django.http import HttpResponse, JsonResponse
from django.test import RequestFactory, SimpleTestCase

from core.middleware import SinCacheEnDatosMiddleware


def _respuesta_tras_el_middleware(respuesta):
    """Pasa una respuesta ya hecha por el middleware y la devuelve."""
    middleware = SinCacheEnDatosMiddleware(lambda request: respuesta)
    return middleware(RequestFactory().get('/lo-que-sea/'))


class SinCacheEnDatos(SimpleTestCase):
    def test_el_json_sale_con_no_store(self):
        """El caso que motivó el middleware: los datos no se guardan."""
        r = _respuesta_tras_el_middleware(JsonResponse({'turnos': []}))

        self.assertEqual(r.headers.get('Cache-Control'), 'no-store')

    def test_el_html_se_queda_sin_cabecera(self):
        """No es un olvido: es para no desactivar el bfcache.

        `no-store` en un documento HTML hace que el botón «atrás» vuelva a pedir
        la página entera en vez de restaurarla al instante. En móvil eso es
        justo el viaje de ida y vuelta que se quería evitar. El HTML no lo
        necesita: se regenera en cada petición y sale sin validadores.
        """
        r = _respuesta_tras_el_middleware(HttpResponse('<h1>hola</h1>'))

        self.assertIsNone(
            r.headers.get('Cache-Control'),
            'El HTML no debe llevar Cache-Control: no-store — desactiva el '
            'bfcache y hace lenta la navegación hacia atrás en el celular.',
        )

    def test_no_pisa_la_cabecera_que_ya_venia(self):
        """Una vista que decidió su caché manda sobre el middleware.

        Es lo que protege a `@never_cache` (core/health.py) y a cualquier vista
        que algún día quiera declarar una caché propia.
        """
        original = JsonResponse({'ok': True})
        original.headers['Cache-Control'] = 'max-age=300, public'

        r = _respuesta_tras_el_middleware(original)

        self.assertEqual(r.headers.get('Cache-Control'), 'max-age=300, public')

    def test_el_content_type_con_charset_se_reconoce_igual(self):
        """'text/html; charset=utf-8' es HTML, aunque no sea igual de carácter.

        Comparar el Content-Type entero contra 'text/html' es el error obvio
        aquí, y dejaría a TODAS las páginas con no-store sin que nadie lo note
        hasta que el «atrás» se pusiera lento.
        """
        r = _respuesta_tras_el_middleware(
            HttpResponse('<h1>hola</h1>', content_type='text/html; charset=utf-8')
        )

        self.assertIsNone(r.headers.get('Cache-Control'))

    def test_una_descarga_tampoco_se_guarda(self):
        """Los Excel del reporte llevan datos de un empleado concreto."""
        descarga = HttpResponse(
            b'PK\x03\x04',
            content_type=(
                'application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet'
            ),
        )

        r = _respuesta_tras_el_middleware(descarga)

        self.assertEqual(r.headers.get('Cache-Control'), 'no-store')
