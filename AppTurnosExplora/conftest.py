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


def pytest_addoption(parser):
    parser.addoption(
        '--dias-en-el-futuro', action='store', type=int, default=0, metavar='N',
        help='Corre la suite como si hoy fuese dentro de N días, para descubrir tests '
             'que caducan solos. Ver el docstring de conftest.py.',
    )


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
