"""
Trinquete: los correos heredan de la base, el logo viaja DENTRO y los enlaces son absolutos.

EL FALLO QUE CIERRA
Un correo se lee fuera del sitio, así que nada relativo funciona ahí dentro. Eso da
dos invariantes que se rompen en SILENCIO —el correo sale igual, sin excepción ni
log, y la suite pasa entera—:

1. El logo. La base lo pide como `cid:logo-swalp` y quien lo adjunta es
   `EmailOutboxService._intentar`. Si el <img> volviera a una URL remota, no se vería:
   con SITE_URL=http://127.0.0.1:8000 el cliente resuelve 127.0.0.1 contra la máquina
   de QUIEN LEE, y aun con el dominio público Gmail y Outlook bloquean las remotas.

2. `site_url` en el contexto. Los botones «Ver en el sistema» construyen su enlace con
   él. `render_to_string` se llama SIN `request` en los diez sitios que mandan correo,
   y sin request los context processors no corren: hay que pasarlo en el diccionario o
   el botón apunta a un `/solicitudes/` sin host, que en un correo es un enlace muerto.
   Ya ocurrió: cinco de los nueve contextos de `email_service.py` no lo traían.
"""
import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

RAIZ = Path(settings.BASE_DIR)
PLANTILLAS = RAIZ / 'templates'

BASE = 'emails/base_email.html'

# Los once correos HTML del sistema, relativos a templates/.
CORREOS = [
    'solicitudes/emails/solicitud_receptor.html',
    'solicitudes/emails/solicitud_supervisor.html',
    'solicitudes/emails/solicitud_supervisor_receptor.html',
    'solicitudes/emails/confirmacion_solicitud.html',
    'solicitudes/emails/aprobacion_receptor.html',
    'solicitudes/emails/aprobacion_supervisor.html',
    'solicitudes/emails/rechazo_receptor.html',
    'solicitudes/emails/rechazo_supervisor.html',
    'solicitudes/emails/cancelacion_solicitud.html',
    'permisos/emails/solicitud_permiso.html',
    'registration/aviso_password_cambiada.html',
]

# Módulos que envían correo. Se escanean enteros: si mañana aparece otro
# `render_to_string` de un correo aquí dentro, entra solo en la comprobación.
MODULOS_QUE_ENVIAN = [
    'solicitudes/services/email_service.py',
    'permisos/services/permiso_service.py',
    'core/services/aviso_seguridad_service.py',
]


def _es_plantilla_de_correo(ruta):
    """Una plantilla es de correo si está bajo un `emails/` o es uno de los once."""
    return '/emails/' in ruta or ruta.startswith('emails/') or ruta in CORREOS


class HerenciaDeLaBaseTest(SimpleTestCase):

    def test_los_once_correos_heredan_de_la_base(self):
        for correo in CORREOS:
            with self.subTest(correo=correo):
                fichero = PLANTILLAS / correo
                self.assertTrue(fichero.exists(), f'{correo} no existe')
                primera = fichero.read_text(encoding='utf-8').lstrip().splitlines()[0]
                self.assertIn(
                    BASE, primera,
                    f"{correo} no extiende '{BASE}'. Sin la base pierde cabecera, "
                    f"marca y pie, y deja de parecerse al resto de correos."
                )

    def test_la_base_pide_el_logo_incrustado_y_sin_texto_alternativo(self):
        base = (PLANTILLAS / BASE).read_text(encoding='utf-8')
        self.assertIn(
            'src="cid:logo-swalp"', base,
            'La base ya no pide el logo por cid. Si volvió a una URL remota, el logo '
            'no se verá: ni 127.0.0.1 resuelve en el cliente, ni Gmail carga remotas '
            'sin permiso del destinatario.'
        )
        self.assertIn(
            'alt=""', base,
            'El alt del logo debe ir vacío: con texto, cuando la imagen no se muestra '
            'se pinta «parque explora medellín» en rojo y partido dentro del recuadro.'
        )

    def test_el_outbox_incrusta_el_logo_que_pide_la_base(self):
        """La otra mitad del contrato del cid: que alguien adjunte de verdad esa parte."""
        from django.core.mail import EmailMultiAlternatives

        from solicitudes.services.email_outbox_service import _bytes_del_logo, _incrustar_logo

        self.assertIsNotNone(
            _bytes_del_logo(),
            'No se puede leer static/img/logo-explora-email.png: los correos saldrían '
            'con un hueco donde va la marca.'
        )
        html = '<html><body><img src="cid:logo-swalp"></body></html>'
        mensaje = EmailMultiAlternatives('a', 'texto', 'de@x.org', ['para@x.org'])
        mensaje.attach_alternative(html, 'text/html')
        _incrustar_logo(mensaje, html)

        construido = mensaje.message()
        self.assertEqual(construido.get_content_type(), 'multipart/related')
        cids = [p.get('Content-ID') for p in construido.walk() if p.get('Content-ID')]
        self.assertIn('<logo-swalp>', cids)

    def test_un_correo_sin_logo_no_se_convierte_en_related(self):
        """Adjuntar la imagen a quien no la referencia la dejaría como adjunto suelto."""
        from django.core.mail import EmailMultiAlternatives

        from solicitudes.services.email_outbox_service import _incrustar_logo

        html = '<p>sin logo</p>'
        mensaje = EmailMultiAlternatives('a', 'texto', 'de@x.org', ['para@x.org'])
        mensaje.attach_alternative(html, 'text/html')
        _incrustar_logo(mensaje, html)
        self.assertEqual(mensaje.attachments, [])
        self.assertEqual(mensaje.message().get_content_type(), 'multipart/alternative')


class ContextoConSiteUrlTest(SimpleTestCase):

    def _llamadas_a_correos(self, modulo):
        """Devuelve (nº de línea, ruta de plantilla, claves del contexto) por llamada."""
        arbol = ast.parse((RAIZ / modulo).read_text(encoding='utf-8'))
        llamadas = []
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            nombre = getattr(nodo.func, 'id', None) or getattr(nodo.func, 'attr', None)
            if nombre != 'render_to_string' or not nodo.args:
                continue
            plantilla = nodo.args[0]
            if not isinstance(plantilla, ast.Constant) or not isinstance(plantilla.value, str):
                continue
            if not _es_plantilla_de_correo(plantilla.value):
                continue
            claves = set()
            # El contexto puede ir posicional (`render_to_string(t, {...})`) o por
            # nombre; y puede ser un dict literal o una variable ya construida.
            candidatos = list(nodo.args[1:]) + [kw.value for kw in nodo.keywords]
            for candidato in candidatos:
                if isinstance(candidato, ast.Dict):
                    claves |= {
                        k.value for k in candidato.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    }
                elif isinstance(candidato, ast.Name):
                    # Contexto en una variable: se busca la clave en el módulo entero,
                    # que es lo más que puede afirmar un análisis estático.
                    claves |= {'site_url'} if "'site_url'" in (RAIZ / modulo).read_text(encoding='utf-8') else set()
            llamadas.append((plantilla.lineno, plantilla.value, claves))
        return llamadas

    def test_todo_contexto_de_correo_pasa_site_url(self):
        encontradas = 0
        for modulo in MODULOS_QUE_ENVIAN:
            for linea, plantilla, claves in self._llamadas_a_correos(modulo):
                encontradas += 1
                with self.subTest(modulo=modulo, linea=linea, plantilla=plantilla):
                    self.assertIn(
                        'site_url', claves,
                        f"{modulo}:{linea} renderiza {plantilla} sin 'site_url' en el "
                        f"contexto. El correo se enviará igual, pero SIN LOGO: "
                        f"render_to_string va sin request, así que los context "
                        f"processors no lo rellenan. Añade "
                        f"'site_url': settings.SITE_URL."
                    )
        # Si el escáner deja de encontrar llamadas, la prueba pasaría en vacío.
        self.assertGreaterEqual(
            encontradas, len(CORREOS),
            f'Solo se encontraron {encontradas} llamadas de correo y hay '
            f'{len(CORREOS)} plantillas: el escáner se quedó ciego.'
        )

class RangoDeVigenciaTest(SimpleTestCase):
    """
    Regresión: el rango de los dos tipos PERMANENTES salía en blanco.

    La causa es una trampa del filtro `add` de Django que no avisa de nada: si el
    ARGUMENTO es un objeto `date`, intenta `int(a)+int(b)`, luego `str + date`, se come
    el TypeError y devuelve CADENA VACÍA. Así,

        fecha_inicio|date:"d/m/Y"|add:" a "|add:fecha_fin|date:"d/m/Y"

    no daba "17/09/2026 a 24/09/2026" sino "". El correo salía, con el hueco donde iba
    el rango. Se arregla formateando las dos fechas antes, con {% with %}, para que
    `add` solo concatene cadenas.

    Se renderiza el parcial con objetos de pega (sin BD): lo que se vigila es la
    plantilla, no el modelo.
    """
    from datetime import date as _date

    class _Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

        def __getattr__(self, nombre):
            return ''

    def _solicitud(self, tipo, **relaciones):
        persona = self._Obj(nombre='RONAL', apellido='MORENO')
        otro = self._Obj(nombre='CRISTOBAL', apellido='MORENO')
        campos = dict(
            explorador_solicitante=persona, explorador_receptor=otro,
            tipo_cambio=self._Obj(nombre=tipo), fecha_cambio_turno=self._date(2026, 9, 17),
            comentario='', cambio_permanente=None, doblada_permanente=None,
        )
        campos.update(relaciones)   # la relación que traiga el caso pisa al None
        return self._Obj(**campos)

    def _detalle(self, solicitud):
        from django.template.loader import render_to_string
        return render_to_string('solicitudes/emails/_detalle_solicitud.html',
                                {'solicitud': solicitud})

    def test_ct_permanente_muestra_el_rango(self):
        detalle = self._Obj(fecha_inicio=self._date(2026, 9, 9), fecha_fin=self._date(2026, 9, 30))
        html = self._detalle(self._solicitud('CT PERMANENTE', cambio_permanente=detalle))
        self.assertIn('09/09/2026 a 30/09/2026', html,
                      'El rango de vigencia de CT PERMANENTE volvió a salir en blanco.')

    def test_ct_permanente_sin_fecha_fin_lo_dice(self):
        detalle = self._Obj(fecha_inicio=self._date(2026, 9, 9), fecha_fin=None)
        html = self._detalle(self._solicitud('CT PERMANENTE', cambio_permanente=detalle))
        self.assertIn('09/09/2026 (sin fecha fin)', html)

    def test_doblada_permanente_muestra_rango_y_dias(self):
        detalle = self._Obj(
            fecha_inicio=self._date(2026, 9, 17), fecha_fin=self._date(2026, 9, 24),
            dias_cesion_legible=lambda: 'Miércoles',
            dias_devolucion_legible=lambda: 'Lunes',
        )
        html = self._detalle(self._solicitud('DOBLADA PERMANENTE', doblada_permanente=detalle))
        self.assertIn('17/09/2026 a 24/09/2026', html,
                      'El rango de vigencia de DOBLADA PERMANENTE volvió a salir en blanco.')
        self.assertIn('Miércoles', html)
        self.assertIn('Lunes', html)

# La comprobación de comentarios `{# #}` de varias líneas vivía aquí, pero el fallo no es
# de los correos: cualquier plantilla lo sufre, y de hecho también se coló en cuatro
# pantallas. Se movió a core/tests/test_plantillas_comentarios.py, que escanea
# templates/ entero.


class DetallePermanenteTest(SimpleTestCase):
    """
    Lo que el explorador tiene que poder leer en los dos tipos PERMANENTES: no basta
    con «cede miércoles, devuelve martes» —eso no dice quién trabaja ni cuándo—.

    - DOBLADA PERMANENTE: quién dobla AM+PM y quién descansa, cada día, en el rango.
    - CT PERMANENTE: con qué jornada queda cada uno.
    """
    from datetime import date as _date

    class _Obj:
        def __init__(self, **kw):
            self.__dict__.update(kw)

        def __getattr__(self, nombre):
            return ''

    def _render(self, solicitud):
        from django.template.loader import render_to_string
        return render_to_string('solicitudes/emails/_detalle_solicitud.html',
                                {'solicitud': solicitud})

    def _solicitud(self, tipo, **relaciones):
        campos = dict(
            explorador_solicitante=self._Obj(nombre='RONAL', apellido='MORENO'),
            explorador_receptor=self._Obj(nombre='CRISTOBAL', apellido='GOMEZ'),
            tipo_cambio=self._Obj(nombre=tipo), fecha_cambio_turno=self._date(2026, 9, 17),
            comentario='', cambio_permanente=None, doblada_permanente=None,
        )
        campos.update(relaciones)
        return self._Obj(**campos)

    def test_doblada_permanente_dice_quien_dobla_y_quien_descansa(self):
        detalle = self._Obj(
            fecha_inicio=self._date(2026, 9, 17), fecha_fin=self._date(2026, 10, 24),
            dias_cesion_legible=lambda: 'Miércoles',
            dias_devolucion_legible=lambda: 'Martes, Viernes',
        )
        html = self._render(self._solicitud('DOBLADA PERMANENTE', doblada_permanente=detalle))
        self.assertIn('Cristobal dobla AM + PM y Ronal descansa', html)
        self.assertIn('Ronal dobla AM + PM y Cristobal descansa', html)
        self.assertIn('Martes, Viernes', html)

    def test_ct_permanente_dice_con_que_jornada_queda_cada_uno(self):
        from unittest.mock import patch

        detalle = self._Obj(fecha_inicio=self._date(2026, 9, 9), fecha_fin=self._date(2026, 9, 30))
        resumen = {'dias': 'Miércoles, Jueves', 'total': 5, 'primera': self._date(2026, 9, 9),
                   'jornada_solicitante': 'AM', 'jornada_receptor': 'PM'}
        with patch('solicitudes.services.cambios_permanentes_helper.resumen_correo_ct_permanente',
                   return_value=resumen):
            html = self._render(self._solicitud('CT PERMANENTE', cambio_permanente=detalle))
        self.assertIn('Ronal pasa a PM y Cristobal pasa a AM', html)
        self.assertIn('Miércoles, Jueves', html)
        self.assertIn('5 días entran en el rango', html)

    def test_ct_permanente_sin_jornadas_resolubles_explica_igual(self):
        """Si el estado real no da un par AM/PM, el correo no se queda mudo."""
        from unittest.mock import patch

        detalle = self._Obj(fecha_inicio=self._date(2026, 9, 9), fecha_fin=self._date(2026, 9, 30))
        resumen = {'dias': 'Miércoles', 'total': 0, 'primera': None,
                   'jornada_solicitante': None, 'jornada_receptor': None}
        with patch('solicitudes.services.cambios_permanentes_helper.resumen_correo_ct_permanente',
                   return_value=resumen):
            html = self._render(self._solicitud('CT PERMANENTE', cambio_permanente=detalle))
        self.assertIn('Cada uno toma la jornada del otro', html)
        self.assertIn('quien tiene AM pasa a PM', html)

