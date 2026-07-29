"""
Runner de tests del proyecto.

Único cambio respecto al de Django: NUNCA pregunta por consola.

Cuando una corrida de tests muere a medias (se cancela, se cierra la terminal, se mata el
proceso), la base `test_<DB_NAME>` queda huérfana. En la siguiente corrida Django la encuentra
y, por defecto, PREGUNTA si puede borrarla:

    Type 'yes' if you would like to try deleting the test database, or 'no' to cancel:

Si nadie puede escribir "yes" —CI, un script, una herramienta— el proceso se queda esperando o
revienta con `EOFError: EOF when reading a line`. Y como la base huérfana sigue ahí, el intento
siguiente vuelve a atascarse igual: un círculo del que solo se sale a mano.

Con `interactive=False` la respuesta es siempre la de por defecto (borrar y recrear), que es lo
que se quiere en el 100% de los casos: esa base es desechable, se crea al empezar y se destruye
al terminar. La base REAL nunca se toca — Django solo administra la que lleva el prefijo `test_`.

Equivale a pasar `--noinput` en cada ejecución, pero sin depender de que alguien se acuerde.
Para volver al comportamiento interactivo en un caso puntual: `manage.py test --no-input=False`
no existe; se quita temporalmente `TEST_RUNNER` de settings.
"""
from django.test.runner import DiscoverRunner


class NoInputDiscoverRunner(DiscoverRunner):
    """DiscoverRunner que fuerza `interactive=False` (ver módulo)."""

    def __init__(self, *args, **kwargs):
        kwargs['interactive'] = False
        super().__init__(*args, **kwargs)
