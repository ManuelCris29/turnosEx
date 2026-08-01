"""
Tests del patrón outbox: lo que se verifica aquí es la GARANTÍA DE ENTREGA, es decir
que un correo encolado no se pierde aunque el envío falle o el proceso muera.
"""
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from solicitudes.models import EmailOutbox
from solicitudes.services.email_outbox_service import EmailOutboxService
from solicitudes.services.email_service import EmailService


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='SWALP <no-reply@parqueexplora.org>',
    EMAIL_SEND_ASYNC=False,
)
class OutboxEntregaTest(TestCase):

    def _encolar(self, **kwargs):
        datos = dict(
            asunto='Prueba', cuerpo_texto='cuerpo', remitente='no-reply@x.org',
            destinatarios=['destino@x.org'],
        )
        datos.update(kwargs)
        return EmailOutboxService.encolar(**datos)

    def test_el_correo_queda_registrado_al_encolar(self):
        fila = self._encolar()
        self.assertEqual(fila.estado, EmailOutbox.ESTADO_PENDIENTE)
        self.assertEqual(fila.intentos, 0)

    def test_envio_exitoso_marca_la_fila_como_enviada(self):
        fila = self._encolar()
        self.assertTrue(EmailOutboxService.intentar_enviar(fila.id))

        fila.refresh_from_db()
        self.assertEqual(fila.estado, EmailOutbox.ESTADO_ENVIADO)
        self.assertIsNotNone(fila.enviado_en)
        self.assertEqual(len(mail.outbox), 1)

    def test_un_fallo_de_smtp_deja_la_fila_para_reintentar(self):
        """El punto del outbox: si el SMTP falla, el correo NO se pierde."""
        fila = self._encolar()

        with mock.patch('django.core.mail.EmailMultiAlternatives.send',
                        side_effect=OSError('SMTP caído')):
            self.assertFalse(EmailOutboxService.intentar_enviar(fila.id))

        fila.refresh_from_db()
        self.assertEqual(fila.estado, EmailOutbox.ESTADO_PENDIENTE)
        self.assertEqual(fila.intentos, 1)
        self.assertIn('SMTP caído', fila.ultimo_error)

        # Y cuando el SMTP vuelve, el barrido lo entrega.
        EmailOutbox.objects.filter(pk=fila.id).update(disponible_en=timezone.now())
        resultado = EmailOutboxService.procesar_pendientes()

        self.assertEqual(resultado['enviados'], 1)
        fila.refresh_from_db()
        self.assertEqual(fila.estado, EmailOutbox.ESTADO_ENVIADO)
        self.assertEqual(len(mail.outbox), 1)

    def test_tras_agotar_los_reintentos_queda_marcado_como_fallido(self):
        """Un correo irrecuperable debe quedar VISIBLE, no reintentarse para siempre."""
        fila = self._encolar()

        with mock.patch('django.core.mail.EmailMultiAlternatives.send',
                        side_effect=OSError('destinatario inexistente')):
            for _ in range(EmailOutbox.MAX_INTENTOS):
                EmailOutbox.objects.filter(pk=fila.id).update(disponible_en=timezone.now())
                EmailOutboxService.intentar_enviar(fila.id)

        fila.refresh_from_db()
        self.assertEqual(fila.estado, EmailOutbox.ESTADO_FALLIDO)
        self.assertEqual(fila.intentos, EmailOutbox.MAX_INTENTOS)

        # Ya no se vuelve a intentar: no lo recoge el barrido.
        EmailOutbox.objects.filter(pk=fila.id).update(disponible_en=timezone.now())
        self.assertEqual(EmailOutboxService.procesar_pendientes()['candidatos'], 0)

    def test_backoff_impide_reintentar_de_inmediato(self):
        fila = self._encolar()
        with mock.patch('django.core.mail.EmailMultiAlternatives.send',
                        side_effect=OSError('falla')):
            EmailOutboxService.intentar_enviar(fila.id)

        # Sin tocar `disponible_en`, el barrido no debe recogerlo todavía.
        self.assertEqual(EmailOutboxService.procesar_pendientes()['candidatos'], 0)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='SWALP <no-reply@parqueexplora.org>',
    EMAIL_SEND_ASYNC=False,
)
class OutboxIdempotenciaTest(TestCase):

    def test_la_clave_impide_encolar_dos_veces_el_mismo_correo(self):
        primera = EmailOutboxService.encolar(
            asunto='Aprobada', cuerpo_texto='c', remitente='a@x.org',
            destinatarios=['b@x.org'], clave_idempotencia='aprob_sup_42')
        segunda = EmailOutboxService.encolar(
            asunto='Aprobada', cuerpo_texto='c', remitente='a@x.org',
            destinatarios=['b@x.org'], clave_idempotencia='aprob_sup_42')

        self.assertEqual(primera.id, segunda.id)
        self.assertEqual(EmailOutbox.objects.count(), 1)

    def test_sin_clave_cada_llamada_encola_su_propia_fila(self):
        for _ in range(2):
            EmailOutboxService.encolar(
                asunto='Aviso', cuerpo_texto='c', remitente='a@x.org',
                destinatarios=['b@x.org'])
        self.assertEqual(EmailOutbox.objects.count(), 2)

    def test_una_fila_ya_enviada_no_se_reenvia(self):
        """Reclamar es excluyente: reprocesar la cola no duplica correos ya entregados."""
        fila = EmailOutboxService.encolar(
            asunto='Prueba', cuerpo_texto='c', remitente='a@x.org', destinatarios=['b@x.org'])
        EmailOutboxService.intentar_enviar(fila.id)

        self.assertFalse(EmailOutboxService.intentar_enviar(fila.id))
        self.assertEqual(len(mail.outbox), 1)

    def test_una_fila_reclamada_por_otro_worker_no_se_envia_dos_veces(self):
        """Simula dos procesos barriendo la cola a la vez."""
        fila = EmailOutboxService.encolar(
            asunto='Prueba', cuerpo_texto='c', remitente='a@x.org', destinatarios=['b@x.org'])

        # El primer worker la reclama (queda 'enviando' con su ventana por delante).
        reclamada = EmailOutboxService._reclamar(fila.id)
        self.assertIsNotNone(reclamada)

        # El segundo no puede: la ventana del primero sigue vigente.
        self.assertIsNone(EmailOutboxService._reclamar(fila.id))
        self.assertFalse(EmailOutboxService.intentar_enviar(fila.id))
        self.assertEqual(len(mail.outbox), 0)

    def test_un_intento_abandonado_se_puede_reclamar_al_vencer_la_ventana(self):
        """Si el proceso muere a media entrega, la fila no puede quedar atascada."""
        fila = EmailOutboxService.encolar(
            asunto='Prueba', cuerpo_texto='c', remitente='a@x.org', destinatarios=['b@x.org'])
        EmailOutboxService._reclamar(fila.id)  # worker que "muere" aquí

        EmailOutbox.objects.filter(pk=fila.id).update(disponible_en=timezone.now())
        self.assertTrue(EmailOutboxService.intentar_enviar(fila.id))
        self.assertEqual(len(mail.outbox), 1)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='SWALP <no-reply@parqueexplora.org>',
    EMAIL_SEND_ASYNC=False,
)
class EmailServiceUsaOutboxTest(TestCase):
    """El EmailService debe encolar SIEMPRE: es lo que da la garantía transaccional."""

    def test_enviar_deja_rastro_en_la_cola(self):
        EmailService._enviar_email_desde_usuario(
            subject='Prueba', message='cuerpo', from_email='persona@x.org',
            recipient_list=['destino@x.org'], html_message='<p>c</p>')

        fila = EmailOutbox.objects.get()
        self.assertEqual(fila.estado, EmailOutbox.ESTADO_ENVIADO)
        self.assertEqual(fila.destinatarios, ['destino@x.org'])
        self.assertEqual(fila.reply_to, 'persona@x.org')

    def test_un_correo_que_falla_queda_encolado_y_no_se_pierde(self):
        with mock.patch('django.core.mail.EmailMultiAlternatives.send',
                        side_effect=OSError('SMTP caído')):
            EmailService._enviar_email_desde_usuario(
                subject='Prueba', message='cuerpo', from_email='persona@x.org',
                recipient_list=['destino@x.org'])

        fila = EmailOutbox.objects.get()
        self.assertEqual(fila.estado, EmailOutbox.ESTADO_PENDIENTE)
        self.assertEqual(len(mail.outbox), 0)
