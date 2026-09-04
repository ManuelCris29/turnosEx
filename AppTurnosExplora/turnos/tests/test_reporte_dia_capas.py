"""
Las capas de decisión del reporte del día: festivo, temporada y mantenimiento.

POR QUÉ ESTE ARCHIVO
--------------------
`ReporteDiaService.reporte` son 340 líneas: el cuarto punto caliente que señalaba la
auditoría y, con un 72%, el peor cubierto de los tres que quedaban.

Lo que faltaba no eran rechazos —como en los otros dos— sino **ramas de negocio**: el
bloque entero del festivo entre semana (24 líneas entre las que decide si alguien
trabaja, dobla o descansa ese día) y las capas de temporada y mantenimiento.

Una de ellas lleva este comentario en el código:

    «— L4 (lado que TRABAJA): si el grupo contrario descansa hoy por temporada, este
      grupo cubre el DÍA COMPLETO (AM+PM). Faltaba, y por eso el reporte mostraba media
      jornada a gente que en Mis Turnos figura doblada. —»

Es decir: un fallo real, corregido, y sin una sola prueba que lo sujetara. Es el tercer
caso igual que aparece hoy, y el motivo de este archivo.

QUÉ SE PRUEBA
-------------
El reporte es la vista del supervisor: quién trabaja hoy y por qué. Aquí se comprueba
que cada capa gane a la anterior en el orden correcto, que es lo que hace que el reporte
coincida con lo que el explorador ve en Mis Turnos.
"""
from datetime import date

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from core.constants import TipoCambioTurno
from empleados.models import Empleado, Jornada
from turnos.models import (
    AsignarJornadaExplorador,
    DescansoSemanaManual,
    DiaEspecial,
    Sala,
    Turno,
)
from turnos.services.reporte_dia_service import MOTIVO_SIN_PLANIFICAR, ReporteDiaService


def _buscar(data, emp_id):
    """Devuelve `(grupo, ficha)`. El reporte reparte a la gente en DOS listas —quien
    trabaja y quien descansa—, no en una con un booleano, y las fichas de cada lista no
    tienen las mismas claves: la de quien descansa lleva `motivo`."""
    for grupo in ('trabajando', 'descansando'):
        for e in data[grupo]:
            if e['id'] == emp_id:
                return grupo, e
    return None, None


class CapasDelReporteBase(TestCase):

    #: Un miércoles cualquiera, para que la capa de fin de semana no interfiera.
    FECHA = date(2026, 3, 4)

    def setUp(self):
        cache.clear()
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00',
                                         hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00',
                                         hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Cap', activo=True)
        self.emp_am = self._empleado('cap_am', '8501', self.am)
        self.emp_pm = self._empleado('cap_pm', '8502', self.pm)

    def _empleado(self, username, cedula, jornada):
        u = User.objects.create_user(username=username, password='x')
        e = Empleado.objects.create(user=u, nombre=username, apellido='X',
                                    cedula=cedula, activo=True)
        AsignarJornadaExplorador.objects.create(explorador=e, jornada=jornada,
                                                fecha_inicio=date(2025, 1, 1))
        return e

    def _ficha(self, empleado):
        return _buscar(ReporteDiaService.reporte(self.FECHA), empleado.id)

    def _trabajando(self, empleado):
        grupo, ficha = self._ficha(empleado)
        self.assertEqual(grupo, 'trabajando', f'{empleado.nombre} deberia estar trabajando')
        return ficha

    def _descansando(self, empleado):
        grupo, ficha = self._ficha(empleado)
        self.assertEqual(grupo, 'descansando', f'{empleado.nombre} deberia estar descansando')
        return ficha


class DiaNormalTest(CapasDelReporteBase):
    """CONTROL de todo lo demás: sin festivos ni temporada, cada uno trabaja lo suyo."""

    def test_cada_grupo_trabaja_su_jornada(self):
        ficha_am = self._trabajando(self.emp_am)
        ficha_pm = self._trabajando(self.emp_pm)

        self.assertEqual(ficha_am['jornada_dia'], 'AM')
        self.assertEqual(ficha_pm['jornada_dia'], 'PM')
        self.assertEqual(ficha_am['tipo'], 'oficial')


class TemporadaTest(CapasDelReporteBase):
    """
    Las dos caras de una semana de temporada: un grupo descansa y el otro **cubre el día
    completo**. La segunda es la que faltaba y hacía que el reporte enseñara media
    jornada a quien en Mis Turnos figuraba doblado.
    """

    def _temporada_descansa(self, jornada):
        DiaEspecial.objects.create(fecha=self.FECHA, tipo='temporada',
                                   es_temporada=True, activo=True)
        DescansoSemanaManual.objects.create(fecha=self.FECHA, jornada=jornada,
                                            motivo='temporada', activo=True)

    def test_el_grupo_que_descansa_por_temporada_no_trabaja(self):
        self._temporada_descansa(self.am)

        ficha = self._descansando(self.emp_am)

        self.assertEqual(ficha['motivo'], 'descanso de temporada')

    def test_el_grupo_contrario_cubre_el_dia_completo(self):
        """
        LA REGRESIÓN QUE ESTO PROTEGE. Si el grupo AM descansa por temporada, el PM no
        trabaja «su PM»: cubre AM+PM. Sin esta rama el reporte decía media jornada y no
        coincidía con Mis Turnos.
        """
        self._temporada_descansa(self.am)

        ficha = self._trabajando(self.emp_pm)

        self.assertEqual(ficha['jornada_dia'], 'DOBLADA')
        self.assertEqual(ficha['tipo'], 'oficial')


class MantenimientoTest(CapasDelReporteBase):

    def test_en_mantenimiento_descansan_los_dos_grupos(self):
        """El mantenimiento no es de un grupo: ese día no abre el parque."""
        DiaEspecial.objects.create(fecha=self.FECHA, tipo='mantenimiento', activo=True)

        for emp in (self.emp_am, self.emp_pm):
            with self.subTest(empleado=emp.nombre):
                ficha = self._descansando(emp)

                self.assertEqual(ficha['motivo'], 'lunes de mantenimiento')


class FestivoEntreSemanaTest(CapasDelReporteBase):
    """
    El bloque más grande sin cubrir: 24 líneas que deciden qué pasa en un festivo entre
    semana, donde la regla del festivo manda sobre el horario base y solo un cambio
    EXPLÍCITO se respeta por encima.
    """

    def setUp(self):
        super().setUp()
        DiaEspecial.objects.create(fecha=self.FECHA, tipo='festivo', activo=True)

    def test_sin_alternancia_publicada_sale_como_sin_planificar(self):
        """
        Nadie puede saber qué grupo dobla ese festivo si no está publicado. El reporte no
        se lo inventa: lo dice.
        """
        ficha = self._descansando(self.emp_am)

        # Se compara contra la CONSTANTE, no contra el texto: si alguien reescribe el
        # aviso, el test debe seguir valiendo; lo que no puede cambiar es que ese dia
        # salga marcado como no planificado.
        self.assertEqual(ficha['motivo'], MOTIVO_SIN_PLANIFICAR)

    def test_con_alternancia_publicada_un_grupo_dobla_y_el_otro_descansa(self):
        from turnos.tests.alternancia_helpers import publicar_alternancia
        publicar_alternancia(self.FECHA.year)

        from turnos.services.asignacion_especial_service import AsignacionEspecialService
        grupo = AsignacionEspecialService.grupo_trabaja(self.FECHA)
        self.assertIn(grupo, ('AM', 'PM'), 'la alternancia debe quedar publicada')

        que_dobla = self.emp_am if grupo == 'AM' else self.emp_pm
        que_descansa = self.emp_pm if grupo == 'AM' else self.emp_am

        ficha_dobla = self._trabajando(que_dobla)
        self.assertEqual(ficha_dobla['jornada_dia'], 'DOBLADA')

        ficha_descansa = self._descansando(que_descansa)
        self.assertIn('grupo contrario', ficha_descansa['motivo'])

    def test_un_cambio_explicito_manda_sobre_la_regla_del_festivo(self):
        """
        Es la excepción que documenta el propio código: un turno con `tipo_cambio` es una
        decisión tomada por una persona, y gana a la rotación del festivo.
        """
        Turno.objects.create(explorador=self.emp_am, fecha=self.FECHA,
                             jornada=self.am, sala=self.sala,
                             tipo_cambio=TipoCambioTurno.CT)

        ficha = self._trabajando(self.emp_am)

        self.assertEqual(ficha['jornada_dia'], 'AM')
        self.assertEqual(ficha['tipo'], 'cambio')
