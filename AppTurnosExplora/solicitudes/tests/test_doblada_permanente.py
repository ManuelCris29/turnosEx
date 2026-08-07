"""
Tests de DOBLADA PERMANENTE.

Acuerdo recurrente dentro de un rango del mismo mes: el compañero cubre los días de cesión
(él dobla AM+PM, el solicitante descansa) y el solicitante devuelve el favor en los días de
devolución (él dobla, el compañero descansa). Cada doblada efectiva son 30 min de deuda
corporativa para quien dobla.

El formulario permite VARIOS compañeros: el orquestador agrupa por compañero y crea una
solicitud independiente por cada uno, todo o nada.

Las fechas se calculan dinámicamente (nunca hardcodeadas en el pasado).
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.http import QueryDict
from django.test import TestCase
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from solicitudes.models import (
    SolicitudCambio, TipoSolicitudCambio, DobladaPermanenteDetalle, DeudaCorporativa,
    DeudaExplorador,
)
from solicitudes.services.strategies.doblada_permanente_strategy import DobladaPermanenteStrategy
from turnos.models import Turno, AsignarJornadaExplorador, Sala


def _dia_semana_futuro(weekday, desde=None, saltar=0):
    """Próxima fecha con ese `weekday` (0=lun) a partir de `desde` (por defecto, dentro de 2 meses)."""
    d = desde or (timezone.localdate() + timedelta(days=60))
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d + timedelta(days=7 * saltar)


def _lunes_con_holgura():
    """
    Lunes futuro en los primeros 14 días de su mes.

    El rango de una doblada permanente debe caber en UN mes, y varias pruebas necesitan lunes,
    martes, miércoles, jueves y el martes de la semana siguiente. Con día ≤ 14 todo eso cae en el
    mismo mes sin depender de qué día se ejecute la suite.
    """
    d = timezone.localdate() + timedelta(days=45)
    while d.weekday() != 0 or d.day > 14:
        d += timedelta(days=1)
    return d


class DobladaPermanenteBaseTest(TestCase):
    def setUp(self):
        self.tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala DP', activo=True)

        self.solicitante = self._empleado('sol.dp', '111', self.pm)
        self.receptor = self._empleado('rec.dp', '222', self.am)

        self.strat = DobladaPermanenteStrategy()

        # Lunes de cesión y martes de devolución, siempre futuros y del mismo mes.
        self.lunes = _lunes_con_holgura()
        self.martes = self.lunes + timedelta(days=1)
        self.fi, self.ff = self.lunes, self.martes

    def _empleado(self, username, cedula, jornada):
        u = User.objects.create_user(username=username, password='x')
        e = Empleado.objects.create(user=u, nombre=username.split('.')[0], apellido='Test',
                                    cedula=cedula, activo=True)
        AsignarJornadaExplorador.objects.create(explorador=e, jornada=jornada,
                                                fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
        return e

    def _datos(self, **over):
        d = {
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'tipo_cambio': self.tipo,
            'comentario': 'Prueba doblada permanente',
            'fecha_inicio': self.fi.strftime('%Y-%m-%d'),
            'fecha_fin': self.ff.strftime('%Y-%m-%d'),
            'dias_cesion': [self.lunes.weekday()],
            'dias_devolucion': [self.martes.weekday()],
            'fechas_cesion': [self.lunes.strftime('%Y-%m-%d')],
            'fechas_devolucion': [self.martes.strftime('%Y-%m-%d')],
            'fecha_creacion_solicitud': timezone.localdate(),
        }
        d.update(over)
        return d

    def _crear(self, datos=None):
        sol, msg = self.strat.crear_solicitud(datos or self._datos())
        self.assertIsNotNone(sol, msg)
        return SolicitudCambio.objects.select_related(
            'doblada_permanente', 'explorador_solicitante', 'explorador_receptor').get(id=sol.id)

    def _aprobar_y_aplicar(self, datos=None):
        sol = self._crear(datos)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        ok, msg = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        return sol

    def _jornadas(self, emp, fecha):
        return sorted(t.jornada.nombre.upper() for t in
                      Turno.objects.filter(explorador=emp, fecha=fecha).select_related('jornada'))


class DobladaPermanenteValidacionTest(DobladaPermanenteBaseTest):

    def test_caso_valido(self):
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertTrue(ok, msg)

    def test_mismo_empleado_rechazado(self):
        ok, _ = self.strat.validar_solicitud(self._datos(explorador_receptor=self.solicitante))
        self.assertFalse(ok)

    def test_comentario_obligatorio(self):
        ok, msg = self.strat.validar_solicitud(self._datos(comentario=''))
        self.assertFalse(ok)
        self.assertIn('comentario', msg.lower())

    def test_fin_de_semana_rechazado(self):
        sabado = _dia_semana_futuro(5, desde=self.fi)
        ok, msg = self.strat.validar_solicitud(self._datos(
            dias_cesion=[5], fechas_cesion=[sabado.strftime('%Y-%m-%d')],
            fecha_fin=sabado.strftime('%Y-%m-%d')))
        self.assertFalse(ok)
        self.assertIn('lunes a viernes', msg)

    def test_mismo_dia_cesion_y_devolucion_rechazado(self):
        ok, msg = self.strat.validar_solicitud(self._datos(
            dias_devolucion=[self.lunes.weekday()],
            fechas_devolucion=[self.lunes.strftime('%Y-%m-%d')]))
        self.assertFalse(ok)
        self.assertIn('no puede ser de cesión y de devolución', msg)

    def test_balance_desigual_rechazado(self):
        otro_martes = self.martes + timedelta(days=7)
        ok, msg = self.strat.validar_solicitud(self._datos(
            fecha_fin=otro_martes.strftime('%Y-%m-%d'),
            fechas_devolucion=[self.martes.strftime('%Y-%m-%d'),
                               otro_martes.strftime('%Y-%m-%d')]))
        self.assertFalse(ok)
        self.assertIn('misma cantidad', msg)

    def test_rango_de_meses_distintos_rechazado(self):
        fin_otro_mes = self.ff
        while fin_otro_mes.month == self.fi.month:
            fin_otro_mes += timedelta(days=1)
        ok, msg = self.strat.validar_solicitud(self._datos(
            fecha_fin=fin_otro_mes.strftime('%Y-%m-%d')))
        self.assertFalse(ok)
        self.assertIn('mismo mes', msg)

    def test_rango_en_el_pasado_rechazado(self):
        ayer = timezone.localdate() - timedelta(days=1)
        ok, msg = self.strat.validar_solicitud(self._datos(
            fecha_inicio=ayer.strftime('%Y-%m-%d')))
        self.assertFalse(ok)
        self.assertIn('pasado', msg.lower())

    def test_mismas_jornadas_rechazado(self):
        """Sin jornadas contrarias no hay a quién cubrir: no quedan días válidos."""
        gemelo = self._empleado('gemelo.dp', '333', self.pm)   # misma jornada que el solicitante
        ok, msg = self.strat.validar_solicitud(self._datos(explorador_receptor=gemelo))
        self.assertFalse(ok)
        self.assertIn('CONTRARIAS', msg)


class DobladaPermanentePendientesTest(DobladaPermanenteBaseTest):
    """
    Antes solo se cruzaba `fecha_inicio` y solo del solicitante: una pendiente sobre cualquier
    otro día del rango —o cualquiera del compañero— pasaba desapercibida y podía aprobarse en
    paralelo sobre el mismo día.
    """

    def _pendiente_de(self, empleado, fecha, como_receptor=False):
        tipo_ct = TipoSolicitudCambio.objects.create(nombre=f'CT {empleado.id}{fecha}')
        otro = self._empleado(f'otro{empleado.id}{fecha.day}', f'9{empleado.id}{fecha.day}', self.am)
        return SolicitudCambio.objects.create(
            explorador_solicitante=otro if como_receptor else empleado,
            explorador_receptor=empleado if como_receptor else otro,
            tipo_cambio=tipo_ct, comentario='pendiente', fecha_cambio_turno=fecha,
            estado='pendiente')

    def test_pendiente_del_solicitante_en_dia_de_devolucion_bloquea(self):
        # El día de DEVOLUCIÓN no es el inicio del rango: con la regla vieja no se miraba.
        self._pendiente_de(self.solicitante, self.martes)
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertFalse(ok, 'Una pendiente sobre un día afectado debe bloquear')
        self.assertIn('pendiente', msg.lower())

    def test_pendiente_del_receptor_bloquea(self):
        self._pendiente_de(self.receptor, self.lunes, como_receptor=True)
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertFalse(ok, 'Una pendiente del compañero también debe bloquear')
        self.assertIn('compañero', msg.lower())

    def test_pendiente_fuera_del_rango_no_estorba(self):
        fuera = self.ff + timedelta(days=30)
        self._pendiente_de(self.solicitante, fuera)
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertTrue(ok, f'Una pendiente que no toca el acuerdo no debe bloquear: {msg}')

    def test_al_revalidar_para_aprobar_no_estorban_las_pendientes(self):
        """Es una regla de CREACIÓN: al aprobar, la propia solicitud ya existe."""
        sol = self._crear()
        self._pendiente_de(self.solicitante, self.martes)
        ok, msg = self.strat.revalidar_para_aprobar(sol)
        self.assertTrue(ok, msg)


class DobladaPermanenteOtroAcuerdoTest(DobladaPermanenteBaseTest):
    """
    Regla 9: el compañero no puede estar comprometido en otra doblada permanente.

    El choque se mide por FECHA. Antes se comparaban días de la SEMANA, así que dos acuerdos que
    usaban el mismo weekday dentro de rangos solapados se rechazaban aunque no compartieran ni una
    fecha (p. ej. uno los miércoles 9 y 16, otro los miércoles 2, 23 y 30).
    """

    def _acuerdo_del_receptor(self, fechas_cesion, fecha_inicio=None, fecha_fin=None, dias=None):
        """Otra doblada permanente APROBADA en la que el receptor es el compañero."""
        tercero = self._empleado('tercero.dp', '333', self.pm)
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=tercero, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo, comentario='otro acuerdo', estado='aprobada')
        DobladaPermanenteDetalle.objects.create(
            solicitud=sol,
            fecha_inicio=fecha_inicio or self.fi,
            fecha_fin=fecha_fin or (self.ff + timedelta(days=14)),
            dias_cesion=str(self.lunes.weekday()) if dias is None else dias,
            dias_devolucion='',
            fechas_cesion=','.join(f.strftime('%Y-%m-%d') for f in fechas_cesion),
            fechas_devolucion='',
        )
        return sol

    def test_mismo_weekday_en_fechas_distintas_no_bloquea(self):
        # El otro acuerdo usa el lunes de la semana siguiente; este usa el lunes de esta.
        self._acuerdo_del_receptor([self.lunes + timedelta(days=7)])
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertTrue(ok, f'Sin fechas en común no debe bloquear: {msg}')

    def test_misma_fecha_bloquea_y_la_nombra(self):
        self._acuerdo_del_receptor([self.lunes])
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertFalse(ok, 'Una fecha compartida sí debe bloquear')
        self.assertIn(self.lunes.strftime('%d/%m/%Y'), msg)

    def test_choque_contra_el_lado_de_devolucion_del_otro(self):
        """En una fecha comprometida da igual el rol: el compañero ya no está disponible."""
        tercero = self._empleado('tercero2.dp', '444', self.pm)
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=tercero, explorador_receptor=self.receptor,
            tipo_cambio=self.tipo, comentario='otro acuerdo', estado='pendiente')
        DobladaPermanenteDetalle.objects.create(
            solicitud=sol, fecha_inicio=self.fi, fecha_fin=self.ff + timedelta(days=14),
            dias_cesion='', dias_devolucion=str(self.martes.weekday()),
            fechas_cesion='', fechas_devolucion=self.martes.strftime('%Y-%m-%d'))
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertFalse(ok, msg)
        self.assertIn(self.martes.strftime('%d/%m/%Y'), msg)

    def test_acuerdo_legacy_sin_fechas_sigue_bloqueando_por_weekday(self):
        # Acuerdos anteriores a `fechas_cesion`: sus fechas reales son las ocurrencias del weekday.
        self._acuerdo_del_receptor([])
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertFalse(ok, 'Un acuerdo legacy que cubre ese lunes debe bloquear')

    def test_acuerdo_legacy_con_otro_weekday_no_estorba(self):
        self._acuerdo_del_receptor([], dias=str(self.martes.weekday() + 1))
        ok, msg = self.strat.validar_solicitud(self._datos())
        self.assertTrue(ok, f'Otro weekday del legacy no toca este acuerdo: {msg}')

    def test_al_revalidar_no_choca_consigo_misma(self):
        sol = self._crear()
        ok, msg = self.strat.revalidar_para_aprobar(sol)
        self.assertTrue(ok, msg)


class DobladaPermanenteAplicacionTest(DobladaPermanenteBaseTest):

    def test_aplicacion_turnos_y_deudas(self):
        sol = self._aprobar_y_aplicar()
        # Cesión: el receptor dobla, el solicitante descansa.
        self.assertEqual(self._jornadas(self.receptor, self.lunes), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.solicitante, self.lunes), [])
        # Devolución: el solicitante dobla, el receptor descansa.
        self.assertEqual(self._jornadas(self.solicitante, self.martes), ['AM', 'PM'])
        self.assertEqual(self._jornadas(self.receptor, self.martes), [])
        # 30 min por cada doblada efectiva, uno por lado.
        deudas = DeudaCorporativa.objects.filter(solicitud_origen=sol)
        self.assertEqual(deudas.count(), 2)
        self.assertEqual({d.explorador_id for d in deudas},
                         {self.solicitante.id, self.receptor.id})
        self.assertTrue(all(d.minutos == 30 for d in deudas))

    def test_aplicar_dos_veces_no_duplica_deudas(self):
        sol = self._aprobar_y_aplicar()
        ok, msg = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        self.assertEqual(DeudaCorporativa.objects.filter(solicitud_origen=sol).count(), 2)

    def test_revertir_restaura_y_cancela_deudas(self):
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService,
        )
        sol = self._aprobar_y_aplicar()
        DobladaPermanenteAplicacionService.revertir(sol)
        self.assertEqual(self._jornadas(self.receptor, self.lunes), [])
        self.assertEqual(self._jornadas(self.solicitante, self.martes), [])
        self.assertFalse(
            DeudaCorporativa.objects.filter(solicitud_origen=sol).exclude(estado='cancelada').exists())

    def test_snapshot_no_se_pisa_al_reaplicar(self):
        """Una segunda aplicación no puede grabar el estado YA aplicado como 'previo'."""
        sol = self._aprobar_y_aplicar()
        snap1 = sol.doblada_permanente.snapshot_turnos_previos
        self.strat.aplicar_cambios(sol)
        sol.doblada_permanente.refresh_from_db()
        self.assertEqual(sol.doblada_permanente.snapshot_turnos_previos, snap1)


class DobladaPermanenteFavoresTest(DobladaPermanenteBaseTest):
    """
    El favor ENTRE EXPLORADORES (`DeudaExplorador`), que es lo que alimenta "Mis Favores".

    Antes solo se registraban los 30 min corporativos, así que quien pactaba una permanente de
    tres meses veía la pantalla vacía aunque su compañero le hubiera cubierto doce días.
    """

    def test_registra_un_favor_por_par_cesion_devolucion(self):
        sol = self._aprobar_y_aplicar()
        favores = DeudaExplorador.objects.filter(solicitud_origen=sol)
        self.assertEqual(favores.count(), 1)          # un solo par en este escenario

        favor = favores.get()
        # El solicitante cedió su jornada del lunes; el receptor la cubrió doblando.
        self.assertEqual(favor.deudor_id, self.solicitante.id)
        self.assertEqual(favor.acreedor_id, self.receptor.id)
        # La devolución (martes) se aplica en el mismo acto: nace saldado, como la doblada suelta.
        self.assertEqual(favor.fecha_pago_pactada, self.martes)
        self.assertEqual(favor.fecha_pago_real, self.martes)
        self.assertEqual(favor.estado, 'pagada')
        self.assertTrue(favor.media_jornada)
        # El solicitante es PM: esa es la jornada que cede.
        self.assertEqual(favor.jornada_cedida, 'PM')

    def test_un_favor_por_cada_par_cuando_hay_varios(self):
        lunes2 = self.lunes + timedelta(days=7)
        martes2 = self.martes + timedelta(days=7)
        sol = self._aprobar_y_aplicar(self._datos(
            fecha_fin=martes2.strftime('%Y-%m-%d'),
            fechas_cesion=[self.lunes.strftime('%Y-%m-%d'), lunes2.strftime('%Y-%m-%d')],
            fechas_devolucion=[self.martes.strftime('%Y-%m-%d'), martes2.strftime('%Y-%m-%d')]))

        favores = DeudaExplorador.objects.filter(solicitud_origen=sol)
        self.assertEqual(favores.count(), 2)
        # Cada par se salda en SU día de devolución, no todos en el mismo.
        self.assertEqual(sorted(f.fecha_pago_pactada for f in favores), [self.martes, martes2])

    def test_aplicar_dos_veces_no_duplica_los_favores(self):
        """Cada par tiene fecha de devolución distinta, así que la clave idempotente los separa."""
        sol = self._aprobar_y_aplicar()
        ok, msg = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, msg)
        self.assertEqual(DeudaExplorador.objects.filter(solicitud_origen=sol).count(), 1)

    def test_revertir_cancela_los_favores(self):
        """Un acuerdo deshecho no puede seguir figurando como favor en Mis Favores."""
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService,
        )
        sol = self._aprobar_y_aplicar()
        DobladaPermanenteAplicacionService.revertir(sol)
        self.assertFalse(
            DeudaExplorador.objects.filter(solicitud_origen=sol)
            .exclude(estado='cancelada').exists())

    def test_el_favor_sale_en_mis_favores(self):
        """La prueba de que llega a la pantalla: es el punto de todo el cambio."""
        self._aprobar_y_aplicar()

        self.client.force_login(self.solicitante.user)
        r = self.client.get('/solicitudes/mis-favores/')
        recibidos = r.context['recibidos']
        self.assertEqual(len(recibidos), 1)
        self.assertEqual(recibidos[0]['companero'].id, self.receptor.id)
        self.assertEqual(recibidos[0]['fecha_cubierta'], self.lunes)
        self.assertEqual(recibidos[0]['tipo'], 'DOBLADA PERMANENTE')

        # Y al compañero le aparece como favor HECHO, no recibido.
        self.client.force_login(self.receptor.user)
        r2 = self.client.get('/solicitudes/mis-favores/')
        self.assertEqual(len(r2.context['recibidos']), 0)
        self.assertEqual(len(r2.context['hechos']), 1)
        self.assertEqual(r2.context['hechos'][0]['fecha_cubierta'], self.lunes)


class DobladaPermanenteMultiCompaneroTest(DobladaPermanenteBaseTest):
    """Flujo del orquestador: varios compañeros → una solicitud por cada uno, todo o nada."""

    def setUp(self):
        super().setUp()
        from solicitudes.services.solicitud_orchestrator import SolicitudOrchestrator
        self.orch = SolicitudOrchestrator
        self.receptor2 = self._empleado('rec2.dp', '444', self.am)
        self.miercoles = self.lunes + timedelta(days=2)
        self.jueves = self.lunes + timedelta(days=3)

    def _post(self, pares_cesion, pares_devolucion, **extra):
        """pares_* = [(fecha, compañero_id)]."""
        q = QueryDict(mutable=True)
        q['comentarios'] = 'Prueba multi'
        q['fecha_inicio'] = self.fi.strftime('%Y-%m-%d')
        q['fecha_fin'] = (self.jueves).strftime('%Y-%m-%d')
        for f, c in pares_cesion:
            q.appendlist('cesion_fecha', f.strftime('%Y-%m-%d'))
            q.appendlist('cesion_fecha_companero', str(c))
        for f, c in pares_devolucion:
            q.appendlist('devolucion_fecha', f.strftime('%Y-%m-%d'))
            q.appendlist('devolucion_fecha_companero', str(c))
        for k, v in extra.items():
            q[k] = v
        return q

    def _procesar(self, post):
        return self.orch._procesar_doblada_permanente_multi(
            post, self.tipo, self.solicitante, post.get('comentarios'))

    @staticmethod
    def _error(resp):
        """Mensaje de error ya decodificado (en el content los acentos van escapados)."""
        import json
        return json.loads(resp.content.decode()).get('error', '')

    def test_una_solicitud_por_companero(self):
        post = self._post(
            [(self.lunes, self.receptor.id), (self.miercoles, self.receptor2.id)],
            [(self.martes, self.receptor.id), (self.jueves, self.receptor2.id)])
        resp = self._procesar(post)
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(SolicitudCambio.objects.filter(tipo_cambio=self.tipo).count(), 2)

    def test_misma_fecha_como_cesion_y_devolucion_de_otro_rechazada(self):
        """
        Ese día no se puede descansar (te cubre uno) y doblar (le pagas al otro) a la vez. Cada
        solicitud se valida por separado, así que el cruce entre compañeros hay que verlo en el
        orquestador; antes solo lo frenaba el formulario.
        """
        post = self._post(
            [(self.lunes, self.receptor.id), (self.miercoles, self.receptor2.id)],
            [(self.martes, self.receptor.id), (self.lunes, self.receptor2.id)])
        resp = self._procesar(post)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('cedes y como día que devuelves', self._error(resp))
        self.assertEqual(SolicitudCambio.objects.filter(tipo_cambio=self.tipo).count(), 0)

    def test_misma_fecha_a_dos_companeros_rechazada(self):
        post = self._post(
            [(self.lunes, self.receptor.id), (self.lunes, self.receptor2.id)],
            [(self.martes, self.receptor.id), (self.jueves, self.receptor2.id)])
        resp = self._procesar(post)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('dos compañeros', self._error(resp))

    def test_balance_por_companero(self):
        post = self._post(
            [(self.lunes, self.receptor.id), (self.miercoles, self.receptor2.id)],
            [(self.martes, self.receptor.id)])          # al 2º no se le devuelve nada
        resp = self._procesar(post)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('misma cantidad', self._error(resp))

    def test_creacion_es_todo_o_nada(self):
        """Si la segunda creación falla, la primera no puede quedarse viva."""
        from unittest.mock import patch
        from solicitudes.services.solicitud_factory import SolicitudFactory

        real = SolicitudFactory.crear_solicitud
        llamadas = {'n': 0}

        def _falla_la_segunda(tipo, datos):
            llamadas['n'] += 1
            if llamadas['n'] == 2:
                return None, 'fallo simulado'
            return real(tipo, datos)

        post = self._post(
            [(self.lunes, self.receptor.id), (self.miercoles, self.receptor2.id)],
            [(self.martes, self.receptor.id), (self.jueves, self.receptor2.id)])
        with patch.object(SolicitudFactory, 'crear_solicitud', side_effect=_falla_la_segunda):
            resp = self._procesar(post)

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            SolicitudCambio.objects.filter(tipo_cambio=self.tipo).count(), 0,
            'La primera solicitud debió deshacerse con el rollback')
        self.assertEqual(DobladaPermanenteDetalle.objects.count(), 0)


class DobladaPermanenteNoCubreTest(DobladaPermanenteBaseTest):
    """
    El endpoint de disponibilidad debe decir POR QUÉ un compañero no cubre una fecha.

    Sin esto el formulario adivinaba la causa desde la jornada del solicitante y siempre
    concluía "necesitas un compañero de la jornada contraria", consejo FALSO cuando el
    compañero sí es contrario pero ese día ya está doblado o descansa por otro acuerdo.
    """

    URL = '/solicitudes/dias-disponibles-doblada-permanente/'

    def setUp(self):
        super().setUp()
        # Rango de 3 lunes: el compañero cubre el 1º, ya está doblado el 2º y no trabaja el 3º.
        self.l1 = self.lunes
        self.l2 = self.lunes + timedelta(days=7)
        self.l3 = self.lunes + timedelta(days=14)
        self.client.force_login(self.solicitante.user)

    def _pedir(self, fi, ff):
        import json
        resp = self.client.get(self.URL, {
            'fecha_inicio': fi.strftime('%Y-%m-%d'),
            'fecha_fin': ff.strftime('%Y-%m-%d'),
            'pares': json.dumps([{'dia': 0, 'comp': str(self.receptor.id)}]),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        d = d.get('data', d)
        clave = f'0|{self.receptor.id}'
        return d['por_par'][clave], d['no_cubre'][clave]

    def test_companero_ya_doblado_se_reporta_como_no_disponible(self):
        """Doblada real del compañero: no es un problema de jornada, es que ya dobla."""
        Turno.objects.create(explorador=self.receptor, fecha=self.l2, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.receptor, fecha=self.l2, jornada=self.pm, sala=self.sala)

        cubre, no_cubre = self._pedir(self.l1, self.l2)

        self.assertEqual([x['f'] for x in cubre], [self.l1.strftime('%Y-%m-%d')])
        self.assertEqual(len(no_cubre), 1)
        self.assertEqual(no_cubre[0]['f'], self.l2.strftime('%Y-%m-%d'))
        self.assertEqual(no_cubre[0]['tipo'], 'no_disponible')
        self.assertIn('doblada', no_cubre[0]['razon'].lower())

    def test_misma_jornada_se_distingue_de_no_disponible(self):
        """Ese sí se arregla eligiendo otro compañero: el tipo debe permitir distinguirlo."""
        otro = self._empleado('igual.dp', '333', self.pm)  # misma jornada que el solicitante
        import json
        resp = self.client.get(self.URL, {
            'fecha_inicio': self.l1.strftime('%Y-%m-%d'),
            'fecha_fin': self.l1.strftime('%Y-%m-%d'),
            'pares': json.dumps([{'dia': 0, 'comp': str(otro.id)}]),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        d = resp.json()
        d = d.get('data', d)
        no_cubre = d['no_cubre'][f'0|{otro.id}']

        self.assertEqual(len(no_cubre), 1)
        self.assertEqual(no_cubre[0]['tipo'], 'misma_jornada')
        self.assertEqual(no_cubre[0]['ys'], 'PM')

    def test_fechas_cubiertas_y_no_cubiertas_suman_las_del_solicitante(self):
        """Ninguna fecha válida del solicitante puede desaparecer sin explicación."""
        Turno.objects.create(explorador=self.receptor, fecha=self.l2, jornada=self.am, sala=self.sala)
        Turno.objects.create(explorador=self.receptor, fecha=self.l2, jornada=self.pm, sala=self.sala)

        import json
        resp = self.client.get(self.URL, {
            'fecha_inicio': self.l1.strftime('%Y-%m-%d'),
            'fecha_fin': self.l3.strftime('%Y-%m-%d'),
            'pares': json.dumps([{'dia': 0, 'comp': str(self.receptor.id)}]),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        d = resp.json()
        d = d.get('data', d)
        clave = f'0|{self.receptor.id}'
        mis_lunes = {x['f'] for x in d['por_dia']['0']}
        cubiertas = {x['f'] for x in d['por_par'][clave]}
        sin_cubrir = {x['f'] for x in d['no_cubre'][clave]}

        self.assertEqual(cubiertas | sin_cubrir, mis_lunes)
        self.assertFalse(cubiertas & sin_cubrir, 'Una fecha no puede estar en ambos lados')


class DobladaPermanenteDiasCalendarioTest(DobladaPermanenteBaseTest):
    """
    Temporada, festivo y mantenimiento NO son doblables, y el endpoint debe filtrarlos por REGLA.

    Antes solo se miraba `estado_dia`, y la capa de temporada únicamente altera el estado de quien
    descansa o dobla por temporada: a quien conservaba su jornada, un día de temporada le llegaba
    como 'base' AM/PM y se ofrecía como día disponible. Lo tapaba el calendario del formulario
    (que deshabilita esos días), una defensa de una sola capa que no cubre el POST directo.
    """

    URL = '/solicitudes/dias-disponibles-doblada-permanente/'

    def setUp(self):
        super().setUp()
        self.l1 = self.lunes
        self.l2 = self.lunes + timedelta(days=7)
        self.client.force_login(self.solicitante.user)

    def _lunes_disponibles(self, fi, ff):
        resp = self.client.get(self.URL, {
            'fecha_inicio': fi.strftime('%Y-%m-%d'),
            'fecha_fin': ff.strftime('%Y-%m-%d'),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)
        d = resp.json()
        d = d.get('data', d)
        return d, {x['f'] for x in d['por_dia']['0']}

    def test_dia_de_temporada_no_es_doblable(self):
        from turnos.models import DiaEspecial
        _, antes = self._lunes_disponibles(self.l1, self.l2)
        self.assertIn(self.l2.strftime('%Y-%m-%d'), antes)

        DiaEspecial.objects.create(fecha=self.l2, tipo='temporada', es_temporada=True, activo=True)

        _, despues = self._lunes_disponibles(self.l1, self.l2)
        self.assertNotIn(self.l2.strftime('%Y-%m-%d'), despues,
                         'un lunes de temporada no puede ofrecerse como día doblable')
        self.assertIn(self.l1.strftime('%Y-%m-%d'), despues, 'el resto del rango no se toca')

    def test_preview_explica_la_temporada(self):
        """La fecha omitida debe llevar su motivo real, no 'descansas o no tienes turno'."""
        from turnos.models import DiaEspecial
        DiaEspecial.objects.create(fecha=self.l2, tipo='temporada', es_temporada=True, activo=True)

        resp = self.client.get('/solicitudes/previsualizar-doblada-permanente/', {
            'fecha_inicio': self.l1.strftime('%Y-%m-%d'),
            'fecha_fin': self.l2.strftime('%Y-%m-%d'),
            'dias': '0',
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        d = resp.json()
        d = d.get('data', d)

        excluidas = {e['fecha']: e['razon'] for e in d['excluidas']}
        self.assertEqual(excluidas.get(self.l2.strftime('%Y-%m-%d')), 'Descanso de temporada')

    def test_rango_avisa_cuando_lo_corta_la_temporada(self):
        """
        El calendario deshabilita la temporada, así que el 'Hasta' se corta solo y en silencio:
        quien creía pedir un rango largo veía la mitad de los días sin saber por qué.
        """
        from turnos.models import DiaEspecial
        inicio_temporada = self.l1 + timedelta(days=1)
        for n in range(3):
            DiaEspecial.objects.create(fecha=inicio_temporada + timedelta(days=n),
                                       tipo='temporada', es_temporada=True, activo=True)

        d, _ = self._lunes_disponibles(self.l1, self.l1)

        self.assertEqual(d['rango']['fin'], self.l1.strftime('%Y-%m-%d'))
        corte = d['rango']['corte']
        self.assertIsNotNone(corte, 'el rango termina pegado a la temporada: hay que decirlo')
        self.assertEqual(corte['tipo'], 'temporada')
        self.assertEqual(corte['desde'], inicio_temporada.strftime('%Y-%m-%d'))
        self.assertEqual(corte['hasta'], (inicio_temporada + timedelta(days=2)).strftime('%Y-%m-%d'))

    def test_sin_corte_no_se_inventa_aviso(self):
        d, _ = self._lunes_disponibles(self.l1, self.l1)
        self.assertIsNone(d['rango']['corte'])


class DobladaPermanenteRendimientoTest(DobladaPermanenteBaseTest):
    """
    El coste de estas consultas NO puede crecer con el tamaño del rango ni con el de la plantilla.

    El formulario dispara la disponibilidad cada vez que se mueve el "Hasta", y el desplegable de
    compañeros barre a TODOS los exploradores. Ambos caminos habían degenerado en N+1: el aviso de
    corte recorría el tramo bloqueado día a día (~3 consultas por día) y los candidatos se
    resolvían de uno en uno (~1,8 consultas por empleado, ~730 con 400 exploradores).
    """

    URL = '/solicitudes/dias-disponibles-doblada-permanente/'

    def setUp(self):
        super().setUp()
        self.client.force_login(self.solicitante.user)

    def _consultas_rango(self, fi, ff):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as cap:
            self.client.get(self.URL, {
                'fecha_inicio': fi.strftime('%Y-%m-%d'),
                'fecha_fin': ff.strftime('%Y-%m-%d'),
            }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        return len(cap)

    def test_rango_largo_no_cuesta_mas_que_uno_corto(self):
        corto = self._consultas_rango(self.lunes, self.lunes + timedelta(days=7))
        largo = self._consultas_rango(self.lunes, self.lunes + timedelta(days=300))
        self.assertEqual(corto, largo,
                         'la disponibilidad debe costar un número CONSTANTE de consultas')

    def test_el_aviso_de_corte_cuesta_una_sola_consulta(self):
        """Un tramo bloqueado largo no puede pagarse día a día."""
        from turnos.models import DiaEspecial
        sin_bloque = self._consultas_rango(self.lunes, self.lunes + timedelta(days=7))

        arranque = self.lunes + timedelta(days=8)
        for n in range(40):
            DiaEspecial.objects.create(fecha=arranque + timedelta(days=n),
                                       tipo='temporada', es_temporada=True, activo=True)
        con_bloque = self._consultas_rango(self.lunes, self.lunes + timedelta(days=7))
        self.assertEqual(sin_bloque, con_bloque,
                         'escanear 40 días bloqueados debe seguir siendo una sola consulta')

    def test_candidatos_en_lote_coinciden_con_el_camino_individual(self):
        """La versión batch es SOLO una optimización: mismo veredicto que la individual."""
        from solicitudes.services.ct_permanente_helper import (
            _jornada_unica_real, jornadas_unicas_reales,
        )
        emps = list(Empleado.objects.filter(activo=True))
        for n in (0, 1, 2, 30):
            f = self.lunes + timedelta(days=n)
            lote = jornadas_unicas_reales(emps, f)
            for e in emps:
                self.assertEqual(lote.get(e.id), _jornada_unica_real(e, f),
                                 f'divergencia para {e.id} el {f}')

    def test_candidatos_en_lote_usan_consultas_constantes(self):
        from solicitudes.services.ct_permanente_helper import jornadas_unicas_reales
        emps = list(Empleado.objects.filter(activo=True))
        with self.assertNumQueries(2):
            jornadas_unicas_reales(emps, self.lunes)
