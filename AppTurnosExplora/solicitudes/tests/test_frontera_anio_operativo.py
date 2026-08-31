"""
Ninguna solicitud puede tocar un año distinto del año en curso.

Cada 1 de enero el sistema arranca en limpio y el año siguiente se planifica aparte en la
apertura de año (festivos, temporadas, descansos de semana, alternancia). Una solicitud con
el pago —o con el final de su rango permanente— en el año siguiente caería sobre un
calendario que todavía no existe, y el turno resultante sería basura.

La comprobación vive en `SolicitudFactory.validar_solicitud`, ANTES de delegar en la
estrategia: así rige para los seis tipos y un tipo nuevo la hereda sin acordarse de ella.
Estas pruebas la fijan ahí, en el punto único, en vez de repetirla tipo por tipo.
"""
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from solicitudes.services.solicitud_factory import SolicitudFactory


class FronteraAnioOperativoTest(TestCase):
    """Se prueba el guardián directamente: no necesita empleados ni BD."""

    def setUp(self):
        self.hoy = timezone.localdate()
        self.este_anio = date(self.hoy.year, 6, 15)
        self.otro_anio = date(self.hoy.year + 1, 6, 15)

    def _error(self, datos):
        return SolicitudFactory._error_de_anio_operativo(datos)

    def test_fechas_del_anio_en_curso_pasan(self):
        self.assertIsNone(self._error({
            'fecha_cambio_turno': self.este_anio.strftime('%Y-%m-%d'),
            'fecha_pago': (self.este_anio + timedelta(days=3)).strftime('%Y-%m-%d'),
        }))

    def test_pago_en_el_anio_siguiente_se_rechaza(self):
        error = self._error({
            'fecha_cambio_turno': self.este_anio.strftime('%Y-%m-%d'),
            'fecha_pago': self.otro_anio.strftime('%Y-%m-%d'),
        })

        self.assertIsNotNone(error, 'un pago en el año siguiente debe rechazarse')
        self.assertIn('apertura de año', error)

    def test_rango_permanente_que_termina_el_anio_siguiente_se_rechaza(self):
        """`MAX_DIAS_RANGO_PERMANENTE` son 366 días: por duración, un rango puede cruzar el año."""
        error = self._error({
            'fecha_inicio': date(self.hoy.year, 12, 1).strftime('%Y-%m-%d'),
            'fecha_fin': date(self.hoy.year + 1, 1, 31).strftime('%Y-%m-%d'),
        })

        self.assertIsNotNone(error)

    def test_revisa_tambien_las_listas_de_fechas(self):
        """Los permanentes mandan `fechas_cesion` / `fechas_devolucion` como listas."""
        error = self._error({
            'fecha_inicio': self.este_anio.strftime('%Y-%m-%d'),
            'fechas_cesion': [self.este_anio.strftime('%Y-%m-%d'),
                              self.otro_anio.strftime('%Y-%m-%d')],
        })

        self.assertIsNotNone(error, 'una fecha suelta dentro de una lista no debe colarse')

    def test_la_fecha_de_creacion_no_cuenta(self):
        """`fecha_creacion_solicitud` es «hoy», no una fecha sobre la que se opere."""
        self.assertIsNone(self._error({
            'fecha_cambio_turno': self.este_anio.strftime('%Y-%m-%d'),
            'fecha_creacion_solicitud': self.hoy,
        }))

    def test_al_revalidar_no_se_aplica(self):
        """
        Regla de CREACIÓN. Una solicitud enviada en diciembre y aprobada en enero no debe
        rechazarse por esto: de las fechas ya pasadas se ocupa su propia validación.
        """
        self.assertIsNone(self._error({
            'fecha_cambio_turno': self.otro_anio.strftime('%Y-%m-%d'),
            'es_revalidacion': True,
        }))

    def test_los_valores_que_no_son_fecha_no_rompen_la_comprobacion(self):
        """El formato lo reportan los validadores del tipo; aquí solo se ignora."""
        self.assertIsNone(self._error({
            'fecha_cambio_turno': self.este_anio.strftime('%Y-%m-%d'),
            'fecha_pago': 'no-es-una-fecha',
        }))
