"""
Pantalla de deudas de horas vencidas (morosos) y su comando equivalente.

Existe porque la auto-sanción es perezosa: hasta que el explorador no entra a la app, su
deuda vencida no está sancionada y no aparece en ningún informe. El supervisor necesitaba
verla —y poder aplicarla— sin depender de que el moroso entre.

Lo que se prueba aquí es sobre todo la SEPARACIÓN entre mirar y actuar: entrar a la pantalla
no puede sancionar a nadie, y el botón sí.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from empleados.models import Empleado, SancionEmpleado
from solicitudes.models import DeudaCorporativa
from solicitudes.services.deuda_corporativa_service import DeudaCorporativaService


class MorososTestBase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.sup = Empleado.objects.create(
            user=User.objects.create_user(username='sup-mor', password='x', is_staff=True),
            nombre='Supervisora', apellido='Test', cedula='sup-mor', activo=True)
        cls.moroso = Empleado.objects.create(
            user=User.objects.create_user(username='moroso', password='x'),
            nombre='Moroso', apellido='Test', cedula='moroso', activo=True, supervisor=cls.sup)
        cls.en_plazo = Empleado.objects.create(
            user=User.objects.create_user(username='enplazo', password='x'),
            nombre='EnPlazo', apellido='Test', cedula='enplazo', activo=True, supervisor=cls.sup)

    def setUp(self):
        self.hoy = timezone.localdate()
        mes_pasado = self.hoy.replace(day=1) - timedelta(days=1)
        # Vencida: mes anterior, sin pagar. Nadie la ha evaluado todavía.
        DeudaCorporativa.objects.create(
            explorador=self.moroso, minutos=30, fecha_doblada=mes_pasado, estado='activa')
        # En plazo: del mes en curso, todavía puede pagarla.
        DeudaCorporativa.objects.create(
            explorador=self.en_plazo, minutos=30, fecha_doblada=self.hoy, estado='activa')

    def _fila(self, filas, empleado):
        return next(f for f in filas if f['explorador'].id == empleado.id)


class AuditarMorososTest(MorososTestBase):

    def test_distingue_vencida_de_en_plazo(self):
        filas = DeudaCorporativaService.auditar_morosos()

        self.assertEqual(self._fila(filas, self.moroso)['estado'], 'pendiente')
        self.assertEqual(self._fila(filas, self.en_plazo)['estado'], 'en_plazo')

    def test_mirar_no_sanciona_a_nadie(self):
        """El diagnóstico tiene que poder consultarse sin efectos disciplinarios."""
        DeudaCorporativaService.auditar_morosos(aplicar=False)

        self.assertFalse(SancionEmpleado.objects.exists())

    def test_aplicar_sanciona_solo_al_vencido(self):
        DeudaCorporativaService.auditar_morosos(aplicar=True)

        self.assertTrue(SancionEmpleado.objects.filter(explorador=self.moroso).exists())
        self.assertFalse(SancionEmpleado.objects.filter(explorador=self.en_plazo).exists())

    def test_quien_ya_esta_sancionado_deja_de_contar_como_pendiente(self):
        DeudaCorporativaService.auditar_morosos(aplicar=True)

        filas = DeudaCorporativaService.auditar_morosos()
        self.assertEqual(self._fila(filas, self.moroso)['estado'], 'sancionado')

    def test_aplicar_dos_veces_no_duplica(self):
        DeudaCorporativaService.auditar_morosos(aplicar=True)
        DeudaCorporativaService.auditar_morosos(aplicar=True)

        self.assertEqual(SancionEmpleado.objects.filter(explorador=self.moroso).count(), 1)

    def test_pagar_no_hace_caer_la_sancion(self):
        """
        Antes la auditoría levantaba la sanción de quien pagaba. Ya no: el castigo se
        cumple entero y pagar solo salda el ledger. Mientras eran la misma cosa, la sanción
        funcionaba como una fianza que el moroso recuperaba cuando quería.
        """
        DeudaCorporativaService.auditar_morosos(aplicar=True)
        DeudaCorporativa.objects.filter(explorador=self.moroso).update(estado='pagada')

        DeudaCorporativaService.auditar_morosos(aplicar=True)

        self.assertEqual(
            SancionEmpleado.objects.get(explorador=self.moroso).estado, 'activa')

    def test_los_pendientes_van_primero(self):
        """El orden es la urgencia: quien debería estar bloqueado y no lo está, arriba."""
        filas = DeudaCorporativaService.auditar_morosos()

        self.assertEqual(filas[0]['explorador'].id, self.moroso.id)

    def test_el_plazo_es_el_fin_del_mes_de_la_doblada(self):
        filas = DeudaCorporativaService.auditar_morosos()
        fila = self._fila(filas, self.en_plazo)

        plazo = fila['plazo_hasta']
        self.assertEqual(plazo.month, self.hoy.month)
        self.assertNotEqual((plazo + timedelta(days=1)).month, plazo.month,
                            'debe ser el ÚLTIMO día del mes')

    def test_las_deudas_pagadas_o_canceladas_no_aparecen(self):
        DeudaCorporativa.objects.filter(explorador=self.en_plazo).update(estado='cancelada')

        filas = DeudaCorporativaService.auditar_morosos()

        self.assertNotIn(self.en_plazo.id, [f['explorador'].id for f in filas])


class MorososVistaTest(MorososTestBase):

    def setUp(self):
        super().setUp()
        self.url = reverse('sanciones_morosos')

    def test_el_supervisor_ve_la_lista_sin_sancionar_a_nadie(self):
        self.client.force_login(self.sup.user)

        resp = self.client.get(self.url)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['total_pendientes'], 1)
        self.assertEqual(resp.context['total_en_plazo'], 1)
        self.assertContains(resp, 'Moroso')
        self.assertFalse(SancionEmpleado.objects.exists(), 'un GET no puede sancionar')

    def test_el_boton_aplica_y_avisa_a_quien_sanciono(self):
        self.client.force_login(self.sup.user)

        resp = self.client.post(self.url, follow=True)

        self.assertRedirects(resp, self.url)
        self.assertTrue(SancionEmpleado.objects.filter(explorador=self.moroso).exists())
        mensajes = ' '.join(str(m) for m in resp.context['messages'])
        self.assertIn('Moroso', mensajes)

    def test_sin_pendientes_el_boton_lo_dice_y_no_miente(self):
        self.client.force_login(self.sup.user)
        self.client.post(self.url)          # ya quedan sancionados

        resp = self.client.post(self.url, follow=True)

        mensajes = ' '.join(str(m) for m in resp.context['messages'])
        self.assertIn('No había ninguna sanción pendiente', mensajes)

    def test_un_explorador_normal_no_entra(self):
        """Es una pantalla de supervisión: expone la deuda de TODOS."""
        self.client.force_login(self.moroso.user)

        resp = self.client.get(self.url)

        self.assertNotEqual(resp.status_code, 200)


class ComandoRevisarSancionesTest(MorososTestBase):

    def test_dry_run_no_escribe(self):
        call_command('revisar_sanciones_por_deuda', '--dry-run')

        self.assertFalse(SancionEmpleado.objects.exists())

    def test_sin_dry_run_aplica(self):
        call_command('revisar_sanciones_por_deuda')

        self.assertTrue(SancionEmpleado.objects.filter(explorador=self.moroso).exists())


class ContadorDashboardTest(MorososTestBase):
    """
    El contador del dashboard es una versión barata de la auditoría (2 consultas, sin N+1).
    Barato no puede significar distinto: estos tests fijan que ambos cuenten lo mismo.
    """

    def _pendientes_segun_auditoria(self):
        return sum(1 for f in DeudaCorporativaService.auditar_morosos()
                   if f['estado'] == 'pendiente')

    def test_cuenta_lo_mismo_que_la_auditoria(self):
        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(),
                         self._pendientes_segun_auditoria())

    def test_sigue_coincidiendo_despues_de_sancionar(self):
        DeudaCorporativaService.auditar_morosos(aplicar=True)

        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(), 0)
        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(),
                         self._pendientes_segun_auditoria())

    def test_una_sancion_manual_no_lo_saca_de_pendientes(self):
        """
        Una sanción manual del supervisor bloquea a la persona HOY, pero es una vía paralela
        con sus propias fechas: no salda la deuda ni sustituye a la automática. Si la
        contáramos, el moroso desaparecería del aviso mientras durase el castigo manual y
        reaparecería al terminar — justo cuando ya es tarde para enterarse.
        """
        SancionEmpleado.objects.create(
            explorador=self.moroso, supervisor=self.sup,
            fecha_inicio=self.hoy, fecha_fin=self.hoy + timedelta(days=5),
            motivo='Sanción puesta a mano por el supervisor')

        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(), 1)

    def test_la_deuda_en_plazo_no_cuenta(self):
        DeudaCorporativa.objects.filter(explorador=self.moroso).delete()

        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(), 0)


class DashboardAvisoMorososTest(MorososTestBase):

    def test_el_supervisor_ve_el_aviso_con_el_numero(self):
        self.client.force_login(self.sup.user)

        resp = self.client.get(reverse('dashboard'))

        self.assertEqual(resp.context['morosos_pendientes'], 1)
        self.assertContains(resp, 'deuda de horas vencida sin sancionar')
        self.assertContains(resp, reverse('sanciones_morosos'))

    def test_el_aviso_desaparece_cuando_no_hay_nada_que_hacer(self):
        DeudaCorporativaService.auditar_morosos(aplicar=True)
        self.client.force_login(self.sup.user)

        resp = self.client.get(reverse('dashboard'))

        self.assertEqual(resp.context['morosos_pendientes'], 0)
        self.assertNotContains(resp, 'deuda de horas vencida sin sancionar')

    def test_el_explorador_no_ve_el_aviso_aunque_sea_el_moroso(self):
        """Es información de supervisión: la deuda de TODOS, no la suya."""
        self.client.force_login(self.moroso.user)

        resp = self.client.get(reverse('dashboard'))

        self.assertEqual(resp.context['morosos_pendientes'], 0)
        self.assertNotContains(resp, 'deuda de horas vencida sin sancionar')

    def test_mirar_el_dashboard_no_sanciona_a_nadie(self):
        self.client.force_login(self.sup.user)

        self.client.get(reverse('dashboard'))

        self.assertFalse(SancionEmpleado.objects.exists())


class SancionLevantadaTest(MorososTestBase):
    """
    Qué pasa con un moroso cuya sanción levantó el supervisor.

    Es un estado propio, y hace falta distinguirlo: el sistema NO recrea una sanción
    levantada —sería anular la decisión del supervisor en el acto—, así que si se contara
    como "sin sancionar" el aviso quedaría encendido para siempre y el botón de aplicar no
    podría apagarlo. Ese era el síntoma: pulsarlo una y otra vez sin que cambiara nada.
    """

    def _sancionar_y_levantar(self):
        self.client.force_login(self.sup.user)
        self.client.post(reverse('sanciones_morosos'))
        sancion = SancionEmpleado.objects.get(
            explorador=self.moroso,
            motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO)
        sancion.levantar('Acuerdo con el explorador', supervisor=self.sup)
        return sancion

    def test_una_sancion_levantada_deja_de_contar_como_pendiente(self):
        self._sancionar_y_levantar()

        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(), 0)

    def test_al_levantarla_desaparece_del_listado_de_morosos(self):
        """
        Levantar condona la deuda del mes, así que ya no hay nada que reclamar y la fila
        se va del listado. Es el mismo objetivo que perseguía el estado 'levantada' —que
        el aviso no quedara encendido para siempre— resuelto ahora en el origen: sin deuda
        viva no hay moroso.
        """
        self._sancionar_y_levantar()

        self.assertFalse(any(f['explorador'] == self.moroso
                             for f in DeudaCorporativaService.auditar_morosos()))

    def test_la_deuda_queda_condonada_al_levantar(self):
        """Levantar perdona el hecho entero: el castigo y las horas de ese mes."""
        self._sancionar_y_levantar()

        self.assertEqual(
            DeudaCorporativa.objects.filter(explorador=self.moroso, estado='activa').count(), 0)
        self.assertEqual(
            DeudaCorporativa.objects.filter(explorador=self.moroso, estado='condonada').count(), 1)

    def test_una_levantada_antigua_con_deuda_viva_sigue_saliendo_como_levantada(self):
        """
        El estado 'levantada' sobrevive para los datos anteriores a la condonación.

        Desde que levantar condona, ninguna sanción nueva llega a este estado. Pero las
        levantadas de antes dejaron su deuda activa, y esas filas tienen que seguir
        contándose como decisión tomada: devolverlas al montón de 'pendiente' reviviría
        justo el aviso que no se podía apagar.
        """
        sancion = self._sancionar_y_levantar()
        # Se rehace a mano el estado que dejaba el código anterior: deuda viva bajo una
        # sanción levantada.
        DeudaCorporativa.objects.filter(explorador=self.moroso, estado='condonada').update(
            estado='activa', sancion_consumidora=None, fecha_consumo=None)

        fila = next(f for f in DeudaCorporativaService.auditar_morosos()
                    if f['explorador'] == self.moroso)

        self.assertEqual(fila['estado'], 'levantada')
        self.assertEqual(fila['sancion'].id, sancion.id)
        self.assertIsNotNone(fila['sancion'].levantada_en)

    def test_volver_a_pulsar_aplicar_no_la_resucita(self):
        """La decisión del supervisor manda; el botón no puede deshacerla por accidente."""
        levantada = self._sancionar_y_levantar()

        self.client.post(reverse('sanciones_morosos'))

        vivas = SancionEmpleado.objects.filter(
            explorador=self.moroso,
            motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO,
            levantada_en__isnull=True)
        self.assertFalse(vivas.exists())
        self.assertEqual(
            SancionEmpleado.objects.filter(explorador=self.moroso).count(), 1,
            'no debe crearse una segunda sanción para el mismo mes')
        self.assertEqual(levantada.periodo_mes,
                         SancionEmpleado.objects.get(explorador=self.moroso).periodo_mes)

    def test_un_mes_nuevo_impago_si_vuelve_a_contar(self):
        """
        Levantar cierra el juicio de ESE mes, no abre una amnistía. La comparación es por
        periodo justamente para esto: si mañana cierra otro mes debiendo, vuelve a hacer
        falta un juicio y el aviso tiene que encenderse otra vez.
        """
        self._sancionar_y_levantar()
        hace_dos_meses = self.hoy.replace(day=1) - timedelta(days=40)
        DeudaCorporativa.objects.create(
            explorador=self.moroso, minutos=30,
            fecha_doblada=hace_dos_meses, estado='activa')

        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(), 1)
        fila = next(f for f in DeudaCorporativaService.auditar_morosos()
                    if f['explorador'] == self.moroso)
        self.assertEqual(fila['estado'], 'pendiente')

    def test_el_contador_barato_y_la_auditoria_coinciden(self):
        """Se pintan en pantallas distintas; que discrepen es peor que que fallen."""
        self._sancionar_y_levantar()

        filas = DeudaCorporativaService.auditar_morosos()

        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(),
                         sum(1 for f in filas if f['estado'] == 'pendiente'))


class MesNuevoDurandoLaSancionTest(MorososTestBase):
    """
    Cerrar un mes debiendo MIENTRAS se cumple la sanción de otro mes.

    Cada mes vencido se juzga por separado, así que estar cumpliendo un castigo no exime
    del siguiente. El aviso tiene que verlo: mientras contaba "personas sin sanción
    vigente" en vez de "meses sin juzgar", esta persona salía como atendida —lo estaba,
    pero por otro mes— y su mes nuevo no aparecía por ninguna parte.

    El daño real no era el número: la pantalla esconde el botón de aplicar cuando el
    contador es cero. El supervisor no podía sancionar el mes nuevo aunque lo viera.
    """

    def setUp(self):
        super().setUp()
        self.client.force_login(self.sup.user)
        # Queda cumpliendo la sanción del mes pasado, vigente hoy.
        self.client.post(reverse('sanciones_morosos'))
        self.sancion = SancionEmpleado.objects.get(
            explorador=self.moroso,
            motivo__startswith=DeudaCorporativaService.AUTO_SANCION_PREFIJO)
        # Y aparece una deuda de OTRO mes vencido que nadie ha juzgado.
        self.mes_anterior = self.hoy.replace(day=1) - timedelta(days=40)
        DeudaCorporativa.objects.create(
            explorador=self.moroso, minutos=30,
            fecha_doblada=self.mes_anterior, estado='activa')

    def test_la_sancion_sigue_vigente(self):
        """Premisa del caso: si no lo estuviera, no habría nada que distinguir."""
        self.assertTrue(self.sancion.esta_vigente(self.hoy))

    def test_el_mes_sin_juzgar_cuenta_aunque_este_sancionado(self):
        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(), 1)

    def test_y_la_pantalla_le_ofrece_el_boton(self):
        r = self.client.get(reverse('sanciones_morosos'))

        self.assertEqual(r.context['total_pendientes'], 1)
        self.assertContains(r, 'Aplicar sanciones')

    def test_al_aplicar_se_crea_la_sancion_del_mes_nuevo(self):
        self.client.post(reverse('sanciones_morosos'))

        periodos = set(SancionEmpleado.objects
                       .filter(explorador=self.moroso, periodo_anio__isnull=False)
                       .values_list('periodo_anio', 'periodo_mes'))
        self.assertIn((self.mes_anterior.year, self.mes_anterior.month), periodos)
        self.assertEqual(len(periodos), 2, 'un juicio por cada mes vencido')

    def test_y_despues_ya_no_queda_nada_pendiente(self):
        """Aplicar tiene que apagar el aviso; si no, es el bucle que motivó todo esto."""
        self.client.post(reverse('sanciones_morosos'))

        self.assertEqual(DeudaCorporativaService.contar_pendientes_de_sancion(), 0)


class MorososVistaCorteTest(MorososTestBase):
    """
    Con `?corte=` la pantalla responde otra pregunta y deja de ser accionable.

    El riesgo que cubren estos tests es un malentendido caro: que el supervisor vea una lista
    filtrada por fecha y crea que el botón sanciona a ESOS, cuando sancionaría a todos los
    vencidos. Con corte, el botón no está y el POST tampoco pasa.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('sanciones_morosos')

    def test_muestra_solo_la_deuda_del_mes_en_curso_hasta_hoy(self):
        self.client.force_login(self.sup.user)

        resp = self.client.get(self.url, {'corte': self.hoy.isoformat()})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context['corte'], self.hoy)
        ids = [f['explorador'].id for f in resp.context['filas_corte']]
        self.assertIn(self.en_plazo.id, ids)
        self.assertNotIn(self.moroso.id, ids, 'su deuda es del mes anterior')

    def test_un_get_con_corte_no_sanciona_ni_ofrece_hacerlo(self):
        self.client.force_login(self.sup.user)

        resp = self.client.get(self.url, {'corte': self.hoy.isoformat()})

        self.assertFalse(SancionEmpleado.objects.exists())
        self.assertNotContains(resp, 'Aplicar sanciones')

    def test_el_post_con_corte_se_rechaza(self):
        self.client.force_login(self.sup.user)

        resp = self.client.post(f'{self.url}?corte={self.hoy.isoformat()}', follow=True)

        self.assertFalse(SancionEmpleado.objects.exists())
        mensajes = ' '.join(str(m) for m in resp.context['messages'])
        self.assertIn('solo de consulta', mensajes)

    def test_una_fecha_con_basura_se_ignora_y_cae_a_la_vista_normal(self):
        self.client.force_login(self.sup.user)

        resp = self.client.get(self.url, {'corte': 'ayer'})

        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(resp.context.get('corte'))
        self.assertEqual(resp.context['total_pendientes'], 1)

    def test_sin_corte_la_pantalla_sigue_siendo_la_de_siempre(self):
        self.client.force_login(self.sup.user)

        resp = self.client.get(self.url)

        self.assertIsNone(resp.context.get('corte'))
        self.assertContains(resp, 'Aplicar sanciones')

