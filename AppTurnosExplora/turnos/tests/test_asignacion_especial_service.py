"""
Tests de la planeación ANUAL de findes y festivos (AsignacionEspecialService).

Cubren los hallazgos de la auditoría de `/turnos/asignacion-especial/anual/`:
  1. El bloqueo por solicitud aprobada debe ver TODOS los tipos que atan a un día,
     no solo la cesión y el pago de doblada (hallazgo 2).
  2. Guardar el año no debe aceptar días que no son finde ni festivo (hallazgo 3).
  3. Una solicitud en un día normal no debe bloquear la pantalla (hacía que
     `anio_editable_completo` fuera False sin que ningún finde estuviera comprometido).
  4. `grupo_trabaja_efectivo` debe resolver también los festivos entre semana (hallazgo 7).
"""
from datetime import date, timedelta

from django.test import TestCase
from django.contrib.auth.models import User

from empleados.models import Empleado, Jornada
from turnos.models import AsignacionEspecialManual, DiaEspecial
from turnos.services.asignacion_especial_service import (
    AsignacionEspecialService, AsignacionEspecialConflicto,
)


def _primer_weekday_del_anio(anio, weekday):
    d = date(anio, 1, 1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


class AsignacionEspecialAnualTest(TestCase):

    ANIO = 2030

    def setUp(self):
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        # Un finde y un festivo entre semana bien separados, para no solaparse.
        self.sabado = _primer_weekday_del_anio(self.ANIO, 5) + timedelta(weeks=10)
        self.domingo = self.sabado + timedelta(days=1)
        self.martes = _primer_weekday_del_anio(self.ANIO, 1) + timedelta(weeks=20)
        self.festivo = _primer_weekday_del_anio(self.ANIO, 3) + timedelta(weeks=30)
        DiaEspecial.objects.create(fecha=self.festivo, tipo='festivo', activo=True)

    # ------------------------------------------------------------------ guardar
    def test_guardar_anual_acepta_finde_y_festivo(self):
        n = AsignacionEspecialService.guardar_anual(self.ANIO, {
            self.sabado.isoformat(): 'AM',
            self.festivo.isoformat(): 'PM',
        })
        self.assertEqual(n, 2)
        self.assertEqual(
            AsignacionEspecialManual.objects.get(fecha=self.sabado).tipo, 'finde')
        self.assertEqual(
            AsignacionEspecialManual.objects.get(fecha=self.festivo).tipo, 'festivo')

    def test_guardar_anual_descarta_dia_que_no_es_finde_ni_festivo(self):
        """Un martes normal llegado por POST no puede guardarse como si fuera festivo."""
        n = AsignacionEspecialService.guardar_anual(self.ANIO, {
            self.sabado.isoformat(): 'AM',
            self.martes.isoformat(): 'PM',
        })
        self.assertEqual(n, 1)
        self.assertFalse(AsignacionEspecialManual.objects.filter(fecha=self.martes).exists())

    def test_guardar_anual_descarta_otro_anio_y_jornada_inexistente(self):
        n = AsignacionEspecialService.guardar_anual(self.ANIO, {
            date(self.ANIO + 1, 3, 2).isoformat(): 'AM',
            self.sabado.isoformat(): 'XX',
        })
        self.assertEqual(n, 0)

    # ------------------------------------------------- bloqueo por solicitudes
    def _empleados(self, sufijo='1'):
        u1 = User.objects.create_user(f'sol_ae{sufijo}', password='x', email=f's{sufijo}@s.com')
        u2 = User.objects.create_user(f'rec_ae{sufijo}', password='x', email=f'r{sufijo}@r.com')
        e1 = Empleado.objects.create(user=u1, nombre='S', apellido='X', cedula=f'80{sufijo}',
                                     email=f's{sufijo}@s.com', activo=True)
        e2 = Empleado.objects.create(user=u2, nombre='R', apellido='X', cedula=f'81{sufijo}',
                                     email=f'r{sufijo}@r.com', activo=True)
        return e1, e2

    def _solicitud(self, fecha, nombre='DOBLADA', sufijo='1'):
        from solicitudes.models import SolicitudCambio, TipoSolicitudCambio
        tipo, _ = TipoSolicitudCambio.objects.get_or_create(
            nombre=nombre, defaults={'codigo_estrategia': nombre.replace(' ', '_'), 'activo': True})
        e1, e2 = self._empleados(sufijo)
        return SolicitudCambio.objects.create(
            explorador_solicitante=e1, explorador_receptor=e2, tipo_cambio=tipo,
            fecha_cambio_turno=fecha, estado='aprobada',
        )

    def test_cesion_en_sabado_bloquea_todo_el_finde(self):
        self._solicitud(self.sabado)
        bloq = AsignacionEspecialService.fechas_bloqueadas_por_solicitud(self.ANIO)
        self.assertIn(self.sabado.isoformat(), bloq)
        self.assertIn(self.domingo.isoformat(), bloq)

    def test_solicitud_en_dia_normal_no_bloquea_nada(self):
        """Antes bloqueaba, y con eso escondía los botones de sembrar sin motivo."""
        self._solicitud(self.martes)
        self.assertEqual(AsignacionEspecialService.fechas_bloqueadas_por_solicitud(self.ANIO), set())
        self.assertTrue(AsignacionEspecialService.anio_editable_completo(self.ANIO))

    def test_fecha_pago_semana_bloquea(self):
        from solicitudes.models import DobladaDetalle
        s = self._solicitud(self.martes)
        DobladaDetalle.objects.create(
            solicitud=s, fecha_pago=self.martes + timedelta(days=1),
            jornada_pago_sabado='AMBAS', fecha_pago_semana=self.festivo,
        )
        self.assertIn(self.festivo.isoformat(),
                      AsignacionEspecialService.fechas_bloqueadas_por_solicitud(self.ANIO))

    def test_cambio_permanente_dia_especifico_bloquea(self):
        """El modelo solo admite lun-vie, así que la fuente aplica a festivos entre semana."""
        from solicitudes.models import CambioPermanenteDetalle, CambioPermanenteDia
        s = self._solicitud(self.martes, nombre='CT PERMANENTE')
        det = CambioPermanenteDetalle.objects.create(
            solicitud=s, fecha_inicio=self.festivo, fecha_fin=self.festivo)
        CambioPermanenteDia.objects.create(
            cambio_permanente=det, fecha_especifica=self.festivo, tipo='fecha_especifica')
        self.assertIn(self.festivo.isoformat(),
                      AsignacionEspecialService.fechas_bloqueadas_por_solicitud(self.ANIO))

    def test_reprogramacion_bloquea_el_dia_nuevo(self):
        from solicitudes.models import ReprogramacionDiaDoblada
        s = self._solicitud(self.martes)
        ReprogramacionDiaDoblada.objects.create(
            doblada_origen=s, explorador=s.explorador_solicitante,
            fecha_original=self.martes, fecha_reprogramada=self.sabado, estado='pendiente')
        self.assertIn(self.sabado.isoformat(),
                      AsignacionEspecialService.fechas_bloqueadas_por_solicitud(self.ANIO))

    def test_deuda_pendiente_bloquea_la_fecha_pactada(self):
        from solicitudes.models import DeudaExplorador
        s = self._solicitud(self.martes)
        DeudaExplorador.objects.create(
            deudor=s.explorador_solicitante, acreedor=s.explorador_receptor,
            solicitud_origen=s, fecha_pago_pactada=self.festivo, estado='pendiente')
        self.assertIn(self.festivo.isoformat(),
                      AsignacionEspecialService.fechas_bloqueadas_por_solicitud(self.ANIO))

    def test_doblada_permanente_con_fechas_especificas_bloquea(self):
        from solicitudes.models import DobladaPermanenteDetalle
        s = self._solicitud(self.martes, nombre='DOBLADA PERMANENTE')
        DobladaPermanenteDetalle.objects.create(
            solicitud=s, fecha_inicio=self.sabado - timedelta(days=7),
            fecha_fin=self.sabado + timedelta(days=7),
            fechas_cesion=self.sabado.isoformat(), fechas_devolucion='')
        self.assertIn(self.sabado.isoformat(),
                      AsignacionEspecialService.fechas_bloqueadas_por_solicitud(self.ANIO))

    def test_doblada_permanente_por_weekday_bloquea_los_sabados_del_rango(self):
        from solicitudes.models import DobladaPermanenteDetalle
        s = self._solicitud(self.martes, nombre='DOBLADA PERMANENTE')
        DobladaPermanenteDetalle.objects.create(
            solicitud=s, fecha_inicio=self.sabado, fecha_fin=self.sabado + timedelta(days=1),
            dias_cesion='5', dias_devolucion='')
        self.assertIn(self.sabado.isoformat(),
                      AsignacionEspecialService.fechas_bloqueadas_por_solicitud(self.ANIO))

    # ------------------------------------------------------------- conflictos
    def test_no_se_puede_alterar_un_dia_bloqueado(self):
        AsignacionEspecialService.guardar_anual(self.ANIO, {self.sabado.isoformat(): 'AM'})
        self._solicitud(self.sabado)
        with self.assertRaises(AsignacionEspecialConflicto):
            AsignacionEspecialService.guardar_anual(self.ANIO, {self.sabado.isoformat(): 'PM'})
        # La transacción se abortó: el valor original sigue intacto.
        self.assertEqual(
            AsignacionEspecialManual.objects.get(fecha=self.sabado).jornada_trabaja.nombre, 'AM')

    def test_se_puede_guardar_si_el_dia_bloqueado_no_cambia(self):
        AsignacionEspecialService.guardar_anual(self.ANIO, {self.sabado.isoformat(): 'AM'})
        self._solicitud(self.sabado)
        n = AsignacionEspecialService.guardar_anual(self.ANIO, {
            self.sabado.isoformat(): 'AM',      # igual que está: permitido
            self.festivo.isoformat(): 'PM',     # día libre: se puede añadir
        })
        self.assertEqual(n, 2)

    def test_el_domingo_del_finde_bloqueado_tampoco_se_puede_tocar(self):
        """Cambiar el domingo altera el mismo finde que la solicitud comprometió."""
        AsignacionEspecialService.guardar_anual(self.ANIO, {self.sabado.isoformat(): 'AM'})
        self._solicitud(self.sabado)
        with self.assertRaises(AsignacionEspecialConflicto):
            AsignacionEspecialService.guardar_anual(self.ANIO, {
                self.sabado.isoformat(): 'AM',
                self.domingo.isoformat(): 'PM',
            })

    # ------------------------------------------------------------ grupo_trabaja
    def test_grupo_trabaja_sin_publicar_es_none(self):
        """None = SIN PLANIFICAR. No se inventa un grupo con una fórmula."""
        self.assertIsNone(AsignacionEspecialService.grupo_trabaja(self.festivo))
        self.assertIsNone(AsignacionEspecialService.grupo_trabaja(self.sabado))

    def test_grupo_trabaja_devuelve_lo_publicado(self):
        AsignacionEspecialService.guardar_anual(self.ANIO, {self.festivo.isoformat(): 'AM'})
        self.assertEqual(AsignacionEspecialService.grupo_trabaja(self.festivo), 'AM')

    def test_grupo_trabaja_en_dia_normal_es_none(self):
        self.assertIsNone(AsignacionEspecialService.grupo_trabaja(self.martes))

    # ----------------------------------------------------------------- siembra
    def test_la_siembra_cubre_el_anio_completo(self):
        n = AsignacionEspecialService.sembrar_anio(self.ANIO, 'AM', 'PM')
        self.assertEqual(AsignacionEspecialService.fechas_sin_planificar(self.ANIO), [])
        self.assertTrue(AsignacionEspecialService.anio_sembrado(self.ANIO))
        self.assertGreater(n, 100)

    def test_la_siembra_alterna_findes_por_paridad_de_fecha(self):
        """
        Por paridad y no por posición: así, saltarse un día (p. ej. bloqueado) no desfasa
        el resto del año. Era el bug de la siembra que vivía en el JavaScript.
        """
        siembra = AsignacionEspecialService.calcular_siembra(self.ANIO, 'AM', 'PM')
        primer_sabado = _primer_weekday_del_anio(self.ANIO, 5)
        self.assertEqual(siembra[primer_sabado.isoformat()], 'AM')
        # El domingo de ese finde trabaja el contrario…
        self.assertEqual(siembra[(primer_sabado + timedelta(days=1)).isoformat()], 'PM')
        # …y el finde siguiente se invierte.
        self.assertEqual(siembra[(primer_sabado + timedelta(days=7)).isoformat()], 'PM')

    def test_la_siembra_rechaza_grupos_invalidos(self):
        with self.assertRaises(ValueError):
            AsignacionEspecialService.calcular_siembra(self.ANIO, 'XX', 'PM')

    # -------------------------------------------------- continuidad entre años
    def test_sin_anio_previo_no_hay_sugerencia(self):
        self.assertEqual(AsignacionEspecialService.sugerencia_siembra(self.ANIO),
                         {'primer_sabado': None, 'primer_festivo': None})

    def test_la_sugerencia_continua_la_alternancia_del_anio_anterior(self):
        """Sustituye al ancla que antes estaba fija en el código: sale del dato, no de una constante."""
        AsignacionEspecialService.sembrar_anio(self.ANIO, 'AM', 'PM')
        sug = AsignacionEspecialService.sugerencia_siembra(self.ANIO + 1)

        ultimo = (AsignacionEspecialManual.objects
                  .filter(fecha__year=self.ANIO, tipo='finde').order_by('-fecha').first())
        grupo_sabado_final = ultimo.jornada_trabaja.nombre.upper()
        if ultimo.fecha.weekday() == 6:
            grupo_sabado_final = 'AM' if grupo_sabado_final == 'PM' else 'PM'
        esperado = 'AM' if grupo_sabado_final == 'PM' else 'PM'
        self.assertEqual(sug['primer_sabado'], esperado)

    # ------------------------------------------------------------- capa L2 / festivo
    def test_cesion_completa_de_festivo_deja_al_solicitante_descansando(self):
        """
        En un festivo entre semana, `estado_dia` decide por rotación y solo respeta turnos
        con `tipo_cambio`; no consulta la capa de descanso por solicitud. Mientras la
        aplicación materialice el Turno esto no se nota, pero si un día cede el festivo
        COMPLETO sin dejar turno, el explorador no puede aparecer trabajando.
        """
        from solicitudes.models import DobladaDetalle
        from turnos.models import AsignarJornadaExplorador
        from turnos.services.turno_service import TurnoService
        from solicitudes.services.descanso_solicitud_service import DescansoPorSolicitudService

        grupo = AsignacionEspecialService.grupo_trabaja(self.festivo)
        s = self._solicitud(self.festivo, sufijo='f')
        DobladaDetalle.objects.create(
            solicitud=s, fecha_pago=self.festivo + timedelta(days=7),
            tipo_cesion='cesion_completa')
        # El solicitante pertenece al grupo que dobla ese festivo: sin la solicitud, trabajaría.
        AsignarJornadaExplorador.objects.create(
            explorador=s.explorador_solicitante,
            jornada=self.am if grupo == 'AM' else self.pm,
            fecha_inicio=date(self.ANIO, 1, 1))

        self.assertIsNotNone(
            DescansoPorSolicitudService.en_fecha(s.explorador_solicitante, self.festivo),
            'la solicitud debería atribuir descanso ese día')
        estado = TurnoService.estado_dia(s.explorador_solicitante, self.festivo)
        self.assertFalse(
            estado['trabaja'],
            f'cedió el festivo completo pero estado_dia lo pone a trabajar ({estado})')
        # `estado_mes` es el camino batch de lo mismo: no puede discrepar.
        mes = TurnoService.estado_mes(s.explorador_solicitante, self.ANIO, self.festivo.month)
        self.assertEqual(mes[self.festivo]['trabaja'], estado['trabaja'])
        self.assertEqual(mes[self.festivo]['fuente'], estado['fuente'])
