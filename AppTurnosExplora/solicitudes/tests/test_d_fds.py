"""
Tests para D FDS (Doblada de Fin de Semana).

Cubren validación y aplicación:
- El solicitante cede su día del finde a un compañero del grupo contrario.
- En la cesión: receptor dobla (AM+PM), solicitante descansa.
- En el pago (otro finde del mismo mes): solicitante dobla (AM+PM), receptor descansa.
- Deudas: entre exploradores + corporativa 30 min por cada día doblado.

Las fechas se calculan dinámicamente (nunca hardcodeadas en el pasado).
"""
from datetime import date, timedelta
from unittest import mock

from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import (
    SolicitudCambio, TipoSolicitudCambio, DobladaDetalle,
    DeudaExplorador, DeudaCorporativa,
)
from turnos.models import Turno, AsignarJornadaExplorador, Sala
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService
from solicitudes.services.strategies import d_fds_strategy as _d_fds_mod
from solicitudes.services.strategies.d_fds_strategy import DFDSStrategy


def _findes_de_mes(anio, mes):
    """Lista [(fecha, grupo_que_trabaja)] de todos los días de finde del mes."""
    d = date(anio, mes, 1)
    res = []
    while d.month == mes:
        if d.weekday() in (5, 6):
            res.append((d, AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(d)))
        d += timedelta(days=1)
    return res


def _fechas_fds(grupo_solicitante, grupo_receptor):
    """
    Devuelve (cesion, pago) en un mismo mes futuro y del MISMO día de la semana
    (sáb→sáb o dom→dom), conforme a la regla: si cedes un domingo, devuelves un domingo.
    - cesion: día de finde donde trabaja el grupo del solicitante.
    - pago: otro día de finde del MISMO día de semana (mismo mes) donde trabaja el receptor.
    """
    hoy = timezone.localdate()
    # Empezar dos meses adelante para asegurar futuro y margen.
    anio, mes = hoy.year, hoy.month
    for _ in range(2):
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    for _ in range(6):  # buscar en meses sucesivos por si acaso
        findes = _findes_de_mes(anio, mes)
        # Probar por cada tipo de día (sábado=5, domingo=6) un par cesión/pago del mismo tipo.
        for wd in (5, 6):
            dias = [f for f, _g in findes if f.weekday() == wd and f > hoy]
            ces = next((f for f in dias if AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(f) == grupo_solicitante), None)
            pago = next((f for f in dias if AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(f) == grupo_receptor and f != ces), None)
            if ces and pago:
                return ces, pago
        mes += 1
        if mes > 12:
            mes = 1
            anio += 1
    raise AssertionError("No se hallaron fechas de finde válidas para la prueba")


class DFDSBaseTest(TestCase):
    def setUp(self):
        self.tipo = TipoSolicitudCambio.objects.create(nombre='D FDS')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala FDS', activo=True)

        # Solicitante PM, receptor AM (grupos contrarios)
        self.u_sol = User.objects.create_user(username='sol.fds', password='x')
        self.solicitante = Empleado.objects.create(user=self.u_sol, nombre='Sol', apellido='Uno', cedula='111', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.solicitante, jornada=self.pm, fecha_inicio=date(2025, 1, 1))

        self.u_rec = User.objects.create_user(username='rec.fds', password='x')
        self.receptor = Empleado.objects.create(user=self.u_rec, nombre='Rec', apellido='Dos', cedula='222', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=self.receptor, jornada=self.am, fecha_inicio=date(2025, 1, 1))

        # Sala (especialidad) de ambos vía competencia — necesaria para crear turnos de doblada
        CompetenciaEmpleado.objects.create(empleado=self.solicitante, sala=self.sala)
        CompetenciaEmpleado.objects.create(empleado=self.receptor, sala=self.sala)

        self.strat = DFDSStrategy()
        self.ces, self.pago = _fechas_fds('PM', 'AM')
        # La alternancia de findes/festivos es un DATO publicado: sin publicarla, estos
        # días saldrían como 'sin_planificar'. Se publica igual a la fórmula histórica.
        from turnos.tests.alternancia_helpers import publicar_alternancia
        publicar_alternancia(self.ces.year, self.pago.year)

    def _datos(self, **over):
        d = {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'tipo_cambio': self.tipo,
            'comentario': 'Prueba',
            'fecha_cambio_turno': self.ces.strftime('%Y-%m-%d'),
            'fecha_pago': self.pago.strftime('%Y-%m-%d'),
            'fecha_creacion_solicitud': timezone.localdate(),
        }
        d.update(over)
        return d


class DFDSValidacionTest(DFDSBaseTest):
    def test_caso_valido(self):
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertTrue(ok, msg)

    def test_revalidacion_para_aprobar_ok(self):
        # Una D FDS válida debe re-validar True al aprobar (no bloquear aprobaciones válidas).
        sol, msg = self.strat.crear_solicitud(self._datos())
        self.assertIsNotNone(sol, msg)
        sol = SolicitudCambio.objects.select_related('doblada').get(id=sol.id)
        ok, m = self.strat.revalidar_para_aprobar(sol)
        self.assertTrue(ok, m)

    def test_mismo_empleado_rechazado(self):
        ok, msg = self.strat.validar_solicitud(self._datos(explorador_receptor=self.solicitante))
        self.assertFalse(ok)

    def test_companero_que_trabaja_ese_dia_rechazado(self):
        """
        Ya NO se rechaza por "mismo grupo": lo que importa es el estado real del día. Un
        compañero que trabaja el día que se cede no puede cubrirlo (no lo tiene libre), y ese
        es justamente el caso de alguien del mismo grupo en la fecha de cesión.
        """
        u = User.objects.create_user(username='rec.pm', password='x')
        rec_pm = Empleado.objects.create(user=u, nombre='RecPM', apellido='Tres', cedula='333', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=rec_pm, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        ok, msg = self.strat.validar_solicitud(self._datos(explorador_receptor=rec_pm))
        self.assertFalse(ok)
        self.assertIn('ya trabaja el', msg)
        # El motivo es el día ocupado, no la etiqueta del grupo.
        self.assertNotIn('grupo contrario', msg)

    def test_cesion_entre_semana_rechazada(self):
        lunes = self.ces
        while lunes.weekday() != 0:
            lunes += timedelta(days=1)
        ok, msg = self.strat.validar_solicitud(self._datos(fecha_cambio_turno=lunes.strftime('%Y-%m-%d')))
        self.assertFalse(ok)

    def test_pago_distinto_dia_rechazado(self):
        # Regla del mismo día: si cedes un sábado, el pago debe ser sábado (y viceversa).
        opp_wd = 6 if self.ces.weekday() == 5 else 5
        cand = None
        d = date(self.ces.year, self.ces.month, 1)
        while d.month == self.ces.month:
            if d.weekday() == opp_wd and d > timezone.localdate() and d != self.ces:
                cand = d
                break
            d += timedelta(days=1)
        self.assertIsNotNone(cand, "No se encontró un finde del día opuesto para la prueba")
        ok, msg = self.strat.validar_solicitud(self._datos(fecha_pago=cand.strftime('%Y-%m-%d')))
        self.assertFalse(ok)
        self.assertIn('debe ser un', msg.lower())

    def test_pago_otro_mes_rechazado(self):
        # Avanzar al mes siguiente, primer día del MISMO tipo que la cesión (sáb/dom),
        # para que dispare la regla de "mismo mes" y no la de "mismo día".
        m = self.pago.month
        d = date(self.pago.year + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1)
        while d.weekday() != self.ces.weekday():
            d += timedelta(days=1)
        ok, msg = self.strat.validar_solicitud(self._datos(fecha_pago=d.strftime('%Y-%m-%d')))
        self.assertFalse(ok)
        self.assertIn('mismo mes', msg.lower())


class DFDSConcurrenciaReceptorTest(DFDSBaseTest):
    def test_caso_b_receptor_ya_comprometido(self):
        # A (solicitante -> receptor) aprobada y aplicada: el receptor dobla ese finde.
        solA, msg = self.strat.crear_solicitud(self._datos())
        self.assertIsNotNone(solA, msg)
        solA.estado = 'aprobada'
        solA.fecha_resolucion = timezone.now()
        solA.save()
        solA = SolicitudCambio.objects.select_related('doblada').get(id=solA.id)
        ok, m = self.strat.aplicar_cambios(solA)
        self.assertTrue(ok, m)
        # Segundo solicitante (mismo grupo) hacia el MISMO receptor, mismo finde -> debe bloquearse.
        u = User.objects.create_user(username='sol3.fds', password='x')
        sol2 = Empleado.objects.create(user=u, nombre='Sol3', apellido='Uno', cedula='444', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=sol2, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=sol2, sala=self.sala)
        ok2, m2 = self.strat.validar_solicitud(self._datos(explorador_solicitante=sol2))
        self.assertFalse(ok2, f"B debió bloquearse (receptor ya doblado por A). msg={m2}")


class DFDSAplicacionTest(DFDSBaseTest):
    def _crear_y_aplicar(self):
        sol, msg = self.strat.crear_solicitud(self._datos())
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        sol = SolicitudCambio.objects.select_related('doblada', 'explorador_solicitante', 'explorador_receptor').get(id=sol.id)
        ok, msg = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        return sol

    def _jornadas(self, emp, fecha):
        return sorted(t.jornada.nombre.upper() for t in Turno.objects.filter(explorador=emp, fecha=fecha).select_related('jornada'))

    def test_aplicacion_turnos(self):
        self._crear_y_aplicar()
        # Favor: receptor dobla cesión, solicitante descansa
        self.assertEqual(self._jornadas(self.receptor, self.ces), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.solicitante, self.ces), [])
        # Pago: solicitante dobla, receptor descansa
        self.assertEqual(self._jornadas(self.solicitante, self.pago), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.receptor, self.pago), [])

    def test_deudas_generadas(self):
        sol = self._crear_y_aplicar()
        # Deuda entre exploradores: solicitante deudor, receptor acreedor
        de = DeudaExplorador.objects.filter(solicitud_origen=sol)
        self.assertEqual(de.count(), 1)
        self.assertEqual(de.first().deudor_id, self.solicitante.id)
        self.assertEqual(de.first().acreedor_id, self.receptor.id)
        # Corporativa: en D FDS la cesión y el pago caen en fin de semana, y los fines de
        # semana NO generan deuda de 30 min (solo se debe al cambiar un sábado por un día
        # de semana). Por lo tanto no debe generarse ninguna deuda corporativa.
        dc = DeudaCorporativa.objects.filter(solicitud_origen=sol)
        self.assertEqual(dc.count(), 0)

    def test_revert_restaura_y_cancela_deudas(self):
        from solicitudes.services.d_fds_aplicacion_service import DFDSAplicacionService
        sol = self._crear_y_aplicar()
        # Tras aplicar: receptor dobla cesión, solicitante dobla pago; hay deuda vigente.
        self.assertEqual(self._jornadas(self.receptor, self.ces), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.solicitante, self.pago), ['AM', 'PM'])
        self.assertTrue(DeudaExplorador.objects.filter(solicitud_origen=sol)
                        .exclude(estado='cancelada').exists())
        # Revertir → turnos vuelven a vacío (findes virtuales) y deudas canceladas.
        DFDSAplicacionService.revertir(sol)
        self.assertEqual(self._jornadas(self.receptor, self.ces), [])
        self.assertEqual(self._jornadas(self.solicitante, self.pago), [])
        self.assertEqual(self._jornadas(self.solicitante, self.ces), [])
        self.assertEqual(self._jornadas(self.receptor, self.pago), [])
        self.assertFalse(DeudaExplorador.objects.filter(solicitud_origen=sol)
                         .exclude(estado='cancelada').exists())


class DFDSHuecosCorregidosTest(DFDSBaseTest):
    """Regresión de los huecos detectados en la auditoría del formulario D FDS."""

    def _aprobar_y_aplicar(self, datos=None):
        sol, msg = self.strat.crear_solicitud(datos or self._datos())
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        sol = SolicitudCambio.objects.select_related(
            'doblada', 'explorador_solicitante', 'explorador_receptor').get(id=sol.id)
        ok, m = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, m)
        return sol

    def _otro_dia_del_grupo(self, referencia, grupo):
        """Otro día del mes de `referencia`, mismo día de la semana, donde trabaja `grupo`."""
        for f, _g in _findes_de_mes(referencia.year, referencia.month):
            if (f.weekday() == referencia.weekday() and f != referencia
                    and f > timezone.localdate()
                    and AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(f) == grupo):
                return f
        return None

    def test_se_puede_pagar_cubriendo_un_dia_que_el_companero_cubre(self):
        """
        Se puede devolver el favor cubriendo un día que el compañero trabaja por un favor AJENO.
        Un favor se mide en días trabajados, no en de quién es el día: si él estaba comprometido
        a trabajarlo y se lo cubren, trabaja un día menos, que es justo lo que se le debe. El día
        sigue teniendo una sola persona y las cuentas de los tres quedan en cero.

        En turnos es la MISMA operación que el traspaso de cobertura, solo que vista desde el
        otro lado; bloquearla mientras se permitía el traspaso era incoherente.
        """
        # Tras aplicar, el solicitante trabaja `self.pago` cubriendo al receptor.
        self._aprobar_y_aplicar()
        # Un tercero del MISMO grupo (trabaja la fecha de cesión) le pide al solicitante que le
        # devuelva el favor justo en ese día de cobertura.
        u = User.objects.create_user(username='tercero.fds', password='x')
        tercero = Empleado.objects.create(user=u, nombre='Ter', apellido='Cero', cedula='555', activo=True)
        AsignarJornadaExplorador.objects.create(explorador=tercero, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=tercero, sala=self.sala)
        ok, msg = self.strat.validar_solicitud(self._datos(
            explorador_solicitante=tercero, explorador_receptor=self.solicitante,
            fecha_cambio_turno=self.ces.strftime('%Y-%m-%d'),
            fecha_pago=self.pago.strftime('%Y-%m-%d'),
        ))
        self.assertTrue(ok, f'El día de cobertura del compañero sí sirve como devolución: {msg}')

    def _solicitud_aprobada_de_otro_tipo(self, nombre_tipo, fecha_cesion, solicitante=None):
        """Solicitud aprobada de otro tipo que deja al solicitante DESCANSANDO en `fecha_cesion`."""
        tipo = TipoSolicitudCambio.objects.create(nombre=nombre_tipo)
        s = SolicitudCambio.objects.create(
            explorador_solicitante=solicitante or self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=tipo, comentario='previa', fecha_cambio_turno=fecha_cesion,
            estado='aprobada', fecha_resolucion=timezone.now())
        DobladaDetalle.objects.create(
            solicitud=s, fecha_pago=fecha_cesion + timedelta(days=7),
            minutos_deuda=0, tipo_cesion='cesion_completa', empleado_receptor=self.receptor)
        return s

    def test_no_se_puede_pagar_con_un_dia_que_ya_cediste(self):
        """Ese día lo cubre alguien COMO EXTRA: trabajarlo dejaría dos personas en el turno."""
        self._solicitud_aprobada_de_otro_tipo('DOBLADA', self.pago)
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertFalse(ok)
        self.assertIn('ya se lo cediste', msg)

    def test_si_se_puede_pagar_un_dia_que_descansas_por_un_cambio_de_descanso(self):
        """
        Un cambio de descanso es un INTERCAMBIO ya saldado: diste tu día y tomaste otro, y quien
        trabaja ese día lo hace EN TU LUGAR, no como extra. Al cubrir a un compañero ese día
        sustituyes a ese compañero, así que el turno conserva la misma gente.

        Antes se rechazaba junto con las cesiones de verdad y dejaba sin salida a quien había
        hecho un cambio de descanso ese finde.
        """
        self._solicitud_aprobada_de_otro_tipo('CAMBIO DESCANSO', self.pago)
        from turnos.services.turno_service import TurnoService
        est = TurnoService.estado_dia(self.solicitante, self.pago)
        self.assertFalse(est['trabaja'], 'sanity: ese día debe quedar libre por el intercambio')

        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertTrue(ok, f'Un día libre por intercambio sí sirve para pagar: {msg}')

    def test_helper_dia_cubriendo_detecta_ambos_lados(self):
        from turnos.services.turno_service import TurnoService
        sol = self._aprobar_y_aplicar()
        # Solicitante: trabaja el día de pago porque devuelve el favor.
        info_pago = TurnoService.dia_cubriendo_por_solicitud(self.solicitante, self.pago)
        self.assertIsNotNone(info_pago)
        self.assertEqual(info_pago['tipo'], 'pago')
        self.assertEqual(info_pago['solicitud_id'], sol.id)
        # El compañero es SIEMPRE la otra parte del favor, nunca uno mismo.
        self.assertEqual(info_pago['companero']['id'], self.receptor.id)
        # Receptor: trabaja el día de cesión porque cubre al compañero.
        info_ces = TurnoService.dia_cubriendo_por_solicitud(self.receptor, self.ces)
        self.assertIsNotNone(info_ces)
        self.assertEqual(info_ces['tipo'], 'cubre_cesion')
        self.assertEqual(info_ces['companero']['id'], self.solicitante.id)
        # `excluir_id` (re-validación de la propia solicitud) no debe detectarse a sí misma.
        self.assertIsNone(TurnoService.dia_cubriendo_por_solicitud(
            self.solicitante, self.pago, excluir_id=sol.id))

    def test_pendiente_con_mismo_dia_de_pago_bloquea(self):
        """Hueco 4: antes solo se cruzaba `fecha_cambio_turno`, así que dos pendientes podían
        apuntar al mismo día de pago y aprobarse en paralelo."""
        sol, msg = self.strat.crear_solicitud(self._datos())
        self.assertIsNotNone(sol, msg)
        self.assertEqual(sol.estado, 'pendiente')
        otra_cesion = self._otro_dia_del_grupo(self.ces, 'PM')
        if not otra_cesion:
            self.skipTest('El mes de prueba no tiene otro día de finde del grupo PM')
        ok, m = self.strat.validar_solicitud(self._datos(
            fecha_cambio_turno=otra_cesion.strftime('%Y-%m-%d')))  # mismo self.pago
        self.assertFalse(ok, 'Una pendiente que ya usa ese día de pago debe bloquear la nueva')
        self.assertIn('pendiente', m.lower())

    def test_cesion_hoy_rechazada_al_crear(self):
        """
        Antes este test se saltaba salvo que se corriera un sábado o domingo (una D FDS solo opera
        sobre findes), así que 5 de cada 7 días la regla no se comprobaba y `N passed` no lo
        delataba. Ahora se fija "hoy" EN el día de cesión —que es finde por construcción— y corre
        siempre.
        """
        with mock.patch.object(_d_fds_mod.timezone, 'localdate', return_value=self.ces):
            ok, msg = self.strat.validar_solicitud(self._datos(
                fecha_cambio_turno=self.ces.strftime('%Y-%m-%d')))
        self.assertFalse(ok, 'ceder el finde en curso no se permite al crear')
        self.assertIn('día en curso', msg)

    def test_cesion_hoy_admitida_al_revalidar(self):
        """
        El supervisor puede aprobar el mismo día del finde: si no, una solicitud creada antes
        quedaría atrapada sin poder aprobarse ni rechazarse.
        """
        with mock.patch.object(_d_fds_mod.timezone, 'localdate', return_value=self.ces):
            ok, msg = self.strat.validar_solicitud(self._datos(
                fecha_cambio_turno=self.ces.strftime('%Y-%m-%d'), es_revalidacion=True))
        self.assertNotIn('día en curso', msg or '',
                         'al re-validar, el día en curso no debe bloquear la aprobación')

    def test_cesion_pasada_rechazada(self):
        """Un finde ya pasado no se puede ceder, ni creando ni re-validando."""
        with mock.patch.object(_d_fds_mod.timezone, 'localdate',
                               return_value=self.ces + timedelta(days=7)):
            ok, msg = self.strat.validar_solicitud(self._datos(
                fecha_cambio_turno=self.ces.strftime('%Y-%m-%d')))
        self.assertFalse(ok)
        self.assertIn('posterior a hoy', msg)


class DFDSAlternanciaMesAPITest(DFDSBaseTest):
    """Hueco 2: findes a caballo entre dos meses."""

    def _mes_que_empieza_en_domingo(self):
        hoy = timezone.localdate()
        anio, mes = hoy.year, hoy.month
        for _ in range(14):
            mes += 1
            if mes > 12:
                mes, anio = 1, anio + 1
            if date(anio, mes, 1).weekday() == 6:
                return anio, mes
        return None, None

    def test_finde_a_caballo_aparece_en_el_mes_del_domingo(self):
        anio, mes = self._mes_que_empieza_en_domingo()
        if not anio:
            self.skipTest('No hay un mes próximo que empiece en domingo')
        self.client.force_login(self.u_sol)
        r = self.client.get('/solicitudes/alternancia-mes/', {'anio': anio, 'mes': mes})
        self.assertEqual(r.status_code, 200)
        data = r.json().get('data', r.json())
        primeros = [f for f in data['findes'] if f['domingo']['fecha'] == date(anio, mes, 1).isoformat()]
        self.assertEqual(len(primeros), 1,
                         'El finde cuyo domingo es el día 1 debe listarse en ese mes')
        self.assertTrue(primeros[0]['domingo']['del_mes'])
        self.assertFalse(primeros[0]['sabado']['del_mes'])

    def test_dia_de_otro_mes_no_es_seleccionable(self):
        anio, mes = self._mes_que_empieza_en_domingo()
        if not anio:
            self.skipTest('No hay un mes próximo que empiece en domingo')
        mes_ant, anio_ant = (mes - 1, anio) if mes > 1 else (12, anio - 1)
        self.client.force_login(self.u_sol)
        r = self.client.get('/solicitudes/alternancia-mes/', {'anio': anio_ant, 'mes': mes_ant})
        data = r.json().get('data', r.json())
        ultimo = [f for f in data['findes'] if f['domingo']['fecha'] == date(anio, mes, 1).isoformat()]
        self.assertEqual(len(ultimo), 1)
        # Si el día trabajado de ese finde es el domingo (mes siguiente), no debe poder elegirse
        # desde este mes: el pago del mismo mes sería imposible.
        if ultimo[0]['mi_dia'] == 'domingo':
            self.assertFalse(ultimo[0]['seleccionable'])
            self.assertIn('otro mes', ultimo[0]['motivo_no_seleccionable'] or '')


class DFDSElegibilidadPorEstadoRealTest(DFDSBaseTest):
    """
    La elegibilidad se decide por el ESTADO REAL de cada día, no por el grupo AM/PM: en la
    operación conviven quienes trabajan los dos días del finde, quienes descansan los dos y
    quienes tienen media jornada por un cambio previo.
    """

    def _aprobar_y_aplicar(self, datos=None):
        sol, msg = self.strat.crear_solicitud(datos or self._datos())
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        sol = SolicitudCambio.objects.select_related(
            'doblada', 'explorador_solicitante', 'explorador_receptor').get(id=sol.id)
        ok, m = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, m)
        return sol

    def _otro_dia_finde(self, fecha):
        return fecha + timedelta(days=1) if fecha.weekday() == 5 else fecha - timedelta(days=1)

    def _nuevo_empleado(self, username, cedula, jornada):
        u = User.objects.create_user(username=username, password='x')
        e = Empleado.objects.create(user=u, nombre=username.split('.')[0], apellido='Test',
                                    cedula=cedula, activo=True)
        AsignarJornadaExplorador.objects.create(explorador=e, jornada=jornada,
                                                fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
        return e

    def _dia_devolucion(self, deudor, acreedor, referencia):
        """Día del mismo tipo (sáb/dom) y mes donde `acreedor` trabaja y `deudor` descansa."""
        from turnos.services.turno_service import TurnoService
        for f, _g in _findes_de_mes(referencia.year, referencia.month):
            if (f.weekday() == referencia.weekday() and f != referencia
                    and f > timezone.localdate()
                    and TurnoService.estado_dia(acreedor, f)['trabaja']
                    and not TurnoService.estado_dia(deudor, f)['trabaja']):
                return f
        return None

    # ---------------------------------------------------------------- candidatos
    def test_candidato_que_descansa_los_dos_dias_es_valido(self):
        """
        Antes se exigía que el compañero trabajase el OTRO día del finde, así que quien
        descansaba los dos quedaba fuera aunque fuese a quien mejor se le podía ceder.
        """
        # Tras ceder su día, el solicitante descansa los DOS días de ese finde.
        self._aprobar_y_aplicar()
        disp, motivo = self.strat.disponibilidad_companero(self.solicitante, self.ces)
        self.assertTrue(disp, f'Quien descansa los dos días debe poder recibir: {motivo}')

    def test_candidato_que_trabaja_ese_dia_no_es_valido(self):
        # El receptor pasa a trabajar la fecha de cesión: ya no tiene ese día libre.
        self._aprobar_y_aplicar()
        disp, motivo = self.strat.disponibilidad_companero(self.receptor, self.ces)
        self.assertFalse(disp)
        self.assertIn('trabaja', motivo)

    def test_candidato_con_media_jornada_en_el_otro_dia_no_es_valido(self):
        otro = self._otro_dia_finde(self.ces)
        candidato = self._nuevo_empleado('media.fds', '666', self.am)
        # Media jornada real (solo AM) el otro día del finde, por un cambio previo.
        Turno.objects.create(explorador=candidato, fecha=otro, jornada=self.am,
                             sala=self.sala, tipo_cambio='CT')
        disp, motivo = self.strat.disponibilidad_companero(candidato, self.ces)
        self.assertFalse(disp)
        self.assertIn('media jornada', motivo)

    def test_etiqueta_describe_a_la_persona_no_al_calendario(self):
        """
        La etiqueta del selector debe decir por qué ese compañero sirve —que DESCANSA el día que
        se le cede—, no "trabaja el otro día del finde". Ese texto se armaba desde el calendario,
        igual para todos, y afirmaba cosas falsas: a quien descansa los dos días del finde lo
        anunciaba como que trabajaba uno.
        """
        # Quien descansa los DOS días del finde (tras ceder el suyo) es candidato válido...
        self._aprobar_y_aplicar()
        disp, _ = self.strat.disponibilidad_companero(self.solicitante, self.ces)
        self.assertTrue(disp)
        # ...y su etiqueta no puede afirmar que trabaja nada.
        etiqueta = self.strat.etiqueta_companero(self.solicitante, self.ces)
        self.assertIn('descansa', etiqueta)
        self.assertNotIn('trabaja', etiqueta)
        self.assertIn(self.ces.strftime('%d/%m'), etiqueta)

    def test_etiqueta_del_intercambio_sigue_siendo_la_de_siempre(self):
        """CAMBIO DESCANSO es un intercambio: ahí lo que habilita SÍ es trabajar el otro día."""
        from solicitudes.services.strategies.cambio_descanso_strategy import CambioDescansoStrategy
        etiqueta = CambioDescansoStrategy().etiqueta_companero(self.receptor, self.ces)
        self.assertIn('trabaja', etiqueta)

    def test_pool_de_companeros_no_filtra_por_grupo(self):
        """El pool ya no excluye a los del mismo grupo: el filtro fino es por día."""
        companero_pm = self._nuevo_empleado('pool.pm', '777', self.pm)
        pool = self.strat.get_empleados_disponibles(self.ces.strftime('%Y-%m-%d'), self.solicitante)
        ids = {e.id for e in pool}
        self.assertIn(companero_pm.id, ids)          # mismo grupo que el solicitante
        self.assertIn(self.receptor.id, ids)         # grupo contrario
        self.assertNotIn(self.solicitante.id, ids)   # uno mismo nunca

    # ------------------------------------------------------- trabajar los dos días
    def test_quien_trabaja_los_dos_dias_puede_ceder_cualquiera_de_ellos(self):
        """
        Caso central (el que motivó el cambio): tras cubrir un favor, el RECEPTOR trabaja los
        DOS días de ese finde —el suyo y el que ha cubierto— y debe poder ceder cualquiera de
        los dos. Con el criterio anterior (un único "tu día" por finde) no podía ceder ninguno.
        """
        from turnos.services.turno_service import TurnoService
        self._aprobar_y_aplicar()
        propio = self._otro_dia_finde(self.ces)  # el día que le toca por alternancia
        self.assertTrue(TurnoService.estado_dia(self.receptor, self.ces)['trabaja'])
        self.assertTrue(TurnoService.estado_dia(self.receptor, propio)['trabaja'],
                        'Cubrir un favor debe dejarlo trabajando los dos días del finde')

        # a) El día que cubre por el favor (traspaso de cobertura).
        tercero = self._nuevo_empleado('sust.fds', '888', self.am)
        pago_a = self._dia_devolucion(self.receptor, tercero, self.ces)
        if pago_a:
            ok, msg = self.strat.validar_solicitud(self._datos(
                explorador_solicitante=self.receptor, explorador_receptor=tercero,
                fecha_cambio_turno=self.ces.strftime('%Y-%m-%d'),
                fecha_pago=pago_a.strftime('%Y-%m-%d')))
            self.assertTrue(ok, f'Debe poder ceder el día que cubre: {msg}')

        # b) Su propio día de ese mismo finde.
        pago_b = self._dia_devolucion(self.receptor, self.solicitante, propio)
        if not pago_a and not pago_b:
            self.skipTest('El mes de prueba no ofrece días de devolución')
        if pago_b:
            ok, msg = self.strat.validar_solicitud(self._datos(
                explorador_solicitante=self.receptor, explorador_receptor=self.solicitante,
                fecha_cambio_turno=propio.strftime('%Y-%m-%d'),
                fecha_pago=pago_b.strftime('%Y-%m-%d')))
            self.assertTrue(ok, f'Debe poder ceder también su propio día: {msg}')

    def test_traspaso_deja_el_dia_cubierto_y_avisa_al_acreedor(self):
        """
        El receptor traspasa a un tercero el día que cubría: el día sigue cubierto (completo),
        el acreedor original conserva su descanso y su acuerdo sigue vigente; solo cambia quién
        lo cubre, y por eso se le avisa.
        """
        from solicitudes.models import Notificacion
        from turnos.services.turno_service import TurnoService

        s1 = self._aprobar_y_aplicar()
        tercero = self._nuevo_empleado('sust2.fds', '999', self.am)
        pago_rec = self._dia_devolucion(self.receptor, tercero, self.ces)
        if not pago_rec:
            self.skipTest('El mes de prueba no ofrece un día de devolución para el traspaso')

        s2 = self._aprobar_y_aplicar(self._datos(
            explorador_solicitante=self.receptor, explorador_receptor=tercero,
            fecha_cambio_turno=self.ces.strftime('%Y-%m-%d'),
            fecha_pago=pago_rec.strftime('%Y-%m-%d'),
        ))

        # El día cedido lo trabaja ahora el sustituto, completo.
        jornadas = sorted(t.jornada.nombre.upper() for t in
                          Turno.objects.filter(explorador=tercero, fecha=self.ces)
                          .select_related('jornada'))
        self.assertEqual(jornadas, ['AM', 'PM'], 'El sustituto debe cubrir el día completo')
        # El acreedor original (quien cedió ese día) sigue descansándolo y su acuerdo vigente.
        self.assertFalse(TurnoService.estado_dia(self.solicitante, self.ces)['trabaja'])
        s1.refresh_from_db()
        self.assertEqual(s1.estado, 'aprobada')
        self.assertTrue(DeudaExplorador.objects.filter(solicitud_origen=s1)
                        .exclude(estado='cancelada').exists())
        # Y se le avisa del cambio de cobertura.
        self.assertTrue(
            Notificacion.objects.filter(destinatario=self.solicitante, solicitud=s2).exists(),
            'El acreedor original debe recibir el aviso de traspaso')

    def test_api_informa_cuando_el_companero_cubre_ese_dia(self):
        """
        El día que el compañero trabaja CUBRIENDO a un tercero sirve igual como fecha de pago,
        pero el formulario lo señala: hay un tercero implicado y el día cambia de manos. La API
        expone `propio` (¿es su día?) y `cobertura` (¿a quién cubre?) para poder decirlo.
        """
        self._aprobar_y_aplicar()  # el receptor pasa a cubrir `self.ces`
        self.client.force_login(self.u_sol)
        r = self.client.get('/solicitudes/alternancia-mes/',
                            {'anio': self.ces.year, 'mes': self.ces.month,
                             'receptor_id': self.receptor.id})
        self.assertEqual(r.status_code, 200)
        data = r.json().get('data', r.json())
        clave = 'sabado' if self.ces.weekday() == 5 else 'domingo'
        finde = next(f for f in data['findes'] if f[clave]['fecha'] == self.ces.isoformat())
        rec = finde['receptor']
        self.assertTrue(rec[f'{clave}_mio'], 'El compañero sí trabaja ese día...')
        self.assertFalse(rec[f'{clave}_propio'], '...pero no es SU día: lo cubre por un favor')
        self.assertEqual(rec[f'{clave}_cobertura']['solicitud_id'],
                         SolicitudCambio.objects.filter(estado='aprobada').first().id)

    def test_cadena_de_tres_deudas_independientes(self):
        """
        Sol → Rec → tercero sobre el mismo día: dos deudas separadas, cada una con su fecha de
        pago, y el día lo acaba trabajando el último de la cadena.
        """
        s1 = self._aprobar_y_aplicar()  # Sol cede `ces`; Rec lo cubre
        tercero = self._nuevo_empleado('cadena.fds', '1010', self.am)
        pago_rec = self._dia_devolucion(self.receptor, tercero, self.ces)
        if not pago_rec:
            self.skipTest('El mes de prueba no ofrece devolución para el segundo eslabón')

        s2 = self._aprobar_y_aplicar(self._datos(
            explorador_solicitante=self.receptor, explorador_receptor=tercero,
            fecha_cambio_turno=self.ces.strftime('%Y-%m-%d'),
            fecha_pago=pago_rec.strftime('%Y-%m-%d'),
        ))

        # El día lo trabaja el ÚLTIMO de la cadena.
        jornadas = sorted(t.jornada.nombre.upper() for t in
                          Turno.objects.filter(explorador=tercero, fecha=self.ces)
                          .select_related('jornada'))
        self.assertEqual(jornadas, ['AM', 'PM'])
        # Dos deudas independientes: Sol→Rec y Rec→tercero. Nadie hereda la del otro.
        d1 = DeudaExplorador.objects.get(solicitud_origen=s1)
        d2 = DeudaExplorador.objects.get(solicitud_origen=s2)
        self.assertEqual((d1.deudor_id, d1.acreedor_id), (self.solicitante.id, self.receptor.id))
        self.assertEqual((d2.deudor_id, d2.acreedor_id), (self.receptor.id, tercero.id))

    def test_guardia_lifo_impide_deshacer_el_eslabon_intermedio(self):
        """La cadena solo se deshace en orden inverso; eso es lo que la mantiene consistente."""
        from solicitudes.use_cases.cancelar_solicitud import CancelarSolicitudUseCase
        from solicitudes.tests.helpers_cancelacion import cancelar_con_acuerdo

        s1 = self._aprobar_y_aplicar()
        tercero = self._nuevo_empleado('lifo.fds', '1111', self.am)
        pago_rec = self._dia_devolucion(self.receptor, tercero, self.ces)
        if not pago_rec:
            self.skipTest('El mes de prueba no ofrece devolución para el segundo eslabón')
        self._aprobar_y_aplicar(self._datos(
            explorador_solicitante=self.receptor, explorador_receptor=tercero,
            fecha_cambio_turno=self.ces.strftime('%Y-%m-%d'),
            fecha_pago=pago_rec.strftime('%Y-%m-%d'),
        ))

        ok, msg = cancelar_con_acuerdo(s1, self.solicitante)
        self.assertFalse(ok, 'No debe poder cancelarse el eslabón anterior de la cadena')
        self.assertIn('más reciente', msg)
