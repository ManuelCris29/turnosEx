"""
Template tag `static_v`: igual que `{% static %}` pero añade `?v=<mtime>`
(la fecha de última modificación del archivo) como parámetro de versión.

Esto fuerza al navegador a descargar la última versión del archivo cada vez que
lo editamos (cache-busting automático), sin tener que cambiar nada a mano ni
recargar con Ctrl+Shift+R. Si el archivo no cambia, la URL no cambia y el
navegador sigue usando su caché (rápido).

Uso en plantillas:

    {% load static_version %}
    <script src="{% static_v 'js/cambio-turno/solicitar_doblada.js' %}"></script>
"""
import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    url = static(path)
    absolute = finders.find(path)
    if absolute and os.path.exists(absolute):
        try:
            mtime = int(os.path.getmtime(absolute))
            separador = '&' if '?' in url else '?'
            return f"{url}{separador}v={mtime}"
        except OSError:
            pass
    return url
