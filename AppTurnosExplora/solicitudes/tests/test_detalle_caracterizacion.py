"""
Red de caracterización de `ObtenerDetalleSolicitudView.construir_datos`.

POR QUÉ EXISTE
--------------
`views/detalle.py` estaba al 12 % de cobertura y contiene una de las cadenas
`if tipo_nombre == ...` que la Fase 2 va a mover a las strategies. Mover ~320
líneas de código apenas probado es justo lo que la auditoría desaconsejaba.

Estos tests no comprueban que el detalle sea "correcto": comprueban que **siga
siendo el mismo** antes y después del refactor. Es una red de caracterización,
no de especificación. Se escribe ANTES de mover nada.

QUÉ VIGILA
----------
La FORMA de la respuesta: el conjunto de rutas de claves que produce cada tipo.
Es lo que rompe un refactor de despacho de verdad — perder una rama, o que un
tipo acabe cayendo en la de otro, se manifiesta como claves que aparecen o
desaparecen. Los valores concretos dependen de datos de prueba y cambiarían el
test sin señalar nada.

Se prueba con solicitudes SIN sus modelos de detalle asociados a propósito: cada
`_detalle_*` envuelve su acceso en try/except, así que ese es el camino que
recorren todas las ramas por igual y el que fija el contrato mínimo de cada tipo.

LÍMITE CONOCIDO
---------------
Sin modelos de detalle, tres tipos producen la MISMA forma (CAMBIO TURNO, DOBLADA
y D FDS), así que la comparación de formas por sí sola no distinguiría un cruce
entre esos tres. Por eso `TestDespacho` comprueba aparte, y de forma directa, QUÉ
rama atiende a cada tipo: es lo que el refactor de la Fase 2 mueve, y por tanto lo
que puede romper.
"""
from django.test import TestCase

from core.tests.factories import crear_empleado, crear_jornada, crear_sala
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.views.detalle import ObtenerDetalleSolicitudView

TIPOS = [
    'CAMBIO TURNO',
    'CT PERMANENTE',
    'DOBLADA',
    'D FDS',
    'DOBLADA PERMANENTE',
    'CAMBIO DESCANSO',
]

# Claves que produce el tronco común, iguales para los seis tipos.
COMUNES = {
    'id', 'fecha_solicitud', 'tipo', 'tipo_codigo', 'estado', 'comentario',
    'fecha_resolucion', 'fecha_cancelacion',
    'solicitante.id', 'solicitante.nombre', 'solicitante.email', 'solicitante.supervisor',
    'receptor.id', 'receptor.nombre', 'receptor.email', 'receptor.supervisor',
    'aprobaciones.receptor.aprobado', 'aprobaciones.receptor.fecha',
    'aprobaciones.supervisor.aprobado', 'aprobaciones.supervisor.fecha',
}


def rutas(dic, prefijo=''):
    """
    Aplana un diccionario a un conjunto de rutas 'a.b.c'.

    Las listas se cortan en su clave: su contenido depende de cuántos registros
    de detalle haya, que no es lo que este test vigila.
    """
    salida = set()
    for clave, valor in dic.items():
        ruta = f'{prefijo}{clave}'
        if isinstance(valor, dict) and valor:
            salida |= rutas(valor, f'{ruta}.')
        else:
            salida.add(ruta)
    return salida


class DetalleCaracterizacionTestCase(TestCase):

    def setUp(self):
        sala = crear_sala()
        jornada = crear_jornada('AM')
        self.supervisor = crear_empleado('Supi', 'Visor', jornada=jornada, sala=sala)
        self.solicitante = crear_empleado('Soli', 'Citante', jornada=jornada, sala=sala,
                                          supervisor=self.supervisor)
        self.receptor = crear_empleado('Recep', 'Tor', jornada=jornada, sala=sala,
                                       supervisor=self.supervisor)

    def _solicitud(self, tipo_nombre):
        tipo, _ = TipoSolicitudCambio.objects.get_or_create(nombre=tipo_nombre)
        return SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=tipo,
            comentario=f'Solicitud de prueba ({tipo_nombre})',
        )

    def _datos(self, tipo_nombre):
        return ObtenerDetalleSolicitudView.construir_datos(self._solicitud(tipo_nombre))


class TestTroncoComun(DetalleCaracterizacionTestCase):
    """Lo que NO depende del tipo. Si el despacho se rompe, esto sigue en pie."""

    def test_los_seis_tipos_producen_las_claves_comunes(self):
        for tipo in TIPOS:
            with self.subTest(tipo=tipo):
                assert COMUNES <= rutas(self._datos(tipo))

    def test_el_tipo_se_refleja_tal_cual(self):
        for tipo in TIPOS:
            with self.subTest(tipo=tipo):
                assert self._datos(tipo)['tipo'] == tipo

    def test_los_supervisores_se_resuelven_a_nombre(self):
        datos = self._datos('CAMBIO TURNO')

        assert datos['solicitante']['supervisor'] == 'Supi Visor'
        assert datos['receptor']['supervisor'] == 'Supi Visor'

    def test_sin_supervisor_queda_a_None(self):
        huerfano = crear_empleado('Sin', 'Jefe')
        solicitud = SolicitudCambio.objects.create(
            explorador_solicitante=huerfano,
            explorador_receptor=self.receptor,
            tipo_cambio=TipoSolicitudCambio.objects.get_or_create(nombre='CAMBIO TURNO')[0],
        )

        datos = ObtenerDetalleSolicitudView.construir_datos(solicitud)

        assert datos['solicitante']['supervisor'] is None

    def test_sin_comentario_pone_el_texto_por_defecto(self):
        solicitud = self._solicitud('DOBLADA')
        solicitud.comentario = ''
        solicitud.save()

        assert ObtenerDetalleSolicitudView.construir_datos(solicitud)['comentario'] == 'Sin comentario'


class TestFormaPorTipo(DetalleCaracterizacionTestCase):
    """
    La fotografía que hace segura la Fase 2: la forma exacta de la respuesta de
    cada tipo, tal como es HOY. Si al mover una rama a su strategy se pierde o se
    cruza con otra, esta comparación lo señala y nombra el tipo afectado.
    """

    # Claves PROPIAS de cada tipo (además de COMUNES), medidas el 2026-08-20 sobre
    # una solicitud sin modelos de detalle. Son literales a propósito: comparar la
    # salida contra sí misma en la misma ejecución no detectaría ninguna deriva.
    PROPIAS_HOY = {
        'CAMBIO TURNO': {'fechas', 'informacion_adicional'},
        'CT PERMANENTE': {'fechas.error', 'informacion_adicional'},
        'DOBLADA': {'fechas', 'informacion_adicional'},
        'D FDS': {'fechas', 'informacion_adicional'},
        'DOBLADA PERMANENTE': {'fechas.error', 'informacion_adicional'},
        'CAMBIO DESCANSO': {'fechas.error', 'informacion_adicional'},
    }

    def test_forma_estable_por_tipo(self):
        for tipo, esperado in self.PROPIAS_HOY.items():
            with self.subTest(tipo=tipo):
                assert rutas(self._datos(tipo)) - COMUNES == esperado

    def test_ningun_tipo_pierde_las_secciones_de_detalle(self):
        """
        `fechas` e `informacion_adicional` los inicializa el tronco común y los
        rellena la rama de cada tipo. Que existan como claves es el contrato que
        consume el frontend.
        """
        for tipo in TIPOS:
            with self.subTest(tipo=tipo):
                datos = self._datos(tipo)
                assert 'fechas' in datos
                assert 'informacion_adicional' in datos

    def test_un_tipo_desconocido_no_revienta(self):
        """
        Hoy la cadena termina en `else` y cualquier tipo no contemplado cae en la
        rama de CAMBIO TURNO. Al pasar a despacho por strategy hay que conservar
        ese comportamiento: un tipo sin strategy registrada debe seguir devolviendo
        el detalle, no un error.
        """
        datos = self._datos('TIPO QUE NO EXISTE')

        assert COMUNES <= rutas(datos)
        assert datos['tipo'] == 'TIPO QUE NO EXISTE'


class TestDespacho(DetalleCaracterizacionTestCase):
    """
    Qué strategy atiende a cada tipo.

    Antes del refactor esto comprobaba qué método `_detalle_*` de la vista se
    ejecutaba; tras la Fase 2 comprueba qué **strategy** recibe la llamada. Es la
    misma pregunta —¿acaba cada tipo en su rama?— sobre el mecanismo nuevo, y sigue
    siendo necesaria: sin modelos de detalle asociados, CAMBIO TURNO, DOBLADA y
    D FDS producen la misma forma, así que un cruce entre esos tres no se vería
    comparando la salida.

    Los 8 tests de forma y comportamiento de este archivo pasaron SIN modificarse
    tras mover los seis cuerpos: esa es la prueba de que el traslado no cambió nada.
    """

    ESPERADO = {
        'CAMBIO TURNO': 'CambioTurnoStrategy',
        'CT PERMANENTE': 'CTPermanenteStrategy',
        'DOBLADA': 'DobladaStrategy',
        'D FDS': 'DFDSStrategy',
        'DOBLADA PERMANENTE': 'DobladaPermanenteStrategy',
        'CAMBIO DESCANSO': 'CambioDescansoStrategy',
        # Sin strategy propia: la factory cae a CambioTurnoStrategy, que es
        # exactamente donde lo mandaba el `else` de la cadena anterior.
        'TIPO QUE NO EXISTE': 'CambioTurnoStrategy',
    }

    @staticmethod
    def _clases():
        from solicitudes.services.strategies.cambio_descanso_strategy import CambioDescansoStrategy
        from solicitudes.services.strategies.cambio_turno_strategy import CambioTurnoStrategy
        from solicitudes.services.strategies.ct_permanente_strategy import CTPermanenteStrategy
        from solicitudes.services.strategies.d_fds_strategy import DFDSStrategy
        from solicitudes.services.strategies.doblada_permanente_strategy import DobladaPermanenteStrategy
        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy

        return [CambioTurnoStrategy, CTPermanenteStrategy, DobladaStrategy,
                DFDSStrategy, DobladaPermanenteStrategy, CambioDescansoStrategy]

    def _strategy_usada(self, tipo_nombre):
        from unittest.mock import patch

        llamadas = []
        parches = []
        for clase in self._clases():
            p = patch.object(clase, 'detalle',
                             lambda self, s, d, _n=clase.__name__: llamadas.append(_n))
            parches.append(p)
            p.start()
        try:
            self._datos(tipo_nombre)
        finally:
            for p in parches:
                p.stop()
        return llamadas

    def test_cada_tipo_va_a_su_strategy(self):
        for tipo, strategy in self.ESPERADO.items():
            with self.subTest(tipo=tipo):
                assert self._strategy_usada(tipo) == [strategy]

    def test_la_vista_ya_no_conoce_los_tipos(self):
        """
        El objetivo de la Fase 2, comprobado: `construir_datos` no puede volver a
        contener una cadena de comparaciones por nombre de tipo. Si alguien la
        reintroduce, este test lo caza.
        """
        import inspect

        from solicitudes.views.detalle import ObtenerDetalleSolicitudView

        fuente = inspect.getsource(ObtenerDetalleSolicitudView.construir_datos)
        codigo = [l for l in fuente.splitlines() if not l.strip().startswith('#')]

        for tipo in TIPOS:
            assert f"== '{tipo}'" not in ' '.join(codigo), tipo

    def test_un_tipo_dado_de_baja_conserva_SU_detalle(self):
        """
        Desactivar un tipo no cambia como se materializo una solicitud que ya
        existe. Con `get_strategy` (que filtra por `activo`) una DOBLADA inactiva
        pasaba a mostrar el detalle de un CAMBIO TURNO; se corrigio el 2026-08-20.
        """
        from solicitudes.models import TipoSolicitudCambio

        tipo = TipoSolicitudCambio.objects.get_or_create(nombre='DOBLADA')[0]
        tipo.activo = False
        tipo.save()

        assert self._strategy_usada('DOBLADA') == ['DobladaStrategy']
