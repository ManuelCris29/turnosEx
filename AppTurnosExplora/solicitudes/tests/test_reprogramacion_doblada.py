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
from solicitudes.models import SolicitudCambio, DeudaCorporativa, ReprogramacionDiaDoblada
from solicitudes.services.reprogramacion_doblada_service import ReprogramacionDobladaService as RS
from solicitudes.tests.test_matriz_dobladas import MatrizDobladasTestCase, FECHA_CESION, FECHA_PAGO
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
        from solicitudes.services.strategies.doblada_permanente_strategy import DobladaPermanenteStrategy
        from solicitudes.services.doblada_permanente_aplicacion_service import DobladaPermanenteAplicacionService as DPAS

        cache.clear()
        tipo = TipoSolicitudCambio.objects.create(nombre='DOBLADA PERMANENTE')
        am = self.jornada_am
        pm = self.jornada_pm
        # sol PM, rec AM (contrarios). Reusar emisor(PM)/receptor(AM) del fixture.
        self._asignar_jornada_base(self.emisor, pm)
        self._asignar_jornada_base(self.receptor, am)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.emisor, sala=self.sala)
        CompetenciaEmpleado.objects.get_or_create(empleado=self.receptor, sala=self.sala)
        hoy = date.today()
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
        from django.test import Client
        from django.urls import reverse
        from django.core.cache import cache
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
