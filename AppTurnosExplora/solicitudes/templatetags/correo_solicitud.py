"""
Datos que el correo necesita CALCULAR, no solo leer de la solicitud.

Existe por un caso concreto: en un CT PERMANENTE las jornadas no están guardadas en
ninguna parte. El intercambio se resuelve día a día contra el estado real de "Mis
Turnos", así que para poder decirle al explorador *«tú pasas a PM y tu compañero a AM»*
hay que preguntárselo al servicio.

Por qué un template tag y no una clave más en el contexto: el parcial
`solicitudes/emails/_detalle_solicitud.html` lo incluyen SEIS correos distintos, cada
uno con su propio `render_to_string`. Meter el dato por contexto obligaría a acordarse
en los seis —y el que se olvidara no fallaría, mostraría un hueco en silencio, que es
exactamente la trampa que ya nos costó los rangos en blanco y el `site_url`. Con el tag,
el parcial se lo pide solo y no hay nada que recordar.

Uso::

    {% load correo_solicitud %}
    {% resumen_ct_permanente solicitud as ct %}
    {{ ct.dias }} · {{ ct.jornada_solicitante }} → {{ ct.jornada_receptor }}
"""
from django import template

register = template.Library()


@register.simple_tag
def resumen_ct_permanente(solicitud):
    """
    `{'dias', 'total', 'primera', 'jornada_solicitante', 'jornada_receptor'}` del CT
    permanente de esta solicitud.

    Las jornadas son las de HOY —las que cada uno tiene antes del cambio—, tomadas del
    primer día aplicable. El correo las presenta así, como el punto de partida del
    intercambio, porque es lo único que se puede afirmar con certeza en el momento de
    enviarlo: la solicitud aún no está aprobada.

    Devuelve las claves siempre, en `None` o vacías si no se pueden resolver, para que la
    plantilla caiga a la explicación genérica en vez de romperse.
    """
    from solicitudes.services.cambios_permanentes_helper import resumen_correo_ct_permanente

    return resumen_correo_ct_permanente(solicitud)
