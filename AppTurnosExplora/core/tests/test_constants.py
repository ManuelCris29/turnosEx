"""
Ata `core.constants` a la realidad: a la tabla maestra, a los `choices` de los
modelos y a los valores que de verdad hay en `Turno.tipo_cambio`.

Sin esto las constantes serían solo una copia del texto que quedaría desfasada
en cuanto alguien tocara la maestra o un modelo, que es exactamente el fallo que
el módulo pretende evitar.
"""
from django.test import TestCase

from core.constants import (
    EstadoSolicitud,
    TipoSolicitud,
    TipoCambioTurno,
    MAPA_SOLICITUD_A_TURNO,
)


class MapaVocabulariosTest(TestCase):

    def test_todo_tipo_de_solicitud_tiene_traduccion_a_turno(self):
        """Un tipo nuevo en la maestra sin entrada en el mapa deja el vocabulario cojo."""
        self.assertEqual(set(TipoSolicitud.TODOS), set(MAPA_SOLICITUD_A_TURNO))

    def test_el_mapa_solo_produce_valores_validos_de_turno(self):
        for origen, destino in MAPA_SOLICITUD_A_TURNO.items():
            with self.subTest(tipo=origen):
                self.assertIn(destino, TipoCambioTurno.TODOS)

    def test_las_dos_correspondencias_no_identicas(self):
        """
        El corazón del problema que documenta el módulo: mismo concepto, dos
        textos, según el campo que se consulte. Si esto empieza a fallar es que
        alguien unificó los vocabularios, y entonces sobra medio módulo.
        """
        self.assertEqual(MAPA_SOLICITUD_A_TURNO[TipoSolicitud.CAMBIO_TURNO],
                         TipoCambioTurno.CT)
        self.assertEqual(MAPA_SOLICITUD_A_TURNO[TipoSolicitud.DOBLADA_PERMANENTE],
                         TipoCambioTurno.DOBLADA_PERM)
        self.assertNotEqual(TipoSolicitud.CAMBIO_TURNO, TipoCambioTurno.CT)
        self.assertNotEqual(TipoSolicitud.DOBLADA_PERMANENTE, TipoCambioTurno.DOBLADA_PERM)

    def test_valores_de_turno_sin_tipo_de_solicitud(self):
        """PAGO REPROGRAMADO y PERMISO no salen de una solicitud: no se derivan de la maestra."""
        sin_solicitud = set(TipoCambioTurno.TODOS) - set(MAPA_SOLICITUD_A_TURNO.values())
        self.assertEqual(
            sin_solicitud,
            {TipoCambioTurno.PAGO_REPROGRAMADO, TipoCambioTurno.PERMISO},
        )


class CoherenciaConLosModelosTest(TestCase):

    def test_estado_solicitud_coincide_con_los_choices_del_modelo(self):
        from solicitudes.models import SolicitudCambio
        campo = SolicitudCambio._meta.get_field('estado')
        self.assertEqual(list(campo.choices), EstadoSolicitud.CHOICES)

    def test_el_factory_resuelve_una_estrategia_para_cada_tipo(self):
        """
        `SolicitudFactory` despacha leyendo la maestra en runtime. Un `nombre` que
        el factory no sepa resolver cae en el fallback silencioso a
        `CambioTurnoStrategy`, que aplicaría la lógica equivocada sin avisar.

        Se construyen los tipos en memoria (sin guardar): la tabla maestra no la
        crea ninguna migración de datos, así que en la BD de test está vacía.
        """
        from solicitudes.models import TipoSolicitudCambio
        from solicitudes.services.solicitud_factory import SolicitudFactory
        from solicitudes.services.strategies.cambio_turno_strategy import CambioTurnoStrategy

        for nombre in TipoSolicitud.TODOS:
            with self.subTest(tipo=nombre):
                tipo = TipoSolicitudCambio(nombre=nombre, activo=True)
                estrategia = SolicitudFactory.get_strategy(tipo)
                self.assertIsNotNone(estrategia, f'{nombre} no resuelve ninguna estrategia')
                if nombre != TipoSolicitud.CAMBIO_TURNO:
                    self.assertNotIsInstance(
                        estrategia, CambioTurnoStrategy,
                        f'{nombre} cayó en el fallback a CambioTurnoStrategy',
                    )
