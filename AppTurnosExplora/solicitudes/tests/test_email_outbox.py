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


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='SWALP <no-reply@parqueexplora.org>',
    EMAIL_SEND_ASYNC=False,
)
class OutboxUnaConexionPorLoteTest(TestCase):
    """
    El coste de un correo no es el mensaje: es el saludo (handshake TLS + AUTH, ~2 s
    medidos contra Gmail). Crear una solicitud manda TRES correos, y los flujos
    multi-compañero muchos más. Lo que se verifica aquí es que todos comparten un
    único canal, porque de eso —y no del tamaño del mensaje— dependía la latencia.
    """

    def _encolar(self, n=3):
        return [
            EmailOutboxService.encolar(
                asunto=f'Correo {i}', cuerpo_texto='c', remitente='a@x.org',
                destinatarios=[f'b{i}@x.org'])
            for i in range(n)
        ]

    def test_un_lote_de_tres_abre_una_sola_conexion(self):
        filas = self._encolar(3)

        with mock.patch.object(EmailOutboxService, '_abrir_conexion',
                               wraps=EmailOutboxService._abrir_conexion) as abrir:
            enviados = EmailOutboxService.enviar_lote([f.id for f in filas])

        self.assertEqual(enviados, 3)
        self.assertEqual(abrir.call_count, 1, 'una conexión para todo el lote')
        self.assertEqual(len(mail.outbox), 3)

    def test_el_barrido_tambien_va_en_una_sola_conexion(self):
        self._encolar(4)

        with mock.patch.object(EmailOutboxService, '_abrir_conexion',
                               wraps=EmailOutboxService._abrir_conexion) as abrir:
            resultado = EmailOutboxService.procesar_pendientes()

        self.assertEqual(resultado['enviados'], 4)
        self.assertEqual(abrir.call_count, 1)

    def test_si_el_smtp_no_abre_nadie_quema_un_intento(self):
        """
        Antes se reclamaba fila por fila y cada una gastaba un intento contra un
        servidor caído: cinco caídas seguidas y el correo quedaba FALLIDO para
        siempre sin que su destinatario tuviera nada que ver.
        """
        filas = self._encolar(3)

        with mock.patch.object(EmailOutboxService, '_abrir_conexion', return_value=None):
            self.assertEqual(EmailOutboxService.enviar_lote([f.id for f in filas]), 0)

        for fila in filas:
            fila.refresh_from_db()
            self.assertEqual(fila.estado, EmailOutbox.ESTADO_PENDIENTE)
            self.assertEqual(fila.intentos, 0, 'una caída del SMTP no gasta intentos')

    def test_un_fallo_a_media_tanda_renueva_el_canal_y_sigue(self):
        """Un canal muerto haría fallar todo el resto del lote; se renueva y se continúa."""
        primera, segunda, tercera = self._encolar(3)
        fallos = {'restantes': 1}

        def send_con_un_fallo(self_mensaje, *args, **kwargs):
            if fallos['restantes']:
                fallos['restantes'] -= 1
                raise OSError('conexión cortada por el servidor')
            mail.outbox.append(self_mensaje)
            return 1

        with mock.patch('django.core.mail.EmailMultiAlternatives.send', send_con_un_fallo):
            with mock.patch.object(EmailOutboxService, '_abrir_conexion',
                                   wraps=EmailOutboxService._abrir_conexion) as abrir:
                enviados = EmailOutboxService.enviar_lote(
                    [primera.id, segunda.id, tercera.id])

        self.assertEqual(enviados, 2, 'las dos siguientes sí salen')
        self.assertEqual(abrir.call_count, 2, 'se renueva el canal tras el fallo')

        primera.refresh_from_db()
        self.assertEqual(primera.estado, EmailOutbox.ESTADO_PENDIENTE)
        self.assertEqual(primera.intentos, 1)

    def test_una_fila_omitida_no_provoca_reconexion(self):
        """Que otro worker tenga la fila no dice nada del canal: reabrir sería gratuito."""
        primera, segunda = self._encolar(2)
        EmailOutboxService._reclamar(primera.id)  # se la queda otro worker

        with mock.patch.object(EmailOutboxService, '_abrir_conexion',
                               wraps=EmailOutboxService._abrir_conexion) as abrir:
            enviados = EmailOutboxService.enviar_lote([primera.id, segunda.id])

        self.assertEqual(enviados, 1)
        self.assertEqual(abrir.call_count, 1)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    DEFAULT_FROM_EMAIL='SWALP <no-reply@parqueexplora.org>',
    EMAIL_SEND_ASYNC=False,
)
class OutboxEnvioAgrupadoTest(TestCase):
    """`envio_agrupado`: varios correos encolados por separado, una sola entrega."""

    def _enviar(self, destino):
        return EmailService._enviar_email_desde_usuario(
            subject='Prueba', message='cuerpo', from_email='persona@x.org',
            recipient_list=[destino])

    def test_los_correos_del_bloque_salen_en_un_unico_lote(self):
        with mock.patch.object(EmailOutboxService, 'enviar_lote',
                               wraps=EmailOutboxService.enviar_lote) as lote:
            with EmailOutboxService.envio_agrupado():
                self._enviar('uno@x.org')
                self._enviar('dos@x.org')
                self._enviar('tres@x.org')
                # Dentro del bloque todavía no ha salido nada.
                self.assertEqual(len(mail.outbox), 0)

        self.assertEqual(len(mail.outbox), 3)
        self.assertEqual(lote.call_count, 1)
        self.assertEqual(len(lote.call_args[0][0]), 3, 'los tres ids en la misma llamada')

    def test_sin_bloque_cada_correo_se_despacha_por_su_cuenta(self):
        """El comportamiento de siempre: agrupar es opt-in, no un cambio de contrato."""
        self._enviar('uno@x.org')
        self.assertEqual(len(mail.outbox), 1)

    def test_anidar_grupos_produce_un_solo_lote(self):
        """
        Reentrancia: el orquestador abre un grupo alrededor del bucle y cada
        `crear_notificacion_solicitud` abre el suyo. Si el de dentro despachara,
        volveríamos a una conexión por solicitud.
        """
        with mock.patch.object(EmailOutboxService, 'enviar_lote',
                               wraps=EmailOutboxService.enviar_lote) as lote:
            with EmailOutboxService.envio_agrupado():
                with EmailOutboxService.envio_agrupado():
                    self._enviar('uno@x.org')
                self.assertEqual(len(mail.outbox), 0, 'el grupo interior no despacha')
                self._enviar('dos@x.org')

        self.assertEqual(lote.call_count, 1)
        self.assertEqual(len(mail.outbox), 2)

    def test_una_excepcion_no_retiene_los_correos_ya_encolados(self):
        """El despacho va en un `finally`: lo encolado antes del fallo debe salir."""
        with self.assertRaises(RuntimeError):
            with EmailOutboxService.envio_agrupado():
                self._enviar('uno@x.org')
                raise RuntimeError('algo se rompió después de encolar')

        self.assertEqual(len(mail.outbox), 1)

    def test_el_grupo_queda_cerrado_tras_una_excepcion(self):
        """Un grupo que no se cierra contaminaría al siguiente envío del mismo hilo."""
        with self.assertRaises(RuntimeError):
            with EmailOutboxService.envio_agrupado():
                raise RuntimeError('x')

        # Si el grupo hubiera quedado abierto, esto no enviaría nada.
        self._enviar('dos@x.org')
        self.assertEqual(len(mail.outbox), 1)
