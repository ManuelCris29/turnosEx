"""
Horas a favor del explorador (crédito corporativo).

El sistema de horas nace unidireccional —lo que el explorador debe a la corporación—, pero
la deuda también corre al revés: si su jornada es de 08:00 a 14:00 y el supervisor le pide
entrar a las 07:00, esa hora se la deben. Este servicio es el ledger de esa dirección.

Dos decisiones de negocio que conviene tener a la vista al leer el código:

1. Es una BOLSA, no un ajuste contra una deuda concreta. El crédito se otorga por el hecho
   y sobrevive al pago: si le deben 1 h y solo tiene 0.5 h de deuda, tras saldarla le
   quedan 0.5 h disponibles para la próxima. Por eso `consumir` recorre créditos en FIFO
   en vez de exigir que uno solo cubra el importe.

2. NO toca la sanción. `DeudaCorporativaService.gestionar_sancion_por_deuda` no consulta
   nada de aquí: un mes vencido sigue sancionando aunque se salde con crédito, porque lo
   sancionable es haber dejado vencer el plazo, no el importe.

Convenciones del proyecto que se respetan: `@staticmethod`, `@transaction.atomic` en lo que
escribe y retorno `(objeto, error)` en vez de excepciones.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import models, transaction

from permisos.models import ConsumoCreditoHoras, CreditoHoras

logger = logging.getLogger(__name__)


class CreditoHorasService:
    """Otorga, consume y revierte las horas que la corporación le debe al explorador."""

    @staticmethod
    def creditos_disponibles(explorador):
        """
        Créditos con saldo, en orden de consumo (FIFO por `fecha_hecho`).

        El filtro de saldo va en SQL —`minutos_consumidos < minutos_otorgados`— y no
        recorriendo `minutos_pendientes` en Python: esta consulta la hace la vista de PDH
        en cada carga y no debe traerse el histórico entero para descartarlo después.
        """
        return (
            CreditoHoras.objects
            .filter(explorador=explorador, estado='activo',
                    minutos_consumidos__lt=models.F('minutos_otorgados'))
            .order_by('fecha_hecho', 'id')
        )

    @staticmethod
    def saldo_disponible(explorador) -> int:
        """Minutos totales a favor del explorador."""
        agregado = CreditoHorasService.creditos_disponibles(explorador).aggregate(
            total=models.Sum(models.F('minutos_otorgados') - models.F('minutos_consumidos'))
        )
        return int(agregado['total'] or 0)

    @staticmethod
    def horas_disponibles(explorador) -> float:
        return round(CreditoHorasService.saldo_disponible(explorador) / 60, 2)

    @staticmethod
    @transaction.atomic
    def otorgar(explorador, fecha_hecho, minutos, motivo, otorgado_por):
        """
        Reconoce horas a favor de un explorador. Devuelve (credito, error).

        `minutos` es entero: la conversión desde las horas que teclea el supervisor la hace
        el formulario, para que aquí no dependa de un redondeo de coma flotante.
        """
        motivo = (motivo or '').strip()
        if not motivo:
            return None, 'Escribe el motivo por el que se le deben estas horas.'
        try:
            minutos = int(minutos)
        except (TypeError, ValueError):
            return None, 'Las horas a favor no son un número válido.'

        credito = CreditoHoras(
            explorador=explorador,
            fecha_hecho=fecha_hecho,
            minutos_otorgados=max(0, minutos),
            motivo=motivo,
            otorgado_por=otorgado_por,
            estado='activo',
        )
        try:
            credito.full_clean()
        except ValidationError as e:
            return None, ' '.join(e.messages)
        credito.save()
        logger.info('Crédito de horas %s creado: %s min para el explorador %s (otorga %s)',
                    credito.id, credito.minutos_otorgados, explorador.id, otorgado_por.id)
        return credito, None

    @staticmethod
    @transaction.atomic
    def consumir(pdh, minutos):
        """
        Aplica `minutos` de crédito a un PDH, gastando los créditos más antiguos primero.

        Devuelve (consumos, error). Si error != None no se escribió nada: la comprobación
        del saldo va ANTES de tocar ningún crédito, porque un consumo a medias dejaría
        créditos gastados contra un pago que la vista va a rechazar.

        El crédito es un MEDIO DE PAGO del PDH, no un pago suelto: no puede superar las
        horas que el propio PDH salda, o el consolidado descontaría dos veces lo mismo.
        """
        try:
            minutos = int(minutos)
        except (TypeError, ValueError):
            return None, 'Las horas a favor a aplicar no son un número válido.'
        if minutos <= 0:
            return [], None

        # select_for_update: sin el bloqueo, dos pagos simultáneos pasan ambos la
        # comprobación de saldo y gastan el mismo crédito dos veces.
        creditos = list(
            CreditoHorasService.creditos_disponibles(pdh.explorador).select_for_update()
        )
        disponible = sum(c.minutos_pendientes for c in creditos)
        if minutos > disponible:
            return None, (f'Solo hay {round(disponible / 60, 2)} h a favor disponibles y se '
                          f'han indicado {round(minutos / 60, 2)} h.')

        minutos_pdh = round(float(pdh.horas) * 60)
        if minutos > minutos_pdh:
            return None, (f'Las horas a favor aplicadas ({round(minutos / 60, 2)} h) no pueden '
                          f'superar las {pdh.horas} h que salda este pago.')

        consumos, restante = [], minutos
        for credito in creditos:
            if restante <= 0:
                break
            aplicado = min(restante, credito.minutos_pendientes)
            credito.minutos_consumidos += aplicado
            if credito.minutos_pendientes <= 0:
                credito.estado = 'consumido'
            credito.save(update_fields=['minutos_consumidos', 'estado', 'actualizado_en'])
            consumos.append(
                ConsumoCreditoHoras.objects.create(pdh=pdh, credito=credito, minutos=aplicado)
            )
            restante -= aplicado

        logger.info('PDH %s consume %s min de crédito repartidos en %s crédito(s)',
                    pdh.id, minutos, len(consumos))
        return consumos, None

    @staticmethod
    def revertir_consumos(pdh):
        """
        Devuelve a sus créditos los minutos que este PDH había consumido (al borrarlo).

        Un crédito anulado no revive: se anuló por una corrección administrativa, y
        resucitarlo por borrar un pago le devolvería al explorador horas que ya se decidió
        que no le correspondían. Mismo criterio que las deudas extinguidas por sanción en
        `PagoHorasService.revertir_pago`.
        """
        for detalle in ConsumoCreditoHoras.objects.filter(pdh=pdh).select_related('credito'):
            credito = CreditoHoras.objects.select_for_update().get(id=detalle.credito_id)
            if credito.estado == 'anulado':
                logger.warning('El PDH %s consumía el crédito %s, ya anulado: no se revierte.',
                               pdh.id, credito.id)
                detalle.delete()
                continue
            credito.minutos_consumidos = max(0, credito.minutos_consumidos - detalle.minutos)
            if credito.minutos_pendientes > 0 and credito.estado == 'consumido':
                credito.estado = 'activo'
            credito.save(update_fields=['minutos_consumidos', 'estado', 'actualizado_en'])
            detalle.delete()

    @staticmethod
    @transaction.atomic
    def anular(credito, motivo):
        """
        Deja sin efecto un crédito otorgado por error. Devuelve (credito, error).

        Solo si no se ha consumido nada: con consumos encima habría que deshacer pagos ya
        registrados, y eso es borrar el PDH, no anular el crédito.
        """
        motivo = (motivo or '').strip()
        if not motivo:
            return None, 'Escribe el motivo de la anulación.'
        if credito.minutos_consumidos > 0:
            return None, ('Este crédito ya se aplicó a un pago de horas. Para deshacerlo, '
                          'borra primero ese pago.')
        credito.estado = 'anulado'
        credito.motivo = f'{credito.motivo}\n[ANULADO] {motivo}'
        credito.save(update_fields=['estado', 'motivo', 'actualizado_en'])
        return credito, None
