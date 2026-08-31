"""
Test de integración: verifica que al APROBAR/aplicar cada tipo de solicitud,
el cambio se refleja en la API de "Mis Turnos" (/turnos/api/mis-turnos-por-mes/).

Cubre los 6 tipos de solicitud —CT sencillo, Doblada, D FDS, CT Permanente, Doblada
Permanente y Cambio de Descanso (en sus DOS modalidades: fin de semana y entre semana)—
y los permisos especiales.

Es la unica prueba que recorre el ciclo entero hasta lo que VE el empleado. Afirmar sobre
`AsignarJornadaExplorador` o sobre el estado de la solicitud no basta: el turno puede
aplicarse bien y aun asi el calendario mostrar otra cosa, porque entre la BD y la pantalla
estan la composicion de capas de `MisTurnosPorMesView` y su cache mensual. Cada tipo nuevo
de solicitud necesita su caso AQUI.
Las fechas se calculan dinámicamente (siempre futuras) para no caducar.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from empleados.models import CompetenciaEmpleado, Empleado, Jornada
from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
from solicitudes.services.solicitud_factory import SolicitudFactory
from turnos.models import AsignarJornadaExplorador, Sala
from turnos.services.alternancia_fines_semana_service import AlternanciaFinesSemanaService


class ReflejoMisTurnosTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Test', activo=True)

        # Supervisor
        u_sup = User.objects.create_user(username='sup.test', password='x')
        self.supervisor = Empleado.objects.create(user=u_sup, nombre='Sup', apellido='Test', cedula='900', activo=True,
                                                  email='sup@test.com')
        # Solicitante AM, Receptor PM (jornadas contrarias)
        u_sol = User.objects.create_user(username='sol.test', password='x')
        self.sol = Empleado.objects.create(user=u_sol, nombre='Sol', apellido='AM', cedula='901', activo=True,
                                           email='sol@test.com', supervisor=self.supervisor)
        u_rec = User.objects.create_user(username='rec.test', password='x')
        self.rec = Empleado.objects.create(user=u_rec, nombre='Rec', apellido='PM', cedula='902', activo=True,
                                           email='rec@test.com', supervisor=self.supervisor)

        for emp, jor in ((self.sol, self.am), (self.rec, self.pm)):
            AsignarJornadaExplorador.objects.create(explorador=emp, jornada=jor, fecha_inicio=date(2025, 1, 1))
            # La sala es la especialidad del explorador vía competencia
            CompetenciaEmpleado.objects.create(empleado=emp, sala=self.sala)

        self.tipos = {n: TipoSolicitudCambio.objects.create(nombre=n) for n in
                      ['CAMBIO TURNO', 'DOBLADA', 'D FDS', 'CT PERMANENTE', 'DOBLADA PERMANENTE',
                       'CAMBIO DESCANSO']}

        # La alternancia de findes/festivos es un DATO publicado: sin publicarla, estos
        # días saldrían como 'sin_planificar'. Se publica igual a la fórmula histórica.
        from turnos.tests.alternancia_helpers import publicar_alternancia
        _hoy = timezone.localdate().year
        publicar_alternancia(_hoy, _hoy + 1)

    # ----------------------------------------------------------------- helpers
    def _dia_semana(self, weekday, desde=None):
        d = desde or (timezone.localdate() + timedelta(days=30))
        while d.weekday() != weekday:
            d += timedelta(days=1)
        return d

    def _primer_dia_semana_de_mes_futuro(self, weekday):
        """
        Primera ocurrencia de `weekday` en un mes FUTURO, contando desde el día 1 de ese mes.

        Anclar en el primer lunes del mes (en vez de en el primer lunes tras hoy+30) es lo que hace
        deterministas los escenarios que necesitan varias ocurrencias del mismo día de la semana:
        todo mes tiene 4 lunes como mínimo, así que desde su PRIMER lunes siempre quedan ≥3 lunes y
        ≥2 martes hasta fin de mes. Anclado en hoy+30 el ancla podía caer a final de mes y el test
        se saltaba solo, dejando la regla sin comprobar según el día en que se corriera la suite.
        """
        base = timezone.localdate() + timedelta(days=30)
        anio, mes = (base.year + 1, 1) if base.month == 12 else (base.year, base.month + 1)
        return self._dia_semana(weekday, desde=date(anio, mes, 1))

    def _findes_fds(self):
        """
        (cesion, pago) en un mismo mes futuro y del MISMO día de la semana (regla D FDS:
        si cedes un domingo, devuelves un domingo). cesion: trabaja AM; pago: trabaja PM.
        """
        hoy = timezone.localdate()
        base = hoy + timedelta(days=30)
        for _ in range(6):
            anio, mes = base.year, base.month
            findes = []
            d = date(anio, mes, 1)
            while d.month == mes:
                if d > hoy and d.weekday() in (5, 6):
                    findes.append(d)
                d += timedelta(days=1)
            for wd in (5, 6):
                dias = [f for f in findes if f.weekday() == wd]
                ces = next((f for f in dias if AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(f) == 'AM'), None)
                pago = next((f for f in dias if AlternanciaFinesSemanaService.jornada_trabaja_fin_semana(f) == 'PM' and f != ces), None)
                if ces and pago:
                    return ces, pago
            base = (date(anio, mes, 28) + timedelta(days=7))
        self.fail("No se hallaron fechas de finde para D FDS")

    def _crear_y_aplicar(self, tipo, datos):
        ok, msg = SolicitudFactory.validar_solicitud(tipo, datos)
        self.assertTrue(ok, f"validar falló: {msg}")
        sol, msg = SolicitudFactory.crear_solicitud(tipo, datos)
        self.assertIsNotNone(sol, f"crear falló: {msg}")
        sol = SolicitudCambio.objects.select_related(
            'doblada', 'doblada_permanente', 'cambio_permanente',
            'explorador_solicitante', 'explorador_receptor', 'tipo_cambio'
        ).get(id=sol.id)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        ok, msg = SolicitudFactory.aplicar_cambios(sol)
        self.assertTrue(ok, f"aplicar falló: {msg}")
        return sol

    def _cell(self, empleado, fecha):
        cache.clear()
        self.client.force_login(empleado.user)
        resp = self.client.get('/turnos/api/mis-turnos-por-mes/', {'mes': fecha.month, 'anio': fecha.year})
        self.assertEqual(resp.status_code, 200, resp.content)
        return resp.json().get(fecha.strftime('%Y-%m-%d'), {})

    # ------------------------------------------------------------------- tests
    def test_ct_sencillo_refleja(self):
        f = self._dia_semana(0)  # lunes
        _sol = self._crear_y_aplicar(self.tipos['CAMBIO TURNO'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['CAMBIO TURNO'], 'comentario': 'test',
            'fecha_cambio_turno': f.strftime('%Y-%m-%d'),
        })
        self.assertEqual(self._cell(self.sol, f).get('jornada'), 'PM')   # AM -> PM
        self.assertEqual(self._cell(self.rec, f).get('jornada'), 'AM')   # PM -> AM

    def test_doblada_refleja(self):
        fc = self._dia_semana(0)
        fp = self._dia_semana(2, desde=fc + timedelta(days=1))  # otro día, mismo mes habitualmente
        if fp.month != fc.month:
            fp = self._dia_semana(2, desde=fc.replace(day=1))
        _sol = self._crear_y_aplicar(self.tipos['DOBLADA'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['DOBLADA'], 'comentario': 'test',
            'fecha_cambio_turno': fc.strftime('%Y-%m-%d'), 'fecha_pago': fp.strftime('%Y-%m-%d'),
            'jornada_cedida': 'AM', 'tipo_cesion': 'cesion_completa',
            'fecha_creacion_solicitud': timezone.localdate(),
        })
        self.assertTrue(self._cell(self.sol, fc).get('es_descanso'))   # solicitante descansa en cesión
        self.assertEqual(self._cell(self.rec, fc).get('jornada'), 'DOBLADA')  # receptor dobla en cesión
        self.assertEqual(self._cell(self.sol, fp).get('jornada'), 'DOBLADA')  # solicitante dobla en pago
        self.assertTrue(self._cell(self.rec, fp).get('es_descanso'))   # receptor descansa en pago

    def test_d_fds_refleja(self):
        ces, pago = self._findes_fds()
        _sol = self._crear_y_aplicar(self.tipos['D FDS'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['D FDS'], 'comentario': 'test',
            'fecha_cambio_turno': ces.strftime('%Y-%m-%d'), 'fecha_pago': pago.strftime('%Y-%m-%d'),
            'fecha_creacion_solicitud': timezone.localdate(),
        })
        self.assertTrue(self._cell(self.sol, ces).get('es_descanso'))
        self.assertEqual(self._cell(self.rec, ces).get('jornada'), 'DOBLADA')
        self.assertEqual(self._cell(self.sol, pago).get('jornada'), 'DOBLADA')
        self.assertTrue(self._cell(self.rec, pago).get('es_descanso'))

    def test_ct_permanente_refleja(self):
        fi = self._dia_semana(0)             # lunes
        ff = fi + timedelta(days=10)
        _sol = self._crear_y_aplicar(self.tipos['CT PERMANENTE'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['CT PERMANENTE'], 'comentario': 'test',
            'fecha_inicio': fi.strftime('%Y-%m-%d'), 'fecha_fin': ff.strftime('%Y-%m-%d'),
            'dias_seleccionados': {'dias_semana': [0]},
        })
        self.assertEqual(self._cell(self.sol, fi).get('jornada'), 'PM')  # AM -> PM en el lunes
        self.assertEqual(self._cell(self.rec, fi).get('jornada'), 'AM')

    def test_doblada_permanente_refleja(self):
        import calendar
        fi = self._dia_semana(0)             # lunes (cesión)
        # Si el lunes calculado cae justo el último día del mes, el martes de devolución
        # cruzaría al mes siguiente y quedaría fuera del rango (que se acota al mismo mes
        # de fi más abajo). Se avanza una semana para dejar margen.
        while fi.day == calendar.monthrange(fi.year, fi.month)[1]:
            fi += timedelta(days=7)
        martes = self._dia_semana(1, desde=fi)  # martes (devolución)
        # El rango de la doblada permanente ya puede cruzar meses, pero esta prueba lo acota al
        # mes de fi a propósito: así el lunes y el martes que comprueba caen en un mes cerrado y
        # sus aserciones no dependen de qué día se ejecute la suite.
        ultimo_dia_mes = date(fi.year, fi.month, calendar.monthrange(fi.year, fi.month)[1])
        ff = min(fi + timedelta(days=13), ultimo_dia_mes)
        _sol = self._crear_y_aplicar(self.tipos['DOBLADA PERMANENTE'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['DOBLADA PERMANENTE'], 'comentario': 'test',
            'fecha_inicio': fi.strftime('%Y-%m-%d'), 'fecha_fin': ff.strftime('%Y-%m-%d'),
            'dias_cesion': ['0'], 'dias_devolucion': ['1'],
        })
        # Lunes (cesión): solicitante descansa, receptor dobla
        self.assertTrue(self._cell(self.sol, fi).get('es_descanso'))
        self.assertEqual(self._cell(self.rec, fi).get('jornada'), 'DOBLADA')
        # Martes (devolución): solicitante dobla, receptor descansa
        self.assertEqual(self._cell(self.sol, martes).get('jornada'), 'DOBLADA')
        self.assertTrue(self._cell(self.rec, martes).get('es_descanso'))

    def test_doblada_permanente_multicompanero_atribuye_por_fecha(self):
        """Regresión (caso marco 11/08): cuando el MISMO día de la semana se reparte entre varios
        compañeros por FECHAS distintas, Mis Turnos debe atribuir el descanso de cada fecha al
        compañero de ESA fecha (no al primero que coincida por patrón), y un día del mismo weekday
        que no se cedió no debe aparecer como descanso."""
        import calendar
        # Tercer explorador, también PM (contrario al solicitante AM) para poder cubrir.
        u_c2 = User.objects.create_user(username='comp2.test', password='x')
        comp2 = Empleado.objects.create(user=u_c2, nombre='Comp2', apellido='PM', cedula='903', activo=True,
                                        email='comp2@test.com', supervisor=self.supervisor)
        AsignarJornadaExplorador.objects.create(explorador=comp2, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=comp2, sala=self.sala)

        # Primer lunes de un mes futuro: garantiza ≥3 lunes y ≥2 martes hasta fin de mes, así que
        # el escenario siempre se puede armar (antes se saltaba según el día en que se corriera).
        fi = self._primer_dia_semana_de_mes_futuro(0)
        ultimo = date(fi.year, fi.month, calendar.monthrange(fi.year, fi.month)[1])
        lunes, martes = [], []
        d = fi
        while d <= ultimo:
            if d.weekday() == 0:
                lunes.append(d)
            if d.weekday() == 1:
                martes.append(d)
            d += timedelta(days=1)
        self.assertGreaterEqual(len(lunes), 3, 'el ancla debe garantizar 3 lunes')
        self.assertGreaterEqual(len(martes), 2, 'el ancla debe garantizar 2 martes')
        ff = ultimo
        # sol -> rec cubre el lunes[0]; sol -> comp2 cubre el lunes[1] (mismo weekday, fechas distintas).
        self._crear_y_aplicar(self.tipos['DOBLADA PERMANENTE'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['DOBLADA PERMANENTE'], 'comentario': 'test',
            'fecha_inicio': fi.strftime('%Y-%m-%d'), 'fecha_fin': ff.strftime('%Y-%m-%d'),
            'dias_cesion': ['0'], 'dias_devolucion': ['1'],
            'fechas_cesion': [lunes[0].strftime('%Y-%m-%d')],
            'fechas_devolucion': [martes[0].strftime('%Y-%m-%d')],
        })
        self._crear_y_aplicar(self.tipos['DOBLADA PERMANENTE'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': comp2,
            'tipo_cambio': self.tipos['DOBLADA PERMANENTE'], 'comentario': 'test',
            'fecha_inicio': fi.strftime('%Y-%m-%d'), 'fecha_fin': ff.strftime('%Y-%m-%d'),
            'dias_cesion': ['0'], 'dias_devolucion': ['1'],
            'fechas_cesion': [lunes[1].strftime('%Y-%m-%d')],
            'fechas_devolucion': [martes[1].strftime('%Y-%m-%d')],
        })
        # Cada lunes cedido se atribuye a SU compañero.
        c0 = self._cell(self.sol, lunes[0])
        c1 = self._cell(self.sol, lunes[1])
        self.assertTrue(c0.get('es_descanso'))
        self.assertTrue(c1.get('es_descanso'))
        self.assertEqual((c0.get('descanso_info') or {}).get('companero_nombre'), 'Rec PM',
                         f'lunes[0] debe ser de Rec, no {c0.get("descanso_info")}')
        self.assertEqual((c1.get('descanso_info') or {}).get('companero_nombre'), 'Comp2 PM',
                         f'lunes[1] debe ser de Comp2, no {c1.get("descanso_info")}')
        # Un lunes NO cedido no debe aparecer como descanso por patrón.
        self.assertFalse(self._cell(self.sol, lunes[2]).get('es_descanso'),
                         'un lunes sin fecha cedida no debe quedar como descanso por patrón de weekday')

    # ------------------------------------------------- CAMBIO DESCANSO (fin de semana)
    def _findes_cambio_descanso(self):
        """
        (cesion, pago) para un CAMBIO DESCANSO de finde entre `self.sol` (AM) y `self.rec` (PM),
        en un mismo mes futuro:
        - cesion: SABADO que trabaja el solicitante (AM) y cuyo domingo trabaja el receptor (PM).
        - pago:   DOMINGO de OTRO finde que trabaja el solicitante y cuyo sabado trabaja el receptor.

        Mismo criterio que `_fechas_cd` en test_cambio_descanso.py: las fechas salen de la
        alternancia real publicada, nunca hardcodeadas, o el test caduca.
        """
        A = AlternanciaFinesSemanaService
        hoy = timezone.localdate()
        anio, mes = hoy.year, hoy.month
        for _ in range(12):
            mes += 1
            if mes > 12:
                mes, anio = 1, anio + 1
            sabados = []
            d = date(anio, mes, 1)
            while d.month == mes:
                if d.weekday() == 5:
                    sabados.append(d)
                d += timedelta(days=1)
            ces = next((s for s in sabados if s > hoy
                        and A.jornada_trabaja_sabado(s) == 'AM'
                        and A.jornada_trabaja_domingo(s) == 'PM'), None)
            pago = next((s + timedelta(days=1) for s in sabados
                         if s != ces and (s + timedelta(days=1)).month == mes
                         and s + timedelta(days=1) > hoy
                         and A.jornada_trabaja_domingo(s) == 'AM'
                         and A.jornada_trabaja_sabado(s) == 'PM'), None)
            if ces and pago:
                return ces, pago
        self.fail('No se hallaron findes validos para CAMBIO DESCANSO')

    def test_cambio_descanso_finde_refleja(self):
        """
        Al ceder el descanso de un finde, el que cede DESCANSA el dia cedido y dobla el dia
        opuesto de ese mismo finde; el compañero hace el espejo. Mis Turnos debe mostrar esas
        cuatro celdas, para AMBOS empleados.
        """
        ces, pago = self._findes_cambio_descanso()
        otro_ces = ces + timedelta(days=1)      # domingo del finde de cesion
        otro_pago = pago - timedelta(days=1)    # sabado del finde de pago

        self._crear_y_aplicar(self.tipos['CAMBIO DESCANSO'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['CAMBIO DESCANSO'], 'comentario': 'test',
            'fecha_cambio_turno': ces.strftime('%Y-%m-%d'),
            'fecha_pago': pago.strftime('%Y-%m-%d'),
        })

        # Solicitante: descansa los dias que cede, dobla los opuestos.
        self.assertTrue(self._cell(self.sol, ces).get('es_descanso'),
                        f'{ces}: el solicitante cedio ese dia, debe verlo como descanso')
        self.assertEqual(self._cell(self.sol, otro_ces).get('jornada'), 'DOBLADA')
        self.assertTrue(self._cell(self.sol, pago).get('es_descanso'))
        self.assertEqual(self._cell(self.sol, otro_pago).get('jornada'), 'DOBLADA')
        # Receptor: espejo exacto.
        self.assertEqual(self._cell(self.rec, ces).get('jornada'), 'DOBLADA')
        self.assertTrue(self._cell(self.rec, otro_ces).get('es_descanso'))

    # ---------------------------------------------------- CAMBIO DESCANSO (entre semana)
    def test_cambio_descanso_entre_semana_refleja(self):
        """
        Entre semana el descanso no sale de la alternancia sino de `DescansoSemanaManual`.
        En `intercambio_dia` los dos permutan su dia de descanso: cada uno pasa a trabajar el
        dia que antes descansaba y a descansar el del otro. Es la modalidad hermana de la de
        finde y se rompe por su cuenta, asi que necesita su propio caso.
        """
        from turnos.models import DescansoSemanaManual

        hoy = timezone.localdate()
        lunes = hoy + timedelta(days=7 - hoy.weekday() + 7)
        f_sol = lunes + timedelta(days=1)   # martes: descansa AM (el solicitante)
        f_rec = lunes + timedelta(days=3)   # jueves: descansa PM (el receptor)
        DescansoSemanaManual.objects.create(fecha=f_sol, jornada=self.am, activo=True)
        DescansoSemanaManual.objects.create(fecha=f_rec, jornada=self.pm, activo=True)

        # Antes: cada uno descansa SU dia y trabaja el del otro.
        self.assertTrue(self._cell(self.sol, f_sol).get('es_descanso'))
        self.assertTrue(self._cell(self.rec, f_rec).get('es_descanso'))

        self._crear_y_aplicar(self.tipos['CAMBIO DESCANSO'], {
            'explorador_solicitante': self.sol, 'explorador_receptor': self.rec,
            'tipo_cambio': self.tipos['CAMBIO DESCANSO'], 'comentario': 'test',
            'fecha_cambio_turno': f_sol.strftime('%Y-%m-%d'),
            'fecha_pago': f_rec.strftime('%Y-%m-%d'),
        })

        # Despues: se permutan. El solicitante cede su martes y pasa a descansar el jueves.
        self.assertFalse(self._cell(self.sol, f_sol).get('es_descanso'),
                         f'{f_sol}: el solicitante cedio su descanso, debe verse trabajando')
        self.assertTrue(self._cell(self.sol, f_rec).get('es_descanso'),
                        f'{f_rec}: el solicitante recibio el descanso del compañero')
        self.assertTrue(self._cell(self.rec, f_sol).get('es_descanso'),
                        f'{f_sol}: el receptor recibio el descanso del solicitante')
        self.assertFalse(self._cell(self.rec, f_rec).get('es_descanso'),
                         f'{f_rec}: el receptor cedio su descanso, debe verse trabajando')


class ReflejoMisTurnosPermisosTest(ReflejoMisTurnosTest):
    """
    Los permisos especiales no son solicitudes de cambio, pero comparten el destino: se aprueban
    y el empleado espera verlos en su calendario. No cambian la jornada; se pintan como
    indicador del dia (`celda['permiso']`).
    """

    def _permiso(self, **campos):
        from permisos.models import PermisoEspecial
        return PermisoEspecial.objects.create(
            empleado=self.sol, estado='APROBADO', fecha_aprobacion=timezone.now(), **campos)

    def test_permiso_puntual_refleja(self):
        f = self._dia_semana(2)  # miercoles
        self._permiso(tipo='MEDICO', fecha_inicio=f, fecha_fin=f, tiempo=2)

        permiso = self._cell(self.sol, f).get('permiso')
        self.assertIsNotNone(permiso, f'{f}: el permiso aprobado no aparece en Mis Turnos')
        self.assertEqual(permiso['estado'], 'APROBADO')
        self.assertEqual(permiso['horas'], 2.0)

    def test_permiso_permanente_refleja_solo_sus_dias(self):
        inicio = self._primer_dia_semana_de_mes_futuro(0)   # lunes
        fin = inicio + timedelta(days=13)
        self._permiso(tipo='PERSONAL', es_permanente=True, dias_semana='0',
                      fecha_inicio=inicio, fecha_fin=fin, tiempo=1)

        self.assertIsNotNone(self._cell(self.sol, inicio).get('permiso'))
        self.assertIsNotNone(self._cell(self.sol, inicio + timedelta(days=7)).get('permiso'),
                             'el permiso permanente debe repetirse cada lunes del rango')
        self.assertIsNone(self._cell(self.sol, inicio + timedelta(days=1)).get('permiso'),
                          'un martes no esta en dias_semana: no debe marcarse')

    def test_media_jornada_temporada_marca_el_dia_de_compensacion(self):
        f = self._dia_semana(2)
        comp = f + timedelta(days=2)
        self._permiso(tipo='MEDIA_JORNADA_TEMPORADA', fecha_inicio=f, fecha_fin=f,
                      tiempo=0, jornada_trabaja='AM', fecha_compensacion=comp)

        self.assertIsNotNone(self._cell(self.sol, f).get('permiso'))
        self.assertIsNotNone(self._cell(self.sol, comp).get('permiso'),
                             f'{comp}: el dia de compensacion tambien debe quedar marcado')

    def _par_media_jornada_que_cruza_de_mes(self):
        """
        (trabajo, compensacion) LEGALES que caen en meses distintos.

        La regla del formulario (MediaJornadaTemporadaCreateView) es: ambos dias de LUNES A
        VIERNES y en la MISMA semana (mismo lunes). Eso sigue permitiendo cruzar el cambio de
        mes cuando el corte cae de martes a viernes —p. ej. lunes 30/11 y martes 01/12—, que es
        justamente el escenario que se escapaba. Un par sabado→domingo NO es valido y no sirve
        para probar nada.
        """
        d = timezone.localdate() + timedelta(days=15)
        for _ in range(400):
            lunes_de = d - timedelta(days=d.weekday())
            for k in range(1, 5):
                otro = d + timedelta(days=k)
                if (d.weekday() < 5 and otro.weekday() < 5
                        and otro - timedelta(days=otro.weekday()) == lunes_de
                        and d.month != otro.month):
                    return d, otro
            d += timedelta(days=1)
        self.fail('No se hallo un par L-V de la misma semana que cruce de mes')

    def test_compensacion_en_otro_mes_se_ve_al_consultar_ese_mes(self):
        """
        La compensacion es un dia de la MISMA semana, y una semana de lunes a viernes cruza el
        cambio de mes varias veces al año (lunes 30/11 → martes 01/12, etc.). Al consultar el mes
        de la compensacion, el RANGO del permiso no se solapa con ese mes: si el queryset filtra
        solo por rango, el permiso ni se trae y el dia sale sin marcar.
        """
        f, comp = self._par_media_jornada_que_cruza_de_mes()
        # El escenario debe ser legal segun la regla del formulario, o no prueba nada.
        self.assertLess(f.weekday(), 5)
        self.assertLess(comp.weekday(), 5)
        self.assertEqual(f - timedelta(days=f.weekday()), comp - timedelta(days=comp.weekday()),
                         'trabajo y compensacion deben ser de la MISMA semana')
        self.assertNotEqual(f.month, comp.month, 'el escenario exige cruzar el cambio de mes')

        self._permiso(tipo='MEDIA_JORNADA_TEMPORADA', fecha_inicio=f, fecha_fin=f,
                      tiempo=0, jornada_trabaja='AM', fecha_compensacion=comp)

        self.assertIsNotNone(self._cell(self.sol, comp).get('permiso'),
                             f'{comp}: la compensacion cae en otro mes y quedo sin marcar')
