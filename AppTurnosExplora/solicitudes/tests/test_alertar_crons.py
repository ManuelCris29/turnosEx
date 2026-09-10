"""
El vigilante que avisa cuando una tarea programada deja de correr (`alertar_crons`).

Lo que se prueba aquí no es el diagnóstico —de eso responde `test_verificar_crons.py`, y
este comando reutiliza esos mismos chequeos a propósito para no tener dos criterios que
se desincronicen—. Lo que se prueba es lo que `alertar_crons` añade encima:

  · que CALLE cuando todo está bien (una alarma que suena sin motivo se desactiva),
  · que AVISE cuando algo falla, y que el correo lleve el marcador correcto,
  · que el envío NO pase por el outbox (si lo roto es el outbox, la alerta se perdería),
  · que un fallo al enviar la alerta se note en vez de tragarse,
  · y que el latido semanal solo salga los lunes.
"""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from solicitudes.management.commands.alertar_crons import (
    ASUNTO_ALERTA,
    ASUNTO_LATIDO,
)
from solicitudes.management.commands.verificar_crons import (
    MARCADOR_ALERTA,
    MARCADOR_CORREOS_FALLIDOS,
    UMBRAL_OUTBOX_MINUTOS,
)
from solicitudes.models import EmailOutbox, RevisionSancionesDeuda

# Un lunes y un martes reales, para el latido semanal.
UN_LUNES = timezone.datetime(2026, 9, 7).date()
UN_MARTES = timezone.datetime(2026, 9, 8).date()


@override_settings(
    EMAIL_HOST='smtp-relay.test', EMAIL_PORT=587, EMAIL_USE_TLS=True,
    EMAIL_HOST_USER='', EMAIL_HOST_PASSWORD='',
    DEFAULT_FROM_EMAIL='SWALP <no-reply@swalp.test>',
)
class AlertarCronsBase(TestCase):
    """
    Base con el reloj y el SMTP bajo control.

    El SMTP se sustituye por un doble: estas pruebas verifican QUE se envía y CON QUÉ, no
    el protocolo. Se parchea `smtplib.SMTP` dentro del módulo del comando, que es donde se
    resuelve el nombre.
    """

    def setUp(self):
        # Por defecto, un día que no es lunes: así el latido no contamina los casos que
        # comprueban el silencio.
        self._parche_fecha = mock.patch(
            'solicitudes.management.commands.alertar_crons.timezone.localdate',
            return_value=UN_MARTES)
        self._parche_fecha.start()
        self.addCleanup(self._parche_fecha.stop)

        self._parche_smtp = mock.patch(
            'solicitudes.management.commands.alertar_crons.smtplib.SMTP')
        self.smtp = self._parche_smtp.start()
        self.addCleanup(self._parche_smtp.stop)
        # `smtplib.SMTP(...)` devuelve la conexión: el doble útil es el del valor de
        # retorno, no el de la clase.
        self.conexion = self.smtp.return_value

    # --- utilidades ---------------------------------------------------

    def _ejecutar(self, **opciones):
        """Devuelve (codigo_salida, stdout, stderr)."""
        out, err = StringIO(), StringIO()
        codigo = 0
        opciones.setdefault('para', 'soporte@swalp.test')
        try:
            call_command('alertar_crons', stdout=out, stderr=err, **opciones)
        except SystemExit as exc:
            codigo = exc.code
        return codigo, out.getvalue(), err.getvalue()

    def _mensaje_enviado(self):
        """El EmailMessage que se pasó a `send_message`, o None si no se envió nada."""
        if not self.conexion.send_message.called:
            return None
        return self.conexion.send_message.call_args[0][0]

    def _sistema_sano(self):
        """La revisión de sanciones corrió hoy y no hay nada esperando en la cola."""
        RevisionSancionesDeuda.objects.create(fecha=timezone.localdate())

    def _correo_atascado(self):
        """Un pendiente que lleva mucho más del umbral esperando: nadie vacía la cola."""
        fila = EmailOutbox.objects.create(
            asunto='x', cuerpo_texto='y', remitente='no-reply@swalp.test',
            destinatarios=['a@b.c'], estado=EmailOutbox.ESTADO_PENDIENTE, intentos=0)
        EmailOutbox.objects.filter(pk=fila.pk).update(
            disponible_en=timezone.now() - timedelta(minutes=UMBRAL_OUTBOX_MINUTOS + 30))
        return fila

    def _correo_agotado(self):
        """Una fila que gastó los cinco intentos: exige una persona, no un cron."""
        fila = EmailOutbox.objects.create(
            asunto='x', cuerpo_texto='y', remitente='no-reply@swalp.test',
            destinatarios=['a@b.c'], estado=EmailOutbox.ESTADO_FALLIDO,
            intentos=EmailOutbox.MAX_INTENTOS)
        return fila


class SilencioCuandoTodoVaBienTest(AlertarCronsBase):

    def setUp(self):
        super().setUp()
        self._sistema_sano()

    def test_no_envia_nada_si_no_hay_problemas(self):
        codigo, salida, _ = self._ejecutar()

        self.assertEqual(codigo, 0)
        self.assertFalse(self.smtp.called,
                         'Un sistema sano no debe generar correo: una alarma que suena '
                         'sin motivo se acaba desactivando.')
        self.assertIn('Nada que avisar', salida)

    def test_informa_del_estado_por_stdout_aunque_no_envie(self):
        _, salida, _ = self._ejecutar()

        self.assertIn('[ok] procesar_email_outbox', salida)
        self.assertIn('[ok] revisar_sanciones_por_deuda', salida)


class AvisaCuandoAlgoFallaTest(AlertarCronsBase):

    def test_cola_atascada_envia_correo_con_el_marcador_de_cron(self):
        self._sistema_sano()
        self._correo_atascado()

        codigo, _, error = self._ejecutar()

        self.assertEqual(codigo, 1, 'El Schedule debe quedar en rojo, no solo avisar.')
        mensaje = self._mensaje_enviado()
        self.assertIsNotNone(mensaje, 'Con la cola atascada tiene que salir el aviso.')
        self.assertEqual(mensaje['Subject'], ASUNTO_ALERTA)
        self.assertIn(MARCADOR_ALERTA, mensaje.get_content())
        self.assertIn(MARCADOR_ALERTA, error)

    def test_correos_agotados_usan_su_propio_marcador(self):
        # Marcador distinto porque la respuesta es distinta: esto lo arregla una persona
        # desde el admin, no programar un cron.
        self._sistema_sano()
        self._correo_agotado()

        codigo, _, _ = self._ejecutar()

        self.assertEqual(codigo, 1)
        cuerpo = self._mensaje_enviado().get_content()
        self.assertIn(MARCADOR_CORREOS_FALLIDOS, cuerpo)

    def test_revision_de_sanciones_que_nunca_corrio_dispara_el_aviso(self):
        # Sin ninguna fila en RevisionSancionesDeuda: la tarea no existe.
        codigo, _, _ = self._ejecutar()

        self.assertEqual(codigo, 1)
        cuerpo = self._mensaje_enviado().get_content()
        self.assertIn('revisar_sanciones_por_deuda', cuerpo)

    def test_el_correo_va_a_los_destinatarios_pedidos(self):
        self._correo_atascado()

        self._ejecutar(para='uno@swalp.test, dos@swalp.test')

        mensaje = self._mensaje_enviado()
        self.assertIn('uno@swalp.test', mensaje['To'])
        self.assertIn('dos@swalp.test', mensaje['To'])

    def test_el_cuerpo_explica_que_hacer_con_cada_marcador(self):
        # Un aviso que no dice qué hacer obliga a buscar el manual justo cuando hay prisa.
        self._correo_atascado()

        self._ejecutar()

        cuerpo = self._mensaje_enviado().get_content()
        self.assertIn('/admin/solicitudes/emailoutbox/', cuerpo)


class NoPasaPorElOutboxTest(AlertarCronsBase):
    """
    El punto entero del diseño: si lo averiado es el worker del outbox, una alerta
    encolada ahí se quedaría esperando junto a los correos que denuncia.
    """

    def test_el_aviso_no_deja_fila_en_la_cola(self):
        self._sistema_sano()
        self._correo_atascado()
        antes = EmailOutbox.objects.count()

        self._ejecutar()

        self.assertEqual(EmailOutbox.objects.count(), antes,
                         'La alerta no puede encolarse en el mismo sistema que vigila.')

    def test_no_intenta_autenticarse_si_no_hay_credenciales(self):
        # El relay SMTP de Workspace autenticado por IP va sin usuario ni contraseña.
        # Llamar a `login` con credenciales vacías da error y no habría alerta.
        self._correo_atascado()

        self._ejecutar()

        self.assertFalse(self.conexion.login.called)

    @override_settings(EMAIL_HOST_USER='u', EMAIL_HOST_PASSWORD='p')
    def test_se_autentica_cuando_si_hay_credenciales(self):
        self._correo_atascado()

        self._ejecutar()

        self.conexion.login.assert_called_once_with('u', 'p')


class FalloAlEnviarTest(AlertarCronsBase):

    def test_si_el_aviso_no_sale_el_comando_termina_en_rojo(self):
        # Un vigilante que no puede avisar y calla es peor que ninguno.
        self._sistema_sano()
        self._correo_atascado()
        self.conexion.send_message.side_effect = OSError('conexion rechazada')

        codigo, _, error = self._ejecutar()

        self.assertEqual(codigo, 1)
        self.assertIn(MARCADOR_ALERTA, error)
        self.assertIn('no se pudo enviar', error)

    def test_sin_destinatarios_falla_ruidosamente(self):
        self._correo_atascado()

        with mock.patch.dict('os.environ', {'ALERTAS_CRON_EMAIL': ''}, clear=False):
            codigo, _, _ = self._ejecutar(para='')

        self.assertNotEqual(codigo, 0)
        self.assertFalse(self.conexion.send_message.called)


class LatidoSemanalTest(AlertarCronsBase):

    def setUp(self):
        super().setUp()
        self._sistema_sano()

    def _es_lunes(self):
        self._parche_fecha.stop()
        parche = mock.patch(
            'solicitudes.management.commands.alertar_crons.timezone.localdate',
            return_value=UN_LUNES)
        parche.start()
        self.addCleanup(parche.stop)

    def test_el_lunes_avisa_aunque_todo_este_bien(self):
        self._es_lunes()

        codigo, _, _ = self._ejecutar()

        self.assertEqual(codigo, 0, 'El latido no es un problema: sale en verde.')
        mensaje = self._mensaje_enviado()
        self.assertIsNotNone(mensaje)
        self.assertEqual(mensaje['Subject'], ASUNTO_LATIDO)

    def test_el_resto_de_dias_calla(self):
        codigo, _, _ = self._ejecutar()

        self.assertEqual(codigo, 0)
        self.assertIsNone(self._mensaje_enviado())

    def test_sin_latido_lo_desactiva(self):
        self._es_lunes()

        self._ejecutar(sin_latido=True)

        self.assertIsNone(self._mensaje_enviado())


class DryRunTest(AlertarCronsBase):

    def test_no_envia_pero_muestra_el_correo(self):
        self._sistema_sano()
        self._correo_atascado()

        codigo, salida, _ = self._ejecutar(dry_run=True)

        self.assertEqual(codigo, 1)
        self.assertFalse(self.smtp.called)
        self.assertIn(ASUNTO_ALERTA, salida)
        self.assertIn(MARCADOR_ALERTA, salida)
