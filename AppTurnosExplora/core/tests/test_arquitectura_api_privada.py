"""
Invariante de arquitectura: NINGÚN módulo de producción importa un nombre
PRIVADO de otro módulo.

Por qué existe este test
------------------------
Un nombre con guion bajo es un contrato: «esto es un detalle interno, puedo
cambiarlo sin avisar». Cuando otro módulo lo importa, el contrato se rompe en
silencio — el autor del módulo cree que puede refactorizar libremente, y en
realidad tiene consumidores que no ve.

La auditoría de agosto de 2026 encontró **10 fugas de este tipo**, casi todas
saliendo de `solicitudes/services/ct_permanente_helper.py` y cruzando incluso
fronteras de app (`empleados/services/indicadores_service.py` importaba
`_es_festivo`). Nueve símbolos eran API pública de facto y se promovieron a
nombres públicos; dos re-exportaciones en `empleados/views/__init__.py` no las
consumía nadie y se retiraron.

El problema no era ninguna de las diez en particular: era que **nada lo
vigilaba**. Este test es esa vigilancia. Si vuelve a aparecer una fuga, falla
aquí y no tres refactorizaciones más tarde.

Qué hacer si este test falla
----------------------------
Hay exactamente dos salidas legítimas, y elegir bien importa:

1. **El símbolo es API pública de facto** (lo consume otro módulo a propósito):
   quítale el guion bajo. El nombre debe decir la verdad sobre quién lo usa.
2. **El consumidor no debería estar llamándolo**: arregla el consumidor, o
   expón una función pública que dé lo que necesita sin destapar el interior.

Añadir el caso a una lista de excepciones NO es la tercera salida. Si algún día
hiciera falta de verdad, documenta el porqué junto a la entrada.

Alcance
-------
Solo código de PRODUCCIÓN. Los tests quedan fuera a propósito: una prueba de
caja blanca que llama a una función interna para fijar su comportamiento es una
técnica válida, no una fuga de arquitectura.

Se comprueba `from modulo import _nombre`. NO se marca
`from modulo import publico as _alias`: ahí lo importado es un nombre público y
el guion bajo solo señala «local a este archivo», que es una convención sana y
usada en el proyecto (`from datetime import timedelta as _td`).
"""
import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

# Carpetas que no son código de producción de este proyecto.
CARPETAS_EXCLUIDAS = {
    'migrations',      # generado por Django
    'tests',           # caja blanca legítima (ver docstring)
    'integration_tests',
    'scripts',         # herramientas que un admin ejecuta a mano; no se despliegan
    'venvturnos',
    'staticfiles',
    '__pycache__',
}


def _es_privado(nombre: str) -> bool:
    """`_x` sí; `__init__`/`__all__` no (dunder = protocolo de Python, no un privado)."""
    return nombre.startswith('_') and not nombre.startswith('__')


def _recorrer_modulos_de_produccion():
    raiz = Path(settings.BASE_DIR)
    for ruta in raiz.rglob('*.py'):
        partes = set(ruta.relative_to(raiz).parts)
        if partes & CARPETAS_EXCLUIDAS or any(p.startswith('.') for p in partes):
            continue
        yield ruta


def _buscar_fugas():
    fugas = []
    raiz = Path(settings.BASE_DIR)
    for ruta in _recorrer_modulos_de_produccion():
        try:
            arbol = ast.parse(ruta.read_text(encoding='utf-8'))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - no debería ocurrir
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.ImportFrom):
                continue
            for alias in nodo.names:
                # `import publico as _alias` NO es una fuga: lo importado es público.
                if _es_privado(alias.name) and alias.asname is None:
                    fugas.append(
                        f"{ruta.relative_to(raiz).as_posix()}:{nodo.lineno}  "
                        f"from {nodo.module or '.'} import {alias.name}"
                    )
    return fugas


class ApiPrivadaNoCruzaModulosTest(SimpleTestCase):
    def test_ningun_modulo_de_produccion_importa_un_privado_de_otro(self):
        fugas = _buscar_fugas()
        self.assertEqual(
            fugas, [],
            "Un módulo de producción importa un nombre privado de otro módulo.\n"
            "Lee la cabecera de este archivo: o el símbolo es público de facto y hay\n"
            "que quitarle el guion bajo, o el consumidor no debería llamarlo.\n\n"
            + "\n".join(fugas)
        )
