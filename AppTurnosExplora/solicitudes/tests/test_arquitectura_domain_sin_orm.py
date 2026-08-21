"""
`solicitudes/domain/` no habla con la base de datos.

Es lo que hace útil a esa carpeta: reglas que se pueden leer, razonar y probar sin
levantar nada. `estado_machine.py` es el ejemplo — un diccionario de transiciones
válidas, comprobable en microsegundos y sin base de datos.

`bloqueo_partes.py` estaba ahí y no encajaba. La auditoría lo anotó como «sacar el
ORM del dominio», pero medido resultó ser al revés: no había ORM de más, había un
archivo mal colocado. Ese módulo ES una primitiva de bloqueo del motor —su razón
de existir es el `SELECT ... FOR UPDATE`— y todo lo que importa de él es específico
de MySQL. Se movió a `services/`, que es donde vive la infraestructura, sin tocar
una línea de su lógica.

Este test evita que la carpeta se vuelva a ensuciar. No es una regla de estilo: en
cuanto el dominio toca el ORM, deja de poder probarse aislado y las reglas de
negocio empiezan a necesitar una base de datos para responder «¿es válida esta
transición?».
"""
import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

DOMAIN = Path(settings.BASE_DIR) / 'solicitudes' / 'domain'

# Señales de que se está hablando con el motor de base de datos.
#
# `save` y `delete` NO están en la lista, y la omisión está medida, no supuesta.
# `estado_machine.transicionar` llama a `solicitud.save(...)`, pero sobre un objeto
# que RECIBE: no importa Django en ninguna línea. Se comprobó ejecutándolo con un
# objeto falso y sin Django configurado, y funciona entero —aplica sus reglas y
# rechaza las transiciones ilegales—, que es justamente la propiedad que esta
# carpeta debe conservar. Prohibirlo obligaría a partir la función en dos por una
# regla de estilo, sin ganar nada real.
#
# Lo que sí entra en la lista es lo que NO se puede sustituir por un doble: acceder
# a un manager, tomar un cerrojo o abrir una transacción exige el ORM de verdad.
SOSPECHOSOS = ('objects', 'select_for_update', 'atomic', 'bulk_create',
               'raw', 'cursor')


class DomainSinOrmTestCase(SimpleTestCase):
    def test_ningun_modulo_del_dominio_usa_el_orm(self):
        infractores = {}

        for py in DOMAIN.glob('*.py'):
            arbol = ast.parse(py.read_text(encoding='utf-8'))
            for nodo in ast.walk(arbol):
                # `algo.objects`, `algo.save()`, `transaction.atomic()`…
                if isinstance(nodo, ast.Attribute) and nodo.attr in SOSPECHOSOS:
                    infractores.setdefault(py.name, set()).add(nodo.attr)
                # `from django.db import transaction`, `from x.models import Y`
                if isinstance(nodo, ast.ImportFrom) and nodo.module:
                    if 'django.db' in nodo.module or nodo.module.endswith('.models'):
                        infractores.setdefault(py.name, set()).add(nodo.module)

        self.assertEqual(
            {k: sorted(v) for k, v in infractores.items()}, {},
            'Un módulo de solicitudes/domain/ está hablando con la base de datos. '
            'El valor de esa carpeta es poder razonar y probar las reglas sin '
            'levantar nada; en cuanto entra el ORM, eso se pierde. Si lo que '
            'escribiste ES infraestructura (un cerrojo, una consulta), su sitio es '
            f'services/, como bloqueo_partes.py. Detectado: {infractores}'
        )

    def test_el_dominio_se_puede_importar_sin_django_configurado(self):
        """
        La comprobación de verdad, y la que manda sobre la anterior: buscar nombres
        es una aproximación, esto es la propiedad en sí. Si un módulo del dominio
        importa algo de Django que exija configuración, esto revienta.

        Es también lo que justifica tolerar el `solicitud.save()` de
        `estado_machine`: mientras este test pase, el dominio sigue siendo
        razonable y probable con un doble, que es lo único que se le pide.
        """
        import subprocess
        import sys

        modulos = [f'solicitudes.domain.{p.stem}' for p in DOMAIN.glob('*.py')
                   if p.stem != '__init__']
        guion = '; '.join(f'import {m}' for m in modulos)

        r = subprocess.run([sys.executable, '-c', guion],
                           capture_output=True, text=True, cwd=str(settings.BASE_DIR))

        self.assertEqual(
            r.returncode, 0,
            f'El dominio ya no se importa sin arrancar Django:\n{r.stderr}'
        )
