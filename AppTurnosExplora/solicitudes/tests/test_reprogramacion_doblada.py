"""
Reprogramación del día de doblada por inasistencia (simétrica y auditable).

Verifica que, en una doblada aprobada A↔B, si UNA persona no cumple su día:
- se ANULA su día (soft-delete: el Turno sigue existiendo para auditoría, pero no cuenta activo)
  y se le RESTA su deuda de 30 min, SIN tocar al otro explorador;
- al PROGRAMAR el día nuevo, dobla esa fecha y se le REGENERA la deuda de 30 min → neto: 1 sola
  deuda activa, en el día que sí dobla.
"""
from datetime import date, timedelta

from django.utils import timezone

from empleados.models import CompetenciaEmpleado
from solicitudes.models import DeudaCorporativa, ReprogramacionDiaDoblada, SolicitudCambio
from solicitudes.services.reprogramacion_doblada_service import ReprogramacionDobladaService as RS
from solicitudes.tests.test_d_fds import DFDSBaseTest, _findes_de_mes
from solicitudes.tests.test_matriz_dobladas import FECHA_CESION, FECHA_PAGO, MatrizDobladasTestCase
from turnos.models import Turno
from turnos.services.turno_service import TurnoService as TS


class ReprogramacionDobladaTest(MatrizDobladasTestCase):
    def _crear_aplicar_doblada(self):
        self._asignar_jornada_base(self.emisor, self.jornada_pm)   # emisor PM
        self._asignar_jornada_base(self.receptor, self.jornada_am)  # receptor AM
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)
        sol, msg = self.strategy.crear_solicitud(self._datos(tipo_cambio=self.tipo_doblada))
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        sol = SolicitudCambio.objects.select_related('doblada').get(id=sol.id)
        ok, m = self.strategy.aplicar_cambios(sol)
        self.assertTrue(ok, m)
        return sol

    def _activas(self, emp):
        return DeudaCorporativa.objects.filter(explorador=emp, estado='activa').count()

    def _dia_habil_libre(self):
        """Un día hábil del mismo mes, distinto a cesión/pago, para reprogramar."""
        d = FECHA_PAGO + timedelta(days=1)
        while d.weekday() >= 5 or d in (FECHA_CESION, FECHA_PAGO) or d.month != FECHA_PAGO.month:
            d += timedelta(days=1)
        return d

    def test_receptor_no_cumple_su_dia_reprograma(self):
        from django.core.cache import cache
        sol = self._crear_aplicar_doblada()
        # Tras aplicar: receptor dobla en cesión, emisor dobla en pago; ambos con 30 min.
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).count(), 2)
        self.assertEqual(self._activas(self.receptor), 1)
        self.assertEqual(self._activas(self.emisor), 1)

        # El receptor no cumple su día (cesión).
        reprog = RS.registrar_inasistencia(sol, self.receptor, supervisor=self.emisor, motivo='Enfermedad')
        cache.clear()
        # Soft-delete auditable: activo = 0, pero all_objects lo conserva con motivo.
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).count(), 0)
        anulados = Turno.all_objects.filter(explorador=self.receptor, fecha=FECHA_CESION, anulado=True)
        self.assertEqual(anulados.count(), 2)
        self.assertTrue(all('reprogramaci' in (t.motivo_anulacion or '').lower() for t in anulados))
        # Su deuda de 30 min de ese día queda cancelada; el emisor intacto.
        self.assertEqual(self._activas(self.receptor), 0)
        self.assertEqual(self._activas(self.emisor), 1)
        self.assertEqual(Turno.objects.filter(explorador=self.emisor, fecha=FECHA_PAGO).count(), 2)
        self.assertEqual(reprog.estado, 'pendiente')
        # Mis Turnos: receptor ya no dobla el día original.
        self.assertNotEqual(TS.estado_dia(self.receptor, FECHA_CESION).get('jornada'), 'DOBLADA')

        # El supervisor programa el día de pago.
        nueva = self._dia_habil_libre()
        RS.programar(reprog, nueva)
        cache.clear()
        reprog.refresh_from_db()
        self.assertEqual(reprog.estado, 'pagada')
        self.assertEqual(reprog.fecha_reprogramada, nueva)
        # Ese día el receptor dobla (AM+PM) con tipo PAGO REPROGRAMADO.
        turnos_nuevos = Turno.objects.filter(explorador=self.receptor, fecha=nueva)
        self.assertEqual(turnos_nuevos.count(), 2)
        self.assertTrue(all(t.tipo_cambio == 'PAGO REPROGRAMADO' for t in turnos_nuevos))
        self.assertEqual(TS.estado_dia(self.receptor, nueva).get('jornada'), 'DOBLADA')
        # Neto: exactamente 1 deuda de 30 min activa del receptor, en la fecha nueva.
        activas = DeudaCorporativa.objects.filter(explorador=self.receptor, estado='activa')
        self.assertEqual(activas.count(), 1)
        self.assertEqual(activas.first().fecha_doblada, nueva)
        # El emisor sigue intacto.
        self.assertEqual(self._activas(self.emisor), 1)

    def test_emisor_no_cumple_su_dia_reprograma(self):
        """Simétrico: el emisor (primero/segundo, aquí paga en FECHA_PAGO) tampoco puede."""
        from django.core.cache import cache
        sol = self._crear_aplicar_doblada()
        reprog = RS.registrar_inasistencia(sol, self.emisor, supervisor=self.emisor, motivo='Incapacidad')
        cache.clear()
        # Emisor: su día (pago) anulado + su 30 min cancelada. Receptor intacto.
        self.assertEqual(Turno.objects.filter(explorador=self.emisor, fecha=FECHA_PAGO).count(), 0)
        self.assertEqual(Turno.all_objects.filter(explorador=self.emisor, fecha=FECHA_PAGO, anulado=True).count(), 2)
        self.assertEqual(self._activas(self.emisor), 0)
        self.assertEqual(self._activas(self.receptor), 1)
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).count(), 2)

        nueva = self._dia_habil_libre()
        RS.programar(reprog, nueva)
        cache.clear()
        self.assertEqual(TS.estado_dia(self.emisor, nueva).get('jornada'), 'DOBLADA')
        self.assertEqual(self._activas(self.emisor), 1)
        self.assertEqual(self._activas(self.receptor), 1)  # receptor nunca se tocó

    def test_puede_cancelar_segun_estado(self):
        sol = self._crear_aplicar_doblada()
        # Ambas fechas son futuras (FECHA_CESION/PAGO del mes siguiente) → cancelar permitido.
        self.assertTrue(RS.puede_cancelar(sol))

    def test_doblada_permanente_reprograma_una_fecha(self):
        """En doblada permanente, si la persona no cumple UNA fecha específica de doblada, se
        reprograma esa fecha (anula solo ese día + su 30 min) y paga doblando otro."""
        import calendar

        from django.core.cache import cache

        from solicitudes.models import TipoSolicitudCambio
        from solicitudes.services.doblada_permanente_aplicacion_service import (
            DobladaPermanenteAplicacionService as DPAS,
        )
        from solicitudes.services.strategies.doblada_permanente_strategy import DobladaPermanenteStrategy

        cache.clear()
        tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')
        am = self.jornada_am
        pm = self.jornada_pm
        # sol PM, rec AM (contrarios). Reusar emisor(PM)/receptor(AM) del fixture.
        self._asignar_jornada_base(self.emisor, pm)
        self._asignar_jornada_base(self.receptor, am)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)
        hoy = timezone.localdate()
        anio, mes = (hoy.year + 1, 1) if hoy.month == 12 else (hoy.year, hoy.month + 1)
        fi = date(anio, mes, 1)
        ff = date(anio, mes, calendar.monthrange(anio, mes)[1])
        martes = [d for d in (fi + timedelta(n) for n in range((ff - fi).days + 1)) if d.weekday() == 1]
        miercoles = [d for d in (fi + timedelta(n) for n in range((ff - fi).days + 1)) if d.weekday() == 2]
        # cesión: receptor cubre martes[0] y martes[1]; devolución: solicitante dobla miércoles[0], [1].
        strat = DobladaPermanenteStrategy()
        sol, msg = strat.crear_solicitud({
            'explorador_solicitante': self.emisor, 'explorador_receptor': self.receptor,
            'tipo_cambio': tipo, 'comentario': 'perm',
            'fecha_inicio': fi.strftime('%Y-%m-%d'), 'fecha_fin': ff.strftime('%Y-%m-%d'),
            'dias_cesion': ['1'], 'dias_devolucion': ['2'],
            'fechas_cesion': ','.join(d.strftime('%Y-%m-%d') for d in martes[:2]),
            'fechas_devolucion': ','.join(d.strftime('%Y-%m-%d') for d in miercoles[:2]),
        })
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'; sol.fecha_resolucion = timezone.now(); sol.save()
        sol = SolicitudCambio.objects.select_related('doblada_permanente', 'tipo_cambio').get(id=sol.id)
        DPAS.aplicar(sol, sol.doblada_permanente)
        cache.clear()

        # El receptor se dobla en martes[0] y martes[1] (cesión).
        parts = {rol: (emp, fechas) for (rol, emp, fechas) in RS.participantes_y_dias(sol)}
        self.assertEqual(set(parts['receptor'][1]), set(martes[:2]))

        # El receptor no cumple martes[0].
        reprog = RS.registrar_inasistencia(sol, self.receptor, supervisor=self.emisor,
                                           motivo='Enfermedad', fecha_original=martes[0])
        cache.clear()
        self.assertEqual(reprog.fecha_original, martes[0])
        # martes[0] anulado; martes[1] intacto (sigue doblando).
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=martes[0]).count(), 0)
        self.assertEqual(Turno.all_objects.filter(explorador=self.receptor, fecha=martes[0], anulado=True).count(), 2)
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=martes[1]).count(), 2)
        # Programar el pago en un día hábil libre.
        nueva = self._dia_habil_libre()
        RS.programar(reprog, nueva)
        cache.clear()
        self.assertEqual(TS.estado_dia(self.receptor, nueva).get('jornada'), 'DOBLADA')

    def test_flujo_ui_supervisor(self):
        """Superficie real: el supervisor registra la inasistencia y programa el pago vía las vistas."""
        from django.core.cache import cache
        from django.test import Client
        from django.urls import reverse
        sol = self._crear_aplicar_doblada()
        # Supervisor (staff) autenticado.
        self.emisor.user.is_staff = True
        self.emisor.user.save(update_fields=['is_staff'])
        c = Client()
        c.force_login(self.emisor.user)

        # 1) Página de registrar (GET) + POST inasistencia del receptor.
        r = c.get(reverse('solicitudes:reprog_registrar', args=[sol.id]))
        self.assertEqual(r.status_code, 200)
        r = c.post(reverse('solicitudes:reprog_registrar', args=[sol.id]),
                   {'seleccion': f'receptor|{FECHA_CESION.isoformat()}', 'motivo': 'Enfermedad'})
        self.assertEqual(r.status_code, 302)
        reprog = ReprogramacionDiaDoblada.objects.get(doblada_origen=sol, explorador=self.receptor)
        self.assertEqual(reprog.estado, 'pendiente')
        cache.clear()
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).count(), 0)

        # 2) Página de programar (GET) + POST con el día nuevo.
        r = c.get(reverse('solicitudes:reprog_programar', args=[reprog.id]))
        self.assertEqual(r.status_code, 200)
        nueva = self._dia_habil_libre()
        r = c.post(reverse('solicitudes:reprog_programar', args=[reprog.id]),
                   {'fecha_nueva': nueva.isoformat()})
        self.assertEqual(r.status_code, 302)
        reprog.refresh_from_db()
        self.assertEqual(reprog.estado, 'pagada')
        cache.clear()
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=nueva).count(), 2)
        self.assertEqual(DeudaCorporativa.objects.filter(explorador=self.receptor, estado='activa').count(), 1)

        # 3) La lista de reprogramaciones renderiza (ya está 'pagada' → filtrar por todos).
        r = c.get(reverse('solicitudes:reprog_list'), {'estado': 'todos'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, self.receptor.nombre)

    # ── Cancelación ──────────────────────────────────────────────────────────
    def _llegar_a_pagada(self):
        """Registra inasistencia del receptor y programa el pago; devuelve (reprog, fecha_nueva)."""
        from django.core.cache import cache
        sol = self._crear_aplicar_doblada()
        reprog = RS.registrar_inasistencia(sol, self.receptor, supervisor=self.emisor, motivo='Enf')
        nueva = self._dia_habil_libre()
        RS.programar(reprog, nueva)
        cache.clear()
        reprog.refresh_from_db()
        return reprog, nueva

    def test_deshacer_pago_restaura_turno_previo_y_vuelve_a_pendiente(self):
        """Al deshacer el pago de una reprogramación 'pagada': se anulan los turnos PAGO
        REPROGRAMADO, se restaura el turno único original (base AM del receptor) y Mis Turnos ya
        NO muestra doblada; la deuda de 30 min de ese día queda cancelada. Y lo esencial: la
        reprogramación vuelve a PENDIENTE — la persona sigue debiendo el día y se le puede volver
        a programar (antes quedaba 'cancelada' y la deuda se perdía)."""
        from django.core.cache import cache
        reprog, nueva = self._llegar_a_pagada()
        # Se guardó la jornada previa (base del receptor = AM) y ese día dobla.
        self.assertEqual(reprog.jornada_pago_previa, 'AM')
        self.assertEqual(TS.estado_dia(self.receptor, nueva).get('jornada'), 'DOBLADA')

        RS.deshacer_pago(reprog)
        cache.clear()
        reprog.refresh_from_db()

        self.assertEqual(reprog.estado, 'pendiente')
        self.assertIsNone(reprog.fecha_reprogramada)
        # Los 2 turnos de pago quedan anulados (auditables), y se recrea 1 turno normal (AM).
        activos = Turno.objects.filter(explorador=self.receptor, fecha=nueva)
        self.assertEqual(activos.count(), 1)
        self.assertIsNone(activos.first().tipo_cambio)
        self.assertEqual(activos.first().jornada.nombre, 'AM')
        self.assertEqual(
            Turno.all_objects.filter(explorador=self.receptor, fecha=nueva,
                                     anulado=True, tipo_cambio='PAGO REPROGRAMADO').count(), 2)
        # Mis Turnos: ese día vuelve a su jornada única original (AM), NO doblada.
        self.assertEqual(TS.estado_dia(self.receptor, nueva).get('jornada'), 'AM')
        # La deuda de 30 min de ese día queda cancelada.
        self.assertEqual(DeudaCorporativa.objects.filter(
            explorador=self.receptor, fecha_doblada=nueva, estado='activa').count(), 0)

    def test_deshacer_pago_es_idempotente(self):
        """Deshacer dos veces no re-procesa ni duplica turnos, y sobre todo NO encadena hasta
        'cancelada': un doble submit del botón no puede perdonar la deuda por accidente."""
        from django.core.cache import cache
        reprog, nueva = self._llegar_a_pagada()
        RS.deshacer_pago(reprog)
        cache.clear(); reprog.refresh_from_db()
        total_tras_1 = Turno.all_objects.filter(explorador=self.receptor, fecha=nueva).count()
        RS.deshacer_pago(reprog)  # segunda vez: no-op
        reprog.refresh_from_db()
        self.assertEqual(reprog.estado, 'pendiente')
        self.assertEqual(
            Turno.all_objects.filter(explorador=self.receptor, fecha=nueva).count(), total_tras_1)

    def test_reprogramar_de_nuevo_tras_deshacer_el_pago(self):
        """El caso que motivó el arreglo: se deshace un pago y la persona SÍ puede volver a
        tener día de pago programado, porque la reprogramación sigue viva en 'pendiente'."""
        reprog, nueva = self._llegar_a_pagada()
        RS.deshacer_pago(reprog)
        reprog.refresh_from_db()
        RS.programar(reprog, nueva)
        reprog.refresh_from_db()
        self.assertEqual(reprog.estado, 'pagada')
        self.assertEqual(reprog.fecha_reprogramada, nueva)
        # Un solo cargo de 30 min por el día doblado, no dos (deuda idempotente).
        self.assertEqual(DeudaCorporativa.objects.filter(
            explorador=self.receptor, fecha_doblada=nueva, estado='activa').count(), 1)

    def test_cerrar_sin_pago_exige_deshacer_el_pago_primero(self):
        """Desde 'pagada' no se puede perdonar la deuda de un golpe: quedarían turnos de pago
        vivos de una reprogramación cerrada."""
        reprog, _ = self._llegar_a_pagada()
        with self.assertRaises(ValueError):
            RS.cerrar_sin_pago(reprog)

    def test_cerrar_sin_pago_pendiente_no_toca_turnos(self):
        """Cerrar sin pago una reprogramación 'pendiente' solo cambia el estado; el día original
        no cumplido sigue anulado (fue inasistencia real)."""
        sol = self._crear_aplicar_doblada()
        reprog = RS.registrar_inasistencia(sol, self.receptor, supervisor=self.emisor, motivo='Enf')
        self.assertEqual(reprog.estado, 'pendiente')
        RS.cerrar_sin_pago(reprog)
        reprog.refresh_from_db()
        self.assertEqual(reprog.estado, 'cancelada')
        RS.cerrar_sin_pago(reprog)  # idempotente
        self.assertEqual(reprog.estado, 'cancelada')
        # El día original sigue anulado (no se restaura la doblada no cumplida).
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=FECHA_CESION).count(), 0)

    def test_dia_ya_anulado_no_vuelve_a_ofrecerse_para_reprogramar(self):
        """Tras registrar la inasistencia, ese día ya no aparece como candidato: no hay doblada
        que incumplir. Sin esto, Gestión de Solicitudes seguía ofreciendo 'Reprogramar' sobre un
        día anulado."""
        sol = self._crear_aplicar_doblada()
        RS.registrar_inasistencia(sol, self.receptor, supervisor=self.emisor)
        fechas = {rol: f for (rol, _e, f) in RS.participantes_y_dias(sol)}
        self.assertEqual(fechas['receptor'], [], 'el día anulado no debe seguir siendo reprogramable')


class ReprogramacionDFDSTest(DFDSBaseTest):
    """
    D FDS también se puede reprogramar. Lo que cambia respecto a una doblada entre semana es el
    DÍA con el que se compensa: en finde la unidad es el día completo, así que la persona no
    "agrega la jornada contraria" a un día que ya trabaja — trabaja un día de finde que tenía
    libre. El compañero no entra: su descanso ya lo tuvo el día original.
    """

    def _aplicada(self):
        sol, msg = self.strat.crear_solicitud(self._datos())
        self.assertIsNotNone(sol, msg)
        sol.estado = 'aprobada'
        sol.fecha_resolucion = timezone.now()
        sol.save()
        sol = SolicitudCambio.objects.select_related(
            'doblada', 'tipo_cambio', 'explorador_solicitante', 'explorador_receptor').get(id=sol.id)
        ok, m = self.strat.aplicar_cambios(sol)
        self.assertTrue(ok, m)
        return sol

    def _otro_dia_libre_mismo_tipo(self, referencia):
        """Otro día del mes, mismo día de la semana, en el que el solicitante descansa."""
        for f, _g in _findes_de_mes(referencia.year, referencia.month):
            if (f.weekday() == referencia.weekday() and f != referencia
                    and not TS.estado_dia(self.solicitante, f)['trabaja']
                    and not TS.dia_comprometido_por_solicitud(self.solicitante, f)):
                return f
        return None

    def test_una_d_fds_ofrece_dias_reprogramables(self):
        """Antes devolvía lista vacía: D FDS no estaba contemplada y no se podía ni empezar."""
        sol = self._aplicada()
        partes = RS.participantes_y_dias(sol)
        self.assertEqual(len(partes), 2, 'deben salir receptor y solicitante')
        por_rol = {rol: (emp, fechas) for rol, emp, fechas in partes}
        self.assertEqual(por_rol['receptor'][1], [self.ces], 'el receptor dobla en la cesión')
        self.assertEqual(por_rol['solicitante'][1], [self.pago], 'el solicitante dobla en el pago')

    def test_compensa_trabajando_otro_dia_de_finde(self):
        sol = self._aplicada()
        nueva = self._otro_dia_libre_mismo_tipo(self.pago)
        if not nueva:
            self.skipTest('El mes de prueba no ofrece otro día libre del mismo tipo')

        reprog = RS.registrar_inasistencia(sol, self.solicitante, motivo='Incapacidad')
        self.assertEqual(reprog.fecha_original, self.pago)
        # El día no cumplido queda anulado (soft-delete), no borrado.
        self.assertEqual(Turno.objects.filter(explorador=self.solicitante, fecha=self.pago).count(), 0)
        self.assertTrue(Turno.all_objects.filter(
            explorador=self.solicitante, fecha=self.pago, anulado=True).exists())

        RS.programar(reprog, nueva)
        reprog.refresh_from_db()
        self.assertEqual(reprog.estado, 'pagada')
        # Compensa con el DÍA COMPLETO del finde.
        jornadas = sorted(t.jornada.nombre.upper() for t in
                          Turno.objects.filter(explorador=self.solicitante, fecha=nueva)
                          .select_related('jornada'))
        self.assertEqual(jornadas, ['AM', 'PM'])
        # En finde no se cobran los 30 min.
        self.assertFalse(DeudaCorporativa.objects.filter(
            explorador=self.solicitante, fecha_doblada=nueva).exists())
        # Y el compañero no se ve afectado en ningún momento.
        self.assertEqual(Turno.objects.filter(explorador=self.receptor, fecha=nueva).count(), 0)

    def test_el_dia_de_compensacion_debe_ser_de_finde(self):
        sol = self._aplicada()
        reprog = RS.registrar_inasistencia(sol, self.solicitante)
        lunes = self.pago
        while lunes.weekday() != 0:
            lunes += timedelta(days=1)
        with self.assertRaises(ValueError) as cm:
            RS.programar(reprog, lunes)
        self.assertIn('sábado o un domingo', str(cm.exception))

    def test_el_dia_de_compensacion_debe_ser_el_mismo_dia_de_la_semana(self):
        """Es lo que mantiene intacta su cantidad de sábados y domingos del mes."""
        sol = self._aplicada()
        reprog = RS.registrar_inasistencia(sol, self.solicitante)
        opuesto = self.pago + timedelta(days=1 if self.pago.weekday() == 5 else -1)
        with self.assertRaises(ValueError) as cm:
            RS.programar(reprog, opuesto)
        self.assertIn('también debe ser un', str(cm.exception))

    def test_no_se_compensa_en_un_dia_que_la_persona_cedio(self):
        """
        Estar libre no basta. El día de cesión lo está cubriendo el compañero COMO EXTRA: si el
        solicitante lo trabajara, quedarían dos personas en el turno y el favor se desperdiciaría.
        """
        sol = self._aplicada()
        reprog = RS.registrar_inasistencia(sol, self.solicitante)
        self.assertFalse(TS.estado_dia(self.solicitante, self.ces)['trabaja'],
                         'sanity: ese día lo tiene libre porque lo cedió')
        with self.assertRaises(ValueError) as cm:
            RS.programar(reprog, self.ces)
        self.assertIn('ya se lo cedió', str(cm.exception))

    def test_el_calendario_del_supervisor_ofrece_dias_de_finde(self):
        """
        Regresión: el calendario marcaba elegibles solo los días con jornada única (entre semana),
        justo los que `programar` rechaza en una D FDS. Resultado: ningún día seleccionable y la
        reprogramación quedaba atascada en 'pendiente' para siempre. Ahora calendario y servicio
        comparten `validar_dia_pago`, así que lo que se pinta es exactamente lo que se acepta.
        """
        from django.test import Client
        from django.urls import reverse
        sol = self._aplicada()
        nueva = self._otro_dia_libre_mismo_tipo(self.pago)
        if not nueva:
            self.skipTest('El mes de prueba no ofrece otro día libre del mismo tipo')
        reprog = RS.registrar_inasistencia(sol, self.solicitante)

        self.u_rec.is_staff = True
        self.u_rec.save(update_fields=['is_staff'])
        c = Client()
        c.force_login(self.u_rec)
        r = c.get(reverse('solicitudes:reprog_programar', args=[reprog.id]),
                  {'anio': nueva.year, 'mes': nueva.month})
        self.assertEqual(r.status_code, 200)

        elegibles = [d['fecha'] for d in r.context['dias'] if d['valido']]
        self.assertTrue(elegibles, 'una D FDS debe ofrecer al menos un día de compensación')
        self.assertIn(nueva, elegibles)
        # Y solo días de fin de semana del mismo tipo que el no cumplido.
        for f in elegibles:
            self.assertEqual(f.weekday(), self.pago.weekday())

        # El día ofrecido es aceptado por el POST real (calendario y servicio no divergen).
        r = c.post(reverse('solicitudes:reprog_programar', args=[reprog.id]),
                   {'fecha_nueva': nueva.isoformat()})
        self.assertEqual(r.status_code, 302)
        reprog.refresh_from_db()
        self.assertEqual(reprog.estado, 'pagada')

    def test_no_se_programa_un_dia_en_el_pasado(self):
        """El calendario ya excluía el pasado, pero el POST lo aceptaba: turno y deuda retroactivos."""
        sol = self._aplicada()
        reprog = RS.registrar_inasistencia(sol, self.solicitante)
        ayer = timezone.localdate() - timedelta(days=1)
        with self.assertRaises(ValueError) as cm:
            RS.programar(reprog, ayer)
        self.assertIn('pasado', str(cm.exception))
        reprog.refresh_from_db()
        self.assertEqual(reprog.estado, 'pendiente')

    def test_mes_invalido_en_la_url_no_revienta(self):
        """?mes=abc / ?mes=13 caían en 500; ahora vuelven al mes del día no cumplido."""
        from django.test import Client
        from django.urls import reverse
        sol = self._aplicada()
        reprog = RS.registrar_inasistencia(sol, self.solicitante)
        self.u_rec.is_staff = True
        self.u_rec.save(update_fields=['is_staff'])
        c = Client()
        c.force_login(self.u_rec)
        for params in ({'mes': 'abc'}, {'mes': '13'}, {'anio': '99999'}, {'mes': '0', 'anio': 'x'}):
            r = c.get(reverse('solicitudes:reprog_programar', args=[reprog.id]), params)
            self.assertEqual(r.status_code, 200, params)
            self.assertEqual(r.context['mes'], reprog.fecha_original.month, params)

    def test_deshacer_pago_devuelve_el_dia_a_descanso(self):
        """Sin jornada previa que restaurar: la persona simplemente vuelve a descansar."""
        sol = self._aplicada()
        nueva = self._otro_dia_libre_mismo_tipo(self.pago)
        if not nueva:
            self.skipTest('El mes de prueba no ofrece otro día libre del mismo tipo')
        reprog = RS.registrar_inasistencia(sol, self.solicitante)
        RS.programar(reprog, nueva)
        RS.deshacer_pago(reprog)
        reprog.refresh_from_db()
        self.assertEqual(reprog.estado, 'pendiente')
        self.assertEqual(Turno.objects.filter(explorador=self.solicitante, fecha=nueva).count(), 0,
                         'al deshacer el pago no debe quedar ningún turno activo ese día')
