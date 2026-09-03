"""
`DobladaStrategy._validar_pago_en_sabado`: las reglas del pago en sábado.

POR QUÉ ESTE ARCHIVO
--------------------
Medida la cobertura sobre el artefacto del CI, este método era el punto ciego del
proyecto: 172 líneas con 45 sin cubrir, la peor concentración de todo
`doblada_strategy.py` (887 líneas de validación al 90%, pero este método al 74%).

Lo que quedaba sin probar no era código muerto: eran las RAMAS DE RECHAZO —los
mensajes que lee el usuario cuando su solicitud no se puede hacer— y el tratamiento
COMPLETO del día de devolución en semana que acompaña a un sábado 'AMBAS'.

Dentro de eso había un caso que merece nombre propio: la emisión de
`RequiereCambioTurnoPrevio` de la línea final. Es el error tipado que pinta el recuadro
con el botón «Ir a Cambio de Turno Sencillo», y su módulo (`errores_validacion.py`)
existe precisamente porque una vez se renombró la clave `fecha_pago` en dos de los tres
sitios que la producían, el frontend lo tapó con un `||` y el CI pasó en verde. Esta
vía de emisión seguía sin red.

CÓMO SE PRUEBA
--------------
Llamando al método directamente. Es un `@staticmethod` con argumentos explícitos, así
que no hace falta montar la solicitud entera: se le da el estado y se mira qué contesta.
Devuelve `None` cuando todo está bien, o `(False, mensaje)` cuando rechaza.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, Jornada
from solicitudes.services.errores_validacion import RequiereCambioTurnoPrevio
from solicitudes.services.strategies.doblada_strategy import DobladaStrategy
from turnos.models import AsignarJornadaExplorador, Sala
from turnos.services.asignacion_especial_service import AsignacionEspecialService


class PagoEnSabadoBase(TestCase):

    def setUp(self):
        from django.core.cache import cache
        cache.clear()

        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00',
                                         hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00',
                                         hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Test', activo=True)

        self.solicitante = self._empleado('sol.sab', '3001')
        self.receptor = self._empleado('rec.sab', '3002')

        # La alternancia es un DATO publicado: sin ella, `grupo_trabaja` devuelve None y
        # todos los casos caerían en la rama de "año sin publicar".
        from turnos.tests.alternancia_helpers import publicar_alternancia
        self.sabado = self._sabado_futuro()
        publicar_alternancia(self.sabado.year)

        # Qué grupo trabaja ESE sábado lo decide el dato publicado, no una fórmula: se
        # consulta en vez de suponerlo, para que el test no dependa de la paridad del mes.
        self.grupo_sabado = AsignacionEspecialService.grupo_trabaja(self.sabado)
        self.assertIn(self.grupo_sabado, ('AM', 'PM'), 'la alternancia debe estar publicada')
        self.jornada_sabado = self.am if self.grupo_sabado == 'AM' else self.pm
        self.jornada_contraria = self.pm if self.grupo_sabado == 'AM' else self.am

        # Cesión: un día de semana anterior al sábado, siempre futuro.
        self.cesion = self.sabado - timedelta(days=3)
        while self.cesion.weekday() >= 5:
            self.cesion -= timedelta(days=1)

    # ------------------------------------------------------------------

    def _empleado(self, username, cedula):
        u = User.objects.create_user(username, password='x')
        return Empleado.objects.create(user=u, nombre=username, apellido='T',
                                       cedula=cedula, activo=True)

    @staticmethod
    def _sabado_futuro():
        """Un sábado del mes siguiente: futuro con holgura y lejos del fin de mes."""
        hoy = timezone.localdate()
        anio, mes = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        d = date(anio, mes, 8)
        while d.weekday() != 5:
            d += timedelta(days=1)
        return d

    def _jornada(self, empleado, jornada, desde=None):
        AsignarJornadaExplorador.objects.filter(explorador=empleado).delete()
        AsignarJornadaExplorador.objects.create(
            explorador=empleado, jornada=jornada, fecha_inicio=desde or date(2020, 1, 1))

    def _validar(self, **cambios):
        """Llama al método con un caso VÁLIDO por defecto y solo lo que cada test altera."""
        args = {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'fecha_pago_obj': self.sabado,
            'jornada_pago_sabado': self.grupo_sabado,
            'jornada_cedida': None,
            'fecha_cesion': self.cesion.strftime('%Y-%m-%d'),
            'fecha_pago_semana': None,
        }
        args.update(cambios)
        return DobladaStrategy._validar_pago_en_sabado(**args)


class JornadaDelSabadoTest(PagoEnSabadoBase):
    """Las guardas previas: qué se pide y quién puede cobrar ese sábado."""

    def setUp(self):
        super().setUp()
        self._jornada(self.receptor, self.jornada_sabado)
        self._jornada(self.solicitante, self.jornada_contraria)

    def test_el_caso_valido_no_rechaza(self):
        """CONTROL. Sin esto, un test que espera rechazo podría estar pasando porque el
        montaje está mal y TODO se rechaza."""
        self.assertIsNone(self._validar())

    def test_sin_jornada_de_sabado_valida_se_rechaza(self):
        for valor in ('XX', '', None, 'ambos'):
            with self.subTest(valor=valor):
                ok, msg = self._validar(jornada_pago_sabado=valor)

                self.assertFalse(ok)
                self.assertIn('jornada válida', msg)

    def test_sin_alternancia_publicada_se_dice_que_falta_publicarla(self):
        """
        El año sin publicar no es un error del usuario: nadie puede saber quién trabaja ese
        sábado. El mensaje tiene que mandar al supervisor, no culpar a quien solicita.
        """
        sabado_sin_publicar = self.sabado.replace(year=self.sabado.year + 5)

        ok, msg = self._validar(fecha_pago_obj=sabado_sin_publicar)

        self.assertFalse(ok)
        self.assertIn('alternancia', msg)
        self.assertIn('supervisor', msg)

    def test_receptor_sin_jornada_en_la_fecha_de_pago_se_rechaza(self):
        AsignarJornadaExplorador.objects.filter(explorador=self.receptor).delete()

        ok, msg = self._validar()

        self.assertFalse(ok)
        self.assertIn('no tiene jornada asignada para la fecha de pago', msg)

    def test_receptor_del_grupo_que_no_trabaja_ese_sabado_se_rechaza(self):
        """Se le paga doblando el sábado a quien de verdad trabaja ese sábado."""
        self._jornada(self.receptor, self.jornada_contraria)

        ok, msg = self._validar()

        self.assertFalse(ok)
        self.assertIn(self.grupo_sabado, msg)
        self.assertIn('grupo', msg)

    def test_receptor_sin_jornada_en_la_fecha_de_cesion_se_rechaza(self):
        """
        Distinto del caso anterior: aquí SÍ tiene jornada el sábado, pero no la tenía el día
        que cubrió. Sin ese dato no se puede comprobar la regla de abajo.
        """
        self._jornada(self.receptor, self.jornada_sabado,
                      desde=self.cesion + timedelta(days=1))

        ok, msg = self._validar(jornada_cedida=self.jornada_contraria.nombre)

        self.assertFalse(ok)
        self.assertIn('fecha de cesión', msg)

    def test_el_sabado_debe_corresponder_a_la_jornada_del_receptor_en_la_cesion(self):
        """
        El sábado de pago tiene que ser el de la jornada de quien hizo el doble turno. Se
        monta con DOS asignaciones: la del día de la cesión distinta de la del sábado.
        """
        AsignarJornadaExplorador.objects.filter(explorador=self.receptor).delete()
        AsignarJornadaExplorador.objects.create(
            explorador=self.receptor, jornada=self.jornada_contraria,
            fecha_inicio=date(2020, 1, 1))
        AsignarJornadaExplorador.objects.create(
            explorador=self.receptor, jornada=self.jornada_sabado,
            fecha_inicio=self.cesion + timedelta(days=1))

        ok, msg = self._validar(jornada_cedida=self.jornada_sabado.nombre)

        self.assertFalse(ok)
        self.assertIn('doble turno', msg)


class DevolucionEnSemanaTest(PagoEnSabadoBase):
    """
    Sábado 'AMBAS': el receptor cubre el día entero y queda debiendo una jornada, que
    devuelve un día de semana. Ese tercer día lo muta la misma solicitud, así que necesita
    las mismas guardas que la cesión y el pago — y era el bloque entero sin cubrir.
    """

    def setUp(self):
        super().setUp()
        self._jornada(self.receptor, self.jornada_sabado)
        self._jornada(self.solicitante, self.jornada_contraria)
        # Un día de semana del mismo mes que el sábado, futuro.
        self.dia_semana = self.sabado + timedelta(days=3)
        while self.dia_semana.weekday() >= 5:
            self.dia_semana += timedelta(days=1)

    def _ambas(self, **cambios):
        args = {'jornada_pago_sabado': 'AMBAS',
                'fecha_pago_semana': self.dia_semana.strftime('%Y-%m-%d')}
        args.update(cambios)
        return self._validar(**args)

    def test_el_caso_valido_no_rechaza(self):
        """CONTROL del bloque AMBAS."""
        self.assertIsNone(self._ambas())

    def test_sin_dia_de_devolucion_se_rechaza(self):
        ok, msg = self._ambas(fecha_pago_semana=None)

        self.assertFalse(ok)
        self.assertIn('día de la semana', msg)

    def test_una_fecha_ilegible_se_rechaza(self):
        ok, msg = self._ambas(fecha_pago_semana='31/02/2027')

        self.assertFalse(ok)
        self.assertIn('no es una fecha válida', msg)

    def test_el_dia_de_devolucion_no_puede_ser_finde(self):
        """Se devuelve en semana: un finde tiene sus propias reglas de alternancia."""
        domingo = self.sabado + timedelta(days=1)

        ok, msg = self._ambas(fecha_pago_semana=domingo.strftime('%Y-%m-%d'))

        self.assertFalse(ok)
        self.assertIn('lunes a viernes', msg)

    def test_el_dia_de_devolucion_debe_ser_del_mismo_mes_que_el_sabado(self):
        otro_mes = self.sabado.replace(day=1) + timedelta(days=45)
        while otro_mes.weekday() >= 5:
            otro_mes += timedelta(days=1)

        ok, msg = self._ambas(fecha_pago_semana=otro_mes.strftime('%Y-%m-%d'))

        self.assertFalse(ok)
        self.assertIn('mismo mes', msg)

    def test_el_dia_de_devolucion_no_puede_ser_festivo_ni_mantenimiento(self):
        from turnos.models import DiaEspecial
        DiaEspecial.objects.create(fecha=self.dia_semana, tipo='festivo', activo=True)

        ok, msg = self._ambas()

        self.assertFalse(ok)
        self.assertIn('festivo', msg)

    def test_el_dia_de_devolucion_no_puede_ser_en_el_pasado(self):
        pasado = timezone.localdate() - timedelta(days=10)
        while pasado.weekday() >= 5:
            pasado -= timedelta(days=1)
        # El sábado se mueve al mes del día pasado para que el fallo sea por PASADO y no
        # por la guarda del mismo mes, que se comprueba antes.
        sabado_del_pasado = pasado
        while sabado_del_pasado.weekday() != 5:
            sabado_del_pasado += timedelta(days=1)

        ok, msg = self._ambas(fecha_pago_obj=sabado_del_pasado,
                              fecha_pago_semana=pasado.strftime('%Y-%m-%d'))

        self.assertFalse(ok)
        self.assertIn('pasado', msg)

    def test_si_el_solicitante_y_el_receptor_comparten_jornada_pide_un_ct_previo(self):
        """
        El caso con nombre propio. Para que el compañero se doble por ti ese día tenéis que
        estar en jornadas contrarias; si coincidís, la salida es un cambio de turno sencillo
        previo, y el formulario lo pinta como un recuadro con botón.

        Se comprueba el TIPO y sus datos, no solo el texto: las claves `fecha_pago` y
        `jornada_comun` las lee `solicitar_doblada.js`, y cambiarlas rompe la pantalla sin
        que el servidor dé error. Eso ya pasó una vez —un refactor las renombró en dos de
        los tres sitios que las producían— y el `||` del frontend lo tapó.
        """
        self._jornada(self.solicitante, self.jornada_sabado)

        ok, msg = self._ambas()

        self.assertFalse(ok)
        self.assertIsInstance(msg, RequiereCambioTurnoPrevio)
        self.assertEqual(msg.jornada_comun, self.grupo_sabado)
        self.assertEqual(msg.fecha_pago, str(self.dia_semana))

        payload = msg.como_payload()
        self.assertEqual(payload['code'], 'requiere_cambio_turno_previo')
        self.assertEqual(payload['fecha_pago'], str(self.dia_semana))
        self.assertEqual(payload['jornada_comun'], self.grupo_sabado)
