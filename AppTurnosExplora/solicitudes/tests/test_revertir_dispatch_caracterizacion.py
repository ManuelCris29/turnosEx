"""
Red de caracterización de `CancelarSolicitudUseCase._revertir_por_tipo`, previa a
moverla a las strategies (última cadena de la Fase 2).

POR QUÉ ES LA MÁS DELICADA DE LAS SIETE
---------------------------------------
Las anteriores leían, transformaban o re-materializaban. Ésta **deshace** lo que
una solicitud aprobada escribió. Si el despacho se equivoca, no se muestra un dato
falso ni se deja un día sin reconciliar: se revierte con la lógica de OTRO tipo
sobre turnos reales ya aplicados.

Cada rama hace DOS cosas que hay que preservar por separado:

  1. llamar al revertidor de su tipo;
  2. invalidar la caché de turnos de los meses afectados, para las DOS partes.

Lo segundo es fácil de perder en un refactor porque no salta en ningún test
funcional: la caché mal invalidada no rompe nada hoy, solo hace que alguien vea
turnos viejos hasta que expire. Por eso aquí se comprueba explícitamente, con los
pares (empleado, mes, año) exactos.

Los dos tipos PERMANENTES recorren su rango en saltos de 28 días para juntar los
meses. Ese recorrido es la parte con más aritmética y la que más fácil se
estropea al mover, así que tiene sus propios casos: un rango dentro de un mes y
otro que cruza varios.

CÓMO SE COMPRUEBA
-----------------
Con dobles sobre los revertidores y sobre `CacheService`: interesa a QUIÉN se
llama y con qué meses, no lo que cada revertidor haga por dentro. Montar el estado
real de turnos de los seis tipos daría una red más lenta y más frágil, sin cubrir
mejor lo que el refactor puede romper: el despacho.
"""
from datetime import date
from unittest.mock import patch

from django.test import TestCase

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from solicitudes.models import (
    CambioPermanenteDetalle,
    DobladaDetalle,
    DobladaPermanenteDetalle,
    SolicitudCambio,
    TipoSolicitudCambio,
)
from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase

CESION = date(2026, 9, 2)
PAGO = date(2026, 9, 9)

# Revertidores observados, por nombre corto.
REVERTIDORES = {
    'doblada': ('solicitudes.services.doblada_aplicacion_service'
                '.DobladaAplicacionService.revertir_doblada_aplicada'),
    'd_fds': ('solicitudes.services.d_fds_aplicacion_service'
              '.DFDSAplicacionService.revertir'),
    'cambio_turno': ('solicitudes.services.strategies.cambio_turno_strategy'
                     '.CambioTurnoStrategy.revertir'),
    'ct_permanente': ('solicitudes.services.strategies.ct_permanente_strategy'
                      '.CTPermanenteStrategy.revertir'),
    'cambio_descanso': ('solicitudes.services.cambio_descanso_aplicacion_service'
                        '.CambioDescansoAplicacionService.revertir'),
    'doblada_permanente': ('solicitudes.services.doblada_permanente_aplicacion_service'
                           '.DobladaPermanenteAplicacionService.revertir'),
}

CACHE = 'core.services.cache_service.CacheService.invalidar_cache_turnos_empleado'


class RevertirDispatchTestCase(TestCase):

    def setUp(self):
        sala = crear_sala()
        jornada = crear_jornada('AM')
        self.a = crear_empleado('Uno', 'Uno', jornada=jornada, sala=sala)
        self.b = crear_empleado('Dos', 'Dos', jornada=jornada, sala=sala)

    def _solicitud(self, tipo_nombre, fecha=CESION):
        tipo, _ = TipoSolicitudCambio.objects.get_or_create(nombre=tipo_nombre)
        return SolicitudCambio.objects.create(
            explorador_solicitante=self.a,
            explorador_receptor=self.b,
            tipo_cambio=tipo,
            fecha_cambio_turno=fecha,
            estado='aprobada',
        )

    def _con_doblada(self, tipo_nombre, fecha_pago=PAGO):
        solicitud = self._solicitud(tipo_nombre)
        DobladaDetalle.objects.create(solicitud=solicitud, fecha_pago=fecha_pago)
        solicitud.refresh_from_db()
        return solicitud

    def _observar(self, solicitud):
        """
        Ejecuta la reversión con todo doblado y devuelve
        (revertidores_llamados, invalidaciones_de_cache).
        """
        llamados = []
        cache = []
        parches = [patch(ruta, side_effect=lambda *a, _n=nombre, **k: llamados.append(_n))
                   for nombre, ruta in REVERTIDORES.items()]
        parches.append(patch(CACHE, side_effect=lambda eid, m, y: cache.append((eid, m, y))))
        for p in parches:
            p.start()
        try:
            CancelarSolicitudUseCase._revertir_por_tipo(solicitud)
        finally:
            for p in parches:
                p.stop()
        return llamados, sorted(set(cache))

    def _meses(self, *pares_mes_anio):
        """Invalidaciones esperadas: cada mes, para las DOS partes."""
        return sorted({(e.id, m, y)
                       for e in (self.a, self.b)
                       for (m, y) in pares_mes_anio})


class TestQueRevertidorSeUsa(RevertirDispatchTestCase):

    def test_doblada(self):
        revertidores, _ = self._observar(self._con_doblada('DOBLADA'))

        assert revertidores == ['doblada']

    def test_d_fds_usa_el_suyo_y_no_el_de_doblada(self):
        """D FDS comparte `DobladaDetalle`, pero su reversión es otra."""
        revertidores, _ = self._observar(self._con_doblada('D FDS'))

        assert revertidores == ['d_fds']

    def test_cambio_descanso_usa_el_suyo_y_no_el_de_doblada(self):
        revertidores, _ = self._observar(self._con_doblada('CAMBIO DESCANSO'))

        assert revertidores == ['cambio_descanso']

    def test_cambio_turno(self):
        revertidores, _ = self._observar(self._solicitud('CAMBIO TURNO'))

        assert revertidores == ['cambio_turno']

    def test_ct_permanente(self):
        solicitud = self._solicitud('CT PERMANENTE')
        CambioPermanenteDetalle.objects.create(
            solicitud=solicitud, fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30))
        solicitud.refresh_from_db()

        revertidores, _ = self._observar(solicitud)

        assert revertidores == ['ct_permanente']

    def test_doblada_permanente(self):
        solicitud = self._solicitud('DOBLADA PERMANENTE')
        DobladaPermanenteDetalle.objects.create(
            solicitud=solicitud, fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30))
        solicitud.refresh_from_db()

        revertidores, _ = self._observar(solicitud)

        assert revertidores == ['doblada_permanente']


class TestSinDetalleNoSeRevierteNada(RevertirDispatchTestCase):
    """
    Cada rama exige su modelo de detalle además del tipo. Sin él no entra en
    ninguna y NO se revierte nada: es lo correcto —no hay efecto que deshacer— y
    hay que conservarlo, porque revertir a ciegas sí escribiría turnos.
    """

    def test_doblada_sin_detalle(self):
        revertidores, cache = self._observar(self._solicitud('DOBLADA'))

        assert revertidores == []
        assert cache == []

    def test_d_fds_sin_detalle(self):
        assert self._observar(self._solicitud('D FDS')) == ([], [])

    def test_cambio_descanso_sin_detalle(self):
        assert self._observar(self._solicitud('CAMBIO DESCANSO')) == ([], [])

    def test_ct_permanente_sin_detalle(self):
        assert self._observar(self._solicitud('CT PERMANENTE')) == ([], [])

    def test_doblada_permanente_sin_detalle(self):
        assert self._observar(self._solicitud('DOBLADA PERMANENTE')) == ([], [])

    def test_un_tipo_desconocido_no_hace_nada(self):
        """La cadena no tiene `else`: un tipo no contemplado se queda quieto."""
        assert self._observar(self._solicitud('TIPO QUE NO EXISTE')) == ([], [])


class TestInvalidacionDeCache(RevertirDispatchTestCase):
    """
    Los meses cuya caché se invalida, para AMBAS partes.

    Es la mitad silenciosa de cada rama: si se pierde al mover, ningún test
    funcional se entera y el usuario ve turnos viejos hasta que la caché expire.
    """

    def test_doblada_invalida_los_meses_de_sus_dos_dias(self):
        _, cache = self._observar(self._con_doblada('DOBLADA'))

        assert cache == self._meses((9, 2026))

    def test_doblada_con_pago_en_otro_mes_invalida_los_dos(self):
        solicitud = self._con_doblada('DOBLADA', fecha_pago=date(2026, 10, 7))

        _, cache = self._observar(solicitud)

        assert cache == self._meses((9, 2026), (10, 2026))

    def test_cambio_turno_invalida_solo_su_mes(self):
        _, cache = self._observar(self._solicitud('CAMBIO TURNO'))

        assert cache == self._meses((9, 2026))

    def test_cambio_descanso_usa_su_propio_calculo_de_fechas(self):
        """
        No deduce los meses de la solicitud: los saca de `fechas_afectadas`, que
        incluye los días OPUESTOS del finde y puede cruzar de mes.
        """
        solicitud = self._con_doblada('CAMBIO DESCANSO')
        ruta = ('solicitudes.services.cambio_descanso_aplicacion_service'
                '.CambioDescansoAplicacionService.fechas_afectadas')

        with patch(ruta, return_value=[date(2026, 9, 5), date(2026, 11, 1)]):
            _, cache = self._observar(solicitud)

        assert cache == self._meses((9, 2026), (11, 2026))

    def test_ct_permanente_dentro_de_un_mes(self):
        solicitud = self._solicitud('CT PERMANENTE')
        CambioPermanenteDetalle.objects.create(
            solicitud=solicitud, fecha_inicio=date(2026, 9, 1), fecha_fin=date(2026, 9, 30))
        solicitud.refresh_from_db()

        _, cache = self._observar(solicitud)

        assert cache == self._meses((9, 2026))

    def test_ct_permanente_cruzando_varios_meses_y_el_cambio_de_anio(self):
        """
        El rango se recorre en saltos de 28 días. Con saltos así puede saltarse un
        mes corto, por eso el código añade aparte el mes del final. Este caso cruza
        además el cambio de año.
        """
        solicitud = self._solicitud('CT PERMANENTE')
        CambioPermanenteDetalle.objects.create(
            solicitud=solicitud, fecha_inicio=date(2026, 11, 15), fecha_fin=date(2027, 2, 10))
        solicitud.refresh_from_db()

        _, cache = self._observar(solicitud)

        assert cache == self._meses((11, 2026), (12, 2026), (1, 2027), (2, 2027))

    def test_ct_permanente_sin_fecha_fin_usa_la_de_inicio(self):
        """`fecha_fin` es opcional en este detalle."""
        solicitud = self._solicitud('CT PERMANENTE')
        CambioPermanenteDetalle.objects.create(
            solicitud=solicitud, fecha_inicio=date(2026, 9, 10), fecha_fin=None)
        solicitud.refresh_from_db()

        _, cache = self._observar(solicitud)

        assert cache == self._meses((9, 2026))

    def test_doblada_permanente_cruzando_varios_meses(self):
        solicitud = self._solicitud('DOBLADA PERMANENTE')
        DobladaPermanenteDetalle.objects.create(
            solicitud=solicitud, fecha_inicio=date(2026, 11, 15), fecha_fin=date(2027, 2, 10))
        solicitud.refresh_from_db()

        _, cache = self._observar(solicitud)

        assert cache == self._meses((11, 2026), (12, 2026), (1, 2027), (2, 2027))
