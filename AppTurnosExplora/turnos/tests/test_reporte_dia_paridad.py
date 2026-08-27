"""
Paridad entre el reporte operativo del día y la fuente única de verdad de turnos.

`ReporteDiaService.reporte` clasifica a TODA la plantilla en batch, mientras que
`TurnoService.estado_dia` resuelve un empleado y un día. Son dos caminos distintos por
necesidad (con ~400 exploradores no se puede llamar `estado_dia` 400 veces por reporte),
y precisamente por eso derivaron: el reporte llegó a mostrar descansando a gente que
estaba doblando, porque reimplementaba la capa L2 por patrón de día de la semana en vez
de por las fechas reales, y porque le faltaban capas enteras (el lado que dobla en
temporada, la rotación de festivo sin turnos registrados).

Este test es la red que impide que vuelva a pasar: recorre un rango de fechas con datos
de todos los tipos y exige que, para cada empleado y cada día, el reporte diga lo MISMO
que `estado_dia` en las dos cosas que el supervisor lee — si trabaja y qué jornada.
"""
from datetime import date, timedelta

from django.test import TestCase

from empleados.models import Empleado
from turnos.services.reporte_dia_service import ReporteDiaService
from turnos.services.turno_service import TurnoService


class ReporteDiaParidadMixin:
    """Comparador reutilizable: exige paridad reporte ↔ estado_dia en un rango."""

    def assert_paridad(self, desde, hasta, empleados=None):
        empleados = empleados if empleados is not None else list(
            Empleado.objects.filter(activo=True))
        fallos = []
        d = desde
        while d <= hasta:
            rep = ReporteDiaService.reporte(d)
            trabajando = {r['id']: r for r in rep['trabajando']}
            descansando = {r['id']: r for r in rep['descansando']}
            for e in empleados:
                est = TurnoService.estado_dia(e, d)
                real_trabaja = bool(est.get('trabaja'))
                rep_trabaja = e.id in trabajando

                # Todo empleado activo debe aparecer exactamente en una columna.
                if not rep_trabaja and e.id not in descansando:
                    fallos.append(f'{d} {e.nombre}: no aparece en ninguna columna')
                    continue

                if real_trabaja != rep_trabaja:
                    donde = 'trabajando' if rep_trabaja else 'descansando'
                    motivo = (descansando.get(e.id) or {}).get('motivo')
                    fallos.append(
                        f'{d} ({d:%a}) {e.nombre} {e.apellido}: estado_dia dice '
                        f'trabaja={real_trabaja} (jornada={est.get("jornada")}, '
                        f'fuente={est.get("fuente")}) pero el reporte lo pone en '
                        f'{donde} (motivo={motivo!r})')
                elif real_trabaja:
                    jr, jrep = est.get('jornada'), trabajando[e.id].get('jornada_dia')
                    if (jr or '') != (jrep or ''):
                        fallos.append(
                            f'{d} ({d:%a}) {e.nombre} {e.apellido}: jornada real {jr!r} '
                            f'!= jornada del reporte {jrep!r}')
            d += timedelta(days=1)
        if fallos:
            self.fail(
                f'{len(fallos)} discrepancia(s) entre el reporte del día y estado_dia:\n  '
                + '\n  '.join(fallos))


class ReporteDiaParidadDobladaPermanenteTest(ReporteDiaParidadMixin, TestCase):
    """
    El caso que destapó el problema: una DOBLADA PERMANENTE con FECHAS específicas.

    `dias_cesion`/`dias_devolucion` son el patrón de día de la semana, pero cuando el
    detalle trae `fechas_cesion`/`fechas_devolucion` esas fechas MANDAN (así se aplica de
    verdad). El reporte leía solo el patrón y marcaba descansando al receptor TODOS los
    miércoles del rango, cuando solo debía uno — incluidos días en que estaba doblando.
    """

    @classmethod
    def setUpTestData(cls):
        from solicitudes.models import DobladaPermanenteDetalle, SolicitudCambio, TipoSolicitudCambio
        from turnos.models import AsignarJornadaExplorador, Jornada

        cls.am = Jornada.objects.get_or_create(
            nombre='AM', defaults={'hora_inicio': '06:00:00', 'hora_fin': '14:00:00'})[0]
        cls.pm = Jornada.objects.get_or_create(
            nombre='PM', defaults={'hora_inicio': '14:00:00', 'hora_fin': '22:00:00'})[0]

        def _emp(username, nombre, cedula, jornada):
            from django.contrib.auth.models import User
            u = User.objects.create_user(username=username, password='x')
            e = Empleado.objects.create(
                user=u, nombre=nombre, apellido='Test', cedula=cedula, activo=True)
            AsignarJornadaExplorador.objects.create(
                explorador=e, jornada=jornada, fecha_inicio=date(2026, 1, 1))
            return e

        cls.solicitante = _emp('perm.sol', 'Sol', '97001', cls.pm)
        cls.receptor = _emp('perm.rec', 'Rec', '97002', cls.am)

        tipo = TipoSolicitudCambio.objects.get_or_create(nombre='DOBLADA PERMANENTE')[0]
        cls.sol = SolicitudCambio.objects.create(
            explorador_solicitante=cls.solicitante, explorador_receptor=cls.receptor,
            tipo_cambio=tipo, estado='aprobada', fecha_cambio_turno=date(2026, 3, 4))
        DobladaPermanenteDetalle.objects.create(
            solicitud=cls.sol,
            fecha_inicio=date(2026, 3, 2), fecha_fin=date(2026, 3, 27),
            # Patrón: miércoles cede / jueves devuelve...
            dias_cesion='2', dias_devolucion='3',
            # ...pero las fechas REALES son una sola de cada una.
            fechas_cesion='2026-03-11', fechas_devolucion='2026-03-19',
        )

    def test_solo_las_fechas_reales_cuentan_como_descanso(self):
        rep = ReporteDiaService.reporte(date(2026, 3, 11))
        desc = {r['id']: r for r in rep['descansando']}
        self.assertIn(self.solicitante.id, desc,
                      'el 11/03 es su fecha de cesión real: debe descansar')
        self.assertEqual(desc[self.solicitante.id]['motivo'], 'doblada permanente')

        # Los otros miércoles del rango NO son suyos: el patrón no manda sobre las fechas.
        for otro_miercoles in (date(2026, 3, 4), date(2026, 3, 18), date(2026, 3, 25)):
            rep = ReporteDiaService.reporte(otro_miercoles)
            ids_desc = {r['id'] for r in rep['descansando']}
            self.assertNotIn(
                self.solicitante.id, ids_desc,
                f'{otro_miercoles} no es fecha de cesión: no puede figurar descansando')

    def test_paridad_en_todo_el_rango(self):
        self.assert_paridad(date(2026, 3, 1), date(2026, 3, 31),
                            [self.solicitante, self.receptor])


class ReporteDiaCosteConstanteTest(TestCase):
    """
    El reporte debe costar un número de consultas CONSTANTE, no proporcional a la plantilla.

    En producción son ~400 exploradores y este mismo reporte alimenta la exportación a Excel.
    La versión correcta de la clasificación existe también por empleado (`estado_dia`), pero
    llamarla 400 veces son miles de consultas: por eso el reporte usa las variantes batch
    (`en_rango_multiple`, `_mapa_descanso_multi`). Si alguien mete una consulta dentro del
    bucle de empleados, este test lo caza antes de que llegue a producción.
    """

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User

        from turnos.models import AsignarJornadaExplorador, Jornada

        cls.am = Jornada.objects.get_or_create(
            nombre='AM', defaults={'hora_inicio': '06:00:00', 'hora_fin': '14:00:00'})[0]
        cls.pm = Jornada.objects.get_or_create(
            nombre='PM', defaults={'hora_inicio': '14:00:00', 'hora_fin': '22:00:00'})[0]

        cls.empleados = []
        for i in range(30):
            u = User.objects.create_user(username=f'carga{i}', password='x')
            e = Empleado.objects.create(
                user=u, nombre=f'Emp{i}', apellido='Carga',
                cedula=f'9800{i:03d}', activo=True)
            AsignarJornadaExplorador.objects.create(
                explorador=e, jornada=cls.am if i % 2 else cls.pm,
                fecha_inicio=date(2026, 1, 1))
            cls.empleados.append(e)

    def _consultas_con(self, activos):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        Empleado.objects.update(activo=False)
        ids = [e.id for e in self.empleados[:activos]]
        Empleado.objects.filter(id__in=ids).update(activo=True)
        with CaptureQueriesContext(connection) as ctx:
            ReporteDiaService.reporte(date(2026, 3, 10))
        return len(ctx)

    def test_el_numero_de_consultas_no_crece_con_la_plantilla(self):
        pocos = self._consultas_con(3)
        muchos = self._consultas_con(30)
        self.assertEqual(
            pocos, muchos,
            f'El reporte hizo {pocos} consultas con 3 empleados y {muchos} con 30: el coste '
            f'crece con la plantilla. Con ~400 exploradores en producción esto no escala — '
            f'alguna consulta quedó dentro del bucle por empleado.')


class ReporteDiaParidadTurnoRealTest(ReporteDiaParidadMixin, TestCase):
    """
    Guarda L1-sobre-L2: un TURNO REAL gana sobre una solicitud aprobada del mismo día.

    Es la regla "la última aprobada gana por día". El reporte evaluaba los descansos por
    solicitud ANTES que los turnos, así que una persona con doblada real ese día (por
    ejemplo un PAGO REPROGRAMADO) seguía apareciendo como que descansaba.
    """

    @classmethod
    def setUpTestData(cls):
        from solicitudes.models import DobladaPermanenteDetalle, SolicitudCambio, TipoSolicitudCambio
        from turnos.models import AsignarJornadaExplorador, Jornada, Sala, Turno

        cls.sala = Sala.objects.create(nombre='Sala paridad')

        cls.am = Jornada.objects.get_or_create(
            nombre='AM', defaults={'hora_inicio': '06:00:00', 'hora_fin': '14:00:00'})[0]
        cls.pm = Jornada.objects.get_or_create(
            nombre='PM', defaults={'hora_inicio': '14:00:00', 'hora_fin': '22:00:00'})[0]

        def _emp(username, nombre, cedula, jornada):
            from django.contrib.auth.models import User
            u = User.objects.create_user(username=username, password='x')
            e = Empleado.objects.create(
                user=u, nombre=nombre, apellido='Test', cedula=cedula, activo=True)
            AsignarJornadaExplorador.objects.create(
                explorador=e, jornada=jornada, fecha_inicio=date(2026, 1, 1))
            return e

        cls.solicitante = _emp('l1.sol', 'Sol', '97003', cls.pm)
        cls.receptor = _emp('l1.rec', 'Rec', '97004', cls.am)
        cls.fecha = date(2026, 3, 11)   # miércoles: fecha de cesión de la permanente

        tipo = TipoSolicitudCambio.objects.get_or_create(nombre='DOBLADA PERMANENTE')[0]
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=cls.solicitante, explorador_receptor=cls.receptor,
            tipo_cambio=tipo, estado='aprobada', fecha_cambio_turno=cls.fecha)
        DobladaPermanenteDetalle.objects.create(
            solicitud=sol, fecha_inicio=date(2026, 3, 2), fecha_fin=date(2026, 3, 27),
            dias_cesion='2', dias_devolucion='3',
            fechas_cesion='2026-03-11', fechas_devolucion='2026-03-19')

        # Pero ese mismo día el solicitante acaba doblando de verdad (pago reprogramado):
        # la realidad manda sobre el descanso que decía la solicitud.
        for j in (cls.am, cls.pm):
            Turno.objects.create(explorador=cls.solicitante, fecha=cls.fecha,
                                 jornada=j, sala=cls.sala,
                                 tipo_cambio='PAGO REPROGRAMADO')

    def test_turno_real_gana_sobre_el_descanso_por_solicitud(self):
        rep = ReporteDiaService.reporte(self.fecha)
        trab = {r['id']: r for r in rep['trabajando']}
        ids_desc = {r['id'] for r in rep['descansando']}
        self.assertIn(self.solicitante.id, trab,
                      'tiene turnos reales ese día: el reporte debe mostrarlo trabajando')
        self.assertNotIn(self.solicitante.id, ids_desc)
        self.assertEqual(trab[self.solicitante.id]['jornada_dia'], 'DOBLADA')

    def test_paridad_en_todo_el_rango(self):
        self.assert_paridad(date(2026, 3, 1), date(2026, 3, 31),
                            [self.solicitante, self.receptor])
