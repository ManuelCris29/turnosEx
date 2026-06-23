"""
Tests unitarios — Matriz de combinación: doblada (cesión y pago)

Cubre todos los casos del documento 'Matriz de combinación doblada.pdf':
  CASO 1:  Emisor 1 jornada  | Receptor 1 jornada
  CASO 2:  Emisor 1 jornada  | Receptor DOBLADA  (cesión inválida)
  CASO 3:  Emisor 1 jornada  | Receptor DESCANSANDO
  CASO 4:  Emisor DOBLADA    | Receptor 1 jornada  (cesión parcial)
  CASO 5:  Emisor DOBLADA    | Receptor DOBLADA    (cesión inválida)
  CASO 6:  Emisor DOBLADA    | Receptor DESCANSANDO
  CASO 7:  Emisor DESCANSANDO — siempre inválido en cesión
  CASO 8:  Emisor DESCANSANDO | Receptor DOBLADA   — siempre inválido
  CASO 9:  Ambos DESCANSANDO  — siempre inválido

Estados por persona en una fecha:
  1 JORNADA   → un único turno AM ó PM (o asignación base sin turno específico)
  DOBLADA     → dos turnos AM + PM en Turno table
  DESCANSANDO → sin turno ni asignación base para esa fecha
"""

import json
from datetime import date, timedelta
from django.test import TestCase
from django.contrib.auth.models import User

from empleados.models import Empleado, Jornada
from solicitudes.models import TipoSolicitudCambio, SolicitudCambio, DobladaDetalle
from solicitudes.services.strategies.doblada_strategy import DobladaStrategy
from turnos.models import Turno, AsignarJornadaExplorador, Sala


# ---------------------------------------------------------------------------
# Fechas de prueba — SIEMPRE futuras y en el mismo mes.
#
# Se calculan dinámicamente relativas a date.today() para no caducar: usar
# fechas fijas provoca que, al pasar esa fecha, la validación "la fecha de
# cesión no puede ser en el pasado" rechace todos los casos antes de llegar a
# la lógica real. Tomamos el mes SIGUIENTE (garantiza futuro y holgura para
# no chocar con el fin de mes) y los días 10 y 17 (existen en todo mes),
# saltando domingos (único día bloqueado para doblada; la tabla DiaEspecial
# está vacía en tests, así que no hay festivos ni mantenimiento que evitar).
# ---------------------------------------------------------------------------
def _fechas_prueba_doblada():
    hoy = date.today()
    if hoy.month == 12:
        anio, mes = hoy.year + 1, 1
    else:
        anio, mes = hoy.year, hoy.month + 1

    # Estos casos son de DÍA DE SEMANA (coincidencia de jornada fija AM/PM). En sábado la
    # jornada la gobierna la alternancia de fin de semana, así que se evitan sáb (5) y dom (6)
    # para que las fechas de cesión y pago sean siempre días de semana deterministas.
    cesion = date(anio, mes, 10)
    while cesion.weekday() >= 5:          # evitar sábado y domingo
        cesion += timedelta(days=1)

    pago = date(anio, mes, 17)
    while pago.weekday() >= 5 or pago == cesion:
        pago += timedelta(days=1)

    return cesion, pago


FECHA_CESION, FECHA_PAGO = _fechas_prueba_doblada()


class MatrizDobladasTestCase(TestCase):
    """
    Clase base con toda la infraestructura de prueba.

    Proporciona:
      - jornada_am / jornada_pm
      - sala_test
      - tipo_doblada
      - emisor  (Mariana) con jornada base PM
      - receptor (Jhon)   con jornada base AM
      - helpers para crear turnos y limpiarlos
    """

    # ------------------------------------------------------------------
    # setUp
    # ------------------------------------------------------------------
    def setUp(self):
        # Jornadas
        self.jornada_am = Jornada.objects.create(
            nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00'
        )
        self.jornada_pm = Jornada.objects.create(
            nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00'
        )

        # Sala necesaria por FK de Turno
        self.sala = Sala.objects.create(nombre='Sala Test', activo=True)

        # Tipo de cambio
        self.tipo_doblada, _ = TipoSolicitudCambio.objects.get_or_create(
            nombre='DOBLADA',
            defaults={'activo': True, 'genera_deuda': True}
        )

        # Empleado emisor — jornada base PM
        user_e = User.objects.create_user('mariana_test', password='x', email='m@t.com')
        self.emisor = Empleado.objects.create(
            user=user_e, nombre='Mariana', apellido='Test',
            cedula='1111111111', email='m@t.com', activo=True
        )

        # Empleado receptor — jornada base AM
        user_r = User.objects.create_user('jhon_test', password='x', email='j@t.com')
        self.receptor = Empleado.objects.create(
            user=user_r, nombre='Jhon', apellido='Test',
            cedula='2222222222', email='j@t.com', activo=True
        )

        self.strategy = DobladaStrategy()

    # ------------------------------------------------------------------
    # Helpers de estado
    # ------------------------------------------------------------------
    def _asignar_jornada_base(self, empleado, jornada, desde=None):
        """Asigna jornada base (AsignarJornadaExplorador)."""
        AsignarJornadaExplorador.objects.filter(explorador=empleado).delete()
        AsignarJornadaExplorador.objects.create(
            explorador=empleado,
            jornada=jornada,
            fecha_inicio=desde or date(2026, 1, 1)
        )

    def _crear_turno(self, empleado, fecha, jornada):
        """Crea un Turno específico para la fecha."""
        return Turno.objects.create(
            explorador=empleado,
            fecha=fecha,
            jornada=jornada,
            sala=self.sala,
            tipo_cambio='TEST'
        )

    def _crear_doblada_turnos(self, empleado, fecha):
        """Crea AM + PM para simular estado DOBLADA."""
        self._crear_turno(empleado, fecha, self.jornada_am)
        self._crear_turno(empleado, fecha, self.jornada_pm)

    def _limpiar_turnos(self, empleado, fecha):
        """Elimina todos los turnos del empleado en esa fecha."""
        Turno.objects.filter(explorador=empleado, fecha=fecha).delete()

    def _datos(self, **extra):
        """
        Construye el dict mínimo para DobladaStrategy.validar_solicitud().
        Se puede sobreescribir con **extra.
        """
        base = {
            'explorador_solicitante': self.emisor,
            'explorador_receptor': self.receptor,
            'fecha_cambio_turno': str(FECHA_CESION),
            'fecha_pago': str(FECHA_PAGO),
            'comentario': 'Test de matriz',
            'tipo_cesion': 'cesion_completa',
            'jornada_cedida': None,
            'jornada_pago_sabado': None,
            'jornada_cubre_en_pago': None,
        }
        base.update(extra)
        return base

    # ------------------------------------------------------------------
    # Asertos de conveniencia
    # ------------------------------------------------------------------
    def assertValido(self, datos, msg=''):
        valido, error = self.strategy.validar_solicitud(datos)
        self.assertTrue(valido, f"Se esperaba VÁLIDO pero fue RECHAZADO: {error}. {msg}")

    def assertRechazado(self, datos, texto_esperado='', msg=''):
        valido, error = self.strategy.validar_solicitud(datos)
        self.assertFalse(valido, f"Se esperaba RECHAZADO pero fue VÁLIDO. {msg}")
        if texto_esperado:
            self.assertIn(
                texto_esperado.lower(), error.lower(),
                f"Mensaje inesperado: '{error}'. {msg}"
            )

    def assertRequiereCTSencillo(self, datos, msg=''):
        """Verifica que el rechazo sea por coincidencia de jornadas (requiere CT sencillo)."""
        valido, error = self.strategy.validar_solicitud(datos)
        self.assertFalse(valido, f"Se esperaba bloqueo por CT sencillo pero fue VÁLIDO. {msg}")
        try:
            payload = json.loads(error)
            self.assertEqual(
                payload.get('code'), 'requiere_cambio_turno_previo',
                f"Se esperaba code='requiere_cambio_turno_previo', got: {payload}. {msg}"
            )
        except (json.JSONDecodeError, TypeError):
            self.fail(f"Error no es JSON de CT sencillo: '{error}'. {msg}")


# ===========================================================================
# CASO 7 / 8 / 9 — Emisor DESCANSANDO en cesión (siempre rechazado)
# ===========================================================================
class TestCesionEmisoriDescansando(MatrizDobladasTestCase):
    """Casos 7, 8, 9 — el emisor no tiene jornada en fecha de cesión."""

    def setUp(self):
        super().setUp()
        # Receptor AM en cesión (no importa su estado, el error es del emisor)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        # Emisor SIN asignación base → DESCANSANDO
        AsignarJornadaExplorador.objects.filter(explorador=self.emisor).delete()
        # Pago: emisor descansando también, para no complicar validación de pago
        AsignarJornadaExplorador.objects.filter(explorador=self.emisor).delete()

    def test_caso7_emisor_descansando_receptor_1_jornada(self):
        """CASO 7: Emisor DESCANSANDO | Receptor 1 JORNADA → RECHAZADO."""
        datos = self._datos()
        self.assertRechazado(datos, 'jornada asignada', 'CASO 7')

    def test_caso8_emisor_descansando_receptor_doblada(self):
        """CASO 8: Emisor DESCANSANDO | Receptor DOBLADA → RECHAZADO (error emisor prevalece)."""
        self._crear_doblada_turnos(self.receptor, FECHA_CESION)
        datos = self._datos()
        self.assertRechazado(datos, 'jornada asignada', 'CASO 8')

    def test_caso9_ambos_descansando(self):
        """CASO 9: Emisor DESCANSANDO | Receptor DESCANSANDO → RECHAZADO.
        El validador detecta 'ambos descansando en pago' antes de revisar la cesión."""
        AsignarJornadaExplorador.objects.filter(explorador=self.receptor).delete()
        datos = self._datos()
        # El validador de pago dispara primero: "Los dos están descansando"
        self.assertRechazado(datos, 'descansando', 'CASO 9')


# ===========================================================================
# CASO 2 — Receptor DOBLADA en cesión → cesión siempre inválida
# ===========================================================================
class TestCesionReceptorDoblada(MatrizDobladasTestCase):
    """CASO 2: el receptor tiene AM+PM en la fecha de cesión."""

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        # Receptor DOBLADA en cesión
        self._crear_doblada_turnos(self.receptor, FECHA_CESION)
        # Asignación de pago (no importa para este test)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    def test_caso2_receptor_doblada_en_cesion(self):
        """CASO 2: Emisor 1 JORNADA | Receptor DOBLADA en cesión → RECHAZADO."""
        datos = self._datos()
        self.assertRechazado(datos, 'doblada', 'CASO 2')


# ===========================================================================
# CASO 5 — Emisor DOBLADA | Receptor DOBLADA en cesión → siempre inválido
# ===========================================================================
class TestCesionAmbosDoblada(MatrizDobladasTestCase):
    """CASO 5: ambos tienen doblada en cesión."""

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        self._crear_doblada_turnos(self.receptor, FECHA_CESION)

    def test_caso5_ambos_doblada_en_cesion(self):
        """CASO 5: Emisor DOBLADA | Receptor DOBLADA → RECHAZADO."""
        datos = self._datos(
            tipo_cesion='cesion_parcial_pm',
            jornada_cedida='PM',
        )
        self.assertRechazado(datos, 'doblada', 'CASO 5')


# ===========================================================================
# CASO 1 — Emisor 1 JORNADA | Receptor 1 JORNADA (ambos activos en cesión)
# ===========================================================================
class TestCaso1EmisoryReceptor1Jornada(MatrizDobladasTestCase):
    """
    CASO 1: Emisor tiene 1 jornada (PM) y Receptor tiene 1 jornada (AM)
    en la fecha de cesión. Variantes según estado en fecha de pago.
    """

    def setUp(self):
        super().setUp()
        # Cesión: emisor PM, receptor AM (contrarias → OK)
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    # ------------------------------------------------------------------
    # 1.1 La combinación perfecta — pago: emisor PM, receptor AM
    # ------------------------------------------------------------------
    def test_caso1_1_combinacion_perfecta(self):
        """CASO 1.1: Pago en fecha donde emisor PM, receptor AM → VÁLIDO."""
        # Jornadas base ya son PM / AM — no necesita turnos extra
        self.assertValido(self._datos(), 'CASO 1.1')

    # ------------------------------------------------------------------
    # 1.2 Ambos DESCANSANDO en pago → RECHAZADO
    # ------------------------------------------------------------------
    def test_caso1_2_ambos_descansando_en_pago(self):
        """CASO 1.2: Pago: emisor DESC + receptor DESC → RECHAZADO."""
        # Borrar asignaciones base para que en pago ambos descansen
        AsignarJornadaExplorador.objects.all().delete()
        # Restaurar cesión para que la validación de cesión pase
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        # Para la fecha de pago: sin turno y sin asignación que cubra esa fecha → descansando
        # Como la asignación cubre desde 2026-01-01, vamos a quitar todo
        # y recrear solo para cesión usando fecha_inicio en la cesión (no pago)
        AsignarJornadaExplorador.objects.all().delete()
        AsignarJornadaExplorador.objects.create(
            explorador=self.emisor, jornada=self.jornada_pm,
            fecha_inicio=FECHA_CESION
        )
        AsignarJornadaExplorador.objects.create(
            explorador=self.receptor, jornada=self.jornada_am,
            fecha_inicio=FECHA_CESION
        )
        # Crear una segunda asignación con fecha_inicio DESPUÉS de pago para bloquear pago
        # No — más sencillo: no hay asignación que cubra FECHA_PAGO porque la asignación
        # empieza exactamente en FECHA_CESION y JornadaService busca fecha_inicio <= fecha.
        # FECHA_PAGO > FECHA_CESION → aún la cubre. Necesitamos otro enfoque.
        # La forma más directa: asignar jornada base solo HASTA cesión (no hay "fecha_fin")
        # → usar Turno SOLO en cesión y eliminar base, luego no habrá jornada en pago.
        AsignarJornadaExplorador.objects.all().delete()
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Sin asignación base → en FECHA_PAGO ambos descansando
        self.assertRechazado(
            self._datos(), 'descansando', 'CASO 1.2'
        )

    # ------------------------------------------------------------------
    # 1.3 Emisor DESCANSANDO + Receptor 1 JORNADA en pago → VÁLIDO
    # ------------------------------------------------------------------
    def test_caso1_3_emisor_descansando_receptor_jornada_en_pago(self):
        """CASO 1.3: Pago: emisor DESC + receptor AM → VÁLIDO."""
        AsignarJornadaExplorador.objects.all().delete()
        # Cesión vía turno directo
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Pago: solo receptor tiene jornada
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        # Emisor sin nada en pago → descansando
        self.assertValido(self._datos(), 'CASO 1.3')

    # ------------------------------------------------------------------
    # 1.4 Emisor DESCANSANDO + Receptor DOBLADA en pago → VÁLIDO
    # ------------------------------------------------------------------
    def test_caso1_4_emisor_descansando_receptor_doblada_en_pago(self):
        """CASO 1.4: Pago: emisor DESC + receptor DOBLADA → VÁLIDO."""
        AsignarJornadaExplorador.objects.all().delete()
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Receptor tiene doblada en fecha de pago
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertValido(self._datos(), 'CASO 1.4')

    # ------------------------------------------------------------------
    # 1.5 Emisor 1 JORNADA + Receptor DESCANSANDO en pago → RECHAZADO
    # ------------------------------------------------------------------
    def test_caso1_5_receptor_descansando_en_pago(self):
        """CASO 1.5: Pago: emisor AM/PM + receptor DESC → RECHAZADO."""
        AsignarJornadaExplorador.objects.all().delete()
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Emisor tiene jornada en pago; receptor no
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_pm)
        self.assertRechazado(
            self._datos(), 'receptor', 'CASO 1.5'
        )

    # ------------------------------------------------------------------
    # 1.6 Emisor 1 JORNADA + Receptor 1 JORNADA (misma) → requiere CT sencillo
    # ------------------------------------------------------------------
    def test_caso1_6_misma_jornada_en_pago_requiere_ct_sencillo(self):
        """CASO 1.6: Pago: emisor AM + receptor AM (misma) → bloqueo CT sencillo."""
        AsignarJornadaExplorador.objects.all().delete()
        # Cesión: emisor PM, receptor AM (contrarias OK)
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Pago: ambos con AM (misma jornada)
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertRequiereCTSencillo(self._datos(), 'CASO 1.6')

    def test_caso1_6_jornadas_distintas_en_pago_valido(self):
        """CASO 1.6 variante: Pago: emisor AM + receptor PM (distintas) → VÁLIDO."""
        AsignarJornadaExplorador.objects.all().delete()
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Pago: jornadas distintas
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_pm)
        self.assertValido(self._datos(), 'CASO 1.6 jornadas distintas')

    # ------------------------------------------------------------------
    # 1.7 Emisor 1 JORNADA + Receptor DOBLADA en pago → VÁLIDO
    # ------------------------------------------------------------------
    def test_caso1_7_emisor_jornada_receptor_doblada_en_pago(self):
        """CASO 1.7: Pago: emisor 1 jornada + receptor DOBLADA → VÁLIDO."""
        AsignarJornadaExplorador.objects.all().delete()
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Pago: emisor solo AM, receptor AM+PM
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertValido(self._datos(), 'CASO 1.7')

    # ------------------------------------------------------------------
    # 1.8 Emisor PM + Receptor DESCANSANDO en pago → RECHAZADO
    # ------------------------------------------------------------------
    def test_caso1_8_emisor_pm_receptor_descansando_en_pago(self):
        """CASO 1.8: Pago: emisor PM + receptor DESC → RECHAZADO."""
        AsignarJornadaExplorador.objects.all().delete()
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Pago: solo emisor tiene jornada
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_pm)
        # Receptor sin nada en pago
        self.assertRechazado(self._datos(), 'receptor', 'CASO 1.8')

    # ------------------------------------------------------------------
    # 1.9 Emisor DOBLADA + Receptor 1 JORNADA en pago → RECHAZADO
    # ------------------------------------------------------------------
    def test_caso1_9_emisor_doblada_en_pago(self):
        """CASO 1.9: Pago: emisor DOBLADA → RECHAZADO (no tiene jornada libre)."""
        AsignarJornadaExplorador.objects.all().delete()
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Pago: emisor DOBLADA, receptor 1 jornada
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertRechazado(self._datos(), 'doblada', 'CASO 1.9')

    # ------------------------------------------------------------------
    # 1.10 Ambos DOBLADA en pago → RECHAZADO
    # ------------------------------------------------------------------
    def test_caso1_10_ambos_doblada_en_pago(self):
        """CASO 1.10: Pago: emisor DOBLADA + receptor DOBLADA → RECHAZADO."""
        AsignarJornadaExplorador.objects.all().delete()
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertRechazado(self._datos(), 'doblada', 'CASO 1.10')


# ===========================================================================
# CASO 3 — Emisor 1 JORNADA | Receptor DESCANSANDO en cesión
# ===========================================================================
class TestCaso3ReceptorDescansandoEnCesion(MatrizDobladasTestCase):
    """
    CASO 3: Emisor tiene 1 jornada, receptor DESCANSANDO en la fecha de cesión.
    El validador permite la cesión cuando el receptor descansa (sub-casos 3.x
    se distinguen por el estado en la fecha de pago).
    """

    def setUp(self):
        super().setUp()
        # Cesión: emisor PM, receptor DESCANSANDO (sin asignación en cesión)
        AsignarJornadaExplorador.objects.all().delete()
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        # Receptor: sin turno ni asignación → DESCANSANDO en cesión

    # 3.1 — ambos descansando en pago → RECHAZADO
    def test_caso3_1_ambos_descansando_en_pago(self):
        """CASO 3.1: Pago: emisor DESC + receptor DESC → RECHAZADO."""
        self.assertRechazado(self._datos(), 'descansando', 'CASO 3.1')

    # 3.2 — emisor descansando + receptor 1 jornada en pago → VÁLIDO
    def test_caso3_2_emisor_descansando_receptor_jornada_en_pago(self):
        """CASO 3.2: Pago: emisor DESC + receptor AM → VÁLIDO."""
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertValido(self._datos(), 'CASO 3.2')

    # 3.4 — emisor descansando + receptor DOBLADA en pago → VÁLIDO
    def test_caso3_4_emisor_descansando_receptor_doblada_en_pago(self):
        """CASO 3.4: Pago: emisor DESC + receptor DOBLADA → VÁLIDO."""
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertValido(self._datos(), 'CASO 3.4')

    # 3.5 — emisor 1 jornada + receptor descansando en pago → RECHAZADO
    def test_caso3_5_receptor_descansando_en_pago(self):
        """CASO 3.5: Pago: emisor PM + receptor DESC → RECHAZADO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_pm)
        self.assertRechazado(self._datos(), 'receptor', 'CASO 3.5')

    # 3.6 — emisor 1 jornada + receptor 1 jornada en pago
    def test_caso3_6_misma_jornada_en_pago_requiere_ct_sencillo(self):
        """CASO 3.6: Pago: emisor AM + receptor AM (misma) → bloqueo CT sencillo."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertRequiereCTSencillo(self._datos(), 'CASO 3.6')

    def test_caso3_6_jornadas_distintas_valido(self):
        """CASO 3.6 variante: Pago: emisor AM + receptor PM → VÁLIDO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_pm)
        self.assertValido(self._datos(), 'CASO 3.6 distintas')

    # 3.7 — emisor 1 jornada + receptor DOBLADA en pago → VÁLIDO
    def test_caso3_7_emisor_jornada_receptor_doblada_en_pago(self):
        """CASO 3.7: Pago: emisor AM + receptor DOBLADA → VÁLIDO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertValido(self._datos(), 'CASO 3.7')

    # 3.8 — emisor PM + receptor descansando en pago → RECHAZADO
    def test_caso3_8_receptor_descansando_en_pago(self):
        """CASO 3.8: Pago: emisor PM + receptor DESC → RECHAZADO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_pm)
        self.assertRechazado(self._datos(), 'receptor', 'CASO 3.8')

    # 3.9 — emisor DOBLADA + receptor descansando en pago → RECHAZADO
    def test_caso3_9_emisor_doblada_receptor_descansando_en_pago(self):
        """CASO 3.9: Pago: emisor DOBLADA + receptor DESC → RECHAZADO.
        El validador detecta 'receptor sin jornada' antes que 'emisor tiene doblada'."""
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        # receptor está descansando → validación de receptor dispara primero
        self.assertRechazado(self._datos(), 'receptor', 'CASO 3.9')

    # 3.14a — emisor DOBLADA + receptor 1 jornada en pago → RECHAZADO
    def test_caso3_14a_emisor_doblada_receptor_jornada_en_pago(self):
        """CASO 3.14: Pago: emisor DOBLADA + receptor 1 jornada → RECHAZADO."""
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertRechazado(self._datos(), 'doblada', 'CASO 3.14a')

    # 3.14b — ambos DOBLADA en pago → RECHAZADO
    def test_caso3_14b_ambos_doblada_en_pago(self):
        """CASO 3.14 (2do): Pago: emisor DOBLADA + receptor DOBLADA → RECHAZADO."""
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertRechazado(self._datos(), 'doblada', 'CASO 3.14b')


# ===========================================================================
# CASO 4 — Emisor DOBLADA en cesión (cede 1 jornada) | Receptor 1 JORNADA
# ===========================================================================
class TestCaso4EmisoriDobladaCesionParcial(MatrizDobladasTestCase):
    """
    CASO 4: Emisor tiene DOBLADA (AM+PM) en cesión y cede solo 1 jornada
    (cesión parcial). Receptor tiene 1 jornada en cesión.
    """

    def setUp(self):
        super().setUp()
        AsignarJornadaExplorador.objects.all().delete()
        # Emisor DOBLADA en cesión
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        # Receptor 1 jornada (AM) en cesión
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)

    def _datos_parcial(self, **extra):
        return self._datos(
            tipo_cesion='cesion_parcial_pm',
            jornada_cedida='PM',
            **extra
        )

    # 4.1 — ambos descansando en pago → RECHAZADO
    def test_caso4_1_ambos_descansando_en_pago(self):
        """CASO 4.1: Pago: emisor DESC + receptor DESC → RECHAZADO."""
        self.assertRechazado(self._datos_parcial(), 'descansando', 'CASO 4.1')

    # 4.2 — emisor descansando + receptor 1 jornada en pago → VÁLIDO
    def test_caso4_2_emisor_descansando_receptor_jornada_en_pago(self):
        """CASO 4.2: Pago: emisor DESC + receptor AM → VÁLIDO."""
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertValido(self._datos_parcial(), 'CASO 4.2')

    # 4.2b — emisor descansando + receptor DOBLADA en pago → VÁLIDO
    def test_caso4_2b_emisor_descansando_receptor_doblada_en_pago(self):
        """CASO 4.2b: Pago: emisor DESC + receptor DOBLADA → VÁLIDO."""
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertValido(self._datos_parcial(), 'CASO 4.2b')

    # 4.3 — emisor 1 jornada + receptor descansando en pago → RECHAZADO
    def test_caso4_3_receptor_descansando_en_pago(self):
        """CASO 4.3: Pago: emisor PM + receptor DESC → RECHAZADO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_pm)
        self.assertRechazado(self._datos_parcial(), 'receptor', 'CASO 4.3')

    # 4.4 — emisor 1 jornada + receptor 1 jornada (misma) → CT sencillo
    def test_caso4_4_misma_jornada_en_pago_requiere_ct_sencillo(self):
        """CASO 4.4: Pago: emisor PM + receptor PM (misma) → bloqueo CT sencillo."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_pm)
        self.assertRequiereCTSencillo(self._datos_parcial(), 'CASO 4.4')

    def test_caso4_4_jornadas_distintas_valido(self):
        """CASO 4.4 variante: Pago: emisor PM + receptor AM (distintas) → VÁLIDO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertValido(self._datos_parcial(), 'CASO 4.4 distintas')

    # 4.5 — emisor 1 jornada + receptor DOBLADA en pago → VÁLIDO
    def test_caso4_5_emisor_jornada_receptor_doblada_en_pago(self):
        """CASO 4.5: Pago: emisor AM + receptor DOBLADA → VÁLIDO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertValido(self._datos_parcial(), 'CASO 4.5')

    # 4.6 — emisor 1 jornada + receptor descansando → RECHAZADO
    def test_caso4_6_receptor_descansando_en_pago(self):
        """CASO 4.6: Pago: emisor AM + receptor DESC → RECHAZADO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self.assertRechazado(self._datos_parcial(), 'receptor', 'CASO 4.6')

    # 4.7 — emisor DOBLADA + receptor descansando en pago → RECHAZADO
    def test_caso4_7_emisor_doblada_receptor_descansando_en_pago(self):
        """CASO 4.7: Pago: emisor DOBLADA + receptor DESC → RECHAZADO.
        Receptor descansando dispara antes que emisor con doblada."""
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self.assertRechazado(self._datos_parcial(), 'receptor', 'CASO 4.7')

    # 4.8 — emisor DOBLADA + receptor 1 jornada en pago → RECHAZADO
    def test_caso4_8_emisor_doblada_receptor_jornada_en_pago(self):
        """CASO 4.8: Pago: emisor DOBLADA + receptor 1 jornada → RECHAZADO."""
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertRechazado(self._datos_parcial(), 'doblada', 'CASO 4.8')

    # 4.9 — ambos DOBLADA en pago → RECHAZADO
    def test_caso4_9_ambos_doblada_en_pago(self):
        """CASO 4.9: Pago: emisor DOBLADA + receptor DOBLADA → RECHAZADO."""
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertRechazado(self._datos_parcial(), 'doblada', 'CASO 4.9')

    # 4A.11 — emisor PM + receptor PM (misma jornada) → CT sencillo
    def test_caso4a_11_mismo_pm_en_pago_requiere_ct_sencillo(self):
        """CASO 4A.11: Pago: emisor PM + receptor PM → bloqueo CT sencillo."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_pm)
        self.assertRequiereCTSencillo(self._datos_parcial(), 'CASO 4A.11')


# ===========================================================================
# CASO 6 — Emisor DOBLADA en cesión | Receptor DESCANSANDO en cesión
# ===========================================================================
class TestCaso6EmisoriDobladaReceptorDescansandoEnCesion(MatrizDobladasTestCase):
    """
    CASO 6: Emisor tiene DOBLADA en cesión, receptor DESCANSANDO en cesión.
    Cesión parcial: emisor cede una jornada al receptor que está descansando.
    """

    def setUp(self):
        super().setUp()
        AsignarJornadaExplorador.objects.all().delete()
        # Emisor DOBLADA en cesión
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        # Receptor DESCANSANDO en cesión (sin turno ni asignación)

    def _datos_parcial(self, **extra):
        return self._datos(
            tipo_cesion='cesion_parcial_am',
            jornada_cedida='AM',
            **extra
        )

    # 6.1 — emisor descansando + receptor 1 jornada en pago → VÁLIDO
    def test_caso6_1_emisor_descansando_receptor_jornada_en_pago(self):
        """CASO 6.1: Pago: emisor DESC + receptor AM → VÁLIDO."""
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertValido(self._datos_parcial(), 'CASO 6.1')

    # 6.2 — ambos descansando en pago → RECHAZADO
    def test_caso6_2_ambos_descansando_en_pago(self):
        """CASO 6.2: Pago: emisor DESC + receptor DESC → RECHAZADO."""
        self.assertRechazado(self._datos_parcial(), 'descansando', 'CASO 6.2')

    # 6.3 — emisor descansando + receptor DOBLADA en pago → VÁLIDO
    def test_caso6_3_emisor_descansando_receptor_doblada_en_pago(self):
        """CASO 6.3: Pago: emisor DESC + receptor DOBLADA → VÁLIDO."""
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertValido(self._datos_parcial(), 'CASO 6.3')

    # 6.4 — emisor descansando + receptor 1 jornada en pago → VÁLIDO
    def test_caso6_4_emisor_descansando_receptor_jornada_en_pago(self):
        """CASO 6.4: Pago: emisor DESC + receptor AM → VÁLIDO."""
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertValido(self._datos_parcial(), 'CASO 6.4')

    # 6.5 — emisor 1 jornada + receptor descansando en pago → RECHAZADO
    def test_caso6_5_receptor_descansando_en_pago(self):
        """CASO 6.5: Pago: emisor AM + receptor DESC → RECHAZADO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self.assertRechazado(self._datos_parcial(), 'receptor', 'CASO 6.5')

    # 6.6 — emisor 1 jornada + receptor 1 jornada en pago
    def test_caso6_6_misma_jornada_en_pago_requiere_ct_sencillo(self):
        """CASO 6.6: Pago: emisor AM + receptor AM (misma) → bloqueo CT sencillo."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertRequiereCTSencillo(self._datos_parcial(), 'CASO 6.6')

    def test_caso6_6_jornadas_distintas_valido(self):
        """CASO 6.6 variante: Pago: emisor AM + receptor PM (distintas) → VÁLIDO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_pm)
        self.assertValido(self._datos_parcial(), 'CASO 6.6 distintas')

    # 6.7 — emisor 1 jornada + receptor DOBLADA en pago → VÁLIDO
    def test_caso6_7_emisor_jornada_receptor_doblada_en_pago(self):
        """CASO 6.7: Pago: emisor AM + receptor DOBLADA → VÁLIDO."""
        self._crear_turno(self.emisor, FECHA_PAGO, self.jornada_am)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertValido(self._datos_parcial(), 'CASO 6.7')

    # 6.8 — emisor DOBLADA + receptor descansando en pago → RECHAZADO
    def test_caso6_8_emisor_doblada_receptor_descansando_en_pago(self):
        """CASO 6.8: Pago: emisor DOBLADA + receptor DESC → RECHAZADO.
        Receptor descansando dispara antes que emisor con doblada."""
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self.assertRechazado(self._datos_parcial(), 'receptor', 'CASO 6.8')

    # 6.9 — emisor DOBLADA + receptor 1 jornada en pago → RECHAZADO
    def test_caso6_9_emisor_doblada_receptor_jornada_en_pago(self):
        """CASO 6.9: Pago: emisor DOBLADA + receptor AM → RECHAZADO."""
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertRechazado(self._datos_parcial(), 'doblada', 'CASO 6.9')

    # 6.10 — ambos DOBLADA en pago → RECHAZADO
    def test_caso6_10_ambos_doblada_en_pago(self):
        """CASO 6.10: Pago: emisor DOBLADA + receptor DOBLADA → RECHAZADO."""
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        self.assertRechazado(self._datos_parcial(), 'doblada', 'CASO 6.10')


# ===========================================================================
# Tests de validaciones generales (comentario, fechas, mismo empleado)
# ===========================================================================
class TestValidacionesGenerales(MatrizDobladasTestCase):
    """Validaciones transversales que aplican a cualquier caso."""

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    def test_comentario_vacio_rechazado(self):
        """Sin comentario → RECHAZADO."""
        datos = self._datos(comentario='')
        self.assertRechazado(datos, 'comentario', 'Comentario vacío')

    def test_comentario_solo_espacios_rechazado(self):
        """Comentario solo con espacios → RECHAZADO."""
        datos = self._datos(comentario='   ')
        self.assertRechazado(datos, 'comentario', 'Comentario espacios')

    def test_mismo_empleado_rechazado(self):
        """Solicitante == receptor → RECHAZADO."""
        datos = self._datos()
        datos['explorador_receptor'] = self.emisor
        self.assertRechazado(datos, msg='Mismo empleado')

    def test_fecha_cesion_en_pasado_rechazado(self):
        """Fecha de cesión en el pasado → RECHAZADO."""
        cesion_pasada = date.today() - timedelta(days=30)
        datos = self._datos(
            fecha_cambio_turno=str(cesion_pasada),
            fecha_pago=str(cesion_pasada + timedelta(days=7)),
        )
        self.assertRechazado(datos, 'pasado', 'Fecha cesión pasada')

    def test_fecha_pago_diferente_mes_rechazado(self):
        """Fecha de pago en mes diferente al de cesión → RECHAZADO."""
        datos = self._datos(
            fecha_cambio_turno=str(FECHA_CESION),                 # mes base
            fecha_pago=str(FECHA_CESION + timedelta(days=40)),    # ~mes siguiente
        )
        self.assertRechazado(datos, 'mes', 'Diferente mes')

    def test_fecha_pago_igual_cesion_rechazado(self):
        """Fecha de pago == fecha de cesión → RECHAZADO."""
        datos = self._datos(
            fecha_cambio_turno=str(FECHA_CESION),
            fecha_pago=str(FECHA_CESION),
        )
        self.assertRechazado(datos, 'misma', 'Mismo día cesión/pago')

    def test_empleado_inactivo_rechazado(self):
        """Empleado inactivo → RECHAZADO."""
        self.emisor.activo = False
        self.emisor.save()
        self.assertRechazado(self._datos(), msg='Empleado inactivo')
        self.emisor.activo = True
        self.emisor.save()

    def test_solicitud_pendiente_existente_rechazado(self):
        """Si ya existe solicitud pendiente del solicitante en fecha cesión → RECHAZADO."""
        SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='pendiente',
            fecha_cambio_turno=FECHA_CESION,
        )
        self.assertRechazado(self._datos(), 'pendiente', 'Solicitud duplicada')


# ===========================================================================
# Deuda de 30 min al EMISOR: cesión de doblada de SEMANA pagada en SÁBADO
# ===========================================================================
class TestDeudaEmisorDobladaSemanaPagoSabado(MatrizDobladasTestCase):
    """
    Regla de negocio: cuando el EMISOR cede una jornada de una DOBLADA que tenía
    en un día de SEMANA y la paga en SÁBADO, deben generarse 30 min para AMBOS:
      - Receptor: dobla (AM+PM) en la fecha de cesión (día de semana) → 30 min.
      - Emisor:   por la doblada de semana que cedió, asociada al DÍA DE SEMANA
                  de la cesión (el sábado por sí solo no genera 30 min).
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    @staticmethod
    def _martes_y_sabado_futuros():
        """Devuelve (martes futuro, sábado de esa misma semana)."""
        d = date.today() + timedelta(days=7)
        while d.weekday() != 1:          # 1 = martes
            d += timedelta(days=1)
        cesion = d
        sabado = cesion + timedelta(days=(5 - cesion.weekday()))  # sábado misma semana
        return cesion, sabado

    def _crear_solicitud_detalle(self, cesion, sabado, snapshot_emisor):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=cesion,
            comentario='Test deuda emisor sábado',
        )
        detalle = DobladaDetalle.objects.create(
            solicitud=sol,
            fecha_pago=sabado,
            tipo_cesion='cesion_parcial_am',
            jornada_cedida='AM',
            empleado_receptor=self.receptor,
            jornada_pago_sabado='AM',
            snapshot_turnos_previos=snapshot_emisor,
        )
        return sol, detalle

    def test_emisor_recibe_30min_por_doblada_semana_pagada_en_sabado(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        from solicitudes.models import DeudaCorporativa

        cesion, sabado = self._martes_y_sabado_futuros()
        # Receptor dobla (AM+PM) en la cesión → debe recibir sus 30 min.
        self._crear_doblada_turnos(self.receptor, cesion)
        # Snapshot: el emisor TENÍA una doblada (AM+PM) en el día de semana de cesión.
        snapshot = {
            f"{self.emisor.id}:{cesion.isoformat()}": [
                {'jornada_nombre': 'AM', 'sala_id': self.sala.id, 'tipo_cambio': 'DOBLADA'},
                {'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': 'DOBLADA'},
            ],
        }
        sol, detalle = self._crear_solicitud_detalle(cesion, sabado, snapshot)

        DobladaAplicacionService.generar_deudas_doblada(sol, detalle)

        deuda_emisor = DeudaCorporativa.objects.filter(
            explorador=self.emisor, fecha_doblada=cesion, estado='activa'
        )
        self.assertTrue(
            deuda_emisor.exists(),
            "El emisor debe recibir 30 min por la doblada de semana cedida pagada en sábado.",
        )
        self.assertEqual(deuda_emisor.first().minutos, 30)

        deuda_receptor = DeudaCorporativa.objects.filter(
            explorador=self.receptor, fecha_doblada=cesion, estado='activa'
        )
        self.assertTrue(
            deuda_receptor.exists(),
            "El receptor debe recibir 30 min por doblar en la fecha de cesión.",
        )


# ===========================================================================
# Pago en SÁBADO de un subpago de cesión total (cesión parcial) + fix AMBAS
# ===========================================================================
class TestPagoSabadoCesionParcial(MatrizDobladasTestCase):
    """
    Un subpago de cesión total que cae en sábado (cesión parcial) es válido cuando el
    emisor elige la jornada (AM/PM) y el receptor trabaja ese sábado por alternancia.
    Además, pagar 'AMBAS' sin día de semana ya NO debe crashear con NameError (bug
    de fecha_pago_semana que solo se leía en crear_solicitud).
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    @staticmethod
    def _sabado_am_y_cesion():
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
        d = date.today() + timedelta(days=10)
        while not (d.weekday() == 5 and (AlternanciaFinesSemanaService.jornada_trabaja_sabado(d) or '').upper() == 'AM'):
            d += timedelta(days=1)
        sab = d
        ces = date(sab.year, sab.month, 2)
        while ces.weekday() >= 5 or ces <= date.today():
            ces += timedelta(days=1)
        return ces, sab

    def _datos_parcial_pm(self, ces, sab, jps):
        return {
            'explorador_solicitante': self.emisor,
            'explorador_receptor': self.receptor,
            'fecha_cambio_turno': str(ces),
            'fecha_pago': str(sab),
            'comentario': 'test pago sábado',
            'tipo_cesion': 'cesion_parcial_pm',
            'jornada_cedida': 'PM',
            'jornada_pago_sabado': jps,
            'fecha_creacion_solicitud': date.today(),
        }

    def test_subpago_sabado_am_valido(self):
        ces, sab = self._sabado_am_y_cesion()
        self._crear_turno(self.emisor, ces, self.jornada_pm)
        self._crear_turno(self.receptor, ces, self.jornada_am)
        ok, msg = self.strategy.validar_solicitud(self._datos_parcial_pm(ces, sab, 'AM'))
        self.assertTrue(ok, f"Esperaba VÁLIDO el subpago de sábado (AM): {msg}")

    def test_pago_ambas_sin_fecha_semana_no_crashea(self):
        ces, sab = self._sabado_am_y_cesion()
        self._crear_turno(self.emisor, ces, self.jornada_pm)
        self._crear_turno(self.receptor, ces, self.jornada_am)
        ok, msg = self.strategy.validar_solicitud(self._datos_parcial_pm(ces, sab, 'AMBAS'))
        self.assertFalse(ok)
        # No debe ser un crash de NameError, sino un rechazo de negocio claro.
        self.assertNotIn('not defined', str(msg))
        self.assertNotIn('NameError', str(msg))


# ===========================================================================
# Receptor descansa por ALTERNANCIA de fin de semana en la fecha de pago
# ===========================================================================
class TestReceptorDescansaFinDeSemanaEnPago(MatrizDobladasTestCase):
    """
    Si la fecha de pago cae en un SÁBADO donde el receptor DESCANSA por alternancia, no hay
    jornada que cubrir → la solicitud debe RECHAZARSE. Antes la validación usaba la jornada
    predeterminada (que ignora el descanso de fin de semana) y dejaba pasar el pago.
    """

    @staticmethod
    def _sabado_futuro():
        d = date.today() + timedelta(days=7)
        while d.weekday() != 5:   # 5 = sábado
            d += timedelta(days=1)
        return d

    def test_receptor_descansa_sabado_por_alternancia_rechaza(self):
        from django.core.exceptions import ValidationError
        from solicitudes.services.solicitud_validator import SolicitudValidator
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
        sab = self._sabado_futuro()
        trabaja = (AlternanciaFinesSemanaService.jornada_trabaja_sabado(sab) or 'AM').upper()
        descansa = 'PM' if trabaja == 'AM' else 'AM'
        # Receptor con jornada base del grupo que DESCANSA ese sábado.
        self._asignar_jornada_base(self.receptor, self.jornada_am if descansa == 'AM' else self.jornada_pm)
        with self.assertRaises(ValidationError):
            SolicitudValidator.validar_receptor_tiene_jornada_en_fecha_pago(self.receptor, sab.isoformat())

    def test_receptor_trabaja_sabado_por_alternancia_permite(self):
        from solicitudes.services.solicitud_validator import SolicitudValidator
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
        sab = self._sabado_futuro()
        trabaja = (AlternanciaFinesSemanaService.jornada_trabaja_sabado(sab) or 'AM').upper()
        # Receptor con jornada base del grupo que SÍ trabaja ese sábado → no debe rechazar.
        self._asignar_jornada_base(self.receptor, self.jornada_am if trabaja == 'AM' else self.jornada_pm)
        SolicitudValidator.validar_receptor_tiene_jornada_en_fecha_pago(self.receptor, sab.isoformat())

    def test_solicitante_descansa_sabado_en_cesion_rechaza(self):
        """El SOLICITANTE descansa por alternancia en la fecha de cesión → no tiene jornada que ceder."""
        from django.core.exceptions import ValidationError
        from solicitudes.services.solicitud_validator import SolicitudValidator
        from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
        sab = self._sabado_futuro()
        trabaja = (AlternanciaFinesSemanaService.jornada_trabaja_sabado(sab) or 'AM').upper()
        descansa = 'PM' if trabaja == 'AM' else 'AM'
        # Solicitante en el grupo que DESCANSA ese sábado; receptor en el que trabaja.
        self._asignar_jornada_base(self.emisor, self.jornada_am if descansa == 'AM' else self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am if trabaja == 'AM' else self.jornada_pm)
        with self.assertRaises(ValidationError):
            SolicitudValidator.validar_jornadas_contrarias_doblada(
                self.emisor, self.receptor, sab.isoformat(), None
            )


# ===========================================================================
# Reconciliación al cancelar una CESIÓN TOTAL (snapshots intermedios)
# ===========================================================================
class TestReconciliacionRevertCesionTotal(MatrizDobladasTestCase):
    """
    Al cancelar una cesión total (2 solicitudes enlazadas que comparten la fecha de
    cesión), el snapshot intermedio puede dejar al solicitante con MEDIA doblada. La
    reconciliación re-aplica las dobladas que SIGUEN APROBADAS sobre las fechas afectadas
    y restaura el estado correcto (AM+PM), sin importar el orden de cancelación.
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_am)
        self._asignar_jornada_base(self.receptor, self.jornada_pm)

    def _crear_doblada_aprobada_pago(self, fdob):
        from django.utils import timezone
        from solicitudes.models import DobladaDetalle
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=FECHA_CESION,
            fecha_resolucion=timezone.now(),
            comentario='doblada base aprobada',
        )
        DobladaDetalle.objects.create(
            solicitud=sol,
            fecha_pago=fdob,
            tipo_cesion='cesion_completa',
            jornada_cedida='PM',
            empleado_receptor=self.receptor,
        )
        return sol

    def test_reconciliacion_restaura_doblada_del_solicitante(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        fdob = FECHA_PAGO  # día de semana garantizado por el helper
        self._crear_doblada_aprobada_pago(fdob)
        # Estado INTERMEDIO tras un revert mal hecho: el solicitante quedó solo con AM.
        self._limpiar_turnos(self.emisor, fdob)
        self._crear_turno(self.emisor, fdob, self.jornada_am)

        DobladaAplicacionService.reconciliar_dobladas_aprobadas(
            {(self.emisor.id, fdob)}, excluir_solicitud_id=999999
        )

        jornadas = {
            j.upper()
            for j in Turno.objects.filter(explorador=self.emisor, fecha=fdob)
            .values_list('jornada__nombre', flat=True)
        }
        self.assertEqual(
            {'AM', 'PM'}, jornadas,
            "La reconciliación debe restaurar la doblada completa (AM+PM) del solicitante.",
        )

    def test_reconciliacion_sin_dobladas_aprobadas_no_cambia(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        fdob = FECHA_PAGO
        self._limpiar_turnos(self.emisor, fdob)
        self._crear_turno(self.emisor, fdob, self.jornada_am)

        # No hay dobladas aprobadas en esa fecha → no debe tocar nada.
        DobladaAplicacionService.reconciliar_dobladas_aprobadas(
            {(self.emisor.id, fdob)}, excluir_solicitud_id=999999
        )
        jornadas = {
            j.upper()
            for j in Turno.objects.filter(explorador=self.emisor, fecha=fdob)
            .values_list('jornada__nombre', flat=True)
        }
        self.assertEqual({'AM'}, jornadas)


class TestDeudaEmisorContinuacion(MatrizDobladasTestCase):
    """Continúa los casos de deuda del emisor (separado por claridad)."""

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    @staticmethod
    def _martes_y_sabado_futuros():
        d = date.today() + timedelta(days=7)
        while d.weekday() != 1:
            d += timedelta(days=1)
        cesion = d
        sabado = cesion + timedelta(days=(5 - cesion.weekday()))
        return cesion, sabado

    def _crear_solicitud_detalle(self, cesion, sabado, snapshot_emisor):
        from solicitudes.models import DobladaDetalle
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=cesion,
            comentario='Test deuda emisor sábado (cont.)',
        )
        detalle = DobladaDetalle.objects.create(
            solicitud=sol,
            fecha_pago=sabado,
            tipo_cesion='cesion_parcial_am',
            jornada_cedida='AM',
            empleado_receptor=self.receptor,
            jornada_pago_sabado='AM',
            snapshot_turnos_previos=snapshot_emisor,
        )
        return sol, detalle

    def test_emisor_sin_doblada_previa_no_recibe_30min(self):
        """Si el emisor NO tenía doblada de semana (snapshot de 1 jornada), no se le cargan 30 min."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        from solicitudes.models import DeudaCorporativa

        cesion, sabado = self._martes_y_sabado_futuros()
        self._crear_doblada_turnos(self.receptor, cesion)
        # Snapshot: el emisor tenía UNA sola jornada (no era doblada).
        snapshot = {
            f"{self.emisor.id}:{cesion.isoformat()}": [
                {'jornada_nombre': 'PM', 'sala_id': self.sala.id, 'tipo_cambio': None},
            ],
        }
        sol, detalle = self._crear_solicitud_detalle(cesion, sabado, snapshot)

        DobladaAplicacionService.generar_deudas_doblada(sol, detalle)

        self.assertFalse(
            DeudaCorporativa.objects.filter(
                explorador=self.emisor, fecha_doblada=cesion, estado='activa'
            ).exists(),
            "El emisor NO debe recibir 30 min si no tenía una doblada de semana.",
        )
