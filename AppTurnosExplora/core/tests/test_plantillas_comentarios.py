"""
Trinquete: un comentario de plantilla no puede acabar en la pantalla del usuario.

EL FALLO QUE CIERRA
`{# ... #}` de Django SOLO comenta si cabe en UNA línea. El lexer usa

    tag_re = re.compile(r"({%.*?%}|{{.*?}}|{#.*?#})")

sin `re.DOTALL`, así que `.` no cruza saltos de línea: un `{#` con salto dentro NO se
reconoce como token de comentario y sale **impreso tal cual** en el HTML. No hay error,
no hay aviso, y en local suele pasar desapercibido porque es texto suelto entre bloques.

Lo pagamos dos veces el mismo día: primero en cinco plantillas de correo —notas internas
de desarrollo enviadas al explorador— y luego en cuatro pantallas (el consolidado de
horas, la lista de notificaciones y el levantamiento de sanción). Para varias líneas el
tag correcto es `{% comment %}`.

Se escanea `templates/` ENTERO a propósito: el fallo no es de los correos, es de
cualquier plantilla, y quien escriba la próxima no tiene por qué conocer esta trampa.
"""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

PLANTILLAS = Path(settings.BASE_DIR) / 'templates'


class ComentariosDePlantillaTest(SimpleTestCase):

    def test_ninguna_plantilla_abre_un_comentario_que_no_cierra_en_la_misma_linea(self):
        culpables = []
        for fichero in sorted(PLANTILLAS.rglob('*.html')):
            for numero, linea in enumerate(
                    fichero.read_text(encoding='utf-8').splitlines(), 1):
                # Se mira lo que hay DESPUÉS de la apertura: `{# ... #}` completo en la
                # misma línea es correcto, y varios en una línea también.
                if '{#' in linea and '#}' not in linea.split('{#', 1)[1]:
                    culpables.append(f'{fichero.relative_to(PLANTILLAS)}:{numero}')
        self.assertEqual(
            culpables, [],
            'Estas plantillas abren un comentario {# que no cierra en su línea. Django '
            'NO lo comenta: lo IMPRIME en la página. Para varias líneas usa '
            '{% comment %}...{% endcomment %}. Sitios: ' + ', '.join(culpables)
        )
