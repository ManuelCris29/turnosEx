"""
Tests de la GESTIÓN de días especiales (temporadas, festivos y mantenimiento).

Lo que se protege aquí:
  1. El guardado es "borrar el año y recrear": un rechazo NUNCA puede dejar el año
     borrado, y un fallo a mitad NUNCA puede confirmarse a medias.
  2. Vaciar un año solo ocurre cuando se pide explícitamente (`permitir_vacio`).
  3. `mes` y `año_planificacion` son derivados de `fecha`: editar la fecha los
     resincroniza, o el registro se vuelve invisible en su año real.
  4. El mantenimiento automático respeta los festivos aunque todavía no se hayan
     guardado — es el caso normal al planificar el año siguiente.
  5. Las pantallas de admin no son alcanzables por un explorador.
"""
from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase, Client

from turnos.models import DiaEspecial
from turnos.services.dia_especial_service import DiaEspecialService
from turnos.services.temporada_service import TemporadaService


ANIO = 2033


class GuardadoNoDestructivoTest(TestCase):
    """Un guardado rechazado o fallido no puede llevarse por delante el año."""

    def setUp(self):
        cache.clear()
        DiaEspecial.objects.create(fecha=date(ANIO, 1, 6), tipo='festivo')
        DiaEspecial.objects.create(fecha=date(ANIO, 3, 3), tipo='temporada', es_temporada=True)

    def _festivos(self):
        return DiaEspecial.objects.filter(tipo='festivo', fecha__year=ANIO).count()

    def test_seleccion_vacia_se_rechaza_sin_borrar_nada(self):
        exito, mensaje = DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {})

        self.assertFalse(exito)
        self.assertIn('No se seleccionaron', mensaje)
        self.assertEqual(self._festivos(), 1, 'el festivo existente no debía tocarse')

    def test_seleccion_vacia_en_temporadas_se_rechaza_sin_borrar_nada(self):
        exito, _ = TemporadaService.guardar_temporadas_anual(ANIO, {})

        self.assertFalse(exito)
        self.assertEqual(DiaEspecial.objects.filter(es_temporada=True, fecha__year=ANIO).count(), 1)

    def test_anio_fuera_de_rango_se_rechaza_sin_borrar_nada(self):
        exito, mensaje = DiaEspecialService.guardar_dias_especiales_anual('festivo', 1999, {1: [1]})

        self.assertFalse(exito)
        self.assertIn('Año inválido', mensaje)
        self.assertEqual(self._festivos(), 1)

    def test_tipo_invalido_se_rechaza_sin_borrar_nada(self):
        exito, mensaje = DiaEspecialService.guardar_dias_especiales_anual('vacaciones', ANIO, {1: [1]})

        self.assertFalse(exito)
        self.assertIn('Tipo inválido', mensaje)
        self.assertEqual(self._festivos(), 1)

    def test_un_fallo_a_mitad_revierte_el_borrado(self):
        """Si algo revienta escribiendo, el año queda como estaba: nada a medias."""
        with patch.object(DiaEspecial.objects, 'update_or_create', side_effect=RuntimeError('boom')):
            exito, mensaje = DiaEspecialService.guardar_dias_especiales_anual(
                'festivo', ANIO, {5: [1, 2, 3]}
            )

        self.assertFalse(exito)
        self.assertIn('Error al guardar', mensaje)
        self.assertEqual(self._festivos(), 1, 'el rollback debía devolver el festivo original')
        self.assertTrue(DiaEspecial.objects.filter(fecha=date(ANIO, 1, 6)).exists())

    def test_limpiar_anio_explicito_si_vacia(self):
        exito, mensaje = DiaEspecialService.guardar_dias_especiales_anual(
            'festivo', ANIO, {}, permitir_vacio=True
        )

        self.assertTrue(exito)
        self.assertIn('eliminaron', mensaje)
        self.assertEqual(self._festivos(), 0)
        # La temporada del mismo año es de otro tipo: no se toca.
        self.assertEqual(DiaEspecial.objects.filter(es_temporada=True, fecha__year=ANIO).count(), 1)

    def test_guardar_reemplaza_el_anio_sin_tocar_temporadas(self):
        exito, _ = DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {7: [20, 21]})

        self.assertTrue(exito)
        festivos = DiaEspecial.objects.filter(tipo='festivo', fecha__year=ANIO).order_by('fecha')
        self.assertEqual([f.fecha for f in festivos], [date(ANIO, 7, 20), date(ANIO, 7, 21)])
        self.assertTrue(DiaEspecial.objects.filter(fecha=date(ANIO, 3, 3), es_temporada=True).exists())

    def test_guardar_dos_veces_no_duplica(self):
        for _ in range(2):
            cache.clear()  # el lock anti doble-submit no es lo que se prueba aquí
            DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {7: [20]})

        self.assertEqual(DiaEspecial.objects.filter(fecha=date(ANIO, 7, 20), tipo='festivo').count(), 1)

    def test_una_fecha_admite_temporada_y_festivo_a_la_vez(self):
        cache.clear()
        TemporadaService.guardar_temporadas_anual(ANIO, {12: [25]})
        cache.clear()
        DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {12: [25]})

        self.assertEqual(DiaEspecial.objects.filter(fecha=date(ANIO, 12, 25)).count(), 2)


class UnicidadFechaTipoTest(TestCase):

    def test_no_se_puede_duplicar_la_misma_fecha_y_tipo(self):
        DiaEspecial.objects.create(fecha=date(ANIO, 1, 1), tipo='festivo')

        with self.assertRaises(IntegrityError):
            DiaEspecial.objects.create(fecha=date(ANIO, 1, 1), tipo='festivo')


class CamposDerivadosTest(TestCase):
    """`mes` y `año_planificacion` se recalculan siempre desde `fecha`."""

    def test_se_rellenan_al_crear(self):
        dia = DiaEspecial.objects.create(fecha=date(ANIO, 4, 9), tipo='festivo')

        self.assertEqual(dia.mes, 4)
        self.assertEqual(dia.año_planificacion, ANIO)

    def test_cambiar_la_fecha_resincroniza_el_anio(self):
        dia = DiaEspecial.objects.create(fecha=date(ANIO, 1, 1), tipo='festivo')

        dia.fecha = date(ANIO + 1, 2, 3)
        dia.save()
        dia.refresh_from_db()

        self.assertEqual(dia.año_planificacion, ANIO + 1)
        self.assertEqual(dia.mes, 2)

    def test_es_temporada_se_deriva_del_tipo(self):
        """El CRUD admin no expone `es_temporada`: no puede quedar contradiciendo a `tipo`."""
        dia = DiaEspecial.objects.create(fecha=date(ANIO, 6, 1), tipo='temporada')
        self.assertTrue(dia.es_temporada)
        self.assertEqual(TemporadaService.obtener_dias_temporada_por_mes(ANIO), {6: [1]})

        dia.tipo = 'festivo'
        dia.save()
        dia.refresh_from_db()
        self.assertFalse(dia.es_temporada)

    def test_el_dia_movido_de_anio_aparece_en_su_anio_nuevo(self):
        dia = DiaEspecial.objects.create(fecha=date(ANIO, 1, 1), tipo='festivo')
        dia.fecha = date(ANIO + 1, 1, 1)
        dia.save()

        por_mes = DiaEspecialService.obtener_dias_por_tipo_por_mes('festivo', ANIO + 1)
        self.assertEqual(por_mes, {1: [1]})
        self.assertEqual(DiaEspecialService.obtener_dias_por_tipo_por_mes('festivo', ANIO), {})


class MantenimientoAutomaticoTest(TestCase):

    def test_evita_los_festivos_calculados_aunque_no_esten_guardados(self):
        """
        El caso normal: se planifica el año siguiente y los festivos aún no se han
        guardado. El cálculo debe usarlos igual, no tratar el año como si no tuviera.
        """
        self.assertFalse(DiaEspecial.objects.filter(tipo='festivo', fecha__year=ANIO).exists())

        por_mes = DiaEspecialService.calcular_dias_mantenimiento_automatico(ANIO)
        fechas_mant = {date(ANIO, mes, dia) for mes, dias in por_mes.items() for dia in dias}

        festivos = DiaEspecialService.calcular_festivos_automaticos(ANIO)
        fechas_festivos = {date(ANIO, mes, dia) for mes, dias in festivos.items() for dia in dias}

        self.assertTrue(fechas_festivos, 'el año debe tener festivos calculables')
        self.assertEqual(fechas_mant & fechas_festivos, set(),
                         'ningún mantenimiento puede caer en un festivo')

    def test_evita_los_festivos_guardados(self):
        # 2033-01-03 es lunes; marcarlo festivo empuja el mantenimiento al martes.
        lunes = date(ANIO, 1, 3)
        self.assertEqual(lunes.weekday(), 0)
        DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {1: [3]})

        por_mes = DiaEspecialService.calcular_dias_mantenimiento_automatico(ANIO)

        self.assertNotIn(3, por_mes.get(1, []))
        self.assertIn(4, por_mes.get(1, []))

    def test_rechaza_anios_fuera_de_rango(self):
        with self.assertRaises(ValueError):
            DiaEspecialService.calcular_dias_mantenimiento_automatico(1999)
        with self.assertRaises(ValueError):
            DiaEspecialService.calcular_festivos_automaticos(9999)


class AccesoVistasTest(TestCase):

    def setUp(self):
        cache.clear()
        self.explorador = User.objects.create_user('explorador', password='x')
        self.admin = User.objects.create_user('admin', password='x', is_staff=True)

    def test_explorador_no_entra_al_listado_admin(self):
        self.client.force_login(self.explorador)
        self.assertEqual(self.client.get('/turnos/dias-especiales-admin/').status_code, 403)

    def test_explorador_no_entra_a_las_paginas_anuales(self):
        self.client.force_login(self.explorador)
        for url in ('/turnos/dias-especiales/temporadas-anual/',
                    '/turnos/dias-especiales/festivos-mantenimiento-anual/'):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_explorador_no_usa_los_endpoints_de_calculo(self):
        self.client.force_login(self.explorador)
        for url in (f'/turnos/api/calcular-festivos-automatico/?anio={ANIO}',
                    f'/turnos/api/calcular-mantenimiento-automatico/?anio={ANIO}'):
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_admin_entra_a_todas(self):
        self.client.force_login(self.admin)
        for url in ('/turnos/dias-especiales-admin/',
                    '/turnos/dias-especiales/temporadas-anual/',
                    '/turnos/dias-especiales/festivos-mantenimiento-anual/'):
            self.assertEqual(self.client.get(url).status_code, 200, url)


class AnioFueraDeRangoEnVistasTest(TestCase):
    """Un año imposible en la URL debe degradar al año por defecto, no reventar."""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user('admin2', password='x', is_staff=True)
        self.client.force_login(self.admin)

    def test_festivos_con_anio_bajo_no_revienta(self):
        respuesta = self.client.get('/turnos/dias-especiales/festivos-mantenimiento-anual/?anio=1999')
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotEqual(respuesta.context['anio_seleccionado'], 1999)

    def test_festivos_con_anio_absurdo_no_revienta(self):
        respuesta = self.client.get('/turnos/dias-especiales/festivos-mantenimiento-anual/?anio=999999')
        self.assertEqual(respuesta.status_code, 200)

    def test_temporadas_con_anio_bajo_no_revienta(self):
        respuesta = self.client.get('/turnos/dias-especiales/temporadas-anual/?anio=1999')
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotEqual(respuesta.context['anio_seleccionado'], 1999)

    def test_anio_no_numerico_no_revienta(self):
        respuesta = self.client.get('/turnos/dias-especiales/temporadas-anual/?anio=abc')
        self.assertEqual(respuesta.status_code, 200)


class SelectorDeAniosTest(TestCase):

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user('admin3', password='x', is_staff=True)
        self.client.force_login(self.admin)

    def test_un_anio_solo_con_festivos_es_seleccionable(self):
        """Antes el selector solo listaba años con temporadas: los demás eran inalcanzables."""
        anio_lejano = 2041
        DiaEspecial.objects.create(fecha=date(anio_lejano, 5, 1), tipo='festivo')

        respuesta = self.client.get('/turnos/dias-especiales-admin/')

        self.assertIn(anio_lejano, respuesta.context['anios_disponibles'])
