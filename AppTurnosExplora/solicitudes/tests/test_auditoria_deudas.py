"""
Validación de la auditoría de deudas (sesión 2026-07-25).

No prueba reglas de negocio nuevas: prueba que los GUARDS que se agregaron no rompieron
lo que ya funcionaba. Cada test corresponde a un riesgo concreto de esos cambios:

A. El guard anti-duplicado NO puede bloquear una deuda legítima. El caso límite es el pago
   en sábado con jornada 'AMBAS', que genera DOS deudas entre exploradores en sentidos
   contrarios: si la clave del guard estuviera mal elegida, se comería la segunda.
B. La reconciliación (que ahora incluye dobladas permanentes) corre en CADA cancelación de
   doblada: cancelar una doblada no puede dañar una permanente vigente en esas fechas.
C. La señal que cancela deudas al cancelar una solicitud debe cancelar SOLO las suyas.
D. Ciclo completo aprobar → cancelar: el Consolidado de Horas debe volver al valor de partida.
"""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from empleados.models import Empleado, CompetenciaEmpleado
from solicitudes.models import (
    SolicitudCambio, TipoSolicitudCambio, DobladaDetalle,
    DeudaCorporativa, DeudaExplorador,
)
from turnos.models import Jornada, Sala, Turno, AsignarJornadaExplorador
from django.utils import timezone


def _martes_futuro(desde_dias=14):
    d = timezone.localdate() + timedelta(days=desde_dias)
    while d.weekday() != 1:
        d += timedelta(days=1)
    return d


class AuditoriaDeudasTestCase(TestCase):
    """Infraestructura mínima: dos exploradores con jornadas contrarias en la misma sala."""

    def setUp(self):
        cache.clear()
        self.tipo_doblada = TipoSolicitudCambio.objects.create(nombre='DOBLADA')
        self.am = Jornada.objects.create(nombre='AM', hora_inicio='06:00:00', hora_fin='14:00:00')
        self.pm = Jornada.objects.create(nombre='PM', hora_inicio='14:00:00', hora_fin='22:00:00')
        self.sala = Sala.objects.create(nombre='Sala Auditoría', activo=True)

        u1 = User.objects.create_user(username='sol.aud', password='x')
        self.solicitante = Empleado.objects.create(
            user=u1, nombre='Sol', apellido='Aud', cedula='90001', activo=True)
        u2 = User.objects.create_user(username='rec.aud', password='x')
        self.receptor = Empleado.objects.create(
            user=u2, nombre='Rec', apellido='Aud', cedula='90002', activo=True)

        AsignarJornadaExplorador.objects.create(
            explorador=self.solicitante, jornada=self.pm, fecha_inicio=date(2025, 1, 1))
        AsignarJornadaExplorador.objects.create(
            explorador=self.receptor, jornada=self.am, fecha_inicio=date(2025, 1, 1))
        for e in (self.solicitante, self.receptor):
            CompetenciaEmpleado.objects.create(empleado=e, sala=self.sala)


# ===========================================================================
# A. El guard no puede comerse la segunda deuda legítima (pago sábado AMBAS)
# ===========================================================================
class TestGuardNoBloqueaDeudaLegitima(AuditoriaDeudasTestCase):

    def _cesion_sabado_y_semana(self):
        """(martes de cesión, sábado de pago, día en semana para la devolución residual)."""
        cesion = _martes_futuro()
        sabado = cesion
        while sabado.weekday() != 5:
            sabado += timedelta(days=1)
        semana = sabado + timedelta(days=3)  # martes siguiente
        return cesion, sabado, semana

    def _solicitud_pago_sabado_ambas(self):
        cesion, sabado, semana = self._cesion_sabado_y_semana()
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=cesion,
            comentario='Pago en sábado cubriendo AMBAS jornadas',
        )
        detalle = DobladaDetalle.objects.create(
            solicitud=sol,
            fecha_pago=sabado,
            tipo_cesion='cesion_completa',
            empleado_receptor=self.receptor,
            jornada_pago_sabado='AMBAS',
            fecha_pago_semana=semana,
        )
        return sol, detalle

    def test_pago_sabado_ambas_genera_las_dos_deudas(self):
        """La principal (solicitante→receptor) y la residual invertida (receptor→solicitante).

        Si el guard usara una clave demasiado amplia (p. ej. solo la solicitud), se comería
        la segunda y el receptor nunca devolvería la jornada.
        """
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        sol, detalle = self._solicitud_pago_sabado_ambas()
        DobladaAplicacionService.generar_deudas_doblada(sol, detalle)

        deudas = DeudaExplorador.objects.filter(solicitud_origen=sol).exclude(estado='cancelada')
        self.assertEqual(deudas.count(), 2, 'deben existir la deuda principal y la residual')

        principal = deudas.filter(deudor=self.solicitante, acreedor=self.receptor)
        residual = deudas.filter(deudor=self.receptor, acreedor=self.solicitante)
        self.assertEqual(principal.count(), 1, 'falta la deuda principal (solicitante debe al receptor)')
        self.assertEqual(residual.count(), 1, 'falta la deuda residual (receptor devuelve en semana)')
        self.assertEqual(residual.first().fecha_pago_pactada, detalle.fecha_pago_semana)

    def test_regenerar_no_duplica_ninguna_de_las_dos(self):
        """Y al re-aplicar (comando de reparación) siguen siendo exactamente dos."""
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        sol, detalle = self._solicitud_pago_sabado_ambas()
        DobladaAplicacionService.generar_deudas_doblada(sol, detalle)
        DobladaAplicacionService.generar_deudas_doblada(sol, detalle)

        self.assertEqual(
            DeudaExplorador.objects.filter(solicitud_origen=sol).exclude(estado='cancelada').count(), 2,
            'regenerar no puede duplicar ni la principal ni la residual')


# ===========================================================================
# C. La señal cancela SOLO las deudas de su solicitud
# ===========================================================================
class TestSenalCancelaSoloLoSuyo(AuditoriaDeudasTestCase):

    def _solicitud_con_deuda(self, fecha, comentario):
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=fecha,
            comentario=comentario,
        )
        DeudaCorporativa.objects.create(
            explorador=self.receptor, solicitud_origen=sol, minutos=30,
            fecha_doblada=fecha, estado='activa', comentario=comentario,
        )
        DeudaExplorador.objects.create(
            deudor=self.solicitante, acreedor=self.receptor, solicitud_origen=sol,
            fecha_pago_pactada=fecha + timedelta(days=7), estado='pendiente',
            media_jornada=True, jornada_cedida='PM',
        )
        return sol

    def test_cancelar_una_no_toca_las_deudas_de_la_otra(self):
        martes = _martes_futuro()
        sol_a = self._solicitud_con_deuda(martes, 'solicitud A')
        sol_b = self._solicitud_con_deuda(martes + timedelta(days=7), 'solicitud B')

        sol_a.estado = 'cancelada'
        sol_a.save()

        # A: todo cancelado
        self.assertFalse(
            DeudaCorporativa.objects.filter(solicitud_origen=sol_a, estado='activa').exists())
        self.assertFalse(
            DeudaExplorador.objects.filter(solicitud_origen=sol_a).exclude(estado='cancelada').exists())

        # B: intacto
        self.assertTrue(
            DeudaCorporativa.objects.filter(solicitud_origen=sol_b, estado='activa').exists(),
            'cancelar A no puede tocar la deuda corporativa de B')
        self.assertTrue(
            DeudaExplorador.objects.filter(solicitud_origen=sol_b, estado='pendiente').exists(),
            'cancelar A no puede tocar la deuda entre exploradores de B')

    def test_guardar_una_solicitud_no_cancelada_no_hace_nada(self):
        """La señal corre en cada save: no puede tocar nada si el estado no es 'cancelada'."""
        martes = _martes_futuro()
        sol = self._solicitud_con_deuda(martes, 'sigue aprobada')

        sol.comentario = 'editada por el supervisor'
        sol.save()

        self.assertTrue(DeudaCorporativa.objects.filter(solicitud_origen=sol, estado='activa').exists())
        self.assertTrue(DeudaExplorador.objects.filter(solicitud_origen=sol, estado='pendiente').exists())


# ===========================================================================
# B. Cancelar una doblada no puede dañar una doblada permanente vigente
# ===========================================================================
class TestGuardiaLIFOProtegeLaPermanente(AuditoriaDeudasTestCase):
    """
    Primera línea de defensa del caso B: si hay un cambio MÁS RECIENTE sobre el mismo día,
    la cancelación se bloquea antes de revertir nada. Esto es lo que impide, en el flujo real,
    que restaurar el snapshot de una doblada pise una doblada permanente posterior.

    (La segunda línea —la reconciliación que re-materializa la permanente si el revert ocurre
    igual— está cubierta en `test_doblada_revalidacion.py`.)
    """

    def setUp(self):
        super().setUp()
        self.tipo_perm = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')

    def test_no_deja_cancelar_si_una_permanente_posterior_toca_el_mismo_dia(self):
        from django.utils import timezone
        from solicitudes.models import DobladaPermanenteDetalle
        from solicitudes.tests.helpers_cancelacion import cancelar_con_acuerdo

        martes = _martes_futuro()
        clave = f"{self.receptor.id}:{martes.isoformat()}"

        # Doblada aprobada hace 5 min (dentro de la ventana de cancelación).
        doblada = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=martes,
            comentario='doblada anterior',
        )
        SolicitudCambio.objects.filter(id=doblada.id).update(
            fecha_resolucion=timezone.now() - timedelta(minutes=5))
        DobladaDetalle.objects.create(
            solicitud=doblada, fecha_pago=martes + timedelta(days=7),
            tipo_cesion='cesion_completa', empleado_receptor=self.receptor,
            snapshot_turnos_previos={clave: []},
        )

        # Doblada PERMANENTE aprobada DESPUÉS, tocando ese mismo día.
        permanente = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_perm,
            estado='aprobada',
            fecha_cambio_turno=martes,
            comentario='permanente posterior',
        )
        SolicitudCambio.objects.filter(id=permanente.id).update(
            fecha_resolucion=timezone.now() - timedelta(minutes=1))
        DobladaPermanenteDetalle.objects.create(
            solicitud=permanente,
            fecha_inicio=martes,
            fecha_fin=martes + timedelta(days=60),
            dias_cesion='1', dias_devolucion='3',
            snapshot_turnos_previos={clave: []},
        )

        doblada = SolicitudCambio.objects.get(id=doblada.id)
        ok, msg = cancelar_con_acuerdo(doblada, self.solicitante)

        self.assertFalse(ok, 'no debe permitir cancelar por debajo de un cambio más reciente')
        self.assertIn('más reciente', msg)
        self.assertIn(martes.strftime('%d/%m'), msg, 'el mensaje debe nombrar el día en conflicto')
        self.assertEqual(
            SolicitudCambio.objects.get(id=doblada.id).estado, 'aprobada',
            'la solicitud bloqueada debe seguir aprobada')


# ===========================================================================
# E. El verificador de integridad no puede dar falsos positivos
# ===========================================================================
class TestVerificacionIntegridadDistingueCasosLegitimos(AuditoriaDeudasTestCase):
    """
    `verificar_integridad_dobladas` marcaba como error toda doblada aprobada cuyo receptor
    no tuviera turnos ese día. Pero hay razones legítimas para eso — la principal, que el
    receptor NO CUMPLIÓ y se registró una reprogramación por inasistencia, que precisamente
    anula su doblada. Un verificador que grita por casos normales deja de servir: se aprende
    a ignorarlo y el día que avise de algo real, nadie lo mira.
    """

    def _doblada_aprobada_sin_turnos(self):
        from django.utils import timezone
        martes = _martes_futuro()
        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=martes,
            fecha_resolucion=timezone.now(),
            comentario='doblada sin turnos materializados',
        )
        DobladaDetalle.objects.create(
            solicitud=sol, fecha_pago=martes + timedelta(days=7),
            tipo_cesion='cesion_completa', empleado_receptor=self.receptor,
        )
        return sol, martes

    def _verificar(self, solicitud):
        from solicitudes.management.commands.verificar_integridad_dobladas import Command
        return Command().verificar_solicitud(solicitud)

    def test_sin_turnos_y_sin_explicacion_es_problema(self):
        sol, _ = self._doblada_aprobada_sin_turnos()
        clase, texto = self._verificar(sol)
        self.assertEqual(clase, 'problema')
        self.assertIn('no tiene turnos', texto)

    def test_reprogramacion_pendiente_no_es_problema(self):
        from solicitudes.models import ReprogramacionDiaDoblada
        sol, martes = self._doblada_aprobada_sin_turnos()
        ReprogramacionDiaDoblada.objects.create(
            doblada_origen=sol, explorador=self.receptor, fecha_original=martes,
            jornada_debida='AM', estado='pendiente',
        )
        clase, texto = self._verificar(sol)
        self.assertEqual(clase, 'explicado', 'una inasistencia registrada no es un fallo de integridad')
        self.assertIn('PENDIENTE', texto)

    def test_reprogramacion_ya_pagada_no_es_problema_y_dice_cuando_se_pago(self):
        from solicitudes.models import ReprogramacionDiaDoblada
        sol, martes = self._doblada_aprobada_sin_turnos()
        pago = martes + timedelta(days=14)
        ReprogramacionDiaDoblada.objects.create(
            doblada_origen=sol, explorador=self.receptor, fecha_original=martes,
            fecha_reprogramada=pago, jornada_debida='AM', estado='pagada',
        )
        clase, texto = self._verificar(sol)
        self.assertEqual(clase, 'explicado')
        self.assertIn(str(pago), texto)

    def test_reprogramacion_cancelada_vuelve_a_ser_problema(self):
        """Si la reprogramación se canceló, la doblada original debería estar vigente otra vez."""
        from solicitudes.models import ReprogramacionDiaDoblada
        sol, martes = self._doblada_aprobada_sin_turnos()
        ReprogramacionDiaDoblada.objects.create(
            doblada_origen=sol, explorador=self.receptor, fecha_original=martes,
            jornada_debida='AM', estado='cancelada',
        )
        clase, _ = self._verificar(sol)
        self.assertEqual(clase, 'problema')


# ===========================================================================
# F. Cambio de descanso ANTIGUO (sin snapshot): revertir no puede dejar los turnos puestos
# ===========================================================================
class TestRevertirCambioDescansoSinSnapshot(AuditoriaDeudasTestCase):
    """
    Las solicitudes anteriores al mecanismo de snapshot no tienen con qué restaurar. Antes,
    `revertir()` en ese caso cancelaba las deudas y NO tocaba los turnos: la persona quedaba
    con la doblada puesta y sin deber los 30 min. El peor cruce posible — trabaja de más y
    encima el sistema dice que no debe nada.

    El fallback borra los turnos que esa gestión creó, identificados por `tipo_cambio`.
    """

    def setUp(self):
        super().setUp()
        self.tipo_cd = TipoSolicitudCambio.objects.create(nombre='CAMBIO DESCANSO')

    def _solicitud_antigua_aplicada(self):
        """Simula una solicitud vieja: turnos ya aplicados, detalle SIN snapshot."""
        cesion = _martes_futuro()
        pago = cesion + timedelta(days=2)

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_cd,
            estado='aprobada',
            fecha_cambio_turno=cesion,
            comentario='cambio de descanso antiguo',
        )
        detalle = DobladaDetalle.objects.create(
            solicitud=sol, fecha_pago=pago, tipo_cesion='cesion_completa',
            empleado_receptor=self.receptor,
        )
        self.assertFalse(detalle.snapshot_turnos_previos, 'este caso exige detalle SIN snapshot')

        # Turnos creados por la gestión (los que hay que borrar al revertir).
        for emp, fecha in ((self.receptor, cesion), (self.solicitante, pago)):
            for jor in (self.am, self.pm):
                Turno.objects.create(explorador=emp, fecha=fecha, jornada=jor,
                                     sala=self.sala, tipo_cambio='CAMBIO DESCANSO')

        DeudaCorporativa.objects.create(
            explorador=self.receptor, solicitud_origen=sol, minutos=30,
            fecha_doblada=cesion, estado='activa', comentario='doblada por cambio de descanso',
        )
        return sol, cesion, pago

    def test_revertir_borra_los_turnos_y_cancela_la_deuda(self):
        from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService

        sol, cesion, pago = self._solicitud_antigua_aplicada()
        self.assertEqual(Turno.objects.filter(tipo_cambio='CAMBIO DESCANSO').count(), 4)

        sol = SolicitudCambio.objects.select_related('doblada').get(id=sol.id)
        CambioDescansoAplicacionService.revertir(sol)

        self.assertEqual(
            Turno.objects.filter(tipo_cambio='CAMBIO DESCANSO').count(), 0,
            'no puede quedar la doblada puesta después de revertir')
        self.assertFalse(
            DeudaCorporativa.objects.filter(solicitud_origen=sol, estado='activa').exists(),
            'la deuda debe quedar cancelada')

    def test_no_borra_turnos_ajenos_de_esas_fechas(self):
        """El fallback filtra por `tipo_cambio`: un turno normal del mismo día debe sobrevivir."""
        from solicitudes.services.cambio_descanso_aplicacion_service import CambioDescansoAplicacionService

        sol, cesion, pago = self._solicitud_antigua_aplicada()
        # Un tercero con turno propio ese mismo día, y un turno base del receptor en otra fecha.
        u3 = User.objects.create_user(username='tercero.aud', password='x')
        tercero = Empleado.objects.create(
            user=u3, nombre='Ter', apellido='Aud', cedula='90003', activo=True)
        CompetenciaEmpleado.objects.create(empleado=tercero, sala=self.sala)
        ajeno = Turno.objects.create(explorador=tercero, fecha=cesion, jornada=self.am, sala=self.sala)
        propio = Turno.objects.create(explorador=self.receptor, fecha=cesion + timedelta(days=1),
                                      jornada=self.am, sala=self.sala)

        sol = SolicitudCambio.objects.select_related('doblada').get(id=sol.id)
        CambioDescansoAplicacionService.revertir(sol)

        self.assertTrue(Turno.objects.filter(id=ajeno.id).exists(),
                        'el turno de otra persona en esa fecha no se puede borrar')
        self.assertTrue(Turno.objects.filter(id=propio.id).exists(),
                        'el turno del receptor en OTRA fecha no se puede borrar')


# ===========================================================================
# D. Ciclo completo: el Consolidado de Horas vuelve a su valor de partida
# ===========================================================================
class TestCicloAprobarCancelarDejaTodoComoEstaba(AuditoriaDeudasTestCase):
    """
    Es la prueba que se haría a mano: anotar el total del Consolidado, hacer el cambio,
    cancelarlo dentro de los 30 min y comprobar que el número volvió.
    """

    def _consolidado(self, empleado):
        from turnos.services.consolidado_horas_service import ConsolidadoHorasService
        return ConsolidadoHorasService.get_consolidado(empleado)['total_horas']

    def _turnos(self, empleado, fecha):
        return {t.jornada.nombre.upper()
                for t in Turno.objects.filter(explorador=empleado, fecha=fecha).select_related('jornada')}

    def test_doblada_aprobar_y_cancelar_restaura_horas_y_turnos(self):
        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        cesion = _martes_futuro()
        pago = cesion + timedelta(days=7)

        # Estado de partida: turnos reales y consolidado en cero.
        for emp, jor in ((self.solicitante, self.pm), (self.receptor, self.am)):
            for f in (cesion, pago):
                Turno.objects.create(explorador=emp, fecha=f, jornada=jor, sala=self.sala)

        horas_sol_0 = self._consolidado(self.solicitante)
        horas_rec_0 = self._consolidado(self.receptor)
        turnos_0 = {
            (emp.id, f): self._turnos(emp, f)
            for emp in (self.solicitante, self.receptor) for f in (cesion, pago)
        }

        sol = SolicitudCambio.objects.create(
            explorador_solicitante=self.solicitante,
            explorador_receptor=self.receptor,
            tipo_cambio=self.tipo_doblada,
            estado='aprobada',
            fecha_cambio_turno=cesion,
            comentario='Ciclo completo',
        )
        DobladaDetalle.objects.create(
            solicitud=sol, fecha_pago=pago, tipo_cesion='cesion_completa',
            empleado_receptor=self.receptor,
        )

        ok, msg = DobladaStrategy().aplicar_cambios(sol)
        self.assertTrue(ok, msg)

        # Durante: alguien dobla y alguien acumuló horas.
        cache.clear()
        self.assertEqual(self._turnos(self.receptor, cesion), {'AM', 'PM'}, 'el receptor debe doblar')
        self.assertGreater(
            self._consolidado(self.solicitante) + self._consolidado(self.receptor),
            horas_sol_0 + horas_rec_0,
            'la doblada debe haber sumado horas al consolidado')

        # Cancelación dentro de la ventana de 30 min.
        sol = SolicitudCambio.objects.select_related('doblada').get(id=sol.id)
        DobladaAplicacionService.revertir_doblada_aplicada(sol)
        sol.estado = 'cancelada'
        sol.save()
        cache.clear()

        self.assertEqual(self._consolidado(self.solicitante), horas_sol_0,
                         'el consolidado del solicitante debe volver a su valor de partida')
        self.assertEqual(self._consolidado(self.receptor), horas_rec_0,
                         'el consolidado del receptor debe volver a su valor de partida')
        for (emp_id, f), jornadas in turnos_0.items():
            emp = self.solicitante if emp_id == self.solicitante.id else self.receptor
            self.assertEqual(self._turnos(emp, f), jornadas,
                             f'los turnos de {emp.nombre} en {f} deben quedar como al inicio')


# ===========================================================================
# E. El snapshot debe cubrir el día de devolución en semana (pago sábado AMBAS)
# ===========================================================================
class TestSnapshotCubreFechaPagoSemana(TestGuardNoBloqueaDeudaLegitima):
    """`aplicar_pago_residual_semana` muta un TERCER día (fecha_pago_semana).

    Si ese día no entra en el snapshot, la cancelación a 30 min no lo revierte: el receptor
    queda doblado sin solicitud que lo respalde y con su deuda ya cancelada. Además las claves
    del snapshot son la fuente de `_pares_afectados`, así que sin él tampoco se reconcilia ni
    se invalida su caché.
    """

    def _turnos(self, empleado, fecha):
        return sorted(
            Turno.objects.filter(explorador=empleado, fecha=fecha)
            .values_list('jornada__nombre', flat=True)
        )

    def test_snapshot_incluye_ambos_exploradores_en_fecha_pago_semana(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        sol, detalle = self._solicitud_pago_sabado_ambas()
        snapshot = DobladaAplicacionService.capturar_snapshot_turnos_previos(sol, detalle)

        semana = detalle.fecha_pago_semana.isoformat()
        self.assertIn(f'{self.solicitante.id}:{semana}', snapshot)
        self.assertIn(f'{self.receptor.id}:{semana}', snapshot)

    def test_revertir_restaura_el_dia_de_devolucion_en_semana(self):
        from solicitudes.services.doblada_aplicacion_service import DobladaAplicacionService

        sol, detalle = self._solicitud_pago_sabado_ambas()
        semana = detalle.fecha_pago_semana
        Turno.objects.create(explorador=self.solicitante, fecha=semana,
                             jornada=self.pm, sala=self.sala)
        Turno.objects.create(explorador=self.receptor, fecha=semana,
                             jornada=self.am, sala=self.sala)

        snapshot = DobladaAplicacionService.capturar_snapshot_turnos_previos(sol, detalle)
        DobladaAplicacionService.aplicar_pago_residual_semana(sol, detalle)

        self.assertEqual(self._turnos(self.receptor, semana), ['AM', 'PM'],
                         'el receptor debe quedar doblado ese día para devolver la jornada')
        self.assertEqual(self._turnos(self.solicitante, semana), [],
                         'el solicitante descansa su jornada ese día')

        DobladaAplicacionService.restaurar_turnos_desde_snapshot(snapshot)

        self.assertEqual(self._turnos(self.receptor, semana), ['AM'],
                         'tras cancelar, el receptor no puede seguir doblado en el día residual')
        self.assertEqual(self._turnos(self.solicitante, semana), ['PM'],
                         'tras cancelar, el solicitante recupera su jornada del día residual')
