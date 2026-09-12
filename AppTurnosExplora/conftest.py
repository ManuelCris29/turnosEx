"""
Configuración de pytest común a toda la suite.

VIAJE EN EL TIEMPO: `--dias-en-el-futuro=N`
-------------------------------------------
Corre la suite entera como si hoy fuese dentro de N días:

    pytest --dias-en-el-futuro=90

POR QUÉ EXISTE
--------------
Esta suite tiene una clase de fallo que el CI no puede ver: el test que fija en el
código una fecha que solo es válida "por ahora". Pasa en verde durante semanas y
revienta un día cualquiera sin que nadie haya tocado nada.

Ocurrió tres veces a la vez, y las tres con una causa distinta:

  - `test_pago_parcial_pdh` escribió `2026-08` porque entonces era el mes abierto.
    Al llegar septiembre, agosto pasó a estar vencido y solo se puede pagar el mes en
    curso: 15 pruebas de PAGO PARCIAL fallaron por una regla que ninguna probaba.
  - `test_pago_horas` usaba `hoy - 2 días`, que los primeros días del mes cae en el
    mes anterior. Habría fallado al principio de CUALQUIER mes.
  - `test_d_fds` fabricaba un día de fixture como `cesión + 7 días`, que según el
    calendario caía justo encima del día bajo prueba.

Un análisis estático no los distingue: hay 333 fechas literales del año en curso en
la suite y casi todas son legítimas —anclas antiguas deliberadas, o el reloj inyectado
a propósito, como en `test_apertura_anio`—. Lo que separa a las buenas de las bombas
no es la fecha escrita, sino si el código bajo prueba la compara con el reloj real.
Eso solo se ve moviendo el reloj.

CÓMO SE USA
-----------
No corre por defecto: mover el reloj hace fallar tests que son correctos hoy, y esos
fallos son el HALLAZGO, no un error de la corrida. Se lanza a propósito —antes de un
despliegue, o al tocar sanciones, deudas y vencimientos— y lo que salga se lee como
"esto se romperá solo dentro de N días".

Los servicios de este proyecto ya aceptan un `hoy` inyectable (`deudas_pendientes`,
`esta_vencido`, `anio_objetivo`, `situacion`…). Esa —y no congelar el reloj— es la
forma correcta de escribir un test nuevo: `--dias-en-el-futuro` es el detector, la
inyección es el arreglo.

ELEGIR EL DESFASE (medido, no supuesto)
---------------------------------------
El destino importa tanto como el hecho de viajar. Medido el 2026-09-02:

  +45 días (mediados de octubre) — mes corriente cualquiera. Es el desfase para buscar
    tests que caducan solos, sin más.

  +90 días — cayó en el 1 de DICIEMBRE y salieron 149 fallos, pero la mayoría no son
    tests podridos: el 1-dic es justo el día en que `AperturaAnioMiddleware` empieza a
    redirigir a CUALQUIER administrador a la pantalla de apertura mientras el año
    siguiente no esté planificado. Los tests de vistas de administración fallan en bloque
    porque la aplicación hace lo que debe. Es un resultado correcto y vale la pena verlo
    una vez —enseña qué le pasará a la operación en diciembre—, pero tapa lo demás.

O sea: para cazar tests caducos, un desfase que NO cruce el 1 de diciembre; para ensayar
el diciembre real, +90 y leerlo sabiendo lo de arriba.
"""
import datetime

import pytest


def pytest_addoption(parser):
    parser.addoption(
        '--dias-en-el-futuro', action='store', type=int, default=0, metavar='N',
        help='Corre la suite como si hoy fuese dentro de N días, para descubrir tests '
             'que caducan solos. Ver el docstring de conftest.py.',
    )
    parser.addoption(
        '--anio-planificado', action='store_true',
        help='Corre como si el año siguiente ya estuviera planificado. Se usa junto con '
             '--dias-en-el-futuro=90 para el ensayo de diciembre. Ver conftest.py.',
    )


@pytest.fixture(autouse=True, scope='session')
def _anio_planificado(request):
    """El ensayo de diciembre con los deberes hechos.

    A +90 días la suite cae en el 1 de diciembre y se ponen rojos ~149 tests de vistas
    de administración: `AperturaAnioMiddleware` redirige a la pantalla de apertura
    mientras el año siguiente no esté planificado. Correcto, pero deja una pregunta sin
    responder — ¿son TODOS por la puerta, o hay algo más escondido detrás?

    Para contestarla hay que correr esa misma fecha con el año ya planificado. Sembrar
    los datos reales del checklist en cada test no es viable: `Jornada.nombre` es único
    y casi todos los tests crean AM/PM en su `setUp`, así que las filas globales
    chocarían y añadirían cientos de fallos nuevos, justo el ruido que se quiere evitar.

    Se simula entonces la CONDICIÓN, que es lo único que el middleware consulta:
    `situacion()` devuelve 'nada' en cuanto `completo(anio)` es cierto, sin mirar la
    fecha. Que completar el checklist de verdad —con sus cinco ítems y sus filas en la
    base— haga que `completo()` sea cierto y la puerta se abra, lo prueba con datos
    reales `turnos/tests/test_apertura_anio_puerta_se_abre.py`. Este atajo mide; aquel
    test demuestra.

    Efecto secundario esperado: los tests de `test_apertura_anio` que comprueban que la
    puerta CIERRA fallan bajo esta bandera. Es coherente —se les está diciendo que el
    año está listo— y sirve de control de que la bandera hace algo.
    """
    if not request.config.getoption('--anio-planificado'):
        yield
        return

    from unittest import mock

    from turnos.services.apertura_anio_service import AperturaAnioService

    with mock.patch.object(AperturaAnioService, 'completo',
                           staticmethod(lambda anio: True)):
        yield


@pytest.fixture(autouse=True)
def _cache_limpia():
    """
    Limpia la caché de Django ANTES de cada test.

    Varias piezas cachean por clave versionada e invalidan por señal al ESCRIBIR
    (turnos/signals.py, empleados/signals.py, solicitudes/signals.py) — correcto en
    producción, donde una transacción que revierte es la excepción. Pero cada test de
    esta suite corre dentro de una transacción que SIEMPRE revierte al terminar
    (`TestCase`), y una escritura revertida no dispara ninguna señal: el registro
    desaparece de la base, pero la caché que esa escritura invalidó o pobló sigue viva
    para el SIGUIENTE test del mismo proceso de pytest-xdist. Un test que crea, por
    ejemplo, un `DiaEspecial` en una fecha que otro test —más adelante, por
    coincidencia— vuelve a usar, heredaría ese valor cacheado apuntando a datos que ya
    no existen (así se cazó: dos tests de `test_cierre_solicitudes.py` fallaban según
    el orden en que pytest-xdist los repartiera entre workers).

    Limpiar antes de CADA test restaura la misma garantía que ya da la base de datos:
    cada test empieza desde cero, sin depender de que cada archivo se acuerde de
    llamar `cache.clear()` en su propio `setUp` (varios ya lo hacían por su cuenta;
    esto lo vuelve automático para toda la suite).
    """
    from django.core.cache import cache
    cache.clear()


def pytest_configure(config):
    dias = config.getoption('--dias-en-el-futuro')
    if not dias:
        return

    # Se importa aquí y no arriba: `freezegun` solo hace falta cuando se pide el viaje,
    # así que la suite normal no depende de que esté instalado.
    from freezegun import freeze_time

    destino = datetime.datetime.now() + datetime.timedelta(days=dias)
    # `tick=True`: el reloj queda adelantado pero SIGUE corriendo. Congelarlo del todo
    # rompe cosas que no tienen que ver con el calendario (medidas de duración, TTLs de
    # caché) y ensuciaría el resultado con fallos que no son el hallazgo que se busca.
    config._reloj_futuro = freeze_time(destino, tick=True)
    config._reloj_futuro.start()
    print(f'\n[reloj] Corriendo como si hoy fuese {destino.date()} (+{dias} días).')


def pytest_unconfigure(config):
    reloj = getattr(config, '_reloj_futuro', None)
    if reloj is not None:
        reloj.stop()
