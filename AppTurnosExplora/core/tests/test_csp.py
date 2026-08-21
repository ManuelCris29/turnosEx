"""
La Content-Security-Policy y su allowlist.

Una CSP falla en SILENCIO: si una plantilla pide un recurso de un origen que no
está en la lista, el navegador lo bloquea sin que el servidor dé error. No hay
500, no hay excepción, no hay test rojo — solo un aviso en la consola del
navegador que nadie mira. En producción eso se traduce en un calendario que no
abre o unos iconos que no cargan, y cuesta horas de diagnosticar.

Por eso la regla "al añadir un CDN, acuérdate de meterlo en settings.py" no puede
vivir en la memoria de nadie. `test_ninguna_plantilla_pide_un_origen_no_permitido`
la comprueba sola en cada push.

El otro test fija la decisión de haber retirado los CDN: no es limpieza
cosmética, es que si alguien los reintroduce sin darse cuenta, se entera aquí.

NOTA sobre 'unsafe-inline': está en `script-src` a propósito y no es un pendiente.
El razonamiento completo está en el bloque de comentarios de `config/settings.py`,
justo encima de CONTENT_SECURITY_POLICY. En resumen: quitarlo obliga a reescribir
más de 90 plantillas (los nonces no cubren `onclick=` ni `style=`) y no cerraría
ninguna amenaza viva.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase

BASE = Path(settings.BASE_DIR)

# Orígenes que aparecen en plantillas y NO son recursos que el navegador cargue:
# enlaces de documentación, ejemplos dentro de comentarios, o el propio sitio.
IGNORAR = {'https://www.w3.org'}


def _origenes_permitidos():
    """Todo lo que la política admite, sin las palabras clave entre comillas."""
    permitidos = set()
    for valores in settings.CONTENT_SECURITY_POLICY['DIRECTIVES'].values():
        for v in valores:
            if v.startswith('http'):
                permitidos.add(v)
    return permitidos


class CspTestCase(TestCase):
    def test_la_cabecera_se_emite_de_verdad(self):
        """
        Comprueba la CABECERA, no el diccionario de settings. Un ajuste bien
        escrito pero con el middleware fuera de MIDDLEWARE no protege nada, y
        leer settings.py no lo detectaría.
        """
        r = self.client.get('/')

        csp = r.headers.get('Content-Security-Policy', '')
        self.assertIn("default-src 'self'", csp)
        self.assertIn("frame-ancestors 'none'", csp)

    def test_ya_no_se_permite_ningun_cdn_retirado(self):
        """Los cuatro se autohospedan en static/plugins/ desde la migración."""
        r = self.client.get('/')
        csp = r.headers.get('Content-Security-Policy', '')

        for cdn in ('jsdelivr', 'cdnjs', 'ionicframework', 'unpkg'):
            self.assertNotIn(cdn, csp, f'{cdn} volvió a la política')

    def test_la_politica_de_observacion_ya_no_se_publica(self):
        """
        La report-only sirvió para migrar sin romper nada. Terminada la
        migración, dejarla puesta solo duplica cabeceras y confunde a quien la
        lea creyendo que aún hay algo en observación.
        """
        r = self.client.get('/')

        self.assertNotIn('Content-Security-Policy-Report-Only', r.headers)

    def test_ninguna_plantilla_pide_un_origen_no_permitido(self):
        """
        El test que de verdad protege: recorre las plantillas buscando URLs
        externas y exige que cada origen esté en la allowlist.

        Si alguien añade un <script src="https://cdn-nuevo/..."> y olvida
        settings.py, esto se pone rojo en el push en vez de romperse callado en
        producción.
        """
        permitidos = _origenes_permitidos()
        infractores = {}

        for html in BASE.rglob('*.html'):
            # `scripts/` son pruebas manuales sueltas, no se sirven a nadie.
            if 'scripts' in html.parts or 'node_modules' in html.parts:
                continue
            texto = html.read_text(encoding='utf-8', errors='ignore')
            for url in re.findall(r'https://[a-zA-Z0-9.-]+', texto):
                if url in IGNORAR or url in permitidos:
                    continue
                infractores.setdefault(url, []).append(
                    str(html.relative_to(BASE))
                )

        self.assertEqual(
            infractores, {},
            'Orígenes externos usados en plantillas pero ausentes de '
            'CONTENT_SECURITY_POLICY en settings.py. El navegador los '
            f'bloqueará sin dar error de servidor: {infractores}'
        )
