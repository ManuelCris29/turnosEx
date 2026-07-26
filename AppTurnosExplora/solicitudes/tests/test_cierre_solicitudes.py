"""
Cierre semanal de solicitudes: lógica de ventana/cutoff (congelando `ahora`).
"""
from datetime import date, datetime, time, timedelta

from django.test import TestCase
from django.utils import timezone

from solicitudes.models import CierreSolicitudesConfig, CierreSemanaOverride
from solicitudes.services.cierre_solicitudes_service import CierreSolicitudesService as CS
from turnos.models import DiaEspecial


def _aware(d, hh, mm=0):
    return timezone.make_aware(datetime.combine(d, time(hh, mm)))


class CierreSolicitudesServiceTest(TestCase):
    def setUp(self):
        self.lunes = date(2026, 8, 3)
        self.assertEqual(self.lunes.weekday(), 0)  # sanity: es lunes
        self.jue = self.lunes + timedelta(days=3)   # 06
        self.vie = self.lunes + timedelta(days=4)   # 07
        self.sab = self.lunes + timedelta(days=5)   # 08
        self.dom = self.lunes + timedelta(days=6)   # 09
        self.lun_sig = self.lunes + timedelta(days=7)   # 10 (primer día hábil)
        self.mar_sig = self.lunes + timedelta(days=8)   # 11
        self.mie_sig = self.lunes + timedelta(days=9)   # 12

    def _habilitar(self, dia='jueves', hora=time(14, 0)):
        cfg = CierreSolicitudesConfig.obtener()
        cfg.habilitado = True
        cfg.dia_cierre = dia
        cfg.hora_cierre = hora
        cfg.save()

    def test_deshabilitado_no_bloquea(self):
        # Config por defecto: habilitado=False.
        f, _ = CS.validar_fechas([self.sab, self.dom, self.lun_sig], ahora=_aware(self.jue, 15))
        self.assertIsNone(f)

    def test_jueves_antes_del_cutoff_permite(self):
        self._habilitar('jueves', time(14, 0))
        ahora = _aware(self.lunes + timedelta(days=2), 10)  # miércoles 10:00
        for t in (self.vie, self.sab, self.dom, self.lun_sig):
            self.assertFalse(CS.fecha_bloqueada(t, ahora), t)

    def test_jueves_despues_del_cutoff_bloquea_ventana(self):
        self._habilitar('jueves', time(14, 0))
        ahora = _aware(self.jue, 14, 1)  # jueves 14:01
        for t in (self.jue, self.vie, self.sab, self.dom, self.lun_sig):
            self.assertTrue(CS.fecha_bloqueada(t, ahora), t)
        for t in (self.mar_sig, self.mie_sig):  # más allá de la ventana → permitido
            self.assertFalse(CS.fecha_bloqueada(t, ahora), t)

    def test_lunes_mantenimiento_corre_al_martes(self):
        self._habilitar('jueves', time(14, 0))
        DiaEspecial.objects.create(fecha=self.lun_sig, tipo='mantenimiento', activo=True)
        ahora = _aware(self.jue, 15)
        self.assertTrue(CS.fecha_bloqueada(self.mar_sig, ahora))   # primer hábil = martes
        self.assertFalse(CS.fecha_bloqueada(self.mie_sig, ahora))  # miércoles ya libre

    def test_lunes_festivo_corre_al_martes(self):
        self._habilitar('jueves', time(14, 0))
        DiaEspecial.objects.create(fecha=self.lun_sig, tipo='festivo', activo=True)
        ahora = _aware(self.jue, 15)
        self.assertTrue(CS.fecha_bloqueada(self.mar_sig, ahora))
        self.assertFalse(CS.fecha_bloqueada(self.mie_sig, ahora))

    def test_dias_intermedios_no_habiles_tambien_se_bloquean(self):
        """La ventana es un rango CONTINUO: si el primer hábil se corre al martes, el lunes
        (festivo) sigue dentro de la ventana y también debe bloquearse."""
        self._habilitar('jueves', time(14, 0))
        DiaEspecial.objects.create(fecha=self.lun_sig, tipo='festivo', activo=True)
        ahora = _aware(self.jue, 15)
        for t in (self.jue, self.vie, self.sab, self.dom, self.lun_sig, self.mar_sig):
            self.assertTrue(CS.fecha_bloqueada(t, ahora), t)
        self.assertFalse(CS.fecha_bloqueada(self.mie_sig, ahora))

    def test_ventana_con_lunes_y_martes_no_habiles(self):
        """Lunes y martes no hábiles → primer hábil miércoles; lunes y martes quedan dentro."""
        self._habilitar('jueves', time(14, 0))
        DiaEspecial.objects.create(fecha=self.lun_sig, tipo='festivo', activo=True)
        DiaEspecial.objects.create(fecha=self.mar_sig, tipo='mantenimiento', activo=True)
        ahora = _aware(self.jue, 15)
        for t in (self.lun_sig, self.mar_sig, self.mie_sig):
            self.assertTrue(CS.fecha_bloqueada(t, ahora), t)
        self.assertFalse(CS.fecha_bloqueada(self.mie_sig + timedelta(days=1), ahora))

    def test_cierre_primer_habil_cubre_el_finde_completo(self):
        """Con `primer_habil` la ventana va del jueves al primer día hábil, pero el bloqueo solo
        se activa el primer día hábil a la hora configurada."""
        self._habilitar('primer_habil', time(14, 0))
        # Antes del lunes 14:00 no bloquea nada del finde.
        for t in (self.jue, self.vie, self.sab, self.dom, self.lun_sig):
            self.assertFalse(CS.fecha_bloqueada(t, _aware(self.dom, 23)), t)
        # Tras el lunes 14:00 la ventana completa queda cerrada.
        ahora = _aware(self.lun_sig, 14, 1)
        for t in (self.jue, self.vie, self.sab, self.dom, self.lun_sig):
            self.assertTrue(CS.fecha_bloqueada(t, ahora), t)
        self.assertFalse(CS.fecha_bloqueada(self.mar_sig, ahora))

    def test_cierre_domingo_solo_bloquea_dom_y_primer_habil(self):
        self._habilitar('domingo', time(14, 0))
        ahora = _aware(self.dom, 15)  # domingo 15:00
        self.assertFalse(CS.fecha_bloqueada(self.vie, ahora))
        self.assertFalse(CS.fecha_bloqueada(self.sab, ahora))
        self.assertTrue(CS.fecha_bloqueada(self.dom, ahora))
        self.assertTrue(CS.fecha_bloqueada(self.lun_sig, ahora))

    def test_override_por_semana(self):
        self._habilitar('jueves', time(14, 0))  # default jueves
        CierreSemanaOverride.objects.create(
            semana_lunes=self.lunes, habilitado=True, dia_cierre='viernes', hora_cierre=time(12, 0))
        # Con override viernes 12:00: el jueves 14:01 aún NO bloquea el sábado (cierra el viernes).
        self.assertFalse(CS.fecha_bloqueada(self.sab, _aware(self.jue, 15)))
        # Tras el viernes 12:00 sí.
        self.assertTrue(CS.fecha_bloqueada(self.sab, _aware(self.vie, 12, 1)))

    def test_override_deshabilita_semana(self):
        self._habilitar('jueves', time(14, 0))
        CierreSemanaOverride.objects.create(
            semana_lunes=self.lunes, habilitado=False, dia_cierre='jueves', hora_cierre=time(14, 0))
        self.assertFalse(CS.fecha_bloqueada(self.sab, _aware(self.jue, 15)))

    def test_mensaje_incluye_fecha(self):
        self._habilitar('jueves', time(14, 0))
        f, msg = CS.validar_fechas([self.mar_sig, self.sab], ahora=_aware(self.jue, 15))
        self.assertEqual(f, self.sab)
        self.assertIn(self.sab.strftime('%d/%m/%Y'), msg)

    def test_solo_bloquea_la_semana_propia_no_las_futuras(self):
        """Desde la semana actual SÍ se puede pedir para el fin de semana de una semana FUTURA;
        cada fin de semana solo se bloquea al llegar a su propia semana (tras su cierre)."""
        self._habilitar('jueves', time(14, 0))
        jue2 = self.lunes + timedelta(days=10)   # jueves semana 2
        vie2 = self.lunes + timedelta(days=11)   # viernes semana 2
        sab2 = self.lunes + timedelta(days=12)   # sábado semana 2
        # Estando en la semana 1 (jueves 14:01): el sábado de la semana 1 ya está cerrado…
        ahora_sem1 = _aware(self.jue, 14, 1)
        self.assertTrue(CS.fecha_bloqueada(self.sab, ahora_sem1))
        # …pero jue/vie/sáb de la semana 2 siguen PERMITIDOS (su cierre es el jueves de la semana 2).
        for t in (jue2, vie2, sab2):
            self.assertFalse(CS.fecha_bloqueada(t, ahora_sem1), t)
        # Al entrar a la semana 2 (su jueves 14:01), el sábado de la semana 2 ya se bloquea.
        ahora_sem2 = _aware(jue2, 14, 1)
        self.assertTrue(CS.fecha_bloqueada(sab2, ahora_sem2))


class CierreIntegracionTest(TestCase):
    """Gate en el orquestador y página de configuración (superficie real)."""

    def _sabado_pasado(self):
        hoy = date.today()
        lunes_esta = hoy - timedelta(days=hoy.weekday())
        return lunes_esta - timedelta(days=2)  # sábado de la semana pasada (cutoff ya pasó)

    def test_orquestador_bloquea_fecha_cerrada(self):
        from solicitudes.services.solicitud_orchestrator import SolicitudOrchestrator as SO
        self._sab = self._sabado_pasado()
        cfg = CierreSolicitudesConfig.obtener()
        cfg.habilitado = True; cfg.dia_cierre = 'jueves'; cfg.hora_cierre = time(14, 0); cfg.save()
        # Fecha en ventana cerrada de una semana ya pasada → cutoff < ahora → bloquea.
        resp = SO.verificar_cierre([self._sab])
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, 400)
        # Deshabilitado → no bloquea.
        cfg.habilitado = False; cfg.save()
        self.assertIsNone(SO.verificar_cierre([self._sab]))

    def test_fechas_objetivo_ct_permanente_expande(self):
        from solicitudes.services.solicitud_orchestrator import SolicitudOrchestrator as SO
        post = {'fecha_inicio': '2026-08-03', 'fecha_fin': '2026-08-12',
                'dias_seleccionados': '{"dias_semana": [0]}'}  # solo lunes
        fechas = SO._fechas_objetivo(post, 'CT PERMANENTE')
        self.assertIn(date(2026, 8, 3), fechas)   # lunes
        self.assertIn(date(2026, 8, 10), fechas)  # lunes
        self.assertNotIn(date(2026, 8, 5), fechas)  # miércoles no

    def test_pagina_config_supervisor(self):
        from django.test import Client
        from django.urls import reverse
        from django.contrib.auth.models import User
        from empleados.models import Empleado
        u = User.objects.create_user('sup.cierre', password='x', is_staff=True)
        Empleado.objects.create(user=u, nombre='Sup', apellido='C', cedula='9001', activo=True)
        c = Client(); c.force_login(u)
        r = c.get(reverse('solicitudes:cierre_config'))
        self.assertEqual(r.status_code, 200)
        # Guardar default.
        r = c.post(reverse('solicitudes:cierre_config'),
                   {'accion': 'default', 'habilitado': 'on', 'dia_cierre': 'viernes', 'hora_cierre': '12:00'})
        self.assertEqual(r.status_code, 302)
        cfg = CierreSolicitudesConfig.obtener()
        self.assertTrue(cfg.habilitado)
        self.assertEqual(cfg.dia_cierre, 'viernes')
        # Guardar override de una semana.
        r = c.post(reverse('solicitudes:cierre_config'),
                   {'accion': 'override', 'semana_lunes': '2026-08-03', 'dia_cierre': 'sabado', 'hora_cierre': '10:00'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(CierreSemanaOverride.objects.filter(semana_lunes=date(2026, 8, 3)).exists())
        # Una fecha que NO es lunes se normaliza al lunes de su semana (no crea huérfanos).
        r = c.post(reverse('solicitudes:cierre_config'),
                   {'accion': 'override', 'semana_lunes': '2026-09-10', 'dia_cierre': 'viernes',
                    'hora_cierre': '11:00'})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(CierreSemanaOverride.objects.filter(semana_lunes=date(2026, 9, 7)).exists())
        self.assertFalse(CierreSemanaOverride.objects.filter(semana_lunes=date(2026, 9, 10)).exists())

    def test_fechas_del_post_recoge_valores_repetidos(self):
        from django.http import QueryDict
        from solicitudes.services.solicitud_request_parser import SolicitudRequestParser
        qd = QueryDict(mutable=True)
        qd.setlist('fecha_solicitud', ['2026-08-08', '2026-08-09'])
        fechas = SolicitudRequestParser.get_fechas_del_post(qd)
        self.assertIn(date(2026, 8, 8), fechas)
        self.assertIn(date(2026, 8, 9), fechas)
