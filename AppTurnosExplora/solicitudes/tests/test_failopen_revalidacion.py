"""
La re-validación al aprobar falla CERRADO (patrón #25).

`revalidar_para_aprobar` es la red que atrapa solicitudes que dejaron de ser
válidas entre el envío y la aprobación: un festivo declarado después, un día que
otra gestión comprometió, una fecha que ya pasó. Tenía tres agujeros por los que
una solicitud se aprobaba SIN pasar por ella, en silencio y sin error:

  1. `_datos_desde_solicitud` traía una implementación por defecto que devolvía
     None, y None significaba "este tipo no soporta re-validación, déjalo pasar".
     Una estrategia nueva que olvidara implementarlo heredaba el atajo. Hoy es
     `@abstractmethod`: olvidarlo hace que Python se niegue a instanciar la clase.

  2. Las tres estrategias con detalle devuelven None cuando falta su fila
     (`DobladaDetalle`, `CambioPermanenteDetalle`…). Eso también aprobaba. Una
     solicitud sin su detalle es un registro corrupto: ni se puede comprobar ni
     se podría aplicar.

  3. `SolicitudFactory.revalidar_para_aprobar` usaba `get_strategy`, que devuelve
     None si el tipo está INACTIVO — así que desactivar un tipo con solicitudes
     pendientes hacía que se aprobaran TODAS sin comprobar ninguna. `activo`
     significa "se pueden CREAR solicitudes nuevas de este tipo"; no dice nada
     sobre las que ya existen.

Los dos últimos se comprobaron EJECUTÁNDOLOS antes de corregirlos: devolvían
`(True, 'Sin re-validación para este tipo')` y `(True, '')`.

Queda a propósito UN fail-open: el `except Exception` de la factory. Bloquear
todas las aprobaciones por un bug en la red de seguridad es peor que aprobar algo
que quizá dejó de ser válido — lo primero para la operación entera, lo segundo se
corrige. Lo cubre `test_un_error_inesperado_si_deja_aprobar`, para que sea una
decisión visible y no un descuido.
"""
from unittest.mock import patch

from django.test import TestCase

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.solicitud_factory import SolicitudFactory
from solicitudes.services.strategies.base_strategy import SolicitudStrategy


class RevalidacionFallaCerradoTestCase(TestCase):
    def setUp(self):
        sala = crear_sala()
        self.a = crear_empleado('Ana', 'Uno', jornada=crear_jornada('AM'), sala=sala)
        self.b = crear_empleado('Ben', 'Dos', jornada=crear_jornada('PM'), sala=sala)
        self.tipo, _ = TipoSolicitudCambio.objects.get_or_create(nombre='DOBLADA')

    def _solicitud(self):
        return SolicitudCambio.objects.create(
            explorador_solicitante=self.a, explorador_receptor=self.b,
            tipo_cambio=self.tipo, estado='pendiente', comentario='x')

    def test_una_solicitud_sin_su_detalle_no_se_aprueba(self):
        """Antes devolvía (True, 'Sin re-validación para este tipo')."""
        sol = self._solicitud()

        ok, msg = SolicitudFactory.revalidar_para_aprobar(sol)

        self.assertFalse(ok, f'se aprobó sin detalle: {msg}')
        self.assertIn('detalles', msg)

    def test_desactivar_el_tipo_no_abre_la_puerta_a_las_pendientes(self):
        """
        El agujero más fácil de provocar sin querer: administración desactiva un
        tipo de solicitud y, sin saberlo, deja pasar sin comprobar todas las que
        ya estaban en la cola. Antes devolvía (True, '').
        """
        sol = self._solicitud()
        self.tipo.activo = False
        self.tipo.save()

        ok, _ = SolicitudFactory.revalidar_para_aprobar(sol)

        self.assertFalse(ok, 'un tipo inactivo dejó aprobar sin re-validar')

    def test_un_tipo_sin_estrategia_registrada_no_se_aprueba(self):
        otro, _ = TipoSolicitudCambio.objects.get_or_create(nombre='TIPO INVENTADO')
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.a, explorador_receptor=self.b,
            tipo_cambio=otro, estado='pendiente', comentario='x')

        ok, msg = SolicitudFactory.revalidar_para_aprobar(sol)

        self.assertFalse(ok, f'se aprobó un tipo sin estrategia: {msg}')

    def test_un_error_inesperado_si_deja_aprobar(self):
        """
        El único fail-open que queda, y es deliberado. Si esto se pone rojo, alguien
        lo cerró: leer primero el razonamiento en `solicitud_factory.py`, porque
        cerrarlo convierte cualquier bug de la re-validación en una parada total de
        las aprobaciones.

        Se provoca el fallo DENTRO de la re-validación de la estrategia, que es lo
        que el `try` cubre. La búsqueda de la estrategia queda fuera a propósito: si
        fallara ahí, la excepción sube y NO se aprueba, que es el lado seguro.
        """
        sol = self._solicitud()
        estrategia = SolicitudFactory.get_strategy_registrada(self.tipo)

        with patch.object(type(estrategia), 'revalidar_para_aprobar',
                          side_effect=RuntimeError('boom')):
            ok, msg = SolicitudFactory.revalidar_para_aprobar(sol)

        self.assertTrue(ok)
        self.assertIn('omitida', msg)


class ContratoDeLaEstrategiaTestCase(TestCase):
    def test_una_estrategia_que_olvide_reconstruir_los_datos_no_se_puede_instanciar(self):
        """
        Aquí está el valor de haberlo hecho abstracto: el olvido se detecta al
        construir la clase, no meses después cuando alguien apruebe una solicitud
        de ese tipo y nadie note que no se comprobó.
        """
        class EstrategiaOlvidadiza(SolicitudStrategy):
            def validar_solicitud(self, datos):
                return True, ''

            def procesar_solicitud(self, datos):
                return True, ''

        with self.assertRaises(TypeError) as ctx:
            EstrategiaOlvidadiza()

        self.assertIn('_datos_desde_solicitud', str(ctx.exception))

    def test_las_seis_estrategias_reales_lo_implementan(self):
        """
        La otra mitad: hacerlo abstracto no puede haber dejado fuera a nadie. Si
        una estrategia real no lo implementara, ni siquiera se podría instanciar y
        el sistema no arrancaría.
        """
        from solicitudes.services.strategies.cambio_descanso_strategy import CambioDescansoStrategy
        from solicitudes.services.strategies.cambio_turno_strategy import CambioTurnoStrategy
        from solicitudes.services.strategies.ct_permanente_strategy import CTPermanenteStrategy
        from solicitudes.services.strategies.d_fds_strategy import DFDSStrategy
        from solicitudes.services.strategies.doblada_permanente_strategy import DobladaPermanenteStrategy
        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy

        for clase in (CambioTurnoStrategy, DobladaStrategy, CTPermanenteStrategy,
                      DFDSStrategy, DobladaPermanenteStrategy, CambioDescansoStrategy):
            with self.subTest(estrategia=clase.__name__):
                instancia = clase()
                self.assertIsNot(
                    type(instancia)._datos_desde_solicitud,
                    SolicitudStrategy._datos_desde_solicitud,
                    'hereda el abstracto en vez de implementarlo',
                )
