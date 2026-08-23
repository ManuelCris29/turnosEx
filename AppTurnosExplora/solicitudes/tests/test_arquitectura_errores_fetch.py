"""
Trinquete: una respuesta HTTP con error NO puede parsearse como si fueran datos.

EL FALLO QUE CIERRA
`fetch` no lanza ante un 404 ni ante un 500: solo lanza si se cae la red. Asi que
esto, que es el patron que habia repetido por todo el frontend...

    fetch(url)
      .then(r => r.json())          <- un 404 pasa por aqui tan tranquilo
      .then(d => pintar(d.turno))   <- d.turno es undefined: se pinta vacio
      .catch(() => mostrarError())  <- NUNCA se ejecuta

...dejaba la pantalla en blanco en vez de avisar. Lo llamativo es que el aviso YA
estaba escrito en el .catch de cada sitio: solo que no habia forma de llegar a el.

Medido cuando se arreglo (73 llamadas fetch en el proyecto):

    comprueban .ok ................................. 15
    tienen .catch pero NO comprobaban .ok .......... 45
        de esas, leen el cuerpo del error a proposito .. 4   (no se tocan:
            muestran el mensaje del servidor, y lanzar lo perderia)
        de forma uniforme `.then(r => r.json())` ...... 26   <- ARREGLADAS
        heterogeneas (await, Promise.all, sueltas) .... 15   <- pendientes

Este fichero fija las 26 y vigila que las 15 restantes no crezcan.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

JS = Path(settings.BASE_DIR) / 'static' / 'js'
UNIFORME = re.compile(r'\.then\(\s*(\w+)\s*=>\s*\1\.json\(\)\s*\)')
LEE_ERROR = re.compile(
    r'data\.error|\.error\s*\)|data\.success\s*===?\s*false|!\s*data\.success|d\.error|res\.error')


def _sitios_sin_guarda():
    """Llamadas fetch con manejo de error que NO miran el codigo de estado."""
    uniformes, heterogeneas = [], []
    for fichero in sorted(JS.rglob('*.js')):
        if 'utils/' in fichero.as_posix():
            continue
        lineas = fichero.read_text(encoding='utf-8', errors='replace').splitlines()
        for i, linea in enumerate(lineas):
            if 'fetch(' not in linea:
                continue
            bloque = '\n'.join(lineas[i:i + 45])
            contexto = '\n'.join(lineas[max(0, i - 12):i + 45])
            if re.search(r'\.ok\b', bloque):
                continue
            if not re.search(r'\.catch\s*\(|try\s*\{', contexto):
                continue
            if LEE_ERROR.search(bloque):
                continue
            donde = f'{fichero.relative_to(JS).as_posix()}:{i + 1}'
            es_multiple = re.search(r'Promise\.all', '\n'.join(lineas[max(0, i - 6):i + 6]))
            if es_multiple or re.search(r'await\s+fetch', linea):
                heterogeneas.append(donde)
            elif any(UNIFORME.search(x) for x in lineas[i:i + 45]):
                uniformes.append(donde)
            else:
                heterogeneas.append(donde)
    return uniformes, heterogeneas


class ErroresHttpNoSeParseanComoDatosTestCase(SimpleTestCase):

    def test_ninguna_llamada_uniforme_se_queda_sin_comprobar_el_estado(self):
        """
        La forma `.then(r => r.json())` es la mayoritaria y se arreglo entera.
        Que vuelva a aparecer sin guarda significa que alguien copio el patron
        viejo: aqui se le avisa, con el fichero y la linea.
        """
        uniformes, _ = _sitios_sin_guarda()

        self.assertEqual(
            uniformes, [],
            'Estas llamadas parsearian un 404/500 como si fueran datos. Añade la '
            'guarda antes de .json():\n    '
            "if (!r.ok) throw new Error('HTTP ' + r.status);\n"
            'Sitios: ' + ', '.join(uniformes))

    def test_las_heterogeneas_pendientes_no_crecen(self):
        """
        TRINQUETE, no meta. Quedan llamadas con `await fetch`, `Promise.all` o
        formas sueltas que no se tocaron: cada una necesita mirarse a mano porque
        el arreglo no es el mismo, y hacerlo a ciegas sobre solicitar_doblada.js
        -3200 lineas sin red de pruebas de DOM- es justo lo que no se quiere.

        Este numero debe BAJAR con el tiempo. Si sube, es que se añadio codigo
        nuevo con el fallo viejo.
        """
        _, heterogeneas = _sitios_sin_guarda()

        self.assertLessEqual(
            len(heterogeneas), 15,
            'Han aparecido llamadas nuevas que ignoran el codigo de estado:\n  '
            + '\n  '.join(heterogeneas))
