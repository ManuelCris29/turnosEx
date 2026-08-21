"""
Trinquete: el reparto por tipo de solicitud vive en las estrategias.

La Fase 2 sacó de la base de código las cadenas `if tipo == 'DOBLADA': … elif …`
que había en la cancelación, el detalle, el parser, el snapshot y el helper de
fechas. Cada una obligaba a tocar cinco sitios para añadir un tipo, y olvidarse
de uno no daba error: daba un comportamiento silenciosamente incompleto.

Nada impide que la próxima urgencia reintroduzca una. Este test lo impide: falla
si aparece una comparación NUEVA contra un nombre de tipo fuera de
`services/strategies/`.

POR QUÉ UN TRINQUETE Y NO CERO ABSOLUTO
Quedan cuatro, y no son la misma cosa que las migradas. Aquellas calculaban una
respuesta de negocio distinta por tipo —justo lo que una estrategia hace mejor—.
Éstas ENRUTAN a un flujo entero distinto (dos solicitudes atómicas que solo
tienen sentido juntas, un alta multi-compañero) o encienden una bandera de
pantalla. Meterlas dentro supondría que una estrategia decida qué orquestación
ejecutar, que no es mejor que esto: sería la misma dependencia, escondida.

Así que se congelan como base conocida. La lista solo puede MENGUAR: si migras
una, quita su línea de aquí y el test seguirá pasando. Si añades una, falla.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR)

NOMBRES_DE_TIPO = ['CT PERMANENTE', 'DOBLADA PERMANENTE', 'CAMBIO DESCANSO',
                   'D FDS', 'DOBLADA', 'CT']

# Comparación contra el nombre de un tipo: `tipo_nombre == 'DOBLADA'`,
# `solicitud.tipo_cambio.nombre == "CT"`, y sus variantes con `!=` o `in (...)`.
PATRON = re.compile(
    r'\b(?:tipo|nombre)[a-zA-Z_.]*\s*(?:==|!=)\s*[\'"](' + '|'.join(NOMBRES_DE_TIPO) + r')[\'"]'
)

APPS = ('solicitudes', 'turnos', 'permisos', 'empleados', 'core')

# Base conocida, congelada el 2026-08-21. Formato: 'ruta/relativa.py'.
# Solo puede menguar. Cada una lleva por qué sigue ahí.
PERMITIDAS = {
    # Enruta a flujos de orquestación completos, no calcula una regla de negocio:
    #   :95  precalcula las fechas candidatas antes de existir la solicitud
    #   :637 alta multi-compañero, con su propio manejo de errores por bucle
    #   :658 dos solicitudes (AM y PM) que solo tienen sentido juntas y atómicas
    'solicitudes/services/solicitud_orchestrator.py': 3,
    # Bandera de presentación para la plantilla, no una decisión de negocio.
    'solicitudes/views/reprogramacion_views.py': 1,
    # DEUDA RECONOCIDA, y la única de esta lista que SÍ debería migrar algún día.
    # `_mitad_pago` decide cuánto día libera un pago según el tipo: DOBLADA mira
    # jornada_pago_sabado/jornada_cubre_en_pago, mientras D FDS y los intercambios
    # liberan siempre el día completo. Es exactamente una regla de negocio por tipo.
    # Se queda por ahora porque vive dentro de una función anidada muy acoplada al
    # orden de `DobladaPagoService.aplicar_doblada_pago`, y moverla es un refactor
    # con su propia red de pruebas, no un cambio de sitio.
    'solicitudes/services/descanso_solicitud_service.py': 1,
}

# Los comandos de mantenimiento se excluyen como categoría: son herramientas de un
# solo propósito ('corregir_doblada', 'verificar_doblada'), y su comparación no
# REPARTE entre tipos —se NIEGA a actuar sobre lo que no es su tipo—. Añadir un
# tipo nuevo no obliga a tocarlas: la guarda sigue siendo correcta tal cual.
EXCLUIR_CARPETAS = ('tests', 'migrations', 'strategies', 'commands')


def _es_comentario(linea):
    return linea.lstrip().startswith('#')


class DispatchPorTipoTestCase(SimpleTestCase):
    def _hallazgos(self):
        encontrados = {}
        for app in APPS:
            for py in (BASE / app).rglob('*.py'):
                # `strategies` es precisamente el sitio donde esto SÍ va.
                if any(c in py.parts for c in EXCLUIR_CARPETAS):
                    continue
                for linea in py.read_text(encoding='utf-8', errors='ignore').splitlines():
                    if _es_comentario(linea):
                        continue
                    if PATRON.search(linea):
                        rel = py.relative_to(BASE).as_posix()
                        encontrados[rel] = encontrados.get(rel, 0) + 1
        return encontrados

    def test_no_aparecen_cadenas_nuevas_de_reparto_por_tipo(self):
        hallazgos = self._hallazgos()

        nuevas = {
            ruta: n for ruta, n in hallazgos.items()
            if n > PERMITIDAS.get(ruta, 0)
        }

        self.assertEqual(
            nuevas, {},
            'Comparación contra un nombre de tipo fuera de services/strategies/. '
            'Añadir un tipo obligaría a acordarse de tocar también aquí, y olvidarlo '
            'no da error: da un comportamiento incompleto en silencio. Muévelo a la '
            'estrategia correspondiente. Si de verdad debe quedarse (enrutado a un '
            'flujo distinto, no una regla de negocio), documenta el porqué y súbelo '
            f'a PERMITIDAS en este archivo. Detectado: {nuevas}'
        )

    def test_la_base_congelada_no_se_ha_quedado_obsoleta(self):
        """
        La otra mitad del trinquete. Si alguien migra una de las cuatro y no baja
        el número, la lista deja hueco para colar una nueva sin que nadie se entere
        — y el trinquete dejaría de apretar.
        """
        hallazgos = self._hallazgos()

        for ruta, esperadas in PERMITIDAS.items():
            with self.subTest(archivo=ruta):
                self.assertEqual(
                    hallazgos.get(ruta, 0), esperadas,
                    f'{ruta} ya no tiene {esperadas} comparaciones. Si migraste alguna, '
                    'baja el número en PERMITIDAS (o quita la entrada si llegó a cero).'
                )
