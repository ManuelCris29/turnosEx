#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

from django.core.management import execute_from_command_line


def _salida_tolerante():
    """Que un carácter decorativo no pueda TUMBAR un comando.

    La consola de Windows usa cp1252, que no sabe imprimir los símbolos con los que los
    comandos rotulan su salida (→, ⚠, ✅, 📅…). `self.stdout.write` acaba en un
    `sys.stdout.write` normal, así que uno solo de esos caracteres lanza
    UnicodeEncodeError y ABORTA el comando a media ejecución: `verificar_efecto_aplicado`
    moría al imprimir la primera solicitud descuadrada, y con él 8 comandos más de los 24
    (los de auditoría y reparación, justo los que se corren cuando algo va mal).

    Se cambia SOLO el manejo de errores, no el encoding: la consola sigue pintando en su
    codificación nativa lo que sí entiende, y lo que no sale como '?' en vez de reventar.
    Para verlos de verdad, `PYTHONIOENCODING=utf-8` sigue funcionando.

    Afecta únicamente a `manage.py`: el servidor de producción no pasa por aquí.
    """
    for stream in (sys.stdout, sys.stderr):
        # `reconfigure` solo existe en TextIOWrapper; si algo ya sustituyó el stream
        # (un runner, una captura de tests), se deja como está.
        if hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(errors='replace')
            except (ValueError, OSError):
                pass


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    _salida_tolerante()
    try:
        execute_from_command_line(sys.argv)
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc


if __name__ == '__main__':
    main()
