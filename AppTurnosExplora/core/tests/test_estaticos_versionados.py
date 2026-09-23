"""
Toda referencia a un estático tiene que llevar versión en la URL.

POR QUÉ ESTO ES UN TEST Y NO UNA NOTA EN EL README

`config/settings.py` fija `WHITENOISE_MAX_AGE = 31536000`: un año de caché para
los estáticos. Esa decisión NO es segura por sí sola — lo es únicamente porque
`static_v` añade `?v=<mtime>` a cada URL, de modo que un archivo modificado
cambia de URL y el navegador lo vuelve a pedir.

Si alguien escribe `{% static 'js/x.js' %}` a secas, o pega un
`href="/static/css/y.css"` a mano, esa URL queda FIJA y con caché de un año. El
archivo se congela en el navegador de cada empleado y ningún despliegue lo
actualiza. El fallo es especialmente desagradable porque:

  - No da error en el servidor: la página renderiza perfecta.
  - No se ve en desarrollo: con DEBUG=True WhiteNoise sirve con max-age=0.
  - No se ve al desplegar: el navegador del que despliega suele recargar duro.
  - Aparece semanas después, solo en los clientes que ya visitaron la página,
    y con síntomas absurdos (un JS viejo hablando con una vista nueva).

Es decir: la comprobación no puede vivir en la memoria de nadie ni en una
revisión de código. Vive aquí.

EXCEPCIONES
`templates/errors/_base_error.html` usa una ruta literal a propósito. Es la
plantilla de las páginas de error, deliberadamente autocontenida: se renderiza
cuando algo YA falló, con contexto vacío y sin poder dar por bueno nada del
resto del sistema (el razonamiento completo está en su propia cabecera). Su
único estático es el favicon, y un favicon viejo en una página de error no le
hace daño a nadie. Robustez gana a cache-busting.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

# Se leen de settings, no se escriben a mano: si algún día se añade un tercer
# directorio de plantillas, este test lo cubre solo. No es hipotético — al hacer
# este cambio, `core/login/template/` se quedó fuera de la primera pasada
# justamente por buscar únicamente en `templates/`.
DIRECTORIOS_DE_PLANTILLAS = [Path(d) for d in settings.TEMPLATES[0]['DIRS']]

# Rutas (relativas a BASE_DIR) que pueden saltarse la regla, con su motivo.
EXCEPCIONES = {
    'templates/errors/_base_error.html': (
        'página de error autocontenida a propósito: sin etiquetas de plantilla'
    ),
}

# `{% static '...' %}` pero NO `{% static_v '...' %}`.
STATIC_SIN_VERSION = re.compile(r'\{%\s*static\s+[\'"]')

# Un "/static/..." escrito directamente en un atributo del HTML.
RUTA_A_MANO = re.compile(r'[\'"]/static/')


def _plantillas():
    for carpeta in DIRECTORIOS_DE_PLANTILLAS:
        yield from carpeta.rglob('*.html')


class EstaticosVersionados(SimpleTestCase):
    def _infracciones(self, patron):
        base = Path(settings.BASE_DIR)
        encontradas = []
        for plantilla in _plantillas():
            relativa = plantilla.relative_to(base).as_posix()
            if relativa in EXCEPCIONES:
                continue
            for numero, linea in enumerate(
                plantilla.read_text(encoding='utf-8').splitlines(), start=1
            ):
                if patron.search(linea):
                    encontradas.append(f'{relativa}:{numero}: {linea.strip()}')
        return encontradas

    def test_ninguna_plantilla_usa_static_sin_version(self):
        infracciones = self._infracciones(STATIC_SIN_VERSION)
        self.assertEqual(
            infracciones,
            [],
            '\n\nHay estáticos referenciados con {% static %} en vez de '
            '{% static_v %}.\nCon WHITENOISE_MAX_AGE a un año, esas URLs no '
            'cambian nunca y el archivo se queda congelado en el navegador del '
            'empleado.\nCámbialas a {% static_v %} y añade '
            '{% load static_version %} en la plantilla:\n\n  '
            + '\n  '.join(infracciones)
            + '\n',
        )

    def test_ninguna_plantilla_escribe_la_ruta_static_a_mano(self):
        infracciones = self._infracciones(RUTA_A_MANO)
        self.assertEqual(
            infracciones,
            [],
            '\n\nHay rutas "/static/..." escritas a mano. No pasan por '
            '{% static_v %}, así que no llevan ?v= y con la caché de un año se '
            'congelan en el navegador.\nUsa {% static_v \'ruta/sin/el/prefijo\' %}:'
            '\n\n  ' + '\n  '.join(infracciones) + '\n',
        )

    def test_las_excepciones_siguen_existiendo(self):
        """Una excepción a una regla de seguridad tiene que caducar sola.

        Si el archivo se renombra o se borra, esta lista queda mintiendo y la
        siguiente persona hereda una exención que ya no protege nada.
        """
        base = Path(settings.BASE_DIR)
        for ruta in EXCEPCIONES:
            self.assertTrue(
                (base / ruta).exists(),
                f'{ruta} está en EXCEPCIONES pero ya no existe. '
                f'Bórralo de la lista.',
            )
