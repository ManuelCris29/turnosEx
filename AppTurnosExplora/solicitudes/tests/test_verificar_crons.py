"""
El verificador de tareas programadas (`verificar_crons`).

Lo que se prueba aquí no es "el comando imprime": es que DISTINGA un cron muerto de una
cola con trabajo normal. Un check que se alarma con un sistema sano se desactiva a la
semana, y entonces no protege de nada.
"""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from solicitudes.management.commands.verificar_crons import MARCADOR_ALERTA
from solicitudes.models import EmailOutbox, RevisionSancionesDeuda


class VerificarCronsBase(TestCase):

    def _correo(self, *, minutos_esperando=0, estado=EmailOutbox.ESTADO_PENDIENTE,
                intentos=0):
        fila = EmailOutbox.objects.create(
            asunto='x', cuerpo_texto='y', remitente='no-reply@swalp.test',
            destinatarios=['a@b.c'],
            estado=estado, intentos=intentos)
        # `disponible_en` tiene default=now y `creado_en` es auto_now_add: para situar la
        # fila en el pasado hay que actualizarla después de crearla.
        EmailOutbox.objects.filter(pk=fila.pk).update(
            disponible_en=timezone.now() - timedelta(minutes=minutos_esperando))
        return fila

    def _ejecutar(self, **opciones):
        """Devuelve (codigo_salida, stdout, stderr)."""
        out, err = StringIO(), StringIO()
        codigo = 0
        try:
            call_command('verificar_crons', stdout=out, stderr=err, **opciones)
        except SystemExit as exc:
            codigo = exc.code
        return codigo, out.getvalue(), err.getvalue()

    def _revision_de_hace(self, dias):
        RevisionSancionesDeuda.objects.create(
            fecha=timezone.localdate() - timedelta(days=dias))


class OutboxTest(VerificarCronsBase):

    def setUp(self):
        # Las sanciones no son el objeto de esta clase: se dejan sanas para que el único
        # motivo de alarma posible sea la cola de correo.
        self._revision_de_hace(0)

    def test_cola_vacia_no_alarma(self):
        codigo, salida, _ = self._ejecutar()

        self.assertEqual(codigo, 0)
        self.assertIn('no hay correos esperando', salida)

    def test_una_cola_reciente_no_alarma(self):
        """Lo normal tras un pico: hay trabajo, pero el worker lo está atendiendo."""
        for _ in range(20):
            self._correo(minutos_esperando=2)

        codigo, salida, err = self._ejecutar()

        self.assertEqual(codigo, 0, err)
        self.assertNotIn(MARCADOR_ALERTA, err)

    def test_un_solo_correo_estancado_si_alarma(self):
        """
        La señal es la ESPERA, no el tamaño: una única fila parada horas delata al worker
        igual que mil, y es el caso que de verdad ocurre cuando nadie programó el cron.
        """
        self._correo(minutos_esperando=180)

        codigo, _, err = self._ejecutar()

        self.assertEqual(codigo, 1)
        self.assertIn(MARCADOR_ALERTA, err)
        self.assertIn('180 min', err)
        self.assertIn('procesar_email_outbox', err)

    def test_un_correo_que_aun_no_toca_no_cuenta(self):
        """
        Backoff: una fila reprogramada para dentro de un rato no es un correo estancado, y
        contarla daría la alarma con un worker perfectamente sano.
        """
        fila = self._correo()
        EmailOutbox.objects.filter(pk=fila.pk).update(
            disponible_en=timezone.now() + timedelta(hours=2))

        codigo, salida, _ = self._ejecutar()

        self.assertEqual(codigo, 0)
        self.assertIn('no hay correos esperando', salida)

    def test_un_correo_con_los_reintentos_agotados_no_acusa_al_cron(self):
        """
        Ese correo ya no lo va a tocar nadie: pide una persona, no un cron. Si contara como
        atasco, la alarma seguiría sonando para siempre con el worker sano — y una alarma
        que no se puede apagar arreglando la causa se acaba ignorando.
        """
        self._correo(minutos_esperando=999, estado=EmailOutbox.ESTADO_FALLIDO,
                     intentos=EmailOutbox.MAX_INTENTOS)

        codigo, salida, _ = self._ejecutar()

        self.assertEqual(codigo, 0)
        self.assertIn('revisión manual', salida, 'pero sí se informa de que existe')

    def test_el_umbral_se_puede_ajustar(self):
        self._correo(minutos_esperando=30)

        self.assertEqual(self._ejecutar()[0], 0, 'con el umbral por defecto (60) está bien')
        self.assertEqual(self._ejecutar(umbral_outbox=10)[0], 1)


class SancionesTest(VerificarCronsBase):

    def test_ejecutado_hoy_no_alarma(self):
        self._revision_de_hace(0)

        codigo, salida, _ = self._ejecutar()

        self.assertEqual(codigo, 0)
        self.assertIn('se ejecutó hoy', salida)

    def test_un_retraso_tolerado_no_alarma(self):
        """El proceso se autocura: un día de retraso atrasa el aviso, no lo pierde."""
        self._revision_de_hace(1)

        self.assertEqual(self._ejecutar()[0], 0)

    def test_demasiados_dias_sin_correr_alarma(self):
        self._revision_de_hace(RevisionSancionesDeuda.DIAS_TOLERADOS + 3)

        codigo, _, err = self._ejecutar()

        self.assertEqual(codigo, 1)
        self.assertIn(MARCADOR_ALERTA, err)
        self.assertIn('revisar_sanciones_por_deuda', err)

    def test_nunca_ejecutado_alarma(self):
        """
        El caso que motiva todo esto: recién desplegado y nadie programó la tarea. El propio
        comando de sanciones no puede denunciarlo —para hacerlo tendría que ejecutarse—.
        """
        codigo, _, err = self._ejecutar()

        self.assertEqual(codigo, 1)
        self.assertIn(MARCADOR_ALERTA, err)
        self.assertIn('NUNCA se ha ejecutado', err)


class ContratoDeAlarmaTest(VerificarCronsBase):
    """El marcador es el enganche de la alarma en producción: es contrato, no redacción."""

    def test_el_marcador_es_estable_y_agarrable(self):
        self.assertEqual(MARCADOR_ALERTA, 'CRON_NO_EJECUTADO')
        self.assertTrue(MARCADOR_ALERTA.isascii(), 'un acento rompe el grep del filtro')
        self.assertNotIn(' ', MARCADOR_ALERTA)
        self.assertEqual(MARCADOR_ALERTA, MARCADOR_ALERTA.upper())

    def test_cada_problema_empieza_por_el_marcador(self):
        """Si no va primero, un metric filter anclado al principio de línea no lo ve."""
        _, _, err = self._ejecutar()

        lineas = [l for l in err.splitlines() if l.strip()]
        self.assertTrue(lineas)
        for linea in lineas:
            self.assertTrue(linea.lstrip().startswith(MARCADOR_ALERTA), linea)

    def test_la_salida_json_es_consumible_por_un_script(self):
        import json

        self._revision_de_hace(0)
        self._correo(minutos_esperando=180)

        codigo, salida, _ = self._ejecutar(json=True)

        datos = json.loads(salida)
        self.assertEqual(codigo, 1)
        self.assertFalse(datos['ok'])
        por_cron = {c['cron']: c for c in datos['checks']}
        self.assertFalse(por_cron['procesar_email_outbox']['ok'])
        self.assertTrue(por_cron['revisar_sanciones_por_deuda']['ok'])
        self.assertEqual(por_cron['procesar_email_outbox']['espera_minutos'], 180)

    def test_no_ejecuta_las_tareas_que_vigila(self):
        """
        Un verificador que ARREGLA lo que mide no sirve como verificador: dejaría de haber
        diferencia entre «el cron corre» y «alguien miró el check».
        """
        self._correo(minutos_esperando=180)

        self._ejecutar()

        fila = EmailOutbox.objects.get()
        self.assertEqual(fila.estado, EmailOutbox.ESTADO_PENDIENTE)
        self.assertEqual(fila.intentos, 0)
        self.assertFalse(RevisionSancionesDeuda.objects.exists())
