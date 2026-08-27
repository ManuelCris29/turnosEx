"""
Ata `core.constants` a la realidad: a la tabla maestra, a los `choices` de los
modelos y a los valores que de verdad hay en `Turno.tipo_cambio`.

Sin esto las constantes serían solo una copia del texto que quedaría desfasada
en cuanto alguien tocara la maestra o un modelo, que es exactamente el fallo que
el módulo pretende evitar.
"""
from django.test import TestCase

from core.constants import (
    MAPA_SOLICITUD_A_TURNO,
    EstadoSolicitud,
    JornadaDisplay,
    TipoCambioTurno,
    TipoSolicitud,
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


class JornadaDisplayTest(TestCase):
    """
    `JornadaDisplay` es el vocabulario CALCULADO, el único de los cuatro que no
    respalda ninguna columna. Estos tests fijan justo eso, porque es lo que hace
    que confundirlo con los otros no dé error sino una condición muerta.
    """

    def test_am_y_pm_son_los_de_la_tabla_jornada(self):
        """Los dos que SÍ existen como fila deben coincidir con el modelo."""
        from empleados.models import Jornada
        self.assertEqual({JornadaDisplay.AM, JornadaDisplay.PM},
                         set(Jornada.NOMBRES_PROTEGIDOS))

    def test_doblada_no_es_una_jornada_de_la_tabla(self):
        """
        La propiedad que justifica el módulo: 'DOBLADA' se puede COMPARAR contra
        `estado_dia()['jornada']`, pero NO se puede filtrar por
        `jornada__nombre='DOBLADA'` — no hay ninguna fila así. Si algún día
        alguien la crea, este test avisa antes de que el filtro mudo se extienda.
        """
        from empleados.models import Jornada
        nombres_validos = [valor for valor, _ in Jornada.NOMBRE_CHOICES]
        self.assertNotIn(JornadaDisplay.DOBLADA, nombres_validos)
        self.assertFalse(Jornada.objects.filter(nombre=JornadaDisplay.DOBLADA).exists())

    def test_no_se_confunde_con_los_vocabularios_de_tipo_cambio(self):
        """
        Mismo texto, tres significados. Se comprueba la coincidencia LITERAL a
        propósito: si alguien "unifica" los vocabularios importando uno desde
        otro, el módulo deja de proteger de nada y esto lo delata.
        """
        self.assertEqual(JornadaDisplay.DOBLADA, TipoCambioTurno.DOBLADA)
        self.assertEqual(JornadaDisplay.DOBLADA, TipoSolicitud.DOBLADA)
        # …y aun así son vocabularios distintos: ninguno de los otros dos
        # contiene 'AM'/'PM', que es lo que separa a este de aquellos.
        self.assertNotIn(JornadaDisplay.AM, TipoCambioTurno.TODOS)
        self.assertNotIn(JornadaDisplay.PM, TipoCambioTurno.TODOS)

    def test_estado_dia_solo_produce_valores_del_vocabulario(self):
        """
        Ata la constante a la función que la genera. `estado_dia` devuelve
        `None` cuando se descansa, y ese caso NO tiene constante (§docstring).
        """
        import datetime

        from django.contrib.auth.models import User

        from empleados.models import Empleado, Jornada, Sala
        from turnos.models import Turno
        from turnos.services.turno_service import TurnoService

        user = User.objects.create_user(username='jd_test', password='x')  # noqa: S106
        emp = Empleado.objects.create(user=user, nombre='JD', apellido='Test')
        am = Jornada.objects.create(nombre='AM', hora_inicio='08:00', hora_fin='12:00')
        pm = Jornada.objects.create(nombre='PM', hora_inicio='13:00', hora_fin='17:00')
        sala = Sala.objects.create(nombre='S1')
        fecha = datetime.date(2026, 3, 10)

        # Descansa: sin turnos.
        self.assertIsNone(TurnoService.estado_dia(emp, fecha).get('jornada'))

        # Una jornada.
        Turno.objects.create(explorador=emp, fecha=fecha, jornada=am, sala=sala)
        self.assertEqual(TurnoService.estado_dia(emp, fecha).get('jornada'),
                         JornadaDisplay.AM)

        # Las dos: el valor calculado que no existe como fila.
        Turno.objects.create(explorador=emp, fecha=fecha, jornada=pm, sala=sala)
        self.assertEqual(TurnoService.estado_dia(emp, fecha).get('jornada'),
                         JornadaDisplay.DOBLADA)


class CoherenciaConLosModelosTest(TestCase):

    def test_estado_solicitud_coincide_con_los_choices_del_modelo(self):
        from solicitudes.models import SolicitudCambio
        campo = SolicitudCambio._meta.get_field('estado')
        self.assertEqual(list(campo.choices), EstadoSolicitud.CHOICES)

    def test_tipo_cambio_turno_coincide_con_los_choices_del_modelo(self):
        from turnos.models import Turno, TurnoArchivo
        for modelo in (Turno, TurnoArchivo):
            with self.subTest(modelo=modelo.__name__):
                campo = modelo._meta.get_field('tipo_cambio')
                self.assertEqual(list(campo.choices), TipoCambioTurno.CHOICES)

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
