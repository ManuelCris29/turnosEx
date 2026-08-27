"""Tests del EmailService: remitente fijo + Reply-To y envío síncrono en tests."""
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from solicitudes.services.email_service import EmailService


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='SWALP <no-reply@parqueexplora.org>',
    EMAIL_SEND_ASYNC=False,
)
class EnviarEmailDesdeUsuarioTest(TestCase):
    def test_envia_desde_remitente_fijo_con_persona_en_reply_to(self):
        ok = EmailService._enviar_email_desde_usuario(
            subject='Prueba',
            message='cuerpo en texto plano',
            from_email='persona@empresa.org',
            recipient_list=['destino@empresa.org'],
            html_message='<p>cuerpo</p>',
        )

        self.assertTrue(ok)
        self.assertEqual(len(mail.outbox), 1)
        m = mail.outbox[0]
        # From SIEMPRE es el remitente fijo, no el de la persona.
        self.assertEqual(m.from_email, 'SWALP <no-reply@parqueexplora.org>')
        # La persona va en Reply-To para que las respuestas le lleguen.
        self.assertEqual(m.reply_to, ['persona@empresa.org'])
        self.assertEqual(m.to, ['destino@empresa.org'])
        self.assertEqual(m.subject, 'Prueba')
        # Debe incluir la alternativa HTML.
        self.assertTrue(any(ct == 'text/html' for _, ct in m.alternatives))

    def test_sin_remitente_valido_no_envia(self):
        with override_settings(DEFAULT_FROM_EMAIL=''):
            ok = EmailService._enviar_email_desde_usuario(
                subject='Prueba',
                message='cuerpo',
                from_email='persona@empresa.org',
                recipient_list=['destino@empresa.org'],
            )
        self.assertFalse(ok)
        self.assertEqual(len(mail.outbox), 0)

    def test_destinatarios_invalidos_no_envia(self):
        ok = EmailService._enviar_email_desde_usuario(
            subject='Prueba',
            message='cuerpo',
            from_email='persona@empresa.org',
            recipient_list=['', None],
        )
        self.assertFalse(ok)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='SWALP <no-reply@parqueexplora.org>',
    EMAIL_SEND_ASYNC=True,
)
class EnvioAsyncTest(TestCase):
    """Con EMAIL_SEND_ASYNC el envío se difiere hasta el commit (no bloquea el request)."""

    def test_se_difiere_hasta_el_commit(self):
        # El hilo ejecuta su target de forma síncrona para poder verificar el envío.
        def fake_thread(target=None, args=(), kwargs=None, daemon=None):
            t = mock.Mock()
            t.start = lambda: target(*args)
            return t

        # El hilo lo lanza ahora el outbox, no el EmailService: el envío se movió allí.
        with mock.patch('threading.Thread', side_effect=fake_thread):
            with self.captureOnCommitCallbacks(execute=True):
                ok = EmailService._enviar_email_desde_usuario(
                    subject='Async',
                    message='cuerpo',
                    from_email='persona@empresa.org',
                    recipient_list=['destino@empresa.org'],
                )
                self.assertTrue(ok)
                # Todavía NO se envió: quedó encolado en on_commit (no bloquea el request).
                self.assertEqual(len(mail.outbox), 0)

        # Al ejecutarse los callbacks del commit, se envía.
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].reply_to, ['persona@empresa.org'])
