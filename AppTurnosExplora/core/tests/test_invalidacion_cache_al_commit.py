"""
La invalidación de la caché de Mis Turnos se APLAZA al commit.

Aplicar una solicitud corre dentro de `transaction.atomic()`. Borrar la clave ahí abre una
carrera: entre el borrado y el commit, otra petición lee Mis Turnos, no ve los cambios aún
sin confirmar y RE-CACHEA el horario viejo. Como ya nadie vuelve a invalidar, ese dato viejo
se sirve durante todo el TTL (una hora). Estas pruebas fijan el aplazamiento para que un
refactor no lo devuelva a un borrado inmediato.
"""
from django.db import transaction
from django.test import TestCase, TransactionTestCase

from core.services.cache_service import CacheService

CLAVE = 'turnos_mes_77_2026_03'


class InvalidacionSeAplazaAlCommitTest(TestCase):

    def setUp(self):
        CacheService.set(CLAVE, {'viejo': True}, ttl=600)

    def test_no_borra_mientras_la_transaccion_sigue_abierta(self):
        CacheService.invalidar_cache_turnos_empleado(77, 3, 2026)

        # Dentro del bloque atómico del propio TestCase: el commit no ha ocurrido.
        self.assertIsNotNone(CacheService.get(CLAVE),
                             'la clave cayó antes del commit: la carrera sigue abierta')

    def test_borra_al_ejecutar_los_callbacks_del_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            CacheService.invalidar_cache_turnos_empleado(77, 3, 2026)

        self.assertIsNone(CacheService.get(CLAVE))

    def test_mes_y_anio_invalidos_no_agendan_nada(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            CacheService.invalidar_cache_turnos_empleado(77, 'marzo', 2026)

        self.assertEqual(callbacks, [])
        self.assertIsNotNone(CacheService.get(CLAVE))


class InvalidacionRealTest(TransactionTestCase):
    """Sin la transacción envolvente del TestCase, para comprobar el comportamiento real."""

    def test_fuera_de_transaccion_el_borrado_es_inmediato(self):
        CacheService.set(CLAVE, {'viejo': True}, ttl=600)

        CacheService.invalidar_cache_turnos_empleado(77, 3, 2026)

        self.assertIsNone(CacheService.get(CLAVE),
                          'sin transacción activa, on_commit debe ejecutar en el acto')

    def test_el_rollback_no_borra_la_clave(self):
        """Si la aplicación falla y revierte, la caché sigue siendo válida: no hay que tocarla."""
        CacheService.set(CLAVE, {'viejo': True}, ttl=600)

        class _Abortar(Exception):
            pass

        try:
            with transaction.atomic():
                CacheService.invalidar_cache_turnos_empleado(77, 3, 2026)
                raise _Abortar
        except _Abortar:
            pass

        self.assertIsNotNone(CacheService.get(CLAVE),
                             'tras un rollback la clave no debe borrarse: el dato no cambió')
