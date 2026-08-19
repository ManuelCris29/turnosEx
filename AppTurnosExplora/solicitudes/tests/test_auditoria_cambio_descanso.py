"""
Regresiones de la auditoría del formulario de CAMBIO DESCANSO (07/08/2026).

Cubre cuatro fallos que compartían una misma raíz: dos rutas distintas respondiendo a la
pregunta "¿esta persona descansa este día?" sin ponerse de acuerdo.

  H1  El desplegable de compañeros se filtraba por MI descanso, mientras que la validación
      decide por el descanso del compañero (otra fecha). Ofrecía gente que luego rechazaba.
  H3  La rama CAMBIO DESCANSO no aplicaba la guarda "L1 manda sobre L2" (Patrón #28).
  H4  El compañero atribuido dependía del orden en que la BD devolviera las filas.
  H6  El formulario se elegía por `nombre`; un tipo desconocido caía en el de CT sin avisar.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado, Jornada, CompetenciaEmpleado
from turnos.models import Sala, AsignarJornadaExplorador, Turno, DescansoSemanaManual
from turnos.services.turno_service import TurnoService
from solicitudes.models import TipoSolicitudCambio, SolicitudCambio, DobladaDetalle
from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService as DS
from solicitudes.services.cambio_descanso_aplicacion_service import (
    CambioDescansoAplicacionService as CDA,
)
from solicitudes.views.api_disponibles_ct_preview import ObtenerEmpleadosDisponiblesView


class _BaseAuditoria(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Aud', activo=True)
        self.tipo_cd = TipoSolicitudCambio.objects.create(
            nombre='CAMBIO DESCANSO', codigo_estrategia='CAMBIO DESCANSO')

        self.sol = self._empleado('aud.sol', 'Sol', 'Aud', '9001', self.pm)
        self.rec = self._empleado('aud.rec', 'Rec', 'Aud', '9002', self.am)
        self.otro = self._empleado('aud.otro', 'Otro', 'Aud', '9003', self.am)

        # Semana futura de lunes a viernes (evita el "no puede ser hoy ni pasado").
        base = timezone.localdate() + timedelta(days=30)
        self.lunes = base - timedelta(days=base.weekday())
        self.martes = self.lunes + timedelta(days=1)
        self.viernes = self.lunes + timedelta(days=4)

    def _empleado(self, username, nombre, apellido, cedula, jornada):
        u = User.objects.create_user(username=username, password='x')
        e = Empleado.objects.create(user=u, nombre=nombre, apellido=apellido,
                                    cedula=cedula, activo=True)
        AsignarJornadaExplorador.objects.create(
            explorador=e, jornada=jornada, fecha_inicio=date(2025, 1, 1))
        CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)
        return e

    def _cambio_descanso(self, solicitante, receptor, fecha_cesion, fecha_pago, resolucion=None):
        """CAMBIO DESCANSO entre semana aprobado (submodalidad `intercambio_dia`).

        Con esa submodalidad el SOLICITANTE descansa `fecha_pago` y el RECEPTOR `fecha_cesion`
        (ver `_mapa_descanso_multi`).
        """
        s = SolicitudCambio.objects.create(
            explorador_solicitante=solicitante, explorador_receptor=receptor,
            tipo_cambio=self.tipo_cd, estado='aprobada',
            fecha_cambio_turno=fecha_cesion, comentario='aud',
            fecha_resolucion=resolucion or timezone.now(),
        )
        DobladaDetalle.objects.create(
            solicitud=s, fecha_pago=fecha_pago, tipo_cesion='cesion_completa',
            submodalidad_semana='intercambio_dia', minutos_deuda=0,
        )
        return s

    def _turno(self, empleado, fecha, jornada, tipo_cambio='DOBLADA'):
        return Turno.objects.create(explorador=empleado, fecha=fecha, jornada=jornada,
                                    sala=self.sala, tipo_cambio=tipo_cambio)


class GuardaL1EnCambioDescansoTest(_BaseAuditoria):
    """H3 — un Turno REAL manda sobre un descanso atribuido por CAMBIO DESCANSO."""

    def test_sin_turno_real_el_dia_se_reporta_como_descanso(self):
        self._cambio_descanso(self.sol, self.rec, self.martes, self.viernes)
        info = DS.en_fecha(self.sol, self.viernes)
        self.assertIsNotNone(info, 'el solicitante debe descansar la fecha de pago')
        self.assertEqual(info['origen'], 'cambio_descanso')

    def test_con_turno_real_no_se_reporta_descanso(self):
        """El caso del Patrón #28, que en esta rama seguía sin cubrirse."""
        self._cambio_descanso(self.sol, self.rec, self.martes, self.viernes)
        # Algo aprobado DESPUÉS le devolvió jornada real ese día.
        self._turno(self.sol, self.viernes, self.pm)

        self.assertIsNone(
            DS.en_fecha(self.sol, self.viernes),
            'con Turno real ese día la persona TRABAJA: no se puede atribuir descanso',
        )

    def test_con_turno_real_el_dia_no_queda_comprometido(self):
        """Es lo que rompía de verdad: el falso bloqueo en los formularios."""
        self._cambio_descanso(self.sol, self.rec, self.martes, self.viernes)
        self._turno(self.sol, self.viernes, self.pm)

        self.assertIsNone(
            TurnoService.dia_comprometido_por_solicitud(self.sol, self.viernes),
            'un día con turno real no puede salir como "comprometido en otra solicitud"',
        )
        estado = TurnoService.estado_dia(self.sol, self.viernes)
        self.assertTrue(estado['trabaja'])
        self.assertEqual(estado['fuente'], 'turno')


class CompaneroDeterministaTest(_BaseAuditoria):
    """H4 — con dos intercambios sobre el mismo día gana el aprobado más tarde, siempre."""

    def test_gana_la_ultima_aprobada_y_es_estable(self):
        ahora = timezone.now()
        # Antigua: el solicitante descansa el viernes, con `rec` como compañero.
        self._cambio_descanso(self.sol, self.rec, self.martes, self.viernes,
                              resolucion=ahora - timedelta(hours=2))
        # Reciente: mismo día de descanso, pero con `otro`.
        self._cambio_descanso(self.sol, self.otro, self.martes, self.viernes,
                              resolucion=ahora)

        vistos = set()
        for _ in range(20):
            info = DS.en_fecha(self.sol, self.viernes)
            vistos.add(info['companero']['id'] if info and info.get('companero') else None)

        self.assertEqual(
            vistos, {self.otro.id},
            f'el compañero debe ser siempre el de la última aprobada; se vieron {vistos}',
        )

    def test_mapa_descanso_multi_tambien_es_estable(self):
        ahora = timezone.now()
        self._cambio_descanso(self.sol, self.rec, self.martes, self.viernes,
                              resolucion=ahora - timedelta(hours=2))
        self._cambio_descanso(self.sol, self.otro, self.martes, self.viernes,
                              resolucion=ahora)

        vistos = set()
        for _ in range(20):
            m = CDA._mapa_descanso_multi([self.sol], self.viernes, self.viernes)
            comp = m.get(self.sol.id, {}).get(self.viernes)
            vistos.add(comp['id'] if comp else None)
        self.assertEqual(vistos, {self.otro.id})


class FiltroCompanerosPorDescansoReceptorTest(_BaseAuditoria):
    """H1 — el desplegable se filtra por la fecha que la validación va a comprobar."""

    def setUp(self):
        super().setUp()
        # Escenario real del formulario 6 (entre semana, temporada): esa semana descansa AM el
        # martes y PM el viernes. Para el explorador PM, el martes es su día de trabajo COMPLETO
        # y el candidato del grupo contrario es quien descansa ESE martes.
        DescansoSemanaManual.objects.create(
            fecha=self.martes, jornada=self.am, motivo='temporada', activo=True)
        DescansoSemanaManual.objects.create(
            fecha=self.viernes, jornada=self.pm, motivo='temporada', activo=True)

    def test_sin_parametro_no_filtra_nada(self):
        """Los demás formularios (CT, doblada, CT permanente…) no cambian de comportamiento."""
        candidatos = [self.rec, self.otro]
        self.assertEqual(
            ObtenerEmpleadosDisponiblesView._filtrar_por_descanso_receptor(candidatos, None),
            candidatos,
        )

    def test_excluye_a_quien_ya_no_descansa_esa_fecha(self):
        # `rec` conserva su descanso; `otro` ya trabaja ese día (lo intercambió antes).
        self._turno(self.otro, self.martes, self.am, tipo_cambio='CAMBIO DESCANSO')

        filtrados = ObtenerEmpleadosDisponiblesView._filtrar_por_descanso_receptor(
            [self.rec, self.otro], self.martes.isoformat())

        self.assertIn(self.rec, filtrados)
        self.assertNotIn(self.otro, filtrados,
                         'quien ya trabaja esa fecha no puede ofrecerse como compañero')

    def test_coincide_con_lo_que_decide_la_validacion(self):
        """El filtro y la validación deben usar el MISMO criterio, o vuelven a divergir."""
        self._turno(self.otro, self.martes, self.am, tipo_cambio='CAMBIO DESCANSO')

        for cand in (self.rec, self.otro):
            ofrecido = cand in ObtenerEmpleadosDisponiblesView._filtrar_por_descanso_receptor(
                [cand], self.martes.isoformat())
            lo_rechaza = TurnoService.estado_dia(cand, self.martes)['trabaja']
            self.assertEqual(ofrecido, not lo_rechaza,
                             f'{cand.nombre}: se ofrece={ofrecido} pero la validación '
                             f'rechaza={lo_rechaza}')


class DespachoPorCodigoEstrategiaTest(_BaseAuditoria):
    """H6 — el formulario se elige por `codigo_estrategia`, y un código desconocido da 404."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.sol.user)

    def _get(self, tipo):
        return self.client.get(reverse('solicitudes:solicitar_cambio_turno', args=[tipo.id]))

    def test_cambio_descanso_sirve_su_propio_formulario(self):
        resp = self._get(self.tipo_cd)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'solicitudes/solicitar_cambio_descanso.html')

    def test_ct_sencillo_se_resuelve_por_codigo_no_por_nombre(self):
        """El nombre de la maestra es 'CAMBIO TURNO' pero su código es 'CT'."""
        tipo = TipoSolicitudCambio.objects.create(nombre='CAMBIO TURNO', codigo_estrategia='CT')
        resp = self._get(tipo)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'solicitudes/solicitar_cambio_turno.html')

    def test_codigo_desconocido_da_404_en_vez_del_formulario_de_ct(self):
        tipo = TipoSolicitudCambio.objects.create(nombre='INVENTADO', codigo_estrategia='NUEVO')
        self.assertEqual(self._get(tipo).status_code, 404)

    def test_tipo_renombrado_no_cae_en_el_formulario_de_ct(self):
        """Renombrar la fila no debe cambiar qué formulario se sirve."""
        self.tipo_cd.nombre = 'Cambio de día de descanso (2026)'
        self.tipo_cd.save()
        resp = self._get(self.tipo_cd)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'solicitudes/solicitar_cambio_descanso.html')
