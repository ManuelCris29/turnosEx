"""
Auditoría 2026-08: los dos *fail-open* que quedaban abiertos, cerrados.

Un *fail-open* es lo contrario del patrón #25 de `PROTECTION_PATTERNS.md`
("Guardias que Fallan CERRADO"): cuando a la guardia le falta el dato con el que
decide, DEJA PASAR en vez de bloquear. Es el peor tipo de fallo, porque la
protección parece estar puesta, no da error, y justo en el caso raro no protege.

Los dos huecos:

1. `base_validator.validar_no_dia_mantenimiento` se tragaba el ValueError de una
   fecha ilegible y la regla "no se cambian turnos en día de mantenimiento" se
   saltaba ENTERA. La protección dependía del ORDEN DE LLAMADA (las strategies
   parsean antes), no de sí misma.
2. `solicitud_orchestrator._procesar_doblada_permanente_multi` dejaba caer las
   fechas ilegibles de la lista del cierre semanal, así que esos días NO se
   comprobaban contra la ventana cerrada.

Cada clase trae también su CONTROL: el patrón #25 avisa de que "fallar cerrado"
no puede degenerar en "bloquear siempre".
"""
import json

from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.test import TestCase
from django.utils import timezone

from solicitudes.services.solicitud_orchestrator import SolicitudOrchestrator
from solicitudes.services.solicitud_validator import SolicitudValidator


class TestMantenimientoFallaCerrado(TestCase):
    """Hueco 1: la validación de día de mantenimiento ante una fecha ilegible."""

    def test_fecha_ilegible_bloquea(self):
        with self.assertRaises(ValidationError) as ctx:
            SolicitudValidator.validar_no_dia_mantenimiento('no-es-una-fecha')

        self.assertIn('no se ha podido interpretar', str(ctx.exception).lower())

    def test_fecha_vacia_bloquea(self):
        """Sin dato tampoco se decide: '' no parsea, así que se bloquea igual."""
        with self.assertRaises(ValidationError):
            SolicitudValidator.validar_no_dia_mantenimiento('')

    def test_control_una_fecha_normal_sigue_pasando(self):
        """
        CONTROL del #25: cerrar el hueco no puede convertirse en "bloquear siempre".
        Un día cualquiera sin mantenimiento debe seguir validando sin excepción.
        """
        hoy = timezone.localdate()

        SolicitudValidator.validar_no_dia_mantenimiento(hoy)
        SolicitudValidator.validar_no_dia_mantenimiento(hoy.strftime('%Y-%m-%d'))


class TestCierreSemanalFallaCerrado(TestCase):
    """
    Hueco 2: el cierre semanal de la DOBLADA PERMANENTE por fechas.

    Se llama al método directamente porque el tramo que interesa es anterior a
    cualquier acceso a base de datos: solo mira el POST.
    """

    @staticmethod
    def _post(cesion_fecha, companero='1'):
        q = QueryDict(mutable=True)
        q.update({'fecha_inicio': '2026-09-01', 'fecha_fin': '2026-09-30'})
        q.appendlist('cesion_fecha', cesion_fecha)
        q.appendlist('cesion_fecha_companero', companero)
        return q

    def _llamar(self, post):
        return SolicitudOrchestrator._procesar_doblada_permanente_multi(
            post, tipo_solicitud=None, solicitante=None, comentario='comentario de prueba'
        )

    def test_fecha_ilegible_rechaza_la_solicitud(self):
        """Antes se caía de la lista en silencio y ese día no se comprobaba."""
        resp = self._llamar(self._post('31/02/2026'))

        self.assertEqual(resp.status_code, 400)
        cuerpo = json.loads(resp.content)
        self.assertIn('no es válida', cuerpo['error'])

    def test_fecha_vacia_rechaza_la_solicitud(self):
        """
        Una cadena vacía tampoco se puede comprobar contra la ventana de cierre.
        El JS solo envía valores de checkboxes marcados, así que aquí no llega
        vacío por diseño: si llega, el POST está malformado.
        """
        resp = self._llamar(self._post(''))

        self.assertEqual(resp.status_code, 400)

    def test_control_el_flujo_por_weekday_no_se_ve_afectado(self):
        """
        CONTROL: sin `cesion_fecha` se usa el flujo antiguo (por día de la semana),
        que expande el rango por su cuenta. No debe rechazarse por esta guardia.
        """
        q = QueryDict(mutable=True)
        q.update({'fecha_inicio': '2026-09-01', 'fecha_fin': '2026-09-30'})

        resp = SolicitudOrchestrator._procesar_doblada_permanente_multi(
            q, tipo_solicitud=None, solicitante=None, comentario='comentario de prueba'
        )

        # Se rechaza más adelante por falta de compañeros/días, pero NUNCA con el
        # mensaje de fecha inválida: la guardia del cierre no se ha disparado.
        if resp.status_code == 400:
            self.assertNotIn('no es válida', json.loads(resp.content).get('error', ''))
