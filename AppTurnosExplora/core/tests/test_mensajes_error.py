"""
Tests del texto de error que se le muestra a una persona.

`str()` sobre un `ValidationError` devuelve su repr de lista, no el mensaje. Eso llegaba tal
cual a la pantalla del supervisor ("Error aplicando D FDS: ['Explorador Jessika no tiene
sala...']"), con corchetes y comillas de Python que no significan nada para quien lee.
"""
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from core.utils.mensajes_error import texto_de_error


class TextoDeErrorTest(SimpleTestCase):

    def test_validation_error_no_muestra_corchetes_ni_comillas(self):
        """El caso real que destapó el problema."""
        exc = ValidationError('Explorador Jessika no tiene sala asignada.')
        texto = texto_de_error(exc)
        self.assertEqual(texto, 'Explorador Jessika no tiene sala asignada.')
        self.assertNotIn('[', texto)
        self.assertNotIn("'", texto)

    def test_varios_mensajes_se_unen_legibles(self):
        exc = ValidationError(['Primer motivo.', 'Segundo motivo.'])
        self.assertEqual(texto_de_error(exc), 'Primer motivo. Segundo motivo.')

    def test_errores_por_campo_tambien_se_aplanan(self):
        """La forma de diccionario es la que peor se lee con `str()`."""
        exc = ValidationError({'fecha': ['Fecha inválida.']})
        texto = texto_de_error(exc)
        self.assertIn('Fecha inválida.', texto)
        self.assertNotIn('{', texto)

    def test_otras_excepciones_conservan_su_texto(self):
        self.assertEqual(texto_de_error(ValueError('algo simple')), 'algo simple')

    def test_excepcion_sin_mensaje_no_revienta(self):
        self.assertEqual(texto_de_error(ValueError()), '')
