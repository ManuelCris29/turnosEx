# -*- coding: utf-8 -*-
"""Tope de duración del rango de un CT PERMANENTE: máximo un año.

Regla de NEGOCIO (no un límite técnico): un cambio permanente más largo que un año no tiene
sentido operativo, y además acota el coste de la búsqueda de compañeros, que evalúa
días × candidatos y crece con el rango.

Se aplica solo al CREAR. Al re-validar para APROBAR se omite: las solicitudes enviadas ANTES de
que existiera el tope no deben quedar inaprobables para siempre.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from solicitudes.services.validators.ct_permanente_validator import (
    CTPermanenteValidator, MAX_DIAS_RANGO_PERMANENTE,
)


class CTPermanenteRangoMaximoTest(TestCase):

    def setUp(self):
        self.inicio = timezone.localdate() + timedelta(days=1)

    def _fin_a(self, dias_totales):
        """fecha_fin tal que el rango (extremos incluidos) dure `dias_totales` días."""
        return self.inicio + timedelta(days=dias_totales - 1)

    def test_un_ano_justo_se_acepta(self):
        """El límite es inclusivo: exactamente un año debe pasar, no quedarse fuera por uno."""
        CTPermanenteValidator.validar_fechas_cambio_permanente(
            self.inicio, self._fin_a(MAX_DIAS_RANGO_PERMANENTE)
        )

    def test_un_dia_mas_de_un_ano_se_rechaza(self):
        with self.assertRaises(ValidationError) as ctx:
            CTPermanenteValidator.validar_fechas_cambio_permanente(
                self.inicio, self._fin_a(MAX_DIAS_RANGO_PERMANENTE + 1)
            )
        self.assertIn('más de un año', str(ctx.exception))

    def test_rango_de_dos_anos_se_rechaza(self):
        with self.assertRaises(ValidationError):
            CTPermanenteValidator.validar_fechas_cambio_permanente(
                self.inicio, self.inicio + timedelta(days=730)
            )

    def test_rango_corto_no_se_toca(self):
        CTPermanenteValidator.validar_fechas_cambio_permanente(
            self.inicio, self.inicio + timedelta(days=30)
        )

    def test_revalidacion_no_aplica_el_tope(self):
        """Una solicitud heredada con rango largo sigue siendo APROBABLE.

        Si el tope se aplicara también al re-validar, las solicitudes enviadas antes de que
        existiera quedarían bloqueadas para siempre en la bandeja del supervisor.
        """
        CTPermanenteValidator.validar_fechas_cambio_permanente(
            self.inicio, self.inicio + timedelta(days=730), es_revalidacion=True
        )

    def test_acepta_fechas_en_texto(self):
        """La validación se llama tanto con `date` como con strings del POST."""
        fin = self._fin_a(MAX_DIAS_RANGO_PERMANENTE + 1)
        with self.assertRaises(ValidationError):
            CTPermanenteValidator.validar_fechas_cambio_permanente(
                self.inicio.strftime('%Y-%m-%d'), fin.strftime('%Y-%m-%d')
            )
