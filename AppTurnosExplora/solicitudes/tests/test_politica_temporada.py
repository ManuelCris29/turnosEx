"""
POLÍTICA DE TEMPORADA POR FORMULARIO — decisión de negocio fijada en tests.

Son DOS ejes distintos, y conviene no mezclarlos:

1) ¿El formulario puede operar DENTRO de una semana de temporada?
   En temporada la mayoría de los formularios SÍ permiten modificar jornadas. Solo dos la
   rechazan por completo:

    | Formulario            | ¿Permite temporada?   |
    |-----------------------|-----------------------|
    | CT sencillo (1)       | SÍ                    |
    | CT PERMANENTE (2)     | NO                    |
    | DOBLADA (3)           | SÍ                    |
    | D FDS (4)             | N/A (fines de semana) |
    | DOBLADA PERMANENTE (5)| NO                    |
    | CAMBIO DESCANSO (6)   | SÍ (su modalidad entre semana SOLO existe en temporada) |

2) ¿Puede tocar los DOS DÍAS DE DESCANSO que el supervisor fija dentro de esa semana?
   **Solo el formulario 6 (CAMBIO DESCANSO).** Ningún otro, incluidos los que sí permiten
   temporada. Esos dos días son justamente lo que el 6 intercambia, con cinco opciones
   (intercambiar el día, jornadas partidas, que me cubran mi día, cambio de doblada, permiso
   de media jornada) y con la obligación de compensar EN LA MISMA SEMANA — algo que una
   doblada, que paga en cualquier fecha, no garantiza.

   Ojo al alcance: esto veta dos fechas por semana, NO la temporada entera. DOBLADA sigue
   pudiendo operar en el resto de días de una semana de temporada.

   El predicado único es `DescansoSemanaService.es_dia_descanso_temporada(fecha)`. NO sirve
   `DiaEspecial.es_temporada_en` / `es_temporada`: ese marca la SEMANA, y hay días de descanso
   fijados en fechas sin ese marcador (07/08/2026: `_dia_calendario_no_apto(2026-09-15)`
   devolvía None sobre un día que sí era descanso fijado).

Esto se fija aquí porque es una decisión de negocio que el código reparte entre el front (el
flag `permitirTemporada` del datepicker) y el backend (una regla de calendario explícita), y
NADA obligaba a que ambos lados coincidieran. Si alguien cambia un lado y no el otro, la
incoherencia vivía en producción sin dar error.

Contexto imprescindible: `TurnoService.estado_dia` NO delata los días de temporada al
explorador que conserva su jornada (le devuelve `fuente='base'`), así que un formulario que
quiera rechazar temporada NO puede hacerlo mirando `fuente`. Análisis completo en
`docs/05-referencia/turnos/PUNTO_CIEGO_TEMPORADA_ESTADO_DIA.md`.
"""
import re
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from turnos.models import DiaEspecial
from turnos.services.turno_service import TurnoService

from .test_doblada_permanente import DobladaPermanenteBaseTest

JS_DIR = Path(settings.BASE_DIR) / 'static' / 'js' / 'cambio-turno'

# Formularios cuyo datepicker DEBE dejar elegir días de temporada, y el archivo que lo declara.
PERMITEN_TEMPORADA = {
    'CT sencillo': 'solicitar_cambio_turno.js',
    'DOBLADA': 'solicitar_doblada.js',
}
# Formularios cuyo datepicker DEBE bloquearlos.
RECHAZAN_TEMPORADA = {
    'DOBLADA PERMANENTE': 'solicitar_doblada_permanente.js',
    'CT PERMANENTE': 'solicitar_ct_permanente.js',
}


class PoliticaTemporadaFrontTest(TestCase):
    """El calendario de cada formulario declara su política; aquí se fija cuál es."""

    def _flags(self, archivo):
        """
        Valores de `permitirTemporada` declarados en el archivo, en orden.

        Se devuelven TODOS (no se busca una subcadena suelta) porque un formulario puede tener
        VARIOS datepickers —doblada tiene dos, cesión y pago— y comprobar solo que `true`
        aparece "en algún sitio" dejaba pasar que a uno de ellos le cambiaran la política.
        Además así el fallo dice qué se encontró, en vez de volcar el archivo entero.
        """
        ruta = JS_DIR / archivo
        self.assertTrue(ruta.exists(), f'no se encontró {ruta}')
        return re.findall(r'permitirTemporada:\s*(true|false)',
                          ruta.read_text(encoding='utf-8'))

    def test_los_que_permiten_temporada_lo_declaran(self):
        for etiqueta, archivo in PERMITEN_TEMPORADA.items():
            with self.subTest(formulario=etiqueta):
                flags = self._flags(archivo)
                self.assertTrue(
                    flags,
                    f'{etiqueta} ({archivo}) ya no declara permitirTemporada: si el datepicker '
                    f'cambió, esta política hay que revisarla a mano.',
                )
                self.assertEqual(
                    set(flags), {'true'},
                    f'{etiqueta} permite temporada, pero {archivo} declara {flags}. Si el '
                    f'cambio es deliberado, el backend debe rechazar la temporada POR REGLA '
                    f'(no con estado_dia["fuente"], que no la delata) y hay que actualizar '
                    f'esta política y PUNTO_CIEGO_TEMPORADA_ESTADO_DIA.md.',
                )

    def test_los_que_rechazan_temporada_no_la_habilitan(self):
        for etiqueta, archivo in RECHAZAN_TEMPORADA.items():
            with self.subTest(formulario=etiqueta):
                ruta = JS_DIR / archivo
                self.assertIn(
                    'bloquearDiasEspeciales: true', ruta.read_text(encoding='utf-8'),
                    f'{etiqueta} debe bloquear los días especiales en su calendario',
                )
                self.assertNotIn(
                    'true', self._flags(archivo),
                    f'{etiqueta} NO permite temporada: habilitarla en el calendario '
                    f'contradice la regla del backend y ofrecería días que luego se rechazan.',
                )


class PoliticaTemporadaBackendTest(DobladaPermanenteBaseTest):
    """
    El front es solo la primera capa (no cubre un POST directo). Los dos formularios que
    rechazan temporada deben hacerlo también en el backend, y POR REGLA de calendario.
    """

    def setUp(self):
        super().setUp()
        self.dia_temporada = self.lunes + timedelta(days=1)
        DiaEspecial.objects.create(
            fecha=self.dia_temporada, tipo='temporada', es_temporada=True, activo=True,
        )

    def test_doblada_permanente_rechaza_temporada_por_regla(self):
        from solicitudes.services.ct_permanente_helper import (
            _dia_calendario_no_apto,
            jornada_doblada_perm,
        )
        self.assertEqual(_dia_calendario_no_apto(self.dia_temporada), 'temporada')
        self.assertIsNone(
            jornada_doblada_perm(self.solicitante, self.dia_temporada),
            'un día de temporada no puede ofrecerse como doblable',
        )

    def test_ct_permanente_rechaza_temporada_por_regla(self):
        from solicitudes.services.ct_permanente_helper import (
            razones_exclusion_ct_permanente,
        )
        razones = razones_exclusion_ct_permanente(self.dia_temporada, self.solicitante)
        self.assertIn('Temporada', razones)

    def test_dia_de_descanso_fijado_no_necesita_el_marcador_de_semana(self):
        """
        Los dos ejes son conjuntos DISTINTOS: hay días de descanso fijados en fechas sin el
        marcador `DiaEspecial.es_temporada`. Por eso la regla no puede apoyarse en `es_temporada`.
        """
        from turnos.models import DescansoSemanaManual, Jornada
        from turnos.services.descanso_semana_service import DescansoSemanaService

        suelto = self.lunes + timedelta(days=2)
        self.assertFalse(
            DiaEspecial.objects.filter(fecha=suelto, es_temporada=True).exists(),
            'la fecha de prueba no debe tener el marcador de semana de temporada',
        )
        DescansoSemanaManual.objects.create(
            fecha=suelto, jornada=Jornada.objects.get(nombre='AM'),
            motivo='temporada', activo=True,
        )
        self.assertTrue(DescansoSemanaService.es_dia_descanso_temporada(suelto))

    def test_solo_cambio_descanso_puede_tocar_los_dias_de_descanso_fijados(self):
        """
        REGLA DE NEGOCIO: esos dos días son del formulario 6. Se comprueba en los tres caminos
        que antes llegaban a ellos (DOBLADA, CT PERMANENTE y DOBLADA PERMANENTE).
        """
        from solicitudes.services.ct_permanente_helper import (
            _dia_calendario_no_apto,
            razones_exclusion_ct_permanente,
        )
        from turnos.models import DescansoSemanaManual, Jornada

        dia = self.lunes + timedelta(days=2)
        DescansoSemanaManual.objects.create(
            fecha=dia, jornada=Jornada.objects.get(nombre='AM'),
            motivo='temporada', activo=True,
        )

        # DOBLADA PERMANENTE y CT PERMANENTE comparten la regla de calendario.
        self.assertEqual(_dia_calendario_no_apto(dia), 'temporada')
        self.assertIn('Temporada', razones_exclusion_ct_permanente(dia, self.solicitante))

        # DOBLADA: rechaza tanto si el día es la cesión como si es el pago.
        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy
        otro = dia + timedelta(days=1)
        for fc, fp in ((dia, otro), (otro, dia)):
            ok, msg = DobladaStrategy().validar_solicitud({
                'explorador_solicitante': self.solicitante,
                'explorador_receptor': self.receptor,
                'fecha_cambio_turno': fc.strftime('%Y-%m-%d'),
                'fecha_pago': fp.strftime('%Y-%m-%d'),
                'tipo_cesion': 'cesion_completa',
                'comentario': 'politica',
            })
            self.assertFalse(ok, f'DOBLADA no puede usar {dia} (cesion={fc}, pago={fp})')
            self.assertIn('Cambio de Día de Descanso', str(msg),
                          'el rechazo debe redirigir al formulario que sí puede hacerlo')

    def test_la_doblada_sigue_permitiendo_el_resto_de_la_temporada(self):
        """
        Contrapeso del test anterior: el veto es de DOS FECHAS, no de la temporada entera.
        Si alguien lo convierte en un veto general, esto falla.
        """
        from solicitudes.services.strategies.doblada_strategy import DobladaStrategy

        # `self.dia_temporada` tiene el marcador de SEMANA pero no es descanso fijado.
        ok, msg = DobladaStrategy().validar_solicitud({
            'explorador_solicitante': self.solicitante,
            'explorador_receptor': self.receptor,
            'fecha_cambio_turno': self.dia_temporada.strftime('%Y-%m-%d'),
            'fecha_pago': (self.dia_temporada + timedelta(days=1)).strftime('%Y-%m-%d'),
            'tipo_cesion': 'cesion_completa',
            'comentario': 'politica',
        })
        self.assertNotIn(
            'día de descanso de temporada', str(msg),
            'un día de temporada que NO es descanso fijado no debe rechazarse por esta regla',
        )

    def test_estado_dia_NO_delata_la_temporada(self):
        """
        Fija el punto ciego como comportamiento CONOCIDO, no como accidente.

        No es el comportamiento deseable, pero hoy no rompe nada (§3 del documento) y cambiarlo
        toca "Mis Turnos" y todo lo que cuelga. Si algún día se arregla, este test fallará: es
        la señal para releer PUNTO_CIEGO_TEMPORADA_ESTADO_DIA.md y decidir a conciencia, no
        para 'ajustar el test'.
        """
        estado = TurnoService.estado_dia(self.solicitante, self.dia_temporada)
        if estado['jornada'] in ('AM', 'PM'):
            self.assertEqual(
                estado['fuente'], 'base',
                'Si esto ya no es "base", la capa L4 cambió: revisa '
                'docs/05-referencia/turnos/PUNTO_CIEGO_TEMPORADA_ESTADO_DIA.md antes de seguir.',
            )
            self.assertNotEqual(
                estado['fuente'], 'temporada',
                'un formulario NO puede detectar la temporada con fuente == "temporada"',
            )
