"""
A dónde van los logs en cada entorno.

POR QUE EXISTE
`LOGGING` no tenia ni un test, y la decision que fija este fichero es facil de
revertir sin querer: basta que alguien "arregle" el fichero de log de produccion
por parecerle raro que no exista.

LA DECISION, en corto: en produccion se escribe SOLO por stdout.
El detalle esta en config/settings.py junto a LOG_A_FICHERO; el resumen es que
el fichero (a) desaparece al reiniciar la tarea porque no hay volumen montado,
(b) no se puede leer, porque en Fargate no hay maquina a la que entrar, y (c) se
corrompe, porque con --workers 3 tres procesos rotan a la vez.

POR QUE UN SUBPROCESO Y NO `importlib.reload`
La primera version de este fichero recargaba `config.settings` con ENVIRONMENT
cambiado. Funcionaba, pero recargar el modulo de settings sustituye sus globales
para TODO lo que venga despues en el mismo proceso, y con `pytest -n 4` eso es
una fuente de fallos fantasma que dependen del orden. Un subproceso cuesta un par
de segundos y no puede contaminar a nadie.
"""
import json
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase

# Lee del modulo de settings ya cargado los tres datos que interesan.
SONDA = (
    'import json, config.settings as s; '
    'print(json.dumps({'
    '"a_fichero": bool(s.LOG_A_FICHERO), '
    '"destinos": list(s._DESTINOS), '
    '"clases": [h.get("class","") for h in s.LOGGING["handlers"].values()]'
    '}))'
)


def _settings_con(entorno):
    """Carga config.settings en un proceso limpio con ese ENVIRONMENT."""
    import os
    env = dict(os.environ, ENVIRONMENT=entorno, DJANGO_SETTINGS_MODULE='config.settings')
    salida = subprocess.run(
        [sys.executable, '-c', SONDA],
        capture_output=True, text=True, env=env, cwd=str(settings.BASE_DIR),
    )
    assert salida.returncode == 0, f'no se pudo cargar settings: {salida.stderr[-500:]}'
    return json.loads(salida.stdout.strip().splitlines()[-1])


class DestinosDeLogTestCase(SimpleTestCase):

    def test_en_produccion_no_se_escribe_fichero(self):
        datos = _settings_con('production')

        self.assertFalse(datos['a_fichero'], 'produccion no debe escribir fichero de log')
        self.assertEqual(datos['destinos'], ['console'],
                         'en produccion el unico destino es stdout')

    def test_en_desarrollo_si_se_escribe_fichero(self):
        # Aqui el fichero si vale: es comodo poder abrirlo sin depender de la
        # consola donde corre runserver, y no hay ni rotacion ni CloudWatch.
        datos = _settings_con('development')

        self.assertTrue(datos['a_fichero'])
        self.assertIn('file', datos['destinos'])

    def test_nunca_se_usa_un_handler_con_rotacion(self):
        """
        RotatingFileHandler no es seguro entre procesos, y en este proyecto SIEMPRE
        hay varios escribiendo: runserver levanta dos y `pytest -n 4` cuatro. En
        Windows la rotacion reventaba con WinError 32 en CADA linea de log.
        """
        for entorno in ('production', 'development'):
            for clase in _settings_con(entorno)['clases']:
                self.assertNotIn('Rotating', clase,
                                 f'[{entorno}] {clase} rota ficheros: no es seguro '
                                 f'con varios procesos')

    def test_la_consola_esta_en_todos_los_loggers(self):
        # stdout es el unico destino que funciona en los dos entornos. Si algun
        # logger se quedara sin el, en produccion seria MUDO, y eso no se descubre
        # hasta que hace falta un log que no existe.
        from django.conf import settings as s

        self.assertIn('console', s.LOGGING['root']['handlers'])
        for nombre, cfg in s.LOGGING['loggers'].items():
            self.assertIn('console', cfg['handlers'], f'{nombre} no escribe en stdout')
