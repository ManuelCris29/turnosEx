"""
Tests positivos de re-validación al aprobar para DOBLADA y DOBLADA PERMANENTE.

Garantizan que una solicitud VÁLIDA re-valide True al aprobar (no se bloqueen aprobaciones
válidas por la reconstrucción de datos ni por auto-referencia en chequeos de creación).
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from turnos.models import AsignarJornadaExplorador, Sala
from solicitudes.tests.test_matriz_dobladas import MatrizDobladasTestCase, FECHA_CESION, FECHA_PAGO
from solicitudes.services.strategies.doblada_permanente_strategy import DobladaPermanenteStrategy


class DobladaPagoJornadaRealTest(MatrizDobladasTestCase):
    """Regresión (caso Vanesa/mildrey): la validación de doblada usa la jornada REAL (estado_dia),
    no la base. Si en la fecha de pago el deudor DESCANSA por temporada (aunque su base sea AM), sí
    puede cubrir una jornada de la doblada del compañero; pero si TRABAJA esa jornada de verdad, no."""

    def test_pago_en_temporada_deudor_descansa_cubre_valido(self):
        from turnos.models import DescansoSemanaManual
        from django.core.cache import cache
        # Solicitante AM, receptor PM (contrarios).
        self._asignar_jornada_base(self.emisor, self.jornada_am)
        self._asignar_jornada_base(self.receptor, self.jornada_pm)
        # Fecha de pago en temporada: descansa AM → emisor(AM) descansa, receptor(PM) queda DOBLADA.
        DescansoSemanaManual.objects.create(fecha=FECHA_PAGO, jornada=self.jornada_am, activo=True)
        cache.clear()
        datos = self._datos(tipo_cambio=self.tipo_doblada, jornada_cubre_en_pago='AM')
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertTrue(ok, f'el deudor descansa por temporada → cubrir la AM de la doblada es válido: {msg}')

    def test_control_deudor_trabaja_am_no_puede_cubrir_am(self):
        from django.core.cache import cache
        self._asignar_jornada_base(self.emisor, self.jornada_am)
        self._asignar_jornada_base(self.receptor, self.jornada_pm)
        # Fecha de pago normal: emisor(AM) trabaja AM real; receptor con doblada REAL ese día.
        self._crear_doblada_turnos(self.receptor, FECHA_PAGO)
        cache.clear()
        datos = self._datos(tipo_cambio=self.tipo_doblada, jornada_cubre_en_pago='AM')
        ok, msg = self.strategy.validar_solicitud(datos)
        self.assertFalse(ok, 'el deudor trabaja AM de verdad → cubrir AM debe bloquearse (haría AM dos veces)')


class DobladaRevalidacionTest(MatrizDobladasTestCase):
    def test_revalidacion_para_aprobar_ok(self):
        # CASO 1 válido: emisor PM, receptor AM (una jornada cada uno).
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        sol, msg = self.strategy.crear_solicitud(self._datos(tipo_cambio=self.tipo_doblada))
        self.assertIsNotNone(sol, msg)
        sol = SolicitudCambio.objects.select_related('doblada').get(id=sol.id)
        ok, m = self.strategy.revalidar_para_aprobar(sol)
        self.assertTrue(ok, m)


class DobladaConcurrenciaReceptorTest(MatrizDobladasTestCase):
    def test_caso_b_receptor_ya_comprometido(self):
        from empleados.models import CompetenciaEmpleado
        self._asignar_jornada_base(self.emisor, self.jornada_pm)
        self._asignar_jornada_base(self.receptor, self.jornada_am)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)

        # A: emisor(PM) -> receptor(AM) doblada, aprobada + aplicada.
        solA, msg = self.strategy.crear_solicitud(self._datos(tipo_cambio=self.tipo_doblada))
        self.assertIsNotNone(solA, msg)
        solA.estado = 'aprobada'
        solA.fecha_resolucion = timezone.now()
        solA.save()
        solA = SolicitudCambio.objects.select_related('doblada').get(id=solA.id)
        ok, m = self.strategy.aplicar_cambios(solA)
        self.assertTrue(ok, m)

        # B: segundo emisor (PM) hacia el MISMO receptor, misma cesión -> debe bloquearse.
        u = User.objects.create_user('emisor2.dob', password='x', email='e2@t.com')
        em2 = Empleado.objects.create(user=u, nombre='Em2', apellido='Test', cedula='3333', email='e2@t.com', activo=True)
        self._asignar_jornada_base(em2, self.jornada_pm)
        CompetenciaEmpleado.objects.get_or_create(empleado=em2, sala=self.sala)
        ok2, m2 = self.strategy.validar_solicitud(self._datos(explorador_solicitante=em2, tipo_cambio=self.tipo_doblada))
        self.assertFalse(ok2, f"B debió bloquearse (receptor ya comprometido por A). msg={m2}")


class DobladaPermRevalidacionTest(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala DP', activo=True)

        u1 = User.objects.create_user(username='sol.dp', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='A', cedula='1', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        u2 = User.objects.create_user(username='rec.dp', password='x')
        self.rec = Empleado.objects.create(user=u2, nombre='Rec', apellido='B', cedula='2', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.rec, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=self.sol, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.rec, sala=self.sala)

        # Rango futuro (mes siguiente), días: cesión martes (1), devolución jueves (3).
        hoy = timezone.now().date()
        anio, mes = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        self.fi = date(anio, mes, 1)
        self.ff = self.fi + timedelta(days=27)

    def test_validar_solicitud_acepta_fechas_como_lista(self):
        """Regresión: `django.QueryDict.getlist` entrega 'fechas_cesion'/'fechas_devolucion' como
        LISTA (no csv). `validar_solicitud` no debe reventar con
        AttributeError: 'list' object has no attribute 'split'."""
        strat = DobladaPermanenteStrategy()
        d = self.fi
        while d.weekday() != 1:
            d += timedelta(days=1)
        martes = d
        d = self.fi
        while d.weekday() != 3:
            d += timedelta(days=1)
        jueves = d
        datos = {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba lista',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'), 'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': ['1'], 'dias_devolucion': ['3'],
            'fechas_cesion': [martes.strftime('%Y-%m-%d')],
            'fechas_devolucion': [jueves.strftime('%Y-%m-%d')],
        }
        ok, msg = strat.validar_solicitud(datos)
        self.assertTrue(ok, msg)

    def test_revalidacion_para_aprobar_ok(self):
        strat = DobladaPermanenteStrategy()
        datos = {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'),
            'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '1', 'dias_devolucion': '3',
        }
        # Sanity: debe ser válido al crear.
        ok, msg = strat.validar_solicitud(datos)
        self.assertTrue(ok, msg)
        sol, msg = strat.crear_solicitud(datos)
        self.assertIsNotNone(sol, msg)
        sol = SolicitudCambio.objects.select_related('doblada_permanente').get(id=sol.id)
        ok, m = strat.revalidar_para_aprobar(sol)
        self.assertTrue(ok, m)

    def test_revalidacion_usa_fechas_especificas_y_nombra_la_invalida(self):
        """Regresión (caso marco→vanesa): al re-validar para aprobar, si la solicitud trae FECHAS
        específicas, se re-validan ESAS fechas (igual que la aplicación), no el barrido por día de la
        semana. Si una fecha elegida deja de ser válida, se rechaza NOMBRÁNDOLA (no un mensaje genérico
        sobre todo el rango)."""
        from datetime import timedelta
        from turnos.models import Turno
        # Dos martes (cesión) y dos jueves (devolución) del rango.
        martes, jueves = [], []
        d = self.fi
        while d <= self.ff:
            if d.weekday() == 1 and len(martes) < 2:
                martes.append(d)
            if d.weekday() == 3 and len(jueves) < 2:
                jueves.append(d)
            d += timedelta(days=1)
        strat = DobladaPermanenteStrategy()
        sol, msg = strat.crear_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba fechas',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'), 'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '1', 'dias_devolucion': '3',
            'fechas_cesion': ','.join(x.strftime('%Y-%m-%d') for x in martes),
            'fechas_devolucion': ','.join(x.strftime('%Y-%m-%d') for x in jueves),
        })
        self.assertIsNotNone(sol, msg)
        sol = SolicitudCambio.objects.select_related('doblada_permanente').get(id=sol.id)
        # Con fechas contrarias (sol PM, rec AM) re-valida OK.
        ok, m = strat.revalidar_para_aprobar(sol)
        self.assertTrue(ok, m)
        # Invalidar UNA fecha de devolución elegida: el receptor ya tiene doblada ese jueves.
        invalido = jueves[0]
        Turno.objects.create(explorador=self.rec, fecha=invalido, jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.rec, fecha=invalido, jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')
        from django.core.cache import cache
        cache.clear()
        sol = SolicitudCambio.objects.select_related('doblada_permanente').get(id=sol.id)
        ok, m = strat.revalidar_para_aprobar(sol)
        self.assertFalse(ok, 'una fecha elegida inválida debe bloquear la aprobación')
        self.assertIn(invalido.strftime('%d/%m/%Y'), m, f'el mensaje debe NOMBRAR la fecha inválida: {m}')

    def test_aplicacion_balanceada(self):
        # Si un lado tiene menos días válidos, la aplicación recorta al mínimo común:
        # se aplican IGUAL número de cesiones y devoluciones (no se paga sin recibir).
        from datetime import timedelta
        from turnos.models import Turno
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        strat = DobladaPermanenteStrategy()
        sol, msg = strat.crear_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'),
            'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '1', 'dias_devolucion': '3',  # martes cubre, jueves devuelve
        })
        self.assertIsNotNone(sol, msg)
        # Comprometer UN jueves (devolución) → ese lado queda con un día válido menos.
        d = self.fi
        while d.weekday() != 3:
            d += timedelta(days=1)
        Turno.objects.create(explorador=self.sol, fecha=d, jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.sol, fecha=d, jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')

        sol = SolicitudCambio.objects.select_related('doblada_permanente').get(id=sol.id)
        n_ces, n_dev = DPAS.aplicar(sol, sol.doblada_permanente)
        self.assertEqual(n_ces, n_dev, "Cesiones y devoluciones aplicadas deben quedar balanceadas")
        self.assertGreaterEqual(n_ces, 1)

    def test_sabado_rechazado(self):
        # La doblada permanente ya no admite sábados (solo lun-vie).
        strat = DobladaPermanenteStrategy()
        datos = {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'),
            'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '5', 'dias_devolucion': '3',
        }
        ok, msg = strat.validar_solicitud(datos)
        self.assertFalse(ok)
        self.assertIn('lunes a viernes', msg.lower())

    def test_ocurrencias_omite_comprometido_y_sabado(self):
        # Núcleo del comportamiento "omitir": un día comprometido se salta; los demás siguen.
        from datetime import timedelta
        from turnos.models import Turno
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        d = self.fi
        while d.weekday() != 1:  # primer martes
            d += timedelta(days=1)
        primer_martes = d

        occ = list(DPAS._ocurrencias(self.fi, self.ff, {1}, self.sol, self.rec))
        self.assertIn(primer_martes, occ)

        # Comprometer ese martes para el solicitante (doblada previa).
        Turno.objects.create(explorador=self.sol, fecha=primer_martes, jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.sol, fecha=primer_martes, jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')

        occ2 = list(DPAS._ocurrencias(self.fi, self.ff, {1}, self.sol, self.rec))
        self.assertNotIn(primer_martes, occ2)   # se OMITE
        self.assertGreaterEqual(len(occ2), 1)   # pero los demás martes siguen

        # Sábado: nunca aparece.
        self.assertEqual(list(DPAS._ocurrencias(self.fi, self.ff, {5}, self.sol, self.rec)), [])


class DobladaPermJornadaRealTest(TestCase):
    """La doblada permanente usa la jornada REAL de cada fecha (no la predeterminada): incluye los
    días cambiados por CT sencillo/permanente y valida jornadas contrarias por fecha, tanto para el
    solicitante como para el receptor."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala DP2', activo=True)
        # Solicitante y receptor con la MISMA base (AM): por la predeterminada NUNCA serían contrarios.
        u1 = User.objects.create_user(username='sol.jr', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='JR', cedula='11', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        u2 = User.objects.create_user(username='rec.jr', password='x')
        self.rec = Empleado.objects.create(user=u2, nombre='Rec', apellido='JR', cedula='22', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.rec, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=self.sol, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.rec, sala=self.sala)
        hoy = timezone.now().date()
        anio, mes = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        self.fi = date(anio, mes, 1)
        self.ff = self.fi + timedelta(days=27)

    def _martes(self):
        d = self.fi
        out = []
        while d <= self.ff:
            if d.weekday() == 1:
                out.append(d)
            d += timedelta(days=1)
        return out

    def _ct_pm(self, emp, fecha):
        """Materializa un CT permanente: turno real PM ese día (cambia la jornada real del día)."""
        from turnos.models import Turno
        Turno.objects.create(explorador=emp, fecha=fecha, jornada=self.pm, sala=self.sala, tipo_cambio='CT PERMANENTE')

    def test_ct_flip_hace_el_dia_valido_por_jornada_real(self):
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        from solicitudes.services.ct_permanente_helper import _jornada_unica_real
        martes = self._martes()
        # Sin CT: sol y rec ambos AM (misma base) → NINGÚN martes es válido (no son contrarios).
        self.assertEqual(list(DPAS._ocurrencias(self.fi, self.ff, {1}, self.sol, self.rec)), [])
        # Aplicar CT permanente PM al solicitante en los 2 primeros martes → esos días es real PM.
        self._ct_pm(self.sol, martes[0])
        self._ct_pm(self.sol, martes[1])
        occ = list(DPAS._ocurrencias(self.fi, self.ff, {1}, self.sol, self.rec))
        self.assertEqual(sorted(occ), sorted(martes[:2]),
                         f'solo los martes con jornada real PM (contraria a rec AM) son válidos: {occ}')
        self.assertTrue(all(_jornada_unica_real(self.sol, d) == 'PM' for d in occ))

    def test_receptor_con_doblada_se_omite(self):
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        from turnos.models import Turno
        martes = self._martes()
        self._ct_pm(self.sol, martes[0])  # sol real PM (contrario a rec AM) → válido…
        # …pero el receptor ese día YA tiene doblada (AM+PM) → no puede cubrir → se omite.
        Turno.objects.create(explorador=self.rec, fecha=martes[0], jornada=self.am, sala=self.sala, tipo_cambio='DOBLADA')
        Turno.objects.create(explorador=self.rec, fecha=martes[0], jornada=self.pm, sala=self.sala, tipo_cambio='DOBLADA')
        occ = list(DPAS._ocurrencias(self.fi, self.ff, {1}, self.sol, self.rec))
        self.assertNotIn(martes[0], occ, 'no se puede doblar con alguien que ya tiene doblada ese día')

    def test_misma_jornada_real_se_omite(self):
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        martes = self._martes()
        # Ambos quedan reales PM ese martes (misma jornada) → no contrarios → se omite.
        self._ct_pm(self.sol, martes[0])
        self._ct_pm(self.rec, martes[0])
        occ = list(DPAS._ocurrencias(self.fi, self.ff, {1}, self.sol, self.rec))
        self.assertNotIn(martes[0], occ, 'misma jornada real (ambos PM) no permite doblada')

    def test_validacion_ok_con_jornada_real_aunque_base_igual(self):
        # base igual (ambos AM) pero por CT el solicitante queda PM en martes(cesión) y jueves(devolución)
        # → válido por jornada real. Antes se rechazaba por "misma jornada base".
        strat = DobladaPermanenteStrategy()
        d = self.fi
        while d <= self.ff:
            if d.weekday() in (1, 3):  # martes y jueves
                self._ct_pm(self.sol, d)
            d += timedelta(days=1)
        datos = {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba jornada real',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'), 'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '1', 'dias_devolucion': '3',
        }
        ok, msg = strat.validar_solicitud(datos)
        self.assertTrue(ok, f'debe validar por jornada real aunque la base sea igual: {msg}')

    def test_temporada_doblada_virtual_se_omite(self):
        """Regresión (caso marco 18/08): sin turnos reales, por TEMPORADA el grupo contrario descansa
        y el solicitante DOBLA (virtual). La base diría AM, pero la fuente real (estado_dia/Mis Turnos)
        es DOBLADA → no elegible → el día se OMITE (no queda en el limbo)."""
        from django.core.cache import cache
        from turnos.models import DescansoSemanaManual
        from solicitudes.services.ct_permanente_helper import _jornada_doblada_perm, _jornada_unica_real
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        m = self._martes()[0]
        # El grupo contrario (PM) descansa por temporada → el solicitante (AM) cubre el día completo.
        DescansoSemanaManual.objects.create(fecha=m, jornada=self.pm, activo=True)
        cache.clear()
        self.assertEqual(_jornada_unica_real(self.sol, m), 'AM', 'la BASE (lo que veía el form antes) es AM')
        self.assertIsNone(_jornada_doblada_perm(self.sol, m), 'la realidad es DOBLADA virtual → no elegible')
        self.assertNotIn(m, list(DPAS._ocurrencias(self.fi, self.ff, {1}, self.sol, self.rec)))

    def test_cambio_descanso_da_jornada_real_elegible(self):
        """Regresión (caso marco 11/08): un cambio de descanso deja un turno REAL AM en un día que la
        config marca como descanso. La fuente real (estado_dia) es AM → elegible en AM, aunque la
        config (_es_dia_descanso) diga descanso."""
        from django.core.cache import cache
        from turnos.models import DescansoSemanaManual, Turno
        from solicitudes.services.ct_permanente_helper import _jornada_doblada_perm, _es_dia_descanso
        m = self._martes()[0]
        DescansoSemanaManual.objects.create(fecha=m, jornada=self.am, activo=True)  # config: AM descansa
        Turno.objects.create(explorador=self.sol, fecha=m, jornada=self.am, sala=self.sala, tipo_cambio='CAMBIO DESCANSO')
        cache.clear()
        self.assertTrue(_es_dia_descanso(self.sol, m), 'la CONFIG marca descanso (lo que fallaba antes)')
        self.assertEqual(_jornada_doblada_perm(self.sol, m), 'AM', 'pero trabaja AM de verdad → elegible')


class DobladaPermRevertRestauraEstadoPrevioTest(TestCase):
    """Al cancelar una DOBLADA PERMANENTE aprobada, el revert debe dejar exactamente el estado
    previo: si antes NO había fila real de Turno (solo jornada base calculada), después de
    revertir tampoco debe haberla (no se materializa un turno base); si antes había un Turno real
    no-base (p.ej. por CAMBIO DESCANSO), el revert debe restaurar esa fila exacta, no una base."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala DP3', activo=True)
        u1 = User.objects.create_user(username='sol.rev', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='Rev', cedula='31', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        u2 = User.objects.create_user(username='rec.rev', password='x')
        self.rec = Empleado.objects.create(user=u2, nombre='Rec', apellido='Rev', cedula='32', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.rec, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=self.sol, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.rec, sala=self.sala)
        hoy = timezone.now().date()
        anio, mes = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        self.fi = date(anio, mes, 1)
        self.ff = self.fi + timedelta(days=27)
        # Primer martes del rango: día de cesión.
        d = self.fi
        while d.weekday() != 1:
            d += timedelta(days=1)
        self.martes = d

    def _crear_y_aprobar(self):
        strat = DobladaPermanenteStrategy()
        sol, msg = strat.crear_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipo, 'comentario': 'Prueba revert',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'), 'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '1', 'dias_devolucion': '3',
        })
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        return SolicitudCambio.objects.select_related('doblada_permanente').get(id=sol.id)

    def test_revert_sin_turno_previo_no_materializa_base(self):
        from turnos.models import Turno
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        self.assertFalse(Turno.objects.filter(explorador=self.sol, fecha=self.martes).exists())
        sol = self._crear_y_aprobar()
        DPAS.aplicar(sol, sol.doblada_permanente)

        DPAS.revertir(sol)
        sol.estado = 'cancelada'
        sol.save(update_fields=['estado'])

        self.assertFalse(
            Turno.objects.filter(explorador=self.sol, fecha=self.martes).exists(),
            'no debe materializarse un turno donde antes no había ninguno (solo jornada base calculada)',
        )

    def test_revert_con_turno_no_base_restaura_esa_fila_exacta(self):
        from turnos.models import Turno
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        Turno.objects.create(
            explorador=self.sol, fecha=self.martes, jornada=self.pm, sala=self.sala,
            tipo_cambio='CAMBIO DESCANSO',
        )
        sol = self._crear_y_aprobar()
        DPAS.aplicar(sol, sol.doblada_permanente)

        DPAS.revertir(sol)
        sol.estado = 'cancelada'
        sol.save(update_fields=['estado'])

        turnos = list(Turno.objects.filter(explorador=self.sol, fecha=self.martes))
        self.assertEqual(len(turnos), 1, 'debe restaurar exactamente una fila (la previa), no una base ni ninguna')
        self.assertEqual(turnos[0].jornada, self.pm)
        self.assertEqual(turnos[0].tipo_cambio, 'CAMBIO DESCANSO', 'debe conservar el tipo_cambio original, no volverse un turno base')


class DobladaPermAtribucionCompaneroTest(TestCase):
    """Regresión (caso marco 11/08): el detalle del día en 'Mis Turnos' debe atribuir el descanso a la
    solicitud/compañero que REALMENTE lo produjo. Cuando el mismo día de la semana (p. ej. martes) se
    reparte entre VARIOS compañeros por FECHAS distintas, el descanso de cada fecha debe apuntar al
    compañero de ESA fecha (no al primero que coincida por patrón de weekday); y un martes que no se
    eligió no debe aparecer como descanso."""

    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala DPA', activo=True)
        u1 = User.objects.create_user(username='sol.atb', password='x')
        self.sol = Empleado.objects.create(user=u1, nombre='Sol', apellido='Atb', cedula='41', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.sol, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        # Dos compañeros con base AM (contrarios al solicitante PM).
        u2 = User.objects.create_user(username='comp1.atb', password='x')
        self.comp1 = Empleado.objects.create(user=u2, nombre='Uno', apellido='Comp', cedula='42', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.comp1, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        u3 = User.objects.create_user(username='comp2.atb', password='x')
        self.comp2 = Empleado.objects.create(user=u3, nombre='Dos', apellido='Comp', cedula='43', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.comp2, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        for e in (self.sol, self.comp1, self.comp2):
            CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
        hoy = timezone.now().date()
        anio, mes = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        self.fi = date(anio, mes, 1)
        self.ff = self.fi + timedelta(days=27)
        martes, jueves = [], []
        d = self.fi
        while d <= self.ff:
            if d.weekday() == 1:
                martes.append(d)
            if d.weekday() == 3:
                jueves.append(d)
            d += timedelta(days=1)
        self.martes = martes  # >= 3 martes en el rango
        self.jueves = jueves

    def _crear_aprobar_aplicar(self, receptor, fecha_ces, fecha_dev):
        strat = DobladaPermanenteStrategy()
        sol, msg = strat.crear_solicitud({
            'explorador_solicitante': self.sol, 'explorador_receptor': receptor,
            'tipo_cambio': self.tipo, 'comentario': 'atribucion',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'), 'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': '1', 'dias_devolucion': '3',
            'fechas_cesion': fecha_ces.strftime('%Y-%m-%d'),
            'fechas_devolucion': fecha_dev.strftime('%Y-%m-%d'),
        })
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'; sol.fecha_resolucion = timezone.now(); sol.save()
        sol = SolicitudCambio.objects.select_related('doblada_permanente').get(id=sol.id)
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        DPAS.aplicar(sol, sol.doblada_permanente)
        return sol

    def test_descanso_apunta_al_companero_de_esa_fecha(self):
        from django.core.cache import cache
        from turnos.services.turno_service import TurnoService as TS
        # comp1 cubre el martes[0]; comp2 cubre el martes[1] (mismo weekday, fechas distintas).
        self._crear_aprobar_aplicar(self.comp1, self.martes[0], self.jueves[0])
        self._crear_aprobar_aplicar(self.comp2, self.martes[1], self.jueves[1])
        cache.clear()
        # Cada fecha de cesión debe atribuirse a SU compañero real.
        c0 = TS.estado_dia(self.sol, self.martes[0]).get('companero') or {}
        c1 = TS.estado_dia(self.sol, self.martes[1]).get('companero') or {}
        self.assertIn('Uno', c0.get('nombre', ''), f'martes[0] debe ser de comp1, no {c0}')
        self.assertIn('Dos', c1.get('nombre', ''), f'martes[1] debe ser de comp2, no {c1}')
        # Un martes NO elegido no debe aparecer como descanso (el patrón de weekday ya no manda).
        self.assertTrue(TS.estado_dia(self.sol, self.martes[2]).get('trabaja'),
                        'un martes sin fecha elegida no debe quedar como descanso por patrón')
