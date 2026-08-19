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
from django.utils import timezone
from core.constants import TipoCambioTurno


# ---------------------------------------------------------------------------
# Fechas de prueba — SIEMPRE futuras y en el mismo mes.
#
# Se calculan dinámicamente relativas a timezone.localdate() para no caducar: usar
# fechas fijas provoca que, al pasar esa fecha, la validación "la fecha de
# cesión no puede ser en el pasado" rechace todos los casos antes de llegar a
# la lógica real. Tomamos el mes SIGUIENTE (garantiza futuro y holgura para
# no chocar con el fin de mes) y los días 10 y 17 (existen en todo mes),
# saltando domingos (único día bloqueado para doblada; la tabla DiaEspecial
# está vacía en tests, así que no hay festivos ni mantenimiento que evitar).
# ---------------------------------------------------------------------------
def _fechas_prueba_doblada():
    hoy = timezone.localdate()
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
        # Caché limpia entre tests (turnos, estado_dia, etc.): cada test recrea sus jornadas y
        # empleados, así que nada de la corrida anterior debe sobrevivir.
        # (`obtener_jornadas_am_pm` ya no cachea instancias, que era la causa de los
        # IntegrityError de FK al aplicar dobladas; esto sigue por el resto de cachés.)
        from django.core.cache import cache as _django_cache
        _django_cache.clear()
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

        # La alternancia de findes es un DATO publicado, no una fórmula: sin publicarla,
        # los findes de estos tests saldrían como 'sin_planificar'.
        from turnos.tests.alternancia_helpers import publicar_alternancia
        publicar_alternancia(FECHA_CESION.year, FECHA_PAGO.year)

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

    def _crear_turno(self, empleado, fecha, jornada, tipo_cambio=None):
        """Crea un Turno específico para la fecha.

        Por defecto `tipo_cambio=None`: turno normal, el estado de partida sobre el
        que después se aplica la doblada. Antes ponía 'TEST', un marcador inventado
        que no existe en el dominio y que hacía que estos turnos base contaran como
        "turno con un cambio aplicado" en los filtros que excluyen `tipo_cambio`
        nulo o vacío.
        """
        return Turno.objects.create(
            explorador=empleado,
            fecha=fecha,
            jornada=jornada,
            sala=self.sala,
            tipo_cambio=tipo_cambio
        )

    def _crear_doblada_turnos(self, empleado, fecha):
        """Crea AM + PM para simular estado DOBLADA.

        Marcados como DOBLADA a propósito: la validación del intercambio no cuenta
        dos turnos sueltos como una doblada, exige que vengan de una.
        """
        self._crear_turno(empleado, fecha, self.jornada_am, TipoCambioTurno.DOBLADA)
        self._crear_turno(empleado, fecha, self.jornada_pm, TipoCambioTurno.DOBLADA)

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
        cesion_pasada = timezone.localdate() - timedelta(days=30)
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
    Regla de negocio: CEDER una doblada NO genera 30 min al emisor (ceder no es
    doblarse). Cuando el EMISOR cede una jornada de una DOBLADA que tenía en un
    día de SEMANA y la paga en SÁBADO:
      - Receptor: dobla (AM+PM) en la fecha de cesión (día de semana) → 30 min.
      - Emisor:   NO se le generan 30 min por ceder (sus 30 min previos, si los
                  tuviera de otra doblada, quedan intactos; ceder no añade otros).
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    @staticmethod
    def _martes_y_sabado_futuros():
        """Devuelve (martes futuro, sábado de esa misma semana)."""
        d = timezone.localdate() + timedelta(days=7)
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

    def test_emisor_no_recibe_30min_por_ceder_doblada_semana_pagada_en_sabado(self):
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

        # Ceder NO genera 30 min al emisor (no hay deuda previa en este test → no debe existir ninguna).
        deuda_emisor = DeudaCorporativa.objects.filter(
            explorador=self.emisor, fecha_doblada=cesion, estado='activa'
        )
        self.assertFalse(
            deuda_emisor.exists(),
            "Ceder una doblada NO debe generar 30 min al emisor.",
        )

        # El receptor sí recibe sus 30 min por doblar en la fecha de cesión.
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
        d = timezone.localdate() + timedelta(days=10)
        while not (d.weekday() == 5 and (AlternanciaFinesSemanaService.jornada_trabaja_sabado(d) or '').upper() == 'AM'):
            d += timedelta(days=1)
        sab = d
        ces = date(sab.year, sab.month, 2)
        while ces.weekday() >= 5 or ces <= timezone.localdate():
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
            'fecha_creacion_solicitud': timezone.localdate(),
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
# Cubrir pago de receptor con DOBLADA: emisor con jornada VIRTUAL (predeterminada)
# ===========================================================================
class TestCubrePagoReceptorDobladaJornadaVirtual(MatrizDobladasTestCase):
    """
    Si el receptor tiene DOBLADA en la fecha de pago y el emisor trabaja UNA jornada ese día
    —aunque sea VIRTUAL (predeterminada, sin fila Turno)— solo puede cubrir la CONTRARIA:
    no la misma (la haría dos veces) ni AMBAS (su propia jornada quedaría sin cubrir).
    Antes el chequeo solo miraba turnos explícitos, así que con jornada virtual dejaba pasar.
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    def _datos(self, jcp):
        return {
            'explorador_solicitante': self.emisor,
            'explorador_receptor': self.receptor,
            'fecha_cambio_turno': str(FECHA_CESION),
            'fecha_pago': str(FECHA_PAGO),
            'comentario': 'test cubre pago',
            'tipo_cesion': 'cesion_completa',
            'jornada_cubre_en_pago': jcp,
            'fecha_creacion_solicitud': timezone.localdate(),
        }

    def test_solo_puede_cubrir_la_contraria(self):
        from turnos.services.turno_service import TurnoService
        # Cesión válida: emisor PM, receptor AM (contrarios, explícitos).
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_pm)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_am)
        # Pago: receptor con DOBLADA; emisor SIN turno (jornada virtual/predeterminada).
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        emisor_j = TurnoService.obtener_jornada_display(self.emisor, FECHA_PAGO)
        self.assertIn(emisor_j, ('AM', 'PM'))
        contraria = 'PM' if emisor_j == 'AM' else 'AM'

        ok_misma, _ = self.strategy.validar_solicitud(self._datos(emisor_j))
        self.assertFalse(ok_misma, 'Cubrir la MISMA jornada que trabaja el emisor debe rechazarse')

        ok_ambas, _ = self.strategy.validar_solicitud(self._datos('AMBAS'))
        self.assertFalse(ok_ambas, 'Cubrir AMBAS debe rechazarse cuando el emisor trabaja una jornada')

        ok_contra, msg = self.strategy.validar_solicitud(self._datos(contraria))
        self.assertTrue(ok_contra, f'Cubrir la jornada CONTRARIA debe permitirse: {msg}')

    def test_aplicar_pago_el_deudor_queda_doblada(self):
        """Al pagar cubriendo una jornada del receptor (con doblada), el DEUDOR DOBLA
        (su jornada + la que cubre); el receptor conserva la otra."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        from solicitudes.models import DobladaDetalle
        from empleados.models import CompetenciaEmpleado
        # El emisor necesita una sala (vía competencia) porque su jornada en el pago es virtual.
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        # Pago: receptor con DOBLADA (AM+PM); emisor sin turno (su PM es virtual).
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada',
            fecha_cambio_turno=FECHA_CESION, comentario='t',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, fecha_pago=FECHA_PAGO, tipo_cesion='cesion_completa',
            jornada_cedida='PM', jornada_cubre_en_pago='AM', empleado_receptor=self.receptor,
        )
        DobladaAplicacionService.aplicar_doblada_pago(sol, det)
        em = {j.upper() for j in Turno.objects.filter(explorador=self.emisor, fecha=FECHA_PAGO).values_list('jornada__nombre', flat=True)}
        rec = {j.upper() for j in Turno.objects.filter(explorador=self.receptor, fecha=FECHA_PAGO).values_list('jornada__nombre', flat=True)}
        self.assertEqual({'AM', 'PM'}, em, 'El deudor debe quedar con doblada (su PM + el AM que cubre).')
        self.assertEqual({'PM'}, rec, 'El receptor conserva solo PM (el deudor cubrió su AM).')


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
        d = timezone.localdate() + timedelta(days=7)
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
        d = timezone.localdate() + timedelta(days=7)
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


# ===========================================================================
# FESTIVO: jornada completa por alternancia, pero SIN deuda corporativa (30 min)
# ===========================================================================
class TestDobladaFestivoSinDeudaCorporativa(MatrizDobladasTestCase):
    """
    Regla de negocio: en un día FESTIVO se trabaja la jornada completa (AM+PM) por
    alternancia, pero NO se generan los 30 minutos de deuda corporativa porque es
    festivo. Debe cumplirse aunque la persona quede físicamente DOBLADA en esa fecha.

    Se fija aquí para que el guard único `DeudaCorporativaService.aplica_deuda_doblada`
    (que excluye festivos vía DiaEspecial tipo='festivo') no se rompa a futuro.
    FECHA_CESION y FECHA_PAGO ya son DÍAS DE SEMANA del mismo mes; al marcarlas festivo,
    el ÚNICO motivo para no generar la deuda es el festivo (no el fin de semana).
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    def _marcar_festivo(self, fecha):
        from turnos.models import DiaEspecial
        DiaEspecial.objects.create(
            fecha=fecha, tipo='festivo', descripcion='Festivo test', activo=True
        )

    def test_festivo_no_genera_deuda_corporativa(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService
        from solicitudes.models import DeudaCorporativa

        # Marcar como festivo ambas fechas (días de semana del mismo mes).
        self._marcar_festivo(FECHA_CESION)
        self._marcar_festivo(FECHA_PAGO)

        # Sanidad: son días de semana → el único motivo de exclusión es el festivo.
        self.assertLess(FECHA_CESION.weekday(), 5)
        self.assertLess(FECHA_PAGO.weekday(), 5)
        self.assertFalse(DeudaCorporativaService.aplica_deuda_doblada(FECHA_CESION))
        self.assertFalse(DeudaCorporativaService.aplica_deuda_doblada(FECHA_PAGO))

        # Ambos quedan físicamente DOBLADOS (AM+PM) en su festivo. Sin la regla de
        # festivo, esto generaría 30 min para cada uno (receptor en cesión, emisor en pago).
        self._crear_doblada_turnos(self.receptor, FECHA_CESION)
        self._crear_doblada_turnos(self.emisor, FECHA_PAGO)

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=FECHA_CESION,
            comentario='Test festivo sin 30 min',
        )
        detalle = DobladaDetalle.objects.create(
            solicitud=sol,
            fecha_pago=FECHA_PAGO,
            tipo_cesion='cesion_completa',
            jornada_cedida='AM',  # evita el path None->.nombre; no afecta la deuda corporativa
            empleado_receptor=self.receptor,
        )

        DobladaAplicacionService.generar_deudas_doblada(sol, detalle)

        # Ninguna deuda corporativa (ni emisor ni receptor) en los festivos.
        self.assertFalse(
            DeudaCorporativa.objects.filter(
                explorador=self.receptor, fecha_doblada=FECHA_CESION
            ).exists(),
            "El receptor NO debe recibir 30 min: la fecha de cesión es festivo.",
        )
        self.assertFalse(
            DeudaCorporativa.objects.filter(
                explorador=self.emisor, fecha_doblada=FECHA_PAGO
            ).exists(),
            "El emisor NO debe recibir 30 min: la fecha de pago es festivo.",
        )
        self.assertEqual(
            DeudaCorporativa.objects.count(), 0,
            "Un día festivo no debe generar ninguna deuda corporativa (30 min).",
        )


# ===========================================================================
# INTERCAMBIO DE DOBLADAS: swap de días doblados (sin deuda)
# ===========================================================================
class TestDescansoDelAcreedorEnElPago(MatrizDobladasTestCase):
    """
    Qué pierde el ACREEDOR en la fecha de pago. Lo decide el reparto del PAGO
    (`jornada_pago_sabado` / `jornada_cubre_en_pago`), NUNCA `tipo_cesion`, que describe el día de
    la CESIÓN. Regresión (Mariana → arley, #568): con cesión parcial PM y pago en día de semana, el
    acreedor quedaba libre el día COMPLETO (el deudor cubre su única jornada) pero se atribuía medio
    día, así que no se reportaba descanso: sin fila `Turno` y sin motivo, `estado_dia` caía a la
    jornada BASE y lo mostraba trabajando.
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        from empleados.models import CompetenciaEmpleado
        for e in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=e, sala=self.sala)

    def _aprobar_y_aplicar(self, **detalle_extra):
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from django.utils import timezone as _tz

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada',
            fecha_cambio_turno=FECHA_CESION, comentario='pago en día de semana',
            fecha_resolucion=_tz.now(),
        )
        DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=FECHA_PAGO,
            empleado_receptor=self.receptor, **detalle_extra)
        ok, msg = self.strategy.aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        return sol

    def test_cesion_parcial_deja_al_acreedor_libre_el_dia_completo_del_pago(self):
        from turnos.services.turno_service import TurnoService

        self._crear_doblada_turnos(self.emisor, FECHA_CESION)   # el emisor tiene AM+PM y cede la PM
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)  # el acreedor trabaja solo AM
        self._aprobar_y_aplicar(tipo_cesion='cesion_parcial_pm', jornada_cedida='PM')

        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_PAGO).count(), 0,
                         'el deudor cubre su única jornada: el acreedor queda sin turnos')
        est = TurnoService.estado_dia(self.receptor, FECHA_PAGO)
        self.assertFalse(est['trabaja'], f'el acreedor debe quedar LIBRE el día del pago: {est}')
        self.assertEqual(est['fuente'], 'solicitud')
        self.assertEqual(est['motivo'], 'paga doblada')

    def test_si_solo_cubre_una_mitad_el_acreedor_conserva_la_otra(self):
        """Con `jornada_cubre_en_pago` AM/PM el acreedor sigue trabajando la mitad contraria: ahí
        NO hay descanso de día completo que atribuir."""
        from turnos.services.turno_service import TurnoService

        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)   # el acreedor tiene AM+PM
        self._aprobar_y_aplicar(tipo_cesion='cesion_parcial_pm', jornada_cedida='PM',
                                jornada_cubre_en_pago='AM')

        jornadas = set(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_PAGO)
                       .values_list('jornada__nombre', flat=True))
        self.assertEqual(jornadas, {'PM'}, 'le cubren la AM; conserva la PM')
        est = TurnoService.estado_dia(self.receptor, FECHA_PAGO)
        self.assertTrue(est['trabaja'], f'sigue trabajando media jornada: {est}')


class TestIntercambioDobladas(MatrizDobladasTestCase):
    """
    Intercambio de dobladas: dos exploradores que cada uno tiene una DOBLADA (AM+PM) en
    días distintos intercambian esos días. Día A: el receptor dobla y el solicitante
    descansa; día B: el solicitante dobla y el receptor descansa. NO genera ni altera
    deudas (es 'un cambio de turno pero de días doblados').
    """

    def setUp(self):
        super().setUp()
        # En un intercambio, cada uno debe estar LIBRE el día del otro. Partimos SIN jornada base
        # (ambos descansando en días de semana) y la DOBLADA se fija solo en el día propio de cada
        # quien con turnos reales (L1). Así el swap válido cumple "libre el día del otro".
        AsignarJornadaExplorador.objects.filter(
            explorador__in=[self.emisor, self.receptor]
        ).delete()

    def _js(self, empleado, fecha):
        return {t.jornada.nombre.upper()
                for t in Turno.objects.filter(explorador=empleado, fecha=fecha).select_related('jornada')}

    def test_intercambio_swap_correcto_y_sin_deudas(self):
        from solicitudes.models import SolicitudCambio, DobladaDetalle, DeudaCorporativa, DeudaExplorador
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        dia_a, dia_b = FECHA_CESION, FECHA_PAGO
        self.assertNotEqual(dia_a, dia_b)
        # Ambos con DOBLADA (AM+PM) en su día
        self._crear_doblada_turnos(self.emisor, dia_a)
        self._crear_doblada_turnos(self.receptor, dia_b)

        # Validación: intercambio válido cuando ambos tienen doblada
        self.assertValido(
            self._datos(es_intercambio=True, fecha_cambio_turno=str(dia_a), fecha_pago=str(dia_b)),
            'intercambio con ambas dobladas',
        )

        # Crear solicitud aprobada + detalle de intercambio y aplicar
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=dia_a,
            comentario='intercambio de dobladas',
        )
        DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=dia_b, tipo_cesion='cesion_completa',
            empleado_receptor=self.receptor, es_intercambio=True,
        )
        dc0 = DeudaCorporativa.objects.count()
        de0 = DeudaExplorador.objects.count()

        ok, _msg = self.strategy.aplicar_cambios(sol)
        self.assertTrue(ok, _msg)

        # Swap: día A → receptor AM+PM, emisor sin turnos; día B → emisor AM+PM, receptor sin turnos
        self.assertEqual(self._js(self.receptor, dia_a), {'AM', 'PM'})
        self.assertEqual(Turno.objects.filter(explorador=self.emisor, fecha=dia_a).count(), 0)
        self.assertEqual(self._js(self.emisor, dia_b), {'AM', 'PM'})
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=dia_b).count(), 0)

        # SIN deudas nuevas (ni corporativa ni entre exploradores)
        self.assertEqual(DeudaCorporativa.objects.count(), dc0, 'no debe crear deuda corporativa')
        self.assertEqual(DeudaExplorador.objects.count(), de0, 'no debe crear deuda entre exploradores')
        self.assertEqual(DeudaCorporativa.objects.filter(solicitud_origen=sol).count(), 0)
        self.assertEqual(DeudaExplorador.objects.filter(solicitud_origen=sol).count(), 0)

        # Revertir restaura ambos días (cada uno vuelve a su doblada)
        DobladaAplicacionService.revertir_doblada_aplicada(sol)
        self.assertEqual(self._js(self.emisor, dia_a), {'AM', 'PM'})
        self.assertEqual(self._js(self.receptor, dia_b), {'AM', 'PM'})

    def test_cancelar_otra_doblada_no_deshace_el_intercambio_vigente(self):
        """
        Regresión (mildrey ↔ arley, #566): al cancelar una doblada posterior, la reconciliación
        re-aplica las solicitudes que SIGUEN aprobadas sobre las fechas afectadas. El intercambio
        vigente se re-aplicaba con la lógica de cesión/pago (no tiene lado "cesión" ni "pago": es un
        swap de día completo), y en vez de devolverle a cada uno su DOBLADA los dejaba con una sola
        media jornada — mildrey con una PM el 06/08 y arley con una AM el 12/08.
        """
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        from empleados.models import CompetenciaEmpleado
        from django.utils import timezone

        dia_a, dia_b = FECHA_CESION, FECHA_PAGO
        # Sala por competencia: al re-aplicar sobre un día sin turnos no hay sala que heredar.
        for e in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=e, sala=self.sala)
        self._crear_doblada_turnos(self.emisor, dia_a)
        self._crear_doblada_turnos(self.receptor, dia_b)

        # 1) Intercambio APROBADO y aplicado: cada uno asume la doblada del otro.
        inter = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=dia_a,
            comentario='intercambio vigente', fecha_resolucion=timezone.now(),
        )
        DobladaDetalle.objects.create(
            solicitud=inter, minutos_deuda=30, fecha_pago=dia_b,
            tipo_cesion='cesion_parcial_am', jornada_cedida='AM',
            empleado_receptor=self.receptor, es_intercambio=True,
        )
        ok, msg = self.strategy.aplicar_cambios(inter)
        self.assertTrue(ok, msg)
        self.assertEqual(self._js(self.receptor, dia_a), {'AM', 'PM'})
        self.assertEqual(self._js(self.emisor, dia_b), {'AM', 'PM'})

        # 2) Otra doblada posterior sobre las MISMAS fechas: se aplica (snapshot + turnos, sin
        #    deudas: este caso de prueba corre sin jornada base) y se cancela.
        posterior = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=dia_b,
            comentario='doblada que se cancela', fecha_resolucion=timezone.now(),
        )
        det_post = DobladaDetalle.objects.create(
            solicitud=posterior, minutos_deuda=30, fecha_pago=dia_a,
            tipo_cesion='cesion_completa', empleado_receptor=self.receptor,
        )
        snap = DobladaAplicacionService.capturar_snapshot_turnos_previos(posterior, det_post)
        DobladaDetalle.objects.filter(pk=det_post.pk).update(snapshot_turnos_previos=snap)
        DobladaAplicacionService.aplicar_doblada_cesion(posterior, det_post)
        DobladaAplicacionService.aplicar_doblada_pago(posterior, det_post)
        self.assertNotEqual(self._js(self.receptor, dia_a), {'AM', 'PM'},
                            'la doblada posterior debe haber mutado el estado del swap')

        posterior.refresh_from_db()
        DobladaAplicacionService.revertir_doblada_aplicada(posterior)

        # 3) El intercambio sigue aprobado → cada uno recupera la DOBLADA COMPLETA que tenía.
        self.assertEqual(self._js(self.receptor, dia_a), {'AM', 'PM'},
                         'el receptor debe recuperar la doblada del día A que asumió por el swap')
        self.assertEqual(self._js(self.emisor, dia_b), {'AM', 'PM'},
                         'el emisor debe recuperar la doblada del día B que asumió por el swap')
        self.assertEqual(Turno.objects.filter(explorador=self.emisor, fecha=dia_a).count(), 0)
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=dia_b).count(), 0)

    def test_intercambio_atribuye_descanso_completo_a_los_dos_lados(self):
        """
        Regresión (mildrey ↔ arley, #565): el detalle del intercambio llegó con
        `tipo_cesion='cesion_parcial_am'` (ruido del formulario). La atribución de descanso leía ese
        campo, tomaba el día por MEDIO y no reportaba nada; con el día sin turnos (los borra
        `aplicar_intercambio`) y sin motivo, `estado_dia` caía al fallback de la jornada BASE y
        mostraba trabajando a quien tenía el día libre. Un intercambio es día completo por los dos
        lados, sea cual sea el `tipo_cesion` guardado.
        """
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from turnos.services.turno_service import TurnoService

        dia_a, dia_b = FECHA_CESION, FECHA_PAGO
        # Jornada base para que el fallback tenga algo que mostrar si la atribución falla.
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        self._crear_doblada_turnos(self.emisor, dia_a)
        self._crear_doblada_turnos(self.receptor, dia_b)

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=dia_a,
            comentario='intercambio con tipo_cesion parcial heredado del formulario',
        )
        DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=dia_b,
            tipo_cesion='cesion_parcial_am', jornada_cedida='AM',
            empleado_receptor=self.receptor, es_intercambio=True,
        )
        ok, _msg = self.strategy.aplicar_cambios(sol)
        self.assertTrue(ok, _msg)

        # Día A: el emisor cedió su doblada completa → libre, y la fuente es la solicitud.
        est_a = TurnoService.estado_dia(self.emisor, dia_a)
        self.assertFalse(est_a['trabaja'], f'el emisor cedió su doblada del día A: {est_a}')
        self.assertEqual(est_a['fuente'], 'solicitud')
        # Día B: el receptor entregó la suya → libre también.
        est_b = TurnoService.estado_dia(self.receptor, dia_b)
        self.assertFalse(est_b['trabaja'], f'el receptor entregó su doblada del día B: {est_b}')
        self.assertEqual(est_b['fuente'], 'solicitud')
        # Y quien asume cada doblada sí trabaja (AM+PM).
        self.assertEqual(self._js(self.receptor, dia_a), {'AM', 'PM'})
        self.assertEqual(self._js(self.emisor, dia_b), {'AM', 'PM'})

    def test_intercambio_se_guarda_como_cesion_completa(self):
        """El `tipo_cesion` parcial que manda el formulario se normaliza al crear la solicitud."""
        from solicitudes.models import SolicitudCambio

        dia_a, dia_b = FECHA_CESION, FECHA_PAGO
        self._crear_doblada_turnos(self.emisor, dia_a)
        self._crear_doblada_turnos(self.receptor, dia_b)

        ok, msg = self.strategy.crear_solicitud(self._datos(
            es_intercambio=True, fecha_cambio_turno=str(dia_a), fecha_pago=str(dia_b),
            tipo_cesion='cesion_parcial_am', jornada_cedida='AM',
            tipo_cambio=self.tipo_doblada))
        self.assertTrue(ok, msg)

        det = SolicitudCambio.objects.filter(
            explorador_solicitante=self.emisor, fecha_cambio_turno=dia_a).latest('id').doblada
        self.assertTrue(det.es_intercambio)
        self.assertEqual(det.tipo_cesion, 'cesion_completa', 'un intercambio es día completo')
        self.assertIsNone(det.jornada_cedida)

    def test_intercambio_rechaza_si_el_companero_no_tiene_doblada(self):
        # Emisor con doblada en A; receptor con UNA sola jornada en B (no doblada) → rechazado
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        self._crear_turno(self.receptor, FECHA_PAGO, self.jornada_am)
        self.assertRechazado(
            self._datos(es_intercambio=True, fecha_cambio_turno=str(FECHA_CESION), fecha_pago=str(FECHA_PAGO)),
            'doblada',
        )

    def test_intercambio_revalidar_al_aprobar_honra_flag(self):
        """Regresión: la re-validación al aprobar debe reconstruir es_intercambio (si se pierde,
        corre la regla de cesión normal y rechaza un intercambio válido)."""
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from solicitudes.services.solicitud_factory import SolicitudFactory

        dia_a, dia_b = FECHA_CESION, FECHA_PAGO
        # Intercambio VÁLIDO: cada uno con doblada en su día y libre el día del otro.
        self._crear_doblada_turnos(self.emisor, dia_a)
        self._crear_doblada_turnos(self.receptor, dia_b)

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='pendiente', fecha_cambio_turno=dia_a,
            comentario='intercambio de dobladas',
        )
        DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=dia_b, tipo_cesion='cesion_completa',
            empleado_receptor=self.receptor, es_intercambio=True,
        )

        # Guarda directa del fix de reconstrucción: el flag debe viajar a la re-validación.
        datos = self.strategy._datos_desde_solicitud(sol)
        self.assertTrue(datos.get('es_intercambio'),
                        '_datos_desde_solicitud debe incluir es_intercambio')

        ok, msg = SolicitudFactory.revalidar_para_aprobar(sol)
        self.assertTrue(ok, f'la re-validación de un intercambio válido no debe rechazar: {msg}')

    def test_intercambio_rechaza_si_receptor_no_libre_dia_a(self):
        """El receptor debe estar LIBRE el día A para asumir la doblada del solicitante. Si ese
        día ya trabaja (aunque tenga su doblada el día B), el intercambio se rechaza."""
        dia_a, dia_b = FECHA_CESION, FECHA_PAGO
        self._crear_doblada_turnos(self.emisor, dia_a)     # emisor doblada en A
        self._crear_doblada_turnos(self.receptor, dia_b)   # receptor doblada en B
        self._crear_turno(self.receptor, dia_a, self.jornada_am)  # receptor OCUPADO el día A
        self.assertRechazado(
            self._datos(es_intercambio=True, fecha_cambio_turno=str(dia_a), fecha_pago=str(dia_b)),
            'no está libre',
        )

    def test_intercambio_rechaza_sabado_por_sabado(self):
        """Sábado por sábado se gestiona en D FDS, también cuando es un INTERCAMBIO.

        Regresión histórica: el intercambio retornaba antes de esta regla y se colaba. La regla
        vive ahora en el bloque de REGLAS COMUNES de `validar_solicitud`, que corre ANTES del
        corte del intercambio, así que rige ambos caminos sin estar duplicada."""
        sab_a = FECHA_CESION
        while sab_a.weekday() != 5:
            sab_a += timedelta(days=1)
        sab_b = sab_a + timedelta(days=7)
        # Ambos con DOBLADA en su sábado y libres el del otro (el resto de guards en verde).
        self._crear_doblada_turnos(self.emisor, sab_a)
        self._crear_doblada_turnos(self.receptor, sab_b)
        self.assertRechazado(
            self._datos(es_intercambio=True, fecha_cambio_turno=str(sab_a), fecha_pago=str(sab_b)),
            'D FDS',
        )

    def test_intercambio_hereda_regla_mismo_mes(self):
        """Las reglas comunes de doblada corren ANTES del corte del intercambio: el día B debe
        estar en el mismo mes que el día A."""
        dia_a = FECHA_CESION
        dia_b = dia_a + timedelta(days=30)     # mes siguiente
        while dia_b.weekday() == 6:            # domingo no es día de doblada
            dia_b += timedelta(days=1)
        self.assertNotEqual(dia_a.month, dia_b.month)
        self._crear_doblada_turnos(self.emisor, dia_a)
        self._crear_doblada_turnos(self.receptor, dia_b)
        self.assertRechazado(
            self._datos(es_intercambio=True, fecha_cambio_turno=str(dia_a), fecha_pago=str(dia_b)),
            'mes',
        )

    def test_intercambio_hereda_regla_dia_mantenimiento(self):
        """No hay doblada en día de mantenimiento, tampoco por intercambio."""
        from turnos.models import DiaEspecial
        dia_a, dia_b = FECHA_CESION, FECHA_PAGO
        self._crear_doblada_turnos(self.emisor, dia_a)
        self._crear_doblada_turnos(self.receptor, dia_b)
        DiaEspecial.objects.create(fecha=dia_b, tipo='mantenimiento')
        self.assertRechazado(
            self._datos(es_intercambio=True, fecha_cambio_turno=str(dia_a), fecha_pago=str(dia_b)),
            'mantenimiento',
        )

    def test_intercambio_hereda_regla_solicitud_pendiente(self):
        """Si el día A ya tiene una solicitud PENDIENTE del solicitante, no se puede enviar un
        intercambio sobre ese mismo día (antes solo se miraban las aprobadas)."""
        from solicitudes.models import SolicitudCambio
        dia_a, dia_b = FECHA_CESION, FECHA_PAGO
        self._crear_doblada_turnos(self.emisor, dia_a)
        self._crear_doblada_turnos(self.receptor, dia_b)
        SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='pendiente', fecha_cambio_turno=dia_a,
            comentario='otra solicitud pendiente sobre el mismo día',
        )
        self.assertRechazado(
            self._datos(es_intercambio=True, fecha_cambio_turno=str(dia_a), fecha_pago=str(dia_b)),
            'pendiente',
        )

    def test_intercambio_rechaza_si_solicitante_no_libre_dia_b(self):
        """El solicitante debe estar LIBRE el día B para asumir la doblada del receptor."""
        dia_a, dia_b = FECHA_CESION, FECHA_PAGO
        self._crear_doblada_turnos(self.emisor, dia_a)     # emisor doblada en A
        self._crear_doblada_turnos(self.receptor, dia_b)   # receptor doblada en B
        self._crear_turno(self.emisor, dia_b, self.jornada_pm)  # emisor OCUPADO el día B
        self.assertRechazado(
            self._datos(es_intercambio=True, fecha_cambio_turno=str(dia_a), fecha_pago=str(dia_b)),
            'no estás libre',
        )


class TestCesionParcialReceptorDobla(MatrizDobladasTestCase):
    """Cesión parcial: el receptor que YA trabaja su jornada contraria la conserva y se DOBLA
    (antes la aplicación le borraba su jornada y quedaba en media, perdiendo su turno y sus 30 min)."""

    def test_receptor_que_trabaja_conserva_su_jornada_y_se_dobla(self):
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        dia = FECHA_CESION
        # Emisor con doblada (AM+PM) ese día; receptor trabaja PM (contraria a la AM cedida).
        self._crear_doblada_turnos(self.emisor, dia)
        self._crear_turno(self.receptor, dia, self.jornada_pm)

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=dia,
            comentario='cesión parcial AM',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=FECHA_PAGO,
            tipo_cesion='cesion_parcial_am', jornada_cedida='AM', empleado_receptor=self.receptor,
        )
        DobladaAplicacionService.aplicar_doblada_cesion(sol, det)

        # El receptor CONSERVA su PM y suma la AM cedida = DOBLADA (no media jornada).
        js = {t.jornada.nombre.upper()
              for t in Turno.objects.filter(explorador=self.receptor, fecha=dia).select_related('jornada')}
        self.assertEqual(js, {'AM', 'PM'}, f'el receptor debe quedar doblado (AM+PM), quedó: {js}')


class TestPagoParcialDeudorLibre(MatrizDobladasTestCase):
    """Pago de cesión parcial: si el DEUDOR está LIBRE ese día y el acreedor tiene UNA sola jornada,
    el deudor cubre EXACTAMENTE esa jornada (queda con 1 jornada), no una doblada ni día libre."""

    def setUp(self):
        super().setUp()
        # El deudor puede quedar sin turno ese día → obtener_sala usa la competencia. Asignar una.
        from empleados.models import CompetenciaEmpleado
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)

    def _crear_pago(self, pago):
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='pago parcial',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=pago,
            tipo_cesion='cesion_parcial_am', jornada_cedida='AM', empleado_receptor=self.receptor,
        )
        return sol, det

    def test_deudor_libre_cubre_solo_la_jornada_del_acreedor(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        pago = FECHA_PAGO
        # Deudor SIN jornada base → LIBRE ese día. Acreedor con UNA jornada (PM).
        self._crear_turno(self.receptor, pago, self.jornada_pm)
        sol, det = self._crear_pago(pago)
        DobladaAplicacionService.aplicar_doblada_pago(sol, det)
        js = {t.jornada.nombre.upper()
              for t in Turno.objects.filter(explorador=self.emisor, fecha=pago).select_related('jornada')}
        self.assertEqual(js, {'PM'}, f'deudor libre debe cubrir solo PM (1 jornada), quedó: {js}')

    def test_deudor_que_trabaja_dobla_al_pagar(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        pago = FECHA_PAGO
        # Deudor con jornada base AM (TRABAJA); acreedor con PM contraria. Al pagar dobla (AM+PM).
        self._asignar_jornada_base(self.emisor, self.jornada_am)
        self._crear_turno(self.receptor, pago, self.jornada_pm)
        sol, det = self._crear_pago(pago)
        DobladaAplicacionService.aplicar_doblada_pago(sol, det)
        js = {t.jornada.nombre.upper()
              for t in Turno.objects.filter(explorador=self.emisor, fecha=pago).select_related('jornada')}
        self.assertEqual(js, {'AM', 'PM'}, f'deudor que trabaja debe doblar (AM+PM), quedó: {js}')

    def _crear_pago_completa(self, pago, jornada_cedida='AM'):
        """Pago de una cesión COMPLETA (rama jornada_cedida conocida, no la parcial)."""
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='pago completa',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=pago,
            tipo_cesion='cesion_completa', jornada_cedida=jornada_cedida, empleado_receptor=self.receptor,
        )
        return sol, det

    def test_cesion_completa_deudor_libre_cubre_solo_la_del_acreedor(self):
        """Regresión (sol 451): cesión completa, jornada_cedida=AM, deudor LIBRE en el pago y el
        acreedor con UNA sola jornada (PM). El deudor debe quedar con PM (la del acreedor), NO doblada."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        pago = FECHA_PAGO
        # Deudor sin jornada base → LIBRE. Acreedor con base/turno PM (única jornada ese día).
        self._asignar_jornada_base(self.receptor, self.jornada_pm)
        self._crear_turno(self.receptor, pago, self.jornada_pm)
        sol, det = self._crear_pago_completa(pago, jornada_cedida='AM')
        DobladaAplicacionService.aplicar_doblada_pago(sol, det)
        js = {t.jornada.nombre.upper()
              for t in Turno.objects.filter(explorador=self.emisor, fecha=pago).select_related('jornada')}
        self.assertEqual(js, {'PM'}, f'deudor libre debe cubrir solo la del acreedor (PM), quedó: {js}')

    def test_cesion_completa_deudor_que_trabaja_dobla(self):
        """Cesión completa con deudor que TRABAJA su base (AM) y acreedor PM: al pagar dobla (AM+PM)."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        pago = FECHA_PAGO
        self._asignar_jornada_base(self.emisor, self.jornada_am)
        self._asignar_jornada_base(self.receptor, self.jornada_pm)
        self._crear_turno(self.receptor, pago, self.jornada_pm)
        sol, det = self._crear_pago_completa(pago, jornada_cedida='AM')
        DobladaAplicacionService.aplicar_doblada_pago(sol, det)
        js = {t.jornada.nombre.upper()
              for t in Turno.objects.filter(explorador=self.emisor, fecha=pago).select_related('jornada')}
        self.assertEqual(js, {'AM', 'PM'}, f'deudor que trabaja debe doblar (AM+PM), quedó: {js}')

    def test_fallback_deudor_libre_por_cesion_no_duplica_jornada(self):
        """Fallback (jornada_cedida=None): deudor LIBRE porque cedió ese día, con base IGUAL a la
        jornada del acreedor → debe quedar con UNA sola jornada, no duplicada. Regresión del caso
        real Diana 15/07 (quedaba con ['AM','AM'])."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        pago = FECHA_PAGO
        # Emisor base AM (igual que la del acreedor abajo), pero LIBRE ese día por cesión previa.
        self._asignar_jornada_base(self.emisor, self.jornada_am)
        u3 = User.objects.create_user('tercero_dup', password='x', email='tdup@t.com')
        tercero = Empleado.objects.create(user=u3, nombre='Ter', apellido='Dup',
                                          cedula='4747474747', email='tdup@t.com', activo=True)
        prev = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=tercero,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=pago,
            comentario='cede el dia del pago',
        )
        DobladaDetalle.objects.create(
            solicitud=prev, minutos_deuda=30, fecha_pago=FECHA_CESION,
            tipo_cesion='cesion_completa', empleado_receptor=tercero,
        )
        # Acreedor trabaja AM ese día (misma jornada que la base del emisor → dispara el duplicado).
        self._crear_turno(self.receptor, pago, self.jornada_am)
        sol, det = self._crear_pago_completa(pago, jornada_cedida=None)  # fallback
        DobladaAplicacionService.aplicar_doblada_pago(sol, det)
        js = [t.jornada.nombre.upper()
              for t in Turno.objects.filter(explorador=self.emisor, fecha=pago).select_related('jornada')]
        self.assertEqual(sorted(js), ['AM'],
                         f'deudor libre no debe duplicar la jornada del acreedor, quedó: {js}')

    def _crear_pago_jcp(self, pago, jcp):
        """Pago donde el acreedor tiene DOBLADA y el deudor elige qué jornada (jcp) cubrir."""
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='pago jcp',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=pago,
            tipo_cesion='cesion_completa', empleado_receptor=self.receptor, jornada_cubre_en_pago=jcp,
        )
        return sol, det

    def test_acreedor_doblada_deudor_libre_cubre_una_sola(self):
        """Acreedor con DOBLADA y deudor LIBRE que elige cubrir una jornada (AM) → el deudor queda
        con esa jornada (1 sola), NO doblado. El acreedor conserva la otra (PM)."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        pago = FECHA_PAGO
        # Deudor SIN base → LIBRE ese día. Acreedor con DOBLADA (AM+PM).
        self._crear_doblada_turnos(self.receptor, pago)
        sol, det = self._crear_pago_jcp(pago, 'AM')
        DobladaAplicacionService.aplicar_doblada_pago(sol, det)
        js_d = sorted(t.jornada.nombre.upper()
                      for t in Turno.objects.filter(explorador=self.emisor, fecha=pago).select_related('jornada'))
        js_a = sorted(t.jornada.nombre.upper()
                      for t in Turno.objects.filter(explorador=self.receptor, fecha=pago).select_related('jornada'))
        self.assertEqual(js_d, ['AM'], f'deudor libre debe cubrir SOLO AM (1 jornada), quedó: {js_d}')
        self.assertEqual(js_a, ['PM'], f'acreedor debe conservar PM, quedó: {js_a}')

    def test_acreedor_doblada_deudor_trabaja_dobla(self):
        """Acreedor con DOBLADA y deudor que TRABAJA su jornada (PM) elige cubrir la contraria (AM)
        → el deudor DOBLA (PM propia + AM cubierta)."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        pago = FECHA_PAGO
        self._asignar_jornada_base(self.emisor, self.jornada_pm)  # deudor trabaja PM ese día
        self._crear_doblada_turnos(self.receptor, pago)           # acreedor doblada
        sol, det = self._crear_pago_jcp(pago, 'AM')               # cubre la AM del acreedor
        DobladaAplicacionService.aplicar_doblada_pago(sol, det)
        js_d = sorted(t.jornada.nombre.upper()
                      for t in Turno.objects.filter(explorador=self.emisor, fecha=pago).select_related('jornada'))
        self.assertEqual(js_d, ['AM', 'PM'], f'deudor que trabaja debe doblar (PM propia + AM), quedó: {js_d}')


class TestCesionReceptorLiberadoPorAprobacionPrevia(MatrizDobladasTestCase):
    """Principio 'manda la última aprobada': si el RECEPTOR fue liberado ese día por una solicitud
    aprobada previa (aquí, es acreedor de un pago de doblada que cae en la fecha de cesión), al
    aplicarle una NUEVA cesión debe cubrir SOLO la jornada cedida, no doblarse sobre una base que
    en realidad no trabaja. Regresión de _explorador_descansa (antes solo veía 'cedió como
    solicitante' y perdía este caso)."""

    def setUp(self):
        super().setUp()
        from empleados.models import CompetenciaEmpleado
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)

    def test_receptor_liberado_por_pago_previo_cubre_solo_la_cedida(self):
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        # PREVIA aprobada: el receptor es ACREEDOR de una doblada cuyo PAGO cae en FECHA_CESION,
        # así que ese día DESCANSA ('paga doblada'). No hace falta aplicarla: la fuente de verdad
        # L2 la detecta por el registro aprobado.
        prev = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_PAGO,
            comentario='previa',
        )
        DobladaDetalle.objects.create(
            solicitud=prev, minutos_deuda=30, fecha_pago=FECHA_CESION,
            tipo_cesion='cesion_completa', jornada_cedida='AM', empleado_receptor=self.receptor,
        )

        # Base PM del receptor: si se doblara mal, quedaría PM+AM.
        self._asignar_jornada_base(self.receptor, self.jornada_pm)

        # NUEVA cesión: se le cede AM en FECHA_CESION (donde ya está libre por la previa).
        nueva = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='nueva',
        )
        det = DobladaDetalle.objects.create(
            solicitud=nueva, minutos_deuda=30, fecha_pago=FECHA_PAGO,
            tipo_cesion='cesion_completa', jornada_cedida='AM', empleado_receptor=self.receptor,
        )
        DobladaAplicacionService.aplicar_doblada_cesion(nueva, det)

        js = {t.jornada.nombre.upper()
              for t in Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).select_related('jornada')}
        self.assertEqual(js, {'AM'}, f'receptor libre por aprobación previa debe cubrir solo AM, quedó: {js}')


class TestAcreedorDescansaEnPagoRechaza(MatrizDobladasTestCase):
    """Regla de negocio: si el COMPAÑERO (acreedor) DESCANSA en la fecha de pago (por cualquier
    motivo real: otra solicitud, temporada, alternancia), NO tiene jornada que el deudor pueda
    cubrir para devolverle el día → la doblada se RECHAZA con mensaje claro (no el confuso 'misma
    jornada'). Aquí el acreedor está libre por una doblada previa aprobada cuyo pago cae en la
    misma fecha, con jornada base que ANTES disparaba el falso 'misma jornada'."""

    def test_acreedor_descansa_por_solicitud_previa_rechaza_con_mensaje_claro(self):
        from solicitudes.models import SolicitudCambio, DobladaDetalle

        # Deudor trabaja su base PM ese día; acreedor base PM (coincidirían por predeterminada)
        # PERO está LIBRE por una doblada previa aprobada cuyo pago cae en FECHA_PAGO.
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

        prev = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='previa que libera al acreedor en el pago',
        )
        DobladaDetalle.objects.create(
            solicitud=prev, minutos_deuda=30, fecha_pago=FECHA_PAGO,
            tipo_cesion='cesion_completa', jornada_cedida='AM', empleado_receptor=self.receptor,
        )

        valido, error = self.strategy.validar_solicitud(self._datos(jornada_cedida='PM'))
        self.assertFalse(valido, f'acreedor que descansa en pago debe rechazarse: {error}')
        # Mensaje claro (no el confuso 'misma jornada')
        self.assertNotIn('dos veces la misma jornada', str(error).lower())

        # Y el aviso UPFRONT del formulario (que usa validar_coincidencia_jornadas_pago) tampoco debe
        # marcar coincidencia: el acreedor descansa, no hay "misma jornada" que colisione.
        from solicitudes.services.solicitud_validator import SolicitudValidator
        r = SolicitudValidator.validar_coincidencia_jornadas_pago(self.emisor, self.receptor, FECHA_PAGO)
        self.assertFalse(r['coinciden'], f'acreedor que descansa no debe marcar coincidencia: {r}')
        self.assertFalse(r['requiere_cambio_turno'], f'no debe exigir cambio de turno: {r}')


class TestDosPagosMismoSabado(MatrizDobladasTestCase):
    """Ceder AMBAS jornadas de una doblada a DOS personas y pagar las dos en el MISMO sábado:
    se permite el 2º pago si usa la MITAD LIBRE del sábado → el deudor termina doblado (AM+PM),
    cada mitad pagando a una persona. Se bloquea si la mitad ya está tomada."""

    def setUp(self):
        super().setUp()
        from empleados.models import CompetenciaEmpleado
        from django.contrib.auth.models import User
        # Segundo receptor (Y)
        user_y = User.objects.create_user('yuli_test', password='x', email='y@t.com')
        self.receptor2 = Empleado.objects.create(
            user=user_y, nombre='Yuli', apellido='Test', cedula='3333333333', email='y@t.com', activo=True
        )
        for e in (self.emisor, self.receptor, self.receptor2):
            CompetenciaEmpleado.objects.get_or_create(empleado=e, sala=self.sala)

    @staticmethod
    def _sabado_futuro():
        d = timezone.localdate() + timedelta(days=10)
        while d.weekday() != 5:
            d += timedelta(days=1)
        return d

    def _sol_pago_sabado(self, receptor, sab, tipo_cesion, jornada_cedida, jps):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada',
            fecha_cambio_turno=FECHA_CESION, comentario='pago mismo sábado',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=sab,
            tipo_cesion=tipo_cesion, jornada_cedida=jornada_cedida,
            empleado_receptor=receptor, jornada_pago_sabado=jps,
        )
        return sol, det

    def test_dos_pagos_mitades_distintas_deudor_queda_doblado(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        sab = self._sabado_futuro()
        # Receptores trabajan el sábado (doblada de fin de semana): conservan la mitad contraria.
        self._crear_doblada_turnos(self.receptor, sab)
        self._crear_doblada_turnos(self.receptor2, sab)
        # Cede AM a X (paga mitad AM) y PM a Y (paga mitad PM), ambas en el mismo sábado.
        sol1, det1 = self._sol_pago_sabado(self.receptor, sab, 'cesion_parcial_am', 'AM', 'AM')
        sol2, det2 = self._sol_pago_sabado(self.receptor2, sab, 'cesion_parcial_pm', 'PM', 'PM')
        # Ambas ya aprobadas → al aplicar, cada pago ve la mitad contraria de la otra y ACUMULA.
        DobladaAplicacionService.aplicar_doblada_pago(sol1, det1)
        DobladaAplicacionService.aplicar_doblada_pago(sol2, det2)
        js_emisor = {t.jornada.nombre.upper()
                     for t in Turno.objects.filter(explorador=self.emisor, fecha=sab).select_related('jornada')}
        self.assertEqual(js_emisor, {'AM', 'PM'},
                         f'el deudor debe quedar doblado (AM+PM) pagando a dos personas, quedó: {js_emisor}')

    def test_dos_pagos_mismo_receptor_mismo_sabado_receptor_descansa(self):
        """Dos dobladas al MISMO compañero pagadas el mismo sábado (una con AM, otra con PM):
        le cubres las DOS mitades → tú quedas DOBLADO (AM+PM) y él DESCANSA el día completo
        (no se le da la contraria, porque esa también se la cubres tú)."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        sab = self._sabado_futuro()
        # El receptor (Marco) trabaja el sábado completo (AM+PM) por alternancia.
        self._crear_doblada_turnos(self.receptor, sab)
        # Dos dobladas jeison → MISMO receptor, una paga AM y la otra PM.
        sol1, det1 = self._sol_pago_sabado(self.receptor, sab, 'cesion_completa', 'AM', 'AM')
        sol2, det2 = self._sol_pago_sabado(self.receptor, sab, 'cesion_completa', 'PM', 'PM')
        DobladaAplicacionService.aplicar_doblada_pago(sol1, det1)
        DobladaAplicacionService.aplicar_doblada_pago(sol2, det2)
        js_emisor = {t.jornada.nombre.upper()
                     for t in Turno.objects.filter(explorador=self.emisor, fecha=sab).select_related('jornada')}
        js_receptor = {t.jornada.nombre.upper()
                       for t in Turno.objects.filter(explorador=self.receptor, fecha=sab).select_related('jornada')}
        self.assertEqual(js_emisor, {'AM', 'PM'}, f'el deudor debe quedar doblado (AM+PM), quedó: {js_emisor}')
        self.assertEqual(js_receptor, set(), f'el receptor debe DESCANSAR (le cubres las dos mitades), quedó: {js_receptor}')

    def test_validacion_no_bloquea_2o_pago_al_mismo_receptor_por_complemento(self):
        """El guard del receptor NO debe rechazar el 2º pago de doblada al MISMO compañero en el mismo
        sábado cuando le pagas la mitad CONTRARIA (lo estás relevando tú, no está "no disponible")."""
        sab = self._sabado_futuro()
        ces = sab - timedelta(days=1)
        while ces.weekday() >= 5:
            ces -= timedelta(days=1)
        self._crear_doblada_turnos(self.receptor, sab)          # receptor trabaja el sábado
        self._crear_turno(self.emisor, ces, self.jornada_am)    # cesión válida (emisor AM, receptor PM)
        self._crear_turno(self.receptor, ces, self.jornada_pm)
        # Existente: jeison → Marco paga ese sábado con AM.
        self._sol_pago_sabado(self.receptor, sab, 'cesion_completa', 'AM', 'AM')
        # Nueva: jeison → Marco, paga el mismo sábado con la mitad libre PM.
        datos = {
            'explorador_solicitante': self.emisor, 'explorador_receptor': self.receptor,
            'fecha_cambio_turno': str(ces), 'fecha_pago': str(sab), 'comentario': 'complemento',
            'tipo_cesion': 'cesion_completa', 'jornada_cedida': None,
            'jornada_pago_sabado': 'PM', 'jornada_cubre_en_pago': None,
        }
        _, msg = self.strategy.validar_solicitud(datos)
        # Puede fallar por otra regla de setup, pero NUNCA por el guard "el compañero no puede cubrir".
        self.assertNotIn('no puede cubrir ese día', str(msg),
                         f'el 2º pago al mismo compañero (mitad contraria) no debe bloquearse por el receptor: {msg}')

    def test_guardian_permite_mitad_libre_y_bloquea_mitad_tomada(self):
        sab = self._sabado_futuro()
        # Cesión: un día de semana del MISMO mes que el sábado (para no chocar con la regla de mes).
        # Preferir el viernes anterior; si cae en otro mes (sábado = 1º del mes), tomar el lunes siguiente.
        ces = sab - timedelta(days=1)
        while ces.weekday() >= 5:
            ces -= timedelta(days=1)
        if ces.month != sab.month:
            ces = sab + timedelta(days=2)
            while ces.weekday() >= 5:
                ces += timedelta(days=1)
        # El compañero del 2º pago trabaja ese sábado (para no chocar con "ambos descansando").
        self._crear_doblada_turnos(self.receptor2, sab)
        self._crear_turno(self.emisor, ces, self.jornada_pm)
        self._crear_turno(self.receptor2, ces, self.jornada_am)
        # Ya existe una doblada aprobada del emisor que paga ese sábado con la mitad AM.
        self._sol_pago_sabado(self.receptor, sab, 'cesion_parcial_am', 'AM', 'AM')

        base = {
            'explorador_solicitante': self.emisor, 'explorador_receptor': self.receptor2,
            'fecha_cambio_turno': str(ces), 'fecha_pago': str(sab),
            'comentario': 'segundo pago', 'tipo_cesion': 'cesion_parcial_pm', 'jornada_cedida': 'PM',
        }
        # Pedir la MISMA mitad (AM) → bloqueado con mensaje del sábado que indica la mitad libre.
        _, err_am = self.strategy.validar_solicitud({**base, 'jornada_pago_sabado': 'AM'})
        self.assertIn('libre la jornada PM', str(err_am),
                      f'pedir la mitad ya tomada (AM) debe bloquear indicando PM libre: {err_am}')
        # Pedir la mitad LIBRE (PM) → el guardián del sábado NO debe bloquear (puede fallar otra
        # validación de estado, pero NO con el mensaje de sábado comprometido).
        _, err_pm = self.strategy.validar_solicitud({**base, 'jornada_pago_sabado': 'PM'})
        self.assertNotIn('ya pagas la jornada', str(err_pm),
                         f'pedir la mitad libre (PM) no debe bloquear por sábado comprometido: {err_pm}')
        self.assertNotIn('ya está comprometido como', str(err_pm), f'{err_pm}')


class TestPagarEnDiaCedidoPermitido(MatrizDobladasTestCase):
    """Regla nueva (lado del pago): PUEDES pagar una doblada en un día en que estás LIBRE, aunque
    estés libre porque CEDISTE ese día en otra solicitud aprobada. Un día libre está disponible
    para cubrir la jornada que debes; la última jornada aprobada del día es la vigente. Antes se
    bloqueaba con "comprometido" (caso jeison/Diana 15/07); ahora se permite y la aplicación deja
    al deudor con UNA sola jornada (la del acreedor, ver TestPagoParcialDeudorLibre)."""

    def test_pagar_en_dia_ya_cedido_se_permite(self):
        from empleados.models import CompetenciaEmpleado
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)
        # Emisor base AM (trabaja en la cesión); receptor base PM (trabaja en el pago → jornada a cubrir).
        self._asignar_jornada_base(self.emisor, self.jornada_am)
        self._asignar_jornada_base(self.receptor, self.jornada_pm)

        d_cede = FECHA_PAGO
        def _wk(base, n):
            d = base + timedelta(days=n)
            while d.weekday() >= 5:
                d += timedelta(days=1)
            return d
        d_prev_pago = _wk(d_cede, 3)
        d_new_cesion = _wk(d_cede, 6)
        if d_new_cesion in (d_prev_pago, d_cede):
            d_new_cesion = _wk(d_new_cesion, 1)

        # PREVIA aprobada: el emisor CEDE completo el día d_cede a un TERCERO → queda LIBRE ese día
        # (sin ensuciar al receptor, que debe trabajar en el pago para poder ser cubierto).
        u3 = User.objects.create_user('tercero_ndc', password='x', email='t3ndc@t.com')
        tercero = Empleado.objects.create(
            user=u3, nombre='Ter', apellido='Cero', cedula='3939393939', email='t3ndc@t.com', activo=True,
        )
        prev = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=tercero,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=d_cede,
            comentario='cede d_cede al tercero',
        )
        DobladaDetalle.objects.create(
            solicitud=prev, minutos_deuda=30, fecha_pago=d_prev_pago,
            tipo_cesion='cesion_completa', empleado_receptor=tercero,
        )

        # NUEVA doblada: cesión en otro día, PAGA en d_cede (el día ya cedido, donde el emisor está
        # libre) → ahora PERMITIDO.
        datos = {
            'explorador_solicitante': self.emisor, 'explorador_receptor': self.receptor,
            'fecha_cambio_turno': str(d_new_cesion), 'fecha_pago': str(d_cede),
            'comentario': 'paga sobre un día cedido', 'tipo_cesion': 'cesion_completa',
            'jornada_cedida': None, 'jornada_pago_sabado': None, 'jornada_cubre_en_pago': None,
        }
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertTrue(ok, f'pagar en un día libre por cesión debe permitirse ahora: {msg}')


class TestCesionReceptorSinBase(MatrizDobladasTestCase):
    """Borde: si el receptor NO tiene jornada base (ni turno) en la fecha de cesión, no hay con qué
    doblarlo → debe cubrir SOLO la jornada cedida, sin intentar crear un Turno con jornada nula
    (antes crasheaba con IntegrityError 'jornada_id cannot be null')."""

    def setUp(self):
        super().setUp()
        from empleados.models import CompetenciaEmpleado
        for e in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=e, sala=self.sala)

    def test_receptor_sin_base_cubre_solo_la_cedida(self):
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        # Emisor con DOBLADA en la cesión; receptor SIN base ni turno ese día.
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        # (self.receptor no tiene AsignarJornadaExplorador ni Turno en FECHA_CESION)

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='receptor sin base',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=FECHA_PAGO,
            tipo_cesion='cesion_parcial_am', jornada_cedida='AM', empleado_receptor=self.receptor,
        )
        # No debe lanzar IntegrityError.
        DobladaAplicacionService.aplicar_doblada_cesion(sol, det)

        js = {t.jornada.nombre.upper()
              for t in Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).select_related('jornada')}
        self.assertEqual(js, {'AM'}, f'receptor sin base debe cubrir solo la cedida (AM), quedó: {js}')


class TestCesionParcialUnaSolaJornada(MatrizDobladasTestCase):
    """Si el emisor tiene UNA sola jornada y la cesión llega (por error del formulario) como
    'cesion_parcial_am/pm', ceder esa jornada debe dejarlo en DÍA LIBRE — NO materializar la
    otra media jornada (la "PM/AM fantasma" que dejaba el día con jornada errónea). Bug sol 489."""

    def setUp(self):
        super().setUp()
        from empleados.models import CompetenciaEmpleado
        for e in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=e, sala=self.sala)

    def _aplicar(self, tipo_cesion, jornada_cedida):
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='una sola jornada',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=FECHA_PAGO,
            tipo_cesion=tipo_cesion, jornada_cedida=jornada_cedida, empleado_receptor=self.receptor,
        )
        DobladaAplicacionService.aplicar_doblada_cesion(sol, det)
        return {t.jornada.nombre.upper()
                for t in Turno.objects.filter(explorador=self.emisor, fecha=FECHA_CESION).select_related('jornada')}

    def test_una_sola_am_parcial_am_queda_libre(self):
        # Emisor con SOLO AM; receptor con PM (contraria).
        self._crear_turno(self.emisor, FECHA_CESION, self.jornada_am)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_pm)
        js = self._aplicar('cesion_parcial_am', 'AM')
        self.assertEqual(js, set(), f'emisor con una sola jornada (AM) debe quedar LIBRE, quedó: {js}')

    def test_doblada_real_parcial_am_conserva_pm(self):
        # Regresión: emisor con DOBLADA real (AM+PM) sí conserva la PM al ceder la AM.
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_pm)
        js = self._aplicar('cesion_parcial_am', 'AM')
        self.assertEqual(js, {'PM'}, f'emisor con doblada real debe conservar PM, quedó: {js}')


# ===========================================================================
# FESTIVOS — la doblada de festivo es TODO-O-NADA y solo la cede quien dobla
# ===========================================================================
class TestFestivoDobladaReglas(MatrizDobladasTestCase):
    """
    En un festivo entre semana trabaja la doblada completa (AM+PM) SOLO el grupo cuya
    jornada base coincide con el grupo que dobla por rotación; el grupo contrario descansa.
    Reglas que se validan aquí (DobladaStrategy):
      1. No se admite cesión PARCIAL en un festivo (debe cederse la doblada completa).
      2. Solo puede ceder en un festivo quien REALMENTE dobla ese día (si descansa, nada que ceder).
    """

    def setUp(self):
        super().setUp()
        from turnos.models import DiaEspecial
        # Dos festivos de semana el MISMO mes (cesión y pago), tabla DiaEspecial vacía por defecto.
        # Rotación: primer festivo cronológico -> dobla grupo PM (índice 0); segundo -> AM (índice 1).
        DiaEspecial.objects.create(fecha=FECHA_CESION, tipo='festivo', activo=True)
        DiaEspecial.objects.create(fecha=FECHA_PAGO, tipo='festivo', activo=True)
        # Los festivos acaban de nacer: hay que publicar su alternancia (idempotente).
        from turnos.tests.alternancia_helpers import publicar_alternancia
        publicar_alternancia(FECHA_CESION.year, FECHA_PAGO.year)
        # FECHA_CESION es el festivo más temprano -> dobla el grupo PM.
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    def test_dobla_en_festivo_helper(self):
        from turnos.services.turno_service import TurnoService
        # Emisor base PM dobla el primer festivo (grupo PM); receptor base AM no.
        self.assertTrue(TurnoService.dobla_en_festivo(self.emisor, FECHA_CESION),
                        'emisor PM debe doblar el festivo donde dobla el grupo PM')
        self.assertFalse(TurnoService.dobla_en_festivo(self.receptor, FECHA_CESION),
                         'receptor AM NO dobla el festivo donde dobla el grupo PM')
        # Día NO festivo -> nunca "dobla_en_festivo".
        self.assertFalse(TurnoService.dobla_en_festivo(self.emisor, FECHA_PAGO - timedelta(days=1)))

    def test_cesion_parcial_en_festivo_rechazada(self):
        # Emisor dobla el festivo (grupo PM) pero pide cesión PARCIAL -> rechazado: todo-o-nada.
        datos = self._datos(tipo_cesion='cesion_parcial_pm', jornada_cedida='PM')
        self.assertRechazado(datos, 'doblada completa', 'cesión parcial en festivo')

    def test_cesion_festivo_con_jornada_cedida_suelta_rechazada(self):
        """`cesion_completa` + `jornada_cedida` era la puerta trasera de la media jornada: al
        APLICAR manda `jornada_cedida`, así que el festivo se cedía a medias pese al 'completa'."""
        datos = self._datos(tipo_cesion='cesion_completa', jornada_cedida='PM')
        self.assertRechazado(datos, 'doblada completa', 'jornada_cedida suelta en festivo')

    def test_cesion_festivo_sin_doblar_rechazada(self):
        # El emisor (AM) NO dobla FECHA_CESION (dobla el grupo PM) -> no tiene doblada que ceder.
        self._asignar_jornada_base(self.emisor, self.jornada_am)
        datos = self._datos(tipo_cesion='cesion_completa')
        self.assertRechazado(datos, 'no doblas el festivo', 'cesión en festivo donde descansa')

    def test_aplicar_cesion_festivo_receptor_queda_con_dia_completo(self):
        """El festivo se cede ENTERO: el receptor debe terminar con AM+PM (la doblada que el
        emisor tenía por rotación), no con una sola jornada."""
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        # En festivo la jornada es virtual (sin filas Turno): la sala sale de la competencia.
        from turnos.models import CompetenciaEmpleado
        for e in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=e, sala=self.sala)
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='cesion festivo completa',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=FECHA_PAGO,
            tipo_cesion='cesion_completa', jornada_cedida=None, empleado_receptor=self.receptor,
        )
        DobladaAplicacionService.aplicar_doblada_cesion(sol, det)
        jornadas_receptor = {
            t.jornada.nombre.upper()
            for t in Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION)
                                  .select_related('jornada')
        }
        self.assertEqual(jornadas_receptor, {'AM', 'PM'},
                         f'el receptor debe cubrir el festivo COMPLETO, quedó: {jornadas_receptor}')
        jornadas_emisor = set(Turno.objects.filter(explorador=self.emisor, fecha=FECHA_CESION)
                              .values_list('jornada__nombre', flat=True))
        self.assertEqual(jornadas_emisor, set(), 'el emisor cede el festivo entero: queda sin turnos')

    def test_guardia_post_aplicacion_rechaza_festivo_a_medias(self):
        """La red de seguridad debe VER el día escrito de menos. Antes daba ✅ con el receptor en
        una sola jornada, porque solo comprobaba que existiera *algún* turno."""
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='festivo a medias',
        )
        det = DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=FECHA_PAGO,
            tipo_cesion='cesion_completa', jornada_cedida=None, empleado_receptor=self.receptor,
        )
        # Estado corrupto a propósito: el receptor cubre SOLO la PM de un festivo (falta la AM).
        self._crear_turno(self.receptor, FECHA_CESION, self.jornada_pm, TipoCambioTurno.DOBLADA)
        res = DobladaAplicacionService.validar_turnos_doblada_cesion(
            sol, det, jornadas_esperadas_receptor={'AM', 'PM'}
        )
        self.assertFalse(res['valido'], 'un festivo cubierto a medias NO puede dar por válido')
        self.assertIn('AM', ' '.join(res['errores']), 'el error debe nombrar la jornada que falta')

    def test_revert_en_festivo_no_recrea_turno_base(self):
        """Revertir una doblada en festivo NO debe dejar un turno base suelto: la jornada
        (doblada o descanso) la computa la rotación en estado_dia, sin filas Turno."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        from turnos.services.turno_service import TurnoService
        # Simula el estado aplicado: doblada (AM+PM con tipo_cambio DOBLADA) en el festivo de cesión.
        Turno.objects.create(explorador=self.emisor, fecha=FECHA_CESION, jornada=self.jornada_am,
                             sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.emisor, fecha=FECHA_CESION, jornada=self.jornada_pm,
                             sala=self.sala, tipo_cambio='DOBLADA')
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_CESION,
            comentario='festivo revert',
        )
        DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=0, fecha_pago=FECHA_PAGO, tipo_cesion='cesion_completa',
            empleado_receptor=self.receptor,
        )
        DobladaAplicacionService.revertir_doblada_aplicada(sol)
        # El caso de uso de cancelación revierte y transiciona a 'cancelada' en la MISMA
        # transacción (ver CancelarSolicitudUseCase._revertir_por_tipo): una solicitud revertida
        # nunca queda 'aprobada'. Si lo estuviera, seguiría atribuyendo descanso al emisor.
        sol.estado = 'cancelada'
        sol.save(update_fields=['estado'])
        self.assertEqual(
            Turno.objects.filter(explorador=self.emisor, fecha=FECHA_CESION).count(), 0,
            'en festivo el revert no debe recrear un turno base suelto',
        )
        # El emisor (PM) dobla el festivo de cesión (grupo PM): estado_dia lo computa sin filas Turno.
        self.assertEqual(TurnoService.estado_dia(self.emisor, FECHA_CESION)['jornada'], 'DOBLADA')


# ===========================================================================
# PAGAR EN UN DÍA LIBRE POR CESIÓN — permitido (un día libre está disponible para pagar)
# ===========================================================================
class TestPagoEnDiaLibrePorCesionPermitido(MatrizDobladasTestCase):
    """El deudor puede PAGAR en un día en que está LIBRE porque cedió ese día en otra doblada
    aprobada. Antes lo bloqueaba el guard `_comp_pago_sol`; ahora un día libre está disponible
    para cubrir la jornada que se debe (la última jornada aprobada del día es la vigente).
    La aplicación deja al deudor con UNA sola jornada (la del acreedor) — cubierto en
    TestPagoParcialDeudorLibre."""

    def setUp(self):
        super().setUp()
        from empleados.models import CompetenciaEmpleado
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)
        # Emisor base AM (trabaja en la cesión); receptor base PM (trabaja en el pago → jornada a cubrir).
        self._asignar_jornada_base(self.emisor, self.jornada_am)
        self._asignar_jornada_base(self.receptor, self.jornada_pm)
        # Tercero para la cesión PREVIA que deja al emisor LIBRE el día del pago.
        u3 = User.objects.create_user('tercero_test', password='x', email='t3@t.com')
        self.tercero = Empleado.objects.create(
            user=u3, nombre='Ter', apellido='Cero', cedula='3333333333', email='t3@t.com', activo=True,
        )

    def _emisor_cede_el_dia_del_pago(self):
        """DOBLADA aprobada: el emisor cede COMPLETA el día del pago (FECHA_PAGO) al tercero,
        por lo que ese día queda LIBRE (cedió su jornada)."""
        otra = FECHA_PAGO + timedelta(days=5)
        while otra.weekday() >= 5:
            otra += timedelta(days=1)
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.tercero,
            tipo_cambio=self.tipo_doblada, estado='aprobada', fecha_cambio_turno=FECHA_PAGO,
            comentario='cesion previa que deja libre el dia del pago',
        )
        DobladaDetalle.objects.create(
            solicitud=sol, minutos_deuda=30, fecha_pago=otra,
            tipo_cesion='cesion_completa', empleado_receptor=self.tercero,
        )
        return sol

    def test_precondicion_emisor_libre_por_cesion_en_el_pago(self):
        from turnos.services.turno_service import TurnoService
        self._emisor_cede_el_dia_del_pago()
        self.assertFalse(
            TurnoService.estado_dia(self.emisor, FECHA_PAGO)['trabaja'],
            'el emisor debe quedar LIBRE el día del pago por la cesión previa',
        )
        self.assertIsNotNone(
            TurnoService.dia_comprometido_por_solicitud(self.emisor, FECHA_PAGO),
            'ese día debe estar marcado como cedido por solicitud',
        )

    def test_pago_en_dia_cedido_es_permitido(self):
        # El emisor está LIBRE el día del pago porque lo cedió → pagar ahí ahora se permite.
        self._emisor_cede_el_dia_del_pago()
        datos = self._datos()  # emisor (AM) cede FECHA_CESION a receptor; paga en FECHA_PAGO (libre)
        self.assertValido(datos, 'pagar en un día libre por cesión debe permitirse')


# ===========================================================================
# Las deudas no se duplican al re-aplicar, ni sobreviven a una cancelación
# ===========================================================================
class TestDeudasIdempotentesYCancelacion(MatrizDobladasTestCase):
    """
    Dos reglas del ledger que no dependen del formulario:

    1. Re-aplicar una solicitud YA aplicada no vuelve a cobrar. Pasa de verdad:
       `reaplicar_doblada` y `corregir_doblada_cesion_total` llaman a
       `generar_deudas_doblada()` sobre solicitudes ya aprobadas y aplicadas.
    2. Una solicitud cancelada no deja deudas vivas, aunque se cancele por fuera del
       use case (admin de Django, comando, script).
    """

    def setUp(self):
        super().setUp()
        # Jornadas base contrarias: el emisor cede su PM, el receptor (AM) se dobla.
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        from empleados.models import CompetenciaEmpleado
        for e in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=e, sala=self.sala)

    def _solicitud_aplicada(self):
        from solicitudes.models import SolicitudCambio, DobladaDetalle
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=FECHA_CESION,
            comentario='Test idempotencia de deudas',
        )
        DobladaDetalle.objects.create(
            solicitud=sol,
            fecha_pago=FECHA_PAGO,
            tipo_cesion='cesion_completa',
            empleado_receptor=self.receptor,
        )
        ok, msg = self.strategy.aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        return SolicitudCambio.objects.select_related('doblada').get(id=sol.id)

    def test_regenerar_deudas_no_duplica(self):
        """Simula lo que hacen `reaplicar_doblada` y `corregir_doblada_cesion_total`."""
        from solicitudes.models import DeudaCorporativa, DeudaExplorador
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        sol = self._solicitud_aplicada()
        corp = DeudaCorporativa.objects.filter(solicitud_origen=sol, estado='activa').count()
        entre = DeudaExplorador.objects.filter(solicitud_origen=sol).exclude(estado='cancelada').count()
        self.assertGreater(corp + entre, 0, 'sanity: la aplicación debe haber generado deudas')

        # Re-aplicar sobre la solicitud YA aplicada (lo que hace el comando de reparación).
        DobladaAplicacionService.generar_deudas_doblada(sol, sol.doblada)

        self.assertEqual(
            DeudaCorporativa.objects.filter(solicitud_origen=sol, estado='activa').count(), corp,
            'regenerar deudas no puede duplicar los 30 min corporativos')
        self.assertEqual(
            DeudaExplorador.objects.filter(solicitud_origen=sol).exclude(estado='cancelada').count(), entre,
            'regenerar deudas no puede duplicar la deuda entre exploradores')

    def test_cancelar_por_fuera_del_use_case_cancela_las_deudas(self):
        """Poner estado='cancelada' a mano (admin/comando) no puede dejar deudas activas."""
        from solicitudes.models import DeudaCorporativa, DeudaExplorador

        sol = self._solicitud_aplicada()
        self.assertTrue(
            DeudaCorporativa.objects.filter(solicitud_origen=sol, estado='activa').exists()
            or DeudaExplorador.objects.filter(solicitud_origen=sol).exclude(estado='cancelada').exists(),
            'sanity: debe haber alguna deuda viva antes de cancelar')

        sol.estado = 'cancelada'
        sol.save()

        self.assertFalse(
            DeudaCorporativa.objects.filter(solicitud_origen=sol, estado='activa').exists(),
            'una solicitud cancelada no puede dejar deuda corporativa activa')
        self.assertFalse(
            DeudaExplorador.objects.filter(solicitud_origen=sol).exclude(estado='cancelada').exists(),
            'una solicitud cancelada no puede dejar deuda entre exploradores viva')


class TestIntercambioDobladasFestivos(MatrizDobladasTestCase):
    """
    Un FESTIVO solo se cambia por otro FESTIVO del mismo mes, también en el INTERCAMBIO de
    dobladas.

    Regresión histórica: el intercambio retornaba antes del bloque de festivos del flujo normal
    y se colaba cambiar un festivo por un día ordinario. En un festivo el grupo que rota trabaja
    AM+PM, o sea que cuenta como DOBLADA y encajaba con cualquier otra doblada (una cobertura,
    un día de temporada…). El festivo se paga distinto, así que ese cambio movía dinero entre
    personas.

    La regla vive ahora en el bloque de REGLAS COMUNES de `validar_solicitud`, que corre ANTES
    del corte del intercambio: rige los dos caminos sin estar duplicada.
    """

    def setUp(self):
        super().setUp()
        # Sin jornada base a propósito: el intercambio exige que cada uno esté LIBRE el día del
        # otro, y una jornada base los pondría a trabajar todos los días de semana. El estado lo
        # dan los turnos explícitos: doblada real en el día propio, nada en el del compañero.
        self._crear_doblada_turnos(self.emisor, FECHA_CESION)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)

    def _datos_intercambio(self, **extra):
        return self._datos(es_intercambio=True, **extra)

    def _marcar_festivo(self, fecha):
        from turnos.models import DiaEspecial
        DiaEspecial.objects.create(fecha=fecha, tipo='festivo', activo=True,
                                   descripcion='Festivo de prueba')

    def test_festivo_por_dia_ordinario_rechazado(self):
        """El día A es festivo y el B no: no se puede."""
        self._marcar_festivo(FECHA_CESION)
        self.assertRechazado(self._datos_intercambio(), 'no es un festivo')

    def test_dia_ordinario_por_festivo_rechazado(self):
        """Simétrico: el festivo está en el día B."""
        self._marcar_festivo(FECHA_PAGO)
        self.assertRechazado(self._datos_intercambio(), 'no es un festivo')

    def test_festivo_por_festivo_de_otro_mes_rechazado(self):
        """Ambos festivos, pero de meses distintos."""
        otro_mes = FECHA_PAGO
        while otro_mes.month == FECHA_CESION.month:
            otro_mes += timedelta(days=1)
        while otro_mes.weekday() >= 5:
            otro_mes += timedelta(days=1)
        self._limpiar_turnos(self.receptor, FECHA_PAGO)
        self._crear_doblada_turnos(self.receptor, otro_mes)
        self._marcar_festivo(FECHA_CESION)
        self._marcar_festivo(otro_mes)
        valido, error = self.strategy.validar_solicitud(
            self._datos_intercambio(fecha_pago=str(otro_mes)))
        self.assertFalse(valido, 'Dos festivos de meses distintos no se pueden intercambiar')
        self.assertIn('mismo mes', error.lower())

    def test_festivo_por_festivo_del_mismo_mes_permitido(self):
        """El caso que sí debe pasar: festivo por festivo, mismo mes."""
        self._marcar_festivo(FECHA_CESION)
        self._marcar_festivo(FECHA_PAGO)
        self.assertValido(self._datos_intercambio())

    def test_sin_festivos_el_intercambio_sigue_funcionando(self):
        """La regla nueva no debe estorbar al intercambio normal entre días ordinarios."""
        self.assertValido(self._datos_intercambio())


class TestFechasMalformadas(MatrizDobladasTestCase):
    """Una fecha basura es ENTRADA INVÁLIDA del cliente, no un fallo del sistema.

    `DateUtils.parse_date` lanza ValueError con texto no parseable. Desde que
    `validar_solicitud` propaga los fallos inesperados (en vez de disfrazarlos de rechazo de
    negocio), sin una guarda explícita ese ValueError subiría hasta el manejador genérico y
    saldría como 500. No se llega por el formulario —usa datepicker— pero sí manipulando la
    petición, así que debe responder como rechazo de validación normal.
    """

    def test_fecha_cesion_basura_es_rechazo_no_excepcion(self):
        self.assertRechazado(
            self._datos(fecha_cambio_turno='no-es-una-fecha'), 'no son válidas')

    def test_fecha_pago_basura_es_rechazo_no_excepcion(self):
        self.assertRechazado(
            self._datos(fecha_pago='2026-13-45'), 'no son válidas')

    # Que la guarda no estorbe al camino normal lo cubren ya los ~130 tests restantes de este
    # módulo: todos pasan fechas bien formadas por aquí antes de llegar a su propia regla.


class TestPagoSabadoReceptorDescansa(MatrizDobladasTestCase):
    """El reparto de sábado NO puede inventarle un turno a quien ese día descansa.

    `_aplicar_pago_sabado` reparte el sábado: el deudor cubre la mitad elegida y el receptor
    conserva la CONTRARIA — y si no la tiene, se la CREA. Ese "si no la tiene, se la crea" da por
    sentado que el receptor trabaja ese día. Cuando en realidad descansa, el efecto era ponerle un
    turno en un día libre en vez de fallar.

    Aguas arriba lo impide `validar_receptor_tiene_jornada_en_fecha_pago`, pero al servicio se
    entra desde varias rutas (creación, re-validación al aprobar, aprobación por enlace de correo),
    así que la protección se fija aquí, en quien hace la escritura.
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        # `obtener_sala_explorador_fecha` cae en la competencia cuando no hay turno ese día: sin
        # ella el reparto de sábado falla por sala antes de llegar a la regla que se prueba aquí.
        from empleados.models import CompetenciaEmpleado
        for emp in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=emp, sala=self.sala)

    @staticmethod
    def _martes_y_sabado_futuros():
        d = timezone.localdate() + timedelta(days=7)
        while d.weekday() != 1:
            d += timedelta(days=1)
        cesion = d
        sabado = cesion + timedelta(days=(5 - cesion.weekday()))
        return cesion, sabado

    def _sabado_donde_receptor_descansa(self):
        """Sábado futuro en el que al receptor NO le toca trabajar por alternancia.

        Se busca preguntándole al sistema (no se calcula a mano): qué grupo trabaja cada finde es
        un DATO publicado, así que fijar un sábado concreto ataría el test a la semilla de un año.
        """
        from turnos.services.turno_service import TurnoService
        d = timezone.localdate() + timedelta(days=7)
        while d.weekday() != 5:
            d += timedelta(days=1)
        for _ in range(8):  # ~2 meses de sábados: la alternancia rota mucho antes
            if TurnoService.obtener_jornada_display(self.receptor, d) is None:
                return d - timedelta(days=4), d   # (martes de esa semana, sábado)
            d += timedelta(days=7)
        self.skipTest('No hay sábado de descanso del receptor en la alternancia publicada')

    def _crear_solicitud_detalle(self, cesion, sabado, solicitante=None, jps='AM'):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=solicitante or self.emisor,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=cesion,
            comentario='Test pago sábado con receptor descansando',
        )
        detalle = DobladaDetalle.objects.create(
            solicitud=sol,
            fecha_pago=sabado,
            tipo_cesion='cesion_parcial_am',
            jornada_cedida='AM',
            empleado_receptor=self.receptor,
            jornada_pago_sabado=jps,
        )
        return sol, detalle

    def _tercer_explorador(self):
        """Un TERCER deudor: el sábado del acreedor se reparte en dos mitades y cada una la puede
        pagar una doblada distinta, de personas distintas."""
        from empleados.models import CompetenciaEmpleado
        user_t = User.objects.create_user('tercero_test', password='x', email='t@t.com')
        tercero = Empleado.objects.create(
            user=user_t, nombre='Tercero', apellido='Test',
            cedula='3333333333', email='t@t.com', activo=True
        )
        self._asignar_jornada_base(tercero, self.jornada_pm)
        CompetenciaEmpleado.objects.get_or_create(empleado=tercero, sala=self.sala)
        return tercero

    def test_receptor_descansando_en_sabado_de_pago_es_rechazado(self):
        from django.core.exceptions import ValidationError
        from solicitudes.services.doblada_pago_service import DobladaPagoService

        cesion, sabado = self._sabado_donde_receptor_descansa()
        # El receptor no trabaja ese sábado: sin turnos propios y sin doblada que se lo justifique.
        self._limpiar_turnos(self.receptor, sabado)

        sol, detalle = self._crear_solicitud_detalle(cesion, sabado)

        with self.assertRaises(ValidationError) as ctx:
            DobladaPagoService.aplicar_doblada_pago(sol, detalle)
        self.assertIn('no trabaja el sábado', str(ctx.exception))

        # Y sobre todo: NO se le inventó ningún turno (la transacción revierte por completo).
        self.assertFalse(
            Turno.objects.filter(explorador=self.receptor, fecha=sabado).exists(),
            "No se le puede crear un turno al receptor en un sábado que descansa.",
        )

    def test_receptor_que_si_trabaja_el_sabado_se_aplica_normal(self):
        """Contraprueba: el guard no debe estorbar al reparto de sábado legítimo."""
        from solicitudes.services.doblada_pago_service import DobladaPagoService

        cesion, sabado = self._martes_y_sabado_futuros()
        # El receptor SÍ trabaja ese sábado (doblada por regla de negocio: AM + PM).
        self._limpiar_turnos(self.receptor, sabado)
        self._crear_doblada_turnos(self.receptor, sabado)

        sol, detalle = self._crear_solicitud_detalle(cesion, sabado)
        DobladaPagoService.aplicar_doblada_pago(sol, detalle)

        # El deudor cubre AM; al receptor le queda la contraria (PM).
        jornadas_emisor = set(
            Turno.objects.filter(explorador=self.emisor, fecha=sabado)
            .values_list('jornada__nombre', flat=True)
        )
        jornadas_receptor = set(
            Turno.objects.filter(explorador=self.receptor, fecha=sabado)
            .values_list('jornada__nombre', flat=True)
        )
        self.assertEqual({'AM'}, jornadas_emisor)
        self.assertEqual({'PM'}, jornadas_receptor)

    def test_dos_deudores_distintos_cubren_cada_mitad_del_sabado(self):
        """Las dos mitades del sábado del acreedor las pueden pagar DOS deudores distintos.

        `DescansoPorSolicitudService` ya modela ese caso (acumula las mitades con
        `{'AM','PM'} <= parciales`, sin mirar quién paga cada una), así que el servicio de pago
        debe coincidir: al aplicar la segunda mitad el acreedor queda SIN turnos, no con la mitad
        del otro deudor recreada.
        """
        from solicitudes.services.doblada_pago_service import DobladaPagoService

        cesion, sabado = self._martes_y_sabado_futuros()
        tercero = self._tercer_explorador()
        # El acreedor trabaja el sábado completo (AM + PM).
        self._limpiar_turnos(self.receptor, sabado)
        self._crear_doblada_turnos(self.receptor, sabado)

        # Deudor 1 le cubre la AM → el acreedor conserva la PM.
        sol_a, det_a = self._crear_solicitud_detalle(cesion, sabado, jps='AM')
        DobladaPagoService.aplicar_doblada_pago(sol_a, det_a)
        self.assertEqual(
            {'PM'},
            set(Turno.objects.filter(explorador=self.receptor, fecha=sabado)
                .values_list('jornada__nombre', flat=True)),
        )

        # Deudor 2 (otra persona) le cubre la PM → ya no le queda ninguna: descansa completo.
        sol_b, det_b = self._crear_solicitud_detalle(
            cesion, sabado, solicitante=tercero, jps='PM')
        DobladaPagoService.aplicar_doblada_pago(sol_b, det_b)

        self.assertFalse(
            Turno.objects.filter(explorador=self.receptor, fecha=sabado).exists(),
            "Con ambas mitades cubiertas el acreedor descansa; no se le puede recrear la mitad "
            "que ya cubre el otro deudor (sería doble cobertura del mismo turno).",
        )

    def test_reaplicar_doblada_con_la_otra_mitad_de_un_tercero_no_falla(self):
        """El guard no puede bloquear una re-aplicación legítima.

        Tras cubrirse ambas mitades el acreedor no tiene turnos. Re-aplicar (reconciliación o
        re-validación al aprobar) volvía a pasar por el guard, que veía "el receptor no trabaja"
        y rechazaba una doblada perfectamente válida.
        """
        from solicitudes.services.doblada_pago_service import DobladaPagoService

        cesion, sabado = self._martes_y_sabado_futuros()
        tercero = self._tercer_explorador()
        self._limpiar_turnos(self.receptor, sabado)
        self._crear_doblada_turnos(self.receptor, sabado)

        sol_a, det_a = self._crear_solicitud_detalle(cesion, sabado, jps='AM')
        DobladaPagoService.aplicar_doblada_pago(sol_a, det_a)
        sol_b, det_b = self._crear_solicitud_detalle(
            cesion, sabado, solicitante=tercero, jps='PM')
        DobladaPagoService.aplicar_doblada_pago(sol_b, det_b)

        # Re-aplicar la segunda: el acreedor sigue sin turnos, pero es legítimo.
        DobladaPagoService.aplicar_doblada_pago(sol_b, det_b)
        self.assertEqual(
            {'PM'},
            set(Turno.objects.filter(explorador=tercero, fecha=sabado)
                .values_list('jornada__nombre', flat=True)),
        )

    def test_media_cubierta_no_compromete_el_sabado_del_acreedor(self):
        """Con UNA sola mitad cubierta el acreedor NO está comprometido: sigue trabajando la otra.

        Esto es lo que hace que la asimetría entre capas sea inofensiva. `_es_complemento_sabado`
        (`doblada_strategy.py`) sí filtra por el mismo deudor, y podría temerse que rechace en
        creación el caso de dos deudores distintos que el servicio de pago sí aplica. No ocurre:
        esa excepción solo se consulta cuando el acreedor YA está comprometido, y para estarlo
        hacen falta las DOS mitades. Con una sola cubierta no hay bloqueo que esquivar, así que el
        segundo deudor pasa sin necesitar la excepción.

        Si algún día la atribución de descanso pasara a marcar el día con media jornada cubierta,
        este test se cae y avisa de que la excepción de la estrategia hay que revisarla.
        """
        from turnos.services.turno_service import TurnoService
        from solicitudes.services.doblada_pago_service import DobladaPagoService

        cesion, sabado = self._martes_y_sabado_futuros()
        self._limpiar_turnos(self.receptor, sabado)
        self._crear_doblada_turnos(self.receptor, sabado)

        # Solo la AM cubierta: al acreedor le queda la PM → NO está comprometido.
        sol_a, det_a = self._crear_solicitud_detalle(cesion, sabado, jps='AM')
        DobladaPagoService.aplicar_doblada_pago(sol_a, det_a)
        self.assertIsNone(
            TurnoService.dia_comprometido_por_solicitud(self.receptor, sabado),
            "Con media jornada cubierta el acreedor aún trabaja: no puede contar como día "
            "comprometido, o bloquearía al segundo deudor.",
        )

        # Cubiertas las dos, ahora sí descansa el día completo y queda comprometido.
        tercero = self._tercer_explorador()
        sol_b, det_b = self._crear_solicitud_detalle(
            cesion, sabado, solicitante=tercero, jps='PM')
        DobladaPagoService.aplicar_doblada_pago(sol_b, det_b)
        self.assertIsNotNone(
            TurnoService.dia_comprometido_por_solicitud(self.receptor, sabado),
            "Con ambas mitades cubiertas el acreedor descansa: el día debe constar comprometido "
            "para que no le paguen una tercera doblada encima.",
        )


class TestLifoProtegeLaReconciliacion(MatrizDobladasTestCase):
    """La guardia LIFO es lo que impide que la reconciliación re-aplique sobre un mundo cambiado.

    `reconciliar_dobladas_aprobadas` re-aplica las dobladas aprobadas SIN re-validarlas, y todas
    sus llamadas viven dentro de un `revertir(...)`, es decir en rutas de cancelación. La pregunta
    de seguridad es si se puede cancelar una solicitud POR DEBAJO de otra más reciente que comparte
    día y persona: si se pudiera, la reconciliación re-aplicaría la de arriba contra un estado que
    ya no es el que validó, y las ramas de pago que crean turnos "si faltan" (`jcp_media`,
    `jornada_cedida`) le fabricarían un turno a quien ese día ya no trabaja.

    No se puede: `bloqueo_lifo` lo impide, y `_pares_afectados` incluye al RECEPTOR en la FECHA DE
    PAGO, que es justo el par que hace falta para detectar el solape. Estos tests fijan esa
    protección — si alguien la debilita, el punto ciego de esas ramas se vuelve alcanzable.
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)

    def _doblada_aprobada(self, solicitante, receptor, fecha_cesion, fecha_pago, resuelta_en):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=solicitante,
            explorador_receptor=receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=fecha_cesion,
            comentario='Test LIFO / reconciliación',
        )
        DobladaDetalle.objects.create(
            solicitud=sol, fecha_pago=fecha_pago, tipo_cesion='cesion_completa',
            empleado_receptor=receptor,
        )
        # `fecha_resolucion` es lo que ordena el LIFO (no la fecha de creación).
        SolicitudCambio.objects.filter(id=sol.id).update(fecha_resolucion=resuelta_en)
        sol.refresh_from_db()
        return sol

    def test_no_se_puede_cancelar_por_debajo_de_una_doblada_que_paga_ese_dia(self):
        """El caso que haría alcanzable el punto ciego: debe quedar BLOQUEADO."""
        from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase

        ahora = timezone.now()
        dia = FECHA_PAGO
        tercero = User.objects.create_user('lifo_test', password='x', email='l@t.com')
        luis = Empleado.objects.create(
            user=tercero, nombre='Luis', apellido='Test',
            cedula='4444444444', email='l@t.com', activo=True)

        # S1 (ANTIGUA): da a `self.receptor` su jornada en `dia`.
        s1 = self._doblada_aprobada(
            self.emisor, self.receptor, FECHA_CESION, dia,
            resuelta_en=ahora - timedelta(minutes=20))
        # S2 (RECIENTE): Luis paga en `dia` cubriendo a `self.receptor`. El receptor en la fecha
        # de PAGO es el par que el LIFO tiene que ver.
        self._doblada_aprobada(
            luis, self.receptor, FECHA_CESION, dia,
            resuelta_en=ahora - timedelta(minutes=5))

        bloqueo = CancelarSolicitudUseCase().bloqueo_lifo(s1)
        self.assertIsNotNone(
            bloqueo,
            "Cancelar S1 por debajo de S2 dejaría que la reconciliación re-aplicara S2 contra un "
            "estado que ya no es el que validó. El LIFO debe impedirlo.",
        )
        self.assertIn('más reciente', bloqueo)

    def test_sin_solape_de_dia_la_cancelacion_no_se_bloquea(self):
        """Contraprueba: el LIFO no debe bloquear lo que no comparte día."""
        from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase

        ahora = timezone.now()
        s1 = self._doblada_aprobada(
            self.emisor, self.receptor, FECHA_CESION, FECHA_PAGO,
            resuelta_en=ahora - timedelta(minutes=20))
        # Más reciente, mismas personas, pero en fechas que no tocan las de S1.
        otra_cesion = FECHA_CESION + timedelta(days=60)
        self._doblada_aprobada(
            self.emisor, self.receptor, otra_cesion, otra_cesion + timedelta(days=2),
            resuelta_en=ahora - timedelta(minutes=5))

        self.assertIsNone(CancelarSolicitudUseCase().bloqueo_lifo(s1))


class TestGuardPagoEntreSemana(MatrizDobladasTestCase):
    """Guard del patrón 39 en las ramas de pago de DÍA DE SEMANA que crean turnos al acreedor.

    Los comandos `reaplicar_doblada` y `corregir_doblada_cesion_total` llaman a
    `aplicar_doblada_pago` SIN validar nada y sin pasar por la guardia LIFO. Si el día cambió desde
    que se aprobó (al acreedor le cancelaron su jornada, o pasó a descansar), estas ramas le
    CREABAN un turno en un día libre y el comando terminaba diciendo que todo fue bien.

    Solo se cubren las ramas donde el guard es demostrablemente seguro: las que le CONSERVAN una
    jornada al acreedor. Las que le dejan sin turnos por diseño (`cesion_parcial`, `fallback`,
    `jornada_cedida` con cesión completa) no admiten esta comprobación sobre el estado posterior
    —bloquearía su propia re-aplicación—; ver las notas del servicio.
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        from empleados.models import CompetenciaEmpleado
        for emp in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=emp, sala=self.sala)

    def _solicitud(self, jcp=None, jornada_cedida=None, tipo_cesion='cesion_completa'):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=FECHA_CESION,
            comentario='Test guard pago entre semana',
        )
        detalle = DobladaDetalle.objects.create(
            solicitud=sol, fecha_pago=FECHA_PAGO, tipo_cesion=tipo_cesion,
            jornada_cedida=jornada_cedida, empleado_receptor=self.receptor,
            jornada_cubre_en_pago=jcp,
        )
        return sol, detalle

    # ---------------- jcp_media ----------------

    def test_jcp_media_con_acreedor_que_descansa_no_le_inventa_turno(self):
        from django.core.exceptions import ValidationError
        from solicitudes.services.doblada_pago_service import DobladaPagoService

        # El acreedor no trabaja la fecha de pago: sin turnos y con su descanso de semana puesto.
        self._limpiar_turnos(self.receptor, FECHA_PAGO)
        AsignarJornadaExplorador.objects.filter(explorador=self.receptor).delete()

        sol, det = self._solicitud(jcp='AM')
        with self.assertRaises(ValidationError) as ctx:
            DobladaPagoService.aplicar_doblada_pago(sol, det)
        self.assertIn('no trabaja', str(ctx.exception))
        self.assertFalse(
            Turno.objects.filter(explorador=self.receptor, fecha=FECHA_PAGO).exists(),
            "No se le puede crear un turno al acreedor en un día que no trabaja.",
        )

    def test_jcp_media_reaplicar_no_se_autoengana(self):
        """La regresión que hace seguro al guard: re-aplicar no debe bloquearse a sí mismo.

        Es exactamente lo que hace `reaplicar_doblada`. Esta rama le conserva al acreedor su
        jornada propia, así que al repetir sigue constando que trabaja.
        """
        from solicitudes.services.doblada_pago_service import DobladaPagoService

        self._limpiar_turnos(self.receptor, FECHA_PAGO)
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)

        sol, det = self._solicitud(jcp='AM')
        DobladaPagoService.aplicar_doblada_pago(sol, det)
        # Segunda pasada: no debe lanzar.
        DobladaPagoService.aplicar_doblada_pago(sol, det)

        self.assertEqual(
            {'PM'},
            set(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_PAGO)
                .values_list('jornada__nombre', flat=True)),
            "El acreedor conserva su jornada propia (PM) tras cubrirle la AM.",
        )

    # ---------------- jornada_cedida (rama parcial) ----------------

    def test_jornada_cedida_parcial_con_acreedor_que_descansa_no_le_inventa_turno(self):
        """La rama guardada de `_aplicar_pago_jornada_cedida` es la de `tipo_cesion` VACÍO.

        El despachador manda `cesion_parcial_am/pm` a `_aplicar_pago_cesion_parcial`, y dentro de
        `jornada_cedida` el caso `cesion_completa` va por la rama que borra los turnos del acreedor.
        Queda esta: `jornada_cedida` puesta y `tipo_cesion` sin valor.
        """
        from django.core.exceptions import ValidationError
        from solicitudes.services.doblada_pago_service import DobladaPagoService

        self._limpiar_turnos(self.receptor, FECHA_PAGO)
        AsignarJornadaExplorador.objects.filter(explorador=self.receptor).delete()

        sol, det = self._solicitud(jornada_cedida='AM', tipo_cesion='')
        with self.assertRaises(ValidationError) as ctx:
            DobladaPagoService.aplicar_doblada_pago(sol, det)
        self.assertIn('no trabaja', str(ctx.exception))
        self.assertFalse(
            Turno.objects.filter(explorador=self.receptor, fecha=FECHA_PAGO).exists())


class TestReconciliacionNoTumbaLaCancelacion(MatrizDobladasTestCase):
    """Una solicitud vigente que ya no encaja NO puede impedir cancelar otra.

    Al cancelar se restaura el snapshot y después `reconciliar_dobladas_aprobadas` re-aplica las
    solicitudes que siguen vigentes en esas fechas —SIN re-validarlas—. Desde que los servicios de
    aplicación tienen guardias de negocio (patrón 39), una de esas re-aplicaciones puede levantar
    `ValidationError` con toda la razón: la doblada vigente ya no encaja con el calendario actual.

    Sin protección, ese error abortaba la transacción entera y el usuario NO podía cancelar, por
    culpa de una solicitud ajena que él no puede arreglar. La reconciliación es reparación
    best-effort: si una pieza no se puede recolocar, se registra y se sigue.
    """

    def setUp(self):
        super().setUp()
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        from empleados.models import CompetenciaEmpleado
        for emp in (self.emisor, self.receptor):
            CompetenciaEmpleado.objects.get_or_create(empleado=emp, sala=self.sala)

    def test_una_doblada_que_ya_no_encaja_no_impide_cancelar_otra(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService
        from turnos.services.turno_service import TurnoService

        # Sábado en el que el ACREEDOR no trabaja por alternancia.
        s = timezone.localdate() + timedelta(days=25)
        while s.weekday() != 5:
            s += timedelta(days=1)
        for _ in range(8):
            if TurnoService.obtener_jornada_display(self.receptor, s) is None:
                break
            s += timedelta(days=7)
        else:
            self.skipTest('Sin sábado de descanso del receptor en la alternancia publicada')

        # Doblada VIGENTE cuyo pago cae ese sábado: ya no se puede re-aplicar (el guard la rechaza).
        vigente = SolicitudCambio.objects.create(
            explorador_solicitante=self.emisor, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada, estado='aprobada',
            fecha_cambio_turno=s - timedelta(days=4), comentario='vigente que ya no encaja',
            fecha_resolucion=timezone.now() - timedelta(minutes=25))
        det = DobladaDetalle.objects.create(
            solicitud=vigente, fecha_pago=s, tipo_cesion='cesion_completa',
            empleado_receptor=self.receptor, jornada_pago_sabado='AM')

        # Premisa del test: re-aplicarla lanza ValidationError.
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            DobladaAplicacionService.aplicar_doblada_pago(vigente, det)

        # La reconciliación sobre ese día NO debe propagar el error: lo registra y sigue.
        DobladaAplicacionService.reconciliar_dobladas_aprobadas(
            {(self.receptor.id, s), (self.emisor.id, s)}, excluir_solicitud_id=999999)

        vigente.refresh_from_db()
        self.assertEqual(
            vigente.estado, 'aprobada',
            "La solicitud sigue vigente: la reconciliación no la cancela, solo omite re-aplicarla.")
