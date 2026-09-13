"""
Ceder una MEDIA JORNADA de una doblada cuando esa mitad vino de un favor.

Caso real (Marco / #451): Jeison le cede su AM a Marco (base PM) → Marco queda DOBLADA (AM+PM).
Marco quiere ceder esa AM a Mildrey. Antes se bloqueaba con "ese compañero se queda sin cobertura",
que es falso: Mildrey cubre la AM y nadie queda descubierto. La jornada recibida ya es de Marco
desde que se aprobó, así que puede volver a cederla; los 30 min corporativos los debe quien
REALMENTE dobla ese día.

Ceder la mitad con la que se PAGA una deuda tampoco se bloquea: el nuevo receptor cubre al acreedor
y nace una deuda del mismo tamaño con él, así que la media jornada se acaba trabajando igual — solo
cambia a quién se le debe. Lo que sigue bloqueado son los DESCANSOS ya comprometidos: un día que ya
cediste no se puede ceder dos veces.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from empleados.models import CompetenciaEmpleado, Empleado
from solicitudes.models import DeudaCorporativa, DobladaDetalle, SolicitudCambio
from solicitudes.tests.test_matriz_dobladas import (
    FECHA_CESION,
    FECHA_PAGO,
    MatrizDobladasTestCase,
)
from turnos.services.turno_service import TurnoService


class CederJornadaRecibidaTest(MatrizDobladasTestCase):

    def setUp(self):
        super().setUp()
        # emisor = Marco (base PM). La base del receptor se fija en cada test: para cubrir una
        # jornada cedida hay que tener la CONTRARIA (validación previa de la estrategia).
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        for e in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=e, sala=self.sala)

        # Tercero = Jeison (base AM), que le cede su AM al emisor en FECHA_CESION.
        u = User.objects.create_user('jeison.test', password='x', email='j@t.com')
        self.tercero = Empleado.objects.create(
            user=u, nombre='Jeison', apellido='Test', cedula='9999', email='j@t.com', activo=True)
        self._asignar_jornada_base(self.tercero, self.jornada_am)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.tercero, sala=self.sala)

    def _favor_previo(self, jornada_cedida, solicitante, receptor, fecha_cesion, fecha_pago,
                      completa=False):
        """Doblada APROBADA (sin aplicar turnos) que compromete una mitad del día.

        Con `completa=True` el cedente queda SIN jornada ese día (descanso), que es lo que detecta
        `dia_comprometido_por_solicitud`; una cesión parcial no es descanso y no la ve.
        """
        s = SolicitudCambio.objects.create(
            explorador_solicitante=solicitante, explorador_receptor=receptor,
            tipo_cambio=self.tipo_doblada, comentario='favor previo',
            fecha_cambio_turno=fecha_cesion, estado='aprobada',
            fecha_resolucion=timezone.now())
        DobladaDetalle.objects.create(
            solicitud=s, fecha_pago=fecha_pago, minutos_deuda=30,
            tipo_cesion=('cesion_completa' if completa
                         else f'cesion_parcial_{jornada_cedida.lower()}'),
            jornada_cedida=None if completa else jornada_cedida,
            empleado_receptor=receptor)
        return s

    # ------------------------------------------------------------------
    # Lo que ahora SÍ se permite
    # ------------------------------------------------------------------
    def test_puede_ceder_la_jornada_que_le_cedieron(self):
        """El emisor cubre la AM del tercero; puede volver a cederla al receptor."""
        self._asignar_jornada_base(self.receptor, self.jornada_pm)  # cubre la AM cedida
        self._favor_previo('AM', self.tercero, self.emisor, FECHA_CESION, FECHA_PAGO)
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        # Como en el caso real: el receptor tiene DOBLADA en la fecha de pago y el emisor (PM) le
        # cubre la mitad CONTRARIA a la suya. Si no, salta la regla ajena de "misma jornada".
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)

        datos = self._datos(tipo_cesion='cesion_parcial_am', jornada_cedida='AM',
                            jornada_cubre_en_pago='AM')
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertTrue(ok, f'la jornada recibida ya es suya y el receptor la cubre: {msg}')

    def test_puede_ceder_su_propia_mitad_aunque_la_otra_venga_de_un_pago(self):
        """El chequeo es por MITAD: la mitad propia se cede aunque la otra sea una deuda."""
        self._asignar_jornada_base(self.receptor, self.jornada_am)  # cubre la PM cedida
        # El emisor PAGA su AM en FECHA_CESION (el tercero, base AM, es el acreedor).
        self._favor_previo('PM', self.emisor, self.tercero,
                           FECHA_PAGO, FECHA_CESION)
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)

        # Cede su PM propia, no la AM con la que paga.
        datos = self._datos(tipo_cesion='cesion_parcial_pm', jornada_cedida='PM')
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertTrue(ok, f'ceder la mitad PROPIA no compromete la deuda: {msg}')

    def test_puede_ceder_la_jornada_con_la_que_paga(self):
        """
        Ceder la mitad con la que se paga una deuda tampoco deja huecos: el nuevo receptor cubre al
        acreedor y nace una deuda del MISMO tamaño con ese receptor. No se libra de trabajar la
        media jornada, solo cambia a quién se la debe.
        """
        self._asignar_jornada_base(self.receptor, self.jornada_pm)  # cubre la AM cedida
        self._favor_previo('PM', self.emisor, self.tercero, FECHA_PAGO, FECHA_CESION)
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)

        datos = self._datos(tipo_cesion='cesion_parcial_am', jornada_cedida='AM',
                            jornada_cubre_en_pago='AM')
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertTrue(ok, f'la deuda cambia de acreedor, no desaparece: {msg}')

    # ------------------------------------------------------------------
    # Lo que se sigue bloqueando: los DESCANSOS ya comprometidos
    # ------------------------------------------------------------------
    def test_no_puede_ceder_dos_veces_el_mismo_dia(self):
        """`dia_comprometido_por_solicitud`: un día que ya cediste no se cede de nuevo."""
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        # El emisor ya cedió su día COMPLETO de FECHA_CESION a un tercero → ese día descansa.
        self._favor_previo(None, self.emisor, self.tercero, FECHA_CESION, FECHA_PAGO,
                           completa=True)

        datos = self._datos(tipo_cesion='cesion_parcial_pm', jornada_cedida='PM')
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertFalse(ok, 'ese día ya está comprometido en otra solicitud aprobada')
        self.assertIn('no puedes cederlo de nuevo', msg)

    def test_si_ese_dia_recupero_jornada_real_si_puede_cederla(self):
        """
        Regresión (Marco, 30/07/2026): le pagaban una doblada ese día (descansaba), pero DESPUÉS
        aprobó otra doblada cuyo PAGO cae el mismo día → ese día TRABAJA la jornada del acreedor.
        El bloqueo L2 miraba solo el descanso viejo y decía "ya lo cediste", cuando el estado real
        del día (última aprobada gana) es que tiene jornada y sí puede cederla.
        """
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        # El tercero le PAGA una doblada en FECHA_CESION → el emisor descansaría ese día.
        self._favor_previo(None, self.tercero, self.emisor, FECHA_PAGO, FECHA_CESION,
                           completa=True)
        # Pero el emisor tiene un turno REAL ese día (lo tomó como pago de otra doblada posterior).
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)

        self.assertIsNone(
            TurnoService.dia_comprometido_por_solicitud(self.emisor, FECHA_CESION),
            'con turno real ese día no hay descanso comprometido')

        datos = self._datos(tipo_cesion='cesion_parcial_pm', jornada_cedida='PM')
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertTrue(ok, f'ese día trabaja de verdad, puede cederlo: {msg}')

    # ------------------------------------------------------------------
    # Helper: la mitad comprometida queda identificada
    # ------------------------------------------------------------------
    def test_helper_reporta_la_mitad_comprometida(self):
        self._favor_previo('AM', self.tercero, self.emisor, FECHA_CESION, FECHA_PAGO)
        info = TurnoService.dia_cubriendo_por_solicitud(self.emisor, FECHA_CESION)
        self.assertIsNotNone(info)
        self.assertEqual(info['tipo'], 'cubre_cesion')
        self.assertEqual(info['jornada'], 'AM', 'la mitad comprometida es la jornada cedida')

    def test_helper_reporta_la_mitad_del_pago(self):
        self._favor_previo('PM', self.emisor, self.tercero, FECHA_PAGO, FECHA_CESION)
        info = TurnoService.dia_cubriendo_por_solicitud(self.emisor, FECHA_CESION)
        self.assertIsNotNone(info)
        self.assertEqual(info['tipo'], 'pago')
        # Pagando en semana se cubre la jornada base del acreedor (el tercero es AM).
        self.assertEqual(info['jornada'], 'AM')


class SincronizarDeudaCorporativaTest(MatrizDobladasTestCase):
    """Los 30 min son de quien REALMENTE dobla: si el día deja de ser doblada, se cancelan."""

    def test_cancela_la_deuda_cuando_el_dia_ya_no_es_doblada(self):
        from solicitudes.services.deuda_corporativa_repository import DeudaCorporativaRepository

        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)  # una sola jornada
        deuda = DeudaCorporativaRepository.crear_deuda_corporativa(
            explorador=self.emisor, minutos=30, fecha_doblada=FECHA_CESION,
            comentario='deuda de una doblada que ya se deshizo')

        canceladas = DeudaCorporativaRepository.sincronizar_deuda_corporativa(
            self.emisor, FECHA_CESION, motivo='test')

        self.assertEqual(canceladas, 1)
        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'cancelada')

    def test_conserva_la_deuda_si_sigue_doblando(self):
        from solicitudes.services.deuda_corporativa_repository import DeudaCorporativaRepository

        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        DeudaCorporativaRepository.crear_deuda_corporativa(
            explorador=self.emisor, minutos=30, fecha_doblada=FECHA_CESION)

        self.assertEqual(
            DeudaCorporativaRepository.sincronizar_deuda_corporativa(self.emisor, FECHA_CESION), 0)
        self.assertEqual(
            DeudaCorporativa.objects.filter(explorador=self.emisor, estado='activa').count(), 1)

    def test_no_toca_una_deuda_ya_pagada(self):
        """Una deuda saldada se queda saldada: solo se cancelan las ACTIVAS."""
        from solicitudes.services.deuda_corporativa_repository import DeudaCorporativaRepository

        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)  # ya no dobla
        deuda = DeudaCorporativaRepository.crear_deuda_corporativa(
            explorador=self.emisor, minutos=30, fecha_doblada=FECHA_CESION)
        deuda.estado = 'pagada'
        deuda.save(update_fields=['estado'])

        self.assertEqual(
            DeudaCorporativaRepository.sincronizar_deuda_corporativa(self.emisor, FECHA_CESION), 0)
        deuda.refresh_from_db()
        self.assertEqual(deuda.estado, 'pagada')


class CesionNoPuedeSerHoyTest(MatrizDobladasTestCase):
    """
    Regresión (solicitud #561): se creó y se APROBÓ una doblada con fecha de cesión = HOY.

    La comparación era `fecha_cesion < hoy`, así que el día en curso pasaba. Ceder hoy no da margen
    a nadie: el compañero puede haber trabajado ya su jornada y la solicitud todavía tiene que
    aprobarse. Cambio de descanso y D FDS ya usaban `< hoy or (== hoy and not es_revalidacion)`.
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    def test_no_se_puede_ceder_hoy(self):
        hoy = timezone.localdate()
        datos = self._datos(fecha_cambio_turno=str(hoy),
                            fecha_pago=str(hoy + timedelta(days=1)))
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertFalse(ok, 'la cesión no puede ser el día en curso')
        self.assertIn('no puede ser hoy', msg)

    def test_no_se_puede_ceder_en_el_pasado(self):
        datos = self._datos(fecha_cambio_turno=str(timezone.localdate() - timedelta(days=1)))
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertFalse(ok)
        self.assertIn('pasado', msg)

    def test_al_revalidar_para_aprobar_hoy_si_se_admite(self):
        """
        Una solicitud creada ayer para hoy se aprueba hoy. Sin la excepción quedaría atrapada: no
        se podría aprobar ni rechazar.
        """
        hoy = timezone.localdate()
        datos = self._datos(fecha_cambio_turno=str(hoy),
                            fecha_pago=str(hoy + timedelta(days=1)),
                            es_revalidacion=True)
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertNotIn('no puede ser hoy', msg or '',
                         'al re-validar, la fecha de hoy no debe bloquear la aprobación')


class CalendarioNoOfreceHoyTest(TestCase):
    """
    El calendario debe ofrecer MAÑANA como mínimo en los formularios cuyo backend rechaza el día en
    curso. Si ofrece hoy, la persona llena el formulario entero para chocar con el error al enviarlo
    — que es justo lo que pasó con la solicitud #561.
    """

    def test_doblada_y_d_fds_parten_de_manana(self):
        import inspect

        from solicitudes.views.cambio_turno_pages import SolicitarCambioTurnoView as _V

        for metodo in ('_render_doblada', '_render_d_fds'):
            fuente = inspect.getsource(getattr(_V, metodo))
            self.assertIn(
                "'fecha_minima': timezone.localdate() + timezone.timedelta(days=1)", fuente,
                f'{metodo}: el backend rechaza ceder hoy, así que el calendario no debe ofrecerlo')

    def test_ningun_hoy_se_calcula_en_utc(self):
        """
        `new Date().toISOString()` da la fecha en UTC: en Colombia (UTC-5) eso ya es el día
        siguiente a partir de las 19:00. Cualquier "hoy" así se adelanta un día cada noche y deja
        de cuadrar con las fechas que el usuario elige en el calendario (locales) y con el
        `timezone.localdate()` del backend. Pasó en dos sitios: el respaldo del datepicker y la
        fecha de creación con la que se valida la fecha de pago (rechazaba MAÑANA cada noche).

        OJO: `dayDate.toISOString()` sobre una fecha del calendario NO entra aquí. Esos objetos son
        medianoche local, que con offset negativo cae en el mismo día UTC. Lo que rompe es convertir
        la hora ACTUAL, y por eso el patrón buscado incluye `new Date()`.
        """
        from pathlib import Path

        from django.conf import settings

        js = Path(settings.BASE_DIR) / 'static' / 'js'
        objetivos = [
            js / 'cambio-turno' / 'datepicker_festivos.js',
            js / 'cambio-turno' / 'solicitar_doblada.js',
            js / 'cambio-turno' / 'solicitar_ct_permanente.js',
            js / 'utils' / 'date-utils.js',
        ]
        for ruta in objetivos:
            for n, linea in enumerate(ruta.read_text(encoding='utf-8').splitlines(), 1):
                if linea.lstrip().startswith('*') or linea.lstrip().startswith('//'):
                    continue  # los comentarios sí pueden nombrar el patrón para explicarlo
                self.assertNotIn(
                    "new Date().toISOString()", linea,
                    f'{ruta.name}:{n} calcula "hoy" en UTC; usa la fecha local '
                    f'(DateUtils.getToday() o DatepickerFestivos.fechaMinimaPorDefecto())')


class IdempotenciaPorDiaTest(MatrizDobladasTestCase):
    """
    Patrón #21: la clave idempotente es (explorador, fecha), SIN solicitud_origen.

    Con la solicitud en la clave, dos solicitudes DISTINTAS sobre el mismo día del mismo explorador
    creaban 30 min cada una — 60 min por un solo día doblado — y el guard no las veía.
    """

    def _solicitud(self, comentario):
        return SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, comentario=comentario,
            fecha_cambio_turno=FECHA_CESION, estado='aprobada',
            fecha_resolucion=timezone.now())

    def test_dos_solicitudes_distintas_no_cobran_el_dia_dos_veces(self):
        from solicitudes.services.deuda_corporativa_repository import DeudaCorporativaRepository

        sol_a, sol_b = self._solicitud('A'), self._solicitud('B')
        primera = DeudaCorporativaRepository.crear_deuda_corporativa_idempotente(
            explorador=self.emisor, minutos=30, fecha_doblada=FECHA_CESION, solicitud=sol_a)
        segunda = DeudaCorporativaRepository.crear_deuda_corporativa_idempotente(
            explorador=self.emisor, minutos=30, fecha_doblada=FECHA_CESION, solicitud=sol_b)

        self.assertIsNotNone(primera)
        self.assertIsNone(segunda, 'la segunda solicitud no puede cobrar el mismo día otra vez')
        self.assertEqual(
            DeudaCorporativa.objects.filter(
                explorador=self.emisor, fecha_doblada=FECHA_CESION, estado='activa').count(), 1)
        self.assertEqual(
            DeudaCorporativaRepository.obtener_deuda_total(self.emisor), 30,
            'un día doblado son 30 min, no 60')

    def test_si_la_del_dia_esta_cancelada_se_puede_volver_a_crear(self):
        """Al re-aplicar tras revertir, el día vuelve a deber sus 30 min."""
        from solicitudes.services.deuda_corporativa_repository import DeudaCorporativaRepository

        sol = self._solicitud('única')
        primera = DeudaCorporativaRepository.crear_deuda_corporativa_idempotente(
            explorador=self.emisor, minutos=30, fecha_doblada=FECHA_CESION, solicitud=sol)
        DeudaCorporativaRepository.cancelar_deuda(primera, comentario='revertida')

        segunda = DeudaCorporativaRepository.crear_deuda_corporativa_idempotente(
            explorador=self.emisor, minutos=30, fecha_doblada=FECHA_CESION, solicitud=sol)
        self.assertIsNotNone(segunda, 'la cancelada no debe bloquear la nueva')
        self.assertEqual(DeudaCorporativaRepository.obtener_deuda_total(self.emisor), 30)

    def test_revertir_no_des_paga_una_deuda_ya_pagada(self):
        """
        Al revertir se cancelan las ACTIVAS, no las pagadas. Si se cancelaran, se perdería el
        registro de que el explorador ya compensó esos 30 min y el PDH que las pagó quedaría
        apuntando a una deuda 'cancelada'; al re-aplicar, el guard no vería nada activo y volvería
        a cobrar un día ya pagado.
        """
        from solicitudes.services.deuda_corporativa_repository import DeudaCorporativaRepository

        sol = self._solicitud('con deuda pagada')
        pagada = DeudaCorporativaRepository.crear_deuda_corporativa(
            explorador=self.emisor, minutos=30, fecha_doblada=FECHA_CESION, solicitud=sol)
        pagada.estado = 'pagada'
        pagada.save(update_fields=['estado'])
        activa = DeudaCorporativaRepository.crear_deuda_corporativa(
            explorador=self.receptor, minutos=30, fecha_doblada=FECHA_PAGO, solicitud=sol)

        canceladas = DeudaCorporativaRepository.cancelar_deudas_de_solicitud(sol, motivo='test')

        self.assertEqual(canceladas, 1, 'solo la activa')
        pagada.refresh_from_db()
        activa.refresh_from_db()
        self.assertEqual(pagada.estado, 'pagada', 'lo pagado sigue pagado')
        self.assertEqual(activa.estado, 'cancelada')

    def test_dias_distintos_si_cobran_por_separado(self):
        from solicitudes.services.deuda_corporativa_repository import DeudaCorporativaRepository

        sol = self._solicitud('única')
        for f in (FECHA_CESION, FECHA_PAGO):
            DeudaCorporativaRepository.crear_deuda_corporativa_idempotente(
                explorador=self.emisor, minutos=30, fecha_doblada=f, solicitud=sol)

        self.assertEqual(DeudaCorporativaRepository.obtener_deuda_total(self.emisor), 60,
                         'dos días doblados sí son 60 min')
