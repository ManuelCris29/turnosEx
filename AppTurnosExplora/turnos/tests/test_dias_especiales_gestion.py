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
from django.test import TestCase

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


class EdicionConcurrenteTest(TestCase):
    """
    Dos personas editando el mismo año no pueden pisarse en silencio.

    Guardar un año es "borrar y recrear" a partir de lo que envía el navegador. Sin
    protección, quien guarda segundo borra el día que acababa de añadir el primero,
    porque su formulario se cargó antes de que existiera.
    """

    def setUp(self):
        cache.clear()
        DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {1: [1]})
        cache.clear()

    def test_el_token_cambia_cuando_cambia_el_anio(self):
        antes = DiaEspecialService.token_estado('festivo', ANIO)

        DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {1: [1], 3: [24]})

        self.assertNotEqual(antes, DiaEspecialService.token_estado('festivo', ANIO))

    def test_el_token_no_confunde_tipos_ni_anios(self):
        self.assertNotEqual(DiaEspecialService.token_estado('festivo', ANIO),
                            DiaEspecialService.token_estado('mantenimiento', ANIO))
        self.assertNotEqual(DiaEspecialService.token_estado('festivo', ANIO),
                            DiaEspecialService.token_estado('festivo', ANIO + 1))

    def test_un_guardado_con_token_viejo_se_rechaza(self):
        # A y B cargan la página: ambos se llevan el mismo token.
        token_de_b = DiaEspecialService.token_estado('festivo', ANIO)

        # A agrega el 24 de marzo y guarda.
        exito_a, _ = DiaEspecialService.guardar_dias_especiales_anual(
            'festivo', ANIO, {1: [1], 3: [24]},
            token_esperado=token_de_b
        )
        self.assertTrue(exito_a)
        cache.clear()

        # B, que no vio ese cambio, guarda su versión: no debe borrar el 24 de marzo.
        exito_b, mensaje = DiaEspecialService.guardar_dias_especiales_anual(
            'festivo', ANIO, {1: [1], 7: [20]},
            token_esperado=token_de_b
        )

        self.assertFalse(exito_b)
        self.assertIn('Otra persona modificó', mensaje)
        self.assertTrue(DiaEspecial.es_festivo(date(ANIO, 3, 24)),
                        'el día que agregó A debe seguir ahí')
        self.assertFalse(DiaEspecial.es_festivo(date(ANIO, 7, 20)),
                         'el guardado rechazado no debe escribir nada')

    def test_reintentar_con_el_token_fresco_funciona(self):
        token_viejo = DiaEspecialService.token_estado('festivo', ANIO)
        DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {1: [1], 3: [24]})
        cache.clear()

        rechazado, _ = DiaEspecialService.guardar_dias_especiales_anual(
            'festivo', ANIO, {1: [1], 3: [24], 7: [20]}, token_esperado=token_viejo)
        self.assertFalse(rechazado)
        cache.clear()

        # Al recargar la página el token es el actual y el guardado pasa.
        exito, _ = DiaEspecialService.guardar_dias_especiales_anual(
            'festivo', ANIO, {1: [1], 3: [24], 7: [20]},
            token_esperado=DiaEspecialService.token_estado('festivo', ANIO))

        self.assertTrue(exito)
        self.assertTrue(DiaEspecial.es_festivo(date(ANIO, 7, 20)))

    def test_sin_token_se_guarda_igual(self):
        """Los llamadores internos (comandos, tests) no están obligados a pasarlo."""
        exito, _ = DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {1: [1], 7: [20]})

        self.assertTrue(exito)

    def test_temporadas_tambien_estan_protegidas(self):
        cache.clear()
        TemporadaService.guardar_temporadas_anual(ANIO, {3: [3]})
        token_viejo = TemporadaService.token_estado(ANIO)
        cache.clear()
        TemporadaService.guardar_temporadas_anual(ANIO, {3: [3], 4: [4]})
        cache.clear()

        exito, mensaje = TemporadaService.guardar_temporadas_anual(
            ANIO, {3: [3], 5: [5]}, token_esperado=token_viejo)

        self.assertFalse(exito)
        self.assertIn('Otra persona modificó', mensaje)
        self.assertTrue(DiaEspecial.es_temporada_en(date(ANIO, 4, 4)))


class EdicionConcurrenteEnLaPaginaTest(TestCase):
    """El token tiene que viajar de verdad: vista → campo oculto → POST → servicio."""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user('admin5', password='x', is_staff=True)
        self.client.force_login(self.admin)
        DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {1: [1]})
        cache.clear()

    def test_la_pagina_publica_el_token_actual(self):
        respuesta = self.client.get(f'/turnos/dias-especiales/festivos-mantenimiento-anual/?tipo=festivo&anio={ANIO}')

        token = DiaEspecialService.token_estado('festivo', ANIO)
        self.assertEqual(respuesta.context['token_estado'], token)
        self.assertIn(f'name="token_estado" value="{token}"', respuesta.content.decode())

    def test_el_post_con_token_viejo_no_pisa_el_cambio_ajeno(self):
        # B carga la página.
        pagina_b = self.client.get(f'/turnos/dias-especiales/festivos-mantenimiento-anual/?tipo=festivo&anio={ANIO}')
        token_de_b = pagina_b.context['token_estado']

        # A guarda entretanto y agrega el 24 de marzo.
        DiaEspecialService.guardar_dias_especiales_anual('festivo', ANIO, {1: [1], 3: [24]})
        cache.clear()

        # B envía su formulario, que no incluye el 24 de marzo.
        respuesta = self.client.post('/turnos/dias-especiales/festivos-mantenimiento-anual/', {
            'tipo': 'festivo',
            'anio': ANIO,
            'dias_seleccionados': '{"1": [1], "7": [20]}',
            'token_estado': token_de_b,
        }, follow=True)

        self.assertTrue(DiaEspecial.es_festivo(date(ANIO, 3, 24)))
        self.assertFalse(DiaEspecial.es_festivo(date(ANIO, 7, 20)))
        self.assertContains(respuesta, 'Otra persona modificó')

    def test_el_post_con_token_fresco_guarda(self):
        pagina = self.client.get(f'/turnos/dias-especiales/festivos-mantenimiento-anual/?tipo=festivo&anio={ANIO}')

        self.client.post('/turnos/dias-especiales/festivos-mantenimiento-anual/', {
            'tipo': 'festivo',
            'anio': ANIO,
            'dias_seleccionados': '{"1": [1], "7": [20]}',
            'token_estado': pagina.context['token_estado'],
        })

        self.assertTrue(DiaEspecial.es_festivo(date(ANIO, 7, 20)))

    def test_temporadas_publican_su_propio_token(self):
        respuesta = self.client.get(f'/turnos/dias-especiales/temporadas-anual/?anio={ANIO}')

        self.assertEqual(respuesta.context['token_estado'], TemporadaService.token_estado(ANIO))


class ListadoAdminSinAltasNiBajasTest(TestCase):
    """
    El listado admin solo consulta y edita: dar de baja un día desde una fila suelta,
    sin ver el año, es como se borraban por error días ya trabajados.
    """

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user('admin4', password='x', is_staff=True)
        self.client.force_login(self.admin)
        self.festivo = DiaEspecial.objects.create(fecha=date(ANIO, 1, 6), tipo='festivo')

    def test_no_existe_ruta_de_baja(self):
        from django.urls import NoReverseMatch, reverse

        for nombre in ('dias_especiales_delete', 'dias_especiales_toggle_activo'):
            with self.assertRaises(NoReverseMatch):
                reverse(nombre, args=[self.festivo.pk])

    def test_el_listado_no_ofrece_botones_de_baja(self):
        respuesta = self.client.get(f'/turnos/dias-especiales-admin/?anio={ANIO}')
        html = respuesta.content.decode()

        # Sin la fila en pantalla las aserciones negativas pasarían en vacío.
        self.assertIn(self.festivo, respuesta.context['dias_especiales'])
        self.assertIn('Editar', html)
        self.assertNotIn('toggle-activo', html)
        self.assertNotIn('Eliminar', html)

    def test_desactivar_sigue_siendo_posible_desde_la_edicion(self):
        self.client.post(f'/turnos/dias-especiales-admin/edit/{self.festivo.pk}/', {
            'fecha': self.festivo.fecha.isoformat(),
            'tipo': 'festivo',
            'descripcion': 'x',
        })  # 'activo' ausente = checkbox desmarcado

        self.festivo.refresh_from_db()
        self.assertFalse(self.festivo.activo)
        self.assertFalse(DiaEspecial.es_festivo(self.festivo.fecha))

    def test_la_edicion_avisa_de_que_la_desactivacion_no_es_permanente(self):
        html = self.client.get(f'/turnos/dias-especiales-admin/edit/{self.festivo.pk}/').content.decode()

        self.assertIn('se eliminará definitivamente', html)


class PlantillasSinComentariosFiltradosTest(TestCase):
    """
    Ninguna página puede escupir comentarios de plantilla al usuario.

    `{# ... #}` en Django SOLO vale para una línea: si abarca varias, se renderiza como
    texto. Pasó de verdad — se veían los comentarios en la tabla de días especiales.
    """

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_user('admin6', password='x', is_staff=True)
        self.client.force_login(self.admin)
        self.festivo = DiaEspecial.objects.create(fecha=date(ANIO, 1, 6), tipo='festivo')

    def test_ninguna_pagina_muestra_marcas_de_comentario(self):
        urls = (
            f'/turnos/dias-especiales-admin/?anio={ANIO}',
            f'/turnos/dias-especiales-admin/edit/{self.festivo.pk}/',
            f'/turnos/dias-especiales/visualizar/?anio={ANIO}',
            f'/turnos/dias-especiales/temporadas-anual/?anio={ANIO}',
            f'/turnos/dias-especiales/festivos-mantenimiento-anual/?anio={ANIO}',
            f'/turnos/dias-especiales/festivos-mantenimiento-anual/?tipo=mantenimiento&anio={ANIO}',
        )
        for url in urls:
            html = self.client.get(url).content.decode()
            self.assertNotIn('{#', html, f'comentario de plantilla visible en {url}')
            self.assertNotIn('{%', html, f'etiqueta de plantilla sin procesar en {url}')


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
